"""Build the round-2 candidate pool: every detection, scored under the round-2 rubric, plus the
REJECTS the detector threw away.

The rejects matter because ticket 11 handed ticket 15 an obligation ticket 09 did not discharge:
there is no rejected-candidates view in v1, so the discarded set has to be inspected here or
nowhere. `scan_name` drops a bar-date silently in two distinct ways, and they are different
questions, so they are recorded separately:

  no_window      — no end-anchored window passes the triangle test (highs slope <= 0, lows >= 0)
  stop_too_wide  — a valid base exists but trigger-to-base-low exceeds 1 x ADR (08's D6 rejection)

Outputs (into the ticket-09 prototype's cache, which is where the bars already live):
  pool_us.pkl     one row per US detection, round-2 signals attached
  pool_idx.pkl    same for the IDX slice, plus collapsed-bar share inside the base
  rejects_us.pkl  one row per sampled rejection, with its reason
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")

import fastscan                     # noqa: E402
import ranks as R                   # noqa: E402
from rubric2 import remeasure, score2, HORIZON  # noqa: E402


def clean(d):
    return d[d["Volume"] > 0].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)


def attach(rows, frames, sectors=None, rk=None, market="US"):
    out = []
    for i, (sym, g) in enumerate(rows.groupby("symbol")):
        d = frames[sym]
        high, low = d["High"].to_numpy(float), d["Low"].to_numpy(float)
        for _, r in g.iterrows():
            end = int(r["end"])
            m = remeasure(d, end, HORIZON)
            sig = r.to_dict()
            sig["contraction"] = m["contraction_half"]
            sig["churn"] = m["churn"]
            sig["L_eff"] = m["L_eff"]
            sig["L_true"] = int(r["L_longest"])
            pm = R.prior_move_pct(rk, sym, r["date"]) if (rk is not None and market == "US") else None
            ss = R.sector_share_loo(rk, sectors, sym, r["date"]) if (sectors and market == "US") else None
            s2 = score2(sig, pm, ss, "boolean")
            # collapsed-range bars inside the base (D13 probe)
            s0 = end - int(r["L_longest"]) + 1
            rngs = high[s0:end + 1] / np.maximum(low[s0:end + 1], 1e-12) - 1.0
            zero_share = float((rngs < 1e-9).mean())
            out.append({
                "symbol": sym, "market": market, "date": r["date"], "end": end,
                "prior_move": pm, "sector_share": ss,
                "contraction2": m["contraction_half"], "churn2": m["churn"], "L_eff": m["L_eff"],
                "orderliness2": (m["churn"] / m["L_eff"]) if (m["churn"] and m["L_eff"]) else np.nan,
                "stars2": s2["stars"], "zero_rng_in_base": zero_share,
                **{k: r[k] for k in ["L", "L_longest", "n_windows", "adr", "close", "base_high",
                                     "base_low", "trigger", "trigger_bound_by", "stop_width_adr",
                                     "dryup", "ma_dist_adr", "sma20_rising", "low_slope_adr",
                                     "contraction", "churn"]},
            })
        if i % 100 == 0:
            print(f"  {market} {i} names, {len(out)} rows", flush=True)
    df = pd.DataFrame(out)
    df["trig_vs_close"] = df.trigger / df.close - 1.0
    return df


def find_rejects(d, ends, lmax=60):
    """Re-run the detector's two rejection paths and record why each date was dropped."""
    df = d.reset_index(drop=True)
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
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
            out.append({"end": int(end), "date": pd.to_datetime(df["Date"].iloc[end]),
                        "reason": "no_window", "adr": float(a), "close": float(close[end]),
                        "L": np.nan, "L_longest": np.nan, "stop_width_adr": np.nan})
            continue
        L = int(wins[0])
        s = end - L + 1
        bh, bl = high[s:end + 1].max(), low[s:end + 1].min()
        mh = sh[list(Ls).index(L)]
        line_today = high[s:end + 1].mean() + mh * ((L - 1) / 2.0)
        trigger = float(min(bh, line_today))
        stop_w = (trigger - bl) / trigger
        if stop_w > a:
            out.append({"end": int(end), "date": pd.to_datetime(df["Date"].iloc[end]),
                        "reason": "stop_too_wide", "adr": float(a), "close": float(close[end]),
                        "L": L, "L_longest": int(wins[-1]), "stop_width_adr": float(stop_w / a)})
    return out


if __name__ == "__main__":
    rk, elig, C = R.load_or_build()
    sectors = pd.read_pickle(os.path.join(CACHE, "sectors_us.pkl"))

    us = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    sw = pd.read_pickle(os.path.join(CACHE, "sweep_us.pkl"))
    pool = attach(sw, us, sectors, rk, "US")
    pool.to_pickle(os.path.join(CACHE, "pool_us.pkl"))
    print("US pool:", len(pool), flush=True)

    # ---- IDX slice
    idx = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_idx.pkl")).items()}
    rows = []
    for s, d in idx.items():
        if len(d) < 400:
            continue
        ends = list(range(90, len(d), 3))
        for r in fastscan.scan_name(d, ends):
            r["symbol"] = s
            rows.append(r)
    idx_sw = pd.DataFrame(rows)
    idx_pool = attach(idx_sw, idx, None, None, "IDX")
    idx_pool.to_pickle(os.path.join(CACHE, "pool_idx.pkl"))
    print("IDX pool:", len(idx_pool), flush=True)

    # ---- rejects, US only, sampled over the same sweep dates
    rng = np.random.default_rng(15)
    syms = sorted(us)
    rej = []
    for i, s in enumerate(syms):
        d = us[s]
        if len(d) < 400:
            continue
        dates = pd.to_datetime(d["Date"])
        start = int((dates < "2019-01-01").sum())
        ends = list(range(max(start, 90), len(d), 3))
        for r in find_rejects(d, ends):
            r["symbol"] = s
            rej.append(r)
        if i % 100 == 0:
            print(f"  rejects {i}/{len(syms)} rows={len(rej)}", flush=True)
    rdf = pd.DataFrame(rej)
    # keep only rejects that would have cleared D15's decile gate — a name nobody would look at
    # is not an interesting false negative
    keep = []
    for i, r in rdf.iterrows():
        pm = R.prior_move_pct(rk, r["symbol"], r["date"])
        if pm is not None and pm >= 0.90:
            keep.append({**r.to_dict(), "prior_move": pm})
    kdf = pd.DataFrame(keep)
    kdf.to_pickle(os.path.join(CACHE, "rejects_us.pkl"))
    print("rejects (decile-gated):", len(kdf), flush=True)
    print(kdf.reason.value_counts().to_string() if len(kdf) else "none")
