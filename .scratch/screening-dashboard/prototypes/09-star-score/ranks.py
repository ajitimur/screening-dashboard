"""Ticket 06's rank table, prototype-scale: percentile rank of calendar-anchored returns.

06 D: returns are calendar-anchored on adjusted closes; traded-bar windows stay for ADR and
dollar volume only. Universe membership follows ticket 05: median-20d close*volume >= $20M,
>= 20 non-phantom bars.
"""

import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

WINDOWS = {"1m": 21, "3m": 63, "6m": 126, "12m": 252, "1w": 5}


def build(frames, min_dollar_vol=20e6):
    """Returns: dict window -> DataFrame (index=date, columns=symbol) of percentile ranks,
    plus an eligibility mask DataFrame."""
    closes, dvols = {}, {}
    for s, d in frames.items():
        d = d[d["Volume"] > 0]
        if len(d) < 260:
            continue
        idx = pd.to_datetime(d["Date"])
        closes[s] = pd.Series(d["Close"].to_numpy(), index=idx)
        dvols[s] = pd.Series((d["Close"] * d["Volume"]).to_numpy(), index=idx)
    C = pd.DataFrame(closes).sort_index()
    V = pd.DataFrame(dvols).sort_index()

    elig = V.rolling(20).median() >= min_dollar_vol
    elig &= C.notna()

    ranks = {}
    for name, n in WINDOWS.items():
        r = C / C.shift(n) - 1.0
        r = r.where(elig)
        ranks[name] = r.rank(axis=1, pct=True)
    return ranks, elig, C


def load_or_build():
    p = os.path.join(CACHE, "ranks_us.pkl")
    if os.path.exists(p):
        return pd.read_pickle(p)
    frames = pd.read_pickle(os.path.join(CACHE, "universe_us.pkl"))
    out = build(frames)
    pd.to_pickle(out, p)
    return out


def prior_move_pct(ranks, sym, date):
    """D15: top decile in ANY of 1m / 3m / 6m. Returns the best percentile across those three."""
    best = None
    for w in ("1m", "3m", "6m"):
        R = ranks[w]
        if sym not in R.columns:
            continue
        sub = R[sym].loc[:date]
        if len(sub) == 0 or np.isnan(sub.iloc[-1]):
            continue
        v = float(sub.iloc[-1])
        best = v if best is None else max(best, v)
    return best


def sector_share_loo(ranks, sectors, sym, date, window="1m"):
    """Ticket 07: leave-one-out share of the candidate's sector sitting in that window's top decile."""
    sec = sectors.get(sym)
    if not sec or sec == "UNKNOWN":
        return None
    R = ranks[window]
    sub = R.loc[:date]
    if len(sub) == 0:
        return None
    row = sub.iloc[-1].dropna()
    peers = [s for s in row.index if sectors.get(s) == sec and s != sym]
    if len(peers) < 2:
        return None
    return float((row[peers] >= 0.90).mean())
