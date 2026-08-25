"""The `RS line` selection contrast — issue #160's pre-registered study.

Measures whether an **index-relative** dimension earns the rubric slot
``Prior move`` cannot: that dimension is a **constant dimension**, 100.0% in both
the taken and the not-taken group, pooled spread 0.000, so it occupies a point of
a nine-point rubric and can never move the sort.

`RS = adj_close(name) / adj_close(index)`, hit when ``RS_today >=
RS_at_base_start`` over the detection's own base
(:mod:`screener.relative_strength`). **One variant, pass or fail** — selecting
among candidate booleans by whichever gap is largest is magnitude-fitting, which
#128 Q2 forbids.

Two contrasts are run, and the reason there are two is the correction on #160:

- **v1** — over the store's **persisted** detections, which all carry
  ``detector_version = 1``. This is the field findings §5b was measured on, and
  it is run first as a **harness check**: if it does not reproduce §5b's published
  69 / 14,354 and its seven gaps, nothing downstream can be trusted.
- **the live detector** — over detections **recomputed** with whatever
  :data:`screener.detection.DETECTOR_VERSION` currently stamps. §5b's table
  describes a field the detector no longer produces, so a weight read off its
  ordinal positions would slot a newly-measured dimension into a v1-measured
  ordering — the field-change-versus-rubric-change confound the paired re-run
  (#136) exists to prevent.

  #160 calls this "v2", for the graded-tightness detector #154 shipped. It is
  **v3**: #149 admitted ``12m`` to :data:`~screener.detection.DETECTION_LOOKBACKS`
  after the issue was written, widening the gate from 19.3% to 21.9% of universe.
  Both field-widening changes are therefore in the live field, and the label is
  read off the constant rather than written down, so the next bump cannot leave
  this script quietly mislabelling its own output.

**Both contrasts run over the same 505 sessions**, the ones the store holds
detections for, so the *only* thing that differs between them is the detector.
The universe is read from the store as persisted; the ranks are recomputed in
memory with :func:`screener.ranks.rank_table`, which is what the app's own field
replay does since #141 (``Store.append_ranks`` prunes outside its retention
window, so the persisted table cannot serve the early sessions).

**Nothing is written back.** The v2 pass recomputes detections and *does not*
persist them: appending them into ``replay.duckdb`` would leave the store holding
two detectors' rows under one ``(market, session)`` key, and would destroy the v1
harness check on the next run. :class:`~screener.store.Store` runs a schema
migration on open, so it cannot be handed a read-only DuckDB connection; run this
against a **working copy** of the store instead, which is belt and braces on the
same guarantee.

**The redundancy check.** The contrast is not the whole verdict. #160's criterion
2 asks how often ``RS line`` and *price at a new high over the base* disagree; a
dimension that merely restates the break test earns no slot however large its gap.
That rate is reported beside the contrast.

**A known contamination, measured and carried.** ``replay.chain.synthesize_instruments``
tags every symbol with bars as a candidate, so ``^IXIC`` — the benchmark itself —
sits in the replay store's ``universe`` and ``ranks``. It reaches neither
comparison group: it has 0 rows in ``detections`` and clears the 0.90 detection
gate on 0 of 505 ranked sessions (global max 0.8246). The residual effect is on
denominators only, ~0.1% per session. Fixed separately in #162; rebuilding 4.7M
rank rows here would run the study against a *different* field than §5b's,
breaking the comparability the whole exercise depends on.

**The field reconstruction is shared with the other candidate study.**
:mod:`replay.candidate_field` holds the three read-only stages both need — the
measured sessions, the in-memory rank recomputation the retention window forces
(#141/#164), and the live-detector pass that persists nothing. Two copies of that
workaround is one too many: a correction would have to land twice, and the run
that missed the second copy would still print a table.

Run as ``python scripts/rs_line_contrast.py --store data/replay.duckdb``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from replay.candidate_field import (  # noqa: E402
    live_detections,
    measured_sessions,
    session_ranks,
)
from replay.contrast import (  # noqa: E402
    CONTRAST_DIMENSIONS,
    contrast_dimensions,
)
from replay.caching_store import CachingStore  # noqa: E402
from replay.field import build_field, session_rs_lines  # noqa: E402
from replay.reference import (  # noqa: E402
    DEFAULT_REFERENCE_JSON,
    classify,
    load_trades,
)
from screener.detection import DETECTOR_VERSION  # noqa: E402
from screener.relative_strength import base_start_session  # noqa: E402
from screener.store import Store  # noqa: E402

MARKET = "US"


# -- the redundancy check -----------------------------------------------------


def price_new_high_over_base(det, bars) -> bool:
    """Whether the name's close is at a new high over its own base.

    #160's criterion 2 redundancy check: the price analogue of the RS line, on
    the *name alone* with no benchmark. A candidate dimension that agrees with
    this almost everywhere is restating the break test — an event the app already
    reports — rather than adding an index-relative reading, and earns no slot
    however large its selection gap.

    Read on ``adj_close`` for the same reason the RS line is: an unadjusted series
    steps at every split. ``False`` when the base reaches past the stored series,
    matching the RS line's never-carried-forward rule so the two are compared over
    identical rows.
    """
    start = base_start_session(bars, det.session, base_len=det.base_len)
    if start is None:
        return False
    over_base = [b for b in bars if start <= b.session <= det.session]
    if not over_base:
        return False
    return over_base[-1].adj_close >= max(b.adj_close for b in over_base)


# -- the run ------------------------------------------------------------------


@dataclass
class Groups:
    taken: list
    not_taken: list
    n_sessions: int
    n_detections: int


def collect(store, market, sessions, entries, *, live_detector: bool) -> Groups:
    """Split every measured session's field into the taken and not-taken groups.

    ``live_detector`` chooses the field: the store's persisted v1 rows, or a fresh
    pass with the live detector. A quiet session (no entry) contributes to neither
    group, exactly as :func:`replay.contrast.build_contrast` does.
    """
    taken, not_taken, total = [], [], 0
    t0 = time.time()
    for i, session in enumerate(sessions, start=1):
        _members, ranks = session_ranks(store, market, session)
        dets = (
            live_detections(store, market, session, ranks)
            if live_detector
            else store.detections(market, session)
        )
        total += len(dets)

        entered = entries.get(session, set())
        scored = build_field(
            dets, ranks, entered=entered, any_entry=bool(entered),
            rs_line_of=session_rs_lines(store, market, dets),
        )
        taken.extend(d for d in scored if d.taken)
        not_taken.extend(d for d in scored if d.not_taken)

        if i % 25 == 0 or i == len(sessions):
            rate = (time.time() - t0) / i
            print(
                f"  [{'v2' if live_detector else 'v1'}] {i}/{len(sessions)} "
                f"{session}  dets={total}  taken={len(taken)} "
                f"not_taken={len(not_taken)}  {rate:.2f}s/session "
                f"eta {(len(sessions) - i) * rate / 60:.1f}m",
                flush=True,
            )
    return Groups(taken, not_taken, len(sessions), total)


def disagreement(store, market, groups: Groups) -> dict:
    """How often ``RS line`` and price-at-a-new-high-over-base differ.

    Reported over the **pooled** taken + not-taken population, and over each group
    separately — a rate that is low overall but concentrated in one group would
    mean something different from one spread evenly.
    """
    out = {}
    for label, rows in (
        ("pooled", groups.taken + groups.not_taken),
        ("taken", groups.taken),
        ("not_taken", groups.not_taken),
    ):
        n = disagree = rs_only = px_only = 0
        for sd in rows:
            bars = store.bars(market, sd.symbol)
            px = price_new_high_over_base(sd.detection, bars)
            n += 1
            if sd.rs_line != px:
                disagree += 1
                if sd.rs_line:
                    rs_only += 1
                else:
                    px_only += 1
        out[label] = {
            "n": n,
            "disagreements": disagree,
            "rate": disagree / n if n else 0.0,
            "rs_line_only": rs_only,
            "price_new_high_only": px_only,
        }
    return out


def report(label: str, groups: Groups) -> dict:
    contrasts = contrast_dimensions(
        groups.taken, groups.not_taken, dimensions=CONTRAST_DIMENSIONS
    )
    print(f"\n=== {label} — {groups.n_sessions} sessions, "
          f"{groups.n_detections} detections ===")
    print(f"taken: {len(groups.taken)}   not-taken: {len(groups.not_taken)}")
    print(f"{'dimension':<14}{'w':>3}  {'taken':>8} {'not-taken':>10} "
          f"{'delta':>9} {'pooled sd':>10}")
    rows = []
    for c in contrasts:
        delta = (c.taken_hit_rate - c.not_taken_hit_rate) * 100
        print(f"{c.dimension:<14}x{c.weight}  {c.taken_hit_rate:>7.1%} "
              f"{c.not_taken_hit_rate:>10.1%} {delta:>+8.1f}pp "
              f"{c.combined_spread:>10.3f}")
        rows.append({
            "dimension": c.dimension, "weight": c.weight,
            "taken_n": c.taken_n, "taken_hit_rate": c.taken_hit_rate,
            "not_taken_n": c.not_taken_n,
            "not_taken_hit_rate": c.not_taken_hit_rate,
            "delta_pp": delta, "pooled_spread": c.combined_spread,
            "taken_spread": c.taken_spread,
            "not_taken_spread": c.not_taken_spread,
            "untestable_within_executed": c.untestable_within_executed,
            "testability_restored": c.testability_restored,
        })
    return {
        "label": label, "sessions": groups.n_sessions,
        "detections": groups.n_detections,
        "n_taken": len(groups.taken), "n_not_taken": len(groups.not_taken),
        "dimensions": rows,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True)
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON))
    parser.add_argument("--market", default=MARKET)
    parser.add_argument("--out", default="references/rs_line_contrast.json")
    parser.add_argument("--limit", type=int, default=None,
                        help="first N sessions only — a smoke run, never a result")
    args = parser.parse_args(argv)

    store = CachingStore.wrap(Store.open(args.store))
    market = args.market

    trades = load_trades(args.reference)
    classified = classify(trades, store, market=market)
    replayable = [c.trade for c in classified if c.replayable]
    entries: dict[date, set[str]] = defaultdict(set)
    for t in replayable:
        entries[t.entry_date].add(t.ticker)
    print(f"trades: {len(trades)}  replayable: {len(replayable)}  "
          f"entry sessions: {len(entries)}")

    sessions = measured_sessions(store, market)
    if args.limit:
        sessions = sessions[: args.limit]
    print(f"measured sessions: {len(sessions)}  "
          f"{sessions[0]} -> {sessions[-1]}  live detector v{DETECTOR_VERSION}")

    # The live stamp, never a literal: #149 bumped the detector to v3 *after*
    # #160 was written, so an issue that says "v2" is already one field behind.
    live_label = f"detector v{DETECTOR_VERSION} (live, recomputed)"
    results = {}
    for label, live in (("detector v1 (persisted)", False), (live_label, True)):
        groups = collect(store, market, sessions, entries, live_detector=live)
        block = report(label, groups)
        block["disagreement"] = disagreement(store, market, groups)
        d = block["disagreement"]["pooled"]
        print(f"\nRS line vs price-at-new-high-over-base — pooled disagreement: "
              f"{d['rate']:.1%} ({d['disagreements']}/{d['n']}; "
              f"RS-only {d['rs_line_only']}, price-only {d['price_new_high_only']})")
        results["v1" if not live else f"v{DETECTOR_VERSION}"] = block

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {out}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
