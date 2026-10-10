"""Academic-to-market translation tables.

Two consumers:

* `heuristic.py` uses these directly to build `Competency` objects without any
  LLM, so the demo survives a missing or rate-limited Anthropic key.
* `llm.py` ships a condensed form of `MARKET_ALIASES` in its (cached) system
  prompt as a worked example of the translation we want.

The alias table is the single most valuable asset in the extract stage. Academic
phrasing ("Capital Asset Pricing Model") never appears in a gig listing; market
phrasing ("cost of equity", "equity risk modelling") does. Dork quality is
bounded by the quality of these aliases.
"""

from __future__ import annotations

import re

from s2s.models import Band, Discipline

# ------------------------------------------------------- discipline signals ---
# Lowercase keyword -> disciplines it implies. Matched as whole words against
# the unit text. Order within a set is irrelevant.

DISCIPLINE_KEYWORDS: dict[Discipline, set[str]] = {
    Discipline.COMMERCE_FINANCE: {
        "accounting", "accountancy", "audit", "auditing", "balance sheet",
        "capital budgeting", "cash flow", "cost of capital", "dividend",
        "finance", "financial", "gst", "income tax", "ledger", "leverage",
        "npv", "irr", "payback", "profit", "ratio analysis", "revenue",
        "taxation", "valuation", "wacc", "working capital", "capm",
        "depreciation", "amortisation", "bookkeeping", "costing",
    },
    Discipline.ARTS_HUMANITIES: {
        "anthropology", "critical theory", "culture", "discourse",
        "ethnography", "gender", "history", "literature", "philosophy",
        "political science", "psychology", "qualitative", "social",
        "sociology", "survey", "interview", "thematic analysis", "fieldwork",
        "questionnaire", "sampling", "ethics", "policy brief", "caste",
    },
    Discipline.DESIGN_VISUAL: {
        "brand", "branding", "colour theory", "color theory", "composition",
        "design", "figma", "grid", "hierarchy", "identity", "illustration",
        "layout", "logo", "poster", "sketch", "typeface", "typography",
        "visual", "wireframe", "mockup", "palette", "gestalt", "editorial",
    },
    Discipline.CS_SOFTWARE: {
        "algorithm", "api", "b-tree", "compiler", "concurrency", "database",
        "data structure", "dbms", "debugging", "deadlock", "indexing",
        "java", "javascript", "normalisation", "normalization", "operating system",
        "programming", "python", "query", "relational", "software", "sql",
        "transaction", "schema", "backend", "frontend", "git", "testing",
        "serialisability", "acid", "index",
    },
    Discipline.DATA_QUANT: {
        "analytics", "bayesian", "chi-square", "classification", "clustering",
        "correlation", "dataset", "descriptive statistics", "econometrics",
        "forecasting", "hypothesis", "inference", "machine learning",
        "probability", "regression", "sampling", "statistics", "time series",
        "visualisation", "visualization", "numpy", "pandas", "distribution",
    },
    Discipline.LIFE_SCIENCES: {
        "anatomy", "bioinformatics", "biology", "biotechnology", "cell",
        "clinical", "dna", "ecology", "enzyme", "epidemiology", "fasta",
        "genetics", "genome", "microbiology", "molecular", "pathology",
        "pharmacology", "physiology", "protein", "sequence alignment", "rna",
    },
    Discipline.LAW_POLICY: {
        "arbitration", "constitution", "contract", "copyright",
        "criminal law", "governance", "indemnity", "intellectual property",
        "jurisprudence", "legal", "legislation", "licensing", "litigation",
        "public policy", "policy brief", "privacy", "statute", "tort",
        "compliance", "regulation", "legal research",
    },
    Discipline.MEDIA_COMM: {
        "advertising", "broadcast", "communication", "content writing",
        "copywriting", "editing", "journalism", "mass communication", "media",
        "news", "press release", "public relations", "reporting", "newsletter",
    },
    Discipline.ENG_MECHANICAL: {
        "cad", "civil", "fluid mechanics", "manufacturing", "mechanics",
        "solidworks", "stress", "structural", "thermodynamics", "autocad",
        "strength of materials", "surveying", "beam", "truss",
    },
}

# ------------------------------------------------------------- tool hints ---
# Keyword in the unit text -> free tools a student would actually use.

TOOL_HINTS: dict[str, list[str]] = {
    "cash flow": ["Excel", "Google Sheets"],
    "financial": ["Excel", "Google Sheets"],
    "ratio analysis": ["Excel", "Google Sheets"],
    "financial ratio": ["Excel", "Google Sheets"],
    "valuation": ["Excel", "Google Sheets"],
    "capital budgeting": ["Excel", "Google Sheets"],
    "statistics": ["Python (pandas)", "R", "Google Sheets"],
    "regression": ["Python (scikit-learn)", "R"],
    "machine learning": ["Python (scikit-learn)", "Google Colab"],
    "dataset": ["Python (pandas)", "Google Colab"],
    "survey": ["Google Forms", "KoboToolbox", "Excel"],
    "questionnaire": ["Google Forms", "KoboToolbox"],
    "interview": ["Otter.ai", "Google Docs"],
    "thematic analysis": ["Taguette", "Google Docs"],
    "typography": ["Figma", "Inkscape"],
    "logo": ["Figma", "Inkscape", "Canva"],
    "brand": ["Figma", "Canva"],
    "layout": ["Figma", "Scribus"],
    "grid": ["Figma"],
    "sql": ["PostgreSQL", "DBeaver"],
    "database": ["PostgreSQL", "DBeaver"],
    "query": ["PostgreSQL", "EXPLAIN ANALYZE"],
    "indexing": ["PostgreSQL", "EXPLAIN ANALYZE"],
    "normalisation": ["PostgreSQL", "dbdiagram.io"],
    "er model": ["dbdiagram.io", "Graphviz"],
    "programming": ["VS Code", "Git"],
    "algorithm": ["VS Code", "Git", "LeetCode"],
    "sequence alignment": ["Biopython", "BLAST"],
    "genome": ["Biopython", "Google Colab"],
    "contract": ["Google Docs", "PandaDoc"],
    "policy brief": ["Google Docs", "Zotero"],
    "press release": ["Google Docs", "Canva"],
    "cad": ["FreeCAD", "AutoCAD (student)"],
}

# -------------------------------------------------------- market aliases ----
# Academic phrase -> phrases that actually appear in live briefs. This is the
# table that makes a dork find anything.

MARKET_ALIASES: dict[str, list[str]] = {
    # commerce / finance
    "working capital": ["working capital", "cash flow forecast", "liquidity analysis"],
    "cash conversion cycle": ["cash flow forecast", "working capital", "cash budget"],
    "ratio analysis": ["financial analysis", "financial ratios", "balance sheet analysis"],
    "capital budgeting": ["investment appraisal", "NPV analysis", "financial model"],
    "cost of capital": ["cost of equity", "WACC", "valuation model"],
    "capm": ["cost of equity", "equity risk", "valuation"],
    "financial management": ["financial model", "budget", "financial planning"],
    "dividend": ["dividend policy", "payout analysis"],
    "taxation": ["tax filing", "tax compliance", "GST return"],
    "audit": ["financial audit", "bookkeeping review"],
    "budgeting": ["budget", "budget projection", "cash budget"],
    # arts / social science
    "qualitative research": ["qualitative research", "interview study", "thematic analysis"],
    "survey design": ["survey design", "questionnaire design", "survey"],
    "sampling": ["survey sampling", "research design"],
    "thematic analysis": ["qualitative coding", "thematic analysis", "interview analysis"],
    "ethnography": ["field research", "participant observation"],
    "research methodology": ["research design", "research assistant", "study design"],
    "policy brief": ["policy brief", "policy research", "white paper"],
    "needs assessment": ["needs assessment", "community research", "stakeholder mapping"],
    "content analysis": ["content analysis", "media monitoring"],
    # design
    "typography": ["typography", "type design", "font pairing"],
    "grid systems": ["layout design", "editorial design", "grid layout"],
    "brand identity": ["brand identity", "logo design", "brand guidelines"],
    "logo design": ["logo design", "visual identity", "brand mark"],
    "colour theory": ["colour palette", "brand colours", "visual design"],
    "visual hierarchy": ["layout design", "UI design", "poster design"],
    "editorial design": ["report design", "annual report layout", "magazine layout"],
    "infographic": ["infographic design", "data visualisation"],
    # cs
    "database management": ["database design", "SQL", "schema design"],
    "normalisation": ["database schema", "schema design", "data modelling"],
    "sql": ["SQL query", "SQL optimisation", "database query"],
    "indexing": ["query optimisation", "database performance", "slow query"],
    "query optimisation": ["query optimisation", "slow query", "database performance"],
    "b-tree": ["database index", "query performance"],
    "er model": ["database design", "data modelling", "schema design"],
    "transactions": ["concurrency", "transaction handling", "database reliability"],
    "data structures": ["algorithm", "good first issue", "refactor"],
    "operating systems": ["systems programming", "performance"],
    "relational algebra": ["SQL query", "database query"],
    # data
    "regression": ["predictive model", "regression analysis", "forecasting"],
    "time series": ["time series forecasting", "demand forecasting"],
    "descriptive statistics": ["data analysis", "data cleaning", "exploratory analysis"],
    "hypothesis testing": ["statistical analysis", "A/B test analysis"],
    "data visualisation": ["data visualisation", "dashboard", "chart design"],
    # life sciences
    "sequence alignment": ["bioinformatics", "sequence analysis", "genomics"],
    "epidemiology": ["epidemiological analysis", "public health data"],
    "genetics": ["genomics", "bioinformatics"],
    # law
    "contract law": ["contract review", "contract drafting", "agreement review"],
    "intellectual property": ["IP licensing", "copyright review", "licence compliance"],
    "privacy": ["privacy policy", "data protection", "GDPR"],
    "compliance": ["compliance review", "regulatory research"],
    # media
    "journalism": ["reporting", "article writing", "fact-checking"],
    "press release": ["press release", "media outreach"],
    "copywriting": ["copywriting", "content writing"],
}

# ----------------------------------------------------------- Bloom verbs ----
# Highest matching level wins. Practical verbs outrank recall verbs, which is
# how we pick which units are worth spending SerpApi credits on.

BLOOM_VERBS: dict[int, set[str]] = {
    1: {"define", "list", "name", "recall", "state", "identify", "introduction"},
    2: {"describe", "explain", "discuss", "summarise", "interpret", "classify",
        "understand", "concepts", "fundamentals"},
    3: {"apply", "compute", "calculate", "solve", "use", "demonstrate",
        "implement", "estimation", "preparation", "practical"},
    4: {"analyse", "analyze", "compare", "examine", "differentiate", "audit",
        "test", "investigate", "analysis", "optimisation", "optimization"},
    5: {"evaluate", "assess", "critique", "justify", "appraise", "recommend",
        "review", "selection"},
    6: {"create", "design", "develop", "build", "construct", "formulate",
        "produce", "compose", "model", "plan", "prepare", "write"},
}

STOPWORDS = {
    "and", "the", "of", "in", "to", "for", "a", "an", "with", "on", "its",
    "their", "from", "by", "as", "at", "or", "is", "are", "be", "this", "that",
    "unit", "module", "chapter", "introduction", "concepts", "study", "types",
    "methods", "course", "paper", "semester", "credits", "objectives",
}


# A secondary discipline is only kept if it is at least this fraction of the
# top score. Without it, one stray word ("classification of typefaces") tags a
# typography unit as data science and skews platform affinity.
SECONDARY_DISCIPLINE_RATIO = 0.5


def _contains(text_lower: str, phrase: str) -> bool:
    """Whole-word containment. Substring matching mis-fires badly here:
    'ratio' inside 'contrast ratios' pulled spreadsheet tools into design units."""
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text_lower) is not None


def detect_disciplines(text: str) -> list[Discipline]:
    """Rank disciplines by keyword hits. Returns the strongest, most specific first."""
    lowered = text.lower()
    scores: dict[Discipline, int] = {}
    for discipline, keywords in DISCIPLINE_KEYWORDS.items():
        hits = 0
        for keyword in keywords:
            if " " in keyword:
                hits += 2 * lowered.count(keyword)       # phrases are stronger evidence
            elif _contains(lowered, keyword):
                hits += 1
        if hits:
            scores[discipline] = hits

    if not scores:
        return [Discipline.CS_SOFTWARE]

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_discipline, top_score = ranked[0]
    out = [top_discipline]
    if len(ranked) > 1:
        second, second_score = ranked[1]
        if second_score >= top_score * SECONDARY_DISCIPLINE_RATIO:
            out.append(second)
    return out


def detect_bloom(text: str) -> int:
    """Highest Bloom level whose verbs appear in the text."""
    lowered = text.lower()
    best = 2
    for level, verbs in BLOOM_VERBS.items():
        for verb in verbs:
            if re.search(rf"\b{re.escape(verb)}\b", lowered):
                best = max(best, level)
                break
    return best


def band_for(bloom: int, semester: int | None) -> Band:
    """Combine cognitive level with how far through the degree the student is."""
    score = bloom
    if semester is not None:
        if semester <= 2:
            score -= 1
        elif semester >= 6:
            score += 1
    if score <= 2:
        return "beginner"
    if score <= 4:
        return "intermediate"
    return "advanced"


def tools_for(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for keyword, tools in TOOL_HINTS.items():
        if _contains(lowered, keyword):
            for tool in tools:
                if tool not in found:
                    found.append(tool)
    return found[:4]


def aliases_for(text: str) -> list[str]:
    """Market phrasings implied by the academic text.

    Longest keys are tested first so a specific match ('query optimisation')
    wins over a generic one ('query') and the generic alias is then skipped.
    """
    lowered = text.lower()
    found: list[str] = []
    for academic in sorted(MARKET_ALIASES, key=len, reverse=True):
        if _contains(lowered, academic):
            for phrase in MARKET_ALIASES[academic]:
                if phrase not in found:
                    found.append(phrase)
    return found
