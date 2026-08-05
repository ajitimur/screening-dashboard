"""The chart panel's evidence bundle: candles, the MA set and the facts block
(spec §5.1 / ticket 40).

One symbol's evidence in a single call — the unadjusted candles, the daily MA set
drawn as line series (SMA 10/20/50 and the 65 EMA, spec §2), and the facts block
the candidate row deliberately left off (base length, trigger, distance, stop in
ADR, ADR, dollar volume, the five decile ranks and sector).

Pure over the store's rows; no network.
"""

from datetime import date, timedelta

from screener.bars import Bar
from screener.chart import CHART_BARS, build_chart
from screener.detection import DETECTOR_VERSION, Detection
from screener.ranks import Rank

CAL = [date(2026, 1, 1) + timedelta(days=i) for i in range(300)]


def _bars(n, *, close=100.0, volume=1000):
    return [Bar(CAL[i], close, close + 1, close - 1, close, close, volume) for i in range(n)]


def _det(symbol, session, *, trigger=100.0, close=98.0, cluster_low=97.0, adr=0.02):
    adr_abs = adr * close
    stop = trigger - cluster_low
    return Detection(
        symbol=symbol, session=session, detector_version=DETECTOR_VERSION,
        trigger=trigger, stop=stop, stopw_adr=stop / adr_abs,
        base_len=30, move_gain=103.0, adr=adr, close=close,
        cluster_k=5, cluster_high=trigger, cluster_low=cluster_low,
        cluster_range_adr=0.99, line_ok=True, touch_zones=2, overshoot_adr=0.0,
        slope=-0.001, line_end=trigger - 0.1, base_low=cluster_low,
        churn_l=0.45, sma20_rising=True, dryup=0.90,
    )


def test_bundle_carries_candles_and_the_four_ma_lines():
    bars = _bars(100)
    chart = build_chart("US", "AAA", CAL[99], bars, None, [], None)
    assert chart.market == "US"
    assert chart.symbol == "AAA"
    # One candle per bar, OHLCV preserved (unadjusted).
    assert len(chart.candles) == 100
    assert chart.candles[0].session == CAL[0]
    assert chart.candles[-1].close == 100.0
    # The daily set: SMA 10/20/50 and the 65 EMA, each a line series that starts
    # once its window has filled (so shorter than the candles).
    assert len(chart.sma10) == 100 - 9
    assert len(chart.sma20) == 100 - 19
    assert len(chart.sma50) == 100 - 49
    assert len(chart.ema65) == 100 - 64


def test_chart_window_is_capped_but_ma_lines_start_full():
    # More history than the drawn window: candles are the trailing CHART_BARS, and
    # the MA lines are computed over the *full* history, so the first drawn SMA10
    # point already carries a full window behind it (not restarted at the cut).
    bars = _bars(CHART_BARS + 50)
    chart = build_chart("US", "AAA", CAL[CHART_BARS + 49], bars, None, [], None)
    assert len(chart.candles) == CHART_BARS
    # Every drawn candle has an SMA10 point — none dropped for a short window.
    assert len(chart.sma10) == CHART_BARS


def test_facts_block_is_reconstructed_from_the_detection():
    bars = _bars(100, close=98.0, volume=1000)
    det = _det("AAA", CAL[99], trigger=100.0, close=98.0, cluster_low=97.0, adr=0.02)
    ranks = [Rank("AAA", "1m", 0.95, 1.2), Rank("AAA", "3m", 0.90, 1.1)]
    chart = build_chart("US", "AAA", CAL[99], bars, det, ranks, "Technology")

    f = chart.facts
    assert f is not None
    assert f.base_len == 30
    assert f.trigger == 100.0
    # distance = (100 − 98)/(0.02×98) ≈ 1.020 ADR.
    assert abs(f.dist_adr - (100.0 - 98.0) / (0.02 * 98.0)) < 1e-9
    assert abs(f.stopw_adr - (100.0 - 97.0) / (0.02 * 98.0)) < 1e-9
    assert f.adr == 0.02
    assert f.dollar_volume == 98.0 * 1000  # median close×volume over the flat series
    assert f.decile_ranks == {"1m": 0.95, "3m": 0.90}  # the five decile ranks
    assert f.sector == "Technology"


def test_facts_are_none_without_a_detection():
    # A symbol with bars but no detection tonight still draws — there is just no
    # base to describe, so the whole facts block is absent.
    chart = build_chart("US", "AAA", CAL[99], _bars(100), None, [], "Technology")
    assert chart.facts is None
