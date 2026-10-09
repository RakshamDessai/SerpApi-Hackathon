"""Stage 4: the Grounding Gate.

Feature 50 in the vision doc promises "100% verifiable live URLs". That cannot be
honoured against platforms that gate their detail pages, so this module replaces
an unverifiable claim with a verified verdict on every card:

    live        checked and reachable
    unverified  not probed, or the probe was inconclusive
    archived    reachable but closed/expired, or 404, or bounced to a login wall

Three tiers, cheapest first. Tiers 0 and 1 are free. Tier 2 is a plain HTTP
request - it costs no SerpApi credit.
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from s2s.mesh import adapters as adapter_registry
from s2s.models import RawResult, Verdict

log = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 S2S-LinkVerifier/0.1"
)

#: Phrases that mean "closed" on almost any board, checked in addition to each
#: adapter's own `gate_markers`.
GENERIC_DEAD_MARKERS = (
    "no longer available",
    "no longer accepting",
    "applications are closed",
    "application deadline has passed",
    "this opportunity has ended",
    "has expired",
    "registration closed",
)

#: Modern listing pages are React shells: GitHub serves ~400 KB and puts the
#: issue state in an embedded JSON payload far past the first screenful. A
#: 60 KB window silently missed it and reported closed issues as live.
MAX_BODY_CHARS = 600_000


def tier0_url_shape(result: RawResult) -> bool:
    """Does the URL look like an actual opportunity page on that platform?

    The cheapest, highest-yield filter in the system. A `site:` dork happily
    returns homepages, category listings and blog posts; this removes them
    before anything expensive runs.
    """
    adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
    if adapter is None:
        return False
    return re.match(adapter.url_pattern, result.url or "", re.IGNORECASE) is not None


def tier1_snippet(result: RawResult) -> Verdict | None:
    """Free signals from the SERP snippet. Returns 'archived' or None."""
    adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
    markers = tuple(adapter.gate_markers) if adapter else ()
    haystack = f"{result.title} {result.snippet}".lower()

    for marker in markers + GENERIC_DEAD_MARKERS:
        if marker and marker.lower() in haystack:
            return "archived"
    return None


def tier2_probe(result: RawResult, timeout: float = 3.0) -> Verdict:
    """Fetch the page and decide. Costs no SerpApi credit."""
    adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
    if adapter is None:
        return "unverified"

    try:
        import requests

        response = requests.get(
            result.url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "en"},
        )
    except Exception as exc:
        log.debug("probe failed for %s: %s", result.url, exc)
        return "unverified"

    if response.status_code == 404 or response.status_code >= 500:
        return "archived"
    if response.status_code != 200:
        return "unverified"

    # The login-wall case: HTTP 200, but the final URL is a sign-in page.
    # Checking the post-redirect URL is what catches Upwork and Catchafire.
    if not re.match(adapter.url_pattern, response.url or "", re.IGNORECASE):
        return "archived"

    body = (response.text or "")[:MAX_BODY_CHARS].lower()
    for marker in tuple(adapter.gate_markers) + GENERIC_DEAD_MARKERS:
        if marker and marker.lower() in body:
            return "archived"

    return "live"


def verify(
    results: list[RawResult],
    probe_top_n: int = 12,
    timeout: float = 3.0,
    enable_probe: bool = True,
) -> list[tuple[RawResult, Verdict, datetime | None]]:
    """Run the full gate. Returns (result, verdict, verified_at) per surviving item.

    Tier-0 failures are dropped entirely: they are not opportunities at all, so
    there is nothing to label.
    """
    survivors = [r for r in results if tier0_url_shape(r)]
    dropped = len(results) - len(survivors)
    if dropped:
        log.info("gate tier 0 dropped %d of %d results", dropped, len(results))

    verdicts: list[tuple[RawResult, Verdict, datetime | None]] = []
    to_probe: list[int] = []

    for index, result in enumerate(survivors):
        snippet_verdict = tier1_snippet(result)
        if snippet_verdict == "archived":
            verdicts.append((result, "archived", None))
            continue
        verdicts.append((result, "unverified", None))
        adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
        if enable_probe and adapter is not None and adapter.liveness == "http_probe":
            to_probe.append(index)

    to_probe = to_probe[:probe_top_n]
    if not to_probe:
        return verdicts

    def _run(index: int) -> tuple[int, Verdict]:
        return index, tier2_probe(verdicts[index][0], timeout=timeout)

    with ThreadPoolExecutor(max_workers=min(8, len(to_probe))) as pool:
        for index, verdict in pool.map(_run, to_probe):
            result, _, _ = verdicts[index]
            verdicts[index] = (result, verdict, datetime.now())

    return verdicts
