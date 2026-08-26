"""The three exit arms: turning a persisted detection into trades (issues #189 and
#190, PRD #182 Phase 4).

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
6. **The scale**, on arm A only, takes ``scale_fraction`` of the position off at
   the close of the ``scale_day``-th session after entry.

A detection whose next session does not break produces **no trade**, and that is a
measurement rather than a dropped row: the share of detections that trigger is one
of the figures the denominator exists to produce.

The three arms, and why there are three
---------------------------------------
Steps 1 to 4 are computed once and shared, as an :class:`Entry` — one value the
arms are handed rather than a stretch of code three arms happen to agree about. So
a difference between the arms' results is attributable to the exit alone, which is
the only thing running three of them can answer, and the reason
``test_the_three_arms_share_one_entry_and_one_stop`` asserts the sharing rather
than trusting it.

The entry also carries the answer a trade cannot give: **why** a detection produced
nothing. :func:`simulate_arm` collapses every non-fill into ``None``, which is
right for a simulator and useless for a figure — "the next session did not break"
is a resolved miss and "the bars end here" is the window's edge, and
:mod:`backtest.figures` has to tell them apart to report the share of detections
that trigger at all (issue #193). See :data:`ENTRY_FILLED` and its neighbours.

- **Arm A** is the trader's documented behaviour: 50% off at the close of the
  fifth session after entry, remainder on a 10MA trail. Its R is **two-legged**,
  position-weighted per leg and summed, so half a position exiting at +2R
  contributes 1R. It has no counterpart in the reference set, so it is measured and
  never anchored — a fact its report carries rather than a reader remembering it.
- **Arm B** is a pure 10MA trail, and the arm the pre-registered primary metric is
  computed on.
- **Arm C** is a pure 20MA trail. B and C are the two directly comparable to the
  reference set's simulated exits, which is what keeps the reference anchors usable.

Two arbitrary mechanics, recorded as arbitrary
----------------------------------------------
Nothing derives "the fifth session" (:data:`SCALE_MECHANIC`) or "a close through
the MA signals and the next open fills" (:data:`TRAIL_MECHANIC`). Both are choices,
both are recorded in the contract as such, and :func:`check_arm_mechanics` refuses
a run whose cells have dropped the admission — because a mechanic that looks
principled is one nobody thinks to sweep, and a later run should vary these
deliberately rather than rediscover them.

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
Costs (#191) are not here: every figure this module reports is before commission
and slippage, and the contract's ``costs`` cell is applied by the phase that
computes the primary metric. So ``total_r`` here is not the headline and must not
be read as one.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Sequence

from screener.bars import Bar
from screener.detection import Detection
from screener.indicators import ADR_WINDOW, adr
from screener.store import Store

from .chain import bar_index, trailing_bars
from .contract import (
    DEFAULT_CONTRACT,
    EXIT_ARM_A_KEY,
    EXIT_ARM_B_KEY,
    EXIT_ARM_C_KEY,
    EXIT_TRAIL_MECHANIC_KEY,
    RunContract,
)
from .denominator import DenominatorStore, denominator_path
from .result import stamp_result
from .run import ContractDrift

# The three arms. They share one entry and one stop by construction and differ in
# the exit alone, which is the only reason running three of them says anything
# about exits.
#
# - **A** is the trader's documented behaviour: 50% off at the close of the fifth
#   session after entry, remainder on a 10MA trail. It has no counterpart in the
#   reference set, so it is measured and never anchored.
# - **B** is the pure 10MA trail, and the arm the pre-registered primary metric is
#   computed on (contract ``metric.primary``).
# - **C** is a pure 20MA trail.
ARM_A = "A"
ARM_B = "B"
ARM_C = "C"
ARMS = (ARM_A, ARM_B, ARM_C)


@dataclass(frozen=True)
class ArmSpec:
    """What this module knows about an arm that the contract does not say.

    Two things, kept together so a fourth arm is one entry rather than a hunt
    through parallel tables:

    - ``cell`` is which contract cell holds the arm's exit. The contract names the
      arms and their numbers; which arm reads which cell is a fact about this code.
    - ``comparable_to_reference`` is a fact about the **reference study**, not a
      choice this run makes, which is why it is not a contract cell. Arms B and C
      are directly comparable to the reference set's two simulated exits, which is
      what keeps its anchors usable; arm A has no counterpart there, so it is
      measured and never anchored. It rides on the report rather than living in a
      reader's memory, because a figure whose comparability is remembered rather
      than printed gets compared.
    """

    cell: str
    comparable_to_reference: bool


ARM_SPECS = {
    ARM_A: ArmSpec(cell=EXIT_ARM_A_KEY, comparable_to_reference=False),
    ARM_B: ArmSpec(cell=EXIT_ARM_B_KEY, comparable_to_reference=True),
    ARM_C: ArmSpec(cell=EXIT_ARM_C_KEY, comparable_to_reference=True),
}

# The three ways a leg of a position can come off. Recorded on the leg rather than
# inferred from its prices, because a trail fill that happens to land on the stop is
# a different event from a stop — and only one of them is evidence about the trail.
# ``EXIT_SCALE`` is the odd one out: it is a *planned* partial, taken because the
# calendar said so and not because the market did anything.
EXIT_TRAIL = "trail"
EXIT_STOP = "stop"
EXIT_SCALE = "scale"

# The two exit mechanics this module implements. Both are recorded in the contract
# as **arbitrary** — nothing derives "the fifth session" or "fill at the next open"
# — so that a later run varies them deliberately instead of rediscovering them
# (story 39). :func:`check_arm_mechanics` refuses a contract that says otherwise.
TRAIL_MECHANIC = "close_through_ma_signals_fill_next_open"
SCALE_MECHANIC = "close_of_nth_session_after_entry"

# The third arbitrary mechanic, and the one that was nearly left as a code comment:
# on a scaling arm the trail is live **from the fill**, not from the scale day. So a
# runner that rolls over before day 5 takes the whole position out and the scale
# never happens — which on a fast breakout degenerates arm A into arm B. Nothing
# derives that reading either, so it is a contract cell (``trail_live_from``) like
# the other two, and this is the only value implemented here.
TRAIL_LIVE_FROM_FILL = "fill"

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


# The five ways an entry can end, and they are not interchangeable (issue #193).
#
# :func:`simulate_arm` collapses all four of the non-fills into ``None``, which is
# right for a simulator — none of them is a trade — and useless for a figure. The
# share of detections that trigger is one of the denominator's headline numbers,
# and it has a *denominator*: only the detections something actually asked belong
# in it.
#
# - :data:`ENTRY_FILLED` — it broke and the next session opened to fill it.
# - :data:`ENTRY_NO_BREAK` — the deciding session closed under the trigger. A
#   **resolved miss**, and the only one of these four that belongs in the trigger
#   denominator.
# - :data:`ENTRY_PENDING` — the bars end on the detection itself, so nothing has
#   decided the break yet. The window's edge, not a failure.
# - :data:`ENTRY_UNFILLED` — it broke, and the market never opened again. The
#   window's edge again: a signal that never became a trade.
# - :data:`ENTRY_UNDECIDABLE` — the detection's own session is not in the bars, or
#   the ADR that denominates R is undefined. A fact about the store's coverage.
#
# Folding the three non-answers into the miss would deflate the trigger share by
# however many detections the window happened to end on — in the direction that
# makes the detector look worse, which is the direction nobody investigates.
ENTRY_FILLED = "filled"
ENTRY_NO_BREAK = "no_break"
ENTRY_PENDING = "pending"
ENTRY_UNFILLED = "unfilled"
ENTRY_UNDECIDABLE = "undecidable"

# The outcomes in which the detection's own trigger was actually traded through.
# Both are a **trigger**; they differ in whether the window lasted long enough to
# fill one.
ENTRY_BROKE = (ENTRY_FILLED, ENTRY_UNFILLED)

# The outcomes something asked and got an answer to. The trigger share's
# denominator, and the reason it is a tuple here rather than a negation at each
# call site: "which outcomes count" is one decision, and a second copy of it is a
# second place for it to drift.
ENTRY_DECIDED = (ENTRY_FILLED, ENTRY_NO_BREAK, ENTRY_UNFILLED)


@dataclass(frozen=True)
class ExitLeg:
    """One part of a position coming off, and the share of the position it was.

    A leg is the unit R is computed in, because arm A takes its position off in
    two pieces at two prices and the result is neither of them: half a position
    exiting at +2R contributes 1R, not 2R and not the average of the legs. Making
    the weight a field rather than a convention means the arithmetic cannot be got
    right in one place and wrong in another.

    ``signal`` and ``exit`` are the same decision for a stop and for a scale — both
    are filled on the session that decides them — and one session apart for a
    trail, which signals on a close and fills at the next open.
    """

    weight: float
    signal: Decision
    exit: Decision
    reason: str


@dataclass(frozen=True)
class Entry:
    """Everything the three arms share, and why it did or did not become a trade.

    Steps 1 to 4 of the mechanic — trigger, break, fill and stop — are computed
    once and handed to every arm, which is the whole reason a difference between
    the arms is attributable to the exit alone. Making that a **value** rather than
    a stretch of :func:`simulate_arm` is what lets the sharing be a fact about the
    code instead of three code paths that happen to agree
    (``test_a_filled_entry_carries_the_prices_every_arm_shares``).

    It also carries the answer :mod:`backtest.figures` needs and a trade cannot
    give: :attr:`outcome` says *why* a detection produced nothing, and the four
    non-fills mean four different things (see :data:`ENTRY_FILLED` and its
    neighbours). Every price field is ``None`` on an outcome that never reached the
    step that would have set it — absent, never a zero standing in for a price the
    session did not have.
    """

    outcome: str
    symbol: str
    detection_session: date
    trigger: Decision | None = None
    break_signal: Decision | None = None
    fill: Decision | None = None
    stop_price: Decision | None = None
    stop_width: float | None = None
    price_scale: float | None = None

    @property
    def filled(self) -> bool:
        """True when the entry became a position. The one outcome an arm can run."""
        return self.outcome == ENTRY_FILLED

    @property
    def triggered(self) -> bool:
        """True when the detection's own trigger was traded through.

        Includes the break that never got a session to fill on: it triggered, and
        the window ended. The two facts are different and only one of them is about
        the detector.
        """
        return self.outcome in ENTRY_BROKE

    @property
    def decided(self) -> bool:
        """True when something asked whether this detection would trigger.

        The trigger share's denominator. A detection the bars end on has not failed
        to trigger — nothing has asked it yet — and one whose session the store
        never covered was never askable at all.
        """
        return self.outcome in ENTRY_DECIDED

    @property
    def price_scale_ok(self) -> bool:
        """True when the entry's one absolute-price comparison sits in the band.

        ``False`` where the scale is unknown, which is the safe direction: an
        unmeasured comparison is not a verified one.
        """
        return (
            self.price_scale is not None
            and PRICE_SCALE_MIN <= self.price_scale <= PRICE_SCALE_MAX
        )


def entry(bars: Sequence[Bar], detection: Detection) -> Entry:
    """The entry every arm shares, and the reason it did or did not fill.

    Steps 1 to 4 of the module's mechanic, computed once: the detection's own
    trigger, the break on the session after it, the fill at the next open, and the
    detection's own stop. Nothing here depends on the arm, and nothing here reads a
    bar after the session that decides it — every slice goes through
    :func:`~backtest.chain.trailing_bars` or an index at or before the decision.

    ``bars`` is the symbol's whole history; this function cuts it itself rather
    than trusting the caller to have cut it, so a caller holding more bars than
    existed at the time cannot change the answer.
    """
    idx = bar_index(bars, detection.session)
    if idx is None:
        return Entry(ENTRY_UNDECIDABLE, detection.symbol, detection.session)

    # Everything that denominates the trade is measured at the detection's own
    # session, on the bars that existed then.
    at_decision = trailing_bars(bars, detection.session, ADR_WINDOW)
    a = adr(at_decision)
    if a is None or a <= 0:
        return Entry(ENTRY_UNDECIDABLE, detection.symbol, detection.session)
    stop_width = detection.stopw_adr * a * detection.trigger
    if stop_width <= 0:
        return Entry(ENTRY_UNDECIDABLE, detection.symbol, detection.session)

    # The one absolute-price comparison the ADR geometry cannot make immune: a
    # close persisted with the detection against the close on the bar it names.
    bar_close = bars[idx].close
    price_scale = detection.close / bar_close if bar_close else 0.0
    trigger = Decision(session=detection.session, price=detection.trigger)
    stop_price = Decision(session=detection.session, price=detection.stop_price)
    partial = {
        "symbol": detection.symbol,
        "detection_session": detection.session,
        "trigger": trigger,
        "stop_price": stop_price,
        "stop_width": stop_width,
        "price_scale": price_scale,
    }

    # The break: the app's own definition, on the session after the detection.
    if idx + 1 >= len(bars):
        return Entry(ENTRY_PENDING, **partial)
    break_bar = bars[idx + 1]
    if break_bar.close <= detection.trigger:
        return Entry(ENTRY_NO_BREAK, **partial)
    break_signal = Decision(session=break_bar.session, price=break_bar.close)

    # The fill: the next session's open. A break with no session after it is a
    # signal that never became a trade.
    if idx + 2 >= len(bars):
        return Entry(ENTRY_UNFILLED, break_signal=break_signal, **partial)
    fill_bar = bars[idx + 2]
    return Entry(
        ENTRY_FILLED,
        break_signal=break_signal,
        fill=Decision(session=fill_bar.session, price=fill_bar.open),
        **partial,
    )


@dataclass(frozen=True)
class ExitPlan:
    """One arm's exit, read off the contract: a trail, and optionally a scale.

    Every arm trails; arm A additionally takes ``scale_fraction`` off at the close
    of the ``scale_day``-th session after entry. A plan with ``scale_day`` of
    ``None`` is a pure trail, which is arms B and C — so the three arms are one
    mechanic parameterised, not three implementations to keep in agreement.

    ``trail_live_from`` says when the trail starts watching. Only
    :data:`TRAIL_LIVE_FROM_FILL` is implemented, and it matters only to a scaling
    arm: it is what makes a runner that rolls over before the scale day take the
    whole position out.
    """

    trail_ma: int
    scale_day: int | None = None
    scale_fraction: float = 0.0
    trail_live_from: str = TRAIL_LIVE_FROM_FILL


@dataclass(frozen=True)
class SimulatedTrade:
    """One detection, taken mechanically, on one exit arm.

    The **simulated trade** CONTEXT.md names: a counterfactual built from the
    detector's own decision, never an executed trade. Everything down to the fill is
    shared by every arm by construction — the arms differ in :attr:`legs` and in
    nothing else — which is the only reason running three arms answers anything
    about exits.

    A trade is **open** while any of the position is still on: the bars ran out
    before the stop or the trail fired, or arm A scaled and its runner never
    exited. An open trade has no R, because closing it at the last available close
    would invent an exit the rules never gave — systematically, for every name
    still running at the end of the window. Half of one is no better: an equity
    curve built from the legs that happened to close is the same bias, harder to
    see, because the trade would look closed.
    """

    market: str
    symbol: str
    arm: str
    detection_session: date
    trigger: Decision
    break_signal: Decision
    entry: Decision
    stop_price: Decision
    # The R denominator: the detection's own stop width, in price units. Named
    # for the glossary's **Stop width** — never "risk", which CONTEXT.md
    # reserves against precisely because a stop budget and the risk taken on a
    # filled position are different quantities. Rebuilt from the detection's
    # ``stopw_adr`` against the ADR of the *bars* at the deciding session, which
    # is the detector's own formula on the same inputs — so it equals
    # ``detection.stop`` whenever the two price scales agree, and stays in ADR
    # units where they do not.
    stop_width: float
    # The position coming off, in order. One leg for arms B and C and for any trade
    # the stop ended; two for an arm A that reached its scale day. A trade whose
    # legs do not add up to a whole position is still running — the bars ran out
    # under it — and that is how :attr:`open_at_end` reads it.
    legs: tuple[ExitLeg, ...]
    price_scale: float
    price_scale_ok: bool

    @property
    def closed(self) -> bool:
        """True when the whole position has come off."""
        return abs(sum(leg.weight for leg in self.legs) - 1.0) < 1e-9

    @property
    def open_at_end(self) -> bool:
        """True when the bars ran out with any of the position still on."""
        return not self.closed

    @property
    def exit(self) -> Decision | None:
        """The decision that closed the trade, or ``None`` while it is still open.

        The *last* leg, not the first: arm A's scale takes off half a position, and
        a trade whose runner is still running has not exited. Reading the scale as
        the exit would report half a trade as a whole one.
        """
        return self.legs[-1].exit if self.closed else None

    @property
    def exit_signal(self) -> Decision | None:
        """The decision behind :attr:`exit` — one session earlier for a trail."""
        return self.legs[-1].signal if self.closed else None

    @property
    def exit_reason(self) -> str | None:
        """Why the trade ended: :data:`EXIT_TRAIL` or :data:`EXIT_STOP`.

        Never :data:`EXIT_SCALE`, and not by filtering: a scale takes a *fraction*
        of the position, so a trade whose last leg is a scale has not closed and
        reports ``None`` here.
        """
        return self.legs[-1].reason if self.closed else None

    @property
    def r_multiple(self) -> float | None:
        """The result in R, or ``None`` while any of the position is still on.

        **Position-weighted per leg and summed**, which is the whole of what a
        two-legged exit means: half a position exiting at +2R contributes 1R. The
        obvious alternatives are both wrong in ways the output cannot show — summing
        the legs' R doubles a scaled trade, averaging them mis-weights any exit that
        is not a clean half.

        Every term is a price from the bar series — the exits and the entry are bar
        prices, and :attr:`stop_width` was priced off the bars' own ADR — so a
        constant rescale of the whole series cancels and R does not move.
        """
        if not self.closed or self.stop_width <= 0:
            return None
        return sum(
            leg.weight * (leg.exit.price - self.entry.price) for leg in self.legs
        ) / self.stop_width


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


def exit_plan(contract: RunContract, arm: str) -> ExitPlan:
    """One arm's exit, read from its own contract cell.

    Every number in an exit — the 10 in "10MA", the 5 in "day 5", the 50% — belongs
    to the contract and not to this module, so a later run that sweeps any of them
    changes one cell and leaves this code untouched. An arm the contract does not
    name is a hard error rather than an empty plan: an unknown arm that simply
    produced no trades would report a clean zero, which is indistinguishable from a
    correctly-run arm that nothing triggered.
    """
    if arm not in ARM_SPECS:
        raise ValueError(
            f"unknown exit arm {arm!r}; the contract names {sorted(ARM_SPECS)}"
        )
    cell = contract.value(ARM_SPECS[arm].cell)
    scale_day = cell.get("scale_day")
    return ExitPlan(
        trail_ma=int(cell["trail_ma"]),
        scale_day=None if scale_day is None else int(scale_day),
        scale_fraction=float(cell.get("scale_fraction", 0.0)),
        trail_live_from=str(cell.get("trail_live_from", TRAIL_LIVE_FROM_FILL)),
    )


def check_arm_mechanics(contract: RunContract, arm: str) -> None:
    """Refuse a contract whose exit mechanics are not the ones implemented here.

    The trail mechanic must be the one this module implements
    (:func:`check_trail_mechanic`). The rest applies only to an arm that scales,
    and is two claims: the trail is live from the fill, and the arm still records
    its mechanics as **arbitrary**. All three mechanics are arbitrary in fact; a
    contract that has quietly dropped the admission describes a run whose exits
    look principled, and a run whose exits look principled is one whose sweep
    nobody thinks to do.
    """
    check_trail_mechanic(contract)
    plan = exit_plan(contract, arm)
    if plan.scale_day is None:
        return
    key = ARM_SPECS[arm].cell
    if plan.trail_live_from != TRAIL_LIVE_FROM_FILL:
        raise ContractDrift(
            f"contract {key!r} says the trail is live from "
            f"{plan.trail_live_from!r} but backtest.simulate implements "
            f"{TRAIL_LIVE_FROM_FILL!r}; a trail that starts watching somewhere "
            "else is a different arm recorded beside this one, not a "
            "reinterpretation of it"
        )
    if contract.value(key).get("arbitrary_mechanics") is not True:
        raise ContractDrift(
            f"contract {key!r} scales at session {plan.scale_day} on the "
            f"{SCALE_MECHANIC!r} mechanic but does not record its mechanics as "
            "arbitrary; neither the scale day, nor the trail fill, nor the trail "
            "being live from the fill derives from anything, and recording that "
            "is what lets a later run vary them"
        )


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


def simulate_arm(
    bars: Sequence[Bar],
    detection: Detection,
    *,
    market: str,
    contract: RunContract,
    arm: str,
) -> SimulatedTrade | None:
    """Take one detection mechanically on one arm, or ``None`` if it never broke.

    The arm is a parameter of the *exit* and of nothing else: everything down to
    the fill is computed the same way for all three, which is what makes a
    difference between their results attributable to the exit alone. Running the
    arms separately therefore cannot make them disagree about an entry — the
    property ``test_the_three_arms_share_one_entry_and_one_stop`` pins.

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
    check_arm_mechanics(contract, arm)
    return take_entry(bars, entry(bars, detection), market=market,
                      contract=contract, arm=arm)


def take_entry(
    bars: Sequence[Bar],
    e: Entry,
    *,
    market: str,
    contract: RunContract,
    arm: str,
) -> SimulatedTrade | None:
    """Run one arm's exit off an already-computed :class:`Entry`.

    Split out from :func:`simulate_arm` so a caller that needs the entry's
    :attr:`~Entry.outcome` *and* its trades — :mod:`backtest.figures`, counting
    what triggered before measuring what paid — computes the shared entry once and
    walks it out per arm, rather than re-deriving it three times and once more for
    the count.

    ``None`` when the entry never filled: there is no position to walk out.
    """
    if not e.filled:
        return None
    plan = exit_plan(contract, arm)
    # The fill's own index, re-derived rather than carried on the entry: it is a
    # position in *this* caller's bars, and a value that travels can be read
    # against a different series than the one it was measured in.
    start = bar_index(bars, e.fill.session)
    return SimulatedTrade(
        market=market,
        symbol=e.symbol,
        arm=arm,
        detection_session=e.detection_session,
        trigger=e.trigger,
        break_signal=e.break_signal,
        entry=e.fill,
        stop_price=e.stop_price,
        stop_width=e.stop_width,
        legs=_walk_out(bars, start, stop_price=e.stop_price.price, plan=plan),
        price_scale=e.price_scale,
        price_scale_ok=e.price_scale_ok,
    )


def _walk_out(
    bars: Sequence[Bar],
    start: int,
    *,
    stop_price: float,
    plan: ExitPlan,
) -> tuple[ExitLeg, ...]:
    """Walk forward from the fill and return the legs the position came off in.

    ``start`` is the fill session — day 0 — so the plan's scale day counts from it:
    "day 5" is the close of the fifth session *after* entry, which is
    ``bars[start + 5]``. That is :data:`SCALE_MECHANIC`, and it is arbitrary.

    Within a session the order is **stop, then scale, then trail**, and each step is
    a claim about when the decision was taken:

    - The **stop** rests in the market all day, so a bar that trades through it and
      then closes back above the MA ended the trade. Reading it the other way would
      let a losing trade be rescued by the very bar that ended it. A session that
      *opens* under the stop fills at the open, not at the stop: a stop is an order,
      not a guarantee, and filling at the stop price would credit the simulation
      with liquidity that did not exist on precisely the trades a gap ran away from.
      It takes whatever is left of the position, which is the whole of it before the
      scale day — a plan that has not executed holds no position.
    - The **scale** is taken at that session's close, by the calendar.
    - The **trail** signals at the same close and fills at the next open. It is live
      from the fill rather than from the scale day, so a runner that rolls over
      before day 5 takes the whole position out and the scale never happens. That
      reading is a third arbitrary choice and is asserted rather than assumed
      (``test_arm_as_stop_takes_the_whole_position_when_it_fires_before_day_five``
      and its trail counterpart).

    Returns the legs taken, which may be empty (the bars ran out with the position
    whole) or short of a whole position (they ran out with the runner still on).
    """
    remaining = 1.0
    legs: list[ExitLeg] = []
    for i in range(start, len(bars)):
        bar = bars[i]
        if bar.low <= stop_price:
            fill = min(bar.open, stop_price)
            decision = Decision(session=bar.session, price=fill)
            legs.append(ExitLeg(remaining, decision, decision, EXIT_STOP))
            return tuple(legs)

        if plan.scale_day is not None and i == start + plan.scale_day:
            # A planned partial: decided and filled on the same close, because
            # nothing about the market triggered it and there is no signal to wait
            # a session on.
            decision = Decision(session=bar.session, price=bar.close)
            legs.append(ExitLeg(plan.scale_fraction, decision, decision, EXIT_SCALE))
            remaining -= plan.scale_fraction

        ma = trail_ma(bars[: i + 1], plan.trail_ma)
        if ma is not None and bar.close < ma:
            if i + 1 >= len(bars):
                # Signalled, but the market never opened again to fill it. Whatever
                # is left is still on: a signal is not a fill.
                return tuple(legs)
            nxt = bars[i + 1]
            legs.append(
                ExitLeg(
                    remaining,
                    Decision(session=bar.session, price=bar.close),
                    Decision(session=nxt.session, price=nxt.open),
                    EXIT_TRAIL,
                )
            )
            return tuple(legs)
    return tuple(legs)


@dataclass(frozen=True)
class DetectionOutcome:
    """What became of one persisted detection: its entry, and a trade per arm.

    The unit :mod:`backtest.figures` counts in, and the reason it can count at all.
    A list of trades answers "what paid"; it cannot answer "how many of the setups
    the detector named ever triggered", because a detection that never broke left
    no trade to be counted. Both questions are the denominator's, so the walk emits
    the detection *and* its outcome rather than only the trades that survived it.

    ``trades`` holds one entry per arm that produced a position and is **empty**
    when the entry never filled — the arms cannot disagree about that, because they
    share the entry.
    """

    session: date
    detection: Detection
    entry: Entry
    trades: dict[str, SimulatedTrade]


def walk_detections(
    store: Store,
    denominator: DenominatorStore,
    market: str,
    contract: RunContract,
    *,
    arms: Sequence[str] = ARMS,
    include_burn_in: bool = False,
) -> list[DetectionOutcome]:
    """Every persisted detection in the window, with its entry and its trades.

    The one pass over the denominator, shared by :func:`simulate_market` and by
    :mod:`backtest.figures`. Two callers walking the same fourteen years
    separately would read every symbol's whole history twice and — worse — could
    disagree about which detections were in the window at all, which is exactly
    the kind of divergence a rate reported beside a total makes invisible.

    Burn-in sessions are excluded by default for the reason they are flagged at
    all: a warm-up session is persisted and never measured (story 76).

    Bars are read once per symbol rather than once per detection — a fourteen-year
    run names the same symbol on hundreds of sessions, and re-reading its whole
    history each time is the difference between minutes and hours.
    """
    for arm in arms:
        check_arm_mechanics(contract, arm)
    ran = [arm for arm in ARMS if arm in arms]
    bars_by_symbol: dict[str, list[Bar]] = {}
    out: list[DetectionOutcome] = []
    for row in denominator.sessions(market):
        if row.burn_in and not include_burn_in:
            continue
        for scored in denominator.detections(market, row.session):
            detection = scored.detection
            symbol = detection.symbol
            if symbol not in bars_by_symbol:
                bars_by_symbol[symbol] = store.bars(market, symbol)
            bars = bars_by_symbol[symbol]
            e = entry(bars, detection)
            trades = {}
            for arm in ran:
                trade = take_entry(
                    bars, e, market=market, contract=contract, arm=arm
                )
                if trade is not None:
                    trades[arm] = trade
            out.append(
                DetectionOutcome(
                    session=row.session, detection=detection, entry=e, trades=trades
                )
            )
    return out


def simulate_market(
    store: Store,
    denominator: DenominatorStore,
    market: str,
    contract: RunContract,
    *,
    arms: Sequence[str] = ARMS,
    include_burn_in: bool = False,
) -> list[SimulatedTrade]:
    """Every trade the persisted denominator produces for one market, on every arm.

    A detection appears **once per arm** and never more: the arms are exits taken on
    one entry, so three arms over one detection is three trades and not three
    detections. ``arms`` narrows which exits run and nothing else — the entry each
    of them is taken on does not depend on which arms ran beside it.

    Reads the rows :mod:`backtest.run` wrote and the bars they were computed from.
    Burn-in sessions are excluded by default for the reason they are flagged at all:
    a warm-up session is persisted and never measured (story 76), so a trade taken
    off one would be a result resting on an unsettled chain.

    The trades :func:`walk_detections` produced, with the detections that produced
    nothing dropped. Those detections are not noise — the share that never
    triggered is one of the denominator's headline figures — so a caller that needs
    them takes the walk itself rather than inferring them from what is missing here.

    Within one detection the arms come out in :data:`ARMS` order rather than in the
    order ``arms`` spelled them. Changed deliberately in #193 and recorded here
    rather than left to be noticed: it makes the output diff-stable however a
    caller wrote its argument, which is the property :func:`simulate_report`
    already commits to for the same reason.
    """
    return [
        outcome.trades[arm]
        for outcome in walk_detections(
            store, denominator, market, contract,
            arms=arms, include_burn_in=include_burn_in,
        )
        for arm in ARMS
        if arm in outcome.trades
    ]


def closed_trades(trades: Sequence[SimulatedTrade]) -> list[SimulatedTrade]:
    """The trades whose whole position came off, and which therefore have an R.

    One line, and it lives here rather than at each call site because "closed" is a
    fact about :class:`SimulatedTrade` and two readers of it must not drift. Both
    :func:`arm_report` and :mod:`backtest.figures` split an arm's trades this way,
    and a second spelling of the test — ``t.closed`` rather than
    ``t.r_multiple is not None`` — would agree today and diverge the first time a
    trade could close with no computable R.
    """
    return [t for t in trades if t.r_multiple is not None]


def price_scale_drops(trades: Sequence[SimulatedTrade]) -> int:
    """How many trades the price-scale flag would drop.

    A number rather than a filter, because the flag's whole purpose is to make the
    absolute-price comparisons that are *not* rescale-immune visible (story 84). A
    function that quietly removed them would hide the very quantity it exists to
    report.
    """
    return sum(1 for t in trades if not t.price_scale_ok)


def arm_report(
    contract: RunContract, arm: str, trades: Sequence[SimulatedTrade]
) -> dict[str, Any]:
    """One arm's figures, and the exit they came from.

    ``trades`` may span arms; only this arm's are counted. The exit is named in the
    body rather than left to the arm letter, because a sweep that moved a window
    would otherwise leave two runs' figures labelled identically — and the whole
    point of three arms is that the exit is the only thing that differs.

    Not stamped with the contract: :func:`simulate_report` stamps the collection
    once, and a result cannot claim two contracts.
    """
    plan = exit_plan(contract, arm)
    mine = [t for t in trades if t.arm == arm]
    closed = closed_trades(mine)
    body: dict[str, Any] = {
        "arm": arm,
        "trail_ma": plan.trail_ma,
        "trail_mechanic": TRAIL_MECHANIC,
        "comparable_to_reference": ARM_SPECS[arm].comparable_to_reference,
        "trades": len(mine),
        "closed": len(closed),
        "open_at_end": len(mine) - len(closed),
        "price_scale_dropped": price_scale_drops(mine),
        "total_r": sum(t.r_multiple for t in closed),
    }
    if plan.scale_day is not None:
        body["scale_day"] = plan.scale_day
        body["scale_fraction"] = plan.scale_fraction
        body["scale_mechanic"] = SCALE_MECHANIC
    return body


def simulate_report(
    contract: RunContract,
    trades: Sequence[SimulatedTrade],
    *,
    arms: Sequence[str] = ARMS,
) -> dict[str, Any]:
    """Every arm's result as one stamped payload: the contract, the counts, the drops.

    All three arms in one result rather than three files, because the arms are only
    interesting beside each other: they share an entry and a stop, so the comparison
    *is* the finding and splitting it across payloads would make a reader
    reassemble it. Arms appear in :data:`ARMS` order, so the output is diff-stable.

    ``arms`` is the arms that were **run**, not the arms that produced something. An
    arm that ran and triggered nothing reports zeros; an arm that never ran is
    absent. Reporting only the arms present in ``trades`` would collapse those two
    into the same output, which is the confusion :func:`exit_plan` refuses an
    unknown arm to avoid.

    Stamped through :func:`backtest.result.stamp_result` like every other figure the
    package emits, so the price-scale count travels with the result rather than in a
    commit message — and so two runs under different contracts are distinguishable
    from their serialised output alone.
    """
    ran = [arm for arm in ARMS if arm in arms]
    return stamp_result(
        contract,
        {"arms": [arm_report(contract, arm, trades) for arm in ran]},
    )


def format_trades(report: dict[str, Any]) -> str:
    """The arms' results as a few lines a terminal can print.

    The price-scale count is on its own line rather than folded into a total,
    because it is the one figure here that is *about the data* rather than about
    the method, and a reader who skims must not miss that some trades' absolute
    prices could not be verified. Arm A carries "measured, not anchored" on its
    heading for the same reason: it has no counterpart in the reference set, and a
    figure whose comparability is remembered rather than printed gets compared.
    """
    lines: list[str] = []
    for body in report["arms"]:
        trail = f"{body['trail_ma']}MA trail"
        exit_rule = (
            f"{body['scale_fraction']:.0%} at the close of session "
            f"{body['scale_day']}, remainder on a {trail}"
            if "scale_day" in body
            else trail
        )
        anchor_note = (
            "" if body["comparable_to_reference"] else " — measured, not anchored"
        )
        lines += [
            f"arm {body['arm']} — {exit_rule} ({body['trail_mechanic']}){anchor_note}",
            f"  trades          {body['trades']}",
            f"  closed          {body['closed']}",
            f"  open at end     {body['open_at_end']}",
            f"  total R         {body['total_r']:+.2f}",
            f"  price-scale flag would drop {body['price_scale_dropped']} "
            f"of {body['trades']}",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Simulate every exit arm over a persisted denominator and report the results.

    The command that reproduces the arms::

        python -m backtest.simulate --store data/backtest_us.duckdb \\
            --market US --out-json references/backtest_arms_us.json

    All three arms run by default, because they are only interesting beside each
    other. ``--arm`` narrows the run to one; it changes which exits are taken and
    nothing about the entry they are taken on.

    Reads the bar store and the denominator :mod:`backtest.run` wrote beside it.
    Neither is written to: this phase consumes the denominator and produces
    figures, so it has no reason to hold either file open for writing and every
    reason not to.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument("--market", required=True)
    parser.add_argument(
        "--arm", action="append", choices=ARMS, default=None,
        help="run one arm rather than all three (repeatable)",
    )
    parser.add_argument(
        "--include-burn-in", action="store_true",
        help="also take trades off burn-in sessions (never for a measured result)",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable, contract-stamped result",
    )
    args = parser.parse_args(argv)

    arms = tuple(args.arm) if args.arm else ARMS
    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        trades = simulate_market(
            store, denominator, args.market, DEFAULT_CONTRACT,
            arms=arms,
            include_burn_in=args.include_burn_in,
        )
    finally:
        denominator.close()
        store.close()

    report = simulate_report(DEFAULT_CONTRACT, trades, arms=arms)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_trades(report))
    if args.out_json:
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
