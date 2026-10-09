"""Core data types for the S2S pipeline.

These are the contracts between stages. Everything below the extract stage is
deterministic code operating on `Competency`; the LLM never touches anything
downstream of it. See BUILD_PLAN.md section 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


# --------------------------------------------------------------- taxonomy ---

class Discipline(str, Enum):
    """Broad academic stream. Drives platform affinity (mesh/affinity.py)."""

    COMMERCE_FINANCE = "commerce_finance"
    ARTS_HUMANITIES = "arts_humanities"
    DESIGN_VISUAL = "design_visual"
    CS_SOFTWARE = "cs_software"
    DATA_QUANT = "data_quant"
    LIFE_SCIENCES = "life_sciences"
    LAW_POLICY = "law_policy"
    MEDIA_COMM = "media_comm"
    ENG_MECHANICAL = "eng_mechanical"

    @property
    def label(self) -> str:
        return {
            "commerce_finance": "Commerce, Accounting & Finance",
            "arts_humanities": "Arts, Humanities & Social Sciences",
            "design_visual": "Design & Visual Media",
            "cs_software": "Computer Science & Software",
            "data_quant": "Data, Statistics & Quantitative",
            "life_sciences": "Life Sciences & Biotech",
            "law_policy": "Law, Policy & Governance",
            "media_comm": "Media & Mass Communication",
            "eng_mechanical": "Mechanical & Civil Engineering",
        }[self.value]


Band = Literal["beginner", "intermediate", "advanced"]
BAND_ORDER: dict[str, int] = {"beginner": 0, "intermediate": 1, "advanced": 2}


# ------------------------------------------------------------- competency ---

@dataclass(frozen=True)
class Competency:
    """One market-facing skill extracted from one syllabus unit.

    This is the only object the LLM produces. `source_span` must be a verbatim
    substring of the uploaded syllabus: the bridge generator quotes it, and
    extract/llm.py drops any competency whose span fails that check. That
    guard is what stops a hallucinated claim about the student's own syllabus.
    """

    canonical: str
    aliases: list[str]
    tools: list[str]
    disciplines: list[Discipline]
    bloom: int                 # 1 Remember .. 6 Create
    band: Band
    source_unit: str
    source_span: str
    span_offset: int = -1      # char offset into the raw text, -1 if unknown

    @property
    def search_phrases(self) -> list[str]:
        """Phrases worth putting in a dork, strongest first, de-duplicated.

        Aliases come first and `canonical` is a last resort. `canonical` is the
        student-facing label - usually the unit heading, e.g. "Brand Identity
        Systems" - and academic phrasing like that appears in no real brief.
        The aliases are the market translation, so they are what we search.
        """
        seen: set[str] = set()
        out: list[str] = []
        for p in [*self.aliases, self.canonical]:
            key = p.lower().strip()
            if key and key not in seen:
                seen.add(key)
                out.append(p.strip())
        return out


# ---------------------------------------------------------------- adapter ---

Engine = Literal["google", "google_jobs", "google_scholar"]
Ecosystem = Literal[
    "ngo_impact", "freelance", "data_challenge",
    "hackathon", "open_source", "internship", "research",
]
Compensation = Literal["paid", "stipend", "bounty", "volunteer", "prize", "credit_only"]
TrustTier = Literal["A", "B", "C"]
LivenessCheck = Literal["url_shape", "http_probe", "snippet_only"]

ECOSYSTEM_LABEL: dict[str, str] = {
    "ngo_impact": "NGO Impact",
    "freelance": "Freelance",
    "data_challenge": "Data Challenge",
    "hackathon": "Hackathon",
    "open_source": "Open Source",
    "internship": "Internship",
    "research": "Research",
}

COMPENSATION_LABEL: dict[str, str] = {
    "paid": "Paid",
    "stipend": "Stipend",
    "bounty": "Bounty",
    "volunteer": "Volunteer",
    "prize": "Prize",
    "credit_only": "Credit only",
}


@dataclass(frozen=True)
class PlatformAdapter:
    """A declarative platform descriptor.

    Adding a platform to the Open-Mesh is one entry in mesh/adapters.py, not a
    new module. `url_pattern` doubles as Grounding Gate tier 0.
    """

    key: str
    label: str
    engine: Engine
    site: str | None
    url_pattern: str
    dork: str                       # template containing {terms}; may use {negatives}
    ecosystem: Ecosystem
    compensation: Compensation
    trust: TrustTier
    liveness: LivenessCheck
    gate_markers: tuple[str, ...] = ()
    extra_params: dict = field(default_factory=dict)
    enabled_by_default: bool = True


# ------------------------------------------------------------------ dork ----

@dataclass(frozen=True)
class Dork:
    """One planned SerpApi call, covering one or more competencies."""

    adapter_key: str
    query: str
    covers: tuple[Competency, ...]
    engine: Engine
    params: dict = field(default_factory=dict)
    est_cost: int = 1


# ----------------------------------------------------------------- result ---

Verdict = Literal["live", "unverified", "archived"]

VERDICT_LABEL: dict[str, str] = {
    "live": "Verified Live",
    "unverified": "Unverified",
    "archived": "Archived",
}


#: Where a result's underlying data came from. "serpapi" is the real thing;
#: "public-api-harvest" means it was fetched directly from the platform so the
#: demo has something real to show without a key. Never conflate the two.
Provenance = Literal["serpapi", "public-api-harvest"]

PROVENANCE_LABEL: dict[str, str] = {
    "serpapi": "SerpApi",
    "public-api-harvest": "Harvested directly (not SerpApi)",
}


@dataclass
class RawResult:
    """A single SerpApi organic/jobs result, before grounding and scoring."""

    title: str
    url: str
    snippet: str
    adapter_key: str
    organization: str | None = None
    posted_at: datetime | None = None
    raw: dict = field(default_factory=dict)
    provenance: Provenance = "serpapi"


@dataclass
class ScoreBreakdown:
    """The four weighted terms plus the composite. Rendered in the UI so the
    match percentage is auditable rather than an opaque number."""

    semantic: float
    level: float
    freshness: float
    actionability: float
    weights: dict[str, float]

    @property
    def total(self) -> int:
        raw = (
            self.weights["semantic"] * self.semantic
            + self.weights["level"] * self.level
            + self.weights["freshness"] * self.freshness
            + self.weights["actionability"] * self.actionability
        )
        return int(round(raw * 100))

    def explain(self) -> list[tuple[str, float, float]]:
        """[(term label, raw 0-1 score, weighted contribution in points)]."""
        rows = [
            ("Semantic alignment", self.semantic, self.weights["semantic"]),
            ("Semester / level fit", self.level, self.weights["level"]),
            ("Freshness", self.freshness, self.weights["freshness"]),
            ("Actionability", self.actionability, self.weights["actionability"]),
        ]
        return [(label, value, value * weight * 100) for label, value, weight in rows]


@dataclass
class ShipBlueprint:
    """The 3-phase execution playbook attached to a selected opportunity."""

    setup: list[str]
    execution: list[str]
    delivery: list[str]
    toolkit: list[str]
    pitfalls: list[str] = field(default_factory=list)


@dataclass
class Opportunity:
    """A live, grounded, scored brief ready to render as a card."""

    title: str
    url: str
    snippet: str
    adapter_key: str
    matched_competency: Competency
    score: ScoreBreakdown
    verdict: Verdict = "unverified"
    organization: str | None = None
    posted_at: datetime | None = None
    verified_at: datetime | None = None
    band: Band = "intermediate"
    est_hours: tuple[int, int] | None = None
    scam_flag: bool = False
    provenance: Provenance = "serpapi"
    bridge: str | None = None
    blueprint: ShipBlueprint | None = None
    star_bullet: str | None = None

    @property
    def effort_label(self) -> str:
        if not self.est_hours:
            return "Unknown effort"
        lo, hi = self.est_hours
        if hi <= 4:
            return f"Micro-task ({lo}-{hi} hrs)"
        if hi <= 15:
            return f"Weekend sprint ({lo}-{hi} hrs)"
        return f"Capstone ({lo}-{hi}+ hrs)"
