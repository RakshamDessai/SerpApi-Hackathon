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


#: Engines whose `location` parameter places the search. SerpApi resolves a
#: free-text location against its Locations API.
LOCATED_ENGINES = ("google_jobs", "google_events")


def choose_platforms(
    competencies: list[Competency],
    max_platforms: int,
    include_tier_c: bool = False,
    extra: set[str] | None = None,
) -> list[tuple[PlatformAdapter, float]]:
    """Rank eligible platforms by how much of this syllabus they serve.

    Opt-in adapters named in `extra` are added after the affinity choice and
    do not take a slot from it. The student switched them on, so they always
    run - and the five chosen platforms stay the same as without them.
    """
    profile = affinity.discipline_profile(competencies)

    scored: list[tuple[PlatformAdapter, float]] = []
    for adapter in adapter_registry.active(include_tier_c=include_tier_c):
        value = affinity.score(adapter.key, profile)
        if value >= affinity.AFFINITY_FLOOR:
            scored.append((adapter, value))

    scored.sort(key=lambda pair: (-pair[1], pair[0].trust, pair[0].key))
    chosen = scored[:max_platforms]

    taken = {adapter.key for adapter, _ in chosen}
    for key in sorted(extra or ()):
        adapter = adapter_registry.ADAPTERS.get(key)
        if adapter is not None and key not in taken:
            chosen.append((adapter, affinity.score(key, profile)))
    return chosen


def params_for(adapter: PlatformAdapter, city: str | None = None) -> dict:
    """The adapter's fixed parameters, with the student's city when given."""
    params = dict(adapter.extra_params)
    if city and adapter.engine in LOCATED_ENGINES:
        params["location"] = f"{city.strip()}, India"
    return params


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


def keyword_for(group: list[Competency], used: set[str] | None = None) -> str | None:
    """The single phrase a `keywords`-style dork searches for.

    A keyword dork cannot OR-pack, so it packs the other way: it picks the
    phrase shared by the most competencies in the group ("financial model"
    rather than "cost of equity"), so one search still serves several units.
    Ties go to the strongest phrase in `phrases_for` order. Phrases in `used`
    are skipped: two groups sharing "financial model" would otherwise issue the
    identical query twice and lose the second group's coverage.
    """
    used = used or set()
    ordered = [p for p in phrases_for(group) if p.lower() not in used]
    if not ordered:
        return None
    rank = {p.lower(): i for i, p in enumerate(ordered)}
    counts: dict[str, int] = {}
    for competency in group:
        for phrase in {p.lower() for p in competency.search_phrases}:
            counts[phrase] = counts.get(phrase, 0) + 1
    return max(ordered, key=lambda p: (counts.get(p.lower(), 0), -rank[p.lower()]))


def plan(
    competencies: list[Competency],
    credit_cap: int,
    max_platforms: int = 5,
    terms_per_dork: int = 3,
    include_tier_c: bool = False,
    extra: set[str] | None = None,
    year: int | None = None,
    city: str | None = None,
) -> list[Dork]:
    """Build the run's search plan, never exceeding `credit_cap`.

    `year` goes into the dorks of dated-edition platforms (see
    `adapters.render_query`). `city` places Google Jobs and Google Events.
    """
    if not competencies:
        return []

    platforms = choose_platforms(competencies, max_platforms, include_tier_c, extra)
    groups = pack(competencies, terms_per_dork)

    dorks: list[Dork] = []
    budget = credit_cap
    used_keywords: set[str] = set()

    # Breadth before depth: one group across all platforms, then the next.
    # If the cap bites, the student still gets every ecosystem represented.
    for group in groups:
        phrases = phrases_for(group)
        if not phrases:
            continue
        keyword = keyword_for(group, used_keywords) or phrases[0]
        used_keywords.add(keyword.lower())
        keyword_phrases = [keyword] + [p for p in phrases if p != keyword]
        for adapter, _ in platforms:
            if budget <= 0:
                return dorks
            terms = keyword_phrases if adapter.query_style == "keywords" else phrases
            dorks.append(
                Dork(
                    adapter_key=adapter.key,
                    query=adapter_registry.render_query(adapter, terms, year=year),
                    covers=tuple(group),
                    engine=adapter.engine,
                    params=params_for(adapter, city),
                    est_cost=1,
                )
            )
            budget -= 1
    return dorks


#: A platform earns its page 2 when at least this share of its page-1
#: listings verified live, and at least `FOLLOW_UP_MIN_LIVE` of them did.
FOLLOW_UP_MIN_SHARE = 0.5
FOLLOW_UP_MIN_LIVE = 2


def follow_ups(
    dorks: list[Dork],
    verdicts: dict[str, list[str]],
    next_params: dict[tuple[str, str], dict],
    budget: int,
) -> list[Dork]:
    """Page-2 searches for the platforms that are paying off, within `budget`.

    Credits left under the cap are best spent where page 1 was mostly live:
    a platform whose index is full of finished events will not improve on
    page 2. `verdicts` maps adapter key to its page-1 verdicts. `next_params`
    maps (adapter key, query) to the pagination parameters SerpApi itself
    returned (`serpapi_pagination.next`), so no offset is guessed here.
    """
    def strength(key: str) -> tuple[float, int]:
        found = verdicts.get(key, [])
        live = sum(1 for v in found if v == "live")
        return (live / len(found) if found else 0.0), live

    candidates = []
    for dork in dorks:
        share, live = strength(dork.adapter_key)
        nxt = next_params.get((dork.adapter_key, dork.query))
        if nxt and share >= FOLLOW_UP_MIN_SHARE and live >= FOLLOW_UP_MIN_LIVE:
            candidates.append((share, live, dork, nxt))

    candidates.sort(key=lambda c: (-c[0], -c[1], c[2].adapter_key))
    out: list[Dork] = []
    for _, _, dork, nxt in candidates[:max(0, budget)]:
        out.append(Dork(
            adapter_key=dork.adapter_key,
            query=dork.query,
            covers=dork.covers,
            engine=dork.engine,
            params={**dork.params, **nxt},
            est_cost=1,
        ))
    return out


def naive_cost(competencies: list[Competency], include_tier_c: bool = False) -> int:
    """What an unplanned run would have cost, for the efficiency panel."""
    platforms = len(adapter_registry.active(include_tier_c=include_tier_c))
    return max(1, len(competencies) * platforms)
