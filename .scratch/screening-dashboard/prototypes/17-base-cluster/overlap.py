"""Do the two detectors pick the same names?

Ticket 16 measured the base/cluster split's *structure* — base length, cluster existence, line
drawability, list length, stop width — and every number was good. What it never measured is
whether the split fires on the same (symbol, night) pairs ticket 08's window rule fires on. A
detector that produces the same-sized list of *different* names is a different product, and the
ticket cannot be decided on list length alone.

Both scans share a grid: ends = range(90, len(d), 3) over the same cached frames, so the join is
exact rather than approximate.

  ticket 08   nogate.pkl   190,044 ungated detections (D6 shown, not enforced — ticket 16's R3)
              pool_*.pkl    31,553 D6-gated detections, round-2 signals attached
  split       split.pkl    318,357 evaluated bar-dates, 54,201 of which survive

Writes out/overlap.pkl (the joined frame) and prints the agreement tables.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

MOVE_FLOOR = 25.0  # q-scanner's prior-move floor, the split's own list-length control


def load():
    """One row per (market, symbol, end) evaluated by *either* detector, with both verdicts."""
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp["split_ok"] = sp.tight & sp.line_ok & sp.caught_up
    sp = sp.rename(columns={"base_len": "sp_base_len", "trigger": "sp_trigger",
                            "stopw_adr": "sp_stopw", "cluster_low": "sp_stop"})

    ng = pd.read_pickle(os.path.join(CACHE, "nogate.pkl"))
    ng["t08_ok"] = True
    ng = ng.rename(columns={"L": "t08_L", "L_longest": "t08_Lmax",
                            "trig_ols_min": "t08_trigger", "base_low": "t08_stop"})
    ng["t08_stopw"] = (ng.t08_trigger - ng.t08_stop) / ng.t08_trigger / ng.adr

    # Join on the *date*, not on the bar index. split.py's clean() drops a few more bars than
    # ticket 08's (it adds a positive-price guard for IDX), which shifts `end` between the two
    # scans — silently, and only for the names that had a bad bar. Joining on `end` loses 90 of
    # deck A's 120 graded cards to that shift.
    for d in (sp, ng):
        d["date"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m-%d")
    keep_sp = ["market", "symbol", "date", "end", "adr", "close", "move_gain", "sp_base_len",
               "cluster_k", "cluster_range_adr", "sp_trigger", "sp_stop", "sp_stopw", "split_ok",
               "has_base", "tight", "caught_up", "line_ok"]
    keep_ng = ["market", "symbol", "date", "end", "t08_L", "t08_Lmax", "t08_trigger", "t08_stop",
               "t08_stopw", "t08_ok"]
    df = sp[keep_sp].merge(ng[keep_ng].rename(columns={"end": "end08"}),
                           on=["market", "symbol", "date"], how="outer")
    # the outer join makes every flag object-dtype (NaN where the other detector never looked),
    # and `~` on an object column negates *integers* — silently wrong, so cast before any use
    for c in ("t08_ok", "split_ok", "has_base", "tight", "caught_up", "line_ok"):
        df[c] = df[c].fillna(False).astype(bool)
    # D6 as ticket 08 shipped it: reject when trigger-to-base-low exceeds 1 x ADR
    df["t08_gated"] = df.t08_ok & (df.t08_stopw <= 1.0)
    df["split_floor"] = df.split_ok & (df.move_gain >= MOVE_FLOOR)
    return df


def agreement(df, a, b, la, lb):
    both = (df[a] & df[b]).sum()
    only_a = (df[a] & ~df[b]).sum()
    only_b = (~df[a] & df[b]).sum()
    j = both / max(both + only_a + only_b, 1)
    print(f"  {la:34s} {both:>8,} {only_a:>10,} {only_b:>10,}   J={j:.3f}"
          f"   {'':2s}({la} keeps {both / max(both + only_a, 1):.1%} of itself)")
    return j


def report(df):
    print(f"\n=== {len(df):,} (symbol, night) pairs evaluated by either detector")
    print(f"    ticket 08 ungated {df.t08_ok.sum():>8,}   D6-gated {df.t08_gated.sum():>8,}")
    print(f"    split             {df.split_ok.sum():>8,}   >={MOVE_FLOOR:.0f}% move "
          f"{df.split_floor.sum():>8,}")

    print("\npairwise agreement (both / only-left / only-right)")
    print(f"  {'':34s} {'both':>8s} {'only L':>10s} {'only R':>10s}")
    agreement(df, "t08_gated", "split_floor", "08 D6-gated  vs  split+floor", "")
    agreement(df, "t08_ok", "split_ok", "08 ungated   vs  split", "")
    agreement(df, "t08_gated", "split_ok", "08 D6-gated  vs  split", "")
    agreement(df, "t08_ok", "split_floor", "08 ungated   vs  split+floor", "")

    # Where does the split lose 08's D6-gated picks? Walk its funnel.
    lost = df[df.t08_gated & ~df.split_floor]
    print(f"\nwhy the split drops {len(lost):,} of 08's D6-gated detections")
    for lab, mask in (("no base >= 3 bars", ~lost.has_base),
                      ("no tight 3-7 bar cluster", lost.has_base & ~lost.tight),
                      ("not caught up to the 10/20", lost.tight & ~lost.caught_up),
                      ("line not drawable", lost.tight & lost.caught_up
                       & ~lost.line_ok),
                      (f"prior move < {MOVE_FLOOR:.0f}%", lost.split_ok & (lost.move_gain < MOVE_FLOOR)),
                      ("never evaluated by split", lost.sp_base_len.isna())):
        print(f"  {lab:32s} {mask.sum():>8,}  {mask.mean():6.1%}")

    gained = df[df.split_floor & ~df.t08_gated]
    print(f"\nwhy 08 drops {len(gained):,} of the split's picks")
    for lab, mask in (("no valid triangle window", ~gained.t08_ok),
                      ("D6: stop wider than 1 x ADR", gained.t08_ok & (gained.t08_stopw > 1.0))):
        print(f"  {lab:32s} {mask.sum():>8,}  {mask.mean():6.1%}")

    # On the pairs both fire on, how different is the object each describes?
    both = df[df.t08_gated & df.split_floor].copy()
    if len(both):
        a = both.adr * both.close
        both["dtrig"] = (both.sp_trigger - both.t08_trigger) / a
        print(f"\non the {len(both):,} pairs both fire on")
        print(f"  base length     08 primary median {both.t08_L.median():.0f}   "
              f"08 longest {both.t08_Lmax.median():.0f}   split {both.sp_base_len.median():.0f}")
        print(f"  split base is longer than 08's primary on {(both.sp_base_len > both.t08_L).mean():.1%}")
        print(f"  trigger difference, ADR: median {both.dtrig.median():+.3f}  "
              f"mean {both.dtrig.mean():+.3f}   split higher on {(both.dtrig > 0).mean():.1%}")
        print(f"  stop width ADR: 08 median {both.t08_stopw.median():.2f}   "
              f"split median {both.sp_stopw.median():.2f}")

    # The list the trader actually sees is per night, so measure the nightly overlap too.
    print("\nnightly list overlap (mean over sampled nights, per market)")
    for m in ("US", "IDX"):
        sub = df[df.market == m]
        rows = []
        for d, g in sub.groupby("date"):
            A = set(g.symbol[g.t08_gated])
            B = set(g.symbol[g.split_floor])
            if not A and not B:
                continue
            rows.append((len(A), len(B), len(A & B), len(A | B)))
        r = pd.DataFrame(rows, columns=["n08", "nsp", "inter", "union"])
        print(f"  {m:4s} nights={len(r):4d}  08 {r.n08.mean():5.1f}  split {r.nsp.mean():5.1f}  "
              f"shared {r.inter.mean():5.1f}  J={(r.inter / r.union).mean():.3f}")
    print("  (1-in-3 date sampling: multiply the counts by ~3 for a real night)")


if __name__ == "__main__":
    df = load()
    df.to_pickle(os.path.join(OUT, "overlap.pkl"))
    report(df)
