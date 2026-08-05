"""Arm 2 of PREREGISTRATION_R3.md §4's per-market rule, which analyse3.py does not compute.

    python per_market.py A=<120> C=<58> [E=<206>]

analyse3.py section 5 tests only arm 1 — whether the pooled fit's mean residual on IDX differs
from US by more than 0.5 stars. The rule has a second arm: IDX gets its own numbers if an
**IDX-only fit beats pooled on IDX cards by > 0.15 stars out-of-fold**. This runs that arm on the
same folds, the same objective and the same grids, and changes no rule.

Both arms must miss for one threshold set to cover both markets.
"""

import sys

import numpy as np

from analyse3 import RNG, attach_signals, load_cards, stats, to_rows
from rubric3 import fit, score3

FOLDS = 5
ARM2_BAR = 0.15
N_REPEATS = 25


def oof_idx(idx_rows, pooled_rows, mode="boolean"):
    """Out-of-fold predictions on the IDX cards under two fits.

    The folds are cut over the IDX cards only, so both arms are scored on exactly the same held-out
    cards. Pooled trains on the US core plus the IDX training folds; IDX-only trains on the IDX
    training folds alone. The held-out IDX cards are never in either training set.
    """
    n = len(idx_rows)
    order = RNG.permutation(n)
    pooled_pred, only_pred = np.zeros(n), np.zeros(n)
    only_T = []
    for f in range(FOLDS):
        te = set(order[f::FOLDS].tolist())
        tr = [idx_rows[i] for i in order if i not in te]
        T_pool, _ = fit(pooled_rows + tr, mode)
        T_only, _ = fit(tr, mode)
        only_T.append(T_only)
        for i in te:
            r = idx_rows[i]
            for T, out in ((T_pool, pooled_pred), (T_only, only_pred)):
                out[i] = score3(r["sig"], r["prior_move"], r["sector_share"], mode, T)["stars"]
    eye = np.array([r["eye"] for r in idx_rows], float)
    return pooled_pred, only_pred, eye, only_T


def main(grades):
    df = attach_signals(load_cards(grades))
    core = df[(df.deck == "A") & df.split_ok]
    idx = df[(df.deck == "C") & df.split_ok & (df.market == "IDX") & (df.tag != "repeat")]
    print(f"US core cards: {len(core)}   IDX cards: {len(idx)}")
    if len(idx) < 20:
        raise SystemExit("deck C ungraded or too small — arm 2 is not answerable")

    idx_rows, pooled_rows = to_rows(idx), to_rows(core)
    pooled_pred, only_pred, eye, only_T = oof_idx(idx_rows, pooled_rows)
    sp, so = stats(pooled_pred, eye), stats(only_pred, eye)

    print("\n=== arm 2 — IDX-only fit vs pooled, out-of-fold on the same IDX cards")
    for name, s in (("pooled", sp), ("IDX-only", so)):
        print(f"  {name:9s} mae {s['mae']:.3f}  r {s['r']:+.3f}  "
              f"within1 {s['within1']:.0%}  bias {s['bias']:+.2f}")
    gain = sp["mae"] - so["mae"]
    print(f"  IDX-only beats pooled by {gain:+.3f} stars (bar is > {ARM2_BAR})")
    print("  -> ARM 2 FIRES: IDX gets its own thresholds" if gain > ARM2_BAR
          else "  -> arm 2 misses: pooled is not beaten")

    print("\n  IDX-only thresholds by fold (a threshold that moves is not a threshold):")
    for key in only_T[0]:
        vals = [T[key] for T in only_T]
        print(f"    {key:14s} fold spread {min(vals)}-{max(vals)}")

    # descriptive: is the eye simply harsher on IDX, or does the rubric miss it?
    print(f"\n  descriptive: mean eye  US {core.eye.mean():.2f}  IDX {idx.eye.mean():.2f}")
    print(f"  descriptive: >=4 star  US {(core.eye >= 4).mean():.0%}  "
          f"IDX {(idx.eye >= 4).mean():.0%}")

    # How marginal is marginal? Ticket 20 had to discover the fold spread by hand; report it.
    # The bar is a point estimate, so the distance from it only means something next to the
    # spread of the statistic across fold assignments. This changes no rule.
    gains = []
    for _ in range(N_REPEATS):
        p, o, e, _ = oof_idx(idx_rows, pooled_rows)
        gains.append(float(np.abs(p - e).mean() - np.abs(o - e).mean()))
    gains = np.array(gains)
    fires = float((gains > ARM2_BAR).mean())
    print(f"\n  descriptive: over {N_REPEATS} fold assignments the arm-2 gain runs "
          f"{gains.min():+.3f} to {gains.max():+.3f}, median {np.median(gains):+.3f}")
    print(f"  descriptive: it clears the {ARM2_BAR} bar on {fires:.0%} of them")


if __name__ == "__main__":
    g = dict(a.split("=", 1) for a in sys.argv[1:] if "=" in a)
    main({k.upper(): v for k, v in g.items()})
