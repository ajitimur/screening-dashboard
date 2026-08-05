import numpy as np
import pandas as pd

df = pd.read_pickle("cache/scored_us.pkl")

# D15's prior-move gate is a GATE (§3.1), not merely a score dimension — apply it.
gated = df[df.prior_move >= 0.90].copy()

# guard the R denominator: a risk of a few basis points makes R explode
for d in (df, gated):
    d["risk_pct"] = (d.trigger - d.base_low) / d.trigger
gated = gated[gated.risk_pct >= 0.005].copy()
gated["Rw"] = gated.R.clip(-1, 10)

t = gated[gated.triggered == True]
print(f"gated detections: {len(gated)}  (from {len(df)} raw)   names={gated.symbol.nunique()}")
print(f"triggered: {gated.triggered.mean():.1%}   mean Rw={t.Rw.mean():.3f}  win={100*(t.Rw>0).mean():.1f}%")
print()


def band_table(d, col, label):
    b = pd.cut(d[col], [0, 1.5, 2.5, 3.5, 4.5, 5.01], labels=["<=1.5", "2", "3", "4", "5"])
    g = d.groupby(b, observed=True).apply(
        lambda x: pd.Series(
            {
                "n": len(x),
                "trig%": round(x.triggered.mean() * 100, 1),
                "meanR": round(x[x.triggered == True].Rw.mean(), 3),
                "win%": round((x[x.triggered == True].Rw > 0).mean() * 100, 1),
                "R>2 %": round((x[x.triggered == True].Rw > 2).mean() * 100, 1),
            }
        )
    )
    print(f"=== {label} ===")
    print(g)
    print()


band_table(gated, "stars_bool", "forward R by BOOLEAN star band (gated)")
band_table(gated, "stars_cont", "forward R by CONTINUOUS star band (gated)")

print("=== per-signal discrimination: mean Rw by quintile of each signal ===")
print("(a dimension that earns its weight should show a monotone column)")
sigs = [
    ("contraction", "tightness x2"),
    ("orderliness", "orderliness x2 (churn/L)"),
    ("churn", "orderliness, 08's raw churn"),
    ("dryup", "volume x1"),
    ("ma_dist_adr", "MA support x1"),
    ("adr", "ADR x1"),
    ("low_slope_adr", "higher lows x1"),
    ("stop_width_adr", "affordability (gate)"),
    ("L_longest", "base length (not scored)"),
    ("n_windows", "retained set size (not scored)"),
]
rows = []
for c, lab in sigs:
    d = t.dropna(subset=[c])
    if len(d) < 100:
        continue
    q = pd.qcut(d[c].rank(method="first"), 5, labels=["q1", "q2", "q3", "q4", "q5"])
    m = d.groupby(q, observed=True).Rw.mean().round(3)
    w = d.groupby(q, observed=True).apply(lambda x: round((x.Rw > 0).mean() * 100, 1))
    rows.append({"signal": lab, **{f"{k}": v for k, v in m.items()}, "spread": round(m.max() - m.min(), 3)})
print(pd.DataFrame(rows).to_string(index=False))
