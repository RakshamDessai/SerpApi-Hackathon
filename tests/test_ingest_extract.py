"""Ingest and extract, driven by the four real-format preset syllabi."""

from __future__ import annotations

import pytest

from s2s.extract import extract_competencies, heuristic
from s2s.ingest import loader, structure
from s2s.ingest.loader import IngestError
from s2s.mesh import cache as cache_module
from tests.conftest import FIXTURES, PRESETS


@pytest.mark.parametrize("stem", list(PRESETS), ids=lambda s: s[:24])
def test_every_preset_parses_into_units(stem):
    syllabus = loader.from_fixture(FIXTURES / f"{stem}.txt")
    tree = structure.parse(syllabus.text)
    assert tree.unit_count >= 4, f"{stem} only produced {tree.unit_count} units"


@pytest.mark.parametrize("stem", list(PRESETS), ids=lambda s: s[:24])
def test_unit_offsets_point_at_the_real_text(stem):
    syllabus = loader.from_fixture(FIXTURES / f"{stem}.txt")
    tree = structure.parse(syllabus.text)
    for _, span, offset in structure.unit_spans(syllabus.text, tree):
        assert syllabus.text[offset:offset + len(span)].strip().startswith(span[:30])


def test_module_headings_are_parsed_like_units():
    """VTU syllabi say 'Module 3' where DU says 'Unit III'."""
    tree = structure.parse(
        "Module 1: Introduction\nSome text here about databases and schemas.\n"
        "Module 2: Normalisation\nMore text about functional dependencies."
    )
    assert tree.unit_count == 2


def test_roman_numeral_units_are_parsed():
    tree = structure.parse(
        "Unit I: Introduction\nText body that is long enough to matter here.\n"
        "Unit II: Analysis\nAnother body of text that is long enough as well."
    )
    labels = [u.label for u in tree.iter_units()]
    assert labels[0].startswith("Unit 1")
    assert labels[1].startswith("Unit 2")


def test_unstructured_text_still_yields_one_unit():
    tree = structure.parse("Just a wall of prose about accounting " * 10)
    assert tree.unit_count == 1


def test_short_input_is_rejected_clearly():
    with pytest.raises(IngestError):
        loader.from_text("too short")


# ------------------------------------------------------------- extract -----

@pytest.mark.parametrize("stem,semester", PRESETS.items(), ids=lambda v: str(v)[:24])
def test_heuristic_extraction_produces_usable_competencies(stem, semester):
    syllabus = loader.from_fixture(FIXTURES / f"{stem}.txt")
    tree = structure.parse(syllabus.text)
    competencies = heuristic.extract(syllabus, tree, semester=semester)

    assert len(competencies) >= 3, f"{stem} yielded only {len(competencies)}"
    for competency in competencies:
        assert competency.aliases, "a competency with no market alias is unsearchable"
        assert competency.disciplines
        assert 1 <= competency.bloom <= 6


@pytest.mark.parametrize("stem,semester", PRESETS.items(), ids=lambda v: str(v)[:24])
def test_source_spans_are_verbatim(stem, semester):
    """The bridge quotes this span back to the student. If it is not a literal
    substring, the product fabricates a claim about their own syllabus."""
    syllabus = loader.from_fixture(FIXTURES / f"{stem}.txt")
    tree = structure.parse(syllabus.text)
    for competency in heuristic.extract(syllabus, tree, semester=semester):
        assert competency.source_span in syllabus.text


def test_extraction_falls_back_without_a_key():
    syllabus = loader.from_fixture(FIXTURES / "vtu_cse_sem4_dbms.txt")
    tree = structure.parse(syllabus.text)
    result = extract_competencies(syllabus, tree, api_key=None, semester=4)
    assert result.mode == "heuristic"
    assert result.note
    assert result.competencies


def test_extraction_respects_the_limit():
    syllabus = loader.from_fixture(FIXTURES / "du_bcom_sem3_financial_management.txt")
    tree = structure.parse(syllabus.text)
    result = extract_competencies(syllabus, tree, api_key=None, semester=3, limit=2)
    assert len(result.competencies) <= 2


# --------------------------------------------------------------- cache -----

def test_cache_key_is_order_independent():
    a = cache_module.cache_key("google", {"q": "x", "num": 10, "hl": "en"})
    b = cache_module.cache_key("google", {"hl": "en", "num": 10, "q": "x"})
    assert a == b


def test_cache_key_ignores_the_api_key():
    a = cache_module.cache_key("google", {"q": "x", "api_key": "AAA"})
    b = cache_module.cache_key("google", {"q": "x", "api_key": "BBB"})
    assert a == b


def test_cache_key_changes_with_the_query():
    a = cache_module.cache_key("google", {"q": "x"})
    b = cache_module.cache_key("google", {"q": "y"})
    assert a != b


def test_demo_cache_refuses_to_write(tmp_path):
    cache = cache_module.ResponseCache(directory=tmp_path, read_only=True, ignore_ttl=True)
    cache.put("google", {"q": "x"}, {"organic_results": []})
    assert cache.get("google", {"q": "x"}) is None
    assert not list(tmp_path.glob("*.json"))


def test_cache_roundtrip(tmp_path):
    cache = cache_module.ResponseCache(directory=tmp_path, ttl_hours=72)
    payload = {"organic_results": [{"title": "t", "link": "https://x"}]}
    cache.put("google", {"q": "x"}, payload)
    assert cache.get("google", {"q": "x"}) == payload


def test_empty_result_is_billed_and_cached(tmp_path, monkeypatch):
    """SerpApi bills "no results"; re-running the same query must not pay twice."""
    from s2s.mesh import serpapi_client
    from s2s.mesh.cache import ResponseCache
    from s2s.mesh.ledger import BudgetLedger
    from s2s.mesh.serpapi_client import SerpApiClient
    from s2s.models import Dork

    calls = []

    def fake_search(params, timeout=60.0):
        calls.append(params)
        return {"error": "DuckDuckGo hasn't returned any results for this query."}

    monkeypatch.setattr(serpapi_client, "_search", fake_search)
    cache = ResponseCache(directory=tmp_path)
    dork = Dork(adapter_key="unstop", query="site:unstop.com x", covers=(), engine="duckduckgo")

    first = BudgetLedger(cap=5)
    assert SerpApiClient("key", cache, first).run(dork) == []
    assert first.spent == 1 and first.live_calls == 1 and first.skipped == 0

    second = BudgetLedger(cap=5)
    assert SerpApiClient("key", cache, second).run(dork) == []
    assert second.spent == 0 and second.cache_hits == 1
    assert len(calls) == 1


def test_duckduckgo_params_use_region_not_hl_gl(tmp_path):
    from s2s.mesh.cache import ResponseCache
    from s2s.mesh.ledger import BudgetLedger
    from s2s.mesh.serpapi_client import SerpApiClient
    from s2s.models import Dork

    client = SerpApiClient(None, ResponseCache(directory=tmp_path), BudgetLedger(cap=1))
    params = client.build_params(
        Dork(adapter_key="unstop", query="q", covers=(), engine="duckduckgo")
    )
    assert params == {"engine": "duckduckgo", "q": "q", "kl": "in-en"}
