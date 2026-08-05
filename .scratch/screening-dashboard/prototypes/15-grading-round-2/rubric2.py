"""Round-2 rubric: ticket 09's settled STRUCTURE, with its thresholds left free.

Ticket 09 fixed the structure and explicitly did not fix the numbers. Everything structural below
is carried in unchanged and is NOT up for re-litigation in ticket 15:

  S1  contraction sign — higher ratio = more narrowing (09 F1)
  S2  orderliness is churn / L, not raw churn (09 F2)
  S3  both x2 dimensions are measured over a base capped at HORIZON bars, so they stop being
      proxies for base length (09's decoupling result: r +0.076 -> +0.259)
  S4  base length is a SCORE PENALTY, not a gate, and is paid for by the higher-lows point,
      which F4 showed is free (true for 92% of detections by construction)
  S5  an unmeasurable dimension scores NEUTRAL (0.5), not zero

What is free here is exactly what ticket 15 exists to set:

  contraction cut, churn/L cut, MA-distance band, dry-up cut, and the length penalty band.

Two cuts are deliberately NOT free, because another ticket already fixed them:
  adr >= 0.05        — stated outright by the method reference, §3.5
  sector_share >= 0.10 — ticket 07's leave-one-out rule
  prior_move >= 0.90 — ticket 06/08's decile gate; the dimension mirrors the gate
"""

import numpy as np

HORIZON = 20  # S3's cap. §2/§3.5's own 10/20-day horizon — inherited, not invented.

# Provisional values, carried from ticket 09's `calibrated.py`. THE POINT OF TICKET 15 IS TO MOVE THEM.
T2 = {
    "contraction": 1.15,
    "orderliness": 0.35,
    "ma_dist": 1.0,
    "dryup": 0.85,
    "len_ok": 20,
    "len_bad": 40,
}

FIXED = {"adr": 0.05, "sector_share": 0.10, "prior_move": 0.90}

DIMS2 = [
    ("tightness", 2),
    ("orderliness", 2),
    ("prior_move", 1),
    ("base_length", 1),   # S4: replaces "higher lows"
    ("ma_support", 1),
    ("volume", 1),
    ("sector", 1),
    ("adr", 1),
]

# Continuous mode carries NO extra free parameters: every ramp is the fitted cut plus/minus a
# half-width fixed at 0.5 x the population IQR of that signal (measured once, on the full sweep,
# in `spreads.json`). Pre-registered so "continuous" cannot quietly win by having more knobs.
DEFAULT_HALFWIDTH = {
    "contraction": 0.35,
    "orderliness": 0.12,
    "ma_dist": 0.80,
    "dryup": 0.25,
}


def remeasure(d, end, cap=HORIZON):
    """S3: recompute both x2 dimensions over a base capped at `cap` bars.

    contraction is the length-matched half-vs-half range ratio (older half / recent half), which
    has no L dependence at all; orderliness is churn over the capped window, divided by its length.
    """
    high = d["High"].to_numpy(float)
    low = d["Low"].to_numpy(float)
    Lm = int(min(cap, end))
    if Lm < 4:
        return {"churn": None, "L_eff": Lm, "contraction_half": None}
    s = end - Lm + 1
    env = high[s:end + 1].max() - low[s:end + 1].min()
    churn = float((high[s:end + 1] - low[s:end + 1]).sum() / env) if env > 0 else None
    h = Lm // 2
    r_recent = high[end - h + 1:end + 1].max() - low[end - h + 1:end + 1].min()
    r_older = high[end - 2 * h + 1:end - h + 1].max() - low[end - 2 * h + 1:end - h + 1].min()
    contraction = float(r_older / r_recent) if r_recent > 0 else None
    return {"churn": churn, "L_eff": Lm, "contraction_half": contraction}


def _ramp(x, lo, hi):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return float(np.clip((x - lo) / (hi - lo), 0, 1))


def score2(sig, prior_move=None, sector_share=None, mode="boolean", T=None, hw=None):
    """sig must already carry the S3-remeasured `contraction` and `churn` plus the TRUE `L_true`."""
    T = {**T2, **(T or {})}
    hw = {**DEFAULT_HALFWIDTH, **(hw or {})}
    p, raw = {}, {}

    c = sig.get("contraction")
    raw["tightness"] = c
    if c is None:
        p["tightness"] = 0.5                                            # S5
    elif mode == "boolean":
        p["tightness"] = 1.0 if c >= T["contraction"] else 0.0
    else:
        p["tightness"] = _ramp(c, T["contraction"] - hw["contraction"], T["contraction"] + hw["contraction"])

    ch, Le = sig.get("churn"), sig.get("L_eff")
    o = (ch / Le) if (ch and Le) else None
    raw["orderliness"] = o
    if o is None:
        p["orderliness"] = 0.5
    elif mode == "boolean":
        p["orderliness"] = 1.0 if o <= T["orderliness"] else 0.0
    else:
        p["orderliness"] = _ramp(-o, -(T["orderliness"] + hw["orderliness"]), -(T["orderliness"] - hw["orderliness"]))

    raw["prior_move"] = prior_move
    p["prior_move"] = None if prior_move is None else (
        1.0 if prior_move >= FIXED["prior_move"] else 0.0)

    Lt = sig.get("L_true")
    raw["base_length"] = Lt
    if Lt is None:
        p["base_length"] = None
    elif mode == "boolean":
        p["base_length"] = 1.0 if Lt <= T["len_ok"] else 0.0
    else:
        p["base_length"] = _ramp(-float(Lt), -float(T["len_bad"]), -float(T["len_ok"]))

    dd, rising = sig.get("ma_dist_adr"), sig.get("sma20_rising")
    raw["ma_support"] = dd
    if dd is None:
        p["ma_support"] = 0.5                                           # S5
    elif mode == "boolean":
        p["ma_support"] = 1.0 if (abs(dd) <= T["ma_dist"] and rising) else 0.0
    else:
        p["ma_support"] = (_ramp(-abs(dd), -(T["ma_dist"] + hw["ma_dist"]), -(T["ma_dist"] - hw["ma_dist"])) or 0.0) \
            * (1.0 if rising else 0.0)

    du = sig.get("dryup")
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

    a = sig.get("adr")
    raw["adr"] = a
    p["adr"] = None if a is None else (1.0 if a >= FIXED["adr"] else 0.0)

    total = max_total = 0.0
    for name, w in DIMS2:
        if p.get(name) is None:
            continue
        total += w * p[name]
        max_total += w
    scaled = total * (10.0 / max_total) if max_total else 0.0
    return {"points": p, "raw": raw, "score10": scaled, "stars": scaled / 2.0}


# --------------------------------------------------------------------------- fitting

GRIDS = {
    "contraction": np.round(np.arange(0.90, 1.81, 0.05), 3).tolist(),
    "orderliness": np.round(np.arange(0.20, 0.61, 0.025), 4).tolist(),
    "ma_dist": np.round(np.arange(0.4, 2.61, 0.2), 3).tolist(),
    "dryup": np.round(np.arange(0.55, 1.31, 0.05), 3).tolist(),
    "len_ok": list(range(8, 33, 2)),
    "len_bad": list(range(24, 65, 4)),
}
ORDER = ["contraction", "orderliness", "len_ok", "len_bad", "ma_dist", "dryup"]


def fit(rows, mode="boolean", start=None, rounds=3, objective="mae"):
    """Coordinate descent over GRIDS. `rows` = [{sig, prior_move, sector_share, eye}].

    Objective is mean |stars - eye| (pre-registered). Ties break toward the incumbent value, so a
    threshold only moves on evidence.
    """
    T = dict(start or T2)

    def loss(Tc):
        errs = [score2(r["sig"], r["prior_move"], r["sector_share"], mode, Tc)["stars"] - r["eye"]
                for r in rows]
        e = np.array(errs, float)
        return float(np.abs(e).mean()) if objective == "mae" else float((e ** 2).mean())

    best = loss(T)
    for _ in range(rounds):
        moved = False
        for k in ORDER:
            cur = T[k]
            for v in GRIDS[k]:
                if k == "len_bad" and v <= T["len_ok"]:
                    continue
                if k == "len_ok" and v >= T["len_bad"]:
                    continue
                cand = {**T, k: v}
                lv = loss(cand)
                if lv < best - 1e-9:
                    best, T, moved = lv, cand, True
            if T[k] != cur:
                pass
        if not moved:
            break
    return T, best
