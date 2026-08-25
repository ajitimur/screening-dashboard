"""A3, the selection contrast: which dimensions he *selects* on, as distinct from
which *predict* a run (PRD #114 "A3 analyses", issue #122).

The second of A3's two analyses, kept rigorously apart from the outcome regression
(:mod:`replay.regression`) in code and in the write-up. Where the regression asks
whether the rubric *predicts a move*, this asks whether the rubric *encodes his
eye* — a different question, and the two must never be reported as though they
were the same thing (PRD user story 17).

**No outcome variable.** There is no MFE, no realised R, no gain anywhere in this
analysis. It compares the *distribution of each score dimension* between two
groups drawn from the replayed field on the sessions he traded: the **executed
trades** (the field member whose name he actually entered — the *taken*
detections) and the **not-taken detections** (the field members present the same
night in names he did not enter). A dimension he selects on will be hit more often
among his picks than among the field he passed over.

**The not-taken detections are a comparison group, never a negative label** (PRD
user story 25). He may never have seen them, so their absence from his trade
record is not a rejection and is never described as one. This is the nearest
honest substitute for a control group; it is *not* a precision measurement, and
none is claimed (:data:`PRECISION_NOTE`, user story 24). The reference set records
no setup he declined, so no false-positive rate exists to report.

**It partly repairs the range-restriction trap.** Every executed trade already
passed his eye, so the dimensions he applies most consistently show the least
variance within his trades alone and correlate with nothing in the outcome
regression — a null labelled *untestable* there (PRD user story 19). The not-taken
detections restore that variance: a dimension flat across his picks may vary
across the combined field. So each dimension reports its spread within the
executed trades (which mirrors the regression's untestability, being the same
sample and the same spread measure) *and* across the combined groups, and any
dimension whose testability the not-taken detections **restore** is flagged — the
re-check the ticket asks for, without importing the regression's result.

**Coverage** rides every output (:attr:`SelectionContrast.blind_spot_count`, user
story 22): a field-derived contrast is never read without knowing how much of the
field was missing.

This ticket produces *evidence only*. No constant in :mod:`screener` changes; a
gate is loosened elsewhere only when a dimension shows no signal in the regression
**and** real spread — spread this contrast is one source of (PRD "Calibration
rule").
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from typing import Callable, Iterable, Mapping, Sequence

from screener.relative_strength import relative_move_hit
from screener.score import Dimension
from screener.store import Store

from .chain import BURN_IN_SESSIONS, REPLAY_MARKET
from .field import FieldSession, ScoredDetection, replay_field
from .reference import (
    DEFAULT_REFERENCE_JSON,
    ExecutedTrade,
    classify,
    load_trades,
)
from .regression import REGRESSED_DIMENSIONS, _pstdev

# The not-taken detections are a comparison group, never a rejection: he may never
# have seen them (PRD user story 25). Emitted on the report so no reader mistakes
# the group for declined setups.
COMPARISON_GROUP_NOTE = (
    "The not-taken detections are a comparison group: field members present on "
    "nights he traded, in names he did not enter and may never have seen. Their "
    "absence from his trade record carries no verdict on them."
)

# Precision is not measurable here, and this analysis claims no false-positive
# rate (PRD user story 24): the reference set records only the trades he entered,
# never a setup he passed over, so there is no control group — only this
# comparison group.
PRECISION_NOTE = (
    "Precision is not measurable: the reference set records only the trades he "
    "entered, never a setup he passed over, so there is no control group and no "
    "false-positive rate is claimed. This comparison group is the nearest honest "
    "substitute, and no precision is asserted."
)


@dataclass(frozen=True)
class DimensionContrast:
    """One dimension's selection contrast: how often his picks hit it versus the
    not-taken detections, with the testability re-check.

    ``taken_hit_rate`` / ``not_taken_hit_rate`` are the share of each group that
    hit the dimension; ``*_spread`` is the population standard deviation of that
    boolean within each group. ``combined_spread`` is the spread across both groups
    pooled. There is **no** correlation and **no** outcome here — this is a
    selection contrast, not a regression.

    ``untestable_within_executed`` mirrors the outcome regression's untestable
    label: it is set when the taken group alone has no spread (the same sample and
    measure the regression uses). ``testable_in_contrast`` is set when the pooled
    sample does have spread. ``testability_restored`` is the re-check the ticket
    asks for — a dimension untestable within his trades alone that the not-taken
    detections make testable here (PRD user story 19; the range-restriction
    repair).
    """

    dimension: str
    weight: int
    taken_n: int
    taken_hit_rate: float
    taken_spread: float
    not_taken_n: int
    not_taken_hit_rate: float
    not_taken_spread: float
    combined_spread: float
    untestable_within_executed: bool
    testable_in_contrast: bool
    testability_restored: bool


@dataclass(frozen=True)
class SelectionContrast:
    """The A3 selection-contrast result: the per-dimension contrast between his
    executed trades and the not-taken detections, with coverage and the honesty
    notes.

    Carries **no** outcome variable by construction (PRD "A3 analyses"). ``notes``
    holds the comparison-group and precision statements every reader must see
    (:data:`COMPARISON_GROUP_NOTE`, :data:`PRECISION_NOTE`). ``blind_spot_count``
    is the coverage figure every field-derived output must carry (user story 22).
    """

    dimension_contrasts: list[DimensionContrast]
    n_executed: int
    n_not_taken: int
    blind_spot_count: int
    comparison_group_note: str = COMPARISON_GROUP_NOTE
    precision_note: str = PRECISION_NOTE


# The **candidate dimensions**: measured in this contrast, weighted by nothing.
# A candidate is read off the field member itself rather than off its score
# breakdown, because it is not in the rubric — :mod:`replay.field` deliberately
# keeps :class:`~replay.field.SevenDimScore` at exactly the seven dimensions the
# rubric weighs, so a dimension under measurement cannot move a star or a board
# place while the question of whether it belongs is still open.
#
# Two are registered, in the order ADR 0005 registered them:
#
# - ``RS line`` (#160) — whether the name held its ratio to the benchmark across
#   its own base. Measured for the slot ``Prior move`` cannot earn — a
#   **constant dimension**, 100.0% in both groups, pooled spread 0.000 — and
#   **rejected** on criterion 4, a wrong-way gap (findings §5d). It stays a
#   column because retiring the evidence with the candidate would leave §5d
#   unreproducible.
# - ``Relative move`` (#170) — the `6m` return relative to ``MARKET_INDEX``,
#   compounded, in ADR units, hit above the pre-registered cut. Measured by #171
#   (findings §5e). The cut is applied here, at read time, off the value the
#   field member carries: one site owns it, so the column the contrast reads and
#   the row a rubric would score can never disagree about where the line is.
#
# Both carry weight 0 because they have none, and nothing here touches
# :mod:`screener.score`.
#
# **This tuple is the list of what has actually been registered**, and it is
# deliberately short. #171 reports five further columns — the raw move and the
# relative one at other windows — and those are handed in as ``readers`` by the
# study script rather than added here, because ADR 0005 admits **one**
# pre-registered variant per registration. A column promotable by editing this
# tuple is a column promotable after its gap is visible.
#
# **One entry per candidate, name and reader together.** Keeping the reader in a
# second dict keyed by the same string let a typo fall through to the rubric
# lookup and report 0.0% instead of failing, which is the one way a contrast can
# be wrong and look fine.
CANDIDATES: tuple[tuple[str, int, Callable[[ScoredDetection], bool]], ...] = (
    ("RS line", 0, lambda d: d.rs_line),
    ("Relative move", 0, lambda d: relative_move_hit(d.relative_move)),
)

CANDIDATE_DIMENSIONS: tuple[tuple[str, int], ...] = tuple(
    (name, weight) for name, weight, _reader in CANDIDATES
)
_CANDIDATE_READERS = {name: reader for name, _weight, reader in CANDIDATES}

# Every column of the contrast: the rubric's own seven, then the candidates.
CONTRAST_DIMENSIONS: tuple[tuple[str, int], ...] = (
    REGRESSED_DIMENSIONS + CANDIDATE_DIMENSIONS
)


def _dim_hit(breakdown: Sequence[Dimension], name: str) -> bool:
    for d in breakdown:
        if d.dimension == name:
            return d.hit
    return False


def _booleans(
    detections: Iterable[ScoredDetection],
    name: str,
    readers: Mapping[str, Callable[[ScoredDetection], bool]],
) -> list[float]:
    """The dimension's boolean (1.0 hit / 0.0 miss) across a group of detections.

    A **candidate dimension** is read off the field member; a rubric dimension off
    its score breakdown. The two are kept apart deliberately — see
    :data:`CANDIDATE_DIMENSIONS`.
    """
    reader = readers.get(name)
    if reader is not None:
        return [1.0 if reader(d) else 0.0 for d in detections]
    return [1.0 if _dim_hit(d.score.breakdown, name) else 0.0 for d in detections]


def _hit_rate(xs: Sequence[float]) -> float:
    """Share of the group that hit the dimension (0.0 on an empty group)."""
    return sum(xs) / len(xs) if xs else 0.0


def contrast_dimensions(
    taken: Iterable[ScoredDetection],
    not_taken: Iterable[ScoredDetection],
    *,
    dimensions: tuple[tuple[str, int], ...] = CONTRAST_DIMENSIONS,
    readers: Mapping[str, Callable[[ScoredDetection], bool]] | None = None,
) -> list[DimensionContrast]:
    """Contrast each dimension's hit distribution between the two field groups.

    ``taken`` are his executed-trade detections, ``not_taken`` the comparison
    group. For every dimension (the app's eight less the dropped sector dimension,
    in published order, then the :data:`CANDIDATE_DIMENSIONS` under measurement)
    the hit rate and spread are reported for each group and for the pooled
    sample, and a dimension untestable within his trades alone but with spread
    across the pooled sample is flagged as testability-restored (PRD user story
    19). No outcome is read — this measures selection, not prediction.

    ``readers`` supplements :data:`CANDIDATES` for a study reporting a column that
    is **not** a registered candidate — #171's raw and other-window moves, which
    ADR 0005's one-variant clause puts permanently out of reach of the rubric.
    They are a caller's argument rather than a module-level tuple precisely so
    that nothing can quietly promote one, and a name colliding with a registered
    candidate raises rather than replacing it: a study that could redefine
    ``Relative move`` under its own name is a study that could report a candidate
    it had quietly respecified. A name shadowing a *rubric* dimension is left to
    the caller, which is why the study prefixes its columns.
    """
    taken = list(taken)
    not_taken = list(not_taken)
    readers = readers or {}
    clash = sorted(set(readers) & set(_CANDIDATE_READERS))
    if clash:
        raise ValueError(
            f"reader(s) {clash} would redefine a registered candidate dimension; "
            f"rename the study column"
        )
    all_readers = {**_CANDIDATE_READERS, **readers}
    contrasts: list[DimensionContrast] = []
    for name, weight in dimensions:
        taken_xs = _booleans(taken, name, all_readers)
        not_taken_xs = _booleans(not_taken, name, all_readers)
        pooled = taken_xs + not_taken_xs

        taken_spread = _pstdev(taken_xs)
        combined_spread = _pstdev(pooled)
        untestable_within_executed = len(taken_xs) < 2 or taken_spread == 0.0
        testable_in_contrast = len(pooled) >= 2 and combined_spread > 0.0

        contrasts.append(
            DimensionContrast(
                dimension=name,
                weight=weight,
                taken_n=len(taken_xs),
                taken_hit_rate=_hit_rate(taken_xs),
                taken_spread=taken_spread,
                not_taken_n=len(not_taken_xs),
                not_taken_hit_rate=_hit_rate(not_taken_xs),
                not_taken_spread=_pstdev(not_taken_xs),
                combined_spread=combined_spread,
                untestable_within_executed=untestable_within_executed,
                testable_in_contrast=testable_in_contrast,
                testability_restored=untestable_within_executed and testable_in_contrast,
            )
        )
    return contrasts


def build_contrast(
    fields: Iterable[FieldSession], *, blind_spot_count: int
) -> SelectionContrast:
    """Assemble the selection contrast from the replayed field sessions.

    Splits every field session's detections into the taken group (his pick that
    night) and the not-taken comparison group, contrasts each dimension across
    them, and stamps the coverage figure. A quiet session (no entry) contributes
    to neither group.
    """
    taken: list[ScoredDetection] = []
    not_taken: list[ScoredDetection] = []
    for field in fields:
        taken.extend(field.taken)
        not_taken.extend(field.not_taken)

    return SelectionContrast(
        dimension_contrasts=contrast_dimensions(taken, not_taken),
        n_executed=len(taken),
        n_not_taken=len(not_taken),
        blind_spot_count=blind_spot_count,
    )


def run_contrast(
    trades: list[ExecutedTrade],
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
) -> SelectionContrast:
    """Replay the field and contrast his picks against the not-taken detections.

    Runs :func:`replay.field.replay_field` once over the window (the same field the
    outcome regression stands on, but reduced through an entirely separate code
    path into a separate result — the two are never merged), then contrasts the
    dimension distributions of the taken and not-taken detections. Only replayable
    trades mark the field; blind-spot trades never appear as a taken detection and
    ride only in the coverage count.
    """
    classified = classify(trades, store, market=market)
    replayable = [c.trade for c in classified if c.replayable]

    fields = replay_field(
        store,
        market,
        trades=replayable,
        blind_spot_tickers=blind_spot_tickers,
        burn_in=burn_in,
        sessions=sessions,
    )
    blind_spot_count = (
        fields[0].blind_spot_count if fields else len(set(blind_spot_tickers))
    )
    return build_contrast(fields, blind_spot_count=blind_spot_count)


def _fmt_contrast(c: DimensionContrast) -> str:
    flag = ""
    if c.testability_restored:
        flag = "  <- testability restored by the comparison group"
    elif c.untestable_within_executed:
        flag = "  (untestable within his trades; no spread here either)"
    return (
        f"  {c.dimension:<14} x{c.weight}  "
        f"taken {c.taken_hit_rate:>6.1%} (n={c.taken_n})  "
        f"not-taken {c.not_taken_hit_rate:>6.1%} (n={c.not_taken_n}){flag}"
    )


def format_report(report: SelectionContrast) -> str:
    """Human-readable summary: the per-dimension selection contrast and the notes.

    States plainly that this carries no outcome variable and that precision is not
    measurable, and describes the not-taken detections as a comparison group — no
    output labels them rejected, declined or negative (PRD user stories 17/24/25).
    """
    lines = [
        "selection contrast: executed trades vs not-taken detections",
        "(no outcome variable — this measures selection, not prediction)",
        f"executed-trade detections: {report.n_executed}  "
        f"not-taken detections: {report.n_not_taken}  "
        f"blind-spot coverage: {report.blind_spot_count} tickers missing",
        "",
        "dimension       weight  his picks        the field he passed over",
    ]
    lines += [_fmt_contrast(c) for c in report.dimension_contrasts]
    lines += ["", report.comparison_group_note, "", report.precision_note]
    return "\n".join(lines)


# -- command-line entry point -------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the selection contrast over the replay store and print the report.

    Thin CLI over the pure functions above (one entry point per study, PRD user
    story 30), kept separate from the outcome regression's CLI so neither analysis
    can be run into the other's table. Run as
    ``python -m replay.contrast --store data/replay.duckdb``.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--market", default=REPLAY_MARKET)
    args = parser.parse_args(argv)

    trades = load_trades(args.reference)
    store = Store.open(args.store)
    try:
        report = run_contrast(trades, store, args.market)
    finally:
        store.close()

    print(format_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
