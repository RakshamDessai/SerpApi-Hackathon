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
from s2s.mesh import planner
from s2s.mesh.ledger import BudgetLedger
from s2s.mesh.serpapi_client import SerpApiClient
from s2s.models import Competency, Discipline, Dork, Opportunity, RawResult
from s2s.score import scorer

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, float], None]


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
    extraction = extract_competencies(
        syllabus,
        tree,
        api_key=settings.anthropic_key,
        semester=semester,
        limit=settings.max_competencies,
    )
    competencies = extraction.competencies
    if extraction.note:
        warnings.append(extraction.note)

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
    dorks = planner.plan(
        competencies,
        credit_cap=settings.credit_cap,
        max_platforms=settings.max_platforms,
        terms_per_dork=settings.terms_per_dork,
        include_tier_c=settings.include_tier_c,
    )
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

    raw_count = len(raw)
    if raw_count == 0 and ledger.skipped:
        reasons = {e.note for e in ledger.entries if e.skipped}
        warnings.append("No results returned. " + "; ".join(sorted(reasons)))

    # -- stage 4: ground ---------------------------------------------------
    step("Removing duplicates...", 0.70)
    deduped = dedupe.dedupe(raw)

    step("Verifying links are live...", 0.78)
    graded = gate.verify(
        deduped,
        probe_top_n=settings.probe_top_n,
        timeout=settings.probe_timeout_s,
        enable_probe=not settings.demo_mode,
    )
    tier0_dropped = len(deduped) - len(graded)

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
