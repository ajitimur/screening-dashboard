"""Attach scores + forward outcomes to every detection in the sweep.

Outcome model follows §7 as closely as EOD data allows:
  - entry  = trigger, taken on the first of the next 10 bars whose HIGH crosses it (else no trade)
  - stop   = base low, hit if any subsequent LOW touches it
  - result = whichever comes first over the next 30 bars, else mark-to-market at bar 30
Expressed in R (multiples of the risk trigger->base low), which is the only unit §7/§8 care about.

Survivorship bias applies (ticket 02): delisted names are absent, so these numbers are optimistic
in level. They are used here only to COMPARE score bands against each other, which is far less
sensitive to that bias than the absolute level is.
"""

import os
import numpy as np
import pandas as pd
from score import score
import ranks as R

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")


def outcome(d, end, trigger, stop, entry_window=10, hold=30):
    hi = d["High"].to_numpy(float)
    lo = d["Low"].to_numpy(float)
    cl = d["Close"].to_numpy(float)
    n = len(d)
    risk = trigger - stop
    if risk <= 0:
        return None
    ent = None
    for i in range(end + 1, min(end + 1 + entry_window, n)):
        if hi[i] >= trigger:
            ent = i
            break
    if ent is None:
        return {"triggered": False}
    for j in range(ent, min(ent + hold, n)):
        if lo[j] <= stop:
            return {"triggered": True, "R": (stop - trigger) / risk, "bars": j - ent, "stopped": True}
    j = min(ent + hold, n) - 1
    return {"triggered": True, "R": (cl[j] - trigger) / risk, "bars": j - ent, "stopped": False}


if __name__ == "__main__":
    frames = pd.read_pickle(os.path.join(CACHE, "universe_us.pkl"))
    sw = pd.read_pickle(os.path.join(CACHE, "sweep_us.pkl"))
    rk, elig, C = R.load_or_build()
    sp = os.path.join(CACHE, "sectors_us.pkl")
    sectors = pd.read_pickle(sp) if os.path.exists(sp) else {}
    print(f"sectors known for {len(sectors)} names", flush=True)

    clean = {}
    for s, d in frames.items():
        clean[s] = (
            d[d["Volume"] > 0].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)
        )

    recs = []
    for i, (sym, g) in enumerate(sw.groupby("symbol")):
        d = clean[sym]
        for _, r in g.iterrows():
            sig = r.to_dict()
            pm = R.prior_move_pct(rk, sym, r["date"])
            ss = R.sector_share_loo(rk, sectors, sym, r["date"]) if sectors else None
            sb = score(sig, prior_move=pm, sector_share=ss, mode="boolean")
            sc = score(sig, prior_move=pm, sector_share=ss, mode="continuous")
            o = outcome(d, int(r["end"]), r["trigger"], r["base_low"])
            recs.append(
                {
                    "symbol": sym,
                    "date": r["date"],
                    "end": int(r["end"]),
                    "prior_move": pm,
                    "sector_share": ss,
                    "stars_bool": sb["stars"],
                    "stars_cont": sc["stars"],
                    "score10_bool": sb["score10"],
                    "score10_cont": sc["score10"],
                    "pts_bool": sb["points"],
                    "triggered": (o or {}).get("triggered"),
                    "R": (o or {}).get("R"),
                    "stopped": (o or {}).get("stopped"),
                    **{
                        k: r[k]
                        for k in [
                            "L", "L_longest", "n_windows", "adr", "contraction", "churn",
                            "dryup", "ma_dist_adr", "sma20_rising", "low_slope_adr",
                            "stop_width_adr", "trigger", "base_low", "base_high", "close",
                            "trigger_bound_by",
                        ]
                    },
                }
            )
        if i % 100 == 0:
            print(f"  {i} names, {len(recs)} recs", flush=True)
    out = pd.DataFrame(recs)
    out["orderliness"] = out["churn"] / out["L_longest"]
    out.to_pickle(os.path.join(CACHE, "scored_us.pkl"))
    print("DONE", len(out), flush=True)
