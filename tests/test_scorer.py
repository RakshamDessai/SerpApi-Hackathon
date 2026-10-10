"""Scoring: each term independently, then the composite.

This is the deterministic core of the product, so it carries the most tests.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from s2s.models import Competency, Discipline, RawResult, ScoreBreakdown
from s2s.score import scorer, signals


def _result(title="", snippet="", adapter_key="unv", posted_at=None):
    return RawResult(
        title=title, url="https://www.onlinevolunteering.org/en/opportunity/x",
        snippet=snippet, adapter_key=adapter_key, posted_at=posted_at,
    )


# ----------------------------------------------------------- semantic ------

def test_semantic_title_match_beats_body_match(competency):
    in_title = _result(title="cash flow forecast wanted", snippet="")
    in_body = _result(title="Volunteer needed", snippet="cash flow forecast wanted")
    assert scorer.semantic(competency, in_title) > scorer.semantic(competency, in_body)


def test_semantic_zero_when_nothing_matches(competency):
    assert scorer.semantic(competency, _result("Dog walking", "Walk dogs")) == 0.0


def test_semantic_is_capped_at_one(competency):
    spammy = _result(
        title="cash flow forecast working capital liquidity analysis",
        snippet="cash flow forecast working capital liquidity analysis Excel",
    )
    assert scorer.semantic(competency, spammy) == 1.0


def test_semantic_credits_tool_mentions(competency):
    without = _result(title="Budget help", snippet="Prepare a budget")
    with_tool = _result(title="Budget help", snippet="Prepare a budget in Excel")
    assert scorer.semantic(competency, with_tool) > scorer.semantic(competency, without)


# -------------------------------------------------------------- level ------

@pytest.mark.parametrize(
    "band, snippet, expected",
    [
        ("intermediate", "ordinary volunteer task", 1.0),       # intermediate vs intermediate
        ("beginner", "good first issue for newcomers", 1.0),    # beginner vs beginner
        ("beginner", "senior expert with 8+ years", 0.0),       # two bands apart
        ("advanced", "good first issue", 0.0),
    ],
)
def test_level_fit(competency, band, snippet, expected):
    graded = Competency(**{**competency.__dict__, "band": band})
    assert scorer.level(graded, _result(snippet=snippet)) == pytest.approx(expected)


# ---------------------------------------------------------- freshness ------

def test_freshness_decays_with_age(now):
    today = scorer.freshness(_result(posted_at=now), now=now)
    last_week = scorer.freshness(_result(posted_at=now - timedelta(days=7)), now=now)
    last_year = scorer.freshness(_result(posted_at=now - timedelta(days=365)), now=now)
    assert today == pytest.approx(1.0)
    assert 0.0 < last_year < last_week < today


def test_unknown_date_is_penalised_not_zeroed(now):
    """Most site: dork results carry no date. Zeroing them would sink every NGO
    brief below every hackathon; 1.0 would be dishonest."""
    unknown = scorer.freshness(_result(posted_at=None), now=now)
    assert unknown == pytest.approx(scorer.UNKNOWN_DATE_PENALTY)
    assert 0.0 < unknown < 1.0


# ------------------------------------------------------ actionability ------

def test_archived_scores_zero_on_the_verdict_component():
    live = scorer.actionability(_result(snippet="prepare a report"), "live")
    archived = scorer.actionability(_result(snippet="prepare a report"), "archived")
    assert archived == pytest.approx(live - 0.5)


def test_deliverable_noun_raises_actionability():
    vague = scorer.actionability(_result(snippet="help us out sometime"), "live")
    concrete = scorer.actionability(_result(snippet="produce a budget report"), "live")
    assert concrete > vague


def test_trust_tier_affects_actionability():
    tier_a = scorer.actionability(_result(snippet="a report", adapter_key="unv"), "live")
    tier_c = scorer.actionability(_result(snippet="a report", adapter_key="upwork"), "live")
    assert tier_a > tier_c


# -------------------------------------------------------- composite --------

def test_weights_sum_to_one():
    assert sum(scorer.WEIGHTS.values()) == pytest.approx(1.0)


def test_composite_matches_the_documented_worked_example():
    """BUILD_PLAN.md section 9.5 shows 0.92/0.85/0.71/0.90 -> 87."""
    breakdown = ScoreBreakdown(0.92, 0.85, 0.71, 0.90, scorer.WEIGHTS)
    assert breakdown.total == 87


def test_explain_contributions_sum_to_total():
    breakdown = ScoreBreakdown(0.8, 0.6, 0.4, 0.9, scorer.WEIGHTS)
    total = sum(points for _, _, points in breakdown.explain())
    assert total == pytest.approx(breakdown.total, abs=0.5)


def test_build_opportunities_ranks_live_above_archived(competency, fresh_result, now):
    stale = _result(title="cash flow forecast", snippet="cash flow forecast")
    graded = [(stale, "archived", None), (fresh_result, "live", now)]
    out = scorer.build_opportunities(graded, [competency], now=now)
    assert [o.verdict for o in out] == ["live", "archived"]


def test_build_opportunities_picks_the_best_competency(fresh_result, now):
    finance = Competency(
        canonical="Cash flow", aliases=["cash flow forecast"], tools=[],
        disciplines=[Discipline.COMMERCE_FINANCE], bloom=4, band="beginner",
        source_unit="U3", source_span="x",
    )
    unrelated = Competency(
        canonical="Typography", aliases=["font pairing"], tools=[],
        disciplines=[Discipline.DESIGN_VISUAL], bloom=4, band="beginner",
        source_unit="U1", source_span="y",
    )
    out = scorer.build_opportunities(
        [(fresh_result, "live", now)], [unrelated, finance], now=now
    )
    assert out[0].matched_competency.canonical == "Cash flow"


def test_scam_listings_are_dropped(competency, now):
    scam = _result(title="cash flow forecast", snippet="pay to apply, registration fee")
    out = scorer.build_opportunities([(scam, "live", now)], [competency], now=now)
    assert out == []


# ---------------- exclusions, from real Google Jobs results (2026-10-10) ----

def _jobs_result(title, snippet):
    return RawResult(title=title, url="https://example.org/job", snippet=snippet,
                     adapter_key="gjobs")


@pytest.mark.parametrize("title,snippet,reason", [
    ("Concurrency roles for SPPU talent",
     "Recruit Concurrency professionals from SPPU, Pune. 470+ recruiters, "
     "90% placement rate. Post a role on CosmoQuick.",
     "employer-facing ad, not a listing"),
    ("Senior Database Performance & Benchmark Engineer (Bengaluru)",
     "Responsible for designing and executing rigorous testing strategies.",
     "senior role"),
    ("Snowflake + SQL (Advanced) - Technical Lead/Technical Specialist",
     "Job ID: 887412 - 5 - 15 Years - 1 Opening", "senior role"),
    ("SQL Data Engineer", "Requires 5 - 15 Years of hands-on work.",
     "needs years of experience"),
    ("Komplet ansigtsgenkendelse ved hjaelp af SQL-database Projekt",
     "Byg et komplet ansigtsgenkendelsessystem med Python og SQL, der registrerer, "
     "koder og lagrer ansigtsdata til genkendelse og administration i realtid.",
     "not in English"),
])
def test_out_of_reach_listings_are_excluded(title, snippet, reason):
    assert signals.exclusion_reason(_jobs_result(title, snippet)) == reason


@pytest.mark.parametrize("title,snippet", [
    ("SQL Developer Fresher Interns (Bengaluru)",
     "The SQL MySQL Developer plays a crucial role in the design, development, "
     "and maintenance of databases, as well as the optimization of SQL queries."),
    # "lead" in the body is usually the client, not the role
    ("Build a dashboard for a literacy NGO",
     "Our programme lead needs a volunteer to build a 12 month budget dashboard."),
    ("SQL Mania - 2026", "Competition"),
])
def test_student_level_listings_are_kept(title, snippet):
    assert signals.exclusion_reason(_jobs_result(title, snippet)) is None


def test_phd_roles_are_out_of_reach():
    result = _jobs_result("PhD Intern - Machine Learning Researcher", "Join our lab.")
    assert signals.exclusion_reason(result) == "needs a PhD"


def test_c_suite_volunteer_titles_are_out_of_reach():
    result = _jobs_result("Chief Financial Officer - Volunteer Opportunity", "Help us.")
    assert signals.exclusion_reason(result) == "senior role"


# ------------------------------------------------- platform diversity ------

def _opp(key, score, verdict="unverified"):
    from s2s.models import Opportunity
    breakdown = ScoreBreakdown(semantic=score, level=0, freshness=0, actionability=0,
                               weights={"semantic": 1.0, "level": 0, "freshness": 0,
                                        "actionability": 0})
    return Opportunity(title=f"{key}{score}", url=f"https://{key}.org/{score}", snippet="",
                       adapter_key=key, matched_competency=None, score=breakdown,
                       verdict=verdict)


def test_one_platform_cannot_take_over_the_top_ten():
    """15 near-equal Scholar papers must not bury a comparable volunteer role."""
    ranked = [_opp("scholar", 0.70 - i / 1000) for i in range(15)] + [_opp("idealist", 0.62)]
    keys = [o.adapter_key for o in scorer.diversify(ranked)][:10]
    assert keys[:3] == ["scholar"] * 3 and keys[3] == "idealist"


def test_diversity_does_not_promote_a_much_weaker_match():
    ranked = [_opp("idealist", 0.70 - i / 1000) for i in range(5)] + [_opp("catchafire", 0.30)]
    keys = [o.adapter_key for o in scorer.diversify(ranked)]
    assert keys == ["idealist"] * 5 + ["catchafire"]


def test_diversity_never_drops_and_never_promotes_archived():
    ranked = [_opp("a", 0.9, "live")] * 5 + [_opp("b", 0.85, "archived")]
    out = scorer.diversify(ranked)
    assert len(out) == len(ranked)
    assert [o.verdict for o in out] == ["live"] * 5 + ["archived"]


def test_unverifiable_platform_can_join_a_crowded_live_top_ten():
    """Kaggle can never be verified; 11 live job cards must not bury it."""
    ranked = [_opp("gjobs", 0.80 - i / 1000, "live") for i in range(11)] \
        + [_opp("kaggle", 0.74, "unverified")]
    keys = [o.adapter_key for o in scorer.diversify(ranked)][:10]
    assert keys[:3] == ["gjobs"] * 3 and keys[3] == "kaggle"
