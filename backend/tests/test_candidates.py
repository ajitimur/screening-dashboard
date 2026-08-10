"""The candidate list: tonight's detections made readable (spec §4.5 / §4.7 / §5.1).

Five columns off the detection row — ticker, star score, distance to trigger,
stop width in ADR, industry and the ``k/5`` breadth badge. The list sorts by star
score descending, with ``line_ok`` failures a **silent** tiebreak below
equal-scored accepted names. The stop column highlights the sub-1×ADR minority and
filters nothing.
"""

from datetime import date

from screener.candidates import AFFORDABLE_ADR, build_candidates
from screener.detection import DETECTOR_VERSION, Detection
from screener.ranks import Rank


def _det(
    symbol,
    *,
    trigger=100.0,
    close=98.0,
    cluster_low=97.0,
    adr=0.06,
    cluster_k=5,
    base_len=10,
    churn_l=0.45,
    sma20_rising=True,
    dryup=0.90,
    line_ok=True,
):
    """A detection with the derived columns and the eight scored signals dialable
    so the score, the sort and the tiebreak are all predictable. ``adr_abs =
    adr × close``; ``stopw_adr`` is the stop in ADR."""
    adr_abs = adr * close
    stop = trigger - cluster_low
    return Detection(
        symbol=symbol, session=date(2026, 8, 5), detector_version=DETECTOR_VERSION,
        trigger=trigger, stop=stop, stopw_adr=stop / adr_abs,
        base_len=base_len, move_gain=103.0, adr=adr, close=close,
        cluster_k=cluster_k, cluster_high=trigger, cluster_low=cluster_low,
        cluster_range_adr=0.99, line_ok=line_ok, touch_zones=2, overshoot_adr=0.0,
        slope=-0.001, line_end=trigger - 0.1, base_low=cluster_low,
        churn_l=churn_l, sma20_rising=sma20_rising, dryup=dryup,
    )


def _decile(symbol):
    """Rank rows putting ``symbol`` top-decile in 1m and 3m (prior-move point,
    two of five for the k/5 badge)."""
    return [Rank(symbol, "1m", 0.95, 1.2), Rank(symbol, "3m", 0.95, 1.1)]


def test_columns_are_derived_from_the_detection_row():
    # trigger 100, close 98, cluster_low 97, adr 0.06 → adr_abs = 5.88.
    dets = [_det("AAA", adr=0.06)]
    [c] = build_candidates(dets, _decile("AAA"), {"AAA": "Semiconductors"}, {})
    assert c.symbol == "AAA"
    assert abs(c.dist_adr - (100.0 - 98.0) / (0.06 * 98.0)) < 1e-9
    assert abs(c.stopw_adr - (100.0 - 97.0) / (0.06 * 98.0)) < 1e-9
    assert c.industry == "Semiconductors"
    assert c.breadth == 2  # top-decile in 2 of the 5 lookbacks


def test_the_score_is_the_star_rubric_and_its_eight_row_breakdown():
    # Every dimension hits: tight k=5, orderly 0.45, prior move (1m decile),
    # base_len 10, MA rising, dry-up 0.90, sector share ≥ 0.10, ADR 0.06.
    ranks = _decile("AAA") + [Rank("PEER", "1m", 0.95, 1.0)]
    sector_of = {"AAA": "Technology", "PEER": "Technology"}
    [c] = build_candidates([_det("AAA")], ranks, {}, sector_of)
    assert c.score == 5.0
    assert len(c.breakdown) == 8
    assert all(row.hit for row in c.breakdown)
    assert sum(row.weight for row in c.breakdown if row.hit) == 10


def test_the_list_sorts_by_star_score_descending():
    strong = _det("LOW", adr=0.06)                       # 5★
    weak = _det("HIGH", adr=0.04, cluster_k=4, base_len=40)  # loses tightness+len+adr
    rows = build_candidates([weak, strong], _decile("LOW") + _decile("HIGH"), {}, {})
    # Sorted by score, not by ticker — the strong 5★ leads the weaker name.
    assert [c.symbol for c in rows] == ["LOW", "HIGH"]
    assert rows[0].score > rows[1].score


def test_line_ok_failure_sorts_below_an_equal_scored_accepted_name():
    accepted = _det("ZZZ", line_ok=True)
    failed = _det("AAA", line_ok=False)  # identical score, but a poor fit
    rows = build_candidates([accepted, failed], _decile("AAA") + _decile("ZZZ"), {}, {})
    assert rows[0].score == rows[1].score            # a genuine tie on score
    assert [c.symbol for c in rows] == ["ZZZ", "AAA"]  # the failure sinks below


def test_nothing_in_the_row_marks_a_line_ok_failure():
    failed = _det("AAA", line_ok=False)
    [c] = build_candidates([failed], _decile("AAA"), {}, {})
    # The payload carries no line_ok field and no marker of it — a silent tiebreak.
    assert not hasattr(c, "line_ok")
    assert "line_ok" not in c.model_dump()


def test_ticker_breaks_a_remaining_tie_for_a_stable_order():
    # Same score, same line_ok — order falls back to ticker.
    rows = build_candidates(
        [_det("ZZZ"), _det("AAA"), _det("MMM")],
        _decile("ZZZ") + _decile("AAA") + _decile("MMM"),
        {}, {},
    )
    assert [c.symbol for c in rows] == ["AAA", "MMM", "ZZZ"]


def test_the_leave_one_out_sector_share_removes_the_candidate_itself():
    # A lone decile member of its sector: naively it is 1/1 = 100%, but leaving
    # itself out drops the share to 0 — the sector point is not awarded.
    ranks = [Rank("SOLO", "1m", 0.95, 1.2)]
    [c] = build_candidates([_det("SOLO")], ranks, {}, {"SOLO": "Energy"})
    sector = next(r for r in c.breakdown if r.dimension == "Sector")
    assert sector.hit is False


def test_the_score_is_blind_to_the_stop_width():
    # Two names identical except for the stop (cluster_low): same score.
    tight = _det("TIGHT", cluster_low=99.5)
    wide = _det("WIDE", cluster_low=90.0)
    rows = build_candidates([tight, wide], _decile("TIGHT") + _decile("WIDE"), {}, {})
    assert rows[0].score == rows[1].score


def test_affordable_minority_is_flagged_and_nothing_is_filtered():
    tight = _det("TIGHT", trigger=100.0, cluster_low=99.0, adr=0.02)   # 1/1.96 ≈ 0.51
    wide = _det("WIDE", trigger=100.0, cluster_low=95.0, adr=0.02)     # 5/1.96 ≈ 2.55
    rows = build_candidates([tight, wide], [], {}, {})
    assert len(rows) == 2  # the stop column never filters
    by_sym = {c.symbol: c for c in rows}
    assert by_sym["TIGHT"].stopw_adr <= AFFORDABLE_ADR
    assert by_sym["TIGHT"].affordable is True
    assert by_sym["WIDE"].stopw_adr > AFFORDABLE_ADR
    assert by_sym["WIDE"].affordable is False


def test_missing_industry_and_absent_breadth_degrade_gracefully():
    [c] = build_candidates([_det("AAA")], [], {}, {})
    assert c.industry is None  # label never fetched
    assert c.breadth == 0      # in no lookback's top decile


def test_chart_facts_are_folded_onto_the_row():
    # A Setups card renders trigger/stop/distance without a per-symbol chart fetch:
    # the fields that lived only in the chart bundle now ride the candidate row,
    # projected from the same detection (spec §4.3). trigger_price/stop_price are
    # the borrowed names for the overlay's trigger (cluster high) and stop
    # (cluster low); risk_adr is NOT adopted — stopw_adr keeps its name.
    det = _det("AAA", trigger=100.0, close=98.0, cluster_low=97.0, adr=0.06)
    ranks = [Rank("AAA", "1m", 0.95, 1.2), Rank("AAA", "3m", 0.90, 1.1)]
    [c] = build_candidates(
        [det], ranks, {}, {"AAA": "Technology"},
        dollar_volume_of={"AAA": 1234.0}, prev_detected={"OLD"},
    )
    assert c.trigger_price == 100.0            # overlay.trigger = cluster high
    assert c.stop_price == 97.0                # overlay.stop = cluster low
    assert c.close == 98.0
    assert c.sector == "Technology"            # new on the row; industry stays too
    assert c.adr == 0.06
    assert c.dollar_volume == 1234.0
    assert c.decile_ranks == {"1m": 0.95, "3m": 0.90}
    assert not hasattr(c, "risk_adr")          # refused vocabulary — stopw_adr stays
    assert c.stopw_adr > 0


def test_verdict_and_breakdown_are_typed_nullable():
    # Phase-2 fields typed now: verdict is null (P2), breakdown is the eight-row
    # rubric on a detected row (null only on non-detected rows, which P1 has none).
    [c] = build_candidates([_det("AAA")], _decile("AAA"), {}, {})
    assert c.verdict is None
    assert c.breakdown is not None and len(c.breakdown) == 8


def test_new_tonight_is_absence_from_the_previous_sessions_detections():
    # true exactly for names absent from last session's detected rows.
    rows = build_candidates(
        [_det("FRESH"), _det("HELD")],
        _decile("FRESH") + _decile("HELD"),
        {}, {},
        prev_detected={"HELD", "GONE"},
    )
    by_sym = {c.symbol: c for c in rows}
    assert by_sym["FRESH"].new_tonight is True   # not detected last session
    assert by_sym["HELD"].new_tonight is False   # carried over from last session


def test_dollar_volume_and_sector_degrade_to_none():
    # No bars supplied and no cached sector: both come back None rather than a
    # fabricated zero, mirroring the chart facts block.
    [c] = build_candidates([_det("AAA")], [], {}, {})
    assert c.dollar_volume is None
    assert c.sector is None
    assert c.decile_ranks == {}
    assert c.new_tonight is True  # empty prev set → every name is new
