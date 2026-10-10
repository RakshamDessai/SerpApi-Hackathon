"""Discipline x platform affinity.

Expected-yield prior: how likely is this platform to be holding live work for a
student of this discipline? Used by the planner to spend credits only where they
can pay off.

The zeros matter as much as the highs. A Design student should never burn a
credit on Kaggle and a Sociology student should never burn one on GitHub; that
alone removes more than half of a naive search plan.

Scale: 0.0 never, 0.3 occasionally, 0.6 often, 0.9 a primary venue.
"""

from __future__ import annotations

from s2s.models import Discipline

D = Discipline

# adapter key -> {discipline: affinity}
AFFINITY: dict[str, dict[Discipline, float]] = {
    "unv": {
        D.ARTS_HUMANITIES: 0.9, D.LAW_POLICY: 0.9, D.COMMERCE_FINANCE: 0.7,
        D.DATA_QUANT: 0.5, D.DESIGN_VISUAL: 0.6, D.MEDIA_COMM: 0.7,
        D.LIFE_SCIENCES: 0.4, D.CS_SOFTWARE: 0.3, D.ENG_MECHANICAL: 0.3,
    },
    "kaggle": {
        D.DATA_QUANT: 0.9, D.LIFE_SCIENCES: 0.8, D.CS_SOFTWARE: 0.7,
        D.COMMERCE_FINANCE: 0.3, D.ARTS_HUMANITIES: 0.0, D.DESIGN_VISUAL: 0.0,
        D.LAW_POLICY: 0.0, D.MEDIA_COMM: 0.0, D.ENG_MECHANICAL: 0.2,
    },
    "unstop": {
        D.COMMERCE_FINANCE: 0.9, D.CS_SOFTWARE: 0.8, D.DATA_QUANT: 0.7,
        D.DESIGN_VISUAL: 0.6, D.LAW_POLICY: 0.6, D.MEDIA_COMM: 0.6,
        D.ARTS_HUMANITIES: 0.5, D.ENG_MECHANICAL: 0.6, D.LIFE_SCIENCES: 0.4,
    },
    "devpost": {
        D.CS_SOFTWARE: 0.9, D.DATA_QUANT: 0.6, D.DESIGN_VISUAL: 0.3,
        D.ENG_MECHANICAL: 0.3, D.LIFE_SCIENCES: 0.3, D.COMMERCE_FINANCE: 0.2,
        D.ARTS_HUMANITIES: 0.1, D.LAW_POLICY: 0.1, D.MEDIA_COMM: 0.1,
    },
    "devfolio": {
        D.CS_SOFTWARE: 0.9, D.DATA_QUANT: 0.6, D.DESIGN_VISUAL: 0.3,
        D.ENG_MECHANICAL: 0.3, D.COMMERCE_FINANCE: 0.2, D.LIFE_SCIENCES: 0.2,
        D.ARTS_HUMANITIES: 0.1, D.LAW_POLICY: 0.1, D.MEDIA_COMM: 0.1,
    },
    "github": {
        D.CS_SOFTWARE: 0.9, D.DATA_QUANT: 0.5, D.LIFE_SCIENCES: 0.2,
        D.DESIGN_VISUAL: 0.1, D.ENG_MECHANICAL: 0.1, D.COMMERCE_FINANCE: 0.0,
        D.ARTS_HUMANITIES: 0.0, D.LAW_POLICY: 0.0, D.MEDIA_COMM: 0.0,
    },
    "drivendata": {
        D.DATA_QUANT: 0.8, D.LIFE_SCIENCES: 0.7, D.CS_SOFTWARE: 0.5,
        D.ARTS_HUMANITIES: 0.3, D.COMMERCE_FINANCE: 0.2, D.LAW_POLICY: 0.2,
        D.DESIGN_VISUAL: 0.0, D.MEDIA_COMM: 0.1, D.ENG_MECHANICAL: 0.2,
    },
    "catchafire": {
        D.DESIGN_VISUAL: 0.9, D.COMMERCE_FINANCE: 0.9, D.ARTS_HUMANITIES: 0.8,
        D.MEDIA_COMM: 0.8, D.LAW_POLICY: 0.8, D.DATA_QUANT: 0.4,
        D.CS_SOFTWARE: 0.2, D.LIFE_SCIENCES: 0.3, D.ENG_MECHANICAL: 0.2,
    },
    "idealist": {
        D.ARTS_HUMANITIES: 0.8, D.LAW_POLICY: 0.7, D.MEDIA_COMM: 0.6,
        D.COMMERCE_FINANCE: 0.5, D.DESIGN_VISUAL: 0.5, D.DATA_QUANT: 0.4,
        D.LIFE_SCIENCES: 0.3, D.CS_SOFTWARE: 0.2, D.ENG_MECHANICAL: 0.2,
    },
    "zooniverse": {
        D.LIFE_SCIENCES: 0.8, D.DATA_QUANT: 0.6, D.ARTS_HUMANITIES: 0.4,
        D.CS_SOFTWARE: 0.2, D.COMMERCE_FINANCE: 0.0, D.DESIGN_VISUAL: 0.0,
        D.LAW_POLICY: 0.0, D.MEDIA_COMM: 0.1, D.ENG_MECHANICAL: 0.1,
    },
    "upwork": {
        D.DESIGN_VISUAL: 0.9, D.COMMERCE_FINANCE: 0.8, D.CS_SOFTWARE: 0.8,
        D.MEDIA_COMM: 0.8, D.DATA_QUANT: 0.7, D.LAW_POLICY: 0.6,
        D.ARTS_HUMANITIES: 0.4, D.ENG_MECHANICAL: 0.6, D.LIFE_SCIENCES: 0.3,
    },
    "freelancer": {
        D.DESIGN_VISUAL: 0.8, D.CS_SOFTWARE: 0.8, D.COMMERCE_FINANCE: 0.7,
        D.DATA_QUANT: 0.6, D.MEDIA_COMM: 0.6, D.ENG_MECHANICAL: 0.6,
        D.LAW_POLICY: 0.4, D.ARTS_HUMANITIES: 0.3, D.LIFE_SCIENCES: 0.2,
    },
    "contra": {
        D.DESIGN_VISUAL: 0.8, D.MEDIA_COMM: 0.7, D.CS_SOFTWARE: 0.6,
        D.COMMERCE_FINANCE: 0.4, D.DATA_QUANT: 0.4, D.ARTS_HUMANITIES: 0.3,
        D.LAW_POLICY: 0.2, D.LIFE_SCIENCES: 0.1, D.ENG_MECHANICAL: 0.2,
    },
    "gjobs": {
        D.CS_SOFTWARE: 0.8, D.COMMERCE_FINANCE: 0.7, D.DATA_QUANT: 0.7,
        D.DESIGN_VISUAL: 0.6, D.MEDIA_COMM: 0.6, D.ENG_MECHANICAL: 0.6,
        D.LIFE_SCIENCES: 0.5, D.LAW_POLICY: 0.5, D.ARTS_HUMANITIES: 0.4,
    },
    "scholar": {
        D.LIFE_SCIENCES: 0.8, D.LAW_POLICY: 0.7, D.ARTS_HUMANITIES: 0.6,
        D.DATA_QUANT: 0.6, D.CS_SOFTWARE: 0.4, D.COMMERCE_FINANCE: 0.3,
        D.ENG_MECHANICAL: 0.4, D.MEDIA_COMM: 0.3, D.DESIGN_VISUAL: 0.1,
    },
}

#: Below this, a platform is not worth a credit for this student.
#: Tuned against the four preset syllabi: high enough to keep Kaggle away from
#: a Design student, low enough to keep DrivenData for a quantitative one.
AFFINITY_FLOOR = 0.40

#: A competency's first discipline is its primary; the second is corroborating.
PRIMARY_WEIGHT = 1.0
SECONDARY_WEIGHT = 0.35


def discipline_profile(competencies) -> dict[Discipline, float]:
    """How much of this student's syllabus each discipline accounts for.

    Normalised to sum to 1.0. Built from competencies rather than a flat set so
    one stray secondary tag cannot dominate - "classification of typefaces"
    tagging a typography unit as data science must not pull in Kaggle.
    """
    weights: dict[Discipline, float] = {}
    for competency in competencies:
        for index, discipline in enumerate(competency.disciplines):
            weight = PRIMARY_WEIGHT if index == 0 else SECONDARY_WEIGHT
            weights[discipline] = weights.get(discipline, 0.0) + weight

    total = sum(weights.values())
    if total <= 0:
        return {}
    return {d: w / total for d, w in weights.items()}


def score(adapter_key: str, profile: dict[Discipline, float]) -> float:
    """Share-weighted affinity: how much of this syllabus the platform serves.

    A weighted mean, not a max. Taking the max let a single weak secondary
    discipline award a platform full marks.
    """
    table = AFFINITY.get(adapter_key, {})
    return sum(share * table.get(discipline, 0.0) for discipline, share in profile.items())
