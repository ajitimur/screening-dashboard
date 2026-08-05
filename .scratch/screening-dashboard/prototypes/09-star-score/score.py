"""First-cut §3.5 scorer over ticket 08's signals.

Two corrections to ticket 08 are applied here, both established by controlled synthetic tests
(see findings.md). They are flagged inline so the calibration session can see exactly what changed:

  [FIX-1] D7's contraction sign is inverted in 08's write-up. Extending an end-anchored window
          backwards into the WIDE older bars makes range(L) grow FASTER than sqrt(L), not flatter.
          Measured: flat channel 0.86, tight cone 1.59. So higher = more contraction.
  [FIX-2] D8's churn is not scale-free in L (corr 0.87 with base length on real data; 2.2 -> 12.6
          across L=5..40 at fixed disorder). Normalising by L flattens it (0.44 -> 0.31) while
          preserving the smooth/barcode separation (0.19 -> 0.62). Orderliness uses churn / L.

Everything else is 08 as written. Thresholds below are PROVISIONAL — setting them is this ticket's job.
"""

import numpy as np

# Provisional thresholds — the things the calibration session exists to move.
T = {
    "contraction": 1.15,   # [FIX-1] above the sqrt(L) baseline => the base is narrowing
    "orderliness": 0.35,   # [FIX-2] churn/L: mean daily range as a fraction of the envelope
    "ma_dist": 1.0,        # |base low - SMA20| within 1 ADR, and SMA20 rising
    "dryup": 0.85,         # base volume vs the 50 bars before it
    "adr": 0.05,           # §3.5 states this one outright
    "sector_share": 0.10,  # ticket 07: leave-one-out sector share on 1m
}

DIMS = [
    ("tightness", 2),
    ("orderliness", 2),
    ("prior_move", 1),
    ("higher_lows", 1),
    ("ma_support", 1),
    ("volume", 1),
    ("sector", 1),
    ("adr", 1),
]


def score(sig, prior_move=None, sector_share=None, mode="boolean"):
    """sig: a detect() result. Returns per-dimension points, total, stars.

    mode="boolean"    — §3.5 literally: 1 point if the condition holds.
    mode="continuous" — each dimension is a 0..1 ramp around the same threshold.
    """
    p = {}
    raw = {}

    def ramp(x, lo, hi):
        if x is None or (isinstance(x, float) and np.isnan(x)):
            return 0.0
        return float(np.clip((x - lo) / (hi - lo), 0, 1))

    # --- tightness ×2 [FIX-1]: higher contraction ratio = more narrowing
    c = sig.get("contraction")
    raw["tightness"] = c
    if c is None:
        p["tightness"] = 0.0  # single valid window: nothing to measure. 28% of detections.
    elif mode == "boolean":
        p["tightness"] = 1.0 if c >= T["contraction"] else 0.0
    else:
        p["tightness"] = ramp(c, 0.90, 1.60)

    # --- orderliness ×2 [FIX-2]: churn per bar, lower = smoother
    ch = sig.get("churn")
    L = sig.get("L_longest")
    o = (ch / L) if (ch and L) else None
    raw["orderliness"] = o
    if o is None:
        p["orderliness"] = 0.0
    elif mode == "boolean":
        p["orderliness"] = 1.0 if o <= T["orderliness"] else 0.0
    else:
        p["orderliness"] = ramp(-o, -0.60, -0.20)

    # --- prior move ×1: top decile in any of 1m/3m/6m (D15), read from the rank table
    raw["prior_move"] = prior_move
    if prior_move is None:
        p["prior_move"] = None  # not measurable without the universe
    elif mode == "boolean":
        p["prior_move"] = 1.0 if prior_move >= 0.90 else 0.0
    else:
        p["prior_move"] = ramp(prior_move, 0.80, 0.97)

    # --- higher lows ×1: D9 says this IS the low-side fit slope
    ls = sig.get("low_slope_adr")
    raw["higher_lows"] = ls
    if mode == "boolean":
        p["higher_lows"] = 1.0 if (ls is not None and ls > 0) else 0.0
    else:
        p["higher_lows"] = ramp(ls, 0.0, 0.12)

    # --- MA support ×1: D10, one number + rising test
    d = sig.get("ma_dist_adr")
    rising = sig.get("sma20_rising")
    raw["ma_support"] = d
    ok = d is not None and abs(d) <= T["ma_dist"] and rising
    if mode == "boolean":
        p["ma_support"] = 1.0 if ok else 0.0
    else:
        p["ma_support"] = (ramp(-abs(d), -2.5, -0.2) if d is not None else 0.0) * (1.0 if rising else 0.0)

    # --- volume ×1: D11, dry-up only
    du = sig.get("dryup")
    raw["volume"] = du
    if du is None:
        p["volume"] = 0.0
    elif mode == "boolean":
        p["volume"] = 1.0 if du <= T["dryup"] else 0.0
    else:
        p["volume"] = ramp(-du, -1.20, -0.55)

    # --- sector ×1: ticket 07's leave-one-out sector share on 1m
    raw["sector"] = sector_share
    if sector_share is None:
        p["sector"] = None
    elif mode == "boolean":
        p["sector"] = 1.0 if sector_share >= T["sector_share"] else 0.0
    else:
        p["sector"] = ramp(sector_share, 0.04, 0.20)

    # --- ADR ×1
    a = sig.get("adr")
    raw["adr"] = a
    if mode == "boolean":
        p["adr"] = 1.0 if (a is not None and a >= T["adr"]) else 0.0
    else:
        p["adr"] = ramp(a, 0.03, 0.08)

    total = 0.0
    max_total = 0.0
    for name, w in DIMS:
        if p[name] is None:
            continue
        total += w * p[name]
        max_total += w
    # rescale if a dimension was unmeasurable, so stars stay comparable
    scaled = total * (10.0 / max_total) if max_total else 0.0
    return {
        "points": p,
        "raw": raw,
        "total": total,
        "max_total": max_total,
        "score10": scaled,
        "stars": scaled / 2.0,
    }
