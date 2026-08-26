"""The denominator figures: precision, at last (issue #193, PRD #182 Phase 5).

The figures no prior study in this repo could produce. `references/qullamaggie-replay-findings.md`
measures 828 executed entries, and every one of them is a trade a trader **took** —
so §9 states plainly that the study can report no precision and no false-positive
rate. It has a numerator and no denominator. #149 hit the same wall from the other
side and had to record 27,323 detections as *volume carrying no verdict*, which is
the honest limit of a study with no control group.

Those detections are exactly the population this module measures. Three figures,
per market and per year:

- **Detections per session** — the count, and the plot across the window.
- **The share that trigger** — a close through the detection's own trigger.
- **The share that reach a favourable outcome** — precision, per exit arm.

Every rate carries its coverage
-------------------------------
A rate whose denominator is not printed is a rate nobody can check, so every one
here is a :class:`Share` — a numerator, the count it was measured against, and a
``rate`` that is ``None`` rather than ``0.0`` when nothing was measured at all. A
``0/0`` reported as zero is a claim the data never made, and it is the shape a
thin regime cell or an empty year takes.

Two ways to deflate a rate silently, and what stops each
---------------------------------------------------------
Both errors push in the same direction — they make the method look worse — which
is the direction nobody investigates, so neither would be caught by reading the
output:

- **A detection the bars cannot answer is not a miss.** A detection sitting on the
  last session of the window has not failed to trigger; nothing has asked it yet.
  The trigger share's denominator is the *decided* detections only
  (:data:`~backtest.simulate.ENTRY_DECIDED`), and the rest are reported as
  :attr:`Figures.undecided` rather than folded into the miss.
- **A trade still running is not a loss.** Closing it at the last available close
  would invent an exit the rules never gave, systematically, for every name still
  running when the window ends. An open trade leaves precision's denominator and
  is reported as :attr:`ArmFigures.open_at_end`.

Precision and the win rate are different questions
---------------------------------------------------
They differ in the denominator and the difference is the whole point:

- **Precision** is favourable outcomes over every *answered* detection — the ones
  that never broke included. It is a figure about the **detector**: of everything
  it named, what share paid.
- **The win rate** is favourable outcomes over the trades that were actually
  taken. It is a figure about the **exit**, and it is the one directly comparable
  to the reference set's shape — 22.7% of his trades made money and the mean R was
  positive anyway, which is why a low win rate is judged against its right tail
  rather than on its own.

Reporting one as the other would quote a detector's precision as a trader's hit
rate, so both are computed and both are labelled.

Both are per arm, and the trigger share is not. The arms share one entry and one
stop, so what triggered cannot differ between them; what an exit then makes of the
position is exactly what differs, and a single precision figure would be a claim
about an exit it never named.

Before costs, and it says so
-----------------------------
Costs are #191's. A precision figure computed before commission and slippage
**overstates**, and by more on IDX than on US, where the contract's fees and
spread are an order of magnitude larger. The payload carries ``costs_applied:
false`` and the formatter prints it beside the number, because a caveat a reader
has to remember is a caveat a reader forgets.

The SMA50 overlap, stated wherever counts are reported
-------------------------------------------------------
The contract's universe gate is ``close > SMA50`` and the detector carries its own
trend logic, so the two overlap and detection counts fall against an unfiltered
run. **That is the gate working, not the detector becoming more selective** — and
the two effects get conflated by any reader not told. :data:`SMA50_OVERLAP_NOTE`
rides on the payload and prints in every market's section (PRD story 20).

A year that collapses is flagged rather than quietly reported
--------------------------------------------------------------
A count that collapses in a given year is a data hole, and it reads as a quiet
market until someone looks (story 77). Two flags, because two different things
collapse and only one of them is about the field:

- :attr:`YearFigures.sessions_collapsed` — the year holds far fewer sessions per
  day of window than the market's median year. A hole in the *store*: a rate
  computed over it is a rate over a year that never happened.
- :attr:`YearFigures.detections_collapsed` — the year's detections-per-session sits
  far under the market's median year. A hole in the *field*, with the calendar
  intact.

Sessions are judged as a **density** — per day of the year the window actually
covers — so the window's first and last years, which are short by design, are
flagged on the same rule as every other year rather than exempted from it. The
exemption is the tempting shortcut and it is a hole: a store that lost a quarter of
the window's opening year drops that year's sessions and its detections together,
so the rate barely moves and neither flag fires.

Every year between the window's first session and its last gets a row, including
one the store missed **entirely**. Such a year would otherwise produce no row, no
flag and no contribution to the median — the worst hole the report exists to catch
would be the one case it could not.

Neither fraction is a contract cell, and that is deliberate. The contract holds
the choices that decide a *measurement*, and these decide only which rows get a
mark beside them — no figure moves either way. They are named constants whose
values ride on the payload (``collapse_rule``) so a flag's rule is readable off
the result rather than trusted.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any, Sequence

from screener.store import Store

from .contract import DEFAULT_CONTRACT, RunContract
from .denominator import DenominatorStore, denominator_path
from .result import stamp_result
from .simulate import (
    ARMS,
    ENTRY_UNFILLED,
    DetectionOutcome,
    SimulatedTrade,
    closed_trades,
    price_scale_drops,
    walk_detections,
)

# The overlap the PRD requires stated wherever counts are reported (story 20). It
# is a fact about how two gates interact, not a choice the run makes, which is why
# it is a constant here rather than a contract cell — the same call
# ``ARM_SPECS.comparable_to_reference`` makes.
SMA50_OVERLAP_NOTE = (
    "the contract's close > SMA50 universe gate overlaps the detector's own trend "
    "logic, so these counts sit below an unfiltered run — the gate working, not "
    "the detector becoming more selective"
)

# What counts as favourable. The zero line is the contract's own — ``decision.kill``
# draws it at 0.0 R — so the run does not invent a second one, and R is the
# detection's own stop width by construction, which is the unit the app denominates
# in. Stated on the result rather than left in this docstring, because a threshold
# nobody can read off the output is a threshold a later run can quietly move.
FAVOURABLE_RULE = "R > 0 on a closed trade, before costs"

# When a year's count is a hole rather than a quiet market. Both are diagnostic:
# they decide which rows get a mark, and no reported figure moves either way. See
# the module docstring for why they are not contract cells.
DETECTION_COLLAPSE_FRACTION = 0.25
SESSION_COLLAPSE_FRACTION = 0.5

# The plot's alphabet. ``HOLE_MARK`` is deliberately not the lowest bar: a month
# the store never covered and a month that traded and detected nothing are
# different facts, and a yearly mean hides the first one — it drops by a twelfth
# and looks like a slow year.
BARS = "▁▂▃▄▅▆▇█"
HOLE_MARK = "·"
# A measured zero, drawn so it cannot be mistaken for an unmeasured span. The year
# the field went to zero is the row a reader is scanning for, and an empty cell
# beside an empty cell hides it. A sliver rather than a digit, because it sits in
# the bar column and a "0" there reads as the rate printed twice.
ZERO_MARK = "▏"
PLOT_WIDTH = 34


@dataclass(frozen=True)
class Share:
    """A count, the coverage it was measured against, and the rate between them.

    Every rate this module reports is one of these. A bare float would be a figure
    a reader cannot check and — worse — would report ``0/0`` as ``0.0``, which is a
    claim the data never made and exactly the shape an empty year or a thin cell
    takes. :attr:`rate` is ``None`` there instead, and the formatter prints the
    coverage beside every percentage rather than under it.
    """

    hits: int
    of: int

    @property
    def rate(self) -> float | None:
        """The share, or ``None`` when nothing was measured."""
        return self.hits / self.of if self.of else None

    def to_dict(self) -> dict[str, Any]:
        return {"hits": self.hits, "of": self.of, "rate": self.rate}

    def __str__(self) -> str:
        """``42.9% (3 of 7)`` — never a percentage without the count under it."""
        rate = self.rate
        shown = "n/a" if rate is None else f"{rate:.1%}"
        return f"{shown} ({self.hits} of {self.of})"


def favourable(trade: SimulatedTrade) -> bool:
    """Whether a trade reached a favourable outcome: :data:`FAVOURABLE_RULE`.

    ``False`` for a trade still running, which is the honest reading and not a
    convenience — an open trade has no R at all, and the caller keeps it out of
    precision's denominator rather than letting this function decide it lost.

    A function here rather than a property on :class:`SimulatedTrade`, though it
    reads only that trade's ``r_multiple``. The rule is a **measurement decision**
    and this is the phase that makes it; the simulator deliberately emits values
    and no verdicts about them, the same separation the score breakdown keeps when
    it stores a dimension's value and never one rubric's judgement of it (#154).
    Putting the threshold on the trade would let a later phase that wanted a
    different one find it already decided.
    """
    r = trade.r_multiple
    return r is not None and r > 0


@dataclass(frozen=True, kw_only=True)
class ArmFigures:
    """One arm's outcome figures over one market and one span.

    The counts are a funnel and they reconcile: of the entries that ``filled``,
    each is either ``closed`` or still ``open_at_end``, and of the closed ones
    ``favourable`` made money. ``answered`` is the count precision is measured
    against — the ``closed`` ones plus every detection that was asked and never
    triggered, which :attr:`Figures.no_break` holds. A setup that failed to trigger
    *is* an answer, and leaving it out would measure only the setups that got far
    enough to be judged.

    ``filled`` is this module's name for what :func:`~backtest.simulate.arm_report`
    calls ``trades``. The two are the same count; the names differ because here it
    is one stage of an entry funnel and there it is the whole population.
    """

    arm: str
    filled: int
    closed: int
    open_at_end: int
    favourable: int
    answered: int

    @property
    def precision(self) -> Share:
        """Favourable outcomes over every answered detection — the detector's figure."""
        return Share(self.favourable, self.answered)

    @property
    def win_rate(self) -> Share:
        """Favourable outcomes over the trades taken — the exit's figure."""
        return Share(self.favourable, self.closed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "filled": self.filled,
            "closed": self.closed,
            "open_at_end": self.open_at_end,
            "favourable": self.favourable,
            "precision": self.precision.to_dict(),
            "win_rate": self.win_rate.to_dict(),
        }


@dataclass(frozen=True, kw_only=True)
class Figures:
    """The three figures over one span: a year, or a whole market's window.

    ``sessions`` and ``detections`` are the coverage everything else is measured
    against, which is why they are fields rather than something a reader derives.

    **Every detection is in exactly one of four buckets, and all four are
    reported**, because a bucket with no count is a population that quietly leaves
    the arithmetic:

    - ``no_break`` — asked, and the market said no. A resolved miss, and it is in
      precision's denominator on every arm.
    - ``unfilled`` — it triggered, and the window ended before a session opened to
      fill it. In the trigger share (it *did* trigger) and in no precision
      denominator, because no position was ever taken.
    - ``undecided`` — the bars could not answer: the window ended on it, or the
      store never covered its session. In no denominator at all.
    - filled — became a position, and each arm then reports it as ``closed`` or
      ``open_at_end`` (:class:`ArmFigures`).

    ``detections == no_break + unfilled + undecided + filled``, and
    :attr:`reconciles` asserts it rather than leaving a reader to add up.
    """

    sessions: int
    detections: int
    triggered: Share
    undecided: int
    no_break: int
    unfilled: int
    arms: dict[str, ArmFigures]

    @property
    def detections_per_session(self) -> float | None:
        """The headline count, or ``None`` over a span holding no sessions."""
        return self.detections / self.sessions if self.sessions else None

    def reconciles(self, arm: str) -> bool:
        """Whether every detection lands in exactly one bucket, on this arm.

        The arithmetic the docstring above claims, checkable rather than asserted.
        A run where this is false has a population going somewhere unreported,
        which is the failure the four buckets exist to make impossible.
        """
        a = self.arms[arm]
        return (
            self.no_break + self.unfilled + self.undecided + a.filled
            == self.detections
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessions": self.sessions,
            "detections": self.detections,
            "detections_per_session": self.detections_per_session,
            "triggered": self.triggered.to_dict(),
            "no_break": self.no_break,
            "unfilled": self.unfilled,
            "undecided": self.undecided,
            "arms": [self.arms[a].to_dict() for a in ARMS if a in self.arms],
        }


@dataclass(frozen=True, kw_only=True)
class YearFigures(Figures):
    """One year's figures, and whether its counts collapsed.

    The unit the PRD requires every result be reported in — per market and per
    year, never pooled only, so that a window holding a crash and a mania is not
    described by a single number that fits neither.

    ``covered_days`` is how much of the calendar year the measured window actually
    spans, and it is what the session count is judged against. Judging against the
    whole year instead would flag the window's first and last years on every run,
    since they are short by design — and exempting them from the flag instead, as
    this first did, leaves a real hole at either end of the window catchable by
    nothing. A density handles both without an exemption.
    """

    market: str
    year: int
    covered_days: int
    sessions_collapsed: bool = False
    detections_collapsed: bool = False

    @property
    def sessions_per_covered_day(self) -> float | None:
        """The session density: what a hole in the store actually moves."""
        return self.sessions / self.covered_days if self.covered_days else None

    @property
    def flags(self) -> tuple[str, ...]:
        """The year's collapse flags in words, for a reader rather than a query."""
        out: list[str] = []
        if self.sessions_collapsed:
            out.append(
                f"sessions collapsed — {self.sessions} in the year, under "
                f"{SESSION_COLLAPSE_FRACTION:.0%} of this market's median year: a "
                "hole in the store, and a rate over a year that never happened"
            )
        if self.detections_collapsed:
            out.append(
                "detections collapsed — under "
                f"{DETECTION_COLLAPSE_FRACTION:.0%} of this market's median year "
                "with the calendar intact: a hole in the field, not a quiet market"
            )
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "year": self.year,
            **super().to_dict(),
            "covered_days": self.covered_days,
            "sessions_per_covered_day": self.sessions_per_covered_day,
            "sessions_collapsed": self.sessions_collapsed,
            "detections_collapsed": self.detections_collapsed,
            "flags": list(self.flags),
        }


@dataclass(frozen=True, kw_only=True)
class MonthPoint:
    """One month of the plotted series, and whether the store covered it at all.

    ``sessions`` of zero is a **hole**: the store held no session that month, which
    a yearly mean cannot show — it drops by a twelfth and reads as a slow year. A
    month with sessions and no detections is a different fact and draws differently
    (:data:`HOLE_MARK`).
    """

    year: int
    month: int
    sessions: int
    detections: int

    @property
    def hole(self) -> bool:
        return self.sessions == 0

    @property
    def per_session(self) -> float | None:
        return self.detections / self.sessions if self.sessions else None

    def to_dict(self) -> dict[str, Any]:
        # ``year`` and ``month`` ride as numbers as well as in the label. The
        # label alone would make every reader of the payload — the plot included —
        # split a string back into the two integers that produced it, which is a
        # parse that can fail on a value that cannot.
        return {
            "month": f"{self.year:04d}-{self.month:02d}",
            "year": self.year,
            "month_of_year": self.month,
            "sessions": self.sessions,
            "detections": self.detections,
            "detections_per_session": self.per_session,
            "hole": self.hole,
        }


@dataclass(frozen=True, kw_only=True)
class MarketFigures(Figures):
    """One market's whole window: its totals, its years, and its monthly series.

    Reported per market and never pooled with the other, because findings §8
    measured that magnitudes do not transfer between them — a US figure averaged
    with a Jakarta one describes neither market.

    ``price_scale_dropped`` is the count of this market's trades whose one
    absolute-price comparison could not be verified. It rides here because the
    house rule is that the flag is reported beside **every** result built on it,
    and precision is built on entries priced in absolute terms.
    """

    market: str
    price_scale_dropped: int
    years: tuple[YearFigures, ...] = ()
    months: tuple[MonthPoint, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "sma50_overlap": SMA50_OVERLAP_NOTE,
            **super().to_dict(),
            "price_scale_dropped": self.price_scale_dropped,
            "years": [y.to_dict() for y in self.years],
            "months": [m.to_dict() for m in self.months],
        }


def _tally(
    outcomes: Sequence[DetectionOutcome], sessions: int, arms: Sequence[str]
) -> Figures:
    """One span's figures, from its detections' outcomes.

    One pass, because the three figures share a population and computing them
    apart would let them disagree about which detections were in the span. Returns
    the :class:`Figures` rather than the counts behind it: the four values *are*
    that type, and handing them back as a tuple only to be unpacked into it at each
    call site is the same object spelled twice.
    """
    decided = [o for o in outcomes if o.entry.decided]
    triggered = Share(sum(1 for o in decided if o.entry.triggered), len(decided))
    # An answer that is not a trade: the setup never broke. It belongs in
    # precision's denominator on every arm, because the detector named it and the
    # market said no.
    no_break = sum(1 for o in decided if not o.entry.triggered)
    # It triggered and the window ended before a session opened to fill it. In the
    # trigger share, and in no precision denominator: no position was taken, so
    # there is no outcome to be favourable or otherwise.
    unfilled = sum(1 for o in decided if o.entry.outcome == ENTRY_UNFILLED)
    figures: dict[str, ArmFigures] = {}
    for arm in arms:
        trades = [o.trades[arm] for o in outcomes if arm in o.trades]
        closed = closed_trades(trades)
        figures[arm] = ArmFigures(
            arm=arm,
            filled=len(trades),
            closed=len(closed),
            open_at_end=len(trades) - len(closed),
            favourable=sum(1 for t in closed if favourable(t)),
            answered=no_break + len(closed),
        )
    return Figures(
        sessions=sessions,
        detections=len(outcomes),
        triggered=triggered,
        undecided=len(outcomes) - len(decided),
        no_break=no_break,
        unfilled=unfilled,
        arms=figures,
    )


def _months(session_dates: Sequence[date], by_session: Counter) -> tuple[MonthPoint, ...]:
    """The monthly series across the window, holes included.

    Every month between the first session and the last gets a point, whether the
    store covered it or not — a series that simply omitted the empty months would
    plot a hole as a shorter line, which is the one thing the plot exists to make
    visible.
    """
    if not session_dates:
        return ()
    first, last = session_dates[0], session_dates[-1]
    per_month: Counter = Counter()
    detections_per_month: Counter = Counter()
    for d in session_dates:
        per_month[(d.year, d.month)] += 1
        detections_per_month[(d.year, d.month)] += by_session[d]
    points: list[MonthPoint] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        points.append(
            MonthPoint(
                year=year, month=month,
                sessions=per_month[(year, month)],
                detections=detections_per_month[(year, month)],
            )
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(points)


def figures_for_market(
    store: Store,
    denominator: DenominatorStore,
    market: str,
    contract: RunContract = DEFAULT_CONTRACT,
    *,
    arms: Sequence[str] = ARMS,
    include_burn_in: bool = False,
) -> MarketFigures:
    """One market's denominator figures, per year and across the window.

    The single entry point for Phase 5's counts. Reads the rows
    :mod:`backtest.run` persisted and the bars they were computed from, walks each
    detection through the shared entry and every arm's exit
    (:func:`~backtest.simulate.walk_detections`), and reduces the result per year
    and over the whole window.

    Burn-in sessions are excluded by default, from the session spine and from the
    detections alike: a warm-up session is persisted and never measured (story
    76), and a figure that counted one would rest on an unsettled chain.

    The session count comes from the persisted **session headers** rather than
    from the detections, so a year in which nothing detected still contributes its
    calendar — which is the whole of how a collapsed field is told apart from a
    short year.

    Every year between the window's first session and its last gets a row, whether
    the store covered it or not. A year the store missed **entirely** would
    otherwise produce no row, no flag and no contribution to the median — so the
    worst hole the report exists to catch would be the one case it could not, and
    it would survive only as a blank line in the monthly grid.
    """
    headers = denominator.sessions(
        market, burn_in=None if include_burn_in else False
    )
    session_dates = [h.session for h in headers]
    outcomes = walk_detections(
        store, denominator, market, contract,
        arms=arms, include_burn_in=include_burn_in,
    )
    ran = [a for a in ARMS if a in arms]

    by_year_sessions = Counter(d.year for d in session_dates)
    by_session = Counter(o.session for o in outcomes)
    by_year_outcomes: dict[int, list[DetectionOutcome]] = {}
    for o in outcomes:
        by_year_outcomes.setdefault(o.session.year, []).append(o)

    years: list[YearFigures] = []
    for year in _window_years(session_dates):
        span = _tally(by_year_outcomes.get(year, []), by_year_sessions[year], ran)
        years.append(
            YearFigures(
                **_fields(span), market=market, year=year,
                covered_days=_covered_days(year, session_dates),
            )
        )

    span = _tally(outcomes, len(session_dates), ran)
    return MarketFigures(
        **_fields(span), market=market,
        price_scale_dropped=sum(
            price_scale_drops(list(o.trades.values())) for o in outcomes
        ),
        years=tuple(_flag_collapses(years)),
        months=_months(session_dates, by_session),
    )


def _fields(span: Figures) -> dict[str, Any]:
    """A :class:`Figures`'s own fields, for a subclass that extends it.

    Named rather than ``dataclasses.asdict``, which would recurse into ``Share``
    and ``ArmFigures`` and hand back dicts where the constructor wants values.
    """
    return {
        "sessions": span.sessions,
        "detections": span.detections,
        "triggered": span.triggered,
        "undecided": span.undecided,
        "no_break": span.no_break,
        "unfilled": span.unfilled,
        "arms": span.arms,
    }


def _window_years(session_dates: Sequence[date]) -> list[int]:
    """Every year the window touches, including the ones the store never covered."""
    if not session_dates:
        return []
    return list(range(session_dates[0].year, session_dates[-1].year + 1))


def _covered_days(year: int, session_dates: Sequence[date]) -> int:
    """How many days of ``year`` the measured window actually spans.

    The denominator the session count is judged against. A year the window only
    half-covers should be half as long, and a year it covers whole should not — so
    comparing raw session counts would flag the window's first and last years on
    every single run, which is how a flag becomes noise.
    """
    if not session_dates:
        return 0
    start = max(session_dates[0], date(year, 1, 1))
    end = min(session_dates[-1], date(year, 12, 31))
    return max(0, (end - start).days + 1)


def _flag_collapses(years: Sequence[YearFigures]) -> list[YearFigures]:
    """Mark the years whose counts collapsed against this market's median year.

    Measured against the market's **own** median rather than an absolute floor,
    because a year is short or empty relative to the market it sits in — a US
    calendar and a Jakarta one do not hold the same number of sessions, and a floor
    that fitted one would fire every year on the other.

    Sessions are judged as a **density** — sessions per day of the year the window
    actually covers — and not as a raw count. That is what lets the window's first
    and last years be flagged like any other: they hold fewer sessions because they
    are shorter, and dividing by their own span removes exactly that difference and
    nothing else. The obvious alternative, exempting the two edge years from the
    flag, leaves a real hole at either end of the window catchable by neither flag —
    a missing quarter drops sessions and detections together, so the rate barely
    moves and the detections flag stays silent too.
    """
    if len(years) < 2:
        # One year has nothing to collapse relative to, and a median of itself
        # would flag nothing however empty it was. Better no claim than a false one.
        return list(years)
    session_median = _median_of(y.sessions_per_covered_day for y in years)
    detection_median = _median_of(y.detections_per_session for y in years)
    return [
        dataclasses.replace(
            y,
            sessions_collapsed=_under(
                y.sessions_per_covered_day, session_median,
                SESSION_COLLAPSE_FRACTION,
            ),
            detections_collapsed=_under(
                y.detections_per_session, detection_median,
                DETECTION_COLLAPSE_FRACTION,
            ),
        )
        for y in years
    ]


def _median_of(values: Any) -> float | None:
    """The median of the values that exist, or ``None`` if none do.

    ``None`` is absent — a year with no covered days has no density, and a year
    with no sessions has no detection rate — and averaging absence in as a zero
    would drag the median down until nothing could clear a quarter of it.
    """
    present = [v for v in values if v is not None]
    return median(present) if present else None


def _under(value: float | None, reference: float | None, fraction: float) -> bool:
    """Whether ``value`` collapsed against ``reference``.

    ``False`` when either is absent: a span nothing was measured over has not
    collapsed, it is simply unmeasured, and a flag that cannot tell the two apart
    is a flag that fires on the window's own edges.
    """
    if value is None or not reference:
        return False
    return value < fraction * reference


def figures_report(
    contract: RunContract, markets: Sequence[MarketFigures]
) -> dict[str, Any]:
    """Every market's figures as one stamped payload.

    The rules that qualify the numbers ride at the top of the result rather than in
    a companion document: what counts as favourable, that costs are not applied
    yet, how a collapse is decided, and the SMA50 overlap. Each of them changes how
    a figure below should be read, and a qualification a reader has to fetch is a
    qualification a reader skips.

    Markets appear in the order given rather than sorted, and never merged: US and
    IDX are reported separately throughout, so findings §8's result that magnitudes
    do not transfer is honoured rather than averaged away.
    """
    return stamp_result(
        contract,
        {
            "sma50_overlap": SMA50_OVERLAP_NOTE,
            "favourable_rule": FAVOURABLE_RULE,
            "costs_applied": False,
            "costs_note": (
                "these are before costs — commission and slippage are applied by "
                "the phase that computes the pre-registered primary metric, and "
                "precision computed before them overstates"
            ),
            "collapse_rule": {
                "detections_fraction": DETECTION_COLLAPSE_FRACTION,
                "sessions_fraction": SESSION_COLLAPSE_FRACTION,
                "basis": "the market's own median year",
                "edges_exempt_from_sessions_flag": True,
            },
            "markets": [m.to_dict() for m in markets],
        },
    )


def _bar(value: float | None, peak: float | None) -> str:
    """One year's bar, scaled to the tallest year in the market.

    A measured zero draws as :data:`ZERO_MARK` and an unmeasured year as nothing at
    all. Drawing both as an empty cell would put the module's own rule — that a
    ``0`` and an absent value are different claims — on the wrong side of its most
    visible output, and the year where the field went to zero is precisely the row
    a reader is scanning for.
    """
    if value is None or not peak:
        return ""
    if value <= 0:
        return ZERO_MARK
    return BARS[-1] * max(1, round(PLOT_WIDTH * value / peak))


def _sparkline(months: Sequence[dict[str, Any]]) -> list[str]:
    """The monthly series as a calendar grid: one row per year, twelve columns.

    A single line across the window would run past 160 columns on a fourteen-year
    run and lose its own axis. A grid keeps every row twelve wide, so the months
    line up under each other and a hole that recurs every August is a *column* — a
    shape one line of 168 glyphs cannot show at all.

    Three marks, and the third is the point: a bar is a month that traded, a
    :data:`HOLE_MARK` is a month inside the window the store never covered, and a
    blank is a month outside the window, which is not a hole but the edge. Folding
    the last two together would put a permanent hole at each end of every run and
    teach a reader to ignore the mark.

    Eight levels is all a terminal glyph gives, which is plenty: the grid is read
    for *shape* — where the field thins and where it stops — and the table above it
    carries the numbers.
    """
    if not months:
        return []
    rates = [m["detections_per_session"] for m in months if not m["hole"]]
    peak = max((r for r in rates if r is not None), default=0.0)
    drawn: dict[tuple[int, int], str] = {}
    for m in months:
        year, month = m["year"], m["month_of_year"]
        if m["hole"]:
            drawn[(year, month)] = HOLE_MARK
            continue
        rate = m["detections_per_session"] or 0.0
        level = 0 if not peak else round(rate / peak * (len(BARS) - 1))
        drawn[(year, month)] = BARS[min(len(BARS) - 1, level)]
    years = sorted({y for y, _ in drawn})
    return [
        f"    {year}  " + "".join(drawn.get((year, m), " ") for m in range(1, 13))
        for year in years
    ]


def _outcomes_table(years: Sequence[dict[str, Any]]) -> list[str]:
    """The trigger share and each arm's precision, per year.

    Every cell is ``n / m`` rather than a percentage, and that is the point at this
    width: the counts *are* the coverage, so a year whose figures rest on four
    detections cannot be read as one resting on four hundred. A percentage would
    fit more comfortably and would hide exactly that.

    Per year and not only per market, because a window holding a crash and a mania
    is not described by a single number that fits neither (story 88).
    """
    if not years:
        return []
    arms = [a["arm"] for a in years[0]["arms"]]
    head = "  year  detections  decided  triggered" + "".join(
        f"  precision {a}" for a in arms
    )
    rows = [head]
    for y in years:
        decided = y["triggered"]["of"]
        cells = "".join(
            f"  {a['precision']['hits']:>5} /{a['precision']['of']:>4}"
            for a in y["arms"]
        )
        rows.append(
            f"  {y['year']}  {y['detections']:10d}  {decided:7d}  "
            f"{y['triggered']['hits']:4d} /{decided:4d}{cells}"
        )
    return rows


def format_figures(report: dict[str, Any]) -> str:
    """The denominator figures as a page a terminal can print.

    Per market: the overlap note, the per-year table with its plot in the same
    rows, the monthly series, and the arms' precision. The plot shares the table's
    rows rather than sitting under it, because a bar beside its own numbers is read
    together with them and a chart below a table is read instead of it.

    Every rate prints as ``x% (n of m)``. The coverage is not a footnote here: it
    is the difference between a precision figure and a precision figure nobody can
    check.
    """
    lines: list[str] = [
        f"favourable outcome: {report['favourable_rule']}",
        f"note: {report['costs_note']}",
        "",
    ]
    for market in report["markets"]:
        years = market["years"]
        span = (
            f"{years[0]['year']}–{years[-1]['year']}" if years else "no sessions"
        )
        peak = max(
            (y["detections_per_session"] or 0.0 for y in years), default=0.0
        )
        lines += [
            f"{market['market']} — detections per session, {span}",
            f"  {report['sma50_overlap']}",
            "",
            "  year  sessions  detections  per session",
        ]
        for y in years:
            rate = y["detections_per_session"]
            shown = "    n/a" if rate is None else f"{rate:7.3f}"
            lines.append(
                f"  {y['year']}  {y['sessions']:8d}  {y['detections']:10d}  "
                f"{shown}  {_bar(rate, peak)}".rstrip()
            )
            # On its own line rather than trailing the row: a flag is a sentence,
            # and a sentence appended to a fixed-width table pushes the row past
            # any terminal and takes the columns with it.
            lines += [f"          ⚠ {f}" for f in y["flags"]]
        lines += ["", *_outcomes_table(years)]
        lines += [
            "",
            "  detections per session by month  (JFMAMJJASOND)",
            f"    {HOLE_MARK} is a month inside the window the store never "
            "covered — a hole, not a quiet month",
            "",
            *_sparkline(market["months"]),
            "",
            f"  sessions measured   {market['sessions']}",
            f"  detections          {market['detections']}",
            f"  triggered           {_share(market['triggered'])}",
            f"  never broke         {market['no_break']}  "
            "(asked, and the market said no — in precision's denominator)",
            f"  unfilled            {market['unfilled']}  "
            "(triggered, and the window ended before a fill)",
            f"  undecided           {market['undecided']}  "
            "(the bars could not answer these; they are not misses)",
            f"  price-scale flag would drop {market['price_scale_dropped']} of the "
            "trades behind these figures",
            "",
        ]
        for arm in market["arms"]:
            lines += [
                f"  arm {arm['arm']}",
                f"    filled            {arm['filled']}",
                f"    closed            {arm['closed']}",
                f"    open at end       {arm['open_at_end']}  "
                "(no outcome — never counted as a loss)",
                f"    precision         {_share(arm['precision'])}"
                "  — of every answered detection",
                f"    win rate          {_share(arm['win_rate'])}"
                "  — of the trades taken",
            ]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _share(body: dict[str, Any]) -> Share:
    """A serialised :class:`Share` back into the value, for printing.

    The rate is rebuilt from the counts rather than read back: a rate and its
    counts arriving from a file could disagree, and the counts are the record.
    """
    return Share(body["hits"], body["of"])


def main(argv: list[str] | None = None) -> int:
    """Report the denominator figures off a persisted denominator.

    The command that reproduces them::

        python -m backtest.figures --store data/backtest.duckdb \\
            --market US --market IDX --out-json references/backtest_figures.json

    Both markets in one invocation and one payload, reported separately
    throughout — never pooled, and never averaged into a summary figure that fits
    neither. Reads the bar store and the denominator beside it; writes to neither.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument(
        "--market", action="append", required=True,
        help="a market to report (repeatable; each is reported separately)",
    )
    parser.add_argument(
        "--include-burn-in", action="store_true",
        help="also measure burn-in sessions (never for a reported result)",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable, contract-stamped result",
    )
    args = parser.parse_args(argv)

    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        markets = [
            figures_for_market(
                store, denominator, market, DEFAULT_CONTRACT,
                include_burn_in=args.include_burn_in,
            )
            for market in args.market
        ]
    finally:
        denominator.close()
        store.close()

    report = figures_report(DEFAULT_CONTRACT, markets)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_figures(report))
    if args.out_json:
        print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
