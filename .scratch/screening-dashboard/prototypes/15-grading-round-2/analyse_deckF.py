"""Deck F — the pre-registered analysis, and nothing else.

Usage:  analyse_deckF.py F=<105-char grade string, '-' for ungraded>

Every rule below is fixed by PREREGISTRATION_DECK_F.md and this file implements it mechanically,
so the verdict is not a judgement call made after seeing the numbers. §5's decision table is
applied at the bottom and printed as a verdict.

  primary    mean eye, line_not_drawable minus detection, with a 95% CI
  secondary  the same for not_caught_up — descriptive, no remedy attached (two tests, one control)
  ceiling    deck F's 6 repeats, and the pooled figure across every deck
"""

import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
NOISE_FLOOR = 0.46          # pooled 24-pair mean |difference|, PREREGISTRATION_DECK_F §4
POWERED_AT = 20             # below this per arm, report as underpowered (§2)


def welch(a, b):
    """Mean difference a - b, its standard error and a 95% CI. Welch, unequal variances."""
    d = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    df = (a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b)) ** 2 / (
        (a.var(ddof=1) / len(a)) ** 2 / (len(a) - 1)
        + (b.var(ddof=1) / len(b)) ** 2 / (len(b) - 1))
    t = stats.t.ppf(0.975, df)
    p = 2 * (1 - stats.t.cdf(abs(d / se), df))
    return d, se, (d - t * se, d + t * se), p


def dist(g):
    return ", ".join(str(int((g == v).sum())) for v in (1, 2, 3, 4, 5))


def arm_table(df):
    print("\n=== 1. the arms\n")
    print(f"  {'arm':22s} {'n':>3s}  {'1★→5★':16s} {'mean':>6s} {'≥4★':>6s}")
    for tag in ("detection", "line_not_drawable", "not_caught_up", "repeat"):
        g = df[df.tag == tag].eye
        if len(g):
            print(f"  {tag:22s} {len(g):3d}  {dist(g):16s} {g.mean():6.2f} "
                  f"{(g >= 4).mean():6.0%}")


def contrast(df, tag, label, primary):
    det = df[df.tag == "detection"].eye.to_numpy(float)
    rej = df[df.tag == tag].eye.to_numpy(float)
    if len(det) < 5 or len(rej) < 5:
        print(f"  {label}: arms too thin to contrast.")
        return None
    d, se, ci, p = welch(rej, det)
    kind = "PRIMARY" if primary else "secondary"
    print(f"\n  {kind}  {tag} minus detection")
    print(f"    Δ = {d:+.2f}★   se {se:.2f}   95% CI {ci[0]:+.2f} to {ci[1]:+.2f}   p = {p:.3f}")
    if min(len(det), len(rej)) < POWERED_AT:
        print(f"    UNDERPOWERED — {min(len(det), len(rej))} graded in the thinner arm, "
              f"{POWERED_AT} required before this is read as a result (§2).")
    return d, ci


def length_control(df, tag):
    """Δ with base length partialled out — OLS of eye on (arm dummy, base_len)."""
    d = df[df.tag.isin(["detection", tag]) & df.base_len.notna()]
    if len(d) < 20:
        return
    X = np.column_stack([np.ones(len(d)), (d.tag == tag).to_numpy(float),
                         d.base_len.to_numpy(float)])
    y = d.eye.to_numpy(float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    s2 = resid @ resid / (len(d) - X.shape[1])
    se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
    t = stats.t.ppf(0.975, len(d) - X.shape[1])
    print(f"    controlling base length: Δ = {beta[1]:+.2f}★  "
          f"95% CI {beta[1]-t*se:+.2f} to {beta[1]+t*se:+.2f}  "
          f"(base_len coefficient {beta[2]:+.3f}★/bar)")


def failure_modes(df):
    """Which sub-test the graded line_not_drawable cards failed — §6's remedy 2 reads this."""
    d = df[(df.tag == "line_not_drawable") & df.eye.notna()].copy()
    if not len(d):
        return
    z = d.touch_zones.fillna(0)
    o = d.overshoot_adr.fillna(0)
    groups = {"touches only": (z < 2) & (o <= 1.0),
              "overshoot only": (z >= 2) & (o > 1.0),
              "both": (z < 2) & (o > 1.0),
              "overshoot_frac only": (z >= 2) & (o <= 1.0)}
    det = df[df.tag == "detection"].eye.mean()
    print("\n=== 3. which sub-test the rejected cards failed  "
          f"(detections mean {det:.2f})\n")
    for lab, m in groups.items():
        g = d[m].eye
        if len(g):
            print(f"  {lab:22s} n={len(g):2d}  mean {g.mean():.2f}  "
                  f"Δ {g.mean()-det:+.2f}★  ≥4★ {(g >= 4).mean():.0%}")
        else:
            print(f"  {lab:22s} n= 0")


def ceiling(df):
    """Deck F's own repeat pairs, and the pooled figure across every deck that has any."""
    print("\n=== 4. the ceiling")
    a3 = pd.read_csv(os.path.join(HERE, "deck3_manifest.csv"))
    a3 = a3[a3.deck == "A"].copy()
    g_a = open(os.path.join(HERE, "grades3_A.txt")).read().strip()
    a3["eye"] = [int(c) if c.isdigit() else np.nan for c in g_a[:len(a3)]]
    look = {(r.symbol, int(r.end)): r.eye for _, r in a3.iterrows() if not pd.isna(r.eye)}

    pairs = []
    for _, r in df[(df.tag == "repeat") & df.eye.notna()].iterrows():
        first = look.get((r.symbol, int(r.end)))
        if first is not None:
            pairs.append((float(first), float(r.eye)))
    if len(pairs) >= 4:
        a = np.array([p[0] for p in pairs]); b = np.array([p[1] for p in pairs])
        print(f"  deck F alone: n={len(pairs)}  r = {np.corrcoef(a, b)[0,1]:+.3f}  "
              f"mean |difference| {np.abs(a-b).mean():.2f}★")
    else:
        print(f"  deck F repeats graded: {len(pairs)} — too few to read alone.")
    print("  pool with the existing 24 pairs via "
          "`analyse3.py A= C= D= E=` (reads +0.855 / 0.46★ at 24).")


def verdict(primary, n_thin):
    print("\n=== 5. the pre-registered verdict  (PREREGISTRATION_DECK_F.md §5)\n")
    if primary is None:
        print("  not gradable yet.")
        return
    if n_thin < POWERED_AT:
        print(f"  NO VERDICT — {n_thin} cards graded in the thinner primary arm, {POWERED_AT} "
              "required.")
        print("  §2 fixed this in advance: below that, the result is reported as underpowered")
        print("  and not as a verdict. Grade more of the deck — it is shuffled, so any prefix")
        print("  is an unbiased sample.")
        return
    d, (lo, hi) = primary
    if hi < 0:
        print("  CI entirely below zero — the path rejects names the eye also rejects.")
        print("  => `line_ok` STANDS as specified. Ticket 23's discharge extends to it.")
    elif lo > 0:
        print("  CI entirely above zero — the path is discarding the BETTER names.")
        print("  => REMEDY FIRES, and `line_ok` is presumed wrong rather than merely unproven.")
        print("     §6 option 3 (delete `line_ok` from detection) is in range.")
    elif abs(d) <= NOISE_FLOOR:
        print(f"  CI spans zero and |Δ| = {abs(d):.2f}★ is within the eye's own {NOISE_FLOOR:.2f}★ "
              "noise floor.")
        print("  => the path is INDISTINGUISHABLE from what the screen surfaces.")
        print("     This is a finding, not a pass. REMEDY FIRES — §6 option 1 is the default")
        print("     (downgrade from a hard reject to a scored penalty).")
    else:
        print(f"  CI spans zero but |Δ| = {abs(d):.2f}★ exceeds the {NOISE_FLOOR:.2f}★ noise floor.")
        print("  => genuinely unresolved at this n. Report as underpowered, change nothing,")
        print("     and say what n would settle it.")


def main(grades):
    m = pd.read_csv(os.path.join(HERE, "deckF_manifest.csv"))
    g = grades.strip()
    if len(g) != len(m):
        print(f"warning: {len(g)} grades for {len(m)} cards — padding with '-'")
        g = (g + "-" * len(m))[:len(m)]
    m["eye"] = [float(c) if c.isdigit() else np.nan for c in g]
    df = m[m.eye.notna()].copy()
    print(f"deck F: {len(df)} of {len(m)} cards graded")

    arm_table(df)
    print("\n=== 2. the contrasts\n")
    primary = contrast(df, "line_not_drawable", "primary", True)
    if primary:
        length_control(df, "line_not_drawable")
    sec = contrast(df, "not_caught_up", "secondary", False)
    if sec:
        length_control(df, "not_caught_up")
        print("    two comparisons share one control arm — a nominal 0.05 here is not a discovery.")
    failure_modes(df)
    ceiling(df)
    verdict(primary, min((df.tag == "detection").sum(),
                         (df.tag == "line_not_drawable").sum()))


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    kv = {a.split("=", 1)[0].upper(): a.split("=", 1)[1] for a in args}
    main(kv.get("F", ""))
