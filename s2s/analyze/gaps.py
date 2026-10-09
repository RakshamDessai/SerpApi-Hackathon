"""The Syllabus Gap Report.

Inverts the product's question. Instead of "what live work matches my syllabus",
it asks **"which parts of my syllabus matched nothing at all?"**

That turns S2S from a matcher into evidence that a curriculum has drifted from
the market - a sharper, more shareable claim, and one computed almost entirely
from data the pipeline already produced.

Three gap kinds, in descending severity:

    no_market_signal  the unit produced no market alias at all - nothing in the
                      taxonomy recognised it as something anyone pays for
    no_live_work      a competency was extracted, but no search result matched it
    weak_demand       matches exist, but all of them scored below the floor

Honesty rule: a gap is only meaningful if the platforms were actually searched.
When a run spent no credits (no key, or demo mode with no fixture), every unit
would look dead, so `build` reports `searched=False` and the UI must say so
rather than implying the curriculum is outdated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from s2s.extract import taxonomy
from s2s.ingest.structure import CurriculumNode
from s2s.models import Competency, Discipline, Opportunity

#: A match below this score is not real demand.
WEAK_SCORE_FLOOR = 45

GAP_LABEL = {
    "no_market_signal": "No market signal",
    "no_live_work": "No live work found",
    "weak_demand": "Weak demand",
}

GAP_EXPLANATION = {
    "no_market_signal": (
        "Nothing in this unit mapped to a skill that organisations currently "
        "advertise for. It may be foundational theory, or it may be outdated."
    ),
    "no_live_work": (
        "This unit does map to a real market skill, but none of the platforms "
        "searched had open work for it right now."
    ),
    "weak_demand": (
        "Some work matched, but weakly. The overlap with what employers are "
        "asking for is thin."
    ),
}


@dataclass
class Gap:
    unit_label: str
    kind: str                       # no_market_signal | no_live_work | weak_demand
    detail: str
    best_score: int | None = None
    suggestions: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return GAP_LABEL[self.kind]

    @property
    def explanation(self) -> str:
        return GAP_EXPLANATION[self.kind]


@dataclass
class GapReport:
    gaps: list[Gap]
    units_total: int
    units_matched: int
    searched: bool
    note: str | None = None

    @property
    def coverage(self) -> float:
        if self.units_total == 0:
            return 0.0
        return self.units_matched / self.units_total

    @property
    def headline(self) -> str:
        if not self.searched:
            return "Not enough data to judge coverage - no searches ran."
        dead = sum(1 for g in self.gaps if g.kind == "no_market_signal")
        if dead:
            return (
                f"{dead} of {self.units_total} units matched no live market "
                f"demand at all."
            )
        if self.gaps:
            return (
                f"{self.units_matched} of {self.units_total} units led to live "
                f"work; {len(self.gaps)} did not."
            )
        return f"All {self.units_total} units led to live work."


def _discipline_suggestions(
    disciplines: list[Discipline],
    exclude: list[str] | None = None,
    limit: int = 3,
) -> list[str]:
    """Market skills from the same discipline that *do* have demand.

    Drawn from the taxonomy rather than invented, so a suggestion is always
    something the rest of the system can actually search for. `exclude` drops
    phrases this unit already searched - telling a student "try the exact terms
    that just returned nothing" is noise, not insight.
    """
    wanted: set[str] = set()
    for discipline in disciplines:
        wanted |= taxonomy.DISCIPLINE_KEYWORDS.get(discipline, set())

    skip = {phrase.lower() for phrase in (exclude or [])}

    suggestions: list[str] = []
    for academic, market in taxonomy.MARKET_ALIASES.items():
        if not any(keyword in academic for keyword in wanted):
            continue
        for phrase in market:
            if phrase.lower() in skip or phrase in suggestions:
                continue
            suggestions.append(phrase)
            if len(suggestions) >= limit:
                return suggestions
    return suggestions[:limit]


def build(
    tree: CurriculumNode,
    competencies: list[Competency],
    opportunities: list[Opportunity],
    searched: bool,
) -> GapReport:
    """Compare every parsed unit against what the run actually found."""
    unit_labels = [unit.label for unit in tree.iter_units()]
    by_unit: dict[str, Competency] = {c.source_unit: c for c in competencies}

    best_by_unit: dict[str, int] = {}
    for opportunity in opportunities:
        unit = opportunity.matched_competency.source_unit
        score = opportunity.score.total
        if score > best_by_unit.get(unit, -1):
            best_by_unit[unit] = score

    gaps: list[Gap] = []
    matched = 0

    for label in unit_labels:
        competency = by_unit.get(label)

        if competency is None:
            # The unit never became a competency: no market alias matched.
            # Infer a discipline from the label alone for the suggestion.
            disciplines = taxonomy.detect_disciplines(label)
            gaps.append(
                Gap(
                    unit_label=label,
                    kind="no_market_signal",
                    detail="No market-facing skill was extracted from this unit.",
                    suggestions=_discipline_suggestions(disciplines),
                )
            )
            continue

        best = best_by_unit.get(label)

        if best is None:
            gaps.append(
                Gap(
                    unit_label=label,
                    kind="no_live_work",
                    detail=(
                        f"Searched for {', '.join(competency.aliases[:3])} - "
                        f"nothing open right now."
                    ),
                    suggestions=_discipline_suggestions(
                        competency.disciplines, exclude=competency.aliases
                    ),
                )
            )
        elif best < WEAK_SCORE_FLOOR:
            gaps.append(
                Gap(
                    unit_label=label,
                    kind="weak_demand",
                    detail=f"Best match scored only {best}%.",
                    best_score=best,
                    suggestions=_discipline_suggestions(
                        competency.disciplines, exclude=competency.aliases
                    ),
                )
            )
        else:
            matched += 1

    note = None
    if not searched:
        note = (
            "No searches ran in this session, so these are not findings about "
            "the curriculum - add a SerpApi key or record demo fixtures first."
        )

    return GapReport(
        gaps=gaps,
        units_total=len(unit_labels),
        units_matched=matched,
        searched=searched,
        note=note,
    )
