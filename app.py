"""S2S (Syllabus-to-Ship) - Streamlit front end.

Run with:
    .venv/bin/streamlit run app.py

This module is view-only. All logic lives in `s2s/`, which never imports
Streamlit, so the same pipeline can be driven from a CLI or an API later.
"""

from __future__ import annotations

import streamlit as st

from s2s.config import FIXTURE_DIR, Settings
from s2s.ingest import loader
from s2s.ingest.loader import IngestError
from s2s.mesh import adapters as adapter_registry
from s2s.models import Discipline
from s2s.ui import cards
from s2s import pipeline

st.set_page_config(
    page_title="S2S - Syllabus to Ship",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded",
)

PRESETS = {
    "Commerce - DU B.Com, Financial Management (Sem 3)":
        ("du_bcom_sem3_financial_management", 3),
    "Design - B.Des, Typography & Visual Communication (Sem 1)":
        ("bdes_sem1_typography_visual_communication", 1),
    "Engineering - VTU CSE, Database Management Systems (Sem 4)":
        ("vtu_cse_sem4_dbms", 4),
    "Social Sciences - DU Sociology, Research Methods (Sem 2)":
        ("du_sociology_sem2_research_methods", 2),
}


# --------------------------------------------------------------- sidebar ----

def render_sidebar() -> Settings:
    with st.sidebar:
        st.header("Configuration")

        settings = Settings.load()

        if not settings.has_serpapi:
            st.error("No SerpApi key")
            typed = st.text_input(
                "Paste a SerpApi key for this session:",
                type="password",
                help="Or add SERPAPI_API_KEY to .env",
            )
            if typed:
                st.session_state["serpapi_key"] = typed
        if st.session_state.get("serpapi_key"):
            settings = Settings.load(serpapi_override=st.session_state["serpapi_key"])

        if settings.has_serpapi:
            st.success("SerpApi key loaded")

        st.caption(f"**Search:** {settings.search_mode}")
        st.caption(f"**Extraction:** {settings.extraction_mode}")

        st.divider()
        st.subheader("Search budget")

        settings.demo_mode = st.toggle(
            "Demo mode (cached fixtures, 0 credits)",
            value=settings.demo_mode,
            help="Replays recorded SerpApi responses. Guarantees the demo "
                 "cannot spend credits and works with no network.",
        )
        settings.credit_cap = st.slider(
            "Hard credit cap per run", 2, 40, settings.credit_cap,
            help="No run can exceed this many SerpApi searches.",
        )
        settings.max_platforms = st.slider(
            "Platforms per run", 2, 8, settings.max_platforms
        )
        settings.include_tier_c = st.toggle(
            "Include commercial freelance (links may be gated)",
            value=settings.include_tier_c,
            help="Upwork, Freelancer and Contra gate their detail pages and "
                 "their Google index goes stale, so they are the main source "
                 "of dead links. Off by default.",
        )

        st.divider()
        active = adapter_registry.active(include_tier_c=settings.include_tier_c)
        st.caption(f"**Open-Mesh:** {len(active)} platforms active "
                   f"of {len(adapter_registry.ADAPTERS)} registered")

        return settings


# ------------------------------------------------------------- screen 1 -----

def screen_ingest(settings: Settings) -> None:
    st.subheader("1. Your syllabus")

    left, right = st.columns([3, 2])

    with left:
        preset_name = st.selectbox(
            "Start from a preset", ["(upload or paste my own)"] + list(PRESETS)
        )
        uploaded = st.file_uploader(
            "Or upload a syllabus", type=["pdf", "docx", "txt", "md"]
        )
        pasted = st.text_area("Or paste the unit list", height=160)

    with right:
        stream_label = st.selectbox(
            "Stream",
            ["(detect automatically)"] + [d.label for d in Discipline],
            help="Overrides keyword detection. Pick yours if the detected "
                 "platforms look wrong for your course.",
        )
        stream = next(
            (d for d in Discipline if d.label == stream_label), None
        )
        semester = st.slider("Current semester", 1, 8, 3)
        st.caption(
            "Semester calibrates task difficulty: a first-year student is "
            "matched to foundational briefs, a final-year student to complex ones."
        )

    if not st.button("Find me live work", type="primary", width="stretch"):
        return

    # -- load the syllabus -------------------------------------------------
    try:
        if uploaded is not None:
            syllabus = loader.from_bytes(uploaded.getvalue(), uploaded.name)
        elif pasted.strip():
            syllabus = loader.from_text(pasted)
        elif preset_name in PRESETS:
            stem, preset_semester = PRESETS[preset_name]
            syllabus = loader.from_fixture(FIXTURE_DIR / "syllabi" / f"{stem}.txt")
            semester = preset_semester
        else:
            st.warning("Pick a preset, upload a file, or paste your unit list.")
            return
    except IngestError as exc:
        st.error(str(exc))
        return

    # -- run ---------------------------------------------------------------
    bar = st.progress(0.0, text="Starting...")

    def on_progress(message: str, fraction: float) -> None:
        bar.progress(min(1.0, fraction), text=message)

    with st.spinner("Running the pipeline..."):
        result = pipeline.run(
            syllabus, settings, semester=semester,
            progress=on_progress, stream=stream,
        )

    bar.empty()
    st.session_state["result"] = result


# ------------------------------------------------------------- screen 2 -----

def screen_results() -> None:
    result: pipeline.PipelineResult | None = st.session_state.get("result")
    if result is None:
        return

    st.divider()
    st.subheader("2. Live opportunities")

    naive, planned, saved = result.savings
    a, b, c, d = st.columns(4)
    a.metric("Competencies", len(result.competencies))
    b.metric("Searches used", planned, delta=f"-{naive - planned} vs naive",
             delta_color="inverse")
    c.metric("Credit saving", f"{saved:.0%}")
    d.metric("Opportunities", len(result.actionable))

    st.caption(f"Budget ledger: {result.ledger.summary()}")

    for warning in result.warnings:
        st.warning(warning)

    reasons = result.ledger.skip_reasons()
    if reasons:
        with st.expander(f"{sum(reasons.values())} searches were skipped - why"):
            for note, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
                st.write(f"- {count}x {note}")

    with st.expander("Competencies extracted from your syllabus"):
        for competency in result.competencies:
            st.markdown(
                f"**{competency.canonical}** — `{competency.source_unit}` · "
                f"Bloom {competency.bloom} · {competency.band}"
            )
            st.caption("Market phrasing: " + ", ".join(competency.aliases))

    with st.expander(f"The {len(result.dorks)} searches that were planned"):
        for dork in result.dorks:
            st.code(f"[{dork.engine}] {dork.query}", language="text")

    settings = st.session_state.get("settings")
    api_key = settings.anthropic_key if settings else None

    gap_count = len(result.gap_report.gaps) if result.gap_report else 0
    tab_live, tab_archived, tab_gaps = st.tabs(
        [f"Actionable ({len(result.actionable)})",
         f"Archived ({len(result.archived)})",
         f"Syllabus gaps ({gap_count})"]
    )

    with tab_live:
        cards.render_list(
            result.actionable,
            "No live opportunities yet. Add a SerpApi key, or record demo "
            "fixtures with scripts/record_fixtures.py.",
            api_key=api_key,
            syllabus_text=result.syllabus.text,
        )

    with tab_archived:
        st.caption(
            "These were reachable but closed or expired. Kept as study "
            "references - never shown as live work."
        )
        cards.render_list(result.archived, "Nothing archived.",
                          api_key=api_key, syllabus_text=result.syllabus.text)

    with tab_gaps:
        render_gap_report(result)


def render_gap_report(result: pipeline.PipelineResult) -> None:
    """Which parts of the syllabus matched nothing at all."""
    report = result.gap_report
    if report is None:
        st.info("No gap report for this run.")
        return

    st.markdown(f"### {report.headline}")

    if not report.searched:
        # Without searches every unit looks dead; saying so would be a lie.
        st.warning(report.note)
        return

    st.progress(report.coverage,
                text=f"{report.units_matched} of {report.units_total} units led to live work")
    st.caption(
        "This inverts the usual question. Instead of what matches your syllabus, "
        "it asks which parts of it the market is no longer asking for."
    )

    if not report.gaps:
        st.success("Every parsed unit led to live work.")
        return

    for gap in report.gaps:
        with st.container(border=True):
            st.markdown(f"**{gap.unit_label}** — `{gap.label}`")
            st.caption(gap.explanation)
            st.markdown(gap.detail)
            if gap.suggestions:
                st.markdown(
                    "**In demand instead:** " + ", ".join(f"`{s}`" for s in gap.suggestions)
                )


# ----------------------------------------------------------------- main -----

def main() -> None:
    st.title("S2S — Syllabus to Ship")
    st.caption("Turn what you are studying this semester into live, real-world work.")

    settings = render_sidebar()
    st.session_state["settings"] = settings

    tab_main, tab_dev = st.tabs(["Find work", "Developer"])

    with tab_main:
        screen_ingest(settings)
        screen_results()

    with tab_dev:
        render_dev_tab(settings)


def render_dev_tab(settings: Settings) -> None:
    result = st.session_state.get("result")
    if result is not None:
        st.subheader("Credit efficiency")
        naive, planned, saved = result.savings
        a, b, c = st.columns(3)
        a.metric("Naive plan", f"{naive} searches",
                 help="Every competency against every active platform.")
        b.metric("S2S plan", f"{planned} searches")
        c.metric("Saved", f"{saved:.0%}")
        st.caption(
            "Discipline-affinity platform selection removes platforms that "
            "cannot hold work for this student; boolean OR-packing then folds "
            "several competencies into one search. Relevance is recovered "
            "afterwards because every result is scored against every "
            "competency individually."
        )
        with st.expander("Ledger detail"):
            st.table([
                {
                    "platform": e.adapter_key,
                    "cost": e.cost,
                    "source": "cache" if e.cache_hit else ("skipped" if e.skipped else "live"),
                    "note": e.note,
                }
                for e in result.ledger.entries
            ])
        st.divider()

    st.subheader("Platform registry")
    st.caption(
        "Each platform is one declarative adapter. Adding a new one is a "
        "registry entry, not a new module."
    )
    st.dataframe(
        [
            {
                "key": a.key,
                "platform": a.label,
                "engine": a.engine,
                "ecosystem": a.ecosystem,
                "pay": a.compensation,
                "tier": a.trust,
                "liveness": a.liveness,
                "default": "on" if a.enabled_by_default else "opt-in",
            }
            for a in adapter_registry.all_adapters()
        ],
        width="stretch",
        hide_index=True,
    )

    st.subheader("Multi-engine explorer")
    st.caption("Probe SerpApi directly - useful when adding a new adapter.")

    engine = st.selectbox("Engine", ["google", "google_jobs", "google_scholar"])
    query = st.text_input("Query", value='site:kaggle.com/competitions ("time series")')

    if st.button("Run search"):
        if not settings.has_serpapi:
            st.error("No SerpApi key configured.")
            return
        from s2s.mesh.cache import build as build_cache
        from s2s.mesh.ledger import BudgetLedger
        from s2s.mesh.serpapi_client import SerpApiClient
        from s2s.models import Dork

        ledger = BudgetLedger(cap=settings.credit_cap)
        client = SerpApiClient(settings.serpapi_key, build_cache(settings), ledger,
                               demo_mode=settings.demo_mode)
        dork = Dork(adapter_key="kaggle", query=query, covers=(), engine=engine)
        results = client.run(dork)
        st.caption(ledger.summary())
        st.json([{"title": r.title, "url": r.url, "snippet": r.snippet[:200]}
                 for r in results[:5]])


if __name__ == "__main__":
    main()
