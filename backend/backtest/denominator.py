"""The denominator: every session's field, persisted (issue #188, PRD #182 Phase 3).

This is the object the whole exercise exists to produce. The reference study has a
numerator — 828 trades a trader **took** — and no denominator, which is why it can
report no precision and no false-positive rate. These rows are the other half:
every name the universe admitted, every rank, every regime reading and every
detection the detector named, whether anyone traded it or not.

What is persisted, per session
------------------------------
- **Membership** — the contract's stateless universe for that session.
- **The regime, in three columns of deliberately different quality** (see below).
- **The rank table** — every member's percentile and raw return in every lookback.
- **Every detection**, with its full :class:`~screener.detection.Detection` record,
  its seven-dimension star-score breakdown, its star rank, and both registered
  candidate dimensions as values.

Three regime columns, three different warranties
------------------------------------------------
They are stored side by side and must never be read as equals:

- ``regime_state`` is the **conditioning variable**. The app's own regime, off the
  market's own index, unmodified — so a finding here is actionable in the product
  rather than being about a parallel definition that ships nowhere. ``NULL`` below
  :data:`~screener.regime.REGIME_WARMUP`: undefined, not defaulted.
- ``breadth`` is **descriptive only** and carries its survivorship warning in the
  row itself (:data:`BREADTH_BASIS`). It is the measure survivorship bias corrupts
  most directly, and worse here than live, because the names missing from a
  reconstructed past are disproportionately the ones that later died. Condition on
  the state; never on breadth.
- ``broke_out`` is the one regime signal the live app can **never** backfill. The
  app captures follow-through forward nightly precisely because it cannot rebuild
  it from a survivorship-biased past — but the *index series carries no
  survivorship hole*, so this run reconstructs it legitimately across the whole
  window and marks it unbiased (:data:`FOLLOW_THROUGH_BASIS`).

Why a store of its own
----------------------
The denominator lives in its own DuckDB file beside the bar store, the way the
build's coverage ledger lives beside it as JSON (:func:`backtest.coverage_path`).
Two reasons, and the second is the load-bearing one:

- The bar store is the run's **input** and the denominator its **output**. Keeping
  them apart means the expensive, hours-long crawl is never at risk from a rerun of
  the cheap analysis that reads it.
- :meth:`screener.store.Store.append_ranks` **prunes** every rank row outside
  :data:`~screener.store.RANK_RETENTION_YEARS` as the chain advances. That is
  correct for the app, which only ever needs today's table — and fatal for a
  denominator, where a fourteen-year run would finish holding the last two years of
  ranks and nothing else. The rows here are never pruned. This is the same trap the
  reference study hit from the other side (:func:`replay.field._session_detections`).

Every write is idempotent (``ON CONFLICT DO NOTHING``), so a re-run over the same
store reproduces the same rows rather than duplicating or refusing them — which is
what makes the run re-runnable rather than single-use (story 78).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Sequence, TextIO

import duckdb

from replay.caching_store import CachingStore
from replay.chain import SessionField
from replay.field import FieldSession, ScoredDetection, SevenDimScore, build_field_sessions
from screener.detection import Detection
from screener.ranks import Rank
from screener.regime import RegimeState, breadth, index_broke_out, regime_state
from screener.score import Dimension
from screener.source import MARKET_INDEX
from screener.store import Store

from .chain import backtest_chain, excluded_references
from .contract import DEFAULT_CONTRACT, RunContract
from .result import stamp_result

# The warranty each regime companion carries, written into the row rather than
# into a docstring. A column whose quality is recorded only in prose is a column
# that will be read as equal to the one beside it the first time someone queries
# the file directly — which is exactly what the plan warns against for breadth.
BREADTH_BASIS = "descriptive_survivorship_biased"
FOLLOW_THROUGH_BASIS = "reconstructed_unbiased"

# The full detection record's columns, in the dataclass's own order and derived
# from it, so the persisted record cannot silently fall behind the detector. The
# two key fields are held out because they are the row's key, not its payload.
DETECTION_FIELDS: tuple[str, ...] = tuple(
    f.name
    for f in dataclasses.fields(Detection)
    if f.name not in ("symbol", "session")
)

_SCHEMA = """
-- One row per replayed session: the counts, and the three regime columns.
-- ``burn_in`` is the whole of the exclusion rule — a burn-in session is computed
-- and persisted like any other and simply never measured (story 76), so the flag
-- rides on the row rather than on a session list kept somewhere else.
CREATE TABLE IF NOT EXISTS denominator_sessions (
    market                TEXT    NOT NULL,
    session               DATE    NOT NULL,
    burn_in               BOOLEAN NOT NULL,
    members               INTEGER NOT NULL,
    detections            INTEGER NOT NULL,
    -- The conditioning variable. NULL below the regime's warm-up: undefined,
    -- never defaulted to a state the night did not have.
    regime_state          TEXT,
    -- Descriptive only. NULL for an empty universe.
    breadth               DOUBLE,
    breadth_basis         TEXT    NOT NULL,
    -- Reconstructed across the window and unbiased: the index series has no
    -- survivorship hole. NULL until a full trailing window of index bars exists.
    broke_out             BOOLEAN,
    index_close           DOUBLE,
    follow_through_basis  TEXT    NOT NULL,
    PRIMARY KEY (market, session)
);

-- The session's universe membership.
CREATE TABLE IF NOT EXISTS denominator_universe (
    market   TEXT NOT NULL,
    session  DATE NOT NULL,
    symbol   TEXT NOT NULL,
    PRIMARY KEY (market, session, symbol)
);

-- The session's rank table, never pruned — see the module docstring.
CREATE TABLE IF NOT EXISTS denominator_ranks (
    market       TEXT   NOT NULL,
    session      DATE   NOT NULL,
    symbol       TEXT   NOT NULL,
    lookback     TEXT   NOT NULL,
    percentile   DOUBLE NOT NULL,
    raw_return   DOUBLE NOT NULL,
    PRIMARY KEY (market, session, symbol, lookback)
);

-- Every detection, with its full record and its star position.
--
-- ``relative_move`` is a **value, and NULL means absent** — the name had not
-- listed six months ago, or has no ADR — never zero, which is a real value
-- sitting exactly on the pre-registered cut (stories 70, 71). The cut belongs to
-- the rubric and is applied at read time
-- (:func:`screener.relative_strength.relative_move_hit`), so a stored row can
-- never be re-denominated retroactively (story 72). Neither candidate dimension
-- can move a star or a ``star_rank``: both are written from the field, which
-- computes them outside the score.
CREATE TABLE IF NOT EXISTS denominator_detections (
    market             TEXT    NOT NULL,
    session            DATE    NOT NULL,
    symbol             TEXT    NOT NULL,
    star_rank          INTEGER NOT NULL,
    stars              DOUBLE  NOT NULL,
    points             INTEGER NOT NULL,
    max_points         INTEGER NOT NULL,
    score_label        TEXT    NOT NULL,
    rs_line            BOOLEAN NOT NULL,
    relative_move      DOUBLE,
    detector_version   INTEGER NOT NULL,
    trigger            DOUBLE  NOT NULL,
    stop               DOUBLE  NOT NULL,
    stopw_adr          DOUBLE  NOT NULL,
    base_len           INTEGER NOT NULL,
    move_gain          DOUBLE  NOT NULL,
    adr                DOUBLE  NOT NULL,
    close              DOUBLE  NOT NULL,
    cluster_k          INTEGER NOT NULL,
    cluster_high       DOUBLE  NOT NULL,
    cluster_low        DOUBLE  NOT NULL,
    cluster_range_adr  DOUBLE  NOT NULL,
    range_3bar_adr     DOUBLE,
    line_ok            BOOLEAN NOT NULL,
    touch_zones        INTEGER NOT NULL,
    overshoot_adr      DOUBLE  NOT NULL,
    slope              DOUBLE  NOT NULL,
    line_end           DOUBLE  NOT NULL,
    base_low           DOUBLE  NOT NULL,
    churn_l            DOUBLE  NOT NULL,
    sma20_rising       BOOLEAN NOT NULL,
    dryup              DOUBLE  NOT NULL,
    PRIMARY KEY (market, session, symbol)
);

-- The seven-dimension star-score breakdown, one row per dimension per detection,
-- so the field can be re-questioned under a different rubric without a second
-- fourteen-year build (story 69). ``position`` keeps the app's published
-- dimension order, which no alphabetical read-back would recover. ``value`` is
-- the graded quantity where a dimension has one, and NULL on the ungraded ones —
-- the row carries the value, never one rubric's verdict about it (#154).
CREATE TABLE IF NOT EXISTS denominator_score_breakdown (
    market     TEXT    NOT NULL,
    session    DATE    NOT NULL,
    symbol     TEXT    NOT NULL,
    position   INTEGER NOT NULL,
    dimension  TEXT    NOT NULL,
    weight     INTEGER NOT NULL,
    hit        BOOLEAN NOT NULL,
    value      DOUBLE,
    PRIMARY KEY (market, session, symbol, dimension)
);
"""


def denominator_path(store_path: str | Path) -> Path:
    """Where a run persists its denominator: the bar store's path plus a suffix.

    Derived from the store rather than passed separately, for the reason
    :func:`backtest.coverage_path` is: a denominator written beside the wrong bar
    store is a set of rows nothing can be reconciled against.
    """
    out = Path(store_path)
    return out.with_name(out.name + ".denominator.duckdb")


@dataclass(frozen=True)
class SessionRow:
    """One session's persisted header: its counts and its three regime readings.

    ``burn_in`` is the exclusion rule. ``regime_state`` is the conditioning
    variable, ``breadth`` is descriptive, and ``broke_out`` is the reconstructed
    unbiased one; each of the latter two carries the basis it was recorded under
    so the three are never read as equals. See the module docstring.
    """

    market: str
    session: date
    burn_in: bool
    members: int
    detections: int
    regime_state: RegimeState | None
    breadth: float | None
    broke_out: bool | None
    index_close: float | None
    breadth_basis: str = BREADTH_BASIS
    follow_through_basis: str = FOLLOW_THROUGH_BASIS


def session_regime(
    store: Store, market: str, session: date, members: Sequence[str]
) -> tuple[RegimeState | None, float | None, bool | None, float | None]:
    """The session's ``(state, breadth, broke_out, index_close)``.

    All three read off the app's own :mod:`screener.regime` functions, unmodified,
    over bars sliced to ``session`` — the same point-in-time slice every other
    stage takes. The session a denominator row is keyed by is the evaluation
    session: the night a decision is made for the session after it, so bars
    *through* it are exactly what was knowable when the decision was taken.

    A market whose index has no bars in the store yields ``(None, breadth, None,
    None)`` rather than raising: an absent index is a fact about the store's
    coverage, and the run reports it as an undefined regime instead of stopping a
    fourteen-year pass on a missing benchmark.
    """
    index_bars = [
        b for b in store.bars(market, MARKET_INDEX[market]) if b.session <= session
    ]
    members_bars = {
        symbol: [b for b in store.bars(market, symbol) if b.session <= session]
        for symbol in members
    }
    return (
        regime_state(index_bars),
        breadth(members_bars),
        index_broke_out(index_bars),
        index_bars[-1].adj_close if index_bars else None,
    )


class DenominatorStore:
    """The persisted denominator: a thin DuckDB wrapper with idempotent writes.

    Modelled on :class:`screener.store.Store` and deliberately *not* it: the app's
    store carries the app's schema, its write-once session guard and its rank
    retention window, none of which fit rows whose whole purpose is to survive a
    fourteen-year pass and be rewritten identically by the next one.

    Every write is ``ON CONFLICT DO NOTHING``. That is the shape re-runnability
    takes here: a session already persisted is left exactly as it was, so a second
    run over the same store neither duplicates a row nor refuses to proceed — and
    a run that was interrupted resumes without a repair step.
    """

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._con = connection
        self._con.execute(_SCHEMA)

    @classmethod
    def open(cls, path: str | Path) -> "DenominatorStore":
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return cls(duckdb.connect(str(p)))

    @classmethod
    def memory(cls) -> "DenominatorStore":
        """An in-memory denominator, for fixtures and tests."""
        return cls(duckdb.connect(":memory:"))

    def close(self) -> None:
        self._con.close()

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        return self._con.cursor()

    # -- writes ---------------------------------------------------------------

    def append_session(self, row: SessionRow) -> None:
        """Persist one session's header and its three regime readings."""
        self._cursor().execute(
            "INSERT INTO denominator_sessions VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
            [
                row.market, row.session, row.burn_in, row.members, row.detections,
                row.regime_state, row.breadth, row.breadth_basis,
                row.broke_out, row.index_close, row.follow_through_basis,
            ],
        )

    def append_universe(self, market: str, session: date, symbols: Sequence[str]) -> int:
        if not symbols:
            return 0
        self._cursor().executemany(
            "INSERT INTO denominator_universe VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            [[market, session, s] for s in symbols],
        )
        return len(symbols)

    def append_ranks(self, market: str, session: date, rows: Sequence[Rank]) -> int:
        if not rows:
            return 0
        self._cursor().executemany(
            "INSERT INTO denominator_ranks VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [
                [market, session, r.symbol, r.lookback, r.percentile, r.raw_return]
                for r in rows
            ],
        )
        return len(rows)

    def append_detections(
        self, market: str, session: date, rows: Sequence[ScoredDetection]
    ) -> int:
        """Persist a session's field: full record, score, star rank, both candidates.

        The detection's own columns are read off the dataclass by name
        (:data:`DETECTION_FIELDS`), so a field added to
        :class:`~screener.detection.Detection` and not to the schema fails loudly
        here instead of being dropped on the floor.
        """
        if not rows:
            return 0
        placeholders = ", ".join(["?"] * (10 + len(DETECTION_FIELDS)))
        self._cursor().executemany(
            f"INSERT INTO denominator_detections VALUES ({placeholders}) "
            "ON CONFLICT DO NOTHING",
            [
                [
                    market, session, d.symbol, d.star_rank, d.score.stars,
                    d.score.points, d.score.max_points, d.score.label,
                    d.rs_line, d.relative_move,
                ]
                + [getattr(d.detection, name) for name in DETECTION_FIELDS]
                for d in rows
            ],
        )
        self._cursor().executemany(
            "INSERT INTO denominator_score_breakdown VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT DO NOTHING",
            [
                [market, session, d.symbol, i, dim.dimension, dim.weight, dim.hit, dim.value]
                for d in rows
                for i, dim in enumerate(d.score.breakdown)
            ],
        )
        return len(rows)

    # -- reads ----------------------------------------------------------------

    def sessions(self, market: str, *, burn_in: bool | None = None) -> list[SessionRow]:
        """The persisted session headers in order.

        ``burn_in`` filters: ``False`` is the measured denominator, ``True`` the
        settling stretch, ``None`` (the default) everything that was persisted.
        """
        clause = "" if burn_in is None else " AND burn_in = ?"
        params: list[object] = [market] + ([] if burn_in is None else [burn_in])
        rows = self._cursor().execute(
            "SELECT session, burn_in, members, detections, regime_state, breadth, "
            "breadth_basis, broke_out, index_close, follow_through_basis "
            f"FROM denominator_sessions WHERE market = ?{clause} ORDER BY session",
            params,
        ).fetchall()
        return [
            SessionRow(
                market=market, session=r[0], burn_in=r[1], members=r[2],
                detections=r[3], regime_state=r[4], breadth=r[5],
                breadth_basis=r[6], broke_out=r[7], index_close=r[8],
                follow_through_basis=r[9],
            )
            for r in rows
        ]

    def universe(self, market: str, session: date) -> list[str]:
        return [
            r[0]
            for r in self._cursor().execute(
                "SELECT symbol FROM denominator_universe "
                "WHERE market = ? AND session = ? ORDER BY symbol",
                [market, session],
            ).fetchall()
        ]

    def ranks(self, market: str, session: date) -> list[Rank]:
        return [
            Rank(symbol=r[0], lookback=r[1], percentile=r[2], raw_return=r[3])
            for r in self._cursor().execute(
                "SELECT symbol, lookback, percentile, raw_return FROM denominator_ranks "
                "WHERE market = ? AND session = ? ORDER BY lookback, symbol",
                [market, session],
            ).fetchall()
        ]

    def breakdown(self, market: str, session: date, symbol: str) -> list[Dimension]:
        """One detection's star-score breakdown, in the app's published order."""
        return [
            Dimension(dimension=r[0], weight=r[1], hit=r[2], value=r[3])
            for r in self._cursor().execute(
                "SELECT dimension, weight, hit, value FROM denominator_score_breakdown "
                "WHERE market = ? AND session = ? AND symbol = ? ORDER BY position",
                [market, session, symbol],
            ).fetchall()
        ]

    def detections(self, market: str, session: date) -> list[ScoredDetection]:
        """A session's field in star order, reconstructed whole.

        The full detection record, the seven-dimension score with its breakdown,
        the star rank and both candidate dimensions — the row as it was written.
        ``relative_move`` comes back ``None`` where it was absent, which is the
        distinction the column exists to keep (story 71).
        """
        columns = ", ".join(DETECTION_FIELDS)
        rows = self._cursor().execute(
            "SELECT symbol, star_rank, stars, points, max_points, score_label, "
            f"rs_line, relative_move, {columns} FROM denominator_detections "
            "WHERE market = ? AND session = ? ORDER BY star_rank",
            [market, session],
        ).fetchall()
        out: list[ScoredDetection] = []
        for r in rows:
            symbol = r[0]
            detection = Detection(
                symbol=symbol,
                session=session,
                **dict(zip(DETECTION_FIELDS, r[8:])),
            )
            out.append(
                ScoredDetection(
                    symbol=symbol,
                    detection=detection,
                    score=SevenDimScore(
                        stars=r[2], points=r[3], max_points=r[4],
                        breakdown=self.breakdown(market, session, symbol),
                        label=r[5],
                    ),
                    star_rank=r[1],
                    not_taken=False,
                    rs_line=r[6],
                    relative_move=r[7],
                )
            )
        return out


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
        """Detections per measured session — the count the run plots.

        A count that collapses in a given year is a data hole, and it reads as a
        quiet market until someone looks (story 77).
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
    second run over the same pair of stores produces byte-identical rows (story
    78). A gapped session sequence raises :class:`~replay.chain.GapError` rather
    than running (story 75).

    ``progress`` is called as ``progress(i, total, session)`` as the chain
    advances, so a long pass reports rather than hanging silently.
    """
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
    state, share, broke, index_close = session_regime(store, market, sf.session, sf.members)
    row = SessionRow(
        market=market,
        session=sf.session,
        burn_in=sf.burn_in,
        members=len(sf.members),
        detections=len(fs.detections),
        regime_state=state,
        breadth=share,
        broke_out=broke,
        index_close=index_close,
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
            "sessions": [_session_dict(r) for r in run.sessions],
        },
    )


def write_results(run: DenominatorRun, path: str | Path) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run_to_dict(run), indent=2) + "\n")


def format_run(run: DenominatorRun) -> str:
    """A short human-readable summary of what the run persisted."""
    detections = sum(s.detections for s in run.measured)
    measured = run.measured
    lines = [
        f"denominator — {run.market}",
        f"  sessions persisted   {len(run.sessions)} "
        f"({len(measured)} measured, {len(run.burn_in)} burn-in, excluded)",
    ]
    if measured:
        lines.append(f"  window               {measured[0].session} .. {measured[-1].session}")
        lines.append(
            f"  detections           {detections} over {len(measured)} measured sessions "
            f"({detections / len(measured):.1f} per session)"
        )
    lines.append(
        f"  references unranked  {', '.join(run.references_excluded) or 'none in store'}"
    )
    lines.append(f"  breadth              {BREADTH_BASIS}")
    lines.append(f"  follow-through       {FOLLOW_THROUGH_BASIS}")
    return "\n".join(lines)


# -- command-line entry point -------------------------------------------------


def progress_printer(stream: TextIO) -> Callable[[int, int, date], None]:
    """Print the chain's position every :data:`_PROGRESS_EVERY` sessions."""

    def report(i: int, total: int, session: date) -> None:
        if i % _PROGRESS_EVERY and i != total:
            return
        stream.write(f"[chain] {i}/{total} ({i / total:.0%})  {session}\n")
        stream.flush()

    return report


_PROGRESS_EVERY = 20


def main(argv: list[str] | None = None) -> int:
    """Replay one market over a window and persist the denominator.

    The command that reproduces the run::

        python -m backtest.denominator --store data/backtest_us.duckdb \\
            --market US --start 2011-01-01 --measured-start 2012-01-01 \\
            --end 2012-06-30 --out-json references/backtest_denominator_us.json

    The denominator is written beside the bar store
    (:func:`denominator_path`) and the bar store is opened read-write only because
    the chain persists its own reuse markers into it; no live history is touched.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument("--market", required=True)
    parser.add_argument("--start", type=date.fromisoformat, default=None,
                        help="first session of the window (default: the contract's store start)")
    parser.add_argument("--end", type=date.fromisoformat, default=None,
                        help="last session of the window (default: the store's last session)")
    parser.add_argument("--measured-start", type=date.fromisoformat, default=None,
                        help="first measured session; earlier sessions are burn-in "
                             "(default: the contract's measured start)")
    parser.add_argument("--out-json", default=None,
                        help="where to write the machine-readable run summary")
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
