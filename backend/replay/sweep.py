"""Pricing the marginal cluster widen: what a wider ``TIGHT_MULT`` admits (#141).

Findings §3a closed with *leave the window unchanged*, and that verdict stands.
But the split it measured came back against the argument it was meant to support:
**113 of the 171 `cluster` misses are marginal** — a median 1.85× ADR against a
1.5× gate — and **148 of 171 are fresh entries**, not the re-entries the section
predicted. Two thirds of the largest single detection miss sit just past the
threshold, and no ticket owned the cost of reaching them.

**Why the widen is still refused, and why this module exists anyway.** The
calibration rule (§7) forbids loosening a gate on an A1 recall miss unless A3
shows the dimension has no signal *and* real spread. Tightness has clear signal —
§5b's +20.8pp, the second-strongest selector in the rubric — so the precondition
fails outright and nothing measured here can change it. What this module changes
is the *quality of the refusal*. The rule exists because precision is
unmeasurable, so a recall gain cannot be weighed against the noise it admits. That
is true of precision. It is **not** true of **field volume**, which is countable
on every measured session. Measure it, and the refusal stands on a number —
"N extra detections field-wide per real entry recovered" — instead of on principle
alone.

**What is measured, at each swept cut, over one forward chain:**

- **Recall recovered** — the A1 detection recall headline and ex-continuation, and
  how many of the live gate's marginal `cluster` misses come back
  (:func:`recovered_entries`, row by row rather than as a difference of totals).
- **Field inflation** — total detections across the measured sessions, against the
  baseline the live gate produces on the same chain.
- **The ratio** — added detections per recovered real entry. This is the ticket's
  headline (:func:`added_per_recovered`).
- **Board displacement** — whether admitted names push existing ones off the top
  thirty (:func:`board_displacement`), and what happens to his picks' in-field and
  top-thirty counts.

**Three constraints ride every figure this module emits, and the report prints
them.** Field inflation is a *volume* proxy and **never a false-positive rate**
(:data:`PRECISION_IS_NOT_MEASURED`) — the admitted names carry no verdict; they
are names he may never have seen (§5b's not-taken comparison group). Coverage
bounds this like everything else: 91 blind-spot tickers, 18.1% of realised R, and
only a fraction of replayable trades reach the field at all. And the scope is US
2019–2022, 86.6% of entries from 2020–21; no figure here transfers to IDX (§8).

**No live constant moves.** ``TIGHT_MULT`` is threaded as an argument from
:func:`screener.detection.detect` down through the funnel and the field
(:func:`replay.field.build_field_sessions`), defaulting to the module constant
everywhere. A swept field is computed in memory and never persisted, so the store
is byte-identical after a sweep. ``K_MIN, K_MAX = 3, 7`` and ``TIGHT_MULT = 1.5``
stand unless a separate ticket changes them on the strength of what this measures.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, Sequence

from screener.boards import BOARD_SIZE
from screener.detection import TIGHT_MULT
from screener.store import Store

from .caching_store import CachingStore
from .chain import BURN_IN_SESSIONS, REPLAY_MARKET, replay_chain
from .field import FieldSession, build_field_sessions
from .funnel import (
    MARGINAL_TIGHT_MULT,
    FunnelReport,
    FunnelRow,
    build_funnel_report,
    is_marginal_cluster_miss,
)
from .placement import SCOPE, PlacementReport, build_placement_report
from .reference import (
    DEFAULT_REFERENCE_JSON,
    ExecutedTrade,
    build_report,
    classify,
    evaluation_session,
    load_trades,
)
from .study import Progress, _progress_printer

# The cuts swept, the ticket's own list: the live gate, then three widenings that
# straddle the marginal population's median (1.85) and its p75 (2.13).
DEFAULT_TIGHT_MULTS = (1.5, 1.75, 2.0, 2.25)

# Printed on every report and carried into the results file. Field inflation counts
# *names*, not mistakes: nothing in the study can say whether an admitted name would
# have been a loss, because there is no control group of setups he passed over
# (§5b, §7, §9). A reader who takes this ratio for a false-positive rate has read
# the one thing the measurement is not.
PRECISION_IS_NOT_MEASURED = (
    "field inflation is a VOLUME proxy, never a false-positive rate: the admitted "
    "names carry no verdict — they are names he may never have seen (§5b, §9)"
)


# -- the three measurements, each computable on its own ----------------------


@dataclass(frozen=True)
class RecoveredEntries:
    """Which of the live gate's detection misses a swept cut turns into detections.

    Measured **row by row** against the baseline funnel rather than as a difference
    of two recall totals: a difference would net a recovered row against one the
    widen happened to lose, and the ticket's denominator is recovered *entries*.
    Rows are matched on ``(ticker, entry_date)``, which is unique per replayable
    trade and stable across cuts.

    ``marginal_baseline`` is the marginal `cluster` population at the *live* gate —
    §3a's 113 — and ``marginal_recovered`` the share of it this cut reaches. The
    two are reported together because a widen that recovers entries from outside
    that population is recovering something §3a never scoped.
    """

    recovered: int
    marginal_recovered: int
    marginal_baseline: int
    recovered_tickers: list[str]


def _row_key(row: FunnelRow) -> tuple[str, date]:
    return (row.ticker, row.entry_date)


def recovered_entries(
    baseline: Sequence[FunnelRow], swept: Sequence[FunnelRow]
) -> RecoveredEntries:
    """The entries ``swept`` detects that ``baseline`` missed, and the marginal share."""
    missed = {_row_key(r): r for r in baseline if not r.detection_pass}
    marginal_baseline = sum(1 for r in missed.values() if is_marginal_cluster_miss(r))

    recovered = [r for r in swept if r.detection_pass and _row_key(r) in missed]
    marginal_recovered = sum(
        1 for r in recovered if is_marginal_cluster_miss(missed[_row_key(r)])
    )
    return RecoveredEntries(
        recovered=len(recovered),
        marginal_recovered=marginal_recovered,
        marginal_baseline=marginal_baseline,
        recovered_tickers=sorted(r.ticker for r in recovered),
    )


@dataclass(frozen=True)
class BoardDisplacement:
    """What a widen does to the board the trader actually reads.

    Per session, the live gate's top :data:`screener.boards.BOARD_SIZE` names
    against the swept cut's. ``displaced`` counts slots lost — names on the live
    board that the swept board no longer carries — and ``admitted`` the names that
    took them. A name that merely changes rank inside the board is neither. The two
    are equal whenever both boards are full, and differ only on a session whose
    field is smaller than the board, which is why both are reported.
    """

    displaced: int
    admitted: int
    sessions_changed: int
    board_size: int


def _board(field: FieldSession, board_size: int) -> set[str]:
    return {d.symbol for d in field.detections[:board_size]}


def board_displacement(
    baseline: Sequence[FieldSession],
    swept: Sequence[FieldSession],
    *,
    board_size: int = BOARD_SIZE,
) -> BoardDisplacement:
    """Compare the two cuts' boards session by session."""
    swept_by_session = {f.session: f for f in swept}
    displaced = admitted = changed = 0
    for field in baseline:
        other = swept_by_session.get(field.session)
        if other is None:
            continue
        live_board = _board(field, board_size)
        swept_board = _board(other, board_size)
        lost = live_board - swept_board
        gained = swept_board - live_board
        displaced += len(lost)
        admitted += len(gained)
        changed += 1 if (lost or gained) else 0
    return BoardDisplacement(
        displaced=displaced,
        admitted=admitted,
        sessions_changed=changed,
        board_size=board_size,
    )


def pick_sessions(
    replayable: Sequence[ExecutedTrade],
    calendar: Sequence[date],
    fields: Sequence[FieldSession],
) -> set[date]:
    """The evaluation sessions his replayable entries are placed against.

    The committed study's field star distribution counts detections on **these**
    sessions only ("his picks vs the field, same sessions",
    :func:`replay.placement.build_placement_report`), not on all 821 measured ones.
    Both denominators are reported by the sweep, because they answer different
    questions and quoting either against the other's baseline would be an error:
    the whole-chain total is the field inflation a widen causes, and the
    pick-session total is the figure comparable to the study's committed 14,239.
    """
    available = {f.session for f in fields}
    sessions = set()
    for trade in replayable:
        eval_session = evaluation_session(list(calendar), trade.entry_date)
        if eval_session is not None and eval_session in available:
            sessions.add(eval_session)
    return sessions


def added_per_recovered(*, added: int, recovered: int) -> float | None:
    """The ticket's headline: extra field-wide detections per recovered real entry.

    ``None`` when nothing was recovered — not zero and not infinity. A widen that
    recovers no entry has no price per entry; reporting one would invent a
    denominator the measurement does not have.
    """
    if recovered <= 0:
        return None
    return added / recovered


# -- one swept cut, and the sweep across them --------------------------------


@dataclass(frozen=True)
class SweepPoint:
    """Everything measured at one ``tight_mult``, against the live gate's baseline.

    ``is_baseline`` marks the point that *is* the live detector — its ``added_*``
    and ``recovered`` figures are zero by construction and its ratio is ``None``,
    since it prices nothing. Every other point is read against it. (It is not named
    ``baseline``: :attr:`TightMultSweep.baseline` is the *point*, and one name for
    both a flag and the thing it flags reads wrong at every call site.)
    """

    tight_mult: float
    is_baseline: bool
    # A1 — recall
    detection_passed: int
    detection_total: int
    detection_passed_ex_continuation: int
    detection_total_ex_continuation: int
    recovered: int
    marginal_recovered: int
    marginal_baseline: int
    recovered_tickers: list[str]
    # A2 — field volume
    field_detections: int
    added_detections: int
    pick_session_detections: int
    added_pick_session_detections: int
    # the headline
    added_per_recovered: float | None
    # A2 — placement and the board
    picks_total: int
    in_field_count: int
    top_thirty_count: int
    displaced: int
    admitted: int
    sessions_changed: int

    @property
    def detection_recall(self) -> float:
        total = self.detection_total
        return self.detection_passed / total if total else 0.0

    @property
    def detection_recall_ex_continuation(self) -> float:
        total = self.detection_total_ex_continuation
        return self.detection_passed_ex_continuation / total if total else 0.0


@dataclass(frozen=True)
class TightMultSweep:
    """The whole sweep: one chain, one point per swept cut.

    ``measured_sessions`` and ``blind_spot_count`` are the run's shape and its
    coverage bound, carried on the result so no figure is read without them.
    """

    market: str
    scope: str
    measured_sessions: int
    blind_spot_count: int
    board_size: int
    points: list[SweepPoint]

    @property
    def baseline(self) -> SweepPoint:
        return next(p for p in self.points if p.is_baseline)


def _point(
    tight_mult: float,
    *,
    baseline_funnel: FunnelReport,
    baseline_fields: Sequence[FieldSession],
    funnel: FunnelReport,
    fields: Sequence[FieldSession],
    placement: PlacementReport,
    picks_sessions: set[date],
) -> SweepPoint:
    """Assemble one swept cut's row against the live gate's baseline."""
    is_live = tight_mult == TIGHT_MULT
    rec = recovered_entries(baseline_funnel.rows, funnel.rows)
    disp = board_displacement(baseline_fields, fields)
    detections = sum(f.field_size for f in fields)
    added = detections - sum(f.field_size for f in baseline_fields)
    on_picks = sum(f.field_size for f in fields if f.session in picks_sessions)
    added_on_picks = on_picks - sum(
        f.field_size for f in baseline_fields if f.session in picks_sessions
    )
    return SweepPoint(
        tight_mult=tight_mult,
        is_baseline=is_live,
        detection_passed=funnel.detection.passed,
        detection_total=funnel.detection.total,
        detection_passed_ex_continuation=funnel.detection.passed_ex_continuation,
        detection_total_ex_continuation=funnel.detection.total_ex_continuation,
        recovered=rec.recovered,
        marginal_recovered=rec.marginal_recovered,
        marginal_baseline=rec.marginal_baseline,
        recovered_tickers=rec.recovered_tickers,
        field_detections=detections,
        added_detections=added,
        pick_session_detections=on_picks,
        added_pick_session_detections=added_on_picks,
        added_per_recovered=added_per_recovered(added=added, recovered=rec.recovered),
        picks_total=len(placement.placements),
        in_field_count=placement.in_field_count,
        top_thirty_count=placement.top_thirty_count,
        displaced=disp.displaced,
        admitted=disp.admitted,
        sessions_changed=disp.sessions_changed,
    )


def run_sweep(
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    trades: list[ExecutedTrade],
    tight_mults: Sequence[float] = DEFAULT_TIGHT_MULTS,
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
    progress: Progress | None = None,
) -> TightMultSweep:
    """Sweep ``tight_mult`` over **one** forward chain and price each widen.

    The chain — universe and ranks per session — is replayed exactly once and every
    cut is measured against it, so the differences between points are the cut's and
    nothing else's. Per cut the funnel is re-walked (A1 recall) and the field
    rebuilt in memory (A2 volume and placement); the live cut runs first and is the
    baseline every other point is read against.

    **The baseline is recomputed, not read back.** Every point — the live cut
    included — is built through :func:`replay.field.build_field_sessions` with
    ``persist=False``, so all of them gate on the chain's own ranks and none of them
    touches the store's detection rows. The store's persisted field would otherwise
    make the baseline the one point produced by a different code path, and the
    difference between paths would land in a column labelled "added detections".
    One consequence worth stating: this baseline need not equal the field total in
    the committed study report, whose detection stage gates on
    :meth:`Store.ranks` and therefore sees an empty rank table on every measured
    session outside the two-year retention window.

    ``tight_mults`` must contain the live :data:`screener.detection.TIGHT_MULT` —
    without the baseline there is nothing to price the widens against. The live
    constant is never assigned; a swept field persists nothing.
    """
    if TIGHT_MULT not in tuple(tight_mults):
        raise ValueError(
            f"the sweep needs the live gate ({TIGHT_MULT}) as its baseline; "
            f"got {tuple(tight_mults)}"
        )
    ordered = [TIGHT_MULT] + [m for m in tight_mults if m != TIGHT_MULT]

    store = CachingStore.wrap(store)
    classified = classify(trades, store, market=market)
    replayable = [c.trade for c in classified if c.replayable]
    calendar = store.sessions(market)
    # The coverage figure every field-derived result must carry (user story 22),
    # recomputed from the reference set exactly as :func:`replay.study.run_study`
    # does rather than defaulted to nothing — a sweep that reported a coverage of
    # zero would be claiming a completeness the study does not have.
    blind_spots = list(blind_spot_tickers) or build_report(
        trades, store, market=market
    ).blind_spot_ticker_list

    def phase_progress(phase: str):
        if progress is None:
            return None
        return lambda i, total, session: progress(phase, i, total, session)

    chain = replay_chain(
        store,
        market,
        blind_spot_tickers=blind_spots,
        burn_in=burn_in,
        sessions=sessions,
        progress=phase_progress("chain"),
    )
    blind_spot_count = chain[0].blind_spot_count if chain else len(set(blind_spots))

    points: list[SweepPoint] = []
    baseline_funnel: FunnelReport | None = None
    baseline_fields: list[FieldSession] | None = None
    picks_sessions: set[date] = set()
    for mult in ordered:
        funnel = build_funnel_report(
            classified, calendar, chain, store, market,
            blind_spot_tickers=blind_spots,
            tight_mult=mult,
        )
        fields = build_field_sessions(
            store, market, chain,
            trades=replayable,
            progress=phase_progress(f"field@{mult:g}"),
            tight_mult=mult,
            # Every point, the baseline included, is a *measurement* field: computed
            # in memory off the chain's own ranks and persisted nowhere. The
            # baseline must be built the same way as the cuts it prices — reading
            # the store's persisted detections for it and recomputing the others
            # would put the difference between two code paths into a column
            # labelled "added detections".
            measurement=True,
        )
        if baseline_funnel is None or baseline_fields is None:
            baseline_funnel, baseline_fields = funnel, fields
            # Fixed at the baseline: which sessions his entries are placed against
            # is a property of the trades and the chain, not of the cut, so every
            # point's pick-session total covers the same sessions.
            picks_sessions = pick_sessions(replayable, calendar, fields)
        placement = build_placement_report(
            replayable, calendar, fields, blind_spot_count
        )
        points.append(
            _point(
                mult,
                baseline_funnel=baseline_funnel,
                baseline_fields=baseline_fields,
                funnel=funnel,
                fields=fields,
                placement=placement,
                picks_sessions=picks_sessions,
            )
        )

    points.sort(key=lambda p: p.tight_mult)
    return TightMultSweep(
        market=market,
        scope=SCOPE,
        measured_sessions=len(chain),
        blind_spot_count=blind_spot_count,
        board_size=BOARD_SIZE,
        points=points,
    )


# -- human-readable report ----------------------------------------------------


def _ratio(value: float | None) -> str:
    return "—" if value is None else f"{value:,.1f}"


def format_sweep(sweep: TightMultSweep) -> str:
    """The sweep as a report: one row per cut, the headline ratio in a column.

    Every figure carries its bound in the text below the table rather than in a
    footnote nobody reads: the ratio is a volume price, not a precision figure; the
    coverage hole bounds it; and the scope is US 2019–2022 only.
    """
    lines = [
        f"TIGHT_MULT sweep — pricing the marginal cluster widen ({sweep.market}, #141)",
        f"one forward chain: {sweep.measured_sessions} measured sessions, "
        f"{sweep.blind_spot_count} blind-spot tickers, board size {sweep.board_size}",
        f"scope: {sweep.scope}",
        "",
        f"{'cut':>6}  {'recall':>7}  {'ex-cont':>7}  {'recov':>6}  {'marginal':>9}  "
        f"{'field':>9}  {'added':>8}  {'added/entry':>11}  {'in-field':>9}  "
        f"{'top-30':>7}  {'displaced':>9}",
    ]
    for p in sweep.points:
        marker = "  (live)" if p.is_baseline else ""
        lines.append(
            f"{p.tight_mult:>6.2f}  "
            f"{p.detection_recall:>6.1%}  "
            f"{p.detection_recall_ex_continuation:>6.1%}  "
            f"{p.recovered:>6d}  "
            f"{p.marginal_recovered:>4d}/{p.marginal_baseline:<4d}  "
            f"{p.field_detections:>9,d}  "
            f"{p.added_detections:>8,d}  "
            f"{_ratio(p.added_per_recovered):>11}  "
            f"{p.in_field_count:>4d}/{p.picks_total:<4d}  "
            f"{p.top_thirty_count:>7d}  "
            f"{p.displaced:>9,d}{marker}"
        )

    base = sweep.baseline
    lines += [
        "",
        f"baseline (the live gate, TIGHT_MULT = {base.tight_mult:g}): "
        f"{base.field_detections:,d} detections over {sweep.measured_sessions} sessions, "
        f"detection recall {base.detection_recall:.1%} "
        f"({base.detection_passed}/{base.detection_total}), "
        f"{base.marginal_baseline} marginal `cluster` misses",
        "",
        "the same fields counted on his evaluation sessions only — the denominator "
        "the study's committed field distribution uses, not the whole chain.",
        "NB the committed study reports 14,239 here, not the baseline below: its "
        "detection stage gates on Store.ranks, which the two-year retention has "
        "pruned on every measured session outside the retained window, so its field "
        "is empty on those sessions. 14,239 is therefore not the live gate's field "
        "on these sessions and is not what a widen should be priced against (§3a).",
    ]
    for p in sweep.points:
        lines.append(
            f"  TIGHT_MULT {p.tight_mult:g}: {p.pick_session_detections:,d} detections"
            + ("" if p.is_baseline else f"  (+{p.added_pick_session_detections:,d})")
        )
    lines += [
        "",
        "headline — added detections per recovered entry:",
    ]
    for p in sweep.points:
        if p.is_baseline:
            continue
        lines.append(
            f"  TIGHT_MULT {p.tight_mult:g}: {_ratio(p.added_per_recovered)} extra "
            f"detections field-wide for each of the {p.recovered} real entries it "
            f"recovers ({p.added_detections:,d} added over {p.recovered})"
        )
    lines += [
        "",
        f"constraint: {PRECISION_IS_NOT_MEASURED}",
        f"coverage:   every figure is bounded by {sweep.blind_spot_count} blind-spot "
        "tickers; only a fraction of replayable trades reach the field at all",
        f"scope:      {sweep.scope} — no figure here transfers to IDX (§8)",
        "no live constant is changed by this measurement: "
        f"TIGHT_MULT = {TIGHT_MULT} stands",
    ]
    return "\n".join(lines)


# -- machine-readable results -------------------------------------------------


def sweep_to_dict(sweep: TightMultSweep) -> dict:
    """A JSON-serialisable dict of every swept point, notes included."""
    return {
        "market": sweep.market,
        "scope": sweep.scope,
        "measured_sessions": sweep.measured_sessions,
        "blind_spot_count": sweep.blind_spot_count,
        "board_size": sweep.board_size,
        "live_tight_mult": TIGHT_MULT,
        "marginal_tight_mult": MARGINAL_TIGHT_MULT,
        "precision_note": PRECISION_IS_NOT_MEASURED,
        "points": [
            {
                "tight_mult": p.tight_mult,
                "baseline": p.is_baseline,
                "detection_passed": p.detection_passed,
                "detection_total": p.detection_total,
                "detection_recall": p.detection_recall,
                "detection_passed_ex_continuation": p.detection_passed_ex_continuation,
                "detection_total_ex_continuation": p.detection_total_ex_continuation,
                "detection_recall_ex_continuation": p.detection_recall_ex_continuation,
                "recovered": p.recovered,
                "marginal_recovered": p.marginal_recovered,
                "marginal_baseline": p.marginal_baseline,
                "recovered_tickers": list(p.recovered_tickers),
                "field_detections": p.field_detections,
                "added_detections": p.added_detections,
                "pick_session_detections": p.pick_session_detections,
                "added_pick_session_detections": p.added_pick_session_detections,
                "added_per_recovered": p.added_per_recovered,
                "picks_total": p.picks_total,
                "in_field_count": p.in_field_count,
                "top_thirty_count": p.top_thirty_count,
                "displaced": p.displaced,
                "admitted": p.admitted,
                "sessions_changed": p.sessions_changed,
            }
            for p in sweep.points
        ],
    }


def write_sweep(
    sweep: TightMultSweep, report_path: str | Path, json_path: str | Path
) -> None:
    """Write both outputs — the report and the results file — creating parents."""
    for path, text in (
        (report_path, format_sweep(sweep) + "\n"),
        (json_path, json.dumps(sweep_to_dict(sweep), indent=2) + "\n"),
    ):
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)


# -- command-line entry point -------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Run the sweep against a built replay store and write both outputs.

        python -m replay.sweep --store data/replay.duckdb

    Progress and an ETA print to stderr per phase — the chain once, then one field
    pass per swept cut — so a long run reports rather than hanging silently.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--market", default=REPLAY_MARKET)
    parser.add_argument("--burn-in", type=int, default=BURN_IN_SESSIONS)
    parser.add_argument(
        "--tight-mults",
        default=",".join(f"{m:g}" for m in DEFAULT_TIGHT_MULTS),
        help="comma-separated cuts to sweep; must include the live gate",
    )
    parser.add_argument("--out-report", default="references/tight_mult_sweep_report.txt")
    parser.add_argument("--out-json", default="references/tight_mult_sweep_results.json")
    args = parser.parse_args(argv)

    mults = tuple(float(m) for m in args.tight_mults.split(","))
    trades = load_trades(args.reference)
    store = Store.open(args.store)
    try:
        sweep = run_sweep(
            store,
            args.market,
            trades=trades,
            tight_mults=mults,
            burn_in=args.burn_in,
            progress=_progress_printer(sys.stderr),
        )
    finally:
        store.close()

    write_sweep(sweep, args.out_report, args.out_json)
    print(format_sweep(sweep))
    print(f"\nwrote {args.out_report}")
    print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
