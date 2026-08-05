"""The calibrated rubric: the trader's two structural calls, applied and tested once.

Call 1 — base length is a SCORE PENALTY, not a gate. Detection is untouched (08's D14 search
        stands, no Lmax), but long bases lose a point. §3.4's "months of sideways" anti-pattern
        becomes visible in the grade instead of silently topping it.

Call 2 — a single valid window scores NEUTRAL on tightness (half credit), not zero. "Nothing to
        compare against" is absence of evidence, not evidence of absence.

Where the length point comes from: F4 established that "higher lows intact" is true for 92% of
detections BY CONSTRUCTION (validity already requires the low-side slope >= 0), so it is a free
point carrying no information. It is spent on base length instead. This keeps §3.5's eight
dimensions, its max of 10, and stars = score / 2 — no rescaling, no ninth dimension.
"""

import numpy as np

TC = {
    "contraction": 1.15,
    "orderliness": 0.35,
    "ma_dist": 1.0,
    "dryup": 0.85,
    "adr": 0.05,
    "sector_share": 0.10,
    "len_ok": 20,    # §2's own 10/20-day horizon; §3.1 puts the floor at 3
    "len_bad": 40,   # beyond here it is §3.4's "months of sideways"
}

DIMS_CAL = [
    ("tightness", 2),
    ("orderliness", 2),
    ("prior_move", 1),
    ("base_length", 1),   # replaces "higher lows" (F4: free point)
    ("ma_support", 1),
    ("volume", 1),
    ("sector", 1),
    ("adr", 1),
]


def ramp(x, lo, hi):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return float(np.clip((x - lo) / (hi - lo), 0, 1))


def score_cal(sig, prior_move=None, sector_share=None, mode="boolean"):
    p, raw = {}, {}

    # tightness x2 — F1's corrected sign, Call 2's neutral default
    c = sig.get("contraction")
    raw["tightness"] = c
    if c is None:
        p["tightness"] = 0.5  # Call 2
    elif mode == "boolean":
        p["tightness"] = 1.0 if c >= TC["contraction"] else 0.0
    else:
        p["tightness"] = ramp(c, 0.90, 1.60)

    # orderliness x2 — F2's length-normalised churn
    ch, L = sig.get("churn"), sig.get("L_longest")
    o = (ch / L) if (ch and L) else None
    raw["orderliness"] = o
    if o is None:
        p["orderliness"] = 0.5
    elif mode == "boolean":
        p["orderliness"] = 1.0 if o <= TC["orderliness"] else 0.0
    else:
        p["orderliness"] = ramp(-o, -0.60, -0.20)

    raw["prior_move"] = prior_move
    p["prior_move"] = None if prior_move is None else (
        (1.0 if prior_move >= 0.90 else 0.0) if mode == "boolean" else ramp(prior_move, 0.80, 0.97))

    # base length x1 — Call 1
    Lm = sig.get("L_longest")
    raw["base_length"] = Lm
    if Lm is None:
        p["base_length"] = None
    elif mode == "boolean":
        p["base_length"] = 1.0 if Lm <= TC["len_ok"] else 0.0
    else:
        p["base_length"] = ramp(-Lm, -TC["len_bad"], -TC["len_ok"])

    d, rising = sig.get("ma_dist_adr"), sig.get("sma20_rising")
    raw["ma_support"] = d
    if mode == "boolean":
        p["ma_support"] = 1.0 if (d is not None and abs(d) <= TC["ma_dist"] and rising) else 0.0
    else:
        p["ma_support"] = (ramp(-abs(d), -2.5, -0.2) or 0.0) * (1.0 if rising else 0.0) if d is not None else 0.0

    du = sig.get("dryup")
    raw["volume"] = du
    p["volume"] = 0.5 if du is None else (
        (1.0 if du <= TC["dryup"] else 0.0) if mode == "boolean" else ramp(-du, -1.20, -0.55))

    raw["sector"] = sector_share
    p["sector"] = None if sector_share is None else (
        (1.0 if sector_share >= TC["sector_share"] else 0.0) if mode == "boolean"
        else ramp(sector_share, 0.04, 0.20))

    a = sig.get("adr")
    raw["adr"] = a
    p["adr"] = (1.0 if (a is not None and a >= TC["adr"]) else 0.0) if mode == "boolean" else (ramp(a, 0.03, 0.08) or 0.0)

    total = max_total = 0.0
    for name, w in DIMS_CAL:
        if p[name] is None:
            continue
        total += w * p[name]
        max_total += w
    scaled = total * (10.0 / max_total) if max_total else 0.0
    return {"points": p, "raw": raw, "score10": scaled, "stars": scaled / 2.0}
