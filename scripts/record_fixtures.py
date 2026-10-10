"""Record real SerpApi responses into fixtures/serpapi/ for demo mode.

Run this ONCE with a real key. Afterwards the whole app runs offline and the
stage demo provably cannot spend a credit.

    .venv/bin/python scripts/record_fixtures.py              # all four presets
    .venv/bin/python scripts/record_fixtures.py --dry-run    # show the plan + cost
    .venv/bin/python scripts/record_fixtures.py --only vtu_cse_sem4_dbms

Cost is printed before anything is spent, and `--max-credits` is a hard stop.
Fixtures are keyed by the same hash the live cache uses, so a recorded response
is simply a cache hit at demo time - no separate code path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from s2s.config import FIXTURE_DIR, Settings          # noqa: E402
from s2s.extract import extract_competencies          # noqa: E402
from s2s.ingest import loader, structure              # noqa: E402
from s2s.mesh import planner                          # noqa: E402
from s2s.mesh.cache import ResponseCache, cache_key   # noqa: E402
from s2s.mesh.ledger import BudgetLedger              # noqa: E402
from s2s.mesh.serpapi_client import SerpApiClient     # noqa: E402

# preset stem -> semester
PRESETS = {
    "du_bcom_sem3_financial_management": 3,
    "bdes_sem1_typography_visual_communication": 1,
    "vtu_cse_sem4_dbms": 4,
    "du_sociology_sem2_research_methods": 2,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and credit cost, call nothing")
    parser.add_argument("--only", help="record a single preset by filename stem")
    parser.add_argument("--max-credits", type=int, default=60,
                        help="hard ceiling across the whole run (default 60)")
    args = parser.parse_args()

    settings = Settings.load()
    if not settings.has_serpapi and not args.dry_run:
        print("ERROR: SERPAPI_API_KEY is not set in .env - nothing to record.")
        print("       Add the key, or re-run with --dry-run to see the plan.")
        return 1

    presets = PRESETS
    if args.only:
        if args.only not in PRESETS:
            print(f"ERROR: unknown preset {args.only!r}. Choose from:")
            for name in PRESETS:
                print(f"  {name}")
            return 1
        presets = {args.only: PRESETS[args.only]}

    fixture_dir = FIXTURE_DIR / "serpapi"
    fixture_dir.mkdir(parents=True, exist_ok=True)

    # Plan everything first so the total cost is known before any spend.
    plans = []
    for stem, semester in presets.items():
        path = FIXTURE_DIR / "syllabi" / f"{stem}.txt"
        syllabus = loader.from_fixture(path)
        tree = structure.parse(syllabus.text)
        competencies = extract_competencies(
            syllabus, tree, api_key=settings.anthropic_key,
            semester=semester, limit=settings.max_competencies,
        ).competencies
        dorks = planner.plan(
            competencies,
            credit_cap=settings.credit_cap,
            max_platforms=settings.max_platforms,
            terms_per_dork=settings.terms_per_dork,
            include_tier_c=settings.include_tier_c,
        )
        plans.append((stem, dorks))
        print(f"{stem}: {len(competencies)} competencies -> {len(dorks)} searches")

    total = sum(len(d) for _, d in plans)
    print(f"\nTotal: {total} SerpApi credits (cap {args.max_credits})")

    if args.dry_run:
        print("\n--dry-run: nothing called. Sample queries:")
        for stem, dorks in plans:
            if dorks:
                print(f"  [{stem}] {dorks[0].query[:120]}")
        return 0

    if total > args.max_credits:
        print(f"ERROR: plan needs {total} credits, over --max-credits={args.max_credits}.")
        print("       Raise the ceiling or use --only to record one preset.")
        return 1

    cache = ResponseCache(directory=fixture_dir, ttl_hours=10 ** 6)
    ledger = BudgetLedger(cap=args.max_credits)
    client = SerpApiClient(
        api_key=settings.serpapi_key,
        cache=cache,
        ledger=ledger,
        demo_mode=False,
        results_per_search=settings.results_per_search,
    )

    print()
    for stem, dorks in plans:
        print(f"recording {stem}...")
        for dork in dorks:
            # A harvested stand-in shares this dork's cache key, so it would be
            # served as a hit and the real SerpApi response never recorded.
            params = client.build_params(dork)
            stale = cache.get(dork.engine, params)
            if stale is not None and stale.get("s2s_source"):
                (fixture_dir / f"{cache_key(dork.engine, params)}.json").unlink()
                print(f"   {dork.adapter_key:<16} replacing harvested fixture")
            results = client.run(dork)
            print(f"   {dork.adapter_key:<16} {len(results):>3} results   {dork.query[:70]}")

    count, size = cache.stats()
    print(f"\n{ledger.summary()}")
    print(f"fixtures: {count} files, {size / 1024:.0f} KB in {fixture_dir}")
    print("\nDemo mode will now run fully offline. Set S2S_DEMO_MODE=true in .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
