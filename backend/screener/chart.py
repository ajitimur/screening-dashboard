"""The chart panel's evidence bundle: candles, the MA set and the facts block
(spec §5.1 / ticket 40).

Click a row, see a chart. This module turns one symbol's stored streams into the
single payload the chart panel renders — the nightly path's one repeated
interaction (spec §5.3). It composes what the pipeline already published for the
name, re-computing nothing about detection or ranking:

- **Candles** — the unadjusted OHLCV series (spec §3.5). The trigger and stop are
  real order levels a trader places, so the candles are drawn in the same
  unadjusted price they live in.
- **The daily MA set** — SMA 10/20/50 and the **65 EMA**, §2's daily set exactly,
  each a line series over every drawn bar (spec §5.1). Computed on the candle
  close so the lines overlay the candles coherently rather than drifting on a
  split; the detector's catch-up MA reasons the same way (``detection._sma_close``).
- **The facts block** — the numbers the candidate row deliberately left off, read
  here where the trade is decided: base length, trigger, distance, stop in ADR,
  ADR, dollar volume, the five decile ranks and sector (spec §5.1).

The MA lines are computed over the **full** stored history and then sliced to the
drawn window, so the first drawn point already carries a full window behind it
rather than restarting at the cut.
"""

from __future__ import annotations

from datetime import date

from .bars import Bar
from .detection import Detection
from .indicators import ema_series, median_dollar_volume, sma_series
from .models import Candle, ChartFacts, ChartResponse, MaPoint, ScoreRow, SetupOverlay
from .ranks import Rank
from .score import star_score

# The 65 EMA is the daily chart's one exponential (spec §2 / §4.2).
EMA_WINDOW = 65

# How many trailing bars the chart draws: enough to hold the prior move (windows
# up to 126 bars, §4.5) and the base with room around it, without shipping a
# name's whole decade of history in one payload.
CHART_BARS = 200


def _ma_points(sessions: list[date], series: list[float | None]) -> list[MaPoint]:
    """Line points for the drawn window, skipping the leading bars where the
    window had not yet filled (those come back as ``None`` from the series)."""
    return [
        MaPoint(session=s, value=v)
        for s, v in zip(sessions, series)
        if v is not None
    ]


def _argmax_high(bars: list[Bar], lo: int, hi: int) -> int:
    """Index in ``[lo, hi]`` of the highest high, first on a tie — the detector's
    own cluster anchor rule (``detection._argmax``), reconstructed here so the
    envelope is drawn from the same anchor it was fitted at."""
    return max(range(lo, hi + 1), key=lambda i: bars[i].high)


def _setup(
    detection: Detection | None,
    bars: list[Bar],
    *,
    prior_move: bool,
    sector_share: float,
) -> SetupOverlay | None:
    """The setup overlay for the chart (spec §5.1 / ticket 41), or ``None`` when the
    name has no detection tonight.

    ``bars`` is the full scoped series whose **last** bar is the detection's session
    (the caller scopes to on/before the as-of session), so the base and cluster are
    trailing spans: the base runs ``base_len`` bars back from today, the cluster
    ``cluster_k``. The envelope is rebuilt from the detection's persisted slope and
    cluster high, anchored at the cluster's max-high bar and evaluated over the base
    — a line the candles pierce, never "corrected" to sit above them (§3.2)."""
    if detection is None:
        return None
    n = len(bars)
    base_i = max(0, n - detection.base_len)
    cluster_i = max(0, n - detection.cluster_k)
    # The envelope is pinned at the cluster's max-high bar with the fitted slope,
    # extrapolated backwards over the base's bars (spec §4.5 step 4).
    anchor = _argmax_high(bars, cluster_i, n - 1)
    envelope = [
        MaPoint(
            session=bars[t].session,
            value=detection.cluster_high + detection.slope * (t - anchor),
        )
        for t in range(base_i, n)
    ]
    stars, breakdown = star_score(
        detection, prior_move=prior_move, sector_share=sector_share
    )
    return SetupOverlay(
        base_start=bars[base_i].session,
        cluster_start=bars[cluster_i].session,
        trigger=detection.trigger,     # cluster high, by identity
        stop=detection.cluster_low,    # the cluster-low stop rule (§4.6)
        envelope=envelope,
        score=stars,
        breakdown=[ScoreRow(**vars(d)) for d in breakdown],
    )


def _facts(
    detection: Detection | None,
    bars: list[Bar],
    ranks_for_symbol: list[Rank],
    sector: str | None,
) -> ChartFacts | None:
    """The facts block, or ``None`` when the name has no detection tonight — the
    chart still draws, but there is no base to describe."""
    if detection is None:
        return None
    return ChartFacts(
        base_len=detection.base_len,
        trigger=detection.trigger,
        dist_adr=detection.dist_adr,
        stopw_adr=detection.stopw_adr,
        adr=detection.adr,
        dollar_volume=median_dollar_volume(bars),
        decile_ranks={r.lookback: r.percentile for r in ranks_for_symbol},
        sector=sector,
    )


def build_chart(
    market: str,
    symbol: str,
    session: date | None,
    bars: list[Bar],
    detection: Detection | None,
    ranks_for_symbol: list[Rank],
    sector: str | None,
    *,
    prior_move: bool = False,
    sector_share: float = 0.0,
) -> ChartResponse:
    """One symbol's evidence bundle (spec §5.1). ``bars`` is the name's clean,
    oldest-first series (already scoped to the as-of session by the caller);
    ``detection`` / ``ranks_for_symbol`` / ``sector`` are its published rows for
    tonight, feeding the facts block. ``prior_move`` / ``sector_share`` are the two
    cross-sectional inputs to the star score (the decile gate and the leave-one-out
    1m sector share), supplied by the caller off the same session — they feed the
    setup overlay's breakdown, mirroring how :mod:`.candidates` scores the list."""
    closes = [b.close for b in bars]  # unadjusted — see the module docstring
    sma10 = sma_series(closes, 10)
    sma20 = sma_series(closes, 20)
    sma50 = sma_series(closes, 50)
    ema65 = ema_series(closes, EMA_WINDOW)

    lo = max(0, len(bars) - CHART_BARS)
    shown = bars[lo:]
    sessions = [b.session for b in shown]
    return ChartResponse(
        market=market,
        symbol=symbol,
        session=session,
        candles=[
            Candle(
                session=b.session, open=b.open, high=b.high,
                low=b.low, close=b.close, volume=b.volume,
            )
            for b in shown
        ],
        sma10=_ma_points(sessions, sma10[lo:]),
        sma20=_ma_points(sessions, sma20[lo:]),
        sma50=_ma_points(sessions, sma50[lo:]),
        ema65=_ma_points(sessions, ema65[lo:]),
        setup=_setup(
            detection, bars, prior_move=prior_move, sector_share=sector_share
        ),
        facts=_facts(detection, bars, ranks_for_symbol, sector),
    )
