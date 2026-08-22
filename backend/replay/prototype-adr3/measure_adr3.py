"""PROTOTYPE — throwaway. Does the last 3 days differ from the 3 days before it?

Question: at the evaluation session, compare the *recent* 3-bar window against the
*prior* 3-bar window (the three bars immediately behind it) — average daily range,
travel (high-low span), and volume. Is the final 3 days measurably quieter than the
3 days before, and is that a property of his entries or just of his kind of stock?

Why this is worth a prototype: findings §3b measured the 3-bar range *level*
(median 1.31 ADR) and prototype-base-length measured the 90-session curve (flat ADR,
travel collapsing over the final ~7-10 sessions). Neither asked the local question —
recent 3 vs prior 3 — which is the one a screen could actually gate on cheaply.

**The control.** Every earlier study lacked a control group (§7, §9: no measurable
false-positive rate). One is available *here* without labelled non-setups: the same
ticker on other sessions. For each trade we sample BACKGROUND_N random sessions of the
same ticker inside a +/-BACKGROUND_SPAN window, excluding anything near a real entry,
and compute identical features. That does not give a false-positive rate for the
screener — the background is not "setups he passed over", it is "this stock on an
ordinary day" — but it does say whether a ratio is a property of the *entry* or just
of the *name*. Seeded, so the sample is fixed.

Run:  backend/.venv/bin/python backend/replay/prototype-adr3/measure_adr3.py
Writes adr3.json next to this file.
"""
import json
import random
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
W = 3                       # the window being compared, in bars
BACKGROUND_N = 10           # random same-ticker sessions per trade
BACKGROUND_SPAN = 120       # sampled within +/- this many sessions of the entry
BACKGROUND_KEEPOUT = 5      # never sample within this many sessions of any real entry
SEED = 20260822
CONTINUATION_SESSIONS = 5


def db_path() -> Path:
    for p in DB_CANDIDATES:
        if p.exists():
            return p
    sys.exit("no replay.duckdb found")


def features(bars, i):
    """The recent-vs-prior feature set at index `i`, or None if unmeasurable.

    bars rows are [session, open, high, low, close, volume].
    """
    if i < ADR_WINDOW + 2 * W:
        return None
    recent = bars[i - W + 1:i + 1]
    prior = bars[i - 2 * W + 1:i - W + 1]
    if any(b[3] <= 0 for b in bars[i - ADR_WINDOW + 1:i + 1]):
        return None

    # ADR20 in price units, the denominator every span is quoted in.
    adr20 = sum(b[2] / b[3] - 1 for b in bars[i - ADR_WINDOW + 1:i + 1]) / ADR_WINDOW
    if adr20 <= 0:
        return None
    adr20_abs = adr20 * bars[i][4]
    if adr20_abs <= 0:
        return None

    # (a) average daily range over each window — "is each bar smaller?"
    a_recent = sum(b[2] / b[3] - 1 for b in recent) / W
    a_prior = sum(b[2] / b[3] - 1 for b in prior) / W
    if a_prior <= 0:
        return None

    # (b) travel — the window's own high-low span, in ADR20 units. This is the
    # quantity §3b measured, and it can collapse while (a) is unchanged.
    sp_recent = (max(b[2] for b in recent) - min(b[3] for b in recent)) / adr20_abs
    sp_prior = (max(b[2] for b in prior) - min(b[3] for b in prior)) / adr20_abs

    # (c) volume — the classic dry-up companion to a tightening.
    v_recent = sum(b[5] for b in recent) / W
    v_prior = sum(b[5] for b in prior) / W
    v20 = sum(b[5] for b in bars[i - ADR_WINDOW + 1:i + 1]) / ADR_WINDOW

    return {
        "adr20_pct": round(adr20 * 100, 3),
        "adr3_recent_pct": round(a_recent * 100, 3),
        "adr3_prior_pct": round(a_prior * 100, 3),
        "adr3_ratio": round(a_recent / a_prior, 4),
        "adr3_vs_adr20": round(a_recent / adr20, 4),
        "span3_recent_adr": round(sp_recent, 4),
        "span3_prior_adr": round(sp_prior, 4),
        "span3_ratio": round(sp_recent / sp_prior, 4) if sp_prior > 0 else None,
        "vol3_ratio": round(v_recent / v_prior, 4) if v_prior > 0 else None,
        "vol3_vs_vol20": round(v_recent / v20, 4) if v20 > 0 else None,
    }


def main():
    con = duckdb.connect(str(db_path()), read_only=True)
    trades = json.loads(TRADES.read_text())["trades"]

    calendar = [r[0] for r in con.execute(
        "SELECT DISTINCT session FROM bars WHERE market = ? ORDER BY session", [MARKET]
    ).fetchall()]
    cal_lo, cal_hi = calendar[0], calendar[-1]

    symbols = sorted({t["ticker"] for t in trades})
    rows = con.execute(
        "SELECT symbol, session, open, high, low, close, volume FROM bars "
        "WHERE market = ? AND symbol IN ? ORDER BY symbol, session", [MARKET, symbols]
    ).fetchall()
    by_symbol: dict[str, list] = {}
    for sym, *bar in rows:
        by_symbol.setdefault(sym, []).append(bar)

    entries_by_ticker: dict[str, list] = {}
    for t in trades:
        d = datetime.fromisoformat(t["entryDate"].replace("Z", "+00:00")).date()
        entries_by_ticker.setdefault(t["ticker"], []).append(d)
    for v in entries_by_ticker.values():
        v.sort()

    rng = random.Random(SEED)
    out, background, skipped = [], [], {}

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
        f = features(bars, eval_i)
        if f is None:
            skip("short_history")
            continue

        priors = [d for d in entries_by_ticker[t["ticker"]] if d < entry]
        sess_since = (bisect_left(sessions, entry) - bisect_left(sessions, priors[-1])
                      if priors else None)

        out.append({
            "ticker": t["ticker"],
            "entry_date": entry.isoformat(),
            "eval_session": bars[eval_i][0].isoformat(),
            "continuation": sess_since is not None and sess_since <= CONTINUATION_SESSIONS,
            **f,
            "gain10sma_pct": t.get("gain10smaPct"),
            "rr10sma": t.get("rr10sma"),
            "mfe10sma_pct": t.get("mfe10smaPct"),
        })

        # --- the same ticker on ordinary days ------------------------------
        entry_idx = {bisect_left(sessions, d) - 1
                     for d in entries_by_ticker[t["ticker"]]}
        lo = max(ADR_WINDOW + 2 * W, eval_i - BACKGROUND_SPAN)
        hi = min(len(bars) - 1, eval_i + BACKGROUND_SPAN)
        pool = [j for j in range(lo, hi + 1)
                if all(abs(j - e) > BACKGROUND_KEEPOUT for e in entry_idx)]
        for j in rng.sample(pool, min(BACKGROUND_N, len(pool))):
            bf = features(bars, j)
            if bf:
                background.append({"ticker": t["ticker"],
                                   "session": bars[j][0].isoformat(), **bf})

    payload = {
        "n_trades_total": len(trades),
        "n_measured": len(out),
        "n_background": len(background),
        "skipped": skipped,
        "bar_window": [cal_lo.isoformat(), cal_hi.isoformat()],
        "params": {"w": W, "adr_window": ADR_WINDOW, "background_n": BACKGROUND_N,
                   "background_span": BACKGROUND_SPAN,
                   "background_keepout": BACKGROUND_KEEPOUT, "seed": SEED},
        "trades": out,
        "background": background,
    }
    (HERE / "adr3.json").write_text(json.dumps(payload, indent=1))
    print(f"measured {len(out)} / {len(trades)}  background={len(background)}  "
          f"skipped={skipped}")


if __name__ == "__main__":
    main()
