"""SerpApi credit accounting.

Two jobs:

1. **Safety.** A hard per-run cap means a runaway loop or an over-eager plan can
   never drain a 100-search monthly quota in one click.
2. **Evidence.** The ledger is what the UI renders as "9 live searches, 4 cache
   hits, 3 credits remaining", and what the credit-efficiency panel uses to show
   naive-vs-planned cost. For a SerpApi hackathon that story is worth as much as
   the search results themselves.

Skipped calls are always recorded. Silent truncation would read as "we covered
everything" when we did not.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LedgerEntry:
    adapter_key: str
    query: str
    cost: int
    cache_hit: bool
    skipped: bool = False
    note: str = ""


@dataclass
class BudgetLedger:
    cap: int
    spent: int = 0
    entries: list[LedgerEntry] = field(default_factory=list)

    # -- accounting ------------------------------------------------------

    def can_afford(self, cost: int = 1) -> bool:
        return self.spent + cost <= self.cap

    @property
    def remaining(self) -> int:
        return max(0, self.cap - self.spent)

    def record_live(self, adapter_key: str, query: str, cost: int = 1) -> None:
        self.spent += cost
        self.entries.append(LedgerEntry(adapter_key, query, cost, cache_hit=False))

    def record_cached(self, adapter_key: str, query: str) -> None:
        """Cache hits cost nothing but are still shown, so the saving is visible."""
        self.entries.append(LedgerEntry(adapter_key, query, 0, cache_hit=True))

    def record_skipped(self, adapter_key: str, query: str, note: str) -> None:
        self.entries.append(
            LedgerEntry(adapter_key, query, 0, cache_hit=False, skipped=True, note=note)
        )

    # -- reporting -------------------------------------------------------

    @property
    def live_calls(self) -> int:
        return sum(1 for e in self.entries if not e.cache_hit and not e.skipped)

    @property
    def cache_hits(self) -> int:
        return sum(1 for e in self.entries if e.cache_hit)

    @property
    def skipped(self) -> int:
        return sum(1 for e in self.entries if e.skipped)

    def summary(self) -> str:
        parts = [
            f"{self.live_calls} live search{'' if self.live_calls == 1 else 'es'}",
            f"{self.cache_hits} cache hit{'' if self.cache_hits == 1 else 's'}",
            f"{self.remaining} credit{'' if self.remaining == 1 else 's'} left",
        ]
        if self.skipped:
            parts.append(f"{self.skipped} skipped")
        return " · ".join(parts)

    def skip_reasons(self) -> dict[str, int]:
        """Why calls were skipped, so the UI never has to guess."""
        reasons: dict[str, int] = {}
        for entry in self.entries:
            if entry.skipped:
                reasons[entry.note] = reasons.get(entry.note, 0) + 1
        return reasons
