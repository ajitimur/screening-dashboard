"""Do length-decoupled variants of the two x2 dimensions agree with the eye better?

WARNING ON OVERFITTING: n=27 graded charts. Each variant below is a single a-priori structural
change motivated by the method text, tested once. No thresholds are tuned against the grades.
With n=27 a correlation needs |r| > ~0.38 to clear p<0.05, so anything below that is noise.
"""

import numpy as np
import pandas as pd
import build_deck as B
from grades import EYE
from score import score, DIMS

us = B.US
idx = B.IDX

HORIZON = 20  # §2/§3.5's own 10/20-day horizon; §3.4 rejects "months of sideways"


def remeasure(d, end, L_cap):
    """Recompute the two x2 dimensions over a base capped at L_cap bars."""
    high = d["High"].to_numpy(float)
    low = d["Low"].to_numpy(float)
    n = len(d)
    out = {}
    Lm = min(L_cap, end)
    s = end - Lm + 1
    env = high[s : end + 1].max() - low[s : end + 1].min()
    out["churn"] = float((high[s : end + 1] - low[s : end + 1]).sum() / env) if env > 0 else None
    out["L_eff"] = Lm
    # contraction: recent half's range vs older half's range, length-matched (no L dependence at all)
    h = Lm // 2
    r_recent = high[end - h + 1 : end + 1].max() - low[end - h + 1 : end + 1].min()
    r_older = high[end - 2 * h + 1 : end - h + 1].max() - low[end - 2 * h + 1 : end - h + 1].min()
    out["contraction_half"] = float(r_older / r_recent) if r_recent > 0 else None
    return out


rows = []
for c in B.cards:
    i = c["i"]
    p = B.picks[i - 1]
    r = p["row"]
    d = p["frames"][c["sym"]]
    end = int(r["end"])
    sig = r.to_dict()
    sig["detected"] = True
    pm = r.get("prior_move") if p["market"] == "US" else None
    ss = r.get("sector_share") if p["market"] == "US" else None
    if isinstance(ss, float) and np.isnan(ss):
        ss = None
    if isinstance(pm, float) and np.isnan(pm):
        pm = None

    base = score(sig, pm, ss, "boolean")["stars"]

    # variant A: cap the base at the method's own 20-day horizon
    m = remeasure(d, end, HORIZON)
    sigA = dict(sig)
    sigA["churn"] = m["churn"]
    sigA["L_longest"] = m["L_eff"]
    sigA["contraction"] = m["contraction_half"]
    vA = score(sigA, pm, ss, "boolean")["stars"]

    # variant B: cap at 20 AND use the length-matched half-vs-half contraction
    sigB = dict(sigA)
    vB = score(sigB, pm, ss, "continuous")["stars"]

    rows.append(
        {
            "i": i, "sym": c["sym"], "mkt": c["market"], "eye": EYE[i],
            "base": base, "capped20_bool": vA, "capped20_cont": vB,
            "L_longest": int(r["L_longest"]), "contraction_half": m["contraction_half"],
            "churn20": m["churn"], "orderliness20": (m["churn"] / m["L_eff"]) if m["churn"] else np.nan,
        }
    )

df = pd.DataFrame(rows).sort_values("i")
pd.set_option("display.width", 220)
print(df.to_string(index=False))
print()
n = len(df)
crit = 0.38
print(f"n={n}; |r| must exceed ~{crit} for p<0.05\n")
for col in ["base", "capped20_bool", "capped20_cont"]:
    e = df[col] - df.eye
    r_ = df[col].corr(df.eye)
    print(f"{col:15s} r={r_:+.3f} {'*' if abs(r_)>crit else ' '}  mean|err|={e.abs().mean():.2f}  within1={100*(e.abs()<=1).mean():.0f}%")
print()
print("raw length-decoupled signals vs the eye:")
for s in ["contraction_half", "orderliness20", "churn20", "L_longest"]:
    sub = df.dropna(subset=[s])
    r_ = sub[s].corr(sub.eye)
    print(f"  {s:18s} r={r_:+.3f} {'*' if abs(r_)>crit else ''}")
