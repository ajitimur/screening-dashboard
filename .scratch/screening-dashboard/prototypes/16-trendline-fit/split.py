"""Port of q-scanner's base/cluster split, measured against ticket 08's window rule.

The trader asked to see this before committing. It is not a variation on D2-D4 — it is a
different way of finding the base entirely:

  ticket 08 (D2/D3/D4)   the base is any end-anchored window whose highs slope down and lows
                         slope up; the primary one is the SHORTEST such window. Median 3 bars.

  q-scanner              the base runs from the PRIOR MOVE'S PEAK to today (capped at 45 bars).
                         No slope test decides its extent. Inside it, a 3-7 bar trailing cluster
                         spanning <= 1.5 x ADR must exist, sitting on a rising 10/20/50 MA. The
                         line anchors at the cluster's max high and is fitted backwards over the
                         base's highs.

So q-scanner's "base" and "cluster" are two levels; ticket 08 collapses them into one 3-bar
object, which is why porting the geometry alone (envelope, max() clamp, cluster-low stop) onto
D4's window gave q-scanner's formulas without the structure that makes them mean anything.

Measures structure only — base length, whether a cluster exists, whether a line is drawable,
list length, stop width. The star rubric is not re-derived here; that is ticket 15's.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")

from compare import clean as _clean  # noqa: E402


def clean(d):
    """clean() plus a positive-price guard — a few IDX bars survive the phantom-bar drop with a
    zero low, which divides by zero in the run-up calculation."""
    d = _clean(d)
    return d[(d["Low"] > 0) & (d["High"] > 0)].reset_index(drop=True)

MOVE_WINDOWS = (21, 42, 63, 126)
MAX_BASE_LEN = 45
MIN_BASE_LEN = 3
K_MIN, K_MAX = 3, 7
TIGHT_MULT = 1.5
MA_PROX_ADR = 0.5
CATCHUP_10, CATCHUP_20 = 1.0, 2.0
OVER_W, UNDER_W, SLOPE_STEPS, MAX_SLOPE_ADR = 3.0, 1.0, 200, 0.5
TOUCH_TOL_ADR, MIN_TOUCHES, MIN_TOUCH_GAP = 0.35, 2, 3
MAX_OVERSHOOT_ADR, MAX_OVERSHOOT_FRAC = 1.0, 0.20


def prior_move(high, low, as_of):
    """Best low->high run-up over the configured windows, ending at or before as_of."""
    best = None
    for w in MOVE_WINDOWS:
        start = max(0, as_of - w)
        if as_of - start < 5:
            continue
        origin = start + int(np.argmin(low[start:as_of + 1]))
        if low[origin] <= 0:  # a handful of IDX bars carry a zero low even after the phantom drop
            continue
        seg = high[origin:as_of + 1]
        peak = origin + int(np.argmax(seg))
        gain = (float(high[peak]) / float(low[origin]) - 1.0) * 100.0
        if best is None or gain > best[0]:
            best = (gain, peak)
    return best


def find_cluster(high, low, as_of, adr_abs):
    """Largest trailing 3-7 bar window spanning <= TIGHT_MULT x ADR."""
    for k in range(K_MAX, K_MIN - 1, -1):
        if as_of - k + 1 < 0:
            continue
        ch = float(high[as_of - k + 1:as_of + 1].max())
        cl = float(low[as_of - k + 1:as_of + 1].min())
        if adr_abs > 0 and (ch - cl) / adr_abs <= TIGHT_MULT:
            return k, ch, cl, (ch - cl) / adr_abs
    return None


def fit_line(high, adr_abs, anchor, base_start, as_of, cluster_k):
    """The anchored, backwards-extrapolated upper envelope, plus its validity test."""
    t = np.arange(base_start, as_of + 1)
    h = high[base_start:as_of + 1].astype(float)
    y_a = float(high[anchor])
    slopes = np.linspace(-MAX_SLOPE_ADR * adr_abs, 0.0, SLOPE_STEPS)
    resid_all = h[None, :] - (y_a + slopes[:, None] * (t - anchor)[None, :])
    loss = OVER_W * np.clip(resid_all, 0, None) + UNDER_W * np.clip(-resid_all, 0, None)
    m = float(slopes[int(np.argmin(loss.sum(axis=1)))])

    resid = h - (y_a + m * (t - anchor))
    tol = TOUCH_TOL_ADR * adr_abs
    cluster_start = as_of - cluster_k + 1
    touch_idx = t[(np.abs(resid) <= tol) & (t < cluster_start)]
    zones = 1 + sum(1 for a, b in zip(touch_idx[:-1], touch_idx[1:]) if b - a >= MIN_TOUCH_GAP) \
        if len(touch_idx) else 0
    over = resid > tol
    over_max = float(resid[over].max() / adr_abs) if over.any() else 0.0
    base_len = as_of - base_start + 1
    reaches_back = len(touch_idx) > 0 and touch_idx[0] <= base_start + 0.6 * base_len
    ok = ((zones >= MIN_TOUCHES or (zones >= 1 and reaches_back))
          and over_max <= MAX_OVERSHOOT_ADR and float(over.mean()) <= MAX_OVERSHOOT_FRAC)
    return m, ok, zones, over_max


def scan(df, ends):
    df = df.reset_index(drop=True)
    high, low, close = (df[c].to_numpy(float) for c in ("High", "Low", "Close"))
    c = pd.Series(close)
    sma = {n: c.rolling(n).mean().to_numpy() for n in (10, 20, 50)}
    adr = pd.Series(high / low - 1.0).rolling(20).mean().to_numpy()

    out = []
    for as_of in ends:
        if as_of < 80 or as_of >= len(df):
            continue
        a = adr[as_of]
        if np.isnan(a) or a <= 0:
            continue
        adr_abs = a * close[as_of]
        mv = prior_move(high, low, as_of)
        if mv is None:
            continue
        gain, peak = mv
        base_start = peak
        if as_of - base_start + 1 > MAX_BASE_LEN:
            recent = as_of - MAX_BASE_LEN + 1
            base_start = recent + int(np.argmax(high[recent:as_of + 1]))
        base_len = as_of - base_start + 1
        rec = {"end": int(as_of), "date": pd.to_datetime(df["Date"].iloc[as_of]),
               "adr": float(a), "close": float(close[as_of]), "move_gain": float(gain),
               "base_len": int(base_len), "has_base": bool(base_len >= MIN_BASE_LEN)}
        if base_len < MIN_BASE_LEN:
            out.append({**rec, "tight": False, "caught_up": False, "line_ok": False})
            continue

        g10 = close[as_of] - sma[10][as_of] if not np.isnan(sma[10][as_of]) else np.inf
        g20 = close[as_of] - sma[20][as_of] if not np.isnan(sma[20][as_of]) else np.inf
        caught = bool(g10 <= CATCHUP_10 * adr_abs and g20 <= CATCHUP_20 * adr_abs)

        cl = find_cluster(high, low, as_of, adr_abs)
        if cl is None:
            out.append({**rec, "tight": False, "caught_up": caught, "line_ok": False})
            continue
        k, ch, clow, rng_adr = cl
        anchor = (as_of - k + 1) + int(np.argmax(high[as_of - k + 1:as_of + 1]))
        m, ok, zones, over_max = fit_line(high, adr_abs, anchor, base_start, as_of, k)
        line_end = float(high[anchor]) + m * (as_of + 1 - anchor)
        trigger = max(line_end, ch)
        out.append({**rec, "tight": True, "caught_up": caught, "cluster_k": k,
                    "cluster_range_adr": float(rng_adr), "line_ok": bool(ok),
                    "touch_zones": int(zones), "overshoot_adr": float(over_max),
                    "trigger": float(trigger), "cluster_low": float(clow),
                    "stopw_adr": float((trigger - clow) / trigger / a) if trigger > 0 else np.nan,
                    "base_low": float(low[base_start:as_of + 1].min())})
    return out


def run(frames, market, step=3, min_len=400):
    rows = []
    for i, (sym, d) in enumerate(sorted(frames.items())):
        if len(d) < min_len:
            continue
        for r in scan(d, range(90, len(d), step)):
            r["symbol"], r["market"] = sym, market
            rows.append(r)
        if i % 200 == 0:
            print(f"  {market} {i} names, {len(rows)} rows", flush=True)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    us = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    idx = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_idx.pkl")).items()}
    df = pd.concat([run(us, "US"), run(idx, "IDX")], ignore_index=True)
    df.to_pickle(os.path.join(CACHE, "split.pkl"))

    SCALE = 3.0
    print(f"\n=== q-scanner base/cluster split, {len(df):,} bar-dates evaluated")
    survives = df[df.tight & df.line_ok & df.caught_up]
    print("\nfunnel (share of evaluated bar-dates)")
    for lab, mask in (("base >= 3 bars", df.has_base), ("tight 3-7 bar cluster", df.tight),
                      ("caught up to the 10/20", df.tight & df.caught_up),
                      ("drawable line", df.tight & df.line_ok),
                      ("all three", df.tight & df.line_ok & df.caught_up)):
        print(f"  {lab:26s} {mask.mean():6.1%}")

    print(f"\nbase length, surviving detections: median {survives.base_len.median():.0f} bars "
          f"(ticket 08 primary: 3)")
    print(survives.base_len.describe(percentiles=[.25, .5, .75, .9]).round(1).to_string())

    print("\nnightly list length (scaled for 1-in-3 sampling)")
    for m in ("US", "IDX"):
        s = survives[survives.market == m]
        n = s.groupby("date").size().mean() * SCALE if len(s) else 0.0
        print(f"  {m:4s} {n:6.1f} / night")

    sw = survives.stopw_adr.replace([np.inf, -np.inf], np.nan).dropna()
    print(f"\nstop width (trigger to cluster low), ADR — median {sw.median():.2f}")
    for t in (1.0, 1.25, 1.5, 2.0):
        print(f"  within {t:.2f} ADR: {(sw <= t).mean():.1%}")
