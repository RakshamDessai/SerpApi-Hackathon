"""Cheap derived signals read off a result's text.

Feeds the scorer (seniority band) and the card UI (compensation, effort, scam
flag). All regex and keyword work - no I/O, no model calls.
"""

from __future__ import annotations

import re

from s2s.mesh import adapters as adapter_registry
from s2s.models import Band, Compensation, RawResult

SENIOR_PATTERNS = (
    r"\bsenior\b", r"\blead\b", r"\bprincipal\b", r"\barchitect\b",
    r"\bhead of\b", r"\bdirector\b", r"\bmanager\b", r"\bph\.?d\b",
    r"\b[5-9]\+?\s*years\b", r"\b1[0-9]\+?\s*years\b", r"\bexpert\b",
)

BEGINNER_PATTERNS = (
    r"good first issue", r"\bbeginner\b", r"\bintern\b", r"\binternship\b",
    r"entry[- ]level", r"\bfresher\b", r"no experience", r"first[- ]time",
    r"\bstudent\b", r"\bjunior\b", r"\bhelp wanted\b", r"\bstarter\b",
)

#: Deliverable nouns. Their presence means the brief states a concrete output,
#: which is the clearest available proxy for "this is actually actionable".
DELIVERABLE_NOUNS = {
    "report", "model", "design", "dashboard", "analysis", "logo", "survey",
    "policy brief", "dataset", "prototype", "audit", "template", "guidelines",
    "script", "plan", "deck", "website", "budget", "forecast", "brief",
    "presentation", "article", "translation", "database", "schema", "wireframe",
}

SCAM_PATTERNS = (
    r"\bno pay\b", r"unpaid internship", r"pay to apply", r"registration fee",
    r"\bcommission only\b", r"\bequity only\b", r"send your bank",
    r"\bwhatsapp me\b", r"earn \$?\d{4,} ?(per|a) (day|week)",
)

EFFORT_HINTS: list[tuple[str, tuple[int, int]]] = [
    (r"\bquick\b|\bsmall task\b|\bmicro\b|\b1[- ]2 hours\b", (1, 4)),
    (r"\bweekend\b|\bshort[- ]term\b|\ba few days\b", (8, 15)),
    (r"\bhackathon\b|\b24[- ]hour\b|\b48[- ]hour\b", (24, 48)),
    # A bare "months?" matches the subject of the work ("12-month cash flow
    # forecast") as readily as its duration, so require commitment phrasing.
    (r"\bcompetition\b|\bchallenge\b|\bcapstone\b|\bsemester[- ]long\b"
     r"|\bover \d+ months\b|\b\d+[- ]month (project|engagement|commitment)\b", (40, 80)),
]


def _text(result: RawResult) -> str:
    return f"{result.title} {result.snippet}".lower()


def infer_band(result: RawResult) -> Band:
    """Difficulty band the listing is pitched at."""
    text = _text(result)
    for pattern in BEGINNER_PATTERNS:
        if re.search(pattern, text):
            return "beginner"
    for pattern in SENIOR_PATTERNS:
        if re.search(pattern, text):
            return "advanced"
    return "intermediate"


def compensation_for(result: RawResult) -> Compensation:
    """Platform default, overridden when the text says otherwise."""
    adapter = adapter_registry.ADAPTERS.get(result.adapter_key)
    default: Compensation = adapter.compensation if adapter else "volunteer"

    text = _text(result)
    if re.search(r"\bstipend\b", text):
        return "stipend"
    if re.search(r"\bprize\b|\bprize pool\b|\bcash award\b", text):
        return "prize"
    if re.search(r"\bbounty\b|\$\d+\s*bounty\b", text):
        return "bounty"
    if re.search(r"\bvolunteer\b|\bpro ?bono\b|\bunpaid\b", text):
        return "volunteer"
    if re.search(r"\$\d|₹\s?\d|\bper hour\b|\bhourly\b|\bbudget\b|\bpaid\b", text):
        return "paid"
    return default


def estimate_hours(result: RawResult) -> tuple[int, int] | None:
    text = _text(result)

    explicit = re.search(r"(\d{1,3})\s*(?:-|to)\s*(\d{1,3})\s*hours?\b", text)
    if explicit:
        low, high = int(explicit.group(1)), int(explicit.group(2))
        if 0 < low <= high <= 500:
            return low, high

    single = re.search(r"\b(\d{1,3})\s*hours?\b", text)
    if single:
        hours = int(single.group(1))
        if 0 < hours <= 500:
            return max(1, hours - 2), hours + 2

    for pattern, span in EFFORT_HINTS:
        if re.search(pattern, text):
            return span
    return None


def has_deliverable(result: RawResult) -> bool:
    text = _text(result)
    return any(noun in text for noun in DELIVERABLE_NOUNS)


def is_scammy(result: RawResult) -> bool:
    """Filter vague, exploitative or obviously fake commercial listings."""
    text = _text(result)
    return any(re.search(pattern, text) for pattern in SCAM_PATTERNS)
