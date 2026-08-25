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
from screener.indicators import anchor_date
from screener.relative_strength import (
    RELATIVE_MOVE_LOOKBACK,
    base_start_session,
    move_adr,
    relative_move_adr,
    relative_move_hit,
    rs_line,
    rs_line_for,
)

CAL = [date(2021, 3, 1) + timedelta(days=i) for i in range(40)]
# A calendar long enough to reach back a year, for the `Relative move` block
# below. The RS line is measured over a base and never needs one.
CAL_YEAR = [date(2021, 1, 1) + timedelta(days=i) for i in range(400)]


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


# -- Relative move: the second candidate dimension (#170) ---------------------
#
# The `6m` calendar return relative to ``MARKET_INDEX``, compounded, in ADR
# units. Pre-registered in ADR 0005 and measured by #171; nothing scores it.

_AS_OF = CAL_YEAR[-1]
_ANCHOR = anchor_date(_AS_OF, "6m")


def _step(sessions, before, after, *, adr_pct=0.05, anchor=None):
    """A series priced ``before`` through ``anchor`` and ``after`` past it.

    ``low == adj_close`` and ``high == adj_close × (1 + adr_pct)`` on every bar,
    so ``SMA20(high/low − 1)`` is exactly ``adr_pct`` and the ADR denominator is
    a fixture rather than an accident of the path.
    """
    anchor = anchor or _ANCHOR
    prices = [before if s <= anchor else after for s in sessions]
    return [
        Bar(s, p, p * (1 + adr_pct), p, p, p, 1000)
        for s, p in zip(sessions, prices)
    ]


def test_a_name_that_outran_the_index_over_6m_scores_positive():
    name = _step(CAL_YEAR, 100.0, 200.0)
    index = _step(CAL_YEAR, 100.0, 125.0)
    assert relative_move_adr(name, index, _AS_OF) > 0
    assert relative_move_hit(relative_move_adr(name, index, _AS_OF)) is True


def test_a_name_that_lagged_the_index_over_6m_scores_negative():
    name = _step(CAL_YEAR, 100.0, 110.0)
    index = _step(CAL_YEAR, 100.0, 125.0)
    assert relative_move_adr(name, index, _AS_OF) < 0
    assert relative_move_hit(relative_move_adr(name, index, _AS_OF)) is False


def test_the_relative_move_is_compounded_not_subtracted():
    """``(1 + stock)/(1 + index) − 1``, not ``stock − index``.

    Over six months a percentage-point difference and a multiple are different
    quantities, and only the second means "outran the market" (findings §3f).
    +100% against +25% is +60% relative, not +75pp.
    """
    name = _step(CAL_YEAR, 100.0, 200.0, adr_pct=0.10)
    index = _step(CAL_YEAR, 100.0, 125.0)
    assert relative_move_adr(name, index, _AS_OF) == pytest.approx(0.6 / 0.10)


def test_the_value_is_denominated_in_the_names_own_adr():
    """The same relative move on a twice-as-volatile name is half the value.

    The units are the point of the row: ADR is the method's volatility unit, and
    a +60% relative advance means something different on a 5% ADR name than on a
    10% one.
    """
    index = _step(CAL_YEAR, 100.0, 125.0)
    quiet = _step(CAL_YEAR, 100.0, 200.0, adr_pct=0.05)
    wild = _step(CAL_YEAR, 100.0, 200.0, adr_pct=0.10)
    assert relative_move_adr(quiet, index, _AS_OF) == pytest.approx(
        2 * relative_move_adr(wild, index, _AS_OF)
    )


def test_the_boolean_is_adr_invariant__the_cut_sits_at_zero():
    """ADR is positive, so the denominator cannot flip the sign.

    This is why the pre-registered cut is sited at zero and not at some number of
    ADR: a non-zero cut-point would be a magnitude read off the replay, which
    #128 Q2 forbids. The units buy the stored *value*, which is what a later
    grading question (ADR 0004) would be asked of — not the pass/fail.
    """
    index = _step(CAL_YEAR, 100.0, 125.0)
    for adr_pct in (0.01, 0.05, 0.50):
        assert relative_move_hit(
            relative_move_adr(_step(CAL_YEAR, 100.0, 130.0, adr_pct=adr_pct), index, _AS_OF)
        ) is True
        assert relative_move_hit(
            relative_move_adr(_step(CAL_YEAR, 100.0, 120.0, adr_pct=adr_pct), index, _AS_OF)
        ) is False


def test_matching_the_index_exactly_misses__the_rule_is_outran_not_kept_up():
    """A tie is measure-zero; the strictness is fixed so the definition has no
    ambiguity, and nothing rests on it. Contrast the RS line, whose ``>=`` was
    load-bearing because *non-decayed* was the whole concept there."""
    both = _step(CAL_YEAR, 100.0, 125.0)
    assert relative_move_adr(both, both, _AS_OF) == 0.0
    assert relative_move_hit(relative_move_adr(both, both, _AS_OF)) is False


def test_a_name_that_had_not_listed_6m_ago_is_absent_not_zero():
    """``None`` — absent — and the dimension scores ``False``.

    The rank table's own convention: a recent IPO is simply missing from the long
    lookbacks rather than zero-filled (§4.3). Scoring ``False`` costs at most a
    point on an edge, where *excluding* the name would let a data gap remove a
    candidate from the list.
    """
    young = _step(CAL_YEAR[-40:], 100.0, 200.0, anchor=CAL_YEAR[-40])
    index = _step(CAL_YEAR, 100.0, 125.0)
    assert relative_move_adr(young, index, _AS_OF) is None
    assert relative_move_hit(None) is False


def test_a_benchmark_with_no_bar_back_at_the_anchor_scores_absent():
    name = _step(CAL_YEAR, 100.0, 200.0)
    short_index = _step(CAL_YEAR[-40:], 100.0, 125.0, anchor=CAL_YEAR[-40])
    assert relative_move_adr(name, short_index, _AS_OF) is None


def test_under_twenty_bars_there_is_no_adr_and_so_no_value():
    """ADR is ``SMA20(high/low − 1)`` and is ``None`` until 20 bars exist, so a
    name with a long enough price history but too few *bars* is absent too."""
    sparse = [b for i, b in enumerate(_step(CAL_YEAR, 100.0, 200.0)) if i % 40 == 0]
    index = _step(CAL_YEAR, 100.0, 125.0)
    assert len(sparse) < 20
    assert relative_move_adr(sparse, index, _AS_OF) is None


def test_the_anchor_is_calendar_and_resolves_to_the_last_bar_on_or_before_it():
    """The one place this departs from the RS line's exact-bar rule.

    An anchor six calendar months back lands on a weekend or holiday about three
    days in ten; requiring a bar *on* it would score ``False`` on a calendar
    artefact rather than on the name. The RS line's anchors are traded sessions
    by construction, so exactness was free there and is not here.
    """
    traded = [s for s in CAL_YEAR if s != _ANCHOR]
    name = _step(traded, 100.0, 200.0)
    index = _step(traded, 100.0, 125.0)
    assert _ANCHOR not in {b.session for b in name}
    assert relative_move_adr(name, index, _AS_OF) == pytest.approx(0.6 / 0.05)


def test_the_window_is_a_parameter_so_the_study_can_carry_more_than_one():
    """#171 measures `12m` and `1w` beside the registered `6m`. The dimension is
    the `6m` one — :data:`RELATIVE_MOVE_LOOKBACK` — and the others are carried as
    lines on the contrast, not as candidate variants to choose between."""
    assert RELATIVE_MOVE_LOOKBACK == "6m"
    name = _step(CAL_YEAR, 100.0, 200.0, anchor=anchor_date(_AS_OF, "12m"))
    index = _step(CAL_YEAR, 100.0, 125.0, anchor=anchor_date(_AS_OF, "12m"))
    assert relative_move_adr(name, index, _AS_OF, lookback="12m") == pytest.approx(
        0.6 / 0.05
    )
    assert relative_move_adr(name, index, _AS_OF) == pytest.approx(0.0)


def test_a_benchmark_that_lost_everything_is_absent_rather_than_a_divide_by_zero():
    """A −100% index makes the compounding denominator zero. It cannot happen on
    real bars, and the guard is here so that if it ever does the dimension goes
    absent like every other missing leg rather than taking the caller down."""
    name = _step(CAL_YEAR, 100.0, 200.0)
    wiped = [Bar(b.session, b.open, b.high, b.low, b.close, 0.0, 1000)
             if b.session > _ANCHOR else b
             for b in _step(CAL_YEAR, 100.0, 100.0)]
    assert relative_move_adr(name, wiped, _AS_OF) is None


def test_the_adr_leg_is_denominated_at_as_of_and_never_reads_past_it():
    """The replay hands whole bar series in and never slices them to the session
    (``replay.field``), which is only safe if the dimension does its own slicing.
    ``adr`` averages the last 20 bars of whatever it is given, so without this a
    2019 session would be denominated by 2022's volatility.
    """
    index = _step(CAL_YEAR, 100.0, 125.0)
    quiet = _step(CAL_YEAR, 100.0, 200.0, adr_pct=0.05)
    # The same name, its range blowing out *after* the session being scored.
    later = [
        b if b.session <= _AS_OF else Bar(
            b.session, b.open, b.low * 2, b.low, b.close, b.adj_close, b.volume
        )
        for b in _step(CAL_YEAR + [_AS_OF + timedelta(days=i) for i in range(1, 40)],
                       100.0, 200.0, adr_pct=0.05)
    ]
    assert relative_move_adr(later, index, _AS_OF) == pytest.approx(
        relative_move_adr(quiet, index, _AS_OF)
    )


def test_a_name_with_no_range_at_all_is_absent_rather_than_a_divide_by_zero():
    """``ADR`` is zero when every bar prints ``high == low``. Phantom bars are
    already stripped at ingest, but a halted name that traded at one price is not
    a phantom, and zero in the denominator would take the caller down."""
    index = _step(CAL_YEAR, 100.0, 125.0)
    rangeless = [
        Bar(b.session, b.low, b.low, b.low, b.low, b.adj_close, 1000)
        for b in _step(CAL_YEAR, 100.0, 200.0)
    ]
    assert relative_move_adr(rangeless, index, _AS_OF) is None


# -- the raw move, the un-benchmarked sibling (#171) ---------------------------
#
# `move_adr` is **not** a registered candidate and never can be: ADR 0005 admits
# one variant per registration, and `Relative move` is it. This is the raw column
# §3f measured — the prior move itself, before the index is netted out — carried
# by #171's contrast so the relative figure can be read against the thing it is
# relative to. It shares the ADR denominator, and therefore the slicing guard,
# with the registered dimension; that shared site is the reason it lives here
# rather than in the study script.


def test_the_raw_move_is_the_return_in_the_names_own_adr():
    name = _step(CAL_YEAR, 100.0, 200.0, adr_pct=0.10)
    assert move_adr(name, _AS_OF) == pytest.approx(1.0 / 0.10)


def test_the_raw_move_nets_out_nothing__that_is_the_whole_difference():
    """The pair #171 reports side by side: a name that doubled while the index
    rose 25% has a raw move of +100% and a relative one of +60%. Netting the
    index out is what turns the first into the second, and reporting only one of
    them is what §3f warns leaves the tape unaccounted for."""
    name = _step(CAL_YEAR, 100.0, 200.0, adr_pct=0.05)
    index = _step(CAL_YEAR, 100.0, 125.0)
    assert move_adr(name, _AS_OF) == pytest.approx(1.0 / 0.05)
    assert relative_move_adr(name, index, _AS_OF) == pytest.approx(0.6 / 0.05)


def test_the_raw_moves_adr_leg_is_sliced_at_as_of_too():
    """The same lookahead guard, asserted separately: two functions sharing a
    helper is not the same as two functions both being tested for the leak."""
    quiet = _step(CAL_YEAR, 100.0, 200.0, adr_pct=0.05)
    later = [
        b if b.session <= _AS_OF else Bar(
            b.session, b.open, b.low * 2, b.low, b.close, b.adj_close, b.volume
        )
        for b in _step(CAL_YEAR + [_AS_OF + timedelta(days=i) for i in range(1, 40)],
                       100.0, 200.0, adr_pct=0.05)
    ]
    assert move_adr(later, _AS_OF) == pytest.approx(move_adr(quiet, _AS_OF))


def test_the_raw_move_carries_the_same_absent_rules():
    young = _step(CAL_YEAR[-40:], 100.0, 200.0, anchor=CAL_YEAR[-40])
    rangeless = [
        Bar(b.session, b.low, b.low, b.low, b.low, b.adj_close, 1000)
        for b in _step(CAL_YEAR, 100.0, 200.0)
    ]
    assert move_adr(young, _AS_OF) is None
    assert move_adr(rangeless, _AS_OF) is None


def test_the_raw_move_takes_the_same_windows_the_relative_one_does():
    name = _step(CAL_YEAR, 100.0, 200.0, anchor=anchor_date(_AS_OF, "12m"))
    assert move_adr(name, _AS_OF, lookback="12m") == pytest.approx(1.0 / 0.05)
    assert move_adr(name, _AS_OF, lookback="1w") == pytest.approx(0.0)
