"""Re-fit every detection in the round-2 pool under both upper-boundary fits.

Deck A's 120 cards established the direction; this sizes it on the whole pool (24,604 US +
6,949 IDX detections), because the three quantities the ticket has to trade off — the trigger,
the already-breached share, and the 1xADR affordability gate — are population properties.

Writes cache/fit_compare.pkl: one row per detection with both triggers and both stop widths.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
sys.path.insert(0, P09)
CACHE = os.path.join(P09, "cache")

import envelope as E  # noqa: E402


def clean(d):
    return d[d["Volume"] > 0].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)


def run(pool, frames, market):
    out = []
    for i, (sym, g) in enumerate(pool.groupby("symbol")):
        d = frames.get(sym)
        if d is None:
            continue
        high = d["High"].to_numpy(float)
        low = d["Low"].to_numpy(float)
        for _, r in g.iterrows():
            end = int(r["end"])
            L = int(r["L"])
            s = end - L + 1
            if s < 0 or end >= len(high):
                continue
            b = E.both(high, low, s, end, float(r["adr"]), float(r["close"]))
            out.append({
                "symbol": sym, "market": market, "date": r["date"], "end": end, "L": L,
                "L_longest": int(r["L_longest"]), "adr": float(r["adr"]),
                "close": float(r["close"]), "stars2": r.get("stars2", np.nan),
                "trigger_pool": float(r["trigger"]), **b,
            })
        if i % 200 == 0:
            print(f"  {market} {i} names, {len(out)} rows", flush=True)
    return pd.DataFrame(out)


VARIANTS = [("ols_min", "OLS + min()      (08 D5, today)"),
            ("env_min", "envelope + min() (fit swapped)"),
            ("ols_max", "OLS + max()      (clamp swapped)"),
            ("env_max", "envelope + max() (q-scanner's trigger)")]


def stop_report(df):
    """D6's gate measures trigger-to-STOP. Ticket 08 stops at the base low; q-scanner stops at
    the cluster low. Pairing q-scanner's trigger with 08's stop overstates the risk, so the
    stop has to be varied too or the max() clamp is judged on a chimera."""
    print("\ngate failures, trigger x stop (share of today's accepted pool D6 would reject)")
    print(f"{'trigger':40s} {'stop = base low':>16s} {'stop = cluster low':>19s}")
    for k, label in VARIANTS:
        t = df[f"trig_{k}"]
        f_base = ((t - df.base_low) / t > df.adr).mean()
        f_cl = ((t - df.cluster_low) / t > df.adr).mean()
        print(f"{label:40s} {f_base:16.1%} {f_cl:19.1%}")
    print(f"\n  cluster low sits above the base low on {(df.cluster_low > df.base_low).mean():.1%} "
          f"of detections;")
    print(f"  median gap {(((df.cluster_low - df.base_low) / (df.adr * df.close))).median():.3f} ADR")


def report(df):
    a = df["adr"] * df["close"]  # ADR in price units
    print(f"\n=== {len(df):,} detections ({df.market.value_counts().to_dict()})")

    print("\nthe 2x2 — fit and clamp are separable, so both are varied")
    print(f"{'variant':40s} {'d trigger':>10s} {'breached':>9s} {'stop ADR':>9s} {'gate fails':>11s}")
    for k, label in VARIANTS:
        d = ((df[f"trig_{k}"] - df.trig_ols_min) / a).mean()
        br = df[f"breached_{k}"].mean()
        sw = (df[f"stopw_{k}"] / df.adr).mean()
        gf = (df[f"stopw_{k}"] > df.adr).mean()
        print(f"{label:40s} {d:+10.3f} {br:9.1%} {sw:9.3f} {gf:11.1%}")
    print("  d trigger: mean move vs today, in ADR.  gate fails: share of today's accepted pool")
    print("  that D6's 1xADR affordability gate would newly reject.")

    print("\nper market, gate failures")
    for m in sorted(df.market.unique()):
        sub = df[df.market == m]
        row = "  ".join(f"{k}={((sub[f'stopw_{k}'] > sub.adr).mean()):.1%}" for k, _ in VARIANTS)
        print(f"  {m:4s} {row}")

    if "stars2" in df and df.stars2.notna().any():
        hi = df[df.stars2 >= 4]
        if len(hi):
            row = "  ".join(f"{k}={((hi[f'stopw_{k}'] > hi.adr).mean()):.1%}" for k, _ in VARIANTS)
            print(f"  4-5 star only ({len(hi):,}): {row}")

    print(f"\nslope of the fitted upper line, ADR/bar:")
    print(f"  OLS      mean {df.ols_slope_adr.mean():+.4f}")
    print(f"  envelope mean {df.env_slope_adr.mean():+.4f}")
    print(f"  envelope line below the OLS line at the last bar: "
          f"{(df.env_line < df.ols_line).mean():.1%}")
    print(f"  max() clamp actually binds (line below cluster high): "
          f"{(df.env_line < df.cluster_high).mean():.1%} env / "
          f"{(df.ols_line < df.cluster_high).mean():.1%} OLS")


if __name__ == "__main__":
    us_pool = pd.read_pickle(os.path.join(CACHE, "pool_us.pkl"))
    us = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_us.pkl")).items()}
    a = run(us_pool, us, "US")

    idx_pool = pd.read_pickle(os.path.join(CACHE, "pool_idx.pkl"))
    idx = {s: clean(d) for s, d in pd.read_pickle(os.path.join(CACHE, "universe_idx.pkl")).items()}
    b = run(idx_pool, idx, "IDX")

    df = pd.concat([a, b], ignore_index=True)
    df.to_pickle(os.path.join(CACHE, "fit_compare.pkl"))
    report(df)
