"""Seam: the RS line — an index-relative candidate dimension under measurement
(issue #160).

``RS = adj_close(name) / adj_close(index)``, hit when today's ratio is at or
above the ratio at the detection's own ``base_start``. **Non-decayed, not a new
high**: a name that merely matched the index across its base passes.

Nothing here is scored. The dimension is computed and carried so #160's
pre-registered study can measure whether it earns a place in the rubric; the
rubric is untouched until that verdict lands.

Pure over two oldest-first ``list[Bar]`` series plus a ``base_start`` session —
no store, no network.
"""

from datetime import date, timedelta

import pytest

from screener.bars import Bar
from screener.detection import Detection
from screener.relative_strength import base_start_session, rs_line, rs_line_for

CAL = [date(2021, 3, 1) + timedelta(days=i) for i in range(40)]


def _bars(sessions, adj_closes):
    return [
        Bar(s, c, c, c, c, a, 1000)
        for s, c, a in zip(sessions, adj_closes, adj_closes)
    ]


def _flat(sessions, level=100.0):
    return _bars(sessions, [level] * len(sessions))


# -- the ratio rule -----------------------------------------------------------


def test_a_name_that_outran_the_index_over_its_base_hits():
    sessions = CAL[:10]
    name = _bars(sessions, [100.0 + i for i in range(10)])
    index = _flat(sessions)
    assert rs_line(name, index, base_start=sessions[0], as_of=sessions[-1]) is True


def test_a_name_that_lagged_the_index_over_its_base_misses():
    sessions = CAL[:10]
    name = _flat(sessions)
    index = _bars(sessions, [100.0 + i for i in range(10)])
    assert rs_line(name, index, base_start=sessions[0], as_of=sessions[-1]) is False


def test_merely_matching_the_index_hits__the_rule_is_non_decayed_not_a_new_high():
    """The dimension has no free parameter: an unchanged ratio passes.

    A strict-new-high form would fire only when the index fell during the base,
    which makes it a regime indicator wearing a rubric dimension's clothes —
    and §4.9 says regime never scores.
    """
    sessions = CAL[:10]
    name = _bars(sessions, [100.0 * (1.0 + 0.01 * i) for i in range(10)])
    index = _bars(sessions, [50.0 * (1.0 + 0.01 * i) for i in range(10)])
    assert rs_line(name, index, base_start=sessions[0], as_of=sessions[-1]) is True


def test_the_ratio_is_read_at_base_start_not_at_the_series_start():
    """Only the base is measured — a run-up before it must not count."""
    sessions = CAL[:10]
    # Doubles over the first five bars, then gives half of it back over the base.
    name = _bars(sessions, [100, 120, 140, 160, 180, 170, 160, 150, 140, 130])
    index = _flat(sessions)
    assert rs_line(name, index, base_start=sessions[0], as_of=sessions[-1]) is True
    assert rs_line(name, index, base_start=sessions[4], as_of=sessions[-1]) is False


def test_both_legs_read_adj_close__an_unadjusted_split_does_not_move_the_ratio():
    """A ratio on unadjusted closes jumps on every split; this one must not."""
    sessions = CAL[:6]
    # Unadjusted close halves at the split; adj_close is continuous.
    raw = [100.0, 100.0, 100.0, 50.0, 50.0, 50.0]
    adj = [50.0] * 6
    name = [Bar(s, c, c, c, c, a, 1000) for s, c, a in zip(sessions, raw, adj)]
    index = _flat(sessions)
    assert rs_line(name, index, base_start=sessions[0], as_of=sessions[-1]) is True


# -- the missing-bar rule -----------------------------------------------------


def test_a_missing_index_bar_scores_false_and_is_never_carried_forward():
    """Phantom bars are removed from series entirely and never zero-filled;
    inventing an index price to score against would break the same rule.

    Scoring ``False`` costs at most one point on a rare edge; excluding the name
    would let a data gap remove a candidate from the list.
    """
    sessions = CAL[:6]
    name = _bars(sessions, [100.0 + i for i in range(6)])
    index = _flat(sessions)
    gapped = [b for b in index if b.session != sessions[0]]
    assert rs_line(name, gapped, base_start=sessions[0], as_of=sessions[-1]) is False
    missing_today = [b for b in index if b.session != sessions[-1]]
    assert rs_line(
        name, missing_today, base_start=sessions[0], as_of=sessions[-1]
    ) is False


def test_a_missing_name_bar_scores_false():
    sessions = CAL[:6]
    name = _bars(sessions, [100.0 + i for i in range(6)])
    index = _flat(sessions)
    assert rs_line(
        [b for b in name if b.session != sessions[0]],
        index, base_start=sessions[0], as_of=sessions[-1],
    ) is False


@pytest.mark.parametrize("bad", [0.0, -1.0])
def test_a_non_positive_price_scores_false_rather_than_dividing_by_zero(bad):
    sessions = CAL[:6]
    name = _bars(sessions, [100.0] * 6)
    index = _bars(sessions, [bad] + [100.0] * 5)
    assert rs_line(name, index, base_start=sessions[0], as_of=sessions[-1]) is False


def test_an_empty_index_series_scores_false():
    sessions = CAL[:6]
    assert rs_line(
        _bars(sessions, [100.0] * 6), [],
        base_start=sessions[0], as_of=sessions[-1],
    ) is False


# -- resolving base_start off a detection -------------------------------------


def _det(session, base_len):
    return Detection(
        symbol="AAA", session=session, detector_version=2, trigger=100.0,
        stop=99.0, stopw_adr=0.345, base_len=base_len, move_gain=0.5, adr=0.06,
        close=100.0, cluster_k=5, cluster_high=100.0, cluster_low=98.0,
        cluster_range_adr=1.0, range_3bar_adr=0.9, line_ok=True, touch_zones=2,
        overshoot_adr=0.1, slope=-0.01, line_end=100.0, base_low=90.0,
        churn_l=0.45, sma20_rising=True, dryup=0.8,
    )


def test_base_start_walks_back_base_len_minus_one_traded_bars():
    """``base_start`` is not on the row — it is ``base_len`` traded bars back
    from the detection's own session, which is why no schema change is needed."""
    sessions = CAL[:10]
    bars = _flat(sessions)
    assert base_start_session(bars, sessions[-1], base_len=4) == sessions[-4]
    assert base_start_session(bars, sessions[-1], base_len=1) == sessions[-1]


def test_base_start_counts_traded_bars_not_calendar_days():
    """Weekends, holidays and phantom-dropped bars are simply absent from the
    series, so the walk-back is over the bars the name actually printed."""
    sessions = [CAL[0], CAL[1], CAL[5], CAL[9]]
    bars = _flat(sessions)
    assert base_start_session(bars, CAL[9], base_len=3) == CAL[1]


def test_base_start_is_none_when_the_series_is_too_short():
    bars = _flat(CAL[:3])
    assert base_start_session(bars, CAL[2], base_len=9) is None


def test_base_start_anchors_on_the_last_bar_on_or_before_the_session():
    """The detection's session always has a bar, but a caller slicing a series
    must not be handed a base that starts after the base did."""
    sessions = [CAL[0], CAL[1], CAL[2]]
    bars = _flat(sessions)
    assert base_start_session(bars, CAL[7], base_len=2) == CAL[1]


def test_rs_line_for_reads_the_detections_own_base():
    sessions = CAL[:10]
    # Flat across the whole series except a rise over the last three bars.
    name = _bars(sessions, [100.0] * 7 + [101.0, 102.0, 103.0])
    index = _flat(sessions)
    det = _det(sessions[-1], base_len=3)
    assert rs_line_for(det, name, index) is True

    # Over a base that starts before the dip, the same name gives ground.
    falling = _bars(sessions, [100.0] * 7 + [99.0, 98.0, 97.0])
    assert rs_line_for(_det(sessions[-1], base_len=3), falling, index) is False


def test_rs_line_for_scores_false_when_the_base_predates_the_series():
    sessions = CAL[:4]
    det = _det(sessions[-1], base_len=40)
    assert rs_line_for(det, _flat(sessions), _flat(sessions)) is False


# -- the base_start round-trip through the detector ---------------------------


def _detector_bars(hlc, calendar):
    return [
        Bar(calendar[i], close, high, low, close, close, 1000)
        for i, (high, low, close) in enumerate(hlc)
    ]


def _textbook_setup():
    """60 flat bars, a run-up 50 -> 99, then a 30-bar tight top ending today —
    the same shape ``tests/test_detection.py`` detects against."""
    hlc = [(50.5, 49.5, 50.0)] * 60
    for i in range(1, 16):
        p = 50.0 + (99.0 - 50.0) * i / 15
        hlc.append((p + 0.5, p - 0.5, p))
    hlc += [(100.5, 99.5, 100.0)] * 30
    return hlc


def test_base_start_recovers_the_detectors_own_base_from_the_persisted_row():
    """The round-trip the no-schema-change claim rests on.

    ``base_low`` is persisted as the minimum low **over the base**, so recomputing
    it between the recovered ``base_start`` and the detection's session must
    reproduce the stored value exactly. Off-by-one in the walk-back — or counting
    calendar days instead of traded bars — breaks this, where asserting the
    arithmetic against itself would not.
    """
    from screener.detection import detect

    calendar = [date(2026, 1, 1) + timedelta(days=i) for i in range(200)]
    bars = _detector_bars(_textbook_setup(), calendar)
    det = detect("AAA", bars, calendar[104])
    assert det is not None

    start = base_start_session(bars, det.session, base_len=det.base_len)
    over_base = [b for b in bars if start <= b.session <= det.session]
    assert len(over_base) == det.base_len
    assert min(b.low for b in over_base) == det.base_low
