"""Drive the real Streamlit app.

Everything else tests `s2s/`, which never imports Streamlit. These tests cover
the part that only runs in a browser: the card renderer, the score table, the
lazily-generated ship section, the download button and the gap tab.

Without them the most user-visible code in the project is the least exercised.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from s2s.mesh.cache import ResponseCache
from s2s.mesh.ledger import BudgetLedger
from s2s.mesh.serpapi_client import SerpApiClient
from tests.test_pipeline_acceptance import (
    CATCHAFIRE_PAYLOAD,
    UNSTOP_PAYLOAD,
    UNV_PAYLOAD,
)

pytest.importorskip("streamlit.testing.v1")
from streamlit.testing.v1 import AppTest  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = str(ROOT / "app.py")
PRESET = "Commerce - DU B.Com, Financial Management (Sem 3)"


@pytest.fixture
def seeded_cache(monkeypatch):
    """Point demo mode at a temp cache preloaded with SerpApi-shaped payloads."""
    from s2s.config import FIXTURE_DIR, Settings
    from s2s.extract import extract_competencies
    from s2s.ingest import loader, structure
    from s2s.mesh import cache as cache_module
    from s2s.mesh import planner

    tmp = pathlib.Path(tempfile.mkdtemp())
    settings = Settings.load()

    syllabus = loader.from_fixture(
        FIXTURE_DIR / "syllabi" / "du_bcom_sem3_financial_management.txt"
    )
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
        "unv": UNV_PAYLOAD,
        "unstop": UNSTOP_PAYLOAD,
        "catchafire": CATCHAFIRE_PAYLOAD,
    }
    cache = ResponseCache(directory=tmp, ttl_hours=10**6)
    client = SerpApiClient(None, cache, BudgetLedger(cap=99))
    for dork in dorks:
        payload = payloads.get(dork.adapter_key)
        if payload is not None:
            cache.put(dork.engine, client.build_params(dork), payload)

    monkeypatch.setattr(
        cache_module,
        "build",
        lambda _s: ResponseCache(
            directory=tmp, ttl_hours=10**6, read_only=True, ignore_ttl=True
        ),
    )
    return tmp


def _run_with_preset(seeded: bool = True) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    for toggle in at.toggle:
        if "Demo mode" in toggle.label:
            toggle.set_value(True)
    at.run()
    at.selectbox[0].set_value(PRESET)
    at.run()
    next(b for b in at.button if "Find me live work" in b.label).click()
    at.run()
    return at


# ------------------------------------------------------------ smoke -------

def test_app_loads_without_exceptions():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    assert not at.exception


def test_clicking_find_work_runs_the_pipeline():
    at = _run_with_preset()
    assert not at.exception
    labels = {m.label for m in at.metric}
    assert {"Competencies", "Searches used", "Credit saving"} <= labels


def test_credit_saving_is_shown():
    at = _run_with_preset()
    saving = next(m for m in at.metric if m.label == "Credit saving")
    assert saving.value.endswith("%")


# ------------------------------------------------- cards actually render ---

def test_cards_render_when_results_exist(seeded_cache):
    at = _run_with_preset()
    assert not at.exception, [e.value for e in at.exception]

    found = next(m for m in at.metric if m.label == "Opportunities")
    assert int(found.value) >= 1, "seeded cache produced no opportunities"

    # Each card renders a Match metric alongside the summary metrics.
    match_metrics = [m for m in at.metric if m.label == "Match"]
    assert match_metrics, "no opportunity cards rendered"
    assert all(m.value.endswith("%") for m in match_metrics)


def test_expanded_card_shows_score_breakdown_and_ship_assets(seeded_cache):
    """The ship section is generated lazily inside the expander, so this is the
    only test that executes bridge + blueprint + STAR through the UI."""
    at = _run_with_preset()
    assert not at.exception

    body = " ".join(str(m.value) for m in at.markdown)
    assert "Why you can already do this" in body
    assert "Your ship blueprint" in body
    assert "Proof of work" in body

    # The download button is built from the case study markdown.
    assert any(".md" in str(b.label) or "case study" in str(b.label).lower()
               for b in at.get("download_button")), "no case-study download button"


def test_gap_tab_renders(seeded_cache):
    at = _run_with_preset()
    assert not at.exception
    body = " ".join(str(m.value) for m in at.markdown)
    assert "units led to live work" in body or "matched no live market" in body


# -------------------------------------------------------- honesty paths ---

def test_without_fixtures_the_app_says_so_rather_than_faking_it():
    at = _run_with_preset()
    assert not at.exception
    messages = " ".join(w.value for w in at.warning)
    assert "no cached fixture" in messages or "ANTHROPIC_API_KEY" in messages


def test_gap_report_refuses_to_blame_the_curriculum_without_searches():
    at = _run_with_preset()
    messages = " ".join(w.value for w in at.warning)
    assert "no searches ran" in messages.lower()


def test_no_serpapi_key_is_surfaced_not_hidden():
    at = AppTest.from_file(APP, default_timeout=120)
    at.run()
    errors = " ".join(e.value for e in at.error)
    assert "SerpApi" in errors
