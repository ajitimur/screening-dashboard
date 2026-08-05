"""Shared scan harness for ticket 19's parameter work.

Every script here asks the same question in a different direction: if this number moved, what
would move with it? So they all need the same three things — a fixed sample of names, a way to
re-scan under overridden parameters, and a consistent definition of "a detection".

The sample is fixed by seed so two scripts' numbers are comparable; the scan is cached to disk
keyed by the override set, because the sweeps re-scan the same configurations repeatedly.
"""

import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
sys.path.insert(0, P16)
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")
SCAN_CACHE = os.path.join(OUT, "scans")

import split as S  # noqa: E402

SEED = 19
N_US = 400
N_IDX = 288          # IDX's whole universe is smaller than the US sample
STEP = 3             # 1-in-3 dates, as tickets 16/17 sampled
MIN_LEN = 400
SCALE = float(STEP)  # nightly counts are scaled back up for the 1-in-3 grid

# Every free number in split.py. `dead` ones are defined and never read by scan().
BILL = {
    "MOVE_WINDOWS": (21, 42, 63, 126),
    "MAX_BASE_LEN": 45, "MIN_BASE_LEN": 3,
    "K_MIN": 3, "K_MAX": 7, "TIGHT_MULT": 1.5,
    "CATCHUP_10": 1.0, "CATCHUP_20": 2.0,
    "OVER_W": 3.0, "UNDER_W": 1.0, "SLOPE_STEPS": 200, "MAX_SLOPE_ADR": 0.5,
    "TOUCH_TOL_ADR": 0.35, "MIN_TOUCHES": 2, "MIN_TOUCH_GAP": 3,
    "MAX_OVERSHOOT_ADR": 1.0, "MAX_OVERSHOOT_FRAC": 0.20,
}
DEAD = {"MA_PROX_ADR": 0.5}
MOVE_FLOOR = 25.0    # the prior-move floor, applied after the scan rather than inside it


def _frames(market):
    """The fixed sample of cleaned frames for a market."""
    path = os.path.join(CACHE, f"universe_{market.lower()}.pkl")
    raw = pd.read_pickle(path)
    syms = sorted(s for s, d in raw.items() if len(d) >= MIN_LEN)
    n = N_US if market == "US" else N_IDX
    if len(syms) > n:
        rng = np.random.default_rng(SEED)
        take = sorted(int(i) for i in rng.choice(len(syms), size=n, replace=False))
        syms = [syms[i] for i in take]
    return {s: S.clean(raw[s]) for s in syms}


_FRAME_CACHE = {}


def frames(market):
    if market not in _FRAME_CACHE:
        _FRAME_CACHE[market] = _frames(market)
    return _FRAME_CACHE[market]


def _key(market, overrides):
    blob = json.dumps({"m": market, "o": sorted(overrides.items()), "seed": SEED,
                       "step": STEP, "n": N_US if market == "US" else N_IDX},
                      default=str, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:16]


def scan(market="US", overrides=None, verbose=False):
    """Re-scan the fixed sample with split.py's module-level parameters overridden.

    Cached on disk: the sweeps below re-request the same configuration from several angles, and a
    full pass is ~40s.
    """
    overrides = dict(overrides or {})
    os.makedirs(SCAN_CACHE, exist_ok=True)
    path = os.path.join(SCAN_CACHE, f"{market}_{_key(market, overrides)}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)

    saved = {k: getattr(S, k) for k in overrides}
    try:
        for k, v in overrides.items():
            setattr(S, k, v)
        rows = []
        for i, (sym, d) in enumerate(sorted(frames(market).items())):
            for r in S.scan(d, range(90, len(d), STEP)):
                r["symbol"] = sym
                rows.append(r)
            if verbose and i % 100 == 0:
                print(f"    {market} {i} names, {len(rows)} rows", flush=True)
    finally:
        for k, v in saved.items():
            setattr(S, k, v)

    df = pd.DataFrame(rows)
    df.to_pickle(path)
    return df


def accepted(df, floor=True):
    """A detection as the nightly list would see it: all three gates, then the prior-move floor."""
    if not len(df):
        return df
    ok = (df.tight.fillna(False).astype(bool)
          & df.line_ok.fillna(False).astype(bool)
          & df.caught_up.fillna(False).astype(bool))
    if floor:
        ok &= df.move_gain >= MOVE_FLOOR
    return df[ok]


_GATE = None
US_UNIVERSE = 1966   # ticket 05's measured US universe, for scaling the sample back up


def gate():
    """Ticket 06 R2's precondition gate: the union of top deciles across 1w/1m/3m/6m/12m.

    A boolean frame (date x symbol). It covers fewer names and dates than the bar cache, so
    anything measured through it is measured on the covered subset and said so.
    """
    global _GATE
    if _GATE is None:
        ranks, _, _ = pd.read_pickle(os.path.join(CACHE, "ranks_us.pkl"))
        g = None
        for frame in ranks.values():
            top = frame >= 0.90
            g = top if g is None else (g | top)
        g.index = pd.to_datetime(g.index)
        _GATE = g
    return _GATE


def covered_names(market="US"):
    """Sample names the rank table covers at all.

    This is the scaling denominator, and it must not depend on the parameter setting: counting
    only names that happened to produce a detection would shrink the denominator whenever the
    detector got stricter, which flatters every tightening.
    """
    return len(set(frames(market)) & set(gate().columns))


def gated(df):
    """Restrict to detections whose name was in the decile gate that night.

    Returns (gated_rows, covered_rows) — coverage is partial, so the caller reports the
    denominator alongside.
    """
    g = gate()
    if not len(df):
        return df, df
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d[d.symbol.isin(set(g.columns)) & d.date.isin(set(g.index))]
    if not len(d):
        return d, d
    keep = np.array([bool(g.at[dt, s]) for s, dt in zip(d.symbol, d.date)])
    return d[keep], d


def per_night(df):
    """Mean nightly list length, scaled back up from the 1-in-3 date grid."""
    if not len(df):
        return 0.0
    return float(df.groupby("date").size().mean()) * SCALE


if __name__ == "__main__":
    import time
    t = time.time()
    d = scan("US", verbose=True)
    a = accepted(d)
    print(f"\nUS baseline: {len(d):,} bar-dates, {len(a):,} accepted, "
          f"{per_night(a):.1f}/night, {time.time() - t:.0f}s")
