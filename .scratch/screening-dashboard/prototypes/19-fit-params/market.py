"""Per-market: do these numbers transfer to IDX, or does the tape break the assumption?

Every parameter in the bill is expressed in ADR units and is therefore scale-free — which is the
argument for one set of numbers across both markets. The argument has a known hole: IDX's limit
days (ARA/ARB) and price quantization produce bars whose range is zero or a fixed tick, and a
zero-range bar makes the cluster look tight for a reason that has nothing to do with a tightening
base. Ticket 09 hit this at D13; ticket 15 then de-scoped it, having measured 98.1% of accepted IDX
detections carrying zero collapsed bars.

That measurement was made under the *old* detector. The cluster is selected to be tight, so it is
exactly the window a collapsed bar would sneak into — this re-measures it on the split.
"""

import os

import numpy as np
import pandas as pd

import harness as H
import split as S

GRID = [1.0, 1.25, 1.5, 1.75, 2.0]


def collapsed_bars():
    """How often is a cluster tight because the tape stopped moving rather than because it based?"""
    print("=== IDX: collapsed bars inside the cluster (the D13 hole, re-measured on the split)\n")
    a = H.accepted(H.scan("IDX"))
    frames = H.frames("IDX")
    zero = []
    for sym, g in a.groupby("symbol"):
        d = frames[sym]
        high = d["High"].to_numpy(float)
        low = d["Low"].to_numpy(float)
        for _, r in g.iterrows():
            as_of, k = int(r["end"]), int(r["cluster_k"])
            rng = high[as_of - k + 1:as_of + 1] - low[as_of - k + 1:as_of + 1]
            zero.append(int((rng <= 0).sum()))
    z = np.array(zero)
    print(f"  accepted IDX detections        {len(z):,}")
    if not len(z):
        return
    print(f"  clusters with 0 collapsed bars {(z == 0).mean():.1%}")
    print(f"  with 1                         {(z == 1).mean():.1%}")
    print(f"  with 2+                        {(z >= 2).mean():.1%}")
    print(f"  mean collapsed bars per cluster {z.mean():.3f} of k")
    print("\n  ticket 15 measured 98.1% clean under the old detector; the comparison above is")
    print("  what the split does to that, since the cluster is *selected* for tightness.")


def idx_sweep():
    print("\n=== TIGHT_MULT on IDX vs US: does the ADR normalisation transfer?\n")
    print(f"  {'TIGHT':>6s} {'IDX/night':>10s} {'vs 1.5':>8s} {'k mean':>7s} "
          f"{'stop med':>9s} {'§7 ok':>7s}")
    base = None
    rows = []
    for v in GRID:
        a = H.accepted(H.scan("IDX", {"TIGHT_MULT": v}))
        if v == 1.5:
            base = len(a)
        sw = a.stopw_adr.replace([np.inf, -np.inf], np.nan).dropna()
        d = f"{len(a) / base - 1:+7.1%}" if base else "      —"
        print(f"  {v:>6.2f} {H.per_night(a):>10.1f} {d:>8s} {a.cluster_k.mean():>7.2f} "
              f"{sw.median():>9.2f} {(sw <= 1.0).mean():>6.0%}")
        rows.append({"TIGHT_MULT": v, "n": len(a), "per_night": H.per_night(a),
                     "k_mean": float(a.cluster_k.mean()), "stop_med": float(sw.median()),
                     "s7": float((sw <= 1.0).mean())})
    pd.DataFrame(rows).to_pickle(os.path.join(H.OUT, "tight_IDX.pkl"))
    print("\n  compare the US grid: if the shapes match, one number serves both markets.")


def adr_levels():
    """A sanity check on the normalisation itself — is IDX's ADR distribution comparable?"""
    print("\n=== ADR distribution, both markets (the quantity every parameter divides by)\n")
    for m in ("US", "IDX"):
        a = H.accepted(H.scan(m))
        q = a.adr.quantile([0.1, 0.5, 0.9])
        print(f"  {m:4s} n={len(a):>7,}  ADR p10 {q.loc[0.1]:.3%}  median {q.loc[0.5]:.3%}  "
              f"p90 {q.loc[0.9]:.3%}")


def main():
    adr_levels()
    collapsed_bars()
    idx_sweep()


if __name__ == "__main__":
    main()
