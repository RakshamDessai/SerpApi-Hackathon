"""Opportunity card rendering.

Only modules under `s2s/ui/` may import Streamlit.

Stage 6 (bridge, blueprint, STAR bullet) is generated lazily, when a card is
expanded - producing it for every result would waste tokens on cards nobody
opens.
"""

from __future__ import annotations

import streamlit as st

from s2s.mesh import adapters as adapter_registry
from s2s.models import (
    COMPENSATION_LABEL,
    ECOSYSTEM_LABEL,
    Opportunity,
    RawResult,
)
from s2s.score import signals
from s2s.ship import export, prepare

VERDICT_BADGE = {
    "live": ("✅", "Verified live"),
    "unverified": ("◻️", "Unverified"),
    "archived": ("🗄️", "Archived"),
}

BAND_BADGE = {
    "beginner": "🟢 Beginner",
    "intermediate": "🟡 Intermediate",
    "advanced": "🔴 Advanced",
}


def _as_raw(opportunity: Opportunity) -> RawResult:
    return RawResult(
        title=opportunity.title,
        url=opportunity.url,
        snippet=opportunity.snippet,
        adapter_key=opportunity.adapter_key,
    )


def _header(opportunity: Opportunity) -> None:
    adapter = adapter_registry.ADAPTERS.get(opportunity.adapter_key)
    platform = adapter.label if adapter else opportunity.adapter_key
    ecosystem = ECOSYSTEM_LABEL.get(adapter.ecosystem, "") if adapter else ""
    compensation = COMPENSATION_LABEL.get(signals.compensation_for(_as_raw(opportunity)), "")
    icon, verdict_text = VERDICT_BADGE[opportunity.verdict]

    head, score_col = st.columns([5, 1])
    with head:
        st.markdown(f"**{opportunity.title}**")
        bits = [f"`{platform}`"]
        if ecosystem:
            bits.append(f"`{ecosystem}`")
        if compensation:
            bits.append(f"`{compensation}`")
        bits.append(BAND_BADGE.get(opportunity.band, ""))
        if opportunity.est_hours:
            bits.append(f"`{opportunity.effort_label}`")
        st.caption(" · ".join(b for b in bits if b))
    with score_col:
        st.metric("Match", f"{opportunity.score.total}%")

    line = f"{icon} {verdict_text}"
    if opportunity.provenance != "serpapi":
        line += " · ⚠︎ harvested, not SerpApi"
    if opportunity.verified_at:
        line += f" · checked {opportunity.verified_at:%H:%M}"
    if opportunity.organization:
        line += f" · {opportunity.organization}"
    st.caption(line)


def _score_table(opportunity: Opportunity) -> None:
    rows = [
        {"Term": label, "Score": f"{raw:.2f}", "Contribution": f"{points:.1f} pts"}
        for label, raw, points in opportunity.score.explain()
    ]
    rows.append({"Term": "Total", "Score": "", "Contribution": f"{opportunity.score.total} pts"})
    st.table(rows)


def _ship_section(opportunity: Opportunity, api_key: str | None, syllabus_text: str) -> None:
    """Bridge, blueprint and proof of work - generated on first expand."""
    prepare(opportunity, api_key=api_key, syllabus_text=syllabus_text)

    st.markdown("#### Why you can already do this")
    st.markdown(opportunity.bridge)

    blueprint = opportunity.blueprint
    if blueprint is not None:
        st.markdown("#### Your ship blueprint")
        phase1, phase2, phase3 = st.tabs(["1 · Setup", "2 · Execution", "3 · Delivery"])
        for tab, steps in (
            (phase1, blueprint.setup),
            (phase2, blueprint.execution),
            (phase3, blueprint.delivery),
        ):
            with tab:
                for index, step in enumerate(steps, 1):
                    st.markdown(f"{index}. {step}")

        if blueprint.toolkit:
            st.caption("**Free toolkit:** " + ", ".join(blueprint.toolkit))
        if blueprint.pitfalls:
            with st.expander("Common mistakes to avoid"):
                for pitfall in blueprint.pitfalls:
                    st.markdown(f"- {pitfall}")

    st.markdown("#### Proof of work")
    st.caption("Paste this into your CV once the work is delivered:")
    st.code(opportunity.star_bullet, language="text")

    st.download_button(
        "Download case study (.md)",
        data=export.case_study_markdown(opportunity, opportunity.bridge),
        file_name=export.filename_for(opportunity),
        mime="text/markdown",
        key=f"dl-{abs(hash(opportunity.url))}",
    )


def render(
    opportunity: Opportunity,
    api_key: str | None = None,
    syllabus_text: str = "",
) -> None:
    with st.container(border=True):
        _header(opportunity)

        with st.expander("Why this matches, and how to ship it"):
            if opportunity.snippet:
                st.markdown(f"> {opportunity.snippet}")

            competency = opportunity.matched_competency
            st.markdown("**Your syllabus unit**")
            st.markdown(f"`{competency.source_unit}` — matched on **{competency.canonical}**")
            st.markdown(f"> _{' '.join(competency.source_span.split())}_")

            st.markdown("**Score breakdown**")
            _score_table(opportunity)

            if opportunity.scam_flag:
                st.warning("This listing tripped the low-quality/scam filter.")

            st.divider()
            _ship_section(opportunity, api_key, syllabus_text)

            st.divider()
            st.link_button("Open the brief ↗", opportunity.url)


def render_list(
    opportunities: list[Opportunity],
    empty_message: str,
    api_key: str | None = None,
    syllabus_text: str = "",
) -> None:
    if not opportunities:
        st.info(empty_message)
        return
    for opportunity in opportunities:
        render(opportunity, api_key=api_key, syllabus_text=syllabus_text)
