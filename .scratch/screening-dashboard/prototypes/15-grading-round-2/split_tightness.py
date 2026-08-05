"""Is §3.5's x2 tightness dimension scorable on the base/cluster structure at all?

Ticket 17's R4 measured five candidates against deck A's 120 grades and found that the two which
look significant collapse to zero under a base-length control — ticket 09's failure mode in new
clothing. It left the question open and named it ticket 15's largest single risk.

This re-runs that test on three populations rather than one, because R4's was in-sample on a deck
built from a detector that no longer exists:

  deckA         114 cards, ticket 08 detections, overlays on          (R4's population)
  deck17        58 cards, BARE candles, no overlay at all             (fresh, out-of-sample)
  split-accept  81 cards the split would actually surface             (the nightly list)

The last one is the one that matters. A rubric ranks the list the detector emits; a tightness
measure that correlates with the eye across a population three quarters of which never appears is
not evidence that it ranks the population that does.

Reported for each candidate: r vs the eye, the partial r controlling for base length, and a
permutation p on the partial. Plus the spread, because a measure pinned into a corner cannot rank
anything however well it correlates.
"""

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
P09 = os.path.abspath(os.path.join(HERE, "..", "09-star-score"))
CACHE = os.path.join(P09, "cache")
sys.path.insert(0, P09)

RNG = np.random.default_rng(15)

CANDIDATES = [
    ("narrow_cluster", "cluster range / ADR       (the 'narrow' half)"),
    ("narrowing_ratio", "cluster range / base range (narrowing)"),
    ("sqrt_shortfall", "sqrt-shortfall over the base"),
    ("base_height_adr", "base height in ADR"),
    ("cluster_k", "cluster length k"),
    ("density", "DENSITY  k / (cluster range in ADR)"),
    ("cluster_churn", "churn over the cluster only"),
]


def derive(df):
    """Two candidates ticket 17 did not test, both suggested by why its five failed.

    The cluster is *selected* as the largest 3-7 bar window fitting under TIGHT_MULT x ADR, so its
    range is compressed by construction (IQR 1.20-1.42, ceiling 1.50) and cannot rank. The
    information the selection leaves behind is not the range but how many bars fit inside it —
    so tightness on this structure is a *density*, bars per unit of range, not a width.
    """
    df = df.copy()
    df["density"] = df.cluster_k / df.cluster_range_adr.replace(0, np.nan)
    return df


def corr(x, y):
    m = np.isfinite(x) & np.isfinite(y)
    if m.sum() < 8:
        return np.nan, int(m.sum())
    return float(np.corrcoef(x[m], y[m])[0, 1]), int(m.sum())


def partial(x, y, z):
    """r(x, y) with z partialled out of both."""
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if m.sum() < 10:
        return np.nan, int(m.sum())
    x, y, z = x[m], y[m], z[m]
    zx = np.polyfit(z, x, 1)
    zy = np.polyfit(z, y, 1)
    rx = x - np.polyval(zx, z)
    ry = y - np.polyval(zy, z)
    if rx.std() == 0 or ry.std() == 0:
        return np.nan, int(m.sum())
    return float(np.corrcoef(rx, ry)[0, 1]), int(m.sum())


def perm_p(x, y, z, n=5000):
    """Permutation p on the partial correlation: shuffle the eye, keep (x, z) paired."""
    m = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    if m.sum() < 10:
        return np.nan
    x, y, z = x[m], y[m], z[m]
    obs = abs(partial(x, y, z)[0])
    hits = 0
    for _ in range(n):
        r = abs(partial(x, RNG.permutation(y), z)[0])
        hits += (r >= obs - 1e-12)
    return (hits + 1) / (n + 1)


def report(df, label):
    eye = df.eye.to_numpy(float)
    blen = df.base_len.to_numpy(float)
    sig = 1.96 / np.sqrt(max(len(df) - 2, 1))
    print(f"\n=== {label}  (n={len(df)}, |r| > {sig:.3f} for p<.05)")
    print(f"{'candidate':46s} {'r vs eye':>9s} {'partial r':>10s} {'perm p':>8s} "
          f"{'median':>8s} {'IQR':>15s}")
    for col, desc in CANDIDATES:
        x = df[col].to_numpy(float)
        r, n = corr(x, eye)
        pr, _ = partial(x, eye, blen)
        pp = perm_p(x, eye, blen)
        fin = x[np.isfinite(x)]
        if not len(fin):
            continue
        q1, q3 = np.percentile(fin, [25, 75])
        print(f"{desc:46s} {r:+9.3f} {pr:+10.3f} {pp:8.3f} "
              f"{np.median(fin):8.2f} {f'{q1:.2f}-{q3:.2f}':>15s}")
    rb, _ = corr(blen, eye)
    print(f"{'base length itself (the trap)':46s} {rb:+9.3f}")


def main():
    df = derive(pd.read_pickle(os.path.join(CACHE, "split_graded.pkl")))

    report(df[df.source == "deckA"], "deck A — ticket 08 detections, overlays on (R4's population)")
    report(df[df.source == "deck17"], "deck 17 — bare candles, no overlay (fresh)")
    report(df[df.split_ok], "SPLIT-ACCEPT — the population the rubric actually ranks")
    report(df, "all graded cards pooled")

    # --- is the 'narrow' half even usable as a ranking key on the real population?
    sp = pd.read_pickle(os.path.join(CACHE, "split.pkl"))
    sp = sp[sp.tight & sp.line_ok & sp.caught_up]
    print(f"\n=== population shape over {len(sp):,} surviving split detections")
    for col in ("cluster_range_adr", "cluster_k", "base_len"):
        x = sp[col].to_numpy(float)
        print(f"  {col:20s} median {np.median(x):6.2f}  "
              f"IQR {np.percentile(x, 25):.2f}-{np.percentile(x, 75):.2f}  "
              f"max {np.nanmax(x):.2f}")
    print(f"  cluster_range_adr pinned within 0.05 of the 1.50 ceiling: "
          f"{(sp.cluster_range_adr > 1.45).mean():.1%}")
    print("  cluster_k distribution: "
          f"{sp.cluster_k.value_counts(normalize=True).sort_index().round(3).to_dict()}")

    # --- deck effect: do the two decks grade the same population differently?
    print("\n=== deck effect check")
    for src in ("deckA", "deck17"):
        s = df[(df.source == src) & df.split_ok]
        print(f"  {src:8s} split-accept cards: n={len(s):3d}  mean eye {s.eye.mean():.2f}")
    def diff(a, b, la, lb):
        obs = b.mean() - a.mean()
        pool = np.concatenate([a, b])
        cnt = 0
        for _ in range(5000):
            p = RNG.permutation(pool)
            cnt += abs(p[:len(b)].mean() - p[len(b):].mean()) >= abs(obs) - 1e-12
        print(f"  {lb} minus {la}: {obs:+.2f} stars (n={len(a)} vs {len(b)}), "
              f"permutation p = {(cnt + 1) / 5001:.3f}")

    a = df[(df.source == "deckA") & df.split_ok].eye.to_numpy(float)
    b = df[(df.source == "deck17") & df.split_ok].eye.to_numpy(float)
    diff(a, b, "deckA split-accepts", "deck17 split-accepts")

    # Presentation or population? deck 17's "shared" arm is the SAME population as deck A's
    # split-accepts — names both detectors fire on — graded bare instead of with overlays.
    sh = df[(df.source == "deck17") & (df.arm == "shared")].eye.to_numpy(float)
    diff(a, sh, "deckA split-accepts", "deck17 SHARED arm (same population, bare)")


if __name__ == "__main__":
    main()
