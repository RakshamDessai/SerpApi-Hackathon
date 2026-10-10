"""Grounding Gate tiers 0 and 1, plus dedupe.

Tier 2 hits the network and is excluded from the default suite.
"""

from __future__ import annotations

import pytest

from s2s.ground import dedupe, gate
from s2s.models import RawResult


def _result(url, title="Some opportunity", snippet="", adapter_key="unv"):
    return RawResult(title=title, url=url, snippet=snippet, adapter_key=adapter_key)


# ------------------------------------------------------------- tier 0 ------

@pytest.mark.parametrize(
    "adapter_key, url, expected",
    [
        ("unv", "https://www.onlinevolunteering.org/en/opportunity/abc-1", True),
        ("unv", "https://www.onlinevolunteering.org/en/", False),          # browse page
        ("unv", "https://www.onlinevolunteering.org/", False),            # homepage
        ("kaggle", "https://www.kaggle.com/competitions/titanic", True),
        ("kaggle", "https://www.kaggle.com/datasets/foo", False),         # wrong section
        ("kaggle", "https://www.kaggle.com/", False),
        ("github", "https://github.com/pandas-dev/pandas/issues/1234", True),
        ("github", "https://github.com/pandas-dev/pandas", False),        # repo, not issue
        ("unstop", "https://unstop.com/competitions/fintech-2026", True),
        ("unstop", "https://unstop.com/", False),
        ("upwork", "https://www.upwork.com/freelance-jobs/apply/xyz", True),
        ("upwork", "https://www.upwork.com/", False),
    ],
)
def test_tier0_url_shape(adapter_key, url, expected):
    assert gate.tier0_url_shape(_result(url, adapter_key=adapter_key)) is expected


def test_tier0_rejects_unknown_adapter():
    assert gate.tier0_url_shape(_result("https://x.com/y", adapter_key="nope")) is False


# ------------------------------------------------------------- tier 1 ------

@pytest.mark.parametrize(
    "snippet, expected",
    [
        ("Applications are closed for this cycle", "archived"),
        ("This opportunity has ended", "archived"),
        ("No longer accepting applications", "archived"),
        ("Volunteer needed to build a budget", None),
    ],
)
def test_tier1_detects_dead_listings(snippet, expected):
    assert gate.tier1_snippet(_result("https://x", snippet=snippet)) == expected


def test_tier1_uses_adapter_specific_markers():
    kaggle = _result(
        "https://www.kaggle.com/competitions/x",
        snippet="This competition has ended.",
        adapter_key="kaggle",
    )
    assert gate.tier1_snippet(kaggle) == "archived"


# -------------------------------------------------------------- verify -----

def test_verify_drops_tier0_failures_and_labels_the_rest():
    results = [
        _result("https://www.onlinevolunteering.org/en/opportunity/live-1"),
        _result("https://www.onlinevolunteering.org/"),                   # dropped
        _result("https://www.onlinevolunteering.org/en/opportunity/dead-1",
                snippet="This opportunity has ended"),
    ]
    graded = gate.verify(results, enable_probe=False)
    assert len(graded) == 2
    assert {v for _, v, _ in graded} == {"unverified", "archived"}


def test_verify_without_probe_never_claims_live():
    graded = gate.verify(
        [_result("https://www.onlinevolunteering.org/en/opportunity/x")],
        enable_probe=False,
    )
    assert graded[0][1] == "unverified"


# -------------------------------------------------------------- dedupe -----

def test_canonical_url_strips_tracking_and_fragments():
    a = dedupe.canonical_url("https://WWW.Example.com/path/?utm_source=g&id=5#frag")
    b = dedupe.canonical_url("https://example.com/path?id=5")
    assert a == b


def test_dedupe_collapses_tracking_variants():
    results = [
        _result("https://www.onlinevolunteering.org/en/opportunity/a"),
        _result("https://www.onlinevolunteering.org/en/opportunity/a?utm_source=x"),
    ]
    assert len(dedupe.dedupe(results)) == 1


def test_dedupe_merges_near_identical_titles():
    results = [
        _result("https://www.onlinevolunteering.org/en/opportunity/a",
                title="Build a cash flow forecast for a clinic", snippet="short"),
        _result("https://www.onlinevolunteering.org/en/opportunity/b",
                title="Build a cash flow forecast for a clinic",
                snippet="a much longer and more useful snippet"),
    ]
    merged = dedupe.dedupe(results)
    assert len(merged) == 1
    assert merged[0].snippet == "a much longer and more useful snippet"


def test_dedupe_keeps_genuinely_different_listings():
    results = [
        _result("https://www.onlinevolunteering.org/en/opportunity/a", title="Cash flow model"),
        _result("https://www.onlinevolunteering.org/en/opportunity/b", title="Logo design for NGO"),
    ]
    assert len(dedupe.dedupe(results)) == 2


# ------------------------------- edition year in the title (2026-10-10) ----

@pytest.mark.parametrize("title,stale", [
    ("Financial Modeling & Valuation Competition - 2020 - Unstop", True),
    ("Sqlize - 2025", True),
    ("Budget Battle - 2026", False),
    ("Nonprofit Budget & Grants Planning Advisor (2027)", False),
    ("FinGenius 2025 - Decoding Finance - 2026", False),   # newest year wins
    ("Hack On Hills 8.0", False),                          # no year: no claim
])
def test_past_edition_year_in_title_is_stale(title, stale):
    from datetime import datetime
    assert gate.stale_by_title_year(title, now=datetime(2026, 10, 10)) is stale


def test_stale_title_is_archived_by_tier1():
    from datetime import datetime
    result = _result("https://unstop.com/competitions/x-1", title="Budget Analysis - 2023",
                     adapter_key="unstop")
    assert gate.tier1_snippet(result, now=datetime(2026, 10, 10)) == "archived"
