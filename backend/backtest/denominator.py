"""The denominator store: every session's field, persisted (issue #188, PRD #182
Phase 3).

These rows are the object the whole exercise exists to produce. The reference
study has a numerator — 828 trades a trader **took** — and no denominator, which
is why it can report no precision and no false-positive rate. This is the other
half: every name the universe admitted, every rank, every regime reading and every
detection the detector named, whether anyone traded it or not.

What is persisted, per session
------------------------------
- **Membership** — the contract's stateless universe for that session.
- **The regime, in three columns of deliberately different quality** (see below).
- **The rank table** — every member's percentile and raw return in every lookback.
- **Every detection**, with its full :class:`~screener.detection.Detection` record,
  its seven-dimension star-score breakdown, its star rank, and both registered
  candidate dimensions as values.

This module owns the *rows*; :mod:`backtest.run` owns the run that produces them.

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

Re-runnable, and it says so rather than assuming it
---------------------------------------------------
Every write is ``ON CONFLICT DO NOTHING``, so a second run over the same store
leaves an already-persisted session exactly as it was rather than duplicating it
or refusing to proceed. On its own that is determinism by suppression: a re-run
under a *different* contract, or after the detector moved, would keep the stale
rows and still report a clean run. So the file carries a stamp
(:meth:`DenominatorStore.stamp`) of the contract and detector version that first
wrote it, and a run that does not match is refused — which is the same rule the
package already commits to for results, that a contract change is a new run
recorded beside the old one rather than a revision mistaken for the original.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Sequence

import duckdb

from replay.field import ScoredDetection, SevenDimScore
from screener.detection import DETECTOR_VERSION, Detection
from screener.ranks import Rank
from screener.regime import RegimeState
from screener.score import Dimension

from .contract import RunContract

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

# The columns a detection row carries before its detection record begins.
_FIELD_COLUMNS: tuple[str, ...] = (
    "market", "session", "symbol", "star_rank", "stars", "points", "max_points",
    "score_label", "rs_line", "relative_move",
)

_SCHEMA = """
-- The stamp of the run that first wrote this file: which contract, and which
-- detector. One row, and a later run that does not match it is refused rather
-- than allowed to leave half its rows measured under a superseded rule.
CREATE TABLE IF NOT EXISTS denominator_meta (
    contract_version  TEXT    NOT NULL,
    contract_label    TEXT    NOT NULL,
    contract_digest   TEXT    NOT NULL,
    detector_version  INTEGER NOT NULL
);

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
-- **Both candidate dimensions are values, and NULL means absent** (stories 70,
-- 71). For ``relative_move`` absent is "the name had not listed six months ago,
-- or has no ADR", never zero — which is a real value sitting exactly on the
-- pre-registered cut. For ``rs_line`` absent is "a price was missing at one of
-- the two anchors, so the question was never asked", which is a different fact
-- from asking it and getting no. Each boolean is derived at read time by the
-- rubric's own reader (:func:`screener.relative_strength.relative_move_hit`,
-- :func:`screener.relative_strength.rs_line_hit`), so a stored row can never be
-- re-denominated retroactively (story 72). Neither can move a star or a
-- ``star_rank``: both are written from the field, which computes them outside
-- the score.
CREATE TABLE IF NOT EXISTS denominator_detections (
    market             TEXT    NOT NULL,
    session            DATE    NOT NULL,
    symbol             TEXT    NOT NULL,
    star_rank          INTEGER NOT NULL,
    stars              DOUBLE  NOT NULL,
    points             INTEGER NOT NULL,
    max_points         INTEGER NOT NULL,
    score_label        TEXT    NOT NULL,
    rs_line            BOOLEAN,
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


def declared_columns() -> dict[str, dict[str, str]]:
    """The shape :data:`_SCHEMA` describes: ``{table: {column: type}}``.

    Read back out of a throwaway in-memory database rather than parsed out of the
    DDL text, so the declaration and anything compared against it cannot drift
    apart — the mechanism :func:`screener.store._declared_columns` established, and
    the reason a test can pin the persisted record against the detector's own
    dataclass without reaching into a store's private cursor.
    """
    con = duckdb.connect(":memory:")
    try:
        con.execute(_SCHEMA)
        rows = con.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns"
        ).fetchall()
    finally:
        con.close()
    shape: dict[str, dict[str, str]] = {}
    for table, column, data_type in rows:
        shape.setdefault(table, {})[column] = data_type
    return shape


def denominator_path(store_path: str | Path) -> Path:
    """Where a run persists its denominator: the bar store's path plus a suffix.

    Derived from the store rather than passed separately, for the reason
    :func:`backtest.coverage_path` is: a denominator written beside the wrong bar
    store is a set of rows nothing can be reconciled against.
    """
    out = Path(store_path)
    return out.with_name(out.name + ".denominator.duckdb")


class RunStampMismatch(RuntimeError):
    """A run's contract or detector differs from the one that wrote these rows.

    Its own error, because the remedy is specific and nothing else here shares it:
    a new contract or a moved detector is a **new run recorded beside the old
    one**, so the answer is a new denominator file, never a second pass over this
    one. Left unguarded, the idempotent writes below would keep every stale row
    and still report a clean run.
    """


@dataclass(frozen=True)
class RegimeReading:
    """One session's whole regime observation — the three columns and their basis.

    The type CONTEXT.md's **regime companions** entry names. They are computed
    together, stored together and must be read apart, so they travel as one value
    rather than as four positional primitives that a caller has to keep in order.
    """

    state: RegimeState | None
    breadth: float | None
    broke_out: bool | None
    index_close: float | None


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

    @staticmethod
    def of(
        market: str,
        session: date,
        *,
        burn_in: bool,
        members: int,
        detections: int,
        regime: RegimeReading,
    ) -> "SessionRow":
        """Assemble a header from a session's counts and its :class:`RegimeReading`."""
        return SessionRow(
            market=market,
            session=session,
            burn_in=burn_in,
            members=members,
            detections=detections,
            regime_state=regime.state,
            breadth=regime.breadth,
            broke_out=regime.broke_out,
            index_close=regime.index_close,
        )


def _insert(table: str, columns: Sequence[str]) -> str:
    """An ``INSERT`` naming every column it fills.

    Named rather than positional, and that is the whole point: the detection row
    is assembled from :data:`DETECTION_FIELDS`, which is derived from the
    dataclass, so *reordering* ``Detection``'s fields would quietly write each
    value into its neighbour's column wherever the types happen to agree — and go
    on doing it for fourteen years. Naming the columns makes a reorder a no-op and
    a rename a loud error.
    """
    names = ", ".join(columns)
    placeholders = ", ".join(["?"] * len(columns))
    return (
        f"INSERT INTO {table} ({names}) VALUES ({placeholders}) "
        "ON CONFLICT DO NOTHING"
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
    a run that was interrupted resumes without a repair step. :meth:`stamp` is what
    keeps that from becoming determinism by suppression.
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

    # -- the run stamp --------------------------------------------------------

    def stamp(self, contract: RunContract) -> None:
        """Record — or re-check — which contract and detector wrote these rows.

        Called before a run writes anything. On an empty file it records the
        stamp; on a file that already carries one it compares, and raises
        :class:`RunStampMismatch` on any difference. The digest is over the
        contract's own serialised bytes, so a cell whose *value* moved is caught
        even when the version string did not.
        """
        digest = hashlib.sha256(contract.to_json().encode()).hexdigest()
        current = (
            contract.contract_version, contract.label, digest, DETECTOR_VERSION,
        )
        rows = self._cursor().execute(
            "SELECT contract_version, contract_label, contract_digest, "
            "detector_version FROM denominator_meta"
        ).fetchall()
        if not rows:
            self._cursor().execute(
                "INSERT INTO denominator_meta VALUES (?, ?, ?, ?)", list(current)
            )
            return
        stored = tuple(rows[0])
        if stored != current:
            raise RunStampMismatch(
                f"this denominator was written under contract "
                f"{stored[0]!r}/{stored[2][:12]} at detector v{stored[3]}, and this "
                f"run is contract {current[0]!r}/{current[2][:12]} at detector "
                f"v{current[3]}: a changed contract or detector is a new run "
                "recorded beside the old one, so build a new denominator rather "
                "than adding to this one"
            )

    # -- writes ---------------------------------------------------------------

    def append_session(self, row: SessionRow) -> None:
        """Persist one session's header and its three regime readings."""
        columns = tuple(f.name for f in dataclasses.fields(SessionRow))
        self._cursor().execute(
            _insert("denominator_sessions", columns),
            [getattr(row, name) for name in columns],
        )

    def append_universe(self, market: str, session: date, symbols: Sequence[str]) -> int:
        if not symbols:
            return 0
        self._cursor().executemany(
            _insert("denominator_universe", ("market", "session", "symbol")),
            [[market, session, s] for s in symbols],
        )
        return len(symbols)

    def append_ranks(self, market: str, session: date, rows: Sequence[Rank]) -> int:
        if not rows:
            return 0
        self._cursor().executemany(
            _insert(
                "denominator_ranks",
                ("market", "session", "symbol", "lookback", "percentile", "raw_return"),
            ),
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
        self._cursor().executemany(
            _insert("denominator_detections", _FIELD_COLUMNS + DETECTION_FIELDS),
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
            _insert(
                "denominator_score_breakdown",
                ("market", "session", "symbol", "position", "dimension", "weight",
                 "hit", "value"),
            ),
            [
                [market, session, d.symbol, i, dim.dimension, dim.weight, dim.hit,
                 dim.value]
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
        Each candidate comes back ``None`` where it was absent, which is the
        distinction the two columns exist to keep (story 71).

        ``not_taken`` and ``taken`` come back ``False``, and that is what was
        written rather than a default standing in for a missing column: the
        backtest takes every detection mechanically and has no executed trades at
        all, so the field it builds carries no entry to be beside. The two flags
        are the reference study's vocabulary (CONTEXT.md, **not-taken detection**),
        and in a mechanical denominator there is no trader for a detection to be
        not-taken *by*.
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
