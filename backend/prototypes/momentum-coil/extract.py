"""PROTOTYPE — throwaway. Nothing imports this. Not part of the pipeline.

Dump bars + coil detections for a few symbols into bars.js for the HTML
viewer, and report recall against the golden set. Usage:

    backend/.venv/bin/python backend/prototypes/momentum-coil/extract.py [SYM.JK ...]

Defaults to the golden-set symbols. Reads data/screener.duckdb read-only.
"""

import json
import sys
from pathlib import Path

import duckdb

import coil

STORE = Path(__file__).resolve().parents[3] / "data" / "screener.duckdb"
OUT = Path(__file__).resolve().parent / "bars.js"
TAIL = 600  # bars per symbol: all of 2026 plus plenty of MA50 runway

# Must-catch boxes, marked by eye (grilling 2026-09-13). A window is caught
# when the detector fires on at least one session inside it.
GOLDEN = [
    ("SGER.JK", "2026-08-05", "2026-08-27"),
    ("TINS.JK", "2026-08-17", "2026-08-31"),
    ("SOCI.JK", "2026-08-06", "2026-08-14"),
    ("SOCI.JK", "2026-08-20", "2026-08-27"),
    ("KOKA.JK", "2026-08-26", "2026-09-08"),
    ("GTSI.JK", "2026-08-10", "2026-08-20"),   # relabelled fine 2026-09-13
    ("PTRO.JK", "2026-08-13", "2026-08-21"),   # the box, before it widens
    # August labelling pass (2026-09-13): plain-yes names, window = the month.
    *[(s + ".JK", "2026-08-01", "2026-08-31") for s in
      "AADI ADMR AMMN AYAM BDMN DATA DSNG DSSA EMAS ERAA GJTL HOPE ICBP "
      "INTP ISAT KJEN PADI PGEO SIMP TEBE TOBA YELO".split()],
    # "ok, but" names — desired box noted; any-fire criterion can't test the
    # desired END, so the span disagreements live in the README, not here.
    ("GGRM.JK", "2026-08-01", "2026-08-31"),   # box should run to 08-28
    ("HRUM.JK", "2026-08-06", "2026-08-31"),   # box should start 08-06
    ("IATA.JK", "2026-08-01", "2026-08-31"),   # box should end 08-28
    ("NCKL.JK", "2026-08-01", "2026-08-31"),   # box should run to 08-31
    # corrected-box names — the eye's window verbatim.
    ("CMRY.JK", "2026-07-09", "2026-08-28"),   # a LONG base, ~35 trading days
    # July out-of-sample pass (2026-09-13).
    ("MAPI.JK", "2026-07-01", "2026-07-31"),
    ("RGAS.JK", "2026-07-01", "2026-07-31"),
    ("PKPK.JK", "2026-07-01", "2026-07-31"),
    ("SMRA.JK", "2026-07-30", "2026-08-14"),   # box should run to 08-14
    ("MARK.JK", "2026-06-15", "2026-06-30"),   # real box, but over by 06-30
    ("SGER.JK", "2026-07-17", "2026-07-30"),   # pre-thrust coils, "perfect"
    # 2025 out-of-sample pass (2026-09-13), off the random-day 2025-09-02
    # watchlist. The junk names were all "too volatile for my eye test".
    ("MINA.JK", "2025-08-01", "2025-09-30"),
    ("BREN.JK", "2025-08-01", "2025-09-30"),
    ("DSSA.JK", "2025-08-01", "2025-09-30"),   # "perfect"
]

# Eye-marked boxes ACCEPTED as out-of-pattern (2026-09-13) — not evaluated.
# TKIM 08-04→10 and HRTA 08-11→19: MA50 flat/declining; the MA50-rising gate
# stays by decision, so these are known, accepted misses.
# LSIP 08-12→19 and SMIL 08-12→19: no momentum candle exists — quiet drift-up
# bases, a different pattern than momentum-coil.
# SLIS 08-27→31: coil after a +36% parabolic thrust; the label was tentative.
OUT_OF_PATTERN = [
    ("BEEF.JK", "2025-09-10", "2025-09-25"),   # eye's 2nd box: no momentum
                                               # candle (best day +5.3% vs
                                               # 6.8% ADR on 0.8x volume)
    ("TKIM.JK", "2026-08-04", "2026-08-10"),
    ("LSIP.JK", "2026-08-12", "2026-08-19"),
    ("HRTA.JK", "2026-08-11", "2026-08-19"),
    ("SLIS.JK", "2026-08-27", "2026-08-31"),
    ("SMIL.JK", "2026-08-12", "2026-08-19"),
]

# Junk by eye (2026-09-13): the detector must stay QUIET inside these.
NEGATIVE = [
    ("KOKA.JK", "2026-07-22", "2026-08-06"),   # coil after a parabolic thrust
    ("PTRO.JK", "2026-08-24", "2026-08-31"),   # box too wide by the 24th
    # August labelling pass: junk for the whole month.
    *[(s + ".JK", "2026-08-01", "2026-08-31") for s in
      "AALI APLN BEEF BFIN ESSA FUTR HATM MBMA NSSS OILS".split()],
    ("INDY.JK", "2026-08-01", "2026-08-31"),   # junk — wants a longer base
    # corrected-box names: quiet outside the eye's window.
    ("HRTA.JK", "2026-08-01", "2026-08-10"), ("HRTA.JK", "2026-08-20", "2026-08-31"),
    ("SLIS.JK", "2026-08-01", "2026-08-26"),
    ("SMIL.JK", "2026-08-01", "2026-08-11"), ("SMIL.JK", "2026-08-20", "2026-08-31"),
    # July out-of-sample pass: junk for the month.
    ("MORA.JK", "2026-07-01", "2026-07-31"),
    ("NTBK.JK", "2026-07-01", "2026-07-31"),
    ("KETR.JK", "2026-07-01", "2026-07-31"),
    ("MARK.JK", "2026-07-01", "2026-07-31"),   # stale — box ended 06-30
    ("GGRM.JK", "2026-07-01", "2026-07-10"),   # the 07-01 firing was junk
    # 2025 out-of-sample pass: "too volatile for my eye test".
    ("MPPA.JK", "2025-08-01", "2025-09-30"),
    ("SMGA.JK", "2025-08-01", "2025-09-30"),
    ("SURI.JK", "2025-08-01", "2025-09-30"),
    ("ASLC.JK", "2025-08-01", "2025-09-30"),
]


def topup_from_yahoo(sym, rows):
    """Append final daily bars newer than the store's last session, straight
    from Yahoo. The store is never written; offline it silently does nothing."""
    try:
        from datetime import date, timedelta
        import yfinance as yf

        last = rows[-1][0]
        df = yf.download(sym, start=last, progress=False, auto_adjust=False)
        if df is None or df.empty:
            return rows
        cutoff = str(date.today() - timedelta(days=1))  # today's bar may be non-final
        added = 0
        for ts, r in df.iterrows():
            s = str(ts.date())
            v = int(r["Volume"].iloc[0] if hasattr(r["Volume"], "iloc") else r["Volume"])
            if s <= last or s > cutoff or v == 0:  # zero volume = phantom bar
                continue
            get = lambda k: float(r[k].iloc[0] if hasattr(r[k], "iloc") else r[k])
            rows.append((s, get("Open"), get("High"), get("Low"), get("Close"), v))
            added += 1
        if added:
            print(f"  {sym}: +{added} bars from Yahoo (→ {rows[-1][0]})")
    except Exception as e:
        print(f"  {sym}: Yahoo top-up skipped ({e})")
    return rows


def main(symbols, topup=True):
    con = duckdb.connect(str(STORE), read_only=True)
    data = {}
    for sym in symbols:
        rows = con.execute(
            "select session, open, high, low, close, volume from bars "
            "where market = 'IDX' and symbol = ? order by session",
            [sym],
        ).fetchall()
        if not rows:
            print(f"  {sym}: NO BARS — skipped")
            continue
        rows = [(str(s), o, h, lo, c, int(v)) for s, o, h, lo, c, v in rows][-TAIL:]
        if topup:
            rows = topup_from_yahoo(sym, rows)
        coils = coil.detect_all(rows)
        data[sym] = {
            "bars": [list(r) for r in rows],
            "coils": [
                {
                    "end": k.end, "boxStart": k.box_start,
                    "thrustStart": k.thrust_start, "thrustEnd": k.thrust_end,
                    "momentumDays": list(k.momentum_days),
                    "boxHigh": k.box_high, "boxLow": k.box_low,
                    "heightAdr": round(k.height_adr, 3),
                    "volRatio": round(k.vol_ratio, 3),
                    "score": round(k.score, 3),
                }
                for k in coils
            ],
        }
        fire_days = sorted({rows[k.end][0] for k in coils})
        print(f"  {sym}: {len(rows)} bars → fires on {len(fire_days)} sessions"
              + (f" ({fire_days[0]} … {fire_days[-1]})" if fire_days else ""))

    golden = []
    print("\ngolden set:")
    for sym, lo, hi in GOLDEN:
        entry = {"symbol": sym, "from": lo, "to": hi, "caught": False, "fired": []}
        if sym in data:
            rows = data[sym]["bars"]
            hits = sorted(rows[k["end"]][0] for k in data[sym]["coils"]
                          if lo <= rows[k["end"]][0] <= hi)
            entry["fired"] = hits
            entry["caught"] = bool(hits)
        mark = "CAUGHT" if entry["caught"] else "MISSED"
        detail = f" ({entry['fired'][0]} … {entry['fired'][-1]})" if entry["fired"] else ""
        print(f"  {mark}  {sym} {lo} → {hi}{detail}")
        golden.append(entry)

    print("\nnegative set (must stay quiet):")
    for sym, lo, hi in NEGATIVE:
        fired = []
        if sym in data:
            rows = data[sym]["bars"]
            fired = sorted(rows[k["end"]][0] for k in data[sym]["coils"]
                           if lo <= rows[k["end"]][0] <= hi)
        mark = "FIRED " if fired else "QUIET "
        detail = f" ({len(fired)} sessions, {fired[0]} … {fired[-1]})" if fired else ""
        print(f"  {mark} {sym} {lo} → {hi}{detail}")
        golden.append({"symbol": sym, "from": lo, "to": hi,
                       "negative": True, "caught": not fired, "fired": fired})

    OUT.write_text(
        "window.DATA = " + json.dumps(data, separators=(",", ":"))
        + ";\nwindow.GOLDEN = " + json.dumps(golden) + ";\n"
    )
    print(f"\nwrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--no-topup"]
    main(args or sorted({g[0] for g in GOLDEN}), topup="--no-topup" not in sys.argv)
