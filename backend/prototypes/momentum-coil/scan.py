"""PROTOTYPE — throwaway. Nothing imports this. Not part of the pipeline.

Scan every liquid IDX name for coils forming on one session and print the
ranked watchlist — the precision half of the prototype's question. Usage:

    backend/.venv/bin/python backend/prototypes/momentum-coil/scan.py [YYYY-MM-DD]

Defaults to the latest IDX session. Reads data/screener.duckdb read-only.
"""

import sys
from pathlib import Path

import duckdb

import coil

STORE = Path(__file__).resolve().parents[3] / "data" / "screener.duckdb"
HISTORY = 120                 # bars per name; detector needs 61
MIN_VALUE_IDR = 5_000_000_000  # 30-day mean traded value floor (grilling Q7)
VALUE_WINDOW = 30


def main(session=None):
    con = duckdb.connect(str(STORE), read_only=True)
    if session is None:
        session = str(con.execute(
            "select max(session) from bars where market = 'IDX'").fetchone()[0])

    rows = con.execute(
        """
        select symbol, session, open, high, low, close, volume from (
            select *, row_number() over (partition by symbol order by session desc) rn
            from bars where market = 'IDX' and session <= ?
        ) where rn <= ? order by symbol, session
        """,
        [session, HISTORY],
    ).fetchall()

    by_symbol = {}
    for sym, s, o, h, lo, c, v in rows:
        by_symbol.setdefault(sym, []).append((str(s), o, h, lo, c, int(v)))

    hits, scanned = [], 0
    for sym, bars in by_symbol.items():
        if bars[-1][0] != session:          # must have traded this session
            continue
        tail = bars[-VALUE_WINDOW:]
        value = sum(b[4] * b[5] for b in tail) / len(tail)
        if value < MIN_VALUE_IDR:
            continue
        scanned += 1
        k = coil.detect(bars, len(bars) - 1)
        if k is not None:
            hits.append((sym, bars, k, value))

    hits.sort(key=lambda x: x[2].score)     # MA convergence: tighter first
    print(f"{session}: {scanned} liquid IDX names scanned, {len(hits)} coils\n")
    print(f"{'symbol':<10} {'box':>4} {'height':>7} {'vol':>5} {'score':>6}   thrust → box")
    for sym, bars, k, value in hits:
        n = k.end - k.box_start + 1
        print(f"{sym:<10} {n:>3}d {k.height_adr:>6.2f}A {k.vol_ratio:>5.2f} "
              f"{k.score:>6.3f}   {bars[k.thrust_start][0]} → {bars[k.box_start][0]}…")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
