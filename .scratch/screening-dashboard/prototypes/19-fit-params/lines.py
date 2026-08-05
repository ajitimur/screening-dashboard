"""The six line-validity numbers: which of them is actually doing the cutting?

`line_ok` is the single largest behaviour change ticket 17 introduced — it drops 58.8% of ticket
08's picks — and it is decided by six numbers nobody has looked at individually. A sweep answers
"what happens if I move this", which is the wrong question when the real one is "does this
constraint ever bind independently of the others".

So this instruments the test instead of sweeping it: one pass records each constraint's verdict
separately for every candidate that got as far as having a cluster. That gives the marginal cost of
each, and — more usefully — how much of the cut survives dropping any one of them, which is what
tells you whether six numbers are carrying six decisions or one.

The fit itself is duplicated from split.py rather than monkeypatched: it belongs to ticket 16 and
should stay untouched, and the duplication is checked against it (`verify()`).
"""

import os

import numpy as np
import pandas as pd

import harness as H
import split as S

CONSTRAINTS = ["touches", "reaches_back", "overshoot_adr", "overshoot_frac"]


def fit_flags(high, adr_abs, anchor, base_start, as_of, cluster_k):
    """split.fit_line, with each clause of `ok` reported separately."""
    t = np.arange(base_start, as_of + 1)
    h = high[base_start:as_of + 1].astype(float)
    y_a = float(high[anchor])
    slopes = np.linspace(-S.MAX_SLOPE_ADR * adr_abs, 0.0, S.SLOPE_STEPS)
    resid_all = h[None, :] - (y_a + slopes[:, None] * (t - anchor)[None, :])
    loss = S.OVER_W * np.clip(resid_all, 0, None) + S.UNDER_W * np.clip(-resid_all, 0, None)
    m = float(slopes[int(np.argmin(loss.sum(axis=1)))])

    resid = h - (y_a + m * (t - anchor))
    tol = S.TOUCH_TOL_ADR * adr_abs
    cluster_start = as_of - cluster_k + 1
    touch_idx = t[(np.abs(resid) <= tol) & (t < cluster_start)]
    zones = 1 + sum(1 for a, b in zip(touch_idx[:-1], touch_idx[1:]) if b - a >= S.MIN_TOUCH_GAP) \
        if len(touch_idx) else 0
    over = resid > tol
    over_max = float(resid[over].max() / adr_abs) if over.any() else 0.0
    base_len = as_of - base_start + 1
    reaches = bool(len(touch_idx) > 0 and touch_idx[0] <= base_start + 0.6 * base_len)

    return {
        "zones": int(zones),
        "touches": bool(zones >= S.MIN_TOUCHES),
        "reaches_back": bool(zones >= 1 and reaches),
        "overshoot_adr": bool(over_max <= S.MAX_OVERSHOOT_ADR),
        "overshoot_frac": bool(float(over.mean()) <= S.MAX_OVERSHOOT_FRAC),
        "over_max": over_max,
        "over_frac": float(over.mean()),
    }


def collect(market="US"):
    """Every candidate that reached the line test, with each constraint's verdict."""
    path = os.path.join(H.OUT, f"lineflags_{market}.pkl")
    if os.path.exists(path):
        return pd.read_pickle(path)
    rows = []
    for sym, d in sorted(H.frames(market).items()):
        d = d.reset_index(drop=True)
        high, low, close = (d[c].to_numpy(float) for c in ("High", "Low", "Close"))
        adr = pd.Series(high / low - 1.0).rolling(20).mean().to_numpy()
        c = pd.Series(close)
        sma = {n: c.rolling(n).mean().to_numpy() for n in (10, 20, 50)}
        for as_of in range(90, len(d), H.STEP):
            a = adr[as_of]
            if np.isnan(a) or a <= 0:
                continue
            adr_abs = a * close[as_of]
            mv = S.prior_move(high, low, as_of)
            if mv is None:
                continue
            gain, peak = mv
            base_start = peak
            if as_of - base_start + 1 > S.MAX_BASE_LEN:
                recent = as_of - S.MAX_BASE_LEN + 1
                base_start = recent + int(np.argmax(high[recent:as_of + 1]))
            if as_of - base_start + 1 < S.MIN_BASE_LEN:
                continue
            g10 = close[as_of] - sma[10][as_of] if not np.isnan(sma[10][as_of]) else np.inf
            g20 = close[as_of] - sma[20][as_of] if not np.isnan(sma[20][as_of]) else np.inf
            if not (g10 <= S.CATCHUP_10 * adr_abs and g20 <= S.CATCHUP_20 * adr_abs):
                continue
            cl = S.find_cluster(high, low, as_of, adr_abs)
            if cl is None:
                continue
            k = cl[0]
            anchor = (as_of - k + 1) + int(np.argmax(high[as_of - k + 1:as_of + 1]))
            f = fit_flags(high, adr_abs, anchor, base_start, as_of, k)
            f.update({"symbol": sym, "end": as_of, "move_gain": gain,
                      "base_len": as_of - base_start + 1, "cluster_k": k})
            rows.append(f)
    df = pd.DataFrame(rows)
    df.to_pickle(path)
    return df


def verify(df):
    """The duplicated fit must reproduce split.py's own line_ok, or none of this counts."""
    ref = H.scan("US")
    ref = ref[ref.tight.fillna(False) & ref.caught_up.fillna(False)]
    ref = ref[ref.move_gain.notna()]
    mine = df.copy()
    mine["line_ok"] = (mine.touches | mine.reaches_back) & mine.overshoot_adr & mine.overshoot_frac
    j = ref.merge(mine[["symbol", "end", "line_ok"]], on=["symbol", "end"],
                  suffixes=("_ref", "_mine"))
    agree = (j.line_ok_ref.astype(bool) == j.line_ok_mine).mean()
    print(f"=== verification: duplicated fit vs split.py, n={len(j):,}  agreement {agree:.4%}")
    if agree < 0.999:
        print("  MISMATCH — the numbers below are not trustworthy")
    return agree


def main():
    df = collect("US")
    verify(df)
    df = df.copy()
    df["line_ok"] = (df.touches | df.reaches_back) & df.overshoot_adr & df.overshoot_frac
    n = len(df)
    print(f"\n=== line validity on {n:,} candidates that reached the test "
          f"(cluster found, caught up)\n")
    print(f"  line_ok passes   {df.line_ok.mean():.1%}  — the rest is what ticket 17's "
          f"58.8% drop is made of\n")

    print("  each constraint on its own:")
    print(f"  {'constraint':18s} {'passes':>8s} {'fails':>8s}")
    named = {"touches": f"zones >= {S.MIN_TOUCHES}",
             "reaches_back": "zones>=1 & reaches 60% back",
             "overshoot_adr": f"over_max <= {S.MAX_OVERSHOOT_ADR} ADR",
             "overshoot_frac": f"over_frac <= {S.MAX_OVERSHOOT_FRAC:.0%}"}
    for c in CONSTRAINTS:
        print(f"  {named[c]:30s} {df[c].mean():>7.1%} {1 - df[c].mean():>7.1%}")

    print("\n  what each is worth: pass rate if that constraint alone is dropped")
    print(f"  {'dropped':30s} {'line_ok':>9s} {'recovered':>10s}")
    base = df.line_ok.mean()
    for c in CONSTRAINTS:
        parts = {x: df[x] for x in CONSTRAINTS}
        parts[c] = pd.Series(True, index=df.index)
        ok = (parts["touches"] | parts["reaches_back"]) & parts["overshoot_adr"] \
            & parts["overshoot_frac"]
        print(f"  {named[c]:30s} {ok.mean():>8.1%} {ok.mean() - base:>+9.1f}pp"
              .replace("pp", " pp"))

    print("\n  the touch pair is an OR, so neither binds alone — dropping both:")
    ok = df.overshoot_adr & df.overshoot_frac
    print(f"  {'both touch tests':30s} {ok.mean():>8.1%} {ok.mean() - base:>+9.1%}")
    ok2 = (df.touches | df.reaches_back)
    print(f"  {'both overshoot tests':30s} {ok2.mean():>8.1%} {ok2.mean() - base:>+9.1%}")

    print("\n  overlap between the two overshoot tests (are they one decision or two?)")
    a, b = df.overshoot_adr, df.overshoot_frac
    print(f"    fails ADR only     {((~a) & b).mean():>6.1%}")
    print(f"    fails frac only    {(a & (~b)).mean():>6.1%}")
    print(f"    fails both         {((~a) & (~b)).mean():>6.1%}")
    print(f"    corr               {np.corrcoef(a.astype(float), b.astype(float))[0, 1]:>+6.3f}")

    print("\n  TOUCH_TOL_ADR / MIN_TOUCH_GAP feed `zones`; the zone distribution:")
    print(df.zones.value_counts().sort_index().head(8).to_string())


if __name__ == "__main__":
    main()
