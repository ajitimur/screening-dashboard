"""The rank table and the decile gate — the shared substrate (spec §4.3).

There is exactly one definition of "strong" in the app, and it lives here.
Sector strength (§4.4) and the setup-detection gate (§4.5) both read this table;
neither defines strength a second time (ticket 06 R6).

Per (name, lookback, session) the table carries a **percentile** and the **raw
return**, for **every universe member** — not only board members, or a name's
history would have holes exactly on the nights it was interesting-but-not-quite
(ticket 06 R5). The rank is on *pure return*, no volatility adjustment: the
quantity hunted is a big prior move, not a big risk-adjusted one (R9).

Two properties the callers must not lose:

- **Per-lookback eligibility.** A name is ranked in a lookback iff it has a bar
  on or before that lookback's anchor date; a recent listing is simply *absent*
  from the long lookbacks — never zero-filled, never backfilled. Per-lookback
  denominators therefore differ by construction.
- **The gate is the union of the five top deciles, any-of, not a composite.**
  Each decile is computed within its own lookback's population. Unioned across
  five windows it passes **~29% of the universe, not 10%** (566 US / 82 IDX
  measured) — a percentile gate is self-normalising, which is why two markets
  differing 7× in size both land near 29%. A composite would lose precisely the
  sharp recent movers the method trades (R2).

Pure over ``{symbol: list[Bar]}``; the store-driven wrapper lives in the
pipeline.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date

from .bars import Bar
from .indicators import LOOKBACKS, calendar_return

# Top decile = the top 10% of a lookback's own population. A percentile is the
# empirical CDF (share of the population at or below), so the maximum sits at 1.0
# and the top tenth at or above 0.90 — inclusive at the threshold. Measured, this
# reproduces the 197-name US / 29-name IDX 1w deciles of ticket 06.
TOP_DECILE = 0.90


@dataclass(frozen=True)
class Rank:
    """One rank row: a name's percentile and raw return in one lookback on one
    session. The unit of the (name, lookback, session) rank table (§4.3)."""

    symbol: str
    lookback: str
    percentile: float
    raw_return: float


def _percentiles(returns: dict[str, float]) -> dict[str, float]:
    """Empirical-CDF percentile of each name within the population: the share of
    returns at or below it. Ties share a percentile (all tied names count as
    "at or below" each other), which is the honest reading of a tie."""
    n = len(returns)
    ordered = sorted(returns.values())
    return {sym: bisect_right(ordered, r) / n for sym, r in returns.items()}


def rank_table(members_bars: dict[str, list[Bar]], as_of: date) -> list[Rank]:
    """Every member's rank rows for ``as_of``, across all five lookbacks (§4.3).

    A member absent from a lookback (no bar on or before its anchor) contributes
    no row *and* is not in that lookback's denominator — the percentile of the
    names that do qualify is taken against the eligible population only.
    """
    rows: list[Rank] = []
    for lookback in LOOKBACKS:
        returns: dict[str, float] = {}
        for symbol, bars in members_bars.items():
            r = calendar_return(bars, as_of, lookback)
            if r is not None:
                returns[symbol] = r
        percentiles = _percentiles(returns)
        rows.extend(
            Rank(symbol, lookback, percentiles[symbol], returns[symbol])
            for symbol in returns
        )
    return rows


def decile_gate(rows: list[Rank]) -> set[str]:
    """The union of the five top deciles: names top-decile in **any** lookback
    (§4.3 / ticket 06 R2). Any-of, not a composite — this is the setup-detection
    precondition, sized for ~29% of the universe, not 10%."""
    return {r.symbol for r in rows if r.percentile >= TOP_DECILE}
