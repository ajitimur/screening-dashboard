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
from .models import Candle, ChartFacts, ChartResponse, MaPoint
from .ranks import Rank

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
    adr_abs = detection.adr * detection.close
    dist_adr = (
        (detection.trigger - detection.close) / adr_abs if adr_abs > 0 else float("nan")
    )
    return ChartFacts(
        base_len=detection.base_len,
        trigger=detection.trigger,
        dist_adr=dist_adr,
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
) -> ChartResponse:
    """One symbol's evidence bundle (spec §5.1). ``bars`` is the name's clean,
    oldest-first series (already scoped to the as-of session by the caller);
    ``detection`` / ``ranks_for_symbol`` / ``sector`` are its published rows for
    tonight, feeding the facts block."""
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
        facts=_facts(detection, bars, ranks_for_symbol, sector),
    )
