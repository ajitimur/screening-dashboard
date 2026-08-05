"""Does the split keep the setups the trader already graded highly?

Ticket 15's deck A is 120 blind grades on ticket 08's detections — human labels that already exist,
on cards drawn from the same grid the split was measured over. So before asking the eye anything
new, ask the labels we have: of the cards the trader called 4-5 star, how many does the split
still surface? Of the 1-2 star ones, how many does it drop?

A detector that keeps the eye's best and drops the eye's worst is an improvement even at J=0.16.
One that drops them at the same rate is a coin flip with extra parameters.

Deck A's tags matter: 'core' cards were sampled per star band from the round-2 rubric, and two
tagged arms (trigger already breached / trigger >= 2% above close) are the probes. All are 08
detections, so every card is by construction a name the split had the chance to accept.
"""

import os
import re
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
P15 = os.path.abspath(os.path.join(HERE, "..", "15-grading-round-2"))
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

MOVE_FLOOR = 25.0


def load_grades():
    txt = open(os.path.join(P15, "grades_A.txt")).read()
    g = {m.group(1): int(m.group(2)) for m in re.finditer(r"(A\d{3}):(\d)", txt)}
    man = pd.read_pickle(os.path.join(CACHE, "manifest_r2.pkl"))
    man = man[man.deck == "A"].copy()
    man["eye"] = man.cid.map(g)
    return man.dropna(subset=["eye"])


def main():
    man = load_grades()
    ov = pd.read_pickle(os.path.join(OUT, "overlap.pkl"))
    ov["date"] = pd.to_datetime(ov["date"]).dt.strftime("%Y-%m-%d")
    man["date"] = pd.to_datetime(man["date"]).dt.strftime("%Y-%m-%d")

    j = man.merge(ov, on=["market", "symbol", "date"], how="left", suffixes=("", "_o"))
    j["split_floor"] = j.split_floor.fillna(False).astype(bool)
    j["split_ok"] = j.split_ok.fillna(False).astype(bool)
    print(f"=== deck A: {len(man)} graded cards, {j.split_ok.notna().sum()} joined to the split scan")
    unmatched = j.sp_base_len.isna().sum()
    print(f"    {unmatched} cards the split scan never evaluated (grid or history edge)")

    print("\nsplit acceptance by the trader's grade")
    print(f"  {'eye':>4s} {'n':>5s} {'split accepts':>14s} {'+ >=25% move':>14s}")
    for s in sorted(j.eye.dropna().unique()):
        sub = j[j.eye == s]
        print(f"  {int(s):>4d} {len(sub):>5d} {sub.split_ok.mean():>13.1%} {sub.split_floor.mean():>14.1%}")
    hi, lo = j[j.eye >= 4], j[j.eye <= 2]
    print(f"\n  4-5 star ({len(hi):>3d} cards): split keeps {hi.split_ok.mean():.1%}"
          f"  (with floor {hi.split_floor.mean():.1%})")
    print(f"  1-2 star ({len(lo):>3d} cards): split keeps {lo.split_ok.mean():.1%}"
          f"  (with floor {lo.split_floor.mean():.1%})")
    d = hi.split_ok.mean() - lo.split_ok.mean()
    print(f"  discrimination (keep-rate gap, best minus worst): {d:+.1%}")
    print("  a cut that is blind to the eye shows ~0 here; a good one is strongly positive")

    # Where the split does drop a card the eye liked, which clause did it?
    drop = j[(j.eye >= 4) & ~j.split_ok & j.sp_base_len.notna()]
    if len(drop):
        print(f"\nwhich clause drops the {len(drop)} well-graded cards the split refuses")
        for lab, mask in (("no tight 3-7 bar cluster", ~drop.tight.fillna(False).astype(bool)),
                          ("not caught up to the 10/20", ~drop.caught_up.fillna(False).astype(bool)),
                          ("line not drawable", ~drop.line_ok.fillna(False).astype(bool))):
            print(f"  {lab:30s} {mask.sum():>4d}  {mask.mean():6.1%}")

    # The same question against the round-2 machine score, as a control: if the split tracks the
    # rubric but not the eye, it is inheriting the very bias ticket 09 found.
    pool = pd.concat([pd.read_pickle(os.path.join(CACHE, "pool_us.pkl")),
                      pd.read_pickle(os.path.join(CACHE, "pool_idx.pkl"))], ignore_index=True)
    pool["date"] = pd.to_datetime(pool["date"]).dt.strftime("%Y-%m-%d")
    k = pool.merge(ov[["market", "symbol", "date", "split_ok", "split_floor", "sp_base_len"]],
                   on=["market", "symbol", "date"], how="left")
    k["split_ok"] = k.split_ok.fillna(False).astype(bool)
    print("\ncontrol — split acceptance by the round-2 machine score, whole pool")
    print(f"  {'stars2':>6s} {'n':>7s} {'split accepts':>14s}")
    for s in sorted(k.stars2.dropna().unique()):
        sub = k[k.stars2 == s]
        print(f"  {int(s):>6d} {len(sub):>7,} {sub.split_ok.mean():>13.1%}")

    j.to_pickle(os.path.join(OUT, "graded_join.pkl"))


if __name__ == "__main__":
    main()
