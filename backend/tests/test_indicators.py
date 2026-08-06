"""Seam 6a: the indicator substrate — ADR, simple MAs and calendar-anchored
returns (spec §4.2).

The load-bearing distinction this seam pins down is §4.2's traded-bar / calendar
split: rolling statistics (ADR, MAs) count *traded* bars — "the last 20 days this
thing actually traded" — while **returns are calendar-anchored** via the last bar
on or before the anchor date, so a name missing sessions is not handed a longer
effective window and systematically flattered.

Every function is pure over a clean, oldest-first ``list[Bar]``; no store, no
network.
"""

from datetime import date, timedelta

from screener.bars import Bar
from screener.indicators import (
    ADR_WINDOW,
    LOOKBACKS,
    adr,
    adr_abs,
    anchor_date,
    calendar_return,
    ema_series,
    median_dollar_volume,
    sma,
    sma_series,
)


def _bar(session, *, high=101.0, low=99.0, close=100.0, adj_close=None):
    return Bar(session, close, high, low, close, adj_close or close, 1000)


def _series(sessions, **kw):
    return [_bar(s, **kw) for s in sessions]


CAL = [date(2026, 7, 1) + timedelta(days=i) for i in range(40)]


# -- ADR: SMA20 of high/low − 1 over traded bars (§4.2) -----------------------


def test_adr_is_the_mean_high_low_range_over_the_trailing_twenty():
    # Every bar spans 110/100 − 1 = 0.10, so the SMA20 is exactly 0.10.
    bars = [_bar(s, high=110.0, low=100.0) for s in CAL[:20]]
    assert abs(adr(bars) - 0.10) < 1e-12


def test_adr_counts_traded_bars_not_a_calendar_window():
    # 25 bars but a ragged calendar (gaps between sessions); ADR still reads the
    # last 20 *traded* bars, indifferent to how many calendar days they span.
    ragged = [CAL[i] for i in (0, 3, 4, 9, 10, 11, 15, 16, 17, 18)] + CAL[20:35]
    bars = [_bar(s, high=103.0, low=100.0) for s in ragged]  # range 0.03 each
    assert len(bars) == 25
    assert abs(adr(bars) - 0.03) < 1e-12


def test_adr_needs_a_full_window_else_none():
    assert adr(_series(CAL[: ADR_WINDOW - 1])) is None
    assert adr(_series(CAL[:ADR_WINDOW])) is not None


def test_adr_abs_is_adr_times_the_last_close():
    bars = [_bar(s, high=110.0, low=100.0, close=50.0) for s in CAL[:20]]
    assert abs(adr_abs(bars) - 0.10 * 50.0) < 1e-12


# -- simple MAs on adjusted closes (§4.2) -------------------------------------


def test_sma_averages_adjusted_closes_over_the_window():
    # adj_close climbs 1..10; SMA10 = mean(1..10) = 5.5, SMA of last 3 = 9.
    bars = [_bar(CAL[i], adj_close=float(i + 1)) for i in range(10)]
    assert sma(bars, 10) == 5.5
    assert sma(bars, 3) == 9.0


def test_sma_uses_adjusted_not_unadjusted_close():
    bars = [_bar(CAL[i], close=999.0, adj_close=2.0) for i in range(5)]
    assert sma(bars, 5) == 2.0  # would be 999 if it read the unadjusted close


def test_sma_needs_a_full_window_else_none():
    assert sma(_series(CAL[:4]), 5) is None


# -- MA series and the 65 EMA for the chart panel (§4.2 / §5.1, ticket 40) ----


def test_sma_series_is_the_rolling_mean_none_until_the_window_fills():
    # A rolling window over closes: None until `window` values exist, then the
    # trailing mean at each index. Values climb 1..5, window 3.
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert sma_series(values, 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_series_matches_the_point_sma_at_the_last_bar():
    # The series' last point equals indicators.sma over the same window — one
    # definition of a moving average, computed for every bar rather than the last.
    bars = [_bar(CAL[i], adj_close=float(i + 1)) for i in range(10)]
    closes = [b.adj_close for b in bars]
    assert sma_series(closes, 10)[-1] == sma(bars, 10)


def test_ema_series_seeds_on_the_first_window_and_then_smooths():
    # Seeded by the SMA of the first `window` values; None before it fills.
    values = [float(i + 1) for i in range(5)]  # 1..5
    series = ema_series(values, 3)
    assert series[0] is None and series[1] is None
    assert series[2] == 2.0  # SMA(1,2,3) seed at the first full window
    # α = 2/(3+1) = 0.5; next = 0.5·4 + 0.5·2 = 3.0, then 0.5·5 + 0.5·3 = 4.0.
    assert series[3] == 3.0
    assert series[4] == 4.0


def test_ema_series_is_all_none_below_the_window():
    assert ema_series([1.0, 2.0], 3) == [None, None]


def test_median_dollar_volume_is_the_median_over_the_trailing_window():
    # dollar_volume = unadjusted close × volume; median over the last ADR_WINDOW
    # traded bars. Closes 1..25 at volume 1 → dollar volumes 1..25; the median of
    # the trailing 20 (values 6..25) is (15+16)/2 = 15.5.
    bars = [_bar(CAL[i], close=float(i + 1)) for i in range(25)]
    bars = [Bar(b.session, b.open, b.high, b.low, b.close, b.adj_close, 1) for b in bars]
    assert median_dollar_volume(bars) == 15.5


def test_median_dollar_volume_is_none_without_bars():
    assert median_dollar_volume([]) is None


# -- calendar-anchored returns (§4.2 / ticket 06 R7) --------------------------


def test_one_week_return_anchors_seven_calendar_days_back():
    # 1w = 7 calendar days. as_of 2026-07-15, anchor 2026-07-08.
    assert anchor_date(date(2026, 7, 15), "1w") == date(2026, 7, 8)


def test_calendar_months_anchor_by_month_not_by_bar_count():
    assert anchor_date(date(2026, 8, 5), "1m") == date(2026, 7, 5)
    assert anchor_date(date(2026, 8, 5), "3m") == date(2026, 5, 5)
    assert anchor_date(date(2026, 8, 5), "12m") == date(2025, 8, 5)


def test_month_anchor_clamps_a_short_month():
    # 31 March minus one month has no 31 Feb; clamp to the month's last day.
    assert anchor_date(date(2026, 3, 31), "1m") == date(2026, 2, 28)


def test_return_uses_the_last_bar_on_or_before_each_anchor():
    # Daily bars; a 1w return over a flat-then-jump series. as_of has no bar on
    # the exact day, and neither does the anchor — both fall back to the last
    # bar at or before, uniformly (weekends, holidays, phantom gaps).
    bars = [_bar(CAL[i], adj_close=100.0) for i in range(7)]  # Jul 1..7 at 100
    bars += [_bar(CAL[i], adj_close=120.0) for i in range(7, 14)]  # Jul 8..14 at 120
    # as_of Jul 14 (last bar 120), anchor Jul 7 (last bar 100) -> +20%.
    r = calendar_return(bars, date(2026, 7, 14), "1w")
    assert abs(r - 0.20) < 1e-12


def test_return_falls_back_across_a_gap_to_the_prior_bar():
    # No bar exactly on the anchor date; the last bar before it is used.
    bars = [_bar(date(2026, 7, 6), adj_close=100.0), _bar(date(2026, 7, 13), adj_close=110.0)]
    # as_of Jul 13, 1w anchor Jul 6 -> exact bar 100 -> +10%.
    assert abs(calendar_return(bars, date(2026, 7, 13), "1w") - 0.10) < 1e-12
    # Now drop the Jul 6 bar; anchor Jul 6 has no bar on or before -> absent.
    assert calendar_return(bars[1:], date(2026, 7, 13), "1w") is None


def test_a_name_without_history_before_the_anchor_is_absent_not_zero():
    # A recent listing: only 10 days old. Absent from 3m rather than 0% return.
    bars = _series(CAL[30:40], adj_close=100.0)
    assert calendar_return(bars, CAL[39], "3m") is None
    assert calendar_return(bars, CAL[39], "1w") is not None  # 1w is in range


def test_lookbacks_are_the_five_windows_shortest_first():
    assert LOOKBACKS == ("1w", "1m", "3m", "6m", "12m")
