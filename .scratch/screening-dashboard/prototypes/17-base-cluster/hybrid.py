"""The option the ticket did not name: keep ticket 08's base, borrow only the cluster.

The ticket is charted as a swap — replace D2/D3/D4 with the base/cluster split, or reject it and
owe an alternative looseness cut. But the split is two separable things, and only one of them is
what ticket 16's R3 actually asked for:

  the base      where the consolidation starts (prior move's peak vs the end-anchored window search)
  the cluster   a 3-7 bar trailing window spanning <= 1.5 x ADR, sitting on a rising MA

R3 owes a *looseness cut expressed as a property of the base*, and it owes D7 its "narrow" half.
The **cluster** supplies both. The **base** supplies neither — it supplies a longer window to fit a
line over, which is a different problem (R4's), and it is the half that costs D3's retained set,
breaks D7's contraction and invalidates ticket 15's in-flight rubric.

So measure the hybrid: ticket 08's detector exactly as it stands, ungated per R3, plus "a valid
3-7 bar cluster must exist" as the cut D6 used to make implicitly, and the cluster low as the stop.

Three questions decide whether it is worth anything:
  1. does it hold the nightly list near ~64 US names, the way D6 did and the full split does?
  2. is the stop bounded by construction, as it is under the full split?
  3. how much of ticket 08 does it keep — D2, D3, D4, D5, D7 and ticket 15's rubric all survive
     untouched, which is the whole point.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
sys.path.insert(0, P16)
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")

import split as S  # noqa: E402

SCALE = 3.0  # 1-in-3 date sampling


def cluster_at(frames, rows):
    """Attach the trailing cluster to each of ticket 08's detections, at that detection's bar."""
    out = []
    for (market, sym), g in rows.groupby(["market", "symbol"]):
        d = frames[market].get(sym)
        if d is None:
            continue
        high = d["High"].to_numpy(float)
        low = d["Low"].to_numpy(float)
        close = d["Close"].to_numpy(float)
        adr = pd.Series(high / low - 1.0).rolling(20).mean().to_numpy()
        dates = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d").to_numpy()
        pos = {v: i for i, v in enumerate(dates)}
        for _, r in g.iterrows():
            e = pos.get(r["date"])
            if e is None or e >= len(high):
                continue
            a = adr[e]
            if not np.isfinite(a) or a <= 0:
                continue
            adr_abs = a * close[e]
            cl = S.find_cluster(high, low, e, adr_abs)
            rec = {"market": market, "symbol": sym, "date": r["date"], "adr": float(a),
                   "close": float(close[e]), "t08_trigger": float(r["t08_trigger"]),
                   "t08_stop": float(r["t08_stop"]), "t08_L": float(r["t08_L"]),
                   "t08_stopw": float(r["t08_stopw"])}
            if cl is None:
                out.append({**rec, "has_cluster": False})
                continue
            k, ch, clow, rng_adr = cl
            trig = float(r["t08_trigger"])
            out.append({**rec, "has_cluster": True, "cluster_k": k, "cluster_range_adr": rng_adr,
                        "cluster_low": clow, "cluster_high": ch,
                        "stopw_cluster": (trig - clow) / trig / a if trig > 0 else np.nan})
    return pd.DataFrame(out)


def main():
    ov = pd.read_pickle(os.path.join(OUT, "overlap.pkl"))
    det = ov[ov.t08_ok].copy()  # ticket 08's detections, ungated per R3
    frames = {}
    for m, f in (("US", "universe_us.pkl"), ("IDX", "universe_idx.pkl")):
        frames[m] = {s: S.clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, f)).items()}

    h = cluster_at(frames, det)
    h.to_pickle(os.path.join(OUT, "hybrid.pkl"))
    print(f"=== {len(h):,} of ticket 08's ungated detections, cluster attached")

    print("\n1. does the cluster hold the list down?")
    print(f"  {'rule':44s} {'US/night':>9s} {'IDX/night':>10s}")
    rules = [
        ("08 ungated (ticket 16 R3, no cut at all)", h.index == h.index),
        ("08 + D6's 1xADR stop gate (today)", h.t08_stopw <= 1.0),
        ("08 + a valid 3-7 bar cluster exists", h.has_cluster),
        ("08 + cluster + stop-to-cluster-low <= 1.5 ADR", h.has_cluster & (h.stopw_cluster <= 1.5)),
    ]
    for lab, mask in rules:
        sub = h[mask]
        row = []
        for m in ("US", "IDX"):
            s = sub[sub.market == m]
            row.append(s.groupby("date").size().mean() * SCALE if len(s) else 0.0)
        print(f"  {lab:44s} {row[0]:9.1f} {row[1]:10.1f}")
    print("  (for reference: today ~64 US / ~12 IDX; the full split ~63 / ~11)")

    print("\n2. is the stop bounded, as it is under the full split?")
    c = h[h.has_cluster]
    for lab, col in (("08's stop (base low)", "t08_stopw"), ("cluster low", "stopw_cluster")):
        x = c[col].replace([np.inf, -np.inf], np.nan).dropna()
        print(f"  {lab:22s} median {x.median():5.2f} ADR   p95 {x.quantile(.95):5.2f}   "
              f"max {x.max():6.2f}   within 1.5 ADR {(x <= 1.5).mean():5.1%}")
    print("  the full split's max across 54,201 detections was 1.499 by construction; ticket 08's")
    print("  trigger is not anchored to the cluster, so the bound is tight but not structural.")

    print("\n3. what the cut costs, against what D6 cut")
    print(f"  detections with no valid cluster: {(~h.has_cluster).mean():.1%}")
    print(f"  of those D6 would have kept:      "
          f"{(~h.has_cluster & (h.t08_stopw <= 1.0)).sum() / max((h.t08_stopw <= 1.0).sum(), 1):.1%}")
    print(f"  of those D6 would have cut:       "
          f"{(~h.has_cluster & (h.t08_stopw > 1.0)).sum() / max((h.t08_stopw > 1.0).sum(), 1):.1%}")
    agree = ((h.has_cluster) == (h.t08_stopw <= 1.0)).mean()
    print(f"  cluster cut and D6 agree on {agree:.1%} of detections — "
          f"{'a different cut' if agree < 0.8 else 'nearly the same cut'}, not a re-parameterised one")


if __name__ == "__main__":
    main()
