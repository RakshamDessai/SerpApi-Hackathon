"""The Open-Mesh platform registry.

Every platform is one `PlatformAdapter` entry - declarative data, not code.
Adding a 18th platform is one dict entry plus an affinity column.

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

`tests/test_adapters.py` enforces that every marker is at least 12 characters,
because substring matching over a 600 KB page makes a short English phrase
("closed", "has expired") match unrelated text and archive live work.
"""

from __future__ import annotations

from s2s.models import PlatformAdapter

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
    engine="google",
    site="onlinevolunteering.org",
    url_pattern=r"^https?://(www\.)?onlinevolunteering\.org/(en|es|fr)/opportunity/",
    dork='site:onlinevolunteering.org/en/opportunity ({terms})',
    ecosystem="ngo_impact",
    compensation="volunteer",
    trust="A",
    liveness="http_probe",
    gate_markers=("no longer available", "this opportunity is closed",
                  "applications are closed"),
))

_register(PlatformAdapter(
    key="kaggle",
    label="Kaggle Competitions",
    engine="google",
    site="kaggle.com",
    url_pattern=r"^https?://(www\.)?kaggle\.com/competitions/[\w\-]+",
    dork='site:kaggle.com/competitions ({terms})',
    ecosystem="data_challenge",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    # A bare "closed" would match almost anything in a 600 KB page.
    gate_markers=("this competition has ended", "competition is closed"),
))

_register(PlatformAdapter(
    key="unstop",
    label="Unstop",
    engine="google",
    site="unstop.com",
    url_pattern=r"^https?://(www\.)?unstop\.com/(competitions?|hackathons?|"
                r"case-competitions?|o)/[\w\-]+",
    dork='site:unstop.com (competitions OR hackathons OR case-competitions) ({terms})',
    ecosystem="hackathon",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    gate_markers=("registration closed", "this opportunity has ended"),
))

_register(PlatformAdapter(
    key="devpost",
    label="Devpost",
    engine="google",
    site="devpost.com",
    url_pattern=r"^https?://[\w\-]+\.devpost\.com/?$|^https?://devpost\.com/(software|hackathons)/",
    dork='site:devpost.com ({terms}) hackathon',
    ecosystem="hackathon",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    gate_markers=("this hackathon has ended", "submissions are closed"),
))

_register(PlatformAdapter(
    key="devfolio",
    label="Devfolio",
    engine="google",
    site="devfolio.co",
    url_pattern=r"^https?://[\w\-]+\.devfolio\.co/?|^https?://(www\.)?devfolio\.co/(hackathons|projects)/",
    dork='site:devfolio.co ({terms})',
    ecosystem="hackathon",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    gate_markers=("applications closed", "hackathon ended"),
))

_register(PlatformAdapter(
    key="github",
    label="GitHub good-first-issues",
    engine="google",
    site="github.com",
    url_pattern=r"^https?://(www\.)?github\.com/[\w\-.]+/[\w\-.]+/issues/\d+",
    dork='site:github.com inurl:issues ("good first issue" OR "help wanted") ({terms})',
    ecosystem="open_source",
    compensation="bounty",
    trust="A",
    liveness="http_probe",
    # OBSERVED against real pages on 2026-10-09, not guessed. GitHub serves a
    # React shell, so the human-readable "this issue was closed" never appears
    # in the HTML; the state lives in an embedded JSON payload. Verified to be
    # absent on open issues, so it does not false-positive.
    gate_markers=('"state":"closed"',),
))

_register(PlatformAdapter(
    key="drivendata",
    label="DrivenData",
    engine="google",
    site="drivendata.org",
    url_pattern=r"^https?://(www\.)?drivendata\.org/competitions/\d+",
    dork='site:drivendata.org/competitions ({terms})',
    ecosystem="data_challenge",
    compensation="prize",
    trust="A",
    liveness="http_probe",
    gate_markers=("competition closed", "this competition is over"),
))

# ------------------------------------------------------------- tier B -------

_register(PlatformAdapter(
    key="catchafire",
    label="Catchafire",
    engine="google",
    site="catchafire.org",
    url_pattern=r"^https?://(www\.)?catchafire\.org/(opportunities?|projects?)/",
    dork='site:catchafire.org ({terms})',
    ecosystem="ngo_impact",
    compensation="volunteer",
    trust="B",
    liveness="http_probe",
    gate_markers=("sign in to view", "log in to view", "this project is no longer"),
))

_register(PlatformAdapter(
    key="taproot",
    label="Taproot Plus",
    engine="google",
    site="taprootplus.org",
    url_pattern=r"^https?://(www\.)?taprootplus\.org/",
    dork='site:taprootplus.org ({terms})',
    ecosystem="ngo_impact",
    compensation="volunteer",
    trust="B",
    liveness="http_probe",
    # "sign in" alone appears in the nav of most logged-out pages.
    gate_markers=("sign in to view", "no longer accepting"),
))

_register(PlatformAdapter(
    key="idealist",
    label="Idealist",
    engine="google",
    site="idealist.org",
    url_pattern=r"^https?://(www\.)?idealist\.org/(en|es)/(volop|job|internship)/",
    dork='site:idealist.org ({terms})',
    ecosystem="ngo_impact",
    compensation="volunteer",
    trust="B",
    liveness="http_probe",
    gate_markers=("this listing has expired", "no longer available"),
))

_register(PlatformAdapter(
    key="volunteermatch",
    label="VolunteerMatch",
    engine="google",
    site="volunteermatch.org",
    url_pattern=r"^https?://(www\.)?volunteermatch\.org/search/opp\d+",
    dork='site:volunteermatch.org ({terms})',
    ecosystem="ngo_impact",
    compensation="volunteer",
    trust="B",
    liveness="http_probe",
    gate_markers=("opportunity is no longer", "this opportunity has expired"),
))

_register(PlatformAdapter(
    key="zooniverse",
    label="Zooniverse",
    engine="google",
    site="zooniverse.org",
    url_pattern=r"^https?://(www\.)?zooniverse\.org/projects/[\w\-]+/[\w\-]+",
    dork='site:zooniverse.org/projects ({terms})',
    ecosystem="research",
    compensation="volunteer",
    trust="B",
    liveness="http_probe",
    gate_markers=("this project is finished", "project is complete"),
))

# ------------------------------------------------------------- tier C -------
# Off by default. These gate their detail pages and their Google index goes
# stale, which makes them the main source of dead links.

_register(PlatformAdapter(
    key="upwork",
    label="Upwork",
    engine="google",
    site="upwork.com",
    url_pattern=r"^https?://(www\.)?upwork\.com/(freelance-jobs|jobs)/",
    dork='site:upwork.com/freelance-jobs ({terms}) {negatives}',
    ecosystem="freelance",
    compensation="paid",
    trust="C",
    liveness="http_probe",
    gate_markers=("this job is no longer available", "log in to continue",
                  "create an account", "job is closed"),
    enabled_by_default=False,
))

_register(PlatformAdapter(
    key="freelancer",
    label="Freelancer",
    engine="google",
    site="freelancer.com",
    url_pattern=r"^https?://(www\.)?freelancer\.(com|in)/projects/",
    dork='site:freelancer.com/projects ({terms}) {negatives}',
    ecosystem="freelance",
    compensation="paid",
    trust="C",
    liveness="http_probe",
    gate_markers=("project has been closed", "bidding closed"),
    enabled_by_default=False,
))

_register(PlatformAdapter(
    key="contra",
    label="Contra",
    engine="google",
    site="contra.com",
    url_pattern=r"^https?://(www\.)?contra\.com/",
    dork='site:contra.com ({terms}) {negatives}',
    ecosystem="freelance",
    compensation="paid",
    trust="C",
    liveness="snippet_only",
    gate_markers=("no longer accepting",),
    enabled_by_default=False,
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
    dork='{terms} intern',
    ecosystem="internship",
    compensation="stipend",
    trust="B",
    liveness="snippet_only",
    gate_markers=("no longer accepting applications",),
    extra_params={"location": "India", "chips": "date_posted:week", "hl": "en", "gl": "in"},
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
        if adapter.trust == "C" and not include_tier_c:
            continue
        out.append(adapter)
    return out


def render_query(adapter: PlatformAdapter, phrases: list[str]) -> str:
    """Fill an adapter's dork template with an OR-group of quoted phrases.

    Google's relevance degrades past roughly six quoted alternatives inside a
    site: scope, so callers should keep groups small (see mesh/planner.py).
    """
    quoted = " OR ".join(f'"{p}"' for p in phrases if p.strip())
    query = adapter.dork.format(terms=quoted, negatives=NEGATIVES)
    return " ".join(query.split())
