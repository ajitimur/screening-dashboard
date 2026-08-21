"""PROTOTYPE — throwaway. Prints the headline numbers from tightness.json."""
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
d = json.loads((HERE / "tightness.json").read_text())
T = d["trades"]


def q(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return float("nan")
    i = (len(xs) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def line(name, xs):
    xs = [x for x in xs if x is not None]
    print(f"{name:<28} n={len(xs):<4} p10={q(xs,.1):6.2f} p25={q(xs,.25):6.2f} "
          f"med={median(xs):6.2f} p75={q(xs,.75):6.2f} p90={q(xs,.9):6.2f} max={max(xs):6.2f}")


print(f"measured {d['n_measured']} / {d['n_trades_total']}  skipped={d['skipped']}")
print(f"bars {d['bar_window'][0]}..{d['bar_window'][1]}\n")

print("== trailing k-bar range at the eval session, in ADR ==")
for k in range(3, 8):
    line(f"  k={k} range_adr", [t["range_adr"][str(k)] for t in T])
line("  tightest over k=3..7", [min(t["range_adr"].values()) for t in T])

print("\n== his own numbers ==")
line("  stop width (ADR)", [t["stop_adr"] for t in T])
line("  stop width (%)", [t["stop_pct"] * 100 for t in T if t["stop_pct"]])
line("  ADR at entry (%)", [t["adr_pct"] for t in T])
line("  entry - high3 (ADR)", [t["entry_vs_high3_adr"] for t in T])
line("  stop - low3 (ADR)", [t["stop_vs_low3_adr"] for t in T])
line("  stop - low7 (ADR)", [t["stop_vs_low7_adr"] for t in T])

print("\n== pass rate of the detector's gate: any k in 3..7 with range <= MULT ==")
for mult in (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 4.0):
    passed = [t for t in T if min(t["range_adr"].values()) <= mult]
    ks = [max(int(k) for k, v in t["range_adr"].items() if v <= mult) for t in passed]
    k5 = sum(1 for x in ks if x >= 5)
    print(f"  MULT={mult:<5} pass {len(passed):>4}/{len(T)} = {len(passed)/len(T)*100:5.1f}%   "
          f"of those, cluster_k>=5: {k5/len(passed)*100 if passed else 0:5.1f}%")

print("\n== does tightness pay? median gain10sma% by tightest-range bucket ==")
buckets = [(0, 1.0), (1.0, 1.5), (1.5, 2.0), (2.0, 3.0), (3.0, 99)]
for lo, hi in buckets:
    sel = [t for t in T if lo <= min(t["range_adr"].values()) < hi]
    g = [t["gain10sma_pct"] for t in sel if t["gain10sma_pct"] is not None]
    r = [t["rr10sma"] for t in sel if t["rr10sma"] is not None]
    if not g:
        continue
    win = sum(1 for x in g if x > 0) / len(g) * 100
    print(f"  [{lo:>4}, {hi:>4}) n={len(sel):<4} median gain {median(g):7.2f}%  "
          f"median R {median(r):5.2f}  win {win:5.1f}%")
