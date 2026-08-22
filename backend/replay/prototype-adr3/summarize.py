"""PROTOTYPE — throwaway. Print the recent-3 vs prior-3 findings from adr3.json.

Run:  backend/.venv/bin/python backend/replay/prototype-adr3/summarize.py
"""
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = json.loads((HERE / "adr3.json").read_text())
T = D["trades"]
B = D["background"]
FRESH = [t for t in T if not t["continuation"]]


def q(xs, p):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    i = (len(xs) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (i - lo)


def compare(field, fmt="{:6.2f}"):
    """Entries vs the same names on ordinary days."""
    a = [t[field] for t in T if t.get(field) is not None]
    b = [x[field] for x in B if x.get(field) is not None]
    cells = lambda xs: "  ".join(fmt.format(q(xs, p)) for p in (0.25, 0.5, 0.75))
    print(f"{field:20s} entry n={len(a):4d}  {cells(a)}   |   "
          f"background n={len(b):5d}  {cells(b)}")


def share(label, xs, pred):
    xs = [x for x in xs if x is not None]
    n = sum(1 for x in xs if pred(x))
    return n, len(xs), 100 * n / len(xs) if xs else 0


def gate(label, pred):
    """Pass rate at entries vs background — the closest thing to a lift figure."""
    ne, de, pe = share(label, T, pred)
    nb, db, pb = share(label, B, pred)
    lift = pe / pb if pb else float("inf")
    print(f"{label:38s} entry {pe:5.1f}%  background {pb:5.1f}%   lift {lift:4.2f}x")


print(f"n entries = {D['n_measured']} / {D['n_trades_total']}, "
      f"background = {D['n_background']} same-ticker sessions")
print(f"params = {D['params']}")
print(f"continuation = {sum(1 for t in T if t['continuation'])}, fresh = {len(FRESH)}")

print("\n=== 1. RECENT 3 BARS vs THE PRIOR 3 BARS ===")
print(f"{'':20s} {'':13s}   p25     p50     p75   |   (same, background)")
compare("adr3_recent_pct")
compare("adr3_prior_pct")
compare("adr3_ratio")
compare("adr3_vs_adr20")
compare("span3_recent_adr")
compare("span3_prior_adr")
compare("span3_ratio")
compare("vol3_ratio")
compare("vol3_vs_vol20")

print("\n=== 2. PASS RATES AT THRESHOLDS (entry vs background) ===")
for thr in (0.7, 0.8, 0.9, 1.0):
    gate(f"adr3_ratio <= {thr}", lambda x, t=thr: x["adr3_ratio"] <= t)
print()
for thr in (0.5, 0.7, 0.9, 1.0):
    gate(f"span3_ratio <= {thr}", lambda x, t=thr: (x["span3_ratio"] or 9) <= t)
print()
for thr in (1.0, 1.3, 1.5, 2.0):
    gate(f"span3_recent <= {thr} ADR", lambda x, t=thr: x["span3_recent_adr"] <= t)
print()
for thr in (0.7, 0.85, 1.0):
    gate(f"vol3_ratio <= {thr}", lambda x, t=thr: (x["vol3_ratio"] or 9) <= t)
print()
gate("span3 <= 1.5 ADR AND adr3_ratio <= 0.9",
     lambda x: x["span3_recent_adr"] <= 1.5 and x["adr3_ratio"] <= 0.9)
gate("span3 <= 1.5 ADR AND vol3_ratio <= 0.9",
     lambda x: x["span3_recent_adr"] <= 1.5 and (x["vol3_ratio"] or 9) <= 0.9)

print("\n=== 2b. DOES THE RATIO ADD ANYTHING ON TOP OF THE LEVEL? ===")
print("Lift is recomputed *within* a band of span3_recent, so the level is held")
print("roughly fixed and only the recent-vs-prior ratio varies.")
for lo, hi in ((0, 1.0), (1.0, 1.5), (1.5, 2.5), (2.5, 99)):
    te = [t for t in T if lo <= t["span3_recent_adr"] < hi]
    be = [x for x in B if lo <= x["span3_recent_adr"] < hi]
    if len(te) < 25:
        continue
    print(f"\n  span3_recent in [{lo}, {hi})   entries n={len(te)}, background n={len(be)}")
    for thr in (0.7, 0.9):
        pe = 100 * sum(1 for t in te if t["adr3_ratio"] <= thr) / len(te)
        pb = 100 * sum(1 for x in be if x["adr3_ratio"] <= thr) / len(be)
        print(f"    adr3_ratio <= {thr}      entry {pe:5.1f}%  background {pb:5.1f}%  "
              f"lift {pe / pb if pb else 0:4.2f}x")
    for thr in (0.7, 0.9):
        pe = 100 * sum(1 for t in te if (t["vol3_ratio"] or 9) <= thr) / len(te)
        pb = 100 * sum(1 for x in be if (x["vol3_ratio"] or 9) <= thr) / len(be)
        print(f"    vol3_ratio  <= {thr}      entry {pe:5.1f}%  background {pb:5.1f}%  "
              f"lift {pe / pb if pb else 0:4.2f}x")

print("\n=== 3. OUTCOME BY BUCKET (MFE under the 10sma exit) ===")


def cross(title, groups):
    print(f"\n{title:>26}  {'n':>4}  {'med MFE%':>9}  {'p75 MFE%':>9}  "
          f"{'mean R':>7}  {'R>0':>6}")
    for label, grp in groups:
        ms = [t["mfe10sma_pct"] for t in grp if t["mfe10sma_pct"] is not None]
        rs = [t["rr10sma"] for t in grp if t["rr10sma"] is not None]
        win = sum(1 for r in rs if r > 0) / len(rs) * 100 if rs else 0
        mean_r = sum(rs) / len(rs) if rs else 0
        print(f"{label:>26}  {len(grp):4d}  {q(ms, 0.5) or 0:9.1f}  {q(ms, 0.75) or 0:9.1f}  "
              f"{mean_r:7.2f}  {win:5.1f}%")


cross("ALL", [("all entries", T)])
cross("adr3_ratio", [(lab, [t for t in T if lo <= t["adr3_ratio"] < hi])
                     for lab, lo, hi in [("<0.6", 0, .6), ("0.6-0.85", .6, .85),
                                         ("0.85-1.15", .85, 1.15), ("1.15+", 1.15, 1e9)]])
cross("span3_ratio", [(lab, [t for t in T if t["span3_ratio"] is not None
                             and lo <= t["span3_ratio"] < hi])
                      for lab, lo, hi in [("<0.5", 0, .5), ("0.5-0.8", .5, .8),
                                          ("0.8-1.1", .8, 1.1), ("1.1+", 1.1, 1e9)]])
cross("vol3_ratio", [(lab, [t for t in T if t["vol3_ratio"] is not None
                            and lo <= t["vol3_ratio"] < hi])
                     for lab, lo, hi in [("<0.7", 0, .7), ("0.7-1.0", .7, 1.0),
                                         ("1.0-1.5", 1.0, 1.5), ("1.5+", 1.5, 1e9)]])

print("\n=== 4. BOOTSTRAP (median MFE, 20k resamples, seeded) ===")


def boot(name, a, b, reps=20000):
    a = [t["mfe10sma_pct"] for t in a if t["mfe10sma_pct"] is not None]
    b = [t["mfe10sma_pct"] for t in b if t["mfe10sma_pct"] is not None]
    if not a or not b:
        print(f"{name:44s} (empty)")
        return
    rng = random.Random(20260822)
    hits = sum(q(rng.choices(a, k=len(a)), 0.5) <= q(rng.choices(b, k=len(b)), 0.5)
               for _ in range(reps))
    print(f"{name:44s} n={len(a):3d} vs {len(b):3d}  "
          f"median {q(a, 0.5):5.1f} vs {q(b, 0.5):5.1f}  p={hits / reps:.3f}")


boot("adr3_ratio < 0.85 vs rest",
     [t for t in T if t["adr3_ratio"] < 0.85], [t for t in T if t["adr3_ratio"] >= 0.85])
boot("span3_ratio < 0.8 vs rest",
     [t for t in T if (t["span3_ratio"] or 9) < 0.8],
     [t for t in T if (t["span3_ratio"] or 9) >= 0.8])
boot("vol3_ratio < 0.7 vs rest",
     [t for t in T if (t["vol3_ratio"] or 9) < 0.7],
     [t for t in T if (t["vol3_ratio"] or 9) >= 0.7])
boot("span3_recent <= 1.5 ADR vs rest",
     [t for t in T if t["span3_recent_adr"] <= 1.5],
     [t for t in T if t["span3_recent_adr"] > 1.5])
