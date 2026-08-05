"""Controlled synthetic bases: envelope shape and per-bar churn varied independently.

envelope h(t): half-width of the converging boundary. Decreasing => triangle.
u,v in (0,1]: how much of the envelope each bar actually traverses => churn.
"""

import numpy as np
from detector import contraction_score, churn_ratio, valid_windows
import pandas as pd


def make(L=20, taper=0.15, fill=0.35, seed=0, h0=3.0):
    """taper: h(end)/h(0). 1.0 = flat channel, 0.15 = strong contraction.
    fill: fraction of the local envelope each bar traverses. 0.2 = smooth drift, 0.95 = barcode.
    """
    rng = np.random.default_rng(seed)
    t = np.arange(L)
    h = h0 * (taper ** (t / max(L - 1, 1)))
    c = 100.0
    hi = np.empty(L)
    lo = np.empty(L)
    for i in range(L):
        span = 2 * h[i] * fill * rng.uniform(0.75, 1.25)
        span = min(span, 2 * h[i])
        # place the bar somewhere inside the envelope
        top = c + h[i] - rng.uniform(0, 2 * h[i] - span)
        hi[i] = top
        lo[i] = top - span
    return hi, lo


def measure(hi, lo):
    end = len(hi) - 1
    wins = valid_windows(hi, lo, end)
    if not wins:
        return None
    df = pd.DataFrame({"High": hi, "Low": lo})
    return {
        "n_windows": len(wins),
        "L_primary": wins[0],
        "L_longest": wins[-1],
        "contraction": contraction_score(hi, lo, end, wins),
        "churn": churn_ratio(df, end, wins[-1]),
        "churn_over_sqrtL": (churn_ratio(df, end, wins[-1]) or np.nan) / np.sqrt(wins[-1]),
    }
