"""Stage 6: bridge, blueprint and proof-of-work export.

The bridge carries the project's most dangerous claim - that a specific unit of
the student's own syllabus qualifies them - so verbatim quoting is tested hard.
"""

from __future__ import annotations

import pytest

from s2s.models import (
    Competency,
    Discipline,
    Opportunity,
    ScoreBreakdown,
)
from s2s.score.scorer import WEIGHTS
from s2s.ship import blueprint as blueprint_module
from s2s.ship import bridge as bridge_module
from s2s.ship import export, prepare

SPAN = (
    "Operating cycle and cash conversion cycle. Estimation of working capital "
    "requirements for a manufacturing firm."
)


def _opportunity(discipline=Discipline.COMMERCE_FINANCE, organization="Health Access",
                 adapter_key="unv", tools=("Excel", "Google Sheets")):
    competency = Competency(
        canonical="Working Capital Management",
        aliases=["cash flow forecast", "liquidity analysis"],
        tools=list(tools),
        disciplines=[discipline],
        bloom=4,
        band="intermediate",
        source_unit="Unit 3: Working Capital Management",
        source_span=SPAN,
        span_offset=0,
    )
    return Opportunity(
        title="Build a cash flow forecast for a community clinic",
        url="https://www.onlinevolunteering.org/en/opportunity/abc",
        snippet="A non-profit needs a 12 month budget and cash flow forecast.",
        adapter_key=adapter_key,
        matched_competency=competency,
        score=ScoreBreakdown(0.8, 0.9, 0.7, 0.8, WEIGHTS),
        verdict="live",
        organization=organization,
        est_hours=(8, 15),
    )


# ---------------------------------------------------------------- bridge ---

def test_template_bridge_quotes_the_syllabus_verbatim():
    result = bridge_module.template_bridge(_opportunity())
    assert result.mode == "template"
    assert bridge_module.quotes_syllabus(result.text, SPAN)


def test_bridge_names_the_source_unit():
    result = bridge_module.template_bridge(_opportunity())
    assert "Unit 3: Working Capital Management" in result.text


def test_bridge_mentions_the_student_tools():
    result = bridge_module.template_bridge(_opportunity())
    assert "Excel" in result.text


def test_bridge_handles_a_competency_with_no_tools():
    result = bridge_module.template_bridge(_opportunity(tools=()))
    assert result.text
    assert bridge_module.quotes_syllabus(result.text, SPAN)


def test_quotes_syllabus_rejects_a_paraphrase():
    """The guard that stops a fabricated claim about the student's syllabus."""
    paraphrase = (
        "Your unit covers business cycles and estimating how much money a firm "
        "needs to operate, which is broadly relevant here."
    )
    assert not bridge_module.quotes_syllabus(paraphrase, SPAN)


def test_quotes_syllabus_accepts_a_long_literal_run():
    quoting = f'Your syllabus says "{SPAN[:80]}" and that is exactly this brief.'
    assert bridge_module.quotes_syllabus(quoting, SPAN)


def test_build_without_a_key_uses_the_template():
    result = bridge_module.build(_opportunity(), api_key=None, syllabus_text="")
    assert result.mode == "template"


def test_long_spans_are_trimmed_but_still_quoted():
    long_span = SPAN * 5
    opportunity = _opportunity()
    opportunity.matched_competency = Competency(
        **{**opportunity.matched_competency.__dict__, "source_span": long_span}
    )
    result = bridge_module.template_bridge(opportunity)
    assert len(result.quoted_span) <= 230
    assert bridge_module.quotes_syllabus(result.text, long_span)


# ------------------------------------------------------------- blueprint ---

@pytest.mark.parametrize("discipline", list(Discipline))
def test_every_discipline_gets_a_three_phase_blueprint(discipline):
    plan = blueprint_module.build(_opportunity(discipline=discipline))
    assert plan.setup and plan.execution and plan.delivery
    assert plan.toolkit


def test_blueprint_leads_with_the_students_own_tools():
    plan = blueprint_module.build(_opportunity())
    assert "Excel" in plan.setup[0]


def test_blueprint_falls_back_to_generic_tools():
    plan = blueprint_module.build(_opportunity(tools=()))
    assert plan.toolkit == blueprint_module.TOOLKIT_FALLBACK


def test_finance_blueprint_warns_about_hardcoded_formulas():
    plan = blueprint_module.build(_opportunity(Discipline.COMMERCE_FINANCE))
    assert any("hard-code" in p.lower() for p in plan.pitfalls)


def test_cs_blueprint_tells_the_student_to_claim_the_issue():
    plan = blueprint_module.build(_opportunity(Discipline.CS_SOFTWARE))
    assert any("claim" in step.lower() for step in plan.setup)


def test_data_blueprint_warns_about_leakage():
    plan = blueprint_module.build(_opportunity(Discipline.DATA_QUANT))
    assert any("leakage" in p.lower() for p in plan.pitfalls)


# ---------------------------------------------------------------- export ---

def test_star_bullet_is_past_tense_and_names_the_organisation():
    bullet = export.star_bullet(_opportunity())
    assert bullet.startswith("Delivered")
    assert "Health Access" in bullet
    assert bullet.endswith(".")


def test_star_bullet_does_not_repeat_the_platform_when_org_is_unknown():
    bullet = export.star_bullet(_opportunity(organization=None))
    assert bullet.count("UN Online Volunteering") == 1


def test_star_bullet_varies_by_ecosystem():
    ngo = export.star_bullet(_opportunity(adapter_key="unv"))
    code = export.star_bullet(_opportunity(adapter_key="github"))
    assert ngo != code
    assert code.startswith("Contributed")


def test_case_study_is_written_in_first_person():
    """It is the student's own portfolio page, not advice addressed to them."""
    markdown = export.case_study_markdown(_opportunity())
    assert "my syllabus" in markdown
    assert "your syllabus" not in markdown.lower()


def test_case_study_contains_the_verbatim_span_and_link():
    opportunity = _opportunity()
    markdown = export.case_study_markdown(opportunity)
    assert " ".join(SPAN.split()) in markdown
    assert opportunity.url in markdown


def test_case_study_includes_the_blueprint_when_present():
    opportunity = prepare(_opportunity(), api_key=None)
    markdown = export.case_study_markdown(opportunity, opportunity.bridge)
    assert "## How I delivered it" in markdown
    assert "### Setup" in markdown


def test_filename_is_slugified():
    name = export.filename_for(_opportunity())
    assert name.endswith(".md")
    assert " " not in name
    assert "--" not in name


# ------------------------------------------------------------ dispatcher ---

def test_ship_fills_every_field():
    opportunity = prepare(_opportunity(), api_key=None)
    assert opportunity.bridge
    assert opportunity.blueprint is not None
    assert opportunity.star_bullet


def test_ship_is_idempotent():
    opportunity = prepare(_opportunity(), api_key=None)
    first = opportunity.bridge
    prepare(opportunity, api_key=None)
    assert opportunity.bridge == first


# ------------------------------------------------- regressions (2026-10-08) ---

def test_reflowed_whitespace_is_not_treated_as_paraphrase():
    """A span containing a newline is still verbatim once reflowed.

    The first validator compared raw strings, so every multi-line span failed
    and honest bridges were rejected.
    """
    span = "Operating cycle and cash conversion cycle.\nEstimation of working capital."
    quoting = (
        'Your syllabus says "Operating cycle and cash conversion cycle. '
        'Estimation of working capital." which is exactly this brief.'
    )
    assert bridge_module.quotes_syllabus(quoting, span)


def test_invented_content_is_still_rejected_after_whitespace_relaxation():
    span = "Operating cycle and cash conversion cycle.\nEstimation of working capital."
    invented = (
        "Your syllabus covers advanced derivatives pricing and stochastic "
        "volatility modelling, which prepares you for this engagement."
    )
    assert not bridge_module.quotes_syllabus(invented, span)


def test_bridge_does_not_stutter_the_unit_heading():
    """The bridge already names the unit, so the quote must not repeat it."""
    from s2s.extract import heuristic
    from s2s.ingest import loader, structure

    text = (
        "Unit IV: Indexing, Storage and Query Optimisation\n"
        "File organisation and record storage. B-Trees and B+ Trees: structure, "
        "search, insertion and deletion. Reading EXPLAIN ANALYZE output and "
        "tuning slow queries with composite indexes.\n"
    )
    syllabus = loader.from_text(text)
    tree = structure.parse(syllabus.text)
    competencies = heuristic.extract(syllabus, tree, semester=4)

    assert competencies
    for competency in competencies:
        assert not competency.source_span.lower().startswith("unit ")
        assert not competency.source_span.lower().startswith("module ")
        assert competency.source_span in syllabus.text
