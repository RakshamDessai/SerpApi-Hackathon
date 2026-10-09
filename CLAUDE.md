# CLAUDE.md — S2S (Syllabus-to-Ship)

> Claude Code loads this file automatically at session start. It is the 60-second
> orientation. For current build status read `PROJECT_STATE.md`; for the full
> engineering design read `BUILD_PLAN.md`.

## What this project is

S2S turns a university syllabus into **live, real-world work**. A student uploads
their current-semester syllabus (any stream — Arts, Commerce, Science,
Engineering); S2S extracts the market-facing competencies behind each unit, then
uses **SerpApi** to find currently-open NGO briefs, freelance gigs, data
competitions, hackathons and open-source issues that those exact units qualify
them for — and explains the connection by quoting their own syllabus back to them.

Built for the **SerpApi India Hackathon 2026**. Repo:
`https://github.com/RakshamDessai/SerpApi-Hackathon`.

## Document map — read in this order

| File | What it is | When to read |
|---|---|---|
| `CLAUDE.md` | This file. Orientation + conventions. | Always, first. |
| `PROJECT_STATE.md` | **Living status.** What is built, what is next, file inventory, gotchas. | Always, second. |
| `BUILD_PLAN.md` | The engineering design: architecture, algorithms, credit math, scoring formulas, phase plan, acceptance criteria. ~690 lines. | Before writing any code. |
| `IMPLEMENTATION_PLAN.md` | The original product vision and 55-feature catalogue. Aspirational, not a build spec. | For product/pitch context. |
| `README.md` | User-facing. Rewritten in Phase 5. | Last. |

**If `BUILD_PLAN.md` and `IMPLEMENTATION_PLAN.md` disagree, `BUILD_PLAN.md` wins.**
Every deliberate deviation is listed in its Appendix A with a reason.

## The four ideas the whole build rests on

Understand these and the code layout is obvious. (Full detail: `BUILD_PLAN.md` §1.)

1. **`Competency` is the only thing the LLM touches.** Syllabus → `Competency[]`
   is the single AI boundary. Everything downstream — query planning, grounding,
   scoring, ranking — is deterministic, testable code. This is what gives one
   codebase for all academic streams, and what makes a no-LLM fallback possible.
2. **Platforms are declarative data, not code.** A `PlatformAdapter` dataclass
   holds domain, URL regex, engine, dork template, badge, trust tier, liveness
   strategy. Adding a platform = one registry entry.
3. **SerpApi credits are a budget to allocate.** Naive search is 102 calls per
   student click. Discipline-affinity platform selection + boolean OR-packing
   gets the same coverage in ~10. This is also the best hackathon story.
4. **Honesty about liveness is a feature.** Gated platforms (Upwork, Catchafire)
   produce dead links. Every card carries a verified verdict —
   `live` / `unverified` / `archived` — rather than an unverifiable claim.

## Pipeline stages

```
0 Ingest  → 1 Extract → 2 Plan → 3 Execute → 4 Ground → 5 Score → 6 Ship
  (text)    (LLM)       (pure)   (SerpApi)   (verify)   (pure)    (LLM)
```

Only stages 1 and 6 call an LLM, and **both have a working non-LLM path**.
Stages 2 and 5 are pure functions with no I/O — keep them that way, they are the
unit-tested core.

Package map: `ingest/ extract/ mesh/ ground/ score/ ship/ analyze/ ui/`.
Stages never import each other; `pipeline.py` is the only module that crosses
stage boundaries.

## Running it

```bash
cd "/Users/saisalelkar/Desktop/serp hack"
.venv/bin/python -m pytest -q          # tests
.venv/bin/streamlit run app.py         # the app
```

The venv is **Python 3.12** at `.venv/` (system Python is 3.14, which lacks wheels
for some pins). Always invoke `.venv/bin/python`, never bare `python3`.

## Hard-won gotchas — do not re-learn these

- **`requirements.txt` must stay UTF-8.** It arrived as UTF-16LE (from PowerShell
  `pip freeze >`), which makes `pip install -r` fail on line 1. The `Write` tool
  will *inherit* an existing file's encoding — if you rewrite it, `rm` it first
  and verify with `file requirements.txt` (must say "ASCII text").
- **Never install the `serpapi` PyPI package.** It collides with
  `google-search-results` on the `serpapi` module name but exposes a different
  API. Our code uses `from serpapi import GoogleSearch`, which only exists in
  `google-search-results`. Whichever pip resolves last silently wins.
- **`claude-opus-5` rejects `temperature` / `top_p` / `top_k`** with a 400. Steer
  with prompting. Thinking is on by default; `max_tokens` caps thinking *plus*
  output together.
- **`tbs=qdr:w` is not a reliable freshness filter** for `site:` dorks — it filters
  on Google's *index* date, not the posting date. Only `google_jobs`
  `chips=date_posted:*` is trustworthy. See `BUILD_PLAN.md` §6.1.
- **`Competency.source_span` must be a verbatim substring of the syllabus.**
  Validate it after every LLM call and drop any competency that fails. This is
  the guard against hallucinating claims about the student's own syllabus.
- **Quote validation is whitespace-insensitive on purpose** (`bridge._squash`).
  Reflowing a line break is not a paraphrase; an earlier raw-string comparison
  silently rejected every multi-line span. Invented content is still rejected.
- **`from s2s.ship import prepare`**, not `ship` — the package and the function
  would otherwise share a name.
- **Affinity is a share-weighted profile, not a max.** Taking the max let one
  stray secondary discipline award a platform full marks (Design → Kaggle).

## Code conventions

- Python 3.12, `from __future__ import annotations`, dataclasses over dicts.
- `s2s/` is import-clean: **nothing below `s2s/ui/` may import Streamlit.**
- Each stage owns its directory; cross-stage calls go through `s2s/pipeline.py`.
- Comments explain *why*, not *what*. Match surrounding density.
- No secrets in code. Keys come from `Settings.load()` only.

## Current status

Phases 0–4 are complete: 234 tests passing, app serving, full pipeline wired
including bridge, blueprint, proof-of-work export and the Syllabus Gap Report.

**The one blocker is that no SerpApi key has ever been used**, so no real query
has run and real-world result quality is unvalidated. Everything else is done.

See `PROJECT_STATE.md` for the file-by-file inventory, the 13 fixed bugs, and
exactly what is owned by whom. It is the authoritative answer to "where are we".
