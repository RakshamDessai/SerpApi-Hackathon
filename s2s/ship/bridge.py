"""Stage 6b: the Pedagogical Bridge - "why you can already do this".

Features 22 and 29, implemented as one mechanism.

This is the emotional core of the product and also the most dangerous thing it
says, because it makes a claim about the student's own syllabus. So the rule is
absolute: **the bridge must quote `Competency.source_span` verbatim.**

Two paths:

* `template` - deterministic, always available, quotes the span by construction.
* `claude`   - richer prose, but post-validated. If the model's output does not
  contain a long literal run of the span, the generation is discarded and the
  template is used instead. A pretty sentence is not worth a fabricated claim.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from s2s.models import Competency, Opportunity

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"

#: The generated bridge must contain a literal run of the syllabus span at
#: least this long, otherwise we cannot claim it quoted the student's syllabus.
MIN_QUOTED_CHARS = 40


@dataclass
class Bridge:
    text: str
    mode: str                 # "claude" | "template"
    quoted_span: str
    note: str | None = None


SYSTEM_PROMPT = """You explain to a student why their coursework already \
qualifies them for a specific live project.

You receive exactly two pieces of evidence:
  <syllabus_unit>  verbatim text from the student's own syllabus
  <live_brief>     the title and snippet of a real, currently-open project

Rules:
- Quote the syllabus unit verbatim at least once, inside quotation marks. Copy \
it character for character; do not paraphrase it as if quoting.
- Reference only what the live brief actually says. Never invent a requirement, \
deliverable, deadline, budget or organisation name that is not in the brief.
- Name the specific technique, formula or method from the unit that applies.
- 3-4 sentences, second person, concrete. No inspirational filler.
- If the unit genuinely does not prepare the student for this brief, say so \
plainly instead of stretching."""


# ---------------------------------------------------------------- helpers ---

def _squash(text: str) -> str:
    """Lowercase with runs of whitespace collapsed to one space.

    Quote validation runs on this form. Reflowing a line break is not a
    paraphrase, and rejecting it would discard honest bridges - the guard
    exists to catch invented content, not changed spacing.
    """
    return " ".join(text.lower().split())


def _longest_common_run(text: str, span: str) -> str:
    """Longest run of `span` that also appears in `text`, ignoring whitespace."""
    haystack = _squash(text)
    needle_source = " ".join(span.split())
    needle = _squash(span)

    best = ""
    length = len(needle)
    for start in range(length):
        if length - start <= len(best):
            break
        for end in range(length, start + len(best), -1):
            if needle[start:end] in haystack:
                if end - start > len(best):
                    best = needle_source[start:end]
                break
    return best


def quotes_syllabus(text: str, span: str) -> bool:
    return len(_longest_common_run(text, span)) >= MIN_QUOTED_CHARS


# --------------------------------------------------------------- template ---

def _trim(span: str, limit: int = 220) -> str:
    span = " ".join(span.split())
    if len(span) <= limit:
        return span
    cut = span[:limit].rsplit(" ", 1)[0]
    return cut + "..."


def template_bridge(opportunity: Opportunity) -> Bridge:
    competency: Competency = opportunity.matched_competency
    quoted = _trim(competency.source_span)

    tools = ""
    if competency.tools:
        tools = (
            f" You already work in {', '.join(competency.tools[:2])} for this unit, "
            f"which is what this deliverable needs."
        )

    text = (
        f'In **{competency.source_unit}** your syllabus covers: "{quoted}" '
        f'That is the same ground this brief stands on - it asks for '
        f'**{competency.canonical.lower()}**, which you have already been '
        f'assessed on.{tools} You are not learning this from scratch; you are '
        f'applying it outside the classroom for the first time.'
    )
    return Bridge(text=text, mode="template", quoted_span=quoted)


# ------------------------------------------------------------------ claude --

def claude_bridge(opportunity: Opportunity, api_key: str, syllabus_text: str) -> Bridge:
    """Richer prose, validated against the real syllabus before being returned."""
    import anthropic

    competency = opportunity.matched_competency
    client = anthropic.Anthropic(api_key=api_key)

    user = (
        f"<syllabus_unit unit=\"{competency.source_unit}\">\n"
        f"{competency.source_span}\n</syllabus_unit>\n\n"
        f"<live_brief platform=\"{opportunity.adapter_key}\">\n"
        f"Title: {opportunity.title}\n"
        f"Snippet: {opportunity.snippet}\n</live_brief>"
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        output_config={"effort": "medium"},
        system=[
            {"type": "text", "text": SYSTEM_PROMPT},
            {
                "type": "text",
                "text": f"<full_syllabus>\n{syllabus_text}\n</full_syllabus>",
                # Breakpoint AFTER the syllabus: it is identical for every card,
                # so expanding ten cards costs roughly one syllabus read.
                "cache_control": {"type": "ephemeral"},
            },
        ],
        messages=[{"role": "user", "content": user}],
    )

    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    ).strip()

    if not text:
        raise RuntimeError("empty response")

    if not quotes_syllabus(text, competency.source_span):
        raise RuntimeError("generated bridge did not quote the syllabus verbatim")

    return Bridge(
        text=text,
        mode="claude",
        quoted_span=_longest_common_run(text, competency.source_span),
    )


# -------------------------------------------------------------- dispatcher --

def build(
    opportunity: Opportunity,
    api_key: str | None = None,
    syllabus_text: str = "",
) -> Bridge:
    if api_key and syllabus_text:
        try:
            return claude_bridge(opportunity, api_key, syllabus_text)
        except Exception as exc:
            log.warning("bridge fell back to template: %s", exc)
            bridge = template_bridge(opportunity)
            bridge.note = f"Claude unavailable ({exc}); used the template bridge."
            return bridge
    return template_bridge(opportunity)
