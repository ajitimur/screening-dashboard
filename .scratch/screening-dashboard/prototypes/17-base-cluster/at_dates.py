"""Run the split detector at an arbitrary set of (market, symbol, date) pairs.

split.py sweeps its own 1-in-3 grid, and ticket 09's pool sweeps a different one, so only about a
quarter of the graded cards happen to fall on both. Rather than compare the two scans where their
grids coincide — which would silently sample — this evaluates the split *at the exact bar* of each
card we want an answer for.

Exposes `evaluate(pairs)` and caches to out/at_dates.pkl keyed by the pair set.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P16)
sys.path.insert(0, P09)
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

import split as S  # noqa: E402

_FRAMES = {}


def frames(market):
    if market not in _FRAMES:
        f = "universe_us.pkl" if market == "US" else "universe_idx.pkl"
        _FRAMES[market] = {s: S.clean(d)
                           for s, d in pd.read_pickle(os.path.join(CACHE, f)).items()}
    return _FRAMES[market]


def evaluate(pairs):
    """pairs: DataFrame with market, symbol, date (YYYY-MM-DD). Returns one row per pair."""
    out = []
    for (market, symbol), g in pairs.groupby(["market", "symbol"]):
        d = frames(market).get(symbol)
        if d is None:
            continue
        dates = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d").to_numpy()
        pos = {v: i for i, v in enumerate(dates)}
        ends = [pos[x] for x in g["date"] if x in pos]
        if not ends:
            continue
        for r in S.scan(d, ends):
            r["symbol"], r["market"] = symbol, market
            r["date"] = pd.to_datetime(r["date"]).strftime("%Y-%m-%d")
            out.append(r)
    df = pd.DataFrame(out)
    if len(df):
        for c in ("tight", "caught_up", "line_ok", "has_base"):
            df[c] = df[c].fillna(False).astype(bool)
        df["split_ok"] = df.tight & df.line_ok & df.caught_up
        df["split_floor"] = df.split_ok & (df.move_gain >= S_MOVE_FLOOR)
    return df


S_MOVE_FLOOR = 25.0
