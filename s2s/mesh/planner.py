"""Stage 2: turn Competency[] into a small, high-yield set of SerpApi calls.

Pure function, no I/O, fully unit-testable. This is where the credit economy
lives (BUILD_PLAN.md section 7).

The arithmetic that motivates it:

    naive                6 competencies x 17 platforms = 102 searches per click
    affinity selection   6 x 5                         = 30
    + OR-packing         2 x 5                         = 10

On a 100-search monthly quota the naive plan allows one run per month.

OR-packing works because relevance is recovered downstream: stage 5 scores every
result against every competency individually, so packing costs nothing in match
precision. It only trades per-result recall depth, which `num=10` offsets.
"""

from __future__ import annotations

from s2s.mesh import adapters as adapter_registry
from s2s.mesh import affinity
from s2s.models import Competency, Dork, PlatformAdapter

#: Google's relevance degrades past roughly this many quoted alternatives
#: inside a site: scope - results start drifting off-topic.
MAX_PHRASES_PER_DORK = 6

#: Phrases contributed by each competency in a group.
PHRASES_PER_COMPETENCY = 2


def choose_platforms(
    competencies: list[Competency],
    max_platforms: int,
    include_tier_c: bool = False,
) -> list[tuple[PlatformAdapter, float]]:
    """Rank eligible platforms by how much of this syllabus they serve."""
    profile = affinity.discipline_profile(competencies)

    scored: list[tuple[PlatformAdapter, float]] = []
    for adapter in adapter_registry.active(include_tier_c=include_tier_c):
        value = affinity.score(adapter.key, profile)
        if value >= affinity.AFFINITY_FLOOR:
            scored.append((adapter, value))

    scored.sort(key=lambda pair: (-pair[1], pair[0].trust, pair[0].key))
    return scored[:max_platforms]


def pack(competencies: list[Competency], per_group: int) -> list[list[Competency]]:
    """Group competencies so one search answers several at once.

    Highest-Bloom competencies are distributed across groups rather than
    clustered, so every search carries at least one strong practical term.
    """
    if per_group < 1:
        per_group = 1
    ordered = sorted(competencies, key=lambda c: -c.bloom)
    group_count = max(1, (len(ordered) + per_group - 1) // per_group)

    groups: list[list[Competency]] = [[] for _ in range(group_count)]
    for index, competency in enumerate(ordered):
        groups[index % group_count].append(competency)
    return [g for g in groups if g]


def phrases_for(group: list[Competency]) -> list[str]:
    """The OR-group's quoted phrases, strongest first, length-capped."""
    phrases: list[str] = []
    seen: set[str] = set()

    for competency in group:
        taken = 0
        for phrase in competency.search_phrases:
            key = phrase.lower()
            if key in seen or len(phrase) < 3:
                continue
            seen.add(key)
            phrases.append(phrase)
            taken += 1
            if taken >= PHRASES_PER_COMPETENCY:
                break

    return phrases[:MAX_PHRASES_PER_DORK]


def plan(
    competencies: list[Competency],
    credit_cap: int,
    max_platforms: int = 5,
    terms_per_dork: int = 3,
    include_tier_c: bool = False,
) -> list[Dork]:
    """Build the run's search plan, never exceeding `credit_cap`."""
    if not competencies:
        return []

    platforms = choose_platforms(competencies, max_platforms, include_tier_c)
    groups = pack(competencies, terms_per_dork)

    dorks: list[Dork] = []
    budget = credit_cap

    # Breadth before depth: one group across all platforms, then the next.
    # If the cap bites, the student still gets every ecosystem represented.
    for group in groups:
        phrases = phrases_for(group)
        if not phrases:
            continue
        for adapter, _ in platforms:
            if budget <= 0:
                return dorks
            dorks.append(
                Dork(
                    adapter_key=adapter.key,
                    query=adapter_registry.render_query(adapter, phrases),
                    covers=tuple(group),
                    engine=adapter.engine,
                    params=dict(adapter.extra_params),
                    est_cost=1,
                )
            )
            budget -= 1
    return dorks


def naive_cost(competencies: list[Competency], include_tier_c: bool = False) -> int:
    """What an unplanned run would have cost, for the efficiency panel."""
    platforms = len(adapter_registry.active(include_tier_c=include_tier_c))
    return max(1, len(competencies) * platforms)
