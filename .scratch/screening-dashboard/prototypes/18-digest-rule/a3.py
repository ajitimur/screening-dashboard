"""What ticket 14's A3 test actually says once the trigger is the cluster high.

A3 is `close_today > trigger_yesterday`. Ticket 14 chose the yesterday-comparison to perform
*attribution*: D5's level descended nightly, so requiring the close to clear the level as it stood
before tonight's descent proved price did the work rather than the line.

That justification is now spent — the trigger cannot descend below today's close under any
circumstances. But the test itself survives, and it means something different and more literal:

    trigger_yesterday = the highest high of the k bars ending yesterday

so A3 is a **k-bar closing breakout**, where k is not a parameter but whatever cluster length the
tightness test picked. This measures the three things that follow:

  1. what k actually is, i.e. how long a lookback the test is really using
  2. the hole: `trigger_yesterday` only exists if the name was DETECTED yesterday, so a name that
     lapses out of detection for a night or two and comes back above its old level is invisible
  3. whether measuring on the close (14 A3, per ticket 05's finality rule) versus the high changes
     the population, now that the trigger sits +0.513 ADR later than D5's
"""

import os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
UNIVERSE = {"US": 1966, "IDX": 288}


def main():
    c = pd.read_pickle(os.path.join(OUT, "crossings.pkl"))
    c = c.sort_values(["market", "symbol", "end"]).reset_index(drop=True)
    det = c[c.detected]

    print("=== 1. what lookback is A3 really using?")
    k = det.cluster_k.dropna()
    print(f"  cluster length k, detections: median {k.median():.0f}, mean {k.mean():.2f}")
    for v in sorted(k.unique()):
        print(f"    k = {int(v)}   {(k == v).mean():6.1%}")
    print("  A3 is 'today's close exceeds the highest high of the last k sessions',")
    print("  with k set by the tightness test rather than chosen. K_MIN/K_MAX are 3 and 7.")

    print("\n=== 2. the hole: trigger_yesterday needs the name to have been detected yesterday")
    g = c.groupby(["market", "symbol"], sort=False)
    # last night this name was detected, and the trigger it carried then
    c["_end_det"] = c.end.where(c.detected)
    last_trig = g.trigger.ffill().shift(1)
    last_end = c.groupby(["market", "symbol"], sort=False)._end_det.ffill().shift(1)
    gap = c.end - last_end
    prev_det_contig = g.detected.shift(1).fillna(False).astype(bool) & (gap == 1)
    fresh = c.detected & ~prev_det_contig

    lapsed = c.detected & fresh & last_trig.notna() & (gap > 1)
    missed = lapsed & (c.close > last_trig)
    print(f"  detections that resume after a lapse of >1 session   {int(lapsed.sum()):,}")
    print(f"  ...of those, close today is already above the level")
    print(f"     they carried when last detected                   {int(missed.sum()):,}")
    print(f"  as a share of all reported breaks (t1 = {int(c.t1.sum()):,})   "
          f"{missed.sum() / max(1, c.t1.sum()):.1%}")
    if missed.any():
        lg = gap[missed]
        print(f"  lapse length when this happens: median {lg.median():.0f} sessions, "
              f"75th {lg.quantile(.75):.0f}, max {lg.max():.0f}")
        adv = ((c.close[missed] / last_trig[missed] - 1) * 100)
        print(f"  median % above the stale level:  {adv.median():+.2f}%")

    print("\n=== 3. close versus high")
    trig_y = g.trigger.shift(1)
    watching_y = (g.detected.shift(1).fillna(False).astype(bool) & (gap == 1)
                  & (g.close.shift(1) <= trig_y))
    base = c.detected & watching_y
    on_close = base & (c.close > trig_y)
    print(f"  breaks measured on the close (14 A3)   {int(on_close.sum()):,}")
    print("  measuring on the high is not computable here: split.scan does not return today's")
    print("  high, but cluster_high >= today's high >= close, so a high-based test is strictly")
    print("  wider. Left as a decision rather than a measurement.")

    print("\n=== volume if the lapse hole were closed")
    nights = {m: c[c.market == m].date.nunique() for m in UNIVERSE}
    names = {m: c[c.market == m].symbol.nunique() for m in UNIVERSE}
    for m in UNIVERSE:
        sc = UNIVERSE[m] / names[m]
        a = (on_close & (c.market == m)).sum() / nights[m] * sc
        b = ((on_close | missed) & (c.market == m)).sum() / nights[m] * sc
        print(f"  {m:4s} A3 as written {a:5.1f}/night   including lapsed resumers {b:5.1f}/night")

    print("\n  NB: no decile gate applied (ticket 08 D15), so volumes are upper bounds.")


if __name__ == "__main__":
    main()
