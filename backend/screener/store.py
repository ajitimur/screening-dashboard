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
from .detection import Detection
from .labels import Label
from .models import ResolutionFailure, RunRecord, RunStatus
from .ranks import Rank
from .regime import FollowThrough

# Bump when a derived-table definition changes. Detection rows additionally carry
# their own detector_version column (spec §7.2); this is the store-level schema.
# v2 adds the sector/industry label cache (spec §3.3); v3 the breakout
# follow-through capture (spec §4.9); v4 the detections table (spec §4.5); v5
# extends detections with the star score's three derived signals (spec §4.7); v6
# the digest_breaks table — the reported-break record behind the repeat marker (§6);
# v7 the run_failures table — the per-symbol record of why a pull fell short (#91);
# v8 the refusals table — the persisted per-symbol refusal verdict (spec §3.6, #100).
# Recorded in the database on open (``schema_meta``) and reconciled against it by
# :meth:`Store._migrate`, so an older file is upgraded rather than crashed into.
SCHEMA_VERSION = 8

_SCHEMA = """
-- The schema this database has been reconciled to. Written on every open, so
-- SCHEMA_VERSION is a fact about the file on disk rather than a constant that
-- only describes what the code would have created from scratch.
CREATE TABLE IF NOT EXISTS schema_meta (
    version INTEGER NOT NULL
);

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

-- Detections: one dated row per name currently sitting in a valid base (spec
-- §4.5). Keyed (market, session, symbol), append-only like every derived stream.
-- Carries the trigger, the stop and the full signal vector, plus a
-- detector_version so rows written by different detector logic are never
-- silently compared (§7.2). trigger is the cluster high by identity; line_end is
-- the fitted line at today (always <= trigger — the line never sets the trigger).
CREATE TABLE IF NOT EXISTS detections (
    market             TEXT    NOT NULL,
    session            DATE    NOT NULL,
    symbol             TEXT    NOT NULL,
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
    line_ok            BOOLEAN NOT NULL,
    touch_zones        INTEGER NOT NULL,
    overshoot_adr      DOUBLE  NOT NULL,
    slope              DOUBLE  NOT NULL,
    line_end           DOUBLE  NOT NULL,
    base_low           DOUBLE  NOT NULL,
    -- The star score's derived signals (spec §4.7), persisted so a corrected
    -- rubric replays over history; the score itself is derived, never stored.
    churn_l            DOUBLE  NOT NULL,
    sma20_rising       BOOLEAN NOT NULL,
    dryup              DOUBLE  NOT NULL,
    PRIMARY KEY (market, session, symbol)
);

-- Reported breaks: one row per (market, session, symbol) the digest reported that
-- night (spec §6). Append-only and dated like every derived stream — the record
-- behind the repeat marker, so "last reported" reads off the archive rather than
-- re-parsing yesterday's Markdown. The digest file is the human view; this is the
-- machine one. An empty night writes no rows (as a quiet detection night does).
CREATE TABLE IF NOT EXISTS digest_breaks (
    market   TEXT NOT NULL,
    session  DATE NOT NULL,
    symbol   TEXT NOT NULL,
    PRIMARY KEY (market, session, symbol)
);

-- Why a run's pull fell short: one row per enumerated candidate that did **not**
-- come back with bars, carrying the outcome the source stated (issue #91). The
-- run record's two integers say a pull was incomplete; they cannot say whether
-- 548 US names went silent under throttling or the listing file carries
-- instruments the provider serves no history for, and those have opposite fixes.
-- The per-symbol outcomes exist only while the run is in flight, so this is the
-- one place they survive. ``counted`` is whether the symbol sat in the
-- completeness gate's denominator — a refused or instrument-type-excluded
-- listing is recorded but held out of the gate (§3.4 rule 7, issue #90), and
-- that distinction is exactly what makes a quarantine legible. Written for the
-- session the pull was measured against, published or quarantined; a clean pull
-- writes no rows.
CREATE TABLE IF NOT EXISTS run_failures (
    market   TEXT    NOT NULL,
    session  DATE    NOT NULL,
    symbol   TEXT    NOT NULL,
    name     TEXT    NOT NULL,
    -- the source's stated outcome: unresolved | throttled | refused. The first
    -- two are both silence and both count against the gate; "throttled" is the
    -- silence the provider stated with a 429, kept apart because it survived the
    -- tail sweep's rests and so points at pacing rather than the listing (#104).
    status   TEXT    NOT NULL,
    counted  BOOLEAN NOT NULL,  -- did it sit in the completeness gate's denominator?
    PRIMARY KEY (market, session, symbol)
);

-- The persisted per-symbol refusal verdict (spec §3.6, issue #100). A *stated*
-- refusal — the provider naming the periods it will serve instead of answering —
-- fires only on the unbounded ``period="max"`` request, so it is detectable only
-- on a symbol's cold start. The nightly incremental fetch passes ``start=``,
-- which sets ``period`` to ``None`` and cannot draw the refusal: left to re-probe,
-- a refused listing would collapse into ordinary silence and drag the gate again
-- (#47). So the verdict is recorded once, here, keyed (market, symbol) like the
-- label cache — a slow-moving fact about a name, not a per-session observation —
-- and every later night skips the symbol entirely rather than re-probing it.
-- ``as_of`` stamps the session the refusal was first observed. Deliberately NOT a
-- dated derived table: it must survive a session recompute (it is not in
-- ``_DERIVED_TABLES``), because the refusal is a fact about the listing, not the
-- run that noticed it.
CREATE TABLE IF NOT EXISTS refusals (
    market  TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    as_of   DATE NOT NULL,
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


# The enumeration-derived streams one session computes off its own pull — every
# table keyed (market, session), guarded by :meth:`Store._guard_absent`, whose
# contents are a function of *which symbols the run enumerated and resolved*.
# These are exactly the streams a fixed enumeration changes, so a recompute
# (:meth:`supersede_published_session`, issue #111) replaces them.
#
# ``follow_through`` is deliberately *not* here: it is the forward, unbiased
# regime record (spec §4.9), a function of the index alone and not of the
# candidate enumeration, and it stays write-once even under an operator
# recompute (spec §7.2). ``runs`` is not here either — it is the commit point
# over these streams rather than one of them, cleared separately below. ``bars``
# is the ingest substrate, committed per symbol so a killed pull keeps what it
# already fetched (spec §3.3), and a re-pull appends them idempotently.
_ENUMERATION_DERIVED_TABLES = (
    "universe",
    "ranks",
    "detections",
    "digest_breaks",
    "run_failures",
)

# Everything a run writes and :meth:`discard_session` clears for a never-published
# session: the enumeration-derived streams *plus* the forward regime record, which
# a session that never published never captured either.
_DERIVED_TABLES = (*_ENUMERATION_DERIVED_TABLES, "follow_through")


class SchemaDriftError(RuntimeError):
    """An existing database's shape cannot be reconciled with the current one.

    Raised for drift a migration must not paper over — a column that exists
    under the right name but the wrong type. Adding a column is safe; silently
    reinterpreting one is not.
    """


def _declared_columns() -> dict[str, dict[str, str]]:
    """The shape ``_SCHEMA`` describes: ``{table: {column: type}}``.

    Read back out of a throwaway in-memory database rather than parsed out of
    the DDL text, so the declaration and the thing compared against it cannot
    drift apart — there is only one description of the schema in this module.
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


class Store:
    """A thin wrapper over one DuckDB connection with append-only writes."""

    def __init__(self, connection: duckdb.DuckDBPyConnection) -> None:
        self._con = connection
        self._con.execute(_SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        """Bring a database created by older code up to the current schema.

        ``_SCHEMA`` only ever says *create if absent*, so a table that already
        exists keeps the shape it was born with however far the declaration has
        moved on. Nothing noticed: :data:`SCHEMA_VERSION` was never written down
        or read back, so an out-of-date store looked identical to a current one
        until a write hit the narrower table — minutes into a pull, after the
        whole network cost had been paid, and (before the run record is stamped)
        leaving the session half-computed.

        The reconciliation is additive and derived from the declaration itself:
        every column the schema declares and the database lacks is added. A
        column added this way is nullable even where the schema says NOT NULL —
        rows written before it existed have no value for it, and inventing one
        would fabricate a signal that night did not have. A column present under
        the right name but the wrong type is drift no migration should decide
        about silently, so it raises.
        """
        for table, columns in _declared_columns().items():
            actual = {
                name: data_type
                for name, data_type in self._con.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = ?",
                    [table],
                ).fetchall()
            }
            for column, data_type in columns.items():
                if column not in actual:
                    self._con.execute(
                        f"ALTER TABLE {table} ADD COLUMN {column} {data_type}"
                    )
                elif actual[column] != data_type:
                    raise SchemaDriftError(
                        f"{table}.{column} is {actual[column]}, the schema declares "
                        f"{data_type}; this database cannot be migrated in place"
                    )
        self._con.execute("DELETE FROM schema_meta")
        self._con.execute("INSERT INTO schema_meta VALUES (?)", [SCHEMA_VERSION])

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

    def _cursor(self) -> duckdb.DuckDBPyConnection:
        """A fresh cursor over the shared database, for one query.

        A DuckDB Python connection is not safe for concurrent use, but the read
        route handlers are plain ``def`` — Starlette dispatches them to its
        threadpool, so several run at once on different threads. Sharing the one
        ``self._con`` across them intermittently 500s (issue #93). ``cursor()``
        hands each query its own execution context over the *same* underlying
        database, which is the documented multi-thread pattern: reads still run
        in parallel, no global lock serialises them (spec §7.3). Every read and
        write method below goes through here rather than touching ``self._con``.
        """
        return self._con.cursor()

    # -- writes (append-only) ---------------------------------------------

    def discard_session(self, market: str, session: date) -> int:
        """Drop the rows of a session that never published, so it can be redone.

        A run computes a session's derived streams and stamps its run record
        **last**, which makes the run record the commit point — every read keys
        off the last *published* run, so a session without one was never visible
        to anyone. Two kinds of session sit in that state, and both must be
        recomputable or the write-once guard (:meth:`_guard_absent`) turns one
        bad night into a permanent one:

        - **No run record at all** — a run that died mid-session, leaving rows
          belonging to no session: debris, not history (issue #46).
        - **A quarantined run record** — the pull fell below the completeness
          floor, so it wrote no universe, no ranks, nothing anyone read; only
          the run row and its failure rows (issue #103). Its own row is what
          made a same-day retry crash instead of running, so the row goes too.

        Clearing either is not a rewrite of recorded history. A **published**
        session is refused here, so the write-once guarantee (spec §7.2) holds
        over everything a run ever published — the one invariant this method
        exists not to break. The failure rows go with the quarantine that wrote
        them: they explain *that* attempt's shortfall, and outliving their run
        record would leave them read as the retry's account of itself.

        Returns the number of rows discarded, the run record included.
        """
        recorded = self.run(market, session)
        if recorded is not None and recorded.status == "published":
            raise SessionExistsError(
                f"({market}, {session}) carries a published run record; a "
                "published session's rows are never discarded"
            )
        return self._delete_session_rows((*_DERIVED_TABLES, "runs"), market, session)

    def _delete_session_rows(
        self, tables: tuple[str, ...], market: str, session: date
    ) -> int:
        """Delete ``(market, session)`` from each of ``tables``, counting the rows.

        The shared mechanics behind :meth:`discard_session` and
        :meth:`supersede_published_session` — they differ only in *which* tables
        clear (and in the inverse guard each applies first), never in how a
        session's rows are removed. Returns the total rows deleted.
        """
        discarded = 0
        for table in tables:
            deleted = self._cursor().execute(
                f"DELETE FROM {table} WHERE market = ? AND session = ? RETURNING 1",
                [market, session],
            ).fetchall()
            discarded += len(deleted)
        return discarded

    def supersede_published_session(self, market: str, session: date) -> int:
        """Clear a **published** session's enumeration-derived rows so an operator
        can recompute it, keeping the forward regime record (issue #111).

        The deliberate inverse of :meth:`discard_session`, and gated the other
        way: that method refuses a published session to protect write-once; this
        one *requires* one, because it exists only to correct a session built
        from a known-buggy enumeration (e.g. the truncated IDX universe of #110).
        A session that never published is not superseded here — it is not
        recorded history to correct but a hole to fill, and
        :meth:`discard_session` already makes it retriable.

        Only the :data:`_ENUMERATION_DERIVED_TABLES` and the run record go — the
        streams a fixed enumeration changes, plus the commit point over them.
        ``follow_through`` stays: it is the unbiased forward record, a function of
        the index and not the candidate list, so correcting the enumeration must
        not rewrite it (spec §7.2, §4.9). The caller re-pulls and recomputes the
        cleared streams and stamps a fresh published run; the swap is safe only
        because the caller clears *after* a fresh pull has cleared the
        completeness gate, never on a throttled retry that would leave the
        session empty.

        Returns the number of rows discarded, the run record included.
        """
        recorded = self.run(market, session)
        if recorded is None or recorded.status != "published":
            raise SessionExistsError(
                f"({market}, {session}) has no published run record; only a "
                "published session is superseded — an absent or quarantined one "
                "is made retriable by discard_session instead"
            )
        return self._delete_session_rows(
            (*_ENUMERATION_DERIVED_TABLES, "runs"), market, session
        )

    def _guard_absent(self, table: str, market: str, session: date) -> None:
        existing = self._cursor().execute(
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
        self._cursor().execute(
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
        self._cursor().executemany(
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
        inserted = self._cursor().execute(
            f"INSERT INTO bars VALUES {placeholders} ON CONFLICT DO NOTHING RETURNING 1",
            params,
        ).fetchall()
        return len(inserted)

    def replace_bars(self, market: str, symbol: str, bars: list[Bar]) -> int:
        """Delete one symbol's bars and rewrite them — the drift repair (§3.6, #102).

        A deliberate, narrow exception to :meth:`append_bars`' write-once rule
        (spec §7.2). When the incremental overlap shows a symbol's stored history
        sits on a stale adjustment basis — a corporate-action rebasis — those bars
        are *wrong*, not merely stale, and no ``ON CONFLICT DO NOTHING`` append can
        fix a row that already exists. §7.2 exists so a *throttled* run cannot
        silently rewrite good data; a rebasis is the opposite case, so this rewrite
        is scoped as hard as it can be:

        - **One symbol's bars only.** The ``DELETE`` is keyed to ``(market,
          symbol)``, so every other symbol on the exchange calendar is untouched.
        - **Never a derived row.** Ranks, detections, digests and run records are
          left exactly as they were computed on the old basis. §3.5's finding that
          nearly every quantity in the method is a ratio — invariant to a uniform
          rescale — makes recomputing them immaterial, so a repair is bars-only by
          construction (issue #102).

        Returns the number of rows written (the delete's count is not reported: the
        caller wants the new series' size, and a repair always overwrites).
        """
        self._cursor().execute(
            "DELETE FROM bars WHERE market = ? AND symbol = ?", [market, symbol]
        )
        return self.append_bars(market, symbol, bars)

    def append_ranks(self, market: str, session: date, rows: list[Rank]) -> int:
        """Append a session's rank rows, then prune outside the 2-year window.

        Append-only within a session (a written session is never rewritten), but
        the table as a whole discards: rows more than :data:`RANK_RETENTION_YEARS`
        older than ``session`` are dropped for this market (spec §4.3). Pruning
        keys off the session just written, so retention rolls forward with the
        data and needs no wall clock.
        """
        self._guard_absent("ranks", market, session)
        self._cursor().executemany(
            "INSERT INTO ranks VALUES (?, ?, ?, ?, ?, ?)",
            [[market, session, r.symbol, r.lookback, r.percentile, r.raw_return]
             for r in rows],
        )
        cutoff = _years_before(session, RANK_RETENTION_YEARS)
        self._cursor().execute(
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
        self._cursor().execute(
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
        self._cursor().execute(
            "INSERT INTO labels VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (market, symbol) DO UPDATE SET "
            "sector = excluded.sector, industry = excluded.industry, "
            "as_of = excluded.as_of",
            [market, symbol, sector, industry, as_of],
        )

    def append_detections(
        self, market: str, session: date, rows: list[Detection]
    ) -> int:
        """Append a session's detections. Raises on a rewrite; empty is a no-op.

        Written once and never rewritten (spec §7.2). An empty ``rows`` — a quiet
        night where the universe published but nothing sits in a base — writes no
        rows and records nothing, exactly as a night with no members would.
        """
        self._guard_absent("detections", market, session)
        if not rows:
            return 0
        self._cursor().executemany(
            "INSERT INTO detections VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                [market, session, d.symbol, d.detector_version, d.trigger, d.stop,
                 d.stopw_adr, d.base_len, d.move_gain, d.adr, d.close, d.cluster_k,
                 d.cluster_high, d.cluster_low, d.cluster_range_adr, d.line_ok,
                 d.touch_zones, d.overshoot_adr, d.slope, d.line_end, d.base_low,
                 d.churn_l, d.sma20_rising, d.dryup]
                for d in rows
            ],
        )
        return len(rows)

    def append_digest_breaks(
        self, market: str, session: date, symbols: list[str]
    ) -> int:
        """Record a session's reported breaks. Raises on a rewrite; empty is fine.

        Append-only and dated (spec §7.2): the reported-break record is written
        once so the repeat marker reads a stable archive. An empty ``symbols`` — an
        empty night — still marks the session as recorded (via the guard) but
        writes no rows, exactly as a quiet detection night does.
        """
        self._guard_absent("digest_breaks", market, session)
        if not symbols:
            return 0
        self._cursor().executemany(
            "INSERT INTO digest_breaks VALUES (?, ?, ?)",
            [[market, session, s] for s in symbols],
        )
        return len(symbols)

    def append_run_failures(
        self, market: str, session: date, rows: list[ResolutionFailure]
    ) -> int:
        """Record why a session's pull fell short. Raises on a rewrite.

        Dated and append-only like every derived stream (spec §7.2), and written
        for a quarantined session as much as a published one — a quarantine is
        precisely the run that needs explaining (issue #91). A clean pull writes
        no rows; the guard still marks the session as recorded, so an empty
        result reads as "nothing failed" rather than "nothing was kept".
        """
        self._guard_absent("run_failures", market, session)
        if not rows:
            return 0
        self._cursor().executemany(
            "INSERT INTO run_failures VALUES (?, ?, ?, ?, ?, ?)",
            [[market, session, f.symbol, f.name, f.status, f.counted] for f in rows],
        )
        return len(rows)

    def mark_refused(self, market: str, symbol: str, as_of: date) -> None:
        """Persist a symbol's stated refusal verdict (spec §3.6, issue #100).

        Recorded once, off the cold-start fetch that is the only place a refusal
        can surface. Idempotent by construction: a symbol already recorded keeps
        its first ``as_of`` (``ON CONFLICT DO NOTHING``), because it is never
        re-probed and so never re-observed anyway — the guard is defensive, not a
        real second write. Not a dated append: the refusal is a cross-session
        fact about the listing, so it lives outside the write-once derived
        streams and survives a session recompute.
        """
        self._cursor().execute(
            "INSERT INTO refusals VALUES (?, ?, ?) ON CONFLICT DO NOTHING",
            [market, symbol, as_of],
        )

    # -- reads -------------------------------------------------------------

    def refusals(self, market: str) -> set[str]:
        """Every symbol the provider has refused history for (spec §3.6, #100).

        What the nightly pull reads to skip re-probing a refused listing: a
        symbol here is excluded from the fetch and held out of the completeness
        gate, exactly as a freshly-refused one is, computed once instead of every
        run.
        """
        rows = self._cursor().execute(
            "SELECT symbol FROM refusals WHERE market = ?", [market]
        ).fetchall()
        return {r[0] for r in rows}

    def run_failures(self, market: str, session: date) -> list[ResolutionFailure]:
        """A session's non-resolving candidates, ordered by symbol (issue #91)."""
        rows = self._cursor().execute(
            "SELECT symbol, name, status, counted FROM run_failures "
            "WHERE market = ? AND session = ? ORDER BY symbol",
            [market, session],
        ).fetchall()
        return [
            ResolutionFailure(
                market=market, session=session,
                symbol=r[0], name=r[1], status=r[2], counted=r[3],
            )
            for r in rows
        ]

    def rank_sessions(self, market: str) -> list[date]:
        """Every session with rank rows, oldest first — the history the sector
        board differences for its temporal delta (spec §4.4 / ticket 07 S3)."""
        rows = self._cursor().execute(
            "SELECT DISTINCT session FROM ranks WHERE market = ? ORDER BY session",
            [market],
        ).fetchall()
        return [r[0] for r in rows]

    def detections(self, market: str, session: date) -> list[Detection]:
        """A session's detection rows, ordered by symbol."""
        rows = self._cursor().execute(
            "SELECT symbol, detector_version, trigger, stop, stopw_adr, base_len, "
            "move_gain, adr, close, cluster_k, cluster_high, cluster_low, "
            "cluster_range_adr, line_ok, touch_zones, overshoot_adr, slope, "
            "line_end, base_low, churn_l, sma20_rising, dryup FROM detections "
            "WHERE market = ? AND session = ? ORDER BY symbol",
            [market, session],
        ).fetchall()
        return [
            Detection(
                symbol=r[0], session=session, detector_version=r[1], trigger=r[2],
                stop=r[3], stopw_adr=r[4], base_len=r[5], move_gain=r[6], adr=r[7],
                close=r[8], cluster_k=r[9], cluster_high=r[10], cluster_low=r[11],
                cluster_range_adr=r[12], line_ok=r[13], touch_zones=r[14],
                overshoot_adr=r[15], slope=r[16], line_end=r[17], base_low=r[18],
                churn_l=r[19], sma20_rising=r[20], dryup=r[21],
            )
            for r in rows
        ]

    def detections_before(self, market: str, session: date) -> list[Detection]:
        """Yesterday's detections: the rows of the most recent session *strictly
        before* ``session``, or ``[]`` if none. This is what the digest reads as
        the setups whose ``trigger_yesterday`` today's close is tested against —
        the rule's recency requirement made concrete (spec §6)."""
        latest = self._cursor().execute(
            "SELECT max(session) FROM detections WHERE market = ? AND session < ?",
            [market, session],
        ).fetchone()[0]
        if latest is None:
            return []
        return self.detections(market, latest)

    def digest_breaks(self, market: str, session: date) -> list[str]:
        """The symbols the digest reported for ``session``, ordered by symbol — the
        machine record behind the digest file (spec §6). Empty on a quiet night.
        Read by the acceptance pass to count digest rows without re-parsing the
        Markdown or re-running the build (spec §8.2 B5)."""
        rows = self._cursor().execute(
            "SELECT symbol FROM digest_breaks WHERE market = ? AND session = ? "
            "ORDER BY symbol",
            [market, session],
        ).fetchall()
        return [r[0] for r in rows]

    def digest_reports_before(self, market: str, session: date) -> dict[str, date]:
        """Each symbol's most recent reported break *strictly before* ``session``.

        The repeat marker's source (spec §6): a symbol present here was reported on
        the returned date, so tonight's break carries ``↺ last reported <date>``. A
        symbol absent from the map is a first-time break. Today's own session is
        excluded, so the digest never reports itself as a repeat of itself."""
        rows = self._cursor().execute(
            "SELECT symbol, max(session) FROM digest_breaks "
            "WHERE market = ? AND session < ? GROUP BY symbol",
            [market, session],
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def ranks(self, market: str, session: date) -> list[Rank]:
        """A session's rank rows, ordered by symbol then lookback."""
        rows = self._cursor().execute(
            "SELECT symbol, lookback, percentile, raw_return FROM ranks "
            "WHERE market = ? AND session = ? ORDER BY symbol, lookback",
            [market, session],
        ).fetchall()
        return [Rank(*r) for r in rows]

    def ranks_before(self, market: str, session: date) -> list[Rank]:
        """The rank rows of the most recent session *strictly before* ``session``,
        or ``[]`` if none. This is what the boards' ``NEW`` marker diffs against
        as "last session" (spec §4.3 / ticket 06 R10)."""
        latest = self._cursor().execute(
            "SELECT max(session) FROM ranks WHERE market = ? AND session < ?",
            [market, session],
        ).fetchone()[0]
        if latest is None:
            return []
        return self.ranks(market, latest)

    def follow_through(self, market: str) -> list[FollowThrough]:
        """A market's breakout-follow-through rows, oldest session first — the
        forward record read to measure whether a break continued (spec §4.9)."""
        rows = self._cursor().execute(
            "SELECT session, broke_out, index_close FROM follow_through "
            "WHERE market = ? ORDER BY session",
            [market],
        ).fetchall()
        return [FollowThrough(*r) for r in rows]

    def bars(self, market: str, symbol: str) -> list[Bar]:
        """A symbol's stored bars, oldest session first."""
        rows = self._cursor().execute(
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
        return self._cursor().execute(
            "SELECT max(session) FROM bars WHERE market = ? AND symbol = ?",
            [market, symbol],
        ).fetchone()[0]

    def sessions(self, market: str) -> list[date]:
        """The market's observed exchange calendar: the union of bar dates
        across every symbol, oldest first (spec §3.4 rule 4). No holiday table
        is ever consulted — a gap simply has no bars."""
        rows = self._cursor().execute(
            "SELECT DISTINCT session FROM bars WHERE market = ? ORDER BY session",
            [market],
        ).fetchall()
        return [r[0] for r in rows]

    def runs(self, market: str) -> list[RunRecord]:
        """All run records for a market, newest session first."""
        rows = self._cursor().execute(
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

    def last_published_run(self, market: str) -> RunRecord | None:
        """The last run that **published** — the as-of session the tab renders.

        Every read surface keys off this: a quarantined run wrote no universe and
        no ranks, so it is not a session anything can be rendered from.
        """
        for record in self.runs(market):
            if record.status == "published":
                return record
        return None

    def last_run(self, market: str) -> RunRecord | None:
        """The last run of **any** status — what this market has already written.

        The scheduler's question (:func:`screener.schedule.run_is_due`), and a
        different one from :meth:`last_published_run`: a quarantined session is
        not *absent*, the store holds a row for it and the write-once guard
        refuses a second one. So the decision to run is made against the last row
        that exists, and that row's ``status`` decides whether the session is
        retriable (issue #103).
        """
        records = self.runs(market)
        return records[0] if records else None

    def run(self, market: str, session: date) -> RunRecord | None:
        """One session's run record, or ``None`` if it never ran.

        The keyed read behind "has this session already been written, and how did
        it end" — the two callers that ask it (the write-once guard in
        :meth:`discard_session` and the pipeline's refusal to quarantine over a
        published session) would otherwise each scan the market's whole run
        history to answer about one date.
        """
        row = self._cursor().execute(
            "SELECT market, session, status, symbols_enumerated, symbols_resolved, "
            "created_at FROM runs WHERE market = ? AND session = ?",
            [market, session],
        ).fetchone()
        if row is None:
            return None
        return RunRecord(
            market=row[0],
            session=row[1],
            status=row[2],
            symbols_enumerated=row[3],
            symbols_resolved=row[4],
            created_at=row[5],
        )

    def universe(self, market: str, session: date) -> list[str]:
        rows = self._cursor().execute(
            "SELECT symbol FROM universe WHERE market = ? AND session = ? ORDER BY symbol",
            [market, session],
        ).fetchall()
        return [r[0] for r in rows]

    def label(self, market: str, symbol: str) -> Label | None:
        """One symbol's cached label, or ``None`` if never fetched."""
        row = self._cursor().execute(
            "SELECT symbol, sector, industry, as_of FROM labels "
            "WHERE market = ? AND symbol = ?",
            [market, symbol],
        ).fetchone()
        return Label(*row) if row is not None else None

    def labels(self, market: str) -> dict[str, Label]:
        """The whole label cache for a market, keyed by symbol — what the
        rolling-refresh policy reads to find the stalest names (spec §3.3)."""
        rows = self._cursor().execute(
            "SELECT symbol, sector, industry, as_of FROM labels WHERE market = ?",
            [market],
        ).fetchall()
        return {r[0]: Label(*r) for r in rows}

    def universe_before(self, market: str, session: date) -> list[str]:
        """Yesterday's membership: the universe of the most recent session
        *strictly before* ``session``, or ``[]`` if none. This is what the
        hysteresis band and sticky membership read as "yesterday" (spec §4.1)."""
        latest = self._cursor().execute(
            "SELECT max(session) FROM universe WHERE market = ? AND session < ?",
            [market, session],
        ).fetchone()[0]
        if latest is None:
            return []
        return self.universe(market, latest)
