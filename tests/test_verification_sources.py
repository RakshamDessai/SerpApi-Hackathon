"""Free verification sources: GitHub issue search, Catchafire and Kaggle APIs.

No network: every HTTP call is replaced with a recorded or documented shape.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from s2s.ground import gate
from s2s.mesh import github_direct
from s2s.models import RawResult


class _FakeResponse:
    def __init__(self, status=200, payload=None, text="", url=""):
        self.status_code, self._payload, self.text, self.url = status, payload, text, url

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _capture_get(monkeypatch, response):
    import requests

    calls = []

    def fake(url, **kwargs):
        calls.append((url, kwargs))
        return response

    monkeypatch.setattr(requests, "get", fake)
    return calls


# ------------------------------------------------------- GitHub issue search -

#: Shape of a real api.github.com/search/issues answer (2026-10-11).
GITHUB_SEARCH = {
    "items": [
        {
            "html_url": "https://github.com/ajitpratap0/GoSQLX/issues/554",
            "title": "perf(parser): replace fmt in clause parsing",
            "state": "open",
            "created_at": "2026-10-10T08:00:00Z",
            "body": "Good first issue.\nTouches the SQL parser.",
            "labels": [{"name": "good first issue"}],
        },
        {"html_url": "https://github.com/a/b/pull/3", "title": "a PR", "state": "open"},
        {"html_url": "https://github.com/a/b/issues/9", "title": "closed", "state": "closed"},
    ]
}


def test_github_search_keeps_only_open_issues():
    results = github_direct.parse(GITHUB_SEARCH)
    assert [r.url for r in results] == ["https://github.com/ajitpratap0/GoSQLX/issues/554"]
    result = results[0]
    assert result.verdict == "live"
    assert result.provenance == "platform-api"
    assert result.organization == "ajitpratap0/GoSQLX"
    assert result.posted_at == datetime(2026, 10, 10, 8, 0)
    assert "Touches the SQL parser." in result.snippet


def test_github_query_is_quoted_open_and_unassigned():
    query = github_direct.build_query("SQL query")
    assert query.startswith('"SQL query" ')
    for part in ("state:open", "is:issue", "no:assignee", '"good first issue"'):
        assert part in query


def test_github_search_fails_soft(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "get", boom)
    assert github_direct.search(["SQL"]) == []


def test_github_token_is_sent_when_given(monkeypatch):
    calls = _capture_get(monkeypatch, _FakeResponse(payload={"items": []}))
    github_direct.search(["SQL"], token="t0ken")
    assert calls[0][1]["headers"]["Authorization"] == "Bearer t0ken"


def test_gate_keeps_a_source_verdict_without_probing(monkeypatch):
    calls = _capture_get(monkeypatch, _FakeResponse(payload={"state": "closed"}))
    result = github_direct.parse(GITHUB_SEARCH)[0]
    graded = gate.verify([result], probe_top_n=10, enable_probe=True)
    assert graded[0][1] == "live" and graded[0][2] is not None
    assert calls == [], "a verdict the source proved must not cost a status call"


# ------------------------------------------------------- Catchafire status -

def _catchafire(listing_id="175602"):
    return RawResult(title="Org needs help with data analytics",
                     url=f"https://www.catchafire.org/volunteer/{listing_id}/slug/",
                     snippet="", adapter_key="catchafire")


#: Fields observed on catchafire.org/volunteer/api/details/<id>/ (2026-10-11).
@pytest.mark.parametrize("payload, verdict", [
    ({"is_matching": True, "is_completed": False, "is_canceled": False}, "live"),
    ({"is_matching": False, "is_completed": True, "is_canceled": False}, "archived"),
    ({"is_matching": False, "is_completed": False, "is_canceled": True}, "archived"),
    ({"is_matching": False, "is_matched": True}, "archived"),
    ({"unexpected": "schema"}, "unverified"),
])
def test_catchafire_state_comes_from_its_details_api(monkeypatch, payload, verdict):
    calls = _capture_get(monkeypatch, _FakeResponse(payload=payload))
    assert gate.tier2_probe(_catchafire()) == verdict
    assert calls[0][0] == "https://www.catchafire.org/volunteer/api/details/175602/"


# ----------------------------------------------------------- Kaggle status -

def _kaggle():
    return RawResult(title="Playground Series", adapter_key="kaggle", snippet="",
                     url="https://www.kaggle.com/competitions/playground-series-s6e10")


def test_kaggle_without_a_token_is_never_checked(monkeypatch):
    calls = _capture_get(monkeypatch, _FakeResponse(payload=[]))
    assert gate.status_api_for(_kaggle()) is None
    assert gate.verify([_kaggle()], probe_top_n=10)[0][1] == "unverified"
    assert calls == []


KAGGLE_LIST = [
    {"ref": "https://www.kaggle.com/competitions/playground-series-s6e1",
     "deadline": "2026-01-31T23:59:00Z"},
    {"ref": "https://www.kaggle.com/competitions/playground-series-s6e10",
     "deadline": "2099-10-31T23:59:00Z"},
]


def test_kaggle_with_a_token_reads_its_own_competition(monkeypatch):
    calls = _capture_get(monkeypatch, _FakeResponse(payload=KAGGLE_LIST))
    credentials = {"kaggle": ("student", "secret")}
    graded = gate.verify([_kaggle()], probe_top_n=10, credentials=credentials)
    assert graded[0][1] == "live"
    url, kwargs = calls[0]
    assert url.endswith("search=playground-series-s6e10")
    assert kwargs["auth"] == ("student", "secret")


def test_kaggle_past_deadline_is_archived(monkeypatch):
    finished = [{"ref": "playground-series-s6e10", "deadline": "2026-01-01T00:00:00Z"}]
    _capture_get(monkeypatch, _FakeResponse(payload=finished))
    assert gate.tier2_probe(_kaggle(), credentials={"kaggle": ("u", "k")}) == "archived"


def test_kaggle_search_without_this_competition_says_nothing(monkeypatch):
    other = [{"ref": "https://www.kaggle.com/competitions/titanic", "deadline": "2099-01-01"}]
    _capture_get(monkeypatch, _FakeResponse(payload=other))
    assert gate.tier2_probe(_kaggle(), credentials={"kaggle": ("u", "k")}) == "unverified"


def test_kaggle_bad_token_fails_soft(monkeypatch):
    _capture_get(monkeypatch, _FakeResponse(status=401, payload={"message": "Unauthorized"}))
    assert gate.tier2_probe(_kaggle(), credentials={"kaggle": ("u", "bad")}) == "unverified"
