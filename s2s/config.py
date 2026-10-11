"""Runtime settings.

Replaces the previous module-level constants, which froze environment values at
first import. Under Streamlit's rerun model that meant a key typed into the
sidebar never reached the client, and a .env created after launch stayed
invisible until restart. `Settings.load()` is called per run instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"
CACHE_DIR = ROOT_DIR / ".cache" / "serpapi"
FIXTURE_DIR = ROOT_DIR / "fixtures"

#: The one identity every S2S checker uses: the link checker, the GitHub
#: search and the scripts. A script that posed as a browser could pass a check
#: the product fails.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 S2S-LinkVerifier/0.1"
)

PLACEHOLDERS = {
    "",
    "your_serpapi_api_key_here",
    "your_anthropic_api_key_here",
    "your_gemini_api_key_here",
    "your_openai_api_key_here",
}


def _clean(value: str | None) -> str | None:
    """Treat .env.example placeholders as 'not set'."""
    if value is None:
        return None
    value = value.strip()
    return None if value.lower() in PLACEHOLDERS else value


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class Settings:
    """One resolved configuration for one pipeline run."""

    serpapi_key: str | None = None
    anthropic_key: str | None = None

    demo_mode: bool = False
    credit_cap: int = 12
    max_platforms: int = 5
    terms_per_dork: int = 3
    max_competencies: int = 6
    cache_ttl_hours: int = 72
    results_per_search: int = 10

    # Grounding gate. Probes are plain HTTP and cost no SerpApi credit, so they
    # run in demo mode too - offline they fail soft to "unverified". The gate
    # probes in search order, not rank order, so N must cover most survivors.
    probe_top_n: int = 40
    probe_timeout_s: float = 4.0

    # Tier C (Upwork / Freelancer / Contra) is opt-in: those platforms gate
    # their detail pages and their Google index goes stale, so they are the
    # main source of dead links. See BUILD_PLAN.md section 6.
    include_tier_c: bool = False

    # -- features that spend extra SerpApi credits: OFF by default --------
    # Each one changes or adds searches, so it has no recorded demo fixture
    # until scripts/record_fixtures.py runs again with it on.

    #: Add the current year to site: keyword dorks, so search engines prefer
    #: this year's editions over the 58-of-67 finished events they index.
    fresh_queries: bool = False
    #: Spend credits left under the cap on page 2 of the platforms whose page 1
    #: verified mostly live.
    follow_up_pages: bool = False
    #: Search Google Events (engine=google_events) near `city`.
    events: bool = False
    #: How many Syllabus Gap Report entries get a YouTube course search (one
    #: credit each).
    gap_courses: int = 0
    #: City for Google Jobs and Google Events, e.g. "Pune". None = all India.
    city: str | None = None

    # -- free sources (no SerpApi credit) ---------------------------------

    #: Ask GitHub's issue search API for open good-first-issues. Free, and
    #: every result is open at fetch time.
    direct_github: bool = True
    github_token: str | None = None
    #: Kaggle's API needs the student's own token. Without one, Kaggle cards
    #: stay unverified: we never get round its CAPTCHA.
    kaggle_username: str | None = None
    kaggle_key: str | None = None

    cache_dir: Path = field(default_factory=lambda: CACHE_DIR)

    @classmethod
    def load(cls, serpapi_override: str | None = None) -> "Settings":
        if ENV_PATH.exists():
            load_dotenv(dotenv_path=ENV_PATH, override=False)
        else:
            load_dotenv(override=False)

        return cls(
            serpapi_key=_clean(serpapi_override) or _clean(os.getenv("SERPAPI_API_KEY")),
            anthropic_key=_clean(os.getenv("ANTHROPIC_API_KEY")),
            demo_mode=_env_bool("S2S_DEMO_MODE", False),
            credit_cap=_env_int("S2S_CREDIT_CAP", 12),
            max_platforms=_env_int("S2S_MAX_PLATFORMS", 5),
            terms_per_dork=_env_int("S2S_TERMS_PER_DORK", 3),
            max_competencies=_env_int("S2S_MAX_COMPETENCIES", 6),
            cache_ttl_hours=_env_int("S2S_CACHE_TTL_HOURS", 72),
            include_tier_c=_env_bool("S2S_INCLUDE_TIER_C", False),
            probe_top_n=_env_int("S2S_PROBE_TOP_N", 40),
            fresh_queries=_env_bool("S2S_FRESH_QUERIES", False),
            follow_up_pages=_env_bool("S2S_FOLLOW_UP_PAGES", False),
            events=_env_bool("S2S_EVENTS", False),
            gap_courses=_env_int("S2S_GAP_COURSES", 0),
            city=_clean(os.getenv("S2S_CITY")),
            direct_github=_env_bool("S2S_DIRECT_GITHUB", True),
            github_token=_clean(os.getenv("GITHUB_TOKEN")),
            kaggle_username=_clean(os.getenv("KAGGLE_USERNAME")),
            kaggle_key=_clean(os.getenv("KAGGLE_KEY")),
        )

    # -- capability flags used by the UI ----------------------------------

    @property
    def has_serpapi(self) -> bool:
        return bool(self.serpapi_key)

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_key)

    @property
    def has_kaggle(self) -> bool:
        return bool(self.kaggle_username and self.kaggle_key)

    @property
    def extraction_mode(self) -> str:
        return "Claude (claude-opus-5)" if self.has_llm else "Heuristic (no LLM key)"

    @property
    def search_mode(self) -> str:
        if self.demo_mode:
            return "DEMO (cached responses, 0 credits)"
        return "LIVE" if self.has_serpapi else "UNAVAILABLE (no SerpApi key)"
