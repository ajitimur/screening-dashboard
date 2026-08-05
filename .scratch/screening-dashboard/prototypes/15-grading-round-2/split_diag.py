"""Three questions the grades cannot answer, and one they can.

1. Are cluster length k and cluster churn the same signal? Both survive the length control at
   +0.327. If they are collinear, the ticket has one new dimension, not two.
2. Is k's relationship with the eye monotone? k takes five values (3-7) and 36.6% of the
   population sits at 3, so a boolean cut has to land somewhere defensible.
3. Does D10's MA distance still carry information once the split's own MA catch-up test has
   already gated? Ticket 17's R3 flagged the overlap and left it here.
"""

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
CACHE = os.path.join(P09, "cache")
sys.path.insert(0, P09)

from split_tightness import derive, partial, corr, perm_p  # noqa: E402


def main():
    df = derive(pd.read_pickle(os.path.join(CACHE, "split_graded.pkl")))
    acc = df[df.split_ok]
    eye = acc.eye.to_numpy(float)
    blen = acc.base_len.to_numpy(float)

    # ---- 1. collinearity
    print("=== 1. cluster length k vs cluster churn")
    k = acc.cluster_k.to_numpy(float)
    cc = acc.cluster_churn.to_numpy(float)
    print(f"  r(k, cluster churn) = {corr(k, cc)[0]:+.3f}")
    print(f"  partial r(cluster churn, eye | base len, k) = "
          f"{partial(cc - np.polyval(np.polyfit(k, cc, 1), k), eye, blen)[0]:+.3f}")
    print("  (churn over a window of fixed range is bar count in disguise — the cluster's range is")
    print("   fixed at <= TIGHT_MULT x ADR by selection, so both measure packing, not width)")

    # ---- 2. shape of k
    print("\n=== 2. does the eye rise monotonically in k?")
    print(f"{'k':>3s} {'n':>5s} {'mean eye':>9s} {'>=4 star':>9s}")
    for kv in sorted(acc.cluster_k.dropna().unique()):
        s = acc[acc.cluster_k == kv]
        print(f"{int(kv):3d} {len(s):5d} {s.eye.mean():9.2f} {(s.eye >= 4).mean():9.1%}")
    for cut in (4, 5, 6):
        lo = acc[acc.cluster_k < cut].eye
        hi = acc[acc.cluster_k >= cut].eye
        if len(lo) >= 5 and len(hi) >= 5:
            print(f"  boolean cut k >= {cut}: {hi.mean() - lo.mean():+.2f} stars "
                  f"(n={len(lo)} below, {len(hi)} at or above)")

    # ---- 3. D10 redundancy, measured on the population rather than the grades
    print("\n=== 3. D10 MA distance against the split's own catch-up gate")
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    surv = sp[sp.tight & sp.line_ok & sp.caught_up]
    print(f"  the catch-up test passes on {sp.caught_up.mean():.1%} of all bar-dates and is a GATE,")
    print(f"  so 100% of the {len(surv):,} surviving detections already satisfy it.")

    d = acc
    md = d.ma_dist_adr.to_numpy(float)
    fin = np.isfinite(md)
    print(f"\n  |MA distance| on graded split-accepts: median {np.median(np.abs(md[fin])):.2f} ADR, "
          f"IQR {np.percentile(np.abs(md[fin]), 25):.2f}-{np.percentile(np.abs(md[fin]), 75):.2f}")
    for t in (0.6, 1.0, 1.5, 2.0):
        print(f"    share passing round 2's boolean |ma_dist| <= {t}: "
              f"{(np.abs(md[fin]) <= t).mean():.1%}")
    r_eye, n = corr(md, eye)
    pr, _ = partial(md, eye, blen)
    print(f"  r(ma_dist, eye) = {r_eye:+.3f}   partial | base len = {pr:+.3f}   "
          f"perm p = {perm_p(md, eye, blen):.3f}  (n={n})")
    g10 = acc.gap10_adr.to_numpy(float)
    g20 = acc.gap20_adr.to_numpy(float)
    print(f"  r(ma_dist, close-to-SMA10 gap) = {corr(md, g10)[0]:+.3f}    "
          f"r(ma_dist, close-to-SMA20 gap) = {corr(md, g20)[0]:+.3f}")
    print(f"  r(SMA20 rising, eye) = "
          f"{corr(acc.sma20_rising.astype(float).to_numpy(), eye)[0]:+.3f}   "
          f"share rising: {acc.sma20_rising.mean():.1%}")


if __name__ == "__main__":
    main()
