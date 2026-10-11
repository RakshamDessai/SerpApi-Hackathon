"""The opt-in searches: this year's events, page 2, Google Events, city, YouTube.

Each one spends credits, so each is OFF by default and must leave the
default plan - and so every recorded demo fixture - exactly as it was.
"""

from __future__ import annotations

import pytest

from s2s.mesh import adapters as registry
from s2s.mesh import planner
from s2s.mesh.cache import ResponseCache
from s2s.mesh.ledger import BudgetLedger
from s2s.mesh.serpapi_client import SerpApiClient, event_link
from s2s.models import Competency, Discipline, Dork


def _competency(name, disciplines, aliases=None):
    return Competency(
        canonical=name, aliases=aliases or [f"{name} skill"], tools=[],
        disciplines=disciplines, bloom=4, band="intermediate",
        source_unit=f"Unit {name}", source_span=name,
    )


CS = [_competency("databases", [Discipline.CS_SOFTWARE], ["SQL query"]),
      _competency("concurrency", [Discipline.CS_SOFTWARE], ["concurrency"])]


# ------------------------------------------------- defaults stay unchanged -

def test_default_plan_is_unchanged_by_the_new_options():
    """Same queries and params as before, so demo fixtures still hit."""
    base = planner.plan(CS, credit_cap=12)
    explicit = planner.plan(CS, credit_cap=12, extra=set(), year=None, city=None)
    assert [(d.query, d.params) for d in base] == [(d.query, d.params) for d in explicit]
    assert not any("gevents" == d.adapter_key for d in base)


def test_default_settings_spend_no_extra_credits():
    from s2s.config import Settings

    settings = Settings.load()
    assert not settings.fresh_queries
    assert not settings.follow_up_pages
    assert not settings.events
    assert settings.gap_courses == 0
    assert settings.city is None


# ----------------------------------------------------- this year's events --

def test_year_goes_only_into_dated_edition_platforms():
    dorks = planner.plan(CS, credit_cap=20, year=2026)
    for dork in dorks:
        adapter = registry.get(dork.adapter_key)
        assert dork.query.endswith(" 2026") == adapter.year_in_query, dork.query


def test_year_keeps_the_measured_keyword_shape():
    adapter = registry.get("unstop")
    query = registry.render_query(adapter, ["cash flow forecast"], year=2026)
    assert query == "site:unstop.com cash flow forecast competition 2026"
    assert '"' not in query


# --------------------------------------------------------- Google Events ---

def test_events_are_added_without_taking_a_platform_slot():
    base = {a.key for a, _ in planner.choose_platforms(CS, max_platforms=3)}
    with_events = {a.key for a, _ in planner.choose_platforms(CS, 3, extra={"gevents"})}
    assert with_events == base | {"gevents"}


def test_events_adapter_is_opt_in():
    assert "gevents" not in {a.key for a in registry.active()}
    assert "gevents" in {a.key for a in registry.active(extra={"gevents"})}


def test_city_places_jobs_and_events_only():
    dorks = planner.plan(CS, credit_cap=30, extra={"gevents"}, city="Pune")
    for dork in dorks:
        if dork.engine in planner.LOCATED_ENGINES:
            assert dork.params["location"] == "Pune, India"
        else:
            assert "location" not in dork.params


#: Shape of a real SerpApi google_events response (from its documentation).
EVENTS_PAYLOAD = {
    "events_results": [
        {
            "title": "SQL for Data Analysis Workshop",
            "date": {"start_date": "Oct 18", "when": "Sat, Oct 18, 10 AM - 1 PM"},
            "address": ["Tech Hub, FC Road", "Pune, Maharashtra"],
            "link": "https://www.meetup.com/pune-data/events/123456/",
            "description": "Hands-on SQL workshop for students.",
            "venue": {"name": "Tech Hub"},
        },
        {
            "title": "Google-only event",
            "date": {"start_date": "Oct 20"},
            "link": "https://www.google.com/search?q=event",
            "ticket_info": [{"source": "Eventbrite",
                             "link": "https://www.eventbrite.com/e/987?utm_source=x"}],
        },
        {"title": "No link at all", "date": {"start_date": "Oct 21"}},
    ]
}


def _client(tmp_path, demo=True):
    return SerpApiClient(None, ResponseCache(directory=tmp_path), BudgetLedger(cap=5),
                         demo_mode=demo)


def test_event_results_parse_with_date_and_place_first(tmp_path):
    client = _client(tmp_path)
    dork = Dork("gevents", "SQL query events", (), "google_events")
    results = client._parse(EVENTS_PAYLOAD, dork)
    assert [r.title for r in results] == ["SQL for Data Analysis Workshop", "Google-only event"]
    first = results[0]
    assert first.snippet.startswith("Sat, Oct 18, 10 AM - 1 PM · Tech Hub")
    assert first.organization == "Tech Hub"
    assert first.posted_at is None, "an event date is not a posting date"


def test_event_link_prefers_a_real_page_over_google():
    assert event_link(EVENTS_PAYLOAD["events_results"][1]) == "https://www.eventbrite.com/e/987"
    assert event_link({"link": "https://www.google.com/x"}) is None


# ------------------------------------------------------------------ YouTube -

def test_youtube_uses_search_query_not_q(tmp_path):
    params = _client(tmp_path).build_params(Dork("youtube", "SQL full course", (), "youtube"))
    assert params["search_query"] == "SQL full course"
    assert "q" not in params


def test_courses_come_from_the_cache_and_count_in_the_ledger(tmp_path):
    client = _client(tmp_path, demo=False)
    dork = Dork("youtube", "data visualisation full course", (), "youtube")
    client.cache.put("youtube", client.build_params(dork), {"video_results": [
        {"title": "Data Visualisation Full Course", "link": "https://www.youtube.com/watch?v=a",
         "channel": {"name": "freeCodeCamp.org"}, "length": "4:12:00"},
        {"title": "no link"},
    ]})
    courses = client.courses("data visualisation")
    assert courses == [{"title": "Data Visualisation Full Course",
                        "url": "https://www.youtube.com/watch?v=a",
                        "channel": "freeCodeCamp.org", "length": "4:12:00"}]
    assert client.ledger.cache_hits == 1 and client.ledger.spent == 0


def test_courses_without_a_key_spend_nothing(tmp_path):
    client = _client(tmp_path, demo=False)
    assert client.courses("anything") == []
    assert client.ledger.spent == 0 and client.ledger.skipped == 1


# ------------------------------------------------------------------- page 2 -

def test_next_page_params_come_from_serpapis_own_link(tmp_path):
    client = _client(tmp_path)
    dork = Dork("idealist", "site:idealist.org budget", (), "duckduckgo")
    client._remember_next(dork, {"serpapi_pagination": {
        "next": "https://serpapi.com/search.json?engine=duckduckgo&q=x&start=11"}})
    assert client.next_params[("idealist", "site:idealist.org budget")] == {"start": "11"}


def _dork(key, query="q"):
    return Dork(key, query, (), "duckduckgo", params={"kl": "in-en"})


def test_follow_ups_go_to_platforms_that_verified_mostly_live():
    dorks = [_dork("idealist"), _dork("unstop")]
    verdicts = {"idealist": ["live", "live", "unverified"],
                "unstop": ["archived", "archived", "live"]}
    nexts = {("idealist", "q"): {"start": "11"}, ("unstop", "q"): {"start": "11"}}
    out = planner.follow_ups(dorks, verdicts, nexts, budget=5)
    assert [d.adapter_key for d in out] == ["idealist"]
    assert out[0].params == {"kl": "in-en", "start": "11"}


def test_follow_ups_respect_the_budget_and_need_a_next_link():
    dorks = [_dork("idealist"), _dork("devpost")]
    verdicts = {"idealist": ["live", "live"], "devpost": ["live", "live"]}
    assert planner.follow_ups(dorks, verdicts, {("idealist", "q"): {"start": "11"}},
                              budget=5)[0].adapter_key == "idealist"
    both = {("idealist", "q"): {"start": "11"}, ("devpost", "q"): {"start": "11"}}
    assert len(planner.follow_ups(dorks, verdicts, both, budget=1)) == 1
    assert planner.follow_ups(dorks, verdicts, both, budget=0) == []


@pytest.mark.parametrize("found", [["live"], ["live", "archived", "archived"]])
def test_follow_ups_need_enough_live_evidence(found):
    out = planner.follow_ups([_dork("idealist")], {"idealist": found},
                             {("idealist", "q"): {"start": "11"}}, budget=5)
    assert out == []
