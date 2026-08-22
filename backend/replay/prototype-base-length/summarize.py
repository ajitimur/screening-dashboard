"""PROTOTYPE — throwaway. Print the base-length findings from base.json.

Run:  backend/.venv/bin/python backend/replay/prototype-base-length/summarize.py
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = json.loads((HERE / "base.json").read_text())
T = D["trades"]
FRESH = [t for t in T if not t["continuation"]]


def q(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    i = (len(xs) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def row(label, xs, fmt="{:.1f}"):
    xs = [x for x in xs if x is not None]
    if not xs:
        print(f"{label:34s} (none)")
        return
    cells = " ".join(fmt.format(q(xs, p)) for p in (0.10, 0.25, 0.50, 0.75, 0.90))
    print(f"{label:34s} n={len(xs):4d}  {cells}   max={max(xs):.1f}")


def share(label, xs, pred):
    xs = [x for x in xs if x is not None]
    n = sum(1 for x in xs if pred(x))
    print(f"{label:34s} {n:4d}/{len(xs)}  {100 * n / len(xs):.1f}%")


print(f"n measured = {D['n_measured']} / {D['n_trades_total']}   skipped={D['skipped']}")
print(f"continuation = {sum(1 for t in T if t['continuation'])}, fresh = {len(FRESH)}")
print(f"params = {D['params']}")

print("\n=== 1. BASE LENGTH (sessions) ===                  p10   p25   p50   p75   p90")
row("D1 pivot-high -> entry (all)", [t["base_len_pivot"] for t in T])
row("D1 pivot-high -> entry (fresh)", [t["base_len_pivot"] for t in FRESH])
share("  D1 censored at lookback", T, lambda t: t["base_len_pivot_censored"])
share("  D1 <= 5 sessions", T, lambda t: t["base_len_pivot"] <= 5)
share("  D1 in 6..30", T, lambda t: 6 <= t["base_len_pivot"] <= 30)
share("  D1 in 31..60", T, lambda t: 31 <= t["base_len_pivot"] <= 60)
share("  D1 > 60", T, lambda t: t["base_len_pivot"] > 60)
print()
for k in D["params"]["contain_t"]:
    key = str(k)
    row(f"D2 contained within {k} ADR (all)", [t["contain"][key]["n"] for t in T])
for k in D["params"]["contain_t"]:
    key = str(k)
    share(f"  D2 {k} ADR censored", T, lambda t, key=key: t["contain"][key]["censored"])

print("\n=== 2. WHEN ADR STARTS TIGHTENING ===              p10   p25   p50   p75   p90")
row("ADR peak, sessions before entry", [t["adr_peak_days_before"] for t in T])
row("  fresh only", [t["adr_peak_days_before"] for t in FRESH])
share("  peak censored at curve edge", T, lambda t: t["adr_peak_censored"])
row("ADR now / ADR at peak", [t["adr_contraction"] for t in T], "{:.2f}")
row("ADR at entry eve (%)", [t["adr_pct"] for t in T], "{:.2f}")
row("ADR at peak (%)", [t["adr_peak_pct"] for t in T], "{:.2f}")
row("ADR at pivot high (%)", [t["adr_at_pivot_pct"] for t in T], "{:.2f}")
share("  ADR peaked at/before pivot", T,
      lambda t: t["adr_peak_days_before"] >= t["base_len_pivot"])

print("\nMedian ADR curve, aligned on entry (d = sessions before entry)")
print(" d   ADR%   ratio-to-entry-eve   n")
for d in (0, 5, 10, 15, 20, 30, 40, 50, 60, 75, 90):
    vals = [t["adr_curve_pct"][d] for t in T
            if len(t["adr_curve_pct"]) > d and t["adr_curve_pct"][d]]
    ratios = [t["adr_curve_pct"][d] / t["adr_curve_pct"][0] for t in T
              if len(t["adr_curve_pct"]) > d and t["adr_curve_pct"][d] and t["adr_curve_pct"][0]]
    if vals:
        print(f"{d:3d}  {q(vals, 0.5):5.2f}      {q(ratios, 0.5):5.2f}          {len(vals)}")

print("\nMedian ADR curve, aligned on the pivot high (x = sessions after base start)")
print("  x   ratio-to-ADR-at-pivot   n")
for x in (-20, -10, -5, 0, 5, 10, 15, 20, 30, 40, 60):
    ratios = []
    for t in T:
        d = t["base_len_pivot"] - x
        c = t["adr_curve_pct"]
        base = c[t["base_len_pivot"]] if len(c) > t["base_len_pivot"] else None
        if 0 <= d < len(c) and c[d] and base:
            ratios.append(c[d] / base)
    if len(ratios) >= 30:
        print(f"{x:4d}   {q(ratios, 0.5):5.2f}                 {len(ratios)}")

print("\n=== 2b. THE RANGE-RATIO CURVE (5-bar range / ADR) ===")
print("This is what actually tightens. d = sessions before entry.")
print(" d   median  p25    p75    n")
for d in (0, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 60, 90):
    vals = [t["rr5_curve"][d] for t in T
            if len(t["rr5_curve"]) > d and t["rr5_curve"][d] is not None]
    if vals:
        print(f"{d:3d}   {q(vals, 0.5):5.2f}  {q(vals, 0.25):5.2f}  {q(vals, 0.75):5.2f}  {len(vals)}")
row("Sessions continuously <= 2 ADR", [t["rr5_quiet_sessions"] for t in T])
row("  fresh only", [t["rr5_quiet_sessions"] for t in FRESH])
row("Days since 5-bar range > 2.5 ADR", [t["rr5_last_wide_days"] for t in T])
share("  quiet run >= 5 sessions", T, lambda t: t["rr5_quiet_sessions"] >= 5)
share("  quiet run >= 10 sessions", T, lambda t: t["rr5_quiet_sessions"] >= 10)
share("  quiet run = 0 (already wide)", T, lambda t: t["rr5_quiet_sessions"] == 0)

print("\n=== 3. THE PRIOR ADVANCE AND BASE DEPTH ===        p10   p25   p50   p75   p90")
for W in D["params"]["advance_lookbacks"]:
    k = str(W)
    row(f"Advance % (within {W} sessions)", [t["advance"][k]["pct"] for t in T])
    row(f"Advance length ({W}-cap)", [t["advance"][k]["len"] for t in T])
    share(f"  {W}-cap censored", T, lambda t, k=k: t["advance"][k]["censored"])
row("Base depth from pivot (%)", [t["base_depth_pct"] for t in T])
row("Base depth (ADR)", [t["base_depth_adr"] for t in T], "{:.2f}")

print("\n=== 4. DOES BASE GEOMETRY PREDICT THE OUTCOME? ===")
print("Outcome of record is MFE (study §A3): the exits are counterfactual, MFE is")
print("a property of the entry. Realised R over the 10sma exit is shown beside it.")


def cross(title, groups):
    print(f"\n{title:>26}  {'n':>4}  {'med MFE%':>9}  {'p75 MFE%':>9}  "
          f"{'med R':>7}  {'mean R':>7}  {'R>0':>6}")
    for label, grp in groups:
        ms = [t["mfe10sma_pct"] for t in grp if t["mfe10sma_pct"] is not None]
        rs = [t["rr10sma"] for t in grp if t["rr10sma"] is not None]
        win = sum(1 for r in rs if r > 0) / len(rs) * 100 if rs else 0
        mean_r = sum(rs) / len(rs) if rs else 0
        print(f"{label:>26}  {len(grp):4d}  {q(ms, 0.5) or 0:9.1f}  {q(ms, 0.75) or 0:9.1f}  "
              f"{q(rs, 0.5) or 0:7.2f}  {mean_r:7.2f}  {win:5.1f}%")


cross("ALL", [("all trades", T)])
cross("D1 base length", [(lab, [t for t in T if lo <= t["base_len_pivot"] <= hi])
                        for lab, lo, hi in [("0-5", 0, 5), ("6-15", 6, 15),
                                            ("16-30", 16, 30), ("31-60", 31, 60),
                                            ("61+", 61, 10**6)]])
cross("quiet run (<=2 ADR)", [(lab, [t for t in T if lo <= t["rr5_quiet_sessions"] <= hi])
                              for lab, lo, hi in [("0-1", 0, 1), ("2-4", 2, 4),
                                                  ("5-9", 5, 9), ("10+", 10, 10**6)]])
cross("base depth %", [(lab, [t for t in T
                              if t["base_depth_pct"] is not None
                              and lo <= t["base_depth_pct"] < hi])
                       for lab, lo, hi in [("<20", 0, 20), ("20-35", 20, 35),
                                           ("35-50", 35, 50), ("50+", 50, 1e9)]])
cross("prior advance % (60-cap)", [(lab, [t for t in T
                                          if t["advance"]["60"]["pct"] is not None
                                          and lo <= t["advance"]["60"]["pct"] < hi])
                                   for lab, lo, hi in [("<50", 0, 50), ("50-100", 50, 100),
                                                       ("100-200", 100, 200), ("200+", 200, 1e12)]])

# --- are the two apparent effects distinguishable from noise? ---------------
# MFE is heavily right-skewed, so a bootstrap on the median difference is the
# honest test; a t-test on these tails would be meaningless. Deterministic seed.
import random

def boot(name, a, b, reps=20000):
    """One-sided bootstrap: P(median MFE of `a` <= median of `b`) under resampling."""
    a = [t["mfe10sma_pct"] for t in a if t["mfe10sma_pct"] is not None]
    b = [t["mfe10sma_pct"] for t in b if t["mfe10sma_pct"] is not None]
    rng = random.Random(20260822)
    hits = 0
    for _ in range(reps):
        ma = q(rng.choices(a, k=len(a)), 0.5)
        mb = q(rng.choices(b, k=len(b)), 0.5)
        hits += (ma <= mb)
    print(f"{name:44s} n={len(a):3d} vs {len(b):3d}  "
          f"median {q(a, 0.5):.1f} vs {q(b, 0.5):.1f}  p={hits / reps:.3f}")


print("\n=== 5. BOOTSTRAP ON THE TWO APPARENT EFFECTS (median MFE) ===")
boot("quiet run >=10 vs rest",
     [t for t in T if t["rr5_quiet_sessions"] >= 10],
     [t for t in T if t["rr5_quiet_sessions"] < 10])
boot("prior advance >=200% vs rest",
     [t for t in T if (t["advance"]["60"]["pct"] or 0) >= 200],
     [t for t in T if (t["advance"]["60"]["pct"] or 0) < 200])
boot("base depth >=50% vs rest",
     [t for t in T if (t["base_depth_pct"] or 0) >= 50],
     [t for t in T if (t["base_depth_pct"] or 0) < 50])
boot("base length 16-30 vs rest",
     [t for t in T if 16 <= t["base_len_pivot"] <= 30],
     [t for t in T if not (16 <= t["base_len_pivot"] <= 30)])
