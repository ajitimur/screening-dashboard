"""The volatility state — the regime's sibling, advisory only (spec §4.10).

The regime says which direction the market is leaning; this says **how violently
it is moving**. It is a sibling of :mod:`screener.regime`, never a component of
it: same advisory-only rule — it never filters, never reorders and never touches
the star score — and its own module, endpoint and banner segment, so the
regime's vocabulary and API stay exactly where they were.

The reading is the market index's **21-day realized volatility** (annualized),
ranked as a percentile against the index's own history:

- **US** ranks against a rolling three years.
- **IDX** ranks **within the current ARB policy era only**. IDX's auto-rejection
  bands cap how far a name — and so the index — can move in a day, and the band
  widths have been changed by decree four times since 2020. A percentile ranked
  across those changes compares observations censored by different amounts: the
  tight-limit eras make the past look artificially calm, so today reads as more
  extreme than it is. The bias direction is known, its size is not (ADR 0006).

Below :data:`VOL_WARMUP` readings the state is **undefined** (``None``), not
defaulted — §4.9's rule, applied to the denominator rather than the series. The
sample size travels with the percentile everywhere so a thin within-era history
is visible rather than hidden.

The bucket edges are **display conventions, not calibrated thresholds** — the
same epistemic status as the posture words. They are declared as such because
the regime's zero-tuned-parameters stance is justified by survivorship bias in
rebuilt *member* series, and a continuous index series carries no such bias;
they are conventions all the same, fixed in §4.10 and moved only with evidence.

Pure over clean, oldest-first ``list[Bar]`` series, like :mod:`screener.regime`:
the store-driven wrappers that read index and second-leg bars live in the API
layer and the pipeline. The instrument *symbols* are the source's business
(:data:`screener.source.SECOND_LEG`); nothing here knows how a bar was fetched.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

from .bars import Bar
from .regime import RegimeState

# The realized-vol window and the annualization factor: 21 sessions is a trading
# month, and √252 puts the reading on the same axis as the implied-vol numbers a
# trader already reads (VIX is quoted annualized).
VOL_WINDOW = 21
TRADING_DAYS = 252

# How many readings a percentile needs before it says anything. Below this the
# state is undefined, not defaulted — the same rule the regime applies to its own
# warm-up, moved to the denominator: a percentile against 12 observations is a
# number, not a rank. A future ARB era change resets IDX to undefined for roughly
# three months, which is the design working rather than a bug (ADR 0006).
VOL_WARMUP = 60

# The rolling history a percentile ranks against, where no era bounds it.
PERCENTILE_YEARS = 3

# The bucket edges, in percentile points (spec §4.10). **Display conventions,
# not calibrated thresholds** — CALM below 50, ELEVATED to 80, STRESSED above.
CALM_EDGE = 50.0
STRESSED_EDGE = 80.0

# The ARB policy eras: spans over which IDX's auto-rejection limit widths were
# constant, as decree dates, newest last. These are **policy facts, not calendar
# data** — hand-verified against idx.co.id (which blocks automated fetch) and
# never inferred from bars, which is why they sit here as a constant rather than
# being derived from the series they censor. The current entry is the asymmetric
# 15% downside band of Kep-00003/BEI/04-2025, effective 2025-04-08. Adding the
# next one is a config edit plus a warm-up, not a redesign (ADR 0006).
#
# US has no entry and needs none: its circuit breakers halt trading rather than
# capping the printed move, so its history is uncensored throughout.
ARB_POLICY_ERAS: dict[str, tuple[date, ...]] = {
    "IDX": (date(2025, 4, 8),),
}

# The three states, defined here where they are computed; the API layer
# (``models.VolatilityResponse``) re-exports this so there is one source of truth.
VolatilityState = Literal["CALM", "ELEVATED", "STRESSED"]

# The nine-cell posture matrix (spec §4.10): every trend×volatility combination
# carries its own sentence — **words, never a computed size**, exactly as the
# regime's own three do. The regime's table is untouched; this one supersedes it
# only in the banner, where both readings are on screen together. "Full size" in
# stressed volatility must never read as an unqualified go-ahead, which is the
# whole reason the matrix is nine sentences rather than three words plus a tag.
_POSTURE: dict[tuple[RegimeState, VolatilityState], str] = {
    ("FRIENDLY", "CALM"): "full size — quiet tape",
    ("FRIENDLY", "ELEVATED"): "full size — vol building, honor stops",
    ("FRIENDLY", "STRESSED"): (
        "full size, but vol is stressed — expect wide swings, size stops accordingly"
    ),
    ("CHOPPY", "CALM"): "reduced — directionless but quiet",
    ("CHOPPY", "ELEVATED"): "reduced — directionless and vol building",
    ("CHOPPY", "STRESSED"): "reduced — chop with stressed vol is whipsaw territory",
    ("HOSTILE", "CALM"): "sit out — downtrend, even quiet",
    ("HOSTILE", "ELEVATED"): "sit out — downtrend with vol building",
    ("HOSTILE", "STRESSED"): "sit out — downtrend in stressed vol, worst cell on the board",
}


def realized_vol(bars: list[Bar]) -> float | None:
    """Annualized realized volatility of ``bars``' last :data:`VOL_WINDOW` returns.

    The sample standard deviation of daily log returns on the **adjusted** close
    (the series every geometric computation reads, §3.5), scaled by ``√252``.
    ``None`` below ``VOL_WINDOW + 1`` bars — a window of returns needs one more
    bar than returns — and ``None`` for a series carrying a non-positive close,
    where a log return is undefined.
    """
    if len(bars) < VOL_WINDOW + 1:
        return None
    closes = [b.adj_close for b in bars[-(VOL_WINDOW + 1) :]]
    if any(c <= 0 for c in closes):
        return None
    returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(TRADING_DAYS)


def vol_series(bars: list[Bar]) -> list[tuple[date, float]]:
    """Every session's realized-vol reading, oldest first.

    One ``(session, vol)`` pair per bar that has a full window behind it — the
    history a percentile ranks against. A session whose window carries a
    non-positive close is skipped rather than defaulted.
    """
    out: list[tuple[date, float]] = []
    for end in range(VOL_WINDOW, len(bars)):
        vol = realized_vol(bars[: end + 1])
        if vol is not None:
            out.append((bars[end].session, vol))
    return out


def _years_before(session: date, years: int) -> date:
    """``session`` shifted back whole ``years``, clamping 29 Feb to 28 Feb so a
    leap-day session yields a valid window start."""
    try:
        return session.replace(year=session.year - years)
    except ValueError:  # 29 Feb in a non-leap target year
        return session.replace(year=session.year - years, day=28)


def current_era(market: str, session: date) -> date | None:
    """The start of the ARB policy era ``session`` falls in, or ``None``.

    ``None`` means *no era bounds this session*, which is two different facts.
    For a market with no era table (US) it is the ordinary case: nothing censors
    the history and the rolling window is the only limit. For a market that
    **has** one, it means the session predates every recorded decree — a session
    whose censoring regime is unknown, which :func:`reading` refuses to rank
    rather than rank across decrees (ADR 0006).
    """
    starts = [s for s in ARB_POLICY_ERAS.get(market, ()) if s <= session]
    return max(starts) if starts else None


def percentile_window_start(market: str, session: date) -> date:
    """The earliest session a percentile for ``session`` may rank against.

    The rolling :data:`PERCENTILE_YEARS` window, tightened to the current ARB
    policy era where one applies — so IDX ranks within-era while the era is
    young, and falls back to the same rolling window as US once the era has
    outgrown it (spec §4.10).
    """
    rolling = _years_before(session, PERCENTILE_YEARS)
    era = current_era(market, session)
    return max(rolling, era) if era is not None else rolling


def percentile_of(value: float, history: list[float]) -> float:
    """``value``'s rank within ``history``, in percentile points (0–100).

    The share of observations strictly below ``value``. ``history`` includes the
    reading itself, so a single observation ranks at 0 — the lowest of one — and
    the number a reader sees is always paired with the sample size it came from.
    """
    below = sum(1 for h in history if h < value)
    return 100.0 * below / len(history)


def volatility_state(percentile: float | None, sample_size: int) -> VolatilityState | None:
    """The three-state volatility bucket, or ``None`` below the warm-up.

    Undefined, never defaulted: below :data:`VOL_WARMUP` observations there is no
    state at all rather than a provisional ``CALM``.
    """
    if percentile is None or sample_size < VOL_WARMUP:
        return None
    if percentile < CALM_EDGE:
        return "CALM"
    if percentile <= STRESSED_EDGE:
        return "ELEVATED"
    return "STRESSED"


def posture(state: RegimeState | None, vol: VolatilityState | None) -> str | None:
    """The trend×volatility cell's posture sentence, in words (spec §4.10).

    ``None`` when either reading is undefined — a cell needs both coordinates,
    and half a posture would advise something neither state supports. The
    regime's own three-word posture (:func:`screener.regime.posture`) is
    unchanged and still answers for the regime alone.
    """
    if state is None or vol is None:
        return None
    return _POSTURE[(state, vol)]


@dataclass(frozen=True)
class VolatilityReading:
    """One session's volatility readings for a market (spec §4.10).

    The **state word is deliberately absent**: it is derivable from the
    percentile and the bucket edges, and storing it would freeze today's display
    convention into historical rows (ADR 0006). What is carried is the raw
    reading, its rank, the denominator that rank came from, the era that bounded
    it, and the second leg beside it.
    """

    session: date
    index_vol: float
    percentile: float
    sample_size: int
    era_start: date | None
    second_leg: float | None


def _latest_close(bars: list[Bar]) -> float | None:
    """The series' last adjusted close — what an already-volatility series reads."""
    return bars[-1].adj_close if bars else None


# How each market's second leg is read off its series (spec §4.10). US reads
# **VIX** as it prints: an implied-vol index is already a volatility number. IDX
# has no implied-vol index at all, so its risk-off proxy is the **21-day
# annualized realized vol of USD/IDR** — the index reading's own computation, run
# on the currency. A table rather than a branch, for the same reason
# :data:`ARB_POLICY_ERAS` and :data:`~screener.source.SECOND_LEG` are: adding a
# market should be an entry, not an edit.
_SECOND_LEG_READING: dict[str, Callable[[list[Bar]], float | None]] = {
    "US": _latest_close,
    "IDX": realized_vol,
}


def second_leg_value(market: str, bars: list[Bar]) -> float | None:
    """The second leg's raw reading for ``market`` — context, never an input.

    ``None`` when the series cannot answer (no bars, or too short for the
    window). Never bucketed and never folded into the state (spec §4.10).
    """
    return _SECOND_LEG_READING[market](bars) if bars else None


def reading(
    market: str,
    session: date,
    index_bars: list[Bar],
    second_leg_bars: list[Bar],
) -> VolatilityReading | None:
    """This session's volatility readings, off the market's own two series.

    ``index_bars`` and ``second_leg_bars`` are the clean, oldest-first series
    **already filtered to ``session``** by the caller — the API reads them as of
    the last published run, the nightly capture as of the session it is writing,
    and neither wants the other's window.

    ``None`` before a first realized-vol reading exists (fewer than
    ``VOL_WINDOW + 1`` index bars, or none of them inside the ranking window),
    and ``None`` for a session of an era-bounded market that predates every
    recorded decree: its censoring regime is unknown, and ranking it would rank
    across decrees, which is the one thing ADR 0006 exists to prevent. Above that
    the reading is always returned, even when the sample is too thin to *state* —
    the percentile and its sample size are what makes the thinness visible, and
    the forward record wants the raw reading from day one, not from the day the
    display woke up.
    """
    era = current_era(market, session)
    if era is None and market in ARB_POLICY_ERAS:
        return None
    start = percentile_window_start(market, session)
    window = [vol for when, vol in vol_series(index_bars) if start <= when <= session]
    if not window:
        return None
    latest = window[-1]
    return VolatilityReading(
        session=session,
        index_vol=latest,
        percentile=percentile_of(latest, window),
        sample_size=len(window),
        era_start=era,
        second_leg=second_leg_value(market, second_leg_bars),
    )
