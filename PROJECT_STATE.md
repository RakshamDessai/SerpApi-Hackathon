# PROJECT_STATE.md — living status

**Last updated:** 2026-10-09, after the adversarial audit round.
**Update rule:** rewrite sections 1, 2 and 6 at the end of every phase. A cold
session must be able to resume from this file alone.

---

## 1. Where we are right now

| Phase | Scope | Status |
|---|---|---|
| **Phase 0** | Unblock the repo | ✅ done |
| **Phase 1** | Vertical spine: syllabus → scored cards | ✅ done |
| **Phase 2** | Open-Mesh breadth, planner, gate, efficiency panel | ✅ done |
| **Phase 3** | Bridge, Blueprint, STAR bullet, case study | ✅ done |
| **Phase 4** | Syllabus Gap Report | ✅ done |
| **Phase 5** | **Demo hardening + live validation** | 🔶 **blocked on a SerpApi key** |

**Test suite: 278 passed, 2 skipped, ~1.8s.** App serves HTTP 200, no tracebacks, pyflakes clean. The UI is now driven end-to-end by `tests/test_ui.py` (Streamlit `AppTest`), which clicks the button and asserts cards, ship assets and the gap tab actually render.

### What is genuinely finished

Everything that can be built and verified **without API keys**:

- Full pipeline, stages 0–6, wired end to end.
- 17 platform adapters, affinity matrix, budget planner (82–86% credit saving).
- Grounding Gate tiers 0–2, dedupe, four-term scorer with visible breakdown.
- Ship stage: bridge, 3-phase blueprint per discipline, STAR bullet, case study.
- Syllabus Gap Report.
- Streamlit UI: ingest, results, gap tab, ship assets in-card, dev tab with
  registry and credit-efficiency panel.
- 278 tests, including a full pipeline acceptance run against cache-seeded
  SerpApi-shaped payloads, and a Streamlit `AppTest` suite that clicks through
  the real UI.

### The one blocker: no key has ever been used

**No real SerpApi query has ever run.** The chain around the call is proven; the
*relevance of real results* is not. This is the entire remaining risk.

First actions once a key exists:

```bash
.venv/bin/python check_serpapi.py                        # connectivity
.venv/bin/python scripts/record_fixtures.py --dry-run    # 40 credits, all 4 presets
.venv/bin/python scripts/record_fixtures.py              # then demo mode works offline
```

Then expect to re-tune `s2s/extract/taxonomy.py` → `MARKET_ALIASES` once real
results are visible. That table is the single biggest lever on result quality.

---

## 2. What exists, file by file

### Pipeline (`s2s/`, ~4,200 lines)

| File | What it does |
|---|---|
| `models.py` | Stage contracts: `Competency`, `PlatformAdapter`, `Dork`, `RawResult`, `ScoreBreakdown`, `Opportunity`, `ShipBlueprint`. |
| `config.py` | `Settings.load()` per run; `.env.example` placeholders read as unset. |
| `pipeline.py` | Orchestrates stages 0–5, progress callback, attaches the gap report. |
| `ingest/loader.py` | PDF / DOCX / TXT / paste, encoding detection, clear scanned-PDF error. |
| `ingest/structure.py` | Curriculum tree: `Unit I`, `Unit-3`, `Module 2`, `Semester III`. |
| `extract/taxonomy.py` | 54 market aliases, 33 tool hints, discipline keywords, Bloom verbs. |
| `extract/heuristic.py` | No-LLM fallback. **First-class path.** |
| `extract/llm.py` | Claude `messages.parse()`, prompt caching, verbatim-span validation. |
| `mesh/adapters.py` | 17 platforms, declarative, tiers A–D. |
| `mesh/affinity.py` | Discipline × platform matrix, share-weighted profile. |
| `mesh/planner.py` | Platform selection + OR-packing + hard cap. |
| `mesh/serpapi_client.py` | Cache-first, ledger-accounted, per-engine parsing. |
| `mesh/cache.py` | SHA-256 disk cache; read-only demo replay. |
| `mesh/ledger.py` | Credit accounting and skip reasons. |
| `ground/gate.py` | Tier 0 URL shape, tier 1 snippet, tier 2 HTTP probe. |
| `ground/dedupe.py` | URL canonicalisation + near-duplicate merge. |
| `score/scorer.py` | Four weighted terms, composite, ranking. |
| `score/signals.py` | Seniority, compensation, effort, deliverable, scam. |
| `ship/bridge.py` | Grounded "why you can do this" + template fallback. |
| `ship/blueprint.py` | 3-phase playbook per discipline + pitfalls. |
| `ship/export.py` | STAR bullet, Markdown case study. |
| `analyze/gaps.py` | Syllabus Gap Report. |
| `ui/cards.py` | Card + score table + ship assets (only Streamlit importer). |
| `analyze/gaps.py` tests | `tests/test_ui.py` drives the real app via Streamlit `AppTest`. |

### Top level

| File | Notes |
|---|---|
| `app.py` | Streamlit UI. Sidebar budget controls, 3 result tabs, dev tab. |
| `scripts/record_fixtures.py` | Records real SerpApi responses. `--dry-run` prints cost first. |
| `check_serpapi.py` | Standalone connectivity check (renamed from `test_serpapi.py`). |
| `fixtures/syllabi/` | 4 presets in real Indian university formats. |
| `fixtures/serpapi/` | **Empty — awaiting a key.** |
| `tests/` | 278 tests, ~1,700 lines. |

### Deleted

`src/` — superseded by `s2s/`. `src/agent.py` was a hardcoded 3-subquery demo.

---

## 3. Environment

```bash
cd "/Users/saisalelkar/Desktop/serp hack"
.venv/bin/python -m pytest          # 278 passed, 2 skipped
.venv/bin/streamlit run app.py
```

- **venv: Python 3.12.12** at `.venv/`. System python3 is 3.14 — do not use it.
- streamlit 1.65.0, anthropic 1.12.1, google-search-results 2.4.2, pypdf,
  python-docx, charset-normalizer, requests, pytest, python-dotenv.
- `serpapi` package **not** installed — no namespace conflict.

### Keys — both ABSENT

`.env` holds `.env.example` placeholders, correctly read as unset.

- No `SERPAPI_API_KEY` → live search unavailable.
- No `ANTHROPIC_API_KEY` → heuristic extraction + template bridge.

---

## 4. Decisions made (do not re-litigate)

| Decision | Reason |
|---|---|
| Streamlit only; no FastAPI | Those pins were never imported. `s2s/` stays import-clean. |
| `google-search-results`, not `serpapi` | Both claim the `serpapi` module name; only the former has `GoogleSearch`. |
| Platforms graded Tier A/B/C/D | Treating all platforms equally produces dead links on stage. |
| Tier C off by default | Upwork/Freelancer/Contra gate detail pages. |
| Heuristic extraction and template bridge are first-class | Two external APIs = two demo failure modes. |
| Affinity uses a **share-weighted profile**, not a max | A max let one stray secondary discipline pull Kaggle into a Design plan. |
| `search_phrases` puts aliases before `canonical` | `canonical` is the unit heading — academic language absent from real briefs. |
| Score breakdown shown in the UI | Transparent arithmetic beats an opaque "AI match: 87%". |
| Quote validation is **whitespace-insensitive** | Reflowing a line break is not a paraphrase. Invented content is still rejected. |
| `s2s.ship.ship()` renamed to `prepare()` | `from s2s.ship import ship` was ambiguous with the package. |

### Bugs found and fixed (all have regression tests)

1. `requirements.txt` was UTF-16LE → `pip install -r` failed on line 1.
2. Taxonomy substring matching put Excel in typography units (`"ratio"` inside
   `"contrast ratios"`). Now whole-word.
3. `"classification"` as an alias key tagged typography as machine learning.
4. Affinity max-over-union sent Design students to Kaggle.
5. Dorks searched academic unit titles instead of market aliases.
6. `EFFORT_HINTS` read `"12-month cash flow forecast"` as a 40–80h capstone.
7. Ledger labelled every skip "cap reached" regardless of cause.
8. `savings` divided by calls-made, so a keyless run reported a fake 99% saving.
9. STAR bullet printed the platform twice when the organisation was unknown.
10. Case study mixed second-person bridge text under a first-person heading.
11. Gap Report suggested the exact phrases it had just searched for.
12. **Quote validation was whitespace-sensitive**, so every multi-line span
    failed and honest bridges were silently rejected.
13. Bridge quoted the unit heading back inside the unit quote ("stutter").

**Audit round, 2026-10-09** (found by adversarial review, not by re-running tests):

14. **The "Stream" dropdown was dead UI** - collected and never used. Now
    promotes the chosen discipline to primary; verified to change platform
    selection.
15. **Grounding Gate tier 2 had never been run at all.** Against live pages it
    reported a closed GitHub issue as `live`, because the probe truncated the
    body at 60 KB and GitHub's React page puts the state in embedded JSON at
    ~400 KB. Window raised to 600 KB; now verified correct on a known-closed
    and a known-open issue.
16. **GitHub's gate markers were invented, not observed.** The human-readable
    "this issue was closed" never appears in the HTML. Replaced with the
    observed `"state":"closed"`, negative-checked against open issues.
17. **Over-generic gate markers** (`"closed"`, `"has expired"`, `"sign in"`)
    would match unrelated text in a 600 KB page and archive live work. All
    tightened; a new test enforces a 12-character minimum.
18. `.env.example` documented none of the seven `S2S_*` knobs.
19. Three unused imports, a stale `check_serpapi.py` self-reference, a wrong
    test count in the README, and a deprecated `use_container_width` call.

---

## 5. What is left — and who owns it

### Yours (blocking)

| # | Action | Why it matters |
|---|---|---|
| 1 | **Provide a SerpApi key** in `.env` | Nothing has been validated against real results. This is the only true blocker. |
| 2 | Decide the submission deadline | Determines whether Phase 5 polish is worth it. |
| 3 | *(optional)* Anthropic key | Upgrades extraction and bridge prose. Not required. |

### Mine, once the key exists

| # | Action |
|---|---|
| 1 | Record fixtures (40 credits) so demo mode works offline. |
| 2 | Inspect real results and re-tune `MARKET_ALIASES`. |
| 3 | Validate gate tier 2 against real Catchafire/Upwork login walls. |
| 4 | Click every link in all four presets (Phase 5 link audit) — a dead link shown as live is a release blocker. |
| 5 | Time the 4-stream demo end to end. |

---

## 6. Next action

Everything buildable without keys is done. **The next step needs the SerpApi
key.** Until it exists, the highest-value remaining work is cosmetic only.
