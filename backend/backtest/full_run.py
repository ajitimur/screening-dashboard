"""The full run — both markets, fourteen years (issue #198).

PRD #182 Phase 3, at full scope.

Phase 3 replayed one market over a short window to prove the machine ran
(:mod:`backtest.run`). This is the same machine at the scope the plan actually
asks about: US and IDX, 2012-01-01 through the latest complete session, each
market run forward in an unbroken sequence.

Nothing here re-implements the replay. :func:`~backtest.run.run_denominator`
already refuses a gapped sequence, already persists burn-in sessions and flags
them out of measurement, and already reuses a session it has computed rather than
recomputing it. What this module adds is the three things that only exist once
there is more than one market and more than a sliver of window:

**The window comes from the contract, not from the caller.** ``scope.markets``,
``window.store_start``, ``window.measured_start`` and ``window.measured_end`` are
committed cells, so "the full run" is a fact about the contract rather than a set
of command-line dates someone has to retype correctly. ``measured_end`` is the
sentinel :data:`LATEST_COMPLETE_SESSION`, resolved per market against that
market's own last stored session — the two exchanges do not close on the same
days and a shared end date would clip one of them.

**The markets are reported separately, and there is no pooled figure to read.**
Findings §8 measured that shapes travel between US and IDX and magnitudes do not,
so a combined number describes neither market. :class:`FullRun` holds one
:class:`~backtest.run.DenominatorRun` per market and offers no total: the absence
is the design, not an omission.

**Figures are gated on the anchors.** The plan's third rule is anchor before
believing, and :meth:`FullRun.require_settled` is where that rule is enforceable
rather than merely written down — a report built over an unsettled anchor check
raises :class:`AnchorsNotSettled` instead of printing numbers. The gate sits
*after* the replay and *before* the figures on purpose: the two gate-dependent
anchors are measured over the run's own field, so a gate ahead of the replay
could never have them (:func:`backtest.anchors._field_measurements`).

The gate also checks *which field* was anchored. Since #211 the ``in_field``
anchor carries one pin per universe, and this run screens its field with the
contract's stateless one — so an anchor report checked over the app's universe is
refused however green it is. That is the one failure a passing report can carry,
and it is the difference between a report that passed and a report that passed
about another run.

Detections per session
----------------------
Plotted across the whole window, per market, off the persisted denominator alone
— :func:`~backtest.figures.detections_series` and
:func:`~backtest.figures.format_detections_grid`, the same series and the same
grid :mod:`backtest.figures` draws, so a hole means one thing in this repo rather
than two. A count that collapses in a given year is a data hole, and a backtest
that quietly skips it reports on a market that took the day off (story 77).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

from backtest.anchors import (
    SETTLED_VERDICTS,
    UNIVERSE_APP,
    UNIVERSE_STATELESS,
    VERDICT_EXPLAINED,
    AnchorReport,
    format_anchors,
)
from backtest.chain import WindowNotCovered
from backtest.contract import (
    DEFAULT_CONTRACT,
    SCOPE_MARKETS_KEY,
    WINDOW_MEASURED_END_KEY,
    WINDOW_MEASURED_START_KEY,
    WINDOW_STORE_START_KEY,
    RunContract,
)
from backtest.denominator import DenominatorStore, denominator_path
from backtest.figures import detections_series, format_detections_grid
from backtest.result import stamp_result
from backtest.run import (
    DenominatorRun,
    format_run,
    progress_printer,
    run_denominator,
)
from backtest.store import Store

# The contract's ``window.measured_end``: not a date, because the store's last
# session moves every night and a date committed here would go stale the day
# after it was written.
LATEST_COMPLETE_SESSION = "latest_complete_session"


class AnchorsNotSettled(RuntimeError):
    """A figure was asked for over a run whose anchors have not been settled.

    Its own error because the plan's third rule is a *refusal*, not a warning: an
    anchor that neither matched nor carries a written cause means the new store or
    the new chain has a bug, and every figure computed over it inherits that bug
    while looking exactly like a figure that does not.
    """


@dataclass(frozen=True)
class AnchorOutcome:
    """A settled-ness verdict, read back from an anchor report on disk.

    The counterpart to a live :class:`~backtest.anchors.AnchorReport`, for the case
    the command-line path actually has: the anchors were checked in a separate
    invocation and all this one can see is what that invocation wrote down.

    It carries the same five names an :class:`~backtest.anchors.AnchorReport`
    answers — ``passes``, ``failed``, ``explained``, ``geometry_only``,
    ``universe`` — so the gate reads one interface and never asks which kind it
    was handed. A run
    anchored from a file is gated exactly as strictly as one anchored in process,
    and that is a property of there being no second code path rather than of two
    code paths agreeing.
    """

    passes: bool
    failed: tuple[str, ...] = ()
    explained: tuple[str, ...] = ()
    geometry_only: bool = False
    universe: str = UNIVERSE_APP
    first_measurement: tuple[str, ...] = ()


class MarketNotRun(KeyError):
    """A market was asked of a run that did not replay it.

    Distinct from a market that replayed and found nothing: the second is a
    result, and the first is a question about a run that was never made. Folding
    them together would let a two-market report print a one-market run's figures
    beside an empty column and read as a market that took fourteen years off.
    """


# -- the contract's window ----------------------------------------------------


def contract_markets(contract: RunContract = DEFAULT_CONTRACT) -> tuple[str, ...]:
    """The markets the contract scopes the run to, in the order it names them.

    Order is preserved rather than sorted: the contract lists US first because
    that is the market the reference study measured, and every report below reads
    in the same order as the cell that authorised it.
    """
    return tuple(contract.value(SCOPE_MARKETS_KEY))


def contract_store_start(contract: RunContract = DEFAULT_CONTRACT) -> date:
    """The contract's store-window boundary, as the calendar date it is written as.

    A *boundary*, not a session: ``2011-01-01`` is New Year's Day and neither
    exchange has ever traded on it. :func:`store_window_start` is what turns it
    into a session.
    """
    return date.fromisoformat(contract.value(WINDOW_STORE_START_KEY))


# Longer than any closure either exchange takes — IDX's Eid collective leave is
# the longest at about a week plus the weekends around it — and far shorter than
# the smallest crawl mistake worth catching, which is measured in months. The
# bound exists so "the boundary is not a trading day" and "the crawl started
# late" stay distinguishable; anything inside it is the calendar, anything past
# it is a hole.
LONGEST_CLOSURE = timedelta(days=14)


def store_window_start(
    store: Store, market: str, contract: RunContract = DEFAULT_CONTRACT
) -> date:
    """The first stored session on or after the contract's store-window boundary.

    The contract names a calendar date and the chain replays sessions, and the two
    are not the same kind of thing: ``window.store_start`` is ``2011-01-01``, which
    is a holiday on both exchanges, so handing it to the chain unresolved asks
    :func:`~backtest.chain.check_window_covered` for a session that cannot exist
    and fails a run that is in fact fully covered. (The documented Phase 3 command
    passes that date directly, and this is the first run to hand it to a real
    store rather than to a fixture whose calendar has no weekends.)

    Resolving forward would, on its own, disarm the guard it is working around: a
    crawl that started in 2013 also has a "first session on or after 2011-01-01".
    So the distance is checked. A first session within :data:`LONGEST_CLOSURE` of
    the boundary is the exchange being shut; anything beyond it is history the
    crawl never fetched, and is refused here for the same reason
    :class:`~backtest.chain.WindowNotCovered` refuses a short end — every count
    over it would be computed correctly across the wrong window.
    """
    boundary = contract_store_start(contract)
    calendar = store.sessions(market)
    if not calendar:
        raise WindowNotCovered(f"the store holds no {market} sessions at all")
    first = next((s for s in calendar if s >= boundary), None)
    if first is None:
        raise WindowNotCovered(
            f"the store's last {market} session is {calendar[-1]}, before the "
            f"contract's store window even opens at {boundary}"
        )
    if first - boundary > LONGEST_CLOSURE:
        raise WindowNotCovered(
            f"the contract's {market} store window opens {boundary} but the "
            f"store's first session on or after it is {first}, "
            f"{(first - boundary).days} "
            f"days later — too far to be a closure, so the crawl never fetched "
            "that history and the burn-in would be computed over the wrong window"
        )
    return first


def contract_measured_start(contract: RunContract = DEFAULT_CONTRACT) -> date:
    """The first *measured* session. Everything before it is burn-in."""
    return date.fromisoformat(contract.value(WINDOW_MEASURED_START_KEY))


def measured_end(
    store: Store, market: str, contract: RunContract = DEFAULT_CONTRACT
) -> date | None:
    """The last measured session for ``market``, resolving the contract's sentinel.

    ``latest_complete_session`` resolves to *this market's* last stored session,
    not to a date shared across markets. US and IDX keep different calendars and
    their crawls finish at different points, so one shared end date would either
    clip the market that ran later or ask the other for a session it does not
    hold — and :func:`~backtest.chain.check_window_covered` would refuse the
    second, loudly, for a reason that is really about the sentinel.

    The contract says "latest **complete** session" and this returns the latest
    *stored* one, which is the same session and not by luck: the store discards a
    non-final bar at ingest (:mod:`backtest.store`, and CONTEXT.md's *Final bar*),
    so a session only has bars once it has closed. Re-checking finality here would
    be a second implementation of that rule, free to disagree with the one that
    actually decided what got written.

    A committed date is honoured as written, so a contract that pins the window
    shut for a reproduction run does not silently reopen it.

    A market the store holds no sessions for raises rather than returning ``None``,
    which :func:`store_window_start` would have meant as "run to the store's own
    edge" — the same empty store answered two ways by two functions in this module
    is how a run over nothing reports a clean empty window.
    """
    declared = contract.value(WINDOW_MEASURED_END_KEY)
    if declared != LATEST_COMPLETE_SESSION:
        return date.fromisoformat(declared)
    calendar = store.sessions(market)
    if not calendar:
        raise WindowNotCovered(f"the store holds no {market} sessions at all")
    return calendar[-1]


# -- the run ------------------------------------------------------------------


@dataclass(frozen=True)
class FullRun:
    """Both markets' denominators, and the anchor check that licenses reading them.

    ``runs`` is one :class:`~backtest.run.DenominatorRun` per market, in the
    contract's order. There is deliberately **no** combined total on this class:
    findings §8 measured that magnitudes do not transfer between the two markets,
    so a pooled figure would describe neither, and the cheapest way to keep one
    from being read is to keep one from existing.

    ``anchors`` is the Phase 6 report (:mod:`backtest.anchors`) or ``None`` when
    the anchors were never checked. Either way the *replay* is complete and
    persisted — the gate is on reading figures, not on doing the work.
    """

    contract: RunContract
    runs: tuple[DenominatorRun, ...]
    anchors: AnchorReport | AnchorOutcome | None = None

    @property
    def markets(self) -> tuple[str, ...]:
        return tuple(r.market for r in self.runs)

    def for_market(self, market: str) -> DenominatorRun:
        """This market's run, or :class:`MarketNotRun` if it was not replayed."""
        for run in self.runs:
            if run.market == market:
                return run
        raise MarketNotRun(
            f"{market} was not replayed by this run; it covered "
            f"{', '.join(self.markets) or 'no markets'}"
        )

    @property
    def settled(self) -> bool:
        """Whether every anchor matched or carries a written cause.

        ``False`` when the anchors were never checked at all, which is the same
        answer as a failure and for the same reason: a run nobody anchored is not
        an anchored run, and the plan's rule is about what has been *established*
        before a figure is read, not about what has been attempted.
        """
        return self.anchors is not None and self.anchors.passes

    def require_settled(self) -> None:
        """Refuse to go on unless the anchors are settled.

        Called by every path in this module that emits a figure, so the rule is
        enforced in one place and cannot be observed by a caller who forgot to ask.
        """
        if self.anchors is None:
            raise AnchorsNotSettled(
                "the anchors were never checked, so no figure from this run may be "
                "read: run backtest.anchors against the store first, and hand its "
                "report here"
            )
        if self.anchors.passes:
            # The one failure a *passing* report can carry: every anchor in it
            # matched, and it anchored a different field than the one this run
            # screened. #211 measured that in_field and §4b's gap are properties
            # of the pair, so a report over the app's universe says nothing about
            # this run however green it is. A report that already fails is left
            # to refuse for its own reason, which is the more specific one.
            if self.anchors.universe != UNIVERSE_STATELESS:
                raise AnchorsNotSettled(
                    f"this run screens its field with the contract's stateless "
                    f"universe, but the anchor report was checked over "
                    f"{self.anchors.universe!r}. A report over another universe "
                    "anchors another run: re-check the anchors against the "
                    "field this run actually built"
                )
            return
        if self.anchors.geometry_only:
            # Read off the report rather than inferred from an empty failure
            # list: a geometry-only check has passing rows and no failing one, so
            # deducing it from what failed would be deducing it from the very
            # thing that makes it read like a pass.
            raise AnchorsNotSettled(
                "only the geometry anchors were checked, so no figure from this "
                "run may be read: a run anchored on four of six is not an "
                "anchored run"
            )
        raise AnchorsNotSettled(
            "these anchors neither matched nor carry a written cause: "
            f"{', '.join(self.anchors.failed) or 'none named'} — a figure read "
            "over them would inherit whatever moved them"
        )

    def detections_per_session(self, market: str) -> dict[date, int]:
        """One market's measured detections per session — the plotted series."""
        return self.for_market(market).detections_per_session


def run_full(
    store: Store,
    denominator: DenominatorStore,
    contract: RunContract = DEFAULT_CONTRACT,
    *,
    markets: Sequence[str] | None = None,
    anchors: AnchorReport | AnchorOutcome | None = None,
    progress: Callable[[int, int, date], None] | None = None,
) -> FullRun:
    """Replay every market the contract scopes, end to end over its full window.

    One :func:`~backtest.run.run_denominator` per market, each over
    ``[window.store_start, latest complete session]`` with everything before
    ``window.measured_start`` persisted as burn-in and excluded from measurement.
    The markets run in the contract's order and never interleave: each is a
    separate forward chain, and a gap in either raises
    :class:`~replay.chain.GapError` before that market computes anything.

    ``markets`` narrows the run for a reproduction of one market; it may not widen
    it past the contract, because a market the contract does not scope has no
    committed window to run over.

    Re-running is safe and is how a long run is resumed: the chain reads back a
    session it has already computed rather than recomputing it, so a second pass
    over the same pair of stores produces identical rows and pays only for what
    the first pass did not reach.
    """
    scoped = contract_markets(contract)
    chosen = tuple(markets) if markets is not None else scoped
    unscoped = [m for m in chosen if m not in scoped]
    if unscoped:
        raise ValueError(
            f"{', '.join(unscoped)} is not scoped by the contract, which covers "
            f"{', '.join(scoped)}: there is no committed window to run it over"
        )

    runs = tuple(
        run_denominator(
            store,
            denominator,
            market,
            contract,
            start=store_window_start(store, market, contract),
            end=measured_end(store, market, contract),
            measured_start=contract_measured_start(contract),
            progress=progress,
        )
        for market in chosen
    )
    return FullRun(contract=contract, runs=runs, anchors=anchors)


# -- reporting, per market and never pooled -----------------------------------


def market_series(run: DenominatorRun) -> list[dict[str, Any]]:
    """One market's monthly detections-per-session series, holes included.

    Built from the **measured** session headers and their detection counts, which
    is why it is taken off the run rather than off the detections: a month whose
    sessions all detected nothing is a real zero, and a month the store never
    covered is a hole, and only the session spine can tell them apart.
    """
    measured = run.measured
    by_session = Counter(
        {s.session: s.detections for s in measured if s.detections}
    )
    return [
        point.to_dict()
        for point in detections_series([s.session for s in measured], by_session)
    ]


def full_run_report(run: FullRun) -> dict[str, Any]:
    """The whole run as a contract-stamped payload, one block per market.

    Refuses over unsettled anchors: this payload is the machine-readable form of
    every figure the run produced, and it is exactly what a later phase would read
    without ever seeing the anchor report.
    """
    run.require_settled()
    return stamp_result(
        run.contract,
        {
            "markets": list(run.markets),
            "anchors": {
                "settled": True,
                # Named rather than left implicit: #211's rule is that §4b's gap
                # may not be cited without naming the field it was measured
                # over, and this payload is what a later phase reads instead of
                # the anchor table. A settled-ness flag with no universe beside
                # it is exactly the citation the rule forbids.
                "universe": run.anchors.universe,
                "diverged_with_cause": list(run.anchors.explained),
                # Carried onto the payload rather than left in the table: the
                # stateless `in_field` pin was measured by the run it anchors, so
                # it detects drift from here on rather than confirming this run.
                # A later phase reading only this file would otherwise see a
                # settled anchor and no sign that one of them cannot corroborate
                # anything yet.
                "first_measurement": list(run.anchors.first_measurement),
            },
            "per_market": {
                r.market: {
                    "market": r.market,
                    "sessions_persisted": len(r.sessions),
                    "sessions_measured": len(r.measured),
                    "sessions_burn_in": len(r.burn_in),
                    "measured_window": (
                        [
                            r.measured[0].session.isoformat(),
                            r.measured[-1].session.isoformat(),
                        ]
                        if r.measured
                        else None
                    ),
                    "detections": sum(s.detections for s in r.measured),
                    "references_excluded": list(r.references_excluded),
                    "detections_per_session": {
                        s.isoformat(): n
                        for s, n in r.detections_per_session.items()
                    },
                    "months": market_series(r),
                }
                for r in run.runs
            },
        },
    )


def format_full_run(run: FullRun) -> str:
    """The run as text: each market's counts, then each market's plot.

    Every market gets its own block and its own grid, and there is no summary line
    across them. A reader who wants the two compared has to do it deliberately,
    which is the point — the one number that would make it easy is the one findings
    §8 says means nothing.
    """
    run.require_settled()
    lines = [
        "the full run — " + ", ".join(run.markets),
        f"  anchored over the {run.anchors.universe} universe",
    ]
    for market_run in run.runs:
        lines.append("")
        lines.append(format_run(market_run))
        lines.append("")
        lines.append(f"  detections per session — {market_run.market}")
        grid = format_detections_grid(market_series(market_run))
        lines.extend(grid or ["    (no measured sessions)"])
    if isinstance(run.anchors, AnchorReport):
        # Only a live report can be formatted: an outcome read off disk
        # carries the verdict, not the table that produced it.
        lines.append("")
        lines.append(format_anchors(run.anchors))
    return "\n".join(lines)


# -- command-line entry point -------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Replay both markets over the contract's full window and report them apart.

    The command that reproduces the run::

        python -m backtest.full_run --store data/backtest.duckdb \\
            --anchors references/backtest_anchors.json \\
            --out-json references/backtest_full_run.json

    The window is not a command-line argument. It comes from the committed
    contract — ``scope.markets``, ``window.store_start``,
    ``window.measured_start``, ``window.measured_end`` — so "the full run" is
    reproducible from the contract and the store rather than from whoever
    remembered the right dates.

    ``--anchors`` takes the report :mod:`backtest.anchors` wrote. Without it the
    replay still runs and still persists — the work is not the thing being gated —
    but no figure is printed and the command exits non-zero, because a run nobody
    anchored is not an anchored run.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument(
        "--market", action="append", default=None,
        help="narrow the run to one market (repeatable; defaults to the "
             "contract's scope, and may not widen past it)",
    )
    parser.add_argument(
        "--anchors", default=None,
        help="path to the anchor report backtest.anchors wrote; without it no "
             "figure is read",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable, contract-stamped result",
    )
    args = parser.parse_args(argv)

    anchors = read_anchor_report(args.anchors) if args.anchors else None

    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        run = run_full(
            store,
            denominator,
            DEFAULT_CONTRACT,
            markets=args.market,
            anchors=anchors,
            progress=progress_printer(sys.stderr),
        )
    finally:
        denominator.close()
        store.close()

    print(f"\nreplayed and persisted: {', '.join(run.markets)}")
    print(f"wrote {denominator_path(args.store)}")

    try:
        run.require_settled()
    except AnchorsNotSettled as exc:
        print(f"\nno figure was read: {exc}")
        return 1

    print()
    print(format_full_run(run))
    if args.out_json:
        Path(args.out_json).write_text(
            json.dumps(full_run_report(run), indent=1) + "\n"
        )
        print(f"\nwrote {args.out_json}")
    return 0


def read_anchor_report(path: str | Path) -> AnchorOutcome:
    """Read a settled-ness verdict off an anchor report :mod:`backtest.anchors` wrote.

    The anchor table is not rebuilt. The gate asks one question — did every anchor
    match or carry a written cause — and the payload already answers it, so this
    carries the answer and the names of whatever failed and nothing else. A partial
    rebuild of :class:`~backtest.anchors.Anchor` here would be a second definition
    of the table, free to drift from the one that did the checking.

    ``geometry_only`` is honoured rather than inferred from the verdicts: a report
    that checked four of six can have four passing rows and still not be an
    anchored run, which is exactly the case that would otherwise read as a pass.
    """
    body = json.loads(Path(path).read_text())
    checks = [*body.get("geometry", []), *body.get("gate_dependent", [])]
    failed = tuple(
        c.get("anchor", "?")
        for c in checks
        if c.get("verdict") not in SETTLED_VERDICTS
    )
    explained = tuple(
        c.get("anchor", "?")
        for c in checks
        if c.get("verdict") == VERDICT_EXPLAINED
    )
    return AnchorOutcome(
        passes=(
            bool(body.get("passes"))
            and not failed
            and not body.get("geometry_only")
            and bool(checks)
        ),
        failed=failed,
        explained=explained,
        geometry_only=bool(body.get("geometry_only")),
        # Defaults to the app's universe rather than to this run's, so a report
        # written before #211 added the key is refused by the gate instead of
        # being read as though it had anchored the contract's field.
        universe=body.get("universe", UNIVERSE_APP),
        first_measurement=tuple(
            c.get("anchor", "?") for c in checks if c.get("first_measurement")
        ),
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
