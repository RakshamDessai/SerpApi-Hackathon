"""Stage 5: the composite match score.

The vision doc states the formula but implements none of its terms. Each is
concrete here, and `ScoreBreakdown.explain()` renders the arithmetic in the UI -
a transparent score beats an opaque "AI match: 87%", and it costs nothing.

Pure functions, no I/O. This module is the unit-tested core.
"""

from __future__ import annotations

import math
from datetime import datetime

from s2s.mesh import adapters as adapter_registry
from s2s.models import (
    BAND_ORDER,
    Competency,
    Opportunity,
    RawResult,
    ScoreBreakdown,
    Verdict,
)
from s2s.score import signals

WEIGHTS: dict[str, float] = {
    "semantic": 0.45,
    "level": 0.25,
    "freshness": 0.15,
    "actionability": 0.15,
}

#: Hits needed before semantic alignment saturates at 1.0.
SEMANTIC_TARGET = 2.5

#: Most `site:` dork results carry no parseable date. Scoring them 0 would sink
#: every NGO brief below every hackathon; scoring them 1.0 would be dishonest.
UNKNOWN_DATE_PENALTY = 0.35
FRESHNESS_TAU_DAYS = 21.0

TRUST_SCORE = {"A": 1.0, "B": 0.7, "C": 0.4}
VERDICT_SCORE = {"live": 1.0, "unverified": 0.5, "archived": 0.0}


# ------------------------------------------------------------- the terms ----

def semantic(competency: Competency, result: RawResult) -> float:
    """Lexical overlap between the competency's market phrases and the brief.

    Deliberately no mandatory embedding call: a second external API is a second
    demo failure mode. An embedding blend can be layered on later, but this path
    alone must produce a working demo.
    """
    title = result.title.lower()
    body = result.snippet.lower()
    body_tokens = set(body.split())
    total = 0.0

    for phrase in competency.search_phrases:
        needle = phrase.lower()
        if needle in title:
            total += 1.0                     # a title match is the strongest signal
        elif needle in body:
            total += 0.5
        else:
            tokens = set(needle.split())
            if tokens and len(tokens & body_tokens) / len(tokens) >= 0.6:
                total += 0.25                # partial credit for token overlap

    for tool in competency.tools:
        if tool.lower() in body or tool.lower() in title:
            total += 0.3

    return min(1.0, total / SEMANTIC_TARGET)


def level(competency: Competency, result: RawResult) -> float:
    """How well the listing's difficulty matches where the student actually is."""
    task_band = signals.infer_band(result)
    distance = abs(BAND_ORDER[competency.band] - BAND_ORDER[task_band])
    return 1.0 - distance / 2.0


def freshness(result: RawResult, now: datetime | None = None) -> float:
    """Exponential decay on the posting date, with an explicit unknown penalty."""
    if result.posted_at is None:
        return UNKNOWN_DATE_PENALTY
    now = now or datetime.now()
    age_days = max(0.0, (now - result.posted_at).total_seconds() / 86400)
    return math.exp(-age_days / FRESHNESS_TAU_DAYS)


def actionability(result: RawResult, verdict: Verdict) -> float:
    """Can the student actually act on this today?

    This is where the Grounding Gate feeds back into ranking: an archived card
    scores zero on half the term and sinks on its own.
    """
    adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
    trust = TRUST_SCORE.get(adapter.trust, 0.4) if adapter else 0.4
    clarity = 1.0 if signals.has_deliverable(result) else 0.4
    return 0.5 * VERDICT_SCORE[verdict] + 0.3 * trust + 0.2 * clarity


# ------------------------------------------------------------- composite ----

def score_one(
    competency: Competency,
    result: RawResult,
    verdict: Verdict,
    now: datetime | None = None,
) -> ScoreBreakdown:
    return ScoreBreakdown(
        semantic=semantic(competency, result),
        level=level(competency, result),
        freshness=freshness(result, now=now),
        actionability=actionability(result, verdict),
        weights=WEIGHTS,
    )


def build_opportunities(
    graded: list[tuple[RawResult, Verdict, datetime | None]],
    competencies: list[Competency],
    now: datetime | None = None,
    drop_scams: bool = True,
) -> list[Opportunity]:
    """Match every result against every competency, keeping each result's best.

    This is what makes OR-packing free: one search can carry several
    competencies because relevance is resolved here, per result, afterwards.
    """
    opportunities: list[Opportunity] = []

    for result, verdict, verified_at in graded:
        scammy = signals.is_scammy(result)
        if scammy and drop_scams:
            continue

        best: tuple[ScoreBreakdown, Competency] | None = None
        for competency in competencies:
            breakdown = score_one(competency, result, verdict, now=now)
            if best is None or breakdown.total > best[0].total:
                best = (breakdown, competency)

        if best is None:
            continue
        breakdown, competency = best

        opportunities.append(
            Opportunity(
                title=result.title,
                url=result.url,
                snippet=result.snippet,
                adapter_key=result.adapter_key,
                matched_competency=competency,
                score=breakdown,
                verdict=verdict,
                organization=result.organization,
                posted_at=result.posted_at,
                verified_at=verified_at,
                band=signals.infer_band(result),
                est_hours=signals.estimate_hours(result),
                scam_flag=scammy,
            )
        )

    # Live before unverified before archived, then by score.
    order = {"live": 0, "unverified": 1, "archived": 2}
    opportunities.sort(key=lambda o: (order[o.verdict], -o.score.total))
    return opportunities
