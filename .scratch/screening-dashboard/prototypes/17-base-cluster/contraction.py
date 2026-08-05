"""What replaces D7's contraction if the retained window set goes away?

Ticket 08 scores tightness (a x2 dimension) as how far the `range(L)` curve sits below a sqrt(L)
random-walk baseline, computed over D3's retained set of valid windows. A base/cluster split emits
one base, not a nested family, so the curve has no obvious domain — and ticket 16's R3 additionally
left D7 owing the "narrow" half it had delegated to the D6 gate.

Both halves need a definition, and ticket 09 established the trap they must avoid: the incumbent
contraction is largely a **proxy for base length**, which the trader reads inverted. So each
candidate is scored on three things:

  |r| vs base length   the ticket-09 failure mode. Lower is better.
  r vs the eye         120 deck-A grades, the only ground truth that exists. Higher is better.
  spread               a metric that is constant, or bounded into a corner, cannot rank anything.

Candidates
  narrow_cluster    cluster range / ADR                    the "narrow" half, free from the split
  narrowing_ratio   cluster range / base range             narrowing, scale-free, no baseline
  sqrt_shortfall    range(k) vs sqrt(k), k = 3..base_len   D7's own shape, over trailing windows
                                                           of the base instead of D3's retained set
  incumbent         ticket 08's D7 as shipped              the control
"""

import os
import re
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
P15 = os.path.abspath(os.path.join(HERE, "..", "15-grading-round-2"))
sys.path.insert(0, P16)
sys.path.insert(0, P09)
CACHE = os.path.join(HERE, "cache")
OUT = os.path.join(HERE, "out")

import split as S            # noqa: E402
import build_deck17 as B     # noqa: E402


def candidates(d, end):
    """Every candidate tightness measure at one bar, plus the base each is computed over."""
    high = d["High"].to_numpy(float)
    low = d["Low"].to_numpy(float)
    close = d["Close"].to_numpy(float)
    adr = pd.Series(high / low - 1.0).rolling(20).mean().to_numpy()
    a = adr[end]
    if np.isnan(a) or a <= 0:
        return None
    adr_abs = a * close[end]

    gs = B.geom_split(d, end)
    if gs is None:
        return None
    bs = int(gs["base_start"])
    cs = int(gs["cluster_start"])
    base_len = end - bs + 1
    cluster_k = end - cs + 1

    base_rng = float(high[bs:end + 1].max() - low[bs:end + 1].min())
    clus_rng = float(high[cs:end + 1].max() - low[cs:end + 1].min())

    # sqrt shortfall over trailing sub-windows of the base — D7's shape, new domain
    ks = list(range(3, base_len + 1))
    if len(ks) >= 2:
        rngs = [float(high[end - k + 1:end + 1].max() - low[end - k + 1:end + 1].min()) for k in ks]
        r0, k0 = rngs[0], ks[0]
        sf = float(np.mean([r / (r0 * np.sqrt(k / k0)) for k, r in zip(ks[1:], rngs[1:])])) \
            if r0 > 0 else np.nan
    else:
        sf = np.nan

    return {"base_len": base_len, "cluster_k": cluster_k,
            "narrow_cluster": clus_rng / adr_abs,
            "narrowing_ratio": clus_rng / base_rng if base_rng > 0 else np.nan,
            "sqrt_shortfall": sf,
            "base_height_adr": base_rng / adr_abs}


METRICS = ["narrow_cluster", "narrowing_ratio", "sqrt_shortfall", "base_height_adr"]


def corr(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 8:
        return np.nan, int(m.sum())
    return float(np.corrcoef(x[m], y[m])[0, 1]), int(m.sum())


def main():
    # ---- the graded cards: the only place an eye correlation can be computed
    man = pd.read_pickle(os.path.join(CACHE, "manifest_r2.pkl"))
    man = man[man.deck == "A"].copy()
    txt = open(os.path.join(P15, "grades_A.txt")).read()
    g = {m.group(1): int(m.group(2)) for m in re.finditer(r"(A\d{3}):(\d)", txt)}
    man["eye"] = man.cid.map(g)
    man["date"] = pd.to_datetime(man.date).dt.strftime("%Y-%m-%d")

    frames = {s: S.clean(d)
              for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    rows = []
    for _, r in man.iterrows():
        d = frames.get(r.symbol)
        if d is None:
            continue
        dates = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d").to_numpy()
        pos = np.where(dates == r.date)[0]
        if not len(pos):
            continue
        c = candidates(d, int(pos[0]))
        if c is None:
            continue
        rows.append({**c, "eye": r.eye, "symbol": r.symbol, "date": r.date})
    G = pd.DataFrame(rows)

    # the incumbent, straight off the round-2 pool so it is the number the rubric actually uses
    pool = pd.read_pickle(os.path.join(CACHE, "pool_us.pkl"))
    pool["date"] = pd.to_datetime(pool["date"]).dt.strftime("%Y-%m-%d")
    inc = man.merge(pool, on=["symbol", "date"], how="left")

    print(f"=== tightness candidates on {len(G)} of {len(man)} graded cards "
          f"(the rest have no base/cluster to measure)")
    print(f"\n{'candidate':18s} {'r vs eye':>9s} {'|r| vs base len':>16s} {'median':>9s} "
          f"{'IQR':>16s}")
    for k in METRICS:
        x = G[k].to_numpy(float)
        re_, n = corr(x, G.eye.to_numpy(float))
        rl, _ = corr(x, G.base_len.to_numpy(float))
        q1, q3 = np.nanpercentile(x, [25, 75])
        print(f"{k:18s} {re_:+9.3f} {abs(rl):16.3f} {np.nanmedian(x):9.2f} "
              f"{f'{q1:.2f} - {q3:.2f}':>16s}")

    for lab, col in (("incumbent D7 (as shipped)", "contraction"),
                     ("incumbent, round-2 min(L,20)", "contraction2")):
        if col in inc:
            x = inc[col].to_numpy(float)
            re_, n = corr(x, inc.eye.to_numpy(float))
            rl, _ = corr(x, inc.L_longest.to_numpy(float))
            print(f"{lab:18s} {re_:+9.3f} {abs(rl):16.3f} {np.nanmedian(x):9.2f}"
                  f"    (n={n})")
    print(f"\n  significance at n={len(G)}: |r| > {1.96/np.sqrt(max(len(G)-2,1)):.3f} for p<.05")

    # ---- population shape, so a threshold could actually be set on these
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp = sp[sp.tight & sp.line_ok & sp.caught_up]
    print(f"\n=== population shape over {len(sp):,} surviving split detections")
    print(f"  cluster range / ADR   median {sp.cluster_range_adr.median():.2f}  "
          f"IQR {sp.cluster_range_adr.quantile(.25):.2f}-{sp.cluster_range_adr.quantile(.75):.2f}  "
          f"max {sp.cluster_range_adr.max():.2f}")
    print(f"  share pinned at the 1.5 ceiling (>1.45): "
          f"{(sp.cluster_range_adr > 1.45).mean():.1%}")
    print(f"  cluster k: {sp.cluster_k.value_counts(normalize=True).sort_index().round(3).to_dict()}")
    print("  (k is picked greedily from 7 downwards, so its distribution is itself a tightness signal)")

    G.to_pickle(os.path.join(OUT, "contraction.pkl"))


if __name__ == "__main__":
    main()
