"""The same 2x2, fitted over the LONGEST valid window instead of the primary one.

compare.py turned up something upstream of this ticket's question: ticket 08's D4 takes the
SHORTEST valid end-anchored window as the primary one, and that window is **3 bars on 52% of
detections** (83.6% are <= 5). Neither fit means much over 3 points, so "envelope or least
squares" is close to moot where the trigger is actually computed — while the longest valid
window has a median of 13 bars, which is a shape you can fit a line to and the shape the trader
was actually looking at on deck A (ticket 09's chart.py drew the longest window).

So the choice of window has to be priced alongside the choice of fit, or this ticket answers a
question that is not the load-bearing one.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")

import envelope as E          # noqa: E402
from compare import clean     # noqa: E402


def run(pool, frames, market):
    out = []
    for i, (sym, g) in enumerate(pool.groupby("symbol")):
        d = frames.get(sym)
        if d is None:
            continue
        high, low = d["High"].to_numpy(float), d["Low"].to_numpy(float)
        for _, r in g.iterrows():
            end, Lm = int(r["end"]), int(r["L_longest"])
            s = end - Lm + 1
            if s < 0 or end >= len(high):
                continue
            b = E.both(high, low, s, end, float(r["adr"]), float(r["close"]))
            out.append({"symbol": sym, "market": market, "end": end, "L": int(r["L"]),
                        "L_longest": Lm, "adr": float(r["adr"]), "close": float(r["close"]),
                        "stars2": r.get("stars2", np.nan), **b})
        if i % 200 == 0:
            print(f"  {market} {i} names, {len(out)} rows", flush=True)
    return pd.DataFrame(out)


if __name__ == "__main__":
    us_pool = pd.read_pickle(os.path.join(CACHE, "pool_us.pkl"))
    us = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    idx_pool = pd.read_pickle(os.path.join(CACHE, "pool_idx.pkl"))
    idx = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_idx.pkl")).items()}
    df = pd.concat([run(us_pool, us, "US"), run(idx_pool, idx, "IDX")], ignore_index=True)
    df.to_pickle(os.path.join(CACHE, "fit_compare_longest.pkl"))

    prim = pd.read_pickle(os.path.join(CACHE, "fit_compare.pkl"))
    a = df.adr * df.close
    print(f"\n=== fitted over the LONGEST valid window ({len(df):,} detections, "
          f"median {df.L_longest.median():.0f} bars vs {prim.L.median():.0f} primary)")
    print(f"{'variant':34s} {'breached':>9s} {'stop ADR':>9s} {'gate fails':>11s}")
    for k in ("ols_min", "env_min", "ols_max", "env_max"):
        print(f"{k:34s} {df[f'breached_{k}'].mean():9.1%} "
              f"{(df[f'stopw_{k}'] / df.adr).mean():9.3f} "
              f"{((df[f'stopw_{k}'] > df.adr).mean()):11.1%}")
    print("\n  gate fails is measured against today's accepted pool, which was gated on the")
    print("  PRIMARY window — over the longest window the base is taller, so the stop is wider.")
    print(f"\n  base height over the longest window: "
          f"{((df.base_high - df.base_low) / a).median():.2f} ADR "
          f"(primary: {((prim.base_high - prim.base_low) / (prim.adr * prim.close)).median():.2f})")
    print(f"  envelope line below the OLS line at the last bar: {(df.env_line < df.ols_line).mean():.1%}")
    print(f"  max() clamp binds: {(df.env_line < df.cluster_high).mean():.1%}")
