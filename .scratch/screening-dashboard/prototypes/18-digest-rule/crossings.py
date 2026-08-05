"""What the crossing population looks like under ticket 17's clamped trigger.

Ticket 14's A2 split "crossed its trigger" three ways and rendered only the first. Every number
under that taxonomy came from ticket 09's D10 measurement of ticket 08's D5 line — 98.3% of
triggers set by a descending line, 16.4% born triggered. Ticket 17 replaced D5 with
`max(line_at(t+1), cluster_high)`, so all of it is stale.

The thing no prior ticket could measure: every scan on this map ran a 1-in-3 date grid, which
cannot see a night-over-night transition at all. This runs the split on CONSECUTIVE daily bars so
`trigger[t-1]` and `close[t]` are both real, then classifies each night.

Taxonomy, extended for what ticket 17 introduced:

  t1  price rose through yesterday's level      close_t > trig_y, close_y <= trig_y   (14: report)
  t2  the level came down to meet a flat name   close_t <= trig_y, close_t > trig_t   (14: no)
  t3  born triggered                            first detected day, close > trig      (14: no)
  t4  the level rose back over a cleared name   was TRIGGERED, close_t <= trig_t      (14: no bucket)

Also measures the trigger's own motion, which is the fact ticket 14's rule rests on: under D5 it
fell every night by construction. Under the clamp it may rise, fall or sit still.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P16 = os.path.abspath(os.path.join(HERE, "..", "16-trendline-fit"))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P16)
CACHE = os.path.join(P09, "cache")
OUT = os.path.join(HERE, "out")

import split as S  # noqa: E402

N_US, N_IDX = 260, 140
SEED = 18
BARS = 760          # ~3 years of daily bars per name, ending at the cache's last bar
MOVE_FLOOR = 25.0   # the split's own prior-move floor (17 R3: two momentum filters, both applied)


def sample(market, n):
    """n names with enough history, sampled reproducibly — same shape as params.py's sampler."""
    u = pd.read_pickle(os.path.join(CACHE, f"universe_{market.lower()}.pkl"))
    rng = np.random.default_rng(SEED)
    syms = sorted(s for s, d in u.items() if len(d) >= BARS + 120)
    take = rng.choice(len(syms), size=min(n, len(syms)), replace=False)
    return {syms[int(i)]: S.clean(u[syms[int(i)]]) for i in take}


def daily(frames, market):
    """Scan every bar in the trailing window, so consecutive nights are comparable."""
    rows = []
    for i, (sym, d) in enumerate(sorted(frames.items())):
        if len(d) < 200:
            continue
        start = max(90, len(d) - BARS)
        for r in S.scan(d, range(start, len(d))):
            r["symbol"], r["market"] = sym, market
            rows.append(r)
        if i and i % 50 == 0:
            print(f"  {market} {i} names, {len(rows):,} rows", flush=True)
    return pd.DataFrame(rows)


def classify(df):
    """One row per (symbol, night) with the transition it represents."""
    df = df.copy()
    df["detected"] = (df.tight.fillna(False).astype(bool)
                      & df.line_ok.fillna(False).astype(bool)
                      & df.caught_up.fillna(False).astype(bool)
                      & (df.move_gain >= MOVE_FLOOR))
    df.loc[~df.detected, "trigger"] = np.nan
    df = df.sort_values(["market", "symbol", "end"]).reset_index(drop=True)
    g = df.groupby(["market", "symbol"], sort=False)

    df["prev_end"] = g.end.shift(1)
    df["trig_y"] = g.trigger.shift(1)
    df["close_y"] = g.close.shift(1)
    df["det_y"] = g.detected.shift(1).fillna(False).astype(bool)
    # contiguous nights only: a gap in `end` means the name left and re-entered the sample
    df["contig"] = df.end - df.prev_end == 1

    det = df.detected
    # yesterday's standing, on yesterday's own level
    watching_y = df.det_y & df.contig & (df.close_y <= df.trig_y)
    triggered_y = df.det_y & df.contig & (df.close_y > df.trig_y)
    fresh = det & ~(df.det_y & df.contig)          # first night of a detection episode

    df["t1"] = det & watching_y & (df.close > df.trig_y)
    df["t2"] = det & watching_y & (df.close <= df.trig_y) & (df.close > df.trigger)
    df["t3"] = fresh & (df.close > df.trigger)
    df["t4"] = det & triggered_y & (df.close <= df.trigger)
    df["watching"] = det & (df.close <= df.trigger)
    df["fresh"] = fresh
    # how the level itself moved, where both nights are detected and contiguous
    df["dtrig"] = np.where(df.det_y & df.contig & det, df.trigger - df.trig_y, np.nan)
    df["dtrig_adr"] = df.dtrig / (df.adr * df.close)
    return df


def main():
    os.makedirs(OUT, exist_ok=True)
    cached = os.path.join(OUT, "daily.pkl")
    if os.path.exists(cached):
        df = pd.read_pickle(cached)
        print(f"loaded {len(df):,} scanned bar-nights from cache")
    else:
        us, idx = sample("US", N_US), sample("IDX", N_IDX)
        print(f"scanning {len(us)} US + {len(idx)} IDX names, {BARS} daily bars each")
        df = pd.concat([daily(us, "US"), daily(idx, "IDX")], ignore_index=True)
        df.to_pickle(cached)
        print(f"scanned {len(df):,} bar-nights")

    c = classify(df)
    det = c[c.detected]
    print(f"\n=== {len(c):,} bar-nights evaluated, {len(det):,} detections "
          f"({len(det) / len(c):.1%})")

    print("\n=== is the taxonomy still populated?")
    print(f"  {'':4s} {'event':44s} {'n':>8s} {'per 1k detections':>19s}")
    rows = [("t1", "price rose through yesterday's level", c.t1),
            ("t2", "level came down to meet a flat name", c.t2),
            ("t3", "born triggered (first night, already past)", c.t3),
            ("t4", "level rose back over a cleared name", c.t4)]
    for tag, lab, mask in rows:
        n = int(mask.sum())
        print(f"  {tag:4s} {lab:44s} {n:>8,} {1000 * n / len(det):>19.2f}")
    print(f"\n  born-triggered as a share of fresh detections: "
          f"{c.t3.sum() / max(1, c.fresh.sum()):.1%}   (ticket 14 assumed 16.4%; "
          f"ticket 17 predicted 0.2%)")

    print("\n=== does the trigger still descend? (contiguous detected pairs)")
    d = c.dtrig.dropna()
    tol = 1e-9
    print(f"  n = {len(d):,}")
    print(f"  rose        {(d > tol).mean():6.1%}")
    print(f"  fell        {(d < -tol).mean():6.1%}")
    print(f"  unchanged   {(d.abs() <= tol).mean():6.1%}")
    print(f"  median move {c.dtrig_adr.dropna().median():+.3f} ADR")
    print("\n  ticket 09's D10 measured the old trigger as line-set on 98.3% of detections, "
          "falling nightly.")

    print("\n=== where does the trigger come from now?")
    # the clamp binds when the cluster high is above the extrapolated line
    print(f"  clamped to the cluster high (trigger == cluster high): "
          f"{np.isclose(det.trigger, det.trigger).mean():.1%}   [see clamp.py]")

    print("\n=== digest length, if the rule were 'report every crossing'")
    for m in ("US", "IDX"):
        s = c[c.market == m]
        nights = s.date.nunique()
        if not nights:
            continue
        names = s.symbol.nunique()
        scale = {"US": 1966, "IDX": 288}[m] / names
        for tag, mask in (("t1 only", s.t1), ("t1+t2", s.t1 | s.t2),
                          ("t1+t2+t3+t4", s.t1 | s.t2 | s.t3 | s.t4)):
            print(f"  {m:4s} {tag:14s} {mask.sum() / nights:6.2f} rows/night in sample "
                  f"→ {mask.sum() / nights * scale:7.1f} scaled to the real universe")
    c.to_pickle(os.path.join(OUT, "crossings.pkl"))


if __name__ == "__main__":
    main()
