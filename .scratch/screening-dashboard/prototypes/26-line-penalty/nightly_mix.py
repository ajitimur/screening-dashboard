"""Ticket 26 — what the longer list actually looks like on a real night.

`lnd_cost.py` (ticket 25) priced the remedy as a COUNT: 5.98 -> 9.5 US names a night. Ticket 11's
list is sorted by star score descending, so the count is not the thing the eye pays — the thing it
pays is where the new rows land. This scores both populations with ticket 15's published rubric and
reports the merged list the way ticket 11's screen would show it.

Deck F answers the same question at 50/50 arm sizes; the nightly mix is not 50/50.

Usage: nightly_mix.py [nights=N]
"""

import os
import sys
import time

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

T_R3 = {"cluster_k": 4, "ord_lo": 0.275, "ord_hi": 0.50, "dryup": 0.90, "len_ok": 26}
DECILE = 0.90
MOVE_FLOOR = 25.0
SCALE = 3.0          # split.pkl is a 1-in-3 sweep of bar-dates
N_NIGHTS = 120
US_UNIVERSE = 1966   # ticket 05, via ticket 19 harness.py and ticket 18 crossings.py


def main(n_nights):
    t0 = time.time()
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp["date"] = pd.to_datetime(sp.date).dt.strftime("%Y-%m-%d")
    rk, _, _ = R.load_or_build()
    sectors = pd.read_pickle(os.path.join(CACHE, "sectors_us.pkl"))
    fr = frames("US")

    # Night selection copies lnd_cost.py exactly — drawn from the has_base population, so nights
    # with no qualifying candidate still count as a night. Selecting on `tight & caught_up`
    # instead over-samples busy nights and inflates every count.
    pool = sp[(sp.market == "US") & sp.has_base & (sp.move_gain >= MOVE_FLOOR)]
    rng = np.random.default_rng(25)
    nights = np.array(sorted(pool.date.unique()))
    nights = nights[rng.permutation(len(nights))[:n_nights]]
    us = pool[pool.caught_up & pool.tight].copy()

    rows = []
    for night in nights:
        d = us[us.date == night]
        for _, r in d.iterrows():
            if r.symbol not in fr:
                continue
            pm = R.prior_move_pct(rk, r.symbol, night)
            if pm is None or pm < DECILE:
                continue
            sig = signals_at(fr[r.symbol], int(r.end))
            if sig is None:
                continue
            ss = R.sector_share_loo(rk, sectors, r.symbol, night)
            s = score3({**sig, "adr": r.adr}, pm, ss, "boolean", T=T_R3)
            rows.append({"night": night, "symbol": r.symbol, "line_ok": bool(r.line_ok),
                         "machine": s["stars"], "cluster_k": sig.get("cluster_k"),
                         "touch_zones": r.get("touch_zones"),
                         "overshoot_adr": r.get("overshoot_adr")})
    df = pd.DataFrame(rows)
    print(f"{len(df):,} scored rows over {df.night.nunique()} nights "
          f"({time.time()-t0:.0f}s)\n")

    per = df.groupby("night").agg(all_rows=("symbol", "size"),
                                  accepted=("line_ok", "sum"))
    per = per.reindex(nights, fill_value=0)      # empty nights are nights
    per["marginal"] = per.all_rows - per.accepted
    n_scanned = pool.symbol.nunique()
    uscale = US_UNIVERSE / n_scanned
    print("=== nightly US list, as specified vs with the line test demoted "
          f"(x{SCALE:.0f} for the 1-in-3 sweep)")
    print(f"  as specified (line_ok only):   {per.accepted.mean()*SCALE:5.2f} names/night")
    print(f"  with the marginal names:       {per.all_rows.mean()*SCALE:5.2f} names/night "
          f"(+{per.all_rows.sum()/per.accepted.sum()-1:.0%})")
    print(f"  marginal share of the list:    {per.marginal.sum()/per.all_rows.sum():5.0%}")

    print(f"\n=== the same list scaled to ticket 05's real universe "
          f"({n_scanned} names scanned -> {US_UNIVERSE}, x{uscale:.2f})")
    print("  ticket 18's digest figures are already scaled this way (crossings.py: 1966/names);")
    print("  ticket 25's list figures are NOT, which is why the two are not comparable as written.")
    print(f"  as specified (line_ok only):   {per.accepted.mean()*SCALE*uscale:5.1f} names/night")
    print(f"  with the marginal names:       {per.all_rows.mean()*SCALE*uscale:5.1f} names/night")
    print("  CAVEAT: the scan pool is a random Nasdaq draw plus a 39-name momentum core, not")
    print("  ticket 05's liquidity-gated universe, so this transfers a per-name rate across")
    print("  populations of different composition. The +59% RATIO does not depend on it.")

    print("\n=== where they land in ticket 11's star-descending sort")
    print(f"{'':22s} {'accepted':>10s} {'marginal':>10s}")
    print(f"{'mean machine star':22s} {df[df.line_ok].machine.mean():10.2f} "
          f"{df[~df.line_ok].machine.mean():10.2f}")
    for cut in (4.0, 3.5, 3.0):
        a = (df[df.line_ok].machine >= cut).mean()
        m = (df[~df.line_ok].machine >= cut).mean()
        print(f"{'share >= ' + str(cut) + '*':22s} {a:10.0%} {m:10.0%}")

    print("\n=== the top of the list, which is the part ticket 11 says gets read")
    for top in (3, 5, 10):
        share, cnt = [], []
        for night, g in df.groupby("night"):
            g = g.sort_values("machine", ascending=False).head(top)
            share.append((~g.line_ok).mean())
            cnt.append((~g.line_ok).sum())
        print(f"  top {top:2d} rows: {np.mean(share):5.0%} marginal "
              f"({np.mean(cnt)*1.0:.2f} rows of {top})")

    print("\n=== how many 4*+ rows a night, before and after")
    a4 = df[df.line_ok & (df.machine >= 4)].groupby("night").size().reindex(
        per.index, fill_value=0)
    t4 = df[df.machine >= 4].groupby("night").size().reindex(per.index, fill_value=0)
    print(f"  as specified: {a4.mean()*SCALE:5.2f} names/night at >=4*")
    print(f"  with marginal: {t4.mean()*SCALE:5.2f} names/night at >=4* "
          f"(+{t4.sum()/max(a4.sum(),1)-1:.0%})")

    print("\n=== if the penalty were keyed on the overshoot sub-test only")
    z = df.touch_zones.fillna(0)
    o = df.overshoot_adr.fillna(0)
    over = (~df.line_ok) & (o > 1.0)
    touch = (~df.line_ok) & (o <= 1.0) & (z < 2)
    print(f"  marginal rows failing overshoot: {over.sum()/max((~df.line_ok).sum(),1):5.0%} "
          f"({over.sum()/df.night.nunique()*SCALE:.2f} names/night)")
    print(f"  marginal rows failing touches:   {touch.sum()/max((~df.line_ok).sum(),1):5.0%} "
          f"({touch.sum()/df.night.nunique()*SCALE:.2f} names/night)")
    print(f"  mean machine star, overshoot subset {df[over].machine.mean():.2f}, "
          f"touches subset {df[touch].machine.mean():.2f}")

    out = os.path.join(HERE, "out")          # gitignored, like every other prototype's out/
    os.makedirs(out, exist_ok=True)
    df.to_csv(os.path.join(out, "nightly_mix.csv"), index=False)
    print(f"\nwrote nightly_mix.csv ({len(df):,} rows)")


if __name__ == "__main__":
    n = N_NIGHTS
    for a in sys.argv[1:]:
        if a.startswith("nights="):
            n = int(a.split("=")[1])
    main(n)
