"""Daily alert: which live listings are new since the last run (Feature 54).

Pure functions over URLs and opportunities, so the diff is unit-tested. The
I/O - running the pipeline, saving state, sending the message - lives in
`scripts/daily_alert.py`.

Only `live` listings alert. An unverified listing may be closed, and a
message is the one place where a student acts without seeing the card's
verdict first.
"""

from __future__ import annotations

from s2s.models import Opportunity


def new_live(opportunities: list[Opportunity], seen: set[str]) -> list[Opportunity]:
    """Live listings whose URL is not in `seen`, best score first."""
    fresh = [o for o in opportunities if o.verdict == "live" and o.url not in seen]
    return sorted(fresh, key=lambda o: -o.score.total)


def message(new: list[Opportunity], limit: int = 3) -> str:
    """Plain text for Telegram or a terminal. Empty when nothing is new."""
    if not new:
        return ""
    lines = [f"S2S: {len(new)} new live listing{'s' if len(new) != 1 else ''} "
             "for your syllabus"]
    for opportunity in new[:limit]:
        lines += [
            "",
            f"{opportunity.title} ({opportunity.score.total}% match)",
            f"Uses: {opportunity.matched_competency.source_unit}",
            opportunity.url,
        ]
    if len(new) > limit:
        lines += ["", f"+{len(new) - limit} more in the app."]
    return "\n".join(lines)
