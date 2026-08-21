"""PROTOTYPE — throwaway. What does "tight" mean in Qullamägi's own trades?

Question this answers: the detector gates on a trailing 3–7 bar window spanning
<= TIGHT_MULT (1.5) x ADR, and the rubric scores tightness as cluster_k >= 5.
Both numbers are borrowed defaults. This measures the geometry his *actual*
entries had, so the threshold can be read off his record instead of assumed.

For each trade in references/trades_bo_gain10smaPct_desc.json it walks to the
evaluation session (last session strictly before entry — funnel.py's convention)
and records the raw trailing k-bar range in ADR for every k in 3..7, plus where
his own stop and entry sat in the same units. Nothing is gated here: the HTML
re-derives pass rates for any TIGHT_MULT / k window from these raw ranges.

Run:  backend/.venv/bin/python backend/replay/prototype-tightness/measure_tightness.py
Writes tightness.json next to this file.
"""
import json
import sys
from bisect import bisect_left
from datetime import datetime
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
# The DBs are untracked, so a worktree has none — fall back to the main checkout.
DB_CANDIDATES = [REPO / "data" / "replay.duckdb",
                 Path.home() / "Projects/trading/screening-dashboard/data/replay.duckdb"]
TRADES = REPO / "references" / "trades_bo_gain10smaPct_desc.json"

K_MIN, K_MAX = 3, 7
ADR_WINDOW = 20
MARKET = "US"


def db_path() -> Path:
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    sys.exit("no replay.duckdb found")


def adr_abs(bars, end):
    """ADR in price units at index `end`: SMA20(high/low - 1) x close."""
    if end + 1 < ADR_WINDOW:
        return None
    window = bars[end + 1 - ADR_WINDOW:end + 1]
    if any(b[3] <= 0 for b in window):          # low <= 0
        return None
    a = sum(b[2] / b[3] - 1 for b in window) / ADR_WINDOW
    return a * bars[end][4]                      # x close


def main():
    con = duckdb.connect(str(db_path()), read_only=True)
    trades = json.loads(TRADES.read_text())["trades"]

    calendar = [r[0] for r in con.execute(
        "SELECT DISTINCT session FROM bars WHERE market = ? ORDER BY session", [MARKET]
    ).fetchall()]
    cal_lo, cal_hi = calendar[0], calendar[-1]

    # One bulk pull: (session, open, high, low, close) per symbol, oldest first.
    symbols = sorted({t["ticker"] for t in trades})
    rows = con.execute(
        "SELECT symbol, session, open, high, low, close FROM bars "
        "WHERE market = ? AND symbol IN ? ORDER BY symbol, session", [MARKET, symbols]
    ).fetchall()
    by_symbol: dict[str, list] = {}
    for sym, *bar in rows:
        by_symbol.setdefault(sym, []).append(bar)   # [session, open, high, low, close]

    out, skipped = [], {}

    def skip(why):
        skipped[why] = skipped.get(why, 0) + 1

    for t in trades:
        entry = datetime.fromisoformat(t["entryDate"].replace("Z", "+00:00")).date()
        if not (cal_lo <= entry <= cal_hi):
            skip("out_of_bar_window")
            continue
        bars = by_symbol.get(t["ticker"])
        if not bars:
            skip("symbol_absent")
            continue
        # Evaluation session: last session strictly before entry (funnel.py).
        eval_i = bisect_left([b[0] for b in bars], entry) - 1
        if eval_i < 0:
            skip("no_prior_session")
            continue
        if eval_i + 1 < max(ADR_WINDOW, K_MAX):
            skip("short_history")
            continue
        a = adr_abs(bars, eval_i)
        if a is None or a <= 0:
            skip("no_adr")
            continue

        ranges, highs, lows = {}, {}, {}
        for k in range(K_MIN, K_MAX + 1):
            lo_i = eval_i - k + 1
            ch = max(b[2] for b in bars[lo_i:eval_i + 1])
            cl = min(b[3] for b in bars[lo_i:eval_i + 1])
            ranges[k] = (ch - cl) / a
            highs[k], lows[k] = ch, cl

        entry_px, stop_px = t["entryPrice"], t["stopPrice"]
        eval_close = bars[eval_i][4]
        # The trade record's prices are raw; the bars are split-adjusted. When a
        # split falls between then and now the two scales diverge and every
        # entry/stop-vs-bar figure is nonsense. range_adr is bars-only so it is
        # unaffected — flag rather than drop, and let the HTML filter.
        scale = entry_px / eval_close if eval_close else 0.0
        out.append({
            "ticker": t["ticker"],
            "entry_date": entry.isoformat(),
            "eval_session": bars[eval_i][0].isoformat(),
            "price_scale": round(scale, 4),
            "price_scale_ok": 0.7 <= scale <= 1.45,
            "adr_pct": round(a / bars[eval_i][4] * 100.0, 3),
            "range_adr": {str(k): round(v, 4) for k, v in ranges.items()},
            # His own risk in ADR units. Both terms are ratios (stop as a fraction
            # of entry, ADR as a fraction of close), so a split cancels and this
            # needs no scale filter. Reproduces the committed §6 Finding 1
            # distribution exactly (median 0.345, p25 0.238, p75 0.490, max 2.753).
            "stop_adr": round(t["stopPercentage"] / (a / eval_close), 4)
                        if t.get("stopPercentage") else None,
            # The naive price-difference form, kept only to show why it is wrong:
            # it compares the record's raw prices against split-adjusted bars.
            "stop_adr_naive": round((entry_px - stop_px) / a, 4) if stop_px else None,
            "stop_pct": t.get("stopPercentage"),
            # Where he entered relative to the 3-bar and 7-bar cluster highs.
            "entry_vs_high3_adr": round((entry_px - highs[3]) / a, 4),
            "entry_vs_high7_adr": round((entry_px - highs[7]) / a, 4),
            # Where his stop sat relative to the cluster low (negative = below it).
            "stop_vs_low3_adr": round((stop_px - lows[3]) / a, 4) if stop_px else None,
            "stop_vs_low7_adr": round((stop_px - lows[7]) / a, 4) if stop_px else None,
            "gain10sma_pct": t.get("gain10smaPct"),
            "rr10sma": t.get("rr10sma"),
        })

    payload = {
        "n_trades_total": len(trades),
        "n_measured": len(out),
        "skipped": skipped,
        "bar_window": [cal_lo.isoformat(), cal_hi.isoformat()],
        "trades": out,
    }
    (HERE / "tightness.json").write_text(json.dumps(payload, indent=1))
    print(f"measured {len(out)} / {len(trades)}  skipped={skipped}")


if __name__ == "__main__":
    main()
