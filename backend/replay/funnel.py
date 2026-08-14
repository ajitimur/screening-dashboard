"""A1, the funnel/recall study: liquidity and detection (PRD #114, ticket #116).

The first two funnel stages, evaluated for every *replayable* executed trade at
the session **strictly before** its entry date — the night the app would have had
to name the stock while the entry was still ahead of the trader (PRD user story
3). For each trade the study records whether it clears the liquidity floor and
whether the app's detector fires on it, unmodified.

**Two stages, and it says so.** The funnel the app runs has three ordered gates —
liquidity, decile, detection — but the decile gate is cross-sectional: it needs
that night's *replayed field* to rank against, which does not exist until the A2
chain (ticket #117) is built. So this study reports liquidity and detection only,
names the two it has (:data:`FUNNEL_STAGES`), and states the decile stage is
deliberately absent (:data:`DECILE_ABSENT_NOTE`) rather than quietly blending it
away.

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
    detect,
)
from screener.indicators import adr as _adr
from screener.store import Store
from screener.universe import LIQUIDITY_FLOOR, median_dollar_volume

from .reference import ClassifiedTrade, ExecutedTrade, classify

# The two stages this study evaluates, in funnel order. The decile stage sits
# between them in the app but is absent here (see the module docstring).
STAGE_LIQUIDITY = "liquidity"
STAGE_DETECTION = "detection"
FUNNEL_STAGES: tuple[str, ...] = (STAGE_LIQUIDITY, STAGE_DETECTION)

DECILE_ABSENT_NOTE = (
    "Two of the app's three funnel stages are evaluated here: liquidity and "
    "detection. The decile stage is deliberately absent — it is cross-sectional "
    "and needs the replayed field (ticket #117), which does not exist yet."
)

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


@dataclass(frozen=True)
class FunnelRow:
    """One executed trade walked through the two funnel stages.

    Keyed to ``eval_session`` — the last market session strictly before entry.
    ``eval_session`` is ``None`` only when no session precedes the entry in the
    store's calendar (there is nothing to evaluate against); such a row passes no
    stage and its ``first_failing_stage`` is :data:`STAGE_LIQUIDITY`.
    """

    ticker: str
    entry_date: date
    eval_session: date | None
    liquidity_pass: bool
    detection_pass: bool
    failed_condition: str | None      # the geometric gate the detector failed on
    first_failing_stage: str | None   # first stage in funnel order that failed
    entry_session_break: bool         # secondary: detector fires on the entry session itself
    continuation: bool
    median_dollar_volume: float       # the liquidity measure at the eval session


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
class FunnelReport:
    """The A1 result: per-row funnel walks plus per-stage recall.

    ``stages`` names the two stages evaluated (decile absent, see
    :data:`DECILE_ABSENT_NOTE`). No single blended recall is emitted — each stage
    reports its own figure (PRD user story 2). ``condition_counts`` tallies the
    geometric condition each detection miss failed on, so the study can say which
    condition costs the most (PRD user story 10).
    """

    rows: list[FunnelRow]
    stages: tuple[str, ...]
    liquidity: StageRecall
    detection: StageRecall
    condition_counts: dict[str, int]
    continuation_count: int


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


def _continuation_flags(
    classified: list[ClassifiedTrade], calendar: list[date]
) -> dict[int, bool]:
    """Tag each replayable trade (by identity) a continuation entry or not.

    A trade is a continuation when a prior entry in the *same ticker* sits within
    :data:`CONTINUATION_SESSIONS` market sessions of it. Distance is counted on the
    market calendar so weekends and holidays do not inflate the gap.
    """
    by_ticker: dict[str, list[ExecutedTrade]] = {}
    for c in classified:
        if c.replayable:
            by_ticker.setdefault(c.trade.ticker, []).append(c.trade)

    flags: dict[int, bool] = {}
    for trades in by_ticker.values():
        ordered = sorted(trades, key=lambda t: t.entry_date)
        for i, trade in enumerate(ordered):
            here = _session_index(calendar, trade.entry_date)
            is_cont = any(
                here - _session_index(calendar, prior.entry_date)
                <= CONTINUATION_SESSIONS
                for prior in ordered[:i]
            )
            flags[id(trade)] = is_cont
    return flags


def _funnel_row(
    trade: ExecutedTrade,
    bars: list[Bar],
    calendar: list[date],
    market: str,
    continuation: bool,
) -> FunnelRow:
    eval_session = evaluation_session(calendar, trade.entry_date)

    if eval_session is None:
        # Nothing precedes the entry: no night to evaluate against.
        return FunnelRow(
            ticker=trade.ticker,
            entry_date=trade.entry_date,
            eval_session=None,
            liquidity_pass=False,
            detection_pass=False,
            failed_condition=None,
            first_failing_stage=STAGE_LIQUIDITY,
            entry_session_break=detect(trade.ticker, bars, trade.entry_date) is not None,
            continuation=continuation,
            median_dollar_volume=0.0,
        )

    up_to_eval = [b for b in bars if b.session <= eval_session]
    liquidity_pass = passes_liquidity(up_to_eval, market)
    mdv = median_dollar_volume(up_to_eval)

    detection = detect(trade.ticker, bars, eval_session)
    detection_pass = detection is not None
    failed_condition = None if detection_pass else diagnose_detection(bars, eval_session)

    if not liquidity_pass:
        first_failing = STAGE_LIQUIDITY
    elif not detection_pass:
        first_failing = STAGE_DETECTION
    else:
        first_failing = None

    return FunnelRow(
        ticker=trade.ticker,
        entry_date=trade.entry_date,
        eval_session=eval_session,
        liquidity_pass=liquidity_pass,
        detection_pass=detection_pass,
        failed_condition=failed_condition,
        first_failing_stage=first_failing,
        entry_session_break=detect(trade.ticker, bars, trade.entry_date) is not None,
        continuation=continuation,
        median_dollar_volume=mdv,
    )


def run_funnel(
    trades: list[ExecutedTrade], store: Store, *, market: str = "US"
) -> FunnelReport:
    """Walk every replayable trade through the liquidity and detection stages.

    Blind-spot trades (ticker with no bars) get no row — they are a blind spot, not
    a stage failure. Continuation entries are tagged and kept in every denominator.
    """
    classified = classify(trades, store, market=market)
    calendar = store.sessions(market)
    continuation = _continuation_flags(classified, calendar)

    rows: list[FunnelRow] = []
    bars_cache: dict[str, list[Bar]] = {}
    for c in classified:
        if not c.replayable:
            continue
        ticker = c.trade.ticker
        if ticker not in bars_cache:
            bars_cache[ticker] = store.bars(market, ticker)
        rows.append(
            _funnel_row(
                c.trade,
                bars_cache[ticker],
                calendar,
                market,
                continuation[id(c.trade)],
            )
        )

    return _build_report(rows)


def _stage_recall(stage: str, rows: list[FunnelRow], predicate) -> StageRecall:
    ex = [r for r in rows if not r.continuation]
    return StageRecall(
        stage=stage,
        passed=sum(1 for r in rows if predicate(r)),
        total=len(rows),
        passed_ex_continuation=sum(1 for r in ex if predicate(r)),
        total_ex_continuation=len(ex),
    )


def _build_report(rows: list[FunnelRow]) -> FunnelReport:
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
        detection=_stage_recall(STAGE_DETECTION, rows, lambda r: r.detection_pass),
        condition_counts=condition_counts,
        continuation_count=sum(1 for r in rows if r.continuation),
    )


def format_report(report: FunnelReport) -> str:
    """Human-readable summary: the two stages, both recalls, condition breakdown."""
    lines = [
        DECILE_ABSENT_NOTE,
        "",
        f"replayable trades:   {len(report.rows)}",
        f"continuation entries: {report.continuation_count}",
        "",
    ]
    for stage in (report.liquidity, report.detection):
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
    return "\n".join(lines)
