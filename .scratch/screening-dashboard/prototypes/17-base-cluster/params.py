"""What the split costs in tunable parameters, and which of them actually bind.

Ticket 08 resolved with zero tunables; ticket 09 cost it two; round 2 fitted six thresholds. The
split adds a lot more, and ticket 16 declined to let that drift unremarked. A count alone is a weak
argument though — a parameter nothing is sensitive to is cheap, and one that swings the nightly list
is not. So this counts them *and* sweeps the load-bearing ones, reporting how much the list moves.

Sampled over 400 US names (seed 17) rather than the full universe: the sweep is 9 full re-scans and
the quantity of interest is a ratio, not a level.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
sys.path.insert(0, P16)
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")

import split as S  # noqa: E402

N_NAMES = 400
SEED = 17

# Every free number in split.py, grouped by the decision it belongs to. MA_PROX_ADR is defined but
# unused by scan(), so it is listed as dead rather than counted.
PARAMS = {
    "where the base starts": ["MOVE_WINDOWS (4 values: 21/42/63/126)", "MAX_BASE_LEN 45",
                              "MIN_BASE_LEN 3"],
    "the cluster": ["K_MIN 3", "K_MAX 7", "TIGHT_MULT 1.5"],
    "catch-up to the MAs": ["CATCHUP_10 1.0", "CATCHUP_20 2.0"],
    "the fitted line": ["OVER_W 3.0", "UNDER_W 1.0", "SLOPE_STEPS 200", "MAX_SLOPE_ADR 0.5"],
    "line validity": ["TOUCH_TOL_ADR 0.35", "MIN_TOUCHES 2", "MIN_TOUCH_GAP 3",
                      "MAX_OVERSHOOT_ADR 1.0", "MAX_OVERSHOOT_FRAC 0.20",
                      "reaches_back 0.6 x base_len"],
    "list length": ["prior-move floor 25%"],
}

SWEEPS = [
    ("TIGHT_MULT", [1.25, 1.5, 1.75]),
    ("K_MAX", [5, 7, 9]),
    ("TOUCH_TOL_ADR", [0.25, 0.35, 0.50]),
    ("MAX_OVERSHOOT_FRAC", [0.10, 0.20, 0.35]),
    ("MAX_BASE_LEN", [30, 45, 60]),
]


def sample_frames():
    us = pd.read_pickle(os.path.join(CACHE, "universe_us.pkl"))
    rng = np.random.default_rng(SEED)
    syms = sorted(s for s, d in us.items() if len(d) >= 400)
    take = rng.choice(len(syms), size=min(N_NAMES, len(syms)), replace=False)
    return {syms[int(i)]: S.clean(us[syms[int(i)]]) for i in take}


def scan_all(frames):
    rows = []
    for sym, d in frames.items():
        for r in S.scan(d, range(90, len(d), 3)):
            r["symbol"] = sym
            rows.append(r)
    df = pd.DataFrame(rows)
    if not len(df):
        return df, 0, 0
    ok = df.tight.fillna(False).astype(bool) & df.line_ok.fillna(False).astype(bool) \
        & df.caught_up.fillna(False).astype(bool)
    floor = ok & (df.move_gain >= 25.0)
    return df, int(ok.sum()), int(floor.sum())


def main():
    total = sum(len(v) for v in PARAMS.values()) + 3  # MOVE_WINDOWS is four numbers, not one
    print("=== the parameter bill\n")
    for group, items in PARAMS.items():
        print(f"  {group}")
        for it in items:
            print(f"      {it}")
    print(f"\n  {total} free numbers, against ticket 08's zero and round 2's six fitted thresholds.")
    print("  MA_PROX_ADR is defined in split.py and never read — dead, not counted.")
    print("  None of them is fitted to anything: they are q-scanner's defaults, carried over.")

    frames = sample_frames()
    print(f"\n=== sensitivity, {len(frames)} US names, 1-in-3 dates")
    base_df, base_ok, base_floor = scan_all(frames)
    print(f"  baseline: {base_ok:,} surviving detections ({base_floor:,} after the 25% floor)\n")
    print(f"  {'parameter':22s} {'value':>8s} {'detections':>12s} {'vs baseline':>13s}")
    results = []
    for name, values in SWEEPS:
        orig = getattr(S, name)
        for v in values:
            setattr(S, name, v)
            _, ok, _ = scan_all(frames)
            d = ok / base_ok - 1.0 if base_ok else np.nan
            mark = "  <- default" if v == orig else ""
            print(f"  {name:22s} {v:>8} {ok:>12,} {d:>12.1%}{mark}")
            results.append({"param": name, "value": v, "n": ok, "delta": d})
        setattr(S, name, orig)
        print()
    r = pd.DataFrame(results)
    r.to_pickle(os.path.join(OUT, "params.pkl"))
    swing = r.groupby("param").delta.agg(lambda s: s.max() - s.min()).sort_values(ascending=False)
    print("  swing in list length across each parameter's tested range:")
    for k, v in swing.items():
        print(f"    {k:22s} {v:6.1%}")


if __name__ == "__main__":
    main()
