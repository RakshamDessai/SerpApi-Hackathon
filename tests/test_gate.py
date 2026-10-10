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


# --------------------------- tier 2 against real page shapes (2026-10-10) --

class _FakeResponse:
    def __init__(self, status=200, text="", url="", payload=None):
        self.status_code, self.text, self.url, self._payload = status, text, url, payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _fake_get(monkeypatch, response):
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)


#: Shape of a real BeBee job page: an i18n bundle holding every error string.
BEBEE_PAGE = (
    '<html><body><h1>Brand Development Intern</h1><button>Apply now</button>'
    '<script>window.i18n={"applyErrorJobExpired":"This job is no longer accepting '
    'applications.","request_expired":"This request has expired."}</script></body></html>'
)


def test_marker_inside_a_script_bundle_does_not_archive():
    assert not gate.dead_marker_in(BEBEE_PAGE.lower(), gate.GENERIC_DEAD_MARKERS
                                   + ("no longer accepting applications",))


def test_marker_in_visible_text_archives():
    page = "<html><body><p>No longer accepting applications</p></body></html>"
    assert gate.dead_marker_in(page.lower(), ("no longer accepting applications",))


def test_json_token_marker_matches_embedded_data():
    page = '<script>var job={"is_expired":true}</script>'
    assert gate.dead_marker_in(page.lower(), ('"is_expired":true',))


def test_open_bebee_job_is_live(monkeypatch):
    url = "https://bebee.com/in/jobs/brand-development-outreach-intern-pacee--fj-2401568370"
    _fake_get(monkeypatch, _FakeResponse(text=BEBEE_PAGE, url=url))
    assert gate.tier2_probe(_result(url, adapter_key="gjobs")) == "live"


@pytest.mark.parametrize("state,verdict", [("open", "live"), ("closed", "archived")])
def test_github_state_comes_from_the_api_not_the_page(monkeypatch, state, verdict):
    """The page embeds linked PRs' states: open apache/doris#48203 read as closed."""
    _fake_get(monkeypatch, _FakeResponse(payload={"state": state}))
    url = "https://github.com/apache/doris/issues/48203"
    assert gate.tier2_probe(_result(url, adapter_key="github")) == verdict


def test_github_rate_limit_fails_soft(monkeypatch):
    _fake_get(monkeypatch, _FakeResponse(status=403, payload={"message": "API rate limit exceeded"}))
    url = "https://github.com/apache/doris/issues/48203"
    assert gate.tier2_probe(_result(url, adapter_key="github")) == "unverified"


def test_job_hosted_on_unstop_uses_unstops_status_api():
    url = "https://unstop.com/internships/creative-branding-internship-pehchan-1766642"
    api = gate.status_api_for(_result(url, adapter_key="gjobs"))
    assert api is not None and "unstop.com/api" in api.url


def test_job_on_an_ordinary_board_has_no_status_api():
    url = "https://internshala.com/internship/detail/graphic-design-internship-123"
    assert gate.status_api_for(_result(url, adapter_key="gjobs")) is None


# ------------------------------ Kaggle / DrivenData / Zooniverse (2026-10-10) --

@pytest.mark.parametrize("payload,verdict", [
    ({"projects": [{"state": "live", "launch_approved": True}]}, "live"),
    ({"projects": [{"state": "paused", "launch_approved": True}]}, "archived"),   # We Cam Coexist
    ({"projects": [{"state": "live", "launch_approved": False}]}, "archived"),   # Parkside Asylum
    ({"projects": []}, "unverified"),
])
def test_zooniverse_state_comes_from_its_api(monkeypatch, payload, verdict):
    _fake_get(monkeypatch, _FakeResponse(payload=payload))
    url = "https://www.zooniverse.org/projects/tkillestein/kilonova-seekers"
    assert gate.tier2_probe(_result(url, adapter_key="zooniverse")) == verdict


def test_finished_drivendata_competition_is_archived(monkeypatch):
    url = "https://www.drivendata.org/competitions/311/dat-parkinsons-challenge/"
    page = ('<div><strong>Completed</strong> <span class="end-date text-capitalize">'
            'sep 2026</span></div>')
    _fake_get(monkeypatch, _FakeResponse(text=page, url=url))
    assert gate.tier2_probe(_result(url, adapter_key="drivendata")) == "archived"


def test_open_drivendata_competition_is_live(monkeypatch):
    url = "https://www.drivendata.org/competitions/320/open-challenge/"
    page = "<div><strong>Ends</strong> <span>dec 2026</span> completed submissions: 12</div>"
    _fake_get(monkeypatch, _FakeResponse(text=page, url=url))
    assert gate.tier2_probe(_result(url, adapter_key="drivendata")) == "live"


def test_kaggle_is_never_page_probed():
    """The page is a shell and the API answers our verifier with a CAPTCHA."""
    from s2s.mesh import adapters
    assert adapters.get("kaggle").liveness == "snippet_only"
    results = [_result("https://www.kaggle.com/competitions/titanic", adapter_key="kaggle")]
    assert [v for _, v, _ in gate.verify(results)] == ["unverified"]


def test_tier2_refuses_platforms_that_are_not_page_probed(monkeypatch):
    _fake_get(monkeypatch, _FakeResponse(text="<html>shell</html>",
                                         url="https://www.kaggle.com/competitions/titanic"))
    result = _result("https://www.kaggle.com/competitions/titanic", adapter_key="kaggle")
    assert gate.tier2_probe(result) == "unverified"
