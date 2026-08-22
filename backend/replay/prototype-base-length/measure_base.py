"""PROTOTYPE — throwaway. How long is the base, and when does ADR start tightening?

Companion to prototype-tightness (findings §3b), which asked how *narrow* the
final cluster was. It never asked how the cluster got there. This measures the
base itself on every replayable trade in the reference set:

  * how long price had been contained before entry (two independent readings,
    so no single definition carries the answer);
  * when volatility peaked and how far it contracted from that peak into entry;
  * the shape of the prior advance the base is resting on; and
  * how deep the base is.

Conventions are the study's (replay/funnel.py): the evaluation session is the
last session strictly before entry, and ADR is screener.indicators.adr_abs
(SMA20 of high/low - 1, times close). Nothing is gated at measurement time —
every threshold below is re-derivable from the raw per-trade rows.

Run:  backend/.venv/bin/python backend/replay/prototype-base-length/measure_base.py
Writes base.json next to this file.
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

ADR_WINDOW = 20
MARKET = "US"

# How far back a base is allowed to be looked for. 120 sessions is ~6 months:
# long enough to contain any base he trades, short enough that the pivot search
# does not wander into an unrelated prior cycle. Reported as a censoring bound.
LOOKBACK = 120
# The prior advance is searched in these windows before the base's start; both
# are reported, because the figure is sensitive to the bound.
ADVANCE_LOOKBACKS = (60, 120)
# Containment thresholds, in ADR. 1.5 is the detector's TIGHT_MULT.
CONTAIN_T = (1.5, 2.0, 3.0, 4.0)
# A trade within this many sessions of a prior entry in the same ticker is a
# continuation (study §1's convention) — kept in, tagged, never dropped.
CONTINUATION_SESSIONS = 5
# Volatility curve depth, in sessions before the evaluation session.
CURVE_DAYS = 90


def db_path() -> Path:
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    sys.exit("no replay.duckdb found")


def adr_pct_at(bars, end):
    """SMA20(high/low - 1) at index `end` — ADR as a fraction of price."""
    if end < 0 or end + 1 < ADR_WINDOW:
        return None
    window = bars[end + 1 - ADR_WINDOW:end + 1]
    if any(b[3] <= 0 for b in window):
        return None
    return sum(b[2] / b[3] - 1 for b in window) / ADR_WINDOW


def main():
    con = duckdb.connect(str(db_path()), read_only=True)
    trades = json.loads(TRADES.read_text())["trades"]

    calendar = [r[0] for r in con.execute(
        "SELECT DISTINCT session FROM bars WHERE market = ? ORDER BY session", [MARKET]
    ).fetchall()]
    cal_lo, cal_hi = calendar[0], calendar[-1]

    symbols = sorted({t["ticker"] for t in trades})
    rows = con.execute(
        "SELECT symbol, session, open, high, low, close FROM bars "
        "WHERE market = ? AND symbol IN ? ORDER BY symbol, session", [MARKET, symbols]
    ).fetchall()
    by_symbol: dict[str, list] = {}
    for sym, *bar in rows:
        by_symbol.setdefault(sym, []).append(bar)   # [session, open, high, low, close]

    # Prior-entry distance per ticker, for the continuation tag.
    entries_by_ticker: dict[str, list] = {}
    for t in trades:
        d = datetime.fromisoformat(t["entryDate"].replace("Z", "+00:00")).date()
        entries_by_ticker.setdefault(t["ticker"], []).append(d)
    for v in entries_by_ticker.values():
        v.sort()

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
        sessions = [b[0] for b in bars]
        eval_i = bisect_left(sessions, entry) - 1
        if eval_i < 0:
            skip("no_prior_session")
            continue
        if eval_i + 1 < ADR_WINDOW:
            skip("short_history")
            continue
        adr_p = adr_pct_at(bars, eval_i)
        if not adr_p or adr_p <= 0:
            skip("no_adr")
            continue
        adr_abs = adr_p * bars[eval_i][4]
        if adr_abs <= 0:
            skip("no_adr")
            continue

        # --- how much history is actually available behind this entry --------
        # Every "days back" figure below is censored at this. Reported so a
        # median that sits against the wall is visible as such.
        avail = min(LOOKBACK, eval_i)

        # --- D1: base start = the pivot high --------------------------------
        # The highest high in the lookback. A breakout entry is a move through
        # overhead supply, so the high that terminated the prior advance is the
        # base's left edge; sessions from it to entry is the classic base count.
        lo_i = eval_i - avail
        pivot_i = max(range(lo_i, eval_i + 1), key=lambda i: bars[i][2])
        base_len_pivot = eval_i - pivot_i
        pivot_high = bars[pivot_i][2]
        pivot_censored = base_len_pivot >= avail

        # --- D2: containment length -----------------------------------------
        # Largest n such that the trailing n-bar range fits inside T x ADR.
        # Range is monotone in n, so walk outward until it breaks.
        contain = {}
        for T in CONTAIN_T:
            hi = bars[eval_i][2]
            lo = bars[eval_i][3]
            n = 1
            while n < avail + 1:
                j = eval_i - n
                nhi = max(hi, bars[j][2])
                nlo = min(lo, bars[j][3])
                if (nhi - nlo) > T * adr_abs:
                    break
                hi, lo = nhi, nlo
                n += 1
            contain[str(T)] = {"n": n, "censored": n >= avail + 1}

        # --- D3: volatility peak and contraction ----------------------------
        # ADR is itself a 20-bar mean, so its peak is a smoothed reading; the
        # onset it names is "when the 20-day average range topped out", not a
        # single bar. Searched over the same lookback.
        curve = []
        for d in range(0, min(CURVE_DAYS, eval_i - ADR_WINDOW + 1) + 1):
            v = adr_pct_at(bars, eval_i - d)
            curve.append(None if v is None else round(v, 6))
        usable = [(d, v) for d, v in enumerate(curve) if v]
        if not usable:
            skip("no_adr_curve")
            continue
        peak_d, peak_v = max(usable, key=lambda dv: dv[1])
        adr_now = curve[0]
        peak_censored = peak_d >= len(usable) - 1

        # ADR at the pivot (base start), for "how much of the contraction had
        # already happened by the time the base began".
        adr_at_pivot = adr_pct_at(bars, pivot_i)

        # --- D4: the range-ratio curve --------------------------------------
        # ADR is a *mean of daily* ranges; it says nothing about whether those
        # days overlap. Tightness is travel, not daily range: a 5-bar window can
        # collapse to 1 ADR wide while ADR itself is unchanged. So carry the
        # ratio the detector actually gates on — trailing 5-bar high-low range
        # over ADR, both re-read at each historical session — as its own curve.
        rr5 = []
        for d in range(0, min(CURVE_DAYS, eval_i - ADR_WINDOW - 3) + 1):
            i = eval_i - d
            a = adr_pct_at(bars, i)
            if not a or a <= 0 or i - 4 < 0:
                rr5.append(None)
                continue
            w = bars[i - 4:i + 1]
            rr5.append(round((max(b[2] for b in w) - min(b[3] for b in w))
                             / (a * bars[i][4]), 4))
        # How long the 5-bar range has been continuously inside 2 ADR, and how
        # long since it was last wider than 2.5 ADR (the last expansion leg).
        quiet_n = 0
        for v in rr5:
            if v is None or v > 2.0:
                break
            quiet_n += 1
        last_wide = next((d for d, v in enumerate(rr5) if v is not None and v > 2.5), None)

        # --- the prior advance the base rests on ----------------------------
        # "Lowest low in the W sessions before the pivot" is sensitive to W, so
        # both windows are measured and reported side by side rather than one
        # being picked. Neither is a swing-detection; it is a bounded lookback.
        advance = {}
        for W in ADVANCE_LOOKBACKS:
            adv_lo_i = max(0, pivot_i - W)
            if adv_lo_i < pivot_i:
                trough_i = min(range(adv_lo_i, pivot_i + 1), key=lambda i: bars[i][3])
                trough_low = bars[trough_i][3]
                advance[str(W)] = {
                    "pct": round((pivot_high / trough_low - 1) * 100, 2) if trough_low > 0 else None,
                    "len": pivot_i - trough_i,
                    "censored": trough_i <= adv_lo_i,
                }
            else:
                advance[str(W)] = {"pct": None, "len": None, "censored": True}

        # --- base depth ------------------------------------------------------
        # Deepest retracement from the pivot high over the base itself.
        base_slice = bars[pivot_i:eval_i + 1]
        base_low = min(b[3] for b in base_slice)
        depth_pct = (1 - base_low / pivot_high) * 100 if pivot_high > 0 else None
        depth_adr = (pivot_high - base_low) / adr_abs

        # --- continuation tag -------------------------------------------------
        priors = [d for d in entries_by_ticker[t["ticker"]] if d < entry]
        if priors:
            prev = priors[-1]
            sess_since = bisect_left(sessions, entry) - bisect_left(sessions, prev)
        else:
            sess_since = None
        continuation = sess_since is not None and sess_since <= CONTINUATION_SESSIONS

        out.append({
            "ticker": t["ticker"],
            "entry_date": entry.isoformat(),
            "eval_session": bars[eval_i][0].isoformat(),
            "avail_sessions": avail,
            "continuation": continuation,
            "sessions_since_prior_entry": sess_since,
            "adr_pct": round(adr_p * 100, 3),
            # D1
            "base_len_pivot": base_len_pivot,
            "base_len_pivot_censored": pivot_censored,
            "pivot_date": bars[pivot_i][0].isoformat(),
            # D2
            "contain": contain,
            # D3
            "adr_peak_days_before": peak_d,
            "adr_peak_censored": peak_censored,
            "adr_peak_pct": round(peak_v * 100, 3),
            "adr_contraction": round(adr_now / peak_v, 4),
            "adr_at_pivot_pct": round(adr_at_pivot * 100, 3) if adr_at_pivot else None,
            "adr_curve_pct": [None if v is None else round(v * 100, 3) for v in curve],
            # D4
            "rr5_curve": rr5,
            "rr5_quiet_sessions": quiet_n,
            "rr5_last_wide_days": last_wide,
            # advance
            "advance": advance,
            # depth
            "base_depth_pct": round(depth_pct, 2) if depth_pct is not None else None,
            "base_depth_adr": round(depth_adr, 3),
            # outcome, for cross-tabs
            "gain10sma_pct": t.get("gain10smaPct"),
            "rr10sma": t.get("rr10sma"),
            # MFE is the study's outcome variable of record (§A3): the exits are
            # counterfactual, MFE is a property of the entry itself.
            "mfe10sma_pct": t.get("mfe10smaPct"),
        })

    payload = {
        "n_trades_total": len(trades),
        "n_measured": len(out),
        "skipped": skipped,
        "bar_window": [cal_lo.isoformat(), cal_hi.isoformat()],
        "params": {"lookback": LOOKBACK, "advance_lookbacks": list(ADVANCE_LOOKBACKS),
                   "contain_t": list(CONTAIN_T), "adr_window": ADR_WINDOW,
                   "curve_days": CURVE_DAYS},
        "trades": out,
    }
    (HERE / "base.json").write_text(json.dumps(payload, indent=1))
    print(f"measured {len(out)} / {len(trades)}  skipped={skipped}")


if __name__ == "__main__":
    main()
