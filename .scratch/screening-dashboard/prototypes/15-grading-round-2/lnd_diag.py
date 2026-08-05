"""Ticket 25 diagnostics — what `line_not_drawable` actually rejects, and what it costs.

Three things the pre-registration needs before deck F is designed:

  1. base rates: how big is this rejection path, absolutely and relative to the nightly list
  2. the decile confound: build_deck3.rejects() does NOT apply D15's decile gate while
     population() does, so ticket 23's two arms were drawn from different populations
  3. the price of the remedy: what does dropping or loosening `line_ok` do to list length

Nothing here is a grade. It is the arithmetic the deck's design rests on.
"""

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
for p in (P09, P16):
    sys.path.insert(0, p)
CACHE = os.path.join(P09, "cache")

import ranks as R                            # noqa: E402

DECILE = 0.90
MOVE_FLOOR = 25.0
SCALE = 3.0          # split.pkl is a 1-in-3 bar-date sweep


def main():
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp["date"] = pd.to_datetime(sp.date).dt.strftime("%Y-%m-%d")
    print(f"{len(sp):,} bar-dates evaluated  ({sp.market.value_counts().to_dict()})")

    # ---------------------------------------------------------------- 1. base rates
    print("\n=== 1. the funnel, per market (share of evaluated bar-dates)")
    for m in ("US", "IDX"):
        d = sp[sp.market == m]
        acc = d.tight & d.line_ok & d.caught_up
        print(f"\n  {m}   n={len(d):,}")
        for lab, mask in (("has_base", d.has_base),
                          ("  & move >= 25%", d.has_base & (d.move_gain >= MOVE_FLOOR)),
                          ("  & tight cluster", d.tight & (d.move_gain >= MOVE_FLOOR)),
                          ("  & line drawable", d.tight & d.line_ok & (d.move_gain >= MOVE_FLOOR)),
                          ("  & caught up (accepted)", acc & (d.move_gain >= MOVE_FLOOR))):
            print(f"    {lab:26s} {mask.mean():7.2%}  {int(mask.sum()):>8,}")

    print("\n=== 2. the three rejection paths, among has_base & move >= 25%")
    for m in ("US", "IDX"):
        d = sp[(sp.market == m) & sp.has_base & (sp.move_gain >= MOVE_FLOOR)].copy()
        d["reason"] = np.where(~d.tight, "no_cluster",
                               np.where(~d.line_ok, "line_not_drawable",
                                        np.where(~d.caught_up, "not_caught_up", "ACCEPTED")))
        vc = d.reason.value_counts()
        print(f"\n  {m}   n={len(d):,}")
        for k in ("ACCEPTED", "no_cluster", "line_not_drawable", "not_caught_up"):
            print(f"    {k:20s} {vc.get(k, 0):>8,}  {vc.get(k, 0)/len(d):7.2%}")

    # ------------------------------------------------- 3. the decile confound in deck D3
    print("\n=== 3. D15's decile gate — applied to the detections arm, not the rejects arm")
    rk, _, _ = R.load_or_build()
    us = sp[(sp.market == "US") & sp.has_base & (sp.move_gain >= MOVE_FLOOR)].copy()
    us["reason"] = np.where(~us.tight, "no_cluster",
                            np.where(~us.line_ok, "line_not_drawable",
                                     np.where(~us.caught_up, "not_caught_up", "ACCEPTED")))
    # sample rather than score all of it — prior_move_pct is a per-row lookup
    rng = np.random.default_rng(25)
    print("\n  share of each path that would clear prior_move >= 0.90 (1,500-row samples):")
    for reason in ("ACCEPTED", "no_cluster", "line_not_drawable", "not_caught_up"):
        pool = us[us.reason == reason]
        if not len(pool):
            continue
        take = pool.iloc[rng.permutation(len(pool))[:1500]]
        pm = [R.prior_move_pct(rk, r.symbol, r.date) for _, r in take.iterrows()]
        pm = np.array([np.nan if v is None else v for v in pm], dtype=float)
        ok = np.nanmean(pm >= DECILE)
        print(f"    {reason:20s} n={len(take):>5,}  clears decile {ok:7.2%}  "
              f"median pm {np.nanmedian(pm):.3f}")

    # ---------------------------------------------- 4. what loosening line_ok would cost
    print("\n=== 4. the price of the remedy — nightly US list length")
    d = sp[(sp.market == "US") & (sp.move_gain >= MOVE_FLOOR)]
    nights = d.date.nunique()
    acc = d[d.tight & d.line_ok & d.caught_up]
    drop = d[d.tight & d.caught_up]                       # line_ok removed entirely
    print(f"  nights sampled: {nights:,}  (1-in-3 sweep, so per-night counts x{SCALE:.0f})")
    print(f"  as specified            {len(acc)/nights*SCALE:7.1f} names/night")
    print(f"  line_ok dropped         {len(drop)/nights*SCALE:7.1f} names/night  "
          f"(x{len(drop)/max(len(acc),1):.2f})")

    print("\n  the components of line_ok, among tight & caught_up & move>=25% (US):")
    t = d[d.tight & d.caught_up]
    if "touch_zones" in t:
        z = t.touch_zones.fillna(0)
        o = t.overshoot_adr.fillna(0)
        print(f"    touch_zones >= 2        {(z >= 2).mean():7.2%}")
        print(f"    touch_zones >= 1        {(z >= 1).mean():7.2%}")
        print(f"    overshoot <= 1.0 ADR    {(o <= 1.0).mean():7.2%}")
        print(f"    line_ok (all of it)     {t.line_ok.mean():7.2%}")
        rej = t[~t.line_ok]
        print(f"\n    among the {len(rej):,} line_not_drawable rows:")
        print(f"      failed on touches only    "
              f"{((rej.touch_zones.fillna(0) < 2) & (rej.overshoot_adr.fillna(0) <= 1.0)).mean():7.2%}")
        print(f"      failed on overshoot only  "
              f"{((rej.touch_zones.fillna(0) >= 2) & (rej.overshoot_adr.fillna(0) > 1.0)).mean():7.2%}")
        print(f"      failed on both            "
              f"{((rej.touch_zones.fillna(0) < 2) & (rej.overshoot_adr.fillna(0) > 1.0)).mean():7.2%}")
        print(f"      neither (overshoot_frac)  "
              f"{((rej.touch_zones.fillna(0) >= 2) & (rej.overshoot_adr.fillna(0) <= 1.0)).mean():7.2%}")

    # ------------------------------------------------- 5. is the path a base-length proxy?
    print("\n=== 5. base length, by path (US, move>=25%)")
    for reason in ("ACCEPTED", "no_cluster", "line_not_drawable", "not_caught_up"):
        pool = us[us.reason == reason]
        if len(pool):
            print(f"    {reason:20s} median {pool.base_len.median():5.1f} bars   "
                  f"mean {pool.base_len.mean():5.1f}   n={len(pool):,}")


if __name__ == "__main__":
    main()
