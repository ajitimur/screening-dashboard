"""Do the registered candidate dimensions predict, or only select? (issue #195).

Both dimensions ADR 0005 has registered, measured against **outcomes** rather than
against the trader's selection, per market, on the mechanical denominator.

Why this measurement exists
---------------------------
ADR 0005 admits a dimension on a **selection contrast** — a candidate's hit rate
among the detections the trader took against its hit rate among the ones he passed
over, no outcome variable anywhere in it. That instrument was not chosen; it was
what existed. The ADR's own "considered options" records the alternative as *not
available*: findings §5a had found no dimension predicting MFE, and there was no
out-of-sample outcome to regress against.

Both registrations then ran into the limits of that instrument:

* ``RS line`` was refused on criterion 4 for a wrong-way Δ (findings §5d), on a
  dimension firing on one detection in ten in *both* groups.
* ``Relative move`` came back positive on both fields and then stalled **0.06pp**
  inside criterion 1's ~85% not-taken hit-rate ceiling (§5e). That ceiling and
  criterion 2's ~15% disagreement floor are **one threshold read from two sides**
  — disagreement with ``Prior move`` is exactly ``1 − hit rate`` — which is why
  the two criteria are the same number and land together: on the literal reading
  criterion 1 admits the dimension, on any reading honouring the tilde criterion 2
  refuses it. The ADR calls that magnitude "the one magnitude in this design with
  nothing behind it", and it now decides an admission by six hundredths of a
  point. The ADR declined to resolve it and recorded that no third candidate
  should register until the threshold is argued on its own.

This run gives the same two dimensions an outcome variable: **R after costs**, on
trades taken mechanically over two markets and fourteen years, which no rubric
weight was fitted to and no detection could see. A dimension that ranks *outcomes*
is a different and stronger claim than one that matches his *selection*, and the
two must never be conflated — so the published selection figures ride on every
candidate's cell (:data:`SELECTION_CONTRAST`) under their own verdict key, beside
the sentence saying why they cannot be added up.

Three groups, because absence is not a miss
-------------------------------------------
Each candidate splits its cohort three ways, never two:

* :data:`GROUP_HIT` and :data:`GROUP_MISS` — the pre-registered cut applied at
  **read time** by the rubric's own reader (:data:`replay.contrast.CANDIDATES`),
  off the value the persisted row carries. The row is never re-denominated: a
  later argument about where the cut belongs re-reads these rows rather than
  rewriting them, which is the whole point of persisting a value (#154).
* :data:`GROUP_ABSENT` — the question was never asked. ``relative_move`` is
  ``None`` when the name had not listed six months back or has no ADR;
  ``rs_line`` is ``None`` when a price was missing at one of its two anchors.

The absent group is not a convenience. ``Relative move``'s cut sits at **zero**,
so an absence coerced to 0.0 would not merely be a guess — it would land exactly
on the boundary and let the strictness of a comparison decide a verdict nobody
measured. Absence therefore has its own group, its own n and its own cell, and it
enters no gap.

What the shipped boolean would do is reported too, and separately
-----------------------------------------------------------------
The pre-registered readers score an absent value ``False``, so a dimension shipped
as a rubric row would put those trades on the miss side. That reading is worth
having — it is what the rubric would actually apply — but it answers a different
question from "does the measured quantity predict". It rides beside the primary
gap as ``rubric_reading``, and :data:`VERDICT_RULE` puts it outside the verdict.

One statistic decides, and it is the gap
----------------------------------------
ADR 0005 admits a dimension **as a boolean** (grading needs demonstrated signal,
which a candidate by definition has none of), so the claim this run can act on is
the gap between the two sides. Spearman's rho against the *stored value* is
reported beside it, because ``Relative move`` persists a real number in ADR units
and that is the grading question ADR 0004 would ask later — but it does not enter
the verdict, for a reason that is structural rather than cautious: ``RS line``
persists only a boolean, so a rule reading rho would mean different things for the
two dimensions.

Nothing here admits a dimension
-------------------------------
Not by construction and not by omission: :func:`check_not_admitted` refuses to run
if a registered candidate has entered the live rubric, and :data:`ADMISSION_NOTE`
says on the payload that admission is ADR 0005's instrument rather than this one's.
The result is evidence that goes through the calibration rule like any other
change.

Everything else is the metric's
-------------------------------
The after-cost R of a trade, the per-market costs, the cell behind every group and
the clustered bootstrap are :mod:`backtest.metric`'s and
:mod:`backtest.stats`', on the same seed, cluster
and floor — so this measurement and the headline can never disagree about what a
trade paid, and two intervals in one run were never built differently.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Sequence

from replay.contrast import CANDIDATES
from replay.field import ScoredDetection
from screener.relative_strength import RELATIVE_MOVE_CUT
from screener.score import DIMENSIONS
from screener.store import Store

from .cohort import DetectionIndex, detection_index, join_detections
from .contract import DEFAULT_CONTRACT, SCOPE_MARKETS_KEY, RunContract
from .denominator import DenominatorStore, denominator_path
from .metric import (
    BOOTSTRAP_CLUSTER,
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    PRIMARY_ARM,
    after_cost_r,
    check_costs,
    check_one_market_one_arm,
    expectancy_cell,
)
from .result import stamp_result
from .run import ContractDrift
from .simulate import SimulatedTrade, simulate_market
from .stats import (
    bootstrap_symbol_statistic,
    cluster_by_symbol,
    format_interval,
    intervals_reported,
    spearman,
)

# -- the three groups ---------------------------------------------------------

# A hit, a miss, and the rows where the question was never asked. Three tokens
# rather than a boolean and a flag, because every count, cell and share in the
# report is keyed by one of them and a two-valued split with an exception beside
# it is the shape that lets an absence quietly become a miss.
GROUP_HIT = "hit"
GROUP_MISS = "miss"
GROUP_ABSENT = "absent"

GROUPS: tuple[str, ...] = (GROUP_HIT, GROUP_MISS, GROUP_ABSENT)

# The two sides a gap is taken between. Named, because the gap is exactly the
# comparison the absent group is kept out of.
ASKED_GROUPS: tuple[str, ...] = (GROUP_HIT, GROUP_MISS)


# -- what kind of value a candidate persists ----------------------------------

# A candidate whose row carries a **degree** — a real number a correlation can be
# run against. ``Relative move``'s ADR units are the only one.
VALUE_GRADED = "graded"
# A candidate whose row carries only the answer. ``RS line`` is a comparison of
# two ratios, so what persists is the verdict and there is no degree to rank.
VALUE_BOOLEAN = "boolean"


@dataclass(frozen=True)
class CandidateDimension:
    """One registered candidate dimension, and how to read a persisted row for it.

    :data:`CANDIDATES` supplies the name and the pre-registered boolean reader;
    everything else here is what an *outcome* measurement additionally needs and a
    selection contrast never did — how to reach the stored value, whether that
    value is a degree or a verdict, and what an absent one means.

    ``hit`` is the registry's own reader and is never re-implemented: the cut the
    contrast read and the cut this measurement reads are one function, so the two
    studies can never disagree about which side of the line a row fell.
    """

    name: str
    hit: Callable[[ScoredDetection], bool]
    value: Callable[[ScoredDetection], Any]
    cut: str
    absent_means: str
    # The **degree** reader, or ``None`` where the row keeps only a verdict. One
    # field carries that fact rather than a ``value_kind`` string switched on at
    # three sites: a candidate either has a number to rank or it does not, and
    # :attr:`value_kind` is derived from it so the label and the behaviour cannot
    # drift apart.
    degree: Callable[[ScoredDetection], float | None] | None = None

    @property
    def value_kind(self) -> str:
        """What the persisted row carries, for the payload and the printed page."""
        return VALUE_GRADED if self.degree is not None else VALUE_BOOLEAN


def _relative_move_degree(detection: ScoredDetection) -> float | None:
    """``Relative move``'s stored degree — the value itself, in ADR units."""
    return detection.relative_move


# How to read each registered candidate's persisted row, keyed by the name the
# register uses. Kept apart from :data:`CANDIDATES` because that tuple is ADR
# 0005's register of what has been *pre-registered*, and a measurement module able
# to add an entry to it is a module able to promote a column after its gap is
# visible.
_READERS: dict[str, dict[str, Any]] = {
    "RS line": dict(
        value=lambda d: d.rs_line,
        degree=None,
        cut="RS_today >= RS_at_base_start, over the detection's own base",
        absent_means=(
            "a price was missing at one of the two anchors, so the question was "
            "never asked — which is a different fact from asking it and getting no"
        ),
    ),
    "Relative move": dict(
        value=lambda d: d.relative_move,
        degree=_relative_move_degree,
        cut=(
            f"the 6m index-relative move in ADR units, strictly above "
            f"{RELATIVE_MOVE_CUT:.1f}"
        ),
        absent_means=(
            "the name had not listed six months ago, or has no ADR — never zero, "
            "which is a real value sitting exactly on the cut"
        ),
    ),
}


def check_registry(
    registered: Sequence[tuple[str, int, Callable[[ScoredDetection], bool]]] = (
        CANDIDATES
    ),
) -> None:
    """Refuse to measure if a registered candidate has no value reader here.

    #195 asks for **both** registered candidates, and a third registration would
    make that sentence mean something new. This module cannot read a row for a
    dimension it has never heard of — it would not know where the value lives or
    what an absent one means — so a new registration stops the measurement instead
    of being quietly left out of a report that still claims to cover the register.
    """
    unknown = sorted({name for name, _w, _r in registered} - set(_READERS))
    if unknown:
        raise ContractDrift(
            f"registered candidate(s) {unknown} have no value reader in "
            "backtest.candidates: this measurement covers the whole register, so "
            "a new registration is a change to make here rather than a column to "
            "leave out"
        )


def _under_test() -> tuple[CandidateDimension, ...]:
    """The register, in its own order, with this module's readers attached."""
    check_registry()
    return tuple(
        CandidateDimension(name=name, hit=hit, **_READERS[name])
        for name, _weight, hit in CANDIDATES
    )


CANDIDATES_UNDER_TEST: tuple[CandidateDimension, ...] = _under_test()


def named_candidate(name: str) -> CandidateDimension:
    """One candidate by the name the register uses."""
    for candidate in CANDIDATES_UNDER_TEST:
        if candidate.name == name:
            return candidate
    raise KeyError(
        f"{name!r} is not a registered candidate dimension; "
        f"{[c.name for c in CANDIDATES_UNDER_TEST]} are"
    )


# -- nothing here admits a dimension ------------------------------------------

ADMISSION_NOTE = (
    "this measurement admits no dimension and retires none. ADR 0005's admission "
    "instrument is the selection contrast, and an outcome claim is not one — it "
    "is evidence that goes through the calibration rule like any other change. "
    "Neither candidate's weight, the rubric version, nor the register moves here"
)


def check_not_admitted(
    dimensions: Sequence[tuple[str, int]] = DIMENSIONS,
) -> None:
    """Refuse if a registered candidate has entered the live rubric.

    A candidate is a dimension **under measurement**, weighted by nothing and
    unable to move a star, a sort or a board place. One that had reached
    :data:`screener.score.DIMENSIONS` would make this a report about a live rubric
    row under a banner saying the opposite, and #195's last criterion — that
    neither dimension is admitted by this ticket — would be false in a way no
    reader of the output could see.
    """
    live = {name for name, _weight in dimensions}
    admitted = sorted(live & {c.name for c in CANDIDATES_UNDER_TEST})
    if admitted:
        raise ContractDrift(
            f"{admitted} is in the live rubric: this measurement reports on "
            "candidate dimensions, which are weighted by nothing, and an admitted "
            "one is a different subject under the same name"
        )


# -- the selection contrast, carried so the two claims are never merged -------

# What ADR 0005's instrument measured on each candidate, quoted from
# `references/qullamaggie-replay-findings.md` rather than recomputed. It rides on
# every candidate's cell because the danger is not that a reader disbelieves §5d
# or §5e — it is that a reader reads the selection Δ and the outcome gap as two
# readings of one claim, when they are two claims that can point opposite ways.
#
# Both figures are the **live detector v3** column, which is the field ADR 0005
# requires a verdict to be read on.
SELECTION_CONTRAST: dict[str, dict[str, Any]] = {
    "RS line": {
        "instrument": "selection contrast",
        "measures": "his taken detections against the ones he passed over",
        "source": "findings §5d",
        "detector": "v3 (live)",
        "taken_hit_rate": 0.100,
        "taken_n": 140,
        "not_taken_hit_rate": 0.121,
        "not_taken_n": 34543,
        "delta_pp": -2.1,
        "pooled_spread": 0.326,
        "adr_0005_verdict": "not admitted",
        "recorded_as": "refused on criterion 4 — a wrong-way gap",
        "why": (
            "refused on criterion 4, a wrong-way gap, with the anchor named as "
            "the mechanism: base_start is a local high under both detector "
            "branches, so the rule asks a name to hold its ratio to the index "
            "measured from a local maximum"
        ),
    },
    "Relative move": {
        "instrument": "selection contrast",
        "measures": "his taken detections against the ones he passed over",
        "source": "findings §5e",
        "detector": "v3 (live)",
        "taken_hit_rate": 0.886,
        "taken_n": 140,
        "not_taken_hit_rate": 0.8494,
        "not_taken_n": 34543,
        "delta_pp": 3.6,
        "pooled_spread": 0.357,
        "adr_0005_verdict": "not admitted",
        "recorded_as": "on_the_bound — the criteria do not separate",
        "why": (
            "positive on both fields, and then 0.06pp inside criterion 1's ~85% "
            "not-taken hit-rate ceiling — 0.29 standard errors from it. That "
            "ceiling and criterion 2's ~15% disagreement floor are one threshold "
            "read from two sides, so the two criteria give opposite answers on "
            "the same number, and the ADR calls that magnitude a judgement rather "
            "than a measurement. The criteria do not separate, so nothing shipped"
        ),
    },
}

SELECTION_CONTRAST_NOTE = (
    "the selection contrast and this measurement are a different claim about the "
    "same dimension, and neither converts into the other: one says the trader "
    "picked names the dimension fires on, the other says the names it fires on "
    "paid. A dimension can select and not predict — his edge would be "
    "discretionary — and it can predict and not select, which is a candidate he "
    "was never using. So the two verdicts are reported side by side under their "
    "own keys and are never summed, averaged or read as confirmation of each other"
)

OUT_OF_SAMPLE_NOTE = (
    "the outcome variable is R after costs on trades taken mechanically over a "
    "window his record does not cover; no rubric weight was fitted to it and no "
    "detection could see it"
)

NOT_CUT_PER_YEAR = (
    "reported per market and not per year, unlike the ranking test: two "
    "candidates, three groups and three statistics each already make this the "
    "widest cell in the run, and a per year row would multiply the interval count "
    "by the length of the window to answer a question #195 does not ask. The "
    "window row is the measurement"
)

MULTIPLE_TESTING_NOTE = (
    "one more view of a dataset that already carried nine before any sweep; "
    "pre-specified by #195 and computed once, not chosen after the fact"
)


# -- the rows the statistics run on -------------------------------------------


@dataclass(frozen=True)
class DetectedTrade:
    """One simulated trade beside the persisted detection row it came from.

    Joined rather than stored together, for the reason the ranking gives: the
    simulator takes an entry and an exit and has no business carrying a candidate
    dimension, and the denominator's row is where both values already live.
    """

    trade: SimulatedTrade
    detection: ScoredDetection

    @property
    def symbol(self) -> str:
        return self.trade.symbol

    @property
    def market(self) -> str:
        return self.trade.market


@dataclass(frozen=True)
class CandidateOutcome:
    """One closed trade reduced to what a statistic needs, for one candidate.

    ``value`` is the **degree** the row persisted, and is ``None`` both when the
    row was absent and when the candidate stores only a verdict — the two are
    already told apart by ``group``, and a correlation has nothing to run on in
    either case. Costs are already applied: one place turns a trade into a number,
    :func:`~backtest.metric.after_cost_r`, and this is where it is called.
    """

    symbol: str
    group: str
    value: float | None
    r: float


def group_of(candidate: CandidateDimension, detection: ScoredDetection) -> str:
    """Which of the three groups a persisted row falls in, read at read time.

    Absence is tested **first** and on the stored value itself, so no absent row
    can reach the cut. That order is the whole guard: ``Relative move``'s cut is
    zero, and a ``None`` coerced to a float would sit exactly on it.
    """
    if candidate.value(detection) is None:
        return GROUP_ABSENT
    return GROUP_HIT if candidate.hit(detection) else GROUP_MISS


def split(
    candidate: CandidateDimension, cohort: Sequence[DetectedTrade]
) -> dict[str, list[DetectedTrade]]:
    """The cohort partitioned into the three groups, every group present.

    A group with no trades comes back empty rather than missing, so a report can
    show its zero: an absent row and a group nobody measured are indistinguishable
    after the fact.
    """
    groups: dict[str, list[DetectedTrade]] = {g: [] for g in GROUPS}
    for row in cohort:
        groups[group_of(candidate, row.detection)].append(row)
    return groups


def _graded_value(
    candidate: CandidateDimension, detection: ScoredDetection
) -> float | None:
    """The stored degree, or ``None`` where the candidate keeps only a verdict.

    The one site that asks whether a candidate has a degree at all, and it asks the
    reader rather than a label: a candidate with no ``degree`` has nothing to
    return, and a row with an absent value has nothing either.
    """
    if candidate.degree is None:
        return None
    value = candidate.degree(detection)
    return None if value is None else float(value)


def outcomes(
    candidate: CandidateDimension,
    cohort: Sequence[DetectedTrade],
    contract: RunContract,
) -> list[CandidateOutcome]:
    """The cohort's **closed** trades as rows, after costs, in cohort order.

    A trade still running has no R, and marking one to the last close would invent
    an exit the rules never gave — systematically, for every name still open. It
    counts toward its group's ``trades`` and toward nothing else.
    """
    rows: list[CandidateOutcome] = []
    for row in cohort:
        r = after_cost_r(row.trade, contract)
        if r is None:
            continue
        rows.append(
            CandidateOutcome(
                symbol=row.symbol,
                group=group_of(candidate, row.detection),
                value=_graded_value(candidate, row.detection),
                r=r,
            )
        )
    return rows


# -- the statistics -----------------------------------------------------------


def _mean_gap(
    rows: Sequence[CandidateOutcome],
    *,
    against: Sequence[str],
) -> float | None:
    """Mean R of the hit group minus mean R of ``against``, or ``None``.

    ``None`` when either side is empty — which a resample can easily produce —
    because a gap against a group nobody drew is undefined rather than zero, and
    the difference matters to every interval built on it.
    """
    hit = [row.r for row in rows if row.group == GROUP_HIT]
    other = [row.r for row in rows if row.group in against]
    if not hit or not other:
        return None
    return sum(hit) / len(hit) - sum(other) / len(other)


def outcome_gap(rows: Sequence[CandidateOutcome]) -> float | None:
    """The measurement: what the dimension's hits paid, less what its misses paid.

    Over the rows where the question was **asked**. An absent row is not a miss —
    the dimension said nothing about that name — so it is no more part of this
    comparison than a trade in another market would be.
    """
    return _mean_gap(rows, against=(GROUP_MISS,))


def rubric_reading_gap(rows: Sequence[CandidateOutcome]) -> float | None:
    """The same gap as a **shipped** boolean would compute it: absent reads as miss.

    The pre-registered readers score an absent value ``False`` and never carry it
    forward, so this is what the dimension would do as a rubric row. Reported
    beside the measurement and outside the verdict: it answers "what would this
    boolean have done", where :func:`outcome_gap` answers "does the quantity
    predict", and only the second is a claim about the world.
    """
    return _mean_gap(rows, against=(GROUP_MISS, GROUP_ABSENT))


def value_correlation(rows: Sequence[CandidateOutcome]) -> float | None:
    """Spearman's rho between the stored **degree** and the outcome.

    Over the rows that have a degree at all: an absent row is not a low one, and
    ranking it anywhere — top, bottom or middle — would put a number nobody
    measured into the figure.

    ``None`` where the candidate stores only a verdict. There is no degree to rank
    there, and correlating a boolean with the outcome would be the gap again under
    a second name, which a reader would meet as a second piece of evidence.
    """
    graded = [row for row in rows if row.value is not None]
    return spearman(
        [row.value for row in graded if row.value is not None],
        [row.r for row in graded],
    )


# -- the verdict --------------------------------------------------------------

# The vocabulary :mod:`backtest.posture` and :mod:`backtest.ranking` established,
# spelled identically so a reader joining two of this run's payloads is not
# comparing "too_thin" against "too thin to say".
VERDICT_PREDICTS = "predicts"
VERDICT_NO_EVIDENCE = "no_evidence"
VERDICT_TOO_THIN = "too_thin"

VERDICT_PHRASE = {
    VERDICT_PREDICTS: "predicts",
    VERDICT_NO_EVIDENCE: "no evidence it predicts",
    VERDICT_TOO_THIN: "too thin to say",
}

VERDICT_RULE = (
    "'predicts' requires the hit-minus-miss gap to have a symbol-clustered "
    "interval entirely above zero. The gap is the whole verdict: ADR 0005 admits "
    "a dimension as a boolean, so the boolean's gap is the claim anything could "
    "act on. The correlation against the stored value is reported beside it and "
    "does not enter — only one of the two registered candidates persists a degree "
    "to run it on, so a rule reading it would mean different things for the two. "
    "The rubric reading, which folds absence into the miss side, does not enter "
    "either: it says what a shipped boolean would have done, not whether the "
    "quantity predicts. A cohort whose hit or miss side is below the cluster "
    "floor, or whose interval was refused for undefined resamples, is 'too thin "
    "to say' — the gap is taken between those two sides. The verdict reads the "
    "95% interval's lower bound, a one-sided 2.5% test and stricter than the "
    "one-sided p printed beside it. 'no evidence it predicts' is never 'the "
    "dimension does not predict': one sample cannot license that"
)


def verdict(*, gap: dict[str, Any], sides: Sequence[dict[str, Any]]) -> str:
    """The verdict :data:`VERDICT_RULE` spells out, read off the gap alone.

    ``sides`` are the hit and miss cells; a suppressed interval on either makes the
    gap unreadable however wide the cohort as a whole is.
    """
    if any(cell["bootstrap"]["suppressed"] is not None for cell in sides):
        return VERDICT_TOO_THIN
    if gap["value"] is None or gap["bootstrap"]["ci_low"] is None:
        return VERDICT_TOO_THIN
    return VERDICT_PREDICTS if gap["bootstrap"]["ci_low"] > 0 else VERDICT_NO_EVIDENCE


# -- joining a trade to the row that produced it ------------------------------

def candidate_trades(
    trades: Sequence[SimulatedTrade], index: DetectionIndex
) -> list[DetectedTrade]:
    """Join each trade to the persisted row that produced it.

    The join is :func:`~backtest.cohort.join_detections`' — **total**, so a trade
    with no row raises rather than being dropped; that module holds the argument.
    What this adds is only the row type: a trade beside the whole detection row,
    because both candidate values are read off it at report time by the readers
    :data:`CANDIDATES` supplies.
    """
    return [
        DetectedTrade(trade=trade, detection=detection)
        for trade, detection in join_detections(trades, index)
    ]


# -- the report ---------------------------------------------------------------


def _group_cell(
    contract: RunContract,
    candidate: CandidateDimension,
    group: str,
    rows: Sequence[DetectedTrade],
    *,
    market: str,
    closed_total: int,
) -> dict[str, Any]:
    """One group's cell: the metric's own expectancy cell, plus what group it is.

    The body is :func:`~backtest.metric.expectancy_cell` unmodified, so a group
    reports the same fields the headline does and a reader comparing the two is
    comparing figures built the same way.
    """
    closed = sum(1 for row in rows if row.trade.r_multiple is not None)
    cell: dict[str, Any] = {
        "group": group,
        "share_of_closed": (closed / closed_total) if closed_total else 0.0,
        **expectancy_cell(
            contract, [row.trade for row in rows], market=market, label=group
        ),
    }
    if group == GROUP_ABSENT:
        # Said on the cell rather than only in the module docstring, because this
        # is the one number a reader is most likely to mistake for a miss.
        cell["absent_means"] = candidate.absent_means
        cell["enters_the_gap"] = False
    return cell


def _gap_cell(rows: Sequence[CandidateOutcome]) -> dict[str, Any]:
    """The hit-minus-miss gap with its clustered interval."""
    return {
        "statistic": "mean after-cost R, hit minus miss",
        "reads_absence_as": "absent — it enters neither side",
        "enters_the_verdict": True,
        "value": outcome_gap(rows),
        "bootstrap": bootstrap_symbol_statistic(cluster_by_symbol(rows), outcome_gap),
    }


def _rubric_reading_cell(rows: Sequence[CandidateOutcome]) -> dict[str, Any]:
    """The same gap as a shipped boolean would compute it, and its interval."""
    return {
        "statistic": "mean after-cost R, hit minus (miss and absent)",
        "reads_absence_as": (
            "a miss — the pre-registered readers score an absent value False, so "
            "this is what the dimension would do as a rubric row"
        ),
        "enters_the_verdict": False,
        "value": rubric_reading_gap(rows),
        "bootstrap": bootstrap_symbol_statistic(
            cluster_by_symbol(rows), rubric_reading_gap
        ),
    }


def _value_cell(
    candidate: CandidateDimension, rows: Sequence[CandidateOutcome]
) -> dict[str, Any]:
    """Spearman's rho against the stored degree, or the reason there is none.

    ``rho`` is :func:`value_correlation` unconditionally: it already returns
    ``None`` where no row carries a degree, and a second guard here would be a
    second place for "this candidate has nothing to rank" to be decided.
    """
    unavailable = None if candidate.degree is not None else (
        f"{candidate.name} persists a boolean, not a degree: there is no value to "
        "rank, and correlating a verdict with the outcome would restate the gap"
    )
    return {
        "statistic": "spearman_rho",
        "ties": "averaged",
        "against": "the persisted value, over the rows that have one",
        "enters_the_verdict": False,
        "value_kind": candidate.value_kind,
        "unavailable": unavailable,
        "rho": value_correlation(rows),
        "pairs": sum(1 for row in rows if row.value is not None),
        "bootstrap": bootstrap_symbol_statistic(
            cluster_by_symbol(rows), value_correlation, unavailable=unavailable
        ),
    }


def market_candidate(
    contract: RunContract,
    candidate: CandidateDimension,
    cohort: Sequence[DetectedTrade],
    *,
    market: str,
) -> dict[str, Any]:
    """One candidate's outcome measurement over one market's cohort.

    The three groups, the gap the verdict is read off, the shipped boolean's
    reading, the correlation against the stored degree, and the selection contrast
    ADR 0005 measured — under its own key, with its own verdict, never merged into
    this one's.
    """
    check_costs(contract, market)
    check_one_market_one_arm(
        [row.trade for row in cohort],
        market=market,
        what=f"a candidate dimension's outcome ({candidate.name})",
    )

    groups = split(candidate, cohort)
    rows = outcomes(candidate, cohort, contract)
    closed_total = len(rows)
    cells = {
        group: _group_cell(
            contract, candidate, group, groups[group],
            market=market, closed_total=closed_total,
        )
        for group in GROUPS
    }
    gap = _gap_cell(rows)
    return {
        "candidate": candidate.name,
        "market": market,
        "arm": PRIMARY_ARM,
        "cut": candidate.cut,
        "cut_applied": (
            "at read time, by the rubric's own reader, off the value the persisted "
            "row carries — no row is re-denominated"
        ),
        "value_kind": candidate.value_kind,
        "absent_means": candidate.absent_means,
        "trades": len(cohort),
        "symbols": len({row.symbol for row in cohort}),
        "closed": closed_total,
        "groups": cells,
        "gap": gap,
        "rubric_reading": _rubric_reading_cell(rows),
        "value_correlation": _value_cell(candidate, rows),
        "verdict": verdict(
            gap=gap, sides=[cells[group] for group in ASKED_GROUPS]
        ),
        "selection_contrast": SELECTION_CONTRAST[candidate.name],
    }


def market_candidates(
    contract: RunContract,
    cohort: Sequence[DetectedTrade],
    *,
    market: str,
) -> dict[str, Any]:
    """Every registered candidate over one market, in the register's own order."""
    return {
        "market": market,
        "trades": len(cohort),
        "symbols": len({row.symbol for row in cohort}),
        "candidates": [
            market_candidate(contract, candidate, cohort, market=market)
            for candidate in CANDIDATES_UNDER_TEST
        ],
    }


def _intervals_reported(markets_body: Sequence[dict[str, Any]]) -> int:
    """How many significance intervals this report actually states.

    Every group, gap, rubric reading and correlation of every candidate in every
    market, because each is a statement made at nominal alpha. Suppressed
    intervals are not counted: a cell that refused to say anything made no claim to
    correct for.
    """
    def in_cell(cell: dict[str, Any]) -> int:
        return intervals_reported(
            [cell["groups"][group] for group in GROUPS]
            + [cell["gap"], cell["rubric_reading"], cell["value_correlation"]]
        )

    return sum(
        sum(in_cell(cell) for cell in market["candidates"])
        for market in markets_body
    )


def candidates_report(
    contract: RunContract,
    cohort: Sequence[DetectedTrade],
    *,
    markets: Sequence[str] | None = None,
) -> dict[str, Any]:
    """The whole measurement as one stamped payload, market by market.

    ``markets`` defaults to the contract's own scope, so a market that produced no
    trade reports its zeros rather than vanishing. There is deliberately no pooled
    figure and no pooled verdict: findings §8 measured that magnitudes do not
    transfer, and the way to stop a pooled number being quoted is for it never to
    have been computed.
    """
    check_registry()
    check_not_admitted()
    named = tuple(markets) if markets else tuple(contract.value(SCOPE_MARKETS_KEY))
    markets_body = [
        market_candidates(
            contract, [row for row in cohort if row.market == market], market=market
        )
        for market in named
    ]
    return stamp_result(
        contract,
        {
            "question": (
                "do the registered candidate dimensions predict outcomes, or only "
                "match the trader's selection?"
            ),
            "arm": PRIMARY_ARM,
            "registered": [
                {
                    "candidate": candidate.name,
                    "cut": candidate.cut,
                    "value_kind": candidate.value_kind,
                    "absent_means": candidate.absent_means,
                }
                for candidate in CANDIDATES_UNDER_TEST
            ],
            "out_of_sample": OUT_OF_SAMPLE_NOTE,
            "selection_contrast_note": SELECTION_CONTRAST_NOTE,
            "admission": ADMISSION_NOTE,
            "verdict_rule": VERDICT_RULE,
            "not_cut_per_year": NOT_CUT_PER_YEAR,
            "groups": {
                "reported": list(GROUPS),
                "in_the_gap": list(ASKED_GROUPS),
                "rule": (
                    "absence is a group, never a value on the cut: the question "
                    "was not asked of those names, so they enter no gap"
                ),
            },
            "multiple_testing": {
                "note": MULTIPLE_TESTING_NOTE,
                "intervals_reported": _intervals_reported(markets_body),
                "alpha_is_nominal": True,
                "reading": (
                    "two candidates, three groups and three statistics each; the "
                    "gap rows are the measurement and the rest are diagnostics"
                ),
            },
            "bootstrap": {
                "cluster": BOOTSTRAP_CLUSTER,
                "resamples": BOOTSTRAP_RESAMPLES,
                "seed": BOOTSTRAP_SEED,
                "confidence": BOOTSTRAP_CONFIDENCE,
            },
            "markets": markets_body,
        },
    )


# -- printing it, and the command that produces it ----------------------------


def _group_line(cell: dict[str, Any]) -> str:
    """One group as a line: what it is, its n, what it paid and how sure that is.

    n sits immediately beside the expectancy and never on a line of its own,
    because a group's expectancy without its count is unreadable — six trades and
    six hundred print the same number.
    """
    head = f"  {cell['group']:<7} n={cell['closed']:<5}"
    if cell["closed"] == 0:
        return f"{head} no closed trades ({cell['trades']} taken)"
    return (
        f"{head} {cell['expectancy_r']:+.3f}R  win {cell['win_rate']:.1%}  "
        f"{cell['symbols']} symbols  {format_interval(cell['bootstrap'])}"
    )


def _value_line(cell: dict[str, Any]) -> str:
    if cell["rho"] is None:
        return f"  rho    — {cell['unavailable']}"
    return (
        f"  rho    {cell['rho']:+.3f} over {cell['pairs']} valued trades  "
        f"{format_interval(cell['bootstrap'])}"
    )


def _candidate_lines(cell: dict[str, Any]) -> list[str]:
    """One candidate's block: the older claim, then the groups, then the new one."""
    prior = cell["selection_contrast"]
    gap, rubric = cell["gap"], cell["rubric_reading"]
    value = "undefined" if gap["value"] is None else f"{gap['value']:+.3f}R"
    rubric_value = (
        "undefined" if rubric["value"] is None else f"{rubric['value']:+.3f}R"
    )
    lines = [
        f"{cell['market']} — {cell['candidate']} ({cell['trades']} trades, "
        f"{cell['symbols']} symbols)",
        f"  selection contrast ({prior['source']}, detector {prior['detector']}): "
        f"Δ {prior['delta_pp']:+.1f}pp — {prior['adr_0005_verdict']}",
        # The outcome ADR 0005 actually recorded, not only that nothing shipped.
        # "not admitted" covers a refusal on a wrong-way gap and a dimension that
        # landed on its own bound, and those are different findings — a reader of
        # the page should not have to open the JSON to tell them apart.
        f"    recorded as: {prior['recorded_as']}",
    ]
    lines += [_group_line(cell["groups"][group]) for group in GROUPS]
    lines += [
        f"  gap    hit − miss {value}  {format_interval(gap['bootstrap'])}",
        f"  as shipped (absent read as a miss) {rubric_value}  "
        f"{format_interval(rubric['bootstrap'])}",
        _value_line(cell["value_correlation"]),
        f"  verdict: {VERDICT_PHRASE[cell['verdict']]}",
    ]
    return lines


def format_candidates(report: dict[str, Any]) -> str:
    """The measurement as a page a terminal can print.

    The selection contrast prints **above** each candidate's outcome figures rather
    than as a footnote, so a reader meets the claim ADR 0005 already measured, and
    the reason it is a different claim, before meeting a number that could be
    mistaken for a second reading of it.
    """
    lines: list[str] = [
        f"{report['question']} — arm {report['arm']}",
        f"  {report['out_of_sample']}",
        f"  {report['selection_contrast_note'].split(':')[0]}",
        f"  {report['admission']}",
        f"  bootstrap {report['bootstrap']['resamples']}× clustered by "
        f"{report['bootstrap']['cluster']}, seed {report['bootstrap']['seed']}",
    ]
    for body in report["markets"]:
        for cell in body["candidates"]:
            lines.append("")
            lines += _candidate_lines(cell)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Measure both registered candidates against outcomes, and record it::

        python -m backtest.candidates --store data/backtest.duckdb \\
            --out-json references/backtest_candidate_outcomes.json

    Both markets by default, arm B only — the pre-registered arm. Reads the bar
    store and the denominator beside it, and writes neither.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument(
        "--market", action="append", default=None,
        help="narrow to one market (repeatable); defaults to the contract's scope",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable, contract-stamped result",
    )
    args = parser.parse_args(argv)

    contract = DEFAULT_CONTRACT
    markets = tuple(args.market) if args.market else tuple(
        contract.value(SCOPE_MARKETS_KEY)
    )
    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        cohort: list[DetectedTrade] = []
        for market in markets:
            trades = simulate_market(
                store, denominator, market, contract, arms=(PRIMARY_ARM,)
            )
            cohort += candidate_trades(trades, detection_index(denominator, market))
    finally:
        denominator.close()
        store.close()

    report = candidates_report(contract, cohort, markets=markets)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_candidates(report))
    if args.out_json:
        print(f"\nwrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
