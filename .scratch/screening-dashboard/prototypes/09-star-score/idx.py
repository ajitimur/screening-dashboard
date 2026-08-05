"""IDX slice — specifically to test ticket 08's D13 (limit-day flattery).

A limit-locked (ARA/ARB) bar has a collapsed high/low range. D13 predicts that flatters BOTH x2
dimensions at once, so a dead stock can score as a textbook base. This fetches enough IDX names to
see whether that actually happens, and flags bars whose range is ~0 as limit-lock suspects.
"""

import os
import time
import numpy as np
import pandas as pd
import yfinance as yf

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")

# A spread of IDX names: large caps, plus the mid/small names where ARA/ARB actually bites.
NAMES = """BBRI BBCA BMRI BBNI TLKM ASII UNVR ICBP INDF KLBF GGRM HMSP UNTR ADRO PTBA ITMG
INCO ANTM TINS MDKA BRPT TPIA BRMS ENRG MEDC PGAS JSMR SMGR INTP CPIN JPFA MYOR
ACES MAPI ERAA LPPF RALS SIDO TKIM INKP AKRA ELSA WIKA WSKT PTPP ADHI EXCL ISAT
FREN BUKA GOTO ARTO BBHI BBYB AGRO AMMN BREN CUAN PANI TOBA HRUM DEWA BUMI ESSA
NCKL RAJA SRTG PSAB DOID SMDR TMAS HEAL MIKA SILO BTPS BJTM BJBR NISP BNGA MEGA""".split()

if __name__ == "__main__":
    frames = {}
    path = os.path.join(CACHE, "universe_idx.pkl")
    if os.path.exists(path):
        frames = pd.read_pickle(path)
    todo = [n for n in NAMES if n not in frames]
    print(f"fetching {len(todo)} IDX names", flush=True)
    for i in range(0, len(todo), 20):
        chunk = [f"{n}.JK" for n in todo[i : i + 20]]
        df = yf.download(
            chunk, start="2017-01-01", end="2024-12-31", auto_adjust=True,
            progress=False, threads=True, group_by="ticker",
        )
        for s in chunk:
            try:
                d = df[s].dropna(how="all")
            except Exception:
                continue
            if len(d) > 300:
                frames[s.replace(".JK", "")] = d.reset_index()
        print(f"  {i+len(chunk)}/{len(todo)} kept={len(frames)}", flush=True)
        time.sleep(1.5)
    pd.to_pickle(frames, path)

    # how common are collapsed-range bars? (limit-lock suspects)
    rows = []
    for s, d in frames.items():
        d = d[d["Volume"] > 0]
        rng = (d["High"] / d["Low"] - 1.0)
        rows.append({"symbol": s, "n": len(d), "zero_range%": round(100 * (rng < 1e-9).mean(), 2),
                     "tiny_range%": round(100 * (rng < 0.005).mean(), 2)})
    r = pd.DataFrame(rows).sort_values("zero_range%", ascending=False)
    print(f"\nDONE {len(frames)} IDX names")
    print("collapsed-range bars (limit-lock suspects), worst 12:")
    print(r.head(12).to_string(index=False))
    print(f"\nacross all IDX names: zero-range {r['zero_range%'].mean():.2f}% of bars, "
          f"sub-0.5%-range {r['tiny_range%'].mean():.2f}%")
