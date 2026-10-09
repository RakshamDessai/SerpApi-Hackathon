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
}


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
