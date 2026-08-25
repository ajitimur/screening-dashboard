"""The backtest's stateless universe classifier (issue #185, PRD #182 Phase 0).

The app's universe (``screener.universe``) is **stateful**: it reads the previous
session's membership for both stickiness (an unresolved fetch carries yesterday's
classification) and the hysteresis band (a member is held in the 0.8–1.0× floor
band). The backtest cannot reuse it for three independent reasons, each recorded
in the run contract:

- its liquidity floors are $20M / Rp 1B, not the contract's $10M / Rp 10B
  (``universe.liquidity_floor``);
- it has no trend gate and no volatility gate — universe in the app is liquidity,
  instrument type, listing age and density and nothing else — whereas the
  contract adds ``close > SMA50`` and ``ADR20 >= 3.5%``
  (``universe.trend_gate``, ``universe.volatility_gate``); and
- it reads prior membership, which the contract drops
  (``universe.statelessness``).

So this is a **new** classifier that reuses the app's median-dollar-volume and
instrument-type functions and leaves the app's classifier untouched. Every gate
is measured **through t−1**: a signal on session *t* is classified on only the
bars knowable the night before (``b.session < t``), so no gate can peek at *t*'s
own bar.

Two things this design deliberately does that a reader will want the reason for,
recorded here beside the constants and in the contract so nobody later "fixes"
them:

- **The ADR20 floor (3.5%) sits below the rubric's 5% minimum**
  (:data:`screener.score.ADR_MIN`). Findings §6 Finding 2 measured that 5% floor
  silently withholding a score point from 31% of the trader's real entries; a
  universe cut at 5% would leave the ADR dimension with no spread left to test.
  The gap is intentional (``universe.volatility_gap_reason``).
- **Statelessness reintroduces boundary churn** the app's hysteresis band exists
  to damp: a name oscillating around a floor enters and leaves day by day. At
  signal level this is nearly free — each signal is evaluated on its own session
  — so it is recorded as a known difference from the app rather than fixed
  (``universe.statelessness``).

The classifier is pure: it takes prepared :class:`Candidate` inputs (symbol, name
and clean oldest-first bars — no ``resolved`` flag, no prior membership) and the
signal session, and returns the surviving symbols. The floors it enforces are
read off the :class:`~backtest.contract.RunContract`, never off the app's
``screener.universe.LIQUIDITY_FLOOR``, so "the contract's values, not the app's"
holds by construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from screener.bars import Bar
from screener.indicators import adr, sma

# The two functions the app owns and this classifier reuses verbatim (issue #185):
# the liquidity measure (median of unadjusted close × volume over 20 traded bars,
# so one block trade cannot lift an illiquid name) and the instrument-type test.
from screener.universe import is_common_stock, median_dollar_volume

from .contract import (
    DEFAULT_CONTRACT,
    UNIVERSE_IDX_PRICE_FLOOR_KEY,
    UNIVERSE_LIQUIDITY_FLOOR_KEY,
    RunContract,
)

# The trend gate: the latest (adjusted) close must sit above its own SMA50. 50 is
# also the binding listing-age minimum — :func:`screener.indicators.sma` returns
# ``None`` until the window is full, so a name with fewer than 50 traded bars
# cannot be a member (contract ``universe.trend_gate``).
TREND_WINDOW = 50

# The volatility gate: ADR20 must clear 3.5%. Set **deliberately below** the
# rubric's 5% floor (:data:`screener.score.ADR_MIN`) — see the module docstring
# and contract ``universe.volatility_gate`` / ``universe.volatility_gap_reason``.
VOLATILITY_FLOOR = 0.035


@dataclass(frozen=True)
class Candidate:
    """One candidate's inputs to stateless classification.

    Unlike :class:`screener.universe.Candidate`, there is no ``resolved`` flag and
    no prior membership anywhere: the classification of ``bars`` on a session does
    not depend on any earlier state. ``bars`` are the symbol's clean,
    phantom-dropped bars, oldest session first.
    """

    symbol: str
    name: str
    bars: list[Bar]


# -- the individual gates (pure, over bars already sliced to ≤ t−1) ------------


def passes_trend_gate(bars: list[Bar]) -> bool:
    """The latest adjusted close is above SMA50 (contract ``universe.trend_gate``).

    ``False`` until 50 traded bars exist, so this doubles as the listing-age
    floor. Compared on adjusted closes throughout, because SMA50 is an adjusted
    average and a raw-close comparison would break across a split.
    """
    ma = sma(bars, TREND_WINDOW)
    if ma is None:
        return False
    return bars[-1].adj_close > ma


def passes_volatility_gate(bars: list[Bar]) -> bool:
    """ADR20 ≥ 3.5% (contract ``universe.volatility_gate``). ``False`` until 20
    traded bars exist. The floor is below the rubric's 5% on purpose — see the
    module docstring."""
    a = adr(bars)
    return a is not None and a >= VOLATILITY_FLOOR


def passes_liquidity_gate(
    bars: list[Bar], market: str, contract: RunContract = DEFAULT_CONTRACT
) -> bool:
    """ADTV ≥ the contract's per-market floor ($10M US / Rp 10B IDX).

    ADTV is the app's :func:`screener.universe.median_dollar_volume` — the 20-day
    median of unadjusted close × volume — reused verbatim, so one block trade
    cannot lift an illiquid name over the floor. The floor is read off the
    contract, never off the app's ``LIQUIDITY_FLOOR`` (contract
    ``universe.liquidity_floor``).
    """
    floor = contract.value(UNIVERSE_LIQUIDITY_FLOOR_KEY)[market]
    return median_dollar_volume(bars) >= floor


def passes_price_gate(
    bars: list[Bar], market: str, contract: RunContract = DEFAULT_CONTRACT
) -> bool:
    """IDX's Rp 100 nominal-price trim on the split-corrected series.

    A **data-validity** trim, never cost control (contract
    ``universe.idx_price_floor_role``): below Rp 100 an IDX quote hits the tick
    grid hard enough that ADR and range geometry stop meaning what they mean
    elsewhere. Applied to the adjusted (split-corrected) close so a pre-split
    quote is judged on today's price. US names have no such gate.
    """
    if market != "IDX":
        return True
    floor = contract.value(UNIVERSE_IDX_PRICE_FLOOR_KEY)
    return bars[-1].adj_close >= floor


# -- the whole gate (pure, stateless) -----------------------------------------


def is_member(
    candidate: Candidate,
    market: str,
    session: date,
    contract: RunContract = DEFAULT_CONTRACT,
) -> bool:
    """Is ``candidate`` a universe member for a signal on ``session``?

    Every gate reads only bars at or before ``t−1`` (``b.session < session``), so
    a signal on ``session`` uses only what was knowable the night before. There
    is no prior-membership input: the answer depends on nothing but these bars.
    """
    bars = [b for b in candidate.bars if b.session < session]
    if not is_common_stock(candidate.symbol, candidate.name):
        return False
    if not passes_trend_gate(bars):
        return False
    if not passes_volatility_gate(bars):
        return False
    if not passes_liquidity_gate(bars, market, contract):
        return False
    if not passes_price_gate(bars, market, contract):
        return False
    return True


def classify(
    market: str,
    candidates: list[Candidate],
    session: date,
    contract: RunContract = DEFAULT_CONTRACT,
) -> list[str]:
    """Return the sorted symbols that are universe members for a signal on
    ``session`` — statelessly.

    There is no ``prior_members`` parameter: classifying the same session twice
    returns identical membership regardless of any earlier state, which is the
    whole point (contract ``universe.statelessness``). The churn this reintroduces
    versus the app's hysteresis band is a recorded known difference, not a bug.
    """
    return sorted(
        c.symbol
        for c in candidates
        if is_member(c, market, session, contract)
    )
