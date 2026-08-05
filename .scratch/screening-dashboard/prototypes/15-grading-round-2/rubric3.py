"""The rubric on ticket 17's base/cluster structure.

Round 2's `rubric2.py` keeps its structure — ticket 09's S1-S5 are not re-litigated — but three of
its dimensions change domain and one changes definition outright:

  tightness (x2)    was contraction over D3's retained set, which no longer exists. Ticket 17's R4
                    found every narrowness candidate collapses under a base-length control; what
                    survives is CLUSTER LENGTH k. The cluster is selected as the largest 3-7 bar
                    window fitting under TIGHT_MULT x ADR, so its range is compressed by
                    construction and the information sits in how many bars pack into it.
                    Tightness on this structure is a packing count, not a width.

  orderliness (x2)  churn / L over the split's base, scored as a BAND rather than a one-sided
                    cut. Round 3 found the one-sided form counterproductive on a ~14-bar base: the
                    eye prefers higher churn/L, and the fit responded by awarding the point to 99%
                    of cards. A synthetic control (bases of identical length and envelope differing
                    only in orderliness) shows the quantity still measures disorder correctly at
                    every length, so the sign is right and must NOT be flipped. What changes with
                    length is the gap between an ORDERLY base and a GAP-THEN-DEAD one: 2.9x at
                    L=3, 1.8x at L=14, 1.65x at L=30. Over a long base a low churn/L stops meaning
                    "orderly" and starts meaning "quiet", so a one-sided cut hands the point to the
                    lifeless base 3.4 warns about. A band loses the point at BOTH ends, which is
                    what the mechanism implies. Adopted by the trader, ticket 15.

  base_length (x1)  same penalty, measured against the split's base.

  ma_support (x1)   D10's distance half is dropped. The split's MA catch-up test already gates
                    every surviving detection, and on the graded cards the distance carries no
                    information once base length is controlled (partial r +0.010, p = 0.93). Only
                    the SMA20-rising half survives, which costs no threshold.

  volume (x1)       dry-up, over the split's base.

Free numbers: `cluster_k`, `ord_lo`/`ord_hi`, `dryup`, plus the length band.
"""

import numpy as np

T3 = {
    "cluster_k": 5,      # ticket 17 R4's one length-free signal
    "ord_lo": 0.275,      # the orderliness band. Below it the base is quiet rather than orderly;
    "ord_hi": 0.60,       # above it, genuinely disorderly. Both ends lose the point.
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
        p["orderliness"] = 1.0 if T["ord_lo"] <= o <= T["ord_hi"] else 0.0
    else:
        # trapezoid: ramps in below the band, flat across it, ramps out above
        p["orderliness"] = float(min(_ramp(o, T["ord_lo"] - hw["orderliness"], T["ord_lo"]),
                                     _ramp(-o, -(T["ord_hi"] + hw["orderliness"]), -T["ord_hi"])))

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
    "ord_lo": np.round(np.arange(0.100, 0.301, 0.025), 4).tolist(),
    "ord_hi": np.round(np.arange(0.350, 0.701, 0.05), 4).tolist(),
    "dryup": np.round(np.arange(0.55, 1.31, 0.05), 3).tolist(),
    "len_ok": list(range(4, 33, 2)),
    "len_bad": list(range(24, 65, 4)),
}
ORDER = ["cluster_k", "ord_lo", "ord_hi", "len_ok", "len_bad", "dryup"]


def _vector_predictor(rows, mode, hw=None):
    """A vectorised stand-in for score3 over a fixed row set — same arithmetic, one array pass.

    An exhaustive grid search calls the objective ~20k times (boolean) or ~224k (continuous), and
    a per-row Python loop makes that minutes rather than seconds. `_assert_matches_score3` pins
    this to score3 so the speed-up cannot silently change the rubric.
    """
    hw = {**DEFAULT_HALFWIDTH, **(hw or {})}
    n = len(rows)
    k = np.full(n, np.nan)
    o = np.full(n, np.nan)
    du = np.full(n, np.nan)
    L = np.full(n, np.nan)
    fixed_total = np.zeros(n)
    fixed_max = np.zeros(n)

    for i, r in enumerate(rows):
        sig = r["sig"]
        k[i] = _num(sig.get("cluster_k")) if _num(sig.get("cluster_k")) is not None else np.nan
        o[i] = _num(sig.get("orderliness")) if _num(sig.get("orderliness")) is not None else np.nan
        du[i] = _num(sig.get("dryup")) if _num(sig.get("dryup")) is not None else np.nan
        L[i] = _num(sig.get("L_true")) if _num(sig.get("L_true")) is not None else np.nan
        # threshold-independent dimensions, all weight 1
        pm, ss = r["prior_move"], r["sector_share"]
        if pm is not None:
            fixed_total[i] += 1.0 if pm >= FIXED["prior_move"] else 0.0
            fixed_max[i] += 1
        rising = sig.get("sma20_rising")
        fixed_total[i] += 0.5 if rising is None else (1.0 if rising else 0.0)
        fixed_max[i] += 1
        if ss is not None:
            fixed_total[i] += 1.0 if ss >= FIXED["sector_share"] else 0.0
            fixed_max[i] += 1
        a = _num(sig.get("adr"))
        if a is not None:
            fixed_total[i] += 1.0 if a >= FIXED["adr"] else 0.0
            fixed_max[i] += 1

    hasL = np.isfinite(L)
    max_total = fixed_max + 2 + 2 + 1 + hasL.astype(float)

    def ramp(x, lo, hi):
        return np.clip((x - lo) / (hi - lo), 0, 1)

    def predict(T):
        if mode == "boolean":
            pt = np.where(np.isfinite(k), (k >= T["cluster_k"]).astype(float), 0.5)
            po = np.where(np.isfinite(o),
                          ((o >= T["ord_lo"]) & (o <= T["ord_hi"])).astype(float), 0.5)
            pv = np.where(np.isfinite(du), (du <= T["dryup"]).astype(float), 0.5)
            pl = np.where(hasL, (L <= T["len_ok"]).astype(float), 0.0)
        else:
            pt = np.where(np.isfinite(k), ramp(k, T["cluster_k"] - hw["cluster_k"],
                                               T["cluster_k"] + hw["cluster_k"]), 0.5)
            po = np.where(np.isfinite(o),
                          np.minimum(ramp(o, T["ord_lo"] - hw["orderliness"], T["ord_lo"]),
                                     ramp(-o, -(T["ord_hi"] + hw["orderliness"]), -T["ord_hi"])), 0.5)
            pv = np.where(np.isfinite(du), ramp(-du, -(T["dryup"] + hw["dryup"]),
                                                -(T["dryup"] - hw["dryup"])), 0.5)
            pl = np.where(hasL, ramp(-L, -float(T["len_bad"]), -float(T["len_ok"])), 0.0)
        total = fixed_total + 2 * pt + 2 * po + pv + pl * hasL
        return total * 5.0 / max_total

    return predict


def _assert_matches_score3(rows, mode, T):
    v = _vector_predictor(rows, mode)(T)
    s = np.array([score3(r["sig"], r["prior_move"], r["sector_share"], mode, T)["stars"]
                  for r in rows])
    assert np.allclose(v, s, atol=1e-9), f"vector predictor diverged from score3 ({mode})"


def fit(rows, mode="boolean", start=None, rounds=3, objective="mae"):
    """Exhaustive search over GRIDS, minimising the pre-registered objective.

    Round 2 fitted by *coordinate descent* over the same grid, and on round 3's grades that search
    does not reach the optimum of its own objective: it returns mae 1.0875 where an exhaustive pass
    over the identical grid finds 1.0292 — and the point it settles on is degenerate, awarding the
    x2 tightness point to 100% of cards and collapsing the predicted-score SD to 0.45, which makes
    the score nearly constant and destroys the ranking the app sorts on.

    This is a defect in the optimiser, not a change of rule: same grid, same objective, same
    tie-break toward the incumbent. An exhaustive search adds no researcher freedom — there is one
    global optimum and nothing to choose — so it is strictly more faithful to the pre-registration
    than a local search that lands wherever its start point leads.

    `rubric2.fit` has the same shape, so round 2's published thresholds were re-checked: coordinate
    descent from 60 random restarts finds the same optimum (mae 0.9750) as the published one, so
    **round 2's numbers are not affected**. The defect bites here and not there because the split's
    domain makes two dimensions nearly non-discriminating, which flattens the loss surface.
    """
    keys = list(ORDER)
    if mode == "boolean":
        # len_bad is only read by the continuous ramps; leaving it free in boolean mode makes 11
        # identical copies of every grid point and lets an arbitrary tie decide it.
        keys = [k for k in keys if k != "len_bad"]

    predict = _vector_predictor(rows, mode)

    def loss_of(T):
        e = predict(T) - np.array([r["eye"] for r in rows], float)
        return float(np.abs(e).mean()) if objective == "mae" else float((e ** 2).mean())

    incumbent = dict(start or T3)
    best_T, best = dict(incumbent), loss_of(incumbent)
    from itertools import product
    for combo in product(*(GRIDS[k] for k in keys)):
        T = {**incumbent, **dict(zip(keys, combo))}
        if T["len_bad"] <= T["len_ok"] or T["ord_hi"] <= T["ord_lo"]:
            continue
        lv = loss_of(T)
        if lv < best - 1e-9:                     # ties break toward the incumbent
            best, best_T = lv, T
    return best_T, best


def fit_coordinate_descent(rows, mode="boolean", start=None, rounds=3, objective="mae"):
    """Round 2's original local search, kept so the defect above stays reproducible."""
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
