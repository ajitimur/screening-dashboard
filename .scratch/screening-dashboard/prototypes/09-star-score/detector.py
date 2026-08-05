"""Ticket 08's detector + a first-cut §3.5 scorer. Throwaway prototype for ticket 09.

Everything here follows the decisions in .scratch/screening-dashboard/issues/08-setup-detection-algorithm.md
literally, so that disagreements found during calibration are disagreements with 08's design and not
with a sloppy re-reading of it.
"""

import numpy as np
import pandas as pd

LMAX = 60  # pure compute bound (D14) — never binds


# --------------------------------------------------------------------------- data


def clean(df):
    """Ticket 05: drop phantom zero-volume bars; windows count traded bars."""
    df = df[df["Volume"] > 0].copy()
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return df


def adr20(df):
    """§: ADR% = SMA20((High / Low - 1) * 100), as a fraction."""
    return ((df["High"] / df["Low"] - 1.0)).rolling(20).mean()


# ----------------------------------------------------------------------- geometry


def _slope(y):
    x = np.arange(len(y), dtype=float)
    return np.polyfit(x, y, 1)[0]


def _fit(y):
    x = np.arange(len(y), dtype=float)
    m, b = np.polyfit(x, y, 1)
    return m, b


def valid_windows(highs, lows, end, lmax=LMAX):
    """D2/D9/D14: end-anchored backward search, triangle test, no Lmax that binds.

    Returns list of L (>=3) whose window [end-L+1 .. end] passes the triangle test.
    """
    out = []
    for L in range(3, lmax + 1):
        s = end - L + 1
        if s < 0:
            break
        h = highs[s : end + 1]
        lo = lows[s : end + 1]
        if _slope(h) <= 0 and _slope(lo) >= 0:
            out.append(L)
    return out


# ------------------------------------------------------------------------ signals


def contraction_score(highs, lows, end, windows):
    """D7: how far the range(L) curve sits below its sqrt(L) random-walk baseline.

    range(L) is monotone non-decreasing in L. Under a random walk it grows ~ sqrt(L).
    Normalise each observed range by range(L0) * sqrt(L/L0) and take the mean shortfall.
    Returns a raw ratio in (0, 1]: < 1 means contracting (flatter than sqrt(L)).
    """
    if len(windows) < 2:
        return None
    rngs = []
    for L in windows:
        s = end - L + 1
        rngs.append(highs[s : end + 1].max() - lows[s : end + 1].min())
    L0, r0 = windows[0], rngs[0]
    if r0 <= 0:
        return None
    ratios = [r / (r0 * np.sqrt(L / L0)) for L, r in zip(windows, rngs)]
    return float(np.mean(ratios[1:]))


def churn_ratio(df, end, L):
    """D8: sum of daily ranges over the base / envelope. Measured on the LONGEST valid window."""
    s = end - L + 1
    w = df.iloc[s : end + 1]
    env = w["High"].max() - w["Low"].min()
    if env <= 0:
        return None
    return float((w["High"] - w["Low"]).sum() / env)


def dryup(df, end, L):
    """D11: median base volume / median volume over the 50 bars preceding the base."""
    s = end - L + 1
    if s - 50 < 0:
        return None
    base = df["Volume"].iloc[s : end + 1].median()
    prior = df["Volume"].iloc[s - 50 : s].median()
    if prior <= 0:
        return None
    return float(base / prior)


def ma_dist_adr(df, end, base_low, adr):
    """D10: (base low - SMA20) / (ADR * price), with SMA20 required to be rising (sign-only)."""
    close = df["Close"]
    sma20 = close.rolling(20).mean()
    if end < 25 or np.isnan(sma20.iloc[end]):
        return None, None
    rising = bool(sma20.iloc[end] > sma20.iloc[end - 5])
    px = float(close.iloc[end])
    d = (base_low - float(sma20.iloc[end])) / (adr * px)
    return float(d), rising


# ------------------------------------------------------------------------ detect


def detect(df, end=None):
    """Run ticket 08's detector at bar `end` (default: last bar). Returns a dict or None."""
    df = df.reset_index(drop=False)
    if end is None:
        end = len(df) - 1
    if end < 75:
        return None

    highs = df["High"].to_numpy()
    lows = df["Low"].to_numpy()
    a = adr20(df)
    adr = float(a.iloc[end])
    if np.isnan(adr):
        return None

    wins = valid_windows(highs, lows, end)
    if not wins:
        return {"detected": False, "reason": "no valid triangle window", "adr": adr}

    L = wins[0]  # D4: primary is the shortest valid window
    Lmax_valid = wins[-1]
    s = end - L + 1
    base_high = float(highs[s : end + 1].max())
    base_low = float(lows[s : end + 1].min())

    # D5: trigger = min(flat max high, fitted descending line evaluated at today)
    m, b = _fit(highs[s : end + 1])
    line_today = m * (L - 1) + b
    trigger = float(min(base_high, line_today))

    # D6: stop estimated at base low; reject when wider than 1 x ADR
    stop_width = (trigger - base_low) / trigger
    if stop_width > adr:
        return {
            "detected": False,
            "reason": f"stop {stop_width:.3f} > 1xADR {adr:.3f}",
            "adr": adr,
            "stop_width": float(stop_width),
            "L": L,
        }

    low_slope = _slope(lows[s : end + 1]) / (adr * float(df["Close"].iloc[end]))
    d, rising = ma_dist_adr(df, end, base_low, adr)

    return {
        "detected": True,
        "date": str(df["Date"].iloc[end])[:10],
        "end": end,
        "L": L,
        "L_longest": Lmax_valid,
        "n_windows": len(wins),
        "windows": wins,
        "adr": adr,
        "close": float(df["Close"].iloc[end]),
        "base_high": base_high,
        "base_low": base_low,
        "trigger": trigger,
        "trigger_bound_by": "line" if line_today < base_high else "flat",
        "line_slope": float(m),
        "stop_width": float(stop_width),
        "stop_width_adr": float(stop_width / adr),
        "contraction": contraction_score(highs, lows, end, wins),
        "churn": churn_ratio(df, end, Lmax_valid),
        "dryup": dryup(df, end, L),
        "ma_dist_adr": d,
        "sma20_rising": rising,
        "low_slope_adr": float(low_slope),
    }
