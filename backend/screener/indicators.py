"""The indicator substrate: ADR, simple moving averages and returns (spec §4.2).

Everything downstream that means "how much did this move" or "how volatile is
this" reads these functions; there is one definition of each quantity, computed
here and nowhere else.

The one distinction that is easy to get wrong and is therefore pinned down here:

- **Rolling statistics count traded bars.** ADR and the moving averages are taken
  over the last *N bars the name actually printed*. "The last 20 days this thing
  traded" is the right question for a volatility unit or a support level — a name
  missing sessions should not have its ADR window silently stretched across
  calendar time.
- **Returns are calendar-anchored.** A board must compare like with like: under
  traded-bar counting a "3-month return" spans 3 calendar months for a name that
  trades every session and ~3.5 months for one missing 15% of them, and the
  longer window has more time to accumulate return — systematically flattering
  illiquid names (ticket 06 R7). The anchor is a *date*; the value read at it is
  the **last bar on or before** that date, which handles weekends, holidays and
  phantom-dropped bars uniformly with no calendar table.

Every function is pure over a clean, oldest-first ``list[Bar]`` — the bars the
store already dropped phantoms from and kept only final sessions of (spec §3.4
rules 1–2). ADR and dollar volume are denominated over ``ADR_WINDOW`` bars, the
one window shared across the app (§4.1 D2/D5).
"""

from __future__ import annotations

from bisect import bisect_right
from calendar import monthrange
from datetime import date, timedelta

from .bars import Bar

# SMA20 for ADR — the same 20-bar window liquidity and listing age use (§4.1).
ADR_WINDOW = 20

# The five ranking lookbacks, shortest first (spec §4.3 / ticket 06 R2). 1w is 7
# calendar days; the rest are calendar months. Calendar-anchored, never a bar
# count — see the module docstring.
LOOKBACKS: tuple[str, ...] = ("1w", "1m", "3m", "6m", "12m")

_LOOKBACK_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "12m": 12}


# -- rolling statistics: traded-bar windows -----------------------------------


def adr(bars: list[Bar]) -> float | None:
    """Average Daily Range: ``SMA20(high / low − 1)`` over the last 20 traded
    bars (spec §4.2). The method's volatility unit; nearly every threshold in the
    system is denominated in it. ``None`` until 20 bars exist."""
    if len(bars) < ADR_WINDOW:
        return None
    window = bars[-ADR_WINDOW:]
    return sum(b.high / b.low - 1 for b in window) / ADR_WINDOW


def adr_abs(bars: list[Bar]) -> float | None:
    """ADR in price units: ``ADR × close`` at the latest bar (spec §4.2)."""
    a = adr(bars)
    if a is None:
        return None
    return a * bars[-1].close


def sma(bars: list[Bar], window: int) -> float | None:
    """Simple moving average of **adjusted** closes over the last ``window``
    traded bars (spec §4.2 — 10/20/50 are the daily set). ``None`` until the
    window is full. Adjusted, because everything geometric uses ``adj_close``."""
    if len(bars) < window:
        return None
    return sum(b.adj_close for b in bars[-window:]) / window


# -- calendar-anchored returns ------------------------------------------------


def anchor_date(as_of: date, lookback: str) -> date:
    """The date a ``lookback`` return reaches back to from ``as_of`` (§4.2).

    1w is 7 calendar days; the calendar-month lookbacks subtract whole months and
    clamp a short target month (31 Mar − 1m → 28/29 Feb, not an invalid date).
    """
    if lookback == "1w":
        return as_of - timedelta(days=7)
    months = _LOOKBACK_MONTHS[lookback]
    total = as_of.year * 12 + (as_of.month - 1) - months
    year, month = divmod(total, 12)
    month += 1
    day = min(as_of.day, monthrange(year, month)[1])
    return date(year, month, day)


def _last_adj_close_on_or_before(bars: list[Bar], when: date) -> float | None:
    """The adjusted close of the last bar dated on or before ``when``.

    Bars are oldest-first, so a binary search on their sessions gives the "last
    bar on or before" rule that handles weekends, holidays and phantom gaps
    uniformly (§4.2). ``None`` when the name had not yet listed by ``when``.
    """
    sessions = [b.session for b in bars]
    idx = bisect_right(sessions, when)
    if idx == 0:
        return None
    return bars[idx - 1].adj_close


def calendar_return(bars: list[Bar], as_of: date, lookback: str) -> float | None:
    """``AdjClose(last bar ≤ as_of) / AdjClose(last bar ≤ as_of − L) − 1`` (§4.2).

    Returns ``None`` — meaning **absent**, not zero — when the name has no bar on
    or before the anchor date, i.e. it had not listed a full ``lookback`` ago.
    Per-lookback eligibility falls straight out of this: a recent IPO is simply
    absent from the long lookbacks rather than zero-filled or backfilled
    (spec §4.3 / ticket 06 D5).
    """
    start = _last_adj_close_on_or_before(bars, anchor_date(as_of, lookback))
    if start is None or start == 0:
        return None
    end = _last_adj_close_on_or_before(bars, as_of)
    if end is None:
        return None
    return end / start - 1
