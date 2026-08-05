"""The candidate list: tonight's detections made readable (spec §4.5 / §5.1).

Five columns off the detection row — ticker, star score (a placeholder until the
rubric lands), distance to trigger, stop width in ADR, industry and the ``k/5``
breadth badge. Ordered by ticker; the score sort is not yet live. The stop column
highlights the sub-1×ADR minority and filters nothing.
"""

from datetime import date

from screener.candidates import AFFORDABLE_ADR, build_candidates
from screener.detection import DETECTOR_VERSION, Detection
from screener.ranks import Rank


def _det(symbol, *, trigger=100.0, close=98.0, cluster_low=97.0, adr=0.02):
    """A detection with a chosen trigger/close/stop so the derived columns are
    predictable. ``adr_abs = adr × close``; ``stopw_adr`` is the stop in ADR."""
    adr_abs = adr * close
    stop = trigger - cluster_low
    return Detection(
        symbol=symbol, session=date(2026, 8, 5), detector_version=DETECTOR_VERSION,
        trigger=trigger, stop=stop, stopw_adr=stop / adr_abs,
        base_len=30, move_gain=103.0, adr=adr, close=close,
        cluster_k=5, cluster_high=trigger, cluster_low=cluster_low,
        cluster_range_adr=0.99, line_ok=True, touch_zones=2, overshoot_adr=0.0,
        slope=-0.001, line_end=trigger - 0.1, base_low=cluster_low,
    )


def test_columns_are_derived_from_the_detection_row():
    # A single name: trigger 100, close 98, cluster_low 97, adr 0.02.
    # adr_abs = 0.02 × 98 = 1.96; distance = (100 − 98)/1.96 ≈ 1.020 ADR;
    # stop width = (100 − 97)/1.96 ≈ 1.531 ADR.
    dets = [_det("AAA")]
    ranks = [Rank("AAA", "1m", 0.95, 1.2), Rank("AAA", "3m", 0.95, 1.1)]
    industry_of = {"AAA": "Semiconductors"}

    [c] = build_candidates(dets, ranks, industry_of)

    assert c.symbol == "AAA"
    assert c.score is None  # placeholder until the rubric lands (ticket 39)
    assert abs(c.dist_adr - (100.0 - 98.0) / (0.02 * 98.0)) < 1e-9
    assert abs(c.stopw_adr - (100.0 - 97.0) / (0.02 * 98.0)) < 1e-9
    assert c.industry == "Semiconductors"
    assert c.breadth == 2  # top-decile in 2 of the 5 lookbacks


def test_rows_are_ordered_by_ticker():
    dets = [_det("ZZZ"), _det("AAA"), _det("MMM")]
    rows = build_candidates(dets, [], {})
    assert [c.symbol for c in rows] == ["AAA", "MMM", "ZZZ"]


def test_affordable_minority_is_flagged_and_nothing_is_filtered():
    # One sub-1×ADR stop (affordable, highlighted), one wide stop (the majority).
    tight = _det("TIGHT", trigger=100.0, cluster_low=99.0, adr=0.02)   # 1/1.96 ≈ 0.51
    wide = _det("WIDE", trigger=100.0, cluster_low=95.0, adr=0.02)     # 5/1.96 ≈ 2.55
    rows = build_candidates([tight, wide], [], {})

    assert len(rows) == 2  # the stop column never filters
    by_sym = {c.symbol: c for c in rows}
    assert by_sym["TIGHT"].stopw_adr <= AFFORDABLE_ADR
    assert by_sym["TIGHT"].affordable is True
    assert by_sym["WIDE"].stopw_adr > AFFORDABLE_ADR
    assert by_sym["WIDE"].affordable is False


def test_missing_industry_and_absent_breadth_degrade_gracefully():
    [c] = build_candidates([_det("AAA")], [], {})
    assert c.industry is None  # label never fetched
    assert c.breadth == 0      # in no lookback's top decile
