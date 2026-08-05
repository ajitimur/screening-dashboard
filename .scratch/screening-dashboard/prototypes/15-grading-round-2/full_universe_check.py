"""The ticket's own caution, executed: do the thresholds survive the REAL universe?

Ticket 09's numbers all come off a reduced 650-name US sample. Ticket 05 measured the real universe
at 1,966 US / 288 IDX names. Two of the eight dimensions are cross-sectional and therefore move with
the denominator:

  prior_move  — D15's top-decile gate, off ticket 06's rank table
  sector      — ticket 07's leave-one-out sector share, also computed off decile membership

Nothing else does: every other scored quantity is a within-name ratio (ticket 08's D-series, and
ticket 05's finding that ratios survive adjustment), so scale cannot touch them. This script rebuilds
the rank table over the full universe and reports how far the two cross-sectional dimensions move on
exactly the cards that were graded.

Stage 1 (`--fetch`) pulls close+volume for every US common-stock symbol, throttled per ticket 02
(12 req/s measured as the safe rate; 1.2s between batches here, which is well inside it). Yahoo
FAILS AS SILENCE — the map's standing data-layer finding — so the fetch reports its resolution rate
and refuses to build a rank table below 99%.
"""

import io
import os
import sys
import time
import numpy as np
import pandas as pd
import requests
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")
FULL = os.path.join(CACHE, "full_us.pkl")

START, END = "2018-01-01", "2023-06-30"
MIN_DOLLAR_VOL = 20e6


def symbols():
    out = []
    for f in ["nasdaqlisted.txt", "otherlisted.txt"]:
        r = requests.get(f"https://www.nasdaqtrader.com/dynamic/symdir/{f}", timeout=60)
        df = pd.read_csv(io.StringIO(r.text), sep="|")[:-1]
        if "Test Issue" in df:
            df = df[df["Test Issue"] == "N"]
        if "ETF" in df:
            df = df[df["ETF"] != "Y"]
        col = "Symbol" if "Symbol" in df else "ACT Symbol"
        out.append(df[[col, "Security Name"]].rename(columns={col: "symbol", "Security Name": "name"}))
    u = pd.concat(out, ignore_index=True)
    u = u[~u["symbol"].astype(str).str.contains(r"[\$\.]", na=True)]
    u = u[u["name"].astype(str).str.contains("Common Stock|Ordinary Shares", na=False)]
    return sorted(u["symbol"].unique().tolist())


def fetch(batch=25, pause=1.2):
    syms = symbols()
    print(f"common-stock symbols: {len(syms)}", flush=True)
    have = pd.read_pickle(FULL) if os.path.exists(FULL) else {}
    todo = [s for s in syms if s not in have]
    print(f"to fetch: {len(todo)}", flush=True)
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        try:
            df = yf.download(chunk, start=START, end=END, auto_adjust=True, progress=False,
                             threads=True, group_by="ticker")
        except Exception as e:
            print(f"  batch {i} error {e}", flush=True)
            time.sleep(5)
            continue
        for s in chunk:
            try:
                d = df[s].dropna(how="all")
            except Exception:
                continue
            if len(d) > 250:
                have[s] = d[["Close", "Volume"]].reset_index()
        if i % (batch * 20) == 0:
            pd.to_pickle(have, FULL)
        print(f"  {i+len(chunk)}/{len(todo)} resolved={len(have)}", flush=True)
        time.sleep(pause)
    pd.to_pickle(have, FULL)
    rate = len(have) / len(syms)
    print(f"DONE: {len(have)}/{len(syms)} resolved ({rate:.2%})", flush=True)
    if rate < 0.90:
        print("!! resolution below 90% — Yahoo is failing as silence; rerun before trusting ranks")


def ranks_full():
    have = pd.read_pickle(FULL)
    closes, dvols = {}, {}
    for s, d in have.items():
        d = d[d["Volume"] > 0]
        if len(d) < 260:
            continue
        idx = pd.to_datetime(d["Date"])
        closes[s] = pd.Series(d["Close"].to_numpy(), index=idx)
        dvols[s] = pd.Series((d["Close"] * d["Volume"]).to_numpy(), index=idx)
    C = pd.DataFrame(closes).sort_index()
    V = pd.DataFrame(dvols).sort_index()
    elig = (V.rolling(20).median() >= MIN_DOLLAR_VOL) & C.notna()
    print(f"universe size (median eligible names per date): {int(elig.sum(axis=1).median())}")
    ranks = {}
    for name, n in {"1m": 21, "3m": 63, "6m": 126}.items():
        r = (C / C.shift(n) - 1.0).where(elig)
        ranks[name] = r.rank(axis=1, pct=True)
    return ranks, elig


def compare():
    import ranks as R
    rk_small, _, _ = R.load_or_build()
    rk_big, elig = ranks_full()
    sectors = pd.read_pickle(os.path.join(CACHE, "sectors_us.pkl"))
    picks = pd.read_pickle(os.path.join(CACHE, "picks_r2.pkl"))

    rows = []
    for p in picks:
        if p["market"] != "US":
            continue
        r = p["row"]
        sym, date = p["symbol"], r["date"]
        small = R.prior_move_pct(rk_small, sym, date)
        big = None
        for w in ("1m", "3m", "6m"):
            Rw = rk_big[w]
            if sym not in Rw.columns:
                continue
            sub = Rw[sym].loc[:date]
            if len(sub) and not np.isnan(sub.iloc[-1]):
                v = float(sub.iloc[-1])
                big = v if big is None else max(big, v)
        ss_small = R.sector_share_loo(rk_small, sectors, sym, date)
        ss_big = R.sector_share_loo(rk_big, sectors, sym, date)
        rows.append({"deck": p["deck"], "symbol": sym, "date": date,
                     "pm_small": small, "pm_big": big,
                     "ss_small": ss_small, "ss_big": ss_big})
    df = pd.DataFrame(rows)
    df["gate_small"] = df.pm_small >= 0.90
    df["gate_big"] = df.pm_big >= 0.90
    df["sec_small"] = df.ss_small >= 0.10
    df["sec_big"] = df.ss_big >= 0.10
    df.to_pickle(os.path.join(CACHE, "universe_compare.pkl"))

    print("\n=== how far do the two cross-sectional dimensions move on the graded cards? ===")
    n = len(df)
    print(f"cards checked: {n}")
    print(f"prior-move percentile: mean {df.pm_small.mean():.3f} (650-name) vs {df.pm_big.mean():.3f} (full)")
    flip = (df.gate_small != df.gate_big)
    print(f"  D15 decile gate flips on {flip.sum()} of {n} cards ({100*flip.mean():.1f}%)"
          f" — {int((df.gate_small & ~df.gate_big).sum())} lose the gate, "
          f"{int((~df.gate_small & df.gate_big).sum())} gain it")
    sub = df.dropna(subset=["ss_small", "ss_big"])
    if len(sub):
        print(f"sector leave-one-out share: mean {sub.ss_small.mean():.3f} vs {sub.ss_big.mean():.3f}")
        f2 = (sub.sec_small != sub.sec_big)
        print(f"  sector boolean flips on {f2.sum()} of {len(sub)} cards ({100*f2.mean():.1f}%)")
    print("\nA flip is worth half a star on the sector dimension and a full gate exclusion on the")
    print("prior-move one, so this is the size of the correction the reduced universe was hiding.")


if __name__ == "__main__":
    if "--fetch" in sys.argv:
        fetch()
    else:
        compare()
