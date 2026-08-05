"""Compare the trader's blind grades against the computed score, and against every raw signal.

The point is not the correlation headline. It is: WHICH quantities does the eye actually track,
including quantities ticket 08 chose not to score.
"""

import os
import numpy as np
import pandas as pd
import build_deck as B  # reuses the exact same card assembly (same seeds => same cards)

EYE = {
    1: 4, 2: 1, 3: 1, 4: 3, 5: 2, 6: 4, 7: 4, 8: 4, 9: 3, 10: 1, 11: 1, 12: 3, 13: 3, 14: 2,
    15: 3, 16: 5, 17: 4, 18: 1, 19: 1, 20: 4, 21: 1, 22: 3, 23: 2, 24: 3, 25: 2, 26: 1, 27: 1,
}

rows = []
for c in B.cards:
    i = c["i"]
    p = B.picks[i - 1]
    r = p["row"]
    rows.append(
        {
            "i": i,
            "sym": c["sym"],
            "mkt": c["market"],
            "tag": c["tag"],
            "eye": EYE[i],
            "bool": c["stars_bool"],
            "cont": c["stars_cont"],
            "err_bool": c["stars_bool"] - EYE[i],
            "err_cont": c["stars_cont"] - EYE[i],
            "outcome": c["outcome"],
            "L": int(r["L"]),
            "L_longest": int(r["L_longest"]),
            "n_windows": int(r["n_windows"]),
            "adr": float(r["adr"]),
            "contraction": r["contraction"],
            "churn": r["churn"],
            "orderliness": (r["churn"] / r["L_longest"]) if r["L_longest"] else np.nan,
            "dryup": r["dryup"],
            "ma_dist_adr": r["ma_dist_adr"],
            "sma20_rising": r["sma20_rising"],
            "low_slope_adr": r["low_slope_adr"],
            "stop_width_adr": r["stop_width_adr"],
            "trigger_bound_by": r["trigger_bound_by"],
            "trig_vs_close": float(r["trigger"]) / float(r["close"]) - 1.0,
        }
    )
df = pd.DataFrame(rows).sort_values("i")
df.to_pickle(os.path.join(B.CACHE, "grades.pkl"))
pd.set_option("display.width", 250)

print("=== every card, eye vs machine ===")
print(df[["i", "sym", "mkt", "tag", "eye", "bool", "cont", "err_bool"]].to_string(index=False))

print("\n=== headline agreement ===")
for col in ["bool", "cont"]:
    e = df[col] - df.eye
    print(f"{col:5s}: pearson r={df[col].corr(df.eye):+.3f}  spearman={df[col].rank().corr(df.eye.rank()):+.3f}  "
          f"mean err={e.mean():+.2f}  mean |err|={e.abs().mean():.2f}  within 1 star={100*(e.abs()<=1).mean():.0f}%")

print("\n=== worst disagreements ===")
d = df.reindex(df.err_bool.abs().sort_values(ascending=False).index)
print(d[["i", "sym", "mkt", "tag", "eye", "bool", "err_bool", "L", "L_longest", "n_windows",
         "adr", "contraction", "orderliness", "trig_vs_close"]].head(12).to_string(index=False))

print("\n=== what does the EYE track? (correlation with the trader's grade) ===")
sigs = ["contraction", "orderliness", "churn", "dryup", "ma_dist_adr", "adr", "low_slope_adr",
        "stop_width_adr", "L", "L_longest", "n_windows", "trig_vs_close"]
tab = []
for s in sigs:
    sub = df.dropna(subset=[s])
    tab.append({
        "signal": s,
        "vs eye": round(sub[s].corr(sub.eye), 3),
        "vs machine": round(sub[s].corr(sub["bool"]), 3),
        "scored?": "yes" if s in ("contraction", "orderliness", "dryup", "ma_dist_adr", "adr", "low_slope_adr") else "NO",
    })
print(pd.DataFrame(tab).sort_values("vs eye", key=abs, ascending=False).to_string(index=False))

print("\n=== did the eye beat the machine on outcome? ===")
df["triggered"] = ~df.outcome.str.startswith("never")
df["R"] = df.outcome.str.extract(r"([+-]?\d+\.\d)R").astype(float)
df.loc[df.outcome.str.contains("stopped out"), "R"] = -1.0
for lab, col in [("eye", "eye"), ("machine bool", "bool")]:
    hi = df[df[col] >= 4]
    lo = df[df[col] < 4]
    print(f"{lab:13s}: >=4 stars n={len(hi):2d} mean R={hi.R.mean():+.2f} | <4 stars n={len(lo):2d} mean R={lo.R.mean():+.2f}")
