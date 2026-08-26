"""Which gate reverses the rubric's edge inside the stateless field? (#211)

#198 ran both markets end to end, then checked the six anchors against the run's
own field. Five settle. ``in_field`` does not: it flips the sign of findings §4b's
gap, from the committed **+1.95pp** to **−5.01pp**, and a sign flip is the one
outcome the anchor table refuses to let a written cause waive
(``references/backtest_anchor_divergence.md``).

#198 isolated three suspects and cleared all three. The **bars**: of the 496 trades
both stores can measure, all 496 carry bit-identical geometry. The **detector**:
recall reproduces at 421/503 = 83.70% against the committed 83.69%. The
**population**: hold the trade list fixed at the same 503 names, run the same grid
over ``replay.duckdb`` under the app's universe, and the gap returns **+1.86** —
the same sign as the pin and within a hair of it.

What is left is the field. The run's field is built from the contract's stateless
universe (:mod:`backtest.universe`), which differs from the app's by **more than one
thing at a time**, and a compound explanation is not an explanation. This module
takes the compound apart.

**The direction the isolation runs.** #198's third measurement moves *towards* the
app — a different store, a different universe. This module moves the other way and
stays inside the run's own field: one store (``backtest.duckdb``), one population
(the same 503 replayable trades), one detector, one window. The only thing that
moves between cells is **which gates build the universe**, one gate at a time. A
cell read against the baseline therefore differs from it by exactly one gate, which
is what "attribute it to a gate rather than to the universe" requires.

**Four gates, not three.** The divergence page names three differences from the
app's universe — the ADR20 floor, the ADTV floor and the dropped hysteresis. There
is a fourth, and it is the one the app has no counterpart for at all: the **trend
gate**, ``close > SMA50`` (:func:`backtest.universe.passes_trend_gate`). The app's
universe is liquidity, instrument type, listing age and density; it has neither a
trend gate nor a volatility gate. So the trend gate is a variant here like the
others, because a difference nobody listed is exactly the kind that ends up
attributed to "the universe".

**Dropping a gate needs a superset, so membership is rebuilt rather than read.**
:func:`replay.gate_sweep.build_sweep_sessions` reads membership off the store's
persisted ``universe`` rows, and those rows are the *intersection* of every gate.
Adding a gate to them is a filter; **dropping** one admits names the run never
stored, so this module recomputes membership from the candidate bars instead.

That reconstruction is the load-bearing claim here, so it is checked rather than
trusted, in two independent ways:

- :func:`members_at` under the full gate set reproduces the store's own universe
  rows **exactly** — same count, no extras, no omissions — on every measured
  session (:func:`verify_reconstruction`, which :func:`run_isolation` stops on).
- the gate predicates are pinned against :mod:`backtest.universe`'s own ``passes_*``
  functions in the seam tests, over the same bars, so this module cannot drift from
  the classifier it is standing in for.

**The arithmetic is the classifier's, not an approximation of it.** Each window
statistic is summed over its own slice, oldest bar first, exactly as
:func:`screener.indicators.adr` and :func:`screener.indicators.sma` do — not
differenced out of a running prefix sum, which would round differently and could
move a name sitting exactly on a floor. Speed comes from computing each gate
**once** per candidate and session rather than once per variant: the three
predicates do not depend on which variant is being measured, so
:func:`gate_flags_by_session` evaluates them in a single pass and every variant is
then a boolean ``and`` over the same flags. That is also what makes "one variable
moves" structural rather than merely intended — no variant can differ from another
by a recomputation.

**This module moves no constant.** Every gate here is evaluated at the contract's
committed value; the variants differ only in which gates are *applied at all*.
Restoring the sign by loosening a floor is explicitly not on the table (#211, ADR
0002's evidence rule) — if a constant would have to move, that is the finding, and
it is reported as one.

**Read-only.** Membership is recomputed in memory and the ranks with it; nothing is
written back to the store, and no live constant is assigned.
"""

from __future__ import annotations

import argparse
import bisect
import json
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Mapping, Sequence

from screener.bars import Bar
from screener.detection import detect, detection_gate
from screener.indicators import ADR_WINDOW
from screener.ranks import rank_table
from screener.store import Store
from screener.universe import LIQUIDITY_WINDOW, is_common_stock

from replay.caching_store import CachingStore
from replay.discrimination_grid import (
    DETECTORS,
    DISCRIMINATION_STARS,
    FIELD_SOURCES,
    PUBLISHED_RUBRIC,
    _cell_fields,
    build_grid,
    sessions_with_stored_ranks,
)
from replay.gate_sweep import SweepSession, gate_membership
from replay.placement import field_match
from replay.reference import (
    DEFAULT_REFERENCE_JSON,
    ExecutedTrade,
    classify as classify_trades,
    evaluation_session,
    load_trades,
)

from .contract import DEFAULT_CONTRACT, UNIVERSE_LIQUIDITY_FLOOR_KEY, RunContract
from .universe import ADR_FLOOR, TREND_WINDOW

# The window the gate-dependent anchors were measured over, and the burn-in they
# were measured with — the reference study's own window, restated here so a re-run
# lands on #198's denominators rather than on a superset of them
# (``backtest_anchor_divergence.md``, "The gate-dependent anchors").
WINDOW_START = date(2019, 4, 1)
WINDOW_END = date(2022, 12, 30)
WINDOW_BURN_IN = 126

# The market the reference set is traded on. IDX carries no executed trades, so the
# anchor — and therefore this isolation — is a US measurement, and the contract's
# IDX-only Rp 100 price trim never applies.
ISOLATION_MARKET = "US"

# The cell the anchor is quoted at: the live detector over the whole field
# (``backtest_field_anchors.json``, ``detector_version: 3``, ``field: "whole"``).
ANCHOR_DETECTOR = 3
ANCHOR_FIELD = "whole"


# -- the gates, as a set that can have one member removed ---------------------

# The three gates :mod:`backtest.universe` intersects on US, named so a variant can
# drop exactly one.
TREND, ADR, LIQUIDITY = "trend", "adr", "liquidity"
ALL_GATES = frozenset({TREND, ADR, LIQUIDITY})


@dataclass(frozen=True)
class GateVariant:
    """One universe rule: the run's gates, minus at most one of them.

    ``dropped`` is the whole point — a variant that drops nothing is the run's own
    field and is the baseline every other cell is read against. Because exactly one
    gate separates any variant from that baseline, a difference between them
    attributes to that gate and to nothing else.
    """

    name: str
    gates: frozenset[str]
    note: str

    @property
    def dropped(self) -> frozenset[str]:
        return ALL_GATES - self.gates


# The baseline first, then one variant per gate. Each note says what the app's
# universe does with the same gate, because the divergence being explained is
# against the app's field.
VARIANTS: tuple[GateVariant, ...] = (
    GateVariant(
        "all-three",
        ALL_GATES,
        "the run's own field — reproduces the committed -5.01pp",
    ),
    GateVariant(
        "no-adr",
        ALL_GATES - {ADR},
        "drops the 3.5% ADR20 floor, which the app's universe does not have",
    ),
    GateVariant(
        "no-trend",
        ALL_GATES - {TREND},
        "drops close > SMA50, which the app's universe does not have",
    ),
    GateVariant(
        "no-liquidity",
        ALL_GATES - {LIQUIDITY},
        "drops the $10M ADTV floor, which the app sets at $20M instead",
    ),
    # The one two-gate cell, and it is here because the single drops above do not
    # answer the question: none of them restores the sign, so "which gate" has no
    # single-gate answer and the next thing to ask is whether *any* gate set does.
    # This is the app's shape reached from inside the run's own field — liquidity
    # alone, without the two gates the app has no counterpart for — so it separates
    # "those two jointly" from "the field is narrow at all".
    GateVariant(
        "liquidity-only",
        frozenset({LIQUIDITY}),
        "drops both gates the app lacks, keeping only a liquidity floor",
    ),
)


# -- one candidate's gate inputs ----------------------------------------------


def _median(values: Sequence[float]) -> float:
    """:func:`screener.universe._median`, which is private and must not be forked.

    Restated rather than imported because it is not part of that module's surface;
    a seam test pins the two against each other so this copy cannot drift.
    """
    n = len(values)
    if n == 0:
        return 0.0
    ordered = sorted(values)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


@dataclass(frozen=True)
class CandidateSeries:
    """One candidate's gate inputs, held as parallel lists over its clean bars.

    ``sessions`` is the symbol's bar calendar, oldest first, and every other list is
    parallel to it. A session becomes an index ``k`` through :meth:`prefix_len` —
    the number of bars strictly *before* it — so every gate reads ``[...k]`` and the
    point-in-time claim is made in one place, exactly as
    :func:`backtest.universe.is_member` makes it with a slice.

    ``day_range`` holds ``None`` where a bar's low is non-positive, which is a
    division the classifier would not survive. Two US symbols carry one such bar
    each. ``None`` is not skipped and not treated as zero: a window containing one
    **fails** the ADR gate, so a corrupt row can only ever exclude a name, never
    admit one.
    """

    symbol: str
    sessions: tuple[date, ...]
    adj_close: tuple[float, ...]
    day_range: tuple[float | None, ...]
    dollar_volume: tuple[float, ...]

    def prefix_len(self, session: date) -> int:
        """How many bars fall strictly before ``session`` (``b.session < session``)."""
        return bisect.bisect_left(self.sessions, session)

    def passes_trend(self, k: int) -> bool:
        """Latest adjusted close above SMA50 — :func:`backtest.universe.passes_trend_gate`.

        ``False`` until 50 bars exist, which is where the listing-age floor actually
        lives: :func:`screener.indicators.sma` returns ``None`` until its window is
        full.
        """
        if k < TREND_WINDOW:
            return False
        window = self.adj_close[k - TREND_WINDOW:k]
        return self.adj_close[k - 1] > sum(window) / TREND_WINDOW

    def passes_adr(self, k: int) -> bool:
        """ADR20 at or above the contract's 3.5% — :func:`backtest.universe.passes_adr_gate`."""
        if k < ADR_WINDOW:
            return False
        window = self.day_range[k - ADR_WINDOW:k]
        if None in window:
            return False
        return sum(window) / ADR_WINDOW >= ADR_FLOOR

    def passes_liquidity(self, k: int, floor: float) -> bool:
        """Median dollar volume at or above ``floor`` — the app's own measure.

        Deliberately **not** gated on a full window, because
        :func:`screener.universe.median_dollar_volume` is not: it medians whatever
        the trailing 20 bars hold and returns ``0.0`` from none. That is unreachable
        while the trend gate is in force — it needs 50 bars — and reachable the
        moment the ``no-trend`` variant drops it, so copying the app's shortfall
        behaviour rather than tidying it is what keeps that variant honest.
        """
        return _median(self.dollar_volume[max(0, k - LIQUIDITY_WINDOW):k]) >= floor

    def flags(self, session: date, floor: float) -> tuple[bool, bool, bool] | None:
        """The three gate answers at ``session``, or ``None`` if no variant can pass.

        Computed once and shared by every variant, which is what keeps the variants
        differing by their gate set alone. ``None`` means the candidate is out under
        *every* variant — it is not common stock, or it has no bars yet — so no
        variant has to represent it.
        """
        if not is_common_stock(self.symbol, ""):
            return None
        k = self.prefix_len(session)
        if k == 0:
            return None
        return (
            self.passes_trend(k),
            self.passes_adr(k),
            self.passes_liquidity(k, floor),
        )

    def is_member(self, session: date, gates: frozenset[str], floor: float) -> bool:
        """Is this candidate a member on ``session`` under ``gates``?

        The instrument-type test is not a variant — it is not one of the three gates
        under investigation and no cell drops it. It is applied on the symbol with an
        empty name, which is what :func:`backtest.chain.stateless_universe` does for
        a name the store did not keep: the listing-name half of the test was already
        spent at enumeration (symbols excluded ``not_common_stock`` never had bars
        fetched), leaving the symbol half — the index mark and the preferred series —
        which is what still has to bite here.
        """
        flags = self.flags(session, floor)
        if flags is None:
            return False
        return passes_under(flags, gates)


def passes_under(flags: tuple[bool, bool, bool], gates: frozenset[str]) -> bool:
    """Do ``flags`` clear ``gates``? The only place a variant's rule is applied."""
    trend, adr, liquidity = flags
    return (
        (trend or TREND not in gates)
        and (adr or ADR not in gates)
        and (liquidity or LIQUIDITY not in gates)
    )


def series_of(symbol: str, bars: Sequence[Bar]) -> CandidateSeries | None:
    """``bars`` as gate-input lists, or ``None`` for a symbol with no bars."""
    if not bars:
        return None
    return CandidateSeries(
        symbol=symbol,
        sessions=tuple(b.session for b in bars),
        adj_close=tuple(b.adj_close for b in bars),
        day_range=tuple(
            (b.high / b.low - 1.0) if b.low > 0 else None for b in bars
        ),
        dollar_volume=tuple(b.close * b.volume for b in bars),
    )


def load_series(store: Store, market: str) -> dict[str, CandidateSeries]:
    """Every candidate's gate inputs, loaded once for the whole isolation.

    The pool is :meth:`screener.store.Store.symbols` — every name the store holds
    bars for — and the equality in :func:`verify_reconstruction` is what proves that
    is the right pool: references were never fetched (they carry the enumeration
    reason ``unread_reference``), so a symbol with bars in this store is a candidate.
    Read off the stored bars rather than off the enumeration JSON, so the pool cannot
    drift from the bars the gates are computed on.
    """
    out: dict[str, CandidateSeries] = {}
    for symbol in store.symbols(market):
        s = series_of(symbol, store.bars(market, symbol))
        if s is not None:
            out[symbol] = s
    return out


# -- membership, for one variant and for all of them at once ------------------


def members_at(
    series: Mapping[str, CandidateSeries],
    session: date,
    gates: frozenset[str],
    floor: float,
) -> list[str]:
    """The sorted members on ``session`` under ``gates`` — one variant's universe.

    Sorted, like :func:`backtest.universe.classify`, so a membership is comparable to
    the store's own rows without either side being re-ordered first.
    """
    return sorted(
        symbol for symbol, s in series.items() if s.is_member(session, gates, floor)
    )


def gate_flags_by_session(
    series: Mapping[str, CandidateSeries],
    sessions: Sequence[date],
    floor: float,
    progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, tuple[bool, bool, bool]]]:
    """Every candidate's three gate answers, per session, computed once.

    The single expensive pass of the isolation, and the reason every variant after it
    is cheap: the predicates do not depend on the variant, so they are evaluated here
    and each variant is a boolean ``and`` over the same flags
    (:func:`memberships_under`). Candidates no variant can admit are absent rather
    than stored as three ``False`` flags.
    """
    out: list[dict[str, tuple[bool, bool, bool]]] = []
    for i, session in enumerate(sessions, start=1):
        per_session: dict[str, tuple[bool, bool, bool]] = {}
        for symbol, s in series.items():
            flags = s.flags(session, floor)
            if flags is not None and any(flags):
                per_session[symbol] = flags
        out.append(per_session)
        if progress is not None:
            progress(i, len(sessions))
    return out


def memberships_under(
    flags_by_session: Sequence[Mapping[str, tuple[bool, bool, bool]]],
    gates: frozenset[str],
) -> list[list[str]]:
    """One variant's membership on every session, derived from the shared flags."""
    return [
        sorted(sym for sym, f in per_session.items() if passes_under(f, gates))
        for per_session in flags_by_session
    ]


# -- checking the reconstruction against the store ----------------------------


@dataclass(frozen=True)
class ReconstructionCheck:
    """How the rebuilt full-gate membership compares to the store's own rows."""

    sessions: int
    stored: int
    rebuilt: int
    extra: int
    missing: int
    worst_session: date | None

    @property
    def exact(self) -> bool:
        return self.extra == 0 and self.missing == 0


def verify_reconstruction(
    store: Store,
    market: str,
    sessions: Sequence[date],
    memberships: Sequence[Sequence[str]],
) -> ReconstructionCheck:
    """Diff the rebuilt full-gate membership against the store's own universe rows.

    This is the check the whole isolation rests on. If it is not exact, no variant
    below means anything — a gate-drop measured off a pool that does not reproduce
    the run's own field is measuring the pool, not the gate — so
    :func:`run_isolation` stops on it rather than reporting cells.
    """
    stored_total = rebuilt_total = extra = missing = 0
    worst: date | None = None
    worst_diff = 0
    for session, rebuilt_syms in zip(sessions, memberships):
        stored = set(store.universe(market, session))
        rebuilt = set(rebuilt_syms)
        stored_total += len(stored)
        rebuilt_total += len(rebuilt)
        e, m = len(rebuilt - stored), len(stored - rebuilt)
        extra += e
        missing += m
        if e + m > worst_diff:
            worst_diff, worst = e + m, session
    return ReconstructionCheck(
        sessions=len(sessions),
        stored=stored_total,
        rebuilt=rebuilt_total,
        extra=extra,
        missing=missing,
        worst_session=worst,
    )


# -- one variant's field, and the pair measured on it -------------------------


def variant_sweep(
    store: Store,
    market: str,
    sessions: Sequence[date],
    memberships: Sequence[Sequence[str]],
    *,
    lookbacks: Sequence[str],
    progress: Callable[[int, int, date], None] | None = None,
) -> list[SweepSession]:
    """:func:`replay.gate_sweep.build_sweep_sessions`, with membership handed in.

    The one line that differs from the original is where ``members`` comes from —
    this variant's gates rather than ``store.universe`` — and everything downstream
    of it (the rank table, the decile gate, the detector) is the app's own code
    reached the same way. So a cell measured here differs from the run's own field by
    the membership rule and by nothing else.
    """
    out: list[SweepSession] = []
    for i, (session, members) in enumerate(zip(sessions, memberships), start=1):
        members = list(members)
        bars = {symbol: store.bars(market, symbol) for symbol in members}
        ranks = rank_table(bars, session)
        gated = detection_gate(ranks, lookbacks=lookbacks)
        detections = [
            found
            for symbol in members
            if symbol in gated
            and (found := detect(symbol, bars[symbol], session)) is not None
        ]
        out.append(
            SweepSession(
                session=session,
                members=members,
                ranks=ranks,
                membership=gate_membership(ranks),
                detections=detections,
            )
        )
        if progress is not None:
            progress(i, len(sessions), session)
    return out


@dataclass(frozen=True)
class DimensionContrast:
    """One rubric dimension's hit rate among his picks and among the field.

    The star share is a threshold statistic, so it says *that* the pair moved and not
    *which* part of the rubric moved it. These rows say which: a gate that duplicates
    a dimension raises the **field's** hit rate on it until there is no spread left to
    discriminate on, and that shows up here as a dimension's gap collapsing while the
    dimensions no gate touches stay put.
    """

    dimension: str
    weight: int
    picks: float
    field: float

    @property
    def gap_pp(self) -> float:
        return (self.picks - self.field) * 100


@dataclass(frozen=True)
class VariantResult:
    """One variant's cell at the anchor's detector and field."""

    variant: GateVariant
    members_per_session: float
    field_detections: int
    in_field: int
    placed: int
    picks_share: float | None
    field_share: float | None
    gap_pp: float | None
    dimensions: tuple[DimensionContrast, ...]
    seconds: float

    @property
    def in_field_share(self) -> float | None:
        return self.in_field / self.placed if self.placed else None


def dimension_contrasts(
    swept: Sequence[SweepSession],
    *,
    replayable: Sequence[ExecutedTrade],
    calendar: Sequence[date],
    stored_rank_sessions: set[date],
) -> tuple[DimensionContrast, ...]:
    """Per-dimension hit rates for his picks and for the field, on the same cell.

    Reuses the sweep the cell was measured on rather than replaying, so this costs
    scoring and nothing else. The field is restricted to the sessions he traded on —
    the same denominator :func:`replay.placement.build_placement_report` uses for its
    star distributions, so these rows and the cell's pair describe one population.

    The breakdown is the **seven-dimension replayed score**: `Sector` is
    cross-sectional and is not reconstructed on this path, exactly as in the replay
    study. It is absent rather than reported as zero.
    """
    entries: dict[date, set[str]] = {}
    for t in replayable:
        entries.setdefault(t.entry_date, set()).add(t.ticker)
    fields = _cell_fields(
        swept,
        DETECTORS[ANCHOR_DETECTOR],
        next(f for f in FIELD_SOURCES if f.name == ANCHOR_FIELD),
        entries=entries,
        stored_rank_sessions=stored_rank_sessions,
        blind_spot_count=0,
    )
    by_session = {f.session: f for f in fields}

    pick_rows, pick_sessions = [], set()
    for trade in replayable:
        session = evaluation_session(list(calendar), trade.entry_date)
        held = by_session.get(session) if session else None
        if held is None:
            continue
        pick_sessions.add(held.session)
        match = field_match(held, trade.ticker)
        if match is not None:
            pick_rows.append(match.score.breakdown)
    field_rows = [
        d.score.breakdown for s in pick_sessions for d in by_session[s].detections
    ]
    if not pick_rows or not field_rows:
        return ()
    return tuple(
        DimensionContrast(
            dimension=row.dimension,
            weight=row.weight,
            picks=sum(1 for b in pick_rows if b[i].hit) / len(pick_rows),
            field=sum(1 for b in field_rows if b[i].hit) / len(field_rows),
        )
        for i, row in enumerate(pick_rows[0])
    )


def measure_variant(
    store: Store,
    market: str,
    sessions: Sequence[date],
    memberships: Sequence[Sequence[str]],
    *,
    variant: GateVariant,
    replayable: Sequence[ExecutedTrade],
    calendar: Sequence[date],
    blind_spot_count: int = 0,
    progress: Callable[[int, int, date], None] | None = None,
) -> VariantResult:
    """Build ``variant``'s field over ``sessions`` and read the anchor's cell off it."""
    started = time.time()
    union = tuple(
        dict.fromkeys(lb for version in DETECTORS for lb in DETECTORS[version].lookbacks)
    )
    swept = variant_sweep(
        store, market, sessions, memberships, lookbacks=union, progress=progress
    )
    field = next(f for f in FIELD_SOURCES if f.name == ANCHOR_FIELD)
    stored_ranks = sessions_with_stored_ranks(store, market, sessions)
    grid = build_grid(
        swept,
        replayable=replayable,
        calendar=calendar,
        stored_rank_sessions=stored_ranks,
        blind_spot_count=blind_spot_count,
        grid=[(ANCHOR_DETECTOR, field)],
    )
    cell = grid.cells[0]
    picks, field_share = cell.discrimination(PUBLISHED_RUBRIC)
    return VariantResult(
        variant=variant,
        members_per_session=sum(len(s.members) for s in swept) / len(swept),
        field_detections=cell.field_detections,
        in_field=cell.in_field,
        placed=cell.placed,
        picks_share=picks,
        field_share=field_share,
        gap_pp=cell.edge(PUBLISHED_RUBRIC),
        dimensions=dimension_contrasts(
            swept,
            replayable=replayable,
            calendar=calendar,
            stored_rank_sessions=stored_ranks,
        ),
        seconds=time.time() - started,
    )


# -- the whole isolation ------------------------------------------------------


class ReconstructionFailed(RuntimeError):
    """The full-gate rebuild did not reproduce the store's universe rows."""


@dataclass(frozen=True)
class Isolation:
    check: ReconstructionCheck
    results: tuple[VariantResult, ...]

    def by_name(self, name: str) -> VariantResult:
        return next(r for r in self.results if r.variant.name == name)


def run_isolation(
    store: Store,
    market: str = ISOLATION_MARKET,
    *,
    contract: RunContract = DEFAULT_CONTRACT,
    trades: Sequence[ExecutedTrade] | None = None,
    variants: Sequence[GateVariant] = VARIANTS,
    sessions: Sequence[date] | None = None,
    progress: Callable[[str], None] | None = None,
) -> Isolation:
    """Measure every variant over one shared pass of the gate predicates.

    Stops on a reconstruction that is not exact, rather than reporting cells that
    would be measuring the candidate pool instead of the gates.
    """
    say = progress or (lambda _m: None)
    store = CachingStore.wrap(store)
    floor = contract.value(UNIVERSE_LIQUIDITY_FLOOR_KEY)[market]
    calendar = store.sessions(market)
    measured = (
        list(sessions)
        if sessions is not None
        else [s for s in calendar if WINDOW_START <= s <= WINDOW_END][WINDOW_BURN_IN:]
    )
    trades = list(trades) if trades is not None else load_trades(DEFAULT_REFERENCE_JSON)
    replayable = [
        c.trade for c in classify_trades(trades, store, market=market) if c.replayable
    ]
    say(f"{len(measured)} measured sessions, {measured[0]} .. {measured[-1]}; "
        f"{len(replayable)} of {len(trades)} trades replayable; "
        f"liquidity floor {floor:,.0f}")

    say("loading candidate series ...")
    series = load_series(store, market)
    say(f"  {len(series)} candidates with bars")

    say("evaluating every gate once per candidate and session ...")
    started = time.time()
    flags = gate_flags_by_session(series, measured, floor)
    say(f"  done in {time.time() - started:.0f}s")

    by_variant = {v.name: memberships_under(flags, v.gates) for v in variants}

    say("checking the full-gate rebuild against the store's own universe rows ...")
    baseline = memberships_under(flags, ALL_GATES)
    check = verify_reconstruction(store, market, measured, baseline)
    say(f"  stored {check.stored}, rebuilt {check.rebuilt}, "
        f"extra {check.extra}, missing {check.missing} -> "
        f"{'EXACT' if check.exact else 'MISMATCH'}")
    if not check.exact:
        raise ReconstructionFailed(
            f"the full-gate rebuild does not reproduce the store's universe: "
            f"{check.extra} extra and {check.missing} missing across "
            f"{check.sessions} sessions (worst {check.worst_session}). "
            f"No gate can be isolated against a pool that does not reproduce the run."
        )

    results = []
    for variant in variants:
        say(f"measuring {variant.name} ({variant.note}) ...")
        r = measure_variant(
            store, market, measured, by_variant[variant.name],
            variant=variant, replayable=replayable, calendar=calendar,
        )
        say(f"  members/session {r.members_per_session:.1f}  "
            f"in_field {r.in_field}/{r.placed}  gap {_pp(r.gap_pp)}  "
            f"[{r.seconds:.0f}s]")
        results.append(r)
    return Isolation(check=check, results=tuple(results))


# -- reporting ----------------------------------------------------------------


def _pp(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}pp"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def format_isolation(isolation: Isolation) -> str:
    """The isolation as a table, baseline first, one gate dropped per row."""
    c = isolation.check
    lines = [
        "The gate isolation (#211) — one store, one population, one detector,",
        "one gate moving at a time.",
        "",
        f"Full-gate rebuild vs the store's own universe rows: stored {c.stored}, "
        f"rebuilt {c.rebuilt}, extra {c.extra}, missing {c.missing}, "
        f"over {c.sessions} sessions -> {'EXACT' if c.exact else 'MISMATCH'}",
        "",
        f"{'variant':<14} {'members/sess':>12} {'field det':>10} "
        f"{'in_field':>12} {'picks':>8} {'field':>8} {'gap':>9}",
    ]
    for r in isolation.results:
        lines.append(
            f"{r.variant.name:<14} {r.members_per_session:>12.1f} "
            f"{r.field_detections:>10} "
            f"{f'{r.in_field}/{r.placed}':>12} "
            f"{_pct(r.picks_share):>8} {_pct(r.field_share):>8} "
            f"{_pp(r.gap_pp):>9}"
        )
    lines += ["", "notes:"]
    for r in isolation.results:
        lines.append(f"  {r.variant.name:<14} {r.variant.note}")
    lines += [
        "",
        f"picks/field are the share reaching >= {DISCRIMINATION_STARS} stars under "
        f"rubric v{PUBLISHED_RUBRIC}; gap is picks - field.",
        "",
        "Per-dimension hit rates, his picks against the field on the sessions he traded.",
        "A gate that duplicates a dimension shows up as that dimension's gap collapsing",
        "while the dimensions no gate touches stay put. Seven-dimension replayed score:",
        "`Sector` is cross-sectional and is not reconstructed on this path.",
    ]
    for r in isolation.results:
        if not r.dimensions:
            continue
        lines += ["", f"  {r.variant.name}"]
        lines.append(
            f"    {'dimension':<13}{'wt':>3}{'picks':>9}{'field':>9}{'gap':>10}"
        )
        for d in r.dimensions:
            lines.append(
                f"    {d.dimension:<13}{d.weight:>3}{d.picks * 100:>8.1f}%"
                f"{d.field * 100:>8.1f}%{d.gap_pp:>+9.1f}pp"
            )
    return "\n".join(lines)


def isolation_payload(isolation: Isolation) -> dict:
    return {
        "window": {
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "burn_in": WINDOW_BURN_IN,
            "market": ISOLATION_MARKET,
        },
        "detector_version": ANCHOR_DETECTOR,
        "field": ANCHOR_FIELD,
        "rubric_version": PUBLISHED_RUBRIC,
        "stars": DISCRIMINATION_STARS,
        "reconstruction": {
            "sessions": isolation.check.sessions,
            "stored": isolation.check.stored,
            "rebuilt": isolation.check.rebuilt,
            "extra": isolation.check.extra,
            "missing": isolation.check.missing,
            "exact": isolation.check.exact,
        },
        "variants": [
            {
                "name": r.variant.name,
                "gates": sorted(r.variant.gates),
                "dropped": sorted(r.variant.dropped),
                "note": r.variant.note,
                "members_per_session": r.members_per_session,
                "field_detections": r.field_detections,
                "in_field": r.in_field,
                "placed": r.placed,
                "in_field_share": r.in_field_share,
                "picks_share": r.picks_share,
                "field_share": r.field_share,
                "gap_pp": r.gap_pp,
                "dimensions": [
                    {
                        "dimension": d.dimension,
                        "weight": d.weight,
                        "picks": d.picks,
                        "field": d.field,
                        "gap_pp": d.gap_pp,
                    }
                    for d in r.dimensions
                ],
            }
            for r in isolation.results
        ],
    }


DEFAULT_OUT_JSON = (
    Path(__file__).resolve().parents[2] / "references" / "backtest_gate_isolation.json"
)
DEFAULT_OUT_TXT = (
    Path(__file__).resolve().parents[2] / "references" / "backtest_gate_isolation.txt"
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The #211 gate isolation.")
    parser.add_argument("--store", default="data/backtest.duckdb")
    parser.add_argument("--market", default=ISOLATION_MARKET)
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-txt", default=str(DEFAULT_OUT_TXT))
    args = parser.parse_args(argv)

    def say(message: str) -> None:
        print(message, flush=True)

    isolation = run_isolation(Store.open(args.store), args.market, progress=say)
    report = format_isolation(isolation)
    print()
    print(report)
    Path(args.out_json).write_text(
        json.dumps(isolation_payload(isolation), indent=1) + "\n"
    )
    Path(args.out_txt).write_text(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
