"""Ticket 26 — score deck F's cards with ticket 15's published rubric.

Ticket 25 measured the `line_not_drawable` arm against the EYE and found no separation. It never
asked what the MACHINE says about the same cards. That is the number ticket 26 needs, because the
remedy is a change to a ranking: if the rubric already sorts the marginal names below the accepted
ones, part of the penalty is already paid and a further demotion is double-counting; if it sorts
them level, the whole question is where the penalty goes.

Also recomputes ticket 15 R5's precision at the 4-star line separately per arm — R5's 0.53 was
measured before the population grew.

Usage: deckF_machine.py F=<grades string>
"""

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P15 = os.path.abspath(os.path.join(HERE, "..", "15-grading-round-2"))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
for p in (P15, P09):
    sys.path.insert(0, p)
CACHE = os.path.join(P09, "cache")

from rubric3 import score3                     # noqa: E402
from split_signals import signals_at, frames   # noqa: E402
import ranks as R                              # noqa: E402

# ticket 15 R4 / ROUND3_RESULTS.md — the published set, not rubric3.py's defaults
T_R3 = {"cluster_k": 4, "ord_lo": 0.275, "ord_hi": 0.50, "dryup": 0.90, "len_ok": 26}

ARMS = ["detection", "line_not_drawable", "not_caught_up"]


def load(grades):
    man = pd.read_csv(os.path.join(P15, "deckF_manifest.csv")).sort_values("card")
    if len(grades) != len(man):
        raise SystemExit(f"got {len(grades)} grades, deck has {len(man)} cards")
    man = man.assign(eye=[int(c) for c in grades])
    rk, _, _ = R.load_or_build()
    sectors = pd.read_pickle(os.path.join(CACHE, "sectors_us.pkl"))
    fr = frames("US")
    out = []
    for _, r in man.iterrows():
        d = fr.get(r.symbol)
        if d is None:
            continue
        sig = signals_at(d, int(r.end))
        if sig is None:
            continue
        pm = R.prior_move_pct(rk, r.symbol, r.date)
        ss = R.sector_share_loo(rk, sectors, r.symbol, r.date)
        s = score3({**sig, "adr": r.adr}, pm, ss, "boolean", T=T_R3)
        out.append({**r.to_dict(), "machine": s["stars"], "points": s["points"],
                    "prior_move": pm, "sector_share": ss})
    return pd.DataFrame(out)


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return d, se, (d - 1.96 * se, d + 1.96 * se)


def main(grades):
    df = load(grades)
    print(f"scored {len(df)} of 105 cards with ticket 15 R4 thresholds {T_R3}\n")

    print("=== machine star score by arm (the sort key ticket 11's list uses)")
    print(f"{'arm':20s} {'n':>3s} {'machine':>8s} {'eye':>6s} {'m>=4':>6s} {'eye>=4':>7s}")
    for tag in ARMS:
        d = df[df.tag == tag]
        if not len(d):
            continue
        print(f"{tag:20s} {len(d):3d} {d.machine.mean():8.2f} {d.eye.mean():6.2f} "
              f"{(d.machine >= 4).mean():6.0%} {(d.eye >= 4).mean():7.0%}")
    rep = df[df.tag.str.startswith("repeat")]
    if len(rep):
        print(f"{'repeats':20s} {len(rep):3d} {rep.machine.mean():8.2f} {rep.eye.mean():6.2f}")

    acc = df[df.tag == "detection"]
    for tag in ARMS[1:]:
        d = df[df.tag == tag]
        if not len(d):
            continue
        dd, se, ci = welch(d.machine, acc.machine)
        print(f"\n{tag} vs detections, MACHINE: {dd:+.2f}* (se {se:.2f}, "
              f"95% CI {ci[0]:+.2f} to {ci[1]:+.2f})")
        de, see, cie = welch(d.eye, acc.eye)
        print(f"{tag} vs detections, EYE:     {de:+.2f}* (se {see:.2f}, "
              f"95% CI {cie[0]:+.2f} to {cie[1]:+.2f})")

    print("\n=== agreement with the eye, per arm")
    for tag in ARMS:
        d = df[df.tag == tag]
        if len(d) < 3:
            continue
        r = np.corrcoef(d.machine, d.eye)[0, 1]
        print(f"{tag:20s} n={len(d):3d}  r = {r:+.3f}  mae = "
              f"{np.abs(d.machine - d.eye).mean():.2f}*")
    r_all = np.corrcoef(df.machine, df.eye)[0, 1]
    print(f"{'pooled':20s} n={len(df):3d}  r = {r_all:+.3f}  mae = "
          f"{np.abs(df.machine - df.eye).mean():.2f}*")

    print("\n=== ticket 15 R5's precision at the 4-star line, per arm")
    print("   (of cards the machine calls >=4*, share the eye also calls >=4*)")
    for tag in ARMS:
        d = df[df.tag == tag]
        call = d[d.machine >= 4]
        if not len(call):
            print(f"{tag:20s} machine never reaches 4* (n={len(d)})")
            continue
        print(f"{tag:20s} n_called={len(call):3d}  precision = "
              f"{(call.eye >= 4).mean():.2f}  recall = "
              f"{(call.eye >= 4).sum() / max((d.eye >= 4).sum(), 1):.2f}")
    mix = df[df.tag.isin(ARMS[:2])]
    call = mix[mix.machine >= 4]
    print(f"{'det + lnd merged':20s} n_called={len(call):3d}  precision = "
          f"{(call.eye >= 4).mean():.2f}")

    print("\n=== where the marginal names would land in a merged nightly sort")
    mix = mix.sort_values("machine", ascending=False)
    for top in (5, 10, 20, len(mix)):
        head = mix.head(top)
        print(f"top {top:3d} of the merged list: {(head.tag == 'line_not_drawable').mean():5.0%} "
              f"are line_not_drawable   (base rate "
              f"{(mix.tag == 'line_not_drawable').mean():.0%})")

    print("\n=== which rubric dimensions the marginal names differ on")
    dims = ["tightness", "orderliness", "base_length", "ma_support", "volume", "sector",
            "prior_move", "adr"]
    print(f"{'dimension':14s} " + "".join(f"{t[:12]:>14s}" for t in ARMS))
    for dim in dims:
        row = f"{dim:14s} "
        for tag in ARMS:
            d = df[df.tag == tag]
            vals = [p.get(dim) for p in d.points if p.get(dim) is not None]
            row += f"{np.mean(vals):14.2f}" if vals else f"{'-':>14s}"
        print(row)

    print("\n=== the sub-tests, machine view (classification copied from analyse_deckF.py)")
    d = df[df.tag == "line_not_drawable"].copy()
    z, o = d.touch_zones.fillna(0), d.overshoot_adr.fillna(0)
    groups = {"touches only": (z < 2) & (o <= 1.0),
              "overshoot only": (z >= 2) & (o > 1.0),
              "both": (z < 2) & (o > 1.0),
              "overshoot_frac only": (z >= 2) & (o <= 1.0)}
    det_m, det_e = acc.machine.mean(), acc.eye.mean()
    for lab, m in groups.items():
        g = d[m]
        if not len(g):
            print(f"  {lab:22s} n= 0")
            continue
        print(f"  {lab:22s} n={len(g):2d}  machine {g.machine.mean():.2f}* "
              f"(d {g.machine.mean()-det_m:+.2f})   eye {g.eye.mean():.2f}* "
              f"(d {g.eye.mean()-det_e:+.2f})")


if __name__ == "__main__":
    g = None
    for a in sys.argv[1:]:
        if a.startswith("F="):
            g = a[2:]
    if not g:
        raise SystemExit(__doc__)
    main(g)
