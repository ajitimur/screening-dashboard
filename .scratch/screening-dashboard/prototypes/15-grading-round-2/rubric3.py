"""The rubric on ticket 17's base/cluster structure.

Round 2's `rubric2.py` keeps its structure — ticket 09's S1-S5 are not re-litigated — but three of
its dimensions change domain and one changes definition outright:

  tightness (x2)    was contraction over D3's retained set, which no longer exists. Ticket 17's R4
                    found every narrowness candidate collapses under a base-length control; what
                    survives is CLUSTER LENGTH k. The cluster is selected as the largest 3-7 bar
                    window fitting under TIGHT_MULT x ADR, so its range is compressed by
                    construction and the information sits in how many bars pack into it.
                    Tightness on this structure is a packing count, not a width.

  orderliness (x2)  churn / L, unchanged in form, but over the split's base (median 14 bars)
                    rather than min(L, 20) of D3's longest window (median 3).

  base_length (x1)  same penalty, measured against the split's base.

  ma_support (x1)   D10's distance half is dropped. The split's MA catch-up test already gates
                    every surviving detection, and on the graded cards the distance carries no
                    information once base length is controlled (partial r +0.010, p = 0.93). Only
                    the SMA20-rising half survives, which costs no threshold.

  volume (x1)       dry-up, over the split's base.

Free numbers fall from six to three: `cluster_k`, `orderliness`, `dryup`, plus the length band.
"""

import numpy as np

T3 = {
    "cluster_k": 5,      # ticket 17 R4's one length-free signal
    "orderliness": 0.35,  # round 2's fitted value, carried in — domain has changed under it
    "dryup": 0.95,
    "len_ok": 14,        # the split's own median base
    "len_bad": 40,
}

FIXED = {"adr": 0.05, "sector_share": 0.10, "prior_move": 0.90}

DIMS3 = [
    ("tightness", 2),
    ("orderliness", 2),
    ("prior_move", 1),
    ("base_length", 1),
    ("ma_support", 1),
    ("volume", 1),
    ("sector", 1),
    ("adr", 1),
]

DEFAULT_HALFWIDTH = {"cluster_k": 1.0, "orderliness": 0.14, "dryup": 0.27}


def _ramp(x, lo, hi):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return float(np.clip((x - lo) / (hi - lo), 0, 1))


def _num(v):
    if v is None:
        return None
    v = float(v)
    return None if not np.isfinite(v) else v


def score3(sig, prior_move=None, sector_share=None, mode="boolean", T=None, hw=None):
    T = {**T3, **(T or {})}
    hw = {**DEFAULT_HALFWIDTH, **(hw or {})}
    p, raw = {}, {}

    k = _num(sig.get("cluster_k"))
    raw["tightness"] = k
    if k is None:
        p["tightness"] = 0.5                                   # S5: neutral, not zero
    elif mode == "boolean":
        p["tightness"] = 1.0 if k >= T["cluster_k"] else 0.0
    else:
        p["tightness"] = _ramp(k, T["cluster_k"] - hw["cluster_k"], T["cluster_k"] + hw["cluster_k"])

    o = _num(sig.get("orderliness"))
    raw["orderliness"] = o
    if o is None:
        p["orderliness"] = 0.5
    elif mode == "boolean":
        p["orderliness"] = 1.0 if o <= T["orderliness"] else 0.0
    else:
        p["orderliness"] = _ramp(-o, -(T["orderliness"] + hw["orderliness"]),
                                 -(T["orderliness"] - hw["orderliness"]))

    raw["prior_move"] = prior_move
    p["prior_move"] = None if prior_move is None else (
        1.0 if prior_move >= FIXED["prior_move"] else 0.0)

    Lt = _num(sig.get("L_true"))
    raw["base_length"] = Lt
    if Lt is None:
        p["base_length"] = None
    elif mode == "boolean":
        p["base_length"] = 1.0 if Lt <= T["len_ok"] else 0.0
    else:
        p["base_length"] = _ramp(-Lt, -float(T["len_bad"]), -float(T["len_ok"]))

    rising = sig.get("sma20_rising")
    raw["ma_support"] = rising
    p["ma_support"] = 0.5 if rising is None else (1.0 if rising else 0.0)

    du = _num(sig.get("dryup"))
    raw["volume"] = du
    if du is None:
        p["volume"] = 0.5
    elif mode == "boolean":
        p["volume"] = 1.0 if du <= T["dryup"] else 0.0
    else:
        p["volume"] = _ramp(-du, -(T["dryup"] + hw["dryup"]), -(T["dryup"] - hw["dryup"]))

    raw["sector"] = sector_share
    p["sector"] = None if sector_share is None else (
        1.0 if sector_share >= FIXED["sector_share"] else 0.0)

    a = _num(sig.get("adr"))
    raw["adr"] = a
    p["adr"] = None if a is None else (1.0 if a >= FIXED["adr"] else 0.0)

    total = max_total = 0.0
    for name, w in DIMS3:
        if p.get(name) is None:
            continue
        total += w * p[name]
        max_total += w
    scaled = total * (10.0 / max_total) if max_total else 0.0
    return {"points": p, "raw": raw, "score10": scaled, "stars": scaled / 2.0}


GRIDS = {
    "cluster_k": [3, 4, 5, 6, 7],
    "orderliness": np.round(np.arange(0.20, 0.61, 0.025), 4).tolist(),
    "dryup": np.round(np.arange(0.55, 1.31, 0.05), 3).tolist(),
    "len_ok": list(range(4, 33, 2)),
    "len_bad": list(range(24, 65, 4)),
}
ORDER = ["cluster_k", "orderliness", "len_ok", "len_bad", "dryup"]


def fit(rows, mode="boolean", start=None, rounds=3, objective="mae"):
    """Coordinate descent, round 2's objective and tie-break rule, on the new free numbers."""
    T = dict(start or T3)

    def loss(Tc):
        e = np.array([score3(r["sig"], r["prior_move"], r["sector_share"], mode, Tc)["stars"]
                      - r["eye"] for r in rows], float)
        return float(np.abs(e).mean()) if objective == "mae" else float((e ** 2).mean())

    best = loss(T)
    for _ in range(rounds):
        moved = False
        for key in ORDER:
            for v in GRIDS[key]:
                if key == "len_bad" and v <= T["len_ok"]:
                    continue
                if key == "len_ok" and v >= T["len_bad"]:
                    continue
                cand = {**T, key: v}
                lv = loss(cand)
                if lv < best - 1e-9:
                    best, T, moved = lv, cand, True
        if not moved:
            break
    return T, best
