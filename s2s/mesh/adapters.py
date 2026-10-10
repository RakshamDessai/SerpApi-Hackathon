"""The Open-Mesh platform registry.

Every platform is one `PlatformAdapter` entry - declarative data, not code.
Adding a platform is one dict entry plus an affinity column.

Tiers (BUILD_PLAN.md section 6) are a correction to the original vision doc,
which treated every platform as equally viable:

  A  stable URLs, public detail pages, well indexed      -> build on these
  B  indexed but partly gated; expect some stale results -> include, label honestly
  C  login-gated and routinely stale                     -> opt-in only
  D  a different SerpApi engine, not a site: dork        -> the engine-breadth exhibit

`url_pattern` doubles as Grounding Gate tier 0: a `site:upwork.com/freelance-jobs`
dork happily returns the Upwork homepage, category pages and blog posts, and this
regex is the cheapest, highest-yield filter in the whole system.

VERIFICATION STATUS of `gate_markers` (tier 2):

  github, kaggle   OBSERVED against real live pages on 2026-10-09, including a
                   negative check that the marker is absent when the listing is
                   open, so it cannot false-positive.
  all others       PLAUSIBLE BUT UNVERIFIED. They are reasonable guesses at the
                   wording each site uses and have never been checked against a
                   real page. A wrong marker fails safe in one direction only:
                   a missed marker shows a closed listing as live. Re-check
                   these once a SerpApi key produces real URLs to probe.

ENGINE ROUTING - MEASURED with a real key on 2026-10-10, not assumed:

  Google (engine=google) treats `site:` as a soft hint. On 7 of 9 recorded CS
  searches, and on every one of 8 platforms in a follow-up matrix, it dropped
  the restriction and back-filled with Medium, Scribd and YouTube - signature:
  `total_results` collapses to ~50. google_light and `as_sitesearch` behaved
  the same. Tier 0 caught all of it, but every such call is a wasted credit.

  DuckDuckGo via SerpApi honoured `site:` on 6 of 7 platforms (11/11 results
  on-site) - but only for short, unquoted keyword queries. Quoted OR-groups
  either returned nothing or leaked too. So site: adapters use
  engine="duckduckgo" with query_style="keywords": one plain phrase plus the
  platform's own vocabulary ("competition", "needs help with"). Relevance
  across the rest of the competency group is recovered in stage 5 scoring.

`tests/test_adapters.py` enforces that every marker is at least 12 characters,
because substring matching over a 600 KB page makes a short English phrase
("closed", "has expired") match unrelated text and archive live work.
"""

from __future__ import annotations

from s2s.models import PlatformAdapter, StatusApi

# Keeps students out of listings they cannot win. Applied to Tier B/C boards.
NEGATIVES = "-senior -lead -director -principal -\"5+ years\" -phd"

ADAPTERS: dict[str, PlatformAdapter] = {}


def _register(adapter: PlatformAdapter) -> PlatformAdapter:
    if adapter.key in ADAPTERS:
        raise ValueError(f"duplicate adapter key: {adapter.key}")
    ADAPTERS[adapter.key] = adapter
    return adapter


# ------------------------------------------------------------- tier A -------

_register(PlatformAdapter(
    key="unv",
    label="UN Online Volunteering",
    engine="duckduckgo",
    site="onlinevolunteering.org",
    url_pattern=r"^https?://(www\.)?onlinevolunteering\.org/(en|es|fr)/opportunity/",
    dork="site:onlinevolunteering.org opportunity {terms}",
    ecosystem="ngo_impact",
    compensation="volunteer",
    trust="A",
    liveness="http_probe",
    gate_markers=("no longer available", "this opportunity is closed",
                  "applications are closed"),
    query_style="keywords",
    # OFF since 2026-10-10: DuckDuckGo returned nothing on 6 of 6 real
    # searches and Google ignored the site: scope. The site sits behind an
    # Imperva WAF, so search engines barely index it - and SerpApi still
    # bills an empty search. Kept registered so it is one flag to re-enable.
    enabled_by_default=False,
))

_register(PlatformAdapter(
    key="kaggle",
    label="Kaggle Competitions",
    engine="duckduckgo",
    site="kaggle.com",
    url_pattern=r"^https?://(www\.)?kaggle\.com/competitions/[\w\-]+",
    dork="site:kaggle.com competitions {terms}",
    ecosystem="data_challenge",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    # A bare "closed" would match almost anything in a 600 KB page.
    gate_markers=("this competition has ended", "competition is closed"),
    query_style="keywords",
))

_register(PlatformAdapter(
    key="unstop",
    label="Unstop",
    engine="duckduckgo",
    site="unstop.com",
    # api.unstop.com serves the same listing pages and is indexed alongside
    # the main host (observed 2026-10-10, HTTP 200).
    url_pattern=r"^https?://(www\.|api\.)?unstop\.com/(competitions?|hackathons?|"
                r"case-competitions?|o)/[\w\-]+",
    dork="site:unstop.com {terms} competition",
    ecosystem="hackathon",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    gate_markers=("registration closed", "this opportunity has ended"),
    query_style="keywords",
    # OBSERVED 2026-10-10: every listing page is the same 25 KB JS shell, so
    # page markers can never fire. The public JSON endpoint reports
    # reg_status FINISHED for ended events - including the #1 CS card.
    status_api=StatusApi(
        url="https://unstop.com/api/public/competition/{id}",
        id_re=r"[/-](\d{5,})(?:/register)?/?$",
        path=("data", "competition", "regnRequirements", "reg_status"),
        dead=("FINISHED", "CLOSED", "EXPIRED", "ENDED"),
        # A listing can still say STARTED hours after registration shut.
        deadline=("data", "competition", "regnRequirements", "end_regn_dt"),
    ),
))

_register(PlatformAdapter(
    key="devpost",
    label="Devpost",
    engine="duckduckgo",
    site="devpost.com",
    # Each hackathon is its own subdomain. devpost.com/software/* pages are
    # past project submissions - someone else's finished work, not an open
    # brief - and were 2 of the first 11 real results (2026-10-10).
    url_pattern=r"^https?://(?!www\.|info\.|help\.)[\w\-]+\.devpost\.com/?$",
    dork="site:devpost.com {terms} hackathon",
    ecosystem="hackathon",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    gate_markers=("this hackathon has ended", "submissions are closed"),
    query_style="keywords",
))

_register(PlatformAdapter(
    key="devfolio",
    label="Devfolio",
    engine="duckduckgo",
    site="devfolio.co",
    # Each hackathon is its own subdomain (innohacks-4.devfolio.co). Paths on
    # the bare host are index pages (/hackathons/past) or past projects.
    url_pattern=r"^https?://(?!www\.)[\w\-]+\.devfolio\.co/?$",
    dork="site:devfolio.co {terms} hackathon",
    ecosystem="hackathon",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    gate_markers=("applications closed", "hackathon ended"),
    query_style="keywords",
))

_register(PlatformAdapter(
    key="github",
    label="GitHub good-first-issues",
    engine="duckduckgo",
    site="github.com",
    url_pattern=r"^https?://(www\.)?github\.com/[\w\-.]+/[\w\-.]+/issues/\d+",
    dork='site:github.com "good first issue" {terms}',
    ecosystem="open_source",
    compensation="bounty",
    trust="A",
    liveness="http_probe",
    # OBSERVED against real pages on 2026-10-09, not guessed. GitHub serves a
    # React shell, so the human-readable "this issue was closed" never appears
    # in the HTML; the state lives in an embedded JSON payload. Verified to be
    # absent on open issues, so it does not false-positive.
    gate_markers=('"state":"closed"',),
    query_style="keywords",
))

_register(PlatformAdapter(
    key="drivendata",
    label="DrivenData",
    engine="duckduckgo",
    site="drivendata.org",
    url_pattern=r"^https?://(www\.)?drivendata\.org/competitions/\d+",
    dork="site:drivendata.org competitions {terms}",
    ecosystem="data_challenge",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    gate_markers=("competition closed", "this competition is over"),
    query_style="keywords",
))

# ------------------------------------------------------------- tier B -------

_register(PlatformAdapter(
    key="catchafire",
    label="Catchafire",
    engine="duckduckgo",
    site="catchafire.org",
    # OBSERVED 2026-10-10: listings live at /volunteer/<id>/<slug>/ and are
    # titled "<Org> needs help with ...". The earlier /opportunities/ pattern
    # was a guess and rejected every real listing; /profiles/ pages are people.
    url_pattern=r"^https?://(www\.)?catchafire\.org/volunteer/\d+/",
    dork='site:catchafire.org "needs help with" {terms}',
    ecosystem="ngo_impact",
    compensation="volunteer",
    trust="B",
    liveness="http_probe",
    gate_markers=("sign in to view", "log in to view", "this project is no longer"),
    query_style="keywords",
))

# Taproot Plus was REMOVED on 2026-10-10 after live verification, for the same
# reason as VolunteerMatch below: taprootplus.org and its /projects/ pages now
# redirect to taprootfoundation.org, so tier 2 archives every result. Its
# url_pattern had also accepted any page on the host (signup, newsletter).

_register(PlatformAdapter(
    key="idealist",
    label="Idealist",
    engine="duckduckgo",
    site="idealist.org",
    # OBSERVED 2026-10-10: /en/volunteer-opportunity/<hex>-<slug>. The earlier
    # /volop/ pattern was a guess and rejected every real listing.
    url_pattern=r"^https?://(www\.)?idealist\.org/(en|es)/"
                r"(volunteer-opportunity|nonprofit-job|nonprofit-internship|volop|job|internship)/",
    dork="site:idealist.org volunteer opportunity {terms}",
    ecosystem="ngo_impact",
    compensation="volunteer",
    trust="B",
    liveness="http_probe",
    gate_markers=("this listing has expired", "no longer available"),
    query_style="keywords",
))

# VolunteerMatch was REMOVED on 2026-10-09 after live verification.
# volunteermatch.org now 302s to idealist.org/volunteermatch - including deep
# /search/oppNNNN.jsp links - so the site no longer serves opportunity pages at
# all. Tier 0 still ACCEPTED those Google-indexed URLs (spending a credit), but
# tier 2 then rejected every one as `archived` because the post-redirect host
# no longer matches url_pattern. The adapter was therefore guaranteed to burn a
# search and return nothing. Idealist, which absorbed it, is already in the
# registry and covers the same ecosystem.

_register(PlatformAdapter(
    key="zooniverse",
    label="Zooniverse",
    engine="duckduckgo",
    site="zooniverse.org",
    url_pattern=r"^https?://(www\.)?zooniverse\.org/projects/[\w\-]+/[\w\-]+",
    dork="site:zooniverse.org projects {terms}",
    ecosystem="research",
    compensation="volunteer",
    trust="B",
    liveness="http_probe",
    gate_markers=("this project is finished", "project is complete"),
    query_style="keywords",
))

# ------------------------------------------------------------- tier C -------
# Off by default. These gate their detail pages and their Google index goes
# stale, which makes them the main source of dead links.

_register(PlatformAdapter(
    key="upwork",
    label="Upwork",
    engine="duckduckgo",
    site="upwork.com",
    url_pattern=r"^https?://(www\.)?upwork\.com/(freelance-jobs|jobs)/",
    dork="site:upwork.com freelance jobs {terms} {negatives}",
    ecosystem="freelance",
    compensation="paid",
    trust="C",
    liveness="http_probe",
    gate_markers=("this job is no longer available", "log in to continue",
                  "create an account", "job is closed"),
    enabled_by_default=False,
    query_style="keywords",
))

_register(PlatformAdapter(
    key="freelancer",
    label="Freelancer",
    engine="duckduckgo",
    site="freelancer.com",
    url_pattern=r"^https?://(www\.)?freelancer\.(com|in)/projects/",
    dork="site:freelancer.com projects {terms} {negatives}",
    ecosystem="freelance",
    compensation="paid",
    trust="C",
    liveness="http_probe",
    gate_markers=("project has been closed", "bidding closed"),
    enabled_by_default=False,
    query_style="keywords",
))

_register(PlatformAdapter(
    key="contra",
    label="Contra",
    engine="duckduckgo",
    site="contra.com",
    url_pattern=r"^https?://(www\.)?contra\.com/",
    dork="site:contra.com {terms} {negatives}",
    ecosystem="freelance",
    compensation="paid",
    trust="C",
    liveness="snippet_only",
    gate_markers=("no longer accepting",),
    enabled_by_default=False,
    query_style="keywords",
))

# ------------------------------------------------------------- tier D -------
# Different SerpApi engines. These are the "we know this API" exhibit: India-
# scoped job freshness chips and a Scholar year floor alongside boolean dorking.

_register(PlatformAdapter(
    key="gjobs",
    label="Google Jobs (India internships)",
    engine="google_jobs",
    site=None,
    url_pattern=r"^https?://",          # aggregated; the share link varies by source
    dork="{terms} intern",
    ecosystem="internship",
    compensation="stipend",
    trust="B",
    liveness="snippet_only",
    gate_markers=("no longer accepting applications",),
    extra_params={"location": "India", "chips": "date_posted:week", "hl": "en", "gl": "in"},
    # Recorded 2026-10-10: OR-grouped phrases returned 1 and 0 jobs.
    query_style="keywords",
))

_register(PlatformAdapter(
    key="scholar",
    label="Google Scholar (open research questions)",
    engine="google_scholar",
    site=None,
    url_pattern=r"^https?://",
    dork='{terms}',
    ecosystem="research",
    compensation="credit_only",
    trust="B",
    liveness="snippet_only",
    extra_params={"as_ylo": 2025, "hl": "en"},
))


# ------------------------------------------------------------- helpers ------

def all_adapters() -> list[PlatformAdapter]:
    return list(ADAPTERS.values())


def get(key: str) -> PlatformAdapter:
    return ADAPTERS[key]


def active(include_tier_c: bool = False, only: set[str] | None = None) -> list[PlatformAdapter]:
    """Adapters eligible for this run."""
    out = []
    for adapter in ADAPTERS.values():
        if only is not None and adapter.key not in only:
            continue
        if adapter.trust == "C":
            if not include_tier_c:
                continue
        elif not adapter.enabled_by_default:
            continue
        out.append(adapter)
    return out


def render_query(adapter: PlatformAdapter, phrases: list[str]) -> str:
    """Fill an adapter's dork template from the group's phrases, strongest first.

    `or_group` packs every phrase into one quoted OR-group. `keywords` uses
    only the strongest phrase, unquoted: that is the only shape DuckDuckGo
    kept inside a site: scope when measured (see the module docstring).
    """
    phrases = [p.strip() for p in phrases if p.strip()]
    if adapter.query_style == "keywords":
        terms = phrases[0] if phrases else ""
    else:
        terms = " OR ".join(f'"{p}"' for p in phrases)
    query = adapter.dork.format(terms=terms, negatives=NEGATIVES)
    return " ".join(query.split())
