"""Time the five-preset demo from start to end, in demo mode.

    .venv/bin/python scripts/time_demo.py            # with link checks, as on stage
    .venv/bin/python scripts/time_demo.py --no-probe # pipeline only

Spends no SerpApi credit: demo mode reads the recorded fixtures only. The link
checks are real HTTP, so the times depend on the network, as they will on stage.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from s2s import pipeline                      # noqa: E402
from s2s.config import FIXTURE_DIR, Settings  # noqa: E402
from s2s.ingest import loader                 # noqa: E402

PRESETS = {
    "du_bcom_sem3_financial_management": 3,
    "bdes_sem1_typography_visual_communication": 1,
    "vtu_cse_sem4_dbms": 4,
    "du_sociology_sem2_research_methods": 2,
    "sppu_bsc_stats_sem5_biostatistics": 5,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-probe", action="store_true", help="skip link checks")
    args = parser.parse_args()

    settings = Settings.load()
    settings.demo_mode = True
    if args.no_probe:
        settings.probe_top_n = 0

    print(f"{'preset':<44} {'secs':>6} {'live':>5} {'unver':>6} {'arch':>5}  ledger")
    total = 0.0
    for stem, semester in PRESETS.items():
        syllabus = loader.from_fixture(FIXTURE_DIR / "syllabi" / f"{stem}.txt")
        start = time.perf_counter()
        result = pipeline.run(syllabus, settings, semester=semester)
        took = time.perf_counter() - start
        total += took
        print(f"{stem:<44} {took:6.1f} {len(result.live):5} {len(result.unverified):6} "
              f"{len(result.archived):5}  {result.ledger.summary()}")
    print(f"{'TOTAL':<44} {total:6.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
