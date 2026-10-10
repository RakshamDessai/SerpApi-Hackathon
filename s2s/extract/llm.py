"""LLM-backed competency extraction (stage 1, primary path).

One Claude call turns a syllabus into `Competency[]`. This is the *only* place
the LLM shapes the search; everything downstream is deterministic.

Two non-negotiable guards:

1. **Structured output.** `client.messages.parse()` validates against a Pydantic
   schema at the SDK layer, so there is no JSON parsing or repair logic here.
2. **Verbatim span validation.** Every returned `source_span` must be a literal
   substring of the uploaded syllabus. Anything else is dropped. The bridge
   generator quotes this span back to the student, so a paraphrase here becomes
   a confident lie about their own syllabus later.

Any failure - missing key, API error, schema mismatch, zero surviving
competencies - raises `LLMUnavailable`, and the pipeline falls back to
`heuristic.py`. The fallback is a first-class path, not a stub.
"""

from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from s2s.extract import taxonomy
from s2s.ingest.loader import RawSyllabus
from s2s.ingest.structure import CurriculumNode, unit_spans
from s2s.models import Competency, Discipline

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"
MAX_TOKENS = 8000

VALID_DISCIPLINES = {d.value for d in Discipline}


class LLMUnavailable(RuntimeError):
    """Extraction could not be completed by the LLM; caller should fall back."""


# ------------------------------------------------------------- schema -------

class ExtractedCompetency(BaseModel):
    canonical: str = Field(description="The market-facing skill, 2-6 words.")
    aliases: list[str] = Field(
        description="2-5 phrases as they would appear in a real job or project "
                    "brief. Market language, never academic language."
    )
    tools: list[str] = Field(description="Free tools a student would use. 0-4 items.")
    disciplines: list[str] = Field(description="1-2 values from the allowed list.")
    bloom: int = Field(description="Bloom level 1-6 of the unit's verbs.")
    source_unit: str = Field(description="The unit heading, e.g. 'Unit 3: Working Capital'.")
    source_span: str = Field(
        description="A VERBATIM sentence copied character-for-character from the "
                    "syllabus. Do not paraphrase, reformat or fix typos."
    )


class Extraction(BaseModel):
    competencies: list[ExtractedCompetency]


# ------------------------------------------------------------- prompt -------

def _alias_examples(limit: int = 14) -> str:
    rows = []
    for academic, market in list(taxonomy.MARKET_ALIASES.items())[:limit]:
        rows.append(f"  {academic} -> {', '.join(market)}")
    return "\n".join(rows)


SYSTEM_PROMPT = f"""You convert university syllabi into market-facing competencies \
so a student can be matched to live, currently-open work.

Your single job: read the syllabus and, for each unit that maps to something \
anyone actually pays for or recruits volunteers for, emit one competency.

Rules:
- `aliases` is the most important field. Academic phrasing never appears in a \
real brief; market phrasing does. Translate.
- Skip units that are pure theory with no live counterpart. Returning 4 strong \
competencies beats returning 8 weak ones.
- `source_span` must be copied VERBATIM from the syllabus - character for \
character, including any odd spacing. It is validated by exact string match and \
silently discarded if it does not match.
- `bloom` reflects the unit's own verbs: 1 remember, 2 understand, 3 apply, \
4 analyse, 5 evaluate, 6 create.
- `disciplines` must come from this list only: {', '.join(sorted(VALID_DISCIPLINES))}

Worked examples of the translation:
{_alias_examples()}
"""


# ------------------------------------------------------------ extraction ----

def _normalise_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _locate(span: str, haystack: str, haystack_ws: str) -> tuple[str, int] | None:
    """Find `span` in the document, tolerating whitespace differences only.

    Returns the document's own substring (not the model's copy) plus its offset,
    so what we quote later is always the real text.
    """
    index = haystack.find(span)
    if index >= 0:
        return span, index

    # Retry on whitespace-normalised text; models reflow line breaks.
    needle = _normalise_ws(span)
    if len(needle) < 25:
        return None
    pos = haystack_ws.find(needle)
    if pos < 0:
        return None

    # Map the normalised hit back to a real offset by walking the original.
    compact = 0
    for real_index, char in enumerate(haystack):
        if compact == pos:
            tail = haystack[real_index:real_index + len(needle) + 40]
            return tail.strip()[:len(needle) + 10], real_index
        if not (char.isspace() and (real_index == 0 or haystack[real_index - 1].isspace())):
            compact += 1
    return None


def extract(
    syllabus: RawSyllabus,
    tree: CurriculumNode,
    api_key: str,
    semester: int | None = None,
    limit: int = 6,
) -> list[Competency]:
    try:
        import anthropic
    except ImportError as exc:                                   # pragma: no cover
        raise LLMUnavailable("anthropic SDK not installed") from exc

    if not api_key:
        raise LLMUnavailable("no ANTHROPIC_API_KEY")

    client = anthropic.Anthropic(api_key=api_key)

    units = unit_spans(syllabus.text, tree)
    outline = "\n".join(f"- {label}" for label, _, _ in units[:30])
    user_content = (
        f"Course semester: {semester if semester else 'unknown'}\n"
        f"Units detected:\n{outline}\n\n"
        f"Return at most {limit} competencies.\n\n"
        f"--- SYLLABUS ---\n{syllabus.text}"
    )

    try:
        response = client.messages.parse(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": "low"},     # mechanical mapping, not deep reasoning
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # Stable prefix: cached across runs and across students.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
            output_format=Extraction,
        )
    except Exception as exc:
        raise LLMUnavailable(f"Claude call failed: {exc}") from exc

    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise LLMUnavailable("no parsed_output on response")

    usage = getattr(response, "usage", None)
    if usage is not None:
        log.info(
            "extract: in=%s cache_read=%s out=%s",
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "cache_read_input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
        )

    haystack = syllabus.text
    haystack_ws = _normalise_ws(haystack)

    competencies: list[Competency] = []
    dropped = 0

    for item in parsed.competencies:
        located = _locate(item.source_span, haystack, haystack_ws)
        if located is None:
            dropped += 1
            log.warning("dropping %r: source_span not found verbatim", item.canonical)
            continue
        verbatim, offset = located

        disciplines = [
            Discipline(value) for value in item.disciplines if value in VALID_DISCIPLINES
        ]
        if not disciplines:
            disciplines = taxonomy.detect_disciplines(verbatim)

        bloom = item.bloom if 1 <= item.bloom <= 6 else taxonomy.detect_bloom(verbatim)

        competencies.append(
            Competency(
                canonical=item.canonical.strip(),
                aliases=[a.strip() for a in item.aliases if a.strip()][:6],
                tools=[t.strip() for t in item.tools if t.strip()][:4],
                disciplines=disciplines[:2],
                bloom=bloom,
                band=taxonomy.band_for(bloom, semester),
                source_unit=item.source_unit.strip(),
                source_span=verbatim,
                span_offset=offset,
            )
        )

    if dropped:
        log.warning("span validation dropped %d of %d competencies",
                    dropped, len(parsed.competencies))

    if not competencies:
        raise LLMUnavailable("every competency failed verbatim span validation")

    competencies.sort(key=lambda c: (-c.bloom, -len(c.aliases)))
    return competencies[:limit]
