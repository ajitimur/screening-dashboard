"""What widening the detection gate actually admits — the price of 3→5 (#149).

ADR 0003 records **widen the gate from three lookbacks to five** as its leading
candidate: it recovers 75 of Kullamägi's real entries (11.4pp, decile recall
60.0% → 71.4%) for 7.8 points of universe. It deliberately did not authorise the
edit. This module is the measurement that decides it.

**The objection the headline number cannot answer.** ``DETECTION_LOOKBACKS`` is
not an arbitrary narrowing: ``1w`` (a momentum burst) and ``12m`` (stale) are
excluded *on purpose* (:func:`screener.detection.detection_gate`, spec §4.5
gates), so a name that topped out a year ago cannot qualify on staleness alone.
Widening 3→5 re-admits exactly those two. So the decisive figure is not the 75 —
it is the **composition** of the 75 by admitting lookback (:func:`decompose_recovered`),
and then, one level down, what those trades looked like on the lookbacks the gate
already unions (:func:`profile_recovered`). Both are needed, because "admitted by
``12m``" and "topped out months ago and has done nothing since" are different
claims, and only the second is what the exclusion was written against: a name
still sitting high in ``6m`` is not stale, whichever lookback let it in.

**Precision stays unmeasurable, so the cost is priced as volume.** The reference
set records no setup he declined, so there is no control group and no
false-positive rate (findings §7, §9). What *is* countable is **field inflation**:
how many more detections the widened gate emits per session, and therefore how
many extra names the app shows per real entry recovered. That is the basis #141
sets for the cluster gate, mirrored here so the funnel's two most expensive gates
are priced the same way. Field inflation is a volume proxy and is **never** a
false-positive rate: the added names carry no verdict.

**One pass, every variant.** Detection geometry does not depend on the gate — the
gate only decides *which* members are handed to :func:`screener.detection.detect`
— so the sweep runs the detector once over the union of every swept lookback set
and derives each variant's field by filtering that superset against the variant's
own gate. Four gate widths therefore cost one detection pass, not four.

**Read-only, and it never mutates the live width.** Every gate here goes through
the app's own :func:`~screener.detection.detection_gate` with its ``lookbacks``
handed in (#149's first acceptance criterion), and the baseline is
:data:`GATE_AS_MEASURED` rather than the live constant, so the report stays
reproducible after its own verdict moves that constant. Nothing here writes to the
store: the
forward chain is reconstructed from the universe rows the replay store already
holds and the ranks are recomputed in memory, exactly as
:func:`replay.chain._replay_session` does on reuse.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence

from screener.detection import Detection, detect, detection_gate
from screener.indicators import LOOKBACKS
from screener.ranks import Rank, rank_table
from screener.store import Store

from .caching_store import CachingStore
from .chain import BURN_IN_SESSIONS, REPLAY_MARKET, SessionField
from .field import build_field
from .funnel import FunnelRow, StageRecall, build_funnel_report, stage_recall
from .placement import BOARD_SIZE
from .study import progress_printer
from .reference import (
    DEFAULT_BLIND_SPOT_OUT,
    DEFAULT_REFERENCE_JSON,
    ExecutedTrade,
    classify,
    load_trades,
)

# The two lookbacks the gate excluded when #149 asked the question, and the reason
# each was kept out (:func:`screener.detection.detection_gate`): `1w` as a momentum
# burst rather than §3.1's big prior move, `12m` as staleness. Named rather than
# inlined because the whole ticket turns on telling them apart — the two exclusions
# rest on different arguments and have to be priced separately.
LOOKBACK_STALE = "12m"
LOOKBACK_BURST = "1w"
EXCLUDED_LOOKBACKS = (LOOKBACK_BURST, LOOKBACK_STALE)

# The width the detection gate ran at when this question was asked. **Pinned here,
# not read off** :data:`~screener.detection.DETECTION_LOOKBACKS`: this module is the
# evidence that settles what the live width should be, so it has to keep producing
# the same report after the decision moves the live value. A sweep whose baseline
# drifted with the constant it is arguing about could not be re-run to audit its own
# verdict.
GATE_AS_MEASURED: tuple[str, ...] = ("1m", "3m", "6m")


@dataclass(frozen=True)
class GateVariant:
    """One detection-gate width to price: a name and the lookbacks it unions.

    ``lookbacks`` is handed straight to :func:`screener.detection.detection_gate`,
    so a variant is the app's own gate under a different width — never a
    reimplementation of the top-decile test.
    """

    name: str
    lookbacks: tuple[str, ...]

    @property
    def added(self) -> tuple[str, ...]:
        """What this variant adds to the as-measured gate, in ``LOOKBACKS`` order."""
        return tuple(
            lb for lb in LOOKBACKS if lb in set(self.lookbacks) - set(GATE_AS_MEASURED)
        )


BASELINE_VARIANT = GateVariant("1m/3m/6m (as measured)", GATE_AS_MEASURED)

# The widths worth pricing. 3→5 is ADR 0003's candidate; the two four-lookback
# variants exist because #149 refuses to let the five-lookback set be adopted as
# one indivisible move — if the recovered trades come overwhelmingly through one
# of the excluded lookbacks, the honest options are the narrower widenings, each
# justified on its own evidence rather than on the union's headline.
GATE_VARIANTS: tuple[GateVariant, ...] = (
    BASELINE_VARIANT,
    GateVariant("+1w (burst)", GATE_AS_MEASURED + (LOOKBACK_BURST,)),
    GateVariant("+12m (stale)", GATE_AS_MEASURED + (LOOKBACK_STALE,)),
    GateVariant("five (3→5)", GATE_AS_MEASURED + EXCLUDED_LOOKBACKS),
)


# -- gate membership, per session, per single lookback ------------------------


# ``{session: {lookback: {symbols top-decile in it}}}`` — the substrate every
# figure here is read off. Built one lookback at a time so a variant's gate is a
# union of these sets *and* a recovered trade's admitting lookbacks are readable
# off the same structure, with no second definition of "top decile" anywhere.
GateMembership = Mapping[date, Mapping[str, set[str]]]


def gate_membership(ranks: list[Rank]) -> dict[str, set[str]]:
    """One session's top-decile set per lookback, via the app's own gate function.

    Each entry is :func:`screener.detection.detection_gate` restricted to a single
    lookback, so ``union(membership[lb] for lb in variant.lookbacks)`` is exactly
    the gate that variant would run — asserted, not assumed, by the seam test.
    """
    return {lb: detection_gate(ranks, lookbacks=(lb,)) for lb in LOOKBACKS}


def variant_gate(membership: Mapping[str, set[str]], variant: GateVariant) -> set[str]:
    """The variant's gate at one session — the union of its lookbacks' deciles."""
    gated: set[str] = set()
    for lb in variant.lookbacks:
        gated |= membership.get(lb, set())
    return gated


# -- the composition of the 75 ------------------------------------------------


@dataclass(frozen=True)
class RecoveredComposition:
    """The trades a widening recovers, split by *which* lookback admits them (#149).

    Every trade counted here fails the as-measured three-union gate, was present in the
    replayed field, and clears the five-union one — the ``recovered_by_five``
    bucket of :class:`replay.funnel.DecileDecomposition`, decomposed one level
    further.

    The four buckets are exclusive and exhaustive over ``total``:

    - ``stale_only`` — admitted by ``12m`` and nothing else: the *candidate* for
      §4.5's stale qualifier. Whether it is one is a separate question these counts
      cannot answer — see :func:`profile_recovered`, which asks what these names
      looked like on the windows the gate already unions.
    - ``burst_only`` — admitted by ``1w`` and nothing else: the momentum-burst
      candidate, on the same footing.
    - ``both_excluded`` — admitted by ``1w`` *and* ``12m``, by neither of the
      gate's own lookbacks.
    - ``also_gated`` — admitted by an excluded lookback *and* by one already in
      the gate. **Zero by construction** (such a name already clears the
      as-measured gate), and carried explicitly so that fact is visible in the
      output rather than assumed by the reader.

    ``continuation`` counts how many of ``total`` are continuation entries — adds
    to a running position, tagged and never dropped (PRD user story 5).
    """

    total: int
    stale_only: int
    burst_only: int
    both_excluded: int
    also_gated: int
    continuation: int

    @property
    def excluded_only(self) -> int:
        """Recovered *solely* by the two deliberately-excluded lookbacks."""
        return self.stale_only + self.burst_only + self.both_excluded

    def share(self, count: int) -> float:
        """``count`` as a share of the recovered trades, 0.0 when none were."""
        return count / self.total if self.total else 0.0


# Where a recovered trade sits on the lookbacks the gate **already** unions, and
# so whether it is really the qualifier the exclusion was written against. The
# spec's objection is not "12m admitted it" — it is "a name that topped out months
# ago and has done nothing since". A name admitted by 12m while still sitting in
# the upper reaches of 3m and 6m has not gone quiet in that sense; one below the
# field's median on every gated lookback has.
FIELD_MEDIAN = 0.50   # mid-pack on a lookback — the "has done nothing since" line
NEAR_DECILE = 0.80    # within reach of the cut the gate already applies


def baseline_pass(row: FunnelRow, membership: GateMembership) -> bool:
    """Whether ``row`` clears the **as-measured** three-union gate.

    Read off :func:`gate_membership` rather than off ``row.decile_pass``, which is
    the *live* gate and therefore moves the moment this study's verdict is adopted.
    Both are the app's own :func:`~screener.detection.detection_gate`; only the
    width differs.
    """
    if row.eval_session is None:
        return False
    per_lookback = membership.get(row.eval_session, {})
    return any(row.ticker in per_lookback.get(lb, set()) for lb in GATE_AS_MEASURED)


def recovered_rows(
    rows: Iterable[FunnelRow], membership: GateMembership
) -> list[FunnelRow]:
    """The decile misses a 3→5 widening would recover — present, outside the
    three-union gate, inside the five-union one.

    ``decile_present`` and ``decile_pass_five`` are the verdicts the funnel row
    carried straight off the app's gate functions; this never re-derives a decile
    verdict from a percentile (the trap #133 calls out).
    """
    return [
        r
        for r in rows
        if not baseline_pass(r, membership) and r.decile_present and r.decile_pass_five
    ]


def admitting_lookbacks(row: FunnelRow, membership: GateMembership) -> set[str]:
    """Which lookbacks had ``row``'s ticker top-decile at its evaluation session."""
    per_lookback = membership.get(row.eval_session, {}) if row.eval_session else {}
    return {lb for lb, gated in per_lookback.items() if row.ticker in gated}


# The four admitting-lookback groups a recovered trade can fall into. Exclusive and
# exhaustive, and named once because both the count decomposition and the profile
# read the same split — two hand-rolled copies of it would be free to disagree
# about which group a trade belongs to.
GROUP_STALE_ONLY = f"{LOOKBACK_STALE} only"
GROUP_BURST_ONLY = f"{LOOKBACK_BURST} only"
GROUP_BOTH = "both"
GROUP_ALSO_GATED = "also gated"


def group_recovered(
    rows: Iterable[FunnelRow], membership: GateMembership
) -> dict[str, list[FunnelRow]]:
    """Split the recovered decile misses by which lookback admits each of them."""
    groups: dict[str, list[FunnelRow]] = {
        GROUP_STALE_ONLY: [], GROUP_BURST_ONLY: [], GROUP_BOTH: [], GROUP_ALSO_GATED: [],
    }
    for row in recovered_rows(rows, membership):
        admitting = admitting_lookbacks(row, membership)
        if admitting & set(GATE_AS_MEASURED):
            groups[GROUP_ALSO_GATED].append(row)
        elif LOOKBACK_STALE in admitting and LOOKBACK_BURST in admitting:
            groups[GROUP_BOTH].append(row)
        elif LOOKBACK_STALE in admitting:
            groups[GROUP_STALE_ONLY].append(row)
        else:
            groups[GROUP_BURST_ONLY].append(row)
    return groups


def flatten_groups(groups: Mapping[str, list[FunnelRow]]) -> list[FunnelRow]:
    """Every recovered trade across the admitting-lookback groups, as one list."""
    return [row for rs in groups.values() for row in rs]


def decompose_recovered(
    rows: Iterable[FunnelRow], membership: GateMembership
) -> RecoveredComposition:
    """Split the recovered decile misses by their admitting lookback (#149).

    This is the ticket's headline. A widening whose recovered trades arrive through
    ``3m``/``6m`` adjacency is a different proposition from one that arrives through
    ``12m`` staleness, and ADR 0003's single number cannot tell them apart.
    """
    groups = group_recovered(rows, membership)
    recovered = flatten_groups(groups)
    return RecoveredComposition(
        total=len(recovered),
        stale_only=len(groups[GROUP_STALE_ONLY]),
        burst_only=len(groups[GROUP_BURST_ONLY]),
        both_excluded=len(groups[GROUP_BOTH]),
        also_gated=len(groups[GROUP_ALSO_GATED]),
        continuation=sum(1 for row in recovered if row.continuation),
    )


@dataclass(frozen=True)
class AdmittedGroup:
    """One admitting-lookback group of the recovered trades, profiled against the
    lookbacks the as-measured gate already unions (#149).

    The bucket counts alone cannot settle the §4.5 objection. "Admitted by ``12m``"
    is not the same claim as "topped out months ago and has done nothing since" —
    the second is what the exclusion was written against, and it is a statement
    about the name's *recent* ranks, not about which lookback let it in. So each
    group carries where its trades sat on ``1m``/``3m``/``6m`` at the evaluation
    session, off the per-lookback margins the funnel row already records (#133):

    - ``dead_on_gated`` — below :data:`FIELD_MEDIAN` on **every** gated lookback.
      This is the stale (or burst) qualifier as the spec describes it, counted.
    - ``within_reach`` — at or above :data:`NEAR_DECILE` on at least one gated
      lookback: a name the as-measured gate very nearly admitted on its own terms.
    - ``median_percentiles`` — the group's median percentile per lookback.
    """

    label: str
    n: int
    dead_on_gated: int
    within_reach: int
    median_percentiles: Mapping[str, float]


def _group_profile(label: str, rows: Sequence[FunnelRow]) -> AdmittedGroup:
    def best_gated(row: FunnelRow) -> float:
        return max(
            (row.eval_percentiles.get(lb, 0.0) for lb in GATE_AS_MEASURED),
            default=0.0,
        )

    medians = {}
    for lb in LOOKBACKS:
        values = [r.eval_percentiles[lb] for r in rows if lb in r.eval_percentiles]
        if values:
            medians[lb] = statistics.median(values)
    return AdmittedGroup(
        label=label,
        n=len(rows),
        dead_on_gated=sum(1 for r in rows if best_gated(r) < FIELD_MEDIAN),
        within_reach=sum(1 for r in rows if best_gated(r) >= NEAR_DECILE),
        median_percentiles=medians,
    )


def profile_recovered(
    rows: Iterable[FunnelRow], membership: GateMembership
) -> tuple[AdmittedGroup, ...]:
    """Profile each admitting-lookback group against the gate's own lookbacks (#149).

    Answers the question the bucket counts raise but cannot settle: of the trades a
    widening recovers through an excluded lookback, how many are the stale or burst
    qualifiers the exclusion exists to keep out, and how many are simply names the
    as-measured gate came close to admitting anyway.
    """
    groups = group_recovered(rows, membership)
    return tuple(_group_profile(label, rs) for label, rs in groups.items() if rs)


# -- outcome quality of the recovered trades ----------------------------------


# R in this trade record is fat-tailed — every group's median R is −1.00 and the
# return lives in a handful of names — so a group's mean is a statement about its
# best trade unless it is read beside a trimmed mean and a tail rate.
TRIM_FRACTION = 0.05   # share of the group dropped from the top before re-meaning
BIG_WIN_R = 3.0        # the tail a breakout method is actually trading for


@dataclass(frozen=True)
class OutcomeQuality:
    """Realised outcome for one group of executed trades (#149).

    Reported so a recall gain is never read as a gain in *quality*: if the trades a
    widening recovers run materially worse than the ones the gate already passes,
    the recovered count is buying less than it looks like.

    **R is fat-tailed here, so the mean alone decides nothing.** Every group in this
    study has a median R of −1.00 — the method stops out most of the time and earns
    in the tail — which makes ``mean_r`` a statement about one or two names. Four
    robust figures are carried beside it, and the comparison between groups is meant
    to be read off these:

    - ``trimmed_mean_r`` — the mean after dropping the top :data:`TRIM_FRACTION` of
      the group by R. A *fraction*, not a count, so groups of very different sizes
      are trimmed comparably.
    - ``win_rate`` — the share with positive R.
    - ``big_win_rate`` — the share reaching :data:`BIG_WIN_R`, where a breakout
      method's whole edge lives.
    - ``top_trade_r_share`` — how much of the group's total R its single best trade
      supplies. A group whose figure is near 1 has no measured central tendency
      worth quoting.

    Figures are ``None`` when no trade in the group carries an outcome.
    """

    label: str
    n: int
    n_with_r: int
    mean_r: float | None
    median_r: float | None
    trimmed_mean_r: float | None
    win_rate: float | None
    big_win_rate: float | None
    top_trade_r_share: float | None
    mean_mfe: float | None


def outcome_quality(
    label: str,
    rows: Iterable[FunnelRow],
    trades: Mapping[tuple[str, date], ExecutedTrade],
) -> OutcomeQuality:
    """Realised R and win rate for the trades behind ``rows``.

    ``trades`` is keyed ``(ticker, entry_date)`` — the identity of an executed
    trade. A row with no matching outcome is counted in ``n`` and excluded from the
    averages, so the group's size is never quietly shrunk to the rows that happened
    to carry a result.
    """
    rows = list(rows)
    rs: list[float] = []
    mfes: list[float] = []
    for row in rows:
        trade = trades.get((row.ticker, row.entry_date))
        if trade is None:
            continue
        if trade.r is not None:
            rs.append(trade.r)
        primary = trade.primary
        if primary is not None and primary.mfe_pct is not None:
            mfes.append(primary.mfe_pct)
    ordered = sorted(rs)
    drop = math.ceil(TRIM_FRACTION * len(ordered)) if ordered else 0
    trimmed = ordered[: len(ordered) - drop] if ordered else []
    total_r = sum(rs)
    return OutcomeQuality(
        label=label,
        n=len(rows),
        n_with_r=len(rs),
        mean_r=statistics.fmean(rs) if rs else None,
        median_r=statistics.median(rs) if rs else None,
        trimmed_mean_r=statistics.fmean(trimmed) if trimmed else None,
        win_rate=sum(1 for r in rs if r > 0) / len(rs) if rs else None,
        big_win_rate=sum(1 for r in rs if r >= BIG_WIN_R) / len(rs) if rs else None,
        top_trade_r_share=(max(rs) / total_r if rs and total_r > 0 else None),
        mean_mfe=statistics.fmean(mfes) if mfes else None,
    )


# -- the per-session pass every variant is measured against -------------------


@dataclass(frozen=True)
class SweepSession:
    """One measured session, prepared once for every variant.

    ``detections`` is the detector's output over the **widest** gate swept, so a
    variant's field is a filter of it rather than a second detection pass:
    detection geometry does not depend on the gate, only on which members reach
    :func:`screener.detection.detect`. ``membership`` is that session's per-lookback
    top-decile sets.
    """

    session: date
    members: list[str]
    ranks: list[Rank]
    membership: dict[str, set[str]]
    detections: list[Detection]


def build_sweep_sessions(
    store: Store,
    market: str,
    sessions: Sequence[date],
    *,
    lookbacks: Sequence[str],
    progress: Callable[[int, int, date], None] | None = None,
) -> list[SweepSession]:
    """Reconstruct each session's universe, ranks and widest-gate detections.

    **Read-only.** Membership is read from the universe rows the replay store
    already holds and the rank table is recomputed in memory — the same pair
    :func:`replay.chain._replay_session` returns when it reuses a session, so the
    reconstruction is the chain's own reuse path with nothing written back. The
    detector then runs over the union gate ``lookbacks`` describes.

    ``progress`` is called as ``progress(i, total, session)`` after each session, so
    a long pass reports rather than hanging silently.
    """
    store = CachingStore.wrap(store)
    total = len(sessions)
    out: list[SweepSession] = []
    for i, session in enumerate(sessions, start=1):
        members = store.universe(market, session)
        bars = {symbol: store.bars(market, symbol) for symbol in members}
        ranks = rank_table(bars, session)
        membership = gate_membership(ranks)
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
                membership=membership,
                detections=detections,
            )
        )
        if progress is not None:
            progress(i, total, session)
    return out


def session_fields(
    sessions: Sequence[SweepSession], blind_spot_count: int
) -> list[SessionField]:
    """The sweep's sessions as a chain, so the funnel can be walked over the same pass."""
    return [
        SessionField(
            session=s.session,
            burn_in=False,
            members=s.members,
            ranks=s.ranks,
            blind_spot_count=blind_spot_count,
        )
        for s in sessions
    ]


# -- one variant, measured ----------------------------------------------------


@dataclass(frozen=True)
class VariantMeasurement:
    """Everything #149 asks to be reported at one gate width.

    ``gate_population_share`` is the share of the universe the gate admits, averaged
    over the measured sessions — the gate's *cost* in ADR 0003's own currency.
    ``decile_recall`` is the share of replayable trades clearing this gate;
    ``surfaced_recall`` is the share clearing it **and** the detector, which is what
    the app would actually have shown. Detection recall on its own is gate-invariant
    (the funnel evaluates every stage unconditionally), so it is not restated per
    variant.

    ``field_detections`` is the total detections emitted across the measured
    sessions — the **field inflation** figure, priced as volume because precision is
    unmeasurable (findings §7, §9). ``field_detections_on_trade_sessions`` is the
    same count restricted to the sessions an executed trade was evaluated at, which
    is the basis A2's star distribution uses; both are carried because the two are
    easy to mistake for each other and differ by more than 4×. ``board_displacement`` counts how many
    baseline top-``board_size`` places are taken by names this variant admits,
    summed over sessions; ``picks_in_field`` and ``picks_on_board`` are his own
    entries' counts under this width — his ticker appearing in that session's
    field at all, and inside the top ``board_size`` of it. ``picks_in_field`` tracks
    ``surfaced_recall`` closely and is not a second reading of it: the recall figure
    asks whether the detector fires on the trade's own bars, while this one asks
    whether the name reached the *field*, which additionally requires it to have been
    a universe member that session. They diverge exactly on the coverage gap.
    """

    variant: GateVariant
    sessions: int
    gate_population_share: float
    decile_recall: StageRecall
    surfaced_recall: StageRecall
    field_detections: int
    field_detections_on_trade_sessions: int
    added_detections_stale: int
    added_detections_total: int
    board_displacement: int
    picks_in_field: int
    picks_on_board: int

    @property
    def detections_per_surfaced_entry(self) -> float | None:
        """The width's own exchange rate: detections shown per entry surfaced.

        The denominator every marginal ratio has to be read against. A widening
        whose *marginal* cost per entry sits near the funnel's *average* cost is not
        degrading the funnel — it is buying at the going rate.
        """
        n = self.surfaced_recall.passed
        return self.field_detections / n if n else None

    @property
    def added_stale_share(self) -> float | None:
        """Share of the detections this width adds that are stale by §4.5's own test.

        A name below :data:`FIELD_MEDIAN` on **every** lookback the as-measured gate unions
        — mid-pack or worse on 1m, 3m and 6m — reaching the field only because a
        wider gate admitted it. This is the exclusion's worry measured against the
        *field*, not against his trades: a widening can leave his recovered entries
        looking healthy while flooding the list with names that topped out long ago.
        """
        n = self.added_detections_total
        return self.added_detections_stale / n if n else None


def _gated_percentiles(ranks: list[Rank]) -> dict[str, float]:
    """Each symbol's **best** percentile across the as-measured gate's lookbacks.

    The one number that says how strong a name is on the gate's own terms, so a name
    the wider gate admitted can be asked whether the as-measured gate had any reason to
    want it.
    """
    best: dict[str, float] = {}
    gated = set(GATE_AS_MEASURED)
    for r in ranks:
        if r.lookback in gated:
            best[r.symbol] = max(best.get(r.symbol, 0.0), r.percentile)
    return best


def measure_variant(
    variant: GateVariant,
    sessions: Sequence[SweepSession],
    rows: Sequence[FunnelRow],
    *,
    baseline_boards: Mapping[date, list[str]] | None = None,
    baseline_gates: Mapping[date, set[str]] | None = None,
    board_size: int = BOARD_SIZE,
) -> tuple[VariantMeasurement, dict[date, list[str]], dict[date, set[str]]]:
    """Measure one gate width over the prepared pass.

    Returns the measurement, this variant's per-session board and its per-session
    gate, so the baseline's pair can be handed back in to price displacement and the
    added field against it — without a second pass over the sessions.
    """
    gates = {s.session: variant_gate(s.membership, variant) for s in sessions}
    universe = sum(len(s.members) for s in sessions)
    gated_total = sum(len(g) for g in gates.values())

    field_detections = 0
    boards: dict[date, list[str]] = {}
    in_field = on_board = 0
    # Counted per *trade*, as A2 counts a placement — the same ticker entered twice
    # off one session is two placements, not one (:mod:`replay.placement`).
    picks_by_session: dict[date, list[FunnelRow]] = {}
    for row in rows:
        if row.eval_session is not None:
            picks_by_session.setdefault(row.eval_session, []).append(row)

    added_stale = added_total = 0
    on_trade_sessions = 0
    for s in sessions:
        gate = gates[s.session]
        detections = [d for d in s.detections if d.symbol in gate]
        field_detections += len(detections)
        if s.session in picks_by_session:
            on_trade_sessions += len(detections)
        if baseline_gates is not None:
            base_gate = baseline_gates.get(s.session, set())
            added = [d for d in detections if d.symbol not in base_gate]
            added_total += len(added)
            percentiles = _gated_percentiles(s.ranks)
            added_stale += sum(
                1 for d in added if percentiles.get(d.symbol, 0.0) < FIELD_MEDIAN
            )
        scored = build_field(detections, s.ranks, lookbacks=variant.lookbacks)
        board = [d.symbol for d in scored[:board_size]]
        boards[s.session] = board
        present = {d.symbol for d in scored}
        for row in picks_by_session.get(s.session, ()):
            in_field += row.ticker in present
            on_board += row.ticker in set(board)

    displacement = 0
    if baseline_boards is not None:
        for session, board in boards.items():
            base = set(baseline_boards.get(session, ()))
            displacement += sum(1 for symbol in board if symbol not in base)

    def gate_pass(row: FunnelRow) -> bool:
        if row.eval_session is None:
            return False
        return row.ticker in gates.get(row.eval_session, set())

    measurement = VariantMeasurement(
        variant=variant,
        sessions=len(sessions),
        gate_population_share=gated_total / universe if universe else 0.0,
        decile_recall=stage_recall("decile", rows, gate_pass),
        surfaced_recall=stage_recall(
            "surfaced", rows, lambda r: gate_pass(r) and r.detection_pass
        ),
        field_detections=field_detections,
        field_detections_on_trade_sessions=on_trade_sessions,
        added_detections_stale=added_stale,
        added_detections_total=added_total,
        board_displacement=displacement,
        picks_in_field=in_field,
        picks_on_board=on_board,
    )
    return measurement, boards, gates


# -- the whole sweep ----------------------------------------------------------


@dataclass(frozen=True)
class Inflation:
    """What one variant costs, per real entry it recovers (#141's basis, #149's mirror).

    ``added_detections`` is the extra field volume over the baseline width across
    the measured sessions; ``recovered_entries`` is the extra executed trades the
    wider gate lets through the decile stage, and ``surfaced_entries`` the extra
    that also clear the detector — the ones the app would truly have shown.

    ``per_recovered_entry`` is the ticket's price tag: **added detections per real
    entry recovered**. It is a *volume* ratio and never a false-positive rate — the
    added names carry no verdict, they are simply names he may never have seen
    (findings §7, §9).
    """

    added_detections: int
    recovered_entries: int
    surfaced_entries: int

    @property
    def per_recovered_entry(self) -> float | None:
        """Added detections per executed trade this width lets through the decile
        stage — #149's headline price. ``None`` when it recovers none."""
        n = self.recovered_entries
        return self.added_detections / n if n else None

    @property
    def per_surfaced_entry(self) -> float | None:
        """Added detections per executed trade this width would actually have put in
        front of the trader — the decile gain that also clears the detector."""
        n = self.surfaced_entries
        return self.added_detections / n if n else None


@dataclass(frozen=True)
class GateSweep:
    """The #149 measurement: every gate width priced against the as-measured one.

    ``composition`` is the headline — the recovered trades split by admitting
    lookback. ``outcomes`` pairs the recovered group with the group the as-measured gate
    already passes, so the recall gain is read against its quality. ``variants``
    and ``inflation`` carry the per-width figures, the baseline first.
    """

    market: str
    sessions: int
    first_session: date | None
    last_session: date | None
    replayable_trades: int
    blind_spot_count: int
    detection_recall: StageRecall
    composition: RecoveredComposition
    profile: tuple[AdmittedGroup, ...]
    outcomes: tuple[OutcomeQuality, ...]
    variants: tuple[VariantMeasurement, ...]
    inflation: Mapping[str, Inflation]

    @property
    def baseline(self) -> VariantMeasurement:
        """The width every other one is priced against — :data:`GATE_AS_MEASURED`."""
        return self.variants[0]


def sweep_gates(
    sessions: Sequence[SweepSession],
    rows: Sequence[FunnelRow],
    trades: Mapping[tuple[str, date], ExecutedTrade],
    *,
    market: str = REPLAY_MARKET,
    variants: Sequence[GateVariant] = GATE_VARIANTS,
    blind_spot_count: int = 0,
    board_size: int = BOARD_SIZE,
) -> GateSweep:
    """Price every gate width in ``variants`` against the first one (the baseline).

    The baseline is ``variants[0]`` — its board is what displacement is measured
    against and its field volume is what inflation is measured from.
    """
    rows = list(rows)
    membership = {s.session: s.membership for s in sessions}

    measurements: list[VariantMeasurement] = []
    baseline_boards: dict[date, list[str]] | None = None
    baseline_gates: dict[date, set[str]] | None = None
    for variant in variants:
        measurement, boards, gates = measure_variant(
            variant, sessions, rows,
            baseline_boards=baseline_boards,
            baseline_gates=baseline_gates,
            board_size=board_size,
        )
        if baseline_boards is None:
            baseline_boards, baseline_gates = boards, gates
        measurements.append(measurement)

    base = measurements[0]
    inflation = {
        m.variant.name: Inflation(
            added_detections=m.field_detections - base.field_detections,
            recovered_entries=m.decile_recall.passed - base.decile_recall.passed,
            surfaced_entries=m.surfaced_recall.passed - base.surfaced_recall.passed,
        )
        for m in measurements[1:]
    }

    groups = group_recovered(rows, membership)
    recovered = flatten_groups(groups)
    passing = [r for r in rows if baseline_pass(r, membership)]
    return GateSweep(
        market=market,
        sessions=len(sessions),
        first_session=sessions[0].session if sessions else None,
        last_session=sessions[-1].session if sessions else None,
        replayable_trades=len(rows),
        blind_spot_count=blind_spot_count,
        detection_recall=stage_recall("detection", rows, lambda r: r.detection_pass),
        composition=decompose_recovered(rows, membership),
        profile=profile_recovered(rows, membership),
        # The recovered group whole, then split by admitting lookback, against the
        # group the as-measured gate already passes. The split is what decides between the
        # two narrower widenings if 3→5 itself does not stand.
        outcomes=(
            outcome_quality("recovered by 3→5", recovered, trades),
            *(
                outcome_quality(f"…{label}", rs, trades)
                for label, rs in groups.items()
                if rs
            ),
            outcome_quality("passing 1m/3m/6m", passing, trades),
        ),
        variants=tuple(measurements),
        inflation=inflation,
    )


# -- human-readable report ----------------------------------------------------


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1%}"


def _num(value: float | None, places: int = 2) -> str:
    return "—" if value is None else f"{value:.{places}f}"


def _format_composition(comp: RecoveredComposition) -> str:
    lines = [
        f"recovered by widening 3→5: {comp.total} trades "
        f"({comp.continuation} of them continuation entries)",
        "",
        "  admitted by                          count   share",
        f"  12m only (excluded as stale)       {comp.stale_only:6d}  "
        f"{_pct(comp.share(comp.stale_only))}",
        f"  1w only (excluded as a burst)      {comp.burst_only:6d}  "
        f"{_pct(comp.share(comp.burst_only))}",
        f"  both 1w and 12m                     {comp.both_excluded:6d}  "
        f"{_pct(comp.share(comp.both_excluded))}",
        f"  also by a lookback already gated    {comp.also_gated:6d}  "
        f"{_pct(comp.share(comp.also_gated))}",
        "",
        f"  recovered solely by the two excluded lookbacks: {comp.excluded_only}"
        f" ({_pct(comp.share(comp.excluded_only))})",
    ]
    return "\n".join(lines)


def _recall_line(recall: StageRecall) -> str:
    """One stage's recall, headline and ex-continuation on the same line (§6)."""
    return (
        f"{recall.passed}/{recall.total} ({_pct(recall.recall)})   "
        f"ex-continuation: {recall.passed_ex_continuation}/"
        f"{recall.total_ex_continuation} ({_pct(recall.recall_ex_continuation)})"
    )


def _format_profile(groups: Sequence[AdmittedGroup]) -> str:
    header = (
        "admitted by       n   dead on 1m/3m/6m   within reach   "
        + "  ".join(f"med {lb:>4}" for lb in LOOKBACKS)
    )
    lines = [header]
    for g in groups:
        medians = "  ".join(
            f"{g.median_percentiles.get(lb, float('nan')):8.3f}" for lb in LOOKBACKS
        )
        lines.append(
            f"{g.label:<15} {g.n:3d}   {g.dead_on_gated:16d}   {g.within_reach:12d}   {medians}"
        )
    lines.append("")
    lines.append(
        "`dead on 1m/3m/6m` is below the field median on every lookback the "
        "as-measured gate unions —\nthe stale (or burst) qualifier as §4.5 describes it. "
        "`within reach` is at or above the 80th\npercentile on one of them: a name "
        "the as-measured gate nearly admitted on its own terms."
    )
    return "\n".join(lines)


def _format_outcomes(outcomes: Sequence[OutcomeQuality]) -> str:
    lines = [
        "group                    n   mean R   trim5% R   median R   win rate   "
        "R>=3 rate   best trade's share of R   mean MFE%"
    ]
    for o in outcomes:
        lines.append(
            f"{o.label:<22} {o.n:4d}   {_num(o.mean_r):>6}   {_num(o.trimmed_mean_r):>8}   "
            f"{_num(o.median_r):>8}   {_pct(o.win_rate):>8}   {_pct(o.big_win_rate):>9}   "
            f"{_pct(o.top_trade_r_share):>23}   {_num(o.mean_mfe, 1):>9}"
        )
    lines.append("")
    lines.append(
        "Median R is −1.00 in every group — the method stops out most of the time "
        "and earns in\nthe tail — so read the trimmed mean and the R>=3 rate, not "
        "the mean. A group whose best\ntrade supplies most of its R has no central "
        "tendency worth quoting."
    )
    return "\n".join(lines)


def _format_variants(sweep: GateSweep) -> str:
    lines = [
        f"{'gate width':<22} universe   decile recall (ex-cont)      "
        "surfaced recall (ex-cont)     field    in-field   on board",
    ]
    for m in sweep.variants:
        d, s = m.decile_recall, m.surfaced_recall
        lines.append(
            f"{m.variant.name:<22} {_pct(m.gate_population_share):>8}   "
            f"{d.passed:3d}/{d.total} ({_pct(d.recall)})  ({_pct(d.recall_ex_continuation)})   "
            f"{s.passed:3d}/{s.total} ({_pct(s.recall)})  ({_pct(s.recall_ex_continuation)})  "
            f"{m.field_detections:8d}    {m.picks_in_field:5d}    {m.picks_on_board:5d}"
        )
    return "\n".join(lines)


def _format_inflation(sweep: GateSweep) -> str:
    base = sweep.baseline
    lines = [
        f"baseline field: {base.field_detections} detections over {base.sessions} "
        f"measured sessions,",
        f"                {base.field_detections_on_trade_sessions} of them on the "
        f"sessions his trades were evaluated at (A2's basis),",
        f"                {_num(base.detections_per_surfaced_entry, 1)} detections "
        f"per entry surfaced — the funnel's own going rate.",
        "",
        f"{'gate width':<22} added detections   recovered entries   per entry   "
        "surfaced   per surfaced   vs going rate   board displacement   stale share of added",
    ]
    for m in sweep.variants[1:]:
        inf = sweep.inflation[m.variant.name]
        going = base.detections_per_surfaced_entry
        marginal = inf.per_surfaced_entry
        ratio = (
            f"{marginal / going:.2f}x" if marginal is not None and going else "—"
        )
        lines.append(
            f"{m.variant.name:<22} {inf.added_detections:16d}   {inf.recovered_entries:17d}   "
            f"{_num(inf.per_recovered_entry, 1):>9}   {inf.surfaced_entries:8d}   "
            f"{_num(inf.per_surfaced_entry, 1):>12}   {ratio:>13}   {m.board_displacement:18d}   "
            f"{_pct(m.added_stale_share):>20}"
        )
    lines.append("")
    lines.append(
        "Field inflation is a volume measure, not a false-positive rate: the added "
        "names carry\nno verdict (findings §7, §9). `vs going rate` divides the "
        "width's marginal cost per\nsurfaced entry by the baseline's average one — "
        "a widening at 1.0x is buying entries at\nexactly the price the funnel "
        "already pays. `stale share of added` is the share of the\ndetections the "
        "width adds that sit below the field median on every lookback the\nas-measured "
        "gate unions: §4.5's worry, measured against the field rather than against his "
        "trades.\nBoard displacement counts board places taken by names the wider "
        "gate admits, summed\nover the measured sessions."
    )
    return "\n".join(lines)


def format_report(sweep: GateSweep) -> str:
    """The #149 report: composition first, then the per-width price."""
    window = (
        f"{sweep.first_session} to {sweep.last_session}"
        if sweep.first_session
        else "no sessions"
    )
    return "\n".join(
        [
            f"detection-gate width sweep ({sweep.market}) — #149",
            f"sessions: {sweep.sessions} measured ({window})",
            f"replayable trades: {sweep.replayable_trades}   "
            f"blind-spot coverage: {sweep.blind_spot_count} tickers missing from the field",
            f"detection recall (gate-invariant): {_recall_line(sweep.detection_recall)}",
            "",
            "== composition of the recovered misses (the headline) ==",
            _format_composition(sweep.composition),
            "",
            "== where the recovered trades sat on the gate's own lookbacks ==",
            _format_profile(sweep.profile),
            "",
            "== outcome quality of the recovered trades ==",
            _format_outcomes(sweep.outcomes),
            "",
            "== the gate widths ==",
            _format_variants(sweep),
            "",
            "== field inflation, priced as #141 prices the cluster gate ==",
            _format_inflation(sweep),
            "",
            "Scope: US 2019–2022, a once-in-a-decade momentum regime. No figure here "
            "is an IDX\nexpectation.",
        ]
    )


# -- machine-readable results -------------------------------------------------


def _outcome_dict(o: OutcomeQuality) -> dict:
    return {
        "label": o.label,
        "n": o.n,
        "n_with_r": o.n_with_r,
        "mean_r": o.mean_r,
        "median_r": o.median_r,
        "trimmed_mean_r": o.trimmed_mean_r,
        "win_rate": o.win_rate,
        "big_win_rate": o.big_win_rate,
        "top_trade_r_share": o.top_trade_r_share,
        "mean_mfe_pct": o.mean_mfe,
    }


def _recall_dict(r: StageRecall) -> dict:
    return {
        "passed": r.passed,
        "total": r.total,
        "recall": r.recall,
        "passed_ex_continuation": r.passed_ex_continuation,
        "total_ex_continuation": r.total_ex_continuation,
        "recall_ex_continuation": r.recall_ex_continuation,
    }


def _inflation_dict(inflation: Inflation | None) -> dict | None:
    """One width's cost, or ``None`` for the baseline, which adds nothing to itself."""
    if inflation is None:
        return None
    return {
        "added_detections": inflation.added_detections,
        "recovered_entries": inflation.recovered_entries,
        "surfaced_entries": inflation.surfaced_entries,
        "added_detections_per_recovered_entry": inflation.per_recovered_entry,
        "added_detections_per_surfaced_entry": inflation.per_surfaced_entry,
    }


def sweep_to_dict(sweep: GateSweep) -> dict:
    """A JSON-serialisable dict of every figure the sweep reports."""
    comp = sweep.composition
    return {
        "market": sweep.market,
        "sessions": sweep.sessions,
        "first_session": sweep.first_session.isoformat() if sweep.first_session else None,
        "last_session": sweep.last_session.isoformat() if sweep.last_session else None,
        "replayable_trades": sweep.replayable_trades,
        "blind_spot_count": sweep.blind_spot_count,
        "detection_recall": _recall_dict(sweep.detection_recall),
        "composition": {
            "total": comp.total,
            "stale_only_12m": comp.stale_only,
            "burst_only_1w": comp.burst_only,
            "both_excluded": comp.both_excluded,
            "also_gated": comp.also_gated,
            "excluded_only": comp.excluded_only,
            "continuation": comp.continuation,
        },
        "recovered_profile": [
            {
                "label": g.label,
                "n": g.n,
                "dead_on_gated_lookbacks": g.dead_on_gated,
                "within_reach_of_the_gate": g.within_reach,
                "median_percentiles": dict(g.median_percentiles),
            }
            for g in sweep.profile
        ],
        "outcomes": [_outcome_dict(o) for o in sweep.outcomes],
        "variants": [
            {
                "name": m.variant.name,
                "lookbacks": list(m.variant.lookbacks),
                "added_lookbacks": list(m.variant.added),
                "gate_population_share": m.gate_population_share,
                "decile_recall": _recall_dict(m.decile_recall),
                "surfaced_recall": _recall_dict(m.surfaced_recall),
                "field_detections": m.field_detections,
                "field_detections_on_trade_sessions": m.field_detections_on_trade_sessions,
                "detections_per_surfaced_entry": m.detections_per_surfaced_entry,
                "added_detections_total": m.added_detections_total,
                "added_detections_stale": m.added_detections_stale,
                "added_stale_share": m.added_stale_share,
                "board_displacement": m.board_displacement,
                "picks_in_field": m.picks_in_field,
                "picks_on_board": m.picks_on_board,
                "inflation": _inflation_dict(sweep.inflation.get(m.variant.name)),
            }
            for m in sweep.variants
        ],
        "precision_note": (
            "Field inflation is a volume measure, never a false-positive rate: the "
            "reference set records no setup he declined, so there is no control group "
            "(findings §7, §9)."
        ),
    }


# -- the runnable measurement -------------------------------------------------


def run_gate_sweep(
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    trades: list[ExecutedTrade],
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
    variants: Sequence[GateVariant] = GATE_VARIANTS,
    progress: Callable[[int, int, date], None] | None = None,
) -> GateSweep:
    """Run the whole #149 measurement over one read-only pass of the replay store.

    Reconstructs the forward pass (universe from the store, ranks in memory),
    detects once over the union of every swept gate, walks the funnel over the same
    pass so the decile verdicts and the sweep read the identical field, and prices
    each width against the as-measured one.
    """
    store = CachingStore.wrap(store)
    classified = classify(trades, store, market=market)
    calendar = store.sessions(market)
    measured = list(sessions) if sessions is not None else calendar[burn_in:]
    union = tuple(lb for lb in LOOKBACKS if any(lb in v.lookbacks for v in variants))

    swept = build_sweep_sessions(
        store, market, measured, lookbacks=union, progress=progress
    )
    blind_spots = set(blind_spot_tickers)
    chain = session_fields(swept, len(blind_spots))
    funnel = build_funnel_report(
        classified, calendar, chain, store, market, blind_spot_tickers=blind_spots
    )
    by_identity = {(t.ticker, t.entry_date): t for t in trades}
    return sweep_gates(
        swept,
        funnel.rows,
        by_identity,
        market=market,
        variants=variants,
        blind_spot_count=len(blind_spots),
    )


def _sweep_progress(stream) -> Callable[[int, int, date], None]:
    """The study's throttled progress printer, bound to this sweep's one phase."""
    report = progress_printer(stream)
    return lambda i, total, session: report("sweep", i, total, session)


def write_report(sweep: GateSweep, path: str | Path) -> None:
    """Write the human-readable sweep report to ``path``."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(format_report(sweep) + "\n")


def write_results(sweep: GateSweep, path: str | Path) -> None:
    """Write the machine-readable sweep results to ``path`` (stable, 2-space JSON)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sweep_to_dict(sweep), indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    """Price the detection gate's width against the replay store (#149).

        python -m replay.gate_sweep --store data/replay.duckdb \\
            --out-report references/detection_gate_sweep.txt \\
            --out-json references/detection_gate_sweep.json

    Read-only: the pass reconstructs universe membership from the rows the replay
    store already holds and recomputes ranks in memory, writing nothing back.
    Progress and an ETA print to stderr while it runs.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--blind-spots", default=str(DEFAULT_BLIND_SPOT_OUT),
                        help="path to the committed blind-spot ticker list")
    parser.add_argument("--market", default=REPLAY_MARKET)
    parser.add_argument("--burn-in", type=int, default=BURN_IN_SESSIONS,
                        help="burn-in sessions before the first measured session")
    parser.add_argument("--out-report", default="references/detection_gate_sweep.txt",
                        help="where to write the human-readable report")
    parser.add_argument("--out-json", default="references/detection_gate_sweep.json",
                        help="where to write the machine-readable results")
    args = parser.parse_args(argv)

    trades = load_trades(args.reference)
    blind_spots = json.loads(Path(args.blind_spots).read_text())
    store = Store.open(args.store)
    try:
        sweep = run_gate_sweep(
            store,
            args.market,
            trades=trades,
            blind_spot_tickers=blind_spots,
            burn_in=args.burn_in,
            progress=_sweep_progress(sys.stderr),
        )
    finally:
        store.close()

    write_report(sweep, args.out_report)
    write_results(sweep, args.out_json)
    print(format_report(sweep))
    print(f"\nwrote {args.out_report}")
    print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
