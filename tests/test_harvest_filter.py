"""Regression tests for the demo-fixture harvester.

The harvester exists so demo mode has real data without a SerpApi key. Its one
subtle job is relevance filtering, and getting that wrong is silent: the demo
still renders, just with results that match nothing.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


from s2s.models import Competency, Discipline, Dork

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "harvest_demo_fixtures", ROOT / "scripts" / "harvest_demo_fixtures.py"
)
harvest = importlib.util.module_from_spec(SPEC)
# @dataclass resolves annotations via sys.modules[cls.__module__]; a module
# loaded by spec alone is absent from it and dataclass creation blows up.
sys.modules["harvest_demo_fixtures"] = harvest
SPEC.loader.exec_module(harvest)


def _competency(canonical, aliases):
    return Competency(
        canonical=canonical, aliases=aliases, tools=[],
        disciplines=[Discipline.CS_SOFTWARE], bloom=4, band="intermediate",
        source_unit="Unit 4", source_span=canonical,
    )


DBMS = _competency("Query Optimisation", ["query optimisation", "slow query"])


def _listing(title, snippet):
    return harvest.Listing(title=title, link="https://x/1", snippet=snippet)


def test_competency_phrases_ignores_adapter_boilerplate():
    """THE BUG: phrases were re-extracted from the rendered dork, which carries
    each adapter's own template terms. Every harvested GitHub issue contains
    "good first issue" by construction, so everything passed the filter and
    semantic scored 0.000 on every result."""
    dork = Dork(
        adapter_key="github",
        query='site:github.com inurl:issues ("good first issue" OR "help wanted") '
              '("query optimisation" OR "slow query")',
        covers=(DBMS,),
        engine="google",
    )
    phrases = [p.lower() for p in harvest.competency_phrases(dork)]
    assert "query optimisation" in phrases
    assert "good first issue" not in phrases
    assert "help wanted" not in phrases


def test_irrelevant_listing_is_filtered_out():
    listings = [_listing("[CI] Test on Python 3.14",
                         "good first issue in some/repo. Python 3.14 is out.")]
    assert harvest.matching(listings, ["query optimisation", "slow query"]) == []


def test_relevant_listing_survives():
    listings = [_listing("Profiling - find and fix slow database queries",
                         "good first issue. Investigate slow query performance.")]
    assert len(harvest.matching(listings, ["slow query"])) == 1


def test_boilerplate_alone_no_longer_admits_everything():
    """Guards the exact failure: filtering on the label term let unrelated
    issues through."""
    listings = [
        _listing("Unrelated docs typo", "good first issue in a/b. Fix a typo."),
        _listing("Optimise slow query in loader", "good first issue. slow query."),
    ]
    kept = harvest.matching(listings, ["slow query"])
    assert len(kept) == 1
    assert "Optimise" in kept[0].title


def test_no_phrases_keeps_everything():
    listings = [_listing("anything", "anything")]
    assert harvest.matching(listings, []) == listings


def test_fixtures_are_stamped_with_provenance():
    """Harvested data must never be mistakable for a SerpApi response."""
    payload = harvest.to_serpapi_shape([_listing("t", "s")], "github", "q")
    assert payload["s2s_source"] == "public-api-harvest"
    assert payload["search_metadata"]["s2s_synthetic"] is True
    assert payload["organic_results"][0]["title"] == "t"


def test_client_propagates_harvest_provenance():
    from s2s.mesh.cache import ResponseCache
    from s2s.mesh.ledger import BudgetLedger
    from s2s.mesh.serpapi_client import SerpApiClient
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    cache = ResponseCache(directory=tmp, ttl_hours=10**6)
    client = SerpApiClient(None, cache, BudgetLedger(cap=9))
    dork = Dork(adapter_key="github", query="q", covers=(DBMS,), engine="google")

    payload = harvest.to_serpapi_shape(
        [harvest.Listing("t", "https://github.com/a/b/issues/1", "s")], "github", "q"
    )
    cache.put(dork.engine, client.build_params(dork), payload)

    results = client.run(dork)
    assert results
    assert all(r.provenance == "public-api-harvest" for r in results)
