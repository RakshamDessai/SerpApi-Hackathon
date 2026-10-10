"""The Syllabus Gap Report."""

from __future__ import annotations

from s2s.analyze import gaps
from s2s.ingest import structure
from s2s.models import Competency, Discipline, Opportunity, ScoreBreakdown
from s2s.score.scorer import WEIGHTS

SYLLABUS = (
    "Unit I: Working Capital Management\n"
    "Operating cycle and cash conversion cycle for a manufacturing firm.\n"
    "Unit II: Punch Card Batch Processing\n"
    "Hollerith codes, card decks and batch job control language.\n"
    "Unit III: Capital Budgeting\n"
    "Net present value and internal rate of return for project appraisal.\n"
)


def _competency(unit, canonical, aliases, discipline=Discipline.COMMERCE_FINANCE):
    return Competency(
        canonical=canonical, aliases=aliases, tools=[], disciplines=[discipline],
        bloom=4, band="intermediate", source_unit=unit, source_span=canonical,
    )


def _opportunity(competency, total_score):
    breakdown = ScoreBreakdown(1.0, 1.0, 1.0, 1.0, WEIGHTS)
    opportunity = Opportunity(
        title="x", url="https://x", snippet="x", adapter_key="unv",
        matched_competency=competency, score=breakdown, verdict="live",
    )
    # Force a known composite without reimplementing the weighting here.
    object.__setattr__(breakdown, "semantic", total_score / 100)
    breakdown.level = breakdown.freshness = breakdown.actionability = total_score / 100
    return opportunity


def test_unit_with_no_market_alias_is_flagged_dead():
    tree = structure.parse(SYLLABUS)
    matched = _competency("Unit 1: Working Capital Management", "Working capital",
                          ["cash flow forecast"])
    report = gaps.build(tree, [matched], [_opportunity(matched, 80)], searched=True)

    dead = [g for g in report.gaps if g.kind == "no_market_signal"]
    assert any("Punch Card" in g.unit_label for g in dead)


def test_dead_unit_gets_in_demand_alternatives():
    tree = structure.parse(SYLLABUS)
    report = gaps.build(tree, [], [], searched=True)
    dead = [g for g in report.gaps if g.kind == "no_market_signal"]
    assert dead
    assert all(isinstance(g.suggestions, list) for g in dead)


def test_competency_with_no_results_is_no_live_work():
    tree = structure.parse(SYLLABUS)
    competency = _competency("Unit 3: Capital Budgeting", "Capital budgeting",
                             ["NPV analysis"])
    report = gaps.build(tree, [competency], [], searched=True)
    kinds = {g.unit_label: g.kind for g in report.gaps}
    assert kinds["Unit 3: Capital Budgeting"] == "no_live_work"


def test_low_scoring_match_is_weak_demand():
    tree = structure.parse(SYLLABUS)
    competency = _competency("Unit 3: Capital Budgeting", "Capital budgeting",
                             ["NPV analysis"])
    weak = _opportunity(competency, 20)
    report = gaps.build(tree, [competency], [weak], searched=True)
    kinds = {g.unit_label: g.kind for g in report.gaps}
    assert kinds["Unit 3: Capital Budgeting"] == "weak_demand"


def test_good_match_is_not_a_gap():
    tree = structure.parse(SYLLABUS)
    competency = _competency("Unit 3: Capital Budgeting", "Capital budgeting",
                             ["NPV analysis"])
    strong = _opportunity(competency, 90)
    report = gaps.build(tree, [competency], [strong], searched=True)
    labels = {g.unit_label for g in report.gaps}
    assert "Unit 3: Capital Budgeting" not in labels
    assert report.units_matched == 1


def test_suggestions_never_repeat_what_was_already_searched():
    """Telling a student to retry the exact terms that just failed is noise."""
    tree = structure.parse(SYLLABUS)
    competency = _competency(
        "Unit 3: Capital Budgeting", "Capital budgeting",
        ["investment appraisal", "NPV analysis", "financial model"],
    )
    report = gaps.build(tree, [competency], [], searched=True)
    gap = next(g for g in report.gaps if g.unit_label == "Unit 3: Capital Budgeting")
    searched = {a.lower() for a in competency.aliases}
    assert not (searched & {s.lower() for s in gap.suggestions})


def test_unsearched_run_refuses_to_blame_the_curriculum():
    """With no searches run, every unit looks dead. Saying so would be a lie."""
    tree = structure.parse(SYLLABUS)
    report = gaps.build(tree, [], [], searched=False)
    assert report.searched is False
    assert report.note
    assert "no searches ran" in report.headline.lower()


def test_coverage_is_a_fraction_of_parsed_units():
    tree = structure.parse(SYLLABUS)
    competency = _competency("Unit 1: Working Capital Management", "Working capital",
                             ["cash flow forecast"])
    report = gaps.build(tree, [competency], [_opportunity(competency, 90)], searched=True)
    assert report.units_total == 3
    assert report.units_matched == 1
    assert report.coverage == 1 / 3


def test_pipeline_attaches_a_gap_report():
    from s2s.config import Settings
    from s2s.ingest import loader
    from s2s import pipeline

    settings = Settings.load()
    settings.demo_mode = True
    syllabus = loader.from_text(SYLLABUS)
    result = pipeline.run(syllabus, settings, semester=3)

    assert result.gap_report is not None
    assert result.gap_report.units_total >= 3
