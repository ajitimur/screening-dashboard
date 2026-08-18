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


def test_bars_window_draws_the_trailing_n_but_ma_lines_still_start_full():
    # A thumbnail asks for the last 60 bars, not the full stored history (spec
    # §4.6). The candles are the trailing N, and the MA lines are still computed
    # over the *full* history and sliced to that window, so the first drawn SMA10
    # already carries a full window behind it rather than restarting at the cut.
    bars = _bars(200)
    chart = build_chart("US", "AAA", CAL[199], bars, None, [], None, window=60)
    assert len(chart.candles) == 60
    assert chart.candles[0].session == CAL[140]
    assert chart.candles[-1].session == CAL[199]
    # Every drawn candle has an SMA10 point — none dropped for a short window.
    assert len(chart.sma10) == 60


def test_bars_window_larger_than_history_draws_everything():
    # Asking for more bars than exist just draws all of them — no padding.
    bars = _bars(40)
    chart = build_chart("US", "AAA", CAL[39], bars, None, [], None, window=60)
    assert len(chart.candles) == 40


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


def test_setup_overlay_shades_base_and_cluster_and_draws_the_envelope():
    # The setup drawn on the candles (spec §5.1 / ticket 41): the base shaded from
    # its start to today, the cluster shaded inside it, the trigger/stop levels and
    # the envelope as a line series.
    bars = _bars(100, close=98.0, volume=1000)
    det = _det("AAA", CAL[99], trigger=100.0, close=98.0, cluster_low=97.0, adr=0.02)
    chart = build_chart(
        "US", "AAA", CAL[99], bars, det, [], "Technology",
        prior_move=True, sector_share=0.2,
    )

    s = chart.setup
    assert s is not None
    # base_len=30 ends today (CAL[99]), so it starts 30 bars back at CAL[70].
    assert s.base_start == CAL[70]
    # cluster_k=5 trailing bars: starts at CAL[95].
    assert s.cluster_start == CAL[95]
    # The two horizontal rules: trigger is the cluster high, stop is the proposed
    # convention stop line (trigger − budget, issue #127). This fixture's budget is
    # trigger − cluster_low, so the line coincides with the cluster low (97.0) here.
    assert s.trigger == 100.0
    assert s.stop == det.stop_price == 97.0
    # The envelope is a line series over the base span, one point per base bar.
    assert len(s.envelope) == det.base_len
    assert s.envelope[0].session == CAL[70]
    assert s.envelope[-1].session == CAL[99]
    # A downward-sloping trendline: non-increasing over time, and by today (the
    # last point) it sits at or below the trigger, so it never sets the trigger.
    values = [p.value for p in s.envelope]
    assert values == sorted(values, reverse=True)
    assert s.envelope[-1].value <= det.trigger + 1e-9


def test_setup_breakdown_reconstructs_the_star_score_arithmetically():
    # The eight-row §4.7 breakdown sits with the chart and reconstructs the score:
    # sum(weight where hit) ÷ 2 = stars.
    bars = _bars(100, close=98.0, volume=1000)
    det = _det("AAA", CAL[99])  # cluster_k=5, churn_l=0.45, sma20_rising, dryup=0.90
    chart = build_chart(
        "US", "AAA", CAL[99], bars, det, [], "Technology",
        prior_move=True, sector_share=0.2,
    )
    s = chart.setup
    assert s is not None
    assert [d.dimension for d in s.breakdown] == [
        "Tightness", "Orderliness", "Prior move", "Base length",
        "MA support", "Volume", "Sector", "ADR",
    ]
    points = sum(d.weight for d in s.breakdown if d.hit)
    assert s.score == points / 2


def test_setup_is_none_without_a_detection():
    # No base tonight — nothing to shade or break down, so the whole overlay is
    # absent (the candles still draw).
    chart = build_chart("US", "AAA", CAL[99], _bars(100), None, [], "Technology")
    assert chart.setup is None
