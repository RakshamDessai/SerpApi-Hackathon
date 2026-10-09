"""URL canonicalisation and near-duplicate merging.

OR-packing means the same listing can come back from several dorks, and boards
hand out the same page under tracking-parameter variants. Without this the
student sees the same brief three times and the ranking looks broken.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from s2s.models import RawResult

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref_", "_hs")
TRACKING_EXACT = {"ref", "source", "src", "campaign", "fromSearch", "position"}

#: Near-duplicate threshold on the Jaccard similarity of title token sets.
TITLE_SIMILARITY = 0.9


def canonical_url(url: str) -> str:
    """Strip tracking noise so the same page hashes identically."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if key not in TRACKING_EXACT
        and not any(key.lower().startswith(p) for p in TRACKING_PREFIXES)
    ]

    path = parts.path.rstrip("/") or "/"
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower().removeprefix("www."),
        path,
        urlencode(sorted(query)),
        "",                              # fragments never identify a listing
    ))


def _tokens(title: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", title.lower()) if len(t) > 2}


def _similar(a: str, b: str) -> bool:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    overlap = len(ta & tb) / len(ta | tb)
    return overlap >= TITLE_SIMILARITY


def dedupe(results: list[RawResult]) -> list[RawResult]:
    """Collapse exact-URL and near-identical-title duplicates, keeping the first.

    Merging keeps the longest snippet seen and the earliest known posting date,
    so deduplication never loses signal the scorer would have used.
    """
    kept: list[RawResult] = []
    by_url: dict[str, RawResult] = {}

    for result in results:
        key = canonical_url(result.url)

        existing = by_url.get(key)
        if existing is None:
            for candidate in kept:
                if candidate.adapter_key == result.adapter_key and _similar(
                    candidate.title, result.title
                ):
                    existing = candidate
                    break

        if existing is not None:
            if len(result.snippet) > len(existing.snippet):
                existing.snippet = result.snippet
            if existing.posted_at is None and result.posted_at is not None:
                existing.posted_at = result.posted_at
            if not existing.organization and result.organization:
                existing.organization = result.organization
            continue

        result.url = key
        by_url[key] = result
        kept.append(result)

    return kept
