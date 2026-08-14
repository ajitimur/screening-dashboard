"""Build the purpose-built replay store (PRD #114 "Replay store").

A replay is run against a fresh DuckDB file holding only ``bars`` for US over
2019-04 through 2022-12, copied out of the live store. This is not a convenience:

- :meth:`screener.store.Store.append_ranks` prunes every session older than
  ``RANK_RETENTION_YEARS`` relative to the session appended, so writing a 2020
  session into the live store would delete years of history; and
- the write-once session guard (:class:`~screener.store.SessionExistsError`)
  would block re-computing an old session in the live store anyway.

So the study gets its own store. The live store is opened **read-only** and never
written to — the build cannot even hold a writable handle to it, which is what
makes the study structurally incapable of corrupting live history (user story 28).

The window ``2019-04 .. 2022-12`` already includes the 126-session burn-in that
precedes the first measured session (PRD "A2 replay chain"): the burn-in is the
early part of the same copied bar history, not a separate fetch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from screener.bars import Bar
from screener.store import Store

# The replay window: US EOD bars from the start of 2019-04 (burn-in included)
# through the end of 2022-12. The reference set's entries run 2019-10..2022-11,
# so this brackets every executed trade with room for the lookbacks the funnel
# and feature vectors need at the session before entry.
WINDOW_START = date(2019, 4, 1)
WINDOW_END = date(2022, 12, 31)

# The reference set is entirely US breakout trades (PRD "Out of Scope: IDX").
REPLAY_MARKET = "US"


@dataclass(frozen=True)
class ReplayStoreStats:
    """What a build copied across — reported so the store's contents are a fact,
    not an assumption."""

    rows: int
    tickers: int


def build_replay_store(
    live_path: str | Path,
    out_path: str | Path,
    *,
    market: str = REPLAY_MARKET,
    start: date = WINDOW_START,
    end: date = WINDOW_END,
) -> ReplayStoreStats:
    """Copy ``market`` bars in ``[start, end]`` from the live store into a fresh
    store at ``out_path``, returning what was copied.

    The live store is connected **read-only** (``duckdb.connect(read_only=True)``)
    — deliberately not via :class:`~screener.store.Store`, whose ``open`` runs a
    schema migration that writes ``schema_meta``. Reading the rows out through a
    raw read-only cursor is the whole point: a build never mutates live history.

    The output is a real :class:`~screener.store.Store`, so later tickets can
    persist result rows beside the bars against the same append-only discipline;
    only ``bars`` are populated here.
    """
    live = duckdb.connect(str(live_path), read_only=True)
    try:
        rows = live.execute(
            "SELECT symbol, session, open, high, low, close, adj_close, volume "
            "FROM bars WHERE market = ? AND session >= ? AND session <= ? "
            "ORDER BY symbol, session",
            [market, start, end],
        ).fetchall()
    finally:
        live.close()

    # Group by symbol so each append is one symbol's whole in-window series.
    by_symbol: dict[str, list[Bar]] = {}
    for symbol, session, o, h, low, close, adj_close, volume in rows:
        by_symbol.setdefault(symbol, []).append(
            Bar(
                session=session,
                open=o,
                high=h,
                low=low,
                close=close,
                adj_close=adj_close,
                volume=volume,
            )
        )

    replay = Store.open(out_path)
    try:
        written = 0
        for symbol, bars in by_symbol.items():
            written += replay.append_bars(market, symbol, bars)
    finally:
        replay.close()

    return ReplayStoreStats(rows=written, tickers=len(by_symbol))
