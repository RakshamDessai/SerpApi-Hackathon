# S2S — Syllabus to Ship

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Powered by SerpApi](https://img.shields.io/badge/Powered%20by-SerpApi-orange.svg)](https://serpapi.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> Turn the syllabus you are studying **this semester** into live, currently-open,
> real-world work — in any stream, not just computer science.

A student uploads their syllabus. S2S extracts the market-facing competency
behind each unit, searches live opportunity platforms through **SerpApi**, verifies
every link is actually open, scores the matches, and then explains the connection
by **quoting the student's own syllabus back to them**.

Built for the SerpApi India Hackathon 2026.

---

## The problem

A third-semester B.Com student can derive a cash conversion cycle. She has never
seen a real balance sheet. Meanwhile a community health clinic is, right now,
looking for a volunteer to build a 12-month cash flow forecast.

Those two facts never meet. S2S is the bridge.

It works the same way for a Design student (brand identity briefs on Catchafire),
a Sociology student (survey design for UN Volunteers), and a CS student (good
first issues on GitHub) — **one engine, one codebase, every stream**.

---

## How it works

```
0 Ingest  →  1 Extract  →  2 Plan  →  3 Execute  →  4 Ground  →  5 Score  →  6 Ship
  PDF/DOCX    LLM or       pure      SerpApi       verify       pure        bridge +
  /paste      heuristic    function  + cache       links        function    blueprint
```

Only stages 1 and 6 touch an LLM. Stages 2 and 5 are pure functions with no I/O —
they are the unit-tested core.

### Four ideas the build rests on

**1. `Competency` is the only thing the LLM touches.**
Syllabus → `Competency[]` is the single AI boundary. Query planning, grounding,
scoring and ranking are all deterministic code below it. That is what gives one
codebase for every academic stream — and what makes a no-LLM fallback possible.

**2. Platforms are declarative data, not code.**
Each of the **16 platforms** is one `PlatformAdapter` entry holding its domain,
URL regex, SerpApi engine, dork template, ecosystem badge, trust tier and
liveness strategy. Adding an eighteenth is one registry entry.

**3. SerpApi credits are a budget to allocate.**
A naive search is 6 competencies × 17 platforms = **102 calls per click** — one
run per month on a free tier. Discipline-affinity platform selection plus boolean
OR-packing delivers the same coverage in **~10 calls (82–86% saved)**, and the UI
shows the ledger for every run.

**4. Honesty about liveness is a feature.**
Gated platforms produce dead links. Every card carries a verified verdict —
`Verified live` / `Unverified` / `Archived` — instead of an unverifiable claim.

---

## Quick start

```bash
git clone https://github.com/RakshamDessai/SerpApi-Hackathon.git
cd SerpApi-Hackathon

python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp .env.example .env          # then add your SerpApi key
.venv/bin/python check_serpapi.py     # verify connectivity

.venv/bin/streamlit run app.py
```

Open <http://localhost:8501>, pick a preset syllabus, and press
**Find me live work**.

### Keys

| Variable | Required | Without it |
|---|---|---|
| `SERPAPI_API_KEY` | Yes, for live search | Run in demo mode against recorded fixtures |
| `ANTHROPIC_API_KEY` | No | Extraction and the bridge fall back to the heuristic/template path |

The heuristic path is **first class, not a stub**. A demo that hard-depends on
two external APIs has two single points of failure.

### Demo mode (0 credits, no network)

```bash
# With a key - real SerpApi responses, ~40 credits:
.venv/bin/python scripts/record_fixtures.py --dry-run   # shows the cost first
.venv/bin/python scripts/record_fixtures.py

# Without a key - real listings harvested from the platforms' own public
# endpoints. Clearly labelled in the UI as "not SerpApi". Covers the CS preset.
.venv/bin/python scripts/harvest_demo_fixtures.py

# Verify url_pattern and gate_markers against live pages (no credits):
.venv/bin/python scripts/verify_adapters.py
```

Then set `S2S_DEMO_MODE=true`. The cache becomes read-only with no expiry, so the
demo provably cannot spend a credit — and works with the conference wifi down.

---

## The Open-Mesh platform registry

Platforms are graded by how reliably they return a **clickable, still-open** page.
This grading is deliberate: treating every platform as equally viable is how you
end up demoing 404s.

| Tier | Platforms | Behaviour |
|---|---|---|
| **A** | UN Online Volunteering, Kaggle, Unstop, Devpost, Devfolio, GitHub, DrivenData | Stable URLs, public detail pages. Build on these. |
| **B** | Catchafire, Taproot Plus, Idealist, VolunteerMatch, Zooniverse | Indexed but partly gated. Included, labelled honestly. |
| **C** | Upwork, Freelancer, Contra | Login-gated and routinely stale. **Opt-in only.** |
| **D** | Google Jobs (India), Google Scholar | A different SerpApi engine, not a `site:` dork. |

Tier D is also the engine-breadth exhibit: `engine=google_jobs` with India-scoped
`chips=date_posted:week` freshness, and `engine=google_scholar` with a publication
year floor, alongside advanced boolean `site:` dorking.

---

## The Grounding Gate

Three tiers, cheapest first. Tiers 0 and 1 are free; tier 2 is a plain HTTP
request and costs **no SerpApi credit**.

| Tier | Check | Catches |
|---|---|---|
| 0 | URL shape vs the adapter's regex | Homepages, category pages, blog posts |
| 1 | Snippet markers (`"this competition has ended"`) | Expired listings |
| 2 | HTTP probe + **post-redirect URL check** | 404s and login walls |

Checking the URL *after* redirects is what catches the Upwork and Catchafire
sign-in-wall case: HTTP 200, but the final page is a login form.

---

## Scoring

```
MatchScore = 0.45·semantic + 0.25·level + 0.15·freshness + 0.15·actionability
```

| Term | What it measures |
|---|---|
| **Semantic** | Overlap between the competency's market aliases and the brief. Lexical by default — an embedding dependency would be a second demo failure mode. |
| **Level** | Distance between the student's band (Bloom level + semester) and the listing's pitch. |
| **Freshness** | Exponential decay on the posting date, with an explicit penalty for unknown dates rather than a silent zero. |
| **Actionability** | Verdict + platform trust tier + whether the brief names a concrete deliverable. |

Every card shows the arithmetic. A transparent score beats an opaque
"AI match: 87%", and it costs nothing.

---

## The Syllabus Gap Report

Inverts the question: **which parts of your syllabus matched nothing at all?**

> *Unit 5 — "Punch Card Batch Processing" matched no live market demand.
> In demand instead: `working capital`, `cash flow forecast`, `liquidity analysis`.*

Computed almost entirely from data the pipeline already produced. It turns S2S
from a matcher into evidence that a curriculum has drifted from the market.

If no search actually ran, the report says so rather than blaming the curriculum.

---

## Project layout

```
s2s/
├── models.py          # stage contracts
├── config.py          # per-run Settings
├── pipeline.py        # orchestrates stages 0-5
├── ingest/            # PDF / DOCX / TXT -> curriculum tree
├── extract/           # taxonomy, Claude path, heuristic fallback
├── mesh/              # adapters, affinity, planner, cache, ledger, SerpApi
├── ground/            # liveness gate, dedupe
├── score/             # the four weighted terms, derived signals
├── ship/              # bridge, blueprint, STAR bullet, case study
├── analyze/           # gap report
└── ui/                # card rendering (the only Streamlit importer)
```

`s2s/` never imports Streamlit, so the same pipeline can be driven from a CLI or
an API without change.

---

## Tests

```bash
.venv/bin/python -m pytest        # 279 passed, 2 skipped
```

Covering registry integrity, the budget cap as a safety property, every scoring
term, gate tiers 0–1, dedupe, PDF/DOCX/UTF-16 ingestion, verbatim-span validation,
the gap report, and a full pipeline acceptance run.

---

## Documentation

| File | What it is |
|---|---|
| `CLAUDE.md` | Orientation for a fresh contributor or agent session |
| `PROJECT_STATE.md` | Living build status: what is done, what is next, decisions, gotchas |
| `BUILD_PLAN.md` | The engineering design: architecture, algorithms, credit math, phases |
| `IMPLEMENTATION_PLAN.md` | The original product vision and 55-feature catalogue |

---

## License

MIT — see [LICENSE](LICENSE).
