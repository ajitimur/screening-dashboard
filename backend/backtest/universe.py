"""The backtest's stateless universe classifier (issue #185, PRD #182 Phase 0).

Three gates and one market-specific trim, all measured **through t−1**: a signal
on session *t* is classified on only the bars knowable the night before
(``b.session < session``), so no gate can peek at *t*'s own bar.

- **Trend** — close above SMA50, on both markets (contract
  ``universe.trend_gate``).
- **Liquidity** — ADTV at or above the contract's per-market floor, $10M for US
  and Rp 10B for IDX (``universe.liquidity_floor``).
- **Volatility** — ADR20 at or above 3.5% (``universe.volatility_gate``).
- **Data-validity trim** — IDX only: nominal price at or above Rp 100 on the
  split-corrected series (``universe.idx_price_floor``).

Why this is a new classifier and not the app's
----------------------------------------------
The app's universe (:mod:`screener.universe`) cannot be reused, for three
independent reasons:

- its liquidity floors are $20M and Rp 1B rather than the contract's values;
- it has no trend gate and no volatility gate at all — universe in the app is
  liquidity, instrument type, listing age and density and nothing else; and
- it reads the previous session's membership for both stickiness (an unresolved
  fetch carries yesterday's classification) and the hysteresis band (a member is
  held in the 0.8–1.0× floor band), which this contract drops.

So this is a new classifier that reuses the app's median-dollar-volume and
instrument-type functions and leaves the app's classifier alone. It is pure: it
takes prepared :class:`Candidate` inputs — symbol, name and clean oldest-first
bars, with no ``resolved`` flag and no prior membership — and the signal session,
and returns the surviving symbols.

Two things recorded here so nobody later "fixes" them
-----------------------------------------------------
- **The ADR20 floor sits deliberately below the rubric's 5% minimum**
  (:data:`screener.score.ADR_MIN`). Findings §6 Finding 2 measured that 5% floor
  silently withholding a score point from 31% of the trader's real entries, so a
  universe cut at 5% would leave the ADR dimension with no spread left to test.
  The gap is the point (contract ``universe.volatility_gap_reason``).
- **Statelessness reintroduces the boundary churn** the app's hysteresis band
  exists to damp: a name oscillating around a floor enters and leaves day by day.
  At signal level this is nearly free — each signal is evaluated on its own
  session — so it is recorded as a known difference from the app rather than
  fixed (contract ``universe.statelessness``).

Every floor is read off the :class:`~backtest.contract.RunContract`, never off
the app's ``screener.universe.LIQUIDITY_FLOOR``, so "the contract's values, not
the app's" holds by construction rather than by vigilance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from screener.bars import Bar
from screener.indicators import adr, sma

# The two functions the app owns and this classifier reuses verbatim: the
# liquidity measure (median of unadjusted close × volume over 20 traded bars, so
# one block trade cannot lift an illiquid name over the floor) and the
# instrument-type test (which also keeps the index and the preferred series out).
from screener.universe import is_common_stock, median_dollar_volume

from .contract import (
    DEFAULT_CONTRACT,
    UNIVERSE_IDX_PRICE_FLOOR_KEY,
    UNIVERSE_LIQUIDITY_FLOOR_KEY,
    RunContract,
)

# The trend window. 50 is also the binding listing-age minimum here —
# :func:`screener.indicators.sma` returns ``None`` until the window is full, so a
# name with fewer than 50 traded bars cannot be a member, and the app's 20-bar
# minimum is not what governs.
TREND_WINDOW = 50

# The volatility floor, set **deliberately below** the rubric's 5%
# (:data:`screener.score.ADR_MIN`) — see the module docstring and contract cell
# ``universe.volatility_gap_reason``. Moving it to 5% to "match" the rubric
# destroys the spread the ADR dimension is being measured on.
VOLATILITY_FLOOR = 0.035


@dataclass(frozen=True)
class Candidate:
    """One candidate's inputs to stateless classification.

    Unlike :class:`screener.universe.Candidate` there is no ``resolved`` flag and
    no prior membership anywhere: how ``bars`` classify on a session does not
    depend on any earlier state. ``bars`` are the symbol's clean, phantom-dropped
    bars, oldest session first.
    """

    symbol: str
    name: str
    bars: list[Bar]


# -- the individual gates (pure, over bars already sliced to ≤ t−1) ------------


def passes_trend_gate(bars: list[Bar]) -> bool:
    """The latest adjusted close is above its SMA50 (``universe.trend_gate``).

    ``False`` until 50 traded bars exist, so this doubles as the listing-age
    floor. Compared on *adjusted* closes on both sides, because SMA50 is an
    average of adjusted closes and a raw-close comparison would break across a
    split.
    """
    ma = sma(bars, TREND_WINDOW)
    if ma is None:
        return False
    return bars[-1].adj_close > ma


def passes_volatility_gate(bars: list[Bar]) -> bool:
    """ADR20 at or above 3.5% (``universe.volatility_gate``).

    ``False`` until 20 traded bars exist. The floor is below the rubric's 5% on
    purpose — see the module docstring.
    """
    a = adr(bars)
    return a is not None and a >= VOLATILITY_FLOOR


def passes_liquidity_gate(
    bars: list[Bar], market: str, contract: RunContract = DEFAULT_CONTRACT
) -> bool:
    """ADTV at or above the contract's per-market floor ($10M US, Rp 10B IDX).

    ADTV is the app's :func:`screener.universe.median_dollar_volume` — the 20-day
    median of unadjusted close × volume — reused verbatim, so one block trade
    cannot lift an illiquid name over the floor. The floor is read off the
    contract, never off the app's ``LIQUIDITY_FLOOR``
    (``universe.liquidity_floor``).
    """
    floor = contract.value(UNIVERSE_LIQUIDITY_FLOOR_KEY)[market]
    return median_dollar_volume(bars) >= floor


def passes_price_gate(
    bars: list[Bar], market: str, contract: RunContract = DEFAULT_CONTRACT
) -> bool:
    """IDX's Rp 100 nominal-price trim on the split-corrected series.

    A **data validity** trim and never cost control (``universe.idx_price_floor_role``):
    below Rp 100 an IDX quote hits the tick grid hard enough that ADR and range
    geometry stop meaning what they mean elsewhere. Read a penny-stock filter
    with an implied cost story into it and the write-up says something the run
    does not.

    Applied to the adjusted (split-corrected) close, which is the series every
    other figure in this package uses — Yahoo's unlabelled rights-issue rescaling
    makes "nominal price" ambiguous otherwise. US names have no such trim.
    """
    if market != "IDX":
        return True
    return bars[-1].adj_close >= contract.value(UNIVERSE_IDX_PRICE_FLOOR_KEY)


# -- the whole gate (pure, stateless) -----------------------------------------


def is_member(
    candidate: Candidate,
    market: str,
    session: date,
    contract: RunContract = DEFAULT_CONTRACT,
) -> bool:
    """Is ``candidate`` a universe member for a signal on ``session``?

    The slice is the point-in-time claim, made once here rather than remembered
    in each gate: every gate below sees only bars strictly before ``session``, so
    a signal on *t* uses only what was knowable the night before. There is no
    prior-membership input — the answer depends on nothing but these bars.
    """
    bars = [b for b in candidate.bars if b.session < session]
    return (
        is_common_stock(candidate.symbol, candidate.name)
        and passes_trend_gate(bars)
        and passes_volatility_gate(bars)
        and passes_liquidity_gate(bars, market, contract)
        and passes_price_gate(bars, market, contract)
    )


def classify(
    market: str,
    candidates: list[Candidate],
    session: date,
    contract: RunContract = DEFAULT_CONTRACT,
) -> list[str]:
    """The sorted symbols that are universe members for a signal on ``session``.

    There is no ``prior_members`` parameter, which is the whole point: classifying
    the same session twice returns identical membership regardless of any earlier
    state (``universe.statelessness``). The boundary churn this reintroduces
    against the app's hysteresis band is a recorded known difference, not a bug.
    """
    return sorted(
        c.symbol for c in candidates if is_member(c, market, session, contract)
    )
