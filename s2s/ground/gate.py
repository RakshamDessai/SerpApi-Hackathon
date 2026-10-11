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
from urllib.parse import urlsplit

from s2s.config import USER_AGENT
from s2s.mesh import adapters as adapter_registry
from s2s.models import RawResult, StatusApi, Verdict

log = logging.getLogger(__name__)


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

#: Parallel link checks. Most probes wait on a slow host, not on CPU: with 8
#: workers the slowest preset spent ~20 s waiting (measured 2026-10-11). The
#: probes go to many different hosts, so 16 is still gentle on each one.
PROBE_WORKERS = 16


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


#: Boards stamp the edition year into the title ("Budget Battle - 2026",
#: "Financial Modeling & Valuation Competition - 2020"). Search indexes keep
#: old editions for years; with no posting date they otherwise rank as fresh.
TITLE_YEAR_RE = re.compile(r"\b(20[1-9]\d)\b")


def stale_by_title_year(title: str, now: datetime | None = None) -> bool:
    """True when every year in the title is already in the past."""
    years = [int(y) for y in TITLE_YEAR_RE.findall(title)]
    current = (now or datetime.now()).year
    return bool(years) and max(years) < current


def tier1_snippet(result: RawResult, now: datetime | None = None) -> Verdict | None:
    """Free signals from the SERP snippet. Returns 'archived' or None."""
    adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
    markers = tuple(adapter.gate_markers) if adapter else ()
    haystack = f"{result.title} {result.snippet}".lower()

    if stale_by_title_year(result.title, now):
        return "archived"

    if dead_marker_in(haystack, markers + GENERIC_DEAD_MARKERS):
        return "archived"
    return None


#: Credentials the gate may send, by `StatusApi.auth` name:
#: "kaggle" -> (username, key) for HTTP basic auth, "github" -> (token,).
Credentials = dict[str, tuple[str, ...]]


def _usable(api: StatusApi | None, credentials: Credentials | None) -> StatusApi | None:
    if api is None:
        return None
    if api.auth_required and not (credentials or {}).get(api.auth or ""):
        return None
    return api


def status_api_for(
    result: RawResult, credentials: Credentials | None = None
) -> StatusApi | None:
    """The status endpoint that can speak for this URL, if any.

    Usually the result's own adapter. A Google Jobs card links to the posting
    on its home board, so a job hosted on Unstop is checked with Unstop's API -
    its page is the same empty shell as an Unstop competition. An endpoint
    that needs a credential the student has not given does not count.
    """
    adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
    if adapter is not None and adapter.status_api is not None:
        return _usable(adapter.status_api, credentials)
    host = urlsplit(result.url or "").netloc.lower()
    for other in adapter_registry.ADAPTERS.values():
        if other.status_api and other.site and (
            host == other.site or host.endswith("." + other.site)
        ):
            return _usable(other.status_api, credentials)
    return None


def _fetch_status(
    api: StatusApi, ident: str, timeout: float, credentials: Credentials | None = None
):
    import requests

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **api.headers}
    auth = None
    secret = (credentials or {}).get(api.auth or "")
    if secret and len(secret) == 2:
        auth = secret                                    # HTTP basic (Kaggle)
    elif secret:
        headers["Authorization"] = f"Bearer {secret[0]}"  # token (GitHub)
    return requests.get(api.url.format(id=ident), headers=headers,
                        timeout=timeout, auth=auth)


def _pick(node, api: StatusApi, ident: str):
    """From a search-list answer, the item for this listing, else None."""
    if api.list_key is None:
        return node
    if not isinstance(node, list):
        return None
    for item in node:
        value = str((item or {}).get(api.list_key, "")).rstrip("/")
        if value == ident or value.endswith("/" + ident):
            return item
    return None


def status_api_probe(
    result: RawResult, timeout: float = 3.0, credentials: Credentials | None = None
) -> Verdict:
    """Ask the platform's own status endpoint. Costs no SerpApi credit.

    Archived if the status is a dead value, the deadline has passed, or a
    required field fails. Live only if at least one signal was actually read;
    anything unreadable (rate limit, changed schema) fails soft to unverified.
    """
    api = status_api_for(result, credentials)
    if api is None:
        return "unverified"
    match = re.search(api.id_re, result.url or "")
    if not match:
        return "unverified"
    try:
        response = _fetch_status(api, match.group(1), timeout, credentials)
        node = response.json()
    except Exception as exc:
        log.debug("status api failed for %s: %s", result.url, exc)
        return "unverified"

    if response.status_code == 404:
        return "archived"
    if response.status_code in (401, 403):
        return "unverified"              # bad token or rate limit: say nothing
    node = _pick(node, api, match.group(1))
    if node is None:
        return "unverified"

    read_something = False
    if api.path:
        status = _dig(node, api.path)
        if isinstance(status, str) and status:
            read_something = True
            if status.upper() in api.dead:
                return "archived"

    if api.deadline:
        closes = _dig(node, api.deadline)
        if isinstance(closes, str) and closes:
            try:
                closing = datetime.fromisoformat(closes.replace("Z", "+00:00"))
                read_something = True
                if closing < datetime.now(closing.tzinfo):
                    return "archived"
            except ValueError:
                pass

    if api.require is not None:
        path, wanted = api.require
        actual = _dig(node, path)
        if actual is not None:
            read_something = True
            if actual != wanted:
                return "archived"

    return "live" if read_something else "unverified"


def _dig(node, path: tuple[str | int, ...]):
    for key in path:
        if isinstance(key, int):
            if not isinstance(node, list) or len(node) <= key:
                return None
            node = node[key]
        else:
            if not isinstance(node, dict):
                return None
            node = node.get(key)
    return node


def tier2_probe(
    result: RawResult, timeout: float = 3.0, credentials: Credentials | None = None
) -> Verdict:
    """Fetch the page and decide. Costs no SerpApi credit."""
    adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
    if adapter is None:
        return "unverified"
    if status_api_for(result, credentials) is not None:
        return status_api_probe(result, timeout=timeout, credentials=credentials)
    if adapter.liveness != "http_probe":
        # e.g. Kaggle: its page is a shell, so a 200 would be read as "live".
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
    if dead_marker_in(body, tuple(adapter.gate_markers) + GENERIC_DEAD_MARKERS):
        return "archived"

    return "live"


_HIDDEN_RE = re.compile(r"<(script|style|template)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def visible_text(html: str) -> str:
    """Page text a reader would see: scripts, styles and tags removed."""
    return re.sub(r"\s+", " ", _TAG_RE.sub(" ", _HIDDEN_RE.sub(" ", html)))


def dead_marker_in(body: str, markers: tuple[str, ...]) -> bool:
    """Does any closed-listing marker appear where it actually means closed?

    Plain-English markers are matched against VISIBLE text only. Observed
    2026-10-10: every BeBee job page ships an i18n bundle containing "this job
    is no longer accepting applications" and "this request has expired", so a
    raw-body match archived open jobs posted that week. Markers written as JSON
    tokens (starting with a quote, e.g. WorkIndia's `"is_expired":true`) live in
    embedded data by design and are matched against the raw body. Markers
    starting with "re:" are regexes over visible text, for wording that is only
    specific with its context ("completed sep 2026").
    """
    lowered = body.lower()
    visible: str | None = None
    for marker in markers:
        if not marker:
            continue
        needle = marker.lower()
        if needle.startswith("re:"):
            if visible is None:
                visible = visible_text(lowered)
            if re.search(needle[3:], visible):
                return True
            continue
        if needle.startswith('"'):
            if needle in lowered:
                return True
            continue
        if visible is None:
            visible = visible_text(lowered)
        if needle in visible:
            return True
    return False


def verify(
    results: list[RawResult],
    probe_top_n: int = 12,
    timeout: float = 3.0,
    enable_probe: bool = True,
    credentials: Credentials | None = None,
) -> list[tuple[RawResult, Verdict, datetime | None]]:
    """Run the full gate. Returns (result, verdict, verified_at) per surviving item.

    Tier-0 failures are dropped entirely: they are not opportunities at all, so
    there is nothing to label. A result whose source already proved it open
    (`RawResult.verdict`) keeps that verdict and is not probed again.
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
        if result.verdict is not None:
            verdicts.append((result, result.verdict, datetime.now()))
            continue
        verdicts.append((result, "unverified", None))
        adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
        if enable_probe and adapter is not None and (
            adapter.liveness == "http_probe"
            or status_api_for(result, credentials) is not None
        ):
            to_probe.append(index)

    to_probe = to_probe[:probe_top_n]
    if not to_probe:
        return verdicts

    def _run(index: int) -> tuple[int, Verdict]:
        return index, tier2_probe(verdicts[index][0], timeout=timeout,
                                  credentials=credentials)

    with ThreadPoolExecutor(max_workers=min(PROBE_WORKERS, len(to_probe))) as pool:
        for index, verdict in pool.map(_run, to_probe):
            result, _, _ = verdicts[index]
            verdicts[index] = (result, verdict, datetime.now())

    return verdicts
