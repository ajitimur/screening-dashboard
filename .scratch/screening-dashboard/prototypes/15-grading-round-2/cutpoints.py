"""Ticket 27: where does the 4-star line land once `cindex` moves the thresholds?

Ticket 27 settled two things by trader's call:

  1. the star number is a **label for a rank plus its cut points** — nothing in v1 reads the
     magnitude, so R6 section 2's mae guardrail was defending a property nothing consumes and
     `cindex` is adopted;
  2. **section 3.5's points/2 mapping stands unchanged** — no isotonic stage, no separately fitted
     band boundaries, no new tunable.

Choice 2 leaves exactly one number open, and it is a *consequence* of the decision rather than an
input to it: ticket 15 R5 measured precision at the 4-star cut as 0.53 under the incumbent `T3`
thresholds, and that is the number ticket 11's screen depends on. Under `cindex`'s thresholds the
printed level is no longer what any loss controlled, so the cut has to be re-read.

**This is reporting, not fitting.** Nothing here chooses a threshold, a cut or a rule. The
thresholds are the ones `objective6` already published; the cuts are the four `analyse3` already
prints. Anything that looks like a new decision belongs in a pre-registration, not here.
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import objective6 as O6                                   # noqa: E402
from rubric3 import T3                                    # noqa: E402

# `cindex` on E3 and on the pooled 366, as OBJECTIVE_FINDINGS.md F1 reports them.
T_CINDEX_E3 = {**T3, "cluster_k": 5, "ord_lo": 0.30, "ord_hi": 0.60, "dryup": 0.85, "len_ok": 20}
T_CINDEX_POOLED = {**T3, "cluster_k": 5, "ord_lo": 0.30, "ord_hi": 0.70, "dryup": 0.85, "len_ok": 20}

CUTS = (3.0, 3.5, 4.0, 4.5)
TRADE_CUT = 4.0


def cut_table(pred, eye):
    """Precision and recall against the eye's own 4-star line, at each printed cut."""
    rows = []
    for cut in CUTS:
        flag = pred >= cut
        n = int(flag.sum())
        if n == 0:
            rows.append((cut, 0, float("nan"), 0.0))
            continue
        prec = float((eye[flag] >= 4).mean())
        rec = float((flag & (eye >= 4)).sum() / max((eye >= 4).sum(), 1))
        rows.append((cut, n, prec, rec))
    return rows


def show(label, pred, eye):
    print(f"\n--- {label}   (n={len(eye)})")
    print(f"    printed stars: mean {pred.mean():.2f}  SD {pred.std():.2f}  "
          f"min {pred.min():.2f}  max {pred.max():.2f}")
    print(f"    share printed >= 4.0: {float((pred >= TRADE_CUT).mean()):.1%}   "
          f"eye >= 4: {float((eye >= 4).mean()):.1%}")
    print(f"    mae {float(np.abs(pred - eye).mean()):.2f}   "
          f"bias {float((pred - eye).mean()):+.2f}   "
          f"rho {O6.spearman(pred, eye):+.3f}")
    print(f"      {'cut':>5s} {'n':>5s} {'precision':>10s} {'recall':>8s}")
    for cut, n, prec, rec in cut_table(pred, eye):
        print(f"      {cut:5.1f} {n:5d} {prec:10.2f} {rec:8.2f}")


def out_of_fold(rows, kind, seeds=O6.SEEDS):
    """Median-over-assignments out-of-fold prediction, so the cut is read the way R5 read it.

    Averaging predictions across fold assignments would smooth the very quantity being measured,
    so each assignment is scored separately and the *median* cut statistic is reported.
    """
    f = O6.Fast(rows)
    preds = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        idx = rng.permutation(len(rows))
        pred = np.zeros(len(rows))
        for fold in range(O6.FOLDS):
            te = idx[fold::O6.FOLDS]
            tr = np.setdiff1d(np.arange(len(rows)), te)
            sub = O6.Fast([rows[i] for i in tr])
            T, _ = O6.fit(None, kind, fast=sub)
            pred[te] = f.predict(T)[te]
        preds.append(pred)
    return preds, f.eye


def main():
    df = O6.load_cards()
    pops = O6.populations(df)
    e3 = O6.rows_of(pops["E3"], "E3")
    pooled = O6.rows_of(pops["A3"], "A3") + e3 + O6.rows_of(pops["C3"], "C3")

    print("=" * 78)
    print("Ticket 27: the 4-star cut under the adopted objective")
    print("=" * 78)
    print(f"E3 cards {len(e3)}   pooled {len(pooled)}")

    O6.assert_matches_score3(pooled)
    print("Fast/score3 agreement asserted on the pooled population.")

    # ---- 1. frozen thresholds, no fitting at all: the cleanest read of the decision
    print("\n\n=== 1. FROZEN thresholds applied to E3 (no fitting, no folds)")
    f = O6.Fast(e3)
    eye = f.eye
    show("incumbent T3 (ticket 15, R5 measured 0.53 here)", f.predict(T3), eye)
    show("cindex thresholds, E3 fit", f.predict(T_CINDEX_E3), eye)
    show("cindex thresholds, pooled fit", f.predict(T_CINDEX_POOLED), eye)

    # ---- 2. out-of-fold, the way R5's 0.53 was produced
    print("\n\n=== 2. OUT-OF-FOLD, 5 assignments x 5 folds")
    for kind in ("mae", "cindex"):
        preds, eye = out_of_fold(e3, kind)
        stats = [cut_table(p, eye) for p in preds]
        prec = [s[CUTS.index(TRADE_CUT)][2] for s in stats]
        rec = [s[CUTS.index(TRADE_CUT)][3] for s in stats]
        n = [s[CUTS.index(TRADE_CUT)][1] for s in stats]
        print(f"\n--- {kind}: precision at {TRADE_CUT}*  "
              f"median {np.nanmedian(prec):.2f}  range {np.nanmin(prec):.2f}-{np.nanmax(prec):.2f}")
        print(f"    recall    median {np.median(rec):.2f}   "
              f"n called median {int(np.median(n))}")

    # ---- 3. the pooled population, since ticket 21 unlocked it on a rank criterion
    print("\n\n=== 3. FROZEN thresholds on the pooled 366")
    fp = O6.Fast(pooled)
    show("incumbent T3", fp.predict(T3), fp.eye)
    show("cindex thresholds, pooled fit", fp.predict(T_CINDEX_POOLED), fp.eye)


if __name__ == "__main__":
    main()
