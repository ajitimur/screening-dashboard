"""Sector per name (ticket 03: Yahoo/Morningstar GECS, one request per symbol).

Ticket 03's hazard applies: throttling fails as SILENCE. A missing sector here is recorded as
UNKNOWN and never confused with "this name has no sector".
"""

import os
import time
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
PATH = os.path.join(CACHE, "sectors_us.pkl")

if __name__ == "__main__":
    frames = pd.read_pickle(os.path.join(CACHE, "universe_us.pkl"))
    have = pd.read_pickle(PATH) if os.path.exists(PATH) else {}
    syms = [s for s in frames if s not in have]
    print(f"fetching sector for {len(syms)} of {len(frames)}", flush=True)
    for i, s in enumerate(syms):
        try:
            info = yf.Ticker(s).get_info()
            have[s] = info.get("sector") or "UNKNOWN"
        except Exception:
            have[s] = "UNKNOWN"
        if i % 25 == 0:
            pd.to_pickle(have, PATH)
            print(f"  {i}/{len(syms)}", flush=True)
        time.sleep(1.2)  # ticket 07 measured 1.2s as throttle-free
    pd.to_pickle(have, PATH)
    n_unk = sum(1 for v in have.values() if v == "UNKNOWN")
    print(f"DONE: {len(have)} names, {n_unk} UNKNOWN", flush=True)
