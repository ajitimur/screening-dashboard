"""THROWAWAY: reconstruct the US universe + ranks on the snapshot copy.

The live nightly US run had not finished at measurement time, so the snapshot
carries US *bars* but no US universe/ranks rows. This calls the production
``rebuild_universe`` / ``rebuild_ranks`` on the snapshot with the same inputs the
pipeline uses (the two Nasdaq Trader listing files + the stored bars), so the
membership is the one the run would have written.

Run:  .venv/bin/python .scratch/nearmiss/build_us.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import duckdb  # noqa: E402

from screener.pipeline import rebuild_ranks  # noqa: E402
from screener.source import (  # noqa: E402
    NASDAQ_LISTED_URL,
    OTHER_LISTED_URL,
    _http_get,
    parse_us_listings,
)
from screener.store import Store  # noqa: E402
from screener.universe import rebuild_universe  # noqa: E402

SNAPSHOT = ROOT / ".scratch/nearmiss/screener.duckdb"
N_SESSIONS = 3


def main() -> None:
    store = Store(duckdb.connect(str(SNAPSHOT)))
    instruments = parse_us_listings(
        _http_get(NASDAQ_LISTED_URL), _http_get(OTHER_LISTED_URL)
    )
    print(f"enumerated instruments: {len(instruments)}")
    candidates = [i.symbol for i in instruments if i.role == "candidate"]
    print(f"candidates: {len(candidates)}")
    with_bars = {
        s for (s,) in store._con.execute(
            "select distinct symbol from bars where market = 'US'"
        ).fetchall()
    }
    unresolved = {s for s in candidates if s not in with_bars}
    print(f"no stored bars (treated as unresolved): {len(unresolved)}")

    for session in store.sessions("US")[-N_SESSIONS:]:
        store.discard_session("US", session)
        members = rebuild_universe(
            store, "US", session, instruments=instruments, unresolved=unresolved
        )
        rows = rebuild_ranks(store, "US", session)
        print(f"{session}: members={len(members)} rank_rows={len(rows)}")


if __name__ == "__main__":
    main()
