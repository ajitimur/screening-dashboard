"""Anchor before believing: the six committed figures a new run must reproduce
(issue #197, PRD #182 Phase 6; the ``in_field`` pin split per universe by #211).

The run overlaps ground the reference study already measured. Before any new
figure from it is read, it reproduces the figures already committed to this repo
or writes down why it cannot — because a mismatch is a bug in the new store or
the new chain, and every downstream number inherits it.

Nothing here is a second measurement. The anchors arrive as the *existing*
measurement types — :class:`replay.funnel.StageRecall`,
:class:`replay.discrimination_grid.CellMeasurement`,
:class:`replay.reference.ReferenceReport` — through the adapters below, and a
mismatch is raised as :class:`replay.reference.DriftError`, the drift mechanism
the study has failed loudly on since #114. The one quantity measured here is the
geometry (:func:`measure_geometry`), and only because its committed figures came
from a throwaway prototype (findings §3b) rather than from a module anything can
call.

Two kinds of anchor, and only one is stable
-------------------------------------------
The three **geometry** anchors are measured from his bars: median trailing 3-bar
range 1.31 ADR, median trailing 5-bar range 1.86 ADR, median 20-day ADR at entry
eve 6.08%. They hold whatever the detector does, so they anchor the *store and the
indicators*. :func:`check_anchors` checks them **first**, reports them apart, and
on a failure stops without reading the other three: if the store's geometry is
wrong, nothing downstream is worth investigating yet.

The three **gate-dependent** anchors — coverage, detection recall, ``in_field`` —
depend on coverage and on the gates themselves and have moved repeatedly (#139,
#149, #154, #164, #165). Each is stamped with the detector version it was measured
at, and every superseded pin is recorded beside its live value
(:attr:`Anchor.superseded`), because an anchor quoted from a stale pin fails for a
reason that has nothing to do with the pipeline it is testing.

The two field rows are different anchors, and were once conflated
-----------------------------------------------------------------
Until #165 one row carried detection recall's label and ``in_field``'s value. They
are not the same quantity: recall asks whether the detector would have fired on his
name at all and is **gate-invariant**; ``in_field`` asks whether the name reached
that night's field and moves with every gate and coverage change. So each anchor
declares the :attr:`Anchor.quantity` it measures, every measurement carries the
quantity it *is*, and :func:`check_anchors` refuses a measurement whose quantity is
not the anchor's. Wiring the funnel's recall into the ``in_field`` anchor is
therefore an error at the seam rather than an anchor failing that should have
passed — the failure this table exists to prevent, arriving through the table.

The ``in_field`` tolerance, and the one thing it may not absorb
---------------------------------------------------------------
``in_field`` was measured on ``replay.duckdb``, which ranks five references as
though they were candidates (#162). The store was deliberately left that way; the
fix binds fresh builds only. **This run is a fresh build, so it will not reproduce
the committed value exactly, and should not.** The direction is known and the size
is bounded — percentile denominators shift by ~0.5%, moving decile membership at
the margin and nothing else — so :data:`CONTAMINATION_TRADES` treats a difference
of a few trades as the fix landing.

What the tolerance may **not** absorb is a difference large enough to flip the sign
of §4b's gap. That is the bug this table is looking for, so the gap rides on the
same anchor as a **sign-checked** component (:attr:`Anchor.sign_checked`): its
magnitude is free to move, its sign is not, and a flip fails the anchor whatever
the trade count did. **Nor can a write-up waive it** — every other divergence may
be explained in writing and recorded as a divergence, but a failure a free-text
argument can wave through is not a failure, and this is the one the table exists
to find.

One quantity, two universes, two pins
-------------------------------------
For a while that sign check failed on #198's full run, and what it had caught was
not a bug. #211 measured that ``in_field`` and §4b's gap are properties of the
**pair** (rubric, universe) rather than of the rubric: +1.95pp under the app's
universe, −5.01pp under the contract's stateless one, the reversal attributable to
the ADR20 floor and the trend gate acting together, each duplicating a rubric
dimension and lifting the field's hit rate on it until no spread is left. A
property of the method under the contracted gates, not a defect in the field.

So holding a stateless-universe run to §4b's app-universe figure was never a
failing anchor. It was a subtraction between two numbers that were never the same
number — the #165 conflation one level down, with the field rather than the
quantity as the thing being conflated. ``in_field`` is therefore **two anchors**,
each naming its :attr:`Anchor.universe`, and :func:`gate_dependent_anchors`
selects the one that holds over the field a run actually screened. A run is still
checked against six anchors; the seventh row is the other universe's pin.

Nothing was widened to get there. Both pins keep zero tolerance on their counts
and both keep the sign check on the gap, so a stateless-universe run coming back
positive fails exactly as before. A measurement counted over one universe and
offered against the other's pin is **refused** rather than reported as a
divergence, because a mismatch there says nothing about the pipeline.

The contract's pin is a first measurement, made by the run it now anchors, so it
detects drift from here on rather than confirming that run. What corroborates the
run is on the other universe: §4b's own 397/656 reproduced exactly, and 324/503
(+1.86pp) with the population held fixed.

Arms B and C only
-----------------
:data:`ANCHOR_ARMS` is derived from :data:`~backtest.simulate.ARM_SPECS`, not
restated: an arm is anchorable exactly when it is comparable to the reference set's
simulated exits. Arm A has no counterpart there, so a measurement tagged with it is
refused — arm A is measured, never anchored.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from math import isnan
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Mapping, Sequence

from replay.discrimination_grid import (
    FIELD_WHOLE,
    PUBLISHED_RUBRIC,
    CellMeasurement,
)
from replay.funnel import STAGE_DETECTION, StageRecall
from replay.reference import (
    DEFAULT_REFERENCE_JSON,
    R_SHARE_TOL,
    REFERENCE_FIGURES,
    DriftError,
    ExecutedTrade,
    ReferenceReport,
    build_report,
    evaluation_session,
    load_trades,
)
from screener.bars import Bar
from screener.detection import DETECTOR_VERSION, K_MIN
from screener.indicators import ADR_WINDOW, adr as _adr
from screener.store import Store

from .contract import DEFAULT_CONTRACT, RunContract
from .result import stamp_result
from .simulate import ARM_SPECS

# The market the reference set was traded in. Every anchor here is measured over
# his 828 US entries; the run reports IDX separately and anchors nothing against
# it, because there is no IDX counterpart in the reference set to anchor to.
ANCHOR_MARKET = "US"

# The arms an anchor may be taken against: exactly the arms comparable to the
# reference set's two simulated exits. Derived from the arm table rather than
# restated as ``("B", "C")``, so a fourth arm is anchorable or not according to
# the one fact that decides it.
ANCHOR_ARMS: tuple[str, ...] = tuple(
    arm for arm, spec in sorted(ARM_SPECS.items()) if spec.comparable_to_reference
)

# The arms an anchor may never be taken against, derived from the same table for
# the same reason: a fourth arm's comparability is one fact, read in one place.
MEASURED_NEVER_ANCHORED: tuple[str, ...] = tuple(
    arm for arm in sorted(ARM_SPECS) if arm not in ANCHOR_ARMS
)

# The two kinds of anchor. Geometry is measured from his bars and holds whatever
# the detector does; a gate-dependent anchor moves with coverage and with the
# gates, which is why the two are checked and reported apart.
GEOMETRY = "geometry"
GATE_DEPENDENT = "gate-dependent"

# What an anchor measures. The two field anchors carry different quantities and
# that is the whole point: a measurement of one can never be checked against the
# other (#165's conflation, made unrepresentable).
QUANTITY_GEOMETRY = "bar-geometry"
QUANTITY_COVERAGE = "reference-coverage"
QUANTITY_DETECTION_RECALL = "detection-recall (gate-invariant)"
QUANTITY_IN_FIELD = "field-membership (gate-dependent)"

# -- the two universes a field figure can be counted over ----------------------
#
# #211 measured that ``in_field`` and §4b's gap are properties of the *pair*
# (rubric, universe) rather than of the rubric alone: +1.95pp under the app's
# universe, −5.01pp under the contract's stateless one. The reversal is the ADR20
# floor and the trend gate acting together, and it is a property of the method
# under those gates rather than a defect in how the field is built
# (``references/backtest_gate_isolation.md``).
#
# So a field figure that does not name its universe is not a number anyone can
# check. These two names are what makes the pair explicit, and they are why
# ``in_field`` is two anchors below rather than one: comparing a run over one
# universe against a pin measured over the other is not a failing anchor, it is
# two different quantities being subtracted.
UNIVERSE_APP = "app"
UNIVERSE_STATELESS = "stateless"

# Why the two are not comparable, in one sentence, so the three refusals below
# say the same thing rather than three drifting paraphrases of it.
WHY_UNIVERSE_MATTERS = (
    "#211 measured that in_field and §4b's gap are properties of the pair "
    "(rubric, universe) — +1.95pp under the app's universe, −5.01pp under the "
    "contract's stateless one — so a count over one is not a count over the "
    "other and subtracting them says nothing about the pipeline"
)

# The universes an anchor may be scoped to. An anchor scoped to neither holds
# over both — the geometry rows are medians off his bars and no gate touches
# them, so scoping them would invent a distinction the measurement does not have.
UNIVERSES = (UNIVERSE_APP, UNIVERSE_STATELESS)

# The `in_field` band the #162 reference contamination is allowed to move the count
# by. The published values were measured on a store that ranks five references in a
# ranked population of ~1,000, so percentile denominators shift by ~0.5%. Applied to
# the 656 replayable trades that is 3.3 trades at one decile boundary; doubled to
# bound movement at both edges and rounded up, which is the "difference of a few
# trades" the plan calls the fix landing. Deliberately not wider: past this, the
# difference is not a denominator shift.
CONTAMINATION_TRADES = 7

# The geometry bands. The committed medians were measured over 649 replayable
# entries by an independently written prototype against a differently-built store,
# so a handful of trades entering or leaving the sample moves a median in the second
# decimal. These bands are that wobble and the quoted precision — roughly 1.5% of
# each figure — and nothing like the movement a wrong adjustment basis or a
# mis-slid evaluation session would produce.
RANGE_TOL_ADR = 0.02
ADR_TOL = 0.001  # 0.10 percentage points, on a fraction

# A component with no tolerance at all: its value is free to move and only its
# sign is anchored. Spelled as an absence rather than an infinite float, so the
# three readers below test for "no tolerance" instead of comparing against a
# sentinel that could be arrived at by arithmetic.
FREE: None = None


@dataclass(frozen=True)
class Pin:
    """A superseded value, recorded beside the live one.

    Kept on the anchor rather than in a comment, because the failure mode this
    guards is a reader quoting a stale figure at a new run: the pin fails the
    anchor for a reason that has nothing to do with the pipeline being tested.
    ``why`` says what moved it, so a mismatch against a pin is recognisable as a
    mismatch against a pin.
    """

    value: str
    why: str


@dataclass(frozen=True)
class Anchor:
    """One committed figure, and everything needed to check it honestly.

    ``committed`` and ``tolerance`` are keyed by component, so a row quoting two
    numbers ("92 / 172 of 312 / 828") is one anchor rather than two half-anchors
    that could pass separately. ``measured_at`` is the detector version stamp —
    empty for the geometry rows, which no detector touches, and multi-valued for
    detection recall, which is gate-invariant and holds at v2 and v3 alike.
    ``sign_checked`` names components whose *sign* must reproduce regardless of
    tolerance.

    ``universe`` names the field the figure was counted over, for the anchors
    where that is part of what the number *is* (:data:`UNIVERSE_APP`,
    :data:`UNIVERSE_STATELESS`). ``None`` means the anchor holds over both, which
    is the honest answer for every row no gate touches. It sits beside
    ``quantity`` because it does the same job one level down: ``quantity`` keeps
    recall and field membership from being conflated (#165), and ``universe``
    keeps two field-membership figures from being conflated (#211).
    """

    key: str
    label: str
    kind: str
    quantity: str
    committed: Mapping[str, float]
    tolerance: Mapping[str, float | None]
    unit: str
    source: str
    measured_at: tuple[int, ...]
    universe: str | None = None
    first_measurement: bool = False
    tolerance_reason: str | None = None
    sign_checked: tuple[str, ...] = ()
    superseded: tuple[Pin, ...] = ()
    note: str = ""

    @property
    def detector_stamp(self) -> str:
        """The version stamp as it prints — never blank, because a figure whose
        version is absent gets compared against a run built at another one."""
        if not self.measured_at:
            return "detector-independent (bar geometry)"
        versions = ", ".join(f"v{v}" for v in self.measured_at)
        return f"detector {versions}"

    def holds_at(self, detector_version: int) -> bool:
        """Whether this anchor has a committed value at ``detector_version``.

        Version-independent anchors hold everywhere. A gate-dependent one holds
        only where it was measured: quoting v2's ``in_field`` at a run built on v3
        is the error the row's per-version stamp exists to prevent.
        """
        return not self.measured_at or detector_version in self.measured_at


# -- the six anchors, geometry first ------------------------------------------

# Findings §3b/§3c. Measured from his bars at the evaluation session, so they say
# whether the store holds the right bars and the indicators read them the same way
# — independently of every gate. Checked first for that reason.
GEOMETRY_ANCHORS: tuple[Anchor, ...] = (
    Anchor(
        key="median_range_3bar_adr",
        label="Median trailing 3-bar range at his entries",
        kind=GEOMETRY,
        quantity=QUANTITY_GEOMETRY,
        committed={"median": 1.31},
        tolerance={"median": RANGE_TOL_ADR},
        unit="ADR",
        source="findings §3b",
        measured_at=(),
        note=(
            "the ungated ruler the far-outlier guard tests and the rubric grades; "
            "monotone in k, so it is also the tightest window the cluster scan sees"
        ),
    ),
    Anchor(
        key="median_range_5bar_adr",
        label="Median trailing 5-bar range at his entries",
        kind=GEOMETRY,
        quantity=QUANTITY_GEOMETRY,
        committed={"median": 1.86},
        tolerance={"median": RANGE_TOL_ADR},
        unit="ADR",
        source="findings §3b, §3c",
        measured_at=(),
        note=(
            "the travel measure §3c reads the late contraction off — flat at ~2.4 "
            "ADR from three months out, falling only in the last ~10 sessions"
        ),
    ),
    Anchor(
        key="median_adr_at_entry_eve",
        label="Median 20-day ADR at entry eve",
        kind=GEOMETRY,
        quantity=QUANTITY_GEOMETRY,
        committed={"median": 0.0608},
        tolerance={"median": ADR_TOL},
        unit="fraction of price",
        source="findings §3c",
        measured_at=(),
        note=(
            "flat into his entries: what contracts is travel, not the daily range, "
            "so a store bug that smooths bars shows here before anywhere else"
        ),
    ),
)

# The three that move with coverage and with the gates. Each carries its version
# stamp and its superseded pins.
GATE_DEPENDENT_ANCHORS: tuple[Anchor, ...] = (
    Anchor(
        key="coverage_blind_spot",
        label="Blind-spot tickers / trades, 2019–2022",
        kind=GATE_DEPENDENT,
        quantity=QUANTITY_COVERAGE,
        # Read off the reference module's own pins rather than restated, so this
        # table and :func:`replay.reference.assert_matches_reference` cannot come
        # to disagree about what was committed.
        committed={
            "blind_spot_tickers": REFERENCE_FIGURES["blind_spot_tickers"],
            "blind_spot_trades": REFERENCE_FIGURES["blind_spot_trades"],
            "distinct_tickers": REFERENCE_FIGURES["distinct_tickers"],
            "total_rows": REFERENCE_FIGURES["total_rows"],
            "rows_with_outcomes": REFERENCE_FIGURES["rows_with_outcomes"],
            # The last pin, carried so this route is no weaker than
            # :func:`~replay.reference.assert_matches_reference`: the hole is
            # bounded in *realised R* as well as in names, and a run that
            # reproduced the counts while moving the share would pass a coverage
            # check having changed which trades are missing.
            "blind_spot_r_share": REFERENCE_FIGURES["blind_spot_r_share"],
        },
        tolerance={
            "blind_spot_tickers": 0,
            "blind_spot_trades": 0,
            "distinct_tickers": 0,
            "total_rows": 0,
            "rows_with_outcomes": 0,
            # A float quoted to 0.1%, so a smaller difference is rounding — the
            # reference module's own band, read from it rather than restated.
            "blind_spot_r_share": R_SHARE_TOL,
        },
        unit="count",
        source="findings §2",
        measured_at=(),
        note=(
            "measured in the replay window against bars covering each trade's "
            "evaluation session — the condition under which anything can be said "
            "about a trade at all"
        ),
        superseded=(
            Pin("81 tickers / 141 trades / 11.7%",
                "measured over all history rather than in the replay window (#114)"),
            Pin("91 tickers / 170 trades of 658 replayable",
                "measured under the has-any-bars test #139 replaced, which replayed "
                "one company's trade against another company's bars"),
        ),
    ),
    Anchor(
        key="detection_recall",
        label="Detection recall (A1), gate-invariant",
        kind=GATE_DEPENDENT,
        quantity=QUANTITY_DETECTION_RECALL,
        committed={"passed": 549, "of": 656},
        tolerance={"passed": 0, "of": 0},
        unit="trades",
        source="findings §3, §3b",
        # Gate-invariant: the funnel evaluates every stage unconditionally, so
        # #149's gate width does not move it. It is stamped at both versions whose
        # geometry it was measured under, and holds at either.
        measured_at=(2, 3),
        note=(
            "whether the detector would have fired on his name at all — never "
            "whether the name reached that night's field"
        ),
        superseded=(
            Pin("380 of 658",
                "measured under v1's hard 1.5×ADR cluster cut, before #154's "
                "far-outlier guard, and on the pre-#139 replayable population"),
        ),
    ),
    Anchor(
        key="in_field",
        label="Trades in the replayed field (A2 in_field), app universe",
        kind=GATE_DEPENDENT,
        quantity=QUANTITY_IN_FIELD,
        # §4b counted this over the *app's* universe, and #211 measured that the
        # figure is a property of that pairing rather than of the rubric. Naming
        # the universe here is what stops it being quoted at a run that screened
        # its field differently.
        universe=UNIVERSE_APP,
        # The gap rides on the same anchor as the count, because the count's
        # tolerance is only defensible while the gap's sign holds.
        committed={"in_field": 397, "of": 656, "gap_pp": 1.95},
        tolerance={
            "in_field": CONTAMINATION_TRADES,
            "of": 0,
            "gap_pp": FREE,
        },
        unit="trades",
        source="findings §4b",
        measured_at=(3,),
        first_measurement=True,
        tolerance_reason=(
            "#162: both committed in_field values were measured on a store that "
            "ranks five references as candidates. A fresh build shifts percentile "
            f"denominators by ~0.5%, so a difference up to {CONTAMINATION_TRADES} "
            "trades is the fix landing, not a bug. The gap's sign is not covered "
            "by this tolerance"
        ),
        sign_checked=("gap_pp",),
        note=(
            "a first measurement with no second one agreeing with it, so a "
            "mismatch is investigated in both directions rather than charged "
            "straight to the new pipeline"
        ),
        superseded=(
            Pin("349 of 656 at detector v2",
                "the live gate has moved v2 → v3; the v2 → v3 widening admits 48 "
                "more of his trades without any of them changing. Measured on the "
                "same contaminated field as the live value (#162), so the "
                "tolerance above is recorded on this row too — a run built at v2 "
                "anchors on it under exactly the same band"),
            Pin("159 of 656 at detector v2",
                "measured on the field the two-year rank retention had truncated "
                "(#164)"),
            Pin("104 of 656 at detector v1",
                "measured on the truncated field under v1's hard cluster cut"),
            Pin("104 of 658 at detector v1",
                "measured before #139 re-pinned the replayable population"),
        ),
    ),
    Anchor(
        key="in_field_stateless",
        label="Trades in the replayed field (A2 in_field), stateless universe",
        kind=GATE_DEPENDENT,
        quantity=QUANTITY_IN_FIELD,
        universe=UNIVERSE_STATELESS,
        committed={"in_field": 165, "of": 503, "gap_pp": -5.01},
        tolerance={
            # Zero on both counts, and deliberately not the app row's
            # contamination band: that band exists because both committed values
            # were measured on a store ranking five references as candidates
            # (#162), and the backtest store is the fresh build where that is
            # already fixed. There is nothing here for it to absorb.
            "in_field": 0,
            "of": 0,
            "gap_pp": FREE,
        },
        unit="trades",
        source="#198's full run, attributed by #211",
        measured_at=(3,),
        first_measurement=True,
        sign_checked=("gap_pp",),
        note=(
            "the same quantity as the row above, counted over the contract's "
            "stateless universe instead of the app's. The negative sign is the "
            "measured property, not a failure: #211 attributed it to the ADR20 "
            "floor and the trend gate acting together, each of which duplicates a "
            "rubric dimension and lifts the field's hit rate on it until no "
            "spread is left. Neither gate alone restores the sign and no constant "
            "was moved (references/backtest_gate_isolation.md)"
        ),
        tolerance_reason=(
            "a first measurement anchoring against the run that produced it, so "
            "it detects drift from here on rather than confirming this run. Two "
            "measurements #211 made over the app's universe are what corroborate "
            "it instead: §4b's own 397/656 (+1.95pp) reproduced exactly, and the "
            "same 503 names held fixed giving 324/503 (+1.86pp) — the pin is "
            "sound and the sign belongs to the pair of universes, not to a bug"
        ),
    ),
)

ANCHORS: tuple[Anchor, ...] = GEOMETRY_ANCHORS + GATE_DEPENDENT_ANCHORS

ANCHORS_BY_KEY: Mapping[str, Anchor] = {a.key: a for a in ANCHORS}


# Which field-membership row a measurement belongs to, by the universe it names.
# Derived from the table rather than written out again, so a third universe would
# arrive here by adding an anchor and not by remembering to edit a second map.
IN_FIELD_ANCHOR_BY_UNIVERSE: Mapping[str, str] = {
    a.universe: a.key
    for a in ANCHORS
    if a.quantity == QUANTITY_IN_FIELD and a.universe is not None
}


def gate_dependent_anchors(universe: str) -> tuple[Anchor, ...]:
    """The gate-dependent anchors that hold over ``universe``, in table order.

    Coverage and recall are universe-independent and appear whatever is asked
    for; ``in_field`` appears once, as whichever of its two rows was counted over
    the universe the run actually screened its field with. A run is therefore
    checked against **six** anchors, never seven — the second field row is a
    second pin for a different universe, not a second thing to satisfy.
    """
    if universe not in UNIVERSES:
        raise DriftError(
            f"unknown universe {universe!r}; a field figure is counted over "
            f"{' or '.join(UNIVERSES)} and a run that names neither cannot be "
            "anchored on a field row at all"
        )
    return tuple(
        a for a in GATE_DEPENDENT_ANCHORS
        if a.universe is None or a.universe == universe
    )


# -- measurements: the existing types, adapted --------------------------------


@dataclass(frozen=True)
class Measurement:
    """One anchor's measured value, tagged with what it *is*.

    ``quantity`` is the guard that keeps the two field anchors apart: it is set by
    the adapter that built the measurement, from the type it read, so a caller
    cannot offer the funnel's recall as the field-membership measurement. ``arm``
    is the exit arm the measurement was taken on where one applies; ``None`` for a
    quantity no exit touches (geometry, coverage, recall).
    """

    anchor: str
    quantity: str
    values: Mapping[str, float]
    arm: str | None = None
    detector_version: int | None = None
    # The universe the figure was counted over, where that is part of what the
    # figure is. Set by the adapter alongside ``anchor``, so the two cannot
    # disagree about which pin this measurement is for; ``None`` on every
    # quantity no gate touches.
    universe: str | None = None


@dataclass(frozen=True)
class GeometrySample:
    """The three geometry medians, measured over his entries at the eval session.

    ``n`` is how many trades carried all three; ``without_bars``,
    ``short_history`` and ``no_prior_session`` say where the rest went, because a
    median over a silently halved sample is the failure this anchor is meant to
    catch and it prints as a plausible number.
    """

    n: int
    median_range_3bar_adr: float | None
    median_range_5bar_adr: float | None
    median_adr_at_entry_eve: float | None
    without_bars: int
    short_history: int
    no_prior_session: int


def trailing_range_adr(bars: Sequence[Bar], as_of: int, k: int) -> float | None:
    """The trailing ``k``-bar range at index ``as_of``, in ADR units.

    ``(max high − min low) / (ADR × close)`` over the ``k`` bars ending at
    ``as_of``, ungated — the quantity findings §3b tabulates for every k in 3..7.
    The detector owns this ruler at ``k = K_MIN`` and only there
    (:func:`screener.detection.range_3bar_adr`), which is why this generalisation
    lives here rather than in the app: nothing the app does needs k = 5. It is
    checked against the detector's own function at k = 3 by
    ``test_the_five_bar_ruler_agrees_with_the_detectors_own_at_three_bars``, so
    the two cannot drift into disagreeing about the same number.

    ``None`` when the window runs off the front of the series or ADR is
    unavailable or non-positive.
    """
    if as_of < 0 or as_of >= len(bars) or k < 1:
        return None
    lo = as_of - k + 1
    if lo < 0:
        return None
    a = _adr(list(bars[: as_of + 1]))
    if a is None or a <= 0:
        return None
    adr_abs = a * bars[as_of].close
    if adr_abs <= 0:
        return None
    window = bars[lo : as_of + 1]
    return (max(b.high for b in window) - min(b.low for b in window)) / adr_abs


def _index_at(bars: Sequence[Bar], as_of: date) -> int | None:
    """Index of the last bar on or before ``as_of``, or ``None`` if there is none."""
    idx = None
    for i, bar in enumerate(bars):
        if bar.session > as_of:
            break
        idx = i
    return idx


def measure_geometry(
    store: Store,
    trades: Iterable[ExecutedTrade],
    *,
    market: str = ANCHOR_MARKET,
) -> GeometrySample:
    """Measure the three geometry anchors off ``store`` at his evaluation sessions.

    Point-in-time throughout: every value is read at the last session strictly
    before the entry (:func:`replay.reference.evaluation_session`), from bars at or
    before it, with the app's own ADR. Nothing is gated at measurement time — the
    ranges are the raw trailing spans, which is what makes them anchor the store
    rather than the detector.

    A trade contributes to all three medians or to none of them, so the three
    figures are taken over one sample and a divergence between them cannot be a
    difference in who was included.
    """
    calendar = store.sessions(market)
    ranges3: list[float] = []
    ranges5: list[float] = []
    adrs: list[float] = []
    without_bars = short_history = no_prior_session = 0

    for trade in trades:
        bars = store.bars(market, trade.ticker)
        if not bars:
            without_bars += 1
            continue
        eve = evaluation_session(calendar, trade.entry_date)
        if eve is None:
            no_prior_session += 1
            continue
        idx = _index_at(bars, eve)
        if idx is None or idx + 1 < ADR_WINDOW:
            short_history += 1
            continue
        a = _adr(list(bars[: idx + 1]))
        r3 = trailing_range_adr(bars, idx, K_MIN)
        r5 = trailing_range_adr(bars, idx, 5)
        if a is None or a <= 0 or r3 is None or r5 is None:
            short_history += 1
            continue
        adrs.append(a)
        ranges3.append(r3)
        ranges5.append(r5)

    return GeometrySample(
        n=len(adrs),
        median_range_3bar_adr=median(ranges3) if ranges3 else None,
        median_range_5bar_adr=median(ranges5) if ranges5 else None,
        median_adr_at_entry_eve=median(adrs) if adrs else None,
        without_bars=without_bars,
        short_history=short_history,
        no_prior_session=no_prior_session,
    )


def geometry_measurements(
    measured: GeometrySample,
) -> list[Measurement]:
    """The three geometry medians as anchor measurements.

    A median that could not be computed is offered as ``nan`` rather than skipped:
    an anchor with no measurement must fail, not vanish from the report.
    """
    values = {
        "median_range_3bar_adr": measured.median_range_3bar_adr,
        "median_range_5bar_adr": measured.median_range_5bar_adr,
        "median_adr_at_entry_eve": measured.median_adr_at_entry_eve,
    }
    return [
        Measurement(
            anchor=key,
            quantity=QUANTITY_GEOMETRY,
            values={"median": float("nan") if value is None else value},
        )
        for key, value in values.items()
    ]


def coverage_measurement(report: ReferenceReport) -> Measurement:
    """The blind-spot coverage anchor, read off the reference report.

    The same report :func:`replay.reference.assert_matches_reference` checks, and
    against the same committed numbers — this anchor reports it in Phase 6's order
    beside the others rather than measuring it a second way.
    """
    return Measurement(
        anchor="coverage_blind_spot",
        quantity=QUANTITY_COVERAGE,
        values={
            "blind_spot_tickers": report.blind_spot_tickers,
            "blind_spot_trades": report.blind_spot_trades,
            "distinct_tickers": report.distinct_tickers,
            "total_rows": report.total_rows,
            "rows_with_outcomes": report.rows_with_outcomes,
            "blind_spot_r_share": report.blind_spot_r_share,
        },
    )


def detection_recall_measurement(
    *, passed: int, of: int, stage: str, arm: str | None = None
) -> Measurement:
    """Detection recall, from a measurement that names the **stage** it came off.

    The narrow gate every route into this anchor goes through, in-process or from
    a file. It exists because the conflation #165 fixed cannot be prevented by a
    parameter name: what makes recall *recall* is that it was measured at the
    funnel's detection stage, so the caller states which stage it read and a
    measurement from any other one is refused. The liquidity stage's recall is a
    real number and is not this anchor.
    """
    if stage != STAGE_DETECTION:
        raise DriftError(
            f"detection recall must be read off the funnel's detection stage; "
            f"got the {stage!r} stage"
        )
    return Measurement(
        anchor="detection_recall",
        quantity=QUANTITY_DETECTION_RECALL,
        values={"passed": passed, "of": of},
        arm=arm,
    )


def field_membership_measurement(
    *,
    in_field: int,
    replayable: int,
    gap_pp: float | None,
    field_source: str,
    universe: str,
    detector_version: int | None,
    arm: str | None = None,
) -> Measurement:
    """``in_field`` and §4b's gap, from a measurement that names its **field**.

    The counterpart gate, and the reason both exist as functions rather than as
    type signatures alone: the command reads its field anchors from a file, and a
    guard that only holds for in-process callers does not hold on the one path the
    documented reproduction command uses.

    The field must be the **whole** one: the truncated field is the population
    #164 found the two-year rank retention had emptied on 316 of 821 sessions, and
    every figure taken over it is superseded.

    ``universe`` says which of the two pins this measurement is for, and has no
    default. The same grid measures both — #211's isolation ran
    :func:`~replay.discrimination_grid.run_grid` over the backtest store, and
    §4b's own figure came off it over the replay store — so there is no universe a
    caller can be assumed to have meant, and guessing wrong is precisely the
    conflation the second pin exists to prevent.
    """
    if field_source != FIELD_WHOLE.name:
        raise DriftError(
            f"in_field is anchored on the whole field; got the "
            f"{field_source!r} field, whose figures are superseded"
        )
    if universe not in IN_FIELD_ANCHOR_BY_UNIVERSE:
        raise DriftError(
            f"in_field must name the universe it was counted over "
            f"({' or '.join(UNIVERSES)}); got {universe!r}. #211 measured that "
            "the figure is a property of the pair, so one without a universe is "
            "not a number that can be checked against anything"
        )
    return Measurement(
        anchor=IN_FIELD_ANCHOR_BY_UNIVERSE[universe],
        quantity=QUANTITY_IN_FIELD,
        values={
            "in_field": in_field,
            "of": replayable,
            "gap_pp": float("nan") if gap_pp is None else gap_pp,
        },
        arm=arm,
        detector_version=detector_version,
        universe=universe,
    )


def recall_measurement(stage: StageRecall, *, arm: str | None = None) -> Measurement:
    """Detection recall, read off a funnel report's :class:`StageRecall`."""
    return detection_recall_measurement(
        passed=stage.passed, of=stage.total, stage=stage.stage, arm=arm
    )


def in_field_measurement(
    cell: CellMeasurement,
    *,
    replayable: int,
    universe: str,
    arm: str | None = None,
) -> Measurement:
    """``in_field`` and §4b's gap, read off one grid cell.

    The gap is the cell's own
    :meth:`~replay.discrimination_grid.CellMeasurement.edge` under the rubric §4b
    published it with, so the sign this anchor guards is the sign §4b states.

    ``universe`` is required and is not inferred from the cell: a cell knows which
    store and which detector it came from, and nothing in it records which set of
    gates screened the field underneath. That is the caller's fact to state.
    """
    return field_membership_measurement(
        in_field=cell.in_field,
        replayable=replayable,
        gap_pp=cell.edge(PUBLISHED_RUBRIC),
        field_source=cell.field_source.name,
        universe=universe,
        detector_version=cell.detector.version,
        arm=arm,
    )


# -- the check ----------------------------------------------------------------


# The three verdicts an anchor can carry, named because they are also read back
# off the serialised report by whoever is deciding whether a run may be believed
# (:func:`backtest.full_run.read_anchor_report`). A verdict compared against a
# string literal on the far side of a JSON file is a match nobody would notice
# breaking.
VERDICT_MATCH = "match"
VERDICT_EXPLAINED = "diverged (explained)"
VERDICT_FAILED = "FAILED"

# The verdicts that license reading a figure: reproduced, or diverged with a
# cause written down. The plan's "reproduce it, or explain the divergence in
# writing", as data.
SETTLED_VERDICTS = (VERDICT_MATCH, VERDICT_EXPLAINED)


@dataclass(frozen=True)
class ComponentCheck:
    """One component of one anchor: what was committed, what came back, and why
    the difference did or did not pass."""

    name: str
    committed: float
    measured: float
    tolerance: float | None
    matched: bool
    sign_flipped: bool

    @property
    def divergence(self) -> float:
        return self.measured - self.committed


@dataclass(frozen=True)
class AnchorCheck:
    """One anchor's verdict, with its components and any written divergence."""

    anchor: Anchor
    measurement: Measurement | None
    components: tuple[ComponentCheck, ...]
    explanation: str | None = None

    @property
    def matched(self) -> bool:
        return bool(self.components) and all(c.matched for c in self.components)

    @property
    def sign_flipped(self) -> bool:
        """Whether a sign-checked component came back with the wrong sign."""
        return any(c.sign_flipped for c in self.components)

    @property
    def explained(self) -> bool:
        """A divergence with a cause written down. Recorded as a divergence, never
        reported as a match — the plan's "or explain the divergence in writing".

        **A sign flip is not explainable.** The whole reason §4b's gap rides on
        this anchor is that a flip is the bug the table exists to find, and a
        failure a free-text argument can wave through is not a failure. So the
        tolerance cannot absorb it and neither can a write-up: it is the one
        outcome here that must stop the run and be investigated in the pipeline
        rather than in the report.
        """
        return not self.matched and bool(self.explanation) and not self.sign_flipped

    @property
    def passes(self) -> bool:
        return self.matched or self.explained

    @property
    def verdict(self) -> str:
        if self.matched:
            return VERDICT_MATCH
        if self.explained:
            return VERDICT_EXPLAINED
        return VERDICT_FAILED


@dataclass(frozen=True)
class AnchorReport:
    """The Phase 6 result: geometry apart from gate-dependent, in that order.

    ``geometry_only`` is set when the gate-dependent anchors were not read at all
    — a geometry failure stopped the check, or their measurements never arrived.
    The report says so rather than printing an empty section that reads as three
    passes, and :attr:`passes` is false whatever the geometry did: a partially
    anchored run is not an anchored run.
    """

    detector_version: int
    arms: tuple[str, ...]
    geometry: tuple[AnchorCheck, ...]
    gate_dependent: tuple[AnchorCheck, ...]
    geometry_only: bool = False
    sample: GeometrySample | None = None
    # Which universe the field rows were counted over. On the report rather than
    # left to the caller because #211's rule is that §4b's gap may not be cited
    # without naming the field it was measured over, and this report is the
    # citation every later phase reads.
    universe: str = UNIVERSE_APP

    @property
    def checks(self) -> tuple[AnchorCheck, ...]:
        return self.geometry + self.gate_dependent

    @property
    def passes(self) -> bool:
        return not self.geometry_only and all(c.passes for c in self.checks)

    @property
    def failed(self) -> tuple[str, ...]:
        """The anchors that neither matched nor carry a written cause.

        Beside :attr:`passes`, because it answers the follow-up question — *which
        ones* — and a caller deriving it for itself has to walk from the report to
        each check to its anchor to its key, which is a path this class should not
        be exporting.
        """
        return tuple(c.anchor.key for c in self.checks if not c.passes)

    @property
    def first_measurement(self) -> tuple[str, ...]:
        """The anchors checked that have no second measurement agreeing with them.

        Reported beside :attr:`passes` because it is the one thing a settled
        verdict does not say: a pin measured by the run it anchors detects drift
        from here on and cannot corroborate that run, and a reader who sees only
        "settled" would take it for independent confirmation.
        """
        return tuple(
            c.anchor.key for c in self.checks if c.anchor.first_measurement
        )

    @property
    def explained(self) -> tuple[str, ...]:
        """The anchors that diverged and carry a written cause.

        The other half of :attr:`failed`: together they are the difference between
        the plan's two ways of passing, and every result built over this report
        reports them.
        """
        return tuple(c.anchor.key for c in self.checks if c.explained)


def _matches(value: float, committed: float, tolerance: float | None) -> bool:
    if isnan(value):
        return False
    if tolerance is FREE:
        return True
    return abs(value - committed) <= tolerance


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)


def _check_one(
    anchor: Anchor,
    measurement: Measurement | None,
    *,
    detector_version: int,
    explanation: str | None,
) -> AnchorCheck:
    if measurement is None:
        raise DriftError(
            f"anchor {anchor.key!r} ({anchor.label}) has no measurement; every "
            "anchor is checked or the run is not anchored"
        )
    if measurement.quantity != anchor.quantity:
        raise DriftError(
            f"anchor {anchor.key!r} measures {anchor.quantity!r}, but the "
            f"measurement offered is {measurement.quantity!r}. These are "
            "different quantities and were conflated once already (#165): "
            "detection recall is gate-invariant, in_field moves with every gate"
        )
    if anchor.universe is not None and measurement.universe != anchor.universe:
        raise DriftError(
            f"anchor {anchor.key!r} is pinned over the {anchor.universe!r} "
            f"universe, but the measurement offered was counted over "
            f"{measurement.universe!r}. {WHY_UNIVERSE_MATTERS}; anchor the run "
            "against the pin measured over the universe it ran"
        )
    if measurement.arm is not None and measurement.arm not in ANCHOR_ARMS:
        raise DriftError(
            f"anchor {anchor.key!r} was measured on arm {measurement.arm!r}, which "
            f"has no counterpart in the reference set; anchor against arms "
            f"{', '.join(ANCHOR_ARMS)} only"
        )
    if not anchor.holds_at(detector_version):
        raise DriftError(
            f"anchor {anchor.key!r} has no committed value at detector "
            f"v{detector_version}; it was measured at {anchor.detector_stamp}, and "
            "a value quoted from the wrong version fails for a reason that has "
            "nothing to do with the pipeline it is testing"
        )
    if (
        measurement.detector_version is not None
        and measurement.detector_version != detector_version
    ):
        raise DriftError(
            f"anchor {anchor.key!r} was measured at detector "
            f"v{measurement.detector_version}, but the run is built at "
            f"v{detector_version}; anchor against the version the run is built at"
        )

    components: list[ComponentCheck] = []
    for name, committed in anchor.committed.items():
        if name not in measurement.values:
            raise DriftError(
                f"anchor {anchor.key!r} is missing its {name!r} component; a row "
                "quoting two numbers cannot pass on one of them"
            )
        value = float(measurement.values[name])
        tolerance = anchor.tolerance[name]
        flipped = name in anchor.sign_checked and (
            isnan(value) or _sign(value) != _sign(committed)
        )
        components.append(
            ComponentCheck(
                name=name,
                committed=committed,
                measured=value,
                tolerance=tolerance,
                matched=_matches(value, committed, tolerance) and not flipped,
                sign_flipped=flipped,
            )
        )
    return AnchorCheck(
        anchor=anchor,
        measurement=measurement,
        components=tuple(components),
        explanation=explanation,
    )


def _describe(check: AnchorCheck) -> str:
    bits = []
    for c in check.components:
        if c.matched:
            continue
        if c.sign_flipped:
            bits.append(
                f"{c.name}: got {c.measured:+.4g}, §4b committed "
                f"{c.committed:+.4g} — the sign flipped, which the "
                "reference-contamination tolerance does not cover"
            )
        else:
            bits.append(
                f"{c.name}: got {c.measured:.6g}, committed {c.committed:.6g} "
                f"(tolerance ±{c.tolerance:g})"
            )
    return f"{check.anchor.key} ({check.anchor.label}) — " + "; ".join(bits)


def _index(
    measurements: Iterable[Measurement],
    *,
    explained: Mapping[str, str],
    arms: Sequence[str],
) -> dict[str, Measurement]:
    """One measurement per anchor, with the two refusals that precede any check."""
    unknown = set(explained) - set(ANCHORS_BY_KEY)
    if unknown:
        raise DriftError(
            f"explanation offered for unknown anchor(s): {', '.join(sorted(unknown))}"
        )
    refused = [a for a in arms if a not in ANCHOR_ARMS]
    if refused:
        raise DriftError(
            f"arm(s) {', '.join(refused)} have no counterpart in the reference set "
            f"and are measured, never anchored; anchor against "
            f"{', '.join(ANCHOR_ARMS)} only"
        )

    by_anchor: dict[str, Measurement] = {}
    for m in measurements:
        if m.anchor not in ANCHORS_BY_KEY:
            raise DriftError(f"measurement offered for unknown anchor {m.anchor!r}")
        if m.anchor in by_anchor:
            raise DriftError(
                f"two measurements offered for anchor {m.anchor!r}; an anchor has "
                "one measured value or it has none"
            )
        by_anchor[m.anchor] = m
    return by_anchor


def check_geometry(
    measurements: Iterable[Measurement],
    *,
    detector_version: int = DETECTOR_VERSION,
    explained: Mapping[str, str] | None = None,
    arms: Sequence[str] = ANCHOR_ARMS,
) -> tuple[AnchorCheck, ...]:
    """The three geometry anchors alone, checked without raising on a mismatch.

    The group :func:`check_anchors` runs first. Exposed on its own so a command
    that cannot reach the gate-dependent measurements still *reports* what the
    store's geometry did, rather than printing nothing and leaving the reader to
    infer whether it was checked.
    """
    explained = dict(explained or {})
    return _check_group(
        GEOMETRY_ANCHORS,
        _index(measurements, explained=explained, arms=arms),
        detector_version=detector_version,
        explained=explained,
    )


def _check_group(
    anchors: Sequence[Anchor],
    by_anchor: Mapping[str, Measurement],
    *,
    detector_version: int,
    explained: Mapping[str, str],
) -> tuple[AnchorCheck, ...]:
    """One group's checks, in the group's own order."""
    return tuple(
        _check_one(a, by_anchor.get(a.key), detector_version=detector_version,
                   explanation=explained.get(a.key))
        for a in anchors
    )


def _refuse_foreign_universe(
    by_anchor: Mapping[str, Measurement], universe: str
) -> None:
    """Refuse a field figure counted over a universe other than the run's.

    Without this the mismatch arrives as "anchor ``in_field`` has no measurement",
    which reads as a caller who forgot a row rather than as a caller who handed
    over the other universe's — and the second is the mistake worth naming,
    because it is the one that used to surface as a sign flip charged to the
    pipeline.
    """
    wanted = IN_FIELD_ANCHOR_BY_UNIVERSE[universe]
    for key, measurement in by_anchor.items():
        if measurement.quantity != QUANTITY_IN_FIELD or key == wanted:
            continue
        raise DriftError(
            f"the run was anchored over the {universe!r} universe, but the "
            f"field-membership measurement offered was counted over "
            f"{measurement.universe!r}. {WHY_UNIVERSE_MATTERS}. Anchor over "
            f"{measurement.universe!r}, or hand over the figures the "
            f"{universe!r} universe produced"
        )


def check_anchors(
    measurements: Iterable[Measurement],
    *,
    detector_version: int = DETECTOR_VERSION,
    explained: Mapping[str, str] | None = None,
    arms: Sequence[str] = ANCHOR_ARMS,
    sample: GeometrySample | None = None,
    universe: str = UNIVERSE_APP,
) -> AnchorReport:
    """Check every anchor, geometry first, and fail loudly on a mismatch.

    Raises :class:`replay.reference.DriftError` — the study's existing drift
    mechanism — on the first group that fails. The **geometry** anchors are checked
    and reported apart from the gate-dependent ones, and a geometry failure stops
    the check: if the store's own geometry does not reproduce, no gate-dependent
    figure measured over that store is worth investigating yet.

    ``explained`` maps an anchor key to a written cause. A divergence with a cause
    is recorded as a divergence and does not raise (the plan's "reproduce it, or
    explain the divergence in writing"); it never prints as a match. A divergence
    without one raises.

    ``universe`` names the field the run screened, and selects which of the two
    ``in_field`` pins it is held to (:func:`gate_dependent_anchors`). It is
    checked against what the measurement itself says it counted, so a caller who
    names one universe and hands over the other's figures is refused rather than
    reported as a sign flip.
    """
    explained = dict(explained or {})
    by_anchor = _index(measurements, explained=explained, arms=arms)
    gate_dependent_group = gate_dependent_anchors(universe)
    _refuse_foreign_universe(by_anchor, universe)

    geometry = _check_group(
        GEOMETRY_ANCHORS, by_anchor, detector_version=detector_version,
        explained=explained,
    )
    failed = [c for c in geometry if not c.passes]
    if failed:
        raise DriftError(
            "the geometry anchors did not reproduce, so the gate-dependent "
            "anchors were not read — these are measured from his bars and hold "
            "whatever the detector does, so a failure here is the store or the "
            "indicators and nothing downstream is worth investigating yet:\n  "
            + "\n  ".join(_describe(c) for c in failed)
        )

    gate_dependent = _check_group(
        gate_dependent_group, by_anchor, detector_version=detector_version,
        explained=explained,
    )
    failed = [c for c in gate_dependent if not c.passes]
    if failed:
        raise DriftError(
            f"the gate-dependent anchors did not reproduce at detector "
            f"v{detector_version}:\n  "
            + "\n  ".join(_describe(c) for c in failed)
        )

    return AnchorReport(
        detector_version=detector_version,
        arms=tuple(arms),
        geometry=geometry,
        gate_dependent=gate_dependent,
        sample=sample,
        universe=universe,
    )


# -- reporting ----------------------------------------------------------------


def _component_dict(c: ComponentCheck) -> dict[str, Any]:
    return {
        "component": c.name,
        "committed": c.committed,
        "measured": None if isnan(c.measured) else c.measured,
        "tolerance": c.tolerance,
        "divergence": None if isnan(c.measured) else c.divergence,
        "matched": c.matched,
        "sign_flipped": c.sign_flipped,
    }


def _check_dict(check: AnchorCheck) -> dict[str, Any]:
    a = check.anchor
    return {
        "anchor": a.key,
        "label": a.label,
        "kind": a.kind,
        "quantity": a.quantity,
        "universe": a.universe,
        "unit": a.unit,
        "source": a.source,
        "detector_stamp": a.detector_stamp,
        "measured_at_detector": list(a.measured_at),
        "first_measurement": a.first_measurement,
        "tolerance_reason": a.tolerance_reason,
        "note": a.note,
        "superseded": [{"value": p.value, "why": p.why} for p in a.superseded],
        "arm": check.measurement.arm if check.measurement else None,
        "verdict": check.verdict,
        "explanation": check.explanation,
        "components": [_component_dict(c) for c in check.components],
    }


def anchors_report(contract: RunContract, report: AnchorReport) -> dict[str, Any]:
    """The anchor report as a stamped, serialisable payload.

    Geometry and gate-dependent are separate keys, not one list with a field to
    filter on: the plan's order is a claim about what is worth reading when, and a
    reader who has to sort the rows to recover it will not.
    """
    body: dict[str, Any] = {
        "detector_version": report.detector_version,
        "universe": report.universe,
        "arms_anchored": list(report.arms),
        "arms_measured_never_anchored": list(MEASURED_NEVER_ANCHORED),
        "geometry": [_check_dict(c) for c in report.geometry],
        "gate_dependent": [_check_dict(c) for c in report.gate_dependent],
        "geometry_only": report.geometry_only,
        "passes": report.passes,
    }
    if report.sample is not None:
        s = report.sample
        body["geometry_sample"] = {
            "n": s.n,
            "without_bars": s.without_bars,
            "short_history": s.short_history,
            "no_prior_session": s.no_prior_session,
        }
    return stamp_result(contract, body)


def _format_check(check: AnchorCheck) -> list[str]:
    a = check.anchor
    lines = [f"  {a.label}", f"    stamp     {a.detector_stamp} — {a.source}"]
    if a.universe is not None:
        lines.append(f"    universe  {a.universe}")
    for c in check.components:
        mark = "ok " if c.matched else "!! "
        measured = "n/a" if isnan(c.measured) else f"{c.measured:.6g}"
        tolerance = "free" if c.tolerance is FREE else f"±{c.tolerance:g}"
        lines.append(
            f"    {mark}{c.name:<20} committed {c.committed:<10.6g} "
            f"measured {measured:<10} ({tolerance} {a.unit})"
        )
        if c.sign_flipped:
            lines.append(
                "       ⚠ the sign of §4b's gap flipped — not covered by the "
                "reference-contamination tolerance"
            )
    if a.first_measurement:
        lines.append(
            "    ⚠ first measurement: no second measurement agrees with it, so a "
            "mismatch is investigated in both directions"
        )
    if a.tolerance_reason:
        lines.append(f"    tolerance {a.tolerance_reason}")
    for pin in a.superseded:
        lines.append(f"    superseded {pin.value} — {pin.why}")
    if check.explanation:
        lines.append(f"    divergence written up: {check.explanation}")
    lines.append(f"    verdict   {check.verdict}")
    return lines


def format_anchors(report: AnchorReport) -> str:
    """The anchor table as a page a terminal can print, in the plan's order."""
    lines = [
        f"anchors — detector v{report.detector_version}, "
        f"universe {report.universe}, "
        f"arms {', '.join(report.arms)} "
        f"(arm{'s' if len(ARM_SPECS) - len(ANCHOR_ARMS) > 1 else ''} "
        f"{', '.join(a for a in sorted(ARM_SPECS) if a not in ANCHOR_ARMS)} "
        "measured, never anchored)",
        "",
        "geometry — measured from his bars; these hold whatever the detector does",
        "",
    ]
    for check in report.geometry:
        lines += _format_check(check) + [""]
    if report.sample is not None:
        s = report.sample
        lines += [
            f"  sample: {s.n} trades  (no bars {s.without_bars}, short history "
            f"{s.short_history}, no prior session {s.no_prior_session})",
            "",
        ]
    if report.geometry_only:
        lines += [
            "gate-dependent — NOT CHECKED",
            "  the geometry anchors did not reproduce, so nothing downstream is "
            "worth investigating yet",
            "",
        ]
        return "\n".join(lines).rstrip() + "\n"
    lines += [
        "gate-dependent — these move with coverage and with the gates",
        "",
    ]
    for check in report.gate_dependent:
        lines += _format_check(check) + [""]
    return "\n".join(lines).rstrip() + "\n"


# -- command-line entry point -------------------------------------------------


def _field_measurements(path: str) -> list[Measurement]:
    """The two field anchors, read from a JSON the field pass wrote.

    Deliberately not computed here. Detection recall and ``in_field`` come from a
    funnel and a discrimination grid over the run's own field, which is the run
    (#198), not a side-car to it; inventing them here would anchor the new pipeline
    against the old pipeline's outputs and report a pass for it.

    It goes through the same two gates an in-process caller does
    (:func:`detection_recall_measurement`, :func:`field_membership_measurement`),
    which is why each row must name **what it measured** rather than only its
    numbers: the ``stage`` the recall came off and the ``field`` the membership was
    counted over. Without those the file could offer the funnel's recall under the
    ``in_field`` key and be believed, and the command is the one path the
    documented reproduction uses.

    Since #211 the ``in_field`` row must also name the **universe** it screened
    its field with, for the same reason it must name the field: the file is the
    one path the documented reproduction uses, and a row without a universe is a
    figure that could be checked against either pin and would be believed against
    whichever one it was handed to.

    Schema — the numbers the two passes already print, and what they were::

        {"detection_recall": {"passed": 549, "of": 656, "stage": "detection"},
         "in_field": {"in_field": 397, "of": 656, "gap_pp": 1.95,
                      "field": "whole", "universe": "app",
                      "detector_version": 3}}
    """
    body = json.loads(Path(path).read_text())
    out: list[Measurement] = []
    if "detection_recall" in body:
        row = body["detection_recall"]
        out.append(
            detection_recall_measurement(
                passed=row["passed"], of=row["of"], stage=row["stage"],
                arm=row.get("arm"),
            )
        )
    if "in_field" in body:
        row = body["in_field"]
        if "universe" not in row:
            raise DriftError(
                f"{path}: the in_field row does not name the universe it was "
                f"counted over, and {WHY_UNIVERSE_MATTERS}. A row without one "
                "cannot be checked against either pin"
            )
        out.append(
            field_membership_measurement(
                in_field=row["in_field"],
                replayable=row["of"],
                gap_pp=row["gap_pp"],
                field_source=row["field"],
                universe=row["universe"],
                detector_version=row.get("detector_version"),
                arm=row.get("arm"),
            )
        )
    return out


def _universe_of(field_rows: Sequence[Measurement], path: str) -> str:
    """The universe a field-measurements file counted its ``in_field`` row over.

    There is no default. A file carrying no ``in_field`` row names no universe,
    and picking one for it would decide at the command line the very thing the
    file exists to record.
    """
    for m in field_rows:
        if m.quantity == QUANTITY_IN_FIELD and m.universe:
            return m.universe
    raise DriftError(
        f"{path}: no in_field row, so the file names no universe and the run "
        "cannot be anchored on a field row at all"
    )


def main(argv: list[str] | None = None) -> int:
    """Check the six anchors against a built store, and write the result.

    The command that reproduces Phase 6::

        python -m backtest.anchors --store data/backtest.duckdb \\
            --field-measurements references/backtest_field_anchors.json \\
            --out-json references/backtest_anchors.json

    Geometry and coverage are measured here off the store and the reference set.
    The two field anchors are **read**, not computed: they come from the run's own
    funnel and discrimination grid, and a command that recomputed them from the
    reference study's outputs would anchor the new pipeline against the old one.
    Without them the command reports what it checked and exits non-zero, because a
    partially anchored run is not an anchored run.

    That file also names the **universe** the run screened its field with, and the
    command takes it from there rather than from a flag of its own — which of
    ``in_field``'s two pins applies is a fact the run recorded, not a choice the
    person typing the command gets to make (#211).
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--market", default=ANCHOR_MARKET,
                        help="the market his entries are anchored in")
    parser.add_argument("--field-measurements", default=None,
                        help="JSON carrying the run's detection-recall and in_field "
                             "measurements (see _field_measurements)")
    parser.add_argument("--explain", action="append", default=[],
                        metavar="ANCHOR=CAUSE",
                        help="record a written cause for a diverging anchor "
                             "(repeatable); a divergence without one fails")
    parser.add_argument("--out-json", default=None,
                        help="where to write the contract-stamped result")
    args = parser.parse_args(argv)

    explained: dict[str, str] = {}
    for item in args.explain:
        key, _, cause = item.partition("=")
        if not cause.strip():
            raise SystemExit(f"--explain {item!r} carries no cause")
        explained[key.strip()] = cause.strip()

    store = Store.open(args.store)
    try:
        trades = load_trades(args.reference)
        geometry = measure_geometry(store, trades, market=args.market)
        coverage = build_report(trades, store, market=args.market)
    finally:
        store.close()

    measurements = [*geometry_measurements(geometry), coverage_measurement(coverage)]

    if not args.field_measurements:
        # Report the geometry, then refuse: the two field anchors were never
        # offered, and a run anchored on four of six is not anchored.
        report = AnchorReport(
            detector_version=DETECTOR_VERSION,
            arms=ANCHOR_ARMS,
            geometry=check_geometry(measurements, explained=explained),
            gate_dependent=(),
            geometry_only=True,
            sample=geometry,
        )
        print(format_anchors(report))
        print(
            "--field-measurements was not given, so detection recall and in_field "
            "were not checked; the run is not anchored"
        )
        return 1

    try:
        # Inside the same guard as the check itself: a field row that does not
        # name the whole field, or a recall row that does not name the detection
        # stage, is a refusal of the same kind and reads better as one printed
        # line than as a traceback.
        field_rows = _field_measurements(args.field_measurements)
        measurements += field_rows
        # The universe comes off the file rather than off a flag of its own.
        # The file is where the run recorded which gates screened its field, and
        # a flag beside it could only ever agree with that or contradict it.
        # A file with no in_field row at all leaves nothing to read it off, and
        # raises here rather than falling back to a universe nobody named — the
        # check that follows would fail anyway, and it would fail describing a
        # missing anchor instead of a file that never said which field it counted.
        universe = _universe_of(field_rows, args.field_measurements)
        report = check_anchors(
            measurements, explained=explained, sample=geometry, universe=universe
        )
    except DriftError as exc:
        print(str(exc))
        return 1

    print(format_anchors(report))
    if args.out_json:
        payload = anchors_report(DEFAULT_CONTRACT, report)
        Path(args.out_json).write_text(json.dumps(payload, indent=1) + "\n")
        print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
