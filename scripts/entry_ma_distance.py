#!/usr/bin/env python
"""How far above the rising MA does Qullamaggie actually enter?

`references/qullamaggie-method.md` §5 asserts, qualitatively, that correct
trendline geometry produces entries "hugging the rising 10/20/50-day", and that
this is the *same rule* as the ≤ 1 × ADR stop cap in §7 — buy far from the MA
and the stop is unaffordable, so the trade is dead on arrival. That is an
empirical claim, and his published trade log lets us measure it.

This script joins `references/trades_bo_gain10smaPct_desc.json` (828 logged
breakout longs, 2019-10 → 2022-11) to daily bars and, for each entry, reports
the distance from the prior-close SMA10 / SMA20 — prior close because that is
the MA value actually on screen at an intraday entry, the entry-day SMA not
being knowable at 09:32.

Distance is reported twice: as a percentage of the MA, and in ADR units
(`ADR% = SMA20(High/Low − 1)`, the same definition `screener/indicators.py`
uses). The ADR-relative number is the one that means anything across names —
7% above the 10-day is routine for a 15%-ADR biotech and absurd for a 3%-ADR
mega-cap, and §7 denominates the stop cap in ADR for exactly that reason.

Bars come from the local `data/screener.duckdb` US bars (which already cover
most of the tickers); `--fetch` fills the delisted remainder from Yahoo into a
local pickle cache.

Usage:
    python scripts/entry_ma_distance.py                 # local bars only
    python scripts/entry_ma_distance.py --fetch         # + Yahoo backfill
    python scripts/entry_ma_distance.py --db /path/to/screener.duckdb
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# The trade log's prices are as-traded; the bar series is split-adjusted to
# today. A name that split after the entry therefore lands in a different price
# frame, and `entryPrice / SMA` would be off by the split ratio. We recover the
# frame per trade by asking which ratio puts the entry back inside its own day's
# range (see `_split_factor`). These are the ratios worth trying — ordinary
# forward splits, the common reverse splits, and a few odd ones (3:2, 5:4).
SPLIT_CANDIDATES = [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 40,
                    1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10, 1 / 20,
                    2 / 3, 3 / 2, 4 / 3, 5 / 4, 3 / 4, 2 / 5, 4 / 5]

# A trade needs a full SMA20 plus enough bars for the 20-bar ADR window. 25
# leaves a small margin for holidays already absent from the series.
MIN_HISTORY = 25

# Tolerance when testing "is this price inside that day's range?". Half a
# percent absorbs the rounding in his logged fills without admitting a wrong
# split ratio — the candidates are all ≥ 25% apart, so there is no ambiguity.
RANGE_TOL = 0.005

# Beyond this the "distance" is not a distance but a data fault — a split ratio
# outside SPLIT_CANDIDATES, or a bad bar. One trade in 580 trips it (NVDA
# 2020-09-27, whose 4:1 and 10:1 splits compound past the candidate list).
MAX_PLAUSIBLE_PCT = 60.0


def load_trades(path: Path) -> list[dict]:
    return json.loads(path.read_text())["trades"]


def load_local_bars(db: Path) -> dict[str, pd.DataFrame]:
    """US daily bars from the screener store, keyed by symbol."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        df = con.execute(
            "SELECT symbol, session, high, low, close FROM bars "
            "WHERE market = 'US' AND session BETWEEN DATE '2019-01-01' "
            "AND DATE '2023-01-15' ORDER BY symbol, session"
        ).df()
    finally:
        con.close()
    out = {}
    for sym, g in df.groupby("symbol"):
        g = g.set_index(pd.to_datetime(g["session"]))
        out[sym] = g[["high", "low", "close"]].rename(columns=str.title)
    return out


def fetch_missing(tickers: list[str], cache: Path) -> dict[str, pd.DataFrame]:
    """Backfill tickers the local store lacks — almost all of them delisted.

    Yahoo's sustained rate limit is real and refills on the order of a minute,
    so this goes in small chunks with a pause and check-points the cache after
    each one: a rate-limited run can be re-run and picks up where it stopped.
    """
    import yfinance as yf

    data: dict[str, pd.DataFrame] = {}
    if cache.exists():
        data = pickle.loads(cache.read_bytes())
    todo = [t for t in tickers if t not in data]
    for i in range(0, len(todo), 25):
        chunk = todo[i:i + 25]
        try:
            df = yf.download(chunk, start="2019-06-01", end="2023-01-15",
                             auto_adjust=False, actions=True, progress=False,
                             group_by="ticker", threads=True)
        except Exception as exc:  # a dead chunk must not sink the whole run
            print(f"  chunk failed ({chunk[0]}…): {exc}", file=sys.stderr)
            continue
        for t in chunk:
            try:
                sub = df[t].dropna(how="all") if len(chunk) > 1 else df.dropna(how="all")
            except KeyError:
                continue
            if len(sub):
                data[t] = sub
        cache.write_bytes(pickle.dumps(data))
        print(f"  fetched {i + len(chunk)}/{len(todo)}", file=sys.stderr)
        time.sleep(2)
    return data


def _split_factor(entry_price: float, low: float, high: float) -> float | None:
    """The ratio that puts `entry_price` back into the bar's own price frame.

    Returns 1.0 when the price already sits in the day's range (the common
    case), the matching split ratio when *exactly one* candidate explains the
    gap, and None otherwise — the trade is then dropped rather than guessed at,
    since a wrong ratio manufactures a plausible-looking distance out of nothing.

    Requiring uniqueness matters on the wide-range days, which is precisely
    where these trades live. GME on 2021-02-24 ranged 44.70–91.71 (ADR 55%);
    both 3:1 and 4:1 put the logged 46.50 fill inside that range, and picking
    the one nearest the midpoint picks 3 — wrong, GME split 4:1. A day whose
    high is more than ~1.4× its low cannot discriminate adjacent ratios at all,
    so we decline to try.
    """
    lo, hi = low * (1 - RANGE_TOL), high * (1 + RANGE_TOL)
    if lo <= entry_price <= hi:
        return 1.0
    fits = [s for s in SPLIT_CANDIDATES if lo <= entry_price / s <= hi]
    return fits[0] if len(fits) == 1 else None


def measure(trades: list[dict], frames: dict[str, pd.DataFrame],
            source: dict[str, str]) -> tuple[pd.DataFrame, list[tuple[str, str]]]:
    rows, skipped = [], []
    for t in trades:
        ticker = t["ticker"]
        frame = frames.get(ticker)
        if frame is None:
            skipped.append((ticker, "no data"))
            continue
        entry_date = pd.Timestamp(t["entryDate"][:10])
        prior = frame.loc[frame.index < entry_date]
        if len(prior) < MIN_HISTORY:
            skipped.append((ticker, "short history"))
            continue

        entry = t["entryPrice"]
        factor = 1.0
        day = frame.loc[frame.index == entry_date]
        if len(day):
            factor = _split_factor(entry, float(day["Low"].iloc[0]),
                                   float(day["High"].iloc[0]))
            if factor is None:
                skipped.append((ticker, "price mismatch"))
                continue
        entry /= factor

        close = prior["Close"].astype(float)
        sma10 = close.iloc[-10:].mean()
        sma20 = close.iloc[-20:].mean()
        adr = float((prior["High"].astype(float) / prior["Low"].astype(float) - 1)
                    .iloc[-20:].mean()) * 100

        rows.append(dict(
            ticker=ticker, date=entry_date.date(), entry=entry,
            d10=(entry / sma10 - 1) * 100, d20=(entry / sma20 - 1) * 100,
            adr=adr, stop_pct=t["stopPercentage"] * 100,
            rr10sma=t.get("rr10sma"), gain10sma_pct=t.get("gain10smaPct"),
            mae10sma_pct=t.get("mae10smaPct"),
            src=source.get(ticker, "?"), split=factor,
        ))

    df = pd.DataFrame(rows)
    df["d10_adr"] = df.d10 / df.adr
    df["d20_adr"] = df.d20 / df.adr
    faults = df[df.d10.abs() > MAX_PLAUSIBLE_PCT]
    for _, r in faults.iterrows():
        skipped.append((r.ticker, "implausible distance"))
    return df[df.d10.abs() <= MAX_PLAUSIBLE_PCT].reset_index(drop=True), skipped


def describe(name: str, s: pd.Series) -> None:
    q = s.quantile([.05, .25, .5, .75, .95])
    print(f"{name:16s} mean {s.mean():6.2f}  median {s.median():6.2f}  "
          f"sd {s.std():5.2f} | p5 {q[.05]:6.2f}  p25 {q[.25]:6.2f}  "
          f"p75 {q[.75]:6.2f}  p95 {q[.95]:6.2f}")


def report(df: pd.DataFrame, n_trades: int, skipped: list[tuple[str, str]]) -> None:
    from collections import Counter
    print(f"matched {len(df)} of {n_trades} trades "
          f"({len(df) / n_trades * 100:.0f}%); skipped {len(skipped)}")
    print("skip reasons:", dict(Counter(r for _, r in skipped)))

    print("\n-- entry distance above the MA, % of the MA (prior-close SMA) --")
    describe("above SMA10", df.d10)
    describe("above SMA20", df.d20)

    print("\n-- the same distance in ADR units --")
    describe("SMA10 (xADR)", df.d10_adr)
    describe("SMA20 (xADR)", df.d20_adr)

    print("\n-- ADR at entry, and the stop he actually set --")
    describe("ADR %", df.adr)
    describe("stop %", df.stop_pct)

    print(f"\nentered below SMA10: {(df.d10 < 0).mean() * 100:.1f}%   "
          f"below SMA20: {(df.d20 < 0).mean() * 100:.1f}%")
    for k in (1, 2):
        print(f"within {k}x ADR of SMA10: {(df.d10_adr.abs() <= k).mean() * 100:.1f}%   "
              f"of SMA20: {(df.d20_adr.abs() <= k).mean() * 100:.1f}%")

    graded = df.dropna(subset=["rr10sma"])
    if graded.empty:
        return

    # His hit rate is ~23%, so the median trade is a −1R stop-out in every
    # bucket and median R tells us nothing. Mean R (the few large winners carry
    # the strategy) and the share of ≥3R trades are what separate the buckets.
    print("\n-- outcome by entry distance above SMA10, in ADR units --")
    bins = [-99, 0, 0.5, 1, 1.5, 2, 3, 99]
    agg = dict(n=("rr10sma", "size"), mean_R=("rr10sma", "mean"),
               win_pct=("rr10sma", lambda s: (s > 0).mean() * 100),
               big_pct=("rr10sma", lambda s: (s >= 3).mean() * 100),
               med_mae=("mae10sma_pct", "median"))
    for col in ("d10_adr", "d20_adr"):
        label = "SMA10" if col == "d10_adr" else "SMA20"
        grouped = graded.groupby(pd.cut(graded[col], bins), observed=True).agg(**agg)
        print(f"\n[{label}]")
        print(grouped.round(2).to_string())

    print("\n-- where the edge dies: split the book at each SMA10 cutoff --")
    for cut in (1.0, 1.5, 2.0, 2.5, 3.0):
        at, beyond = graded[graded.d10_adr <= cut], graded[graded.d10_adr > cut]
        print(f"cut {cut:>4}x ADR | at-or-below n={len(at):3d} meanR {at.rr10sma.mean():5.2f} "
              f"win {(at.rr10sma > 0).mean() * 100:4.1f}% || beyond n={len(beyond):3d} "
              f"meanR {beyond.rr10sma.mean():5.2f} win {(beyond.rr10sma > 0).mean() * 100:4.1f}% "
              f"big {(beyond.rr10sma >= 3).mean() * 100:4.1f}%")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "screener.duckdb")
    ap.add_argument("--trades", type=Path,
                    default=ROOT / "references" / "trades_bo_gain10smaPct_desc.json")
    ap.add_argument("--out", type=Path,
                    default=ROOT / "references" / "qullamaggie-entry-ma-distance.csv")
    ap.add_argument("--fetch", action="store_true",
                    help="backfill missing (mostly delisted) tickers from Yahoo")
    ap.add_argument("--cache", type=Path, default=ROOT / "data" / "entry_ma_yahoo.pkl")
    args = ap.parse_args()

    trades = load_trades(args.trades)
    tickers = sorted({t["ticker"] for t in trades})

    frames = load_local_bars(args.db) if args.db.exists() else {}
    frames = {k: v for k, v in frames.items() if k in tickers}
    source = {k: "db" for k in frames}
    print(f"local bars cover {len(frames)}/{len(tickers)} tickers", file=sys.stderr)

    if args.fetch or args.cache.exists():
        missing = [t for t in tickers if t not in frames]
        extra = fetch_missing(missing, args.cache) if args.fetch else \
            pickle.loads(args.cache.read_bytes())
        for k, v in extra.items():
            if k not in frames and len(v):
                frames[k] = v[["High", "Low", "Close"]]
                source[k] = "yf"
        print(f"with Yahoo backfill: {len(frames)}/{len(tickers)}", file=sys.stderr)

    df, skipped = measure(trades, frames, source)
    df.to_csv(args.out, index=False)
    report(df, len(trades), skipped)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
