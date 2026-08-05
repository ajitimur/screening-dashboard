"""Refit the rubric on the split's structure — and measure whether the existing grades can do it.

Round 2's pre-registration fits thresholds by minimising mean |stars - eye| under 5-fold CV, and
sized the round at 114 cards to confirm an r of 0.26. Neither condition holds now:

  * the population changed. Only 81 of the 172 graded cards are setups the split would surface,
    and a rubric that ranks the nightly list has to be fitted on the list.
  * the two graded sets are not poolable at face value. Deck A was stratified on the OLD
    provisional score (24 cards per band, deliberately range-stretched); deck 17 was not. On the
    same population — names both detectors fire on — the two differ by +0.69 stars, p = 0.044.
    Mean absolute error is a level statistic, so a 0.7-star offset between the halves of the
    sample lands directly on every fitted threshold.

So this reports two things separately: the correlation, which survives a level offset, and the
thresholds, which do not. Fits are run on each source alone and pooled, and the disagreement
between them is the result.
"""

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
CACHE = os.path.join(P09, "cache")
sys.path.insert(0, P09)

from rubric3 import fit, score3, T3, GRIDS  # noqa: E402
from split_tightness import derive          # noqa: E402

RNG = np.random.default_rng(15)


def to_rows(df):
    out = []
    for _, r in df.iterrows():
        out.append({"sig": r.to_dict(), "prior_move": r.prior_move,
                    "sector_share": r.sector_share, "eye": float(r.eye)})
    return out


def evaluate(rows, T, mode="boolean"):
    pred = np.array([score3(r["sig"], r["prior_move"], r["sector_share"], mode, T)["stars"]
                     for r in rows])
    eye = np.array([r["eye"] for r in rows], float)
    r = float(np.corrcoef(pred, eye)[0, 1]) if pred.std() > 0 else np.nan
    return {"r": r, "mae": float(np.abs(pred - eye).mean()),
            "within1": float((np.abs(pred - eye) <= 1).mean()),
            "bias": float((pred - eye).mean()), "pred": pred, "eye": eye}


def cv(rows, mode="boolean", folds=5):
    """Out-of-fold predictions, exactly round 2's honesty rule."""
    idx = RNG.permutation(len(rows))
    pred = np.zeros(len(rows))
    picked = []
    for f in range(folds):
        te = idx[f::folds]
        tr = np.array([i for i in idx if i not in set(te.tolist())])
        T, _ = fit([rows[i] for i in tr], mode)
        picked.append(T)
        for i in te:
            pred[i] = score3(rows[i]["sig"], rows[i]["prior_move"], rows[i]["sector_share"],
                             mode, T)["stars"]
    eye = np.array([r["eye"] for r in rows], float)
    return {"r": float(np.corrcoef(pred, eye)[0, 1]), "mae": float(np.abs(pred - eye).mean()),
            "within1": float((np.abs(pred - eye) <= 1).mean()),
            "bias": float((pred - eye).mean()), "folds": picked}


def main():
    df = derive(pd.read_pickle(os.path.join(CACHE, "split_graded.pkl")))
    acc = df[df.split_ok].copy()

    sets = {
        "deck A split-accepts": acc[acc.source == "deckA"],
        "deck 17 split-accepts": acc[acc.source == "deck17"],
        "pooled": acc,
    }

    print("=== incumbent round-2 thresholds, re-pointed at the split's domain")
    for label, sub in sets.items():
        e = evaluate(to_rows(sub), T3)
        print(f"  {label:24s} n={len(sub):3d}  r {e['r']:+.3f}  mae {e['mae']:.2f}  "
              f"within1 {e['within1']:.0%}  bias {e['bias']:+.2f}")

    print("\n=== fitted thresholds, per source")
    fits = {}
    for label, sub in sets.items():
        rows = to_rows(sub)
        T, loss = fit(rows, "boolean")
        fits[label] = T
        e = evaluate(rows, T)
        print(f"  {label:24s} n={len(sub):3d}  {T}")
        print(f"  {'':24s}      in-sample r {e['r']:+.3f}  mae {e['mae']:.2f}")

    print("\n  threshold agreement across the two independent sources:")
    a, b = fits["deck A split-accepts"], fits["deck 17 split-accepts"]
    for key in GRIDS:
        flag = "" if a[key] == b[key] else "   <-- disagree"
        print(f"    {key:14s} deckA {a[key]:>6}   deck17 {b[key]:>6}{flag}")

    print("\n=== out-of-fold, pooled (round 2's honesty rule)")
    for mode in ("boolean", "continuous"):
        c = cv(to_rows(acc), mode)
        print(f"  {mode:11s} r {c['r']:+.3f}  mae {c['mae']:.2f}  "
              f"within1 {c['within1']:.0%}  bias {c['bias']:+.2f}")
        seen = {}
        for T in c["folds"]:
            for key, v in T.items():
                seen.setdefault(key, []).append(v)
        print(f"    fold-to-fold spread: "
              + "  ".join(f"{key} {min(v)}-{max(v)}" for key, v in seen.items()))

    # --- how much of the sample does the pre-registration actually need?
    print("\n=== what the pre-registration asked for, against what exists")
    sig = 1.96 / np.sqrt(max(len(acc) - 2, 1))
    print(f"  cards on the split's population: {len(acc)}  (deck A {len(sets['deck A split-accepts'])}"
          f" + deck 17 {len(sets['deck 17 split-accepts'])})")
    print(f"  significance needs |r| > {sig:.3f} at n={len(acc)}; "
          f"the pre-registration sized the round at 114 to confirm r = 0.26")
    print(f"  cards on IDX, any structure, any deck: 0")

    # --- the one dimension that is new: does adding it help at all?
    print("\n=== does the k-based tightness dimension earn its x2?")
    rows = to_rows(acc)
    base = cv(rows, "boolean")
    neutral = [{**r, "sig": {**r["sig"], "cluster_k": None}} for r in rows]
    off = cv(neutral, "boolean")
    print(f"  tightness scored from k     : r {base['r']:+.3f}  mae {base['mae']:.2f}")
    print(f"  tightness scored NEUTRAL    : r {off['r']:+.3f}  mae {off['mae']:.2f}")


if __name__ == "__main__":
    main()
