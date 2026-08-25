#!/usr/bin/env python
"""PROTOTYPE — throwaway. How big is the prior move before his entries?

`CONTEXT.md` calls the first criterion a **big prior move**, and the app spends
it as a *binary* gate: top decile of `1m/3m/6m/12m`, in or out. Because every
detection clears that gate by construction, the replay study can say nothing
about the dimension at all — `Prior move` is 100% in every group it can build
(`qullamaggie-replay-findings.md` §5a, §9). The only continuous handle found so
far is a proxy: distance above the SMA50 in ADR units
(`qullamaggie-entry-ma-distance.md` §5).

This asks the direct question instead: at the moment he clicks, what has the
stock actually *done* over `1w / 1m / 3m / 6m / 12m`? Same five lookbacks the
rank table uses, same calendar anchoring, same `adj_close` basis — so a number
here is comparable to a rank row, not a new definition of strength.

Measured **as of the last session strictly before the entry date**: he enters
intraday and early (median 09:42), so the return on screen at the click is the
one through the prior close, not the entry day's.

Two things make the raw distribution readable:

* **In ADR units** (`move% / ADR%`) as well as raw percent. +180% over 3m is a
  different animal on a 12%-ADR biotech than on a 3%-ADR industrial, and the
  whole codebase denominates in ADR for that reason.
* **Against a same-name background** — the same tickers on random ordinary days
  in the same window (the device §3d uses). It cannot say what he *rejected*
  (no control group of passed-over setups exists), only whether the prior move
  belongs to the *entry* or merely to the *kind of stock he trades*.

* **Joined to base age** (#172). §3f read the flat `1w` return at his entries as
  "he buys the quiet end of the base", but that joins two facts measured on
  different denominators — §3c's base age on 649 rows, the `1w` return on 582 —
  and a +0.3% median is equally consistent with mixed weeks that cancel. Base
  age is measured here on the same evaluation session, so the `1w` distribution
  and its index beat-rate can be read *inside* each age band.

Usage:
    backend/.venv/bin/python .scratch/screening-dashboard/prototypes/\
prior-move-at-entry/prior_move_at_entry.py
"""

from __future__ import annotations

import sys
from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "scripts"))

from entry_ma_distance import (  # noqa: E402  (path juggling above)
    SPLIT_CANDIDATES, RANGE_TOL, load_trades,
)

LOOKBACKS = ("1w", "1m", "3m", "6m", "12m")
_MONTHS = {"1m": 1, "3m": 3, "6m": 6, "12m": 12}

# The trade record's window. The background samples from it too, so entry days
# and ordinary days are drawn from the same tape.
WINDOW = (pd.Timestamp("2019-10-01"), pd.Timestamp("2022-11-30"))

# Keep the background's "ordinary day" clear of his own entries — a day two
# sessions after an entry is still inside the move he bought.
QUARANTINE_BARS = 21

SEED = 20260825

# §3c's D1 window, transcribed: how far back a base is allowed to be looked for.
# 120 sessions is ~6 months.
BASE_LOOKBACK = 120

# The buckets #172 asks for. Edges are inclusive on the right.
AGE_BUCKETS = ((5, "<=5"), (30, "6-30"), (60, "31-60"), (10**9, ">60"))


def anchor(as_of: date, lookback: str) -> date:
    """`screener.indicators.anchor_date`, transcribed. 1w is 7 calendar days;
    month lookbacks subtract whole months and clamp a short target month."""
    if lookback == "1w":
        return as_of - timedelta(days=7)
    total = as_of.year * 12 + (as_of.month - 1) - _MONTHS[lookback]
    year, month = divmod(total, 12)
    day = min(as_of.day, monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


def base_age(frame: pd.DataFrame, as_of: pd.Timestamp) -> tuple[int | None, bool]:
    """Sessions from the highest high of the trailing 120 to `as_of`.

    §3c's D1, transcribed from `backend/replay/prototype-base-length/
    measure_base.py`: a breakout is a move through overhead supply, so the high
    that terminated the prior advance is the base's left edge. Ties go to the
    *earliest* high — `max(range(...), key=...)` returns the first maximum, and
    a structure tagged twice at the same price started at the first tag.

    Returns `(age, censored)`. Censored means the pivot sits on the window's own
    left edge, so the age is a floor: either the 120-session wall or, for a young
    series, the first bar available.

    Highs are **raw**, as in §3c — not the `Adj` series the returns use. A split
    inside the window would put the pivot at a pre-split price and censor the
    row; the censored share is reported for exactly that reason.
    """
    hist = frame.loc[frame.index <= as_of]
    if hist.empty:
        return None, False
    eval_i = len(hist) - 1
    avail = min(BASE_LOOKBACK, eval_i)
    window = hist["High"].to_numpy(dtype=float)[eval_i - avail: eval_i + 1]
    age = avail - int(np.argmax(window))
    return age, age >= avail


def age_bucket(age: float | None) -> str | None:
    """#172's four bands, or `None` for a row whose base age is missing."""
    if age is None or (isinstance(age, float) and np.isnan(age)):
        return None
    for edge, label in AGE_BUCKETS:
        if age <= edge:
            return label
    return None


def load_frames() -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Adjusted-close series per ticker: the screener store first, the delisted
    remainder from the Yahoo pickle the entry-to-MA study already cached."""
    import duckdb
    import pickle

    con = duckdb.connect(str(ROOT / "data" / "screener.duckdb"), read_only=True)
    df = con.execute(
        "SELECT symbol, session, high, low, adj_close FROM bars "
        "WHERE market = 'US' AND session BETWEEN DATE '2018-01-01' "
        "AND DATE '2023-01-15' ORDER BY symbol, session"
    ).df()
    con.close()

    frames, source = {}, {}
    for sym, g in df.groupby("symbol"):
        g = g.set_index(pd.to_datetime(g["session"]))
        frames[sym] = g[["high", "low", "adj_close"]].rename(
            columns={"high": "High", "low": "Low", "adj_close": "Adj"})
        source[sym] = "db"

    cache = ROOT / "data" / "entry_ma_yahoo.pkl"
    if cache.exists():
        for sym, g in pickle.loads(cache.read_bytes()).items():
            if sym in frames or not len(g):
                continue
            frames[sym] = g[["High", "Low", "Adj Close"]].rename(
                columns={"Adj Close": "Adj"})
            source[sym] = "yf"
    return frames, source


def belongs(entry_price: float, low: float, high: float) -> bool:
    """Does the logged fill fit this bar's day at *some* split ratio?

    The entry-to-MA study needed the exact ratio (it divides by an SMA) and drops
    a trade when two candidates both fit. Returns are ratio-free on an adjusted
    series, so here the check is only a guard against a **recycled symbol** —
    a ticker later reissued to a different company, whose bars would be a
    different stock's. Ambiguity between 3:1 and 4:1 still proves the series is
    the right company, so those trades are kept. That is why this matches more
    trades than the 579 of the MA study.
    """
    lo, hi = low * (1 - RANGE_TOL), high * (1 + RANGE_TOL)
    return lo <= entry_price <= hi or any(
        lo <= entry_price / s <= hi for s in SPLIT_CANDIDATES)


def prior_moves(frame: pd.DataFrame, as_of: pd.Timestamp) -> dict[str, float]:
    """The five calendar returns through `as_of`, plus the ADR at that point.

    A lookback whose anchor predates the series is **absent**, not zero — same
    per-lookback eligibility rule the rank table has (`ranks.py`).
    """
    hist = frame.loc[frame.index <= as_of]
    if len(hist) < 25:
        return {}
    end = float(hist["Adj"].iloc[-1])
    out: dict[str, float] = {}
    for lb in LOOKBACKS:
        a = pd.Timestamp(anchor(as_of.date(), lb))
        window = hist.loc[hist.index <= a]
        # Demand a real bar before the anchor, not just the first one: a name
        # whose series *starts* two days after the anchor would otherwise report
        # a 12m return that is really a 3-day return.
        if len(window) < 2 or window.index[0] > a - pd.Timedelta(days=5):
            continue
        start = float(window["Adj"].iloc[-1])
        if start > 0:
            out[lb] = (end / start - 1) * 100
    adr = float((hist["High"].astype(float) / hist["Low"].astype(float) - 1)
                .iloc[-20:].mean()) * 100
    out["adr"] = adr
    return out


def build(trades: list[dict], frames: dict[str, pd.DataFrame],
          source: dict[str, str]) -> tuple[pd.DataFrame, dict[str, int]]:
    rows, skips = [], {"no data": 0, "short history": 0, "wrong series": 0}
    for t in trades:
        frame = frames.get(t["ticker"])
        if frame is None:
            skips["no data"] += 1
            continue
        entry_date = pd.Timestamp(t["entryDate"][:10])
        prior = frame.loc[frame.index < entry_date]
        if len(prior) < 25:
            skips["short history"] += 1
            continue
        day = frame.loc[frame.index == entry_date]
        if len(day) and not belongs(t["entryPrice"], float(day["Low"].iloc[0]),
                                    float(day["High"].iloc[0])):
            skips["wrong series"] += 1
            continue

        m = prior_moves(frame, prior.index[-1])
        if not m:
            skips["short history"] += 1
            continue
        age, censored = base_age(frame, prior.index[-1])
        rows.append(dict(ticker=t["ticker"], date=entry_date.date(),
                         as_of=prior.index[-1], src=source.get(t["ticker"], "?"),
                         rr10sma=t.get("rr10sma"),
                         gain10sma_pct=t.get("gain10smaPct"),
                         base_age=age, base_censored=censored,
                         base_bucket=age_bucket(age),
                         **m))
    return pd.DataFrame(rows), skips


def background(entries: pd.DataFrame, frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """The same tickers on random ordinary days in the same window.

    Not a control group of rejected setups — none exists. It answers the weaker
    question: is the prior move a property of the *entry*, or of the kind of
    stock he trades?
    """
    rng = np.random.default_rng(SEED)
    taken = {tk: pd.to_datetime(g["date"]) for tk, g in entries.groupby("ticker")}
    rows = []
    for ticker, dates in taken.items():
        frame = frames[ticker]
        idx = frame.index[(frame.index >= WINDOW[0]) & (frame.index <= WINDOW[1])]
        near = set()
        for d in dates:
            pos = frame.index.searchsorted(d)
            near.update(frame.index[max(0, pos - QUARANTINE_BARS):
                                    pos + QUARANTINE_BARS])
        pool = [d for d in idx if d not in near]
        if not pool:
            continue
        # One draw per entry, so a name he traded ten times weighs ten times in
        # the background too — otherwise the two panels have different ticker mixes.
        for d in rng.choice(len(pool), size=min(len(dates), len(pool)), replace=False):
            m = prior_moves(frame, pool[int(d)])
            if m:
                age, censored = base_age(frame, pool[int(d)])
                rows.append(dict(ticker=ticker, date=pool[int(d)].date(),
                                 as_of=pool[int(d)], base_age=age,
                                 base_censored=censored,
                                 base_bucket=age_bucket(age), **m))
    return pd.DataFrame(rows)


def attach_benchmark(df: pd.DataFrame, bench: pd.DataFrame, tag: str) -> pd.DataFrame:
    """The benchmark's own five lookback returns on each row's `as_of`, and the
    stock's move *relative* to it.

    Relative is compounded — `(1 + stock) / (1 + bench) − 1` — not differenced.
    Over these horizons the difference is not cosmetic: +900% against a +30%
    tape is +670pp but ×7.7, and the second is the one that means "outran the
    market". Both are printed; the compounded one is what the text quotes.

    The benchmark is read on the *name's* own prior session, so a name that did
    not trade the day before entry is compared against the same date it is
    measured through, not a later one.
    """
    cache: dict[pd.Timestamp, dict[str, float]] = {}
    out = {f"{tag}_{lb}": [] for lb in LOOKBACKS}
    out |= {f"rel_{lb}": [] for lb in LOOKBACKS}
    for as_of in df["as_of"]:
        if as_of not in cache:
            cache[as_of] = prior_moves(bench, as_of)
        b = cache[as_of]
        for lb in LOOKBACKS:
            out[f"{tag}_{lb}"].append(b.get(lb, np.nan))
    df = df.assign(**{k: v for k, v in out.items() if k.startswith(tag)})
    for lb in LOOKBACKS:
        df[f"rel_{lb}"] = ((1 + df[lb] / 100) / (1 + df[f"{tag}_{lb}"] / 100) - 1) * 100
    return df


def describe(label: str, s: pd.Series) -> None:
    s = s.dropna()
    q = s.quantile([.05, .25, .5, .75, .95])
    print(f"  {label:14s} n {len(s):4d} | mean {s.mean():8.1f}  median {s.median():7.1f} "
          f"| p5 {q[.05]:7.1f}  p25 {q[.25]:7.1f}  p75 {q[.75]:7.1f}  p95 {q[.95]:8.1f} "
          f"| neg {(s < 0).mean() * 100:4.1f}%")


def report(entries: pd.DataFrame, bg: pd.DataFrame, n_trades: int,
           skips: dict[str, int]) -> None:
    print(f"matched {len(entries)} of {n_trades} logged breakout longs "
          f"({len(entries) / n_trades * 100:.0f}%)  skips: {skips}")
    print(f"background: {len(bg)} ordinary days over the same "
          f"{entries.ticker.nunique()} tickers\n")

    print("== prior move at entry, raw % (through the prior close) ==")
    for lb in LOOKBACKS:
        describe(lb, entries[lb])
    print("\n== the same, in ADR units (move% / ADR%) ==")
    for lb in LOOKBACKS:
        describe(lb, entries[lb] / entries["adr"])
    print("\n== background: same names, random ordinary days, raw % ==")
    for lb in LOOKBACKS:
        describe(lb, bg[lb])

    # Medians, differenced — not divided. An ordinary day's median 1m return is
    # ~0, and a ratio against ~0 is an artefact, not a multiple.
    print("\n== entry vs background (medians; gap, not ratio) ==")
    print(f"  {'':6s} {'entry %':>9s} {'ordinary':>9s} {'gap pp':>8s} | "
          f"{'entry ADRu':>10s} {'ordinary':>9s} {'gap':>7s}")
    for lb in LOOKBACKS:
        e, o = entries[lb].median(), bg[lb].median()
        ea = (entries[lb] / entries["adr"]).median()
        oa = (bg[lb] / bg["adr"]).median()
        print(f"  {lb:6s} {e:9.1f} {o:9.1f} {e - o:8.1f} | "
              f"{ea:10.2f} {oa:9.2f} {ea - oa:7.2f}")

    print("\n== ADR at the moment of entry vs on an ordinary day ==")
    describe("entry ADR%", entries["adr"])
    describe("ordinary ADR%", bg["adr"])

    print("\n== how many lookbacks are positive at once (the 'big move' shape) ==")
    pos = entries[list(LOOKBACKS)].gt(0).sum(axis=1)
    n_lb = entries[list(LOOKBACKS)].notna().sum(axis=1)
    print(f"  (all five measurable on {(n_lb == 5).mean() * 100:.0f}% of entries; "
          f"a missing lookback counts as not-positive here)")
    for k in range(6):
        print(f"  {k}/5 positive: {(pos == k).mean() * 100:5.1f}%")

    graded = entries.dropna(subset=["rr10sma"])
    if graded.empty:
        return
    print("\n== outcome by size of the prior move (mean R, his own 10sma exit) ==")
    print("   his hit rate is ~23%, so the median trade is a stop-out in every")
    print("   bucket — mean R and the share of >=3R are what separate them.")
    for lb in ("1m", "3m", "6m", "12m"):
        sub = graded.dropna(subset=[lb])
        if len(sub) < 40:
            continue
        qs = pd.qcut(sub[lb], 4, duplicates="drop")
        agg = sub.groupby(qs, observed=True).agg(
            n=("rr10sma", "size"), mean_R=("rr10sma", "mean"),
            win_pct=("rr10sma", lambda s: (s > 0).mean() * 100),
            big_pct=("rr10sma", lambda s: (s >= 3).mean() * 100))
        # Spearman by hand — Pearson on the ranks. scipy is not in the venv,
        # and a prototype is not a reason to add a dependency.
        rho = sub[lb].rank().corr(sub["rr10sma"].rank())
        print(f"\n  [{lb}]  n={len(sub)}  Spearman(prior move, R) = {rho:+.3f}")
        print(agg.round(2).to_string().replace("\n", "\n  "))


def report_benchmark(entries: pd.DataFrame, bg: pd.DataFrame,
                     ixic: pd.DataFrame, tag: str) -> None:
    """The same prior moves, netted against the tape.

    The complaint every result in this window attracts is that 2020–21 paid for
    long-horizon momentum everywhere, so a +119% median 12m move might be the
    market's and not the stock's. This is that objection, measured.
    """
    print(f"\n\n== the tape itself: {tag.upper()} over the same windows, "
          f"on the same {len(entries)} entry dates ==")
    for lb in LOOKBACKS:
        describe(lb, entries[f"{tag}_{lb}"])

    print(f"\n== prior move RELATIVE to {tag.upper()}, compounded "
          f"((1+stock)/(1+{tag})−1), % ==")
    for lb in LOOKBACKS:
        describe(lb, entries[f"rel_{lb}"])

    print(f"\n== share of entries that beat {tag.upper()} over the window ==")
    print(f"  {'':6s} {'his entries':>12s} {'ordinary days':>14s} "
          f"{'^IXIC check':>12s}")
    for lb in LOOKBACKS:
        e = (entries[f"rel_{lb}"] > 0).mean() * 100
        o = (bg[f"rel_{lb}"] > 0).mean() * 100
        i = (ixic[f"rel_{lb}"] > 0).mean() * 100
        print(f"  {lb:6s} {e:11.1f}% {o:13.1f}% {i:11.1f}%")

    print(f"\n== median move: stock, {tag.upper()}, and the two netted ==")
    print(f"  {'':6s} {'stock %':>9s} {'{}%'.format(tag.upper()):>9s} "
          f"{'rel %':>9s} {'gap pp':>8s} | {'ordinary rel %':>15s}")
    for lb in LOOKBACKS:
        s, b = entries[lb].median(), entries[f"{tag}_{lb}"].median()
        print(f"  {lb:6s} {s:9.1f} {b:9.1f} {entries[f'rel_{lb}'].median():9.1f} "
              f"{s - b:8.1f} | {bg[f'rel_{lb}'].median():15.1f}")

    graded = entries.dropna(subset=["rr10sma"])
    if graded.empty:
        return
    print(f"\n== outcome by RELATIVE prior move (mean R, his 10sma exit) ==")
    for lb in ("1m", "6m", "12m"):
        sub = graded.dropna(subset=[f"rel_{lb}"])
        if len(sub) < 40:
            continue
        qs = pd.qcut(sub[f"rel_{lb}"], 4, duplicates="drop")
        agg = sub.groupby(qs, observed=True).agg(
            n=("rr10sma", "size"), mean_R=("rr10sma", "mean"),
            win_pct=("rr10sma", lambda s: (s > 0).mean() * 100),
            big_pct=("rr10sma", lambda s: (s >= 3).mean() * 100))
        rho = sub[f"rel_{lb}"].rank().corr(sub["rr10sma"].rank())
        print(f"\n  [rel {lb}]  n={len(sub)}  Spearman = {rho:+.3f}")
        print(agg.round(2).to_string().replace("\n", "\n  "))


BOOT = 5000


def boot_ci(s: pd.Series, stat, seed: int = SEED) -> tuple[float, float]:
    """Seeded percentile bootstrap, 95%. The bands run 69–246 rows, so a band's
    median has to arrive with an interval or the eye reads noise as structure."""
    v = s.dropna().to_numpy(dtype=float)
    if len(v) < 10:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    draws = stat(v[rng.integers(0, len(v), size=(BOOT, len(v)))], axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def report_base_age(entries: pd.DataFrame, bg: pd.DataFrame, tag: str) -> None:
    """#172: is the flat week *the base*, or an average over mixed weeks?

    §3f found a +0.3% median `1w` return and read it as "he buys the quiet end
    of the base". That reading needs the two facts joined per trade, which
    nothing had done: a +0.3% median is equally consistent with a mix of weeks
    up 10% and down 10%. So each row's base age is measured on the same
    evaluation session the returns use, and the `1w` distribution and index
    beat-rate are re-read inside each age band.

    The background carries base age too. The pooled ordinary-day beat-rate
    (49.1%) is the wrong comparator inside a band — an ordinary day in a young
    structure is a different animal from one in a six-month base — so each band
    is scored against ordinary days of *the same* base age.
    """
    labels = [lab for _, lab in AGE_BUCKETS]
    e = entries.dropna(subset=["base_age"])
    b = bg.dropna(subset=["base_age"])

    print("\n\n== base age at entry (§3c's D1, rebuilt here) ==")
    print("   sessions from the highest high of the trailing 120 to the "
          "evaluation session.")
    print("   §3c, on its own independently built 649 rows: median 24, p25 11, "
          "p75 63,")
    print("   12.0% <=5, 42.4% 6-30, 19.3% 31-60, 26.3% >60, 2.8% censored.")
    q = e["base_age"].quantile([.25, .5, .75])
    print(f"  here   n {len(e):4d} | median {e['base_age'].median():5.1f} "
          f"| p25 {q[.25]:5.1f}  p75 {q[.75]:5.1f} "
          f"| censored {e['base_censored'].mean() * 100:4.1f}%")
    share = e["base_bucket"].value_counts(normalize=True) * 100
    print("  bands: " + "  ".join(
        f"{lab} {share.get(lab, 0.0):4.1f}%" for lab in labels))
    bgq = b["base_age"].quantile([.25, .5, .75])
    print(f"  ordinary days for contrast: median {b['base_age'].median():5.1f} "
          f"| p25 {bgq[.25]:5.1f}  p75 {bgq[.75]:5.1f}")

    print("\n== the 1w return at entry, split by base age ==")
    print(f"  {'band':7s} {'n':>4s} {'median %':>9s} {'95% CI':>16s} "
          f"{'mean %':>8s} {'p25':>7s} {'p75':>7s} {'down on wk':>11s} "
          f"{'median xADR':>12s} | {'ordinary median %':>18s}")
    for lab in labels:
        s = e.loc[e["base_bucket"] == lab, "1w"].dropna()
        sub = e[e["base_bucket"] == lab]
        o = b.loc[b["base_bucket"] == lab, "1w"].dropna()
        if s.empty:
            continue
        adru = (sub["1w"] / sub["adr"]).median()
        lo, hi = boot_ci(s, np.median)
        print(f"  {lab:7s} {len(s):4d} {s.median():9.2f} "
              f"[{lo:6.2f},{hi:6.2f}] {s.mean():8.2f} "
              f"{s.quantile(.25):7.1f} {s.quantile(.75):7.1f} "
              f"{(s < 0).mean() * 100:10.1f}% {adru:12.3f} "
              f"| {o.median() if len(o) else float('nan'):17.2f}")

    print(f"\n== the 1w beat-rate against {tag.upper()}, split by base age ==")
    print("   each band against ordinary days of the *same* base age, not "
          "against the pooled 49.1%.")
    print(f"  {'band':7s} {'n':>4s} {'rel 1w median %':>16s} "
          f"{'beats':>7s} {'95% CI':>16s} {'ordinary n':>11s} "
          f"{'ordinary beats':>15s} {'gap pp':>8s} {'gap 2se':>8s}")
    for lab in labels:
        s = e.loc[e["base_bucket"] == lab, "rel_1w"].dropna()
        o = b.loc[b["base_bucket"] == lab, "rel_1w"].dropna()
        if s.empty:
            continue
        beat = (s > 0).mean() * 100
        obeat = (o > 0).mean() * 100 if len(o) else float("nan")
        lo, hi = boot_ci(s > 0, np.mean)
        # Two standard errors on the difference of two shares, at p = 0.5 —
        # the widest case, so a gap inside this is noise on any reading.
        se2 = 2 * 100 * np.sqrt(.25 / len(s) + .25 / max(len(o), 1))
        print(f"  {lab:7s} {len(s):4d} {s.median():16.2f} {beat:6.1f}% "
              f"[{lo * 100:6.1f},{hi * 100:6.1f}] {len(o):11d} "
              f"{obeat:14.1f}% {beat - obeat:8.1f} {se2:8.1f}")

    print("\n== every lookback's median, by base age (is the story the week, "
          "or old structures?) ==")
    print(f"  {'band':7s} {'n':>4s} " +
          " ".join(f"{lb:>8s}" for lb in LOOKBACKS))
    for lab in labels:
        sub = e[e["base_bucket"] == lab]
        if sub.empty:
            continue
        print(f"  {lab:7s} {len(sub):4d} " +
              " ".join(f"{sub[lb].median():8.1f}" for lb in LOOKBACKS))


def load_bench(symbol: str) -> pd.DataFrame:
    """One benchmark's adjusted series, straight from the store.

    `QQQ` because that is what was asked for; `^IXIC` alongside it because that
    is the app's actual `MARKET_INDEX` (§5d), and a result that flips between
    the two would be a result about the benchmark, not about his entries.
    """
    import duckdb

    con = duckdb.connect(str(ROOT / "data" / "screener.duckdb"), read_only=True)
    df = con.execute(
        "SELECT session, high, low, adj_close FROM bars WHERE symbol = ? "
        "AND session BETWEEN DATE '2018-01-01' AND DATE '2023-01-15' "
        "ORDER BY session", [symbol]).df()
    con.close()
    df = df.set_index(pd.to_datetime(df["session"]))
    return df[["high", "low", "adj_close"]].rename(
        columns={"high": "High", "low": "Low", "adj_close": "Adj"})


def main() -> None:
    trades = load_trades(ROOT / "references" / "trades_bo_gain10smaPct_desc.json")
    frames, source = load_frames()
    frames = {k: v for k, v in frames.items()
              if k in {t["ticker"] for t in trades}}
    entries, skips = build(trades, frames, source)
    bg = background(entries, frames)

    qqq, ixic = load_bench("QQQ"), load_bench("^IXIC")
    entries_q = attach_benchmark(entries, qqq, "qqq")
    bg_q = attach_benchmark(bg, qqq, "qqq")
    entries_i = attach_benchmark(entries, ixic, "ixic")

    out = Path(__file__).parent / "prior_move_at_entry.csv"
    entries_q.to_csv(out, index=False)
    report(entries_q, bg_q, len(trades), skips)
    report_benchmark(entries_q, bg_q, entries_i, "qqq")
    report_base_age(entries_q, bg_q, "qqq")
    print(f"\nper-trade rows: {out}")


if __name__ == "__main__":
    main()
