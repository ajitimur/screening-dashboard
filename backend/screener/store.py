"""The DuckDB store: dated, append-only rows keyed ``(market, session, ...)``.

This is the load-bearing architectural decision of v1 (spec §7.1/§7.2). Every
derived table is written once and never rewritten, so the thing the app reads
*is* the archive and the two cannot disagree. "Tonight" is the max session.

The walking skeleton lays down two tables — ``runs`` (the run record) and one
derived table, ``universe`` — enough to prove the append-only discipline and
both test seams. Later tickets add ranks, sector shares, detections and scores
against the same guard.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb

from .bars import Bar
from .labels import Label
from .models import RunRecord, RunStatus
from .ranks import Rank
from .regime import FollowThrough

# Bump when a derived-table definition changes. Detection rows will additionally
# carry their own detector_version (spec §7.2); this is the store-level schema.
# v2 adds the sector/industry label cache (spec §3.3); v3 the breakout
# follow-through capture (spec §4.9).
SCHEMA_VERSION = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    market              TEXT      NOT NULL,
    session             DATE      NOT NULL,
    status              TEXT      NOT NULL,
    symbols_enumerated  INTEGER   NOT NULL,
    symbols_resolved    INTEGER   NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    PRIMARY KEY (market, session)
);

-- One derived table stood up in the skeleton to exercise the append-only guard.
-- Keyed (market, session, symbol); rewritten never, only appended for absent
-- sessions (spec §7.2).
CREATE TABLE IF NOT EXISTS universe (
    market   TEXT NOT NULL,
    session  DATE NOT NULL,
    symbol   TEXT NOT NULL,
    PRIMARY KEY (market, session, symbol)
);

-- Clean EOD bars, both series (spec §3.5), keyed (market, symbol, session).
-- Appended incrementally as each symbol resolves and never rewritten (§7.2);
-- the observed set of sessions IS the exchange calendar (§3.4 rule 4).
CREATE TABLE IF NOT EXISTS bars (
    market     TEXT   NOT NULL,
    symbol     TEXT   NOT NULL,
    session    DATE   NOT NULL,
    open       DOUBLE NOT NULL,
    high       DOUBLE NOT NULL,
    low        DOUBLE NOT NULL,
    close      DOUBLE NOT NULL,  -- unadjusted, for dollar volume
    adj_close  DOUBLE NOT NULL,  -- adjusted, for everything geometric
    volume     BIGINT NOT NULL,
    PRIMARY KEY (market, symbol, session)
);

-- The rank table: one row per (market, session, symbol, lookback) carrying the
-- name's percentile and raw return — the shared "strong" substrate (spec §4.3).
-- Unlike the other derived tables this one *discards*: a rolling 2-year window
-- is pruned on each append (ticket 06 R5). Still append-only within a session —
-- a written session is never rewritten.
CREATE TABLE IF NOT EXISTS ranks (
    market      TEXT   NOT NULL,
    session     DATE   NOT NULL,
    symbol      TEXT   NOT NULL,
    lookback    TEXT   NOT NULL,
    percentile  DOUBLE NOT NULL,
    raw_return  DOUBLE NOT NULL,
    PRIMARY KEY (market, session, symbol, lookback)
);

-- Breakout follow-through: one row per (market, session) recording whether the
-- market's index closed to a new trailing-window high, and its close (spec §4.9).
-- Append-only and dated like the streams above; captured nightly from the first
-- run as the forward, unbiased regime record, and never displayed or gated.
CREATE TABLE IF NOT EXISTS follow_through (
    market       TEXT    NOT NULL,
    session      DATE    NOT NULL,
    broke_out    BOOLEAN NOT NULL,
    index_close  DOUBLE  NOT NULL,
    PRIMARY KEY (market, session)
);

-- The sector/industry label cache: the one *incremental* derived table (spec
-- §3.3, §7.4). Unlike every append-only dated table above, this is keyed
-- (market, symbol) and updated in place — a label is a slow-moving fact about a
-- name, not a per-session observation. ``as_of`` stamps the run that last
-- fetched it (an as-of-only capture, never backfilled, spec §7.3).
CREATE TABLE IF NOT EXISTS labels (
    market    TEXT NOT NULL,
    symbol    TEXT NOT NULL,
    sector    TEXT NOT NULL,
    industry  TEXT NOT NULL,
    as_of     DATE NOT NULL,
    PRIMARY KEY (market, symbol)
);
"""

# Rank history is kept on a rolling window this many years deep; older sessions
# are pruned as each new one is appended (spec §4.3 / ticket 06 R5). At steady
# state this always covers the 12m lookback twice over, so no feature outruns it.
RANK_RETENTION_YEARS = 2


def _years_before(session: date, years: int) -> date:
    """``session`` shifted back whole ``years``, clamping 29 Feb to 28 Feb so a
    leap-day session yields a valid cutoff."""
    try:
        return session.replace(year=session.year - years)
    except ValueError:  # 29 Feb in a non-leap target year
        return session.replace(year=session.year - years, day=28)


class SessionExistsError(RuntimeError):
    """Raised when a write would rewrite an already-written session's rows.

    Backfill only ever fills *absent* sessions; rewriting a derived row would
    inject look-ahead into the unbiased streams that exist because they are not
    rewritten (spec §7.2).
    """


class Store:
    """A thin wrapper over one DuckDB connection with append-only writes."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._con = connection
        self._con.execute(_SCHEMA)

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def open(cls, path: str | Path) -> "Store":
        """Open (creating on first run) the DuckDB file at ``path``."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        return cls(duckdb.connect(str(p)))

    @classmethod
    def memory(cls) -> "Store":
        """An in-memory store, for fixtures and tests."""
        return cls(duckdb.connect(":memory:"))

    def close(self) -> None:
        self._con.close()

    # -- writes (append-only) ---------------------------------------------

    def _guard_absent(self, table: str, market: str, session: date) -> None:
        existing = self._con.execute(
            f"SELECT 1 FROM {table} WHERE market = ? AND session = ? LIMIT 1",
            [market, session],
        ).fetchone()
        if existing is not None:
            raise SessionExistsError(
                f"{table} already has rows for ({market}, {session}); "
                "derived rows are written once and never rewritten"
            )

    def append_run(
        self,
        market: str,
        session: date,
        *,
        status: RunStatus,
        symbols_enumerated: int,
        symbols_resolved: int,
        created_at: datetime,
    ) -> RunRecord:
        """Record one run. Raises :class:`SessionExistsError` on a rewrite."""
        self._guard_absent("runs", market, session)
        self._con.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?)",
            [market, session, status, symbols_enumerated, symbols_resolved, created_at],
        )
        return RunRecord(
            market=market,
            session=session,
            status=status,
            symbols_enumerated=symbols_enumerated,
            symbols_resolved=symbols_resolved,
            created_at=created_at,
        )

    def append_universe(self, market: str, session: date, symbols: list[str]) -> int:
        """Append a session's universe membership. Raises on a rewrite."""
        self._guard_absent("universe", market, session)
        self._con.executemany(
            "INSERT INTO universe VALUES (?, ?, ?)",
            [[market, session, s] for s in symbols],
        )
        return len(symbols)

    def append_bars(self, market: str, symbol: str, bars: list[Bar]) -> int:
        """Append a symbol's clean bars, committed the moment the call returns.

        Bars are written once and never rewritten (spec §7.2): a session already
        present for this ``(market, symbol)`` is left untouched, so an
        incremental pass that overlaps stored history is a safe no-op rather than
        a rescale. Persisting per symbol is what lets a killed second-market pull
        leave the first market's finished bars intact (spec §3.3).

        Returns the number of rows newly inserted (``RETURNING`` counts exactly
        the rows a conflict did not skip — no extra scan of stored history).
        """
        if not bars:
            return 0
        placeholders = ",".join(["(?, ?, ?, ?, ?, ?, ?, ?, ?)"] * len(bars))
        params: list = []
        for b in bars:
            params.extend(
                (market, symbol, b.session, b.open, b.high, b.low, b.close, b.adj_close, b.volume)
            )
        inserted = self._con.execute(
            f"INSERT INTO bars VALUES {placeholders} ON CONFLICT DO NOTHING RETURNING 1",
            params,
        ).fetchall()
        return len(inserted)

    def append_ranks(self, market: str, session: date, rows: list[Rank]) -> int:
        """Append a session's rank rows, then prune outside the 2-year window.

        Append-only within a session (a written session is never rewritten), but
        the table as a whole discards: rows more than :data:`RANK_RETENTION_YEARS`
        older than ``session`` are dropped for this market (spec §4.3). Pruning
        keys off the session just written, so retention rolls forward with the
        data and needs no wall clock.
        """
        self._guard_absent("ranks", market, session)
        self._con.executemany(
            "INSERT INTO ranks VALUES (?, ?, ?, ?, ?, ?)",
            [[market, session, r.symbol, r.lookback, r.percentile, r.raw_return]
             for r in rows],
        )
        cutoff = _years_before(session, RANK_RETENTION_YEARS)
        self._con.execute(
            "DELETE FROM ranks WHERE market = ? AND session < ?", [market, cutoff]
        )
        return len(rows)

    def append_follow_through(
        self, market: str, session: date, broke_out: bool, index_close: float
    ) -> None:
        """Append one session's breakout-follow-through row (spec §4.9).

        Append-only and dated: a session already captured is never rewritten, so
        the forward record cannot be reshaped after the fact. Raises
        :class:`SessionExistsError` on a rewrite.
        """
        self._guard_absent("follow_through", market, session)
        self._con.execute(
            "INSERT INTO follow_through VALUES (?, ?, ?, ?)",
            [market, session, broke_out, index_close],
        )

    def upsert_label(
        self, market: str, symbol: str, sector: str, industry: str, as_of: date
    ) -> None:
        """Write (or overwrite) one symbol's cached sector/industry.

        This is the *one* in-place write in the store — the label cache is
        incremental (spec §3.3), not an append-only dated table. Only ever
        called with a freshly *resolved* fetch: a failed fetch must never null a
        cached value, so the caller simply does not call this on silence (spec
        §3.3), and the ``as_of`` it stamps drives the rolling refresh.
        """
        self._con.execute(
            "INSERT INTO labels VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (market, symbol) DO UPDATE SET "
            "sector = excluded.sector, industry = excluded.industry, "
            "as_of = excluded.as_of",
            [market, symbol, sector, industry, as_of],
        )

    # -- reads -------------------------------------------------------------

    def rank_sessions(self, market: str) -> list[date]:
        """Every session with rank rows, oldest first — the history the sector
        board differences for its temporal delta (spec §4.4 / ticket 07 S3)."""
        rows = self._con.execute(
            "SELECT DISTINCT session FROM ranks WHERE market = ? ORDER BY session",
            [market],
        ).fetchall()
        return [r[0] for r in rows]

    def ranks(self, market: str, session: date) -> list[Rank]:
        """A session's rank rows, ordered by symbol then lookback."""
        rows = self._con.execute(
            "SELECT symbol, lookback, percentile, raw_return FROM ranks "
            "WHERE market = ? AND session = ? ORDER BY symbol, lookback",
            [market, session],
        ).fetchall()
        return [Rank(*r) for r in rows]

    def ranks_before(self, market: str, session: date) -> list[Rank]:
        """The rank rows of the most recent session *strictly before* ``session``,
        or ``[]`` if none. This is what the boards' ``NEW`` marker diffs against
        as "last session" (spec §4.3 / ticket 06 R10)."""
        latest = self._con.execute(
            "SELECT max(session) FROM ranks WHERE market = ? AND session < ?",
            [market, session],
        ).fetchone()[0]
        if latest is None:
            return []
        return self.ranks(market, latest)

    def follow_through(self, market: str) -> list[FollowThrough]:
        """A market's breakout-follow-through rows, oldest session first — the
        forward record read to measure whether a break continued (spec §4.9)."""
        rows = self._con.execute(
            "SELECT session, broke_out, index_close FROM follow_through "
            "WHERE market = ? ORDER BY session",
            [market],
        ).fetchall()
        return [FollowThrough(*r) for r in rows]

    def bars(self, market: str, symbol: str) -> list[Bar]:
        """A symbol's stored bars, oldest session first."""
        rows = self._con.execute(
            "SELECT session, open, high, low, close, adj_close, volume "
            "FROM bars WHERE market = ? AND symbol = ? ORDER BY session",
            [market, symbol],
        ).fetchall()
        return [Bar(*r) for r in rows]

    def last_session(self, market: str, symbol: str) -> date | None:
        """The symbol's most recent stored session, for incremental appends,
        or ``None`` if it has no bars yet (spec §3.6)."""
        # max() is an aggregate: fetchone() is always a one-tuple, (None,) when
        # the symbol has no bars yet.
        return self._con.execute(
            "SELECT max(session) FROM bars WHERE market = ? AND symbol = ?",
            [market, symbol],
        ).fetchone()[0]

    def sessions(self, market: str) -> list[date]:
        """The market's observed exchange calendar: the union of bar dates
        across every symbol, oldest first (spec §3.4 rule 4). No holiday table
        is ever consulted — a gap simply has no bars."""
        rows = self._con.execute(
            "SELECT DISTINCT session FROM bars WHERE market = ? ORDER BY session",
            [market],
        ).fetchall()
        return [r[0] for r in rows]

    def runs(self, market: str) -> list[RunRecord]:
        """All run records for a market, newest session first."""
        rows = self._con.execute(
            "SELECT market, session, status, symbols_enumerated, symbols_resolved, "
            "created_at FROM runs WHERE market = ? ORDER BY session DESC",
            [market],
        ).fetchall()
        return [
            RunRecord(
                market=r[0],
                session=r[1],
                status=r[2],
                symbols_enumerated=r[3],
                symbols_resolved=r[4],
                created_at=r[5],
            )
            for r in rows
        ]

    def latest_run(self, market: str) -> RunRecord | None:
        """The last *published* run — the as-of session the tab renders."""
        for record in self.runs(market):
            if record.status == "published":
                return record
        return None

    def universe(self, market: str, session: date) -> list[str]:
        rows = self._con.execute(
            "SELECT symbol FROM universe WHERE market = ? AND session = ? ORDER BY symbol",
            [market, session],
        ).fetchall()
        return [r[0] for r in rows]

    def label(self, market: str, symbol: str) -> Label | None:
        """One symbol's cached label, or ``None`` if never fetched."""
        row = self._con.execute(
            "SELECT symbol, sector, industry, as_of FROM labels "
            "WHERE market = ? AND symbol = ?",
            [market, symbol],
        ).fetchone()
        return Label(*row) if row is not None else None

    def labels(self, market: str) -> dict[str, Label]:
        """The whole label cache for a market, keyed by symbol — what the
        rolling-refresh policy reads to find the stalest names (spec §3.3)."""
        rows = self._con.execute(
            "SELECT symbol, sector, industry, as_of FROM labels WHERE market = ?",
            [market],
        ).fetchall()
        return {r[0]: Label(*r) for r in rows}

    def universe_before(self, market: str, session: date) -> list[str]:
        """Yesterday's membership: the universe of the most recent session
        *strictly before* ``session``, or ``[]`` if none. This is what the
        hysteresis band and sticky membership read as "yesterday" (spec §4.1)."""
        latest = self._con.execute(
            "SELECT max(session) FROM universe WHERE market = ? AND session < ?",
            [market, session],
        ).fetchone()[0]
        if latest is None:
            return []
        return self.universe(market, latest)
