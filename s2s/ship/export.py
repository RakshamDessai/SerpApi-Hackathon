"""Stage 6c: proof of work.

Features 47 and 48. Turns a completed opportunity into things a student can
actually put in front of a recruiter: a STAR resume bullet and a Markdown case
study.

Deterministic - no LLM needed. A STAR bullet has a fixed shape, and filling it
from data we already hold is more reliable than asking a model to.
"""

from __future__ import annotations

from datetime import date

from s2s.mesh import adapters as adapter_registry
from s2s.models import Opportunity

#: Verb to open the Action clause, by ecosystem.
ACTION_VERB = {
    "ngo_impact": "Delivered",
    "freelance": "Delivered",
    "data_challenge": "Built and evaluated",
    "hackathon": "Designed and shipped",
    "open_source": "Contributed",
    "internship": "Worked on",
    "research": "Researched",
}

RESULT_CLAUSE = {
    "ngo_impact": "giving the organisation a reusable artefact it did not have before",
    "freelance": "accepted by the client and delivered on schedule",
    "data_challenge": "benchmarked against a public leaderboard baseline",
    "hackathon": "submitted and demonstrated to judges",
    "open_source": "merged into the upstream project and publicly visible",
    "internship": "applied to live production work",
    "research": "documented with sources for reuse",
}


def star_bullet(opportunity: Opportunity) -> str:
    """One Situation-Task-Action-Result line for a CV.

    Written in the past tense on purpose: the student pastes it in once the work
    is done, and a half-finished bullet is worse than none.
    """
    adapter = adapter_registry.ADAPTERS.get(opportunity.adapter_key)
    ecosystem = adapter.ecosystem if adapter else "ngo_impact"
    platform = adapter.label if adapter else opportunity.adapter_key

    competency = opportunity.matched_competency
    verb = ACTION_VERB.get(ecosystem, "Delivered")
    result = RESULT_CLAUSE.get(ecosystem, "delivered to the brief")
    tools = f" using {', '.join(competency.tools[:2])}" if competency.tools else ""

    # Naming the organisation is stronger than naming the platform, but saying
    # both when they are the same reads as filler.
    where = (
        f"for {opportunity.organization} (via {platform})"
        if opportunity.organization
        else f"via {platform}"
    )
    return f"{verb} {competency.canonical.lower()} {where}{tools} - {result}."


def case_study_markdown(opportunity: Opportunity, bridge_text: str | None = None) -> str:
    """A portfolio-ready write-up of one shipped project."""
    adapter = adapter_registry.ADAPTERS.get(opportunity.adapter_key)
    platform = adapter.label if adapter else opportunity.adapter_key
    competency = opportunity.matched_competency

    lines: list[str] = [
        f"# {opportunity.title}",
        "",
        f"**Platform:** {platform}  ",
        f"**Sourced:** {date.today():%B %Y}  ",
    ]
    if opportunity.organization:
        lines.append(f"**Organisation:** {opportunity.organization}  ")
    if opportunity.est_hours:
        lines.append(f"**Effort:** {opportunity.effort_label}  ")
    lines += [
        f"**Match score:** {opportunity.score.total}%  ",
        f"**Link:** {opportunity.url}",
        "",
        "## The brief",
        "",
        f"> {opportunity.snippet or 'See the original listing.'}",
        "",
        "## Why I was qualified",
        "",
        # The on-screen bridge is written to the student ("your syllabus"); a
        # portfolio page is written by them, so first person is used here.
        f"This project maps directly onto **{competency.source_unit}** of my "
        f"syllabus, which covers {competency.canonical.lower()}. I had already "
        f"been assessed on the underlying method before taking this on.",
        "",
        "### The syllabus unit this came from",
        "",
        f"**{competency.source_unit}**",
        "",
        f"> {' '.join(competency.source_span.split())}",
        "",
    ]

    if competency.tools:
        lines += ["## Tools", "", ", ".join(competency.tools), ""]

    if opportunity.blueprint:
        blueprint = opportunity.blueprint
        lines += ["## How I delivered it", ""]
        for heading, steps in (
            ("Setup", blueprint.setup),
            ("Execution", blueprint.execution),
            ("Delivery", blueprint.delivery),
        ):
            lines.append(f"### {heading}")
            lines.append("")
            lines += [f"{i}. {step}" for i, step in enumerate(steps, 1)]
            lines.append("")

    lines += [
        "## Resume bullet",
        "",
        f"- {star_bullet(opportunity)}",
        "",
        "---",
        "",
        "*Sourced with S2S (Syllabus-to-Ship), which matches university "
        "coursework to live, open work using SerpApi.*",
    ]
    return "\n".join(lines)


def filename_for(opportunity: Opportunity) -> str:
    slug = "".join(
        char.lower() if char.isalnum() else "-" for char in opportunity.title
    )
    slug = "-".join(part for part in slug.split("-") if part)[:60]
    return f"{slug or 'case-study'}.md"
