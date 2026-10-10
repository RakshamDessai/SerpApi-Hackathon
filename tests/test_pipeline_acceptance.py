"""Phase 1 acceptance: syllabus in, scored opportunities out, credits accounted.

No SerpApi key is needed. The cache is seeded with realistically-shaped SerpApi
payloads and the pipeline is run in demo mode, which exercises the entire chain
(parse -> ground -> dedupe -> score -> rank) and proves the credit accounting.

The one thing this cannot prove is that a real query returns good results; that
needs a key and `scripts/record_fixtures.py`.
"""

from __future__ import annotations

import pytest

from s2s.config import Settings
from s2s.extract import extract_competencies
from s2s.ingest import loader, structure
from s2s.mesh import planner
from s2s.mesh.cache import ResponseCache
from s2s.mesh.serpapi_client import SerpApiClient
from s2s.mesh.ledger import BudgetLedger
from s2s import pipeline
from tests.conftest import FIXTURES


def _organic(title, link, snippet, date=None):
    item = {"title": title, "link": link, "snippet": snippet}
    if date:
        item["date"] = date
    return item


#: Shaped exactly like a real SerpApi `google` response.
IDEALIST_PAYLOAD = {
    "organic_results": [
        _organic(
            "Prepare a 12-month cash flow forecast for a community health clinic",
            "https://www.idealist.org/en/volunteer-opportunity/cash-flow-clinic",
            "A non-profit needs a volunteer to build a cash flow forecast and "
            "budget report in Excel. Beginner friendly, about 10 hours.",
            "3 days ago",
        ),
        _organic(
            "Financial model and liquidity analysis for a literacy NGO",
            "https://www.idealist.org/en/volunteer-opportunity/liquidity-ngo",
            "Build a financial model and liquidity analysis. Deliverable is a "
            "spreadsheet and a short report.",
            "1 week ago",
        ),
        _organic(
            "Browse volunteering opportunities",
            "https://www.idealist.org/en/volunteer",
            "Find opportunities by skill.",
        ),
        _organic(
            "Budget template for a youth sports charity",
            "https://www.idealist.org/en/volunteer-opportunity/budget-template",
            "Build a simple budget template. This opportunity has ended.",
            "6 months ago",
        ),
        _organic(
            "Senior finance director wanted - 8+ years",
            "https://www.idealist.org/en/volunteer-opportunity/senior-role",
            "Seeking a senior expert to lead our finance function.",
            "1 week ago",
        ),
    ]
}

UNSTOP_PAYLOAD = {
    "organic_results": [
        _organic(
            "National FinTech Case Competition: MSME Working Capital",
            "https://unstop.com/competitions/fintech-msme-2026",
            "Design a working capital underwriting model. Prize pool. "
            "Weekend sprint, open to students.",
            "2 days ago",
        ),
        _organic(
            "Budget Analysis Case Challenge for Commerce Students",
            "https://unstop.com/competitions/budget-case-2026",
            "Prepare a budget projection and financial analysis report.",
            "5 days ago",
        ),
    ]
}

CATCHAFIRE_PAYLOAD = {
    "organic_results": [
        _organic(
            "Animal sanctuary needs help with a cash flow forecast and budget",
            # Real listing shape, observed 2026-10-10.
            "https://www.catchafire.org/volunteer/180042/cash-flow-sanctuary/",
            "Volunteer needed to produce a 12 month budget and cash flow "
            "forecast. Deliverable is a spreadsheet model.",
            "4 days ago",
        ),
    ]
}


@pytest.fixture
def seeded_settings(tmp_path):
    """Settings whose cache already contains the payloads the plan will ask for."""
    settings = Settings.load()
    settings.demo_mode = True
    settings.credit_cap = 12
    settings.max_platforms = 5
    settings.cache_dir = tmp_path

    syllabus = loader.from_fixture(FIXTURES / "du_bcom_sem3_financial_management.txt")
    tree = structure.parse(syllabus.text)
    competencies = extract_competencies(
        syllabus, tree, api_key=None, semester=3, limit=settings.max_competencies
    ).competencies
    dorks = planner.plan(
        competencies,
        credit_cap=settings.credit_cap,
        max_platforms=settings.max_platforms,
        terms_per_dork=settings.terms_per_dork,
    )

    payloads = {
        "idealist": IDEALIST_PAYLOAD,
        "unstop": UNSTOP_PAYLOAD,
        "catchafire": CATCHAFIRE_PAYLOAD,
    }

    cache = ResponseCache(directory=tmp_path, ttl_hours=10 ** 6)
    client = SerpApiClient(None, cache, BudgetLedger(cap=99))
    seeded = 0
    for dork in dorks:
        payload = payloads.get(dork.adapter_key)
        if payload is not None:
            cache.put(dork.engine, client.build_params(dork), payload)
            seeded += 1

    assert seeded > 0, "plan never queried a seeded platform"

    # Demo mode reads from fixtures/serpapi; point it at our temp cache instead.
    import s2s.mesh.cache as cache_module

    original = cache_module.build
    cache_module.build = lambda s: ResponseCache(
        directory=tmp_path, ttl_hours=10 ** 6, read_only=True, ignore_ttl=True
    )
    yield settings, syllabus
    cache_module.build = original


def test_phase1_acceptance(seeded_settings):
    settings, syllabus = seeded_settings
    result = pipeline.run(syllabus, settings, semester=3)

    # 1. competencies were extracted
    assert len(result.competencies) >= 4

    # 2. the plan is small
    assert len(result.dorks) <= settings.credit_cap

    # 3. opportunities came through, scored
    assert len(result.opportunities) >= 5, (
        f"only {len(result.opportunities)} opportunities"
    )

    # 4. every surviving card passed tier 0 - no homepages or browse pages
    from s2s.ground import gate
    from s2s.models import RawResult

    for opportunity in result.opportunities:
        probe = RawResult(
            title=opportunity.title, url=opportunity.url,
            snippet=opportunity.snippet, adapter_key=opportunity.adapter_key,
        )
        assert gate.tier0_url_shape(probe), f"junk URL survived: {opportunity.url}"

    # 5. the dead listing was archived, not shown as live
    archived_titles = " ".join(o.title.lower() for o in result.archived)
    assert "youth sports charity" in archived_titles

    # 5b. a senior role is removed outright, not merely ranked low
    all_titles = " ".join(o.title.lower() for o in result.opportunities)
    assert "senior finance director" not in all_titles

    # 6. scores are populated and explainable
    for opportunity in result.opportunities:
        assert 0 <= opportunity.score.total <= 100
        assert len(opportunity.score.explain()) == 4

    # 7. demo mode spent nothing
    assert result.ledger.live_calls == 0
    assert result.ledger.cache_hits > 0


def test_second_run_is_free(seeded_settings):
    """Re-running the same syllabus must not cost a credit."""
    settings, syllabus = seeded_settings
    first = pipeline.run(syllabus, settings, semester=3)
    second = pipeline.run(syllabus, settings, semester=3)

    assert first.ledger.live_calls == 0
    assert second.ledger.live_calls == 0
    assert len(second.opportunities) == len(first.opportunities)


def test_ranking_puts_the_best_match_first(seeded_settings):
    settings, syllabus = seeded_settings
    result = pipeline.run(syllabus, settings, semester=3)

    actionable = result.actionable
    assert actionable, "nothing actionable"
    scores = [o.score.total for o in actionable]
    assert scores == sorted(scores, reverse=True)
    assert all(o.verdict != "archived" for o in actionable)


def test_savings_are_reported_honestly(seeded_settings):
    settings, syllabus = seeded_settings
    result = pipeline.run(syllabus, settings, semester=3)
    naive, planned, saved = result.savings

    assert planned == len(result.dorks)
    assert naive >= planned
    assert 0.0 <= saved < 1.0
