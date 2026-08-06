"""THROWAWAY instrumentation: size the near-miss population (issue #53).

Reads a *snapshot copy* of data/screener.duckdb read-only. It does not modify
detection.py: it re-implements ``detect``'s control flow by calling the module's
own private helpers, so every threshold and helper is the production one.

Run:  .venv/bin/python .scratch/nearmiss/measure.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import duckdb  # noqa: E402

from screener.detection import (  # noqa: E402
    CATCHUP_10,
    CATCHUP_20,
    MAX_BASE_LEN,
    MIN_BASE_LEN,
    MIN_HISTORY,
    RISING_LAG,
    SMA_SUPPORT,
    Detection,
    _adr,
    _argmax,
    _as_of_index,
    _churn_l,
    _dryup,
    _find_cluster,
    _fit_envelope,
    _prior_move,
    _sma_close,
    detection_gate,
)
from screener.ranks import rank_table  # noqa: E402
from screener.score import star_score  # noqa: E402
from screener.sectors import leave_one_out_sector_shares  # noqa: E402
from screener.store import Store  # noqa: E402

SNAPSHOT = ROOT / ".scratch/nearmiss/screener.duckdb"

# Rejection points, in the order detect() applies them. See detection.py:314-350.
REASONS = [
    ("no_bar_asof", "hard"),         # detection.py:314-316
    ("short_history", "hard"),       # detection.py:314-316
    ("adr_nonpositive", "hard"),     # detection.py:322-324
    ("no_prior_move", "hard"),       # detection.py:327-329
    ("base_too_short", "immature"),  # detection.py:336-337
    ("not_caught_up", "immature"),   # detection.py:339-347
    ("no_cluster", "immature"),      # detection.py:349-350
    ("emitted", "-"),
]
IMMATURE = {"base_too_short", "not_caught_up", "no_cluster"}


def instrumented_detect(symbol: str, bars, as_of: date):
    """Mirror of detection.detect(), returning (reason, detection|None, flags).

    ``flags`` records the three immature tests evaluated *independently* for every
    name that clears all hard gates, so overlap between them is visible.
    """
    flags: dict[str, bool] = {}
    idx = _as_of_index(bars, as_of)
    if idx is None:
        return "no_bar_asof", None, flags
    if idx < MIN_HISTORY:
        return "short_history", None, flags
    high = [b.high for b in bars]
    low = [b.low for b in bars]
    close = [b.close for b in bars]
    vol = [b.volume for b in bars]

    a = _adr(bars[: idx + 1])
    if a is None or a <= 0:
        return "adr_nonpositive", None, flags
    adr_abs = a * close[idx]

    mv = _prior_move(high, low, idx)
    if mv is None:
        return "no_prior_move", None, flags
    move_gain, peak = mv
    base_start = peak
    if idx - base_start + 1 > MAX_BASE_LEN:
        recent = idx - MAX_BASE_LEN + 1
        base_start = _argmax(high, recent, idx)
    base_len = idx - base_start + 1

    # -- the three immature tests, all evaluated (production short-circuits) ----
    s10 = _sma_close(close, idx, 10)
    s20 = _sma_close(close, idx, 20)
    caught_up = (
        s10 is not None
        and s20 is not None
        and close[idx] - s10 <= CATCHUP_10 * adr_abs
        and close[idx] - s20 <= CATCHUP_20 * adr_abs
    )
    cluster = _find_cluster(high, low, idx, adr_abs)
    flags = {
        "base_too_short": base_len < MIN_BASE_LEN,
        "not_caught_up": not caught_up,
        "no_cluster": cluster is None,
        "_base_len": base_len,
    }

    if base_len < MIN_BASE_LEN:
        return "base_too_short", None, flags
    if not caught_up:
        return "not_caught_up", None, flags
    if cluster is None:
        return "no_cluster", None, flags

    k, cluster_high, cluster_low, range_adr = cluster
    anchor = _argmax(high, idx - k + 1, idx)
    slope, line_ok, zones, over_max, line_end = _fit_envelope(
        high, adr_abs, anchor, base_start, idx, k
    )
    trigger = cluster_high
    stop = trigger - cluster_low
    stopw_adr = stop / trigger / a if trigger > 0 else float("nan")
    s20 = _sma_close(close, idx, SMA_SUPPORT)
    s20_prev = _sma_close(close, idx - RISING_LAG, SMA_SUPPORT)
    det = Detection(
        symbol=symbol, session=as_of, detector_version=1, trigger=trigger, stop=stop,
        stopw_adr=stopw_adr, base_len=base_len, move_gain=move_gain, adr=a,
        close=close[idx], cluster_k=k, cluster_high=cluster_high,
        cluster_low=cluster_low, cluster_range_adr=range_adr, line_ok=line_ok,
        touch_zones=zones, overshoot_adr=over_max, slope=slope, line_end=line_end,
        base_low=min(low[base_start: idx + 1]),
        churn_l=_churn_l(high, low, base_start, idx),
        sma20_rising=(s20 is not None and s20_prev is not None and s20 > s20_prev),
        dryup=_dryup(vol, base_start, idx),
    )
    return "emitted", det, flags


def measure(store: Store, market: str, sessions: list[date], bars_cache):
    out = []
    for session in sessions:
        members = store.universe(market, session)
        universe_source = "stored"
        if not members:
            # No membership row for this session (only the run's own sessions have
            # one). Carry the nearest stored membership — documented caveat.
            for s in sorted({r.session for r in store.runs(market)}, reverse=True):
                members = store.universe(market, s)
                if members:
                    universe_source = f"carried from {s}"
                    break
        members_bars = {s: bars_cache(market, s) for s in members}
        ranks = store.ranks(market, session)
        ranks_source = "stored"
        if not ranks:
            ranks = rank_table(members_bars, session)
            ranks_source = "recomputed"
        gated = detection_gate(ranks)

        hist: Counter = Counter()
        flagct: Counter = Counter()
        overlap: Counter = Counter()
        baselens: Counter = Counter()
        dets = []
        for symbol in members:
            if symbol not in gated:
                hist["not_top_decile"] += 1
                continue
            reason, det, flags = instrumented_detect(
                symbol, members_bars[symbol], session
            )
            hist[reason] += 1
            if flags:
                baselens[flags.pop("_base_len")] += 1
                for name, failed in flags.items():
                    if failed:
                        flagct[name] += 1
                overlap[sum(flags.values())] += 1
            if det is not None:
                dets.append(det)
        out.append(
            dict(
                market=market, session=session, members=len(members),
                gated=len(gated & set(members)), hist=hist, flags=flagct,
                overlap=overlap, dets=dets, ranks=ranks, baselens=baselens,
                universe_source=universe_source, ranks_source=ranks_source,
            )
        )
    return out


def scores(store: Store, market: str, row):
    """Star score exactly as candidates.build_candidates derives it."""
    labels = store.labels(market)
    sector_of = {s: v.sector for s, v in labels.items()}
    prior_move = detection_gate(row["ranks"])
    shares = leave_one_out_sector_shares(row["ranks"], sector_of)
    have_labels = bool(sector_of)
    out = []
    for det in row["dets"]:
        stars, _ = star_score(
            det, prior_move=det.symbol in prior_move,
            sector_share=shares.get(det.symbol, 0.0),
        )
        # With no label cache the Sector dimension cannot fire; report the
        # +1-point upper bracket too so the distortion is visible.
        upper, _ = star_score(
            det, prior_move=det.symbol in prior_move,
            sector_share=shares.get(det.symbol, 0.0) if have_labels else 1.0,
        )
        out.append((det.symbol, stars, upper))
    return out


def main() -> None:
    con = duckdb.connect(str(SNAPSHOT))  # a throwaway copy; Store() needs DDL rights
    store = Store(con)
    cache: dict[tuple[str, str], list] = {}

    def bars_cache(market, symbol):
        key = (market, symbol)
        if key not in cache:
            cache[key] = store.bars(market, symbol)
        return cache[key]

    markets = [
        m for (m,) in con.execute(
            "select distinct market from universe order by 1"
        ).fetchall()
    ]
    n_sessions = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    for market in markets:
        all_sessions = store.sessions(market)
        sessions = all_sessions[-n_sessions:]
        rows = measure(store, market, sessions, bars_cache)
        for row in rows:
            print("=" * 72)
            print(
                f"{row['market']}  {row['session']}  universe={row['members']} "
                f"({row['universe_source']}) ranks={row['ranks_source']}"
            )
            h = row["hist"]
            print(f"  universe members                : {row['members']}")
            print("  rejected: not top decile (1m/3m/6m, pipeline.py:172): "
                  f"{h['not_top_decile']}")
            print(f"  entering detect()               : {row['gated']}")
            for name, kind in REASONS:
                print(f"    {name:<18} [{kind:<8}] {h[name]}")
            immature = sum(h[n] for n in IMMATURE)
            print(f"  NEAR-MISS (immature rejects)    : {immature}")
            print(f"  independent immature failures   : {dict(row['flags'])}")
            print("  # immature tests failed (of names past hard gates): "
                  f"{dict(sorted(row['overlap'].items()))}")
            print("  base_len of names past hard gates: "
                  f"{dict(sorted(row['baselens'].items()))}")
            sc = scores(store, row["market"], row)
            dist = Counter(s for _, s, _u in sc)
            dist_u = Counter(u for _, _s, u in sc)
            print(f"  detections: {len(sc)}  scores: {dict(sorted(dist.items()))}")
            n = len(sc) or 1
            gt3 = sum(1 for _, s, _u in sc if s > 3)
            gt4 = sum(1 for _, s, _u in sc if s > 4)
            gt3u = sum(1 for _, _s, u in sc if u > 3)
            gt4u = sum(1 for _, _s, u in sc if u > 4)
            print(f"  >3 stars: {gt3} ({100 * gt3 / n:.1f}%)   "
                  f">4 stars: {gt4} ({100 * gt4 / n:.1f}%)")
            print(f"  [sector-hit upper bracket] scores: {dict(sorted(dist_u.items()))}"
                  f"  >3: {gt3u}  >4: {gt4u}")
            print(f"  rows: {sorted(sc, key=lambda r: -r[1])}")


if __name__ == "__main__":
    main()
