"""Does the rubric discriminate his picks from the field? — re-measured with the
detector change held apart from the retention fix (#165).

§4's most consequential result is a **negative** one: his picks reach ≥3.5 stars
**17.3%** of the time against the field's **17.8%**, so the rubric does not rank
what he chose above what he didn't. #164 then found that the field that pair was
measured over was **truncated** — the replayed detection pass gated on
``Store.ranks``, which the two-year retention prunes as the chain advances, so 316
of the 821 measured sessions contributed nothing at all. Re-scored on the whole
field under the same rubric, the pair reads **14.6% / 12.6%** — an edge *in his
favour* where the published pair has him fractionally behind.

**Neither number corrects the other, because two variables moved between them.**
The detector went v1 → v2 with #154 (the hard 1.5×ADR cluster cut became the
far-outlier guard at 3.0), and the field truncation was fixed. A pair that moves
when two things change attributes its movement to neither. #164 said so and
flagged §4/§5's discrimination figures as pending re-derivation rather than
restating them; this module is that re-derivation.

**The grid.** The pair is re-measured at each detector version against each field,
so exactly one variable moves between any two cells read against each other:

===============  ==================  =====================================
detector         field               what the cell is
===============  ==================  =====================================
v1 (pre-#154)    truncated           **as published** — reproduces 17.3/17.8
v1 (pre-#154)    whole               **the retention fix alone**
v2 (#154)        truncated           **the restructure alone**
v2 (#154)        whole               fix and restructure together
v3 (#149)        whole               the **live** detector
===============  ==================  =====================================

Four of those five cells have a committed figure to reproduce, so the grid is
checked against the record rather than merely computed: §4's own pair and its
104 / 14,239 counts, #158's 159 / 29,096 / 45, #164's 349 / 54,399 / 109, and
#164's own v1-on-the-whole-field diagnostic of 242 / 27,116. The fifth is the
first measurement of `in_field` under the width #149 adopted.

**One detection pass, five cells, nothing written.** Two facts make that possible.

*The v1 field is a filter on the v2 field.* :func:`screener.detection._find_cluster`
records the identity: the restructure *added* names and moved none, so a name that
cleared the old 1.5×ADR cut emits a byte-identical row under v2. Reconstructing
v1's field is therefore striking every row whose trailing 3-bar range sits past
1.5, not a second detection pass — and the reconstruction is checkable, because
the committed store still holds the 45,600 ``detector_version = 1`` rows that pass
emitted.

*The truncated field is the whole field restricted to the retained sessions.* A
pruned session gated against an **empty** rank table, so it dropped every member
and contributed nothing — the truncation removed whole sessions rather than
thinning them. The retained set is read off the store, read-only, and handed in as
a parameter.

The gate width likewise rides on the detector version rather than being read off
:data:`~screener.detection.DETECTION_LOOKBACKS`, for the reason
:data:`replay.gate_sweep.GATE_AS_MEASURED` sets down: a measurement whose baseline
drifts with the constant it is arguing about cannot be re-run to audit itself.

**Read-only.** Like :mod:`replay.gate_sweep`, the forward pass is reconstructed
from the universe rows the replay store already holds with the ranks recomputed in
memory (:func:`replay.gate_sweep.build_sweep_sessions`) — the chain's own reuse
path with nothing written back. Nothing here touches the live store, and no live
constant is assigned.

**What the grid cannot say.** It re-measures the pair; it does not repair the
field. The §2 survivorship hole is permanent (#129, closed won't-do), so every
cell here is still measured against a field missing 29% of its tickers, and the
bound §4 states rides on all of them.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from screener.detection import Detection
from screener.store import Store

from .caching_store import CachingStore
from .chain import BURN_IN_SESSIONS, REPLAY_MARKET
from .field import FieldSession, build_field
from .gate_sweep import (
    GATE_AS_MEASURED,
    GateVariant,
    SweepSession,
    build_sweep_sessions,
    variant_gate,
)
from .placement import (
    BOARD_SIZE,
    RubricStarDistributions,
    StarDistribution,
    build_placement_report,
)
from .reference import (
    DEFAULT_BLIND_SPOT_OUT,
    DEFAULT_REFERENCE_JSON,
    ExecutedTrade,
    classify,
    load_trades,
)
from .study import progress_printer

# The star threshold §4's pair is quoted at. The result is *about* the top of the
# scale — the end the board actually shows — so the grid emits the share at or
# above it rather than a histogram to be re-totalled by hand at each reading.
DISCRIMINATION_STARS = 3.5

# The rubric the published pair was measured under. Every star figure carries its
# rubric stamp (#138); quoting a share against 17.3 / 17.8 without matching this
# one is the cross-run comparison the stamp exists to prevent.
PUBLISHED_RUBRIC = 1

# The two fields, named so a cell's provenance is legible without a comment.
# ``truncated`` is the field as it stood when §4 was measured — the sessions the
# rank retention had already pruned contributed nothing (#164).
FIELD_TRUNCATED = "truncated"
FIELD_WHOLE = "whole"
FIELD_SOURCES = (FIELD_TRUNCATED, FIELD_WHOLE)


@dataclass(frozen=True)
class DetectorSpec:
    """One detector version as the two things that decide its **population**.

    ``cluster_cut`` is the trailing-3-bar-range bound a name has to sit inside to
    be a detection at all — 1.5 under v1's hard cut, 3.0 under v2's far-outlier
    guard. ``lookbacks`` is the decile gate's width, which #149 moved for v3.

    **Pinned per version, never read off the live constants.** Both values are
    what the version *ran at*, so this module keeps producing the same grid after
    a later ticket moves either one — the reproducibility discipline
    :data:`replay.gate_sweep.GATE_AS_MEASURED` sets down. ``note`` is the ticket
    that set the version, carried onto the report so no cell is quoted without it.
    """

    version: int
    cluster_cut: float
    lookbacks: tuple[str, ...]
    note: str


# The three stamped populations, keyed by their :data:`~screener.detection.DETECTOR_VERSION`.
# v1 → v2 moves the cluster rule alone; v2 → v3 moves the gate alone. That is what
# makes each pair of cells a one-variable step.
DETECTORS: Mapping[int, DetectorSpec] = {
    1: DetectorSpec(
        version=1,
        cluster_cut=1.5,
        lookbacks=GATE_AS_MEASURED,
        note="hard 1.5xADR cluster cut, pre-#154",
    ),
    2: DetectorSpec(
        version=2,
        cluster_cut=3.0,
        lookbacks=GATE_AS_MEASURED,
        note="far-outlier guard at 3.0 (#145/#154)",
    ),
    3: DetectorSpec(
        version=3,
        cluster_cut=3.0,
        lookbacks=GATE_AS_MEASURED + ("12m",),
        note="guard at 3.0, gate admits 12m (#149)",
    ),
}

# The cells, in reading order: the published pair first, then the one-variable
# step that isolates the retention fix, then the two that isolate the restructure,
# then the live detector. Ordered rather than crossed so the report reads as the
# argument it is making.
GRID: tuple[tuple[int, str], ...] = (
    (1, FIELD_TRUNCATED),
    (1, FIELD_WHOLE),
    (2, FIELD_TRUNCATED),
    (2, FIELD_WHOLE),
    (3, FIELD_WHOLE),
)


def under_detector(
    detections: Iterable[Detection], spec: DetectorSpec
) -> list[Detection]:
    """The rows ``spec``'s detector would have emitted, out of a v2/v3 pass.

    A filter, not a re-detection, and that rests on an identity rather than an
    approximation: :func:`screener.detection._find_cluster` grades what it used to
    gate, so a name inside the old 1.5×ADR cut keeps the same ``k``, trigger and
    span under the guard. Striking the rows past ``cluster_cut`` therefore
    reconstructs the older population exactly.

    The gate width is applied separately (:func:`variant_gate`), because it decides
    which members reach the detector rather than what the detector emits.
    """
    return [d for d in detections if d.range_3bar_adr <= spec.cluster_cut]


def share_at_or_above(dist: StarDistribution, stars: float) -> float | None:
    """The share of a distribution at or above ``stars`` — §4's pair, as one number.

    ``None`` on an empty distribution: a share of nothing is not zero, and a cell
    with no picks in the field must not read as a cell whose picks all scored low.
    """
    if dist.total == 0:
        return None
    return sum(n for s, n in dist.counts.items() if s >= stars) / dist.total


@dataclass(frozen=True)
class CellMeasurement:
    """One cell of the grid: one detector version against one field.

    ``field_detections`` is the whole field over every measured session and
    ``eval_field_detections`` only the field on his evaluation sessions — the
    denominator §4's field share is taken over. ``measured_sessions`` is the window
    both fields were measured across, so ``detections_per_session`` is read against
    the window rather than against the sessions that survived: the truncation was a
    hole in the field, not a shorter run, and dividing by the survivors is exactly
    how the superseded 90.3 figure came about.

    ``by_rubric`` carries the picks/field distributions under every rubric version,
    stamped, so a cell can be read against a committed pair only under the rubric
    that pair was quoted with.
    """

    detector: DetectorSpec
    field_source: str
    measured_sessions: int
    sessions_with_detections: int
    field_detections: int
    placed: int
    in_field: int
    eval_field_detections: int
    by_rubric: list[RubricStarDistributions]

    @property
    def detections_per_session(self) -> float | None:
        """Field volume per **measured** session — the honest per-session figure."""
        if self.measured_sessions == 0:
            return None
        return self.field_detections / self.measured_sessions

    @property
    def detections_per_contributing_session(self) -> float | None:
        """Field volume per session that contributed a field at all.

        The denominator the superseded 90.3 and 201.6 were taken over — the 505
        sessions the retention left ranks for. Carried beside the honest figure
        rather than instead of it, so a reading of this grid can be checked against
        findings §3b and §5d, which state that denominator explicitly, without
        either figure being mistaken for the other.
        """
        if self.sessions_with_detections == 0:
            return None
        return self.field_detections / self.sessions_with_detections

    def rubric(self, version: int) -> RubricStarDistributions | None:
        """This cell's distributions under one rubric version, or ``None``."""
        return next(
            (r for r in self.by_rubric if r.rubric_version == version), None
        )

    def discrimination(
        self, version: int = PUBLISHED_RUBRIC
    ) -> tuple[float | None, float | None]:
        """§4's pair under ``version``: his picks' share, then the field's."""
        scored = self.rubric(version)
        if scored is None:
            return None, None
        return (
            share_at_or_above(scored.picks, DISCRIMINATION_STARS),
            share_at_or_above(scored.field, DISCRIMINATION_STARS),
        )

    def edge(self, version: int = PUBLISHED_RUBRIC) -> float | None:
        """Picks minus field at ≥3.5★, in percentage points — the sign §4 turns on."""
        picks, field = self.discrimination(version)
        if picks is None or field is None:
            return None
        return (picks - field) * 100


def _cell_fields(
    swept: Sequence[SweepSession],
    spec: DetectorSpec,
    field_source: str,
    *,
    entries: Mapping[date, set[str]],
    stored_rank_sessions: set[date],
    blind_spot_count: int,
) -> list[FieldSession]:
    """This cell's field, session by session.

    A truncated cell skips a session the retention had pruned outright rather than
    scoring an empty one: that is what the bug did, and an empty
    :class:`FieldSession` would otherwise read as a session that detected nothing.

    The RS-line candidate dimension is not computed here. It is never scored and
    the star order is identical with or without it (:func:`replay.field.build_field`),
    so supplying it would cost a second symbol's bars per session and change no
    figure this grid reports.
    """
    out: list[FieldSession] = []
    for s in swept:
        if field_source == FIELD_TRUNCATED and s.session not in stored_rank_sessions:
            continue
        gated = variant_gate(s.membership, _gate_of(spec))
        detections = under_detector(
            [d for d in s.detections if d.symbol in gated], spec
        )
        entered = entries.get(s.session, set())
        out.append(
            FieldSession(
                session=s.session,
                burn_in=False,
                members=s.members,
                detections=build_field(
                    detections,
                    s.ranks,
                    entered=entered,
                    any_entry=bool(entered),
                    lookbacks=spec.lookbacks,
                ),
                blind_spot_count=blind_spot_count,
            )
        )
    return out


def _gate_of(spec: DetectorSpec) -> GateVariant:
    """A detector version's gate, as the sweep's own width type.

    Reusing :class:`replay.gate_sweep.GateVariant` rather than re-unioning the
    deciles here keeps one definition of "the gate at this width" in the codebase —
    the sweep's, which runs the app's own :func:`screener.detection.detection_gate`.
    """
    return GateVariant(name=f"detector v{spec.version}", lookbacks=spec.lookbacks)


def measure_cell(
    swept: Sequence[SweepSession],
    spec: DetectorSpec,
    field_source: str,
    *,
    replayable: Sequence[ExecutedTrade],
    calendar: Sequence[date],
    stored_rank_sessions: set[date],
    blind_spot_count: int,
) -> CellMeasurement:
    """Measure one cell: build its field, then place every replayable trade in it.

    The placement is the study's own (:func:`replay.placement.build_placement_report`),
    so a cell's `in_field`, board and star distributions are computed by the code
    that produced the committed figures rather than by a second implementation of
    them — which is what lets four of the five cells be checked against the record.
    """
    entries: dict[date, set[str]] = {}
    for t in replayable:
        entries.setdefault(t.entry_date, set()).add(t.ticker)

    fields = _cell_fields(
        swept,
        spec,
        field_source,
        entries=entries,
        stored_rank_sessions=stored_rank_sessions,
        blind_spot_count=blind_spot_count,
    )
    placement = build_placement_report(
        list(replayable), list(calendar), fields, blind_spot_count
    )
    published = next(
        (r for r in placement.by_rubric if r.rubric_version == PUBLISHED_RUBRIC),
        None,
    )
    return CellMeasurement(
        detector=spec,
        field_source=field_source,
        measured_sessions=len(swept),
        sessions_with_detections=sum(1 for f in fields if f.detections),
        field_detections=sum(len(f.detections) for f in fields),
        placed=len(placement.placements),
        in_field=placement.in_field_count,
        eval_field_detections=published.field.total if published else 0,
        by_rubric=list(placement.by_rubric),
    )


@dataclass(frozen=True)
class DiscriminationGrid:
    """Every cell, plus the two one-variable steps the whole exercise is for.

    ``retention_step`` is (v1 truncated → v1 whole): the retention fix alone, with
    the detector held at the version §4 published under. ``restructure_step`` is
    (v1 whole → v2 whole): the detector change alone, on the whole field. Read
    together they decompose the move from 17.3/17.8 to 14.6/12.6 that #164 could
    only report as confounded.
    """

    cells: list[CellMeasurement]
    board_size: int
    blind_spot_count: int

    def cell(self, version: int, field_source: str) -> CellMeasurement | None:
        """The cell at one (detector version, field) pair, if it was measured."""
        return next(
            (
                c
                for c in self.cells
                if c.detector.version == version and c.field_source == field_source
            ),
            None,
        )

    @property
    def retention_step(
        self,
    ) -> tuple[CellMeasurement | None, CellMeasurement | None]:
        """The retention fix alone, at the detector §4 published under."""
        return self.cell(1, FIELD_TRUNCATED), self.cell(1, FIELD_WHOLE)

    @property
    def restructure_step(
        self,
    ) -> tuple[CellMeasurement | None, CellMeasurement | None]:
        """The detector restructure alone, on the whole field."""
        return self.cell(1, FIELD_WHOLE), self.cell(2, FIELD_WHOLE)


def build_grid(
    swept: Sequence[SweepSession],
    *,
    replayable: Sequence[ExecutedTrade],
    calendar: Sequence[date],
    stored_rank_sessions: set[date],
    blind_spot_count: int,
    grid: Sequence[tuple[int, str]] = GRID,
) -> DiscriminationGrid:
    """Measure every cell of ``grid`` over one prepared pass."""
    return DiscriminationGrid(
        cells=[
            measure_cell(
                swept,
                DETECTORS[version],
                field_source,
                replayable=replayable,
                calendar=calendar,
                stored_rank_sessions=stored_rank_sessions,
                blind_spot_count=blind_spot_count,
            )
            for version, field_source in grid
        ],
        board_size=BOARD_SIZE,
        blind_spot_count=blind_spot_count,
    )


def sessions_with_stored_ranks(
    store: Store, market: str, sessions: Iterable[date]
) -> set[date]:
    """The measured sessions the store still holds a rank table for.

    Read-only, and the whole of what "truncated" means: the replayed detection pass
    gated on these rows, so a session absent here gated against an empty table and
    contributed no field at all (#164). Derived from the store rather than from a
    cutoff date, because the retention boundary is a property of the chain that ran,
    not of the calendar.
    """
    return {s for s in sessions if store.ranks(market, s)}


def run_grid(
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    trades: list[ExecutedTrade],
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
    grid: Sequence[tuple[int, str]] = GRID,
    progress: Callable[[int, int, date], None] | None = None,
) -> DiscriminationGrid:
    """Run the whole #165 re-derivation over one read-only pass of the replay store.

    Reconstructs the forward pass (universe from the store, ranks in memory),
    detects once over the union of every version's gate, then derives each cell by
    filtering that one pass. The store is never written to and no live constant is
    assigned.
    """
    store = CachingStore.wrap(store)
    classified = classify(trades, store, market=market)
    replayable = [c.trade for c in classified if c.replayable]
    calendar = store.sessions(market)
    measured = list(sessions) if sessions is not None else calendar[burn_in:]

    union = tuple(
        dict.fromkeys(
            lb for version, _ in grid for lb in DETECTORS[version].lookbacks
        )
    )
    swept = build_sweep_sessions(
        store, market, measured, lookbacks=union, progress=progress
    )
    blind_spots = set(blind_spot_tickers)
    return build_grid(
        swept,
        replayable=replayable,
        calendar=calendar,
        stored_rank_sessions=sessions_with_stored_ranks(store, market, measured),
        blind_spot_count=len(blind_spots),
        grid=grid,
    )


# -- reporting ----------------------------------------------------------------


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def _pp(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}pp"


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def _cell_label(cell: CellMeasurement) -> str:
    return f"detector v{cell.detector.version}, {cell.field_source} field"


def _format_cell(cell: CellMeasurement) -> list[str]:
    """One cell in full: how much field existed, and what the pair reads on it."""
    lines = [
        f"{_cell_label(cell)}  [{cell.detector.note}]",
        f"  gate:                 {'/'.join(cell.detector.lookbacks)}",
        f"  sessions with a field: {cell.sessions_with_detections}"
        f"/{cell.measured_sessions}",
        f"  field detections:      {cell.field_detections}"
        f"  ({_num(cell.detections_per_session)} per measured session,"
        f" {_num(cell.detections_per_contributing_session)} per contributing one)",
        f"  in_field:              {cell.in_field}/{cell.placed}",
        f"  field on his eval sessions: {cell.eval_field_detections}",
    ]
    # Every rubric version, so the cell can be read against a committed pair under
    # the rubric that pair was stamped with — and so the live rubric's reading of
    # this field is on the artefact rather than only in the JSON.
    for scored in sorted(cell.by_rubric, key=lambda r: r.rubric_version):
        picks, field = cell.discrimination(scored.rubric_version)
        published = " (§4's rubric)" if scored.rubric_version == PUBLISHED_RUBRIC else ""
        lines.append(
            f"  rubric v{scored.rubric_version}{published}:"
            f"  picks >= {DISCRIMINATION_STARS}* {_pct(picks)}"
            f"   field {_pct(field)}"
            f"   edge {_pp(cell.edge(scored.rubric_version))}"
            f"   top {BOARD_SIZE} {scored.top_thirty}/{cell.placed}"
        )
    return lines


def _format_step(
    label: str,
    step: tuple[CellMeasurement | None, CellMeasurement | None],
) -> list[str]:
    """One one-variable step, stated as what it moved and by how much."""
    before, after = step
    if before is None or after is None:
        return [f"{label}: not measured"]
    return [
        f"{label}",
        f"  {_cell_label(before)}  ->  {_cell_label(after)}",
        f"  picks >= {DISCRIMINATION_STARS}*: {_pct(before.discrimination()[0])}"
        f"  ->  {_pct(after.discrimination()[0])}",
        f"  field >= {DISCRIMINATION_STARS}*: {_pct(before.discrimination()[1])}"
        f"  ->  {_pct(after.discrimination()[1])}",
        f"  edge:              {_pp(before.edge())}  ->  {_pp(after.edge())}",
        f"  field detections:  {before.field_detections}"
        f"  ->  {after.field_detections}",
    ]


def format_report(grid: DiscriminationGrid) -> str:
    """The grid, then the two one-variable steps it exists to separate."""
    lines = [
        "Discrimination grid — the detector change held apart from the retention "
        "fix (#165)",
        f"scope: US 2019-2022; blind-spot tickers missing from the field: "
        f"{grid.blind_spot_count}",
        f"the pair is quoted under rubric v{PUBLISHED_RUBRIC}, the rubric §4's "
        f"17.3% / 17.8% was measured with",
        "",
        "== cells ==",
        "",
    ]
    for cell in grid.cells:
        lines += _format_cell(cell) + [""]
    lines += ["== the two one-variable steps ==", ""]
    lines += _format_step("the retention fix alone (#164)", grid.retention_step) + [""]
    lines += _format_step(
        "the detector restructure alone (#154)", grid.restructure_step
    )
    return "\n".join(lines)


def _distribution_dict(dist: StarDistribution) -> dict:
    return {
        "counts": {str(star): n for star, n in sorted(dist.counts.items())},
        "total": dist.total,
        "share_at_or_above": share_at_or_above(dist, DISCRIMINATION_STARS),
    }


def _cell_dict(cell: CellMeasurement) -> dict:
    picks, field = cell.discrimination()
    return {
        "detectorVersion": cell.detector.version,
        "detectorNote": cell.detector.note,
        "clusterCut": cell.detector.cluster_cut,
        "lookbacks": list(cell.detector.lookbacks),
        "fieldSource": cell.field_source,
        "measuredSessions": cell.measured_sessions,
        "sessionsWithDetections": cell.sessions_with_detections,
        "fieldDetections": cell.field_detections,
        "detectionsPerSession": cell.detections_per_session,
        "detectionsPerContributingSession": cell.detections_per_contributing_session,
        "placed": cell.placed,
        "inField": cell.in_field,
        "evalFieldDetections": cell.eval_field_detections,
        "discriminationStars": DISCRIMINATION_STARS,
        "publishedRubric": PUBLISHED_RUBRIC,
        "picksShare": picks,
        "fieldShare": field,
        "edgePp": cell.edge(),
        "byRubric": [
            {
                "rubricVersion": r.rubric_version,
                "topThirty": r.top_thirty,
                "picks": _distribution_dict(r.picks),
                "field": _distribution_dict(r.field),
            }
            for r in cell.by_rubric
        ],
    }


def grid_to_dict(grid: DiscriminationGrid) -> dict:
    """The machine-readable grid: every cell and both steps."""
    def step(pair):
        before, after = pair
        return {
            "before": _cell_label(before) if before else None,
            "after": _cell_label(after) if after else None,
            "edgeBeforePp": before.edge() if before else None,
            "edgeAfterPp": after.edge() if after else None,
        }

    return {
        "boardSize": grid.board_size,
        "blindSpotCount": grid.blind_spot_count,
        "cells": [_cell_dict(c) for c in grid.cells],
        "steps": {
            "retentionFix": step(grid.retention_step),
            "detectorRestructure": step(grid.restructure_step),
        },
    }


def write_report(grid: DiscriminationGrid, path: str | Path) -> None:
    """Write the human-readable grid report to ``path``."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_report(grid) + "\n")


def write_results(grid: DiscriminationGrid, path: str | Path) -> None:
    """Write the machine-readable grid to ``path`` (stable, 2-space JSON)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(grid_to_dict(grid), indent=2) + "\n")


def _grid_progress(stream) -> Callable[[int, int, date], None]:
    """The study's throttled progress printer, bound to this run's one phase."""
    report = progress_printer(stream)
    return lambda i, total, session: report("grid", i, total, session)


def main(argv: list[str] | None = None) -> int:
    """Re-derive §4's discrimination pair with the two changes separated (#165).

        python -m replay.discrimination_grid --store data/replay.duckdb \\
            --out-report references/discrimination_grid.txt \\
            --out-json references/discrimination_grid.json

    Read-only: the pass reconstructs universe membership from the rows the replay
    store already holds and recomputes ranks in memory, writing nothing back.
    Progress and an ETA print to stderr while it runs.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--blind-spots", default=str(DEFAULT_BLIND_SPOT_OUT),
                        help="path to the committed blind-spot ticker list")
    parser.add_argument("--market", default=REPLAY_MARKET)
    parser.add_argument("--burn-in", type=int, default=BURN_IN_SESSIONS,
                        help="burn-in sessions before the first measured session")
    parser.add_argument("--out-report", default="references/discrimination_grid.txt",
                        help="where to write the human-readable report")
    parser.add_argument("--out-json", default="references/discrimination_grid.json",
                        help="where to write the machine-readable results")
    args = parser.parse_args(argv)

    trades = load_trades(args.reference)
    blind_spots = json.loads(Path(args.blind_spots).read_text())
    store = Store.open(args.store)
    try:
        grid = run_grid(
            store,
            args.market,
            trades=trades,
            blind_spot_tickers=blind_spots,
            burn_in=args.burn_in,
            progress=_grid_progress(sys.stderr),
        )
    finally:
        store.close()

    write_report(grid, args.out_report)
    write_results(grid, args.out_json)
    print(format_report(grid))
    print(f"\nwrote {args.out_report}")
    print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
