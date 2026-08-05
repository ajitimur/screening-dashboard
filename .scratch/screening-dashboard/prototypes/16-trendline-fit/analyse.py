"""What the 29.7% gate loss is actually made of.

compare.py found the envelope costs nearly a third of the accepted pool to D6's 1xADR
affordability gate. Before that number can be traded off it has to be decomposed: a pile of
setups sitting just over the threshold is a different problem from setups that were never
affordable and only looked affordable because the OLS line sat too low.
"""

import os
import sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.abspath(os.path.join(HERE, "..", "09-star-score", "cache"))

df = pd.read_pickle(os.path.join(CACHE, "fit_compare.pkl"))
df["sw_ols"] = df.stopw_ols / df.adr
df["sw_env"] = df.stopw_env / df.adr
newly = df[df.sw_env > 1.0]

print(f"pool {len(df):,}   newly gate-rejected under the envelope {len(newly):,} ({len(newly)/len(df):.1%})")

print("\n--- how far over 1xADR do the newly-rejected sit?")
q = newly.sw_env.quantile([0.25, 0.5, 0.75, 0.9]).round(3)
print(q.to_string())
for hi in (1.05, 1.1, 1.25, 1.5):
    share = (newly.sw_env <= hi).mean()
    print(f"  within {hi:.2f} ADR: {share:6.1%} of the newly-rejected "
          f"({(newly.sw_env <= hi).sum():,})")

print("\n--- if D6's threshold were relaxed, what does the pool look like?")
base = (df.sw_ols <= 1.0).sum()
for thr in (1.0, 1.1, 1.25, 1.5):
    keep = (df.sw_env <= thr).sum()
    print(f"  envelope + gate at {thr:.2f} ADR: {keep:,} kept "
          f"({keep/len(df):+.1%} of today's OLS pool of {base:,})")

print("\n--- were the newly-rejected ever affordable, or only on paper?")
print("    (stop width under OLS, for the setups the envelope now rejects)")
print(newly.sw_ols.describe().round(3).to_string())
print(f"    share already above 0.9 ADR under OLS: {(newly.sw_ols > 0.9).mean():.1%}")

print("\n--- does the loss concentrate anywhere?")
df["Lbin"] = pd.cut(df.L, [2, 5, 10, 20, 40, 60])
print(df.groupby("Lbin", observed=True).apply(
    lambda g: pd.Series({"n": len(g), "rejected": (g.sw_env > 1).mean().round(3)}),
    include_groups=False).to_string())
if df.stars2.notna().any():
    print()
    print(df.groupby(df.stars2.round(), observed=True).apply(
        lambda g: pd.Series({"n": len(g), "rejected": (g.sw_env > 1).mean().round(3)}),
        include_groups=False).to_string())

print("\n--- the breached population, which is what F3 was about")
for tag, col in (("OLS", "breached_ols"), ("envelope", "breached_env")):
    b = df[df[col]]
    print(f"  {tag:9s} breached {len(b):,} ({len(b)/len(df):.1%})   "
          f"median depth below close {((b.close - (b.trig_ols if tag=='OLS' else b.trig_env)) / (b.adr*b.close)).median():.3f} ADR")
