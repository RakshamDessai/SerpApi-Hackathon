"""Planner: the credit economy.

The budget cap is a safety property - a bug here can drain a monthly quota in
one click - so it is tested as hard as the scorer.
"""

from __future__ import annotations

import pytest

from s2s.mesh import adapters as registry
from s2s.mesh import affinity, planner
from s2s.models import Competency, Discipline


def _competency(name, disciplines, aliases=None, bloom=4):
    return Competency(
        canonical=name,
        aliases=aliases or [f"{name} alias one", f"{name} alias two"],
        tools=[],
        disciplines=disciplines,
        bloom=bloom,
        band="intermediate",
        source_unit=f"Unit {name}",
        source_span=name,
    )


FINANCE = [_competency(f"finance{i}", [Discipline.COMMERCE_FINANCE]) for i in range(5)]
DESIGN = [_competency(f"design{i}", [Discipline.DESIGN_VISUAL]) for i in range(5)]
CS = [_competency(f"cs{i}", [Discipline.CS_SOFTWARE]) for i in range(5)]


# ------------------------------------------------------------ budget cap ---

@pytest.mark.parametrize("cap", [1, 2, 5, 10, 12, 40])
def test_plan_never_exceeds_the_credit_cap(cap):
    dorks = planner.plan(FINANCE, credit_cap=cap, max_platforms=5, terms_per_dork=3)
    assert len(dorks) <= cap


def test_plan_respects_max_platforms():
    dorks = planner.plan(FINANCE, credit_cap=50, max_platforms=3, terms_per_dork=3)
    assert len({d.adapter_key for d in dorks}) <= 3


def test_empty_competencies_plans_nothing():
    assert planner.plan([], credit_cap=10) == []


def test_breadth_before_depth_under_a_tight_cap():
    """With only 3 credits the student should see 3 different platforms, not
    3 searches against one."""
    dorks = planner.plan(FINANCE, credit_cap=3, max_platforms=5, terms_per_dork=2)
    assert len({d.adapter_key for d in dorks}) == len(dorks)


# -------------------------------------------------------------- packing ---

def test_pack_covers_every_competency_exactly_once():
    groups = planner.pack(FINANCE, per_group=3)
    packed = [c for group in groups for c in group]
    assert sorted(c.canonical for c in packed) == sorted(c.canonical for c in FINANCE)


def test_pack_reduces_search_count():
    unpacked = len(FINANCE)
    packed = len(planner.pack(FINANCE, per_group=3))
    assert packed < unpacked


def test_phrases_are_capped_and_deduplicated():
    duplicated = [
        _competency("a", [Discipline.COMMERCE_FINANCE], aliases=["same phrase"]),
        _competency("b", [Discipline.COMMERCE_FINANCE], aliases=["same phrase"]),
    ]
    phrases = planner.phrases_for(duplicated)
    assert len(phrases) == len(set(p.lower() for p in phrases))
    assert len(phrases) <= planner.MAX_PHRASES_PER_DORK


def test_phrases_prefer_market_aliases_over_the_unit_title():
    """The canonical name is usually the unit heading - academic language that
    appears in no real brief."""
    competency = _competency(
        "Brand Identity Systems", [Discipline.DESIGN_VISUAL],
        aliases=["logo design", "brand guidelines"],
    )
    phrases = planner.phrases_for([competency])
    assert phrases[0] == "logo design"
    assert "Brand Identity Systems" not in phrases[:2]


# ------------------------------------------------------------- affinity ---

def test_design_student_is_not_sent_to_kaggle():
    keys = {a.key for a, _ in planner.choose_platforms(DESIGN, max_platforms=5)}
    assert "kaggle" not in keys
    assert "drivendata" not in keys


def test_cs_student_gets_github_and_hackathons():
    keys = {a.key for a, _ in planner.choose_platforms(CS, max_platforms=5)}
    assert "github" in keys
    assert keys & {"devpost", "devfolio"}


def test_finance_student_gets_ngo_and_competition_boards():
    keys = {a.key for a, _ in planner.choose_platforms(FINANCE, max_platforms=5)}
    assert "catchafire" in keys
    assert "unstop" in keys


def test_one_weak_secondary_discipline_cannot_dominate():
    """A stray tag ('classification of typefaces' -> data science) must not pull
    a data platform into a design student's plan."""
    mixed = DESIGN[:4] + [
        _competency("stray", [Discipline.DESIGN_VISUAL, Discipline.DATA_QUANT])
    ]
    keys = {a.key for a, _ in planner.choose_platforms(mixed, max_platforms=5)}
    assert "kaggle" not in keys


def test_profile_shares_sum_to_one():
    profile = affinity.discipline_profile(FINANCE + DESIGN)
    assert sum(profile.values()) == pytest.approx(1.0)


def test_naive_cost_is_larger_than_the_plan():
    dorks = planner.plan(FINANCE, credit_cap=20, max_platforms=5, terms_per_dork=3)
    assert planner.naive_cost(FINANCE) > len(dorks)


def test_tier_c_excluded_unless_requested():
    without = {a.key for a, _ in planner.choose_platforms(DESIGN, 8, include_tier_c=False)}
    with_c = {a.key for a, _ in planner.choose_platforms(DESIGN, 8, include_tier_c=True)}
    tier_c = {a.key for a in registry.all_adapters() if a.trust == "C"}
    assert not (without & tier_c)
    assert with_c & tier_c


# ------------------------------------------- stream override (2026-10-09) ---

def test_stream_override_changes_platform_selection():
    """The UI's Stream dropdown was collected and never used. It must now
    actually promote the chosen discipline, because keyword detection is good
    but the student knows their own course better."""
    from s2s.config import Settings
    from s2s.ingest import loader
    from s2s import pipeline
    from s2s.config import FIXTURE_DIR

    settings = Settings.load()
    settings.demo_mode = True

    syllabus = loader.from_fixture(
        FIXTURE_DIR / "syllabi" / "du_bcom_sem3_financial_management.txt"
    )

    detected = pipeline.run(syllabus, settings, semester=3)
    forced = pipeline.run(
        syllabus, settings, semester=3, stream=Discipline.CS_SOFTWARE
    )

    assert all(
        c.disciplines[0] is Discipline.CS_SOFTWARE for c in forced.competencies
    )
    detected_platforms = {d.adapter_key for d in detected.dorks}
    forced_platforms = {d.adapter_key for d in forced.dorks}
    assert detected_platforms != forced_platforms, "override had no effect"
    assert "github" in forced_platforms


# --------------------------------------------- keyword dorks (2026-10-10) ---

def test_keyword_prefers_the_phrase_the_group_shares():
    """One plain-keyword search should still serve several units at once."""
    group = [
        _competency("capital", [Discipline.COMMERCE_FINANCE],
                    aliases=["cost of equity", "financial model"], bloom=5),
        _competency("budgeting", [Discipline.COMMERCE_FINANCE],
                    aliases=["NPV analysis", "financial model"], bloom=4),
    ]
    assert planner.keyword_for(group) == "financial model"


def test_keyword_falls_back_to_the_strongest_phrase():
    group = [
        _competency("a", [Discipline.CS_SOFTWARE], aliases=["concurrency"], bloom=5),
        _competency("b", [Discipline.CS_SOFTWARE], aliases=["database schema"], bloom=3),
    ]
    assert planner.keyword_for(group) == "concurrency"


def test_keyword_dorks_are_plain_and_or_group_dorks_are_packed():
    dorks = planner.plan(FINANCE + CS[:1], credit_cap=20, max_platforms=6)
    for dork in dorks:
        adapter = registry.get(dork.adapter_key)
        if adapter.query_style == "keywords":
            assert " OR " not in dork.query, dork.query
        else:
            assert " OR " in dork.query, dork.query


def test_groups_never_repeat_a_keyword():
    """Both B.Com groups once picked "financial model": the same query twice."""
    shared = ["financial model", "budget"]
    group_a = [_competency(f"a{i}", [Discipline.COMMERCE_FINANCE], aliases=shared + [f"a{i}"])
               for i in range(3)]
    group_b = [_competency(f"b{i}", [Discipline.COMMERCE_FINANCE], aliases=shared + [f"b{i}"])
               for i in range(3)]
    dorks = planner.plan(group_a + group_b, credit_cap=40, max_platforms=6, terms_per_dork=3)
    queries = [d.query for d in dorks]
    assert len(queries) == len(set(queries)), queries


def test_disabled_adapters_are_never_planned():
    assert not registry.get("unv").enabled_by_default
    assert "unv" not in {a.key for a in registry.active()}
    assert "unv" not in {a.key for a in registry.active(include_tier_c=True)}
