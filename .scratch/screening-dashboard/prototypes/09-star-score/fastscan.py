"""Vectorised sweep of ticket 08's detector over many names/dates.

The triangle test needs a least-squares slope for every (end, L). Doing that with polyfit is
O(L) work per pair and takes hours; from cumulative sums it is O(1):

    slope = (L*S_iy - S_i*S_y) / (L*S_ii - S_i^2),  i = local index 0..L-1

with S_iy over the window rebased from global cumsums. Results are identical to polyfit
(verified in check_equiv()).
"""

import numpy as np
import pandas as pd

LMAX = 60


def slopes_for_end(y, cy, cky, end, Ls):
    """Least-squares slope of y over each end-anchored window length in Ls."""
    Ls = np.asarray(Ls, dtype=float)
    s = end - Ls + 1
    # sums over [s, end]
    Sy = cy[end + 1] - cy[s.astype(int)]
    Sky = cky[end + 1] - cky[s.astype(int)]  # sum of k*y with k the GLOBAL index
    Siy = Sky - s * Sy  # rebase to local index i = k - s
    Si = Ls * (Ls - 1) / 2.0
    Sii = (Ls - 1) * Ls * (2 * Ls - 1) / 6.0
    den = Ls * Sii - Si**2
    return (Ls * Siy - Si * Sy) / den


def scan_name(df, ends, lmax=LMAX):
    """Run the detector at each index in `ends`. Returns a list of result dicts."""
    df = df.reset_index(drop=True)
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    close = df["Close"].to_numpy(float)
    vol = df["Volume"].to_numpy(float)
    n = len(df)
    k = np.arange(n, dtype=float)

    ch = np.concatenate([[0.0], np.cumsum(high)])
    ckh = np.concatenate([[0.0], np.cumsum(k * high)])
    cl = np.concatenate([[0.0], np.cumsum(low)])
    ckl = np.concatenate([[0.0], np.cumsum(k * low)])
    crange = np.concatenate([[0.0], np.cumsum(high - low)])

    adr = pd.Series(high / low - 1.0).rolling(20).mean().to_numpy()
    sma20 = pd.Series(close).rolling(20).mean().to_numpy()

    # running max/min of end-anchored windows, computed per end below
    out = []
    Ls_all = np.arange(3, lmax + 1)
    for end in ends:
        if end < 80 or end >= n:
            continue
        a = adr[end]
        if np.isnan(a) or a <= 0:
            continue
        Ls = Ls_all[Ls_all <= end + 1]
        sh = slopes_for_end(high, ch, ckh, end, Ls)
        sl = slopes_for_end(low, cl, ckl, end, Ls)
        ok = (sh <= 0) & (sl >= 0)
        wins = Ls[ok]
        if len(wins) == 0:
            continue

        L = int(wins[0])
        Lm = int(wins[-1])
        s = end - L + 1
        bh = high[s : end + 1].max()
        bl = low[s : end + 1].min()

        # D5 trigger: min(flat max high, fitted descending line at today)
        mh = sh[list(Ls).index(L)]
        # intercept from the fit: mean(y) - m*mean(i)
        yb = high[s : end + 1].mean()
        line_today = yb + mh * ((L - 1) - (L - 1) / 2.0)
        trigger = float(min(bh, line_today))
        stop_w = (trigger - bl) / trigger
        if stop_w > a:
            continue

        # contraction over the retained set (D7)
        rngs = np.array(
            [high[end - int(x) + 1 : end + 1].max() - low[end - int(x) + 1 : end + 1].min() for x in wins]
        )
        contraction = None
        if len(wins) >= 2 and rngs[0] > 0:
            ratios = rngs / (rngs[0] * np.sqrt(wins / wins[0]))
            contraction = float(np.mean(ratios[1:]))

        # churn over the longest valid window (D8)
        sm = end - Lm + 1
        env = high[sm : end + 1].max() - low[sm : end + 1].min()
        churn = float((crange[end + 1] - crange[sm]) / env) if env > 0 else None

        # dry-up (D11)
        du = None
        if s - 50 >= 0:
            prior = np.median(vol[s - 50 : s])
            if prior > 0:
                du = float(np.median(vol[s : end + 1]) / prior)

        d = rising = None
        if not np.isnan(sma20[end]) and end >= 25:
            d = float((bl - sma20[end]) / (a * close[end]))
            rising = bool(sma20[end] > sma20[end - 5])

        out.append(
            {
                "end": int(end),
                "date": pd.to_datetime(df["Date"].iloc[end]),
                "L": L,
                "L_longest": Lm,
                "n_windows": int(len(wins)),
                "windows": wins.tolist(),
                "adr": float(a),
                "close": float(close[end]),
                "base_high": float(bh),
                "base_low": float(bl),
                "trigger": trigger,
                "trigger_bound_by": "line" if line_today < bh else "flat",
                "stop_width": float(stop_w),
                "stop_width_adr": float(stop_w / a),
                "contraction": contraction,
                "churn": churn,
                "dryup": du,
                "ma_dist_adr": d,
                "sma20_rising": rising,
                "low_slope_adr": float(sl[list(Ls).index(L)] / (a * close[end])),
                "detected": True,
            }
        )
    return out


def check_equiv(df, end):
    """Confirm the cumsum slopes match polyfit exactly."""
    from detector import valid_windows

    df = df.reset_index(drop=True)
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    n = len(df)
    k = np.arange(n, dtype=float)
    ch = np.concatenate([[0.0], np.cumsum(high)])
    ckh = np.concatenate([[0.0], np.cumsum(k * high)])
    cl = np.concatenate([[0.0], np.cumsum(low)])
    ckl = np.concatenate([[0.0], np.cumsum(k * low)])
    Ls = np.arange(3, min(LMAX, end + 1) + 1)
    sh = slopes_for_end(high, ch, ckh, end, Ls)
    sl = slopes_for_end(low, cl, ckl, end, Ls)
    fast = Ls[(sh <= 0) & (sl >= 0)].tolist()
    slow = valid_windows(high, low, end)
    return fast, slow, fast == slow
