"""Scoring: each term independently, then the composite.

This is the deterministic core of the product, so it carries the most tests.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from s2s.models import Competency, Discipline, RawResult, ScoreBreakdown
from s2s.score import scorer


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
