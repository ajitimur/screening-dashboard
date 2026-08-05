"""POST HOC, NOT PRE-REGISTERED. Ticket 21, run after the R6 verdict was read.

R6 section 2's level guardrail blocked `cindex` by 0.01 stars: it ranks far better (+0.111 median
out-of-fold rho) and predicts levels worse (mae +0.16 against a 0.15 tolerance). That is the
signature of an objective that gets the ORDER right and the SCALE wrong -- which is a two-stage
problem, not a choice between two objectives.

This measures the two-stage fit: thresholds fitted under `cindex` on the training folds, then a
monotone (isotonic, PAVA) map from predicted score to stars fitted on the SAME training folds and
applied to the held-out fold. The ordering is untouched by construction -- isotonic regression is
monotone -- so rho can only change through ties, while mae is free to recover.

It is descriptive. It decides nothing: R6 was written before the grades were looked at and this was
not in it. Its job is to say whether the remedy is worth pre-registering in a round of its own.

    python posthoc_calibration.py
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from objective6 import (Fast, FOLDS, SEEDS, fit, load_cards, populations,   # noqa: E402
                        rows_of, spearman)


def pava(x, y, w):
    """Isotonic regression by pool-adjacent-violators, on (unique x, mean y, count) triples."""
    order = np.argsort(x, kind="mergesort")
    x, y, w = x[order], y[order], w[order]
    ys, ws, xs = list(y), list(w), list(x)
    i = 0
    while i < len(ys) - 1:
        if ys[i] > ys[i + 1] + 1e-12:
            tot = ws[i] + ws[i + 1]
            ys[i] = (ys[i] * ws[i] + ys[i + 1] * ws[i + 1]) / tot
            ws[i] = tot
            xs[i] = xs[i + 1]          # the block spans up to this knot
            del ys[i + 1], ws[i + 1], xs[i + 1]
            if i:
                i -= 1
        else:
            i += 1
    return np.array(xs), np.array(ys)


def fit_isotonic(pred, eye):
    """Monotone map from predicted score to stars, fitted on training-fold predictions."""
    vals, inv = np.unique(pred, return_inverse=True)
    means = np.array([eye[inv == i].mean() for i in range(len(vals))])
    counts = np.array([(inv == i).sum() for i in range(len(vals))], float)
    knots, fitted = pava(vals, means, counts)
    return knots, fitted


def apply_isotonic(knots, fitted, pred):
    idx = np.searchsorted(knots, pred, side="left")
    idx = np.clip(idx, 0, len(fitted) - 1)
    return np.clip(fitted[idx], 1.0, 5.0)


def run(rows, kind, calibrate):
    f = Fast(rows)
    eye = f.eye
    out = []
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(rows))
        pred = np.zeros(len(rows))
        for fold in range(FOLDS):
            te = idx[fold::FOLDS]
            tr = np.setdiff1d(np.arange(len(rows)), te)
            sub = Fast([rows[i] for i in tr])
            T, _ = fit(None, kind, fast=sub)
            p_all = f.predict(T)
            if calibrate:
                knots, fitted = fit_isotonic(p_all[tr], eye[tr])
                pred[te] = apply_isotonic(knots, fitted, p_all[te])
            else:
                pred[te] = p_all[te]
        out.append({"rho": spearman(pred, eye),
                    "mae": float(np.abs(pred - eye).mean()),
                    "within1": float((np.abs(pred - eye) <= 1).mean()),
                    "sd": float(np.std(pred))})
    med = lambda k: float(np.median([o[k] for o in out]))       # noqa: E731
    return {k: med(k) for k in ("rho", "mae", "within1", "sd")}


def main():
    rows = rows_of(populations(load_cards())["E3"], "E3")
    print(f"E3, n={len(rows)}.  POST HOC — decides nothing, R6 did not contain this.\n")
    print(f"  {'fit':34s} {'rho':>7s} {'mae':>6s} {'within1':>8s} {'pred sd':>8s}")
    base = None
    for kind in ("mae", "cindex"):
        for cal in (False, True):
            r = run(rows, kind, cal)
            label = f"{kind}" + (" + isotonic level map" if cal else "")
            print(f"  {label:34s} {r['rho']:+7.3f} {r['mae']:6.2f} {r['within1']:8.0%} "
                  f"{r['sd']:8.2f}")
            if kind == "mae" and not cal:
                base = r
    print(f"\n  R6 S2's guardrail was: mae may not exceed the incumbent's ({base['mae']:.2f}) "
          f"by more than 0.15 -> {base['mae'] + 0.15:.2f}")


if __name__ == "__main__":
    main()
