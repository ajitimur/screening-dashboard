"""Every graded card, re-measured over ticket 17's base/cluster structure.

Ticket 17 replaced D3/D4, so four of round 2's six fitted thresholds describe a window that no
longer exists. Before anything can be refitted, the rubric's inputs have to be recomputed over the
*split's* base rather than ticket 08's:

  orderliness   churn / L, over the split's base instead of min(L, 20) of D3's longest window
  dryup         median volume in the split's base / median of the 50 bars before it
  ma_dist       (base low - SMA20) / (ADR x close), where "base low" is now the split's
  base_length   the split's base length, median ~14 bars rather than ~3
  tightness     no incumbent at all — every candidate from ticket 17's R4 is carried here

Two graded sets exist and neither was collected on this structure, which is the whole difficulty:

  deck A   120 cards, ticket 08 detections, overlays ON. The split accepts about a third of them.
  deck 17  60 cards, BARE candles, no overlay — 20 shared / 20 split-only / 20 08-only, so 40 of
           them are the split's own population and were graded without seeing any geometry.

Both are US. There are still zero graded IDX cards on any structure.

Writes cache/split_graded.pkl — one row per graded card that has computable split geometry.
"""

import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
P17 = os.path.abspath(os.path.join(HERE, "..", "17-base-cluster"))
sys.path.insert(0, P09)
sys.path.insert(0, P16)
CACHE = os.path.join(P09, "cache")

import ranks as R      # noqa: E402
import split as S      # noqa: E402

_FRAMES = {}


def frames(market):
    if market not in _FRAMES:
        f = "universe_us.pkl" if market == "US" else "universe_idx.pkl"
        _FRAMES[market] = {s: S.clean(d)
                           for s, d in pd.read_pickle(os.path.join(CACHE, f)).items()}
    return _FRAMES[market]


# --------------------------------------------------------------------------- the graded cards

def deck_a():
    """120 grades from round 2's core deck — ticket 08 detections, overlays on."""
    man = pd.read_pickle(os.path.join(CACHE, "manifest_r2.pkl"))
    man = man[man.deck == "A"].copy()
    txt = open(os.path.join(HERE, "grades_A.txt")).read()
    g = {m.group(1): int(m.group(2)) for m in re.finditer(r"(A\d{3}):(\d)", txt)}
    man["eye"] = man.cid.map(g)
    man["date"] = pd.to_datetime(man.date).dt.strftime("%Y-%m-%d")
    man["source"] = "deckA"
    man["arm"] = "t08"
    return man[["symbol", "market", "date", "eye", "source", "arm"]]


def deck_17():
    """60 grades from ticket 17's section 1 — bare candles, three arms, no overlay."""
    man = pd.read_csv(os.path.join(P17, "deck17_manifest.csv"))
    man = man[man.section == "population"].sort_values("card").copy()
    txt = open(os.path.join(P17, "grades17.txt")).read().strip()
    digits = [c for c in txt if c.isdigit()]
    assert len(digits) >= len(man), (len(digits), len(man))
    man["eye"] = [int(c) for c in digits[:len(man)]]
    man["market"] = "US"
    man["source"] = "deck17"
    man["date"] = pd.to_datetime(man.date).dt.strftime("%Y-%m-%d")
    return man[["symbol", "market", "date", "eye", "source", "arm"]]


# --------------------------------------------------------------------------- split-domain signals

def signals_at(d, end):
    """Every rubric input and every ticket-17 tightness candidate, over the split's base."""
    rows = S.scan(d, [end])
    if not rows:
        return None
    r = rows[0]
    if not r.get("has_base"):
        return None

    high = d["High"].to_numpy(float)
    low = d["Low"].to_numpy(float)
    close = d["Close"].to_numpy(float)
    vol = d["Volume"].to_numpy(float)
    sma20 = pd.Series(close).rolling(20).mean().to_numpy()
    sma10 = pd.Series(close).rolling(10).mean().to_numpy()

    a = r["adr"]
    adr_abs = a * close[end]
    base_len = int(r["base_len"])
    bs = end - base_len + 1

    base_hi = float(high[bs:end + 1].max())
    base_lo = float(low[bs:end + 1].min())
    env = base_hi - base_lo
    churn = float((high[bs:end + 1] - low[bs:end + 1]).sum() / env) if env > 0 else None

    dryup = None
    if bs - 50 >= 0:
        prior = np.median(vol[bs - 50:bs])
        if prior > 0:
            dryup = float(np.median(vol[bs:end + 1]) / prior)

    ma_dist = rising = None
    if not np.isnan(sma20[end]) and end >= 25:
        ma_dist = float((base_lo - sma20[end]) / adr_abs)
        rising = bool(sma20[end] > sma20[end - 5])

    # ticket 17 R4's tightness candidates, all over the split's own geometry
    k = int(r["cluster_k"]) if r.get("tight") else None
    cs = end - k + 1 if k else None
    clus_rng = float(high[cs:end + 1].max() - low[cs:end + 1].min()) if k else None
    clus_churn = (float((high[cs:end + 1] - low[cs:end + 1]).sum() / clus_rng)
                  if (k and clus_rng and clus_rng > 0) else np.nan)

    ks = list(range(3, base_len + 1))
    sqrt_shortfall = np.nan
    if len(ks) >= 2:
        rngs = [float(high[end - x + 1:end + 1].max() - low[end - x + 1:end + 1].min()) for x in ks]
        if rngs[0] > 0:
            sqrt_shortfall = float(np.mean([rr / (rngs[0] * np.sqrt(x / ks[0]))
                                            for x, rr in zip(ks[1:], rngs[1:])]))

    # the split's own MA catch-up test, as a number rather than a boolean — D10 overlaps it
    g10 = float((close[end] - sma10[end]) / adr_abs) if not np.isnan(sma10[end]) else np.nan
    g20 = float((close[end] - sma20[end]) / adr_abs) if not np.isnan(sma20[end]) else np.nan

    return {
        "end": end, "adr": a, "close": float(close[end]), "move_gain": r["move_gain"],
        "base_len": base_len, "L_true": base_len,
        "tight": bool(r.get("tight")), "line_ok": bool(r.get("line_ok")),
        "caught_up": bool(r.get("caught_up")),
        "split_ok": bool(r.get("tight") and r.get("line_ok") and r.get("caught_up")),
        "cluster_k": k,
        "cluster_range_adr": float(r["cluster_range_adr"]) if r.get("tight") else np.nan,
        "trigger": float(r["trigger"]) if r.get("tight") and r.get("line_ok") is not None
        and "trigger" in r else np.nan,
        "stopw_adr": float(r["stopw_adr"]) if "stopw_adr" in r else np.nan,
        # rubric inputs, split domain
        "churn": churn, "L_eff": base_len,
        "orderliness": (churn / base_len) if churn else np.nan,
        "dryup": dryup, "ma_dist_adr": ma_dist, "sma20_rising": rising,
        # tightness candidates
        "narrow_cluster": (clus_rng / adr_abs) if clus_rng is not None else np.nan,
        "narrowing_ratio": (clus_rng / env) if (clus_rng is not None and env > 0) else np.nan,
        "sqrt_shortfall": sqrt_shortfall, "cluster_churn": clus_churn,
        "base_height_adr": (env / adr_abs) if adr_abs > 0 else np.nan,
        "gap10_adr": g10, "gap20_adr": g20,
    }


def main():
    cards = pd.concat([deck_a(), deck_17()], ignore_index=True)
    print(f"graded cards in: {len(cards)}  "
          f"({cards.source.value_counts().to_dict()})")

    rk, elig, C = R.load_or_build()
    sectors = pd.read_pickle(os.path.join(CACHE, "sectors_us.pkl"))

    out = []
    for (market, symbol), g in cards.groupby(["market", "symbol"]):
        d = frames(market).get(symbol)
        if d is None:
            continue
        dates = pd.to_datetime(d["Date"]).dt.strftime("%Y-%m-%d").to_numpy()
        pos = {v: i for i, v in enumerate(dates)}
        for _, row in g.iterrows():
            if row.date not in pos:
                continue
            sig = signals_at(d, pos[row.date])
            if sig is None:
                continue
            pm = R.prior_move_pct(rk, symbol, row.date) if market == "US" else None
            ss = R.sector_share_loo(rk, sectors, symbol, row.date) if market == "US" else None
            out.append({"symbol": symbol, "market": market, "date": row.date, "eye": row.eye,
                        "source": row.source, "arm": row.arm,
                        "prior_move": pm, "sector_share": ss, **sig})

    df = pd.DataFrame(out).drop_duplicates(subset=["symbol", "date", "source"])
    df.to_pickle(os.path.join(CACHE, "split_graded.pkl"))
    print(f"\nrows with computable split geometry: {len(df)} of {len(cards)}")
    print(df.groupby(["source", "arm"]).size().to_string())
    print(f"\nof those, the split ACCEPTS (tight & line_ok & caught_up): {df.split_ok.sum()}")
    print(df.groupby(["source", "arm"]).split_ok.mean().round(3).to_string())
    print("\nbase length, split domain: median "
          f"{df.base_len.median():.0f}  IQR {df.base_len.quantile(.25):.0f}-"
          f"{df.base_len.quantile(.75):.0f}")
    for c in ("orderliness", "dryup", "ma_dist_adr", "cluster_k", "cluster_range_adr"):
        x = df[c].to_numpy(float)
        x = x[np.isfinite(x)]
        if len(x):
            print(f"  {c:20s} median {np.median(x):7.3f}  "
                  f"IQR {np.percentile(x, 25):7.3f} - {np.percentile(x, 75):7.3f}  n={len(x)}")


if __name__ == "__main__":
    main()
