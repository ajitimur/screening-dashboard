"""The break is an event now, not a state — so can the same name be reported repeatedly?

`crossings.py` turned up a structural fact rather than a frequency: the trigger is
`max(line_at(t+1), cluster_high)` and `cluster_high` is the max high over the trailing k bars,
which includes today. So

    trigger_t >= cluster_high_t >= high_t >= close_t

for every detection, always. A detected name can never be sitting above its own trigger, which is
why `crossings.py` measures type 2 at exactly 0 and type 3 at 2 events in 29k detections. Ticket
14's three-way taxonomy is not merely depopulated — two of its three buckets are unreachable.

The consequence ticket 14 never faced: under D5 a broken name stayed above a descending line, so
`TRIGGERED` was absorbing. Under the clamp the cluster rolls up to include the breakout bar, so the
level jumps above the close and the name is `WATCHING` again the next night. That re-arms it — and
a name can therefore be reported on the digest more than once for the same move.

This measures how often that happens, which is what decides whether the digest needs a
de-duplication rule and whether ticket 08's D1 state model still describes anything.
"""

import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")


def main():
    c = pd.read_pickle(os.path.join(OUT, "crossings.pkl"))
    det = c[c.detected & c.trigger.notna()]

    print("=== is a detected name ever already above its own trigger?")
    above = det.close > det.trigger
    print(f"  detections           {len(det):,}")
    print(f"  close > trigger      {int(above.sum()):,}  ({above.mean():.4%})")
    print(f"  close > cluster-high-implied floor: unreachable by construction "
          f"(cluster high includes today's high)")
    print("  → ticket 14's types 2 and 3 are not rare, they are structurally impossible.")

    print("\n=== what happens to a name the night after it breaks?")
    c = c.sort_values(["market", "symbol", "end"]).reset_index(drop=True)
    g = c.groupby(["market", "symbol"], sort=False)
    nxt_det = g.detected.shift(-1)
    nxt_trig = g.trigger.shift(-1)
    nxt_close = g.close.shift(-1)
    nxt_end = g.end.shift(-1)
    contig_fwd = (nxt_end - c.end) == 1
    b = c[c.t1]
    m = c.t1 & contig_fwd
    print(f"  breaks (t1)                                   {int(c.t1.sum()):,}")
    print(f"  still detected the next night                 "
          f"{nxt_det[m].fillna(False).mean():6.1%}")
    sub = m & nxt_det.fillna(False)
    print(f"  ...and back below the new level (WATCHING)    "
          f"{(nxt_close[sub] <= nxt_trig[sub]).mean():6.1%}")
    rise = (nxt_trig[sub] - c.trigger[sub]) / (c.adr[sub] * c.close[sub])
    print(f"  ...median jump in the level that night        {rise.median():+.3f} ADR")

    print("\n=== how often is the same name reported again?")
    br = c[c.t1][["market", "symbol", "end", "date", "close"]].copy()
    br = br.sort_values(["market", "symbol", "end"])
    gap = br.groupby(["market", "symbol"]).end.diff()
    print(f"  reported breaks                               {len(br):,}")
    print(f"  names with >1 break in the window             "
          f"{(br.groupby(['market', 'symbol']).size() > 1).mean():6.1%} of reported names")
    for w in (1, 5, 10, 20):
        print(f"  breaks within {w:>2d} session(s) of the last one  "
              f"{(gap <= w).mean():6.1%}")
    print(f"  median gap between a name's breaks            "
          f"{gap.median():.0f} sessions" if gap.notna().any() else "")

    print("\n=== digest rows per night, with and without a de-duplication rule")
    for market in ("US", "IDX"):
        s = br[br.market == market]
        nights = c[c.market == market].date.nunique()
        names = c[c.market == market].symbol.nunique()
        if not len(s):
            continue
        scale = {"US": 1966, "IDX": 288}[market] / names
        raw = len(s) / nights
        # suppress a repeat within 20 sessions of the same name's previous report
        gp = s.groupby(["market", "symbol"]).end.diff()
        dedup = int((gp.isna() | (gp > 20)).sum()) / nights
        print(f"  {market:4s} every break {raw * scale:6.1f}/night   "
              f"first-per-20-sessions {dedup * scale:6.1f}/night   "
              f"({100 * (1 - dedup / raw):.0f}% of rows are repeats)")

    print("\n  NB: no decile gate applied (ticket 08 D15), so these are upper bounds on volume.")


if __name__ == "__main__":
    main()
