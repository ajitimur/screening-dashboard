"""Where the trigger comes from, and what that does to attribution.

Ticket 14's A2 excluded type-2 crossings on an *attribution* argument, not a frequency one:
ticket 08's D5 chose the lower of two levels deliberately so the trigger would descend, so a
crossing caused by the descent is the parameter choice reporting itself back to you.

Ticket 17's clamp takes the *upper* of the two, and ticket 16 measured the cluster high winning on
82% of detections. Where the cluster high wins, the level is a price the tape actually printed and
it cannot descend — it only moves when the cluster rolls. Where the line wins (the other 18%), the
old argument survives intact. So the attribution question now has two regimes, and this measures
their sizes and their crossing behaviour separately.

Re-derives cluster_high and line_end for each detection in `out/daily.pkl` (split.scan returns
neither, but cluster_k is enough to recover the first, and the trigger is the max of the two).
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit")))
OUT = os.path.join(HERE, "out")

import split as S  # noqa: E402
from crossings import sample, classify, N_US, N_IDX  # noqa: E402


def add_clamp(c):
    """cluster_high per row, recovered from cluster_k against the name's own bars."""
    frames = {("US", s): d for s, d in sample("US", N_US).items()}
    frames.update({("IDX", s): d for s, d in sample("IDX", N_IDX).items()})
    ch = np.full(len(c), np.nan)
    end = c.end.to_numpy()
    k = c.cluster_k.to_numpy()
    keys = list(zip(c.market, c.symbol))
    hi_cache = {key: d["High"].to_numpy(float) for key, d in frames.items()}
    for i in range(len(c)):
        if not np.isfinite(k[i]):
            continue
        h = hi_cache.get(keys[i])
        if h is None:
            continue
        a, kk = int(end[i]), int(k[i])
        ch[i] = h[a - kk + 1:a + 1].max()
    c = c.copy()
    c["cluster_high"] = ch
    # the trigger is max(line_end, cluster_high); if it equals the cluster high, the clamp bound
    c["clamped"] = np.isclose(c.trigger, c.cluster_high, rtol=0, atol=1e-9)
    c["line_end"] = np.where(c.clamped, np.nan, c.trigger)
    return c


def main():
    c = pd.read_pickle(os.path.join(OUT, "crossings.pkl"))
    c = add_clamp(c)
    det = c[c.detected & c.trigger.notna()]
    print(f"=== {len(det):,} detections")
    print(f"  trigger == cluster high (clamp binds) {det.clamped.mean():7.1%}   "
          f"(ticket 16 measured 82% on its sample)")
    print(f"  trigger == extrapolated line          {1 - det.clamped.mean():7.1%}")

    print("\n=== how the level moves, split by regime (contiguous detected pairs)")
    d = c[c.dtrig.notna()]
    for lab, sub in (("clamped tonight", d[d.clamped]), ("line tonight", d[~d.clamped]),
                     ("all", d)):
        t = 1e-9
        print(f"  {lab:18s} n={len(sub):>7,}  rose {(sub.dtrig > t).mean():6.1%}  "
              f"fell {(sub.dtrig < -t).mean():6.1%}  flat {(sub.dtrig.abs() <= t).mean():6.1%}  "
              f"median {sub.dtrig_adr.median():+.3f} ADR")

    print("\n=== the crossing types, split by regime")
    print(f"  {'':18s} {'t1':>8s} {'t2':>8s} {'t3':>8s} {'t4':>8s}")
    for lab, sub in (("clamped", c[c.clamped]), ("line", c[~c.clamped & c.detected])):
        print(f"  {lab:18s} {int(sub.t1.sum()):>8,} {int(sub.t2.sum()):>8,} "
              f"{int(sub.t3.sum()):>8,} {int(sub.t4.sum()):>8,}")

    print("\n=== does a type-1 break survive holding the line still?")
    b = c[c.t1]
    print(f"  reported breaks n = {len(b):,}")
    print(f"    also clear tonight's level (close > trigger_t)  {(b.close > b.trigger).mean():6.1%}")
    print(f"    median % through yesterday's level              "
          f"{((b.close / b.trig_y - 1) * 100).median():.2f}%")

    print("\n=== t4: the level rising back over a name that had cleared it")
    t4 = c[c.t4]
    if len(t4):
        print(f"  n = {len(t4):,}; median rise {t4.dtrig_adr.median():+.3f} ADR")
        print(f"  share of these that later re-break: see persistence.py")
    c.to_pickle(os.path.join(OUT, "clamped.pkl"))


if __name__ == "__main__":
    main()
