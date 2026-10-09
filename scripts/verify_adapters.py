"""Verify the adapter registry against the real internet - no SerpApi key needed.

PROBLEM THIS SOLVES
Two things in s2s/mesh/adapters.py were written from assumption rather than
observation, and both fail silently:

  url_pattern    Grounding Gate tier 0. If the regex does not match the URLs a
                 platform actually serves, every result from that platform is
                 dropped and it looks like "the platform had no matches".
  gate_markers   Grounding Gate tier 2. If the wording is wrong, a closed
                 listing is reported as live - the exact failure the gate
                 exists to prevent. (This really happened: GitHub's markers
                 were invented and a closed issue scored as `live`.)

HOW IT WORKS
Each platform publishes its own listing page. We fetch that page directly over
plain HTTP, harvest real detail URLs from it, then:

  1. check `url_pattern` actually matches those real URLs
  2. probe a sample and report which `gate_markers` fired, if any
  3. report the verdict distribution the Grounding Gate would produce

No SerpApi credit is spent. This is a developer tool, so the discovery config
lives here rather than polluting the product registry.

USAGE
    .venv/bin/python scripts/verify_adapters.py              # all reachable
    .venv/bin/python scripts/verify_adapters.py --only github kaggle
    .venv/bin/python scripts/verify_adapters.py --samples 5
    .venv/bin/python scripts/verify_adapters.py --json report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from s2s.ground import gate  # noqa: E402
from s2s.mesh.adapters import ADAPTERS  # noqa: E402
from s2s.models import RawResult  # noqa: E402

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "en"}


@dataclass
class Discovery:
    """Where a platform lists its own opportunities, and how to pull links out.

    `link_re` runs against the raw HTML and must capture a URL or path in
    group 1. Deliberately regex rather than a parser: these pages are mostly
    React shells where the useful links live in embedded JSON, which a DOM
    parser would not see anyway.
    """

    listing: str
    link_re: str
    absolute: bool = True          # False => join against `base`
    base: str = ""
    api: str | None = None         # preferred JSON source, when one exists
    api_field: str = "html_url"


DISCOVERY: dict[str, Discovery] = {
    "github": Discovery(
        listing="https://github.com/search?q=label%3A%22good+first+issue%22+state%3Aopen&type=issues",
        link_re=r"",
        # GitHub has a real API, so use it rather than scraping the SPA.
        api=(
            "https://api.github.com/search/issues"
            "?q=label:%22good+first+issue%22+state:open+language:python&per_page=8"
        ),
    ),
    "kaggle": Discovery(
        listing="https://www.kaggle.com/competitions",
        link_re=r'"competitionUrl"\s*:\s*"(/competitions/[^"]+)"|href="(/competitions/[\w\-]+)"',
        absolute=False,
        base="https://www.kaggle.com",
    ),
    "devpost": Discovery(
        listing="https://devpost.com/api/hackathons",
        link_re=r'"url"\s*:\s*"(https://[\w\-]+\.devpost\.com/?)"',
    ),
    "drivendata": Discovery(
        listing="https://www.drivendata.org/competitions/",
        link_re=r'href="(/competitions/\d+/[^"]+)"',
        absolute=False,
        base="https://www.drivendata.org",
    ),
    "zooniverse": Discovery(
        listing="https://www.zooniverse.org/projects",
        link_re=r'href="(/projects/[\w\-]+/[\w\-]+)"',
        absolute=False,
        base="https://www.zooniverse.org",
    ),
    "unstop": Discovery(
        listing="https://unstop.com/competitions",
        link_re=r'href="(/(?:competitions|hackathons|o)/[\w\-]+)"|'
                r'"public_url"\s*:\s*"([^"]+)"',
        absolute=False,
        base="https://unstop.com",
    ),
    "devfolio": Discovery(
        listing="https://devfolio.co/hackathons",
        link_re=r'"slug"\s*:\s*"([\w\-]+)"',
        absolute=False,
        base="https://",  # slug.devfolio.co
    ),
    "catchafire": Discovery(
        listing="https://www.catchafire.org/opportunities/",
        link_re=r'href="(/opportunities/[\w\-]+/?)"',
        absolute=False,
        base="https://www.catchafire.org",
    ),
    "idealist": Discovery(
        listing="https://www.idealist.org/en/volops",
        link_re=r'href="(/en/volop/[\w\-]+)"',
        absolute=False,
        base="https://www.idealist.org",
    ),
    "volunteermatch": Discovery(
        listing="https://www.volunteermatch.org/search/",
        link_re=r'href="(/search/opp\d+\.jsp)"',
        absolute=False,
        base="https://www.volunteermatch.org",
    ),
    "taproot": Discovery(
        listing="https://taprootplus.org/projects",
        link_re=r'href="(/projects/[\w\-]+)"',
        absolute=False,
        base="https://taprootplus.org",
    ),
}


@dataclass
class AdapterReport:
    key: str
    tier: str
    reachable: bool = False
    listing_status: int | None = None
    urls_found: int = 0
    pattern_matches: int = 0
    pattern_failures: list[str] = field(default_factory=list)
    probed: int = 0
    verdicts: dict[str, int] = field(default_factory=dict)
    markers_fired: dict[str, int] = field(default_factory=dict)
    note: str = ""

    @property
    def pattern_ok(self) -> bool:
        return self.urls_found > 0 and self.pattern_matches == self.urls_found

    @property
    def status(self) -> str:
        if not self.reachable:
            return "UNREACHABLE"
        if self.urls_found == 0:
            return "NO-URLS"
        if not self.pattern_ok:
            return "PATTERN-FAIL"
        if self.probed and self.verdicts.get("live", 0) == 0:
            return "NEVER-LIVE"
        return "OK"


def harvest(key: str, disc: Discovery, limit: int) -> tuple[list[str], int | None, str]:
    """Pull real detail URLs straight from the platform's own listing."""
    target = disc.api or disc.listing
    try:
        response = requests.get(target, timeout=20, headers=HEADERS)
    except Exception as exc:
        return [], None, f"{type(exc).__name__}"

    if response.status_code != 200:
        return [], response.status_code, f"HTTP {response.status_code}"

    urls: list[str] = []

    if disc.api:
        try:
            payload = response.json()
            items = payload.get("items") or payload.get("hackathons") or []
            for item in items:
                value = item.get(disc.api_field) or item.get("url")
                if value:
                    urls.append(value)
        except Exception as exc:
            return [], response.status_code, f"bad JSON: {type(exc).__name__}"
    else:
        for match in re.finditer(disc.link_re, response.text):
            captured = next((g for g in match.groups() if g), None)
            if not captured:
                continue
            if disc.absolute:
                url = captured
            elif key == "devfolio":
                url = f"https://{captured}.devfolio.co/"
            else:
                url = disc.base + captured
            if url not in urls:
                urls.append(url)

    return urls[:limit], response.status_code, ""


def verify_one(key: str, samples: int, timeout: float) -> AdapterReport:
    adapter = ADAPTERS[key]
    report = AdapterReport(key=key, tier=adapter.trust)

    disc = DISCOVERY.get(key)
    if disc is None:
        report.note = "no discovery config (engine-based adapter)"
        return report

    urls, status, note = harvest(key, disc, samples)
    report.listing_status = status
    report.reachable = status == 200
    report.note = note
    report.urls_found = len(urls)

    if not urls:
        return report

    # 1. does tier 0 accept URLs the platform really serves?
    for url in urls:
        if re.match(adapter.url_pattern, url, re.IGNORECASE):
            report.pattern_matches += 1
        elif len(report.pattern_failures) < 3:
            report.pattern_failures.append(url)

    # 2. what does tier 2 actually say about them?
    def probe(url: str) -> tuple[str, list[str]]:
        result = RawResult(title="", url=url, snippet="", adapter_key=key)
        verdict = gate.tier2_probe(result, timeout=timeout)
        fired: list[str] = []
        if verdict == "archived":
            try:
                body = requests.get(url, timeout=timeout, headers=HEADERS).text.lower()
                fired = [m for m in adapter.gate_markers if m.lower() in body]
            except Exception:
                pass
        return verdict, fired

    probe_urls = [u for u in urls if re.match(adapter.url_pattern, u, re.IGNORECASE)][:samples]
    if probe_urls:
        with ThreadPoolExecutor(max_workers=min(5, len(probe_urls))) as pool:
            for verdict, fired in pool.map(probe, probe_urls):
                report.probed += 1
                report.verdicts[verdict] = report.verdicts.get(verdict, 0) + 1
                for marker in fired:
                    report.markers_fired[marker] = report.markers_fired.get(marker, 0) + 1

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="adapter keys to check")
    parser.add_argument("--samples", type=int, default=4, help="URLs per platform")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--json", help="also write the full report here")
    args = parser.parse_args()

    keys = args.only or [k for k in ADAPTERS if k in DISCOVERY]
    unknown = [k for k in keys if k not in ADAPTERS]
    if unknown:
        print(f"unknown adapter keys: {unknown}")
        return 1

    print(f"Verifying {len(keys)} adapters against live pages "
          f"({args.samples} samples each). No SerpApi credits used.\n")

    reports: list[AdapterReport] = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        for report in pool.map(lambda k: verify_one(k, args.samples, args.timeout), keys):
            reports.append(report)

    reports.sort(key=lambda r: (r.tier, r.key))

    print(f"{'adapter':<16} {'tier':<5} {'status':<13} {'urls':>5} {'tier0':>7} {'verdicts'}")
    print("-" * 78)
    for r in reports:
        t0 = f"{r.pattern_matches}/{r.urls_found}" if r.urls_found else "-"
        verdicts = ", ".join(f"{k}:{v}" for k, v in sorted(r.verdicts.items())) or "-"
        print(f"  {r.key:<14} {r.tier:<5} {r.status:<13} {r.urls_found:>5} {t0:>7} {verdicts}")
        if r.pattern_failures:
            print(f"       url_pattern REJECTED real URLs, e.g. {r.pattern_failures[0]}")
        if r.markers_fired:
            print(f"       markers that fired: {dict(r.markers_fired)}")
        if r.note:
            print(f"       note: {r.note}")

    ok = [r for r in reports if r.status == "OK"]
    broken = [r for r in reports if r.status == "PATTERN-FAIL"]
    print(f"\n{len(ok)}/{len(reports)} fully OK")
    if broken:
        print(f"url_pattern BROKEN for: {', '.join(r.key for r in broken)}")
        print("  -> every result from these platforms is silently dropped by tier 0")

    never_live = [r for r in reports if r.status == "NEVER-LIVE"]
    if never_live:
        print(f"never returned 'live': {', '.join(r.key for r in never_live)}")
        print("  -> either the markers are wrong, or the site blocks our probe")

    if args.json:
        Path(args.json).write_text(
            json.dumps([asdict(r) for r in reports], indent=2), encoding="utf-8"
        )
        print(f"\nfull report -> {args.json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
