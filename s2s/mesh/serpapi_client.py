"""SerpApi access: cache-first, ledger-accounted, engine-aware.

Evolves the original `src/serpapi_service.py`. Differences that matter:

* Every call goes through the cache and the budget ledger, so cost is bounded
  and visible.
* Result parsing is per-engine (`organic_results` vs `jobs_results`) and
  normalises straight into `RawResult`, so downstream stages never see SerpApi's
  response shape.
* A failure returns an empty list rather than raising: one dead platform must
  not take down a run across five platforms.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from s2s.mesh import adapters as adapter_registry
from s2s.mesh.cache import ResponseCache
from s2s.mesh.ledger import BudgetLedger
from s2s.models import Dork, RawResult

log = logging.getLogger(__name__)

#: SerpApi's wording when an engine answered but matched nothing, e.g.
#: "DuckDuckGo hasn't returned any results for this query."
EMPTY_RESULT_MARKER = "hasn't returned any results"

RESULT_FIELD = {
    "google": "organic_results",
    "google_light": "organic_results",
    "duckduckgo": "organic_results",
    "google_jobs": "jobs_results",
    "google_scholar": "organic_results",
    "google_events": "events_results",
    "youtube": "video_results",
}

#: Engines that take the query as `search_query`, not `q`.
QUERY_PARAM = {"youtube": "search_query"}

# "3 days ago", "2 weeks ago", "27 minutes ago"
RELATIVE_RE = re.compile(
    r"(\d+)\s*(minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE
)
UNIT_DAYS = {
    "minute": 1 / 1440, "hour": 1 / 24, "day": 1,
    "week": 7, "month": 30, "year": 365,
}


def parse_posted_at(text: str | None, now: datetime | None = None) -> datetime | None:
    """Best-effort posting date from a snippet or a jobs `posted_at` string."""
    if not text:
        return None
    now = now or datetime.now()

    match = RELATIVE_RE.search(text)
    if match:
        amount = int(match.group(1))
        return now - timedelta(days=amount * UNIT_DAYS[match.group(2).lower()])

    for fmt in ("%b %d, %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y"):
        for candidate in re.findall(r"[A-Za-z]{3}\s+\d{1,2},\s*\d{4}|\d{4}-\d{2}-\d{2}", text):
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return None


SEARCH_URL = "https://serpapi.com/search.json"


def _search(params: dict, timeout: float = 60.0) -> dict:
    """One SerpApi call over plain HTTPS.

    Deliberately no SDK. The legacy `google-search-results` and the newer
    `serpapi` package both install a module named `serpapi` with different APIs,
    so code written against one fails silently on a machine that has the other.
    Both are thin wrappers over this endpoint. SerpApi returns its `error` field
    as JSON even on 4xx, so the body is parsed regardless of status.
    """
    import requests

    response = requests.get(SEARCH_URL, params=params, timeout=timeout)
    try:
        return response.json()
    except ValueError:
        return {"error": f"HTTP {response.status_code}: non-JSON response"}


class SerpApiClient:
    def __init__(
        self,
        api_key: str | None,
        cache: ResponseCache,
        ledger: BudgetLedger,
        demo_mode: bool = False,
        results_per_search: int = 10,
    ) -> None:
        self.api_key = api_key
        self.cache = cache
        self.ledger = ledger
        self.demo_mode = demo_mode
        self.results_per_search = results_per_search
        #: (adapter key, query) -> the parameters of SerpApi's own "next page"
        #: link, read from each response. planner.follow_ups uses it.
        self.next_params: dict[tuple[str, str], dict] = {}

    # -- request building -------------------------------------------------

    def build_params(self, dork: Dork) -> dict:
        if dork.engine in QUERY_PARAM:
            params: dict = {"engine": dork.engine, QUERY_PARAM[dork.engine]: dork.query,
                            "hl": "en", "gl": "in"}
        elif dork.engine == "duckduckgo":
            # DuckDuckGo takes a combined region code and ignores hl/gl/num.
            params = {"engine": dork.engine, "q": dork.query, "kl": "in-en"}
        else:
            params = {"engine": dork.engine, "q": dork.query, "hl": "en"}
        if dork.engine in ("google", "google_light"):
            params.update({"gl": "in", "num": self.results_per_search})
        params.update(dork.params or {})
        return params

    # -- execution --------------------------------------------------------

    def run(self, dork: Dork) -> list[RawResult]:
        response = self.fetch(dork)
        return self._parse(response, dork) if response else []

    def fetch(self, dork: Dork) -> dict | None:
        """The raw SerpApi response for one dork: cache first, then the API.

        Returns None when nothing usable came back. Every outcome is in the
        ledger, so a skipped search is never silent.
        """
        params = self.build_params(dork)

        cached = self.cache.get(dork.engine, params)
        if cached is not None:
            self.ledger.record_cached(dork.adapter_key, dork.query)
            self._remember_next(dork, cached)
            return cached

        if self.demo_mode:
            self.ledger.record_skipped(
                dork.adapter_key, dork.query, "demo mode: no cached fixture"
            )
            return None

        if not self.api_key:
            self.ledger.record_skipped(dork.adapter_key, dork.query, "no SerpApi key")
            return None

        if not self.ledger.can_afford(dork.est_cost):
            self.ledger.record_skipped(
                dork.adapter_key, dork.query, "budget cap reached"
            )
            log.warning("budget cap reached, skipping %s", dork.adapter_key)
            return None

        try:
            response = _search({**params, "api_key": self.api_key})
        except Exception as exc:
            self.ledger.record_skipped(dork.adapter_key, dork.query, f"error: {exc}")
            log.warning("SerpApi call failed for %s: %s", dork.adapter_key, exc)
            return None

        if "error" in response and EMPTY_RESULT_MARKER in str(response["error"]):
            # A legitimate "nothing matched" answer. SerpApi bills it (observed
            # 2026-10-10), so count the credit - and cache it, or every re-run
            # pays again for the same empty query.
            self.ledger.record_live(dork.adapter_key, dork.query, dork.est_cost)
            self.cache.put(dork.engine, params, response)
            return None

        if "error" in response:
            self.ledger.record_skipped(
                dork.adapter_key, dork.query, f"serpapi: {response['error']}"
            )
            log.warning("SerpApi error for %s: %s", dork.adapter_key, response["error"])
            return None

        self.ledger.record_live(dork.adapter_key, dork.query, dork.est_cost)
        self.cache.put(dork.engine, params, response)
        self._remember_next(dork, response)
        return response

    def _remember_next(self, dork: Dork, response: dict) -> None:
        """Keep the pagination parameters SerpApi itself offers for page 2.

        Read from `serpapi_pagination.next` rather than computed. The offset
        depends on how many results page 1 held: the recorded DuckDuckGo
        responses ask for start=11 after a full page, and start=1 to 9 after
        a short one. Google Jobs pages with a token instead of an offset.
        """
        link = (response.get("serpapi_pagination") or {}).get("next")
        if not link:
            return
        query = dict(parse_qsl(urlsplit(link).query))
        wanted = {k: query[k] for k in ("start", "next_page_token") if k in query}
        if wanted:
            self.next_params[(dork.adapter_key, dork.query)] = wanted

    # -- parsing ----------------------------------------------------------

    def _parse(self, response: dict, dork: Dork) -> list[RawResult]:
        field = RESULT_FIELD.get(dork.engine, "organic_results")
        items = response.get(field) or []
        # Fixtures harvested straight from a platform carry this stamp so the
        # UI can never present them as SerpApi output.
        provenance = response.get("s2s_source") or "serpapi"
        out: list[RawResult] = []

        for item in items:
            if dork.engine == "google_jobs":
                parsed = self._parse_job(item, dork)
            elif dork.engine == "google_events":
                parsed = self._parse_event(item, dork)
            else:
                parsed = self._parse_organic(item, dork)
            if parsed is not None:
                parsed.provenance = provenance
                out.append(parsed)
        return out

    def _parse_organic(self, item: dict, dork: Dork) -> RawResult | None:
        url = item.get("link")
        title = item.get("title")
        if not url or not title:
            return None
        url = canonical_url(dork.adapter_key, url)

        snippet = item.get("snippet") or ""
        rich = item.get("rich_snippet") or {}
        extensions = []
        for section in ("top", "bottom"):
            block = rich.get(section) or {}
            extensions.extend(block.get("extensions") or [])
        date_text = item.get("date") or " ".join(extensions)

        return RawResult(
            title=title,
            url=url,
            snippet=snippet,
            adapter_key=dork.adapter_key,
            organization=item.get("source") or item.get("displayed_link"),
            posted_at=parse_posted_at(date_text or snippet),
            raw=item,
        )

    def _parse_job(self, item: dict, dork: Dork) -> RawResult | None:
        title = item.get("title")
        if not title:
            return None

        url = job_link(item)
        if not url:
            return None

        detected = item.get("detected_extensions") or {}
        posted = detected.get("posted_at") or " ".join(item.get("extensions") or [])
        return RawResult(
            title=title,
            url=url,
            snippet=(item.get("description") or "")[:600],
            adapter_key=dork.adapter_key,
            organization=item.get("company_name"),
            posted_at=parse_posted_at(posted),
            raw=item,
        )


    def _parse_event(self, item: dict, dork: Dork) -> RawResult | None:
        title = item.get("title")
        url = event_link(item)
        if not title or not url:
            return None
        date = item.get("date") or {}
        when = date.get("when") or date.get("start_date") or ""
        venue = (item.get("venue") or {}).get("name")
        place = venue or ", ".join(item.get("address") or [])
        # The date and place lead the snippet: they are what a student needs
        # first, and the card shows the snippet as the brief.
        parts = [p for p in (when, place, item.get("description") or "") if p]
        return RawResult(
            title=title,
            url=url,
            snippet=" · ".join(parts)[:600],
            adapter_key=dork.adapter_key,
            organization=venue,
            # An event's date is when it happens, not when it was posted, so
            # it does not feed freshness scoring.
            posted_at=None,
            raw=item,
        )

    # -- free-course search for the Syllabus Gap Report ---------------------

    def courses(self, skill: str, limit: int = 3) -> list[dict]:
        """Free video courses for a skill the syllabus does not teach.

        One `youtube` search, cache-first and in the ledger like any other.
        Returns [{title, url, channel, length}].
        """
        dork = Dork(adapter_key="youtube", query=f"{skill} full course",
                    covers=(), engine="youtube")
        response = self.fetch(dork) or {}
        out: list[dict] = []
        for item in response.get("video_results") or []:
            link = item.get("link")
            title = item.get("title")
            if not link or not title:
                continue
            out.append({
                "title": title,
                "url": link,
                "channel": (item.get("channel") or {}).get("name") or "",
                "length": item.get("length") or "",
            })
            if len(out) >= limit:
                break
        return out


def event_link(item: dict) -> str | None:
    """The organiser's page for an event, not a Google search URL.

    `link` is usually the organiser's page. When it is a Google URL, the first
    ticket link that is not Google is used instead.
    """
    candidates = [item.get("link")]
    candidates += [t.get("link") for t in item.get("ticket_info") or []]
    for candidate in candidates:
        if candidate and "google." not in urlsplit(candidate).netloc:
            return _strip_tracking(candidate)
    return None


def account(api_key: str, timeout: float = 20.0) -> dict:
    """The key's plan and searches left. SerpApi does not bill this call."""
    import requests

    try:
        response = requests.get(
            "https://serpapi.com/account.json",
            params={"api_key": api_key},
            timeout=timeout,
        )
        return response.json()
    except Exception as exc:
        return {"error": str(exc)}


def canonical_url(adapter_key: str, url: str) -> str:
    """Map a listing's subpage onto its main page, per the adapter's rule."""
    adapter = adapter_registry.ADAPTERS.get(adapter_key)
    if adapter is None or adapter.canonical is None:
        return url
    pattern, replacement = adapter.canonical
    return re.sub(pattern, replacement, url, count=1, flags=re.IGNORECASE)


#: Re-posting aggregators. Their copy of a listing is a step removed from the
#: employer and goes stale first, so the original board is preferred.
JOB_AGGREGATORS = (
    "jobrapido.", "bebee.", "jooble.", "trabajo.", "kitjob.", "expertini.",
    "talentd.", "theelitejob.", "niyukjobs.", "simplyhired.", "getmereferred.",
)


def _strip_tracking(url: str) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query) if not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def job_link(item: dict) -> str | None:
    """The posting itself, not Google's share link.

    `share_link` is a google.com search URL: it cannot be probed, so every job
    card used to stay "unverified". Every recorded job carries `apply_options`
    pointing at the real board (Unstop, Internshala, LinkedIn, ...); the first
    one that is not a re-poster wins, then `source_link`, then any option.
    """
    options = [o.get("link") for o in item.get("apply_options") or [] if o.get("link")]
    direct = [u for u in options if not any(a in urlsplit(u).netloc for a in JOB_AGGREGATORS)]
    for candidate in (*direct, item.get("source_link"), *options, item.get("share_link")):
        if candidate:
            return _strip_tracking(candidate) if "google." not in urlsplit(candidate).netloc else candidate
    return None
