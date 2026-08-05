"""Cached yfinance fetch. Ticket 01/02: throttle, and treat empty results as throttling, not absence."""

import os
import time
import pandas as pd
import yfinance as yf

CACHE = os.path.join(os.path.dirname(__file__), "cache")
os.makedirs(CACHE, exist_ok=True)


def bars(ticker, start="2015-01-01", end=None, retries=3):
    path = os.path.join(CACHE, f"{ticker.replace('.', '_')}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)
    last = None
    for i in range(retries):
        df = yf.download(
            ticker, start=start, end=end, auto_adjust=True, progress=False, threads=False
        )
        if df is not None and len(df) > 0:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.reset_index()
            df.to_pickle(path)
            return df
        last = "empty"
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{ticker}: empty after {retries} tries ({last}) — assume throttled, not absent")
