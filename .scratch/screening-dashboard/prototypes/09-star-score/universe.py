"""Reduced point-in-time-ish universe for the prototype.

Honest limits, inherited from tickets 02/05 and documented rather than fixed:
  - survivorship-biased (Nasdaq Trader lists only live names), so historical deciles are optimistic
  - reduced size (~800 US names, not 1,966), so decile boundaries are approximations
Both are acceptable here: this prototype calibrates the SHAPE of the score, not production ranks.
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
CACHE = os.path.join(HERE, "cache")
os.makedirs(CACHE, exist_ok=True)


def nasdaq_symbols():
    out = []
    for f in ["nasdaqlisted.txt", "otherlisted.txt"]:
        r = requests.get(f"https://www.nasdaqtrader.com/dynamic/symdir/{f}", timeout=60)
        df = pd.read_csv(io.StringIO(r.text), sep="|")
        df = df[:-1]  # drop the file-creation footer row
        if "Test Issue" in df:
            df = df[df["Test Issue"] == "N"]
        if "ETF" in df:
            df = df[df["ETF"] != "Y"]
        col = "Symbol" if "Symbol" in df else "ACT Symbol"
        name_col = "Security Name"
        d = df[[col, name_col]].rename(columns={col: "symbol", name_col: "name"})
        out.append(d)
    u = pd.concat(out, ignore_index=True)
    u = u[~u["symbol"].astype(str).str.contains(r"[\$\.]", na=True)]
    # common stock only, per ticket 05
    u = u[u["name"].astype(str).str.contains("Common Stock|Ordinary Shares", na=False)]
    return sorted(u["symbol"].unique().tolist())


def fetch_batch(syms, start, end, batch=40, pause=1.0):
    frames = {}
    for i in range(0, len(syms), batch):
        chunk = syms[i : i + batch]
        try:
            df = yf.download(
                chunk, start=start, end=end, auto_adjust=True,
                progress=False, threads=True, group_by="ticker",
            )
        except Exception as e:
            print(f"  batch {i} error {e}", flush=True)
            time.sleep(5)
            continue
        for s in chunk:
            try:
                d = df[s].dropna(how="all")
            except Exception:
                continue
            if len(d) > 300:
                frames[s] = d.reset_index()
        print(f"  {i+len(chunk)}/{len(syms)} kept={len(frames)}", flush=True)
        time.sleep(pause)
    return frames


if __name__ == "__main__":
    n_target = int(sys.argv[1]) if len(sys.argv) > 1 else 800
    syms = nasdaq_symbols()
    print(f"nasdaq common-stock symbols: {len(syms)}", flush=True)
    rng = np.random.default_rng(7)
    # deterministic sample, plus a core of names that were liquid through the window
    core = ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","AMD","NFLX","CRM","ZM","AR","APPS",
            "ENPH","MRNA","SQ","ROKU","PLUG","FSLR","SEDG","DKNG","PTON","DDOG","NET","CRWD","SNAP",
            "UPST","AFRM","RIVN","COIN","MARA","RIOT","OXY","DVN","FANG","HAL","SLB","XOM","CVX"]
    rest = [s for s in syms if s not in core]
    pick = core + list(rng.choice(rest, size=max(0, n_target - len(core)), replace=False))
    frames = fetch_batch(pick, "2017-01-01", "2023-06-30")
    pd.to_pickle(frames, os.path.join(CACHE, "universe_us.pkl"))
    print(f"DONE: {len(frames)} names cached", flush=True)
