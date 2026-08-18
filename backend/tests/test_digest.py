"""The digest: tonight's breaks made into one Markdown file (spec §6 / ticket 42).

The break gets its one home. Membership is a single sentence — *report a name iff
today's close is above yesterday's trigger* — and consults neither the score nor
the stop nor ``line_ok``. Every break is reported; repeats are marked, not
suppressed. The stop column is computed from the **breakout day's low** (§7's real
default stop), deliberately different from the watchlist's cluster-low stop. An
empty night still writes a file with an explicit no-breaks line.
"""

from datetime import date

from screener.bars import Bar
from screener.detection import DETECTOR_VERSION, Detection
from screener.digest import DigestBreak, build_digest, render_digest
from screener.score import RUBRIC_VERSION
from screener.ranks import Rank

YESTERDAY = date(2026, 8, 4)
TODAY = date(2026, 8, 5)


def _det(symbol, *, trigger=100.0, adr=0.06, close=98.0, cluster_low=97.0,
         cluster_k=5, base_len=10, churn_l=0.45, sma20_rising=True, dryup=0.90,
         line_ok=True):
    """Yesterday's detection: the setup whose trigger the break tests against."""
    stop = trigger - cluster_low
    return Detection(
        symbol=symbol, session=YESTERDAY, detector_version=DETECTOR_VERSION,
        trigger=trigger, stop=stop, stopw_adr=stop / trigger / adr,
        base_len=base_len, move_gain=103.0, adr=adr, close=close,
        cluster_k=cluster_k, cluster_high=trigger, cluster_low=cluster_low,
        cluster_range_adr=0.99, line_ok=line_ok, touch_zones=2, overshoot_adr=0.0,
        slope=-0.001, line_end=trigger - 0.1, base_low=cluster_low,
        churn_l=churn_l, sma20_rising=sma20_rising, dryup=dryup,
    )


def _bar(session, *, close, low):
    """Today's bar for a symbol — only close and low matter to the digest."""
    return Bar(session, close, close + 1, low, close, close, 1_000_000)


def _decile(symbol):
    return [Rank(symbol, "1m", 0.95, 1.2), Rank(symbol, "3m", 0.95, 1.1)]


def test_a_name_is_reported_when_todays_close_exceeds_yesterdays_trigger():
    dets = [_det("UP", trigger=100.0), _det("FLAT", trigger=100.0)]
    today = {"UP": _bar(TODAY, close=101.0, low=99.0),
             "FLAT": _bar(TODAY, close=99.5, low=98.0)}
    breaks = build_digest(dets, today, _decile("UP") + _decile("FLAT"), {}, {}, {})
    assert [b.symbol for b in breaks] == ["UP"]  # FLAT did not clear its trigger
    assert breaks[0].close == 101.0
    assert breaks[0].trigger == 100.0


def test_membership_ignores_score_stop_and_line_ok():
    # A poor fit (line_ok False), a wide stop and a low score still report: the
    # only test is close > trigger.
    det = _det("WEAK", trigger=100.0, line_ok=False, cluster_low=80.0,
               cluster_k=3, base_len=40, churn_l=0.9, sma20_rising=False, dryup=1.5)
    today = {"WEAK": _bar(TODAY, close=100.01, low=95.0)}
    breaks = build_digest([det], today, [], {}, {}, {})
    assert [b.symbol for b in breaks] == ["WEAK"]


def test_a_name_with_no_bar_today_cannot_be_tested():
    # trigger_yesterday exists but the name did not resolve today — no close to test.
    breaks = build_digest([_det("GONE")], {}, [], {}, {}, {})
    assert breaks == []


def test_the_stop_is_computed_from_the_breakout_day_low_not_the_cluster_low():
    # Cluster low 97 (the watchlist stop), breakout-day low 99 — the digest uses 99.
    det = _det("AAA", trigger=100.0, adr=0.05, cluster_low=97.0)
    today = {"AAA": _bar(TODAY, close=101.0, low=99.0)}
    [b] = build_digest([det], today, [], {}, {}, {})
    # (entry − breakout_day_low) / entry / adr, entry = trigger.
    assert abs(b.stopw_adr - (100.0 - 99.0) / 100.0 / 0.05) < 1e-9
    # Deliberately different from the watchlist's cluster-low stop.
    assert abs(b.stopw_adr - det.stopw_adr) > 1e-6


def test_pct_through_measures_how_decisive_the_break_was():
    det = _det("AAOI", trigger=17.88)
    today = {"AAOI": _bar(TODAY, close=18.04, low=17.9)}
    [b] = build_digest([det], today, [], {}, {}, {})
    assert abs(b.pct_through - (18.04 - 17.88) / 17.88 * 100.0) < 1e-6


def test_the_star_score_and_industry_ride_the_row():
    # Every dimension hits → 4.5★ (nine-point ceiling, PRD #138); industry comes
    # from the label cache.
    ranks = _decile("AAA") + [Rank("PEER", "1m", 0.95, 1.0)]
    det = _det("AAA", trigger=100.0)
    today = {"AAA": _bar(TODAY, close=101.0, low=99.0)}
    [b] = build_digest(
        [det], today, ranks,
        {"AAA": "Semiconductors"}, {"AAA": "Technology", "PEER": "Technology"}, {},
    )
    assert b.score == 4.5
    assert b.industry == "Semiconductors"


def test_repeats_are_marked_with_the_last_reported_date_never_suppressed():
    det = _det("RPT", trigger=100.0)
    today = {"RPT": _bar(TODAY, close=101.0, low=99.0)}
    last = {"RPT": date(2026, 7, 28)}
    [b] = build_digest([det], today, [], {}, {}, last)
    assert b.repeat is True
    assert b.last_reported == date(2026, 7, 28)  # reported, not withheld


def test_a_first_time_break_carries_no_repeat_marker():
    det = _det("NEW", trigger=100.0)
    today = {"NEW": _bar(TODAY, close=101.0, low=99.0)}
    [b] = build_digest([det], today, [], {}, {}, {})
    assert b.repeat is False
    assert b.last_reported is None


def test_breaks_are_ordered_by_star_score_descending():
    strong = _det("LOW", trigger=100.0, adr=0.06)                       # 5★
    weak = _det("HIGH", trigger=100.0, adr=0.04, cluster_k=4, base_len=40)  # fewer points
    today = {"LOW": _bar(TODAY, close=101.0, low=99.0),
             "HIGH": _bar(TODAY, close=101.0, low=99.0)}
    breaks = build_digest([weak, strong], today, _decile("LOW") + _decile("HIGH"),
                          {}, {}, {})
    assert [b.symbol for b in breaks] == ["LOW", "HIGH"]
    assert breaks[0].score > breaks[1].score


def test_line_ok_failure_is_a_silent_tiebreak_below_equal_scored_names():
    accepted = _det("ZZZ", trigger=100.0, line_ok=True)
    failed = _det("AAA", trigger=100.0, line_ok=False)  # identical score
    today = {"ZZZ": _bar(TODAY, close=101.0, low=99.0),
             "AAA": _bar(TODAY, close=101.0, low=99.0)}
    breaks = build_digest([accepted, failed], today, _decile("ZZZ") + _decile("AAA"),
                          {}, {}, {})
    assert breaks[0].score == breaks[1].score
    assert [b.symbol for b in breaks] == ["ZZZ", "AAA"]
    # Nothing on the row marks the demotion — line_ok is not a field.
    assert not hasattr(breaks[1], "line_ok")


# -- the Markdown file --------------------------------------------------------


def test_render_writes_one_row_per_break_with_the_plain_language_rule():
    det = _det("AAOI", trigger=17.88)
    today = {"AAOI": _bar(TODAY, close=18.04, low=17.9)}
    breaks = build_digest([det], today, [], {"AAOI": "Semiconductors"}, {}, {})
    md = render_digest("US", TODAY, breaks)
    assert "2026-08-05" in md
    assert "AAOI" in md
    assert "17.88" in md and "18.04" in md
    # The membership rule, stated the way a trader can check by eye.
    assert "last four sessions" in md.lower()
    assert "no breaks" not in md.lower()


def test_render_marks_a_repeat_in_the_file():
    det = _det("RPT", trigger=100.0)
    today = {"RPT": _bar(TODAY, close=101.0, low=99.0)}
    breaks = build_digest([det], today, [], {}, {}, {"RPT": date(2026, 7, 28)})
    md = render_digest("US", TODAY, breaks)
    assert "2026-07-28" in md
    assert "↺" in md  # ↺


def test_the_digest_header_stamps_the_rubric_version():
    # A digest freezes its stars; the app derives them on read. The header records
    # which rubric produced them, so a frozen star and a live one can be compared
    # like with like after a rubric change (PRD #138).
    det = _det("AAOI", trigger=17.88)
    today = {"AAOI": _bar(TODAY, close=18.04, low=17.9)}
    breaks = build_digest([det], today, [], {"AAOI": "Semiconductors"}, {}, {})
    md = render_digest("US", TODAY, breaks)
    assert f"rubric v{RUBRIC_VERSION}" in md
    # Present on a quiet night too — the frozen scale is stated even with no rows.
    assert f"rubric v{RUBRIC_VERSION}" in render_digest("IDX", TODAY, [])


def test_an_empty_night_still_writes_a_file_with_an_explicit_no_breaks_line():
    md = render_digest("IDX", TODAY, [])
    assert "2026-08-05" in md
    assert "no breaks" in md.lower()
