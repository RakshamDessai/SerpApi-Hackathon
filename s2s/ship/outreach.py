"""Stage 6d: words a student sends to other people.

Features 32 (application message) and 52 (LinkedIn post). Deterministic, like
the STAR bullet: both have a fixed shape, and every fact in them comes from
data the pipeline already holds - the listing, the verdict and the student's
own syllabus. Nothing here invents a deadline, a budget or a result.

The syllabus quote is the same verbatim `source_span` the bridge quotes, so
the student never sends a stranger a claim about their course that the
course does not make.
"""

from __future__ import annotations

import re

from s2s.mesh import adapters as adapter_registry
from s2s.models import Opportunity

#: What the student offers to send first, by ecosystem. A concrete first
#: deliverable is what makes a cold message worth answering.
FIRST_STEP = {
    "ngo_impact": "a one-page plan of how I would approach it",
    "freelance": "a short plan and a timeline before any work starts",
    "data_challenge": "a baseline notebook as my first submission",
    "hackathon": "a one-paragraph project idea for the team",
    "open_source": "a short outline of the change before I open a pull request",
    "internship": "a sample of similar coursework",
    "research": "a short summary of the method I would use",
    "event": "my questions about the agenda before I register",
}

#: LinkedIn's "see more" cut is near 210 characters; the opening line must
#: carry the point on its own.
HOOK_LIMIT = 200


def _platform(opportunity: Opportunity) -> tuple[str, str]:
    adapter = adapter_registry.ADAPTERS.get(opportunity.adapter_key)
    if adapter is None:
        return opportunity.adapter_key, "ngo_impact"
    return adapter.label, adapter.ecosystem


def _quote(span: str, limit: int = 160) -> str:
    span = " ".join(span.split())
    if len(span) <= limit:
        return span
    return span[:limit].rsplit(" ", 1)[0] + "..."


def _hashtag(phrase: str) -> str:
    """'Indexing, Storage and Query' -> '#IndexingStorageQuery ' (or '')."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", phrase) if w.lower() != "and"]
    tag = "".join(w.capitalize() for w in words[:3])
    return f"#{tag} " if tag else ""


def application_message(opportunity: Opportunity, student_name: str = "") -> str:
    """A short, specific application or cover message for one listing.

    Short on purpose: organisations skim. It names the listing, the exact
    syllabus unit, one verbatim line from it, the tools, and a first step.
    """
    competency = opportunity.matched_competency
    _, ecosystem = _platform(opportunity)
    who = opportunity.organization or "your team"
    tools = (f" I work in {', '.join(competency.tools[:3])}."
             if competency.tools else "")
    first = FIRST_STEP.get(ecosystem, FIRST_STEP["ngo_impact"])
    sign = student_name.strip() or "[Your name]"

    lines = [
        f"Hello {who},",
        "",
        f'I would like to work on "{opportunity.title}".',
        "",
        f"I am a student, and this semester my course covers "
        f"{competency.canonical.lower()} in {competency.source_unit}. "
        f'The syllabus says: "{_quote(competency.source_span)}"',
        "",
        f"That is the skill this work needs.{tools} "
        f"I can send {first}.",
        "",
        "Thank you for your time.",
        sign,
    ]
    return "\n".join(lines)


def linkedin_post(opportunity: Opportunity) -> str:
    """A plain post for after the work is delivered.

    Past tense, like the STAR bullet: it is for finished work. No emoji walls,
    no "thrilled to announce" - the specifics carry it.
    """
    competency = opportunity.matched_competency
    platform, _ = _platform(opportunity)
    where = opportunity.organization or platform

    hook = (f"This semester I learned {competency.canonical.lower()} in class. "
            f"This month I used it on real work for {where}.")
    if len(hook) > HOOK_LIMIT:
        hook = f"I used {competency.canonical.lower()} from my course on real work."

    lines = [
        hook,
        "",
        f"The work: {opportunity.title}.",
        f"The course unit: {competency.source_unit}.",
    ]
    if competency.tools:
        lines.append(f"Tools: {', '.join(competency.tools[:3])}.")
    lines += [
        "",
        "What I learned: [one thing the classroom did not teach you].",
        "",
        "If you study the same unit, open work like this exists now. "
        "Look outside the classroom.",
        "",
        f"{_hashtag(competency.canonical)}#StudentWork #LearningByDoing",
    ]
    return "\n".join(lines)
