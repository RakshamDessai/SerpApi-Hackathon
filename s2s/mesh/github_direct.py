"""Open good-first-issues straight from GitHub's issue search API.

A `site:github.com` dork returns whatever the search engine indexed, open or
not, and every result then needs a rate-limited status call. GitHub's own
search answers the real question in one free request: `state:open` filters
on the issue's state NOW, so every result is open at fetch time.

Costs no SerpApi credit. Results carry provenance "platform-api" so the UI
never shows them as SerpApi output, and `verdict="live"` so the gate does not
spend a status call to learn what the search already said.

Unauthenticated limit: 10 searches a minute. `GITHUB_TOKEN` raises it to 30.
"""

from __future__ import annotations

import logging
from datetime import datetime

from s2s.config import USER_AGENT
from s2s.models import RawResult

log = logging.getLogger(__name__)

SEARCH_URL = "https://api.github.com/search/issues"

#: Labels projects use for starter issues. Inside one `label:` term, a comma
#: means OR.
STARTER_LABELS = '"good first issue","help wanted"'


def build_query(keyword: str) -> str:
    """The search string for one competency phrase."""
    # Quoted, so the words must appear together. Relevance is still loose
    # (2026-10-11: "SQL query" also returned a pagination task); stage 5
    # scores each result against the competencies, as for every source.
    return f'"{keyword}" label:{STARTER_LABELS} state:open is:issue no:assignee'


def parse(payload: dict) -> list[RawResult]:
    """Normalise a search response into `RawResult`s (pure, unit-tested)."""
    out: list[RawResult] = []
    for item in payload.get("items") or []:
        url = item.get("html_url") or ""
        title = item.get("title")
        if not title or "/issues/" not in url or item.get("state") != "open":
            continue
        repo = url.split("github.com/", 1)[-1].split("/issues/", 1)[0]
        created = item.get("created_at")
        try:
            posted = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(
                tzinfo=None) if created else None
        except ValueError:
            posted = None
        body = " ".join((item.get("body") or "").split())
        labels = ", ".join(l.get("name", "") for l in item.get("labels") or [])
        out.append(RawResult(
            title=title,
            url=url,
            snippet=f"{repo} · good first issue · {labels} · {body}"[:600],
            adapter_key="github",
            organization=repo,
            posted_at=posted,
            raw=item,
            provenance="platform-api",
            verdict="live",
        ))
    return out


def search(
    keywords: list[str],
    per_keyword: int = 5,
    token: str | None = None,
    timeout: float = 6.0,
) -> list[RawResult]:
    """One search per keyword. Fails soft: a network error returns []."""
    import requests

    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    out: list[RawResult] = []
    for keyword in keywords:
        try:
            response = requests.get(
                SEARCH_URL,
                params={"q": build_query(keyword), "sort": "created",
                        "order": "desc", "per_page": per_keyword},
                headers=headers,
                timeout=timeout,
            )
            if response.status_code != 200:
                log.info("github search %r: HTTP %s", keyword, response.status_code)
                continue
            out.extend(parse(response.json()))
        except Exception as exc:
            log.info("github search %r failed: %s", keyword, exc)
    return out
