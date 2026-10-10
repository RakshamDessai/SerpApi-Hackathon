"""Give demo mode something real to show, without a SerpApi key.

THE PROBLEM
`fixtures/serpapi/` holds only .gitkeep. `cache.build()` points demo mode at it
read-only, so `SerpApiClient.run` logs "demo mode: no cached fixture" and returns
[]. With no key the Actionable tab renders empty: there is currently no demo.

THE FIX
Several platforms in the registry publish their own listings over plain HTTP with
no key at all. We fetch those, normalise them into the SerpApi `google` response
shape, and write them through the same `ResponseCache` under the same
`cache_key(engine, params)` the planner would produce. Demo mode then hits them
as ordinary cache reads - no special code path.

HONESTY (read this before demoing)
These are REAL, currently-open listings from the real platforms. They are NOT
SerpApi responses. Each record is stamped `"s2s_source": "public-api-harvest"`,
`SerpApiClient` surfaces that, and the UI labels any run containing them as
HARVESTED rather than SerpApi. Presenting harvested data as SerpApi output in a
SerpApi hackathon would be dishonest, so the provenance is carried end to end.

Once a real key exists, `scripts/record_fixtures.py` overwrites these with
genuine SerpApi responses and the label disappears on its own.

USAGE
    .venv/bin/python scripts/harvest_demo_fixtures.py            # all presets
    .venv/bin/python scripts/harvest_demo_fixtures.py --dry-run
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from s2s.config import FIXTURE_DIR, Settings  # noqa: E402
from s2s.extract import extract_competencies  # noqa: E402
from s2s.ingest import loader, structure  # noqa: E402
from s2s.mesh import planner  # noqa: E402
from s2s.mesh.cache import ResponseCache  # noqa: E402
from s2s.mesh.ledger import BudgetLedger  # noqa: E402
from s2s.mesh.serpapi_client import SerpApiClient  # noqa: E402

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en"}

PRESETS = {
    "du_bcom_sem3_financial_management": 3,
    "bdes_sem1_typography_visual_communication": 1,
    "vtu_cse_sem4_dbms": 4,
    "du_sociology_sem2_research_methods": 2,
}


@dataclass
class Listing:
    title: str
    link: str
    snippet: str
    date: str | None = None


# --------------------------------------------------------------- oracles ---
# One harvester per platform that publishes openly. Each returns only
# CURRENTLY-OPEN listings, because demo mode must not show dead work.

def harvest_devpost(limit: int) -> list[Listing]:
    r = requests.get(
        "https://devpost.com/api/hackathons?status[]=open&order_by=deadline",
        timeout=25, headers=HEADERS,
    )
    r.raise_for_status()
    out = []
    for item in (r.json().get("hackathons") or [])[:limit]:
        prizes = re.sub(r"<[^>]+>", "", item.get("prize_amount") or "").strip()
        themes = ", ".join(t.get("name", "") for t in (item.get("themes") or [])[:4])
        snippet = " ".join(filter(None, [
            item.get("displayed_location", {}).get("location", ""),
            f"Themes: {themes}." if themes else "",
            f"Prize {prizes}." if prizes else "",
            (item.get("submission_period_dates") or ""),
            "Open hackathon, submissions accepted.",
        ]))
        out.append(Listing(
            title=item.get("title", "").strip(),
            link=(item.get("url") or "").rstrip("/") + "/",
            snippet=snippet.strip(),
            date=item.get("open_state"),
        ))
    return out


def harvest_github(query: str, limit: int) -> list[Listing]:
    """Search GitHub for the student's own competency terms.

    `query` is an OR of their market phrases, so the issues that come back are
    actually about their syllabus rather than a hardcoded language filter.
    """
    r = requests.get(
        "https://api.github.com/search/issues",
        params={
            "q": f'{query} label:"good first issue" state:open',
            "per_page": limit,
            "sort": "updated",
        },
        timeout=25,
        headers={**HEADERS, "Accept": "application/vnd.github+json"},
    )
    if r.status_code == 422:        # query too complex for GitHub's parser
        return []
    r.raise_for_status()
    out = []
    for item in r.json().get("items", [])[:limit]:
        body = (item.get("body") or "").strip().replace("\n", " ")
        repo = item.get("repository_url", "").rsplit("/", 2)[-2:]
        out.append(Listing(
            title=item.get("title", ""),
            link=item.get("html_url", ""),
            snippet=(f"good first issue in {'/'.join(repo)}. {body}")[:400],
            date=item.get("created_at", "")[:10],
        ))
    return out


def harvest_drivendata(limit: int) -> list[Listing]:
    r = requests.get("https://www.drivendata.org/competitions/", timeout=25, headers=HEADERS)
    r.raise_for_status()
    out, seen = [], set()
    # The listing wraps each competition in several anchors (image, badge,
    # title). Taking the first match per path grabbed the badge text, which is
    # why every title came out as "CONCEPT COMPETITION". Keep the longest.
    best: dict[str, str] = {}
    for path, inner in re.findall(
        r'href="(/competitions/\d+/[\w\-]+/?)"[^>]*>(.*?)</a>', r.text, re.S
    ):
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        if len(text) > len(best.get(path, "")):
            best[path] = text

    for path, text in best.items():
        if path in seen:
            continue
        seen.add(path)
        if len(text) < 12 or text.isupper():
            continue
        out.append(Listing(
            title=text[:120],
            link="https://www.drivendata.org" + path,
            snippet=f"{text} Open data science competition: build a predictive "
                    f"model and submit against a public leaderboard.",
        ))
        if len(out) >= limit:
            break
    return out


def harvest_zooniverse(limit: int) -> list[Listing]:
    r = requests.get(
        "https://www.zooniverse.org/api/projects",
        params={"page_size": limit * 3, "launch_approved": "true"},
        timeout=25,
        headers={**HEADERS, "Accept": "application/vnd.api+json; version=1",
                 "Content-Type": "application/json"},
    )
    r.raise_for_status()
    out = []
    for p in (r.json().get("projects") or []):
        if p.get("completeness", 0) >= 1.0:
            continue                       # finished projects are not live work
        slug = p.get("slug")
        if not slug:
            continue
        out.append(Listing(
            title=p.get("display_name", ""),
            link=f"https://www.zooniverse.org/projects/{slug}",
            snippet=(p.get("description") or "")[:350] +
                    " Citizen science research project, volunteers welcome.",
        ))
        if len(out) >= limit:
            break
    return out


#: adapter key -> harvester. Only platforms that publish openly and for free.
ORACLES = {
    "devpost": lambda n, q: harvest_devpost(n),
    "drivendata": lambda n, q: harvest_drivendata(n),
    "zooniverse": lambda n, q: harvest_zooniverse(n),
    "github": lambda n, q: harvest_github(q, n),
}


def matching(listings: list[Listing], dork_phrases: list[str]) -> list[Listing]:
    """Keep only listings that actually match the dork's phrases.

    Harvesting once per platform and reusing the same listings for every dork
    would hand a "database schema" query the same hackathons as a "concurrency"
    query - inflating result counts while destroying relevance, and misleading
    anyone reading the match scores. A search engine filters; so do we. If
    nothing matches, the fixture is legitimately empty.
    """
    if not dork_phrases:
        return listings
    out = []
    for listing in listings:
        haystack = f"{listing.title} {listing.snippet}".lower()
        for phrase in dork_phrases:
            needle = phrase.lower().strip()
            if not needle:
                continue
            tokens = [t for t in needle.split() if len(t) > 3]
            if needle in haystack or (
                tokens and all(t in haystack for t in tokens)
            ):
                out.append(listing)
                break
    return out


def competency_phrases(dork) -> list[str]:
    """The student's own skill phrases for this dork.

    Deliberately NOT re-extracted from the rendered query: that string also
    carries each adapter's boilerplate ("good first issue", "help wanted"),
    and every harvested GitHub issue contains those by construction. Filtering
    on them let completely unrelated issues through while matching zero
    competency terms - semantic scored 0.000 on all 22 results.
    """
    phrases: list[str] = []
    for competency in dork.covers:
        for phrase in competency.search_phrases:
            if phrase not in phrases:
                phrases.append(phrase)
    return phrases


def to_serpapi_shape(listings: list[Listing], adapter_key: str, query: str) -> dict:
    """Normalise into the exact shape `SerpApiClient._parse` expects."""
    return {
        # Provenance travels with the data so nothing downstream can mistake
        # a harvested fixture for a real SerpApi response.
        "s2s_source": "public-api-harvest",
        "s2s_adapter": adapter_key,
        "s2s_query": query,
        "search_metadata": {"status": "Success", "s2s_synthetic": True},
        "organic_results": [
            {k: v for k, v in
             {"title": l.title, "link": l.link, "snippet": l.snippet, "date": l.date}.items()
             if v}
            for l in listings if l.title and l.link
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--per-platform", type=int, default=8)
    args = parser.parse_args()

    settings = Settings.load()
    fixture_dir = FIXTURE_DIR / "serpapi"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    cache = ResponseCache(directory=fixture_dir, ttl_hours=10**6)
    client = SerpApiClient(None, cache, BudgetLedger(cap=999))

    # Harvest once per platform, then reuse across every dork that targets it.
    harvested: dict[str, list[Listing]] = {}
    print("Harvesting real open listings from keyless public endpoints...\n")
    for key, fn in ORACLES.items():
        try:
            listings = fn(args.per_platform, "python")
            harvested[key] = listings
            print(f"  {key:<12} {len(listings):>3} live listings")
            for l in listings[:2]:
                print(f"       - {l.title[:68]}")
        except Exception as exc:
            print(f"  {key:<12} FAILED {type(exc).__name__}: {exc}")
            harvested[key] = []

    total_written = 0
    print()
    for stem, semester in PRESETS.items():
        syllabus = loader.from_fixture(FIXTURE_DIR / "syllabi" / f"{stem}.txt")
        tree = structure.parse(syllabus.text)
        competencies = extract_competencies(
            syllabus, tree, api_key=None, semester=semester,
            limit=settings.max_competencies,
        ).competencies
        dorks = planner.plan(
            competencies,
            credit_cap=settings.credit_cap,
            max_platforms=settings.max_platforms,
            terms_per_dork=settings.terms_per_dork,
        )

        covered = 0
        hits = 0
        for dork in dorks:
            if dork.adapter_key == "github":
                # GitHub takes a real search query, so ask it for THIS dork's
                # skills rather than reusing one generic harvest.
                terms = competency_phrases(dork)[:4]
                gh_query = " OR ".join(f'"{t}"' for t in terms)
                try:
                    listings = harvest_github(gh_query, args.per_platform)
                except Exception:
                    listings = []
            else:
                listings = harvested.get(dork.adapter_key)
            if listings is None:
                continue
            relevant = matching(listings, competency_phrases(dork))
            payload = to_serpapi_shape(relevant, dork.adapter_key, dork.query)
            if not args.dry_run:
                cache.put(dork.engine, client.build_params(dork), payload)
            covered += 1
            hits += len(relevant)
            total_written += 1

        platforms = sorted({d.adapter_key for d in dorks})
        have = sorted({d.adapter_key for d in dorks if harvested.get(d.adapter_key)})
        print(f"  {stem[:44]:<44} {covered}/{len(dorks)} dorks seeded, "
              f"{hits} matching listings")
        print(f"       plan targets {platforms}")
        print(f"       seeded       {have or '(none - no oracle for these)'}")

    count, size = cache.stats()
    print(f"\n{'[dry-run] would write' if args.dry_run else 'wrote'} {total_written} fixtures")
    if not args.dry_run:
        print(f"fixtures/serpapi: {count} files, {size/1024:.0f} KB")
        print("\nSet S2S_DEMO_MODE=true (or use the sidebar toggle) to run offline.")
        print("These are REAL listings but NOT SerpApi responses - the UI labels them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
