"""A1, the funnel/recall study: liquidity, decile and detection (PRD #114,
tickets #116, #119).

The three funnel stages, evaluated for every *replayable* executed trade at the
session **strictly before** its entry date — the night the app would have had to
name the stock while the entry was still ahead of the trader (PRD user story 3).
For each trade the study records whether it clears the liquidity floor, whether
it sits in the top decile of that night's *replayed field*, and whether the app's
detector fires on it — all unmodified.

**Three stages, in the app's funnel order.** The funnel the app runs has three
ordered gates — liquidity, decile, detection (:data:`FUNNEL_STAGES`) — and A1 now
reports all three (ticket #119 folds in the decile stage that #116 left absent).
The decile gate is cross-sectional: it needs that night's replayed field to rank
against, so the funnel runs the A2 forward chain (:func:`replay.chain.replay_chain`)
to reconstruct universe membership and ranks per session, then reads each trade's
decile result off the chain's ranks at its evaluation session. Because the decile
depends on the replayed field's population, every decile-dependent output carries
a coverage number against the blind-spot tickers (:attr:`FunnelReport.blind_spot_count`,
PRD user story 22).

**Absent from the field is distinguished from outside the decile.** A trade whose
ticker is not a universe member at the evaluation session was *absent from the
field* (:attr:`FunnelRow.decile_present` is ``False``) — a coverage gap, not a
ranking verdict — and is kept apart from a ticker that was present but ranked
outside the top decile (present, ``decile_pass`` ``False``).

**Detection failures name a geometric condition.** The app's :func:`detect` is a
black box that returns a base or ``None``; a bare "detection failed" would point
at the detector in general rather than at the gate that actually cost the trade.
So on a miss the study walks the detector's own gates, in the detector's own
order, using the detector's own helper functions (never a reimplementation of the
geometry — PRD user story 31), and records the *first* one that failed
(:func:`diagnose_detection`). The verdict itself is always taken from
:func:`detect` unmodified; the walk only attributes a failure the detector already
returned.

**Continuation entries stay in every denominator.** A trade within
:data:`CONTINUATION_SESSIONS` market sessions of a prior entry in the same ticker
is an add to a running position, not a fresh base the detector was ever going to
fire on. It is *tagged*, not dropped (PRD user story 5): every report emits the
headline recall over all replayable trades **and** the ex-continuation recall
together, and no code path emits the ex-continuation figure on its own (user
story 6).

Blind-spot trades (ticker with no bars) get no funnel row — they are recorded as
a blind spot by :mod:`replay.reference`, not as a stage failure (PRD "A1 funnel").
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Callable, Iterable, Sequence

from screener.bars import Bar
from screener.detection import (
    CATCHUP_10,
    CATCHUP_20,
    MAX_BASE_LEN,
    MIN_BASE_LEN,
    MIN_HISTORY,
    _argmax,
    _as_of_index,
    _find_cluster,
    _prior_move,
    _sma_close,
    cluster_min_range_adr,
    detect,
    detection_gate,
)
from screener.indicators import adr as _adr
from screener.ranks import TOP_DECILE, decile_gate
from screener.store import Store
from screener.universe import LIQUIDITY_FLOOR, median_dollar_volume

from .chain import BURN_IN_SESSIONS, REPLAY_MARKET, SessionField, replay_chain
from .reference import ClassifiedTrade, ExecutedTrade, classify

if TYPE_CHECKING:
    from .regression import Distribution

# The three stages this study evaluates, in the app's funnel order: liquidity,
# then the cross-sectional decile gate, then detection (ticket #119 folded the
# decile stage in; #116 landed the outer two).
STAGE_LIQUIDITY = "liquidity"
STAGE_DECILE = "decile"
STAGE_DETECTION = "detection"
FUNNEL_STAGES: tuple[str, ...] = (STAGE_LIQUIDITY, STAGE_DECILE, STAGE_DETECTION)

# A trade within this many market sessions of a prior entry in the same ticker is
# a continuation entry (an add), tagged rather than dropped (PRD user story 5).
CONTINUATION_SESSIONS = 5

# The geometric conditions a detection can fail on, in the detector's gate order.
# These are the gates :func:`screener.detection.detect` actually applies; ``line_ok``
# (slope / touches / overshoot) is *not* a gate — a poor fit is still emitted as a
# detection — so it never appears here as a hard miss.
COND_HISTORY = "history"          # < MIN_HISTORY bars before the eval session
COND_ADR = "adr"                  # non-positive ADR
COND_PRIOR_MOVE = "prior_move"    # no qualifying low->high prior move
COND_BASE_LENGTH = "base_length"  # base shorter than MIN_BASE_LEN
COND_CATCH_UP = "catch_up"        # price not back at the 10/20 MA
COND_CLUSTER = "cluster"          # no tight 3-7 bar cluster (size or tightness)

# A `cluster` miss whose tightest trailing window sits within this multiple of ADR
# is *marginal* — a modest widening of the detector's TIGHT_MULT (1.5) would recover
# it; beyond it the name is genuinely in motion and no plausible widening reaches a
# base. This is the boundary the #132 characterisation reads the misses against; it
# is *reported*, never applied, and no detection constant is changed by it.
MARGINAL_TIGHT_MULT = 2.0


@dataclass(frozen=True)
class FunnelRow:
    """One executed trade walked through the three funnel stages.

    Keyed to ``eval_session`` — the last market session strictly before entry.
    ``eval_session`` is ``None`` only when no session precedes the entry in the
    store's calendar (there is nothing to evaluate against); such a row passes no
    stage and its ``first_failing_stage`` is :data:`STAGE_LIQUIDITY`.

    ``decile_present`` records whether the ticker was a member of the replayed
    field at the evaluation session at all; ``decile_pass`` whether it sat in the
    top decile of the detection lookbacks there. A ticker absent from the field
    (``decile_present`` ``False``) is a coverage gap distinguished from one present
    but ranked outside the decile — both fail the decile stage, but only the
    second is a ranking verdict (PRD "A1 funnel").

    ``decile_pass`` is the app's *three-union* gate (:func:`detection_gate`, over
    1m/3m/6m); ``decile_pass_five`` is the app's *five-union* gate
    (:func:`screener.ranks.decile_gate`, adding 1w and 12m), so a miss recovered by
    widening the gate 3→5 is recoverable without a second rebuild (#133). Both come
    straight from the app's own gate functions — never a hand-rolled percentile
    test, the trap #133 calls out. ``eval_percentiles`` and ``decile_verdicts``
    carry the *margin* of a decile miss: the ticker's percentile per detection
    lookback at the eval session, and the per-lookback top-decile verdict, so a miss
    clustered at the 11th percentile is distinguishable from one scattered across
    the distribution, and the lookback he was strong in is recoverable. Both are
    empty when the ticker was absent from the field (no ranks to read).
    """

    ticker: str
    entry_date: date
    eval_session: date | None
    liquidity_pass: bool
    decile_present: bool              # the ticker was a member of the field at all
    decile_pass: bool                 # top decile on the *three-union* detection gate
    decile_pass_five: bool            # top decile on the *five-union* gate (1w..12m)
    eval_percentiles: dict[str, float]  # per-lookback percentile at the eval session
    decile_verdicts: dict[str, bool]    # per-lookback top-decile verdict (#133)
    detection_pass: bool
    failed_condition: str | None      # the geometric gate the detector failed on
    first_failing_stage: str | None   # first stage in funnel order that failed
    entry_session_break: bool         # secondary: detector fires on the entry session itself
    continuation: bool
    median_dollar_volume: float       # the liquidity measure at the eval session
    # -- `cluster`-miss characterisation (#132): both carry the *margin* of a
    # cluster miss so the 171-miss population can be read against the way he
    # re-enters names and against the condition's current window.
    cluster_min_range_adr: float | None   # tightest trailing 3-7 bar range in ADR; set only on a cluster miss
    sessions_since_prior_entry: int | None  # market-session distance to the nearest prior entry (None = first)


@dataclass(frozen=True)
class StageRecall:
    """One stage's recall, reported two ways at once (PRD user story 6).

    The headline figures cover every replayable trade; the ex-continuation figures
    strip the tagged continuation entries. Both are emitted together; the
    ex-continuation figure is never surfaced on its own.
    """

    stage: str
    passed: int
    total: int
    passed_ex_continuation: int
    total_ex_continuation: int

    @property
    def recall(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def recall_ex_continuation(self) -> float:
        n = self.total_ex_continuation
        return self.passed_ex_continuation / n if n else 0.0


@dataclass(frozen=True)
class DecileDecomposition:
    """The decile miss, decomposed into three exclusive, exhaustive buckets (#133).

    Every replayable trade that fails the three-union decile gate lands in exactly
    one bucket, so the buckets sum to :attr:`total_misses`:

    - ``coverage_gap`` — the ticker was absent from the replayed field entirely
      (``decile_present`` ``False``): a survivorship hole, not a ranking verdict.
    - ``recovered_by_five`` — present and outside the three-union gate, but inside
      the *five-union* gate (top decile in 1w or 12m): the loss widening 3→5 would
      recover. A preliminary #114 read put this near a third of the decile loss;
      the full run confirms or kills it.
    - ``outside_any_union`` — present and outside even the five-union gate: a
      genuine ranking miss no gate widening reaches.
    """

    total_misses: int
    coverage_gap: int
    recovered_by_five: int
    outside_any_union: int


def decompose_decile_misses(rows: Iterable[FunnelRow]) -> DecileDecomposition:
    """Decompose every three-union decile miss across ``rows`` (#133).

    A miss is any row that fails the three-union gate (``decile_pass`` ``False``);
    each is attributed to exactly one bucket, so the three counts partition the
    misses. The verdicts read here (``decile_present``, ``decile_pass``,
    ``decile_pass_five``) are the ones the row carried straight off the app's gate
    functions — this never re-derives a decile verdict from the percentiles (the
    trap #133 calls out).
    """
    coverage_gap = recovered_by_five = outside_any_union = 0
    for r in rows:
        if r.decile_pass:
            continue  # not a miss
        if not r.decile_present:
            coverage_gap += 1
        elif r.decile_pass_five:
            recovered_by_five += 1
        else:
            outside_any_union += 1
    return DecileDecomposition(
        total_misses=coverage_gap + recovered_by_five + outside_any_union,
        coverage_gap=coverage_gap,
        recovered_by_five=recovered_by_five,
        outside_any_union=outside_any_union,
    )


@dataclass(frozen=True)
class ClusterDecomposition:
    """The `cluster` detection miss, characterised two ways (#132).

    `cluster` accounts for the largest share of the detection misses — more than
    the other firing conditions combined — and A1 shows detection is the *only*
    stage whose ex-continuation recall exceeds its headline, the signature of a
    rule that penalises his repeat entries. This decomposition reads every
    replayable trade whose detection failed on the `cluster` condition
    (``failed_condition == COND_CLUSTER``) against the two questions #132 asks:

    - **how far from the prior entry** — ``continuation`` counts the misses that
      are continuation entries (within :data:`CONTINUATION_SESSIONS` of a prior
      entry in the same ticker), ``fresh`` the rest. A cluster miss on a
      continuation entry is the base detector correctly declining a name that is
      mid-move rather than in a base; recall on it is not a legitimate target,
      because the reference set records no setup he declined and precision is not
      measurable. ``prior_distance_distribution`` summarises the market-session
      distance to the nearest prior entry across the continuation misses.
    - **how they distribute against the condition's window** — ``marginal`` counts
      the misses whose tightest trailing window sits within
      :data:`MARGINAL_TIGHT_MULT` × ADR (a modest widening of the detector's
      ``TIGHT_MULT`` would recover them), ``far`` the ones beyond it (a name
      genuinely in motion no plausible widening reaches).
      ``range_distribution`` summarises the tightest-window range in ADR across
      all the misses.

    ``continuation + fresh == total_misses`` and ``marginal + far ==
    total_misses`` (every real cluster miss cleared the ADR gate, so it always
    carries a tightest-window range). The distributions are ``None`` when their
    subset is empty. Nothing here changes a detector constant (PRD #114 out of
    scope); it is the evidence a change would have to rest on.
    """

    total_misses: int
    continuation: int
    fresh: int
    marginal: int
    far: int
    range_distribution: "Distribution | None"
    prior_distance_distribution: "Distribution | None"


def characterise_cluster_misses(rows: Iterable[FunnelRow]) -> ClusterDecomposition:
    """Characterise every `cluster` detection miss across ``rows`` (#132).

    A miss is any row whose detection failed on the `cluster` condition. Each is
    read off the margin the row already carries — ``cluster_min_range_adr`` (how
    far over the condition's window) and ``continuation`` /
    ``sessions_since_prior_entry`` (how far from a prior entry) — never re-running
    the detector. ``distribution`` is imported locally to keep :mod:`replay.funnel`
    free of a top-level dependency on :mod:`replay.regression`, which imports it.
    """
    from .regression import distribution

    misses = [r for r in rows if r.failed_condition == COND_CLUSTER]
    ranges = [
        r.cluster_min_range_adr
        for r in misses
        if r.cluster_min_range_adr is not None
    ]
    continuation = sum(1 for r in misses if r.continuation)
    marginal = sum(
        1
        for r in misses
        if r.cluster_min_range_adr is not None
        and r.cluster_min_range_adr <= MARGINAL_TIGHT_MULT
    )
    prior_distances = [
        float(r.sessions_since_prior_entry)
        for r in misses
        if r.continuation and r.sessions_since_prior_entry is not None
    ]
    return ClusterDecomposition(
        total_misses=len(misses),
        continuation=continuation,
        fresh=len(misses) - continuation,
        marginal=marginal,
        far=len(misses) - marginal,
        range_distribution=distribution(ranges),
        prior_distance_distribution=distribution(prior_distances),
    )


@dataclass(frozen=True)
class FunnelReport:
    """The A1 result: per-row funnel walks plus per-stage recall.

    ``stages`` names the three stages evaluated, in funnel order
    (:data:`FUNNEL_STAGES`). No single blended recall is emitted — each stage
    reports its own figure (PRD user story 2). ``condition_counts`` tallies the
    geometric condition each detection miss failed on, so the study can say which
    condition costs the most (PRD user story 10). ``blind_spot_count`` is the
    coverage figure every decile-dependent output carries, since the decile stage
    depends on the replayed field's population (PRD user story 22).
    ``decile_decomposition`` breaks the decile miss into coverage gap /
    recovered-by-5 / outside-any-union across all replayable trades (#133).
    ``cluster_characterisation`` breaks the largest detection miss — `cluster` —
    down by continuation-vs-fresh and by how far each miss sits over the
    condition's tightness window (#132).
    """

    rows: list[FunnelRow]
    stages: tuple[str, ...]
    liquidity: StageRecall
    decile: StageRecall
    detection: StageRecall
    condition_counts: dict[str, int]
    continuation_count: int
    blind_spot_count: int
    decile_decomposition: DecileDecomposition
    cluster_characterisation: ClusterDecomposition


# -- evaluation session -------------------------------------------------------


def evaluation_session(calendar: list[date], entry_date: date) -> date | None:
    """The last session in ``calendar`` strictly before ``entry_date``.

    ``calendar`` is the market's observed session dates, oldest first (the union of
    bar dates — :meth:`screener.store.Store.sessions`), so the "session before"
    lands correctly across weekends and market holidays with no holiday table: a
    gap simply has no session in it. ``None`` when nothing precedes the entry.
    """
    idx = bisect_left(calendar, entry_date) - 1
    return calendar[idx] if idx >= 0 else None


def _session_index(calendar: list[date], when: date) -> int:
    """Index of the last session on or before ``when`` (``-1`` if none)."""
    return bisect_right(calendar, when) - 1


# -- detection failure attribution --------------------------------------------


def diagnose_detection(bars: list[Bar], as_of: date) -> str | None:
    """The first detector gate that fails for ``(bars, as_of)``, or ``None``.

    Walks :func:`screener.detection.detect`'s gates in its exact order, reusing its
    own helper functions and constants so the geometry under test is the app's, not
    a reimplementation of it (PRD user story 31). ``None`` means every gate passed —
    the name is a detection. Called only to attribute a miss the detector already
    returned; the pass/fail verdict is always :func:`detect`'s.
    """
    idx = _as_of_index(bars, as_of)
    if idx is None or idx < MIN_HISTORY:
        return COND_HISTORY
    high = [b.high for b in bars]
    low = [b.low for b in bars]
    close = [b.close for b in bars]

    a = _adr(bars[: idx + 1])
    if a is None or a <= 0:
        return COND_ADR
    adr_abs = a * close[idx]

    mv = _prior_move(high, low, idx)
    if mv is None:
        return COND_PRIOR_MOVE
    _move_gain, peak = mv
    base_start = peak
    if idx - base_start + 1 > MAX_BASE_LEN:
        base_start = _argmax(high, idx - MAX_BASE_LEN + 1, idx)
    if idx - base_start + 1 < MIN_BASE_LEN:
        return COND_BASE_LENGTH

    s10 = _sma_close(close, idx, 10)
    s20 = _sma_close(close, idx, 20)
    caught_up = (
        s10 is not None
        and s20 is not None
        and close[idx] - s10 <= CATCHUP_10 * adr_abs
        and close[idx] - s20 <= CATCHUP_20 * adr_abs
    )
    if not caught_up:
        return COND_CATCH_UP

    if _find_cluster(high, low, idx, adr_abs) is None:
        return COND_CLUSTER

    return None


# -- the funnel walk ----------------------------------------------------------


def passes_liquidity(bars: list[Bar], market: str) -> bool:
    """Whether the trailing median dollar volume clears the market's floor.

    Uses the app's own :func:`screener.universe.median_dollar_volume` and
    :data:`screener.universe.LIQUIDITY_FLOOR` (PRD "using the app's own indicator
    functions"). A fresh entry is measured against the plain floor — the
    hysteresis band only holds an *existing* member, and an executed trade the app
    never surfaced was never a member.
    """
    return median_dollar_volume(bars) >= LIQUIDITY_FLOOR[market]


def _prior_entry_distances(
    classified: list[ClassifiedTrade], calendar: list[date]
) -> dict[int, int | None]:
    """Market-session distance from each replayable trade (by identity) to the
    *nearest prior* entry in the same ticker, or ``None`` when it is the first
    entry in that ticker.

    Distance is counted on the market calendar so weekends and holidays do not
    inflate the gap. A trade is a continuation entry when this distance is not
    ``None`` and ``<= CONTINUATION_SESSIONS`` (:func:`_is_continuation`) — so the
    single distance both drives the continuation tag (PRD user story 5) and carries
    the "how far from the prior entry" margin the #132 cluster characterisation
    reads.
    """
    by_ticker: dict[str, list[ExecutedTrade]] = {}
    for c in classified:
        if c.replayable:
            by_ticker.setdefault(c.trade.ticker, []).append(c.trade)

    distances: dict[int, int | None] = {}
    for trades in by_ticker.values():
        ordered = sorted(trades, key=lambda t: t.entry_date)
        for i, trade in enumerate(ordered):
            here = _session_index(calendar, trade.entry_date)
            priors = [
                here - _session_index(calendar, prior.entry_date)
                for prior in ordered[:i]
            ]
            distances[id(trade)] = min(priors) if priors else None
    return distances


def _is_continuation(distance: int | None) -> bool:
    """Whether a nearest-prior-entry ``distance`` marks a continuation entry."""
    return distance is not None and distance <= CONTINUATION_SESSIONS


def _eval_cluster_min_range(bars: list[Bar], as_of: date) -> float | None:
    """The tightest trailing 3–7 bar cluster range at ``as_of``, in ADR units.

    Reuses the detector's own :func:`screener.detection.cluster_min_range_adr` over
    the same ADR the detector would compute, so a `cluster` miss carries how far
    over the condition's window it sat. ``None`` when there is no session on or
    before ``as_of`` or ADR is non-positive.
    """
    idx = _as_of_index(bars, as_of)
    if idx is None:
        return None
    a = _adr(bars[: idx + 1])
    if a is None or a <= 0:
        return None
    high = [b.high for b in bars]
    low = [b.low for b in bars]
    adr_abs = a * bars[idx].close
    return cluster_min_range_adr(high, low, idx, adr_abs)


def _funnel_row(
    trade: ExecutedTrade,
    bars: list[Bar],
    calendar: list[date],
    market: str,
    continuation: bool,
    sessions_since_prior_entry: int | None,
    members_by_session: dict[date, set[str]],
    gate3_by_session: dict[date, set[str]],
    gate5_by_session: dict[date, set[str]],
    percentiles_by_session: dict[date, dict[str, dict[str, float]]],
) -> FunnelRow:
    # Secondary signal, independent of the eval session: does the base the app
    # would look for stand on the entry session itself?
    entry_session_break = detect(trade.ticker, bars, trade.entry_date) is not None
    eval_session = evaluation_session(calendar, trade.entry_date)

    if eval_session is None:
        # Nothing precedes the entry: no night to evaluate against.
        return FunnelRow(
            ticker=trade.ticker,
            entry_date=trade.entry_date,
            eval_session=None,
            liquidity_pass=False,
            decile_present=False,
            decile_pass=False,
            decile_pass_five=False,
            eval_percentiles={},
            decile_verdicts={},
            detection_pass=False,
            failed_condition=None,
            first_failing_stage=STAGE_LIQUIDITY,
            entry_session_break=entry_session_break,
            continuation=continuation,
            median_dollar_volume=0.0,
            cluster_min_range_adr=None,
            sessions_since_prior_entry=sessions_since_prior_entry,
        )

    up_to_eval = [b for b in bars if b.session <= eval_session]
    liquidity_pass = passes_liquidity(up_to_eval, market)
    mdv = median_dollar_volume(up_to_eval)

    # The decile is cross-sectional: read it off the forward chain's field at the
    # eval session. Absent from the field (not a member) is a coverage gap kept
    # apart from present-but-outside-the-decile; both fail the decile stage. The
    # pass/fail verdicts come straight from the app's gate functions
    # (detection_gate -> three-union, decile_gate -> five-union); the per-lookback
    # percentiles carry the *margin* of a miss but never re-decide the verdict.
    members = members_by_session.get(eval_session, set())
    decile_present = trade.ticker in members
    decile_pass = trade.ticker in gate3_by_session.get(eval_session, set())
    decile_pass_five = trade.ticker in gate5_by_session.get(eval_session, set())
    eval_percentiles = dict(
        percentiles_by_session.get(eval_session, {}).get(trade.ticker, {})
    )
    decile_verdicts = {lb: pct >= TOP_DECILE for lb, pct in eval_percentiles.items()}

    detection = detect(trade.ticker, bars, eval_session)
    detection_pass = detection is not None
    failed_condition = None if detection_pass else diagnose_detection(bars, eval_session)
    # The margin of a `cluster` miss (#132): how far the tightest trailing window
    # sat over the condition's TIGHT_MULT window. Set only on a cluster miss — the
    # other conditions have their own margins and a pass has no miss to characterise.
    cluster_min_range = (
        _eval_cluster_min_range(bars, eval_session)
        if failed_condition == COND_CLUSTER
        else None
    )

    if not liquidity_pass:
        first_failing = STAGE_LIQUIDITY
    elif not decile_pass:
        first_failing = STAGE_DECILE
    elif not detection_pass:
        first_failing = STAGE_DETECTION
    else:
        first_failing = None

    return FunnelRow(
        ticker=trade.ticker,
        entry_date=trade.entry_date,
        eval_session=eval_session,
        liquidity_pass=liquidity_pass,
        decile_present=decile_present,
        decile_pass=decile_pass,
        decile_pass_five=decile_pass_five,
        eval_percentiles=eval_percentiles,
        decile_verdicts=decile_verdicts,
        detection_pass=detection_pass,
        failed_condition=failed_condition,
        first_failing_stage=first_failing,
        entry_session_break=entry_session_break,
        continuation=continuation,
        median_dollar_volume=mdv,
        cluster_min_range_adr=cluster_min_range,
        sessions_since_prior_entry=sessions_since_prior_entry,
    )


def _percentiles_by_session(
    chain: Sequence[SessionField], tickers: set[str]
) -> dict[date, dict[str, dict[str, float]]]:
    """Per-session, per-lookback percentiles for just the trade ``tickers`` (#133).

    Restricted to the trade tickers so the map stays a handful of rows per session
    rather than a copy of the whole rank table; a trade's own margin is all the
    decomposition ever needs.
    """
    out: dict[date, dict[str, dict[str, float]]] = {}
    for sf in chain:
        per_symbol: dict[str, dict[str, float]] = {}
        for r in sf.ranks:
            if r.symbol in tickers:
                per_symbol.setdefault(r.symbol, {})[r.lookback] = r.percentile
        out[sf.session] = per_symbol
    return out


def build_funnel_report(
    classified: list[ClassifiedTrade],
    calendar: list[date],
    chain: Sequence[SessionField],
    store: Store,
    market: str,
    *,
    blind_spot_tickers: Iterable[str] = (),
) -> FunnelReport:
    """Walk every replayable trade over an already-built forward ``chain``.

    The chain-free core of :func:`run_funnel`: it reads universe membership, both
    decile gates, and the per-lookback margins off the chain the caller already
    computed, so the one-process runner (:mod:`replay.study`) can share a single
    chain across all four analyses instead of rebuilding it per analysis.
    """
    distances = _prior_entry_distances(classified, calendar)
    members_by_session = {sf.session: set(sf.members) for sf in chain}
    gate3_by_session = {sf.session: detection_gate(sf.ranks) for sf in chain}
    gate5_by_session = {sf.session: decile_gate(sf.ranks) for sf in chain}
    trade_tickers = {c.trade.ticker for c in classified if c.replayable}
    percentiles_by_session = _percentiles_by_session(chain, trade_tickers)
    blind_spot_count = (
        chain[0].blind_spot_count if chain else len(set(blind_spot_tickers))
    )

    rows: list[FunnelRow] = []
    bars_cache: dict[str, list[Bar]] = {}
    for c in classified:
        if not c.replayable:
            continue
        ticker = c.trade.ticker
        if ticker not in bars_cache:
            bars_cache[ticker] = store.bars(market, ticker)
        distance = distances[id(c.trade)]
        rows.append(
            _funnel_row(
                c.trade,
                bars_cache[ticker],
                calendar,
                market,
                _is_continuation(distance),
                distance,
                members_by_session,
                gate3_by_session,
                gate5_by_session,
                percentiles_by_session,
            )
        )

    return _build_report(rows, blind_spot_count)


def run_funnel(
    trades: list[ExecutedTrade],
    store: Store,
    *,
    market: str = REPLAY_MARKET,
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
) -> FunnelReport:
    """Walk every replayable trade through the liquidity, decile and detection stages.

    The decile stage is cross-sectional, so the funnel first runs the A2 forward
    chain (:func:`replay.chain.replay_chain`) to reconstruct universe membership
    and ranks per session, then reads each trade's decile result off the chain's
    ranks at its evaluation session. ``blind_spot_tickers``, ``burn_in`` and
    ``sessions`` are handed through to the chain; the blind-spot count rides onto
    the report as the coverage figure every decile-dependent output must carry
    (PRD user story 22).

    Blind-spot trades (ticker with no bars) get no row — they are a blind spot, not
    a stage failure. Continuation entries are tagged and kept in every denominator.
    """
    classified = classify(trades, store, market=market)
    calendar = store.sessions(market)
    chain = replay_chain(
        store,
        market,
        blind_spot_tickers=blind_spot_tickers,
        burn_in=burn_in,
        sessions=sessions,
    )
    return build_funnel_report(
        classified, calendar, chain, store, market,
        blind_spot_tickers=blind_spot_tickers,
    )


def _stage_recall(
    stage: str, rows: list[FunnelRow], predicate: Callable[[FunnelRow], bool]
) -> StageRecall:
    ex = [r for r in rows if not r.continuation]
    return StageRecall(
        stage=stage,
        passed=sum(1 for r in rows if predicate(r)),
        total=len(rows),
        passed_ex_continuation=sum(1 for r in ex if predicate(r)),
        total_ex_continuation=len(ex),
    )


def _build_report(rows: list[FunnelRow], blind_spot_count: int) -> FunnelReport:
    condition_counts: dict[str, int] = {}
    for r in rows:
        if r.failed_condition is not None:
            condition_counts[r.failed_condition] = (
                condition_counts.get(r.failed_condition, 0) + 1
            )
    return FunnelReport(
        rows=rows,
        stages=FUNNEL_STAGES,
        liquidity=_stage_recall(STAGE_LIQUIDITY, rows, lambda r: r.liquidity_pass),
        decile=_stage_recall(STAGE_DECILE, rows, lambda r: r.decile_pass),
        detection=_stage_recall(STAGE_DETECTION, rows, lambda r: r.detection_pass),
        condition_counts=condition_counts,
        continuation_count=sum(1 for r in rows if r.continuation),
        blind_spot_count=blind_spot_count,
        decile_decomposition=decompose_decile_misses(rows),
        cluster_characterisation=characterise_cluster_misses(rows),
    )


def format_report(report: FunnelReport) -> str:
    """Human-readable summary: the three stages, both recalls, condition breakdown."""
    lines = [
        f"funnel stages: {', '.join(report.stages)}",
        f"replayable trades:    {len(report.rows)}",
        f"continuation entries: {report.continuation_count}",
        f"blind-spot coverage:  {report.blind_spot_count} tickers missing from the field",
        "",
    ]
    for stage in (report.liquidity, report.decile, report.detection):
        lines.append(
            f"{stage.stage:<10} recall: {stage.passed}/{stage.total} "
            f"({stage.recall:.1%})  ex-continuation: "
            f"{stage.passed_ex_continuation}/{stage.total_ex_continuation} "
            f"({stage.recall_ex_continuation:.1%})"
        )
    if report.condition_counts:
        lines.append("")
        lines.append("detection misses by condition:")
        for cond, n in sorted(
            report.condition_counts.items(), key=lambda kv: kv[1], reverse=True
        ):
            lines.append(f"  {cond:<12} {n}")
    d = report.decile_decomposition
    lines += [
        "",
        f"decile miss decomposed ({d.total_misses} misses over all replayable trades):",
        f"  coverage gap (absent from field):   {d.coverage_gap}",
        f"  recovered by widening the gate 3->5: {d.recovered_by_five}",
        f"  outside any union (genuine miss):   {d.outside_any_union}",
    ]
    c = report.cluster_characterisation
    lines += [
        "",
        f"cluster miss characterised ({c.total_misses} misses):",
        f"  continuation entries (re-entries): {c.continuation}",
        f"  fresh entries:                     {c.fresh}",
        f"  marginal (<= {MARGINAL_TIGHT_MULT:.1f}x ADR, a modest widen recovers): {c.marginal}",
        f"  far (name in motion, no base):     {c.far}",
    ]
    if c.range_distribution is not None:
        r = c.range_distribution
        lines.append(
            f"  tightest-window range in ADR: median {r.median:.2f} "
            f"(p25 {r.p25:.2f}, p75 {r.p75:.2f}, max {r.maximum:.2f})"
        )
    if c.prior_distance_distribution is not None:
        p = c.prior_distance_distribution
        lines.append(
            f"  sessions since prior entry (continuation misses): median "
            f"{p.median:.1f} (min {p.minimum:.0f}, max {p.maximum:.0f})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Run the A1 funnel over the replay store and print the report.

    Thin CLI over the pure functions above (one entry point per study, PRD user
    story 30). The blind-spot tickers are recomputed from the reference set rather
    than passed in, so the coverage figure on the report is always the store's own.
    Run as ``python -m replay.funnel --store data/replay.duckdb``.
    """
    import argparse

    from .reference import DEFAULT_REFERENCE_JSON, build_report, load_trades

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the replay store")
    parser.add_argument("--reference", default=str(DEFAULT_REFERENCE_JSON),
                        help="path to the executed-trade reference JSON")
    parser.add_argument("--market", default=REPLAY_MARKET)
    args = parser.parse_args(argv)

    trades = load_trades(args.reference)
    store = Store.open(args.store)
    try:
        coverage = build_report(trades, store, market=args.market)
        report = run_funnel(
            trades,
            store,
            market=args.market,
            blind_spot_tickers=coverage.blind_spot_ticker_list,
        )
    finally:
        store.close()

    print(format_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
