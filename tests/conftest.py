from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from s2s.models import Competency, Discipline, RawResult  # noqa: E402

FIXTURES = ROOT / "fixtures" / "syllabi"

PRESETS = {
    "du_bcom_sem3_financial_management": 3,
    "bdes_sem1_typography_visual_communication": 1,
    "vtu_cse_sem4_dbms": 4,
    "du_sociology_sem2_research_methods": 2,
    "sppu_bsc_stats_sem5_biostatistics": 5,
}


#: Variables a developer's real .env may set. Tests must behave identically
#: with or without them - and must never spend a real SerpApi credit.
ENV_VARS = (
    "SERPAPI_API_KEY", "ANTHROPIC_API_KEY", "S2S_DEMO_MODE", "S2S_CREDIT_CAP",
    "S2S_MAX_PLATFORMS", "S2S_TERMS_PER_DORK", "S2S_MAX_COMPETENCIES",
    "S2S_CACHE_TTL_HOURS", "S2S_INCLUDE_TIER_C", "S2S_PROBE_TOP_N",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch):
    """Keep the developer's .env out of every test.

    Once a real key went into .env, the "no key" UI test started failing and
    any test that missed a fixture could have made a paid call.
    """
    import s2s.config

    monkeypatch.setattr(s2s.config, "load_dotenv", lambda *a, **k: False)
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Link probes are real HTTP; tests that need one call the gate directly.
    monkeypatch.setenv("S2S_PROBE_TOP_N", "0")


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 10, 8, 12, 0, 0)


@pytest.fixture
def competency() -> Competency:
    return Competency(
        canonical="Working Capital Management",
        aliases=["cash flow forecast", "working capital", "liquidity analysis"],
        tools=["Excel", "Google Sheets"],
        disciplines=[Discipline.COMMERCE_FINANCE],
        bloom=4,
        band="intermediate",
        source_unit="Unit 3: Working Capital Management",
        source_span="Operating cycle and cash conversion cycle.",
        span_offset=100,
    )


@pytest.fixture
def fresh_result(now: datetime) -> RawResult:
    return RawResult(
        title="Build a cash flow forecast for a community clinic",
        url="https://www.onlinevolunteering.org/en/opportunity/abc-123",
        snippet=(
            "A non-profit needs a volunteer to prepare a cash flow forecast "
            "and budget report in Excel. Beginner friendly."
        ),
        adapter_key="unv",
        organization="Health Access",
        posted_at=now - timedelta(days=3),
    )
