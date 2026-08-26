"""Arm B: turning a persisted detection into a trade (issue #189, PRD #182 Phase 4).

The denominator (:mod:`backtest.denominator`) says which setups the detector named
over the window. This module says what happened to them. One detection becomes at
most one trade per arm, denominated in R, and every price it carries is stamped
with the session that decided it.

The mechanic, end to end
------------------------
Every step is a contract cell, not a code decision (:mod:`backtest.contract`):

1. **The trigger** is the detection's own — ``cluster_high``, by identity. It is a
   decision made on the detection's session.
2. **The break** is the app's own :term:`Break`: a close above the trigger, checked
   on the session *after* the detection. There is no search forward beyond that
   one session, and none is needed — the detector re-names a setup that still
   stands every night, so a base that breaks on its fifth day arrives as that
   night's detection breaking on its next session. Searching forward instead would
   need a holding window that no contract cell defines, and would let one setup
   produce several overlapping trades.
3. **The fill** is the next session's open. Signal, then fill — the same shape the
   trail uses, and the reason neither can read the bar that decides it.
4. **The stop** is the detection's own, unmodified: ``trigger − stop``
   (:attr:`~screener.detection.Detection.stop_price`). It is checked intraday and
   takes precedence over the trail within a session, because a stop is an order
   resting in the market and the trail is a decision taken at the close.
5. **The trail** is a simple moving average of ``trail_ma`` sessions. A close
   through it signals; the next open fills.

A detection whose next session does not break produces **no trade**, and that is a
measurement rather than a dropped row: the share of detections that trigger is one
of the figures the denominator exists to produce.

Why the trail reads the unadjusted close
----------------------------------------
:func:`screener.indicators.sma` averages ``adj_close``, because a return series
must be dividend-continuous. The trail must not: it is compared against a close and
sits in the same price the trigger and the stop are quoted in, which is the
*unadjusted* one — the same reasoning that gives the detector its own
``detection._sma_close`` for the catch-up MA. Mixing the two would compare a price
against a level from a different series and call the difference a signal.

The two price scales, and what is immune to them
------------------------------------------------
Yahoo applies an **unlabelled retroactive rescale** for rights issues — measured on
BBRI as pre-2021-09-08 OHLC scaled by exactly 10/11, with no split or dividend row
to explain it. Two consequences, and this module answers each separately:

- **Geometry in ADR units is immune**, because both terms rescale together. So R is
  denominated by the detection's stop width *in ADR* (``stopw_adr``, the detection's
  own stop expressed in the system's own unit) priced off the ADR measured on the
  **bars** at the deciding session. Numerator and denominator are then both prices
  from the same series, and a constant rescale cancels.
- **Absolute prices are not immune**, and one absolute comparison is unavoidable:
  the trigger is imported from a row persisted earlier and compared against a bar
  read now. So every trade carries a :attr:`SimulatedTrade.price_scale` and the
  flag derived from it, and :func:`price_scale_drops` reports how many trades it
  would drop. Flagged, never silently dropped — the same call the
  ``prototype-tightness`` spike made (commit ``233c008``), whose band this borrows.

Point-in-time, proved rather than cared about
---------------------------------------------
Every decision slices the bars with :func:`backtest.chain.trailing_bars` to the
session deciding it, so no bar after a decision can reach it. That claim is not
worth a docstring on its own: it is asserted by
``test_shifting_a_future_bar_into_an_entry_decision_changes_nothing``, which
replaces every bar after the fill with a 10× spike and requires the entry to be
identical. A look-ahead bug produces a beautiful equity curve and no error message,
so it is the one defect here that reading the output can never catch.

What this module does not do
----------------------------
Arms A and C (#190) and costs (#191) are not here. The shape is built for them
anyway: the entry and the stop are computed once and the exit is the only per-arm
step, which is the whole reason to run three arms — a difference between them is
then attributable to the exit alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Sequence

from screener.bars import Bar
from screener.detection import Detection
from screener.indicators import ADR_WINDOW, adr_abs
from screener.store import Store

from .chain import bar_index, trailing_bars
from .contract import EXIT_ARM_B_KEY, EXIT_TRAIL_MECHANIC_KEY, RunContract
from .denominator import DenominatorStore
from .result import stamp_result
from .run import ContractDrift

# The arm this module simulates. Arm B is the pure trail and the arm the
# pre-registered primary metric is computed on (contract ``metric.primary``).
ARM_B = "B"

# The two ways a trade can end. Recorded on the trade rather than inferred from its
# prices, because a trail fill that happens to land on the stop is a different event
# from a stop, and only one of them is evidence about the trail.
EXIT_TRAIL = "trail"
EXIT_STOP = "stop"

# The trail mechanic this module implements, named exactly as the contract cell
# names it. :func:`check_trail_mechanic` refuses a run whose cell says anything else.
TRAIL_MECHANIC = "close_through_ma_signals_fill_next_open"

# The band a trade's price scale must sit in to be trusted for absolute-price
# comparisons, borrowed unchanged from the ``prototype-tightness`` spike (commit
# ``233c008``) that first hit this. It is deliberately wide: it is looking for a
# *rescale* — a factor of 10/11, of a split, of a rights issue — and not for a
# price that moved. A real session-to-session move cannot leave this band; a
# retroactive rescale leaves it immediately.
PRICE_SCALE_MIN = 0.7
PRICE_SCALE_MAX = 1.45


@dataclass(frozen=True)
class Decision:
    """One price and the session it was decided on.

    Every price on a :class:`SimulatedTrade` is one of these rather than a bare
    float, so any trade can be audited back to its inputs (story 86). A price with
    no session cannot be reconciled against the bars, which makes every figure
    derived from it unfalsifiable.
    """

    session: date
    price: float


@dataclass(frozen=True)
class SimulatedTrade:
    """One detection, taken mechanically, on one exit arm.

    The **simulated trade** CONTEXT.md names: a counterfactual built from the
    detector's own decision, never an executed trade. ``trigger`` and ``stop`` are
    shared by every arm by construction — #190's arms A and C differ from this one
    in ``exit`` and in nothing else — which is the only reason running three arms
    answers anything about exits.

    ``exit`` is ``None`` when the bars run out before either the stop or the trail
    fired. Such a trade is **open**, and an open trade has no R: closing it at the
    last available close would invent an exit the rules never gave, systematically,
    for every name still running at the end of the window.
    """

    market: str
    symbol: str
    arm: str
    detection_session: date
    trigger: Decision
    breakout: Decision
    entry: Decision
    stop: Decision
    # The R denominator in price units: the detection's stop width in ADR, priced
    # off the bars at the deciding session. See the module docstring.
    risk: float
    exit_signal: Decision | None
    exit: Decision | None
    exit_reason: str | None
    price_scale: float
    price_scale_ok: bool

    @property
    def open_at_end(self) -> bool:
        """True when the bars ran out before the trade closed."""
        return self.exit is None

    @property
    def r_multiple(self) -> float | None:
        """The result in R, or ``None`` while the trade is still open.

        Both terms are prices from the bar series — the exit and the entry are bar
        prices, and :attr:`risk` was priced off the bars' own ADR — so a constant
        rescale of the whole series cancels and R does not move.
        """
        if self.exit is None or self.risk <= 0:
            return None
        return (self.exit.price - self.entry.price) / self.risk


def trail_ma(bars: Sequence[Bar], window: int) -> float | None:
    """The trail's moving average: the mean **unadjusted** close over ``window``
    bars ending at the last one given.

    Distinct from :func:`screener.indicators.sma`, which averages ``adj_close`` for
    returns. The trail is compared against a close and lives in the same price the
    trigger and the stop do — see the module docstring. ``None`` until the window is
    full: an average of four closes is not a 10MA, and approximating one would let a
    trade exit on a level that never existed.
    """
    if window <= 0 or len(bars) < window:
        return None
    return sum(b.close for b in bars[-window:]) / window


def trail_ma_window(contract: RunContract) -> int:
    """Arm B's trail window, read from the contract's ``exit.arm_b`` cell.

    The 10 in "10MA" belongs to the contract, not to this module, so a later run
    that sweeps it changes one cell and this code is untouched.
    """
    return int(contract.value(EXIT_ARM_B_KEY)["trail_ma"])


def check_trail_mechanic(contract: RunContract) -> None:
    """Refuse a contract whose trail mechanic is not the one implemented here.

    The mechanic is recorded as *arbitrary* precisely so a later run can vary it
    deliberately (story 39). Varying the cell without varying the code would leave a
    run whose contract and behaviour disagree while both look right — the failure
    :func:`backtest.run.check_detection_gate` exists to prevent for the gate, in the
    one other place a contract cell and this package's code have to agree.
    """
    declared = contract.value(EXIT_TRAIL_MECHANIC_KEY)
    if declared != TRAIL_MECHANIC:
        raise ContractDrift(
            f"contract {EXIT_TRAIL_MECHANIC_KEY!r} is {declared!r} but "
            f"backtest.simulate implements {TRAIL_MECHANIC!r}; a changed mechanic "
            "is a new run recorded beside the old one, not a reinterpretation of "
            "this one"
        )


def simulate_arm_b(
    bars: Sequence[Bar],
    detection: Detection,
    *,
    market: str,
    contract: RunContract,
) -> SimulatedTrade | None:
    """Take one detection mechanically on arm B, or return ``None`` if it never broke.

    ``bars`` is the symbol's whole history; this function slices it to the deciding
    session at every step rather than trusting the caller to have cut it, so a
    caller that passes more bars than existed at the time cannot change the answer.
    That is the property ``test_appending_later_sessions_never_moves_a_settled_trade``
    pins.

    Returns ``None`` — never a trade with an empty entry — when the setup produced
    no trade at all: the detection's session is not in the bars, the ADR that
    denominates R is undefined, the next session did not close through the trigger,
    or the market never opened again to fill it.
    """
    check_trail_mechanic(contract)
    window = trail_ma_window(contract)

    idx = bar_index(bars, detection.session)
    if idx is None:
        return None

    # Everything that denominates the trade is measured at the detection's own
    # session, on the bars that existed then.
    at_decision = trailing_bars(bars, detection.session, ADR_WINDOW)
    a = adr_abs(at_decision)
    if a is None or a <= 0:
        return None
    risk = detection.stopw_adr * a
    if risk <= 0:
        return None

    # The one absolute-price comparison the ADR geometry cannot make immune: a
    # close persisted with the detection against the close on the bar it names.
    bar_close = bars[idx].close
    price_scale = detection.close / bar_close if bar_close else 0.0

    # The break: the app's own definition, on the session after the detection.
    if idx + 1 >= len(bars):
        return None
    break_bar = bars[idx + 1]
    if break_bar.close <= detection.trigger:
        return None

    # The fill: the next session's open. A break with no session after it is a
    # signal that never became a trade.
    if idx + 2 >= len(bars):
        return None
    fill_bar = bars[idx + 2]

    stop_price = detection.stop_price
    exit_signal, exit_decision, reason = _walk_out(
        bars, idx + 2, stop_price=stop_price, window=window
    )

    return SimulatedTrade(
        market=market,
        symbol=detection.symbol,
        arm=ARM_B,
        detection_session=detection.session,
        trigger=Decision(session=detection.session, price=detection.trigger),
        breakout=Decision(session=break_bar.session, price=break_bar.close),
        entry=Decision(session=fill_bar.session, price=fill_bar.open),
        stop=Decision(session=detection.session, price=stop_price),
        risk=risk,
        exit_signal=exit_signal,
        exit=exit_decision,
        exit_reason=reason,
        price_scale=price_scale,
        price_scale_ok=PRICE_SCALE_MIN <= price_scale <= PRICE_SCALE_MAX,
    )


def _walk_out(
    bars: Sequence[Bar],
    start: int,
    *,
    stop_price: float,
    window: int,
) -> tuple[Decision | None, Decision | None, str | None]:
    """Walk forward from the fill and return ``(signal, exit, reason)``.

    Within a session the **stop is checked first**. It rests in the market all day
    and the trail is a decision taken at the close, so a bar that trades through the
    stop and then closes back above the MA ended the trade — reading it the other
    way would let a losing trade be rescued by the very bar that ended it.

    A session that *opens* under the stop fills at the open, not at the stop. A stop
    is an order, not a guarantee; filling at the stop price would credit the
    simulation with liquidity that did not exist, and would do it precisely on the
    trades a gap ran away from — the direction that flatters an equity curve.

    Returns ``(None, None, None)`` when the bars run out with the trade still open.
    """
    for i in range(start, len(bars)):
        bar = bars[i]
        if bar.low <= stop_price:
            fill = min(bar.open, stop_price)
            decision = Decision(session=bar.session, price=fill)
            return decision, decision, EXIT_STOP

        ma = trail_ma(bars[: i + 1], window)
        if ma is not None and bar.close < ma:
            if i + 1 >= len(bars):
                # Signalled, but the market never opened again to fill it. The
                # trade is open: a signal is not a fill.
                return None, None, None
            nxt = bars[i + 1]
            return (
                Decision(session=bar.session, price=bar.close),
                Decision(session=nxt.session, price=nxt.open),
                EXIT_TRAIL,
            )
    return None, None, None


def simulate_market(
    store: Store,
    denominator: DenominatorStore,
    market: str,
    contract: RunContract,
    *,
    include_burn_in: bool = False,
) -> list[SimulatedTrade]:
    """Every arm-B trade the persisted denominator produces for one market.

    Reads the rows :mod:`backtest.run` wrote and the bars they were computed from.
    Burn-in sessions are excluded by default for the reason they are flagged at all:
    a warm-up session is persisted and never measured (story 76), so a trade taken
    off one would be a result resting on an unsettled chain.

    Bars are read once per symbol rather than once per detection — a fourteen-year
    run names the same symbol on hundreds of sessions, and re-reading its whole
    history each time is the difference between minutes and hours.
    """
    check_trail_mechanic(contract)
    bars_by_symbol: dict[str, list[Bar]] = {}
    trades: list[SimulatedTrade] = []
    for row in denominator.sessions(market):
        if row.burn_in and not include_burn_in:
            continue
        for scored in denominator.detections(market, row.session):
            symbol = scored.detection.symbol
            if symbol not in bars_by_symbol:
                bars_by_symbol[symbol] = store.bars(market, symbol)
            trade = simulate_arm_b(
                bars_by_symbol[symbol],
                scored.detection,
                market=market,
                contract=contract,
            )
            if trade is not None:
                trades.append(trade)
    return trades


def price_scale_drops(trades: Sequence[SimulatedTrade]) -> int:
    """How many trades the price-scale flag would drop.

    A number rather than a filter, because the flag's whole purpose is to make the
    absolute-price comparisons that are *not* rescale-immune visible (story 84). A
    function that quietly removed them would hide the very quantity it exists to
    report.
    """
    return sum(1 for t in trades if not t.price_scale_ok)


def simulate_report(
    contract: RunContract, trades: Sequence[SimulatedTrade]
) -> dict[str, Any]:
    """The arm's result as a stamped payload: the contract, the counts, the drops.

    Stamped through :func:`backtest.result.stamp_result` like every other figure the
    package emits, so the price-scale count travels with the result rather than in a
    commit message — and so two runs under different contracts are distinguishable
    from their serialised output alone.
    """
    closed = [t for t in trades if t.r_multiple is not None]
    return stamp_result(
        contract,
        {
            "arm": ARM_B,
            "trail_ma": trail_ma_window(contract),
            "trail_mechanic": TRAIL_MECHANIC,
            "trades": len(trades),
            "closed": len(closed),
            "open_at_end": len(trades) - len(closed),
            "price_scale_dropped": price_scale_drops(trades),
            "total_r": sum(t.r_multiple for t in closed),
        },
    )
