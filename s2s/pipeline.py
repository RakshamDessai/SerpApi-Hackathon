"""The S2S pipeline: syllabus in, ranked opportunities out.

Stages 0-5 (stage 6, the bridge and blueprint, is generated lazily per card in
Phase 3). This is the only module that crosses stage boundaries; stages never
import each other.

Nothing here imports Streamlit - the UI consumes `PipelineResult`, so the same
pipeline can later be driven from a CLI or an API with no changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Callable

from s2s.analyze import gaps as gaps_module
from s2s.config import Settings
from s2s.extract import extract_competencies
from s2s.ground import dedupe, gate
from s2s.ingest import structure
from s2s.ingest.loader import RawSyllabus
from s2s.mesh import cache as cache_module
from s2s.mesh import github_direct
from s2s.mesh import planner
from s2s.mesh.ledger import BudgetLedger
from s2s.mesh.serpapi_client import SerpApiClient
from s2s.models import Competency, Discipline, Dork, Opportunity, RawResult
from s2s.score import scorer

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, float], None]


#: Most competencies one multi-subject run keeps, whatever the subject count.
MAX_MULTI_SUBJECT_COMPETENCIES = 10

#: Free GitHub issue searches per run (10 a minute without a token).
GITHUB_KEYWORDS = 3


def _balance_subjects(competencies: list[Competency], limit: int) -> list[Competency]:
    """Round-robin across subjects, so one strong subject cannot fill the run.

    The extractor ranks by Bloom level; with five subjects, the most practical
    one would otherwise take every slot.
    """
    by_course: dict[str, list[Competency]] = {}
    for competency in competencies:
        by_course.setdefault(competency.source_course, []).append(competency)
    queues = list(by_course.values())
    out: list[Competency] = []
    while len(out) < limit and any(queues):
        for queue in queues:
            if queue and len(out) < limit:
                out.append(queue.pop(0))
    return out


def _with_primary_discipline(competency: Competency, stream: Discipline) -> Competency:
    """Move `stream` to the front of a competency's disciplines."""
    others = [d for d in competency.disciplines if d != stream]
    return replace(competency, disciplines=[stream, *others][:2])


@dataclass
class PipelineResult:
    syllabus: RawSyllabus
    tree: object
    competencies: list[Competency]
    extraction_mode: str
    extraction_note: str | None
    dorks: list[Dork]
    opportunities: list[Opportunity]
    ledger: BudgetLedger
    naive_cost: int
    raw_count: int = 0
    tier0_dropped: int = 0
    warnings: list[str] = field(default_factory=list)
    gap_report: "gaps_module.GapReport | None" = None

    @property
    def provenances(self) -> set[str]:
        """Distinct data sources behind this run's results."""
        return {o.provenance for o in self.opportunities}

    @property
    def has_harvested(self) -> bool:
        """True if any result came from a direct harvest rather than SerpApi."""
        return "public-api-harvest" in self.provenances

    @property
    def searched(self) -> bool:
        """Did any search actually execute? Gap findings are meaningless if not."""
        return (self.ledger.live_calls + self.ledger.cache_hits) > 0

    # -- convenience splits for the UI ------------------------------------

    @property
    def live(self) -> list[Opportunity]:
        return [o for o in self.opportunities if o.verdict == "live"]

    @property
    def unverified(self) -> list[Opportunity]:
        return [o for o in self.opportunities if o.verdict == "unverified"]

    @property
    def archived(self) -> list[Opportunity]:
        return [o for o in self.opportunities if o.verdict == "archived"]

    @property
    def actionable(self) -> list[Opportunity]:
        """What the student is actually shown first."""
        return self.live + self.unverified

    @property
    def savings(self) -> tuple[int, int, float]:
        """(naive searches, planned searches, fraction saved).

        Measured against the plan, not against calls that happened to execute -
        otherwise a run with no key reports a fake 99% saving.
        """
        planned = max(1, len(self.dorks))
        naive = max(planned, self.naive_cost)
        return naive, planned, 1.0 - planned / naive


def plan_searches(competencies: list[Competency], settings: Settings) -> list[Dork]:
    """Stage 2 with this run's settings.

    Shared with scripts/record_fixtures.py: a fixture is only a cache hit if
    it was recorded from exactly the plan the app will make.
    """
    return planner.plan(
        competencies,
        credit_cap=settings.credit_cap,
        max_platforms=settings.max_platforms,
        terms_per_dork=settings.terms_per_dork,
        include_tier_c=settings.include_tier_c,
        extra={"gevents"} if settings.events else set(),
        year=datetime.now().year if settings.fresh_queries else None,
        city=settings.city,
    )


def run(
    syllabus: RawSyllabus,
    settings: Settings,
    semester: int | None = None,
    progress: ProgressFn | None = None,
    stream: "Discipline | None" = None,
) -> PipelineResult:
    """Execute stages 0-5.

    `stream`, when the student picks one, is promoted to each competency's
    primary discipline. Keyword detection is good but not perfect, and the
    student knows their own course better than the taxonomy does.
    """

    def step(message: str, fraction: float) -> None:
        log.info("[%3.0f%%] %s", fraction * 100, message)
        if progress is not None:
            progress(message, fraction)

    warnings: list[str] = []

    # -- stage 0: structure ------------------------------------------------
    step("Parsing syllabus structure...", 0.05)
    tree = structure.parse(syllabus.text)

    # -- stage 1: extract --------------------------------------------------
    step("Extracting market competencies...", 0.15)
    subjects = structure.subject_count(tree)
    limit = settings.max_competencies
    if subjects > 1:
        limit = min(MAX_MULTI_SUBJECT_COMPETENCIES, max(limit, 2 * subjects))
    extraction = extract_competencies(
        syllabus,
        tree,
        api_key=settings.anthropic_key,
        semester=semester,
        # Over-extract for several subjects, then balance below.
        limit=limit * 3 if subjects > 1 else limit,
    )
    competencies = extraction.competencies
    if extraction.note:
        warnings.append(extraction.note)

    if subjects > 1:
        competencies = [
            replace(c, source_course=structure.course_of(tree, c.span_offset))
            for c in competencies
        ]
        competencies = _balance_subjects(competencies, limit)

    if stream is not None:
        competencies = [_with_primary_discipline(c, stream) for c in competencies]

    if not competencies:
        warnings.append(
            "No unit in this syllabus mapped to a known market competency. "
            "Try a syllabus with more practical units, or paste a unit listing."
        )
        return PipelineResult(
            syllabus=syllabus, tree=tree, competencies=[],
            extraction_mode=extraction.mode, extraction_note=extraction.note,
            dorks=[], opportunities=[],
            ledger=BudgetLedger(cap=settings.credit_cap),
            naive_cost=0, warnings=warnings,
            gap_report=gaps_module.build(tree, [], [], searched=False),
        )

    # -- stage 2: plan -----------------------------------------------------
    step(f"Planning searches for {len(competencies)} competencies...", 0.25)
    dorks = plan_searches(competencies, settings)
    naive = planner.naive_cost(competencies, include_tier_c=settings.include_tier_c)

    platform_count = len({d.adapter_key for d in dorks})

    # -- stage 3: execute --------------------------------------------------
    ledger = BudgetLedger(cap=settings.credit_cap)
    client = SerpApiClient(
        api_key=settings.serpapi_key,
        cache=cache_module.build(settings),
        ledger=ledger,
        demo_mode=settings.demo_mode,
        results_per_search=settings.results_per_search,
    )

    raw: list[RawResult] = []
    for index, dork in enumerate(dorks):
        step(
            f"Searching {dork.adapter_key} ({index + 1}/{len(dorks)})...",
            0.25 + 0.40 * (index + 1) / max(1, len(dorks)),
        )
        raw.extend(client.run(dork))

    # Free: GitHub's own search returns only issues that are open now. Run
    # only when the plan chose GitHub, so a Design student never sees it.
    github_dorks = [d for d in dorks if d.adapter_key == "github"]
    if settings.direct_github and github_dorks:
        step("Asking GitHub for open good-first-issues...", 0.66)
        keywords: list[str] = []
        for dork in github_dorks:
            keyword = planner.keyword_for(list(dork.covers))
            if keyword and keyword not in keywords:
                keywords.append(keyword)
        raw.extend(github_direct.search(keywords[:GITHUB_KEYWORDS],
                                        token=settings.github_token))

    raw_count = len(raw)
    if raw_count == 0 and ledger.skipped:
        reasons = {e.note for e in ledger.entries if e.skipped}
        warnings.append("No results returned. " + "; ".join(sorted(reasons)))

    # -- stage 4: ground ---------------------------------------------------
    step("Removing duplicates...", 0.70)
    deduped = dedupe.dedupe(raw)

    step("Verifying links are live...", 0.78)
    credentials: dict[str, tuple[str, ...]] = {}
    if settings.has_kaggle:
        credentials["kaggle"] = (settings.kaggle_username, settings.kaggle_key)
    if settings.github_token:
        credentials["github"] = (settings.github_token,)

    def grade(results: list[RawResult]):
        return gate.verify(
            results,
            probe_top_n=settings.probe_top_n,
            timeout=settings.probe_timeout_s,
            # Not tied to demo mode: in demo mode 58 of 67 recorded Unstop
            # events had already finished, and without a probe they rank as
            # if open.
            enable_probe=settings.probe_top_n > 0,
            credentials=credentials,
        )

    graded = grade(deduped)
    tier0_dropped = len(deduped) - len(graded)

    # -- stage 3b: page 2 where page 1 paid off ----------------------------
    if settings.follow_up_pages and ledger.remaining > 0:
        verdicts: dict[str, list[str]] = {}
        for result, verdict, _ in graded:
            if result.provenance == "serpapi":
                verdicts.setdefault(result.adapter_key, []).append(verdict)
        extra_dorks = planner.follow_ups(
            dorks, verdicts, client.next_params, budget=ledger.remaining
        )
        if extra_dorks:
            step(f"Fetching page 2 of {len(extra_dorks)} strong platforms...", 0.84)
            seen = {dedupe.canonical_url(r.url) for r in deduped}
            more: list[RawResult] = []
            for dork in extra_dorks:
                more.extend(client.run(dork))
            raw_count += len(more)
            fresh = [r for r in dedupe.dedupe(more) if dedupe.canonical_url(r.url) not in seen]
            more_graded = grade(fresh)
            tier0_dropped += len(fresh) - len(more_graded)
            graded += more_graded
            dorks = dorks + extra_dorks

    # -- stage 5: score ----------------------------------------------------
    step("Scoring and ranking...", 0.92)
    opportunities = scorer.build_opportunities(graded, competencies, now=datetime.now())

    step("Done.", 1.0)
    log.info(
        "pipeline: %d raw -> %d deduped -> %d gated -> %d scored (%s)",
        raw_count, len(deduped), len(graded), len(opportunities), ledger.summary(),
    )

    ledger_searched = (ledger.live_calls + ledger.cache_hits) > 0
    gap_report = gaps_module.build(
        tree, competencies, opportunities, searched=ledger_searched
    )

    # One YouTube search per gap, for the first N gaps only. Each costs a
    # credit and runs through the same cap and ledger as every other search.
    if settings.gap_courses > 0 and ledger_searched:
        for gap in [g for g in gap_report.gaps if g.suggestions][:settings.gap_courses]:
            gap.courses = client.courses(gap.suggestions[0])

    return PipelineResult(
        syllabus=syllabus,
        tree=tree,
        competencies=competencies,
        extraction_mode=extraction.mode,
        extraction_note=extraction.note,
        dorks=dorks,
        opportunities=opportunities,
        ledger=ledger,
        naive_cost=naive or max(1, len(competencies) * max(1, platform_count)),
        raw_count=raw_count,
        tier0_dropped=tier0_dropped,
        warnings=warnings,
        gap_report=gap_report,
    )
