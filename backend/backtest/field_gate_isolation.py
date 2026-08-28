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
moves between cells is **one difference from the app's universe** — a gate, or (since
#213) the membership band. A cell read against the one beside it therefore differs
from it by exactly that one thing, which is what "attribute it to a gate rather than
to the universe" requires.

**Four gates, not three.** The divergence page names three differences from the
app's universe — the ADR20 floor, the ADTV floor and the dropped hysteresis. There
is a fourth, and it is the one the app has no counterpart for at all: the **trend
gate**, ``close > SMA50`` (:func:`backtest.universe.passes_trend_gate`). The app's
universe is liquidity, instrument type, listing age and density; it has neither a
trend gate nor a volatility gate. So the trend gate is a variant here like the
others, because a difference nobody listed is exactly the kind that ends up
attributed to "the universe".

**The fourth difference is not a gate, so it is walked rather than dropped (#213).**
The app's universe is *hysteretic*: a name enters on the liquidity floor at ≥ 1.0× and
leaves only below 0.8× (:data:`screener.universe.HYSTERESIS_EXIT`), which the contract
drops. That cannot be switched off here, because the contract's classifier never had
it — :func:`backtest.universe.classify` takes no prior membership and is stateless by
construction (``universe.statelessness``). So the band is added instead, by a **stateful
variant classifier** that lives only in this module
(:func:`hysteretic_memberships`): it walks sessions forward carrying the previous
session's membership, applies the app's band on the liquidity gate, and is otherwise the
contract's own gates. Two cells use it — the run's own field plus the band, and the
app-shaped field plus the band — and each is read against the same gate set without it,
so what moves between them is the band and nothing else. Nothing about
:mod:`backtest.universe` changes: its statelessness is a recorded property with its own
test, and #213 measures what it costs rather than reversing it.

Because the band is stateful, its cells are **walked into**: the window's own 126-session
burn-in is replayed first so a member is something the walk has made rather than
something its first session had to invent. No warm-up session is reported, and no bar
outside the reference study's window is read to settle it.

**Dropping a gate needs a superset, so membership is rebuilt rather than read.**
:func:`replay.gate_sweep.build_sweep_sessions` reads membership off the store's
persisted ``universe`` rows, and those rows are the *intersection* of every gate.
Adding a gate to them is a filter; **dropping** one admits names the run never
stored, so this module recomputes membership from the candidate bars and hands it
to that same function through its ``members_for`` hook. The sweep itself — ranks,
decile gate, detector — is not reimplemented here.

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
from typing import (
    Any,
    Callable,
    Collection,
    Iterable,
    Mapping,
    NamedTuple,
    Sequence,
)

from screener.bars import Bar
from screener.detection import detect, detection_gate
from screener.indicators import ADR_WINDOW
from screener.ranks import rank_table
from screener.store import Store
from screener.universe import (
    HYSTERESIS_EXIT,
    LIQUIDITY_WINDOW,
    _median as app_median,
    is_common_stock,
)

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
from replay.gate_sweep import SweepSession, build_sweep_sessions
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

# The recorded figures, as JSON holds them: one payload, or one variant's row inside
# it. Heterogeneous by construction — this is what is written to
# ``backtest_gate_isolation.json`` and read back to re-render or merge a table without
# re-measuring a cell.
Cell = Mapping[str, Any]

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
# drop exactly one. The middle one is ``VOLATILITY`` rather than ``ADR`` because that
# is what the contract calls it (``universe.volatility_gate``) and because ADR is the
# *quantity* it is measured with — this module also imports ``ADR_FLOOR`` and
# ``ADR_WINDOW``, and one label cannot mean both the gate and the number.
TREND, VOLATILITY, LIQUIDITY = "trend", "volatility", "liquidity"
ALL_GATES = frozenset({TREND, VOLATILITY, LIQUIDITY})


def band_threshold(floor: float, *, held: bool) -> float:
    """The floor a name has to clear: 1.0× to enter, ``HYSTERESIS_EXIT`` to stay.

    The app's asymmetry, in one expression and one place — "more evidence to leave
    than to enter" (:mod:`screener.universe`, spec §4.1, §3.4 rules 3/6). The
    multiple is imported from the app rather than restated here, so the band this
    module measures is the band the app applies and cannot drift from it.
    """
    return floor * (HYSTERESIS_EXIT if held else 1.0)


class GateFlags(NamedTuple):
    """One candidate's gate answers on one session, computed once for every variant.

    Four answers for three gates, because the liquidity floor is asked twice: at
    1.0× (:attr:`liquidity`, which is what a non-member has to clear) and at 0.8×
    (:attr:`liquidity_held`, which is what a member has to fall below to leave).
    A stateless variant reads the first and never the second; a hysteretic one
    picks between them by whether the name was a member on the session before.
    """

    trend: bool
    volatility: bool
    liquidity: bool
    liquidity_held: bool


@dataclass(frozen=True)
class UniverseGateSet:
    """One universe rule: the run's gates, minus at most one — and its band, or not.

    ``dropped`` is the whole point — a variant that drops nothing and holds no band
    is the run's own field and is the baseline every other cell is read against.
    Because exactly one thing separates any variant from a variant beside it, a
    difference between them attributes to that thing and to nothing else.

    ``hysteresis`` is the fourth difference from the app's universe (#213) and the
    one that is not a gate: it cannot be switched off, because the contract's
    classifier never had it. A variant that sets it walks sessions forward carrying
    the previous session's membership and applies the app's 0.8–1.0× band on the
    liquidity floor, and is otherwise these same gates. It is a **measurement
    variant and lives only here** — :func:`backtest.universe.classify` stays
    stateless (``universe.statelessness``).
    """

    name: str
    gates: frozenset[str]
    note: str
    hysteresis: bool = False

    @property
    def dropped(self) -> frozenset[str]:
        return ALL_GATES - self.gates


# The baseline first, then one variant per gate. Each note says what the app's
# universe does with the same gate, because the divergence being explained is
# against the app's field.
VARIANTS: tuple[UniverseGateSet, ...] = (
    UniverseGateSet(
        "all-three",
        ALL_GATES,
        "the run's own field — reproduces the committed -5.01pp",
    ),
    UniverseGateSet(
        "no-adr",
        ALL_GATES - {VOLATILITY},
        "drops the 3.5% ADR20 floor, which the app's universe does not have",
    ),
    UniverseGateSet(
        "no-trend",
        ALL_GATES - {TREND},
        "drops close > SMA50, which the app's universe does not have",
    ),
    UniverseGateSet(
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
    UniverseGateSet(
        "liquidity-only",
        frozenset({LIQUIDITY}),
        "drops both gates the app lacks, keeping only a liquidity floor",
    ),
    # The two band cells (#213). Each one is a row above it plus the app's
    # hysteresis and nothing else, so each is read against that row and the
    # difference is what the band is worth. Both keep the liquidity gate, because
    # the band is on that floor and a band on a dropped floor measures nothing.
    UniverseGateSet(
        "all-three+band",
        ALL_GATES,
        "the run's own field, plus the app's 0.8-1.0x hysteresis band",
        hysteresis=True,
    ),
    UniverseGateSet(
        "liquidity-only+band",
        frozenset({LIQUIDITY}),
        "the app's full shape — its gate set and its band — from the run's store",
        hysteresis=True,
    ),
)


# -- one candidate's gate inputs ----------------------------------------------


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

    def adtv(self, k: int) -> float:
        """Median dollar volume over the trailing window — the app's own measure.

        Deliberately **not** gated on a full window, because
        :func:`screener.universe.median_dollar_volume` is not: it medians whatever
        the trailing 20 bars hold and returns ``0.0`` from none. That is unreachable
        while the trend gate is in force — it needs 50 bars — and reachable the
        moment the ``no-trend`` variant drops it, so copying the app's shortfall
        behaviour rather than tidying it is what keeps that variant honest.
        """
        return app_median(self.dollar_volume[max(0, k - LIQUIDITY_WINDOW):k])

    def passes_liquidity_band(self, k: int, floor: float, *, held: bool) -> bool:
        """The app's hysteretic floor: 1.0× to enter, below 0.8× to leave (#213).

        ``held`` is whether this name was a member on the session before, which is
        the only state anywhere in this module — and the reason a hysteretic variant
        has to be *walked* rather than evaluated session by session.
        """
        return self.adtv(k) >= band_threshold(floor, held=held)

    def passes_liquidity(self, k: int, floor: float) -> bool:
        """ADTV at or above ``floor`` — :func:`backtest.universe.passes_liquidity_gate`.

        The entry side of the band, which is what a name with no prior membership
        faces, and which is the whole liquidity gate for every stateless variant.
        """
        return self.passes_liquidity_band(k, floor, held=False)

    def flags(self, session: date, floor: float) -> GateFlags | None:
        """The gate answers at ``session``, or ``None`` if no variant can pass.

        Computed once and shared by every variant, which is what keeps the variants
        differing by their gate set alone. ``None`` means the candidate is out under
        *every* variant — it is not common stock, or it has no bars yet — so no
        variant has to represent it.

        Both ends of the band are asked through :meth:`passes_liquidity_band` rather
        than compared here, so the predicate the seam tests pin against
        :mod:`screener.universe` is the predicate this pass actually runs. The extra
        median is worth it: the whole pass is 19 seconds against the sweeps' minutes.
        """
        if not is_common_stock(self.symbol, ""):
            return None
        k = self.prefix_len(session)
        if k == 0:
            return None
        return GateFlags(
            self.passes_trend(k),
            self.passes_adr(k),
            self.passes_liquidity(k, floor),
            self.passes_liquidity_band(k, floor, held=True),
        )

    def is_member(
        self, session: date, gates: frozenset[str], floor: float, *, held: bool = False
    ) -> bool:
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
        return passes_under(flags, gates, held=held)


def passes_under(flags: GateFlags, gates: frozenset[str], *, held: bool = False) -> bool:
    """Do ``flags`` clear ``gates``? The only place a variant's rule is applied.

    ``held`` is the band, and it relaxes the liquidity floor and nothing else — the
    app's band is on that floor alone (``screener.universe._is_member``), so a held
    name still has to clear every other gate the variant applies. It is ``False``
    for every stateless variant, which is what makes those variants stateless.
    """
    liquidity = flags.liquidity_held if held else flags.liquidity
    return (
        (flags.trend or TREND not in gates)
        and (flags.volatility or VOLATILITY not in gates)
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
    *,
    prior: Collection[str] = (),
) -> list[str]:
    """The sorted members on ``session`` under ``gates`` — one variant's universe.

    Sorted, like :func:`backtest.universe.classify`, so a membership is comparable to
    the store's own rows without either side being re-ordered first. ``prior`` is
    the previous session's membership, and passing a non-empty one is what asks for
    the band; a stateless variant's caller leaves it empty.
    """
    return sorted(
        symbol
        for symbol, s in series.items()
        if s.is_member(session, gates, floor, held=symbol in prior)
    )


def gate_flags_by_session(
    series: Mapping[str, CandidateSeries],
    sessions: Sequence[date],
    floor: float,
    progress: Callable[[int, int], None] | None = None,
) -> list[dict[str, GateFlags]]:
    """Every candidate's gate answers, per session, computed once.

    The single expensive pass of the isolation, and the reason every variant after it
    is cheap: the predicates do not depend on the variant, so they are evaluated here
    and each variant is a boolean ``and`` over the same flags
    (:func:`memberships_for`). Candidates no variant can admit are absent rather
    than stored as four ``False`` flags — and a name that cannot even clear 0.8× the
    floor is out under the band too, so dropping it stays safe now that a hysteretic
    variant reads the same flags.
    """
    out: list[dict[str, GateFlags]] = []
    for i, session in enumerate(sessions, start=1):
        per_session: dict[str, GateFlags] = {}
        for symbol, s in series.items():
            flags = s.flags(session, floor)
            if flags is not None and any(flags):
                per_session[symbol] = flags
        out.append(per_session)
        if progress is not None:
            progress(i, len(sessions))
    return out


def memberships_under(
    flags_by_session: Sequence[Mapping[str, GateFlags]],
    gates: frozenset[str],
) -> list[list[str]]:
    """One stateless variant's membership on every session, from the shared flags.

    Each session's answer depends on that session's flags and nothing else, exactly
    as :func:`backtest.universe.classify` does.
    """
    return [
        sorted(sym for sym, f in per_session.items() if passes_under(f, gates))
        for per_session in flags_by_session
    ]


def hysteretic_memberships(
    flags_by_session: Sequence[Mapping[str, GateFlags]],
    gates: frozenset[str],
    prior: Collection[str] = (),
) -> list[list[str]]:
    """The **stateful variant classifier** (#213): the same gates, walked forward.

    The one thing in this module that is not a function of a single session. It
    carries the previous session's membership and lets a member clear the liquidity
    floor at 0.8× where a non-member needs 1.0×, which is the app's band and the
    app's asymmetry — "more evidence to leave than to enter".

    It is a **measurement variant and nothing else**. It is used by this harness and
    never by the run: :func:`backtest.universe.classify` takes no prior membership
    and returns the same answer however often it is asked
    (``universe.statelessness``), and #213 measures what that costs rather than
    changing it.

    ``prior`` seeds the walk, which is what a warm-up hands in. Started cold it
    admits nobody on the band on its first session — a member is something the walk
    has to have made — so the sessions a cell reports are walked *into* rather than
    started at (:func:`memberships_for`).

    A name absent from a session's flags is out under every rule including the band,
    so it leaves membership here as it does anywhere else.
    """
    members: set[str] = set(prior)
    out: list[list[str]] = []
    for per_session in flags_by_session:
        members = {
            sym
            for sym, f in per_session.items()
            if passes_under(f, gates, held=sym in members)
        }
        out.append(sorted(members))
    return out


def memberships_for(
    flags_by_session: Sequence[Mapping[str, GateFlags]],
    variant: UniverseGateSet,
    *,
    warm_up: int = 0,
    prior: Collection[str] = (),
) -> list[list[str]]:
    """One variant's membership on the **measured** sessions, however it is built.

    ``warm_up`` is how many leading sessions are there to settle the band rather
    than to be reported: the walk reads them and the result drops them, so a
    hysteretic cell is measured over the same sessions as every other cell. A
    stateless variant ignores them, which is what "the warm-up changes nothing
    except the band" means here.
    """
    if not variant.hysteresis:
        return memberships_under(flags_by_session[warm_up:], variant.gates)
    return hysteretic_memberships(flags_by_session, variant.gates, prior)[warm_up:]


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
    """This variant's field, through the sweep the run's own field is built with.

    :func:`replay.gate_sweep.build_sweep_sessions` does the work; the only thing
    handed in is where membership comes from. Reusing it rather than reimplementing
    the loop is what makes "only the gate set moved" true of the *code* as well as
    of the intent — the rank table, the decile gate and the detector are literally
    the same statements for a variant field as for the run's own.
    """
    by_session = dict(zip(sessions, memberships))
    return build_sweep_sessions(
        store,
        market,
        sessions,
        lookbacks=lookbacks,
        members_for=lambda session: by_session[session],
        progress=progress,
    )


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

    variant: UniverseGateSet
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
    variant: UniverseGateSet,
    replayable: Sequence[ExecutedTrade],
    calendar: Sequence[date],
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
        blind_spot_count=0,
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
    warm_up: int = 0

    def by_name(self, name: str) -> VariantResult:
        return next(r for r in self.results if r.variant.name == name)


def window_sessions(calendar: Sequence[date]) -> tuple[list[date], list[date]]:
    """The anchor's window, split into the burn-in and the sessions it measures.

    The burn-in is what the reference study discards, and it is what a hysteretic
    variant needs for the very reason that study discards it: a walk started cold
    has no members to hold, so its first sessions would read as stateless ones. The
    replay study warms over the same 126 sessions and says why — "so the hysteresis
    band settles before any measured session" (findings §4, user stories 13/14) — so
    the band cells here settle over exactly the sessions the app-side figure they are
    compared against settled over, and no bar outside the window is read to do it.
    """
    windowed = [s for s in calendar if WINDOW_START <= s <= WINDOW_END]
    return windowed[:WINDOW_BURN_IN], windowed[WINDOW_BURN_IN:]


def run_isolation(
    store: Store,
    market: str = ISOLATION_MARKET,
    *,
    contract: RunContract = DEFAULT_CONTRACT,
    trades: Sequence[ExecutedTrade] | None = None,
    variants: Sequence[UniverseGateSet] = VARIANTS,
    sessions: Sequence[date] | None = None,
    warm_up: Sequence[date] | None = None,
    progress: Callable[[str], None] | None = None,
) -> Isolation:
    """Measure every variant over one shared pass of the gate predicates.

    Stops on a reconstruction that is not exact, rather than reporting cells that
    would be measuring the candidate pool instead of the gates.

    ``warm_up`` is the sessions a hysteretic variant walks through before the ones
    it reports, and it defaults to the window's own burn-in. It is skipped entirely
    when no variant is hysteretic, so the stateless table costs exactly what it did.
    Nothing measured is read off a warm-up session: the reconstruction check and
    every cell are over ``sessions`` alone.
    """
    say = progress or (lambda _m: None)
    store = CachingStore.wrap(store)
    floor = contract.value(UNIVERSE_LIQUIDITY_FLOOR_KEY)[market]
    calendar = store.sessions(market)
    burn_in, windowed = window_sessions(calendar)
    measured = list(sessions) if sessions is not None else windowed
    warming = (
        list(warm_up)
        if warm_up is not None
        else (burn_in if sessions is None else [])
    )
    if not any(v.hysteresis for v in variants):
        warming = []
    trades = list(trades) if trades is not None else load_trades(DEFAULT_REFERENCE_JSON)
    replayable = [
        c.trade for c in classify_trades(trades, store, market=market) if c.replayable
    ]
    say(f"{len(measured)} measured sessions, {measured[0]} .. {measured[-1]}; "
        f"{len(warming)} warm-up sessions for the band; "
        f"{len(replayable)} of {len(trades)} trades replayable; "
        f"liquidity floor {floor:,.0f}")

    say("loading candidate series ...")
    series = load_series(store, market)
    say(f"  {len(series)} candidates with bars")

    say("evaluating every gate once per candidate and session ...")
    started = time.time()
    flags = gate_flags_by_session(series, list(warming) + measured, floor)
    say(f"  done in {time.time() - started:.0f}s")

    by_variant = {
        v.name: memberships_for(flags, v, warm_up=len(warming)) for v in variants
    }

    say("checking the full-gate rebuild against the store's own universe rows ...")
    baseline = memberships_under(flags[len(warming):], ALL_GATES)
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
    return Isolation(check=check, results=tuple(results), warm_up=len(warming))


# -- reporting ----------------------------------------------------------------


def _pp(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}pp"


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.2f}%"


def band_effects(variants: Sequence[Cell]) -> list[dict[str, Any]]:
    """What the band is worth, per hysteretic cell: its stateless twin, subtracted.

    The twin is the row with the same gate set and no band, so the difference is
    the band and nothing else — the same one-variable-at-a-time rule the gate rows
    are built on. A pair with a cell nobody measured (no ``gap_pp``, no placed
    trades) yields **no effect at all** rather than a zero one: "the band is worth
    nothing" and "nobody measured it" are different claims, and only the first is a
    finding.
    """
    by_gates = {
        frozenset(v["gates"]): v for v in variants if not v.get("hysteresis")
    }
    out = []
    for variant in variants:
        if not variant.get("hysteresis"):
            continue
        twin = by_gates.get(frozenset(variant["gates"]))
        if twin is None or variant["gap_pp"] is None or twin["gap_pp"] is None:
            continue
        placed = variant["placed"]
        out.append(
            {
                "variant": variant["name"],
                "baseline": twin["name"],
                "gates": sorted(variant["gates"]),
                "members_delta": variant["members_per_session"]
                - twin["members_per_session"],
                "in_field": variant["in_field"],
                "baseline_in_field": twin["in_field"],
                "placed": placed,
                "in_field_delta": variant["in_field"] - twin["in_field"],
                "in_field_delta_pp": (
                    (variant["in_field"] - twin["in_field"]) / placed * 100
                    if placed
                    else None
                ),
                "gap_pp": variant["gap_pp"],
                "baseline_gap_pp": twin["gap_pp"],
                "gap_delta_pp": variant["gap_pp"] - twin["gap_pp"],
            }
        )
    return out


def format_payload(payload: Cell) -> str:
    """The isolation as a table, rendered from the figures that were recorded.

    Reading the payload rather than the objects is what lets a table be re-rendered
    — or a subset of rows merged into it (:func:`merge_payloads`) — without
    re-measuring cells that have already been run.
    """
    c = payload["reconstruction"]
    variants = payload["variants"]
    width = max(len("variant"), *(len(v["name"]) for v in variants))
    lines = [
        "The gate isolation (#211, #213) — one store, one population, one detector,",
        "one difference from the app's universe moving at a time.",
        "",
        f"Full-gate rebuild vs the store's own universe rows: stored {c['stored']}, "
        f"rebuilt {c['rebuilt']}, extra {c['extra']}, missing {c['missing']}, "
        f"over {c['sessions']} sessions -> {'EXACT' if c['exact'] else 'MISMATCH'}",
        "",
        f"{'variant':<{width}} {'members/sess':>12} {'field det':>10} "
        f"{'in_field':>12} {'picks':>8} {'field':>8} {'gap':>9}",
    ]
    for v in variants:
        placed = "{}/{}".format(v["in_field"], v["placed"])
        lines.append(
            f"{v['name']:<{width}} {v['members_per_session']:>12.1f} "
            f"{v['field_detections']:>10} {placed:>12} "
            f"{_pct(v['picks_share']):>8} {_pct(v['field_share']):>8} "
            f"{_pp(v['gap_pp']):>9}"
        )
    lines += ["", "notes:"]
    for v in variants:
        lines.append(f"  {v['name']:<{width}} {v['note']}")
    lines += [
        "",
        f"picks/field are the share reaching >= {payload['stars']} stars under "
        f"rubric v{payload['rubric_version']}; gap is picks - field.",
    ]
    effects = payload.get("band_effects") or []
    if effects:
        warm = payload["window"].get("band_warm_up", 0)
        lines += [
            "",
            "What the app's hysteresis band is worth: each band row against the same",
            f"gates without it. The band relaxes the liquidity floor to "
            f"{HYSTERESIS_EXIT:g}x for a",
            "name that was a member on the session before, and touches no other gate.",
            f"It is walked into over {warm} warm-up sessions, none of which is reported.",
            "",
            f"  {'band row':<{width}} {'vs':<{width}} {'members':>9} "
            f"{'in_field':>12} {'gap':>9} {'gap delta':>10}",
        ]
        for e in effects:
            moved = "{:+d}/{}".format(e["in_field_delta"], e["placed"])
            lines.append(
                f"  {e['variant']:<{width}} {e['baseline']:<{width}} "
                f"{e['members_delta']:>+9.1f} {moved:>12} "
                f"{_pp(e['gap_pp']):>9} {_pp(e['gap_delta_pp']):>10}"
            )
    lines += [
        "",
        "Per-dimension hit rates, his picks against the field on the sessions he traded.",
        "A gate that duplicates a dimension shows up as that dimension's gap collapsing",
        "while the dimensions no gate touches stay put. Seven-dimension replayed score:",
        "`Sector` is cross-sectional and is not reconstructed on this path.",
    ]
    for v in variants:
        if not v["dimensions"]:
            continue
        lines += ["", f"  {v['name']}"]
        lines.append(
            f"    {'dimension':<13}{'wt':>3}{'picks':>9}{'field':>9}{'gap':>10}"
        )
        for d in v["dimensions"]:
            lines.append(
                f"    {d['dimension']:<13}{d['weight']:>3}{d['picks'] * 100:>8.1f}%"
                f"{d['field'] * 100:>8.1f}%{d['gap_pp']:>+9.1f}pp"
            )
    return "\n".join(lines)


def format_isolation(isolation: Isolation) -> str:
    """The isolation as a table, baseline first, one difference per row."""
    return format_payload(isolation_payload(isolation))


def _comparable(payload: Cell, key: str) -> Any:
    """The part of ``key`` two payloads have to agree on to sit in one table.

    The window's warm-up is excluded: it settles the band for the rows that have
    one and changes nothing about the sessions any row is measured over, so a
    recorded table from before there were band rows still merges.
    """
    value = payload.get(key)
    if key == "window":
        return {k: v for k, v in value.items() if k != "band_warm_up"}
    return value


def merge_payloads(recorded: Cell, fresh: Cell) -> dict[str, Any]:
    """``fresh``'s cells on top of ``recorded``'s, in :data:`VARIANTS` order.

    #213 adds two rows to a table whose other five were run three times across two
    implementations and reproduced identically, so it measures the two and merges
    rather than re-measuring what is already recorded.

    Rows from two different measurements would read as one, so the things that
    would make them incomparable — the window, the detector, the field, the rubric —
    have to match, and a mismatch raises rather than merging. The reconstruction
    check reported is the fresh run's: it is the pass that actually verified the
    pool these cells were measured off.
    """
    for key in ("window", "detector_version", "field", "rubric_version", "stars"):
        if _comparable(recorded, key) != _comparable(fresh, key):
            raise ValueError(
                f"refusing to merge: {key} differs between the recorded isolation "
                f"({_comparable(recorded, key)!r}) and the fresh one "
                f"({_comparable(fresh, key)!r}). Cells from two measurements would "
                f"read as one table."
            )
    cells = {v["name"]: v for v in recorded["variants"]}
    cells.update({v["name"]: v for v in fresh["variants"]})
    # A table recorded before there were band rows has no ``hysteresis`` on its
    # cells. Fill it from the variant of that name rather than leaving the merged
    # artifact half-labelled, which would read as "unknown" rather than "stateless".
    known = {v.name: v.hysteresis for v in VARIANTS}
    cells = {
        name: (
            cell
            if "hysteresis" in cell
            else {**cell, "hysteresis": known.get(name, False)}
        )
        for name, cell in cells.items()
    }
    order = [v.name for v in VARIANTS]
    merged = dict(recorded)
    merged["window"] = fresh["window"]
    merged["reconstruction"] = fresh["reconstruction"]
    merged["variants"] = [cells.pop(name) for name in order if name in cells] + list(
        cells.values()
    )
    merged["band_effects"] = band_effects(merged["variants"])
    return merged


def isolation_payload(isolation: Isolation) -> dict:
    payload = {
        "window": {
            "start": WINDOW_START.isoformat(),
            "end": WINDOW_END.isoformat(),
            "burn_in": WINDOW_BURN_IN,
            "band_warm_up": isolation.warm_up,
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
                "hysteresis": r.variant.hysteresis,
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
    payload["band_effects"] = band_effects(payload["variants"])
    return payload


DEFAULT_OUT_JSON = (
    Path(__file__).resolve().parents[2] / "references" / "backtest_gate_isolation.json"
)
DEFAULT_OUT_TXT = (
    Path(__file__).resolve().parents[2] / "references" / "backtest_gate_isolation.txt"
)


def selected_variants(names: Iterable[str]) -> tuple[UniverseGateSet, ...]:
    """The named variants, in :data:`VARIANTS` order, or a refusal naming the rest."""
    wanted = list(names)
    known = {v.name: v for v in VARIANTS}
    unknown = [n for n in wanted if n not in known]
    if unknown:
        raise SystemExit(
            f"unknown variant(s) {', '.join(unknown)}; "
            f"known: {', '.join(known)}"
        )
    return tuple(v for v in VARIANTS if v.name in set(wanted))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The #211/#213 gate isolation.")
    parser.add_argument("--store", default="data/backtest.duckdb")
    parser.add_argument("--market", default=ISOLATION_MARKET)
    parser.add_argument("--out-json", default=str(DEFAULT_OUT_JSON))
    parser.add_argument("--out-txt", default=str(DEFAULT_OUT_TXT))
    parser.add_argument(
        "--only",
        default="",
        help=(
            "comma-separated variant names to measure, merged into the cells "
            "--out-json already records rather than replacing them. The five "
            "stateless rows were run three times across two implementations and "
            "reproduced identically; #213's two band rows are what this adds."
        ),
    )
    args = parser.parse_args(argv)

    def say(message: str) -> None:
        print(message, flush=True)

    only = [n.strip() for n in args.only.split(",") if n.strip()]
    variants = selected_variants(only) if only else VARIANTS
    isolation = run_isolation(
        Store.open(args.store), args.market, variants=variants, progress=say
    )
    payload = isolation_payload(isolation)
    if only:
        recorded = json.loads(Path(args.out_json).read_text())
        payload = merge_payloads(recorded, payload)
        say(f"merged {len(only)} measured cell(s) into {args.out_json}")
    report = format_payload(payload)
    print()
    print(report)
    Path(args.out_json).write_text(json.dumps(payload, indent=1) + "\n")
    Path(args.out_txt).write_text(report + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
