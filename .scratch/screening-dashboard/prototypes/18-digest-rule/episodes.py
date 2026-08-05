"""If repeats need suppressing, is there a rule that costs no parameter?

`repeats.py` found that 20.6% of reported breaks fall within 20 sessions of the same name's
previous break and 7.4% land on consecutive sessions — because the clamp re-arms a name the night
after it breaks. A "suppress within N sessions" rule would fix it and would be the notification
layer's first tunable, which ticket 14's A4 explicitly refused.

The parameter-free alternative is the *detection episode*: a maximal run of contiguous nights on
which the name is detected at all. A name that breaks, drops out of detection and comes back weeks
later is a new episode; a name that breaks twice while continuously detected is not. This counts
what each rule reports.
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
    g = c.groupby(["market", "symbol"], sort=False)
    # a new episode starts whenever the name was not detected on the immediately preceding session
    prev_det = g.detected.shift(1).fillna(False).astype(bool)
    prev_end = g.end.shift(1)
    new_ep = c.detected & ~(prev_det & ((c.end - prev_end) == 1))
    c["episode"] = new_ep.cumsum().where(c.detected)

    det = c[c.detected]
    ep = det.groupby("episode")
    print(f"=== {det.episode.nunique():,} detection episodes over {len(det):,} detected nights")
    L = ep.size()
    print(f"  episode length, sessions: median {L.median():.0f}, "
          f"75th {L.quantile(.75):.0f}, 90th {L.quantile(.9):.0f}, max {L.max():.0f}")

    br = c[c.t1]
    per_ep = br.groupby("episode").size()
    print(f"\n=== breaks per episode  (episodes containing >=1 break: {len(per_ep):,})")
    for n in (1, 2, 3):
        share = (per_ep == n).mean() if n < 3 else (per_ep >= n).mean()
        lab = f"exactly {n}" if n < 3 else f"{n} or more"
        print(f"  {lab:12s} {share:6.1%}")
    print(f"  mean breaks per break-carrying episode: {per_ep.mean():.2f}")

    first = br.groupby("episode").end.transform("min") == br.end
    print(f"\n=== what each rule reports")
    rules = {
        "every break (no rule)": np.ones(len(br), bool),
        "first break per detection episode": first.to_numpy(),
    }
    gap = br.sort_values(["market", "symbol", "end"]).groupby(["market", "symbol"]).end.diff()
    for w in (5, 20):
        rules[f"suppress a repeat within {w} sessions"] = (gap.isna() | (gap > w)).to_numpy()

    nights = {m: c[c.market == m].date.nunique() for m in UNIVERSE}
    names = {m: c[c.market == m].symbol.nunique() for m in UNIVERSE}
    print(f"  {'rule':38s} {'US/night':>10s} {'IDX/night':>10s} {'rows kept':>11s}")
    for lab, mask in rules.items():
        out = []
        for m in UNIVERSE:
            sel = mask & (br.market == m).to_numpy()
            out.append(sel.sum() / nights[m] * UNIVERSE[m] / names[m])
        print(f"  {lab:38s} {out[0]:>10.1f} {out[1]:>10.1f} {mask.mean():>11.1%}")

    print("\n=== when a repeat inside one episode happens, is it a different move?")
    rep = br[~first]
    if len(rep):
        prev_close = br.groupby("episode").close.shift(1)
        adv = ((rep.close / prev_close[~first] - 1) * 100)
        print(f"  repeats within an episode: {len(rep):,}")
        print(f"  median price advance since that episode's previous break: {adv.median():+.2f}%")
        print(f"  share where price is LOWER than the previous break: {(adv < 0).mean():.1%}")

    print("\n  NB: no decile gate applied (ticket 08 D15), so volumes are upper bounds.")


if __name__ == "__main__":
    main()
