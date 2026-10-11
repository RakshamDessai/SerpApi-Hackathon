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

It works the same way for a Design student (brand identity volunteer roles on
Idealist), a Sociology student (data-analysis projects on Catchafire), a CS
student (open hackathons on Devpost and Devfolio), and a Statistics student
(Kaggle competitions and Zooniverse citizen science) — **one engine, one
codebase, every stream**.

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
Each of the **15 registered platforms** is one `PlatformAdapter` entry holding its
domain, URL regex, SerpApi engine, query template, ecosystem badge, trust tier
and liveness strategy. Adding another is one registry entry.

**3. SerpApi credits are a budget to allocate.**
A naive search is every competency × every active platform — 44 to 55 calls per
click on the five presets, a fifth of a free tier's month. Discipline-affinity
platform selection plus competency grouping delivers it in **8–10 calls (77–85%
saved)**, and the UI shows the ledger for every run. Empty searches are billed
too, so they are counted and cached rather than silently retried.

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
.venv/bin/python check_serpapi.py     # verify the key and quota (free)

.venv/bin/streamlit run app.py
```

Open <http://localhost:8501>, pick a preset syllabus, and press
**Find me live work**.

### Keys

| Variable | Required | Without it |
|---|---|---|
| `SERPAPI_API_KEY` | Yes, for live search | Run in demo mode against recorded fixtures |
| `ANTHROPIC_API_KEY` | No | Extraction and the bridge fall back to the heuristic/template path |
| `GITHUB_TOKEN` | No | GitHub issue search and status checks use the lower anonymous limits |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | No | Kaggle cards stay **Unverified** |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | No | `scripts/daily_alert.py` prints instead of sending |

The heuristic path is **first class, not a stub**. A demo that hard-depends on
two external APIs has two single points of failure.

### Demo mode (0 credits)

Real SerpApi responses for all five presets — Commerce, Design, Engineering,
Social Sciences and Science — are committed in `fixtures/serpapi/` (45 searches,
recorded 2026-10-10). Set `S2S_DEMO_MODE=true` or flip the sidebar
toggle: the cache becomes read-only with no expiry, so the demo provably cannot
spend a credit.

The free liveness check still runs in demo mode — it is plain HTTP, not SerpApi —
so a competition that has closed since recording shows as **Archived**, not live.
With the conference wifi down it fails soft to **Unverified**.

```bash
# Re-record (about 45 credits; prints the cost first):
.venv/bin/python scripts/record_fixtures.py --dry-run
.venv/bin/python scripts/record_fixtures.py

# Verify url_pattern and the liveness check against live pages (no credits):
.venv/bin/python scripts/verify_adapters.py

# Time the five-preset demo, link checks included (no credits):
.venv/bin/python scripts/time_demo.py
```

Measured 2026-10-11 on a home connection: 62.6 s for all five presets
(10 s to 17 s each). Most of it is link checks waiting on slow hosts.

### Extra searches (each spends extra credits, off by default)

| Setting | Sidebar | What it does |
|---|---|---|
| `S2S_FRESH_QUERIES` | Prefer this year's events | Adds the current year to hackathon and competition searches, so the engines prefer this year's editions. |
| `S2S_FOLLOW_UP_PAGES` | Page 2 for strong platforms | Spends credits left under the cap on page 2 of the platforms whose page 1 verified mostly live. The offset comes from SerpApi's own `serpapi_pagination.next` link. |
| `S2S_EVENTS` | Events near me | `engine=google_events`: workshops, meetups and hackathons in your city. |
| `S2S_GAP_COURSES` | Free courses for syllabus gaps | `engine=youtube`: one free-course search per Gap Report entry. |
| `S2S_CITY` | Your city | Places Google Jobs and Google Events. |

None of these has recorded demo data yet, so in demo mode their searches show
as skipped. To record them, set them in `.env` and run
`scripts/record_fixtures.py` (it plans with the same settings as the app).

---

## The Open-Mesh platform registry

Platforms are graded by how reliably they return a **clickable, still-open** page.
This grading is deliberate: treating every platform as equally viable is how you
end up demoing 404s.

| Tier | Platforms | Behaviour |
|---|---|---|
| **A** | Kaggle, Unstop, Devpost, Devfolio, GitHub, DrivenData | Stable URLs, public detail pages. Build on these. |
| **B** | Catchafire, Idealist, Zooniverse | Indexed but partly gated. Included, labelled honestly. |
| **C** | Upwork, Freelancer, Contra | Login-gated and routinely stale. **Opt-in only.** |
| **D** | Google Jobs (India), Google Scholar, Google Events (opt-in) | A different SerpApi engine, not a `site:` query. |

Google Jobs cards link to the posting on its own board (Unstop, Internshala,
LinkedIn…), taken from `apply_options` and preferring the original board over
re-posting aggregators. Google's share link cannot be checked, so job cards used
to stay unverified; now 34 of 38 recorded jobs verify live. Indeed and Jooble
block automated checks, so their cards honestly stay **Unverified**.
| off | UN Online Volunteering | Registered but disabled: 0 results on 6 of 6 real searches. |

Removed after live checks: **VolunteerMatch** and **Taproot Plus** — both now
redirect to another site, so every result would be archived.

SerpApi engines used: `duckduckgo` for every `site:` platform (see below),
`google_jobs` with India-scoped `chips=date_posted:week`, `google_scholar`
with a publication-year floor, and, when switched on, `google_events` near the
student's city and `youtube` for free courses in the Gap Report.

**GitHub, free and direct.** For a CS syllabus, S2S also asks GitHub's own issue
search for `"<skill>" label:"good first issue","help wanted" state:open
no:assignee`. That costs no SerpApi credit, and every result is open when it is
fetched. These cards say **Platform API (direct, not SerpApi)**.

### What the first real SerpApi run taught us

The design originally sent every platform through `engine=google` with packed
boolean dorks like `site:devpost.com ("SQL query" OR "query optimisation")`.
Measured with a real key, that failed:

- **Google treated `site:` as a hint.** On 7 of 9 recorded CS searches, and on all
  8 platforms in a follow-up matrix, it dropped the restriction and returned
  Medium, Scribd and YouTube. Only 8 of 80 results were real listings.
  `google_light` and `as_sitesearch` behaved the same.
- **SerpApi's DuckDuckGo engine kept `site:` — 11 of 11 results on-site for 6 of 7
  platforms** — but only for short plain-keyword queries. Quoted OR-groups leaked
  or returned nothing.

So `site:` platforms now use `engine=duckduckgo` with one plain phrase plus the
platform's own wording (`site:unstop.com financial model competition`). Instead of
OR-packing, each search uses the phrase **shared by the most competencies in its
group**, and stage 5 recovers per-competency relevance. Real listings per CS run
went from 8 to 57.

---

## The Grounding Gate

Three tiers, cheapest first. Tiers 0 and 1 are free; tier 2 is a plain HTTP
request and costs **no SerpApi credit**.

| Tier | Check | Catches |
|---|---|---|
| 0 | URL shape vs the adapter's regex, checked against real URLs | Homepages, profiles, past project pages |
| 1 | Snippet markers, and a past edition year in the title (`"… – 2023"`) | Expired listings |
| 2 | HTTP probe + **post-redirect URL check**, or the platform's own status API | 404s, login walls, ended or paused projects |

Checking the URL *after* redirects catches the sign-in-wall case: HTTP 200, but
the final page is a login form.

The status API exists because of Unstop. Every Unstop listing serves the same
25 KB JavaScript shell, so a page probe can only prove the server answered. On
real data, **58 of 67** recorded Unstop competitions had already finished, and the
#1 CS card ("SQL Mania") had ended six months earlier. Unstop's public JSON
endpoint reports `reg_status: FINISHED`, so the gate asks it instead.

| Platform | Liveness source | Why |
|---|---|---|
| Unstop | public status API (`reg_status`, `end_regn_dt`) | Every page is the same JS shell |
| GitHub | REST API (`state`) | The page embeds linked PRs' states: an open issue with closed PRs read as closed |
| Catchafire | the details API its own page calls (`is_matching`) | Every page is the same 162 KB JS shell. All 12 recorded listings probed "live"; the API showed **9 of 12 were closed** (5 completed, 3 cancelled, 1 matched). |
| Zooniverse | public API (`state`, `launch_approved`) | Paused and never-launched projects look normal on the page |
| DrivenData | page text "Completed Sep 2026" | Precise once month and year are attached |
| Kaggle | **not probed** — snippet wording and title year only. With the student's own `KAGGLE_USERNAME` / `KAGGLE_KEY`, Kaggle's documented API gives the deadline. | Page is a JS shell; the web endpoint answers our checker with a CAPTCHA. We do not get round bot checks, so without a token Kaggle cards show **Unverified**. |

Plain-English "closed" phrases are matched against **visible text only**. BeBee
ships every error string in a script bundle on every job page, so a raw-page
match archived jobs posted that week. The link checker always identifies itself
as `S2S-LinkVerifier`, and the verification script uses the same identity, so it
can never pass a check the product would fail.

---

## Scoring

```
MatchScore = 0.45·semantic + 0.25·level + 0.15·freshness + 0.15·actionability
```

| Term | What it measures |
|---|---|
| **Semantic** | Whole market phrases in the title or snippet, plus smaller credit for distinctive single keywords ("SQL Mania", "Zero to Query"). Lexical by default — an embedding dependency would be a second demo failure mode. |
| **Level** | Distance between the student's band (Bloom level + semester) and the listing's pitch. |
| **Freshness** | Exponential decay on the posting date, with an explicit penalty for unknown dates rather than a silent zero. |
| **Actionability** | Verdict + platform trust tier + whether the brief names a concrete deliverable. |

Every card shows the arithmetic. A transparent score beats an opaque
"AI match: 87%", and it costs nothing.

Two rules sit on top of the score:

- **Out-of-reach listings are removed, not ranked low:** senior, C-suite or PhD
  titles, "5–15 years" experience, employer-facing recruiter ads, and non-English
  listings.
  All four appeared in the first real Google Jobs results.
- **Platform diversity:** no platform takes more than 3 of the top 10 while an
  alternative within 15 points exists. Otherwise 15 Google Scholar papers buried
  every real research role for a Sociology student, and verified job cards buried
  every (unverifiable) Kaggle competition for a Statistics student. Archived
  cards are never promoted.

---

## The Syllabus Gap Report

Inverts the question: **which parts of your syllabus matched nothing at all?**

> *Unit 5 — "Punch Card Batch Processing" matched no live market demand.
> In demand instead: `working capital`, `cash flow forecast`, `liquidity analysis`.*

Computed almost entirely from data the pipeline already produced. It turns S2S
from a matcher into evidence that a curriculum has drifted from the market.

If no search actually ran, the report says so rather than blaming the curriculum.

With `S2S_GAP_COURSES` on, each gap also lists free YouTube courses for the
skill that is in demand instead.

---

## Several subjects at once

Upload one file per subject. S2S reads them as one semester, keeps each unit
labelled with its subject, and shares the competency slots between subjects.
A listing that clearly uses units from **two different subjects** gets a
**Uses two subjects** badge and quotes both units. Both units must match the
listing well on their own; a strong match plus a weak one is not claimed.

---

## Apply, get credit, share

Every card has three more outputs. All are templates filled from data S2S
already holds, and all quote the same verbatim syllabus text as the bridge.

| Output | For | Notes |
|---|---|---|
| Application message | The organisation | Names the listing, the unit, one verbatim syllabus line, the tools and a first step. |
| Faculty credit report (PDF) | Your professor | One page to ask for internal practical marks: the work, the unit text, how the listing was checked, and a signature block. Fields only the student knows are marked as written by the student. |
| LinkedIn post | Your network | Past tense, for after the work is delivered. |

### Daily alert

```bash
.venv/bin/python scripts/daily_alert.py my_syllabus.pdf --semester 4 --dry-run
```

Runs the pipeline and sends only **new live** listings, to Telegram when
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are set. One run costs what one
click costs (8 to 10 searches). On the free plan, use `--every 2` or more.

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
├── ship/              # bridge, blueprint, STAR bullet, case study,
│                      # application message, LinkedIn post, faculty PDF
├── analyze/           # gap report, daily-alert diff
└── ui/                # card rendering (the only Streamlit importer)
```

`s2s/` never imports Streamlit, so the same pipeline can be driven from a CLI or
an API without change.

---

## Tests

```bash
.venv/bin/python -m pytest        # 433 passed, 6 skipped
```

Covering registry integrity, the budget cap as a safety property, every scoring
term, gate tiers 0–2, dedupe, PDF/DOCX/UTF-16 ingestion, verbatim-span validation,
the gap report, a full pipeline acceptance run, and URL rules checked against
real listings. Tests never read your `.env` and never spend a credit.

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
