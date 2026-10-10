"""No-LLM extraction fallback.

Lower quality than `llm.py`, but it must always work: a hackathon demo that
hard-depends on two external APIs has two single points of failure. This path
runs whenever `ANTHROPIC_API_KEY` is absent or the LLM call fails.

Strategy: for each parsed unit, mine the unit text against `taxonomy.py` for
market aliases, tools, disciplines and a Bloom level. Units that yield no market
alias are dropped - they are theory with no live counterpart, which is itself
signal the Gap Report (Phase 4) will use.
"""

from __future__ import annotations

import re

from s2s.extract import taxonomy
from s2s.ingest.loader import RawSyllabus
from s2s.ingest.structure import CurriculumNode, unit_spans
from s2s.models import Competency

# Phrases that look like topics inside a unit body: "Title Case Runs" or
# comma-separated clauses following a colon.
TOPIC_SPLIT = re.compile(r"[.;]\s+|\n")

#: Sentence boundaries: a period followed by whitespace and a capital letter.
#: Avoids splitting on "Unit 3." or decimal points mid-sentence.
SENTENCE_SPLIT = re.compile(r"(?<=[.])\s+(?=[A-Z])")

#: A leading "Unit III: Title" / "Module 4: Title" heading on a unit body.
HEADING_PREFIX = re.compile(
    r"^(?:unit|module|chapter)\s*[-\u2013:.\s]*\s*(?:\d{1,2}|[ivx]{1,4})\b[^\n.]{0,80}",
    re.IGNORECASE,
)


def _title_from(label: str) -> str:
    """'Unit 3: Working Capital Management' -> 'Working Capital Management'."""
    return label.split(":", 1)[1].strip() if ":" in label else label.strip()


def _canonical_for(unit_title: str, aliases: list[str]) -> str:
    """Prefer the unit's own title; it is what the student will recognise."""
    cleaned = unit_title.strip(" -:.")
    if cleaned and cleaned.lower() not in {"full syllabus", "unit"}:
        return cleaned
    return aliases[0] if aliases else "General coursework"


def _salient_sentence(body: str, aliases: list[str]) -> str:
    """Pick the sentence that best justifies the aliases, for `source_span`.

    This span is quoted back to the student verbatim, so a fragment ending in a
    stray comma reads badly even though it is honest. Full sentences are
    preferred and clause fragments are only a fallback.
    """
    # Drop the unit heading itself: the bridge already names the unit, so
    # quoting "Unit II: Capital Budgeting The capital budgeting process."
    # reads as a stutter.
    body = HEADING_PREFIX.sub("", body.strip(), count=1).strip()

    sentences = [s.strip() for s in SENTENCE_SPLIT.split(body) if len(s.strip()) > 45]
    candidates = sentences or [
        s.strip() for s in TOPIC_SPLIT.split(body) if len(s.strip()) > 40
    ]
    if not candidates:
        return body.strip()[:400]

    lowered_aliases = [a.lower() for a in aliases]
    best, best_score = candidates[0], -1.0
    for sentence in candidates:
        low = sentence.lower()
        hits = sum(1 for a in lowered_aliases if a in low)
        # Nudge towards sentences that actually end, and away from stubs.
        score = hits + (0.5 if sentence.rstrip().endswith(".") else 0.0)
        if score > best_score:
            best, best_score = sentence, score

    best = best.strip()
    if not best.endswith("."):
        best += "."
    return best[:400]


def extract(
    syllabus: RawSyllabus,
    tree: CurriculumNode,
    semester: int | None = None,
    limit: int = 6,
) -> list[Competency]:
    spans = unit_spans(syllabus.text, tree)
    found: list[Competency] = []

    for label, span, offset in spans:
        aliases = taxonomy.aliases_for(span)
        if not aliases:
            continue                       # theory with no live market counterpart

        unit_title = _title_from(label)
        bloom = taxonomy.detect_bloom(span)
        sentence = _salient_sentence(span, aliases)

        # Anchor source_span to the real document so the bridge can quote it.
        local = span.find(sentence)
        span_offset = offset + local if local >= 0 else offset
        verbatim = sentence if local >= 0 else span[:400]

        found.append(
            Competency(
                canonical=_canonical_for(unit_title, aliases),
                aliases=aliases[:6],
                tools=taxonomy.tools_for(span),
                disciplines=taxonomy.detect_disciplines(span),
                bloom=bloom,
                band=taxonomy.band_for(bloom, semester),
                source_unit=label,
                source_span=verbatim,
                span_offset=span_offset,
            )
        )

    # Practical units beat recall units when we have to choose where to spend
    # SerpApi credits.
    found.sort(key=lambda c: (-c.bloom, -len(c.aliases)))
    return found[:limit]
