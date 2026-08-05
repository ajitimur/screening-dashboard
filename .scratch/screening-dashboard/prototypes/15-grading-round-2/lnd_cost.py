"""Ticket 25 — the decile-gated cost of loosening `line_ok`, and the deck's true reject arm.

`lnd_diag.py` measured the funnel without D15's decile gate, which overstates every count. This
computes the numbers that actually decide the remedy: the nightly US list as specified, and the
names a dropped or loosened `line_ok` would add to *that* list — the marginal population, which is
also exactly the population deck F's reject arm must be drawn from.

The marginal population is `tight & caught_up & ~line_ok & move >= 25% & decile` — names that fail
on nothing but the line. Ticket 23's deck sampled `has_base & ~line_ok` instead, ungated, so its
reject arm carried names that also failed the catch-up test and were 93% outside the decile.
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
SCALE = 3.0
N_NIGHTS = 250


def main():
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp["date"] = pd.to_datetime(sp.date).dt.strftime("%Y-%m-%d")
    rk, _, _ = R.load_or_build()

    us = sp[(sp.market == "US") & sp.has_base & (sp.move_gain >= MOVE_FLOOR)].copy()
    rng = np.random.default_rng(25)
    nights = np.array(sorted(us.date.unique()))
    nights = nights[rng.permutation(len(nights))[:N_NIGHTS]]

    counts = {k: [] for k in ("accepted", "lnd_marginal", "no_cluster", "not_caught_up")}
    for night in nights:
        d = us[us.date == night]
        if not len(d):
            continue
        pm = np.array([R.prior_move_pct(rk, r.symbol, night) or np.nan for _, r in d.iterrows()])
        g = d[pm >= DECILE]
        counts["accepted"].append(int((g.tight & g.line_ok & g.caught_up).sum()))
        counts["lnd_marginal"].append(int((g.tight & ~g.line_ok & g.caught_up).sum()))
        counts["no_cluster"].append(int((~g.tight).sum()))
        counts["not_caught_up"].append(int((g.tight & g.line_ok & ~g.caught_up).sum()))

    print(f"=== decile-gated nightly US counts, {len(counts['accepted'])} sampled nights "
          f"(1-in-3 sweep, x{SCALE:.0f})\n")
    base = np.mean(counts["accepted"]) * SCALE
    for k, v in counts.items():
        m = np.mean(v) * SCALE
        print(f"  {k:16s} {m:7.2f} / night   ({m/max(base,1e-9):5.2f}x the accepted list)")

    print(f"\n  dropping line_ok entirely: {base:.1f} -> "
          f"{base + np.mean(counts['lnd_marginal'])*SCALE:.1f} names/night "
          f"(x{1 + np.mean(counts['lnd_marginal'])/max(np.mean(counts['accepted']),1e-9):.2f})")

    # ---- the marginal population's shape: which sub-test does it fail, and how long is its base
    marg = us[us.tight & ~us.line_ok & us.caught_up]
    z = marg.touch_zones.fillna(0)
    o = marg.overshoot_adr.fillna(0)
    print(f"\n=== the marginal population, ungated ({len(marg):,} rows) — which test fails")
    print(f"  touches only    {((z < 2) & (o <= 1.0)).mean():7.2%}")
    print(f"  overshoot only  {((z >= 2) & (o > 1.0)).mean():7.2%}")
    print(f"  both            {((z < 2) & (o > 1.0)).mean():7.2%}")
    print(f"  overshoot_frac  {((z >= 2) & (o <= 1.0)).mean():7.2%}")
    acc = us[us.tight & us.line_ok & us.caught_up]
    print(f"\n  base_len   marginal median {marg.base_len.median():.0f}  "
          f"accepted median {acc.base_len.median():.0f}")
    print(f"  cluster_k  marginal median {marg.cluster_k.median():.0f}  "
          f"accepted median {acc.cluster_k.median():.0f}")
    print(f"  adr        marginal median {marg.adr.median():.4f}  "
          f"accepted median {acc.adr.median():.4f}")


if __name__ == "__main__":
    main()
