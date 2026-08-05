"""The pre-registered round-3 analysis. Runs the moment the grades arrive.

    python analyse3.py A=<120 chars> [C=<58 chars>] [D=<46 chars>] [E=<206 chars>]

Each argument is the export string from the matching deck: one character per card, '1'-'5', or '-'
for ungraded. Everything it computes is fixed by PREREGISTRATION_R3.md (sections 1-7) and
PREREGISTRATION_R4.md (section 8); nothing here chooses a rule.

Self-test:  python analyse3.py --selftest   (synthetic grades, end to end)
"""

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
CACHE = os.path.join(P09, "cache")
sys.path.insert(0, P09)

from rubric3 import fit, score3, T3, GRIDS   # noqa: E402
from split_signals import signals_at, frames  # noqa: E402
import ranks as R                            # noqa: E402

RNG = np.random.default_rng(3)
K_PARTIAL_FLOOR = 0.15    # pre-registered: below this, tightness is declared unscorable
OVERFIT_TOL = 0.15


def manifest():
    """Decks A/C/D, plus deck E if it has been built. Two files so A3's graded string, which
    indexes by position into deck3_manifest.csv, cannot be disturbed by adding a deck."""
    mans = [pd.read_csv(os.path.join(HERE, "deck3_manifest.csv"))]
    e = os.path.join(HERE, "deckE_manifest.csv")
    if os.path.exists(e):
        mans.append(pd.read_csv(e))
    return pd.concat(mans, ignore_index=True)


def load_cards(grades):
    man = manifest()
    rows = []
    for deck, s in grades.items():
        sub = man[man.deck == deck].sort_values("card")
        if len(s) != len(sub):
            raise SystemExit(f"deck {deck}: got {len(s)} grades, deck has {len(sub)} cards")
        for (_, r), ch in zip(sub.iterrows(), s):
            if ch == "-":
                continue
            rows.append({**r.to_dict(), "eye": int(ch)})
    return pd.DataFrame(rows)


def attach_signals(cards):
    rk, _, _ = R.load_or_build()
    sectors = pd.read_pickle(os.path.join(CACHE, "sectors_us.pkl"))
    fr = {}
    out = []
    for _, r in cards.iterrows():
        if r.market not in fr:
            fr[r.market] = frames(r.market)
        d = fr[r.market].get(r.symbol)
        if d is None:
            continue
        sig = signals_at(d, int(r.end))
        if sig is None:
            continue
        pm = R.prior_move_pct(rk, r.symbol, r.date) if r.market == "US" else None
        ss = R.sector_share_loo(rk, sectors, r.symbol, r.date) if r.market == "US" else None
        out.append({**r.to_dict(), **sig, "prior_move": pm, "sector_share": ss})
    return pd.DataFrame(out)


def to_rows(df):
    return [{"sig": r.to_dict(), "prior_move": r.prior_move, "sector_share": r.sector_share,
             "eye": float(r.eye)} for _, r in df.iterrows()]


def stats(pred, eye):
    return {"r": float(np.corrcoef(pred, eye)[0, 1]) if pred.std() > 0 else np.nan,
            "mae": float(np.abs(pred - eye).mean()),
            "within1": float((np.abs(pred - eye) <= 1).mean()),
            "bias": float((pred - eye).mean())}


def cv(rows, mode="boolean", folds=5, drop=()):
    idx = RNG.permutation(len(rows))
    pred = np.zeros(len(rows))
    picked = []
    for f in range(folds):
        te = set(idx[f::folds].tolist())
        tr = [rows[i] for i in idx if i not in te]
        T, _ = fit(tr, mode, drop=drop)
        picked.append(T)
        for i in te:
            pred[i] = score3(rows[i]["sig"], rows[i]["prior_move"], rows[i]["sector_share"],
                             mode, T, drop=drop)["stars"]
    eye = np.array([r["eye"] for r in rows], float)
    return pred, eye, stats(pred, eye), picked


def partial_r(x, y, z):
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if m.sum() < 10:
        return np.nan
    x, y, z = x[m], y[m], z[m]
    rx = x - np.polyval(np.polyfit(z, x, 1), z)
    ry = y - np.polyval(np.polyfit(z, y, 1), z)
    return float(np.corrcoef(rx, ry)[0, 1]) if rx.std() and ry.std() else np.nan


def main(grades):
    cards = load_cards(grades)
    df = attach_signals(cards)
    core = df[(df.deck == "A") & df.split_ok]
    print(f"graded cards: {len(df)}  (deck A core, split-accepted: {len(core)})")

    # ---- 1. the pre-registered gate on the x2 tightness dimension
    pr = partial_r(core.cluster_k.to_numpy(float), core.eye.to_numpy(float),
                   core.base_len.to_numpy(float))
    print(f"\n=== 1. tightness gate — cluster k, partial r controlling base length: {pr:+.3f}")
    if not np.isfinite(pr) or pr < K_PARTIAL_FLOOR:
        print(f"  BELOW the pre-registered floor of +{K_PARTIAL_FLOOR:.2f}.")
        print("  The x2 tightness dimension is UNSCORABLE on this structure. It scores neutral,")
        print("  and ticket 17's R6 fallback goes to the trader. Say this loudly.")
    else:
        print(f"  clears the floor — k is the x2 tightness dimension.")

    # ---- 2. the fit
    rows = to_rows(core)
    print("\n=== 2. thresholds")
    T_all, _ = fit(rows, "boolean")
    ins = stats(np.array([score3(r["sig"], r["prior_move"], r["sector_share"], "boolean",
                                 T_all)["stars"] for r in rows]),
                np.array([r["eye"] for r in rows], float))
    results = {}
    for mode in ("boolean", "continuous"):
        pred, eye, st, folds = cv(rows, mode)
        results[mode] = (pred, eye, st, folds)
        print(f"  {mode:11s} out-of-fold  r {st['r']:+.3f}  mae {st['mae']:.2f}  "
              f"within1 {st['within1']:.0%}  bias {st['bias']:+.2f}")
    gap = results["boolean"][2]["mae"] - ins["mae"]
    print(f"  in-sample mae {ins['mae']:.2f} vs out-of-fold "
          f"{results['boolean'][2]['mae']:.2f}  (gap {gap:+.2f}, tolerance {OVERFIT_TOL})")
    if abs(gap) > OVERFIT_TOL:
        print("  OVERFITTED by the pre-registered test — no thresholds are published.")
    else:
        print(f"  fitted thresholds: {T_all}")
    for key in GRIDS:
        vals = [T[key] for T in results["boolean"][3]]
        print(f"    {key:14s} {T_all[key]:>6}   fold spread {min(vals)}-{max(vals)}")

    # ---- 3. boolean vs continuous, by the pre-registered rule
    b, c = results["boolean"][2], results["continuous"][2]
    wins = (c["mae"] <= b["mae"] - 0.10) and (c["within1"] > b["within1"])
    print(f"\n=== 3. boolean vs continuous: {'CONTINUOUS' if wins else 'BOOLEAN'} "
          f"(needs mae better by >=0.10 AND within-1 better)")

    # ---- 4. the 4-star cut
    print("\n=== 4. the trade threshold, out-of-fold")
    pred, eye = results["boolean"][0], results["boolean"][1]
    print(f"  {'cut':>6s} {'n':>5s} {'precision':>10s} {'recall':>8s}")
    for cut in (3.0, 3.5, 4.0, 4.5):
        flag = pred >= cut
        if flag.sum() == 0:
            continue
        prec = float((eye[flag] >= 4).mean())
        rec = float((flag & (eye >= 4)).sum() / max((eye >= 4).sum(), 1))
        print(f"  {cut:6.1f} {int(flag.sum()):5d} {prec:10.2f} {rec:8.2f}")

    # ---- 5. per-market
    # deck C also carries 6 US repeat cards for the ceiling — they are not IDX evidence
    idx = df[(df.deck == "C") & df.split_ok & (df.market == "IDX") & (df.tag != "repeat")]
    print(f"\n=== 5. per-market  (IDX cards graded: {len(idx)})")
    if len(idx) >= 20:
        ip = np.array([score3(r["sig"], r["prior_move"], r["sector_share"], "boolean",
                              T_all)["stars"] for r in to_rows(idx)])
        res_idx = float((ip - idx.eye.to_numpy(float)).mean())
        res_us = results["boolean"][2]["bias"]
        print(f"  mean residual: US {res_us:+.2f}  IDX {res_idx:+.2f}  "
              f"difference {abs(res_idx - res_us):.2f} (splits at 0.5)")
        print("  -> IDX needs its own thresholds" if abs(res_idx - res_us) > 0.5
              else "  -> one threshold set covers both markets, and that is the finding")
        lock = idx[idx.tag == "idx_locked"]
        if len(lock) >= 5:
            print(f"  partially limit-locked cards (n={len(lock)}, 1.8% of the population — "
                  f"descriptive only): mean eye {lock.eye.mean():.2f} vs "
                  f"{idx[idx.tag == 'idx_clean'].eye.mean():.2f} clean")
    else:
        print("  deck C ungraded — per-market calibration remains unanswered.")

    # ---- 6. rejects
    d = df[df.deck == "D"]
    print(f"\n=== 6. what the detector threw away  (deck D cards graded: {len(d)})")
    if len(d) >= 20:
        for tag, g in d.groupby("tag"):
            print(f"  {tag:28s} n={len(g):3d}  mean eye {g.eye.mean():.2f}  "
                  f">=4 star {(g.eye >= 4).mean():.0%}")
    else:
        print("  deck D ungraded — ticket 11's obligation still unowned.")

    # ---- 7. the ceiling
    reps = df[df.tag == "repeat"]
    print(f"\n=== 7. test-retest ceiling  (repeat cards graded: {len(reps)})")
    pairs = []
    for _, r in reps.iterrows():
        orig = df[(df.deck == "A") & (df.symbol == r.symbol) & (df.end == r.end)]
        if len(orig):
            pairs.append((float(orig.iloc[0].eye), float(r.eye)))
    if len(pairs) >= 6:
        a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
        ceil = float(np.corrcoef(a, b)[0, 1])
        print(f"  n={len(pairs)}  test-retest r = {ceil:+.3f}  "
              f"mean |difference| {np.abs(a - b).mean():.2f} stars")
        print("  BELOW 0.6 — thresholds are provisional whatever they fit."
              if ceil < 0.6 else "  every r above should be read against this ceiling.")
    else:
        print("  not measured. Every correlation above is against an UNMEASURED ceiling,")
        print("  and by the pre-registration no threshold is final until it is.")

    # ---- 8. the orderliness band's confirmation (PREREGISTRATION_R4.md)
    band_confirmation(df, T_all)


def r_se(r, n):
    """Standard error of a correlation. The +0.20 bar is a point-estimate threshold, so the
    distance from it is only meaningful next to this."""
    return float((1 - r ** 2) / np.sqrt(max(n - 1, 1))) if np.isfinite(r) else np.nan


def band_confirmation(df, T_a3):
    e = df[(df.deck == "E") & df.split_ok & (df.tag == "confirm")]
    print(f"\n=== 8. the orderliness band, on grades collected after R3 §6  "
          f"(deck E cards graded: {len(e)})")
    if len(e) < 60:
        print("  deck E ungraded or too thin — the band remains a HYPOTHESIS WITH FITTED NUMBERS,")
        print("  and ticket 15's +0.255 stays optimistic by R3 §6's own terms.")
        return

    rows = to_rows(e)

    # the decision number: the identical 5-fold procedure, refit on E alone (R4 §5)
    pred, eye, st, folds = cv(rows, "boolean")
    se = r_se(st["r"], len(rows))
    print(f"  DECISION  out-of-fold r {st['r']:+.3f} (se {se:.3f}, n={len(rows)})  "
          f"mae {st['mae']:.2f}  within1 {st['within1']:.0%}")
    credited = st["r"] >= 0.20
    if len(rows) < 120:
        print(f"  UNDERPOWERED — R4 §2 calls anything under 120 graded a report, not a verdict.")
    print("  -> the band is CREDITED: it reproduces on cards it was not fitted to."
          if credited else
          "  -> the band FAILS its pre-registered bar. By R3 §6 orderliness is DROPPED and its x2\n"
          "     redistributed. The refit without it is below.")

    # descriptive, and deliberately not the decision number (R4 §5)
    frozen = np.array([score3(r["sig"], r["prior_move"], r["sector_share"], "boolean",
                              T_a3)["stars"] for r in rows])
    fs = stats(frozen, eye)
    print(f"  descriptive: A3's thresholds applied FROZEN, no refit — r {fs['r']:+.3f}  "
          f"mae {fs['mae']:.2f}  bias {fs['bias']:+.2f}")

    o = e.orderliness.to_numpy(float)
    inside = (o >= T_a3["ord_lo"]) & (o <= T_a3["ord_hi"])
    print(f"  descriptive: {inside.mean():.0%} of E cards fall inside A3's band "
          f"[{T_a3['ord_lo']}, {T_a3['ord_hi']}]  (A3's failure mode was 99% inside a one-sided cut)")
    pr = partial_r(o, e.eye.to_numpy(float), e.base_len.to_numpy(float))
    print(f"  descriptive: orderliness partial r vs the eye, controlling base length: {pr:+.3f}")
    for key in ("ord_lo", "ord_hi"):
        vals = [T[key] for T in folds]
        print(f"    {key:8s} fold spread {min(vals)}-{max(vals)}")

    # what dropping it costs, reported whichever way the decision went (R4 §5)
    pred_d, eye_d, st_d, _ = cv(rows, "boolean", drop=("orderliness",))
    print(f"  orderliness DROPPED, x2 redistributed, refit on E: r {st_d['r']:+.3f}  "
          f"mae {st_d['mae']:.2f}  within1 {st_d['within1']:.0%}")
    print(f"  -> keeping the band is worth {st['r'] - st_d['r']:+.3f} r and "
          f"{st_d['mae'] - st['mae']:+.2f} mae on E")


def selftest():
    """End-to-end on synthetic grades, so the analysis is known-good before the real ones land."""
    man = manifest()
    g = {}
    decks = ("A", "C", "D", "E") if (man.deck == "E").any() else ("A", "C", "D")
    for deck in decks:
        n = (man.deck == deck).sum()
        g[deck] = "".join(str(int(x)) for x in RNG.integers(1, 6, n))
    print(f"self-test with random grades: "
          f"{ {k: len(v) for k, v in g.items()} }\n")
    main(g)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--selftest":
        selftest()
    elif args:
        main({a.split("=", 1)[0].upper(): a.split("=", 1)[1] for a in args})
    else:
        raise SystemExit(__doc__)
