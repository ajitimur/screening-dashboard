"""The `Relative move` selection contrast — issue #171's pre-registered study.

§3f (#169) measured the prior move behind 582 of his entries against a
**same-name background**: the same tickers on random ordinary days. That is §3d's
device and it is deliberately weak — a random day is not a setup he passed over,
so no lift computed against it is a precision figure and §9 forbids citing one as
such. What §3f cannot say is what the strength cut-off *costs*, or whether a
`6m`-relative prior move separates his picks from the field he did not enter.

This runs §5b's instrument over that question: **taken detections against
not-taken detections**, no outcome variable anywhere, with the prior-move
quantities added as columns. It is the measurement ADR 0005's second
registration — `Relative move` — has been waiting on, and until it exists none of
that registration's four criteria can fire.

**The verdict reads one column, and only one.** `Relative move` is the
pre-registered variant: the `6m` return relative to
:data:`~screener.source.MARKET_INDEX`, compounded, in ADR units, hit above zero
(:func:`screener.relative_strength.relative_move_adr`). Every other column —
the raw move at `1w`/`6m`/`12m`, the relative move at `1w`/`12m`, and the two
`1w` controls below — is **descriptive and permanently inadmissible**: ADR 0005
registers one variant per candidate, and reading a verdict off whichever column
came back widest is the magnitude-fitting #128 Q2 forbids. They are carried because §3f's own finding
is that QQQ takes about a third of the `6m` move, and a contrast reporting only
the net figure would leave that share invisible. `1w` is here for a third
reason: ADR 0003 refuses the `1w` lookback and §3f gave that refusal its third
line of evidence, all three drawn from his trades alone. A flat `1w` gap over the
field he passed over is the fourth line, and the first with a comparison group
under it.

They are passed to :func:`replay.contrast.contrast_dimensions` as ``readers``
rather than added to :data:`replay.contrast.CANDIDATES`, so the registered list
stays an honest record of what was actually registered.

**The `1w` columns are measured twice, and the second one is the control.** Every
column above is read at the detection's own session, which for a *taken*
detection is the session he entered on — so that day's close, the day he bought
it, sits inside the window. Over six months one session is nothing; over a week
it is a fifth of the window, and the taken group is by construction the names he
bought that day. So `1w` is also measured through the session **strictly before**
the detection — §3f's own convention, adopted there because at a 09:42 median
entry the entry day's return is not on screen at the click. The pair separates a
week he selected on from the day he traded on, and reporting only the first would
have put a number on the record that ADR 0003's `1w` line cannot carry.

**Two fields, and the first one is the control.**

- **v1** — over the store's **persisted** detections, which all carry
  ``detector_version = 1``. This is the field findings §5b was measured on, and
  it runs first as the harness check: if it does not reproduce §5b's published
  69 / 14,354 and its seven gaps, nothing below it can be trusted. §5d's result
  is believable because its harness did exactly this, and this one inherits the
  requirement rather than re-arguing it.
- **the live detector** — detections **recomputed** with whatever
  :data:`screener.detection.DETECTOR_VERSION` currently stamps. ADR 0005 requires
  the contrast to be measured under the detector the dimension would ship
  against, because an ordinal position read off a v1 table would rank a
  v3-measured dimension among v1-measured ones — the field-change-versus-rubric-
  change confound the paired re-run (#136) exists to prevent.

Both run over the **same 505 sessions**, the ones the store holds detections for,
so the detector is the only thing that moves between them.

**Why the store is read and not rebuilt.** ``data/replay.duckdb`` cannot be
re-run in place: its detections are detector v1 over 505 sessions and a full
chain re-run raises ``SessionExistsError``. #171 offered three routes and this
takes §5d's — read the persisted detections for the control, recompute the live
field in memory, write nothing back. Appending the recomputed rows would leave
the store holding two detectors under one ``(market, session)`` key and would
destroy the v1 check on the next run. :class:`~screener.store.Store` migrates on
open and so cannot be handed a read-only connection; run this against a **working
copy** of the store, which is belt and braces on the same guarantee.

**The ranks are the chain's, not the store's** (#141/#164), and the three
read-only stages that make that true are :mod:`replay.candidate_field`, shared
with the `RS line` study — see that module for why they are not repeated here.

**Criterion 2 needs no second measurement here.** `RS line`'s redundancy partner
was price-at-a-new-high-over-base, which had to be computed. This dimension's
partner is ``Prior move``, which is ``True`` on every detection by construction —
so disagreement with it is exactly ``1 − hit rate``, read on the not-taken group,
and it is reported from the contrast rather than recomputed. Which also means
**criteria 1 and 2 are one threshold read from two sides**, and the #171 run put
that one number on it; see :func:`verdict`.

Run as ``python scripts/relative_move_contrast.py --store <copy of replay.duckdb>``.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

_BACKEND = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(_BACKEND))

from replay.caching_store import CachingStore  # noqa: E402
from replay.candidate_field import (  # noqa: E402
    live_detections,
    measured_sessions,
    session_ranks,
)
from replay.contrast import (  # noqa: E402
    CONTRAST_DIMENSIONS,
    contrast_dimensions,
)
from replay.field import (  # noqa: E402
    ScoredDetection,
    build_field,
    session_relative_moves,
    session_rs_lines,
)
from replay.reference import (  # noqa: E402
    DEFAULT_REFERENCE_JSON,
    classify,
    load_trades,
)
from screener.detection import DETECTOR_VERSION  # noqa: E402
from screener.relative_strength import (  # noqa: E402
    RELATIVE_MOVE_LOOKBACK,
    move_adr,
    relative_move_adr,
    relative_move_hit,
)
from screener.source import MARKET_INDEX  # noqa: E402
from screener.store import Store  # noqa: E402

MARKET = "US"

# The dimension the verdict is read off. Named from the registration rather than
# spelled again, so a column heading and a criterion can never drift apart.
REGISTERED = "Relative move"

# The descriptive columns, and every one of them is inadmissible by construction
# (ADR 0005's one-variant clause). `rel 6m` is absent because that *is* the
# registered dimension — listing it twice would invite reading the pair as a
# sweep with a winner.
DESCRIPTIVE_WINDOWS: tuple[str, ...] = ("1w", "6m", "12m")

# The window whose reading the entry session itself can move, and which is
# therefore measured a second time through the prior session. One column heading
# owns the suffix so the table, the distributions and the write-up cannot drift.
PRIOR_SESSION_WINDOW = "1w"
PRIOR_SESSION_SUFFIX = " (t-1)"


@dataclass(frozen=True)
class MoveValues:
    """The descriptive prior-move quantities for one detection, all in ADR units.

    Keyed by the **column heading** the table prints — ``"raw 6m"``,
    ``"rel 1w (t-1)"`` — built by :func:`column_heading` and by nothing else, so
    the readers, the distributions and the printed table cannot key one thing
    three ways.

    A ``None`` is **absent** — the name had not listed that far back, or has no
    ADR — never zero, which is a real value sitting exactly on the cut.
    """

    by_column: dict[str, float | None]


def prior_session(bars, session: date) -> date | None:
    """The last bar the name printed **strictly before** ``session``.

    §3f's evaluation session, and its reason: at a 09:42 median entry the entry
    day's own return is not on screen at the click. Here it does a second job —
    the taken group is the names he entered that session, so the detection day's
    close is the one bar a `1w` window cannot afford to have in it.

    ``None`` when the name has no earlier bar, which scores the column absent
    under the same never-carried-forward rule as every other missing leg.
    """
    sessions = [b.session for b in bars]
    idx = bisect_left(sessions, session) - 1
    return sessions[idx] if idx >= 0 else None


def column_heading(leg: str, window: str, *, at_prior_session: bool = False) -> str:
    """The one place a descriptive column's name is spelled.

    Three sites need it — the readers, the value distributions and the printed
    table — and a column whose heading is composed independently in each is a
    column that can go missing from one of them silently.
    """
    return f"{leg} {window}" + (PRIOR_SESSION_SUFFIX if at_prior_session else "")


def descriptive_legs() -> list[tuple[str, str, bool]]:
    """Every descriptive column as ``(leg, window, at_prior_session)``, in table
    order.

    ``rel`` omits :data:`RELATIVE_MOVE_LOOKBACK` because that *is* the registered
    dimension — listing it twice would invite reading the pair as a sweep with a
    winner. Both legs carry the `1w` control.
    """
    out: list[tuple[str, str, bool]] = []
    for leg in ("raw", "rel"):
        for window in DESCRIPTIVE_WINDOWS:
            if leg == "rel" and window == RELATIVE_MOVE_LOOKBACK:
                continue
            out.append((leg, window, False))
        out.append((leg, PRIOR_SESSION_WINDOW, True))
    return out


def column_headings() -> list[str]:
    """The descriptive column headings, in table order."""
    return [
        column_heading(leg, window, at_prior_session=at_prior)
        for leg, window, at_prior in descriptive_legs()
    ]


def move_values(bars, index_bars, as_of: date) -> MoveValues:
    """Every descriptive column for one detection, from the same two series.

    The registered dimension is **not** computed here: it rides the field member,
    put there by :func:`replay.field.session_relative_moves`, so that the number
    the contrast reads is the same number a shipped breakdown row would carry.
    """
    before = prior_session(bars, as_of)
    by_column: dict[str, float | None] = {}
    for leg, window, at_prior in descriptive_legs():
        when = before if at_prior else as_of
        if when is None:
            value = None
        elif leg == "raw":
            value = move_adr(bars, when, lookback=window)
        else:
            value = relative_move_adr(bars, index_bars, when, lookback=window)
        by_column[column_heading(leg, window, at_prior_session=at_prior)] = value
    return MoveValues(by_column=by_column)


def descriptive_columns(
    values: dict[tuple[str, date], MoveValues],
) -> tuple[tuple[tuple[str, int], ...], dict[str, Callable[[ScoredDetection], bool]]]:
    """The descriptive columns as ``(dimensions, readers)`` for the contrast.

    Every column takes the **same cut as the registered dimension** — above zero,
    in ADR units. Not because zero is optimal anywhere, but because a per-column
    cut is a free parameter per column, and six of those is a sweep. Zero means
    "it went up" on the raw columns and "it outran the index" on the relative
    ones, which is the only reading that needs no defending.
    """
    names: list[tuple[str, int]] = []
    readers: dict[str, Callable[[ScoredDetection], bool]] = {}

    def _reader(column: str) -> Callable[[ScoredDetection], bool]:
        def read(d: ScoredDetection) -> bool:
            return relative_move_hit(
                values[(d.symbol, d.detection.session)].by_column[column]
            )

        return read

    for column in column_headings():
        names.append((column, 0))
        readers[column] = _reader(column)
    return tuple(names), readers


# -- the run ------------------------------------------------------------------


@dataclass
class Groups:
    taken: list
    not_taken: list
    values: dict[tuple[str, date], MoveValues]
    n_sessions: int
    n_detections: int


def collect(store, market, sessions, entries, *, live_detector: bool) -> Groups:
    """Split every measured session's field into the taken and not-taken groups.

    ``live_detector`` chooses the field: the store's persisted v1 rows, or a fresh
    pass with the live detector. A quiet session (no entry) contributes to neither
    group, exactly as :func:`replay.contrast.build_contrast` does — which is why
    the descriptive values are computed only for the two groups and not for the
    whole field.
    """
    taken, not_taken, total = [], [], 0
    values: dict[tuple[str, date], MoveValues] = {}
    index_bars = store.bars(market, MARKET_INDEX[market])
    label = f"v{DETECTOR_VERSION}" if live_detector else "v1"
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
            relative_move_of=session_relative_moves(store, market, dets),
        )
        in_groups = [d for d in scored if d.taken or d.not_taken]
        for d in in_groups:
            values[(d.symbol, d.detection.session)] = move_values(
                store.bars(market, d.symbol), index_bars, d.detection.session
            )
        taken.extend(d for d in in_groups if d.taken)
        not_taken.extend(d for d in in_groups if d.not_taken)

        if i % 25 == 0 or i == len(sessions):
            rate = (time.time() - t0) / i
            print(
                f"  [{label}] {i}/{len(sessions)} {session}  dets={total}  "
                f"taken={len(taken)} not_taken={len(not_taken)}  "
                f"{rate:.2f}s/session eta {(len(sessions) - i) * rate / 60:.1f}m",
                flush=True,
            )
    return Groups(taken, not_taken, values, len(sessions), total)


def _distribution(xs: list[float]) -> dict | None:
    """Median and quartiles of a value column, for the groups' own record.

    The criteria read hit rates and nothing else — this is here so the verdict can
    be read *against* §3f's published distribution rather than only against its
    own sign, and so a gap driven by a handful of extreme names is visible as one.
    """
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    q = statistics.quantiles(xs, n=100) if len(xs) >= 2 else [xs[0]] * 99
    return {
        "n": len(xs),
        "p25": q[24],
        "median": statistics.median(xs),
        "p75": q[74],
    }


def report(label: str, groups: Groups) -> dict:
    """The contrast table for one field, with the descriptive columns appended."""
    names, readers = descriptive_columns(groups.values)
    contrasts = contrast_dimensions(
        groups.taken,
        groups.not_taken,
        dimensions=CONTRAST_DIMENSIONS + names,
        readers=readers,
    )
    print(f"\n=== {label} — {groups.n_sessions} sessions, "
          f"{groups.n_detections} detections ===")
    print(f"taken: {len(groups.taken)}   not-taken: {len(groups.not_taken)}")
    print(f"{'dimension':<16}{'w':>3}  {'taken':>8} {'not-taken':>10} "
          f"{'delta':>9} {'pooled sd':>10}")
    rows = []
    for c in contrasts:
        delta = (c.taken_hit_rate - c.not_taken_hit_rate) * 100
        mark = "  <- registered" if c.dimension == REGISTERED else ""
        print(f"{c.dimension:<16}x{c.weight}  {c.taken_hit_rate:>7.1%} "
              f"{c.not_taken_hit_rate:>10.1%} {delta:>+8.1f}pp "
              f"{c.combined_spread:>10.3f}{mark}")
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

    values = {}
    for column in column_headings():
        values[column] = {
            group: _distribution([
                groups.values[(d.symbol, d.detection.session)].by_column[column]
                for d in rows_of
            ])
            for group, rows_of in (
                ("taken", groups.taken), ("not_taken", groups.not_taken)
            )
        }
    values[REGISTERED] = {
        group: _distribution([d.relative_move for d in rows_of])
        for group, rows_of in (
            ("taken", groups.taken), ("not_taken", groups.not_taken)
        )
    }

    return {
        "label": label, "sessions": groups.n_sessions,
        "detections": groups.n_detections,
        "n_taken": len(groups.taken), "n_not_taken": len(groups.not_taken),
        "dimensions": rows,
        "value_distributions": values,
    }


# The bounds ADR 0005 fixed for the registered dimension, before any of this was
# visible. Criterion 2's partner is ``Prior move``, ``True`` on every detection,
# so disagreement with it is exactly ``1 − hit rate`` on the not-taken group.
# **Criteria 1 and 2 are therefore one threshold read from two sides**: criterion
# 1's ~85% ceiling and criterion 2's ~15% disagreement floor are the same cut on
# the same number, and whichever way it rounds, both go with it.
HIT_RATE_FLOOR = 0.15
HIT_RATE_CEILING = 0.85

# The three outcomes this script can return. ``ON_THE_BOUND`` is the one ADR 0005
# did not anticipate, and it exists because the run produced it: see
# :func:`verdict`.
SHIP = "ship"
DO_NOT_SHIP = "do_not_ship"
ON_THE_BOUND = "on_the_bound"


def _standard_error(p: float, n: int) -> float:
    """Sampling error of a proportion. Zero on an empty group."""
    return (p * (1 - p) / n) ** 0.5 if n else 0.0


def verdict(block: dict) -> dict:
    """The four pre-registered criteria, evaluated against the registered column.

    Written to fire mechanically: nothing here chooses which column to read, and
    the thresholds are the ADR's, not this script's. All four are evaluated and
    every one that fires is recorded, rather than stopping at the first — for
    `RS line`, criterion 4 fired and criterion 2 stood ready behind it, and the
    fact that a second one would also have refused it was worth having.

    **The third outcome, and why it is not a fifth criterion.** ADR 0005 promises
    pass or fail on one variant, and this function returned exactly that until the
    #171 run put the deciding number 0.06pp inside its own bound — 0.29 standard
    errors, on a threshold the ADR records as "a judgement, not a measurement…
    the one magnitude in this design with nothing behind it". So a hit rate within
    **one standard error** of the ceiling or the floor returns
    :data:`ON_THE_BOUND` rather than a verdict.

    Three things keep that honest. It **moves no threshold**: the ADR's numbers
    are untouched and the criteria still fire exactly where they did. It is
    **symmetric**: it refuses a pass and a fail alike, so it cannot be the
    mechanism by which a preferred answer arrives. And it is **stated as
    post-hoc**, here and in the ADR, because it is — it was added after the
    measurement landed on the bound, and a rule written after the numbers is
    evidence about the threshold rather than about the dimension.
    """
    row = next(r for r in block["dimensions"] if r["dimension"] == REGISTERED)
    delta = row["delta_pp"]
    not_taken = row["not_taken_hit_rate"]
    se = _standard_error(not_taken, row["not_taken_n"])

    fired = []
    if delta > 0 and HIT_RATE_FLOOR <= not_taken <= HIT_RATE_CEILING:
        fired.append((1, "delta positive and the not-taken hit rate inside both "
                         "bounds — ship, at the weight its ordinal position implies"))
    if delta > 0 and not_taken > HIT_RATE_CEILING:
        fired.append((2, "not-taken hit rate above the ceiling — the constant in a "
                         "new costume; disagreement with `Prior move` is under the "
                         "floor"))
    if not_taken < HIT_RATE_FLOOR:
        fired.append((3, "not-taken hit rate under the floor — it discriminates "
                         "over a sliver of the field"))
    if delta <= 0:
        fired.append((4, "delta negative — do not ship, and record it"))

    on_the_bound = (
        se > 0
        and min(abs(not_taken - HIT_RATE_CEILING), abs(not_taken - HIT_RATE_FLOOR))
        <= se
    )
    if on_the_bound:
        outcome = ON_THE_BOUND
    elif [n for n, _ in fired] == [1]:
        outcome = SHIP
    else:
        outcome = DO_NOT_SHIP

    return {
        "dimension": REGISTERED,
        "delta_pp": delta,
        "delta_standard_error_pp": 100 * (
            _standard_error(row["taken_hit_rate"], row["taken_n"]) ** 2 + se ** 2
        ) ** 0.5,
        # How far the deciding number sits from the bound that decides it, in
        # points and in its own sampling error. A verdict turning on a tenth of a
        # point against a threshold ADR 0005 itself calls a judgement is a fact
        # about the threshold, and it belongs in the machine-readable record and
        # not only in the prose.
        "margin_to_ceiling_pp": (HIT_RATE_CEILING - not_taken) * 100,
        "margin_to_ceiling_se": (HIT_RATE_CEILING - not_taken) / se if se else None,
        "not_taken_hit_rate_standard_error_pp": se * 100,
        "taken_hit_rate": row["taken_hit_rate"],
        "not_taken_hit_rate": not_taken,
        "disagreement_with_prior_move": 1.0 - not_taken,
        "pooled_spread": row["pooled_spread"],
        "criteria_fired": [{"criterion": n, "reason": why} for n, why in fired],
        "outcome": outcome,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True)
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON))
    parser.add_argument("--market", default=MARKET)
    parser.add_argument("--out", default="references/relative_move_contrast.json")
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

    # The live stamp, never a literal: #149 bumped the detector to v3 after ADR
    # 0005 was drafted, so a document that says "v2" is already one field behind.
    live_label = f"detector v{DETECTOR_VERSION} (live, recomputed)"
    results = {}
    for label, live in (("detector v1 (persisted)", False), (live_label, True)):
        groups = collect(store, market, sessions, entries, live_detector=live)
        block = report(label, groups)
        block["verdict"] = verdict(block)
        v = block["verdict"]
        print(f"\n{REGISTERED} under {label}: delta {v['delta_pp']:+.1f}pp, "
              f"not-taken hit rate {v['not_taken_hit_rate']:.1%}, "
              f"disagreement with `Prior move` "
              f"{v['disagreement_with_prior_move']:.1%}")
        for fired in v["criteria_fired"]:
            print(f"  criterion {fired['criterion']} fires: {fired['reason']}")
        if v["outcome"] == ON_THE_BOUND:
            print(f"  the deciding number sits "
                  f"{abs(v['margin_to_ceiling_se']):.2f} standard errors from its "
                  f"own bound — no verdict")
        print(f"  -> {v['outcome'].replace('_', ' ').upper()}")
        results["v1" if not live else f"v{DETECTOR_VERSION}"] = block

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nwrote {out}")
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
