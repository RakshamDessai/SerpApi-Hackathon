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
}

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

    # -- request building -------------------------------------------------

    def build_params(self, dork: Dork) -> dict:
        if dork.engine == "duckduckgo":
            # DuckDuckGo takes a combined region code and ignores hl/gl/num.
            params: dict = {"engine": dork.engine, "q": dork.query, "kl": "in-en"}
        else:
            params = {"engine": dork.engine, "q": dork.query, "hl": "en"}
        if dork.engine in ("google", "google_light"):
            params.update({"gl": "in", "num": self.results_per_search})
        params.update(dork.params or {})
        return params

    # -- execution --------------------------------------------------------

    def run(self, dork: Dork) -> list[RawResult]:
        params = self.build_params(dork)

        cached = self.cache.get(dork.engine, params)
        if cached is not None:
            self.ledger.record_cached(dork.adapter_key, dork.query)
            return self._parse(cached, dork)

        if self.demo_mode:
            self.ledger.record_skipped(
                dork.adapter_key, dork.query, "demo mode: no cached fixture"
            )
            return []

        if not self.api_key:
            self.ledger.record_skipped(dork.adapter_key, dork.query, "no SerpApi key")
            return []

        if not self.ledger.can_afford(dork.est_cost):
            self.ledger.record_skipped(
                dork.adapter_key, dork.query, "budget cap reached"
            )
            log.warning("budget cap reached, skipping %s", dork.adapter_key)
            return []

        try:
            response = _search({**params, "api_key": self.api_key})
        except Exception as exc:
            self.ledger.record_skipped(dork.adapter_key, dork.query, f"error: {exc}")
            log.warning("SerpApi call failed for %s: %s", dork.adapter_key, exc)
            return []

        if "error" in response and EMPTY_RESULT_MARKER in str(response["error"]):
            # A legitimate "nothing matched" answer. SerpApi bills it (observed
            # 2026-10-10), so count the credit - and cache it, or every re-run
            # pays again for the same empty query.
            self.ledger.record_live(dork.adapter_key, dork.query, dork.est_cost)
            self.cache.put(dork.engine, params, response)
            return []

        if "error" in response:
            self.ledger.record_skipped(
                dork.adapter_key, dork.query, f"serpapi: {response['error']}"
            )
            log.warning("SerpApi error for %s: %s", dork.adapter_key, response["error"])
            return []

        self.ledger.record_live(dork.adapter_key, dork.query, dork.est_cost)
        self.cache.put(dork.engine, params, response)
        return self._parse(response, dork)

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

        url = item.get("share_link")
        if not url:
            options = item.get("apply_options") or item.get("related_links") or []
            if options:
                url = options[0].get("link")
        if not url:
            return None

        detected = item.get("detected_extensions") or {}
        return RawResult(
            title=title,
            url=url,
            snippet=(item.get("description") or "")[:600],
            adapter_key=dork.adapter_key,
            organization=item.get("company_name"),
            posted_at=parse_posted_at(detected.get("posted_at")),
            raw=item,
        )
