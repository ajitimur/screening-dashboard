"""What the restored §7 stop gate does to the population ticket 15 fitted the rubric on.

The gate was chosen partly on the argument that it disturbs ticket 15 *less* than re-tightening
TIGHT_MULT would, because it filters the population rather than redefining the geometry. That is
an argument, and it is cheap to check: if the surviving population's k distribution is badly
skewed, the rubric's tightness dimension is being fed something other than what it was fitted on,
and the difference between "filter" and "redefine" stops mattering.

Also prices the gate on IDX, since the decision applies to both markets.
"""

import numpy as np
import pandas as pd

import harness as H

CAP = 1.0


def shift(market="US"):
    a = H.accepted(H.scan(market, {"TIGHT_MULT": 1.5}))
    sw = a.stopw_adr.replace([np.inf, -np.inf], np.nan)
    keep = a[(sw <= CAP).fillna(False)]
    print(f"\n=== {market}: population before and after the 1 x ADR stop gate\n")
    print(f"  detections            {len(a):>8,}  ->  {len(keep):>8,}  "
          f"({len(keep) / len(a):.1%} survive)")
    print(f"  nightly (raw sample)  {H.per_night(a):>8.1f}  ->  {H.per_night(keep):>8.1f}")
    print()
    print(f"  {'quantity':22s} {'before':>9s} {'after':>9s} {'shift':>9s}")
    for col, label in (("cluster_k", "cluster k (rubric)"),
                       ("base_len", "base length"),
                       ("cluster_range_adr", "cluster range ADR"),
                       ("adr", "ADR"),
                       ("move_gain", "prior move %")):
        b, f = a[col].astype(float), keep[col].astype(float)
        print(f"  {label:22s} {b.mean():>9.2f} {f.mean():>9.2f} {f.mean() - b.mean():>+9.2f}")

    print(f"\n  k distribution (ticket 15's tightness dimension)")
    print(f"  {'k':>3s} {'before':>9s} {'after':>9s}")
    for k in range(3, 8):
        b = float((a.cluster_k == k).mean())
        f = float((keep.cluster_k == k).mean())
        print(f"  {k:>3d} {b:>8.1%} {f:>8.1%}")

    # the honest comparison: option B re-tightened k to a mean of 3.70 on US
    if market == "US":
        alt = H.accepted(H.scan("US", {"TIGHT_MULT": 1.0}))
        print(f"\n  for comparison, TIGHT_MULT = 1.0 (the option not taken): "
              f"k mean {alt.cluster_k.mean():.2f}")
        print(f"  the gate leaves k at {keep.cluster_k.mean():.2f} against "
              f"{a.cluster_k.mean():.2f} unfiltered")


def graded_check():
    """How many of ticket 15's 164 graded cards would the gate have removed?

    If the gate deletes most of the graded set, the rubric's fitted thresholds are calibrated on a
    population the screen no longer shows, and ticket 20 inherits a bigger job than it thinks.
    """
    import os
    path = os.path.join(H.CACHE, "split_graded.pkl")
    if not os.path.exists(path):
        return
    g = pd.read_pickle(path)
    g = g[g.stopw_adr.notna()].copy()
    keep = g[g.stopw_adr <= CAP]
    print(f"\n=== ticket 15's graded cards under the gate\n")
    print(f"  graded cards with a stop measured   {len(g)}")
    print(f"  within the 1 x ADR cap              {len(keep)} ({len(keep) / len(g):.0%})")
    if "eye" in g and len(keep) > 3:
        print(f"  mean eye grade, kept                {keep.eye.astype(float).mean():.2f}")
        print(f"  mean eye grade, removed             "
              f"{g[g.stopw_adr > CAP].eye.astype(float).mean():.2f}")
    print("\n  a low survival rate here does not invalidate ticket 15's fit, but it means the")
    print("  thresholds were fitted mostly on cards the gate now removes — which is a question")
    print("  for ticket 20, not this one.")


if __name__ == "__main__":
    shift("US")
    shift("IDX")
    graded_check()
