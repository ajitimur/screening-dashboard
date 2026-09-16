"""PROTOTYPE — throwaway. Nothing imports this. Not part of the pipeline.

The sector leadership study. One question: does Turnover share, Participation
or Rotation momentum (research note 06 §7, CONTEXT.md §Themes) predict Sector
leadership better than the two rotation columns already on the sector board,
the Shape differential and the Temporal delta?

    backend/.venv/bin/python backend/prototypes/sector-leadership/study.py \
        --store /abs/path/to/a/COPY/of/screener.duckdb [--market US|IDX]

Reads a copy of data/screener.duckdb read-only, never the live store. History
is reconstructed from ``bars`` alone: the universe per past session by the
pipeline's own rules (screener.universe), the rank table by the pipeline's own
lookback anchors (screener.indicators), today's sector labels applied to every
past date. Writes results.txt and results.json beside this file.

Parameters are the note's, fixed, no sweeps: Turnover share 5 vs 60 sessions;
Participation 20 and 50 bar SMA, 20 bar highs; Rotation momentum EWM span 10,
lag 5. The forecaster for Participation is the share above the 20 bar SMA (the
number the note itself names for its follow-up contrast); the 50 bar share and
the net new highs are printed beside it and do not decide.
"""

from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_left, bisect_right
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from screener.indicators import LOOKBACKS, anchor_date  # noqa: E402
from screener.ranks import TOP_DECILE  # noqa: E402
from screener.sectors import (  # noqa: E402
    ROTATION_MIN_MEMBERS,
    SECTORS,
    LONG_LOOKBACK,
    SHORT_LOOKBACK,
    TEMPORAL_LOOKBACK,
    TEMPORAL_SESSIONS,
)
from screener.universe import (  # noqa: E402
    DENSITY_MAX_GAP,
    DENSITY_MIN,
    DENSITY_WINDOW,
    HYSTERESIS_EXIT,
    LIQUIDITY_FLOOR,
    LIQUIDITY_WINDOW,
    MIN_LISTING_BARS,
)
from screener.volatility import ARB_POLICY_ERAS  # noqa: E402

HERE = Path(__file__).resolve().parent

# The study's own constants (the handoff's, not tunables).
LOAD_FROM = date(2017, 6, 1)      # enough runway for 12m anchors and EWM warm-up
EVAL_FROM = date(2019, 1, 1)      # first forecast session scored
HORIZON = 20                      # sessions; the target's rise and the delta's lag
TOP_N = 3                         # sector leadership is the top three
TURNOVER_SHORT, TURNOVER_LONG = 5, 60
SMA_SHORT, SMA_LONG = 20, 50
HIGH_WINDOW = 20
EWM_SPAN, MOMENTUM_LAG = 10, 5
BOOT_BLOCK, BOOT_DRAWS, BOOT_SEED = 20, 2000, 7

INCUMBENTS = ("Shape differential", "Temporal delta")
CANDIDATES = ("Turnover share", "Participation", "Rotation momentum")

SURVIVORSHIP = (
    "WARNING: survivorship. Sector labels exist only for names the store labels "
    "today, so every past sector is built from survivors and every hit rate below "
    "is inflated. Incumbents and candidates share the hole; read only differences."
)


# -- load ---------------------------------------------------------------------


def load(con, market: str):
    bars = con.execute(
        """
        select symbol, session, close, adj_close, volume from bars
        where market = ? and session >= ?
          and symbol not like '^%' and symbol not like '%=%'
          and symbol not in ('SPY', 'QQQ', 'IWM', 'DIA')
        order by symbol, session
        """,
        [market, LOAD_FROM],
    ).df()
    bars["session"] = pd.to_datetime(bars["session"]).dt.date
    labels = dict(
        con.execute(
            "select symbol, sector from labels where market = ?", [market]
        ).fetchall()
    )
    return bars, labels


def matrices(bars: pd.DataFrame):
    """Per-symbol rolling features over traded bars, then session × symbol grids.

    Rolling windows run over a name's own traded bars (the repo's convention for
    SMA, ADR and the liquidity median), then the value is carried forward onto
    the market calendar so a session reads the last bar on or before it.
    """
    sessions = np.array(sorted(bars["session"].unique()))
    symbols = np.array(sorted(bars["symbol"].unique()))
    S, N = len(sessions), len(symbols)
    si = np.searchsorted(sessions, bars["session"].to_numpy())
    yi = np.searchsorted(symbols, bars["symbol"].to_numpy())

    g = bars.groupby("symbol", sort=False)
    bars = bars.assign(
        dv=bars["close"] * bars["volume"],
        nbars=g.cumcount() + 1,
    )
    g = bars.groupby("symbol", sort=False)
    roll = lambda col, w, f: getattr(g[col].rolling(w), f)().reset_index(level=0, drop=True)
    bars["dv_med"] = roll("dv", LIQUIDITY_WINDOW, "median")
    bars["sma_s"] = roll("adj_close", SMA_SHORT, "mean")
    bars["sma_l"] = roll("adj_close", SMA_LONG, "mean")
    bars["hi"] = roll("adj_close", HIGH_WINDOW, "max")
    bars["lo"] = roll("adj_close", HIGH_WINDOW, "min")
    bars["prev_adj"] = g["adj_close"].shift(1)

    def grid(col, fill=np.nan, dtype=float):
        m = np.full((S, N), fill, dtype=dtype)
        m[si, yi] = bars[col].to_numpy()
        return m

    def ffill(m):
        df = pd.DataFrame(m)
        return df.ffill().to_numpy()

    has_bar = np.zeros((S, N), bool)
    has_bar[si, yi] = True
    out = {
        "sessions": sessions,
        "symbols": symbols,
        "has_bar": has_bar,
        "adj": ffill(grid("adj_close")),
        "dv_med": ffill(grid("dv_med")),
        "nbars": ffill(grid("nbars")),
        "sma_s": ffill(grid("sma_s")),
        "sma_l": ffill(grid("sma_l")),
        "hi": ffill(grid("hi")),
        "lo": ffill(grid("lo")),
        "dv": grid("dv", fill=0.0),
        "up": grid("adj_close") > grid("prev_adj"),
        "down": grid("adj_close") < grid("prev_adj"),
    }
    # At a 20 bar closing high / low, on a session the name traded.
    at = grid("adj_close")
    out["new_high"] = has_bar & (at >= grid("hi"))
    out["new_low"] = has_bar & (at <= grid("lo"))
    return out


# -- the universe, per past session (screener.universe rules) -----------------


def rolling_sum(m: np.ndarray, window: int) -> np.ndarray:
    c = np.cumsum(m, axis=0, dtype=float)
    out = c.copy()
    out[window:] = c[window:] - c[:-window]
    return out


def universe(M, market: str) -> np.ndarray:
    has = M["has_bar"]
    traded20 = rolling_sum(has, DENSITY_WINDOW)
    recent = rolling_sum(has, DENSITY_MAX_GAP + 1) > 0
    gate = (traded20 >= DENSITY_MIN) & recent & (M["nbars"] >= MIN_LISTING_BARS)
    floor = LIQUIDITY_FLOOR[market]
    dv_med = np.nan_to_num(M["dv_med"], nan=-1.0)
    S, N = has.shape
    member = np.zeros((S, N), bool)
    prev = np.zeros(N, bool)
    for t in range(S):
        thr = np.where(prev, floor * HYSTERESIS_EXIT, floor)
        prev = gate[t] & (dv_med[t] >= thr)
        member[t] = prev
    return member


# -- the rank table and the sector shares (screener.ranks / sectors) ----------


def top_deciles(M, member: np.ndarray) -> dict[str, np.ndarray]:
    sessions = list(M["sessions"])
    adj = M["adj"]
    S, N = adj.shape
    out = {}
    for lb in LOOKBACKS:
        start = np.full((S, N), np.nan)
        for t, s in enumerate(sessions):
            i = bisect_right(sessions, anchor_date(s, lb)) - 1
            if i >= 0:
                start[t] = adj[i]
        with np.errstate(divide="ignore", invalid="ignore"):
            ret = adj / start - 1
        ret[~member] = np.nan
        ret[start == 0] = np.nan
        df = pd.DataFrame(ret)
        pct = df.rank(axis=1, method="max").to_numpy() / df.notna().sum(axis=1).to_numpy()[:, None]
        out[lb] = (pct >= TOP_DECILE) & member
    return out


def onehot_sectors(symbols, labels) -> np.ndarray:
    idx = {s: j for j, s in enumerate(SECTORS)}
    H = np.zeros((len(symbols), len(SECTORS)))
    for i, sym in enumerate(symbols):
        j = idx.get(labels.get(sym, ""))
        if j is not None:
            H[i, j] = 1.0
    return H


def share(mask: np.ndarray, member: np.ndarray, H: np.ndarray):
    n = member.astype(float) @ H
    k = (mask & member).astype(float) @ H
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(n > 0, k / n, 0.0)
    return s, k, n


# -- the five series, each session × 11 sectors ---------------------------------


def zscore_rows(x: np.ndarray) -> np.ndarray:
    mu = x.mean(axis=1, keepdims=True)
    sd = x.std(axis=1, keepdims=True)
    return np.where(sd > 0, (x - mu) / np.where(sd > 0, sd, 1.0), 0.0)


def series(M, member, top, H):
    S = member.shape[0]
    shares, ks = {}, {}
    for lb in LOOKBACKS:
        shares[lb], ks[lb], n = share(top[lb], member, H)

    out = {}
    # Incumbents.
    out["Shape differential"] = shares[SHORT_LOOKBACK] - shares[LONG_LOOKBACK]
    temporal = np.full_like(shares[TEMPORAL_LOOKBACK], np.nan)
    temporal[TEMPORAL_SESSIONS:] = (
        shares[TEMPORAL_LOOKBACK][TEMPORAL_SESSIONS:]
        - shares[TEMPORAL_LOOKBACK][:-TEMPORAL_SESSIONS]
    )
    out["Temporal delta"] = temporal

    # Turnover share: sector dollar volume as a share of the universe's, 5 vs 60.
    dv = np.where(member, M["dv"], 0.0)
    sec = dv @ H
    mkt = dv.sum(axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        s5 = rolling_sum(sec, TURNOVER_SHORT) / rolling_sum(mkt, TURNOVER_SHORT)
        s60 = rolling_sum(sec, TURNOVER_LONG) / rolling_sum(mkt, TURNOVER_LONG)
    out["Turnover share"] = (s5 - s60) * 100.0
    out["Turnover share"][:TURNOVER_LONG] = np.nan
    up = np.where(member & M["up"], M["dv"], 0.0) @ H
    down = np.where(member & M["down"], M["dv"], 0.0) @ H
    with np.errstate(divide="ignore", invalid="ignore"):
        out["_updown"] = (rolling_sum(up, 5) - rolling_sum(down, 5)) / rolling_sum(sec, 5)
    dv5 = rolling_sum(dv, TURNOVER_SHORT)
    conc = np.zeros_like(sec)
    for j in range(len(SECTORS)):
        cols = H[:, j] > 0
        if cols.any():
            with np.errstate(divide="ignore", invalid="ignore"):
                conc[:, j] = dv5[:, cols].max(axis=1) / rolling_sum(sec, 5)[:, j]
    out["_concentration"] = conc

    # Participation: share of members above their own SMA; net 20 bar highs.
    above_s = M["adj"] > M["sma_s"]
    above_l = M["adj"] > M["sma_l"]
    out["Participation"], _, _ = share(above_s, member, H)
    out["_above_50"], _, _ = share(above_l, member, H)
    nh, _, n = share(M["new_high"], member, H)
    nl, _, _ = share(M["new_low"], member, H)
    out["_net_new_highs"] = nh - nl

    # Rotation momentum: EWM of share(1m), standardised across the 11 sectors,
    # then the EWM of its 5 session change, standardised again.
    ratio = pd.DataFrame(shares[TEMPORAL_LOOKBACK]).ewm(span=EWM_SPAN, adjust=False).mean().to_numpy()
    ratio = zscore_rows(ratio)
    change = np.full_like(ratio, np.nan)
    change[MOMENTUM_LAG:] = ratio[MOMENTUM_LAG:] - ratio[:-MOMENTUM_LAG]
    mom = pd.DataFrame(change).ewm(span=EWM_SPAN, adjust=False).mean().to_numpy()
    out["Rotation momentum"] = np.where(np.isnan(mom), np.nan, zscore_rows(np.nan_to_num(mom)))
    out["Rotation momentum"][:MOMENTUM_LAG] = np.nan

    # The target: the 20 session rise in share(1m), eligible at k(1m) >= 2 at the end.
    rise = np.full_like(shares[TEMPORAL_LOOKBACK], np.nan)
    rise[:-HORIZON] = shares[TEMPORAL_LOOKBACK][HORIZON:] - shares[TEMPORAL_LOOKBACK][:-HORIZON]
    eligible = np.zeros_like(rise, dtype=bool)
    eligible[:-HORIZON] = ks[TEMPORAL_LOOKBACK][HORIZON:] >= ROTATION_MIN_MEMBERS
    out["_rise"] = rise
    out["_eligible"] = eligible
    out["_share_1m"] = shares[TEMPORAL_LOOKBACK]
    out["_k_1m"] = ks[TEMPORAL_LOOKBACK]
    out["_n"] = n
    return out


# -- scoring --------------------------------------------------------------------


def top_k(values: np.ndarray, k: int, allowed: np.ndarray | None = None) -> set[int]:
    """Top ``k`` sector indices by value, ties broken by SECTORS order (the
    board's own tie rule)."""
    order = np.lexsort((np.arange(len(values)), -values))
    picked = []
    for j in order:
        if allowed is not None and not allowed[j]:
            continue
        if np.isnan(values[j]):
            continue
        picked.append(int(j))
        if len(picked) == k:
            break
    return set(picked)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    ra = pd.Series(a).rank().to_numpy()
    rb = pd.Series(b).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def per_session(series_: dict, sessions, eval_idx):
    """Per forecast session: hits (0..3) for every forecaster, the chance
    expectation, and the rank correlation with the rise."""
    names = INCUMBENTS + CANDIDATES
    rows = []
    for t in eval_idx:
        actual = top_k(series_["_rise"][t], TOP_N, series_["_eligible"][t])
        if not actual:
            continue
        row = {"session": sessions[t], "chance": len(actual) / len(SECTORS)}
        # Diagnostic only: the current level of share(1m) against its own rise.
        row["level rho"] = spearman(series_["_share_1m"][t], series_["_rise"][t])
        skip = False
        for name in names:
            v = series_[name][t]
            if np.isnan(v).any():
                skip = True
                break
            row[name] = len(top_k(v, TOP_N) & actual) / TOP_N
            row[name + " rho"] = spearman(v, series_["_rise"][t])
        if not skip:
            rows.append(row)
    return pd.DataFrame(rows)


def block_bootstrap(diff: np.ndarray) -> tuple[float, float]:
    rng = np.random.default_rng(BOOT_SEED)
    n = len(diff)
    if n < BOOT_BLOCK * 2:
        return float("nan"), float("nan")
    nblocks = int(np.ceil(n / BOOT_BLOCK))
    means = np.empty(BOOT_DRAWS)
    for d in range(BOOT_DRAWS):
        starts = rng.integers(0, n, nblocks)
        idx = (starts[:, None] + np.arange(BOOT_BLOCK)[None, :]).ravel() % n
        means[d] = diff[idx[:n]].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def score(ps: pd.DataFrame) -> dict:
    names = INCUMBENTS + CANDIDATES
    table = {
        name: {
            "hit_rate": float(ps[name].mean()),
            "spearman": float(ps[name + " rho"].mean()),
        }
        for name in names
    }
    best_inc = max(INCUMBENTS, key=lambda k: table[k]["hit_rate"])
    verdicts = {}
    for c in CANDIDATES:
        diff = (ps[c] - ps[best_inc]).to_numpy()
        lo, hi = block_bootstrap(diff)
        verdicts[c] = {
            "vs": best_inc,
            "gap": float(diff.mean()),
            "ci95": [lo, hi],
            "beats": bool(diff.mean() > 0 and lo > 0),
        }
    return {
        "sessions": int(len(ps)),
        "from": str(ps["session"].iloc[0]),
        "to": str(ps["session"].iloc[-1]),
        "chance": float(ps["chance"].mean()),
        "level_spearman": float(ps["level rho"].mean()),
        "table": table,
        "best_incumbent": best_inc,
        "verdicts": verdicts,
    }


# -- checks against the 29 stored sessions ------------------------------------


def check_against_store(con, market, M, member, series_, H, labels, out):
    """The store holds universe and ranks for a few weeks only; agree with them."""
    sessions = list(M["sessions"])
    stored = con.execute(
        "select session, symbol from universe where market = ? order by 1", [market]
    ).fetchall()
    by_session: dict[date, set[str]] = {}
    for s, sym in stored:
        by_session.setdefault(s, set()).add(sym)
    sym_idx = {s: i for i, s in enumerate(M["symbols"])}
    jac, sizes = [], []
    for s, theirs in by_session.items():
        if s not in sessions:
            continue
        t = sessions.index(s)
        mine = {M["symbols"][i] for i in np.flatnonzero(member[t])}
        jac.append(len(mine & theirs) / len(mine | theirs))
        sizes.append((len(mine), len(theirs)))
    out.append(f"  universe vs stored ({len(jac)} sessions): mean Jaccard {np.mean(jac):.3f}, "
               f"mine/stored on last {sizes[-1][0]}/{sizes[-1][1]}")

    last = max(by_session)
    t = sessions.index(last)
    rows = con.execute(
        """
        select r.symbol, l.sector, r.percentile from ranks r join labels l
          on l.market = r.market and l.symbol = r.symbol
        where r.market = ? and r.session = ? and r.lookback = ?
        """,
        [market, last, TEMPORAL_LOOKBACK],
    ).fetchall()
    n_st: dict[str, set] = {}
    k_st: dict[str, set] = {}
    for sym, sec, pct in rows:
        n_st.setdefault(sec, set()).add(sym)
        if pct >= TOP_DECILE:
            k_st.setdefault(sec, set()).add(sym)
    out.append(f"  share(1m) on {last}, mine vs stored (k/n):")
    for j, sec in enumerate(SECTORS):
        out.append(f"    {sec:<24} {int(series_['_k_1m'][t][j]):>3}/{int(series_['_n'][t][j]):<4} "
                   f"vs {len(k_st.get(sec, ())):>3}/{len(n_st.get(sec, ())):<4}")


# -- report ---------------------------------------------------------------------


def fmt_table(res: dict) -> list[str]:
    lines = [f"  sessions {res['sessions']} ({res['from']} to {res['to']}), "
             f"chance hit rate {res['chance']:.3f}"]
    lines.append(f"  {'forecaster':<20} {'hit rate':>9} {'rank corr':>10}")
    for name in INCUMBENTS + CANDIDATES:
        r = res["table"][name]
        tag = "incumbent" if name in INCUMBENTS else "candidate"
        lines.append(f"  {name:<20} {r['hit_rate']:>9.3f} {r['spearman']:>10.3f}   {tag}")
    lines.append(f"  diagnostic: rank corr of the share(1m) level itself with the rise "
                 f"{res['level_spearman']:+.3f} (mean reversion of the target)")
    lines.append(f"  best incumbent: {res['best_incumbent']}")
    for c, v in res["verdicts"].items():
        lo, hi = v["ci95"]
        word = "BEATS" if v["beats"] else "does not beat"
        lines.append(f"  {c:<20} {word} {v['vs']}: gap {v['gap']:+.3f} "
                     f"(block bootstrap 95% [{lo:+.3f}, {hi:+.3f}])")
    return lines


def run_market(con, market: str, report: list[str], results: dict):
    bars, labels = load(con, market)
    M = matrices(bars)
    del bars
    member = universe(M, market)
    top = top_deciles(M, member)
    H = onehot_sectors(M["symbols"], labels)
    ser = series(M, member, top, H)
    sessions = list(M["sessions"])
    first = bisect_left(sessions, EVAL_FROM)
    eval_idx = range(first, len(sessions) - HORIZON)
    ps = per_session(ser, M["sessions"], eval_idx)

    report.append(f"\n=== {market} ===")
    report.append(f"  symbols loaded {len(M['symbols'])}, labelled {int((H.sum(axis=1) > 0).sum())}, "
                  f"sessions {len(sessions)} from {sessions[0]}")
    report.append(f"  median concentration (top member's share of sector 5 session turnover): "
                  f"{np.nanmedian(ser['_concentration'][first:]):.2f}; "
                  f"median |up/down split| {np.nanmedian(np.abs(ser['_updown'][first:])):.2f}")
    check_against_store(con, market, M, member, ser, H, labels, report)

    res = score(ps)
    results[market] = {"pooled": res}
    report.append("  -- pooled --")
    report.extend(fmt_table(res))

    eras = ARB_POLICY_ERAS.get(market, ())
    if eras:
        bounds = [sessions[0]] + list(eras) + [date.max]
        for a, b in zip(bounds[:-1], bounds[1:]):
            sub = ps[(ps["session"] >= a) & (ps["session"] < b)]
            label = f"era {a} to {b if b != date.max else 'now'}"
            if len(sub) == 0:
                report.append(f"  -- {label}: no sessions --")
                continue
            r = score(sub)
            results[market][label] = r
            report.append(f"  -- {label} --")
            report.extend(fmt_table(r))
    ps.to_csv(HERE / f"per-session-{market}.csv", index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True, help="absolute path to a COPY of screener.duckdb")
    ap.add_argument("--market", choices=["US", "IDX"], action="append")
    args = ap.parse_args()
    con = duckdb.connect(args.store, read_only=True)
    report = ["PROTOTYPE sector leadership study", SURVIVORSHIP]
    results = {"survivorship": SURVIVORSHIP}
    for market in args.market or ["IDX", "US"]:
        run_market(con, market, report, results)
        print("\n".join(report[-40:]), flush=True)
    report.append("")
    report.append(SURVIVORSHIP)
    (HERE / "results.txt").write_text("\n".join(report) + "\n")
    (HERE / "results.json").write_text(json.dumps(results, indent=2, default=str))
    print("\nwrote", HERE / "results.txt")


if __name__ == "__main__":
    main()
