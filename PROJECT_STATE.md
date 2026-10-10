# PROJECT_STATE.md — living status

**Last updated:** 2026-10-10, after the first live SerpApi validation (Phase 5).
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
| **Phase 5** | Demo hardening + live validation | ✅ **done** (2026-10-10) |

**Test suite: 370 passed, 4 skipped, ~2.2s.** Tests are isolated from `.env`
(autouse fixture in `tests/conftest.py`) and never make a network call.

### Phase 5: the first real SerpApi run, 2026-10-10

A SerpApi key went into `.env` (git-ignored). About 110 of the free tier's 250
monthly credits were used for diagnosis and recording, leaving **~140** at the end
of the session. Check with `python check_serpapi.py` (free) before recording again.

**What real data showed, and what changed:**

| Finding (measured) | Change |
|---|---|
| `engine=google` ignored `site:` on 7/9 CS searches and on 8/8 platforms in a matrix; only 8/80 results were real listings. `google_light` and `as_sitesearch` did the same. | `site:` adapters use `engine=duckduckgo` (on-site 11/11 on 6/7 platforms). |
| DuckDuckGo leaks or returns nothing for quoted OR-groups. | `query_style="keywords"`: one plain phrase plus platform wording. `planner.keyword_for` picks the phrase shared by the most competencies in the group, unique across groups. |
| Catchafire and Idealist `url_pattern`s were guesses that rejected **every** real listing; Taproot's accepted any page. | Patterns rewritten from observed URLs; regression tests use those real URLs. |
| Taproot Plus redirects to taprootfoundation.org (like VolunteerMatch). | Adapter **removed**. |
| UN Online Volunteering: 0 results on 6/6 searches (WAF-blocked from indexers). | `enabled_by_default=False`; `active()` now honours that flag. |
| Devpost `/software/*` and `devfolio.co/hackathons/past` passed tier 0 but are past projects and index pages. | Patterns now accept only hackathon subdomains. |
| Unstop serves an identical 25 KB JS shell for every listing; **58/67** recorded events had finished, including the #1 CS card. | Declarative `StatusApi` on the adapter: the gate asks `unstop.com/api/public/competition/{id}` for `reg_status` and `end_regn_dt`. |
| Demo mode skipped the liveness probe, so finished events ranked as open. | The probe (free HTTP) runs in demo mode too and fails soft offline. `probe_top_n` 12 → 40, env `S2S_PROBE_TOP_N`. |
| Empty searches are billed but were logged as free "skipped" and never cached. | Billed in the ledger and cached. |
| Google Jobs returned recruiter lead-gen ads, senior roles, and Shona/Danish course ads. | `signals.exclusion_reason` removes them (not just ranks them low). |
| Semantic scored 0 on 32/34 real CS results: listings name a theme, not a syllabus phrase. | Keyword-level credit (title > body), generic words ignored. |
| 15 Scholar papers buried every Sociology volunteer role. | `scorer.diversify`: ≤3 per platform in the top 10, within a 15-point margin. |
| Unstop titles carry the edition year ("… – 2020"). | Tier 1 archives titles whose newest year is in the past. |

### Round 2, same day: job links and the Science preset

| Finding (measured) | Change |
|---|---|
| Job cards linked Google's share URL, which cannot be probed. | `serpapi_client.job_link` uses `apply_options`, preferring the original board over re-posting aggregators. 34/38 recorded jobs verify live; Indeed/Jooble block checkers → unverified. |
| BeBee pages embed every error string ("no longer accepting applications") in a script bundle; raw matching archived week-old jobs. | `gate.dead_marker_in`: English markers match visible text only; `"json":tokens` match the raw body; `re:` markers are regexes. |
| GitHub's page embeds linked PRs' states: open apache/doris#48203 read as closed. | GitHub liveness comes from the REST API (`StatusApi`). |
| Kaggle, DrivenData and Zooniverse had no data: no preset selected them. | New preset `sppu_bsc_stats_sem5_biostatistics` (Science); ecology / ML aliases added; 9 searches recorded. |
| Kaggle pages are JS shells; the API needs login and answers our verifier with a reCAPTCHA. | Kaggle is `snippet_only` — never page-probed, cards stay unverified. **We do not bypass bot checks.** `tier2_probe` itself now refuses non-`http_probe` adapters. |
| Zooniverse pages hide "paused" / "not launched". | Zooniverse `StatusApi` (`state`, `launch_approved`). |
| DrivenData finished competitions say "Completed Sep 2026". | Regex marker; subdomain and group competition URLs accepted. |
| Subpages (`/titanic/data`, `/project/about/team`) became separate cards. | `PlatformAdapter.canonical` collapses them at parse time. |
| Verified job cards filled the Science top 12, burying every unverifiable Kaggle competition. | Diversity may now promote an unverified card over a capped live one (never an archived one). |
| Verification scripts posed as Chrome, so they could pass checks the product fails. | Both use `gate.USER_AGENT`. |

**Result**, demo mode with the live probe on:

| Preset | Searches (naive) | Saving | Live | Unverified | Archived |
|---|---|---|---|---|---|
| CS (VTU DBMS) | 10 (44) | 77% | 12 | 0 | 22 |
| Commerce (DU B.Com) | 8 (55) | 85% | 16 | 0 | 18 |
| Design (B.Des) | 8 (55) | 85% | 21 | 3 | 20 |
| Sociology (DU) | 10 (44) | 77% | 29 | 23 | 17 |
| Science (SPPU B.Sc. Stats) | 10 (55) | 82% | 11 | 29 | 11 |

The app was driven in a browser in demo mode: 0 live searches, 10 cache hits, and
cards render with a verified verdict, verbatim syllabus quote and score breakdown.

`scripts/verify_adapters.py`: 7 of 9 OK; Kaggle reports NOT-PROBED by design and
Unstop's newest samples are all finished events (1 of 25 live in a wider sample).
It falls back to recorded SerpApi URLs for client-rendered listing pages.

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
| `mesh/adapters.py` | 15 platforms (11 active by default), declarative, tiers A–D, engine routing notes. |
| `mesh/affinity.py` | Discipline × platform matrix, share-weighted profile. |
| `mesh/planner.py` | Platform selection + competency grouping + shared-keyword choice + hard cap. |
| `mesh/serpapi_client.py` | Cache-first, ledger-accounted, per-engine parsing. |
| `mesh/cache.py` | SHA-256 disk cache; read-only demo replay. |
| `mesh/ledger.py` | Credit accounting and skip reasons. |
| `ground/gate.py` | Tier 0 URL shape, tier 1 snippet + title year, tier 2 HTTP probe or status API. |
| `ground/dedupe.py` | URL canonicalisation + near-duplicate merge. |
| `score/scorer.py` | Four weighted terms, composite, ranking, platform diversity. |
| `score/signals.py` | Seniority, compensation, effort, deliverable, scam, exclusion reasons. |
| `ship/bridge.py` | Grounded "why you can do this" + template fallback. |
| `ship/blueprint.py` | 3-phase playbook per discipline + pitfalls. |
| `ship/export.py` | STAR bullet, Markdown case study. |
| `analyze/gaps.py` | Syllabus Gap Report. |
| `ui/cards.py` | Card + score table + ship assets (only Streamlit importer). |
| `tests/test_ui.py` | Drives the real app via Streamlit `AppTest`. |

### Top level

| File | Notes |
|---|---|
| `app.py` | Streamlit UI. Sidebar budget controls, 3 result tabs, dev tab. |
| `scripts/record_fixtures.py` | Records real SerpApi responses. `--dry-run` prints cost first. Replaces harvested stand-ins. |
| `check_serpapi.py` | Key + quota check via the free account endpoint (renamed from `test_serpapi.py`). |
| `fixtures/syllabi/` | 5 presets in real Indian university formats (Commerce, Design, CS, Sociology, Science). |
| `fixtures/serpapi/` | **45 real SerpApi responses** (DuckDuckGo, Google Jobs, Scholar) for all 5 presets, recorded 2026-10-10. |
| `tests/` | 370 tests. |

### Deleted

`src/` — superseded by `s2s/`. `src/agent.py` was a hardcoded 3-subquery demo.

---

## 3. Environment

```bash
cd "/Users/saisalelkar/Desktop/serp hack"
.venv/bin/python -m pytest          # 370 passed, 4 skipped
.venv/bin/streamlit run app.py
```

- **venv: Python 3.12.12** at `.venv/`. System python3 is 3.14 — do not use it.
- streamlit 1.65.0, anthropic 1.12.1, pypdf, python-docx, charset-normalizer,
  requests, pytest, python-dotenv.
- **No SerpApi SDK.** Calls go over plain HTTPS (`serpapi_client._search`), so it
  does not matter whether a machine has `google-search-results` or `serpapi`.
  (`google-search-results` may still be in old venvs; nothing imports it.)

### Keys

- `SERPAPI_API_KEY` — **set** in `.env` (git-ignored, free plan, 250/month).
- `ANTHROPIC_API_KEY` — absent → heuristic extraction + template bridge.

---

## 4. Decisions made (do not re-litigate)

| Decision | Reason |
|---|---|
| Streamlit only; no FastAPI | Those pins were never imported. `s2s/` stays import-clean. |
| No SerpApi SDK; plain HTTPS | Both SDKs claim the `serpapi` module name with different APIs; supersedes the earlier "keep `google-search-results`" decision (2026-10-10). |
| Platforms graded Tier A/B/C/D | Treating all platforms equally produces dead links on stage. |
| Tier C off by default | Upwork/Freelancer/Contra gate detail pages. |
| Heuristic extraction and template bridge are first-class | Two external APIs = two demo failure modes. |
| Affinity uses a **share-weighted profile**, not a max | A max let one stray secondary discipline pull Kaggle into a Design plan. |
| `search_phrases` puts aliases before `canonical` | `canonical` is the unit heading — academic language absent from real briefs. |
| Score breakdown shown in the UI | Transparent arithmetic beats an opaque "AI match: 87%". |
| Quote validation is **whitespace-insensitive** | Reflowing a line break is not a paraphrase. Invented content is still rejected. |
| `s2s.ship.ship()` renamed to `prepare()` | `from s2s.ship import ship` was ambiguous with the package. |
| `site:` adapters use `engine=duckduckgo` | Measured: Google ignored `site:` on every platform; DuckDuckGo kept it. |
| Keyword queries, not OR-groups, for `site:` | OR-groups leaked off-site or returned nothing on every engine tested. |
| Out-of-reach listings are removed, not penalised | A ranked-low senior role still lands on a student's screen. |
| Liveness probe runs in demo mode | It is free HTTP; skipping it showed finished events as open. |

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

**Live-validation round, 2026-10-10** (found with a real key, not by tests):

20. `record_fixtures.py` claimed to overwrite harvested stand-ins but served them
    as cache hits, so real responses were never recorded.
21. Google ignored `site:` (see section 1): ~90% of results were off-site junk.
22. Catchafire and Idealist URL patterns rejected every real listing.
23. Taproot Plus is dead (redirects off-host); its pattern accepted any page.
24. UN Online Volunteering is unsearchable; `active()` ignored `enabled_by_default`.
25. Empty searches were billed but recorded as free, and never cached.
26. Both B.Com groups chose the same keyword, issuing one query twice.
27. Unstop "live" verdicts were meaningless: one shell page for every listing.
28. Demo mode skipped liveness, so ended events ranked as open.
29. Semantic score was 0 for nearly every real result.
30. Senior roles, recruiter ads and non-English listings reached the cards.
31. One platform could fill the whole top 10.
32. Tests read the developer's real `.env`; with a key present they failed and
    could have spent credits.
33. `origin/main` gained a teammate commit moving to the new `serpapi` SDK, which
    our `from serpapi import GoogleSearch` cannot run on. Both SDKs dropped in
    favour of plain HTTPS; `check_serpapi.py` now uses the free account endpoint.
34. Job cards were unverifiable (Google share links).
35. BeBee's script bundle archived open jobs (raw-body marker matching).
36. GitHub's `"state":"closed"` marker fired on linked PRs, archiving open issues.
37. Kaggle 200-shell pages read as "live"; `tier2_probe` ignored `liveness`.
38. Verification scripts used a browser user agent the product never sends.
39. PhD-level roles reached undergraduate cards.

---

## 5. What is left — and who owns it

Nothing blocks a demo. These are the known limits, in priority order.

| # | Item | Owner | Notes |
|---|---|---|---|
| 1 | **Catchafire liveness is unverified wording.** Pages return 200 with no observed "closed" text; its `gate_markers` are still guesses. | dev | Find a closed Catchafire listing and record the real marker. |
| 2 | **Kaggle can never be verified** without a Kaggle login (API) — and we will not bypass its CAPTCHA. | user | Optional: a Kaggle API token would allow an authenticated status check. |
| 3 | **Search engines index mostly past events.** 58/67 Unstop and every recorded DrivenData competition had finished. The gate archives them correctly, but live supply per run is thinner than the raw counts suggest. | — | Market reality. |
| 4 | Many open events are not syllabus-specific (e.g. general hackathons for CS). | — | An Anthropic key would improve extraction phrasing. |
| 5 | Indeed and Jooble job links block automated checks → unverified. | — | Honest as labelled. |
| 6 | `scripts/harvest_demo_fixtures.py` is superseded by real fixtures. | dev | Keep for keyless forks, or delete. |
| 7 | Time the 5-stream demo end to end (~15 s per run, mostly link checks). | user | |

Credit budget: recording all presets again costs ~45 credits. `check_serpapi.py`
shows the remaining quota for free.

---

## 6. Next action

Phase 5 is complete and pushed. The next most valuable step is item 1 above
(observe a real closed Catchafire listing), then a timed dry run of the demo.
