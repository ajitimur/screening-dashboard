import os
import numpy as np
import pandas as pd
import fastscan
import ranks as R

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

if __name__ == "__main__":
    frames = pd.read_pickle(os.path.join(CACHE, "universe_us.pkl"))
    rk, elig, C = R.load_or_build()
    rows = []
    for i, (s, d) in enumerate(frames.items()):
        d = d[d["Volume"] > 0].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
        if len(d) < 400:
            continue
        dates = pd.to_datetime(d["Date"])
        start = int((dates < "2019-01-01").sum())
        ends = list(range(max(start, 90), len(d), 3))
        for r in fastscan.scan_name(d, ends):
            r["symbol"] = s
            rows.append(r)
        if i % 50 == 0:
            print(f"  {i}/{len(frames)} rows={len(rows)}", flush=True)
    df = pd.DataFrame(rows)
    df.to_pickle(os.path.join(CACHE, "sweep_us.pkl"))
    print("DONE rows:", len(df), flush=True)
