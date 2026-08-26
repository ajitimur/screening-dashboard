"""The run that produces the denominator (issue #188, PRD #182 Phase 3).

One entry point — :func:`run_denominator` — takes a bar store, a denominator store
and a run contract, replays one market over a window, and leaves the rows on disk.
Below it sit the contract's stateless universe, the replay chain, the field and the
per-session regime read; above it sit a result value, a human-readable formatter, a
machine-readable serialiser and a CLI, in the shape :mod:`replay.study` already
established for the reference study.

The module is separate from :mod:`backtest.denominator` for the reason the package
is already split into ``contract`` / ``universe`` / ``store`` / ``result``: the
denominator is the *rows*, and this is the *run*. They change for different
reasons — a schema change and a window change have nothing to do with each other —
and keeping the store out of the CLI's module is what lets the store be imported by
a later phase that has no interest in running anything.

Two refusals guard the run, and both exist because the failure they prevent is
silent rather than loud:

- **The gate width is checked against the contract** before anything is computed
  (:func:`check_detection_gate`). The run measures the detector *as encoded*, and
  the contract records what that was; if the live
  :data:`~screener.detection.DETECTION_LOOKBACKS` has moved since, the denominator
  would be built against a width its own contract does not describe.
- **The denominator is stamped** with the contract and detector that wrote it
  (:meth:`~backtest.denominator.DenominatorStore.stamp`), so a re-run under a
  different contract is refused rather than quietly adding fresh rows beside stale
  ones that the idempotent writes would preserve.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

from replay.caching_store import CachingStore
from replay.chain import SessionField
from replay.field import FieldSession, build_field_sessions
from screener.bars import Bar
from screener.detection import DETECTION_LOOKBACKS
from screener.regime import REGIME_WARMUP, breadth, index_broke_out, regime_state
from screener.source import MARKET_INDEX
from screener.store import Store

from .chain import backtest_chain, excluded_references, trailing_bars
from .contract import DETECTION_GATE_KEY, DEFAULT_CONTRACT, RunContract
from .denominator import (
    BREADTH_BASIS,
    FOLLOW_THROUGH_BASIS,
    DenominatorStore,
    RegimeReading,
    SessionRow,
    denominator_path,
)
from .result import stamp_result

# How many trailing bars the regime's three readings can see, and therefore all
# any of them needs. :func:`screener.regime._snapshot` refuses below
# :data:`~screener.regime.REGIME_WARMUP` bars and reads no deeper than that —
# the constant *is* ``SMA_SLOW + SLOPE_LOOKBACK``, which is exactly the deepest
# read it makes — and :func:`~screener.regime.index_broke_out` reads a shorter
# window still. So a trailing slice of this length gives every one of them the
# identical answer a whole fourteen-year series would, at a bounded cost.
#
# This matters because the alternative is what the first cut of this module did:
# re-slice every member's entire history once per session, which is
# O(sessions x members x bars) and does not finish the pass this package exists
# to run. A seam test pins the two against each other on a real series.
REGIME_TAIL = REGIME_WARMUP


class ContractDrift(RuntimeError):
    """The live code no longer matches the contract the run is being made under.

    Its own error because the remedy is never "carry on": the plan's freeze says
    the next change to the detector restarts the dependency list, so a run whose
    gate width has moved out from under its contract is stale on arrival, and the
    answer is a new contract recorded beside the old one.
    """


def check_detection_gate(contract: RunContract) -> None:
    """Refuse a run whose contract's gate width is not the detector's.

    The denominator is built against the four-lookback width ADR 0003's amendment
    settled — ``1m``/``3m``/``6m``/``12m``, detector v3 — and the field gates on
    the live :data:`~screener.detection.DETECTION_LOOKBACKS`. Those two agreeing is
    an acceptance criterion, and left unchecked it is only ever a coincidence that
    a test noticed once: the run would go on building a denominator under whatever
    width the detector happened to carry that week, and stamp the contract's claim
    onto the result.
    """
    declared = tuple(contract.value(DETECTION_GATE_KEY))
    if declared != DETECTION_LOOKBACKS:
        raise ContractDrift(
            f"the contract's detection gate is {declared} and the detector's is "
            f"{DETECTION_LOOKBACKS}: the denominator would be built against a "
            "width its own contract does not describe"
        )


def session_regime(
    store: Store, market: str, session: date, members: Sequence[str]
) -> RegimeReading:
    """The session's regime state, breadth and follow-through.

    All three read off the app's own :mod:`screener.regime` functions, unmodified,
    over bars that end at ``session`` — the same point-in-time cut every other
    stage takes. The session a denominator row is keyed by is the evaluation
    session: the night a decision is made for the session after it, so bars
    *through* it are exactly what was knowable when the decision was taken.

    Only the trailing :data:`REGIME_TAIL` bars are handed to each function, which
    changes no answer and is what makes the pass finish — see the constant.

    A market whose index has no bars in the store yields a reading with no state
    and no follow-through rather than raising: an absent index is a fact about the
    store's coverage, and the run reports it as an undefined regime instead of
    stopping a fourteen-year pass on a missing benchmark.
    """
    index_bars = trailing_bars(
        store.bars(market, MARKET_INDEX[market]), session, REGIME_TAIL
    )
    members_bars = {
        symbol: trailing_bars(store.bars(market, symbol), session, REGIME_TAIL)
        for symbol in members
    }
    return RegimeReading(
        state=regime_state(index_bars),
        breadth=breadth(members_bars),
        broke_out=index_broke_out(index_bars),
        index_close=index_bars[-1].adj_close if index_bars else None,
    )


@dataclass(frozen=True)
class DenominatorRun:
    """What one replay of the denominator produced, as a committable value.

    ``sessions`` is every persisted session's header, burn-in included and
    flagged; ``measured`` and ``burn_in`` split it the way every later phase must.
    ``references_excluded`` names the benchmarks the store held and the field
    refused to rank, so the #162 exclusion is a reported fact about *this* run and
    not only a property of the code that ran it (story 73).
    """

    market: str
    contract: RunContract
    sessions: tuple[SessionRow, ...]
    references_excluded: tuple[str, ...]

    @property
    def measured(self) -> tuple[SessionRow, ...]:
        """The measured sessions — the denominator proper."""
        return tuple(s for s in self.sessions if not s.burn_in)

    @property
    def burn_in(self) -> tuple[SessionRow, ...]:
        """The settling sessions: persisted, and never measured (story 76)."""
        return tuple(s for s in self.sessions if s.burn_in)

    @property
    def detections_per_session(self) -> dict[date, int]:
        """Detections per measured session — the series the window is read across.

        A count that collapses in a given year is a data hole, and it reads as a
        quiet market until someone looks (story 77). It is reported as a series so
        a reader never has to re-derive it from the rows to see that.
        """
        return {s.session: s.detections for s in self.measured}


def run_denominator(
    store: Store,
    denominator: DenominatorStore,
    market: str,
    contract: RunContract = DEFAULT_CONTRACT,
    *,
    start: date | None = None,
    end: date | None = None,
    measured_start: date | None = None,
    sessions: Sequence[date] | None = None,
    progress: Callable[[int, int, date], None] | None = None,
) -> DenominatorRun:
    """Replay one market over a window and persist the denominator.

    The single entry point for Phase 3: the contract's stateless universe, then
    the chain, then the field, then rows on disk. Every session in the window is
    computed and persisted; the burn-in ones are flagged and excluded from
    measurement rather than skipped (story 76).

    The run is deterministic and re-runnable over the same bar store. The chain
    reuses a session it has already computed rather than recomputing it, the field
    reuses persisted detections, and every denominator write is idempotent — so a
    second run over the same pair of stores produces identical rows (story 78),
    while a run under a *different* contract or detector is refused outright
    rather than left to mix its rows with the old ones.

    A gapped session sequence raises :class:`~replay.chain.GapError`, and a window
    the store cannot reach across raises
    :class:`~backtest.chain.WindowNotCovered` — both before anything is computed
    (story 75).

    ``progress`` is called as ``progress(i, total, session)`` as the chain
    advances, so a long pass reports rather than hanging silently.
    """
    check_detection_gate(contract)
    denominator.stamp(contract)
    store = CachingStore.wrap(store)
    chain = backtest_chain(
        store,
        market,
        contract,
        start=start,
        end=end,
        measured_start=measured_start,
        sessions=sessions,
        progress=progress,
    )
    fields = build_field_sessions(store, market, chain)
    rows = tuple(
        _persist_session(store, denominator, market, sf, fs)
        for sf, fs in zip(chain, fields)
    )
    return DenominatorRun(
        market=market,
        contract=contract,
        sessions=rows,
        references_excluded=tuple(excluded_references(store, market)),
    )


def _persist_session(
    store: Store,
    denominator: DenominatorStore,
    market: str,
    sf: SessionField,
    fs: FieldSession,
) -> SessionRow:
    """Write one session's whole denominator and return its header row."""
    row = SessionRow.of(
        market,
        sf.session,
        burn_in=sf.burn_in,
        members=len(sf.members),
        detections=len(fs.detections),
        regime=session_regime(store, market, sf.session, sf.members),
    )
    denominator.append_session(row)
    denominator.append_universe(market, sf.session, sf.members)
    denominator.append_ranks(market, sf.session, sf.ranks)
    denominator.append_detections(market, sf.session, fs.detections)
    return row


# -- serialisation ------------------------------------------------------------


def _session_dict(row: SessionRow) -> dict:
    return {
        "session": row.session.isoformat(),
        "burn_in": row.burn_in,
        "members": row.members,
        "detections": row.detections,
        "regime_state": row.regime_state,
        "breadth": row.breadth,
        "breadth_basis": row.breadth_basis,
        "broke_out": row.broke_out,
        "index_close": row.index_close,
        "follow_through_basis": row.follow_through_basis,
    }


def run_to_dict(run: DenominatorRun) -> dict:
    """The run as a JSON-serialisable dict, stamped with the contract that produced it.

    Every result the package emits carries its contract (:func:`backtest.stamp_result`),
    so two runs under different contracts are distinguishable from their serialised
    output alone.
    """
    return stamp_result(
        run.contract,
        {
            "market": run.market,
            "sessions_persisted": len(run.sessions),
            "sessions_measured": len(run.measured),
            "sessions_burn_in": len(run.burn_in),
            "references_excluded": list(run.references_excluded),
            "detections_per_session": {
                s.isoformat(): n for s, n in run.detections_per_session.items()
            },
            "sessions": [_session_dict(r) for r in run.sessions],
        },
    )


def write_results(run: DenominatorRun, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run_to_dict(run), indent=2) + "\n")


def format_run(run: DenominatorRun) -> str:
    """A short human-readable summary of what the run persisted."""
    measured = run.measured
    detections = sum(s.detections for s in measured)
    lines = [
        f"denominator — {run.market}",
        f"  sessions persisted   {len(run.sessions)} "
        f"({len(measured)} measured, {len(run.burn_in)} burn-in, excluded)",
    ]
    if measured:
        lines.append(
            f"  window               {measured[0].session} .. {measured[-1].session}"
        )
        lines.append(
            f"  detections           {detections} over {len(measured)} measured "
            f"sessions ({detections / len(measured):.1f} per session)"
        )
    lines.append(
        f"  references unranked  {', '.join(run.references_excluded) or 'none in store'}"
    )
    lines.append(f"  breadth              {BREADTH_BASIS}")
    lines.append(f"  follow-through       {FOLLOW_THROUGH_BASIS}")
    return "\n".join(lines)


# -- command-line entry point -------------------------------------------------

# How often the chain's position is printed. Frequent enough that a stalled pass
# is distinguishable from a slow one, rare enough that a fourteen-year run does
# not print a line per session.
PROGRESS_EVERY = 20


def progress_printer(stream: TextIO) -> Callable[[int, int, date], None]:
    """Print the chain's position every :data:`PROGRESS_EVERY` sessions."""

    def report(i: int, total: int, session: date) -> None:
        if i % PROGRESS_EVERY and i != total:
            return
        stream.write(f"[chain] {i}/{total} ({i / total:.0%})  {session}\n")
        stream.flush()

    return report


def main(argv: list[str] | None = None) -> int:
    """Replay one market over a window and persist the denominator.

    The command that reproduces the run::

        python -m backtest.run --store data/backtest_us.duckdb \\
            --market US --start 2011-01-01 --measured-start 2012-01-01 \\
            --end 2012-06-30 --out-json references/backtest_denominator_us.json

    The denominator is written beside the bar store
    (:func:`~backtest.denominator.denominator_path`). The bar store is opened
    read-write only because the chain persists its own reuse markers into it; no
    live history is touched — the backtest fetches into a purpose-built file and
    :func:`backtest.store.refuse_live_store` refuses any other.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument("--market", required=True)
    parser.add_argument(
        "--start", type=date.fromisoformat, default=None,
        help="first session of the window (default: the contract's store start)",
    )
    parser.add_argument(
        "--end", type=date.fromisoformat, default=None,
        help="last session of the window (default: the store's last session)",
    )
    parser.add_argument(
        "--measured-start", type=date.fromisoformat, default=None,
        help="first measured session; earlier sessions are burn-in "
             "(default: the contract's measured start)",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable run summary",
    )
    args = parser.parse_args(argv)

    store = Store.open(args.store)
    denominator = DenominatorStore.open(denominator_path(args.store))
    try:
        run = run_denominator(
            store,
            denominator,
            args.market,
            start=args.start,
            end=args.end,
            measured_start=args.measured_start,
            progress=progress_printer(sys.stderr),
        )
    finally:
        denominator.close()
        store.close()

    if args.out_json:
        write_results(run, args.out_json)
    print(format_run(run))
    print(f"\nwrote {denominator_path(args.store)}")
    if args.out_json:
        print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
