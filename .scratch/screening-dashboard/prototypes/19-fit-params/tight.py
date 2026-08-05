"""TIGHT_MULT and the k range — the numbers that have to be chosen rather than derived.

TIGHT_MULT is four things at once, which is why it cannot be fitted against a single objective:

  1. §3.4's looseness auto-reject — the trader's own criterion, an eye judgement
  2. the bound on the stop: the cluster must span <= TIGHT_MULT x ADR, and the stop runs from the
     trigger to the cluster low
  3. the largest single lever on nightly list length (ticket 17 measured a 63% swing)
  4. since ticket 15, an input to the *score* — cluster length k is the rubric's tightness
     dimension, and k is chosen as the largest window that fits under TIGHT_MULT x ADR

(4) is new and is the reason this ticket could not run before 15. Moving TIGHT_MULT redistributes
k, and k is what the rubric reads, so the parameter moves the sort as well as the list.

The k range inherits its own double duty from ticket 18: the cluster high *is* the trigger, so
K_MIN/K_MAX also set the digest's effective breakout lookback.

This script measures all four consequences on one grid and hands the choice over. It does not pick
a value — that is the trader's, against an explicit budget.
"""

import os

import numpy as np
import pandas as pd

import harness as H

GRID = [1.0, 1.125, 1.25, 1.375, 1.5, 1.625, 1.75, 2.0, 2.5]
K_GRIDS = [(3, 5), (3, 7), (3, 9), (2, 7), (4, 7), (5, 9)]


def tight_sweep(market="US"):
    print(f"=== TIGHT_MULT, {market}: the four consequences on one grid\n")
    rows = []
    for v in GRID:
        a = H.accepted(H.scan(market, {"TIGHT_MULT": v}))
        sw = a.stopw_adr.replace([np.inf, -np.inf], np.nan).dropna()
        # what the trader actually sees: the decile gate runs first, and the sample is 400 of the
        # 1,966 US names, so the gated count is scaled back up to the real universe
        if market == "US":
            gt, cov = H.gated(a)
            n_cov = H.covered_names(market)
            real = H.per_night(gt) * (H.US_UNIVERSE / n_cov)
        else:
            gt = cov = a
            real = np.nan
        rows.append({
            "TIGHT_MULT": v,
            "accepted": len(a),
            "per_night": H.per_night(a),
            "gate_pass": (len(gt) / len(cov)) if len(cov) else np.nan,
            "real_night": real,
            "k_mean": float(a.cluster_k.mean()) if len(a) else np.nan,
            "k3_share": float((a.cluster_k == 3).mean()) if len(a) else np.nan,
            "stop_med": float(sw.median()) if len(sw) else np.nan,
            "stop_p90": float(sw.quantile(0.90)) if len(sw) else np.nan,
            # §7 caps the stop at 1 x ADR and calls anything wider a no-trade. Ticket 17 removed
            # ticket 08's D6 gate on exactly this quantity, so this column is what that cost.
            "stop_le_1.0": float((sw <= 1.0).mean()) if len(sw) else np.nan,
            "stop_le_1.5": float((sw <= 1.5).mean()) if len(sw) else np.nan,
            "rng_med": float(a.cluster_range_adr.median()) if len(a) else np.nan,
        })
    r = pd.DataFrame(rows)
    base = float(r.loc[r.TIGHT_MULT == 1.5, "accepted"].iloc[0])
    r["vs_default"] = r.accepted / base - 1.0

    print(f"  {'TIGHT':>6s} {'/night':>7s} {'gated':>7s} {'vs 1.5':>8s} {'k mean':>7s} {'k=3':>6s} "
          f"{'stop med':>9s} {'stop p90':>9s} {'§7 ok':>7s}")
    for _, x in r.iterrows():
        print(f"  {x.TIGHT_MULT:>6.3f} {x.per_night:>7.1f} {x.real_night:>7.1f} "
              f"{x.vs_default:>+7.1%} "
              f"{x.k_mean:>7.2f} {x['k3_share']:>5.0%} {x.stop_med:>9.2f} "
              f"{x.stop_p90:>9.2f} {x['stop_le_1.0']:>6.0%}")
    print("\n  '/night' is the raw detector on the 400-name sample; 'gated' is after ticket 06's")
    print("  decile gate and scaled to the full 1,966-name US universe — what the trader sees.")
    print("  '§7 ok' is the share whose trigger-to-cluster-low stop is within the method's 1 x ADR")
    print("  cap. TIGHT_MULT *is* the stop budget: the cluster spans <= TIGHT_MULT x ADR and the")
    print("  stop runs from the trigger to the cluster low, so the column is near-mechanical —")
    print("  which is the point. Ticket 08 gated this at 1.0 (D6); ticket 17 deleted that gate.")
    print(f"\n  swing across the grid: {r.vs_default.max() - r.vs_default.min():.0%} in list length")
    r.to_pickle(os.path.join(H.OUT, f"tight_{market}.pkl"))
    return r


def stop_gate_option():
    """What ticket 08's D6 would cost if restored on top of the split, rather than replaced by it.

    Ticket 17's argument for deleting D6 was that the cluster bounds the stop 'as a side effect
    rather than as a gate' — the separation the trader asked for. That argument is about *form*.
    This is the number about *substance*: at the default, how much of the list is outside §7?
    """
    print("\n=== restoring a §7 stop gate on top of TIGHT_MULT = 1.5\n")
    a = H.accepted(H.scan("US", {"TIGHT_MULT": 1.5}))
    sw = a.stopw_adr.replace([np.inf, -np.inf], np.nan)
    ok = sw <= 1.0
    print(f"  detections                     {len(a):,}")
    print(f"  within §7's 1 x ADR cap        {ok.mean():.1%}")
    print(f"  a D6-style gate would cut      {1 - ok.mean():.1%} of the nightly list")
    n_cov = H.covered_names("US")
    gt, cov = H.gated(a)
    gt2, _ = H.gated(a[ok.fillna(False)])
    scale = H.US_UNIVERSE / n_cov
    print(f"  gated list, full universe      {H.per_night(gt) * scale:.1f}/night  ->  "
          f"{H.per_night(gt2) * scale:.1f}/night")
    print(f"  (rank coverage: {n_cov} of {len(H.frames('US'))} sampled names)")
    print("\n  compare TIGHT_MULT = 1.0 above, which reaches the same cap by construction")
    print("  instead of by a second gate — one number rather than two, but it also re-tightens")
    print("  the cluster the rubric reads (k) and the digest's breakout lookback.")


def eye_on_looseness():
    """Does the trader's eye actually dislike a loose cluster?

    The 172 graded cards carry `cluster_range_adr`, so the question is answerable without new
    grading — and it is the only evidence that could make TIGHT_MULT a *fitted* number rather than
    a budget. Cards were selected under 1.5, so this sees the eye's response only within
    [0, 1.5]: it can say whether tightening is supported, never whether loosening is.
    """
    path = os.path.join(H.CACHE, "split_graded.pkl")
    if not os.path.exists(path):
        print("\n  (no graded set — skipped)")
        return
    g = pd.read_pickle(path)
    g = g[g.cluster_range_adr.notna() & g.eye.notna()].copy()
    g["eye"] = g.eye.astype(float)
    print(f"\n=== the eye against cluster looseness, n={len(g)} graded cards\n")
    r = float(np.corrcoef(g.cluster_range_adr, g.eye)[0, 1])
    print(f"  corr(cluster range in ADR, eye grade)  r = {r:+.3f}")
    print(f"  (negative would mean the eye punishes a loose cluster)\n")
    bins = [0, 0.75, 1.0, 1.25, 1.5]
    g["band"] = pd.cut(g.cluster_range_adr, bins)
    t = g.groupby("band", observed=True).eye.agg(["mean", "count"])
    print(f"  {'cluster range (ADR)':22s} {'mean eye':>9s} {'n':>5s}")
    for b, x in t.iterrows():
        print(f"  {str(b):22s} {x['mean']:>9.2f} {int(x['count']):>5d}")
    lo = g[g.cluster_range_adr <= 1.0].eye
    hi = g[g.cluster_range_adr > 1.0].eye
    if len(lo) > 5 and len(hi) > 5:
        p = welch_p(lo.to_numpy(float), hi.to_numpy(float))
        print(f"\n  tight (<=1.0 ADR, n={len(lo)}) {lo.mean():.2f}  vs  "
              f"loose (>1.0, n={len(hi)}) {hi.mean():.2f}   p = {p:.3f}")
        print("\n  the sign is the finding: every card here was selected under TIGHT_MULT = 1.5,")
        print("  so this can only speak about tightening, and it does not support it.")


def welch_p(a, b, iters=20000, seed=19):
    """Two-sided permutation p-value for a difference in means (no scipy in this venv)."""
    rng = np.random.default_rng(seed)
    obs = abs(a.mean() - b.mean())
    pool = np.concatenate([a, b])
    n = len(a)
    hits = 0
    for _ in range(iters):
        rng.shuffle(pool)
        if abs(pool[:n].mean() - pool[n:].mean()) >= obs - 1e-12:
            hits += 1
    return (hits + 1) / (iters + 1)


def k_sweep(market="US"):
    """The k range sets detection AND the digest's breakout lookback AND the rubric's tightness."""
    print(f"\n=== the k range, {market}: detection, digest lookback, rubric input\n")
    print(f"  {'K_MIN':>6s} {'K_MAX':>6s} {'/night':>7s} {'vs 3-7':>8s} {'k mean':>7s} "
          f"{'k med':>6s} {'stop med':>9s}")
    base = None
    for kmin, kmax in K_GRIDS:
        a = H.accepted(H.scan(market, {"K_MIN": kmin, "K_MAX": kmax}))
        if (kmin, kmax) == (3, 7):
            base = len(a)
        sw = a.stopw_adr.replace([np.inf, -np.inf], np.nan).dropna()
        d = f"{len(a) / base - 1:+7.1%}" if base else "      —"
        print(f"  {kmin:>6d} {kmax:>6d} {H.per_night(a):>7.1f} {d:>8s} "
              f"{a.cluster_k.mean():>7.2f} {a.cluster_k.median():>6.0f} "
              f"{sw.median():>9.2f}")
    print("\n  k is the effective breakout lookback (ticket 18 R3) and the rubric's tightness")
    print("  dimension (ticket 15 R1), so this grid moves the digest and the sort, not just the list.")


def main():
    r = tight_sweep("US")
    stop_gate_option()
    eye_on_looseness()
    k_sweep("US")


if __name__ == "__main__":
    main()
