"""Price the #145/#154 tightness restructure: recall recovered, field admitted.

The hard 1.5×ADR cluster cut became a far-outlier guard at ``OUTLIER_MULT``. A
loosening is only reportable with **both** halves of the ledger (ADR 0002's
condition 4, and the discipline #141/#149 used): how many of his executed trades
the change recovers, *and* how many more names it puts in the field per session.
Quoting the first without the second is the one-sided recall number the
calibration rule exists to prevent.

Two measurements, each against a committed baseline:

1. **Detection-stage recall**, over the 828-trade reference set. The detection
   stage is per-name — it reads bars and nothing cross-sectional — so it is
   re-measured without rebuilding the 947-session forward chain. Liquidity and
   decile are cross-sectional and untouched by this change, so their committed
   figures stand. Baseline: findings §3 (380/658, `cluster` 171 of 278).

2. **Field inflation per session.** For every session the replay store holds both
   ranks and v1 detection rows for, the detector is re-run over that night's
   *same* gated members and the count compared to the persisted v1 count. The
   gate itself does not move, so the difference is the detector's alone.

A side-car, like §3b's prototype: it is not part of `replay.study`'s reproducible
pass (§10) and writes nothing to the store it reads. It needs a replay store built
by `replay.store.build_replay_store`; give it a **copy** if another process holds
the live one's lock.

    python scripts/tightness_restructure.py --store data/replay.duckdb

``--sessions N`` samples N sessions evenly for part 2 instead of walking all of
them; the sample size is reported with the result either way.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from replay.caching_store import CachingStore  # noqa: E402
from replay.funnel import (  # noqa: E402
    COND_CLUSTER,
    diagnose_detection,
)
from replay.reference import (  # noqa: E402
    classify,
    evaluation_session,
    load_trades,
)
from replay.store import REPLAY_MARKET  # noqa: E402
from screener.detection import (  # noqa: E402
    OUTLIER_MULT,
    TIGHT_MULT,
    detect,
    detection_gate,
    range_3bar_adr,
)
from screener.indicators import adr as _adr  # noqa: E402
from screener.store import Store  # noqa: E402

# The committed v1 figures this run is read against (findings §3, `replay.study`
# last run 2026-08-19). Hard-coded rather than re-derived: the point of the
# comparison is that the *old* numbers are the published ones.
V1_DETECTION_PASSED, V1_TOTAL = 380, 658
V1_CONDITION_COUNTS = {
    "cluster": 171, "catch_up": 47, "base_length": 37, "history": 23,
}

REFERENCE = Path(__file__).resolve().parent.parent / "references" / (
    "trades_bo_gain10smaPct_desc.json"
)


@dataclass
class RecallResult:
    passed: int
    total: int
    passed_ex_continuation: int
    total_ex_continuation: int
    condition_counts: dict[str, int]
    recovered_three_bar_ranges: list[float]


def measure_recall(store: Store, market: str) -> RecallResult:
    """Re-run the funnel's detection stage over every replayable trade.

    Reproduces :func:`replay.funnel._funnel_row`'s detection half exactly — the
    same evaluation session (the last session strictly before entry), the same
    ``detect``, the same ``diagnose_detection`` attribution — without the chain
    the decile stage would need.
    """
    trades = load_trades(REFERENCE)
    classified = classify(trades, store, market=market)
    calendar = store.sessions(market)

    # Continuation tagging: an entry within 5 sessions of a prior entry in the
    # same ticker. Recomputed here off the calendar, as the funnel does.
    index = {s: i for i, s in enumerate(calendar)}
    by_ticker: dict[str, list[date]] = {}
    for c in classified:
        by_ticker.setdefault(c.trade.ticker, []).append(c.trade.entry_date)
    for entries in by_ticker.values():
        entries.sort()

    passed = total = passed_ex = total_ex = 0
    conditions: dict[str, int] = {}
    recovered: list[float] = []
    bars_cache: dict[str, list] = {}
    for c in classified:
        if not c.replayable:
            continue
        ticker = c.trade.ticker
        if ticker not in bars_cache:
            bars_cache[ticker] = store.bars(market, ticker)
        bars = bars_cache[ticker]
        eval_session = evaluation_session(calendar, c.trade.entry_date)

        entries = by_ticker[ticker]
        prior = [e for e in entries if e < c.trade.entry_date]
        distance = None
        if prior and prior[-1] in index and c.trade.entry_date in index:
            distance = index[c.trade.entry_date] - index[prior[-1]]
        continuation = distance is not None and distance <= 5

        total += 1
        if not continuation:
            total_ex += 1
        found = detect(ticker, bars, eval_session) if eval_session else None
        if found is not None:
            passed += 1
            if not continuation:
                passed_ex += 1
            # A trade the old 1.5 cut would have declined: recovered by the guard.
            if found.range_3bar_adr is not None and found.range_3bar_adr > TIGHT_MULT:
                recovered.append(found.range_3bar_adr)
        else:
            cond = diagnose_detection(bars, eval_session) if eval_session else "history"
            conditions[cond] = conditions.get(cond, 0) + 1

    return RecallResult(
        passed=passed,
        total=total,
        passed_ex_continuation=passed_ex,
        total_ex_continuation=total_ex,
        condition_counts=conditions,
        recovered_three_bar_ranges=sorted(recovered),
    )


def far_misses(store: Store, market: str) -> list[float]:
    """The three-bar range of every trade the far-outlier guard still declines.

    The guard's own cost, in his trades: what is left of the 171 `cluster` misses
    once the graded range takes over. Reported so the guard's n is visible rather
    than implied.
    """
    trades = load_trades(REFERENCE)
    classified = classify(trades, store, market=market)
    calendar = store.sessions(market)
    out: list[float] = []
    bars_cache: dict[str, list] = {}
    for c in classified:
        if not c.replayable:
            continue
        eval_session = evaluation_session(calendar, c.trade.entry_date)
        if eval_session is None:
            continue
        ticker = c.trade.ticker
        if ticker not in bars_cache:
            bars_cache[ticker] = store.bars(market, ticker)
        bars = bars_cache[ticker]
        if diagnose_detection(bars, eval_session) != COND_CLUSTER:
            continue
        upto = [b for b in bars if b.session <= eval_session]
        a = _adr(upto)
        if a is None or a <= 0:
            continue
        r3 = range_3bar_adr(
            [b.high for b in upto], [b.low for b in upto], len(upto) - 1,
            a * upto[-1].close,
        )
        if r3 is not None:
            out.append(r3)
    return sorted(out)


@dataclass
class InflationResult:
    sessions: int
    v1_total: int
    v2_total: int
    per_session_deltas: list[int]


def measure_field_inflation(
    store: Store, market: str, sample: int | None
) -> InflationResult:
    """Re-detect each session's *same* gated members and compare to the v1 rows.

    The population cost, in the app's own units: how many more names land on the
    Setups list per night. The decile gate is held fixed — the members and the
    ranks come from the persisted chain — so the whole difference is the
    detector's.
    """
    sessions = sorted(
        s for s, in store._cursor().execute(  # noqa: SLF001 — a side-car, read-only
            "SELECT DISTINCT session FROM detections WHERE market = ? ORDER BY session",
            [market],
        ).fetchall()
    )
    if sample and sample < len(sessions):
        step = len(sessions) / sample
        sessions = [sessions[int(i * step)] for i in range(sample)]

    store = CachingStore.wrap(store)
    v1_total = v2_total = 0
    deltas: list[int] = []
    started = time.time()
    for i, session in enumerate(sessions, start=1):
        members = store.universe(market, session)
        gated = detection_gate(store.ranks(market, session))
        v1 = len(store.detections(market, session))
        v2 = sum(
            1
            for symbol in members
            if symbol in gated
            and detect(symbol, store.bars(market, symbol), session) is not None
        )
        v1_total += v1
        v2_total += v2
        deltas.append(v2 - v1)
        elapsed = time.time() - started
        print(
            f"  [{i}/{len(sessions)}] {session}  v1={v1}  v2={v2}  "
            f"({elapsed / i:.1f}s/session, ETA {(len(sessions) - i) * elapsed / i / 60:.0f}m)",
            file=sys.stderr,
        )
    return InflationResult(len(sessions), v1_total, v2_total, deltas)


def _quantiles(values: list[float]) -> str:
    if not values:
        return "n=0"
    n = len(values)

    def q(p: float) -> float:
        return values[min(n - 1, int(p * n))]

    return (
        f"n={n}  p25 {q(0.25):.2f}  median {q(0.50):.2f}  p75 {q(0.75):.2f}  "
        f"max {values[-1]:.2f}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True)
    ap.add_argument("--market", default=REPLAY_MARKET)
    ap.add_argument("--sessions", type=int, default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    store = Store.open(args.store)
    lines: list[str] = []

    def emit(line: str = "") -> None:
        lines.append(line)
        print(line)

    emit(f"Tightness restructure (#145/#154) — TIGHT_MULT {TIGHT_MULT} gate -> "
         f"OUTLIER_MULT {OUTLIER_MULT} guard")
    emit("=" * 78)
    emit()

    print("measuring detection-stage recall ...", file=sys.stderr)
    r = measure_recall(store, args.market)
    emit("1. Detection-stage recall, 828-trade reference set")
    emit(f"   replayable trades          : {r.total}")
    emit(f"   v1 (hard 1.5 cut)          : {V1_DETECTION_PASSED}/{V1_TOTAL} "
         f"({V1_DETECTION_PASSED / V1_TOTAL:.1%})")
    emit(f"   v2 (far-outlier guard)     : {r.passed}/{r.total} "
         f"({r.passed / r.total:.1%})")
    emit(f"   recovered                  : {r.passed - V1_DETECTION_PASSED} trades")
    emit(f"   ex-continuation            : {r.passed_ex_continuation}/"
         f"{r.total_ex_continuation} "
         f"({r.passed_ex_continuation / r.total_ex_continuation:.1%})")
    emit()
    emit("   Failed condition           v1     v2")
    for cond in ("cluster", "catch_up", "base_length", "history", "adr",
                 "prior_move"):
        v1 = V1_CONDITION_COUNTS.get(cond, 0)
        v2 = r.condition_counts.get(cond, 0)
        if v1 or v2:
            emit(f"     {cond:<22} {v1:>5}  {v2:>5}")
    emit()
    emit("   Three-bar range of the recovered trades (all past the old 1.5 cut):")
    emit(f"     {_quantiles(r.recovered_three_bar_ranges)}")
    emit()

    print("measuring the guard's residual misses ...", file=sys.stderr)
    far = far_misses(store, args.market)
    emit(f"   Trades the guard still declines: {len(far)}")
    emit(f"     three-bar range: {_quantiles(far)}")
    emit()

    print("measuring field inflation ...", file=sys.stderr)
    inf = measure_field_inflation(store, args.market, args.sessions)
    per_v1 = inf.v1_total / inf.sessions
    per_v2 = inf.v2_total / inf.sessions
    emit("2. Field inflation per session (same universe, same decile gate)")
    emit(f"   sessions measured          : {inf.sessions}")
    emit(f"   v1 detections / session    : {per_v1:.1f}")
    emit(f"   v2 detections / session    : {per_v2:.1f}")
    emit(f"   inflation                  : +{per_v2 - per_v1:.1f} names/session "
         f"(+{(per_v2 / per_v1 - 1):.1%})")
    if r.passed > V1_DETECTION_PASSED:
        admitted = (inf.v2_total - inf.v1_total) / inf.sessions
        emit(f"   names admitted per trade recovered, per session: "
         f"{admitted / (r.passed - V1_DETECTION_PASSED):.2f}")
    emit()

    if args.out:
        Path(args.out).write_text("\n".join(lines) + "\n")
        print(f"wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
