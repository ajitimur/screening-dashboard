"""What the list looks like once D6 stops rejecting.

The trader's call: the 1xADR affordability test is an entry-time judgement, not a screening
criterion. This is a scanner — its job is to surface setups; the stop is decided when the trade
is taken. So D6 becomes a displayed quantity rather than a hard cut.

That changes what has to be measured. Every earlier number here was "share of the ACCEPTED pool
D6 would newly reject", which is meaningless once nothing is rejected. The live question is now
list length: how many names reach the nightly review under each geometry, including the ones
today's gate silently drops.

`fastscan.scan_name` applies the gate inline (`if stop_w > a: continue`), so it cannot answer
this; the scan is repeated here with the gate removed and the stop width recorded instead.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")

import fastscan  # noqa: E402
import envelope as E  # noqa: E402
from compare import clean  # noqa: E402

LMAX = 60


def scan_ungated(df, ends, lmax=LMAX):
    """fastscan.scan_name with D6's rejection removed and both geometries measured."""
    df = df.reset_index(drop=True)
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    close = df["Close"].to_numpy(float)
    n = len(df)
    k = np.arange(n, dtype=float)
    ch = np.concatenate([[0.0], np.cumsum(high)])
    ckh = np.concatenate([[0.0], np.cumsum(k * high)])
    cl = np.concatenate([[0.0], np.cumsum(low)])
    ckl = np.concatenate([[0.0], np.cumsum(k * low)])
    adr = pd.Series(high / low - 1.0).rolling(20).mean().to_numpy()
    Ls_all = np.arange(3, lmax + 1)

    out = []
    for end in ends:
        if end < 80 or end >= n:
            continue
        a = adr[end]
        if np.isnan(a) or a <= 0:
            continue
        Ls = Ls_all[Ls_all <= end + 1]
        sh = fastscan.slopes_for_end(high, ch, ckh, end, Ls)
        sl = fastscan.slopes_for_end(low, cl, ckl, end, Ls)
        wins = Ls[(sh <= 0) & (sl >= 0)]
        if len(wins) == 0:
            continue
        L = int(wins[0])
        s = end - L + 1
        b = E.both(high, low, s, end, float(a), float(close[end]))
        out.append({"end": int(end), "date": pd.to_datetime(df["Date"].iloc[end]),
                    "L": L, "L_longest": int(wins[-1]), "adr": float(a),
                    "close": float(close[end]), **b})
    return out


def run(frames, market, step=3, min_len=400):
    rows = []
    for i, (sym, d) in enumerate(sorted(frames.items())):
        if len(d) < min_len:
            continue
        for r in scan_ungated(d, range(90, len(d), step)):
            r["symbol"] = sym
            r["market"] = market
            rows.append(r)
        if i % 200 == 0:
            print(f"  {market} {i} names, {len(rows)} rows", flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    us = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    idx = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_idx.pkl")).items()}
    df = pd.concat([run(us, "US"), run(idx, "IDX")], ignore_index=True)
    df.to_pickle(os.path.join(CACHE, "nogate.pkl"))

    SCALE = 3.0  # ends are sampled every 3rd bar
    print(f"\n=== ungated detections: {len(df):,}")
    print("\nnightly list length (mean over sweep dates, scaled for 1-in-3 sampling)")
    print(f"{'geometry':30s} {'US gated':>9s} {'US all':>8s} {'IDX gated':>10s} {'IDX all':>8s}")
    for k, lab in (("ols_min", "OLS + min()  (08 as built)"),
                   ("env_min", "envelope + min()"),
                   ("env_max", "q-scanner geometry")):
        cells = []
        for m in ("US", "IDX"):
            s = df[df.market == m]
            g = s[s[f"stopw_{k}"] <= s.adr].groupby("date").size().mean() * SCALE
            allc = s.groupby("date").size().mean() * SCALE
            cells += [g, allc]
        print(f"{lab:30s} {cells[0]:9.1f} {cells[1]:8.1f} {cells[2]:10.1f} {cells[3]:8.1f}")
    print("\n  'gated' = today's hard cut. 'all' = the same detections with D6 shown, not enforced.")
    print("  'all' is identical across geometries by construction: the geometry moves the trigger,")
    print("  and with nothing rejected on trigger-to-stop it no longer changes membership.")

    print("\nstop width in ADR, distribution of the full ungated list (q-scanner geometry)")
    sw = (df.stopw_env_max / df.adr).replace([np.inf, -np.inf], np.nan).dropna()
    print(sw.describe(percentiles=[.25, .5, .75, .9]).round(2).to_string())
    for t in (1.0, 1.25, 1.5, 2.0):
        print(f"  within {t:.2f} ADR: {(sw <= t).mean():.1%}")
