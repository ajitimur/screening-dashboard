"""The one replay test seam (PRD #114 "Testing Decisions").

Modelled on ``test_store_seam.py``: seed a fixture store with *synthetic* bars,
hand the replay a handful of executed trades, and assert on the rows it emits —
never on how it got there. Later replay tickets (A1/A2/A3) extend this same
file; #115 lands the substrate it stands on:

- the replay store builder (US bars, the window, live store left read-only), and
- the reference-set parser + classifier + count report, whose one behavioural
  claim is that a trade whose ticker has no bars is a blind spot, not a failure.

Synthetic bars are authored, not copied from the live store, so the geometry
under test is chosen rather than discovered.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

from replay.funnel import (
    COND_BASE_LENGTH,
    COND_CLUSTER,
    COND_HISTORY,
    FUNNEL_STAGES,
    MARGINAL_TIGHT_MULT,
    STAGE_DECILE,
    STAGE_DETECTION,
    STAGE_LIQUIDITY,
    ClusterDecomposition,
    FunnelReport,
    characterise_cluster_misses,
    diagnose_detection,
    run_funnel,
)
from replay.reference import (
    DEFAULT_REFERENCE_JSON,
    REFERENCE_FIGURES,
    DriftError,
    ExecutedTrade,
    ReferenceReport,
    assert_matches_reference,
    build_report,
    classify,
    evaluation_session,
    load_trades,
    parse_trades,
    write_blind_spot_list,
)
from replay.chain import (
    BURN_IN_SESSIONS,
    REPLAY_REFERENCES,
    GapError,
    replay_chain,
    synthesize_instruments,
)
from replay.field import (
    SEVEN_DIM_LABEL,
    SEVEN_DIM_MAX_POINTS,
    FieldSession,
    ScoredDetection,
    SevenDimScore,
    build_field,
    build_field_sessions,
    replay_field,
    session_relative_moves,
    seven_dimension_score,
)
from replay.placement import (
    BOARD_SIZE,
    SCOPE,
    PlacementReport,
    StarDistribution,
    build_placement_report,
    place_trade,
    run_placement,
)
from replay.regression import (
    DimensionStat,
    OutcomeRegression,
    build_feature_vector,
    distribution,
    regress_dimensions,
    run_regression,
)
from replay.contrast import (
    CANDIDATE_DIMENSIONS,
    CONTRAST_DIMENSIONS,
    COMPARISON_GROUP_NOTE,
    PRECISION_NOTE,
    DimensionContrast,
    SelectionContrast,
    build_contrast,
    contrast_dimensions,
    format_report as format_contrast_report,
    run_contrast,
)
from replay.caching_store import CachingStore
from replay.store import WINDOW_END, WINDOW_START, build_replay_store
from screener.bars import Bar
from screener.detection import Detection, detect, detection_gate
from screener.indicators import anchor_date
from screener.ranks import Rank
from screener.relative_strength import relative_move_hit
from screener.source import MARKET_INDEX
from screener.store import Store


# -- helpers ---------------------------------------------------------------


def _bar(session: date, close: float = 10.0) -> Bar:
    return Bar(
        session=session,
        open=close,
        high=close,
        low=close,
        close=close,
        adj_close=close,
        volume=1_000_000,
    )


def _trade_record(ticker: str, entry: str, *, with_outcomes: bool = True) -> dict:
    """A synthetic reference-JSON row in the exact schema the reference tool emits.

    This mirrors ``references/trades_bo_gain10smaPct_desc.json`` field-for-field so
    every test built on it exercises the real parse path, not an invented one
    (#124): ``entryDate`` is a full ISO timestamp, the stop is ``stopPercentage``
    as a *fraction* of entry price (0.03, scaled to 3.0 percent on parse), and the
    realised-R keys are ``rr<exit>``. Entry 100 / stop 97 makes the fraction
    (100 - 97) / 100 = 0.03, so ``stop_pct`` parses to 3.0 percent.
    """
    rec = {
        "ticker": ticker,
        "entryDate": f"{entry}T00:00:00.000Z",
        "entryPrice": 100.0,
        "stopPrice": 97.0,
        "stopPercentage": 0.03,
    }
    if with_outcomes:
        rec.update(
            {
                "gain10smaPct": 25.0,
                "mfe10smaPct": 40.0,
                "rr10sma": 8.0,
                "gain20smaPct": 30.0,
                "mfe20smaPct": 45.0,
                "rr20sma": 10.0,
            }
        )
    return rec


def _make_funnel_row(
    *,
    ticker: str = "AAA",
    decile_present: bool = True,
    decile_pass: bool = False,
    decile_pass_five: bool = False,
    failed_condition=None,
    continuation: bool = False,
    range_3bar_adr=None,
    sessions_since_prior_entry=None,
):
    """A ``FunnelRow`` with just the decile / cluster fields set — the assertion
    surface for the decile-miss decomposition and the #132 cluster
    characterisation, everything else inert."""
    from replay.funnel import FunnelRow

    return FunnelRow(
        ticker=ticker,
        entry_date=date(2020, 6, 2),
        eval_session=date(2020, 6, 1),
        liquidity_pass=True,
        decile_present=decile_present,
        decile_pass=decile_pass,
        decile_pass_five=decile_pass_five,
        eval_percentiles={},
        decile_verdicts={},
        detection_pass=False,
        failed_condition=failed_condition,
        first_failing_stage=None,
        entry_session_break=False,
        continuation=continuation,
        median_dollar_volume=0.0,
        range_3bar_adr=range_3bar_adr,
        sessions_since_prior_entry=sessions_since_prior_entry,
    )


def _reference_payload(rows: list[dict]) -> dict:
    """Wrap fixture rows in the committed ``{"count", "trades"}`` envelope (#124).

    ``load_trades`` unwraps this envelope; a synthetic payload built through it
    exercises the same file shape as the committed reference set.
    """
    return {"count": len(rows), "trades": rows}


# -- the replay store builder ---------------------------------------------


def test_build_replay_store_copies_only_us_window_bars(tmp_path):
    """The replay store holds only US bars inside the window — an out-of-window
    US bar and an IDX bar are both left behind."""
    live_path = tmp_path / "live.duckdb"
    live = Store.open(live_path)
    live.append_bars("US", "AAA", [_bar(date(2020, 6, 1)), _bar(date(2021, 6, 1))])
    live.append_bars("US", "OLD", [_bar(date(2018, 1, 2))])  # before the window
    live.append_bars("US", "NEW", [_bar(date(2023, 6, 1))])  # after the window
    live.append_bars("IDX", "BBCA.JK", [_bar(date(2020, 6, 1))])  # wrong market
    live.close()

    replay_path = tmp_path / "replay.duckdb"
    stats = build_replay_store(live_path, replay_path)

    replay = Store.open(replay_path)
    try:
        assert replay.bars("US", "AAA") == [
            _bar(date(2020, 6, 1)),
            _bar(date(2021, 6, 1)),
        ]
        assert replay.bars("US", "OLD") == []
        assert replay.bars("US", "NEW") == []
        assert replay.bars("IDX", "BBCA.JK") == []
        # Only bars are populated — no run, no universe leaked across.
        assert replay.runs("US") == []
    finally:
        replay.close()

    assert stats.rows == 2
    assert stats.tickers == 1
    assert (WINDOW_START, WINDOW_END) == (date(2019, 4, 1), date(2022, 12, 31))


def test_build_replay_store_copies_a_non_default_market_and_window(tmp_path):
    """The builder's market and window are arguments, not the US 2019–2022 module
    constants they default to (#183). Pointed at IDX over a 2015 window it copies
    exactly IDX's in-window bars and leaves the default market and window behind —
    the same selectivity the US default has, driven by the passed values."""
    live_path = tmp_path / "live.duckdb"
    live = Store.open(live_path)
    live.append_bars("IDX", "BBCA.JK", [_bar(date(2015, 6, 1))])  # in the passed window
    live.append_bars("IDX", "OLD.JK", [_bar(date(2014, 1, 2))])  # before it
    live.append_bars("US", "AAA", [_bar(date(2015, 6, 1))])  # the default market
    live.close()

    replay_path = tmp_path / "replay.duckdb"
    stats = build_replay_store(
        live_path, replay_path,
        market="IDX", start=date(2015, 1, 1), end=date(2015, 12, 31),
    )

    replay = Store.open(replay_path)
    try:
        assert replay.bars("IDX", "BBCA.JK") == [_bar(date(2015, 6, 1))]
        assert replay.bars("IDX", "OLD.JK") == []
        assert replay.bars("US", "AAA") == []
    finally:
        replay.close()

    assert stats.rows == 1
    assert stats.tickers == 1


def test_build_replay_store_leaves_live_store_byte_identical(tmp_path):
    live_path = tmp_path / "live.duckdb"
    live = Store.open(live_path)
    live.append_bars("US", "AAA", [_bar(date(2020, 6, 1))])
    live.close()

    before = hashlib.sha256(live_path.read_bytes()).hexdigest()
    build_replay_store(live_path, tmp_path / "replay.duckdb")
    after = hashlib.sha256(live_path.read_bytes()).hexdigest()

    assert before == after


def test_build_replay_store_opens_live_read_only(tmp_path):
    """The live store is opened read-only: a build never even holds a writable
    handle to it, so it is structurally incapable of corrupting live history."""
    live_path = tmp_path / "live.duckdb"
    live = Store.open(live_path)
    live.append_bars("US", "AAA", [_bar(date(2020, 6, 1))])
    live.close()

    # Prove the file physically forbids the write build_replay_store must not do.
    ro = duckdb.connect(str(live_path), read_only=True)
    try:
        with pytest.raises(duckdb.Error):
            ro.execute("INSERT INTO bars VALUES ('US','X',DATE '2020-06-01',1,1,1,1,1,1)")
    finally:
        ro.close()


# -- the reference-set parser ---------------------------------------------


def test_parse_trades_reads_fields_and_both_exits():
    (trade,) = parse_trades([_trade_record("AAA", "2020-05-01")])

    assert isinstance(trade, ExecutedTrade)
    assert trade.ticker == "AAA"
    assert trade.entry_date == date(2020, 5, 1)
    assert trade.entry_price == 100.0
    assert trade.stop_price == 97.0
    assert trade.stop_pct == 3.0
    # Both simulated exits parsed, keyed by exit label.
    assert set(trade.outcomes) == {"10sma", "20sma"}
    assert trade.outcomes["10sma"].gain_pct == 25.0
    assert trade.outcomes["10sma"].mfe_pct == 40.0
    assert trade.outcomes["10sma"].r == 8.0
    assert trade.outcomes["20sma"].r == 10.0
    assert trade.has_outcomes


def test_load_trades_reads_the_committed_reference_file():
    """Parse the real committed reference set, not a synthetic row.

    The synthetic ``_trade_record`` above is written in the schema the parser
    reads; this test is the one that pins the schema the reference tool actually
    *emits* — the ``{"count", "trades"}`` envelope, ISO-timestamp ``entryDate``,
    ``stopPercentage`` and ``rr<exit>``. Without it the parser can drift away from
    the committed file while every other test stays green.
    """
    trades = load_trades(DEFAULT_REFERENCE_JSON)

    assert len(trades) == REFERENCE_FIGURES["total_rows"]
    assert sum(1 for t in trades if t.has_outcomes) == REFERENCE_FIGURES[
        "rows_with_outcomes"
    ]
    assert len({t.ticker for t in trades}) == REFERENCE_FIGURES["distinct_tickers"]
    # Every row carries a usable entry, stop and primary-exit R.
    assert all(t.entry_date.year in range(2019, 2023) for t in trades)
    assert all(t.stop_pct is not None for t in trades)
    assert sum(1 for t in trades if t.r is not None) == REFERENCE_FIGURES[
        "rows_with_outcomes"
    ]
    # MFE is the A3 regression target; it must survive the parse.
    assert all(t.primary.mfe_pct is not None for t in trades if t.has_outcomes)


def test_load_trades_reads_stop_width_in_percent_not_fraction():
    """The stop width is percent, matching what the feature vector divides by 100.

    The reference file stores ``stopPercentage`` as a *fraction* of the entry
    price. Reading it as a percent would understate every stop width by 100x and
    quietly gut the study's stop-width finding, so the unit is pinned against the
    stop distance recomputed from the row's own entry and stop prices.

    (Not pinned against ``riskPct``: that is position risk, a different quantity,
    and it is null on some rows.)
    """
    raw = json.loads(Path(DEFAULT_REFERENCE_JSON).read_text())["trades"]
    trades = load_trades(DEFAULT_REFERENCE_JSON)

    for record, trade in zip(raw, trades):
        entry, stop = record["entryPrice"], record["stopPrice"]
        expected = (entry - stop) / entry * 100.0
        assert trade.stop_pct == pytest.approx(expected, rel=1e-9)
        # A real stop is percent-scaled: single digits, not hundredths.
        assert 0.0 <= trade.stop_pct < 100.0

    # Exactly one row is degenerate — entry == stop, so a zero-width stop — and it
    # is the same row that carries no outcomes. Pinned so it stays a known,
    # single, inspectable exception rather than becoming a silent class of rows
    # that drags the stop-width distribution toward zero.
    degenerate = [t for t in trades if t.stop_pct == 0.0]
    assert len(degenerate) == 1
    assert not degenerate[0].has_outcomes


def test_parse_trades_counts_a_row_without_outcomes():
    trades = parse_trades(
        [
            _trade_record("AAA", "2020-05-01"),
            _trade_record("BBB", "2020-05-04", with_outcomes=False),
        ]
    )
    assert [t.has_outcomes for t in trades] == [True, False]
    # The outcome-less row still parses as a trade — it is a row, just outcome-less.
    assert trades[1].ticker == "BBB"
    assert trades[1].outcomes == {}


def test_synthetic_fixture_matches_committed_reference_schema():
    """The synthetic fixture must speak the committed file's schema (#124).

    Four schema mismatches (``stopPct`` for ``stopPercentage``, ``r<exit>`` for
    ``rr<exit>``, a plain-date ``entryDate`` for the ISO timestamp, and a bare
    list for the ``{"count", "trades"}`` envelope) once survived a fully green
    suite because the fixture invented its own schema and nothing exercised the
    real shape. This test pins the fixture to the committed shape so reintroducing
    any of the four fails here.
    """
    real_top = json.loads(Path(DEFAULT_REFERENCE_JSON).read_text())
    real_row = real_top["trades"][0]
    fixture = _trade_record("AAA", "2020-05-01")

    # The synthetic payload wraps rows in the same envelope the file uses — the
    # {"count", "trades"} shape, not a bare list.
    payload = _reference_payload([fixture])
    assert set(payload) == set(real_top)
    assert payload["count"] == 1
    assert payload["trades"] == [fixture]

    # Every fixture key is a real committed key — no invented schema, and in
    # particular the legacy names the parser only keeps for back-compat are gone.
    assert set(fixture) <= set(real_row)
    assert "stopPercentage" in fixture
    assert "stopPct" not in fixture
    assert "rr10sma" in fixture
    assert "r10sma" not in fixture
    assert "rr20sma" in fixture
    assert "r20sma" not in fixture

    # entryDate is a full ISO timestamp, matching the file, not a plain date.
    assert "T" in fixture["entryDate"]
    assert date.fromisoformat(fixture["entryDate"][:10]) == date(2020, 5, 1)

    # stopPercentage is a fraction of entry price, exactly as the file stores it —
    # single-digit percent read as a fraction, converted to percent on parse.
    assert fixture["stopPercentage"] < 1.0
    assert fixture["stopPercentage"] == pytest.approx(
        (fixture["entryPrice"] - fixture["stopPrice"]) / fixture["entryPrice"]
    )


def test_load_trades_unwraps_the_envelope_on_synthetic_rows(tmp_path):
    """A synthetic payload wrapped in the committed envelope parses through
    ``load_trades``, exercising the ``{"count", "trades"}`` shape and the
    fraction-to-percent stop scaling on the synthetic path too (#124)."""
    payload = _reference_payload(
        [_trade_record("AAA", "2020-05-01"), _trade_record("BBB", "2020-05-04")]
    )
    path = tmp_path / "synthetic_reference.json"
    path.write_text(json.dumps(payload))

    trades = load_trades(path)

    assert [t.ticker for t in trades] == ["AAA", "BBB"]
    assert [t.entry_date for t in trades] == [date(2020, 5, 1), date(2020, 5, 4)]
    # 0.03 fraction scaled to 3.0 percent, and rr<exit> read as realised R.
    assert all(t.stop_pct == 3.0 for t in trades)
    assert all(t.r == 8.0 for t in trades)


# -- classification: replayable vs blind spot -----------------------------


def test_trade_with_bars_is_replayable_without_bars_is_blind_spot(store: Store):
    store.append_bars("US", "AAA", [_bar(date(2020, 4, 30)), _bar(date(2020, 5, 1))])
    trades = parse_trades(
        [_trade_record("AAA", "2020-05-01"), _trade_record("ZZZ", "2020-05-01")]
    )

    classified = {c.trade.ticker: c.replayable for c in classify(trades, store)}

    assert classified == {"AAA": True, "ZZZ": False}


def test_replayable_asks_whether_bars_cover_the_evaluation_session(store: Store):
    """Replayability is "can this trade be evaluated?", not "does the store hold
    this symbol?" — a recycled symbol whose listing begins after the entry, and a
    name whose bars end before it, are both blind spots however many bars they
    carry under the ticker (#139)."""
    store.append_bars("US", "OLD", [_bar(d) for d in _daily(date(2020, 5, 4), 5)])
    store.append_bars("US", "RECY", [_bar(d) for d in _daily(date(2020, 6, 1), 5)])
    trades = parse_trades(
        [
            _trade_record("OLD", "2020-05-08"),   # bars span the eval session
            _trade_record("RECY", "2020-05-08"),  # listing begins a month later
            _trade_record("OLD", "2020-06-04"),   # bars ended before the entry
            _trade_record("ZZZ", "2020-05-08"),   # no bars at all
        ]
    )

    classified = [(c.trade.ticker, c.trade.entry_date, c.replayable)
                  for c in classify(trades, store)]

    assert classified == [
        ("OLD", date(2020, 5, 8), True),
        ("RECY", date(2020, 5, 8), False),
        ("OLD", date(2020, 6, 4), False),
        ("ZZZ", date(2020, 5, 8), False),
    ]


def test_trade_before_the_first_session_has_no_night_to_evaluate(store: Store):
    """No session precedes the entry, so there is no night the app could have
    named the stock on: a blind spot, not a stage failure (#139)."""
    store.append_bars("US", "AAA", [_bar(d) for d in _daily(date(2020, 5, 1), 3)])

    (classified,) = classify(parse_trades([_trade_record("AAA", "2020-05-01")]), store)

    assert classified.replayable is False


# -- the count report ------------------------------------------------------


def test_report_counts_and_blind_spot_r_share(store: Store):
    store.append_bars(
        "US", "AAA",
        [_bar(date(2020, 4, 30)), _bar(date(2020, 5, 1)), _bar(date(2020, 6, 1))],
    )
    store.append_bars("US", "BBB", [_bar(date(2020, 4, 30)), _bar(date(2020, 5, 4))])
    # AAA/BBB have bars (replayable); ZZZ does not (blind spot). One outcome-less row.
    trades = parse_trades(
        [
            _trade_record("AAA", "2020-05-01"),  # r 8
            _trade_record("BBB", "2020-05-04"),  # r 8
            _trade_record("ZZZ", "2020-05-01"),  # r 8, blind spot
            _trade_record("AAA", "2020-06-01", with_outcomes=False),
        ]
    )

    report = build_report(trades, store)

    assert isinstance(report, ReferenceReport)
    assert report.total_rows == 4
    assert report.rows_with_outcomes == 3
    assert report.distinct_tickers == 3
    assert report.blind_spot_tickers == 1
    assert report.blind_spot_trades == 1
    assert report.blind_spot_ticker_list == ["ZZZ"]
    # total R = 8+8+8 = 24 (the outcome-less row carries no R); blind spot = 8.
    assert report.blind_spot_r_share == pytest.approx(8.0 / 24.0)


def test_write_blind_spot_list_is_sorted_and_committed(tmp_path, store: Store):
    store.append_bars("US", "AAA", [_bar(date(2020, 4, 30)), _bar(date(2020, 5, 1))])
    trades = parse_trades(
        [
            _trade_record("ZZZ", "2020-05-01"),
            _trade_record("MMM", "2020-05-01"),
            _trade_record("AAA", "2020-05-01"),
        ]
    )
    report = build_report(trades, store)

    out = tmp_path / "blind_spot_tickers.json"
    write_blind_spot_list(report, out)

    assert json.loads(out.read_text()) == ["MMM", "ZZZ"]


# -- drift detection against the #114 figures ------------------------------


def test_drift_detection_fails_loudly_on_mismatch(store: Store):
    store.append_bars("US", "AAA", [_bar(date(2020, 4, 30)), _bar(date(2020, 5, 1))])
    report = build_report(parse_trades([_trade_record("AAA", "2020-05-01")]), store)

    # A three-row fixture cannot match the 828-row reference figures.
    assert report.total_rows != REFERENCE_FIGURES["total_rows"]
    with pytest.raises(DriftError):
        assert_matches_reference(report)


# -- A1 funnel: liquidity and detection (ticket #116) ----------------------
#
# Synthetic bars are authored so the geometry under test is chosen: a monotonic
# ramp never forms a base (fails detection at ``base_length``), and the textbook
# base is a run-up into a tight flat top (a clean detection). Liquidity rides on
# ``close × volume``; the fixtures below carry a $-volume well over the US floor
# so a detection failure is never masked by a liquidity failure.


def _bars_from_hlc(dates, hlc, *, volume: int = 1_000_000):
    """Bars over ``dates`` from ``(high, low, close)`` triples (adj = close)."""
    return [
        Bar(dates[i], close, high, low, close, close, volume)
        for i, (high, low, close) in enumerate(hlc)
    ]


def _daily(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def _ramp_hlc(n: int):
    """A monotonic rise: the highest high is always today, so the base is one bar
    long and detection fails at ``base_length`` — never a base."""
    out = []
    for i in range(n):
        c = 50.0 + 0.5 * i
        out.append((c + 0.5, c - 0.5, c))
    return out


def _textbook_base_hlc():
    """60 flat bars, a run-up 50->99, then a 30-bar tight top ending today — a
    clean detection (mirrors ``test_detection._base_series``)."""
    hlc = [(50.5, 49.5, 50.0)] * 60
    for i in range(1, 16):
        p = 50.0 + (99.0 - 50.0) * i / 15
        hlc.append((p + 0.5, p - 0.5, p))
    hlc += [(100.5, 99.5, 100.0)] * 30
    return hlc


def _wide_tail_hlc():
    """A run-up into a name still in motion: 60 flat bars, a tight run-up 100->110,
    12 tight bars at 110, then 3 *wide* bars (118/102) ending today. ADR is set by
    the tight 20-bar history, so the last-3-bar range reads far over the cluster's
    1.5x window — the geometry of a re-entry into a running name, which fails
    detection at ``cluster`` while clearing every earlier gate (history, adr,
    prior_move, base_length, catch_up)."""
    hlc = [(100.5, 99.5, 100.0)] * 60
    for i in range(1, 16):  # tight run-up 100 -> 110
        p = 100.0 + (110.0 - 100.0) * i / 15
        hlc.append((p + 0.5, p - 0.5, p))
    hlc += [(110.5, 109.5, 110.0)] * 12   # a tight shelf at 110 (sets a small ADR)
    hlc += [(118.0, 102.0, 110.0)] * 3    # wide bars: close pinned, range blown out
    return hlc


def _funnel_record(ticker: str, entry: date) -> dict:
    return _trade_record(ticker, entry.isoformat())


# -- the evaluation session, across weekends and holidays ------------------


def test_evaluation_session_is_last_session_strictly_before_entry():
    cal = [date(2020, 5, 13), date(2020, 5, 14), date(2020, 5, 15)]
    # An entry that itself falls on a session: the session *before* it, not it.
    assert evaluation_session(cal, date(2020, 5, 15)) == date(2020, 5, 14)
    # Nothing precedes the first session.
    assert evaluation_session(cal, date(2020, 5, 13)) is None


def test_funnel_evaluation_session_skips_a_market_holiday(store: Store):
    # Fri 05-15 is a session; Mon 05-18 is a holiday (no bar); Tue 05-19 trades.
    # An entry on Tue must evaluate at Fri, not at the non-existent Monday.
    sessions = [date(2020, 5, 14), date(2020, 5, 15), date(2020, 5, 19)]
    store.append_bars("US", "HOL", _bars_from_hlc(sessions, [(11, 9, 10)] * 3))

    report = run_funnel(parse_trades([_funnel_record("HOL", date(2020, 5, 19))]), store)

    (row,) = report.rows
    assert row.eval_session == date(2020, 5, 15)


# -- stage attribution: pass liquidity, fail detection, name the condition --


def test_funnel_row_passes_liquidity_fails_detection_and_names_condition(store: Store):
    dates = _daily(date(2020, 1, 1), 90)
    store.append_bars("US", "RAMP", _bars_from_hlc(dates, _ramp_hlc(90)))
    entry = dates[89] + timedelta(days=1)  # entry the day after the last bar

    # burn_in=0 so the eval session is a measured field session: RAMP is the sole
    # member, so it tops its own decile — the miss is at detection, not decile.
    report = run_funnel(parse_trades([_funnel_record("RAMP", entry)]), store, burn_in=0)

    (row,) = report.rows
    assert row.eval_session == dates[89]
    assert row.liquidity_pass is True          # $-volume well over the US floor
    assert row.decile_pass is True             # sole member -> tops its own decile
    assert row.detection_pass is False         # a ramp never forms a base
    assert row.failed_condition == COND_BASE_LENGTH
    assert row.first_failing_stage == STAGE_DETECTION
    # The stage recall records the miss, and it is attributed to the condition.
    assert report.detection.passed == 0
    assert report.condition_counts == {COND_BASE_LENGTH: 1}
    # A non-cluster miss carries no cluster-window margin (#132).
    assert row.range_3bar_adr is None


def test_funnel_cluster_miss_carries_its_window_margin(store: Store):
    """A re-entry into a running name fails detection at ``cluster`` and the row
    carries how far the trailing 3-bar range sat over the condition's 1.5x
    window — the margin the #132 characterisation reads (acceptance criterion 1)."""
    dates = _daily(date(2020, 1, 1), 90)
    store.append_bars("US", "RUN", _bars_from_hlc(dates, _wide_tail_hlc()))
    entry = dates[89] + timedelta(days=1)

    report = run_funnel(parse_trades([_funnel_record("RUN", entry)]), store, burn_in=0)

    (row,) = report.rows
    assert row.detection_pass is False
    assert row.failed_condition == COND_CLUSTER
    assert report.condition_counts == {COND_CLUSTER: 1}
    # The wide tail sits far over the cluster's 1.5x window — a name in motion, not
    # a base a modest widening reaches.
    assert row.range_3bar_adr is not None
    assert row.range_3bar_adr > MARGINAL_TIGHT_MULT


def test_funnel_row_carries_distance_to_the_prior_entry(store: Store):
    """Every replayable trade carries the market-session distance to its nearest
    prior entry (None on the first), the "how far from the prior entry" axis of the
    #132 characterisation and the basis of the continuation tag (PRD user story 5)."""
    dates = _daily(date(2020, 1, 1), 90)
    store.append_bars("US", "CONT", _bars_from_hlc(dates, [(101, 99, 100)] * 90))
    # First entry, then a re-entry three sessions later, then a fresh one 20 later.
    trades = parse_trades(
        [
            _funnel_record("CONT", dates[60]),
            _funnel_record("CONT", dates[63]),
            _funnel_record("CONT", dates[83]),
        ]
    )

    report = run_funnel(trades, store)

    by_entry = {r.entry_date: r for r in report.rows}
    assert by_entry[dates[60]].sessions_since_prior_entry is None   # first entry
    assert by_entry[dates[60]].continuation is False
    assert by_entry[dates[63]].sessions_since_prior_entry == 3      # within 5 -> add
    assert by_entry[dates[63]].continuation is True
    # 20 sessions from the nearest prior (dates[63]) -> a fresh entry, not a cont.
    assert by_entry[dates[83]].sessions_since_prior_entry == 20
    assert by_entry[dates[83]].continuation is False


def test_funnel_report_characterises_the_cluster_misses(store: Store):
    """The report characterises every ``cluster`` detection miss two ways (#132):
    continuation-vs-fresh (how far from a prior entry) and marginal-vs-far (how far
    over the condition's window), each bucket-pair partitioning the misses, with the
    3-bar-range and prior-distance distributions carried alongside."""

    def _miss(*, cont, rng, dist):
        return _make_funnel_row(
            failed_condition=COND_CLUSTER, continuation=cont,
            range_3bar_adr=rng, sessions_since_prior_entry=dist,
        )

    rows = [
        _make_funnel_row(failed_condition=COND_BASE_LENGTH),        # not a cluster miss
        _miss(cont=True, rng=1.7, dist=2),                          # continuation, marginal
        _miss(cont=True, rng=3.5, dist=4),                          # continuation, far
        _miss(cont=False, rng=1.8, dist=None),                      # fresh, marginal
        _miss(cont=False, rng=4.0, dist=None),                      # fresh, far
    ]

    c = characterise_cluster_misses(rows)

    assert isinstance(c, ClusterDecomposition)
    assert c.total_misses == 4                       # the base_length row is excluded
    assert c.continuation == 2 and c.fresh == 2
    assert c.marginal == 2 and c.far == 2            # <= 2.0x ADR vs beyond
    # Both bucket-pairs partition the misses exactly.
    assert c.continuation + c.fresh == c.total_misses
    assert c.marginal + c.far == c.total_misses
    # The range distribution spans every miss; the prior-distance distribution only
    # the continuation misses (2 and 4 sessions).
    assert c.range_distribution.n == 4
    assert c.prior_distance_distribution.n == 2
    assert c.prior_distance_distribution.median == 3.0
    # It rides the report the runner emits, computed over the report's own rows.
    assert cluster_characterisation_matches(store)


def cluster_characterisation_matches(store: Store) -> bool:
    """The funnel report carries the cluster characterisation of its own rows."""
    dates = _daily(date(2020, 1, 1), 90)
    store.append_bars("US", "RUN", _bars_from_hlc(dates, _wide_tail_hlc()))
    entry = dates[89] + timedelta(days=1)
    report = run_funnel(
        parse_trades([_funnel_record("RUN", entry)]), store, burn_in=0
    )
    return report.cluster_characterisation == characterise_cluster_misses(report.rows)


def test_funnel_clean_base_passes_both_stages(store: Store):
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
    entry = dates[104] + timedelta(days=1)

    # burn_in=0: the eval session is measured, so BASE clears all three stages.
    report = run_funnel(parse_trades([_funnel_record("BASE", entry)]), store, burn_in=0)

    (row,) = report.rows
    assert row.liquidity_pass is True
    assert row.decile_pass is True
    assert row.detection_pass is True
    assert row.failed_condition is None
    assert row.first_failing_stage is None
    # The break check is a separate secondary field: the base is present on the
    # entry session too, so it registers as a break there.
    assert row.entry_session_break is True
    assert report.liquidity.passed == report.detection.passed == 1


def test_diagnose_detection_matches_the_detector_verdict(store: Store):
    dates = _daily(date(2020, 1, 1), 105)
    ramp = _bars_from_hlc(_daily(date(2020, 1, 1), 90), _ramp_hlc(90))
    base = _bars_from_hlc(dates, _textbook_base_hlc())
    # A clean base names no failing condition; a ramp names base_length.
    assert diagnose_detection(base, dates[104]) is None
    assert diagnose_detection(ramp, _daily(date(2020, 1, 1), 90)[89]) == COND_BASE_LENGTH


# -- blind-spot trades get no funnel row -----------------------------------


def test_blind_spot_trade_gets_no_funnel_row(store: Store):
    dates = _daily(date(2020, 1, 1), 90)
    store.append_bars("US", "RAMP", _bars_from_hlc(dates, _ramp_hlc(90)))
    trades = parse_trades(
        [
            _funnel_record("RAMP", dates[89] + timedelta(days=1)),
            _funnel_record("ZZZ", date(2020, 3, 1)),  # no bars -> blind spot
        ]
    )

    report = run_funnel(trades, store)

    assert [r.ticker for r in report.rows] == ["RAMP"]  # ZZZ is not a stage failure


def test_recycled_symbol_is_a_blind_spot_not_a_history_stage_failure(store: Store):
    """A ticker whose bars begin after the entry it is paired with is a *different
    listing* under the same symbol. It must be recorded as a blind spot, never
    charged to the detector as a ``history`` miss (#139 — the live ``FUSE`` case)."""
    dates = _daily(date(2020, 1, 1), 90)
    store.append_bars("US", "RAMP", _bars_from_hlc(dates, _ramp_hlc(90)))
    later = _daily(dates[89] + timedelta(days=10), 90)
    store.append_bars("US", "RECY", _bars_from_hlc(later, _ramp_hlc(90)))
    trades = parse_trades(
        [
            _funnel_record("RAMP", dates[89] + timedelta(days=1)),
            _funnel_record("RECY", dates[50]),  # entry predates RECY's listing
        ]
    )

    report = run_funnel(trades, store)

    assert [r.ticker for r in report.rows] == ["RAMP"]
    assert COND_HISTORY not in report.condition_counts


# -- continuation entries stay in every denominator ------------------------


def test_continuation_entry_stays_in_all_denominators(store: Store):
    dates = _daily(date(2020, 1, 1), 90)
    store.append_bars("US", "CONT", _bars_from_hlc(dates, [(101, 99, 100)] * 90))
    # Two entries three sessions apart in the same ticker -> the second is an add.
    trades = parse_trades(
        [
            _funnel_record("CONT", dates[85]),
            _funnel_record("CONT", dates[88]),
        ]
    )

    report = run_funnel(trades, store)

    by_entry = {r.entry_date: r for r in report.rows}
    assert by_entry[dates[85]].continuation is False
    assert by_entry[dates[88]].continuation is True
    assert report.continuation_count == 1
    # The continuation entry stays in every stage's headline denominator...
    assert report.liquidity.total == 2
    assert report.detection.total == 2
    # ...and the ex-continuation figure — emitted alongside, never alone — drops it.
    assert report.liquidity.total_ex_continuation == 1
    assert report.detection.total_ex_continuation == 1


# -- the report names three stages in funnel order -------------------------


def test_funnel_report_names_three_stages_in_order(store: Store):
    dates = _daily(date(2020, 1, 1), 90)
    store.append_bars("US", "RAMP", _bars_from_hlc(dates, _ramp_hlc(90)))
    report = run_funnel(
        parse_trades([_funnel_record("RAMP", dates[89] + timedelta(days=1))]),
        store,
        burn_in=0,
    )

    assert isinstance(report, FunnelReport)
    assert report.stages == FUNNEL_STAGES == ("liquidity", "decile", "detection")
    # Per-stage recall is emitted separately for each of the three; no blended number.
    assert report.liquidity.stage == STAGE_LIQUIDITY
    assert report.decile.stage == STAGE_DECILE
    assert report.detection.stage == STAGE_DETECTION


# -- the decile stage, folded in off the forward chain's ranks (A1) --------


def _flat_hlc(n: int, price: float = 100.0):
    return [(price, price, price)] * n


def _rising_hlc(n: int, start: float = 50.0):
    """A monotonic climb: a strong prior move so the name tops its 1m decile."""
    return [(start + i, start + i, start + i) for i in range(n)]


def test_funnel_row_passes_liquidity_fails_decile(store: Store):
    """A ticker that is a field member (passes liquidity) but ranks outside the
    top decile of the detection lookbacks fails exactly the decile stage — the
    stage between liquidity and detection (PRD user story 8)."""
    dates = _daily(date(2020, 1, 1), 40)
    # LAG is flat (a dead 1m return); HI climbs hard (tops the 1m decile). Both
    # clear the $20M floor and 20-bar listing age, so both are field members.
    store.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(40)))
    store.append_bars("US", "HI", _bars_from_hlc(dates, _rising_hlc(40)))
    entry = dates[39] + timedelta(days=1)

    report = run_funnel(parse_trades([_funnel_record("LAG", entry)]), store, burn_in=0)

    (row,) = report.rows
    assert row.eval_session == dates[39]
    assert row.liquidity_pass is True     # a member: it cleared the floor
    assert row.decile_present is True      # present in the field
    assert row.decile_pass is False        # but ranked outside the top decile
    assert row.first_failing_stage == STAGE_DECILE
    # Per-stage recall is separate: liquidity kept it, the decile dropped it.
    assert report.liquidity.passed == 1
    assert report.decile.passed == 0


def test_funnel_distinguishes_absent_from_field_from_outside_decile(store: Store):
    """A ticker absent from the field at the eval session (not a member) is kept
    apart from one present but ranked outside the decile — a coverage gap versus a
    ranking verdict (PRD "A1 funnel")."""
    dates = _daily(date(2020, 1, 1), 40)
    store.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(40)))
    store.append_bars("US", "HI", _bars_from_hlc(dates, _rising_hlc(40)))
    # GHOST trades liquidly but only for 15 sessions — short of the 20-bar listing
    # age — so it is never a field member: absent, not ranked.
    store.append_bars("US", "GHOST", _bars_from_hlc(dates[25:], _flat_hlc(15)))
    entry = dates[39] + timedelta(days=1)

    report = run_funnel(
        parse_trades(
            [_funnel_record("LAG", entry), _funnel_record("GHOST", entry)]
        ),
        store,
        burn_in=0,
    )

    by_ticker = {r.ticker: r for r in report.rows}
    # LAG is in the field but below the decile.
    assert by_ticker["LAG"].decile_present is True
    assert by_ticker["LAG"].decile_pass is False
    # GHOST cleared the floor yet never entered the field: absent, distinguished.
    assert by_ticker["GHOST"].liquidity_pass is True
    assert by_ticker["GHOST"].decile_present is False
    assert by_ticker["GHOST"].decile_pass is False


def test_funnel_decile_output_carries_blind_spot_coverage(store: Store):
    """The decile depends on the replayed field's population, so the report carries
    a coverage number against the blind-spot tickers (PRD user story 22)."""
    dates = _daily(date(2020, 1, 1), 40)
    store.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(40)))
    entry = dates[39] + timedelta(days=1)

    report = run_funnel(
        parse_trades([_funnel_record("LAG", entry)]),
        store,
        burn_in=0,
        blind_spot_tickers=["ZZZ", "YYY", "XXX"],
    )

    assert report.blind_spot_count == 3


# -- #133: the funnel row carries the per-lookback decile detail ------------
#
# `FunnelRow` used to throw away the margin of a decile miss: the row knew only
# the flattened gate verdict, so whether he ranked 11th percentile or 40th,
# and which lookback he was strong in, were both discarded at the gate. #133 needs
# those, so the row now carries the per-lookback eval-session percentiles and the
# per-lookback top-decile verdicts, plus the five-union verdict — the second gate
# the detection gate is compared against. The verdicts still go through the app's own
# gate functions (`detection_gate`, `decile_gate`), never a second hand-rolled path.


def test_funnel_row_carries_per_lookback_percentiles_and_verdicts(store: Store):
    """A decile-present trade carries its eval-session percentile per lookback and a
    per-lookback top-decile verdict, so the margin of a miss is recoverable (#133).
    LAG is flat (dead in every lookback -> no verdict true); HI climbs hard (tops
    its short lookbacks)."""
    dates = _daily(date(2020, 1, 1), 40)
    store.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(40)))
    store.append_bars("US", "HI", _bars_from_hlc(dates, _rising_hlc(40)))
    entry = dates[39] + timedelta(days=1)

    report = run_funnel(
        parse_trades([_funnel_record("LAG", entry), _funnel_record("HI", entry)]),
        store,
        burn_in=0,
    )

    by_ticker = {r.ticker: r for r in report.rows}
    lag, hi = by_ticker["LAG"], by_ticker["HI"]

    # Percentiles are carried per lookback, keyed by the lookback name, as floats in
    # [0, 1]; a verdict is carried for exactly the lookbacks the name was ranked in.
    assert lag.eval_percentiles  # non-empty: LAG is a field member
    assert set(lag.decile_verdicts) == set(lag.eval_percentiles)
    assert all(0.0 <= p <= 1.0 for p in lag.eval_percentiles.values())
    # LAG is dead across every lookback -> no lookback is a top-decile verdict, and
    # it fails both the detection gate and the five-union gate.
    assert not any(lag.decile_verdicts.values())
    assert lag.decile_pass is False
    assert lag.decile_pass_five is False
    # A verdict is exactly the app's top-decile test on that lookback's percentile.
    for lb, pct in lag.eval_percentiles.items():
        assert lag.decile_verdicts[lb] == (pct >= 0.90)
    # HI tops at least one lookback -> a true verdict, and it clears the gate.
    assert any(hi.decile_verdicts.values())
    assert hi.decile_pass is True


def test_funnel_decile_verdicts_go_through_the_app_gate_functions(store: Store):
    """The row's gate verdict is the app's ``detection_gate`` and its five-union
    verdict is the app's ``decile_gate`` — never a second hand-rolled path (the trap
    #133 calls out). The five-union gate is a superset of the detection gate at any
    width, so a detection-gate pass implies a five-union pass."""
    dates = _daily(date(2020, 1, 1), 40)
    store.append_bars("US", "HI", _bars_from_hlc(dates, _rising_hlc(40)))
    store.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(40)))
    entry = dates[39] + timedelta(days=1)

    report = run_funnel(
        parse_trades([_funnel_record("HI", entry)]), store, burn_in=0
    )
    (row,) = report.rows
    # detection_gate ⊆ decile_gate: passing the narrower gate implies the wider one.
    assert row.decile_pass is True
    assert row.decile_pass_five is True


def test_funnel_report_decomposes_the_decile_miss(store: Store):
    """The report decomposes every replayable trade's decile miss into three
    mutually exclusive, exhaustive buckets — coverage gap (absent from the field),
    recovered-by-5 (fails the detection gate but clears the five-union one), and
    outside-any-union (fails even the five-union) — across all replayable trades
    (#133)."""
    from replay.funnel import DecileDecomposition, decompose_decile_misses

    def _row(ticker, *, present, pass3, pass5):
        return _make_funnel_row(
            ticker=ticker, decile_present=present, decile_pass=pass3,
            decile_pass_five=pass5,
        )

    rows = [
        _row("PASS", present=True, pass3=True, pass5=True),      # not a miss
        _row("GAP", present=False, pass3=False, pass5=False),    # coverage gap
        _row("REC", present=True, pass3=False, pass5=True),      # recovered by 5
        _row("OUT", present=True, pass3=False, pass5=False),     # outside any union
        _row("OUT2", present=True, pass3=False, pass5=False),    # outside any union
    ]

    decomp = decompose_decile_misses(rows)

    assert isinstance(decomp, DecileDecomposition)
    assert decomp.total_misses == 4               # every row but PASS
    assert decomp.coverage_gap == 1
    assert decomp.recovered_by_five == 1
    assert decomp.outside_any_union == 2
    # The three buckets partition the misses exactly.
    assert (
        decomp.coverage_gap + decomp.recovered_by_five + decomp.outside_any_union
        == decomp.total_misses
    )
    # It rides the report the runner emits, computed over the report's own rows.
    assert report_decomposition_matches(store)


def report_decomposition_matches(store: Store) -> bool:
    """The funnel report carries the decomposition of its own rows."""
    from replay.funnel import decompose_decile_misses

    dates = _daily(date(2020, 1, 1), 40)
    store.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(40)))
    store.append_bars("US", "HI", _bars_from_hlc(dates, _rising_hlc(40)))
    entry = dates[39] + timedelta(days=1)
    report = run_funnel(
        parse_trades([_funnel_record("LAG", entry)]), store, burn_in=0
    )
    return report.decile_decomposition == decompose_decile_misses(report.rows)


# -- the forward replay chain (A2): universe membership + ranks ------------


def _dv_bar(session: date, volume: int, close: float = 10.0) -> Bar:
    """A synthetic bar with an authored dollar volume (``close × volume``)."""
    return Bar(
        session=session,
        open=close,
        high=close,
        low=close,
        close=close,
        adj_close=close,
        volume=volume,
    )


def _calendar(n: int, start: date = date(2020, 1, 1)) -> list[date]:
    """``n`` consecutive calendar days — the observed replay calendar for a test.

    The app reads the calendar off the union of bar dates, never a holiday table,
    so consecutive days are a perfectly good synthetic exchange calendar."""
    from datetime import timedelta

    return [start + timedelta(days=k) for k in range(n)]


def _seed_series(store: Store, symbol: str, sessions: list[date], volumes: list[int]):
    store.append_bars(
        "US",
        symbol,
        [_dv_bar(s, v) for s, v in zip(sessions, volumes)],
    )


def test_membership_reflects_prior_session_through_stickiness(store: Store):
    """Path dependence made concrete: two names with identical *current* bars,
    one a member and one not, purely because one crossed the floor earlier and is
    held in the hysteresis band. Rebuilding a single session in isolation could
    not tell them apart — only the forward chain can."""
    sessions = _calendar(44)
    # STICKY clears 1.0× the $20M floor for 24 sessions (dv $30M), then drops into
    # the 0.8–1.0× hysteresis band (dv $18M) for the rest.
    _seed_series(store, "STICKY", sessions, [3_000_000] * 24 + [1_800_000] * 20)
    # FRESH sits in the band the whole time (dv $18M) — never crosses 1.0×.
    _seed_series(store, "FRESH", sessions, [1_800_000] * 44)

    # burn_in=0 so every session is a reported result; the chain still cold-starts
    # with empty prior membership on the first session by construction.
    fields = replay_chain(store, "US", burn_in=0)

    assert [f.session for f in fields] == sessions
    last = fields[-1]
    # Same trailing-20 dollar volume on the last session, opposite membership.
    assert "STICKY" in last.members
    assert "FRESH" not in last.members
    # Cold start: the first session has no member (no name has 20 bars yet).
    assert fields[0].members == []


def test_a_gapped_session_sequence_is_a_hard_error(store: Store):
    """Replaying only some sessions would make membership depend on which dates
    were picked, so a gap in the sequence is rejected rather than silently run."""
    sessions = _calendar(5)
    _seed_series(store, "AAA", sessions, [3_000_000] * 5)

    calendar = store.sessions("US")
    gapped = [calendar[0], calendar[1], calendar[3]]  # skips calendar[2]

    with pytest.raises(GapError):
        replay_chain(store, "US", sessions=gapped, burn_in=0)


def test_burn_in_sessions_are_computed_but_excluded_from_results(store: Store):
    """Burn-in sessions settle the hysteresis band before any measured session:
    they are computed and persisted, but never appear in the reported field."""
    sessions = _calendar(30)
    _seed_series(store, "AAA", sessions, [3_000_000] * 30)

    fields = replay_chain(store, "US", burn_in=25)

    # Only the sessions past the burn-in are reported.
    assert [f.session for f in fields] == sessions[25:]
    # But the burn-in sessions were still computed and persisted: a member on a
    # burn-in session is in the store even though it is absent from the results.
    burned = sessions[24]
    assert burned not in [f.session for f in fields]
    assert "AAA" in store.universe("US", burned)


def test_replay_chain_is_rerunnable_and_deterministic(store: Store):
    """A built store is not single-use: replaying the same chain a second time
    reuses the persisted sessions instead of re-appending them, so it neither
    raises the write-once :class:`SessionExistsError` nor changes the result
    (issue #126). The second run must return the same members and ranks as the
    first, session for session."""
    sessions = _calendar(30)
    _seed_series(store, "AAA", sessions, [3_000_000] * 30)
    _seed_series(store, "BBB", sessions, [1_800_000] * 30)

    first = replay_chain(store, "US", burn_in=5)
    # A second forward chain over the same store — the run that used to die on the
    # first already-persisted session — must run clean and reproduce the first.
    second = replay_chain(store, "US", burn_in=5)

    assert [f.session for f in second] == [f.session for f in first]
    assert [f.members for f in second] == [f.members for f in first]
    assert [f.ranks for f in second] == [f.ranks for f in first]


def test_replay_field_and_funnel_run_in_sequence_over_one_store(store: Store):
    """The two per-analysis entry points can be run in sequence against a single
    built store, in any order, without error — the acceptance criterion of #126.
    The chain the second analysis rides on is reused from what the first left
    behind, and the detections the field appends do not poison a later run."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
    trades = parse_trades([_funnel_record("BASE", dates[104])])

    # Field first (which appends detections), then the funnel over the same store,
    # then the field again — every run clean, and the field's result stable.
    (field_first,) = replay_field(store, "US", burn_in=104)
    funnel = run_funnel(trades, store, burn_in=104)
    (field_again,) = replay_field(store, "US", burn_in=104)

    assert [d.symbol for d in field_again.detections] == [
        d.symbol for d in field_first.detections
    ]
    assert funnel.detection.total == 1


def test_session_field_carries_coverage_against_blind_spots(store: Store):
    """Every field row carries a coverage number against the blind-spot tickers,
    so a ranking result is never read without knowing how much of the field was
    missing (PRD user story 22)."""
    sessions = _calendar(22)
    _seed_series(store, "AAA", sessions, [3_000_000] * 22)

    fields = replay_chain(
        store, "US", burn_in=0, blind_spot_tickers=["ZZZ", "YYY", "XXX"]
    )

    last = fields[-1]
    assert last.blind_spot_count == 3
    assert last.field_size == len(last.members) == 1


def test_synthesize_instruments_one_candidate_per_symbol_with_bars(store: Store):
    """Instruments are synthesised from the bars present, since the app's
    enumeration returns only today's listing snapshot (the survivorship hole)."""
    sessions = _calendar(3)
    _seed_series(store, "BBB", sessions, [1_000] * 3)
    _seed_series(store, "AAA", sessions, [1_000] * 3)

    instruments = synthesize_instruments(store, "US")

    assert [i.symbol for i in instruments] == ["AAA", "BBB"]
    assert all(i.role == "candidate" for i in instruments)
    assert all(i.market == "US" for i in instruments)


def test_synthesize_instruments_excludes_the_market_index(store: Store):
    """Issue #162: the index reaches the replay store as bars, without the role
    that would have held it out, so only its symbol can say it is a reference."""
    sessions = _calendar(3)
    _seed_series(store, "AAA", sessions, [1_000] * 3)
    _seed_series(store, "^IXIC", sessions, [1_000] * 3)

    instruments = synthesize_instruments(store, "US")

    assert [i.symbol for i in instruments] == ["AAA"]


def test_synthesize_instruments_excludes_the_benchmark_etfs(store: Store):
    """The index is not the only reference whose bars reached the replay store
    (#162). ``SPY``, ``QQQ``, ``IWM`` and ``DIA`` were fetched as study
    benchmarks, and an ETF carries no mark at all — no ``^``, no ``$``, a plain
    four-letter symbol indistinguishable from common stock. Only naming them
    keeps them out."""
    sessions = _calendar(3)
    for symbol in ["AAA", "SPY", "QQQ", "IWM", "DIA"]:
        _seed_series(store, symbol, sessions, [1_000] * 3)

    instruments = synthesize_instruments(store, "US")

    assert [i.symbol for i in instruments] == ["AAA"]


def test_the_replay_reference_set_names_every_reference_with_bars():
    """The set is a blocklist, which rots silently — so it is pinned here against
    what ``data/replay.duckdb`` actually holds, measured at the time of #162."""
    assert REPLAY_REFERENCES == {"^IXIC", "SPY", "QQQ", "IWM", "DIA"}


def test_the_reference_exclusion_is_the_replayed_markets_not_a_us_constant(store: Store):
    """The blocklist is a function of the market being replayed, not the US module
    constant applied to whatever runs (#183). ``QQQ`` is one of the US study
    benchmarks (:data:`REPLAY_REFERENCES`), but on IDX it is an ordinary common
    stock — striking it there is the US set leaking into another market's field.
    The IDX index still goes, on its ``^`` mark exactly as the US one does."""
    sessions = _calendar(22)
    for symbol in ["QQQ", "AAA.JK", MARKET_INDEX["IDX"]]:
        store.append_bars("IDX", symbol, [_dv_bar(s, 2_000_000, 1000.0) for s in sessions])

    instruments = synthesize_instruments(store, "IDX")

    assert [i.symbol for i in instruments] == ["AAA.JK", "QQQ"]
    assert all(i.market == "IDX" for i in instruments)


def test_replay_field_over_a_non_default_market_and_window(store: Store):
    """Acceptance #183, end to end: the same chain drives a non-default market
    over a non-default window. IDX bars in 2015 — neither the US default market
    nor the 2019–2022 default window — replay through universe, detection and the
    seven-dimension score, proving market and window are arguments rather than the
    constants they were."""
    dates = _daily(date(2015, 1, 1), 105)
    store.append_bars(
        "IDX", "BASE.JK",
        _bars_from_hlc(dates, _textbook_base_hlc(), volume=30_000_000),
    )

    # burn_in=104 measures only the last session, where the base ends.
    (field,) = replay_field(store, "IDX", burn_in=104)

    assert field.session == dates[104]
    assert field.session.year == 2015  # outside the US 2019–2022 default window
    assert "BASE.JK" in field.members
    assert [d.symbol for d in field.detections] == ["BASE.JK"]
    assert field.detections[0].score.label == SEVEN_DIM_LABEL
    assert field.detections[0].score.max_points == 8


def test_the_replayed_field_never_ranks_the_benchmark(store: Store):
    """The exclusion where it matters: through the whole chain, not just the
    instrument list. The index clears every liquidity and age gate the universe
    applies, so nothing downstream would have kept it out — left in, ``^IXIC``
    was ranked against the single names it is the benchmark *for*."""
    sessions = _calendar(22)
    _seed_series(store, "AAA", sessions, [3_000_000] * 22)
    _seed_series(store, "^IXIC", sessions, [3_000_000] * 22)

    fields = replay_chain(store, "US", burn_in=0)

    last = fields[-1]
    assert "^IXIC" not in last.members
    assert all(r.symbol != "^IXIC" for r in last.ranks)


def test_burn_in_default_matches_the_prd_window():
    assert BURN_IN_SESSIONS == 126


# -- the run-scoped bar-read cache (issue #125) ----------------------------
#
# Bars are immutable for the life of a replay; only the derived streams are
# written. Caching the reads at the store boundary is what turns a two-hour run
# into a half-hour one, and it must be semantics-preserving: a cached read is
# byte-identical to a fresh one, and no screening function changes.


def test_caching_store_serves_repeat_bar_reads_without_requerying(store: Store):
    """A second read of the same symbol comes from memory, not the store: proven
    by deleting the underlying rows between the two reads — a fresh query would
    now return nothing, but the cache still hands back the original bars."""
    seeded = [_bar(date(2020, 1, 1)), _bar(date(2020, 1, 2))]
    store.append_bars("US", "AAA", seeded)
    cache = CachingStore(store)

    first = cache.bars("US", "AAA")
    assert first == store.bars("US", "AAA")  # byte-identical to a fresh read

    # Delete the rows out from under the cache: a re-query would see nothing.
    store._con.execute("DELETE FROM bars")
    second = cache.bars("US", "AAA")

    assert second == first          # still the stored bars, not the empty table
    assert second is first          # the very same object — never re-queried


def test_caching_store_delegates_writes_and_reflects_them(store: Store):
    """Only ``bars`` is intercepted; a universe written through the cache lands in
    the shared store and is read straight back, so a cached store is a drop-in for
    the stages that both read bars and write derived rows."""
    cache = CachingStore(store)
    cache.append_universe("US", date(2020, 1, 2), ["AAA", "BBB"])

    assert cache.universe("US", date(2020, 1, 2)) == ["AAA", "BBB"]
    assert store.universe("US", date(2020, 1, 2)) == ["AAA", "BBB"]


def test_caching_store_evicts_a_symbol_on_a_bar_write(store: Store):
    """A bar write must not leave a stale cache: after appending to a cached
    symbol, the next read reflects the new bar."""
    store.append_bars("US", "AAA", [_bar(date(2020, 1, 1))])
    cache = CachingStore(store)
    assert len(cache.bars("US", "AAA")) == 1  # warms the cache

    cache.append_bars("US", "AAA", [_bar(date(2020, 1, 2))])

    assert len(cache.bars("US", "AAA")) == 2


def test_caching_store_wrap_does_not_nest_a_second_cache(store: Store):
    """``wrap`` keeps one run on a single shared cache: wrapping a cache returns
    it unchanged rather than building a cold one on top."""
    cache = CachingStore(store)
    assert CachingStore.wrap(cache) is cache
    assert isinstance(CachingStore.wrap(store), CachingStore)


def test_replay_chain_reads_each_symbols_bars_once_per_run(store: Store, monkeypatch):
    """The acceptance criterion made concrete: across a multi-session chain, each
    symbol's bars are fetched from the store exactly once, not once per session per
    stage. rebuild_universe and rebuild_ranks both read every member's history
    every session; without the run-scoped cache this symbol would be queried dozens
    of times."""
    sessions = _calendar(30)
    _seed_series(store, "AAA", sessions, [3_000_000] * 30)

    calls: dict[str, int] = {}
    real_bars = Store.bars

    def counting_bars(self, market, symbol):
        calls[symbol] = calls.get(symbol, 0) + 1
        return real_bars(self, market, symbol)

    monkeypatch.setattr(Store, "bars", counting_bars)
    fields = replay_chain(store, "US", burn_in=0)

    assert [f.session for f in fields] == sessions
    assert "AAA" in fields[-1].members  # the chain still produced the right field
    assert calls["AAA"] == 1            # ...reading its bars exactly once


# -- the replayed field (A2): detections + the seven-dimension score -------
#
# The field stands on the forward chain: universe -> ranks -> detections ->
# candidates -> a seven-of-eight-dimension star score. The sector dimension is
# dropped (its history is unrecoverable), so the score totals out of eight and is
# always labelled a seven-dimension score. The synthetic textbook base is the
# same authored geometry the funnel tests use, run here through the whole chain.


def _det(symbol: str, cluster_k: int) -> Detection:
    """A hand-authored detection whose signal vector fixes every score dimension
    but Tightness, which ``cluster_k`` flips — so two of these differ by exactly
    the ×2 tightness weight, a clear star-score gap to order on."""
    return Detection(
        symbol=symbol,
        session=date(2020, 1, 2),
        detector_version=1,
        trigger=100.0,
        stop=5.0,
        stopw_adr=0.5,
        base_len=10,          # <= 14 -> Base length hit
        move_gain=30.0,
        adr=0.06,             # >= 0.05 -> ADR hit
        close=95.0,
        cluster_k=cluster_k,  # >= 5 -> Tightness hit
        cluster_high=100.0,
        cluster_low=95.0,
        cluster_range_adr=0.5,
        range_3bar_adr=0.5,
        line_ok=True,
        touch_zones=2,
        overshoot_adr=0.0,
        slope=0.0,
        line_end=99.0,
        base_low=90.0,
        churn_l=0.4,          # in [0.30, 0.60] -> Orderliness hit
        sma20_rising=True,    # -> MA support hit
        dryup=0.9,            # <= 0.95 -> Volume hit
    )


def test_seven_dimension_score_omits_sector_and_totals_out_of_eight(store: Store):
    """The replayed score drops the sector dimension outright: seven rows, no
    sector, a ceiling of eight weighted points (PRD #138), and always the
    seven-dimension label so it can never be confused with the app's full score."""
    dates = _daily(date(2020, 1, 1), 105)
    bars = _bars_from_hlc(dates, _textbook_base_hlc())
    det = detect("BASE", bars, dates[104])
    assert det is not None

    score = seven_dimension_score(det, prior_move=True)

    dims = [d.dimension for d in score.breakdown]
    assert "Sector" not in dims
    assert len(score.breakdown) == 7
    # The app's published order, with the sector row struck out.
    assert dims == [
        "Tightness",
        "Orderliness",
        "Prior move",
        "Base length",
        "MA support",
        "Volume",
        "ADR",
    ]
    assert score.max_points == SEVEN_DIM_MAX_POINTS == 8
    assert 0 <= score.points <= 8
    assert score.stars == score.points / 2
    assert score.label == SEVEN_DIM_LABEL
    assert "seven-dimension" in score.label


def test_field_lists_symbols_in_star_order(store: Store):
    """A field row lists its symbols in star order — score descending. Two
    detections differing only by the ×2 tightness dimension: the tighter one
    outranks the looser one, and the order is the score's, not alphabetical."""
    looser = _det("AAA", cluster_k=3)   # Tightness miss -> lower score
    tighter = _det("BBB", cluster_k=6)  # Tightness hit  -> higher score

    field = build_field([looser, tighter], ranks=[])

    # BBB scores higher despite sorting after AAA alphabetically -> score-driven.
    assert [d.symbol for d in field] == ["BBB", "AAA"]
    assert [d.star_rank for d in field] == [1, 2]
    assert field[0].score.stars > field[1].score.stars
    # The tightness ×2 weight is exactly the gap.
    assert field[0].score.points - field[1].score.points == 2


def test_replay_field_detects_over_the_universe_with_a_seven_dim_score(store: Store):
    """The whole chain end to end: a member ranks top decile, the app's detector
    fires on its base, and the field carries it with a seven-dimension score."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))

    # burn_in=104 measures only the last session, where the base ends.
    (field,) = replay_field(store, "US", burn_in=104)

    assert field.session == dates[104]
    assert "BASE" in field.members
    assert [d.symbol for d in field.detections] == ["BASE"]
    scored = field.detections[0]
    assert scored.star_rank == 1
    assert scored.score.label == SEVEN_DIM_LABEL
    assert scored.score.max_points == 8


def test_not_taken_detection_marked_over_the_chain(store: Store):
    """Over the whole chain: he entered a trade elsewhere on the field session,
    so the field's member in another name is a not-taken detection (a
    comparison-group member, never a rejection)."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))

    elsewhere = parse_trades([_funnel_record("OTHER", dates[104])])
    (field,) = replay_field(store, "US", trades=elsewhere, burn_in=104)

    (scored,) = field.detections
    assert scored.symbol == "BASE"
    assert scored.not_taken is True
    assert field.not_taken == [scored]


def test_not_taken_flag_distinguishes_taken_from_untaken_and_quiet_sessions():
    """The not-taken predicate: a member is not-taken only on a session an entry
    was made and only in a name other than the one taken. On a session with no
    entry at all, nothing is a not-taken detection."""
    det = _det("BASE", cluster_k=6)

    # Entered elsewhere -> not-taken.
    (elsewhere,) = build_field([det], [], entered={"OTHER"}, any_entry=True)
    assert elsewhere.not_taken is True
    # The name he actually took -> taken, not not-taken.
    (taken,) = build_field([det], [], entered={"BASE"}, any_entry=True)
    assert taken.not_taken is False
    # A session with no entry at all -> not a comparison group.
    (quiet,) = build_field([det], [], any_entry=False)
    assert quiet.not_taken is False


def test_field_coverage_reflects_blind_spot_tickers_in_scope(store: Store):
    """Every field output carries a coverage number against the blind-spot
    tickers in its scope (PRD user story 22)."""
    sessions = _calendar(22)
    _seed_series(store, "AAA", sessions, [3_000_000] * 22)

    fields = replay_field(
        store, "US", burn_in=0, blind_spot_tickers=["ZZZ", "YYY"]
    )

    last = fields[-1]
    assert isinstance(last, FieldSession)
    assert last.blind_spot_count == 2
    assert "AAA" in last.members


# -- A2 reporting (issue #120): the top-thirty hit and the star distribution --
#
# Where the trade sat within that night's replayed field — deliberately only two
# statements per trade: whether it appeared at all, and whether it landed inside
# the top thirty by star score (the board size the trader reads). Per session:
# the star distribution of his picks against the field. No percentile is emitted.


def _scored(symbol: str, rank: int, stars: float) -> ScoredDetection:
    """A field candidate at a fixed star rank and score — the assertion surface."""
    score = SevenDimScore(
        stars=stars,
        points=int(stars * 2),
        max_points=SEVEN_DIM_MAX_POINTS,
        breakdown=[],
        label=SEVEN_DIM_LABEL,
    )
    return ScoredDetection(
        symbol=symbol,
        detection=_det(symbol, cluster_k=6),
        score=score,
        star_rank=rank,
        not_taken=False,
    )


def _field_of(session: date, symbols_in_star_order: list[str]) -> FieldSession:
    """A field of the given symbols in star order (rank 1 first), scores descending."""
    scored = [
        _scored(sym, rank=i + 1, stars=(len(symbols_in_star_order) - i) / 2)
        for i, sym in enumerate(symbols_in_star_order)
    ]
    return FieldSession(
        session=session,
        burn_in=False,
        members=list(symbols_in_star_order),
        detections=scored,
        blind_spot_count=0,
    )


def test_top_thirty_flag_matches_position_in_a_field_of_known_star_order():
    """A trade's top-thirty flag matches its position in a field of known star
    order: rank 30 is inside the board, rank 31 is outside it. The cut is the
    app's board size, not a separately chosen constant."""
    session = date(2020, 6, 1)
    field = _field_of(session, [f"S{i:02d}" for i in range(35)])  # 35 in star order

    inside = parse_trades([_funnel_record("S29", date(2020, 6, 2))])[0]   # rank 30
    outside = parse_trades([_funnel_record("S30", date(2020, 6, 2))])[0]  # rank 31

    assert BOARD_SIZE == 30
    inside_p = place_trade(inside, session, field)
    outside_p = place_trade(outside, session, field)

    assert inside_p.in_field is True and inside_p.top_thirty is True
    assert outside_p.in_field is True and outside_p.top_thirty is False


def test_absent_from_field_is_distinguished_from_present_but_outside_top_thirty():
    """A trade absent from the field is distinguished from one present but outside
    the top thirty: both fail the top-thirty flag, but only one appeared at all."""
    session = date(2020, 6, 1)
    field = _field_of(session, [f"S{i:02d}" for i in range(35)])

    present_outside = parse_trades([_funnel_record("S34", date(2020, 6, 2))])[0]
    absent = parse_trades([_funnel_record("GHOST", date(2020, 6, 2))])[0]

    present_p = place_trade(present_outside, session, field)
    absent_p = place_trade(absent, session, field)

    assert present_p.in_field is True and present_p.top_thirty is False
    assert absent_p.in_field is False and absent_p.top_thirty is False
    # No eval-session field at all: still recorded, still absent.
    none_p = place_trade(absent, session, None)
    assert none_p.in_field is False and none_p.top_thirty is False


def test_no_rank_position_or_percentile_is_emitted_on_a_placement():
    """No percentile or rank-position figure is emitted anywhere: a placement
    carries the two coarse statements and a star score, never a rank or percentile."""
    session = date(2020, 6, 1)
    field = _field_of(session, ["AAA", "BBB"])
    p = place_trade(parse_trades([_funnel_record("AAA", date(2020, 6, 2))])[0], session, field)

    names = {f.name for f in dataclasses.fields(p)}
    assert "star_rank" not in names
    assert not any("percentile" in n or "rank" in n for n in names)


def test_star_distribution_from_stars_buckets_by_score():
    """The star distribution buckets scores; the field's spread and his picks'
    spread are the prize — the shape, not a percentile."""
    dist = StarDistribution.from_stars([4.5, 4.5, 2.0, 0.0])
    assert dist.total == 4
    assert dist.counts[4.5] == 2
    assert dist.counts[2.0] == 1
    assert dist.counts[0.0] == 1


def test_run_placement_reports_hits_distribution_coverage_and_scope(store: Store):
    """End to end over the chain: his executed trade is placed in that night's
    field with a top-thirty hit, the picks distribution is reported against the
    field's on the same session, coverage rides the report, and the scope is US
    2019–2022 — never presented as an IDX expectation."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
    # An entry the day after the base ends -> eval session is dates[104], the one
    # measured session (burn_in=104), where the app's detector fires on BASE.
    trades = parse_trades([_funnel_record("BASE", dates[104] + timedelta(days=1))])

    report = run_placement(
        trades, store, burn_in=104, blind_spot_tickers=["ZZZ", "YYY"]
    )

    assert isinstance(report, PlacementReport)
    (placement,) = report.placements
    assert placement.ticker == "BASE"
    assert placement.eval_session == dates[104]
    assert placement.in_field is True
    assert placement.top_thirty is True          # lone member -> rank 1
    assert placement.stars is not None
    # The board size is the app's, not a separate constant.
    assert report.board_size == BOARD_SIZE == 30
    # His picks distribution against the field's on the same session.
    assert report.picks.total == 1
    assert report.field.total >= 1
    assert report.picks.counts[placement.stars] == 1
    # Coverage rides every output; scope is US 2019–2022, not IDX.
    assert report.blind_spot_count == 2
    assert "US" in report.scope and "2019" in report.scope
    assert "IDX" not in report.scope
    assert report.scope == SCOPE


def test_placement_scores_one_field_under_both_rubrics_stamped_by_version():
    """The paired A2 re-run (#136): one field, both rubrics, so a rubric change is
    held apart from a field change. Each star distribution carries its rubric
    version stamp; the live pair equals the report's headline picks/field; and with
    the field fixed, only the weights move — Base length ×0→×1 lifts his pick by
    exactly half a star under the old rubric."""
    from screener.score import RUBRICS, RUBRIC_VERSION, stars_under

    session = date(2020, 6, 1)
    det = _det("BASE", cluster_k=6)  # Base length, ADR, Orderliness all hit
    scored = ScoredDetection(
        symbol="BASE",
        detection=det,
        score=seven_dimension_score(det, prior_move=True),
        star_rank=1,
        not_taken=False,
    )
    field = FieldSession(
        session=session, burn_in=False, members=["BASE"],
        detections=[scored], blind_spot_count=0,
    )
    calendar = [session, date(2020, 6, 2)]
    trade = parse_trades([_funnel_record("BASE", date(2020, 6, 2))])[0]

    report = build_placement_report([trade], calendar, [field], blind_spot_count=0)

    # Both rubric versions are reported over the SAME field, each stamped.
    assert {r.rubric_version for r in report.by_rubric} == set(RUBRICS)
    live = next(r for r in report.by_rubric if r.rubric_version == RUBRIC_VERSION)
    old = next(r for r in report.by_rubric if r.rubric_version == 1)
    # The live-rubric pair *is* the report's headline picks/field — one source.
    assert live.picks.counts == report.picks.counts
    assert live.field.counts == report.field.counts
    # Field held fixed, only weights move: Base length ×0→×1 is +0.5 star under v1.
    live_star = stars_under(scored.score.breakdown, RUBRICS[RUBRIC_VERSION])
    v1_star = stars_under(scored.score.breakdown, RUBRICS[1])
    assert v1_star == live_star + 0.5
    assert live.picks.counts[live_star] == 1
    assert old.picks.counts[v1_star] == 1
    assert live.field.counts[live_star] == 1
    assert old.field.counts[v1_star] == 1


def test_blind_spot_trade_gets_no_placement_row(store: Store):
    """A blind-spot trade (ticker with no bars) is not placed — it is a blind
    spot, counted in coverage, never an absent-from-field verdict."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
    trades = parse_trades(
        [
            _funnel_record("BASE", dates[104] + timedelta(days=1)),
            _funnel_record("ZZZ", date(2020, 3, 1)),  # no bars -> blind spot
        ]
    )

    report = run_placement(trades, store, burn_in=104, blind_spot_tickers=["ZZZ"])

    assert [p.ticker for p in report.placements] == ["BASE"]


# -- A3 outcome regression: score dimensions against MFE (ticket #121) ------
#
# The feature vector is reconstructed at the evaluation session (the last session
# strictly before entry): the seven surviving score dimensions read off the app's
# detection, plus the trade's own stop width in ADR and the ADR at entry. Each
# dimension is regressed against MFE across executed trades; a dimension with no
# spread in the sample is untestable, not absent. The sector dimension is gone
# throughout, and realised R rides alongside as a descriptive statistic only.


def test_regression_feature_vector_matches_hand_computed_values(store: Store):
    """A feature vector is emitted per executed trade at the evaluation session,
    and its values match what the synthetic bars hand-compute: the seven detection
    dimensions, the ADR at entry, and the trade's own stop as a multiple of it."""
    dates = _daily(date(2020, 1, 1), 105)
    bars = _bars_from_hlc(dates, _textbook_base_hlc())
    store.append_bars("US", "BASE", bars)
    entry = dates[104] + timedelta(days=1)  # eval session is the last bar

    # burn_in=104 measures only the last session, where the base ends.
    report = run_regression(
        parse_trades([_funnel_record("BASE", entry)]), store, burn_in=104
    )

    (vec,) = report.feature_vectors
    assert vec.ticker == "BASE"
    assert vec.eval_session == dates[104]
    assert vec.detected is True
    # The seven dimensions match the app's own detection + seven-dim score, in
    # published order with the sector row struck.
    det = detect("BASE", bars, dates[104])
    assert vec.dimensions == seven_dimension_score(det, prior_move=True).breakdown
    assert [d.dimension for d in vec.dimensions] == [
        "Tightness", "Orderliness", "Prior move",
        "Base length", "MA support", "Volume", "ADR",
    ]
    # ADR at entry: the flat top's 100.5/99.5 bars give ADR = 100.5/99.5 - 1.
    expected_adr = 100.5 / 99.5 - 1.0
    assert vec.adr_at_entry == pytest.approx(expected_adr)
    # Stop width in ADR: his 3% stop as a multiple of that ADR.
    assert vec.stop_width_adr == pytest.approx((3.0 / 100.0) / expected_adr)
    # MFE (10sma) is the regression target; realised R rides alongside.
    assert vec.mfe == 40.0
    assert vec.r == 8.0


def test_regression_dimension_without_spread_is_untestable():
    """A dimension every trade shares — no spread — is labelled untestable, its
    correlation absent; a dimension that varies is testable and reports one. The
    sector dimension is absent throughout."""
    # Two detections identical but for tightness (cluster_k): Base length is hit
    # by both (no spread), Tightness by only one (spread).
    hi = build_feature_vector(
        ticker="AAA", entry_date=date(2020, 1, 3), eval_session=date(2020, 1, 2),
        det=_det("AAA", cluster_k=6), prior_move=True,
        adr_at_entry=0.06, stop_pct=3.0, mfe=40.0, r=8.0,
    )
    lo = build_feature_vector(
        ticker="BBB", entry_date=date(2020, 1, 3), eval_session=date(2020, 1, 2),
        det=_det("BBB", cluster_k=3), prior_move=True,
        adr_at_entry=0.06, stop_pct=3.0, mfe=10.0, r=2.0,
    )

    stats = {s.dimension: s for s in regress_dimensions([hi, lo])}

    assert "Sector" not in stats
    assert set(stats) == {
        "Tightness", "Orderliness", "Prior move",
        "Base length", "MA support", "Volume", "ADR",
    }
    # Base length: both hit, no variance -> untestable, no correlation.
    assert stats["Base length"].untestable is True
    assert stats["Base length"].correlation is None
    assert stats["Base length"].spread == 0.0
    # Tightness: one hit, one miss -> real spread, a correlation is reported.
    assert stats["Tightness"].untestable is False
    assert stats["Tightness"].spread > 0.0
    assert stats["Tightness"].correlation is not None
    # Prior move is untestable by construction (every detection cleared the gate).
    assert stats["Prior move"].untestable is True


def test_regression_reports_distributions_and_drops_sector(store: Store):
    """Realised R is reported as a descriptive statistic, and stop width in ADR
    and ADR at entry as distributions (the two #114 findings). The sector
    dimension is absent from the per-dimension stats, and coverage is carried."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
    entry = dates[104] + timedelta(days=1)

    report = run_regression(
        parse_trades([_funnel_record("BASE", entry)]),
        store,
        burn_in=104,
        blind_spot_tickers=["ZZZ", "YYY"],
    )

    assert isinstance(report, OutcomeRegression)
    assert "Sector" not in {s.dimension for s in report.dimension_stats}
    assert isinstance(report.dimension_stats[0], DimensionStat)
    # Realised R alongside, never the regression target.
    assert report.r_distribution is not None
    assert report.r_distribution.median == 8.0
    # The two preliminary #114 findings, reconstructed as distributions.
    expected_adr = 100.5 / 99.5 - 1.0
    assert report.adr_distribution.median == pytest.approx(expected_adr)
    assert report.stop_width_adr_distribution.median == pytest.approx(
        (3.0 / 100.0) / expected_adr
    )
    # Coverage rides on the field-derived output (PRD user story 22).
    assert report.blind_spot_count == 2


def test_distribution_percentiles_are_linear_interpolated():
    """The distribution helper's quartiles interpolate linearly (numpy default),
    so a hand-worked fixture value lands exactly."""
    dist = distribution([1.0, 2.0, 3.0, 4.0, 5.0])
    assert dist.minimum == 1.0
    assert dist.p25 == 2.0
    assert dist.median == 3.0
    assert dist.p75 == 4.0
    assert dist.maximum == 5.0
    assert dist.mean == 3.0
    assert dist.share_le(3.0) == pytest.approx(0.6)
    assert distribution([]) is None


# -- A3 selection contrast: executed trades vs not-taken detections (#122) ---
#
# The rubric's other question — which dimensions he *selects* on, as distinct from
# which *predict* a run. Dimension hit distributions are compared between his
# executed-trade detections (the taken members) and the not-taken detections (the
# field he passed over the same night). There is no outcome variable at all, and
# the not-taken detections are a comparison group, never a rejection. This partly
# repairs the outcome regression's range restriction: a dimension flat across his
# trades may vary once the not-taken detections restore the spread.


def _scored_det(
    symbol: str,
    cluster_k: int,
    *,
    taken=False,
    not_taken=False,
    rs_line=False,
    relative_move=None,
):
    """A field candidate carrying a real seven-dimension breakdown: ``cluster_k``
    flips the Tightness dimension, every other dimension is hit by construction.
    ``rs_line`` (#160) and ``relative_move`` (#170) are the candidate dimensions
    under measurement, which sit beside the score rather than inside it."""
    det = _det(symbol, cluster_k)
    return ScoredDetection(
        symbol=symbol,
        detection=det,
        score=seven_dimension_score(det, prior_move=True),
        star_rank=1,
        not_taken=not_taken,
        taken=taken,
        rs_line=rs_line,
        relative_move=relative_move,
    )


def _contrast_field(session: date, taken, not_taken, *, blind_spot_count=0):
    """A field session carrying the given taken and not-taken detections."""
    return FieldSession(
        session=session,
        burn_in=False,
        members=[d.symbol for d in taken + not_taken],
        detections=taken + not_taken,
        blind_spot_count=blind_spot_count,
    )


def test_selection_contrast_over_a_fixture_field_with_known_members():
    """The contrast compares dimension hit rates between his picks (taken) and the
    not-taken detections over a fixture field of known members. Tightness, which he
    selects on here, is hit by every pick and by only half the field he passed
    over; the sector dimension is absent, and coverage is carried.

    The columns are the rubric's seven **plus** the candidate dimensions under
    measurement (``RS line``, #160) — a candidate is reported so it can be judged
    against ADR 0005's ship criteria, and weighted at nothing so it cannot move a
    star while that judgement is open."""
    taken = [_scored_det("P1", 6, taken=True), _scored_det("P2", 6, taken=True)]
    not_taken = [
        _scored_det("N1", 3, not_taken=True),  # Tightness miss
        _scored_det("N2", 6, not_taken=True),  # Tightness hit
    ]
    field = _contrast_field(date(2020, 6, 1), taken, not_taken, blind_spot_count=4)

    report = build_contrast([field], blind_spot_count=4)

    assert isinstance(report, SelectionContrast)
    by_dim = {c.dimension: c for c in report.dimension_contrasts}
    assert "Sector" not in by_dim
    assert set(by_dim) == {
        "Tightness", "Orderliness", "Prior move",
        "Base length", "MA support", "Volume", "ADR",
        "RS line", "Relative move",
    }
    # The candidate carries no weight: it is measured, not scored (ADR 0005).
    assert by_dim["RS line"].weight == 0
    # He selects on Tightness: every pick hits it, half the passed-over field does.
    assert by_dim["Tightness"].taken_hit_rate == 1.0
    assert by_dim["Tightness"].not_taken_hit_rate == 0.5
    # Base length is hit by everyone (the detector requires it) -> no selection.
    assert by_dim["Base length"].taken_hit_rate == 1.0
    assert by_dim["Base length"].not_taken_hit_rate == 1.0
    assert report.n_executed == 2
    assert report.n_not_taken == 2
    assert report.blind_spot_count == 4


def test_selection_contrast_restores_testability_from_not_taken_detections():
    """A dimension flat across his trades alone (untestable in the outcome
    regression) but varying once the not-taken detections are added is flagged as
    testability-restored — the range-restriction repair. A dimension flat across
    both groups stays untestable and is not restored."""
    taken = [_scored_det("P1", 6, taken=True), _scored_det("P2", 6, taken=True)]
    not_taken = [
        _scored_det("N1", 3, not_taken=True),
        _scored_det("N2", 3, not_taken=True),
    ]

    by_dim = {c.dimension: c for c in contrast_dimensions(taken, not_taken)}

    # Tightness: all picks hit (no spread within his trades -> untestable there),
    # the not-taken detections miss it -> the pooled sample has spread -> restored.
    tight = by_dim["Tightness"]
    assert tight.untestable_within_executed is True
    assert tight.testable_in_contrast is True
    assert tight.testability_restored is True
    # Base length: hit by everyone in both groups -> no spread anywhere -> the
    # comparison group restores nothing.
    base = by_dim["Base length"]
    assert base.untestable_within_executed is True
    assert base.testable_in_contrast is False
    assert base.testability_restored is False


def test_selection_contrast_testable_within_executed_is_not_flagged_untestable():
    """A dimension that already varies within his trades alone is not labelled
    untestable within the executed set."""
    taken = [_scored_det("P1", 6, taken=True), _scored_det("P2", 3, taken=True)]
    by_dim = {c.dimension: c for c in contrast_dimensions(taken, [])}

    assert by_dim["Tightness"].untestable_within_executed is False
    assert by_dim["Tightness"].taken_spread > 0.0


def test_selection_contrast_carries_no_outcome_variable():
    """No outcome variable appears anywhere in the selection contrast — not on the
    report, not on a per-dimension row. This measures selection, not prediction."""
    contrast_names = {f.name for f in dataclasses.fields(SelectionContrast)}
    dim_names = {f.name for f in dataclasses.fields(DimensionContrast)}
    forbidden = ("mfe", "gain", "outcome", "correlation", "realis", "return", "_r_")
    for name in contrast_names | dim_names:
        assert not any(bad in name.lower() for bad in forbidden), name


def test_selection_contrast_describes_a_comparison_group_and_no_precision():
    """The output describes the not-taken detections as a comparison group, states
    precision is not measurable, claims no false-positive rate, and never labels
    the group rejected, declined or negative."""
    report = build_contrast(
        [_contrast_field(date(2020, 6, 1),
                         [_scored_det("P1", 6, taken=True)],
                         [_scored_det("N1", 3, not_taken=True)])],
        blind_spot_count=0,
    )
    assert report.comparison_group_note == COMPARISON_GROUP_NOTE
    assert report.precision_note == PRECISION_NOTE
    assert "comparison group" in report.comparison_group_note.lower()
    assert "precision is not measurable" in report.precision_note.lower()
    assert "false-positive" in report.precision_note.lower()

    text = format_contrast_report(report).lower()
    assert "comparison group" in text
    assert "precision is not measurable" in text
    for label in ("reject", "declined", "decline", "negative"):
        assert label not in text


def test_selection_contrast_and_outcome_regression_remain_separate():
    """The two A3 analyses stay apart: each runs over its own store through its own
    code path, returns a distinct result type, and neither report carries the
    other's table — no code path merges them into one figure. (Each runs the
    forward chain, which persists to its store write-once, so the two cannot share
    one store — a structural guarantee they are separate runs.)"""
    dates = _daily(date(2020, 1, 1), 105)
    trades = parse_trades([_funnel_record("BASE", dates[104] + timedelta(days=1))])

    reg_store = Store.memory()
    con_store = Store.memory()
    try:
        reg_store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
        con_store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
        regression = run_regression(trades, reg_store, burn_in=104)
        contrast = run_contrast(trades, con_store, burn_in=104)
    finally:
        reg_store.close()
        con_store.close()

    assert isinstance(regression, OutcomeRegression)
    assert isinstance(contrast, SelectionContrast)
    reg_fields = {f.name for f in dataclasses.fields(OutcomeRegression)}
    con_fields = {f.name for f in dataclasses.fields(SelectionContrast)}
    # The contrast's table is not on the regression, and vice versa.
    assert "dimension_contrasts" not in reg_fields
    assert "dimension_stats" not in con_fields
    assert "feature_vectors" not in con_fields
    assert "mfe_distribution" not in con_fields


def test_run_contrast_splits_his_pick_from_the_not_taken_field(store: Store):
    """End to end over the chain: on a night he entered one detected name, that
    name is his taken pick and the other detected member is a not-taken detection;
    coverage rides the report."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASEA", _bars_from_hlc(dates, _textbook_base_hlc()))
    store.append_bars("US", "BASEB", _bars_from_hlc(dates, _textbook_base_hlc()))
    # Entry on the one measured session (burn_in=104): BASEA taken, BASEB not-taken.
    trades = parse_trades([_funnel_record("BASEA", dates[104])])

    report = run_contrast(
        trades, store, burn_in=104, blind_spot_tickers=["ZZZ", "YYY"]
    )

    assert isinstance(report, SelectionContrast)
    assert report.n_executed == 1     # BASEA, the name he entered
    assert report.n_not_taken == 1    # BASEB, present but not entered
    assert report.blind_spot_count == 2


# -- the one-process study runner (#131) -----------------------------------
#
# One command that reproduces the whole study: it builds the field once and
# computes the A1 funnel, A2 placement and both A3 analyses against it, so four
# rebuilds of the 947-session chain become one. It emits both the human-readable
# reports and a machine-readable results file, and reports progress with an ETA so
# a silent hour-long run is distinguishable from a hung one.


def _study_store(store: Store):
    """A two-name synthetic store with one clean base and one lagging member."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
    store.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(105)))
    entry = dates[104] + timedelta(days=1)
    trades = parse_trades([_funnel_record("BASE", entry)])
    return trades, dates


def test_run_study_runs_all_four_analyses_against_one_built_field(store: Store):
    """The runner returns coverage plus all four analyses, and each matches the
    standalone entry point run over the same store — one field, four analyses."""
    from replay.study import StudyResult, run_study
    from replay.funnel import FunnelReport
    from replay.placement import PlacementReport
    from replay.regression import OutcomeRegression
    from replay.contrast import SelectionContrast

    trades, _ = _study_store(store)

    result = run_study(store, trades=trades, burn_in=104, blind_spot_tickers=["ZZZ"])

    assert isinstance(result, StudyResult)
    assert isinstance(result.funnel, FunnelReport)
    assert isinstance(result.placement, PlacementReport)
    assert isinstance(result.regression, OutcomeRegression)
    assert isinstance(result.contrast, SelectionContrast)
    # The shared field is correct for every analysis: the standalone runs (which
    # reuse the persisted chain) agree with the shared-field ones.
    funnel = run_funnel(trades, store, burn_in=104, blind_spot_tickers=["ZZZ"])
    placement = run_placement(trades, store, burn_in=104, blind_spot_tickers=["ZZZ"])
    regression = run_regression(trades, store, burn_in=104, blind_spot_tickers=["ZZZ"])
    contrast = run_contrast(trades, store, burn_in=104, blind_spot_tickers=["ZZZ"])
    assert result.funnel.detection.passed == funnel.detection.passed
    assert result.funnel.decile_decomposition == funnel.decile_decomposition
    assert result.placement.top_thirty_count == placement.top_thirty_count
    assert result.regression.n_detected == regression.n_detected
    assert result.contrast.n_executed == contrast.n_executed
    # Coverage is recomputed from the reference set (BASE is replayable -> no blind
    # spot there); the explicit blind-spot list rides onto the field coverage count.
    assert result.coverage.total_rows == 1
    assert result.funnel.blind_spot_count == 1
    assert result.placement.blind_spot_count == 1


def test_run_study_computes_the_chain_and_detection_pass_once(store: Store, monkeypatch):
    """The chain and the per-session detection pass are each computed once, not once
    per analysis: the forward chain is replayed a single time across all four."""
    import replay.study as study_mod

    trades, _ = _study_store(store)

    chain_calls = {"n": 0}
    real_chain = study_mod.replay_chain

    def counting_chain(*args, **kwargs):
        chain_calls["n"] += 1
        return real_chain(*args, **kwargs)

    monkeypatch.setattr(study_mod, "replay_chain", counting_chain)
    study_mod.run_study(store, trades=trades, burn_in=104)

    assert chain_calls["n"] == 1  # one forward pass, shared by all four analyses


def test_run_study_writes_human_and_machine_readable_outputs(tmp_path, store: Store):
    """The runner writes both a human-readable report and a machine-readable results
    file; the results file round-trips as JSON and carries the funnel rows with
    their per-lookback decile detail, so #133's decomposition survives the run and
    can be recomputed without another rebuild."""
    from replay.study import run_study, write_reports, write_results, load_results

    trades, _ = _study_store(store)
    result = run_study(store, trades=trades, burn_in=104, blind_spot_tickers=["ZZZ"])

    report_path = tmp_path / "study.txt"
    json_path = tmp_path / "study.json"
    write_reports(result, report_path)
    write_results(result, json_path)

    # Human-readable: names all four analyses.
    text = report_path.read_text()
    for token in ("funnel", "placement", "regression", "contrast"):
        assert token in text.lower()

    # Machine-readable: valid JSON, and the funnel rows survive with the #133 detail.
    raw = json.loads(json_path.read_text())
    funnel_rows = raw["funnel"]["rows"]
    assert funnel_rows
    row = funnel_rows[0]
    assert "eval_percentiles" in row
    assert "decile_verdicts" in row
    assert "decile_pass_five" in row
    assert raw["funnel"]["decile_decomposition"]["total_misses"] >= 0

    # And it reloads into a decomposition recomputable without a rebuild.
    reloaded = load_results(json_path)
    assert reloaded["funnel"]["decile_decomposition"] == raw["funnel"]["decile_decomposition"]

    # The A2 placement carries the paired star distributions, each stamped with its
    # rubric version (#136), so a re-run separates a rubric change from a field
    # change and no star figure is quoted without its stamp (#138).
    from screener.score import RUBRIC_VERSION

    from screener.score import RUBRICS

    by_rubric = raw["placement"]["by_rubric"]
    stamps = {r["rubric_version"] for r in by_rubric}
    assert stamps == set(RUBRICS)
    for r in by_rubric:
        assert "picks" in r and "field" in r and "total" in r["picks"]
        # The board figure is paired too — a rubric reorders the field around a
        # pick, so top-thirty moves independently of the histogram (#136).
        assert "top_thirty" in r
    live = next(r for r in by_rubric if r["rubric_version"] == RUBRIC_VERSION)
    assert live["picks"] == raw["placement"]["picks"]
    assert live["top_thirty"] == raw["placement"]["top_thirty_count"]


def test_run_study_reports_progress_with_a_running_count(store: Store):
    """Progress is reported while running: the runner calls back per session for the
    chain and the detection pass, with a monotonically rising count against a fixed
    total, so a long run never goes silent."""
    from replay.study import run_study

    trades, _ = _study_store(store)
    events: list[tuple[str, int, int]] = []

    run_study(
        store,
        trades=trades,
        burn_in=100,
        progress=lambda phase, i, total, session: events.append((phase, i, total)),
    )

    phases = {e[0] for e in events}
    assert "chain" in phases and "field" in phases
    # Counts rise from 1 and never exceed the total, per phase.
    for phase in phases:
        counts = [i for p, i, _ in events if p == phase]
        totals = {t for p, _, t in events if p == phase}
        assert counts == sorted(counts)
        assert counts[0] >= 1
        assert len(totals) == 1
        assert max(counts) <= next(iter(totals))


def test_study_cli_writes_outputs_and_prints_summary(tmp_path, store: Store, capsys):
    """The documented single command runs coverage plus all four analyses against
    one built store and writes both outputs."""
    from replay import study as study_mod

    trades, _ = _study_store(store)
    store_path = tmp_path / "replay.duckdb"
    disk = Store.open(store_path)
    try:
        dates = _daily(date(2020, 1, 1), 105)
        disk.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
        disk.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(105)))
    finally:
        disk.close()

    ref_path = tmp_path / "ref.json"
    ref_path.write_text(json.dumps(_reference_payload(
        [_funnel_record("BASE", dates[104] + timedelta(days=1))]
    )))
    report_path = tmp_path / "out.txt"
    json_path = tmp_path / "out.json"

    rc = study_mod.main([
        "--store", str(store_path),
        "--reference", str(ref_path),
        "--burn-in", "104",
        "--no-drift-check",
        "--out-report", str(report_path),
        "--out-json", str(json_path),
    ])

    assert rc == 0
    assert report_path.exists()
    assert json.loads(json_path.read_text())["funnel"]["rows"]


def test_placement_pairs_the_top_thirty_hit_per_rubric_not_only_the_histogram():
    """#136 asks for the top-thirty figure *and* the star distribution paired, and
    a board place is a re-ranking, not a re-scoring: the same detection can sit
    inside the board under one rubric and outside it under the other, because the
    weights reorder the whole field around it.

    So ``by_rubric`` carries ``top_thirty`` alongside the two histograms. Here the
    field is thirty-one names on one session: thirty that hit Base length (×1 under
    v1, ×0 under v2) and his pick, which does not. Under v1 the thirty outscore him
    and he is pushed to rank 31 — off the board; under v2 the dimension is worth
    nothing, the field collapses level with him, and the symbol-ordered tie-break
    puts him first. One field, one set of hits, two board verdicts."""
    from screener.score import RUBRIC_VERSION

    session = date(2020, 6, 1)
    # His pick misses Base length (base_len > 14); the thirty others hit it. Every
    # other dimension is identical, so v1's ×1 on Base length is the only gap.
    pick = _det("AAA", cluster_k=6)
    pick = dataclasses.replace(pick, base_len=40)
    others = [_det(f"Z{i:02d}", cluster_k=6) for i in range(BOARD_SIZE)]

    def _scored(det: Detection, rank: int) -> ScoredDetection:
        return ScoredDetection(
            symbol=det.symbol,
            detection=det,
            score=seven_dimension_score(det, prior_move=True),
            star_rank=rank,
            not_taken=False,
        )

    # Star order under the live rubric (v2): Base length is worth nothing, so all
    # thirty-one tie and the field falls back to the symbol tie-break — AAA first.
    detections = [_scored(pick, 1)] + [
        _scored(det, i) for i, det in enumerate(others, start=2)
    ]
    field = FieldSession(
        session=session, burn_in=False,
        members=[d.symbol for d in detections],
        detections=detections, blind_spot_count=0,
    )
    calendar = [session, date(2020, 6, 2)]
    trade = parse_trades([_funnel_record("AAA", date(2020, 6, 2))])[0]

    report = build_placement_report([trade], calendar, [field], blind_spot_count=0)

    live = next(r for r in report.by_rubric if r.rubric_version == RUBRIC_VERSION)
    old = next(r for r in report.by_rubric if r.rubric_version == 1)
    # The live entry is the report's headline top-thirty count by identity — the
    # detections were ranked under the live rubric, so nothing is ranked twice.
    assert live.top_thirty == report.top_thirty_count == 1
    # Under the old rubric the same pick, in the same field, is off the board.
    assert old.top_thirty == 0


# -- the replayed field outlives the rank table's retention window ----------


def test_field_detects_on_a_session_whose_stored_ranks_were_pruned(store: Store):
    """A measured session older than the rank table's retention window still
    produces its detections.

    ``Store.append_ranks`` keeps only ``RANK_RETENTION_YEARS`` and prunes as the
    chain advances, and the whole chain is built before the detection pass runs —
    so an early session's rank rows are gone by the time detection reaches it.
    Gating on the store there returns an empty rank table, every member falls out
    of the decile gate, and the session contributes nothing to the field while
    looking exactly like a night that legitimately found no setup. The chain
    carries the ranks it computed; those are what the gate reads.
    """
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _textbook_base_hlc()))
    chain = replay_chain(store, "US", burn_in=104)
    (sf,) = chain
    assert sf.ranks, "the chain computed this session's ranks"

    # Retention having pruned this session's rows is indistinguishable, at the
    # detection stage, from their never having been written.
    store._cursor().execute("DELETE FROM ranks WHERE market = 'US'")
    assert store.ranks("US", dates[104]) == []

    (field,) = build_field_sessions(store, "US", chain)

    assert [d.symbol for d in field.detections] == ["BASE"]

# -- #149: pricing the detection gate's width --------------------------------
#
# ADR 0003 leaves `DETECTION_LOOKBACKS = ("1m", "3m", "6m")` -> the five-lookback
# set as its leading candidate and explicitly does not authorise the edit. The
# widening re-admits the two lookbacks `detection_gate` excludes on purpose — `1w`
# (a momentum burst) and `12m` (stale) — so what decides it is not the headline 75
# but *which* lookback admits each of them. These tests pin the decomposition, the
# volume price, and the two properties that keep the measurement honest: every gate
# goes through the app's own `detection_gate`, and the live constant is never
# mutated to measure an alternative to it.


def _with_outcome(record: dict, *, r: float, mfe: float) -> dict:
    """``record`` with its primary exit's R and MFE set — the two figures the
    outcome-quality group averages."""
    return {**record, "rr10sma": r, "mfe10smaPct": mfe}


def _funnel_row(
    ticker: str,
    *,
    session: date,
    present: bool = True,
    pass3: bool = False,
    pass5: bool = True,
    detection: bool = True,
    continuation: bool = False,
    entry: date | None = None,
):
    from replay.funnel import FunnelRow

    return FunnelRow(
        ticker=ticker,
        entry_date=entry or (session + timedelta(days=1)),
        eval_session=session,
        liquidity_pass=True,
        decile_present=present,
        decile_pass=pass3,
        decile_pass_five=pass5,
        eval_percentiles={},
        decile_verdicts={},
        detection_pass=detection,
        failed_condition=None,
        first_failing_stage=None if pass3 and detection else STAGE_DECILE,
        entry_session_break=False,
        continuation=continuation,
        median_dollar_volume=50_000_000.0,
        range_3bar_adr=None,
        sessions_since_prior_entry=None,
    )


def test_a_variants_gate_is_the_apps_gate_under_that_width():
    """A variant's gate is the union of its lookbacks' top deciles, and that union
    is *exactly* what the app's own `detection_gate` returns for the same width —
    asserted rather than assumed, so the sweep can never drift into a second
    definition of "top decile" (#149)."""
    from replay.gate_sweep import GATE_VARIANTS, gate_membership, variant_gate

    rows = [
        Rank("BURST", "1w", percentile=0.99, raw_return=0.5),
        Rank("STALE", "12m", percentile=0.97, raw_return=2.0),
        Rank("NOW", "3m", percentile=0.95, raw_return=0.8),
        Rank("MID", "6m", percentile=0.40, raw_return=0.1),
    ]
    membership = gate_membership(rows)

    for variant in GATE_VARIANTS:
        assert variant_gate(membership, variant) == detection_gate(
            rows, lookbacks=variant.lookbacks
        )
    # …and the widths are what they claim: the live one admits neither excluded name.
    assert variant_gate(membership, GATE_VARIANTS[0]) == {"NOW"}
    assert variant_gate(membership, GATE_VARIANTS[-1]) == {"NOW", "BURST", "STALE"}


def test_recovered_misses_are_split_by_which_lookback_admits_them():
    """The ticket's headline: the trades a 3->5 widening recovers, decomposed into
    `12m`-only (the stale qualifier the §4.5 exclusion exists to prevent), `1w`-only
    (the momentum burst), both, and also-admitted-by-a-gated-lookback (#149)."""
    from replay.gate_sweep import decompose_recovered

    session = date(2021, 3, 1)
    rows = [
        _funnel_row("STALE", session=session),
        _funnel_row("STALE2", session=session, continuation=True),
        _funnel_row("BURST", session=session),
        _funnel_row("BOTH", session=session),
        # Not recovered: already clears the live gate, so not a miss at all.
        _funnel_row("PASSER", session=session, pass3=True),
        # Not recovered: absent from the field (a coverage gap), and outside every union.
        _funnel_row("GONE", session=session, present=False, pass5=False),
        _funnel_row("MISS", session=session, pass5=False),
    ]
    membership = {
        session: {
            "1m": set(), "3m": set(), "6m": {"PASSER"},
            "1w": {"BURST", "BOTH"},
            "12m": {"STALE", "STALE2", "BOTH"},
        }
    }

    comp = decompose_recovered(rows, membership)

    assert comp.total == 4
    assert comp.stale_only == 2
    assert comp.burst_only == 1
    assert comp.both_excluded == 1
    assert comp.also_gated == 0
    assert comp.continuation == 1
    # The four buckets partition the recovered trades, and none of them is reached
    # through a lookback the gate already unions.
    assert (
        comp.stale_only + comp.burst_only + comp.both_excluded + comp.also_gated
        == comp.total
    )
    assert comp.excluded_only == comp.total


def test_a_trade_the_gate_already_admits_is_not_a_recovered_trade():
    """`also_existing` is zero *by construction*: a name top-decile in a lookback the
    gate already unions clears the gate, so it was never a miss for a widening to
    recover. The bucket is carried and reported anyway, so "every recovered trade
    arrives through an excluded lookback" is visible in the output rather than
    assumed by the reader (#149)."""
    from replay.gate_sweep import decompose_recovered, recovered_rows

    session = date(2021, 3, 1)
    rows = [_funnel_row("ODD", session=session)]
    membership = {session: {"3m": {"ODD"}, "12m": {"ODD"}}}

    assert recovered_rows(rows, membership) == []
    comp = decompose_recovered(rows, membership)
    assert comp.total == 0
    assert comp.also_gated == 0


def test_outcome_quality_reports_the_recovered_groups_realised_r():
    """A recall gain is reported against the *quality* of what it recovers: mean and
    median R and the win rate, over the trades behind the rows. A row whose trade
    carries no outcome stays in ``n`` and out of the averages, so the group is never
    quietly shrunk to the rows that happen to have a result (#149)."""
    from replay.gate_sweep import outcome_quality

    session = date(2021, 3, 1)
    rows = [
        _funnel_row("WIN", session=session, entry=date(2021, 3, 2)),
        _funnel_row("LOSS", session=session, entry=date(2021, 3, 2)),
        _funnel_row("NOOUT", session=session, entry=date(2021, 3, 2)),
    ]
    trades = {
        (t.ticker, t.entry_date): t
        for t in parse_trades(
            [
                _with_outcome(_trade_record("WIN", "2021-03-02"), r=4.0, mfe=30.0),
                _with_outcome(_trade_record("LOSS", "2021-03-02"), r=-1.0, mfe=2.0),
            ]
        )
    }

    quality = outcome_quality("recovered", rows, trades)

    assert quality.n == 3          # every row in the group
    assert quality.n_with_r == 2   # only the two carrying an outcome
    assert quality.mean_r == 1.5
    assert quality.median_r == 1.5
    assert quality.win_rate == 0.5
    assert quality.mean_mfe == 16.0
    # R is fat-tailed, so the mean is carried beside figures that survive one
    # outlier: the top 5% (here, one of two) is trimmed off before re-meaning, the
    # 3R tail is counted, and the best trade's share of the group's R is stated.
    assert quality.trimmed_mean_r == -1.0
    assert quality.big_win_rate == 0.5
    assert quality.top_trade_r_share == pytest.approx(4.0 / 3.0)


def _sweep_session(session: date, ranks: list[Rank], symbols: list[str]):
    """One prepared sweep session: a hand-authored rank table and one detection per
    name in ``symbols``, all identical so star order falls back to the ticker."""
    from replay.gate_sweep import SweepSession, gate_membership

    return SweepSession(
        session=session,
        members=sorted({r.symbol for r in ranks}),
        ranks=ranks,
        membership=gate_membership(ranks),
        detections=[
            dataclasses.replace(_det(symbol, cluster_k=5), session=session)
            for symbol in symbols
        ],
    )


def _widening_pass():
    """Two sessions where each excluded lookback admits exactly one extra name:
    NOW clears the live gate, STALE is top-decile only in 12m, BURST only in 1w,
    and DEAD is top-decile nowhere. All but DEAD sit in a base."""
    sessions = [date(2021, 3, 1), date(2021, 3, 2)]
    out = []
    for session in sessions:
        ranks = [
            Rank("NOW", "3m", percentile=0.95, raw_return=0.8),
            Rank("STALE", "12m", percentile=0.97, raw_return=2.0),
            Rank("BURST", "1w", percentile=0.99, raw_return=0.5),
            Rank("DEAD", "3m", percentile=0.10, raw_return=0.0),
        ]
        out.append(_sweep_session(session, ranks, ["NOW", "STALE", "BURST"]))
    return out


def test_the_widened_gate_is_priced_in_added_detections_per_recovered_entry():
    """#141's basis, mirrored for the decile gate: the widening's price is the extra
    field volume it emits per real entry it recovers. Precision is unmeasurable, so
    this is a *volume* ratio and never a false-positive rate (#149)."""
    from replay.gate_sweep import GATE_VARIANTS, sweep_gates

    swept = _widening_pass()
    rows = [
        _funnel_row("NOW", session=swept[0].session, pass3=True),
        _funnel_row("STALE", session=swept[0].session),
    ]

    sweep = sweep_gates(swept, rows, {}, board_size=2)

    base, five = sweep.variants[0], sweep.variants[-1]
    # The live gate admits one name a session; the five-lookback union admits three.
    assert base.field_detections == 2
    assert five.field_detections == 6
    # It recovers exactly the one trade admitted by 12m…
    assert base.decile_recall.passed == 1
    assert five.decile_recall.passed == 2
    # …so the price is four extra detections for one recovered entry.
    inflation = sweep.inflation[five.variant.name]
    assert inflation.added_detections == 4
    assert inflation.recovered_entries == 1
    assert inflation.per_recovered_entry == 4.0
    # The narrower widenings are priced separately, each on its own evidence.
    assert {v.variant.name for v in sweep.variants} == {
        v.name for v in GATE_VARIANTS
    }
    assert sweep.inflation["+12m (stale)"].recovered_entries == 1
    assert sweep.inflation["+1w (burst)"].recovered_entries == 0


def test_the_widened_gate_displaces_names_from_the_board():
    """Board displacement: with a two-name board, the names a wider gate admits take
    places the live gate's names held. Counted over every measured session (#149)."""
    from replay.gate_sweep import sweep_gates

    swept = _widening_pass()
    sweep = sweep_gates(swept, [], {}, board_size=2)

    base, five = sweep.variants[0], sweep.variants[-1]
    # The live gate can only fill one of the two board places (one name is gated).
    assert base.board_displacement == 0
    # Under the five-union gate the board fills to two, and BURST — admitted only by
    # 1w — takes the second place on both sessions.
    assert five.board_displacement == 2


def test_his_picks_in_field_and_top_thirty_counts_move_with_the_gate():
    """What the widening does to his own entries' placement: a pick admitted only by
    an excluded lookback appears in the field, and can reach the board (#149)."""
    from replay.gate_sweep import sweep_gates

    swept = _widening_pass()
    rows = [_funnel_row("STALE", session=swept[0].session)]

    sweep = sweep_gates(swept, rows, {}, board_size=3)

    base, five = sweep.variants[0], sweep.variants[-1]
    assert (base.picks_in_field, base.picks_on_board) == (0, 0)
    assert (five.picks_in_field, five.picks_on_board) == (1, 1)


def test_the_sweep_never_mutates_the_live_gate_width(store: Store):
    """The measurement's first acceptance criterion: the gate's lookbacks are handed
    in as a parameter, never assigned. Running the whole sweep leaves the live
    constant exactly where it was (#149)."""
    from screener import detection as detection_module
    from replay.gate_sweep import sweep_gates

    before = detection_module.DETECTION_LOOKBACKS
    sweep_gates(_widening_pass(), [], {}, board_size=2)
    assert detection_module.DETECTION_LOOKBACKS == before


def test_the_sweep_baselines_against_the_width_it_measured_not_the_live_one():
    """The sweep is the evidence that decided the live width, so its baseline is
    pinned to the width the gate ran at when the question was asked. A baseline that
    tracked `DETECTION_LOOKBACKS` would change the moment the verdict was adopted,
    and the report could no longer be re-run to audit itself (#149)."""
    from replay.gate_sweep import BASELINE_VARIANT, GATE_AS_MEASURED, GATE_VARIANTS

    assert GATE_AS_MEASURED == ("1m", "3m", "6m")
    assert BASELINE_VARIANT.lookbacks == GATE_AS_MEASURED
    # Every swept width is the as-measured gate plus something, so `added` names
    # exactly what that width re-admits.
    for variant in GATE_VARIANTS:
        assert set(GATE_AS_MEASURED) <= set(variant.lookbacks)
        assert set(variant.added) == set(variant.lookbacks) - set(GATE_AS_MEASURED)


def test_the_sweep_pass_reads_the_store_without_writing_to_it(store: Store):
    """The pass reconstructs the forward chain from the universe rows the replay
    store already holds and recomputes the ranks in memory — the chain's own reuse
    path, with nothing written back. A measurement must not leave the store it
    measured in a different state (#149)."""
    from replay.gate_sweep import build_sweep_sessions

    dates = _daily(date(2020, 1, 1), 40)
    store.append_bars("US", "HI", _bars_from_hlc(dates, _rising_hlc(40)))
    store.append_bars("US", "LAG", _bars_from_hlc(dates, _flat_hlc(40)))
    chain = replay_chain(store, "US", burn_in=0)
    sessions = [sf.session for sf in chain[-3:]]
    counts_before = _row_counts(store)

    swept = build_sweep_sessions(
        store, "US", sessions, lookbacks=("1m", "3m", "6m", "1w", "12m")
    )

    assert [s.session for s in swept] == sessions
    # The reconstructed pass is the chain's: the same members and the same ranks.
    for prepared, sf in zip(swept, chain[-3:]):
        assert prepared.members == sf.members
        assert prepared.ranks == sf.ranks
    assert _row_counts(store) == counts_before


def _row_counts(store: Store) -> dict[str, int]:
    """Row counts for every derived table — the store's state, before and after."""
    tables = ("runs", "universe", "ranks", "detections")
    return {
        t: store._con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        for t in tables
    }


def test_the_recovered_groups_are_profiled_against_the_gates_own_lookbacks():
    """"Admitted by 12m" is not the same claim as "topped out months ago and has
    done nothing since" — and only the second is what the §4.5 exclusion was written
    against. Each admitting-lookback group therefore carries where its trades sat on
    the lookbacks the gate already unions: below the field median on all three (the
    stale qualifier, counted) against within reach of the cut (#149)."""
    from replay.gate_sweep import FIELD_MEDIAN, NEAR_DECILE, profile_recovered

    session = date(2021, 3, 1)

    def _with_percentiles(ticker, pcts):
        return dataclasses.replace(
            _funnel_row(ticker, session=session), eval_percentiles=pcts
        )

    rows = [
        # Genuinely stale: top-decile on 12m, mid-pack or worse on every gated one.
        _with_percentiles("STALE", {"1m": 0.20, "3m": 0.30, "6m": 0.45, "12m": 0.96}),
        # Admitted by 12m, but 6m had it just under the cut — not a stale qualifier.
        _with_percentiles("NEAR", {"1m": 0.50, "3m": 0.70, "6m": 0.88, "12m": 0.95}),
        _with_percentiles("BURST", {"1w": 0.97, "1m": 0.10, "3m": 0.05, "6m": 0.10}),
    ]
    membership = {
        session: {"12m": {"STALE", "NEAR"}, "1w": {"BURST"}}
    }

    groups = {g.label: g for g in profile_recovered(rows, membership)}

    stale, burst = groups["12m only"], groups["1w only"]
    assert (stale.n, stale.dead_on_gated, stale.within_reach) == (2, 1, 1)
    assert (burst.n, burst.dead_on_gated, burst.within_reach) == (1, 1, 0)
    # The medians are the group's own, per lookback, off the margins #133 recorded.
    assert stale.median_percentiles["6m"] == 0.665
    # The two cuts are what they say they are.
    assert FIELD_MEDIAN == 0.50 and NEAR_DECILE == 0.80


def test_the_added_field_is_measured_for_staleness_not_only_his_trades():
    """§4.5's worry is about what the gate *admits*, not only about which of his
    trades a widening recovers — a widening can leave the recovered entries looking
    healthy while flooding the list with names that topped out long ago. So each
    width reports the share of the detections it adds that sit below the field median
    on every lookback the live gate unions (#149)."""
    from replay.gate_sweep import GateVariant, sweep_gates

    session = date(2021, 3, 1)
    ranks = [
        Rank("NOW", "3m", percentile=0.95, raw_return=0.8),
        # Admitted by 12m and genuinely dead on the gated lookbacks.
        Rank("STALE", "12m", percentile=0.97, raw_return=2.0),
        Rank("STALE", "3m", percentile=0.20, raw_return=0.0),
        # Admitted by 12m but still near the cut on 6m — not stale.
        Rank("NEAR", "12m", percentile=0.96, raw_return=1.5),
        Rank("NEAR", "6m", percentile=0.88, raw_return=0.9),
    ]
    swept = [_sweep_session(session, ranks, ["NOW", "STALE", "NEAR"])]

    sweep = sweep_gates(
        swept, [], {},
        variants=(
            GateVariant("live", ("1m", "3m", "6m")),
            GateVariant("+12m", ("1m", "3m", "6m", "12m")),
        ),
        board_size=30,
    )

    base, wider = sweep.variants
    # The baseline adds nothing to itself, so it has no added-field share to report.
    assert base.added_detections_total == 0 and base.added_stale_share is None
    # The wider gate adds two names, one of which is stale on the gate's own terms.
    assert wider.added_detections_total == 2
    assert wider.added_detections_stale == 1
    assert wider.added_stale_share == 0.5
    # The going rate: with no surfaced entries there is nothing to divide by.
    assert base.detections_per_surfaced_entry is None


# -- the candidate dimension under measurement (#160) -------------------------


def test_the_rs_line_column_is_read_off_the_field_member_not_the_score():
    """``RS line`` is a **candidate** dimension: measured by the contrast, absent
    from the score.

    It cannot be read off the breakdown, because :func:`seven_dimension_score`
    deliberately carries only the seven dimensions the rubric weighs — so a
    dimension still being judged cannot move a star or a board place. The contrast
    reads it off the field member instead, and this pins that wiring: two picks
    that hit it against a passed-over field where one of two does.
    """
    taken = [
        _scored_det("P1", 6, taken=True, rs_line=True),
        _scored_det("P2", 6, taken=True, rs_line=True),
    ]
    not_taken = [
        _scored_det("N1", 6, not_taken=True, rs_line=True),
        _scored_det("N2", 6, not_taken=True, rs_line=False),
    ]

    by_dim = {c.dimension: c for c in contrast_dimensions(taken, not_taken)}
    assert by_dim["RS line"].taken_hit_rate == 1.0
    assert by_dim["RS line"].not_taken_hit_rate == 0.5
    # Not in the score it sits beside — the seven the rubric weighs, and no more.
    assert "RS line" not in {d.dimension for d in taken[0].score.breakdown}


def test_the_rs_line_does_not_move_a_replayed_star():
    """The invariant the whole staging rests on: the replayed score is identical
    whether the candidate hits or misses, so the act of measuring the dimension
    cannot contaminate the measurement."""
    hit = _scored_det("AAA", 6, rs_line=True)
    miss = _scored_det("AAA", 6, rs_line=False)
    assert hit.score == miss.score


def test_build_field_defaults_the_candidate_dimension_to_absent():
    """A caller with no index bars to hand builds the same field as before, with
    every candidate reading **absent** rather than raising.

    Absent and not ``False``, which is what this defaulted to until #195 needed the
    distinction to hold end to end: a caller that never computed the dimension has
    not measured a decayed RS line, and a row saying ``False`` would put the whole
    field on the miss side of a measurement that reports the two apart. The
    reachable path always supplies a real value (:func:`session_rs_lines` keys
    every detection), so this is the default made honest rather than a bug fixed —
    but the honest default is the one that cannot lie if that path ever changes.
    """
    dets = [_det("AAA", 6), _det("BBB", 3)]

    without = build_field(dets, [])
    with_rs = build_field(dets, [], rs_line_of={"AAA": True})

    assert {d.symbol: d.rs_line for d in without} == {"AAA": None, "BBB": None}
    assert {d.symbol: d.rs_line for d in with_rs} == {"AAA": True, "BBB": None}
    # Supplying it changes neither the order nor the scores.
    assert [d.symbol for d in without] == [d.symbol for d in with_rs]
    assert [d.score for d in without] == [d.score for d in with_rs]


# -- the discrimination grid (#165): the detector change held apart from the
#    retention fix -----------------------------------------------------------
#
# §4's published pair — picks 17.3% against field 17.8% at >= 3.5 stars — was
# measured under detector v1 on the field the two-year rank retention had
# truncated. #164 fixed the truncation, and the same rubric on the whole field
# reads 14.6% / 12.6%. Two variables moved between those two pairs, so neither
# corrects the other. The grid re-measures the pair at each detector version
# against each field, so exactly one variable moves between adjacent cells.


def _grid_session(session: date, ranks: list[Rank], ranges: dict[str, float]):
    """One prepared sweep session whose detections differ only in their trailing
    3-bar range — the quantity v1's hard cut gated and v2's guard grades."""
    from replay.gate_sweep import SweepSession, gate_membership

    return SweepSession(
        session=session,
        members=sorted({r.symbol for r in ranks}),
        ranks=ranks,
        membership=gate_membership(ranks),
        detections=[
            dataclasses.replace(
                _det(symbol, cluster_k=5), session=session, range_3bar_adr=r
            )
            for symbol, r in sorted(ranges.items())
        ],
    )


def test_the_v1_field_is_the_v2_field_with_the_names_past_the_hard_cut_struck():
    """The one identity the grid stands on (#154, ``detection._find_cluster``): the
    restructure *added* names and moved none, so a name that cleared the old
    1.5xADR cut emits the same row under v2 as it did under v1. Reconstructing
    v1's field is therefore a filter on v2's, not a second detection pass."""
    from replay.discrimination_grid import DETECTORS, under_detector

    dets = [
        dataclasses.replace(_det("TIGHT", cluster_k=5), range_3bar_adr=1.2),
        dataclasses.replace(_det("WIDE", cluster_k=3), range_3bar_adr=2.4),
    ]

    # v1's hard cut strikes the name past 1.5; v2's far-outlier guard keeps it.
    assert [d.symbol for d in under_detector(dets, DETECTORS[1])] == ["TIGHT"]
    assert [d.symbol for d in under_detector(dets, DETECTORS[2])] == [
        "TIGHT",
        "WIDE",
    ]


def test_a_detector_version_carries_its_own_gate_width_not_the_live_one():
    """The stamp is a claim about the **population**, and #149 moved that population
    by admitting ``12m`` — so a version's lookbacks ride on the version rather than
    being read off the live constant, whose value this grid's own reading must not
    drift with (the discipline ``gate_sweep.GATE_AS_MEASURED`` sets)."""
    from replay.discrimination_grid import DETECTORS
    from replay.gate_sweep import GATE_AS_MEASURED

    assert DETECTORS[1].lookbacks == GATE_AS_MEASURED
    assert DETECTORS[2].lookbacks == GATE_AS_MEASURED
    assert DETECTORS[3].lookbacks == ("1m", "3m", "6m", "12m")
    # v1 and v2 differ in the cluster rule alone; v2 and v3 in the gate alone.
    assert DETECTORS[1].cluster_cut != DETECTORS[2].cluster_cut
    assert DETECTORS[2].cluster_cut == DETECTORS[3].cluster_cut


def test_the_truncated_field_drops_every_session_the_rank_retention_pruned():
    """What the bug did, reproduced as a parameter rather than as a bug: a measured
    session outside the retained window gated against an empty rank table and
    contributed *nothing*, so the truncated field is the whole field restricted to
    the sessions the store still holds ranks for (#164)."""
    from replay.discrimination_grid import (
        DETECTORS,
        FIELD_TRUNCATED,
        FIELD_WHOLE,
        measure_cell,
    )

    ranks = [Rank("NOW", "3m", percentile=0.95, raw_return=0.8)]
    pruned, retained = date(2020, 3, 2), date(2022, 3, 2)
    swept = [
        _grid_session(pruned, ranks, {"NOW": 1.0}),
        _grid_session(retained, ranks, {"NOW": 1.0}),
    ]
    def cell(source):
        return measure_cell(
            swept,
            DETECTORS[2],
            source,
            replayable=[],
            calendar=[pruned, retained],
            stored_rank_sessions={retained},
            blind_spot_count=0,
        )

    whole, truncated = cell(FIELD_WHOLE), cell(FIELD_TRUNCATED)

    assert (whole.sessions_with_detections, whole.field_detections) == (2, 2)
    assert (truncated.sessions_with_detections, truncated.field_detections) == (1, 1)
    # Both measured the same two sessions — the truncation is in the field, not in
    # the window, so the per-session figure is read against the window either way.
    assert whole.measured_sessions == truncated.measured_sessions == 2
    assert truncated.detections_per_session == 0.5
    # Both denominators are carried: dividing by the sessions that survived is how
    # the superseded 90.3 came about, so it is reported beside the honest figure
    # rather than in place of it.
    assert truncated.detections_per_contributing_session == 1.0


def test_the_grid_reports_the_share_at_or_above_the_published_threshold():
    """§4's pair is one number a side — the share at >= 3.5 stars — so the grid
    emits that share rather than leaving a histogram to be re-totalled by hand at
    each reading. An empty distribution has no share, and says so."""
    from replay.discrimination_grid import DISCRIMINATION_STARS, share_at_or_above
    from replay.placement import StarDistribution

    assert DISCRIMINATION_STARS == 3.5
    assert share_at_or_above(
        StarDistribution.from_stars([4.0, 3.5, 3.0, 2.0]), DISCRIMINATION_STARS
    ) == 0.5
    assert share_at_or_above(StarDistribution.from_stars([]), 3.5) is None


def test_the_deleted_sessions_are_measured_not_derived_by_subtraction_downstream():
    """The retention step's *mechanism* — the field was strongest exactly where the
    bug deleted it — is what turns "the null hardens" from an assertion into an
    explanation, so the grid measures the deleted sessions' own contribution and
    emits the counts. A share quoted in prose that no committed artefact carries is
    the same unreproducible figure this whole study exists to avoid."""
    from replay.discrimination_grid import (
        DETECTORS,
        FIELD_WHOLE,
        CellMeasurement,
        PrunedComparison,
        pruned_comparison,
    )
    from replay.placement import RubricStarDistributions, StarDistribution

    def cell(picks, field, sessions):
        return CellMeasurement(
            detector=DETECTORS[1],
            field_source=FIELD_WHOLE,
            measured_sessions=10,
            sessions_with_detections=sessions,
            field_detections=0,
            placed=0,
            in_field=0,
            eval_field_detections=0,
            by_rubric=[
                RubricStarDistributions(
                    rubric_version=1,
                    picks=StarDistribution.from_stars(picks),
                    field=StarDistribution.from_stars(field),
                )
            ],
        )

    # The truncated cell is a strict subset of the whole one — same detections,
    # same scoring, fewer sessions — so the difference is the deleted sessions.
    truncated = cell(picks=[4.0, 2.0], field=[3.5, 1.0], sessions=4)
    whole = cell(picks=[4.0, 2.0, 2.5], field=[3.5, 1.0, 4.0, 3.5], sessions=10)

    pruned = pruned_comparison(truncated, whole)

    assert isinstance(pruned, PrunedComparison)
    assert pruned.sessions == 6
    # One extra pick, scoring below the threshold; two extra field rows, both above.
    assert (pruned.picks_at_stars, pruned.picks_total) == (0, 1)
    assert (pruned.field_at_stars, pruned.field_total) == (2, 2)
    assert pruned.picks_share == 0.0
    assert pruned.field_share == 1.0
    assert pruned.edge == -100.0


def test_the_grid_never_mutates_the_live_detector_constants():
    """Read-only in the same sense the gate sweep is: every version's cluster cut
    and gate width are handed to the filter, never assigned to the live module."""
    from screener import detection as detection_module
    from replay.discrimination_grid import DETECTORS, under_detector

    before = (detection_module.OUTLIER_MULT, detection_module.DETECTION_LOOKBACKS)
    for spec in DETECTORS.values():
        under_detector([_det("AAA", cluster_k=5)], spec)
    assert (
        detection_module.OUTLIER_MULT,
        detection_module.DETECTION_LOOKBACKS,
    ) == before


# -- the second candidate dimension (#170/#171) -------------------------------
#
# `Relative move` — the `6m` return relative to ``MARKET_INDEX``, compounded, in
# ADR units, hit above zero. Pre-registered in ADR 0005 and measured by #171's
# selection contrast. It rides the field member as a **value** where ``RS line``
# rides as a boolean, and the reason is the registration's: the rubric owns the
# cut, a breakdown row carries the number, and a row cannot be re-denominated
# retroactively.


def test_the_relative_move_rides_as_a_value_and_the_cut_lives_in_one_place():
    """The column is the number; the boolean is derived from it at read time.

    Carrying the pass/fail instead would freeze the pre-registered cut into every
    stored row, and ADR 0004's later grading question — asked of the value —
    could then only be answered by re-scoring history.
    """
    dets = [_det("AAA", 6), _det("BBB", 3)]

    field = build_field(dets, [], relative_move_of={"AAA": 2.5, "BBB": -1.0})

    assert {d.symbol: d.relative_move for d in field} == {"AAA": 2.5, "BBB": -1.0}
    by_dim = {
        c.dimension: c
        for c in contrast_dimensions(
            [d for d in field if d.symbol == "AAA"],
            [d for d in field if d.symbol == "BBB"],
        )
    }
    assert by_dim["Relative move"].taken_hit_rate == 1.0
    assert by_dim["Relative move"].not_taken_hit_rate == 0.0
    assert by_dim["Relative move"].weight == 0


def test_an_absent_relative_move_is_none_and_scores_a_miss():
    """A name that had not listed six months ago, or has no ADR, is **absent** —
    not zero. The distinction is the rank table's own convention, and zero would
    be a real value sitting exactly on the cut."""
    field = build_field([_det("AAA", 6)], [])

    assert field[0].relative_move is None
    by_dim = {c.dimension: c for c in contrast_dimensions(field, [])}
    assert by_dim["Relative move"].taken_hit_rate == 0.0


def test_the_relative_move_does_not_move_a_replayed_star():
    """The staging invariant, asserted for the second candidate as it was for the
    first: measuring a dimension cannot contaminate the field it is measured on."""
    strong = _scored_det("AAA", 6, relative_move=9.0)
    weak = _scored_det("AAA", 6, relative_move=-9.0)
    assert strong.score == weak.score
    assert strong.score.breakdown == weak.score.breakdown
    assert "Relative move" not in {d.dimension for d in strong.score.breakdown}


def test_session_relative_moves_reads_the_market_index_as_the_benchmark(store: Store):
    """The wiring #171 runs on: the value is the name's `6m` return netted against
    ``MARKET_INDEX``, in the name's own ADR, read off the store.

    Two names over the same benchmark — one that outran it, one that lagged —
    pin that the benchmark is actually netted out rather than the raw move being
    reported under a relative name.
    """
    sessions = _daily(date(2020, 1, 1), 260)
    as_of = sessions[-1]
    anchor = anchor_date(as_of, "6m")

    def _step(before: float, after: float) -> list[Bar]:
        return [
            Bar(s, p, p * 1.05, p, p, p, 1000)
            for s, p in ((s, before if s <= anchor else after) for s in sessions)
        ]

    store.append_bars("US", MARKET_INDEX["US"], _step(100.0, 125.0))
    store.append_bars("US", "FAST", _step(100.0, 200.0))
    store.append_bars("US", "SLOW", _step(100.0, 110.0))
    dets = [
        dataclasses.replace(_det("FAST", 6), session=as_of),
        dataclasses.replace(_det("SLOW", 6), session=as_of),
    ]

    values = session_relative_moves(store, "US", dets)

    assert values["FAST"] == pytest.approx(0.6 / 0.05)
    assert values["SLOW"] < 0
    assert relative_move_hit(values["FAST"]) is True
    assert relative_move_hit(values["SLOW"]) is False


def test_a_study_column_is_read_through_a_supplied_reader_not_a_new_field():
    """#171 reports five descriptive columns beside the registered dimension —
    the raw move and the relative one at `1w` and `12m` — and none of them is a
    candidate for the rubric.

    So they are handed to the contrast as readers by the study script rather than
    added to :class:`ScoredDetection`, which is what keeps
    :data:`CANDIDATE_DIMENSIONS` an honest list of what has actually been
    registered. A column that can be promoted by editing a tuple is a column that
    can be promoted after seeing its gap.
    """
    taken = [_scored_det("P1", 6, taken=True), _scored_det("P2", 6, taken=True)]
    not_taken = [_scored_det("N1", 6, not_taken=True)]
    values = {"P1": 3.0, "P2": -1.0, "N1": -1.0}

    contrasts = contrast_dimensions(
        taken,
        not_taken,
        dimensions=CONTRAST_DIMENSIONS + (("raw 12m", 0),),
        readers={"raw 12m": lambda d: values[d.symbol] > 0},
    )

    by_dim = {c.dimension: c for c in contrasts}
    assert by_dim["raw 12m"].taken_hit_rate == 0.5
    assert by_dim["raw 12m"].not_taken_hit_rate == 0.0
    assert "raw 12m" not in dict(CANDIDATE_DIMENSIONS)


def test_a_study_column_cannot_redefine_a_registered_candidate():
    """The collision the ``readers`` seam has to refuse.

    A study supplying a reader named ``Relative move`` would report a number under
    a registered candidate's name while computing something of its own — the one
    way this contrast can be wrong and look fine, which is the same failure the
    :data:`CANDIDATES` comment describes for a mistyped dimension name.
    """
    with pytest.raises(ValueError, match="registered candidate"):
        contrast_dimensions(
            [_scored_det("P1", 6, taken=True)],
            [_scored_det("N1", 6, not_taken=True)],
            readers={"Relative move": lambda d: True},
        )


# -- the backtest run contract (issue #184) --------------------------------
#
# Phase 0 of PRD #182: the whole run contract as one frozen, serialisable value.
# These extend the one replay seam rather than starting a new file, as the PRD's
# testing decisions require. The backtest is a *new top-level package* that
# imports replay machinery rather than extending the replay package, so the
# imports below reach into ``backtest``, not ``replay``.

from backtest import DEFAULT_CONTRACT, Cell, RunContract, stamp_result
from backtest.contract import (
    DEFAULT_CONTRACT_JSON,
    METRIC_PRIMARY_KEY,
    SCOPE_MARKETS_KEY,
    UNIVERSE_LIQUIDITY_FLOOR_KEY,
    WINDOW_MEASURED_START_KEY,
)
from backtest.result import CONTRACT_KEY


def test_backtest_is_a_top_level_package_importing_replay_not_extending_it():
    """The backtest is new and top-level (PRD "Implementation Decisions").

    It is imported as ``backtest``, a sibling of ``replay`` and ``screener``, and
    it is not a submodule of ``replay``. The reuse is by import: it stands beside
    the replay package rather than extending it.
    """
    import backtest
    import replay

    assert backtest.__name__ == "backtest"
    assert not backtest.__name__.startswith("replay.")
    assert Path(backtest.__file__).parent != Path(replay.__file__).parent


def test_the_contract_is_frozen():
    """One frozen contract object: neither the contract nor a cell can be mutated
    in place, so a run cannot quietly re-decide a Phase 0 cell after the fact."""
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_CONTRACT.label = "tampered"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        DEFAULT_CONTRACT.cells[0].value = "tampered"  # type: ignore[misc]


def test_every_cell_carries_a_one_line_justification():
    """Every Phase 0 cell records its one-line justification (user story 3), so a
    reader can tell a measured choice from an arbitrary one — and a cell with a
    blank justification is rejected at construction, not merely discouraged."""
    assert DEFAULT_CONTRACT.cells  # the contract is not empty
    for cell in DEFAULT_CONTRACT.cells:
        assert cell.justification.strip()

    with pytest.raises(ValueError, match="justification"):
        Cell(key="x", value=1, justification="   ")


def test_cell_keys_are_unique():
    """A duplicate key is a second definition of the same cell, and is rejected —
    two runs must differ in a cell's *value*, never in which cell wins a clash."""
    assert len(DEFAULT_CONTRACT.keys()) == len(set(DEFAULT_CONTRACT.keys()))
    with pytest.raises(ValueError, match="duplicate"):
        RunContract(
            contract_version="1",
            label="dup",
            cells=(Cell("k", 1, "why"), Cell("k", 2, "why")),
        )


def test_the_contract_round_trips_through_json_without_loss():
    """The contract round-trips to and from JSON without loss (acceptance
    criterion): the reconstruction equals the original, cells and all."""
    restored = RunContract.from_json(DEFAULT_CONTRACT.to_json())

    assert restored == DEFAULT_CONTRACT
    assert restored.cells == DEFAULT_CONTRACT.cells


def test_the_committed_contract_file_matches_the_object(tmp_path):
    """The contract is fixed and committed before any code runs (user story 1):
    the committed ``references/`` file deserialises to exactly ``DEFAULT_CONTRACT``,
    and re-serialising the object reproduces the committed bytes — a drift guard
    so the file and the object cannot silently disagree."""
    assert Path(DEFAULT_CONTRACT_JSON).exists()
    assert RunContract.load(DEFAULT_CONTRACT_JSON) == DEFAULT_CONTRACT

    regenerated = tmp_path / "contract.json"
    DEFAULT_CONTRACT.write(regenerated)
    assert regenerated.read_text() == Path(DEFAULT_CONTRACT_JSON).read_text()


def test_contract_values_are_the_contract_values_not_the_apps():
    """The contract carries the deliberate Phase 0 values, read by key — in
    particular the liquidity floors are the contract's $10M / Rp 10B, not the
    app's inherited $20M / Rp 1B (user story 11)."""
    assert DEFAULT_CONTRACT.value(SCOPE_MARKETS_KEY) == ["US", "IDX"]
    assert DEFAULT_CONTRACT.value(WINDOW_MEASURED_START_KEY) == "2012-01-01"
    floors = DEFAULT_CONTRACT.value(UNIVERSE_LIQUIDITY_FLOOR_KEY)
    assert floors == {"US": 10_000_000.0, "IDX": 10_000_000_000.0}
    from screener.universe import LIQUIDITY_FLOOR

    assert floors["US"] != LIQUIDITY_FLOOR["US"]
    assert floors["IDX"] != LIQUIDITY_FLOOR["IDX"]
    # The pre-registered primary metric is arm B's after-cost expectancy.
    assert "arm_b" in DEFAULT_CONTRACT.value(METRIC_PRIMARY_KEY)


def test_a_missing_cell_is_a_loud_key_error():
    """Reading a cell the run never registered fails loudly, so a typo'd key is a
    ``KeyError`` rather than a silent ``None`` that reads as a real value."""
    with pytest.raises(KeyError):
        DEFAULT_CONTRACT.value("universe.no_such_gate")


def test_every_result_the_package_emits_carries_its_contract():
    """Any result the package emits carries the contract that produced it
    (acceptance criterion): the stamped contract is the serialised contract, in
    full, under a fixed key, and it round-trips back to the object."""
    stamped = stamp_result(DEFAULT_CONTRACT, {"headline": {"expectancy_r": 0.42}})

    assert stamped[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    assert stamped["headline"] == {"expectancy_r": 0.42}
    # The contract on the result is the contract, not a lossy summary of it.
    assert RunContract.from_dict(stamped[CONTRACT_KEY]) == DEFAULT_CONTRACT


def test_a_result_cannot_claim_two_contracts():
    """A payload that already carries a contract key is rejected rather than
    silently overwritten — a result claiming two contracts is a bug."""
    with pytest.raises(ValueError, match="two contracts"):
        stamp_result(DEFAULT_CONTRACT, {CONTRACT_KEY: {"forged": True}})


def test_two_runs_under_different_contracts_are_distinguishable_from_output_alone():
    """Two runs under different contracts are distinguishable from their serialised
    output alone (acceptance criterion): change one cell's value and the stamped
    result's bytes change, so a revision can never be mistaken for the original."""
    altered_cells = tuple(
        Cell(c.key, "5000000.0-and-rp-1b", c.justification)
        if c.key == UNIVERSE_LIQUIDITY_FLOOR_KEY
        else c
        for c in DEFAULT_CONTRACT.cells
    )
    other = RunContract(contract_version="2", label="looser floors", cells=altered_cells)

    a = json.dumps(stamp_result(DEFAULT_CONTRACT, {"headline": 1}), sort_keys=True)
    b = json.dumps(stamp_result(other, {"headline": 1}), sort_keys=True)

    assert a != b
    assert other != DEFAULT_CONTRACT


# -- the backtest's stateless universe (issue #185) -------------------------
#
# Phase 0's second half: a universe classifier that reads no prior membership.
# These extend the one replay seam beside the contract's tests above. The
# classifier is pure, so every case here is authored bars and a signal session —
# no store, no calendar, no yesterday.

import inspect

from screener import universe as app_universe
from screener.score import ADR_MIN
from backtest.contract import (
    UNIVERSE_IDX_PRICE_FLOOR_KEY,
    UNIVERSE_IDX_PRICE_FLOOR_ROLE_KEY,
    UNIVERSE_STATELESSNESS_KEY,
    UNIVERSE_TREND_GATE_KEY,
    UNIVERSE_VOLATILITY_GAP_REASON_KEY,
    UNIVERSE_VOLATILITY_GATE_KEY,
)
from backtest import universe as backtest_universe
from backtest.universe import (
    ADR_FLOOR,
    TREND_WINDOW,
    Candidate as UniverseCandidate,
    is_member as _is_universe_member,
    classify as _classify_universe,
)


def classify_universe(market, candidates, session, contract=DEFAULT_CONTRACT):
    """``backtest.universe.classify`` under the committed contract.

    The classifier itself never defaults its contract — a membership computed
    under a contract nobody named cannot be stamped with one. These cases are all
    about the gates rather than about which contract is in force, so the default
    lives here, in the test, where naming it is the exception.
    """
    return _classify_universe(market, candidates, session, contract)


def is_member(candidate, market, session, contract=DEFAULT_CONTRACT):
    return _is_universe_member(candidate, market, session, contract)

# 60 bars through t−1, plus session t itself — so every case can be asked both
# "what was knowable the night before" and "what does day t's own bar do", and
# the answer to the second must always be "nothing".
_U_SESSIONS = _daily(date(2020, 1, 1), 61)
_U_SIGNAL = _U_SESSIONS[-1]


def _universe_bars(
    *,
    price: float = 50.0,
    drift: float = 0.002,
    adr_pct: float = 0.05,
    dollar_volume: float = 50_000_000.0,
    sessions: list[date] | None = None,
) -> list[Bar]:
    """Bars that clear every gate by default, one knob per gate.

    ``drift`` sets the trend (a rise puts the close above its SMA50), ``adr_pct``
    is exactly the ADR the series prints (every bar spans ``high/low − 1 ==
    adr_pct``), ``price`` is the nominal quote the IDX trim reads, and
    ``dollar_volume`` is the turnover on every bar, so the 20-day median is that
    number. Unadjusted and adjusted closes are equal — no split is in play here.
    """
    out = []
    for i, s in enumerate(sessions or _U_SESSIONS):
        p = price * (1 + drift) ** i
        out.append(
            Bar(
                session=s,
                open=p,
                high=p * (1 + adr_pct),
                low=p,
                close=p,
                adj_close=p,
                volume=max(1, round(dollar_volume / p)),
            )
        )
    return out


def _candidate(symbol: str = "AAA", **kwargs) -> UniverseCandidate:
    return UniverseCandidate(symbol=symbol, name="", bars=_universe_bars(**kwargs))


def test_the_backtest_universe_reads_no_prior_membership():
    """Classifying the same session twice from different prior-membership states
    returns identical membership (acceptance criterion).

    There is nowhere to *put* a prior state: the signature carries no
    ``prior_members``, which is the structural half of the claim. The behavioural
    half is a name parked inside what would be the contract floor's hysteresis
    band (0.8–1.0 × $10M) — exactly where a stateful classifier's answer depends
    on yesterday's — answered the same way both times.
    """
    assert "prior_members" not in inspect.signature(_classify_universe).parameters
    assert "prior_members" in inspect.signature(app_universe.classify).parameters

    # The app, asked about a name inside *its* band, gives two different answers
    # for the two prior states — which is what "stateful" means here, and what
    # this classifier has to stop doing.
    sessions = _U_SESSIONS[:-1]
    app_band = app_universe.Candidate(
        symbol="BAND",
        name="",
        resolved=True,
        bars=_universe_bars(dollar_volume=17_000_000.0, sessions=sessions),
    )
    assert app_universe.classify("US", [app_band], sessions, {"BAND"}) == ["BAND"]
    assert app_universe.classify("US", [app_band], sessions, set()) == []

    # This one has only the one answer to give. $9M sits inside the band a
    # hysteretic version of the contract's own $10M floor would hold a member in
    # (0.8–1.0×), so it is exactly the name a reintroduced band would retain —
    # and it is excluded, on both of two identical calls.
    candidates = [_candidate("BAND", dollar_volume=9_000_000.0), _candidate("CLEAR")]
    assert classify_universe("US", candidates, _U_SIGNAL) == ["CLEAR"]
    assert classify_universe("US", candidates, _U_SIGNAL) == ["CLEAR"]


def test_each_universe_gate_excludes_for_its_own_reason():
    """A name failing each gate is excluded, one gate at a time (acceptance
    criterion): below the ADTV floor, below ADR20 3.5%, below its SMA50, and —
    on IDX only — below Rp 100. Every other name here is a member, so each
    exclusion is attributable to the one knob that was turned.
    """
    assert classify_universe(
        "US",
        [
            _candidate("MEMBER"),
            _candidate("THIN", dollar_volume=5_000_000.0),
            _candidate("QUIET", adr_pct=0.02),
            _candidate("FALLING", drift=-0.002),
        ],
        _U_SIGNAL,
    ) == ["MEMBER"]

    idx = dict(price=500.0, dollar_volume=50_000_000_000.0)
    assert classify_universe(
        "IDX",
        [
            _candidate("MEMBER", **idx),
            _candidate("PENNY", **{**idx, "price": 80.0}),
            _candidate("THIN", **{**idx, "dollar_volume": 5_000_000_000.0}),
            _candidate("QUIET", **{**idx, "adr_pct": 0.02}),
            _candidate("FALLING", **{**idx, "drift": -0.002}),
        ],
        _U_SIGNAL,
    ) == ["MEMBER"]

    # The Rp 100 trim is IDX's alone: the same nominal quote is a US member.
    assert is_member(_candidate("CHEAP", price=80.0), "US", _U_SIGNAL) is True


def test_the_universe_floors_are_the_contracts_and_never_the_apps():
    """Both market floors are the contract's values, and the app's are not
    consulted (acceptance criterion) — proven in both directions, since the two
    markets' floors move opposite ways.

    US: the contract's $10M is *looser* than the app's $20M, so a name at $15M is
    a member here and would not be there. IDX: the contract's Rp 10B is *tighter*
    than the app's Rp 1B, so a name at Rp 5B is excluded here and would be a
    member there. Reading either floor off ``screener.universe.LIQUIDITY_FLOOR``
    flips one of these.
    """
    assert app_universe.LIQUIDITY_FLOOR == {"US": 20_000_000.0, "IDX": 1_000_000_000.0}

    assert is_member(_candidate("US15M", dollar_volume=15_000_000.0), "US", _U_SIGNAL) is True
    assert is_member(
        _candidate("IDX5B", price=500.0, dollar_volume=5_000_000_000.0), "IDX", _U_SIGNAL
    ) is False


def test_universe_adtv_is_the_apps_median_so_a_block_trade_cannot_lift_a_name():
    """ADTV is the 20-day median of unadjusted close × volume, reusing the app's
    function, so one block trade cannot lift an illiquid name over the floor
    (acceptance criterion).

    The reuse is asserted by identity, not by resemblance. The behaviour is
    asserted on a name whose typical day is $1M and whose one block trade is
    $1B: the mean of that window is ~$51M, over the floor, and the median is $1M,
    under it.
    """
    assert backtest_universe.median_dollar_volume is app_universe.median_dollar_volume

    bars = _universe_bars(dollar_volume=1_000_000.0)
    block = bars[-2]
    bars[-2] = dataclasses.replace(block, volume=round(1_000_000_000.0 / block.close))
    window = [b.dollar_volume for b in bars[:-1][-20:]]
    assert sum(window) / len(window) > 10_000_000.0  # a mean would admit it

    assert is_member(UniverseCandidate("BLOCK", "", bars), "US", _U_SIGNAL) is False


def test_every_universe_gate_reads_only_bars_through_t_minus_1():
    """Every gate reads only bars at or before t−1 (acceptance criterion), so a
    signal on session *t* uses only what was knowable the night before.

    Session *t*'s own bar is authored to fail every gate at once — a limit-down,
    zero-range, near-untraded crash — and membership for a signal on *t* is
    unchanged. A gate that peeked at *t* would drop the name.
    """
    bars = _universe_bars()
    knowable = UniverseCandidate("AAA", "", bars[:-1])
    crash = dataclasses.replace(
        bars[-1], open=1.0, high=1.0, low=1.0, close=1.0, adj_close=1.0, volume=1
    )
    with_crash = UniverseCandidate("AAA", "", bars[:-1] + [crash])

    assert classify_universe("US", [with_crash], _U_SIGNAL) == ["AAA"]
    assert classify_universe("US", [with_crash], _U_SIGNAL) == classify_universe(
        "US", [knowable], _U_SIGNAL
    )
    # …and the very same crash bar *is* read once it falls on the night before.
    assert classify_universe("US", [with_crash], _U_SIGNAL + timedelta(days=1)) == []


def test_the_apps_universe_classifier_is_still_sticky_and_hysteretic():
    """The app's own classifier still returns sticky, hysteretic membership
    (acceptance criterion): the backtest's statelessness is a new classifier
    beside it, never an edit to it.

    A name at $17M sits inside the app's own band (0.8–1.0 × $20M): held if it
    was a member, refused if it was not. An unresolved name carries yesterday's
    classification either way.
    """
    sessions = _U_SESSIONS[:-1]
    held = app_universe.Candidate(
        symbol="BAND", name="", resolved=True, bars=_universe_bars(
            dollar_volume=17_000_000.0, sessions=sessions
        )
    )
    silent = dataclasses.replace(held, symbol="SILENT", resolved=False)

    assert app_universe.classify("US", [held], sessions, {"BAND"}) == ["BAND"]
    assert app_universe.classify("US", [held], sessions, set()) == []
    assert app_universe.classify("US", [silent], sessions, {"SILENT"}) == ["SILENT"]
    assert app_universe.classify("US", [silent], sessions, set()) == []


def test_the_prose_gate_cells_and_their_constants_cannot_drift_apart():
    """The trend window and the ADR floor are the two gate values the contract can
    only *describe* — ``"close > SMA50"`` and ``"ADR20 >= 3.5%"`` are prose, so
    unlike the market floors no caller can compute against them.

    That leaves them able to drift: reword the cell, or move the constant, and
    nothing else would notice. This is the something else. Both are pinned to the
    cell that justifies them, so a change has to be made in both places or fail
    here — which is where a reader learns the contract is the authority.
    """
    assert f"SMA{TREND_WINDOW}" in DEFAULT_CONTRACT.value(UNIVERSE_TREND_GATE_KEY)
    assert f"{ADR_FLOOR:.1%}" in DEFAULT_CONTRACT.value(UNIVERSE_VOLATILITY_GATE_KEY)


def test_the_universe_records_its_gap_below_the_rubrics_adr_floor():
    """The gap between the 3.5% floor and the rubric's 5% is recorded with its
    reason (acceptance criterion), so nobody later "fixes" the two to match.

    The gap is real (3.5% < 5%), and the reason travels with the run rather than
    living only in a comment: it is a contract cell, and the cell's justification
    names findings §6's measurement of what the 5% floor withholds.
    """
    assert ADR_FLOOR == 0.035
    assert ADR_FLOOR < ADR_MIN == 0.05

    reason = DEFAULT_CONTRACT.cell(UNIVERSE_VOLATILITY_GAP_REASON_KEY)
    assert "31%" in reason.justification
    assert "findings §6" in reason.justification


def test_the_universe_records_the_churn_statelessness_reintroduces():
    """The churn the stateless gate reintroduces is recorded as a known
    difference from the app (acceptance criterion) rather than fixed.

    The app damps it with :data:`~screener.universe.HYSTERESIS_EXIT`; this
    universe has no such band, and the contract says so — naming the hysteresis
    difference, the churn, and why it is nearly free at signal level.
    """
    assert app_universe.HYSTERESIS_EXIT == 0.8
    assert not hasattr(backtest_universe, "HYSTERESIS_EXIT")

    cell = DEFAULT_CONTRACT.cell(UNIVERSE_STATELESSNESS_KEY)
    assert cell.value == "stateless_gates_through_t_minus_1"
    assert "hysteresis" in cell.justification
    assert "churn" in cell.justification
    assert "signal level" in cell.justification


def test_the_idx_price_trim_is_recorded_as_data_validity_not_cost_control():
    """The Rp 100 trim is described as data validity wherever it surfaces, so no
    reader takes it for a penny-stock filter with an implied cost story.

    It is applied to the split-corrected series — a name whose *unadjusted* quote
    is under Rp 100 but whose split-corrected close is over it stays a member,
    which is the half of the claim a raw-close trim would get wrong.
    """
    assert DEFAULT_CONTRACT.value(UNIVERSE_IDX_PRICE_FLOOR_KEY) == 100.0
    assert DEFAULT_CONTRACT.value(UNIVERSE_IDX_PRICE_FLOOR_ROLE_KEY) == "data_validity"
    assert "cost control" in DEFAULT_CONTRACT.cell(
        UNIVERSE_IDX_PRICE_FLOOR_ROLE_KEY
    ).justification
    assert "data validity" in backtest_universe.passes_price_gate.__doc__

    # A 10-for-1 split: the raw quote is a tenth of the split-corrected one, and
    # the share count — so the turnover the liquidity gate reads — is unchanged.
    split = [
        dataclasses.replace(b, close=b.close / 10.0, volume=b.volume * 10)
        for b in _universe_bars(price=500.0, dollar_volume=50_000_000_000.0)
    ]
    assert split[-2].close < 100.0 <= split[-2].adj_close
    assert is_member(UniverseCandidate("SPLIT", "", split), "IDX", _U_SIGNAL) is True


def test_the_universe_needs_fifty_bars_before_it_will_admit_a_name():
    """SMA50 is also the binding listing-age floor: a name with fewer than 50
    traded bars has no SMA50 to be above, so it cannot be a member. The app's
    20-bar minimum is not what governs here.
    """
    assert TREND_WINDOW == 50
    short = _universe_bars(sessions=_U_SESSIONS[-41:])  # 40 bars through t−1
    assert is_member(UniverseCandidate("NEW", "", short), "US", _U_SIGNAL) is False

    just_enough = _universe_bars(sessions=_U_SESSIONS[-51:])  # 50 bars through t−1
    assert is_member(UniverseCandidate("OLD", "", just_enough), "US", _U_SIGNAL) is True


def test_the_universe_excludes_what_is_not_common_stock_using_the_apps_test():
    """Instrument type is the app's own :func:`~screener.universe.is_common_stock`,
    reused by identity — so the index and the benchmark ETFs the contract's
    reference exclusion names cannot be ranked here either (#162).
    """
    assert backtest_universe.is_common_stock is app_universe.is_common_stock
    assert classify_universe(
        "US",
        [_candidate("AAA"), _candidate("^IXIC"), _candidate("DBRG$H")],
        _U_SIGNAL,
    ) == ["AAA"]


# -- the paced bar fetcher and its refusal ledger (issue #186) --------------
#
# Phase 1 of PRD #182: fill a purpose-built backtest store by fetching through the
# app's own source layer, paced, with every enumerated symbol ending in either
# bars or a refusal row. Tests seed the one source seam (a fake client) and assert
# on the emitted rows — the store's bars and the coverage ledger — never on how
# the fetch got there, exactly as the replay seam does above.

from datetime import datetime, timezone

from backtest import (
    BuildCoverage,
    LiveStoreWriteRefused,
    coverage_path,
    Refusal,
    build_backtest_store,
    market_symbol,
)
from screener.source import (
    DEFAULT_MAX_ATTEMPTS,
    PermanentlyUnavailableError,
    RateLimitedError,
    Source,
)

# A time far past any fixture bar, so the finality rule never trims a synthetic
# session — the backtest crawls historical data, where every bar is final.
_BUILD_NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _bar_row(session: date, *, volume: int = 1_000_000, close: float = 10.0) -> dict:
    """One raw yfinance-style source row, the shape :func:`parse_bars` consumes."""
    return {
        "Date": session,
        "Open": close,
        "High": close,
        "Low": close,
        "Close": close,
        "Adj Close": close,
        "Volume": volume,
    }


class _FetchClient:
    """Fakes the one network operation the fetcher drives: per-symbol ``fetch``.

    ``responses`` maps a symbol to its fetch outcome — a list of raw bar rows
    (resolved), an empty list (silence -> unresolved), the string ``"429"``
    (raises, a throttled silence) or ``"refused"`` (a stated refusal). A symbol
    with no entry answers empty, i.e. unresolved. ``enumerate`` is unused here:
    the backtest fetcher takes an explicit enumeration, so the seam is the fetch
    boundary alone.
    """

    def __init__(self, responses: dict[str, object]) -> None:
        self._responses = responses
        self.fetched: list[str] = []

    def enumerate(self, market):  # pragma: no cover - not exercised by the fetcher
        raise NotImplementedError

    def fetch(self, symbol, start=None):
        self.fetched.append(symbol)
        outcome = self._responses.get(symbol, [])
        if outcome == "429":
            raise RateLimitedError(symbol)
        if outcome == "refused":
            raise PermanentlyUnavailableError(f"{symbol}: period 'max' is invalid")
        return outcome


def _fetch_source(responses: dict[str, object]) -> Source:
    """A real :class:`Source` — pacing, backoff and the resolution policy — over a
    fake client, with no backoff sleeps so the tests do not idle on silence."""
    return Source(_FetchClient(responses), backoff_base=0.0, sleep=lambda _s: None)


def test_idx_suffix_convention_is_applied_at_the_fetch_boundary():
    """The IDX exchange suffix is applied where the symbol is fetched and stored:
    an enumeration of bare IDX symbols is fetched as ``.JK`` and keyed by it, while
    US symbols and already-suffixed IDX ones are untouched (PRD story 50)."""
    assert market_symbol("IDX", "BBCA") == "BBCA.JK"
    assert market_symbol("IDX", "BBRI.JK") == "BBRI.JK"  # already suffixed
    assert market_symbol("IDX", "^JKSE") == "^JKSE"  # a reference takes no suffix
    assert market_symbol("US", "AAPL") == "AAPL"


def test_build_fetches_idx_symbols_under_the_jk_suffix(tmp_path):
    """A bare IDX enumeration resolves against the ``.JK`` wire form and stores its
    bars under it — the fetch went through the suffix convention, not around it."""
    client = _FetchClient({"BBCA.JK": [_bar_row(date(2015, 6, 1))]})
    source = Source(client, backoff_base=0.0, sleep=lambda _s: None)

    coverage = build_backtest_store(
        source, ["BBCA"], tmp_path / "backtest.duckdb",
        market="IDX", now=_BUILD_NOW,
    )

    assert client.fetched == ["BBCA.JK"]  # the suffix reached the wire
    store = Store.open(tmp_path / "backtest.duckdb")
    try:
        assert store.bars("IDX", "BBCA.JK") == [_bar(date(2015, 6, 1))]
    finally:
        store.close()
    assert coverage.stored == ("BBCA.JK",)


def test_every_enumerated_symbol_ends_in_bars_or_a_refusal_row(tmp_path):
    """Each enumerated symbol resolves to either bars in the store or a refusal row
    carrying its reason — silence, a stated 429, and a stated refusal each named
    (PRD story 53)."""
    source = _fetch_source(
        {
            "GOOD": [_bar_row(date(2015, 6, 1)), _bar_row(date(2015, 6, 2))],
            "SILENT": [],  # empty answer -> unresolved
            "HOT": "429",  # a stated 429 -> throttled silence
            "REFUSED": "refused",  # a stated refusal
        }
    )

    coverage = build_backtest_store(
        source, ["GOOD", "SILENT", "HOT", "REFUSED"],
        tmp_path / "backtest.duckdb", market="US", now=_BUILD_NOW,
    )

    assert coverage.stored == ("GOOD",)
    by_symbol = {r.symbol: r.reason for r in coverage.refusals}
    assert by_symbol == {
        "SILENT": "unresolved",
        "HOT": "throttled",
        "REFUSED": "refused",
    }

    store = Store.open(tmp_path / "backtest.duckdb")
    try:
        assert len(store.bars("US", "GOOD")) == 2
        assert store.bars("US", "SILENT") == []
        assert store.bars("US", "REFUSED") == []
    finally:
        store.close()


def test_the_bar_and_refusal_counts_sum_to_the_enumeration(tmp_path):
    """The bars count and the refusal count sum to the enumeration (PRD story 54,
    acceptance criterion), and the sum is asserted by ``check`` before the coverage
    is even returned."""
    enumeration = ["A", "B", "C", "D", "E"]
    source = _fetch_source(
        {
            "A": [_bar_row(date(2015, 6, 1))],
            "B": [_bar_row(date(2015, 6, 1))],
            "C": [],  # unresolved
            "D": "refused",
            # "E" absent -> unresolved
        }
    )

    coverage = build_backtest_store(
        source, enumeration, tmp_path / "backtest.duckdb",
        market="US", now=_BUILD_NOW,
    )

    assert len(coverage.stored) + len(coverage.refusals) == len(enumeration)
    assert coverage.enumerated == len(enumeration)
    # And the check is not merely descriptive: a coverage that does not sum raises.
    with pytest.raises(ValueError, match="does not sum"):
        BuildCoverage("US", enumerated=3, stored=("A",), refusals=()).check()


def test_zero_volume_phantom_bars_are_removed_at_ingest(tmp_path):
    """Zero-volume phantom bars are removed at ingest and never zero-filled or
    carried forward (PRD story 55): a mixed series stores only its traded bars, and
    a wholly-phantom series stores nothing and lands in the ledger as ``no_bars``."""
    source = _fetch_source(
        {
            "MIXED": [
                _bar_row(date(2015, 6, 1), volume=1_000_000),
                _bar_row(date(2015, 6, 2), volume=0),  # phantom — dropped
                _bar_row(date(2015, 6, 3), volume=2_000_000),
            ],
            "PHANTOM": [_bar_row(date(2015, 6, 1), volume=0)],  # all phantom
        }
    )

    coverage = build_backtest_store(
        source, ["MIXED", "PHANTOM"], tmp_path / "backtest.duckdb",
        market="US", now=_BUILD_NOW,
    )

    store = Store.open(tmp_path / "backtest.duckdb")
    try:
        sessions = [b.session for b in store.bars("US", "MIXED")]
        assert sessions == [date(2015, 6, 1), date(2015, 6, 3)]  # the phantom is gone
        assert store.bars("US", "PHANTOM") == []
    finally:
        store.close()

    assert coverage.stored == ("MIXED",)
    assert Refusal("PHANTOM", "no_bars") in coverage.refusals


def test_a_repeated_build_does_not_duplicate_rows(tmp_path):
    """A resumed or repeated build does not duplicate rows (acceptance criterion):
    the second build re-fetches the same series and the store holds each bar once,
    because ``append_bars`` is idempotent."""
    out = tmp_path / "backtest.duckdb"
    responses = {"AAA": [_bar_row(date(2015, 6, 1)), _bar_row(date(2015, 6, 2))]}

    first = build_backtest_store(
        _fetch_source(responses), ["AAA"], out, market="US", now=_BUILD_NOW
    )
    second = build_backtest_store(
        _fetch_source(responses), ["AAA"], out, market="US", now=_BUILD_NOW
    )

    store = Store.open(out)
    try:
        assert len(store.bars("US", "AAA")) == 2  # not four
    finally:
        store.close()
    assert first == second  # the coverage is stable across a repeat


def _seed_live_store(tmp_path, monkeypatch):
    """A live store at the path the app itself would read, and its bytes.

    The build has to be pointed at the *real* live path to be tested against it,
    and :data:`screener.app.DEFAULT_DB_PATH` is read at import time, so the
    attribute is patched rather than the environment. Hashing an arbitrary
    sibling file instead would pass whatever the build did to live history.
    """
    import screener.app

    live_path = tmp_path / "screener.duckdb"
    live = Store.open(live_path)
    live.append_bars("US", "AAA", [_bar(date(2020, 6, 1))])
    live.close()
    monkeypatch.setattr(screener.app, "DEFAULT_DB_PATH", str(live_path))
    return live_path, hashlib.sha256(live_path.read_bytes()).hexdigest()


def test_the_build_refuses_to_write_into_the_live_store(tmp_path, monkeypatch):
    """Handed the live store as its output, the build refuses before opening it.

    This is the claim the module docstring makes — that the run is structurally
    incapable of corrupting live history (PRD story 49) — and until #186 was
    reviewed nothing enforced it: ``Store.open(out_path)`` opens read-write, so
    a caller passing the live path wrote bars straight into live history. The
    refusal is what makes "never written" a property of the code rather than of
    the caller's care, and the bytes are checked after, because an exception
    raised too late is not a guard.
    """
    live_path, before = _seed_live_store(tmp_path, monkeypatch)

    with pytest.raises(LiveStoreWriteRefused, match="live store"):
        build_backtest_store(
            _fetch_source({"ZZZ": [_bar_row(date(2015, 6, 1))]}),
            ["ZZZ"], live_path, market="US", now=_BUILD_NOW,
        )

    assert hashlib.sha256(live_path.read_bytes()).hexdigest() == before


def test_the_build_refuses_the_live_store_by_identity_not_by_spelling(
    tmp_path, monkeypatch
):
    """The refusal resolves the path, so it is not dodged by a different spelling
    of the same file — the guard is about which file is written, not which string
    was passed."""
    live_path, before = _seed_live_store(tmp_path, monkeypatch)
    indirect = tmp_path / "sub" / ".." / "screener.duckdb"
    (tmp_path / "sub").mkdir()

    with pytest.raises(LiveStoreWriteRefused):
        build_backtest_store(
            _fetch_source({"ZZZ": [_bar_row(date(2015, 6, 1))]}),
            ["ZZZ"], indirect, market="US", now=_BUILD_NOW,
        )

    assert hashlib.sha256(live_path.read_bytes()).hexdigest() == before


def test_the_build_leaves_a_live_store_byte_identical(tmp_path, monkeypatch):
    """A build into its own purpose-built store leaves the live store — the one
    the app actually reads — byte-identical (PRD story 49).

    The store is the configured live one, not a same-named file the build never
    had a reference to, so the assertion is about live history rather than about
    an unrelated file in a temp directory.
    """
    live_path, before = _seed_live_store(tmp_path, monkeypatch)

    coverage = build_backtest_store(
        _fetch_source({"ZZZ": [_bar_row(date(2015, 6, 1))]}),
        ["ZZZ"], tmp_path / "backtest.duckdb", market="US", now=_BUILD_NOW,
    )

    assert coverage.stored == ("ZZZ",)
    assert hashlib.sha256(live_path.read_bytes()).hexdigest() == before


def test_the_fetch_reports_progress_during_a_long_run(tmp_path):
    """A long fetch reports progress as it goes, so a multi-hour crawl is not killed
    for having printed nothing (PRD story 52). The pull's closing line always lands,
    marking the end of the pull and naming the running resolved/silent/refused
    split; the sweep then speaks for itself, so the build's last word is what the
    sweep got back rather than a tally the sweep has since revised."""
    lines: list[str] = []
    responses = {f"S{i}": [_bar_row(date(2015, 6, 1))] for i in range(3)}
    responses["S1"] = []  # one silence, so the split is not trivial

    build_backtest_store(
        _fetch_source(responses), ["S0", "S1", "S2"],
        tmp_path / "backtest.duckdb", market="US", now=_BUILD_NOW,
        progress=lines.append,
    )

    assert lines  # progress was emitted
    pull_close = next(line for line in lines if "US: pull 3/3" in line)
    assert "2 resolved" in pull_close and "1 silent" in pull_close
    assert "sweep recovered 0 of 1 silent symbols" in lines[-1]


def test_the_coverage_round_trips_through_json(tmp_path):
    """The coverage is a committable value: both counts and every refusal row
    survive a JSON round-trip, so the store's coverage can be committed beside it
    rather than recomputed on trust (PRD story 54)."""
    coverage = build_backtest_store(
        _fetch_source({"A": [_bar_row(date(2015, 6, 1))], "B": "refused"}),
        ["A", "B"], tmp_path / "backtest.duckdb", market="US", now=_BUILD_NOW,
    )

    restored = BuildCoverage.from_dict(json.loads(json.dumps(coverage.to_dict())))

    assert restored == coverage


class _VirtualClock:
    """A clock that only moves when something waits on it.

    Pacing is a claim about *time between requests*, and the fetcher's own
    wall-clock elapsed is not evidence for it — a test that timed a real pull
    would be asserting the machine's speed. So the source's clock is injected: the
    only thing that can advance it is a wait the pacer itself decided to take.
    """

    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += max(0.0, seconds)


def test_the_fetch_is_paced_rather_than_bursted(tmp_path):
    """A run of symbols is spread across the provider's sustained rate rather than
    fired at once (PRD story 51): at two requests a second, six symbols cannot have
    been asked for in under the five intervals that separate them.

    This is what lets a fourteen-year crawl finish rather than stall — a burst
    earns the throttle wall the pacer exists to stay under.
    """
    clock = _VirtualClock()
    symbols = [f"S{i}" for i in range(6)]
    source = Source(
        _FetchClient({s: [_bar_row(date(2015, 6, 1))] for s in symbols}),
        rate_per_sec=2.0,
        backoff_base=0.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )

    build_backtest_store(
        source, symbols, tmp_path / "backtest.duckdb",
        market="US", now=_BUILD_NOW, workers=1,
    )

    # Every symbol resolved first time, so no backoff ran: the whole of the clock's
    # advance is pacing, and it spans the five gaps between six paced requests.
    assert clock.now >= (len(symbols) - 1) / 2.0


class _TailSilenceClient:
    """A client whose silence is a fact about the *pull*, not about the symbol.

    The first ``silent_asks`` fetches raise a stated 429; every ask after that
    answers in full. That is the shape issue #104 measured — a provider that has
    stopped answering a long crawl serves the very same request once it has been
    left alone for a minute — and it is the shape a fetcher that writes its tail
    off where it fell would record as a permanent absence.
    """

    def __init__(self, rows: list[dict], *, silent_asks: int) -> None:
        self._rows = rows
        self._silent_asks = silent_asks
        self.asks = 0

    def enumerate(self, market):  # pragma: no cover - not exercised by the fetcher
        raise NotImplementedError

    def fetch(self, symbol, start=None):
        self.asks += 1
        if self.asks <= self._silent_asks:
            raise RateLimitedError(symbol)
        return self._rows


def test_a_throttled_tail_is_swept_before_it_is_ledgered_as_an_absence(tmp_path):
    """Silence that survives a symbol's own retries is re-asked after a rest, and
    the answer supersedes the verdict the pull reached (issue #104).

    This is the ledger's honesty, not a recovery nicety. A crawl's tail silence is
    overwhelmingly the provider's exhaustion rather than a listing with no
    history, so a fetcher that stops at the first pass writes throttled names into
    the ledger as refusals — and Phase 2 reads that inflated count as the
    survivorship bound. An absence has to be a fact about the symbol.
    """
    # Silent for the whole of the first pass's retry budget, answering only once
    # the sweep has rested and asked again.
    client = _TailSilenceClient([_bar_row(date(2015, 6, 1))], silent_asks=DEFAULT_MAX_ATTEMPTS)
    source = Source(client, backoff_base=0.0, sleep=lambda _s: None)

    coverage = build_backtest_store(
        source, ["TAIL"], tmp_path / "backtest.duckdb",
        market="US", now=_BUILD_NOW,
    )

    assert coverage.stored == ("TAIL",)
    assert coverage.refusals == ()  # not written off where it fell
    coverage.check()

    store = Store.open(tmp_path / "backtest.duckdb")
    try:
        assert store.bars("US", "TAIL") == [_bar(date(2015, 6, 1))]
    finally:
        store.close()


def test_the_sweep_revises_a_verdict_rather_than_adding_one(tmp_path):
    """A swept symbol is one symbol however many times it was asked: the recovered
    name appears once in the coverage, and the sum invariant still holds over an
    enumeration whose tail was swept."""
    client = _TailSilenceClient([_bar_row(date(2015, 6, 1))], silent_asks=DEFAULT_MAX_ATTEMPTS)
    source = Source(client, backoff_base=0.0, sleep=lambda _s: None)

    coverage = build_backtest_store(
        source, ["TAIL"], tmp_path / "backtest.duckdb",
        market="US", now=_BUILD_NOW,
    )

    assert coverage.enumerated == 1
    assert len(coverage.stored) + len(coverage.refusals) == 1


def test_a_name_enumerated_twice_is_one_symbol_with_one_verdict(tmp_path):
    """A duplicated enumeration entry — including one listed once bare and once
    already suffixed — is one symbol, asked once and ledgered once.

    The sum invariant is the thing being protected: counting a name twice in the
    enumeration while the ledger holds one verdict for it would make the invariant
    unsatisfiable, and an invariant that cannot hold reports nothing about coverage.
    """
    client = _FetchClient({"BBCA.JK": [_bar_row(date(2015, 6, 1))]})
    source = Source(client, backoff_base=0.0, sleep=lambda _s: None)

    coverage = build_backtest_store(
        source, ["BBCA", "BBCA.JK", "BBCA"], tmp_path / "backtest.duckdb",
        market="IDX", now=_BUILD_NOW,
    )

    assert client.fetched == ["BBCA.JK"]  # asked once, not three times
    assert coverage.enumerated == 1
    assert coverage.stored == ("BBCA.JK",)
    coverage.check()


# -- what the #186 review found unguarded -----------------------------------


def test_the_build_refuses_to_return_a_coverage_that_does_not_sum(tmp_path, monkeypatch):
    """The sum invariant is enforced in the build, not merely asserted in a test.

    The spec calls this property the whole point — a symbol that is silently
    absent is survivorship bias entering by the back door — but until this test
    the `.check()` call could be deleted with all tests still passing, because
    the ledger sums by construction and nothing exercised the refusal. Here the
    source layer is made to lose a symbol, which is the shape of the real failure
    (a resolution that never arrives leaves the ledger short), and the build must
    refuse rather than hand back a coverage that quietly under-reports.
    """
    import backtest.store as bt_store

    real = bt_store.resolve_all
    monkeypatch.setattr(
        bt_store, "resolve_all",
        lambda source, symbols, **kw: (
            r for r in real(source, symbols, **kw) if r.symbol != "BBB"
        ),
    )

    with pytest.raises(ValueError, match="does not sum to the enumeration"):
        build_backtest_store(
            _fetch_source({"AAA": [_bar_row(date(2015, 6, 1))], "BBB": []}),
            ["AAA", "BBB"], tmp_path / "bt.duckdb", market="US", now=_BUILD_NOW,
        )


def test_the_build_commits_its_coverage_beside_the_store(tmp_path):
    """Both counts are committed, not just returned (plan Phase 1 "Done when":
    "the two counts sum to the enumeration, and **both are committed**").

    A coverage that lives only in a return value is recomputed on trust by
    whoever asks next; written beside the store it is the artefact that makes an
    absence a fact. It round-trips back to the value the build returned.
    """
    out = tmp_path / "bt.duckdb"
    coverage = build_backtest_store(
        _fetch_source({"AAA": [_bar_row(date(2015, 6, 1))], "BBB": "refused"}),
        ["AAA", "BBB"], out, market="US", now=_BUILD_NOW,
    )

    written = coverage_path(out, "US")
    assert written.exists()
    assert BuildCoverage.load(written) == coverage
    assert json.loads(written.read_text())["enumerated"] == 2


def test_a_resumed_build_does_not_refetch_what_the_store_already_has(tmp_path):
    """A resumed build skips symbols already carrying bars (spec: "A resumed or
    repeated build does not duplicate rows"; the issue splits this from the crawl
    precisely because the crawl is "hours of wall clock").

    Without this the store's contents are ignored and a resumption costs the
    whole crawl again — rows stay unduplicated, but only because `append_bars` is
    idempotent. An already-stored symbol still belongs to the coverage: it ended
    with bars on disk, which is what `stored` means.
    """
    out = tmp_path / "bt.duckdb"
    first = _FetchClient({"AAA": [_bar_row(date(2015, 6, 1))], "BBB": "refused"})
    build_backtest_store(
        Source(first, backoff_base=0.0, sleep=lambda _s: None),
        ["AAA", "BBB"], out, market="US", now=_BUILD_NOW,
    )
    assert first.fetched == ["AAA", "BBB"]

    second = _FetchClient({"AAA": [_bar_row(date(2015, 6, 1))], "BBB": "refused"})
    coverage = build_backtest_store(
        Source(second, backoff_base=0.0, sleep=lambda _s: None),
        ["AAA", "BBB"], out, market="US", now=_BUILD_NOW, resume=True,
    )

    assert second.fetched == ["BBB"]  # AAA had bars; only the refusal is retried
    assert coverage.stored == ("AAA",)
    assert coverage.enumerated == 2
    coverage.check()


def test_a_repeated_build_still_refetches_everything_by_default(tmp_path):
    """Skipping is opt-in. A plain repeat re-asks for every symbol, so a build
    that means to extend an existing store's history is not silently short-cut
    into a no-op — `resume` names the intent."""
    out = tmp_path / "bt.duckdb"
    for _ in range(2):
        client = _FetchClient({"AAA": [_bar_row(date(2015, 6, 1))]})
        build_backtest_store(
            Source(client, backoff_base=0.0, sleep=lambda _s: None),
            ["AAA"], out, market="US", now=_BUILD_NOW,
        )
    assert client.fetched == ["AAA"]


def test_names_folded_by_deduplication_are_reported_not_silently_dropped(tmp_path):
    """A duplicate name is folded to one verdict, and the fold is recorded.

    `enumerated` is the count of distinct symbols, so a caller handing in 900
    names with 20 repeats sees 880 and an invariant that holds — with the 20
    vanished from the arithmetic unexplained. `duplicates` is what keeps the
    caller's own enumeration reconcilable with this one.
    """
    coverage = build_backtest_store(
        _fetch_source({"AAA": [_bar_row(date(2015, 6, 1))]}),
        ["AAA", "AAA", "aaa".upper()], tmp_path / "bt.duckdb",
        market="US", now=_BUILD_NOW,
    )

    assert coverage.enumerated == 1
    assert coverage.duplicates == 2
    assert coverage.stored == ("AAA",)
    coverage.check()
    assert BuildCoverage.from_dict(coverage.to_dict()) == coverage


# -- the full crawl: enumeration, store window and the runner (issue #187) ---
#
# Phase 1's second half. #186 built the fetch loop against an explicit
# enumeration; this is what decides *which* symbols that enumeration holds, trims
# the pull to the contract's store window, and drives both markets from one
# command. The seam stays where #186 put it — a fake source client — so nothing
# here reaches the network either.

from backtest.crawl import (
    CRAWL_START,
    NOT_COMMON_STOCK,
    UNREAD_REFERENCE,
    Enumeration,
    crawl_market,
    enumeration_path,
    main as crawl_main,
    narrow,
)
from backtest.store import live_store_path
from screener.pipeline import fetch_set
from screener.source import Instrument


def test_the_crawl_fetches_the_apps_own_fetch_set_not_a_second_one():
    """The crawl narrows the provider's listing with `screener.pipeline.fetch_set`
    itself — the *same* callable the nightly pull uses (issue #99), not a copy of
    its rule.

    The backtest's denominator is meant to be the app's: a looser fetch set here
    would price names the product cannot trade, and a stricter one would measure
    a market the app doesn't screen. Two copies of the rule would be two things to
    keep in lockstep, with nothing to fail if they drifted — so the test pins the
    call, not the behaviour.
    """
    instruments = [
        Instrument(market="US", symbol="^IXIC", role="reference"),
        Instrument(market="US", symbol="SPY", role="reference"),
        Instrument(
            market="US", symbol="AAPL", role="candidate",
            name="Apple Inc. - Common Stock",
        ),
        Instrument(
            market="US", symbol="ABCW", role="candidate", name="Some Fund - Warrant",
        ),
    ]

    enumeration = narrow(instruments, "US")

    assert enumeration.fetched == tuple(fetch_set(instruments, "US"))
    assert enumeration.fetched == ("^IXIC", "AAPL")


def test_every_listed_name_the_crawl_drops_is_recorded_with_its_rule():
    """The names the crawl never asks about are committed too, with why.

    The coverage ledger accounts for every symbol the crawl was *handed*, but the
    narrowing happens before that — on US it discards 7,643 of 13,141 — and the
    ledger cannot see what it never asked about. Left there, the plan's own
    standard ("a symbol that is silently absent is survivorship bias entering
    through the back door") would hold for the fetch set and quietly fail for the
    listing. Between the two files every listed name gets exactly one verdict.
    """
    instruments = [
        Instrument(market="US", symbol="^IXIC", role="reference"),
        Instrument(market="US", symbol="SPY", role="reference"),
        Instrument(
            market="US", symbol="ABCW", role="candidate", name="Some Fund - Warrant",
        ),
    ]

    enumeration = narrow(instruments, "US")

    assert enumeration.listed == 3
    assert enumeration.excluded == (
        ("SPY", UNREAD_REFERENCE),
        ("ABCW", NOT_COMMON_STOCK),
    )
    enumeration.check()


def test_the_enumeration_record_must_sum_to_the_listing():
    """The same invariant the coverage has, one level up: fetched plus excluded is
    the listing, or the record refuses to be a record."""
    with pytest.raises(ValueError):
        Enumeration("US", listed=9, fetched=("AAA",), excluded=()).check()


def test_the_idx_crawl_keeps_its_own_index_and_drops_the_us_one():
    """The reference kept is the *market's* index, not a constant: IDX's regime
    reads `^JKSE`, and a US index row appearing in an IDX listing is not the
    thing that regime will read. IDX names are recorded in their stored `.JK`
    form, so the enumeration and the coverage speak the same names."""
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="^IXIC", role="reference"),
        Instrument(market="IDX", symbol="BBCA", role="candidate", name="BBCA"),
    ]

    enumeration = narrow(instruments, "IDX")

    assert enumeration.fetched == ("^JKSE", "BBCA.JK")
    assert enumeration.excluded == (("^IXIC", UNREAD_REFERENCE),)


def test_the_store_window_trims_bars_before_the_contracts_store_start(tmp_path):
    """Bars before `window.store_start` never reach the store (contract cell
    2011-01-01, PRD story 6).

    The provider is asked for full history regardless — a cold start is the only
    request that surfaces a stated refusal (`screener.source`, issue #100), so the
    ledger's `refused` reason depends on asking for `period="max"`. The window is
    therefore applied at ingest rather than at the request, which keeps the
    refusal vocabulary intact and still leaves the store carrying only the years
    the run measures.
    """
    source = _fetch_source(
        {
            "AAA": [
                _bar_row(date(2009, 6, 1)),
                _bar_row(date(2011, 1, 3)),
                _bar_row(date(2015, 6, 1)),
            ]
        }
    )
    out = tmp_path / "bt.duckdb"

    coverage = build_backtest_store(
        source, ["AAA"], out, market="US", now=_BUILD_NOW, start=CRAWL_START,
    )

    store = Store.open(out)
    try:
        assert [b.session for b in store.bars("US", "AAA")] == [
            date(2011, 1, 3),
            date(2015, 6, 1),
        ]
    finally:
        store.close()
    assert coverage.stored == ("AAA",)


def test_a_symbol_whose_whole_history_predates_the_window_is_a_refusal(tmp_path):
    """A symbol that resolves but leaves no bars *inside* the window ends with no
    bars in the store, so it earns a ledger row like any other absence — and the
    row says `outside_window`, not `no_bars`.

    The distinction is load-bearing for Phase 2, which reads this ledger as the
    survivorship bound. `no_bars` means ingest hygiene threw everything away — a
    symbol that quotes but never trades. `outside_window` means the listing has
    real history that simply stopped before the run starts, which is not a hole in
    the run's coverage at all. Folding the two would inflate the bound with names
    the run was never going to measure.
    """
    coverage = build_backtest_store(
        _fetch_source({"OLD": [_bar_row(date(2009, 6, 1))]}),
        ["OLD"], tmp_path / "bt.duckdb", market="US", now=_BUILD_NOW,
        start=CRAWL_START,
    )

    assert coverage.stored == ()
    assert coverage.refusals == (Refusal("OLD", "outside_window"),)
    coverage.check()


def test_the_two_markets_coverages_survive_one_shared_store(tmp_path):
    """Both markets fill one store, and each commits its own coverage file.

    The store is keyed `(market, symbol)`, so one file holding both markets is
    what Phase 3 wants to open. But coverage is a *per-market* fact — the
    enumeration it sums to is one market's — so a single path derived from the
    store alone would have the second market silently overwrite the first's
    ledger, and Phase 2 would read a US bound off an IDX crawl.
    """
    out = tmp_path / "bt.duckdb"
    us = build_backtest_store(
        _fetch_source({"AAA": [_bar_row(date(2015, 6, 1))]}),
        ["AAA"], out, market="US", now=_BUILD_NOW,
    )
    idx = build_backtest_store(
        _fetch_source({"BBCA.JK": [_bar_row(date(2015, 6, 1))]}),
        ["BBCA"], out, market="IDX", now=_BUILD_NOW,
    )

    assert coverage_path(out, "US") != coverage_path(out, "IDX")
    assert BuildCoverage.load(coverage_path(out, "US")) == us
    assert BuildCoverage.load(coverage_path(out, "IDX")) == idx


def test_crawl_market_enumerates_then_fetches_the_window(tmp_path):
    """`crawl_market` is the whole per-market job: enumerate through the source,
    filter to the fetch set, then fill the store over the contract's window."""

    class _EnumeratingClient(_FetchClient):
        def enumerate(self, market):
            return [
                Instrument(market="US", symbol="^IXIC", role="reference"),
                Instrument(market="US", symbol="SPY", role="reference"),
                Instrument(
                    market="US", symbol="AAPL", role="candidate",
                    name="Apple Inc. - Common Stock",
                ),
            ]

    client = _EnumeratingClient(
        {
            "^IXIC": [_bar_row(date(2010, 6, 1)), _bar_row(date(2015, 6, 1))],
            "AAPL": [_bar_row(date(2015, 6, 1))],
        }
    )
    out = tmp_path / "bt.duckdb"

    enumeration, coverage = crawl_market(
        Source(client, backoff_base=0.0, sleep=lambda _s: None),
        market="US", out_path=out, now=_BUILD_NOW, progress=lambda _line: None,
    )

    assert client.fetched == ["^IXIC", "AAPL"]  # SPY was never asked for
    assert enumeration.listed == 3
    assert coverage.enumerated == 2
    assert coverage.stored == ("AAPL", "^IXIC")
    # Both records are committed, not just returned.
    assert Enumeration.load(enumeration_path(out, "US")) == enumeration
    assert BuildCoverage.load(coverage_path(out, "US")) == coverage
    store = Store.open(out)
    try:
        assert [b.session for b in store.bars("US", "^IXIC")] == [date(2015, 6, 1)]
    finally:
        store.close()


def test_the_crawl_cli_runs_both_markets_into_one_store(tmp_path):
    """The runner's whole job in one command: both markets, one store, a coverage
    file committed per market. The network is injected, so this drives the real
    argument parsing and the real loop without a socket."""

    class _BothMarketsClient(_FetchClient):
        def enumerate(self, market):
            if market == "US":
                return [
                    Instrument(
                        market="US", symbol="AAA", role="candidate",
                        name="A - Common Stock",
                    )
                ]
            return [Instrument(market="IDX", symbol="BBCA", role="candidate", name="BBCA")]

    client = _BothMarketsClient(
        {"AAA": [_bar_row(date(2015, 6, 1))], "BBCA.JK": [_bar_row(date(2015, 6, 1))]}
    )
    out = tmp_path / "bt.duckdb"

    exit_code = crawl_main(
        ["--out", str(out)],
        source_factory=lambda: Source(client, backoff_base=0.0, sleep=lambda _s: None),
        now=_BUILD_NOW,
    )

    assert exit_code == 0
    assert BuildCoverage.load(coverage_path(out, "US")).stored == ("AAA",)
    assert BuildCoverage.load(coverage_path(out, "IDX")).stored == ("BBCA.JK",)


def test_the_crawl_cli_refuses_the_live_store_before_it_fetches_anything(capsys):
    """The guard runs before the first request, not after the crawl.

    `refuse_live_store` already refuses at the store boundary (#186), but by then
    a multi-hour US pull may have completed and be about to be written into live
    history. The runner checks the destination up front, so the refusal costs
    nothing and the mistake is caught while it is still cheap.

    It reports the way `screener.run` does — the reason on stderr and exit 2 —
    rather than as a traceback: this is the one surface an operator drives by
    hand, and a mis-aimed crawl should explain itself.
    """

    class _NeverAsked(_FetchClient):
        def enumerate(self, market):  # pragma: no cover - the guard fires first
            raise AssertionError("the crawl enumerated before checking its destination")

    exit_code = crawl_main(
        ["--out", str(live_store_path())],
        source_factory=lambda: Source(_NeverAsked({}), sleep=lambda _s: None),
        now=_BUILD_NOW,
    )

    assert exit_code == 2
    assert "refusing to build the backtest store into the live store" in capsys.readouterr().err


def test_the_crawl_cli_reports_a_bad_argument_as_an_exit_code(capsys):
    """Argparse's own exit is caught and returned as 2, matching `screener.run`,
    so the runner has one way of failing rather than two."""
    assert crawl_main(["--market", "MARS", "--out", "x"]) == 2


# -- the denominator: one market, a short window, rows on disk (issue #188) ---
#
# Phase 3 of PRD #182, and the first end-to-end path through the whole machine:
# the bar store, then the contract's stateless universe, then the chain, then the
# field, then persisted rows. Those rows are the denominator — the object the
# reference study has no counterpart for, and the input to every later metric.
#
# The fixtures below are authored against the *contract's* gates, not the app's:
# ADR20 ≥ 3.5% is the binding one, so the synthetic geometry carries wide daily
# ranges where the reference study's textbook base carries narrow ones.

from backtest.chain import (
    WindowNotCovered,
    burn_in_count,
    excluded_references,
    window_sessions,
)
from backtest.contract import DETECTION_GATE_KEY, WINDOW_STORE_START_KEY
from backtest.denominator import (
    BREADTH_BASIS,
    DETECTION_FIELDS,
    FOLLOW_THROUGH_BASIS,
    DenominatorStore,
    RegimeReading,
    RunStampMismatch,
    SessionRow,
    declared_columns,
    denominator_path,
)
from backtest.run import (
    ContractDrift,
    REGIME_TAIL,
    check_detection_gate,
    main as denominator_main,
    run_denominator,
    run_to_dict,
    session_regime,
)
from screener.detection import DETECTION_LOOKBACKS, DETECTOR_VERSION
from screener.regime import breadth, index_broke_out, regime_state
from screener.relative_strength import rs_line_hit, rs_line_value_for
from screener.score import DIMENSIONS
from screener.store import RANK_RETENTION_YEARS


def _wide_base_hlc():
    """A detectable base whose ADR clears the contract's 3.5% volatility gate.

    The reference study's ``_textbook_base_hlc`` cannot be reused here: its bars
    span 1% of price, so a name built from it fails the backtest universe's ADR20
    floor and never reaches the detector at all. Same shape — 60 quiet bars, a
    run-up 50→99, then a 30-bar top ending today — with the daily range widened to
    ~4% throughout.
    """
    hlc = [(51.0, 49.0, 50.0)] * 60
    for i in range(1, 16):
        p = 50.0 + (99.0 - 50.0) * i / 15
        hlc.append((p + 2.0, p - 2.0, p))
    hlc += [(102.0, 98.0, 100.0)] * 30
    return hlc


def _flat_index_hlc(n: int):
    """A benchmark series with no trend — the regime's input, held still so a test
    that is not about the regime does not accidentally depend on it."""
    return [(101.0, 99.0, 100.0)] * n


# The whole authored series: 105 sessions, which is what the geometry costs. The
# universe's SMA50 needs fifty bars and the detector eighty, so a shorter fixture
# would replay a window in which nothing can be a member and nothing can detect —
# it would pass every count assertion below by being empty.
FIXTURE_SESSIONS = 105


def _seed_denominator_store(store: Store, *, market: str = "US"):
    """One detectable name and its market index, over the whole fixture window."""
    dates = _daily(date(2020, 1, 1), FIXTURE_SESSIONS)
    store.append_bars(market, "BASE", _bars_from_hlc(dates, _wide_base_hlc()))
    store.append_bars(
        market,
        MARKET_INDEX[market],
        _bars_from_hlc(dates, _flat_index_hlc(FIXTURE_SESSIONS)),
    )
    return dates


@pytest.fixture
def denominator() -> DenominatorStore:
    d = DenominatorStore.memory()
    yield d
    d.close()


def _short_run(store: Store, denominator: DenominatorStore, dates: list[date], **kw):
    """The short window every test below replays: the last five sessions measured,
    everything before them burn-in."""
    return run_denominator(
        store, denominator, "US", DEFAULT_CONTRACT,
        start=dates[0], end=dates[-1], measured_start=dates[-5], **kw
    )


def test_one_market_and_a_short_window_replay_end_to_end(store, denominator):
    """The acceptance criterion, whole: store → universe → chain → field → rows.

    Every session in the window ends with a persisted header, its membership, its
    rank table and its field; the last session's detection arrives with its full
    record and its seven-dimension breakdown, not a summary of them."""
    dates = _seed_denominator_store(store)

    run = _short_run(store, denominator, dates)

    assert len(run.sessions) == len(dates)
    assert [r.session for r in run.sessions] == dates
    last = dates[-1]
    assert denominator.universe("US", last) == ["BASE"]
    assert {r.symbol for r in denominator.ranks("US", last)} == {"BASE"}
    (detection,) = denominator.detections("US", last)
    assert detection.symbol == "BASE"
    assert detection.star_rank == 1
    assert detection.score.label == SEVEN_DIM_LABEL
    assert detection.score.max_points == SEVEN_DIM_MAX_POINTS
    # The full record, not a digest of it: every field the detector emits.
    assert detection.detection == store.detections("US", last)[0]
    # And the breakdown that reconstructs the score arithmetically.
    assert [d.dimension for d in detection.score.breakdown] == [
        name for name, _ in DIMENSIONS if name != "Sector"
    ]
    assert sum(
        d.weight for d in detection.score.breakdown if d.hit
    ) == detection.score.points


def test_a_missing_interior_session_is_a_hard_error_not_a_silent_skip(store, denominator):
    """A gap fails loudly. A backtest that quietly skips a session reports on a
    market that took the day off, and the count that would have shown it is the
    same count a real data hole moves — so the two must never be confusable."""
    dates = _seed_denominator_store(store)
    gapped = dates[:10] + dates[11:]

    with pytest.raises(GapError):
        run_denominator(
            store, denominator, "US", DEFAULT_CONTRACT,
            sessions=gapped, measured_start=dates[-5],
        )


def test_burn_in_sessions_are_persisted_but_excluded_from_measurement(store, denominator):
    """Computed and persisted, never measured. The rows exist — a burn-in session
    is a fact about the window, not a hole in it — and the flag on each row is the
    whole of the exclusion rule, so no later phase has to be handed a separate
    list of which sessions to ignore."""
    dates = _seed_denominator_store(store)

    run = _short_run(store, denominator, dates)

    assert [r.session for r in run.measured] == dates[-5:]
    assert [r.session for r in run.burn_in] == dates[:-5]
    # Persisted, both of them, and distinguishable in the store itself.
    assert denominator.sessions("US", burn_in=False) == list(run.measured)
    assert denominator.sessions("US", burn_in=True) == list(run.burn_in)
    assert len(denominator.sessions("US")) == len(dates)
    # A burn-in session carries real rows, not placeholders.
    assert denominator.universe("US", dates[-6]) == ["BASE"]


def test_the_burn_in_is_the_window_before_the_measured_start():
    """The backtest's burn-in is a *date*, not a session count. The contract names
    a store start and a measured start, and the sessions between them are the
    warm-up — a count would have to be re-derived every time the window moved."""
    dates = _daily(date(2020, 1, 1), 10)

    assert burn_in_count(dates, dates[4]) == 4
    assert burn_in_count(dates, dates[0]) == 0
    assert burn_in_count(dates, dates[-1]) == len(dates) - 1


def test_follow_through_is_reconstructed_across_the_window_and_marked_unbiased(
    store, denominator
):
    """The one regime signal the live app can never backfill. It captures
    follow-through forward nightly precisely because a survivorship-biased past
    cannot rebuild it — but the index series has no survivorship hole, so here it
    is reconstructed legitimately, and the row says so."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _wide_base_hlc()))
    # An index that closes to a new trailing-window high on the last session only.
    index = [(101.0, 99.0, 100.0)] * 104 + [(121.0, 119.0, 120.0)]
    store.append_bars("US", MARKET_INDEX["US"], _bars_from_hlc(dates, index))

    run = _short_run(store, denominator, dates)

    rows = {r.session: r for r in run.sessions}
    assert rows[dates[-1]].broke_out is True
    assert rows[dates[-2]].broke_out is False
    assert rows[dates[-1]].index_close == 120.0
    assert all(r.follow_through_basis == FOLLOW_THROUGH_BASIS for r in run.sessions)
    assert "unbiased" in FOLLOW_THROUGH_BASIS


def test_breadth_is_persisted_as_descriptive_only_and_carries_its_warning(
    store, denominator
):
    """Breadth is the measure survivorship bias corrupts most directly, and worse
    in a reconstructed past than live, because the missing names are
    disproportionately the ones that later died. It is stored, and the warning is
    stored *with it* — a column whose quality lives only in a docstring is read as
    equal to the one beside it the first time someone queries the file."""
    dates = _seed_denominator_store(store)

    run = _short_run(store, denominator, dates)

    assert all(r.breadth_basis == BREADTH_BASIS for r in run.sessions)
    assert "survivorship" in BREADTH_BASIS
    assert BREADTH_BASIS != FOLLOW_THROUGH_BASIS
    # Descriptive: it is recorded, and nothing was excluded on it.
    assert all(r.breadth is not None for r in run.measured)


def test_the_regime_state_is_the_apps_own_read_off_the_market_index(store, denominator):
    """The conditioning variable is the app's regime, unmodified, off the market's
    own index — so a finding here is actionable in the product rather than being
    about a parallel definition that ships nowhere."""
    dates = _seed_denominator_store(store)

    run = _short_run(store, denominator, dates)

    index_bars = store.bars("US", MARKET_INDEX["US"])
    for row in run.measured:
        expected = regime_state([b for b in index_bars if b.session <= row.session])
        assert row.regime_state == expected


def test_a_persisted_candidate_dimension_keeps_absence_distinct_from_zero(denominator):
    """``None`` is *absent* — the name had not listed six months ago, or has no
    ADR — and ``0.0`` is a real value sitting exactly on the pre-registered cut.
    A store folding the two together would make a name with no history
    indistinguishable from one that exactly matched the market, which is the whole
    reason the dimension rides as a value rather than a boolean."""
    det = _det("AAA", cluster_k=6)
    absent = ScoredDetection(
        symbol="AAA", detection=det,
        score=seven_dimension_score(det, prior_move=False),
        star_rank=1, not_taken=False, rs_line=False, relative_move=None,
    )
    on_the_cut = dataclasses.replace(
        absent, symbol="BBB",
        detection=dataclasses.replace(det, symbol="BBB"),
        star_rank=2, relative_move=0.0,
    )
    session = det.session

    denominator.append_detections("US", session, [absent, on_the_cut])

    stored = {d.symbol: d.relative_move for d in denominator.detections("US", session)}
    assert stored["AAA"] is None
    assert stored["BBB"] == 0.0
    # The cut belongs to the rubric and is applied at read time, never to the row.
    assert relative_move_hit(stored["BBB"]) is False
    assert relative_move_hit(stored["AAA"]) is False


def test_neither_candidate_dimension_moves_a_star_or_a_star_rank(store, denominator):
    """The two registered candidates ride *beside* the score. A field scored with
    them and one scored without must agree on every star and every rank, or a
    dimension still under measurement would already be deciding board order."""
    dates = _seed_denominator_store(store)
    run = _short_run(store, denominator, dates)
    stored = denominator.detections("US", dates[-1])

    without = build_field(
        store.detections("US", dates[-1]), denominator.ranks("US", dates[-1])
    )

    assert [d.symbol for d in stored] == [d.symbol for d in without]
    assert [d.star_rank for d in stored] == [d.star_rank for d in without]
    assert [d.score.stars for d in stored] == [d.score.stars for d in without]
    assert run.measured[-1].detections == len(stored)


def test_the_benchmark_references_never_enter_the_ranked_field(store, denominator):
    """This is a fresh build, so it inherits the #162 fix rather than reproducing
    the contamination the shipped replay store was deliberately left with. All
    five references clear every liquidity, trend and volatility gate the universe
    applies — nothing downstream would have kept them out."""
    dates = _seed_denominator_store(store)
    for symbol in REPLAY_REFERENCES:
        store.append_bars(
            "US", symbol, _bars_from_hlc(dates, _wide_base_hlc(), volume=5_000_000)
        )

    run = _short_run(store, denominator, dates)

    for session in dates[-5:]:
        assert not (REPLAY_REFERENCES & set(denominator.universe("US", session)))
        assert not (
            REPLAY_REFERENCES & {r.symbol for r in denominator.ranks("US", session)}
        )
        assert not (
            REPLAY_REFERENCES
            & {d.symbol for d in denominator.detections("US", session)}
        )
    assert set(run.references_excluded) == REPLAY_REFERENCES


def test_the_reference_exclusion_is_pinned_against_the_stores_own_enumeration(store):
    """The exclusion is a blocklist and a blocklist rots in silence: an ETF ticker
    carries no mark separating it from common stock, so a benchmark fetched later
    would be ranked exactly as these once were. Pinning it against what the store
    actually holds turns that rot into a failing test."""
    dates = _seed_denominator_store(store)
    for symbol in REPLAY_REFERENCES:
        store.append_bars("US", symbol, _bars_from_hlc(dates, _wide_base_hlc()))

    held = excluded_references(store, "US")

    assert set(held) == REPLAY_REFERENCES
    assert len(REPLAY_REFERENCES) == 5
    # Every one of them is in the store's enumeration — so the assertion above is
    # about names the run really had to refuse, not an empty intersection.
    assert REPLAY_REFERENCES <= set(store.symbols("US"))
    assert "BASE" not in held


def test_the_detection_gate_is_the_four_lookback_width_at_detector_v3(store, denominator):
    """The denominator is built against the width ADR 0003's amendment settled —
    ``1m``/``3m``/``6m``/``12m``, detector v3 — and the contract cell and the live
    constant cannot drift apart without this failing."""
    assert tuple(DEFAULT_CONTRACT.value(DETECTION_GATE_KEY)) == DETECTION_LOOKBACKS
    assert DETECTOR_VERSION == 3

    dates = _seed_denominator_store(store)
    _short_run(store, denominator, dates)

    (detection,) = denominator.detections("US", dates[-1])
    assert detection.detection.detector_version == DETECTOR_VERSION


def test_the_run_is_deterministic_and_reuses_a_persisted_session(
    store, denominator, monkeypatch
):
    """Re-runnable, not single-use. A second pass over the same store reads back
    the session it already computed rather than recomputing it — so the classifier
    is never called again — and the rows it reports are identical."""
    dates = _seed_denominator_store(store)
    first = run_denominator(
        store, denominator, "US", DEFAULT_CONTRACT,
        start=dates[0], end=dates[-1], measured_start=dates[-5],
    )

    def refuse(*args, **kwargs):
        raise AssertionError("a persisted session was reclassified, not reused")

    monkeypatch.setattr("backtest.chain.classify", refuse)
    second = run_denominator(
        store, denominator, "US", DEFAULT_CONTRACT,
        start=dates[0], end=dates[-1], measured_start=dates[-5],
    )

    assert second.sessions == first.sessions
    # And no row was duplicated by the second pass.
    assert len(denominator.sessions("US")) == len(dates)
    assert denominator.universe("US", dates[-1]) == ["BASE"]


def test_the_denominator_universe_is_the_contracts_stateless_one(store, denominator):
    """The gate that is swapped, and the only one. A name whose ADR sits under the
    contract's 3.5% floor never enters the denominator, even though the app's own
    universe — which has no volatility gate at all — admits it."""
    dates = _daily(date(2020, 1, 1), 105)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _wide_base_hlc()))
    # Same liquidity, same rising trend, a tenth of the volatility.
    narrow = [(50.1, 49.9, 50.0)] * 60
    narrow += [
        (50.0 + 4.9 * i / 15 + 0.05, 50.0 + 4.9 * i / 15 - 0.05, 50.0 + 4.9 * i / 15)
        for i in range(1, 16)
    ]
    narrow += [(55.05, 54.95, 55.0)] * 30
    store.append_bars("US", "NARROW", _bars_from_hlc(dates, narrow, volume=2_000_000))
    store.append_bars(
        "US", MARKET_INDEX["US"], _bars_from_hlc(dates, _flat_index_hlc(105))
    )

    _short_run(store, denominator, dates)

    members = denominator.universe("US", dates[-1])
    assert "BASE" in members
    assert "NARROW" not in members
    # The app's classifier is untouched: it still has no volatility gate at all,
    # so over the same bars it keeps the name the contract's classifier refused.
    # Replayed into a store of its own, because the derived rows are written once
    # and the run above has already claimed this store's sessions.
    app_store = Store.memory()
    try:
        for symbol in store.symbols("US"):
            app_store.append_bars("US", symbol, store.bars("US", symbol))
        assert "NARROW" in replay_chain(app_store, "US", burn_in=104)[-1].members
    finally:
        app_store.close()


def test_the_denominator_ranks_outlive_the_app_stores_retention_window(store, denominator):
    """The reason the rows live in a store of their own. ``append_ranks`` prunes
    everything outside the app's two-year retention window as the chain advances —
    correct for a store that only ever needs tonight's table, and fatal for a
    fourteen-year denominator, which would finish holding the last two years of
    ranks and nothing else."""
    old = date(2018, 6, 1)
    new = old.replace(year=old.year + RANK_RETENTION_YEARS + 1)
    rows = [Rank(symbol="AAA", lookback="1m", percentile=0.9, raw_return=0.1)]

    store.append_ranks("US", old, rows)
    store.append_ranks("US", new, rows)
    denominator.append_ranks("US", old, rows)
    denominator.append_ranks("US", new, rows)

    assert store.ranks("US", old) == []          # pruned by the app's retention
    assert denominator.ranks("US", old) == rows  # kept — this is the denominator
    assert denominator.ranks("US", new) == rows


def test_the_persisted_detection_record_cannot_fall_behind_the_detector():
    """The record is written by name off the dataclass, so a field added to
    ``Detection`` and not to the denominator's schema fails here rather than being
    dropped on the floor — which is how a column goes missing from a fourteen-year
    build and is noticed a year later. Read through the schema's own declaration,
    the way ``screener.store`` reads its own, so there is one description of the
    shape and nothing to drift from it."""
    declared = declared_columns()["denominator_detections"]

    assert set(DETECTION_FIELDS) <= set(declared)
    assert set(DETECTION_FIELDS) == {
        f.name for f in dataclasses.fields(Detection)
    } - {"symbol", "session"}
    # Both candidate dimensions are nullable, because NULL is how each says absent.
    assert declared["rs_line"] == "BOOLEAN"
    assert declared["relative_move"] == "DOUBLE"


def test_the_run_result_carries_the_contract_that_produced_it(store, denominator):
    """Every result the package emits carries its contract, so two runs under
    different contracts are distinguishable from their serialised output alone."""
    dates = _seed_denominator_store(store)
    run = _short_run(store, denominator, dates)

    payload = run_to_dict(run)

    assert payload[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    assert payload["market"] == "US"
    assert payload["sessions_measured"] == 5
    assert payload["sessions_burn_in"] == len(dates) - 5
    round_tripped = json.loads(json.dumps(payload))
    assert round_tripped["sessions"][0]["breadth_basis"] == BREADTH_BASIS
    assert round_tripped["sessions"][0]["follow_through_basis"] == FOLLOW_THROUGH_BASIS


def test_detections_per_session_is_plottable_across_the_window(store, denominator):
    """A count that collapses in a given year is a data hole, and it reads as a
    quiet market until someone looks — so the count is a reported series, not
    something a later reader has to re-derive from the rows."""
    dates = _seed_denominator_store(store)
    run = _short_run(store, denominator, dates)

    counts = run.detections_per_session

    assert list(counts) == dates[-5:]
    assert counts[dates[-1]] == 1


def test_the_window_defaults_to_the_contracts_store_start(store):
    """The window is the contract's unless a caller narrows it, so a short run and
    the full one differ in their arguments rather than in their code path."""
    dates = _seed_denominator_store(store)
    contract_start = date.fromisoformat(DEFAULT_CONTRACT.value(WINDOW_STORE_START_KEY))

    assert contract_start == date(2011, 1, 1)
    assert window_sessions(store, "US", start=contract_start) == dates
    assert window_sessions(store, "US", start=dates[5], end=dates[9]) == dates[5:10]


def test_the_denominator_is_written_beside_the_bar_store(tmp_path):
    """Derived from the store's path rather than passed separately, for the reason
    the coverage ledger is: a denominator written beside the wrong bar store is a
    set of rows nothing can be reconciled against."""
    assert denominator_path(tmp_path / "backtest_us.duckdb") == (
        tmp_path / "backtest_us.duckdb.denominator.duckdb"
    )


def test_the_denominator_cli_persists_and_reports_the_run(tmp_path, capsys):
    """The one documented command that reproduces a run: it writes the denominator
    beside the bar store, writes the machine-readable summary where it was asked
    to, and prints what it persisted — so a run is reproducible from the shell
    rather than only from a test."""
    store_path = tmp_path / "backtest_us.duckdb"
    bar_store = Store.open(store_path)
    dates = _seed_denominator_store(bar_store)
    bar_store.close()
    out_json = tmp_path / "denominator.json"

    exit_code = denominator_main([
        "--store", str(store_path),
        "--market", "US",
        "--start", dates[0].isoformat(),
        "--measured-start", dates[-5].isoformat(),
        "--end", dates[-1].isoformat(),
        "--out-json", str(out_json),
    ])

    assert exit_code == 0
    assert denominator_path(store_path).exists()
    payload = json.loads(out_json.read_text())
    assert payload[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    assert payload["sessions_measured"] == 5
    printed = capsys.readouterr().out
    assert "5 measured" in printed
    assert BREADTH_BASIS in printed
    assert FOLLOW_THROUGH_BASIS in printed


# -- what the #188 review found unguarded -------------------------------------


def _contract_with(key: str, value) -> RunContract:
    """``DEFAULT_CONTRACT`` with one cell's value replaced, justification kept."""
    return dataclasses.replace(
        DEFAULT_CONTRACT,
        cells=tuple(
            dataclasses.replace(c, value=value) if c.key == key else c
            for c in DEFAULT_CONTRACT.cells
        ),
    )


def test_a_window_the_store_cannot_reach_across_is_refused(store, denominator):
    """The gap the chain's own check can never catch. `window_sessions` slices the
    store's calendar, so a window built from it is gapless by construction — which
    leaves the gap that actually happens in a fetched store unguarded: the crawl
    stopped short, and the window quietly became whatever the bars covered. Every
    count below it would then be computed correctly over the wrong window."""
    dates = _seed_denominator_store(store)

    with pytest.raises(WindowNotCovered):
        run_denominator(
            store, denominator, "US", DEFAULT_CONTRACT,
            start=dates[0] - timedelta(days=1), end=dates[-1],
            measured_start=dates[-5],
        )
    with pytest.raises(WindowNotCovered):
        run_denominator(
            store, denominator, "US", DEFAULT_CONTRACT,
            start=dates[0], end=dates[-1] + timedelta(days=1),
            measured_start=dates[-5],
        )


def test_a_re_run_under_a_different_contract_is_refused(store, denominator):
    """Idempotent writes make a re-run safe and, on their own, make it dishonest:
    a second pass under a changed contract would keep every stale row and still
    report a clean run. A contract change is a new run recorded beside the old
    one, so the file's stamp refuses it rather than mixing the two."""
    dates = _seed_denominator_store(store)
    _short_run(store, denominator, dates)

    changed = dataclasses.replace(DEFAULT_CONTRACT, label="a second run")

    with pytest.raises(RunStampMismatch):
        run_denominator(
            store, denominator, "US", changed,
            start=dates[0], end=dates[-1], measured_start=dates[-5],
        )
    # The same contract is still welcome — that is the re-run the store supports.
    again = _short_run(store, denominator, dates)
    assert len(again.sessions) == len(dates)


def test_a_gate_width_that_drifted_from_its_contract_stops_the_run():
    """The run measures the detector as encoded, and the contract records what
    that was. Unchecked, the two agreeing is a coincidence a test noticed once:
    the run would go on building a denominator against whatever width the detector
    happened to carry, and stamp the contract's claim onto the result."""
    check_detection_gate(DEFAULT_CONTRACT)  # today they agree

    drifted = _contract_with(DETECTION_GATE_KEY, ["1m", "3m", "6m"])

    with pytest.raises(ContractDrift):
        check_detection_gate(drifted)


def test_the_bounded_regime_tail_reads_the_same_as_the_whole_series(store):
    """The regime is read off a trailing slice rather than every bar ever stored,
    because re-slicing each member's full history once per session is
    O(sessions x members x bars) and does not finish the fourteen-year pass this
    package exists to run. The saving is only legitimate if the answer is
    identical, so it is pinned against the whole series here."""
    dates = _seed_denominator_store(store)
    session = dates[-1]
    members = ["BASE"]

    reading = session_regime(store, "US", session, members)

    whole_index = [b for b in store.bars("US", MARKET_INDEX["US"]) if b.session <= session]
    whole_members = {
        s: [b for b in store.bars("US", s) if b.session <= session] for s in members
    }
    assert reading.state == regime_state(whole_index)
    assert reading.breadth == breadth(whole_members)
    assert reading.broke_out == index_broke_out(whole_index)
    assert reading.index_close == whole_index[-1].adj_close
    # And the slice really is bounded, or the assertions above prove nothing.
    assert REGIME_TAIL < len(whole_index)


def test_an_absent_rs_line_is_none_and_never_a_miss(denominator):
    """The candidate rides as a value, like its sibling. A benchmark with no bar
    at one of the two anchors means the question was never asked — a different
    fact from asking it and getting no — and a stored row that folded them could
    not tell a name whose index had no bars from one that genuinely decayed."""
    det = _det("AAA", cluster_k=6)
    bars = _bars_from_hlc(_daily(date(2019, 1, 1), 105 * 4), _wide_base_hlc() * 4)

    # No benchmark bars at all: absent, not a decayed line.
    assert rs_line_value_for(det, bars, []) is None
    # The pre-registered boolean still reads absence as a miss, as #160 published.
    assert rs_line_hit(None) is False

    absent = ScoredDetection(
        symbol="AAA", detection=det,
        score=seven_dimension_score(det, prior_move=False),
        star_rank=1, not_taken=False, rs_line=None, relative_move=None,
    )
    decayed = dataclasses.replace(
        absent, symbol="BBB",
        detection=dataclasses.replace(det, symbol="BBB"),
        star_rank=2, rs_line=False,
    )

    denominator.append_detections("US", det.session, [absent, decayed])

    stored = {d.symbol: d.rs_line for d in denominator.detections("US", det.session)}
    assert stored["AAA"] is None
    assert stored["BBB"] is False


def test_the_detections_per_session_series_is_serialised(store, denominator):
    """The count rides on the machine-readable result as a dated series, so a year
    where it collapses is visible without re-deriving it from the rows."""
    dates = _seed_denominator_store(store)
    run = _short_run(store, denominator, dates)

    series = run_to_dict(run)["detections_per_session"]

    assert list(series) == [d.isoformat() for d in dates[-5:]]
    assert set(series.values()) == {1}


# -- arm B, end to end, and the proof there is no look-ahead (issue #189) ------
#
# Phase 4 of PRD #182. The denominator says which setups the detector named; this
# turns each of them into a trade and denominates the result in R.
#
# One entry and one stop are shared by every arm — #190 adds A and C onto exactly
# these — so a difference between arms is attributable to the exit alone. Arm B is
# the pure 10MA trail, and the arm the pre-registered primary metric is computed
# on.
#
# The load-bearing test in this block is
# ``test_shifting_a_future_bar_into_an_entry_decision_changes_nothing``. Every
# other test here asserts that the simulator computes what the contract says; that
# one asserts it cannot see what it must not see. A look-ahead bug produces a
# beautiful equity curve and no error message, so it is the only bug in this phase
# that no amount of reading the output would catch.

from screener.indicators import ADR_WINDOW, adr, sma

from backtest.chain import trailing_bars
from backtest.contract import EXIT_ARM_B_KEY, EXIT_TRAIL_MECHANIC_KEY
from backtest.simulate import (
    ARM_B,
    EXIT_STOP,
    EXIT_TRAIL,
    PRICE_SCALE_MAX,
    PRICE_SCALE_MIN,
    TRAIL_MECHANIC,
    Decision,
    SimulatedTrade,
    check_trail_mechanic,
    price_scale_drops,
    simulate_arm,
    simulate_market,
    format_trades,
    simulate_report,
    trail_ma,
    exit_plan,
)


def simulate_arm_b(bars, detection, *, market, contract):
    """Arm B by name, which is how every test below this line asks for it.

    #190 made the arm a parameter of :func:`simulate_arm` — the arms share one
    entry and one stop, and only the exit differs — so this is what "arm B" now
    spells. Kept as a test-local shim rather than a second production entry point:
    two names for one function in the module itself is exactly the drift the arms
    were unified to remove.
    """
    return simulate_arm(bars, detection, market=market, contract=contract, arm=ARM_B)


def _sim_bar(session: date, o: float, h: float, l: float, c: float) -> Bar:
    """One authored bar. ``adj_close`` is deliberately set *away* from ``close``:
    the trail and the trigger live in the unadjusted series, so a simulator that
    reached for ``adj_close`` would produce visibly different numbers here rather
    than agreeing by coincidence on a fixture where the two were equal."""
    return Bar(
        session=session, open=o, high=h, low=l, close=c,
        adj_close=c * 0.5, volume=1_000_000,
    )


def _flat_then(dates: list[date], closes: list[float]) -> list[Bar]:
    """Bars whose every OHLC is driven by one close per session.

    ``high``/``low`` straddle the close by 2%, which gives the 20-bar ADR a value
    to be measured in without letting the intraday range reach a stop the closes
    never approach — so a test that is about the trail is never quietly decided by
    the stop.
    """
    return [
        _sim_bar(d, c, c * 1.02, c * 0.98, c)
        for d, c in zip(dates, closes)
    ]


# The authored trade every arm-B test below runs on.
#
# 40 bars flat at 100 give the ADR and the 10MA a settled history. The detection is
# named on the last of them with a trigger of 102. The next session closes at 110 —
# through the trigger, so it breaks — and the one after opens at 111, which is the
# fill. Price then runs to 130 and rolls over, closing back under its own 10MA on a
# session the test can name.
SIM_TRIGGER = 102.0
SIM_STOP_WIDTH = 6.0          # stop price 96.0, six under the trigger
_SIM_FLAT = [100.0] * 40
_SIM_RUN = [110.0, 111.0, 118.0, 124.0, 130.0, 129.0, 128.0, 127.0]
# Then a slide that drags the close under the rising 10MA.
_SIM_FADE = [120.0, 112.0, 104.0, 100.0, 98.0, 97.0, 96.5, 96.2]


def _sim_dates(n: int) -> list[date]:
    return _daily(date(2021, 3, 1), n)


def _sim_closes() -> list[float]:
    return _SIM_FLAT + _SIM_RUN + _SIM_FADE


def _sim_bars(closes: list[float] | None = None) -> list[Bar]:
    closes = closes or _sim_closes()
    return _flat_then(_sim_dates(len(closes)), closes)


def _sim_detection(bars: list[Bar], *, close: float | None = None) -> Detection:
    """The detection the simulator is handed: named on bar 39, trigger 102, stop 96.

    Hand-authored rather than detected, so every figure asserted below is arithmetic
    a reader can check. ``stopw_adr`` is **derived** rather than chosen, because the
    detector's own stop is ``stopw_adr × adr × trigger``: picking the width and the
    ADR-normalised width independently would author a detection no detector could
    emit, and a fixture that cannot exist proves nothing about code that reads real
    ones. ``close`` is the detection's *recorded* close, which is what the
    price-scale flag compares against the bar.
    """
    a = adr(trailing_bars(bars, bars[39].session, ADR_WINDOW))
    return dataclasses.replace(
        _det("BASE", 5),
        session=bars[39].session,
        trigger=SIM_TRIGGER,
        stop=SIM_STOP_WIDTH,
        stopw_adr=SIM_STOP_WIDTH / (a * SIM_TRIGGER),
        adr=a,
        close=bars[39].close if close is None else close,
        cluster_high=SIM_TRIGGER,
    )


def test_a_persisted_detection_becomes_a_trade_on_its_own_trigger_and_stop(store):
    """The acceptance criterion, whole: trigger, fill, stop and 10MA trail.

    The detection names a trigger of 102 on bar 39. Bar 40 closes at 110 — through
    it — which is the break, and the fill is bar 41's open at 111. The stop is the
    detection's own, unmodified: ``trigger − stop`` = 96. The trail then signals on
    the first close under the 10MA and fills at the next open.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)

    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    assert trade is not None
    assert trade.arm == ARM_B
    assert trade.symbol == "BASE"
    assert trade.trigger.price == SIM_TRIGGER
    # The break is a close through the trigger, and the fill is the next open —
    # the same signal-then-fill shape the trail uses, one session apart.
    assert trade.break_signal.session == bars[40].session
    assert trade.break_signal.price == 110.0
    assert trade.entry.session == bars[41].session
    assert trade.entry.price == bars[41].open == 111.0
    # The detection's own stop, used unmodified: trigger less the stop budget.
    assert trade.stop_price.price == det.stop_price == 96.0
    assert trade.exit_reason == EXIT_TRAIL


def test_the_trail_signals_on_a_close_through_the_ma_and_fills_at_the_next_open(store):
    """The contract's trail mechanic, asserted against the fixture's own arithmetic.

    The exit session is not asserted as a constant: it is recomputed here from the
    same closes the fixture authors, so a test that agreed with the simulator by
    copying its answer would disagree the moment either side moved.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)

    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    window = exit_plan(DEFAULT_CONTRACT, ARM_B).trail_ma
    assert window == 10
    signal = next(
        i for i in range(41, len(bars))
        if (ma := trail_ma(bars[: i + 1], window)) is not None and bars[i].close < ma
    )
    assert trade.exit is not None
    assert trade.exit.session == bars[signal + 1].session
    assert trade.exit.price == bars[signal + 1].open
    # The signal session is carried too, so the decision and its fill are separable.
    assert trade.exit_signal.session == bars[signal].session


def test_the_trail_reads_the_unadjusted_close_the_trigger_lives_in(store):
    """The 10MA trails the same series the trigger and the stop are quoted in.

    ``screener.indicators.sma`` averages **adjusted** closes, because returns need
    a dividend-continuous series. A trail compared against a trigger must not: the
    fixture's ``adj_close`` is half its ``close``, so a trail built on the adjusted
    series would sit permanently under every close and never signal at all.
    """
    bars = _sim_bars()

    assert trail_ma(bars[:41], 10) == sum(b.close for b in bars[31:41]) / 10
    assert trail_ma(bars[:41], 10) != sma(bars[:41], 10)
    # And it is undefined rather than approximated before the window is full.
    assert trail_ma(bars[:9], 10) is None


def test_the_stop_is_the_detections_own_and_takes_precedence_within_a_session(store):
    """A session that trades through the stop exits there, whatever its close does.

    The stop is intraday and the trail is a closing decision, so a bar that touches
    the stop and then closes back above the MA is a stopped-out trade, not a held
    one. Deciding it the other way would let a losing trade be rescued by the very
    bar that ended it.
    """
    closes = _SIM_FLAT + [110.0, 111.0]
    bars = _sim_bars(closes)
    # A session that dips to 95 — under the 96 stop — and recovers to close at 111.
    bars.append(_sim_bar(_sim_dates(len(closes) + 1)[-1], 111.0, 112.0, 95.0, 111.0))
    det = _sim_detection(bars)

    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    assert trade.exit_reason == EXIT_STOP
    assert trade.exit.session == bars[42].session
    assert trade.exit.price == det.stop_price == 96.0


def test_a_session_that_gaps_under_the_stop_fills_at_the_open_not_the_stop(store):
    """A stop is an order, not a guarantee. A market that opens under it fills there.

    Filling at the stop price would credit the simulation with liquidity that did
    not exist, and it would do so precisely on the worst trades — the ones a gap
    ran away from — which is the direction that flatters an equity curve.
    """
    closes = _SIM_FLAT + [110.0, 111.0]
    bars = _sim_bars(closes)
    bars.append(_sim_bar(_sim_dates(len(closes) + 1)[-1], 90.0, 91.0, 88.0, 89.0))
    det = _sim_detection(bars)

    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    assert trade.exit_reason == EXIT_STOP
    assert trade.exit.price == 90.0 < det.stop_price


def test_a_detection_whose_next_session_does_not_break_produces_no_trade(store):
    """No break, no trade — and that is a measurement, not a dropped row.

    The share of detections that trigger is one of the denominator figures the
    whole exercise exists to produce (PRD Phase 5). Entering a setup that never
    traded through its own trigger would put that figure at 100% by construction.
    """
    bars = _sim_bars(_SIM_FLAT + [101.0, 105.0, 110.0])
    det = _sim_detection(bars)

    assert simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT) is None


def test_r_is_denominated_off_the_detections_own_stop_in_adr_units(store):
    """R's denominator is the detection's stop width in ADR, priced off the bars.

    ``stopw_adr`` is the detection's own stop expressed in the unit the whole
    system is denominated in, and ADR is measured on the bars at the session that
    decided the trade. Both terms of the ratio therefore live in the *bar* series,
    so an unlabelled retroactive rescale moves them together and R is unchanged —
    which is what "keep the geometry in ADR units" buys (story 83).
    """
    bars = _sim_bars()
    det = _sim_detection(bars)

    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    # The invariant, not the formula: the width R is denominated by IS the
    # detection's own stop. Restating the implementation's arithmetic here would
    # agree with any drift in it, including a systematically wrong one.
    assert trade.stop_width == pytest.approx(det.stop)
    assert trade.stop_price.price == pytest.approx(det.trigger - trade.stop_width)
    assert trade.r_multiple == pytest.approx(
        (trade.exit.price - trade.entry.price) / det.stop
    )
    # And it is rebuilt from the *bars* rather than read off the row, so it stays in
    # ADR units: same number here, and an unrescaled one when the two scales differ.
    at_decision = trailing_bars(bars, det.session, ADR_WINDOW)
    assert trade.stop_width == pytest.approx(
        det.stopw_adr * adr(at_decision) * det.trigger
    )


def test_r_is_unchanged_when_the_whole_bar_series_is_rescaled(store):
    """The rescale immunity the ADR denominator exists for, asserted directly.

    Yahoo's rights-issue rescale multiplies a symbol's whole history by a constant
    and says nothing. Under that transform every price in the trade moves and R
    does not — because numerator and denominator are both prices from the same
    series. This is the reason the denominator is not a stored absolute figure.
    """
    scale = 10 / 11
    bars = _sim_bars()
    det = _sim_detection(bars)
    rescaled = [
        _sim_bar(b.session, b.open * scale, b.high * scale, b.low * scale, b.close * scale)
        for b in bars
    ]
    rescaled_det = dataclasses.replace(
        det,
        trigger=det.trigger * scale,
        stop=det.stop * scale,
        close=det.close * scale,
    )

    plain = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)
    shifted = simulate_arm_b(
        rescaled, rescaled_det, market="US", contract=DEFAULT_CONTRACT
    )

    assert shifted.r_multiple == pytest.approx(plain.r_multiple)
    assert shifted.exit.session == plain.exit.session


def test_every_decision_carries_the_session_it_was_made_on(store):
    """The audit trail (acceptance criterion): five decisions, five sessions.

    A trade whose prices cannot be traced back to the sessions that produced them
    cannot be reconciled against the bars, which makes every figure derived from it
    unfalsifiable. The stop is stamped with the *detection's* session, because that
    is when it was decided — not when it was hit.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)

    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    assert trade.detection_session == det.session
    assert trade.trigger.session == det.session
    assert trade.stop_price.session == det.session
    assert trade.break_signal.session == bars[40].session
    assert trade.entry.session == bars[41].session
    assert trade.exit.session > trade.entry.session
    for decision in (
        trade.trigger, trade.stop_price, trade.break_signal, trade.entry, trade.exit,
    ):
        assert isinstance(decision, Decision)
        assert isinstance(decision.session, date)


def test_shifting_a_future_bar_into_an_entry_decision_changes_nothing(store):
    """**The most important test in the run** (acceptance criterion, story 80/81).

    A look-ahead bug produces a beautiful equity curve and no error message, so the
    point-in-time claim is proved rather than cared about. Every bar after the fill
    is replaced with an absurd one — a 10× spike — and the entry decision is
    asserted identical. Anything that reached forward from the break or the fill
    would move here and nowhere else.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)
    plain = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    tampered = list(bars)
    for i in range(42, len(tampered)):
        b = tampered[i]
        tampered[i] = _sim_bar(
            b.session, b.open * 10, b.high * 10, b.low * 10, b.close * 10
        )
    shifted = simulate_arm_b(tampered, det, market="US", contract=DEFAULT_CONTRACT)

    assert shifted.break_signal == plain.break_signal
    assert shifted.entry == plain.entry
    assert shifted.stop_price == plain.stop_price
    assert shifted.trigger == plain.trigger
    # The risk is measured at the decision session too, so it cannot move either.
    assert shifted.stop_width == pytest.approx(plain.stop_width)


def test_tampering_with_bars_after_the_exit_never_moves_the_exit(store):
    """The same guard carried all the way to the trail, not stopped at the entry.

    Story 79 covers "trigger, fill, stop, **trail**" — every price derived from bars
    at or before the session that decides it. The entry-side tamper above would pass
    unchanged if the trail read one bar into the future, because it asserts nothing
    about the exit. So this one tampers past the *exit* and requires the exit, its
    signal and the resulting R to be identical.

    Its companion is
    ``test_the_trail_signals_on_a_close_through_the_ma_and_fills_at_the_next_open``,
    which recomputes the signal session independently from ``bars[: i + 1]``: between
    them, a trail that looked forward would have to move the signal without moving
    the first session at which a point-in-time MA is broken.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)
    plain = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)
    assert plain.exit is not None

    exit_at = next(i for i, b in enumerate(bars) if b.session == plain.exit.session)
    tampered = list(bars)
    for i in range(exit_at + 1, len(tampered)):
        b = tampered[i]
        tampered[i] = _sim_bar(
            b.session, b.open / 10, b.high / 10, b.low / 10, b.close / 10
        )
    shifted = simulate_arm_b(tampered, det, market="US", contract=DEFAULT_CONTRACT)

    assert shifted.exit_signal == plain.exit_signal
    assert shifted.exit == plain.exit
    assert shifted.exit_reason == plain.exit_reason
    assert shifted.r_multiple == pytest.approx(plain.r_multiple)


def test_appending_later_sessions_never_moves_a_settled_trade(store):
    """The same guard from the other side: a longer store, an identical trade.

    Re-running the simulation months later reads a store that has grown. If any
    decision were taken over the whole series rather than the part of it that
    existed at the time, a settled trade would silently re-price — and the run
    would stop being reproducible without ever failing.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)
    plain = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    longer = _sim_bars(_sim_closes() + [200.0] * 30)
    grown = simulate_arm_b(longer, det, market="US", contract=DEFAULT_CONTRACT)

    assert grown == plain


def test_a_trade_still_open_at_the_end_of_the_store_carries_no_r(store):
    """A trade the bars run out under is open, and an open trade has no result.

    Marking it closed at the last close would invent an exit the rules never gave
    and would do it for every name still running at the end of the window — a
    systematic bias toward whatever the last session happened to be.
    """
    bars = _sim_bars(_SIM_FLAT + _SIM_RUN)
    det = _sim_detection(bars)

    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    assert trade.open_at_end
    assert trade.exit is None
    assert trade.exit_reason is None
    assert trade.r_multiple is None


def test_the_price_scale_flag_rides_on_the_trade_and_its_drops_are_counted(store):
    """The one absolute-price comparison the ADR geometry cannot make immune.

    The trigger is imported from a detection persisted earlier; the bars are read
    now. A rescale between the two leaves the two on different scales, and the
    trigger-versus-close comparison that decides the break is then meaningless. It
    is flagged rather than dropped — the prototype this borrows from does the same
    — and the count it would drop is reported beside the result.
    """
    bars = _sim_bars()
    ok = simulate_arm_b(
        bars, _sim_detection(bars), market="US", contract=DEFAULT_CONTRACT
    )
    # A detection recorded at a tenth of the bar's price: a scale, not a move.
    rescaled = _sim_detection(bars, close=bars[39].close / 10)
    flagged = simulate_arm_b(bars, rescaled, market="US", contract=DEFAULT_CONTRACT)

    assert ok.price_scale == pytest.approx(1.0)
    assert ok.price_scale_ok
    assert not flagged.price_scale_ok
    assert PRICE_SCALE_MIN < ok.price_scale < PRICE_SCALE_MAX
    assert price_scale_drops([ok, flagged]) == 1


def test_the_report_carries_the_contract_and_the_dropped_count(store):
    """Every figure the package emits carries the contract that produced it, and
    the price-scale count travels with it rather than in a commit message."""
    bars = _sim_bars()
    trades = [
        simulate_arm_b(
            bars, _sim_detection(bars), market="US", contract=DEFAULT_CONTRACT
        ),
        simulate_arm_b(
            bars, _sim_detection(bars, close=bars[39].close / 10),
            market="US", contract=DEFAULT_CONTRACT,
        ),
    ]

    report = simulate_report(DEFAULT_CONTRACT, trades)

    assert report[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    (arm_b,) = [r for r in report["arms"] if r["arm"] == ARM_B]
    assert arm_b["trades"] == 2
    assert arm_b["price_scale_dropped"] == 1


def test_the_printed_result_says_how_many_trades_the_price_scale_flag_drops(store):
    """The count is *reported*, not merely computed (acceptance criterion).

    A flag whose count lives only in a returned dict is a flag nobody reads. The
    run's own output has to carry it, on its own line, because it is the one figure
    here that is about the data rather than about the method.
    """
    bars = _sim_bars()
    trades = [
        simulate_arm_b(
            bars, _sim_detection(bars), market="US", contract=DEFAULT_CONTRACT
        ),
        simulate_arm_b(
            bars, _sim_detection(bars, close=bars[39].close / 10),
            market="US", contract=DEFAULT_CONTRACT,
        ),
    ]

    printed = format_trades(simulate_report(DEFAULT_CONTRACT, trades))

    assert "price-scale flag would drop 1 of 2" in printed
    assert "10MA trail" in printed
    assert TRAIL_MECHANIC in printed


def test_a_changed_trail_mechanic_is_contract_drift_not_a_silent_reinterpretation(store):
    """The mechanic is a contract cell, and the code says which one it implements.

    "Close through the MA, fill at the next open" is recorded as *arbitrary* so a
    later run can vary it deliberately. Varying the cell without varying the code
    would leave a run whose contract and behaviour disagree while both look right.
    """
    check_trail_mechanic(DEFAULT_CONTRACT)
    assert DEFAULT_CONTRACT.value(EXIT_TRAIL_MECHANIC_KEY) == TRAIL_MECHANIC

    drifted = RunContract(
        contract_version=DEFAULT_CONTRACT.contract_version,
        label=DEFAULT_CONTRACT.label,
        cells=tuple(
            Cell(
                key=c.key,
                value="close_through_ma_fills_same_close",
                justification=c.justification,
            )
            if c.key == EXIT_TRAIL_MECHANIC_KEY else c
            for c in DEFAULT_CONTRACT.cells
        ),
    )
    with pytest.raises(ContractDrift):
        check_trail_mechanic(drifted)


def test_arm_b_reads_its_window_from_the_contract_not_from_a_constant(store):
    """The 10 in "10MA" belongs to the contract, so a sweep changes one cell."""
    assert (
        exit_plan(DEFAULT_CONTRACT, ARM_B).trail_ma
        == DEFAULT_CONTRACT.value(EXIT_ARM_B_KEY)["trail_ma"]
    )


def _breakout_tail_hlc():
    """The base fixture, plus a tail that actually breaks and then rolls over.

    ``_wide_base_hlc`` ends on a flat top at 100 under a cluster high of ~102, so a
    denominator built on it names detections that never trade through their own
    trigger. That is a fair fixture for #188, which is about the field, and a
    useless one for #189, which is about what happens after: it would let the
    end-to-end test pass on an empty list of trades.

    So the tail here breaks through the top, runs to 130 and slides back under its
    own 10MA — the whole life of an arm-B trade, in the same authored geometry.
    """
    hlc = _wide_base_hlc()
    for c in (108.0, 115.0, 122.0, 130.0, 120.0, 110.0, 100.0, 95.0, 92.0, 90.0):
        hlc.append((c * 1.02, c * 0.98, c))
    return hlc


def _seed_breakout_store(store: Store, *, market: str = "US"):
    """The #188 seeder, over a series whose base breaks out near the end."""
    hlc = _breakout_tail_hlc()
    dates = _daily(date(2020, 1, 1), len(hlc))
    store.append_bars(market, "BASE", _bars_from_hlc(dates, hlc))
    store.append_bars(
        market,
        MARKET_INDEX[market],
        _bars_from_hlc(dates, _flat_index_hlc(len(hlc))),
    )
    return dates


def test_the_denominators_detections_simulate_end_to_end(store, denominator):
    """The whole path the acceptance criterion names: persisted rows in, trades out.

    Nothing here is hand-authored — the detector names the setup, ``run_denominator``
    persists it, and the simulator reads it back out of the store. It is the only
    test in this block that would notice the two halves disagreeing about what a
    detection is.

    The measured window deliberately straddles the break: the detections on the flat
    top before it are measured too, and they produce nothing, because a detection
    whose next session does not close through its trigger is not a trade. So this
    also pins the count — a simulator that entered every detection would return
    five trades here instead of one.
    """
    dates = _seed_breakout_store(store)
    run = run_denominator(
        store, denominator, "US", DEFAULT_CONTRACT,
        start=dates[0], end=dates[-1], measured_start=dates[100],
    )
    measured_detections = sum(
        len(denominator.detections("US", r.session)) for r in run.measured
    )
    assert measured_detections > 1

    trades = simulate_market(store, denominator, "US", DEFAULT_CONTRACT, arms=(ARM_B,))

    # The one detection whose next session broke: bar 104's, filled at bar 106.
    (trade,) = trades
    assert isinstance(trade, SimulatedTrade)
    assert trade.arm == ARM_B
    assert trade.symbol == "BASE"
    assert trade.detection_session == dates[104]
    assert trade.break_signal.session == dates[105]
    assert trade.entry.session == dates[106]
    assert trade.entry.price == 115.0
    # The stop is the detection's own, and R comes off it.
    (scored,) = denominator.detections("US", dates[104])
    assert trade.stop_price.price == scored.detection.stop_price
    assert trade.exit_reason == EXIT_TRAIL
    assert trade.r_multiple is not None
    assert trade.price_scale_ok

    # Burn-in sessions are never traded off: a result resting on an unsettled
    # chain is exactly what the burn-in flag exists to keep out of the measurement.
    # The run's burn-in really does carry detections, so the exclusion has work to do.
    assert any(denominator.detections("US", r.session) for r in run.burn_in)
    assert trade.detection_session in {r.session for r in run.measured}


# -- arms A and C, on arm B's entry and stop (issue #190) ----------------------
#
# The remaining two exits, sharing arm B's entry and stop *by construction* rather
# than by agreement: the entry and the stop are computed once and the exit is the
# only per-arm step, which is the only reason running three arms answers anything
# about exits at all.
#
# Arm A is the trader's documented behaviour — 50% off at the close of the fifth
# session after entry, remainder on a 10MA trail — and has no counterpart in the
# reference set, so it is measured and never anchored. Arm C is a pure 20MA trail;
# B and C are the two directly comparable to the reference set's simulated exits,
# which is what keeps the anchors usable.

from backtest.chain import bar_index
from backtest.contract import EXIT_ARM_A_KEY, EXIT_ARM_C_KEY
from backtest.simulate import (
    ARM_A,
    ARM_C,
    ARMS,
    EXIT_SCALE,
    SCALE_MECHANIC,
    TRAIL_LIVE_FROM_FILL,
    ExitLeg,
    arm_report,
    check_arm_mechanics,
)


def _arm(bars, det, arm, *, market="US"):
    return simulate_arm(bars, det, market=market, contract=DEFAULT_CONTRACT, arm=arm)


def test_the_three_arms_share_one_entry_and_one_stop(store):
    """The premise of running three arms, asserted rather than assumed.

    If the arms differed anywhere before the exit, a difference between their
    results would be attributable to that difference too, and the whole comparison
    would say nothing about exits. So every field decided at or before the fill is
    required to be identical across all three.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)

    trades = {arm: _arm(bars, det, arm) for arm in ARMS}

    assert set(trades) == {ARM_A, ARM_B, ARM_C}
    shared = {
        (t.trigger, t.break_signal, t.entry, t.stop_price, t.stop_width, t.price_scale)
        for t in trades.values()
    }
    assert len(shared) == 1
    # And the exit really is the only thing that moved: C's 20MA holds a trade B's
    # 10MA has already let go of, so the fixture would notice arms that agreed.
    assert trades[ARM_C].exit != trades[ARM_B].exit


def test_arm_a_scales_half_at_the_close_of_the_fifth_session_after_entry(store):
    """The trader's documented behaviour, as the contract's own numbers.

    "Day 5" is the *close of the fifth session after entry* — the fill session is
    day 0 — and the remainder then trails a 10MA on the same signal-then-fill terms
    arm B uses. The scale session is recomputed from the fill here rather than
    written as a constant, so a test that agreed with the simulator by copying its
    answer would disagree the moment either side moved.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)

    trade = _arm(bars, det, ARM_A)

    plan = exit_plan(DEFAULT_CONTRACT, ARM_A)
    assert (plan.scale_day, plan.scale_fraction, plan.trail_ma) == (5, 0.5, 10)
    fill = bar_index(bars, trade.entry.session)
    scale_bar = bars[fill + plan.scale_day]

    scale, runner = trade.legs
    assert scale.reason == EXIT_SCALE
    assert scale.weight == pytest.approx(0.5)
    # A planned partial is decided and filled on the same close: there is no signal
    # to wait a session on, because nothing about the market triggered it.
    assert scale.signal.session == scale.exit.session == scale_bar.session
    assert scale.exit.price == scale_bar.close
    # The remainder is the rest of the position, exited on arm B's own trail.
    assert runner.reason == EXIT_TRAIL
    assert runner.weight == pytest.approx(0.5)
    assert runner.exit == _arm(bars, det, ARM_B).exit


def test_arm_as_r_is_position_weighted_per_leg_and_summed(store):
    """Half a position exiting at +2R contributes 1R, not 2R (acceptance criterion).

    This is the whole of what "two-legged R" means, and it is the one arithmetic in
    the module that a plausible implementation gets wrong by averaging the legs'
    R instead of weighting them — a mistake that is invisible in the output,
    because the wrong number is the same order of magnitude as the right one.
    """
    bars = _sim_bars()
    session = bars[45].session

    def at(price):
        return Decision(session=session, price=price)

    trade = dataclasses.replace(
        _arm(bars, _sim_detection(bars), ARM_A),
        entry=Decision(session=bars[41].session, price=100.0),
        stop_width=10.0,
        legs=(
            # Half out at 120 — ten points is one R, so this leg is +2R on half a
            # position, and it must contribute exactly 1R.
            ExitLeg(weight=0.5, signal=at(120.0), exit=at(120.0), reason=EXIT_SCALE),
            # The remainder out flat, contributing nothing.
            ExitLeg(weight=0.5, signal=at(100.0), exit=at(100.0), reason=EXIT_TRAIL),
        ),
    )

    assert trade.r_multiple == pytest.approx(1.0)
    # The same exit taken in one leg is the two-legged one's ceiling: a simulator
    # that summed its legs unweighted would report 2R here too.
    whole = dataclasses.replace(
        trade,
        legs=(ExitLeg(weight=1.0, signal=at(120.0), exit=at(120.0), reason=EXIT_TRAIL),),
    )
    assert whole.r_multiple == pytest.approx(2.0)


def test_arm_c_trails_a_twenty_session_ma_and_reads_it_from_the_contract(store):
    """Arm C is arm B with one number changed, and the number is a contract cell.

    The 20 belongs to the contract, so a later run that sweeps it changes one cell
    and no code. The exit session is recomputed from the fixture's own closes for
    the same reason arm B's is.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)

    trade = _arm(bars, det, ARM_C)

    window = exit_plan(DEFAULT_CONTRACT, ARM_C).trail_ma
    assert window == DEFAULT_CONTRACT.value(EXIT_ARM_C_KEY)["trail_ma"] == 20
    signal = next(
        i for i in range(41, len(bars))
        if (ma := trail_ma(bars[: i + 1], window)) is not None and bars[i].close < ma
    )
    (leg,) = trade.legs
    assert leg.reason == EXIT_TRAIL
    assert leg.weight == pytest.approx(1.0)
    assert leg.signal.session == bars[signal].session
    assert trade.exit.session == bars[signal + 1].session
    assert trade.exit.price == bars[signal + 1].open


def test_arm_as_stop_takes_the_whole_position_when_it_fires_before_day_five(store):
    """A stop before the scale ends the trade whole, not half.

    The scale is a *plan*, and a plan that has not executed holds no position. An
    implementation that booked the scale leg regardless would credit arm A with an
    exit at a price it never traded, on precisely the trades that went against it.
    """
    # Break, fill, then straight through the stop at 96 on the next session.
    closes = _SIM_FLAT + [110.0, 111.0, 90.0, 89.0, 88.0, 87.0, 86.0, 85.0]
    bars = _sim_bars(closes)
    det = _sim_detection(bars)

    trade = _arm(bars, det, ARM_A)

    (leg,) = trade.legs
    assert leg.reason == EXIT_STOP
    assert leg.weight == pytest.approx(1.0)
    assert trade.r_multiple == pytest.approx(
        (trade.exit.price - trade.entry.price) / trade.stop_width
    )


def test_a_scaled_trade_whose_remainder_never_exits_is_open_and_carries_no_r(store):
    """Half a result is not a result.

    The bars run out with the runner still running. Reporting the realised half
    would be an equity curve made of the legs that happened to close, which is the
    same bias marking an open trade at the last close would introduce — only harder
    to see, because the trade would look closed.
    """
    bars = _sim_bars(_SIM_FLAT + _SIM_RUN)
    det = _sim_detection(bars)

    trade = _arm(bars, det, ARM_A)

    (scale,) = trade.legs
    assert scale.reason == EXIT_SCALE
    assert trade.open_at_end
    assert trade.exit is None
    assert trade.exit_reason is None
    assert trade.r_multiple is None


def test_arm_a_is_measured_and_never_anchored(store):
    """Arm A has no counterpart in the reference set, and says so in its own report.

    B and C are the two directly comparable to the reference set's simulated exits;
    A is the trader's own behaviour and has nothing to be compared against. A report
    that did not carry that distinction would let a later phase anchor A against a
    figure that was never measured on A's rules.
    """
    bars = _sim_bars()
    trades = [_arm(bars, _sim_detection(bars), arm) for arm in ARMS]

    report = simulate_report(DEFAULT_CONTRACT, trades)
    by_arm = {r["arm"]: r for r in report["arms"]}

    assert by_arm[ARM_A]["comparable_to_reference"] is False
    assert by_arm[ARM_B]["comparable_to_reference"] is True
    assert by_arm[ARM_C]["comparable_to_reference"] is True
    assert "arm A — 50% at the close of session 5" in format_trades(report)


def test_the_day_five_and_trail_mechanics_are_recorded_as_arbitrary(store):
    """Both mechanics are contract cells that say they were chosen arbitrarily.

    Neither "the fifth session" nor "fill at the next open" is derived from
    anything. Recording that is what lets a later run vary them deliberately rather
    than rediscover them, and the code refuses a contract that has quietly dropped
    the admission — a run whose mechanics look principled is a run whose sweep
    nobody thinks to do.
    """
    check_arm_mechanics(DEFAULT_CONTRACT, ARM_A)
    assert DEFAULT_CONTRACT.value(EXIT_ARM_A_KEY)["arbitrary_mechanics"] is True
    assert DEFAULT_CONTRACT.value(EXIT_TRAIL_MECHANIC_KEY) == TRAIL_MECHANIC
    assert SCALE_MECHANIC == "close_of_nth_session_after_entry"

    principled = RunContract(
        contract_version=DEFAULT_CONTRACT.contract_version,
        label=DEFAULT_CONTRACT.label,
        cells=tuple(
            Cell(
                key=c.key,
                value={**c.value, "arbitrary_mechanics": False},
                justification=c.justification,
            )
            if c.key == EXIT_ARM_A_KEY else c
            for c in DEFAULT_CONTRACT.cells
        ),
    )
    with pytest.raises(ContractDrift):
        check_arm_mechanics(principled, ARM_A)


def test_a_detection_appears_once_per_arm(store, denominator):
    """One trade per arm per detection (acceptance criterion), end to end.

    Run over the persisted denominator rather than a hand-authored detection, so a
    simulator that produced three arms in isolation and duplicated them over the
    store's rows would still be caught.
    """
    dates = _seed_breakout_store(store)
    run_denominator(
        store, denominator, "US", DEFAULT_CONTRACT,
        start=dates[0], end=dates[-1], measured_start=dates[100],
    )

    trades = simulate_market(store, denominator, "US", DEFAULT_CONTRACT)

    keyed = {(t.symbol, t.detection_session, t.arm) for t in trades}
    assert len(keyed) == len(trades) == 3
    assert {t.arm for t in trades} == set(ARMS)
    # One detection, three arms, one shared entry — the store's own rows, not the
    # authored fixture's.
    assert len({(t.detection_session, t.entry, t.stop_price) for t in trades}) == 1


def test_one_arm_can_be_simulated_alone_without_moving_the_others(store, denominator):
    """Restricting the arms is a filter on which exits run, never on what they read.

    The arms share their entry, so simulating one alone must produce exactly the
    trade the full run produced for it — otherwise the per-arm figures a sweep
    reports would depend on which arms happened to be run beside them.
    """
    dates = _seed_breakout_store(store)
    run_denominator(
        store, denominator, "US", DEFAULT_CONTRACT,
        start=dates[0], end=dates[-1], measured_start=dates[100],
    )

    every = simulate_market(store, denominator, "US", DEFAULT_CONTRACT)
    alone = simulate_market(store, denominator, "US", DEFAULT_CONTRACT, arms=(ARM_C,))

    assert alone == [t for t in every if t.arm == ARM_C]


def test_each_arms_report_carries_its_own_exit_and_the_one_contract(store):
    """Three arms, three sets of figures, one stamped contract.

    The arms differ only in the exit, so the report has to name the exit each figure
    came from; a set of totals labelled only "arm A/B/C" would be unreadable the
    moment a sweep changed a window.
    """
    bars = _sim_bars()
    trades = [_arm(bars, _sim_detection(bars), arm) for arm in ARMS]

    report = simulate_report(DEFAULT_CONTRACT, trades)

    assert report[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    assert [r["arm"] for r in report["arms"]] == list(ARMS)
    by_arm = {r["arm"]: r for r in report["arms"]}
    assert by_arm[ARM_A]["scale_day"] == 5
    assert by_arm[ARM_A]["scale_fraction"] == 0.5
    assert by_arm[ARM_A]["scale_mechanic"] == SCALE_MECHANIC
    assert by_arm[ARM_B]["trail_ma"] == 10
    assert by_arm[ARM_C]["trail_ma"] == 20
    assert all(r["trades"] == 1 for r in report["arms"])
    # And a single arm's body is the same shape whether or not the others ran.
    assert arm_report(DEFAULT_CONTRACT, ARM_C, trades) == by_arm[ARM_C]


def test_an_arm_the_contract_does_not_name_is_refused(store):
    """A typo in an arm name is a hard error, not an empty result set.

    An unknown arm that returned no trades would report a clean zero — the shape a
    real, correctly-run arm takes when nothing triggered — and there is no way to
    tell those two apart after the fact.
    """
    bars = _sim_bars()
    with pytest.raises(ValueError):
        _arm(bars, _sim_detection(bars), "D")


def test_the_trail_is_live_from_the_fill_and_the_contract_says_so(store):
    """The third arbitrary mechanic, in the contract rather than in a comment.

    On a scaling arm the trail watches from the fill, not from the scale day — so a
    runner that rolls over before day 5 takes the *whole* position out and the scale
    never happens. On a fast breakout that degenerates arm A into arm B, which is a
    material claim about what arm A measures and exactly the kind of thing the
    issue means by "the mechanics are contract, not code comments".
    """
    # Break, fill, then a slide that closes under the 10MA well before day 5.
    closes = _SIM_FLAT + [110.0, 111.0, 99.0, 98.5, 98.0, 97.5, 97.2, 97.0]
    bars = _sim_bars(closes)
    det = _sim_detection(bars)

    trade = _arm(bars, det, ARM_A)

    (leg,) = trade.legs
    assert leg.reason == EXIT_TRAIL
    assert leg.weight == pytest.approx(1.0)
    # Degenerate is the point: with the trail live from the fill, arm A took the
    # same trade arm B did.
    assert trade.legs == _arm(bars, det, ARM_B).legs

    assert exit_plan(DEFAULT_CONTRACT, ARM_A).trail_live_from == TRAIL_LIVE_FROM_FILL
    assert (
        DEFAULT_CONTRACT.value(EXIT_ARM_A_KEY)["trail_live_from"]
        == TRAIL_LIVE_FROM_FILL
    )


def test_a_trail_the_contract_starts_elsewhere_is_drift_not_a_reinterpretation(store):
    """Varying the cell without varying the code would leave a run whose contract
    and behaviour disagree while both look right — the same refusal the trail's own
    fill mechanic already carries."""
    elsewhere = RunContract(
        contract_version=DEFAULT_CONTRACT.contract_version,
        label=DEFAULT_CONTRACT.label,
        cells=tuple(
            Cell(
                key=c.key,
                value={**c.value, "trail_live_from": "scale_day"},
                justification=c.justification,
            )
            if c.key == EXIT_ARM_A_KEY else c
            for c in DEFAULT_CONTRACT.cells
        ),
    )
    with pytest.raises(ContractDrift):
        check_arm_mechanics(elsewhere, ARM_A)


def test_an_arm_that_ran_and_traded_nothing_reports_zeros_rather_than_vanishing(store):
    """An arm that triggered nothing is a measurement; an arm that never ran is not.

    A report built from the arms *present in the trades* collapses the two into the
    same output — a missing section — and there is no way to tell them apart after
    the fact. So the report covers the arms that were run.
    """
    bars = _sim_bars()
    trades = [_arm(bars, _sim_detection(bars), ARM_B)]

    ran_all = simulate_report(DEFAULT_CONTRACT, trades)
    ran_one = simulate_report(DEFAULT_CONTRACT, trades, arms=(ARM_B,))

    assert [r["arm"] for r in ran_all["arms"]] == list(ARMS)
    quiet = {r["arm"]: r for r in ran_all["arms"]}[ARM_C]
    assert (quiet["trades"], quiet["closed"], quiet["total_r"]) == (0, 0, 0)
    # And an arm that never ran is absent, which is the distinction being kept.
    assert [r["arm"] for r in ran_one["arms"]] == [ARM_B]


# -- the pre-registered headline metric (issue #191) ---------------------------
#
# Phase 5's first cell, and the only metric the run promised in advance: arm B's
# after-cost expectancy in R, per market per year. Everything here is arithmetic
# over trades the simulator already produced — no bar is read — which is why the
# fixtures below author trades directly rather than running a chain to reach them.
#
# Three claims are load-bearing and each has a test that would fail loudly if the
# code drifted from it:
#
#   * **Costs are the contract's own, per market.** IDX carries real fees and
#     spread; US is near-zero. A market the cell does not name is drift, never a
#     free trade.
#   * **Never pooled only.** The window holds a crash and a mania, so a pooled
#     fourteen-year figure describes neither. Per year always, and the
#     2020–21-excluded figure beside the full-window one.
#   * **Clustered by symbol, not by row.** A stock throwing three signals in a
#     fortnight is not three independent observations, and bootstrapping the rows
#     flatters every p-value.

from backtest.contract import (
    COSTS_KEY,
    METRIC_PRIMARY_KEY,
    WINDOW_MEASURED_START_KEY,
)
from backtest.metric import (
    BOOTSTRAP_CLUSTER,
    BOOTSTRAP_MIN_CLUSTERS,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    EXCLUDED_YEARS,
    EXCLUDED_YEARS_WINDOW,
    FULL_WINDOW,
    PRIMARY_ARM,
    after_cost_r,
    bootstrap_expectancy,
    check_costs,
    check_primary_metric,
    clusters_by_symbol,
    cost_r,
    expectancy_cell,
    format_metric,
    market_report,
    metric_report,
    per_side_cost_bps,
)

# The authored trade every metric test runs on: entry at 100 with a stop width of
# 10, so a trade's *before-cost* R is exactly the number the fixture asks for and
# every figure below is arithmetic a reader can check without a bar series.
_M_ENTRY = 100.0
_M_STOP_WIDTH = 10.0


def _mtrade(
    symbol: str,
    year: int,
    r: float,
    *,
    market: str = "US",
    arm: str = ARM_B,
    price_scale_ok: bool = True,
    open_at_end: bool = False,
    month: int = 3,
) -> SimulatedTrade:
    """One arm-B trade whose before-cost R is exactly ``r``.

    Authored rather than simulated: the metric is arithmetic over trades, so a
    fixture that ran the simulator to reach them would put a second phase's bugs
    inside this one's tests. ``open_at_end`` leaves half the position on, which is
    how a trade with no R is spelled — its legs do not add up to a whole one.
    """
    entry_session = date(year, month, 1)
    exit_session = date(year, month, 20)
    exit_price = _M_ENTRY + r * _M_STOP_WIDTH
    weight = 0.5 if open_at_end else 1.0
    leg = ExitLeg(
        weight=weight,
        signal=Decision(session=exit_session, price=exit_price),
        exit=Decision(session=exit_session, price=exit_price),
        reason=EXIT_TRAIL,
    )
    return SimulatedTrade(
        market=market,
        symbol=symbol,
        arm=arm,
        detection_session=date(year, month, 1),
        trigger=Decision(session=date(year, month, 1), price=_M_ENTRY),
        break_signal=Decision(session=date(year, month, 1), price=_M_ENTRY),
        entry=Decision(session=entry_session, price=_M_ENTRY),
        stop_price=Decision(
            session=date(year, month, 1), price=_M_ENTRY - _M_STOP_WIDTH
        ),
        stop_width=_M_STOP_WIDTH,
        legs=(leg,),
        price_scale=1.0,
        price_scale_ok=price_scale_ok,
    )


def test_the_primary_metric_is_the_contracts_own_and_is_arm_bs(store):
    """The headline is the contract's cell, read rather than restated.

    The metric that gets reported and the metric that was pre-registered are the
    same string, or the run has quietly chosen its headline after the fact — which
    is the one thing pre-registration exists to prevent.
    """
    assert PRIMARY_ARM == ARM_B
    report = metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2015, 1.0)])

    assert report["metric"] == DEFAULT_CONTRACT.value(METRIC_PRIMARY_KEY)
    assert report["arm"] == ARM_B
    check_primary_metric(DEFAULT_CONTRACT)


def test_a_contract_whose_primary_metric_moved_is_drift_not_a_new_headline(store):
    """Changing the cell without changing the code leaves a run whose contract and
    behaviour disagree while both look right — a new run recorded beside the old
    one is the remedy, never a silent reinterpretation."""
    moved = RunContract(
        contract_version=DEFAULT_CONTRACT.contract_version,
        label=DEFAULT_CONTRACT.label,
        cells=tuple(
            Cell(
                key=c.key,
                value="arm_a_after_cost_expectancy_r",
                justification=c.justification,
            )
            if c.key == METRIC_PRIMARY_KEY else c
            for c in DEFAULT_CONTRACT.cells
        ),
    )
    with pytest.raises(ContractDrift):
        check_primary_metric(moved)


def test_costs_are_the_contracts_own_per_market_and_paid_on_both_sides(store):
    """IDX's real fees and spread are not modelled with US's near-zero assumptions.

    Commission and slippage are both per-side bps of the traded price, so a round
    trip pays on the entry and on every leg that comes off. In R that is the cost
    in price divided by the stop width, which keeps the figure in the unit the
    result is denominated in.
    """
    us_costs = DEFAULT_CONTRACT.value(COSTS_KEY)["US"]
    idx_costs = DEFAULT_CONTRACT.value(COSTS_KEY)["IDX"]
    assert per_side_cost_bps(DEFAULT_CONTRACT, "US") == (
        us_costs["commission_bps"] + us_costs["slippage_bps"]
    )
    assert per_side_cost_bps(DEFAULT_CONTRACT, "IDX") == (
        idx_costs["commission_bps"] + idx_costs["slippage_bps"]
    )

    us = _mtrade("AAA", 2015, 1.0, market="US")
    idx = _mtrade("BBB", 2015, 1.0, market="IDX")

    # Entry at 100, exit at 110, stop width 10: (100 + 110) × rate / 10.
    assert cost_r(us, DEFAULT_CONTRACT) == pytest.approx(
        (100.0 + 110.0) * (5.0 / 10_000.0) / 10.0
    )
    assert cost_r(idx, DEFAULT_CONTRACT) == pytest.approx(
        (100.0 + 110.0) * (40.0 / 10_000.0) / 10.0
    )
    # Jakarta pays materially more for the same trade, which is the whole reason
    # the cell is per market.
    assert cost_r(idx, DEFAULT_CONTRACT) > cost_r(us, DEFAULT_CONTRACT) * 5


def test_a_market_the_costs_cell_does_not_name_is_drift_not_a_free_trade(store):
    """An unnamed market priced at zero would report the most flattering
    expectancy in the run and look like a clean result. So it is refused."""
    with pytest.raises(ContractDrift):
        check_costs(DEFAULT_CONTRACT, "LSE")
    with pytest.raises(ContractDrift):
        cost_r(_mtrade("AAA", 2015, 1.0, market="LSE"), DEFAULT_CONTRACT)


def test_the_reported_expectancy_is_after_cost_and_lower_than_before_cost(store):
    """The headline is the after-cost number, and it is the one in the cell."""
    trades = [_mtrade("AAA", 2015, 1.0), _mtrade("BBB", 2015, -1.0)]

    cell = expectancy_cell(DEFAULT_CONTRACT, trades, market="US", label="2015")

    before = sum(t.r_multiple for t in trades) / len(trades)
    after = sum(after_cost_r(t, DEFAULT_CONTRACT) for t in trades) / len(trades)
    assert cell["expectancy_r_before_cost"] == pytest.approx(before)
    assert cell["expectancy_r"] == pytest.approx(after)
    assert cell["expectancy_r"] < cell["expectancy_r_before_cost"]
    assert cell["cost_r"] == pytest.approx(before - after)


def test_the_win_rate_and_the_r_distribution_ride_with_the_expectancy(store):
    """A 20% win rate is not a broken method; a 20% win rate with a small right
    tail is. So the expectancy never travels without the shape behind it.

    Eight losers at −1R and two winners at +8R: one in five made money and the
    mean R is positive anyway, which is the reference set's own shape (22.7% at a
    positive mean) and the reason the win rate alone decides nothing.
    """
    trades = [_mtrade(f"L{i}", 2016, -1.0) for i in range(8)]
    trades += [_mtrade(f"W{i}", 2016, 8.0) for i in range(2)]

    cell = expectancy_cell(DEFAULT_CONTRACT, trades, market="US", label="2016")

    assert cell["win_rate"] == pytest.approx(0.2)
    assert cell["wins"] == 2 and cell["losses"] == 8
    assert cell["expectancy_r"] > 0
    dist = cell["distribution"]
    assert dist["median"] < 0 < dist["max"]
    assert dist["p90"] > 0
    assert dist["mean_win"] > 0 > dist["mean_loss"]


def test_the_same_win_rate_with_a_thin_tail_is_a_different_result(store):
    """The distribution is what separates the two, and only one of them is a
    method worth trading — which is why the win rate is never reported alone."""
    fat = [_mtrade(f"L{i}", 2016, -1.0) for i in range(8)]
    fat += [_mtrade(f"W{i}", 2016, 8.0) for i in range(2)]
    thin = [_mtrade(f"L{i}", 2016, -1.0) for i in range(8)]
    thin += [_mtrade(f"W{i}", 2016, 1.2) for i in range(2)]

    fat_cell = expectancy_cell(DEFAULT_CONTRACT, fat, market="US", label="2016")
    thin_cell = expectancy_cell(DEFAULT_CONTRACT, thin, market="US", label="2016")

    assert fat_cell["win_rate"] == thin_cell["win_rate"]
    assert fat_cell["expectancy_r"] > 0 > thin_cell["expectancy_r"]
    assert fat_cell["distribution"]["max"] > thin_cell["distribution"]["max"]


def test_the_2020_21_excluded_figure_is_reported_beside_the_full_window_one(store):
    """That tape rewarded momentum nearly everywhere, so it cannot carry the
    conclusion alone — and the way to stop it is to print both figures together."""
    trades = [_mtrade("AAA", 2016, -0.5), _mtrade("BBB", 2020, 6.0)]

    body = market_report(DEFAULT_CONTRACT, trades, market="US")

    windows = {w["label"]: w for w in body["windows"]}
    assert set(windows) == {FULL_WINDOW, EXCLUDED_YEARS_WINDOW}
    assert EXCLUDED_YEARS == (2020, 2021)
    assert windows[EXCLUDED_YEARS_WINDOW]["excluded_years"] == list(EXCLUDED_YEARS)
    # The mania year carried the full-window figure, and dropping it flips the sign.
    assert windows[FULL_WINDOW]["expectancy_r"] > 0
    assert windows[EXCLUDED_YEARS_WINDOW]["expectancy_r"] < 0
    assert windows[EXCLUDED_YEARS_WINDOW]["closed"] == 1


def test_a_market_is_never_reported_pooled_only(store):
    """Per year always, in the payload and on the printed page both.

    A pooled fourteen-year number over a window holding a crash and a mania
    describes neither, so a reader must not be able to reach one without the years
    beside it.

    The span runs from the **contract's** measured start, not from the first trade:
    a market that traded nothing until 2016 in a run measuring from 2012 has four
    silent years, and those are exactly the years an empty crawl would hide.
    """
    trades = [_mtrade("AAA", 2016, 1.0), _mtrade("BBB", 2020, -1.0)]

    body = market_report(DEFAULT_CONTRACT, trades, market="US")

    years = [y["label"] for y in body["years"]]
    start = int(DEFAULT_CONTRACT.value(WINDOW_MEASURED_START_KEY)[:4])
    assert start == 2012
    assert years == [str(y) for y in range(start, 2021)]
    assert {y["label"]: y for y in body["years"]}["2013"]["trades"] == 0
    printed = format_metric(metric_report(DEFAULT_CONTRACT, trades))
    for label in years:
        assert label in printed


def test_a_year_inside_the_span_with_no_trades_reports_zero_rather_than_vanishing(store):
    """A quiet year is a measurement; a missing year is a gap in the report.

    Absent rows collapse the two into the same output, and the years between the
    first and last trade are exactly where a data hole would hide.
    """
    trades = [_mtrade("AAA", 2016, 1.0), _mtrade("BBB", 2019, 1.0)]

    body = market_report(DEFAULT_CONTRACT, trades, market="US")

    quiet = {y["label"]: y for y in body["years"]}["2017"]
    assert (quiet["trades"], quiet["closed"]) == (0, 0)
    assert quiet["expectancy_r"] is None
    assert quiet["win_rate"] is None


def test_us_and_idx_are_reported_separately_including_in_the_summary(store):
    """findings §8 measured that magnitudes do not transfer, so an average across
    the two markets is a number about neither."""
    trades = [
        _mtrade("AAA", 2016, 2.0, market="US"),
        _mtrade("BBB", 2016, -1.0, market="IDX"),
    ]

    report = metric_report(DEFAULT_CONTRACT, trades)

    markets = {m["market"]: m for m in report["markets"]}
    assert set(markets) == {"US", "IDX"}
    us = {w["label"]: w for w in markets["US"]["windows"]}[FULL_WINDOW]
    idx = {w["label"]: w for w in markets["IDX"]["windows"]}[FULL_WINDOW]
    assert us["expectancy_r"] > 0 > idx["expectancy_r"]
    # And nothing anywhere in the payload pools them.
    assert "expectancy_r" not in report
    printed = format_metric(report)
    assert "US" in printed and "IDX" in printed


def test_a_cell_that_spans_two_markets_is_refused(store):
    """The separation is enforced where the arithmetic happens, not remembered at
    the call site — a mean across two markets is the exact figure story 4 forbids,
    and it has no shape that would make it visible afterwards."""
    trades = [
        _mtrade("AAA", 2016, 1.0, market="US"),
        _mtrade("BBB", 2016, 1.0, market="IDX"),
    ]
    with pytest.raises(ValueError):
        expectancy_cell(DEFAULT_CONTRACT, trades, market="US", label="2016")


def test_a_cell_that_spans_two_arms_is_refused(store):
    """The pre-registered metric is arm B's. Averaging an arm A trade into it
    would report a number no arm produced, under arm B's name."""
    trades = [
        _mtrade("AAA", 2016, 1.0),
        _mtrade("BBB", 2016, 1.0, arm=ARM_A),
    ]
    with pytest.raises(ValueError):
        expectancy_cell(DEFAULT_CONTRACT, trades, market="US", label="2016")


def test_significance_is_bootstrapped_clustered_by_symbol_not_by_row(store):
    """A stock throwing twenty signals is not twenty independent observations.

    One hot name at +3R twenty times over, against twenty different names at −1R
    each. Resampling *rows* treats the hot name's run as forty independent draws
    and returns a tight interval and a tiny p-value; resampling *symbols* asks the
    question that was actually asked — would another market have thrown up that
    name at all — and the interval widens accordingly.
    """
    trades = [_mtrade("HOT", 2016, 3.0, month=1 + i % 12) for i in range(20)]
    trades += [_mtrade(f"C{i}", 2016, -1.0) for i in range(20)]

    by_symbol = bootstrap_expectancy(clusters_by_symbol(trades, DEFAULT_CONTRACT))
    by_row = bootstrap_expectancy(
        [(after_cost_r(t, DEFAULT_CONTRACT),) for t in trades], cluster="row"
    )

    assert by_symbol["cluster"] == BOOTSTRAP_CLUSTER == "symbol"
    assert by_symbol["clusters"] == 21
    assert by_row["clusters"] == 40
    widened = (by_symbol["ci_high"] - by_symbol["ci_low"]) > (
        by_row["ci_high"] - by_row["ci_low"]
    )
    assert widened
    # And the flattering p-value is exactly what row-counting buys.
    assert by_symbol["p_value"] > by_row["p_value"]


def test_the_bootstrap_is_deterministic_under_its_seed(store):
    """A significance figure that moved between two runs of the same data would
    make every result unreproducible, and nothing in the output would show it."""
    trades = [_mtrade(f"S{i}", 2016, 1.0 if i % 3 else -1.0) for i in range(30)]
    clusters = clusters_by_symbol(trades, DEFAULT_CONTRACT)

    first = bootstrap_expectancy(clusters)
    second = bootstrap_expectancy(clusters)

    assert first == second
    assert first["resamples"] == BOOTSTRAP_RESAMPLES
    assert first["seed"] == BOOTSTRAP_SEED
    # And it rides on every cell rather than being computed on request.
    cell = expectancy_cell(DEFAULT_CONTRACT, trades, market="US", label="2016")
    assert cell["bootstrap"]["clusters"] == 30


def test_an_open_trade_has_no_r_and_is_counted_rather_than_marked_to_market(store):
    """Closing a running trade at the last close would invent an exit the rules
    never gave — systematically, for every name still running at the end of the
    window. So it is excluded from the expectancy and reported as open."""
    trades = [_mtrade("AAA", 2016, 1.0), _mtrade("BBB", 2016, 5.0, open_at_end=True)]

    cell = expectancy_cell(DEFAULT_CONTRACT, trades, market="US", label="2016")

    assert (cell["trades"], cell["closed"], cell["open_at_end"]) == (2, 1, 1)
    assert cell["expectancy_r"] == pytest.approx(
        after_cost_r(trades[0], DEFAULT_CONTRACT)
    )


def test_the_price_scale_dropped_count_travels_with_every_cell(store):
    """The flag's whole purpose is to make the comparisons that are *not*
    rescale-immune visible, so its count rides beside every figure derived from
    the trades it flags — never in a commit message."""
    trades = [
        _mtrade("AAA", 2016, 1.0),
        _mtrade("BBB", 2016, 1.0, price_scale_ok=False),
    ]

    body = market_report(DEFAULT_CONTRACT, trades, market="US")

    window = {w["label"]: w for w in body["windows"]}[FULL_WINDOW]
    assert window["price_scale_dropped"] == 1
    assert {y["label"]: y for y in body["years"]}["2016"]["price_scale_dropped"] == 1
    # Flagged, never silently dropped: both trades are still in the expectancy.
    assert window["closed"] == 2


def test_the_metric_is_recorded_before_any_swept_variant_exists(store):
    """Every threshold tried is a test, and enough of them produce a winner from
    noise. So the headline is computed and recorded first, and the report says so
    with the count of variants that stood behind it — zero, here, because none
    exists yet."""
    report = metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2016, 1.0)])

    assert report["pre_registered"] is True
    assert report["sweep"]["variants_tried"] == 0
    assert "before" in report["sweep"]["note"]


def test_the_metric_report_is_stamped_with_the_contract(store):
    """Like every other figure the package emits: two runs under different
    contracts are distinguishable from their serialised output alone."""
    report = metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2016, 1.0)])

    assert report[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    assert json.loads(json.dumps(report)) == report


def test_the_metric_runs_off_the_simulator_end_to_end(store):
    """The seam that matters: trades the simulator produced, priced and measured.

    Every other test here authors its trades so the arithmetic is checkable; this
    one proves the two phases actually join, and that the headline the run reports
    is arm B's own trade after the contract's costs.
    """
    bars = _sim_bars()
    det = _sim_detection(bars)
    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)

    report = metric_report(DEFAULT_CONTRACT, [trade])

    body = {m["market"]: m for m in report["markets"]}["US"]
    window = {w["label"]: w for w in body["windows"]}[FULL_WINDOW]
    assert window["closed"] == 1
    assert window["expectancy_r"] == pytest.approx(
        trade.r_multiple - cost_r(trade, DEFAULT_CONTRACT)
    )
    # The years run from the contract's measured start to the trade's own year;
    # every one before it is a silent year the run measured and found nothing in.
    years = [y["label"] for y in body["years"]]
    assert years[-1] == str(trade.entry.session.year)
    assert years[0] == DEFAULT_CONTRACT.value(WINDOW_MEASURED_START_KEY)[:4]


def test_a_cell_too_thin_to_bootstrap_reports_no_interval_rather_than_a_degenerate_one(store):
    """One symbol resampled two thousand times returns its own mean two thousand
    times — a zero-width interval at p = 0, which prints as overwhelming
    significance and is the opposite: one independent observation.

    Per-year cells are exactly where the cluster count goes thin, so the floor
    matters most where the metric is reported. The thin cell still says how many
    symbols it had, because "too few to say" and "no result" are different findings.
    """
    thin = [_mtrade("ONE", 2016, 3.0, month=1 + i) for i in range(4)]

    cell = expectancy_cell(DEFAULT_CONTRACT, thin, market="US", label="2016")

    boot = cell["bootstrap"]
    assert boot["clusters"] == 1 < BOOTSTRAP_MIN_CLUSTERS
    assert (boot["ci_low"], boot["ci_high"], boot["p_value"]) == (None, None, None)
    assert "too thin" in boot["suppressed"]
    # The expectancy itself is still reported — it is the interval that is refused.
    assert cell["expectancy_r"] is not None
    printed = format_metric(metric_report(DEFAULT_CONTRACT, thin))
    assert "too thin for an interval" in printed

    # And a cell at the floor gets its interval.
    wide = [_mtrade(f"S{i}", 2016, 1.0) for i in range(BOOTSTRAP_MIN_CLUSTERS)]
    at_floor = expectancy_cell(DEFAULT_CONTRACT, wide, market="US", label="2016")
    assert at_floor["bootstrap"]["ci_low"] is not None
    assert at_floor["bootstrap"]["suppressed"] is None


def test_a_trade_that_closed_without_a_denominator_is_not_counted_as_open(store):
    """A trade whose stop width is non-positive has come fully off and still has no
    R. Folding it into the open count would report a finished trade as running, and
    the two numbers would stop adding up to the total with nothing in between.
    """
    ok = _mtrade("AAA", 2016, 1.0)
    broken = dataclasses.replace(_mtrade("BBB", 2016, 1.0), stop_width=0.0)
    still_on = _mtrade("CCC", 2016, 1.0, open_at_end=True)

    cell = expectancy_cell(
        DEFAULT_CONTRACT, [ok, broken, still_on], market="US", label="2016"
    )

    assert broken.closed and broken.r_multiple is None
    assert cell["trades"] == 3
    assert cell["closed"] == 1
    assert cell["open_at_end"] == 1
    assert cell["undenominated"] == 1
    # Every trade lands in exactly one of the three, so none can go missing.
    assert cell["closed"] + cell["open_at_end"] + cell["undenominated"] == 3


def test_the_headline_cannot_be_stamped_over_another_arms_trades(store):
    """The metric's name and the trades under it are the same arm or the report is
    a mislabel — which is exactly what the two-arm refusal exists to prevent, and
    would be reintroduced by any caller able to choose the arm."""
    arm_a = [_mtrade("AAA", 2016, 5.0, arm=ARM_A)]

    report = metric_report(DEFAULT_CONTRACT, arm_a)

    assert report["arm"] == ARM_B
    # Arm A's trades are not this arm's, so the headline counts none of them rather
    # than reporting arm A's result under arm B's name.
    body = {m["market"]: m for m in report["markets"]}["US"]
    assert {w["label"]: w for w in body["windows"]}[FULL_WINDOW]["trades"] == 0
# -- the denominator figures: precision, at last (issue #193) ------------------
#
# Phase 5 of PRD #182, and the figures no prior study in this repo could produce.
# The reference study has 828 trades a trader **took**, so every result in it is
# conditioned on his selection and it can report no precision at all. #149 hit the
# same wall from the other side and had to record 27,323 detections as volume
# carrying no verdict. Those detections are exactly the population measured here.
#
# Three figures, and each carries the coverage it was measured against, because a
# rate whose denominator is not printed is a rate nobody can check:
#
# - **detections per session**, per market and per year, plotted across the window
# - **the share that trigger** — a close through the detection's own trigger
# - **the share that reach a favourable outcome** — precision
#
# Two things the block guards that no assertion about a rate would catch. A
# detection the bars cannot answer must never be counted as a miss, and a trade
# still running at the end of the window must never be counted as a loss: both
# would deflate precision silently and in the direction that makes the method look
# worse, which is the direction nobody investigates. And a year whose count
# collapses is a data hole that reads as a quiet market until someone looks, so it
# is flagged on the row rather than left for a reader to spot in a column.

from backtest.figures import (
    DETECTION_COLLAPSE_FRACTION,
    FAVOURABLE_RULE,
    HOLE_MARK,
    SESSION_COLLAPSE_FRACTION,
    SMA50_OVERLAP_NOTE,
    Share,
    figures_for_market,
    figures_report,
    format_figures,
    main as figures_main,
)
from backtest.simulate import (
    ARM_A,
    ARM_C,
    ENTRY_FILLED,
    ENTRY_NO_BREAK,
    ENTRY_PENDING,
    ENTRY_UNDECIDABLE,
    ENTRY_UNFILLED,
    entry,
)


def _fig_bars(start: date, closes: list[float]) -> list[Bar]:
    """Bars for one authored name, one close per session, from ``start``."""
    return _flat_then(_daily(start, len(closes)), closes)


# A detection named on the 40th bar of a flat stretch, whose next session decides
# the break. All three runs are the same length, so a year's session count is the
# fixture's arithmetic and never an artefact of which outcome a name happened to
# reach.
#
# ``_FIG_WIN`` breaks, runs to 290 and rolls over under its own 10MA at 200 — the
# fill is at 111 and the exit at 195, so it is favourable by a distance no rounding
# reaches. Authored that way deliberately: a fixture that merely *breaks out* is
# not a winner, because the trail signals on the way back down and can easily fill
# under the entry. ``_FIG_LOSS`` breaks and slides through the stop at 96.
# ``_FIG_NO_BREAK`` never closes through the trigger at all.
_FIG_FLAT = [100.0] * 40
_FIG_WIN = [110.0, 111.0, 130.0, 150.0, 170.0, 190.0, 210.0, 230.0,
            250.0, 270.0, 290.0, 200.0, 195.0, 190.0, 185.0, 180.0,
            175.0, 170.0, 165.0, 160.0, 155.0, 150.0]
_FIG_LOSS = [110.0, 111.0, 108.0, 102.0, 97.0, 90.0, 89.0, 88.0,
             87.0, 86.0, 85.0, 84.0, 83.0, 82.0, 81.0, 80.0,
             79.0, 78.0, 77.0, 76.0, 75.0, 74.0]
_FIG_NO_BREAK = [101.0, 101.0, 100.0, 100.0, 99.0, 99.0, 98.0, 98.0,
                 99.0, 99.0, 100.0, 100.0, 101.0, 101.0, 100.0, 100.0,
                 99.0, 99.0, 100.0, 100.0, 101.0, 101.0]
# What one authored name costs in sessions: the flat stretch plus its run.
FIG_SESSIONS = len(_FIG_FLAT) + len(_FIG_WIN)


def _fig_detection(bars: list[Bar], symbol: str) -> Detection:
    """The detection the figures are measured over: trigger 102, stop 96.

    Built the way ``_sim_detection`` is — ``stopw_adr`` derived from the ADR the
    detector would have measured, never chosen beside it — so the fixture is a
    detection some detector could actually have emitted.
    """
    a = adr(trailing_bars(bars, bars[39].session, ADR_WINDOW))
    return dataclasses.replace(
        _det(symbol, 5),
        symbol=symbol,
        session=bars[39].session,
        trigger=SIM_TRIGGER,
        stop=SIM_STOP_WIDTH,
        stopw_adr=SIM_STOP_WIDTH / (a * SIM_TRIGGER),
        adr=a,
        close=bars[39].close,
        cluster_high=SIM_TRIGGER,
    )


def _seed_figure_name(
    store: Store,
    denominator: DenominatorStore,
    market: str,
    symbol: str,
    start: date,
    closes: list[float],
    *,
    burn_in: bool = False,
    detect: bool = True,
    rs_line: bool | None = False,
    relative_move: float | None = None,
) -> Detection:
    """One authored name: its bars in the bar store, its detection in the denominator.

    The denominator rows are written directly rather than replayed through the
    chain, because these tests are about the *figures* read off the rows and a
    fourteen-year fixture built through the detector would take the geometry — not
    the arithmetic — as the thing under test. Every session between the first bar
    and the last carries a header, so the per-year session counts below are the
    fixture's own and not an artefact of which sessions happened to detect.

    ``detect=False`` seeds the sessions and no detection, which is how a year gets
    a full trading calendar and an empty field — the shape a collapsed count has
    when it is a data hole rather than a short year.

    The two candidate values default to what a name with no benchmark history
    carries — a miss on ``rs_line``, absent on ``relative_move`` — and are
    overridable, because the candidate-outcome section below reads exactly those
    two columns off the persisted row.
    """
    bars = _fig_bars(start, closes)
    store.append_bars(market, symbol, bars)
    det = _fig_detection(bars, symbol)
    for bar in bars:
        denominator.append_session(
            SessionRow(
                market=market, session=bar.session, burn_in=burn_in,
                members=1,
                detections=1 if detect and bar.session == det.session else 0,
                regime_state=None, breadth=None, broke_out=None, index_close=None,
            )
        )
    if detect:
        denominator.append_detections(market, det.session, [
            ScoredDetection(
                symbol=symbol, detection=det,
                score=seven_dimension_score(det, prior_move=False),
                star_rank=1, not_taken=False, rs_line=rs_line,
                relative_move=relative_move,
            )
        ])
    return det


def _figures(store, denominator, market="US", **kw):
    return figures_for_market(store, denominator, market, DEFAULT_CONTRACT, **kw)


def _year(figures, year: int):
    (row,) = [y for y in figures.years if y.year == year]
    return row


# -- the entry, and why it never became a trade -------------------------------


def test_an_entry_records_why_it_never_became_a_trade(store):
    """The five ways an entry ends, and they are not interchangeable.

    ``simulate_arm`` returns ``None`` for all of them, which is right for a
    simulator and useless for a figure: "the next session did not break" is a
    resolved miss and belongs in the trigger denominator, while "the bars end
    before the session that would decide it" is the window's edge and does not.
    Folding the two together deflates the trigger share by however many detections
    the window happened to end on.
    """
    win = _fig_bars(date(2020, 1, 1), _FIG_FLAT + _FIG_WIN)
    det = _fig_detection(win, "BASE")

    assert entry(win, det).outcome == ENTRY_FILLED
    # Bar 40 broke, and the market never opened again to fill it.
    assert entry(win[:41], det).outcome == ENTRY_UNFILLED
    # The bars end on the detection itself: nothing has decided the break yet.
    assert entry(win[:40], det).outcome == ENTRY_PENDING
    # The deciding session closed under the trigger. A resolved miss.
    flat = _fig_bars(date(2020, 1, 1), _FIG_FLAT + _FIG_NO_BREAK)
    assert entry(flat, _fig_detection(flat, "BASE")).outcome == ENTRY_NO_BREAK
    # The detection's own session is not in the bars at all.
    assert entry(win[45:], det).outcome == ENTRY_UNDECIDABLE


def test_a_filled_entry_carries_the_prices_every_arm_shares(store):
    """The entry *is* the shared part: trigger, break, fill, stop and stop width.

    #190 pinned that the three arms agree on these; this pins that they agree
    because there is one entry, not because three code paths happen to compute the
    same numbers.
    """
    bars = _fig_bars(date(2020, 1, 1), _FIG_FLAT + _FIG_WIN)
    det = _fig_detection(bars, "BASE")

    e = entry(bars, det)
    trade = simulate_arm(bars, det, market="US", contract=DEFAULT_CONTRACT, arm=ARM_B)

    assert e.trigger == trade.trigger
    assert e.break_signal == trade.break_signal
    assert e.fill == trade.entry
    assert e.stop_price == trade.stop_price
    assert e.stop_width == trade.stop_width
    assert e.price_scale == trade.price_scale


# -- detections per session, per market and per year --------------------------


def test_detections_per_session_is_reported_per_market_and_per_year(
    store, denominator
):
    """Per market and per year, never pooled only. IDX magnitudes are not US
    magnitudes and a window holding a crash and a mania is not described by a
    single number that fits neither."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "US", "BBB", date(2021, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "IDX", "CCC.JK", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    us = _figures(store, denominator, "US")
    idx = _figures(store, denominator, "IDX")

    assert [y.year for y in us.years] == [2020, 2021]
    assert [y.year for y in idx.years] == [2020]
    # Two names over 2020 and 2021, one detection each, on their own sessions.
    assert _year(us, 2020).detections == 1
    assert _year(us, 2021).detections == 1
    assert _year(us, 2020).sessions == FIG_SESSIONS
    assert _year(us, 2020).detections_per_session == pytest.approx(1 / FIG_SESSIONS)


def test_burn_in_sessions_are_excluded_from_every_figure(store, denominator):
    """A warm-up session is persisted and never measured. A figure that counted
    them would rest on an unsettled chain — and would report a detection the run
    itself declines to measure."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN, burn_in=True)
    _seed_figure_name(store, denominator, "US", "BBB", date(2021, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    us = _figures(store, denominator, "US")

    assert [y.year for y in us.years] == [2021]
    assert us.detections == 1


# -- the share that trigger ---------------------------------------------------


def test_the_share_of_detections_that_trigger_is_reported(store, denominator):
    """One name breaks through its trigger and one does not, so the share is a
    half — the figure the reference study could never produce, because a setup he
    declined was never recorded at all."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "US", "BBB", date(2020, 6, 1),
                      _FIG_FLAT + _FIG_NO_BREAK)

    us = _figures(store, denominator, "US")

    assert us.triggered == Share(2 - 1, 2)
    assert us.triggered.rate == 0.5


def test_a_detection_the_bars_cannot_answer_is_not_counted_as_a_miss(
    store, denominator
):
    """Undecidable and pending detections leave the trigger denominator entirely.

    A detection sitting on the last session of the window has not failed to
    trigger; nothing has asked it yet. Counting it as a miss would deflate the
    trigger share by however many detections the window happened to end on, in the
    direction that makes the detector look worse — which is the direction nobody
    investigates.
    """
    det = _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                            _FIG_FLAT + _FIG_WIN)
    # A second detection on the store's very last session: undecided, not missed.
    last = _fig_bars(date(2020, 1, 1), _FIG_FLAT + _FIG_WIN)[-1].session
    pending = dataclasses.replace(det, symbol="AAA", session=last)
    denominator.append_detections("US", last, [
        ScoredDetection(
            symbol="AAA", detection=pending,
            score=seven_dimension_score(pending, prior_move=False),
            star_rank=1, not_taken=False, rs_line=False, relative_move=None,
        )
    ])

    us = _figures(store, denominator, "US")

    assert us.detections == 2
    assert us.triggered == Share(1, 1)
    assert us.undecided == 1


# -- precision ----------------------------------------------------------------


def test_the_share_reaching_a_favourable_outcome_is_the_precision_figure(
    store, denominator
):
    """Precision at last: of every setup the detector named and the bars answered,
    the share that made money. Three names — one wins, one is stopped out, one
    never breaks — so one detection in three reached a favourable outcome."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "US", "BBB", date(2020, 6, 1),
                      _FIG_FLAT + _FIG_LOSS)
    _seed_figure_name(store, denominator, "US", "CCC", date(2021, 1, 1),
                      _FIG_FLAT + _FIG_NO_BREAK)

    us = _figures(store, denominator, "US")
    arm_b = us.arms[ARM_B]

    assert arm_b.favourable == 1
    assert arm_b.precision == Share(1, 3)
    # The win rate is a different question with a different denominator: of the
    # trades that were *taken*, how many paid. Conflating the two would report a
    # detector's precision as if it were a trader's hit rate.
    assert arm_b.win_rate == Share(1, 2)


def test_the_trigger_share_and_precision_are_reported_per_year_too(
    store, denominator
):
    """Per market *and* per year, never pooled only. A window holding a crash and a
    mania is not described by a single number that fits neither — and pooling is
    how a year the method lost money in disappears into a decade it made money in.
    """
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "US", "BBB", date(2021, 1, 1),
                      _FIG_FLAT + _FIG_LOSS)

    us = _figures(store, denominator, "US")

    assert _year(us, 2020).arms[ARM_B].precision == Share(1, 1)
    assert _year(us, 2021).arms[ARM_B].precision == Share(0, 1)
    assert _year(us, 2020).triggered == Share(1, 1)
    # And the pooled figure is beside them, never instead of them.
    assert us.arms[ARM_B].precision == Share(1, 2)
    printed = format_figures(figures_report(DEFAULT_CONTRACT, [us]))
    assert "precision B" in printed


def test_a_trade_still_open_at_the_end_of_the_window_is_never_a_loss(
    store, denominator
):
    """An open trade has no outcome, so it leaves precision's denominator.

    Closing it at the last available close would invent an exit the rules never
    gave — systematically, for every name still running when the window ends. It
    is reported as unresolved instead, which is the honest shape: a question the
    window was too short to answer.
    """
    # The run-up with no roll-over: the trail never signals and the bars run out.
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + [110.0, 111.0, 118.0, 124.0, 130.0])

    us = _figures(store, denominator, "US")
    arm_b = us.arms[ARM_B]

    assert us.triggered == Share(1, 1)
    assert arm_b.open_at_end == 1
    assert arm_b.precision == Share(0, 0)
    assert arm_b.precision.rate is None


def test_precision_is_reported_per_arm_because_it_depends_on_the_exit(
    store, denominator
):
    """The arms share one entry and one stop, so the trigger share is one figure
    across all three — and precision is not. An exit is what turns a break into a
    favourable outcome or an unfavourable one, so a single precision figure would
    be a claim about an exit it never named."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    us = _figures(store, denominator, "US")

    assert set(us.arms) == {ARM_A, ARM_B, ARM_C}
    # One entry, so the trigger share is one figure and not three.
    assert us.triggered == Share(1, 1)
    # And a precision per arm, each measured against its own answered count: an arm
    # still holding the position has answered nothing yet, whatever the arm beside
    # it did. The entry is shared, so `filled` cannot differ; `answered` can.
    assert us.arms[ARM_B].filled == us.arms[ARM_C].filled == 1
    assert [us.arms[a].answered for a in (ARM_A, ARM_B, ARM_C)] == [1, 1, 1]


def test_the_favourable_rule_rides_on_the_result(store, denominator):
    """What counts as favourable is a threshold, and a threshold nobody can read
    off the result is one a later run can quietly move."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    report = figures_report(DEFAULT_CONTRACT, [_figures(store, denominator, "US")])

    assert report["favourable_rule"] == FAVOURABLE_RULE
    assert FAVOURABLE_RULE in format_figures(report)


def test_precision_is_a_before_cost_figure_and_the_report_says_so(
    store, denominator
):
    """Costs are #191's, and a precision figure computed before them overstates.

    A caveat a reader has to remember is one a reader forgets, so it rides on the
    payload and is printed beside the number rather than living in a commit
    message.
    """
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    report = figures_report(DEFAULT_CONTRACT, [_figures(store, denominator, "US")])

    assert report["costs_applied"] is False
    assert "before costs" in format_figures(report)


# -- coverage -----------------------------------------------------------------


def test_every_figure_carries_the_coverage_count_it_was_measured_against(
    store, denominator
):
    """A rate whose denominator is not printed is a rate nobody can check, and a
    ``0/0`` reported as ``0.0`` is a claim the data never made."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_NO_BREAK)

    us = _figures(store, denominator, "US")

    assert us.triggered.of == 1
    assert Share(0, 0).rate is None
    assert Share(1, 4).rate == 0.25
    # Every rate in the printed report arrives with its own coverage beside it.
    printed = format_figures(figures_report(DEFAULT_CONTRACT, [us]))
    assert "0 of 1" in printed


# -- the SMA50 overlap --------------------------------------------------------


def test_the_sma50_overlap_is_stated_wherever_counts_are_reported(
    store, denominator
):
    """Detection counts fall against an unfiltered run because the contract's
    SMA50 gate overlaps the detector's own trend logic. That is the gate working,
    not the detector becoming more selective — and a reader who is not told
    conflates the two."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    report = figures_report(DEFAULT_CONTRACT, [_figures(store, denominator, "US")])

    assert report["sma50_overlap"] == SMA50_OVERLAP_NOTE
    assert SMA50_OVERLAP_NOTE in format_figures(report)


# -- the plot, and the years that collapse ------------------------------------


def test_a_year_whose_detection_count_collapses_is_flagged(store, denominator):
    """A count that collapses reads as a quiet market until someone looks, so the
    row says so rather than leaving it for a reader to spot in a column."""
    # Three years of a full calendar and a healthy field, then a fourth with the
    # same calendar and an empty one. Nothing about the year is short — only the
    # count is, which is what a data hole looks like from the report.
    for year in (2019, 2020, 2021, 2022):
        for month in (1, 4, 7, 10):
            _seed_figure_name(
                store, denominator, "US", f"N{year}{month}", date(year, month, 1),
                _FIG_FLAT + _FIG_WIN, detect=year != 2022,
            )

    us = _figures(store, denominator, "US")

    assert _year(us, 2021).detections_collapsed is False
    assert _year(us, 2022).detections_collapsed is True
    # The year is not short — only its field is, which is the confusion the two
    # flags exist to keep apart.
    assert _year(us, 2022).sessions == _year(us, 2021).sessions
    assert _year(us, 2022).sessions_collapsed is False
    assert any("detections" in f for f in _year(us, 2022).flags)


def test_a_year_whose_session_count_collapses_is_flagged_as_a_data_hole(
    store, denominator
):
    """Sessions missing from the middle of a window are a hole in the store, and
    a rate computed over them is a rate over a year that never happened."""
    for year in (2019, 2021, 2022):
        for month in (1, 4, 7, 10):
            _seed_figure_name(
                store, denominator, "US", f"N{year}{month}", date(year, month, 1),
                _FIG_FLAT + _FIG_WIN,
            )
    # 2020 is an interior year holding one short stretch and nothing else.
    _seed_figure_name(store, denominator, "US", "HOLE", date(2020, 6, 1),
                      _FIG_FLAT + _FIG_WIN)

    us = _figures(store, denominator, "US")

    assert _year(us, 2020).sessions_collapsed is True
    assert _year(us, 2021).sessions_collapsed is False
    assert any("session" in f for f in _year(us, 2020).flags)


def test_a_partial_year_at_the_edge_of_the_window_is_not_a_hole(store, denominator):
    """The window opens and closes mid-year by design, so its first and last years
    are short on purpose. Flagging them would cry wolf on every run and teach a
    reader to skip the one flag that means something."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 11, 1),
                      _FIG_FLAT + _FIG_WIN)
    for month in (1, 4, 7, 10):
        _seed_figure_name(store, denominator, "US", f"M{month}", date(2021, month, 1),
                          _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "US", "ZZZ", date(2022, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    us = _figures(store, denominator, "US")

    assert _year(us, 2020).sessions_collapsed is False
    assert _year(us, 2022).sessions_collapsed is False


def test_the_collapse_rules_ride_on_the_result_rather_than_on_a_reader(
    store, denominator
):
    """A flag whose rule is not printed is a flag a reader has to trust."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    report = figures_report(DEFAULT_CONTRACT, [_figures(store, denominator, "US")])

    assert report["collapse_rule"]["detections_fraction"] == DETECTION_COLLAPSE_FRACTION
    assert report["collapse_rule"]["sessions_fraction"] == SESSION_COLLAPSE_FRACTION


def test_detections_per_session_is_plotted_across_the_window(store, denominator):
    """The plot is the deliverable, not the table beside it: a collapsing count is
    a shape a reader sees at a glance and a number a reader has to compare."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "US", "BBB", date(2021, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    printed = format_figures(
        figures_report(DEFAULT_CONTRACT, [_figures(store, denominator, "US")])
    )

    assert "2020" in printed and "2021" in printed
    # One bar per year, drawn from the year's own detections-per-session.
    assert printed.count("█") > 0


def test_a_month_the_store_never_covered_plots_as_a_hole_not_a_quiet_month(
    store, denominator
):
    """A yearly mean hides a missing quarter — it drops by a quarter and looks like
    a slow year. The monthly series is where a hole is actually visible, so a month
    with no sessions at all draws differently from a month with sessions and no
    detections."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "US", "BBB", date(2020, 10, 1),
                      _FIG_FLAT + _FIG_WIN)

    printed = format_figures(
        figures_report(DEFAULT_CONTRACT, [_figures(store, denominator, "US")])
    )

    assert HOLE_MARK in printed


# -- the result, and the command ----------------------------------------------


def test_the_figures_report_carries_the_contract_that_produced_it(
    store, denominator
):
    """Every figure the package emits carries its contract, so two runs under
    different contracts are distinguishable from their serialised output alone."""
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)

    report = figures_report(DEFAULT_CONTRACT, [_figures(store, denominator, "US")])

    assert report["contract"] == DEFAULT_CONTRACT.to_dict()
    assert [m["market"] for m in report["markets"]] == ["US"]


def test_the_figures_cli_reports_and_writes_the_denominator_figures(
    tmp_path, capsys
):
    """One command reproduces the figures off a persisted denominator, and writes
    the machine-readable result beside the printed one."""
    path = tmp_path / "backtest_us.duckdb"
    store = Store.open(path)
    denominator = DenominatorStore.open(denominator_path(path))
    denominator.stamp(DEFAULT_CONTRACT)
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    store.close()
    denominator.close()
    out_json = tmp_path / "figures.json"

    code = figures_main([
        "--store", str(path), "--market", "US", "--out-json", str(out_json)
    ])

    assert code == 0
    printed = capsys.readouterr().out
    assert SMA50_OVERLAP_NOTE in printed
    written = json.loads(out_json.read_text())
    assert written["contract"] == DEFAULT_CONTRACT.to_dict()
    assert written["markets"][0]["market"] == "US"


# -- what the #193 review found unguarded -------------------------------------


def test_a_year_the_store_missed_entirely_still_gets_a_row_and_a_flag(
    store, denominator
):
    """The worst hole is the one a year-keyed report cannot see.

    A year with no sessions at all contributes no rows to group by, so a report
    built from the years *present* would give it no line, no flag and no weight in
    the median — and the largest data hole the criterion exists to catch would be
    the single case it could not. It survives only as a blank stretch in the
    monthly grid, which is not a flag.
    """
    for year in (2019, 2020, 2022):
        for month in (1, 4, 7, 10):
            _seed_figure_name(
                store, denominator, "US", f"N{year}{month}", date(year, month, 1),
                _FIG_FLAT + _FIG_WIN,
            )

    us = _figures(store, denominator, "US")

    assert [y.year for y in us.years] == [2019, 2020, 2021, 2022]
    assert _year(us, 2021).sessions == 0
    assert _year(us, 2021).sessions_collapsed is True
    # And it makes no claim it cannot support: no sessions is no rate, never zero.
    assert _year(us, 2021).detections_per_session is None
    assert _year(us, 2021).detections_collapsed is False


def test_a_hole_in_the_windows_first_year_is_flagged_like_any_other(
    store, denominator
):
    """The edge exemption this first shipped with was itself a hole.

    Exempting the window's opening and closing years from the sessions flag reads
    as generosity — they are short by design — but a store that lost three quarters
    of the opening year drops its sessions *and* its detections together, so the
    per-session rate barely moves and the detections flag stays silent too. Judging
    the density against the span the window actually covers removes the by-design
    shortness without removing the flag.
    """
    # 2019 opens the window on 1 January and then holds one stretch and nothing
    # else — the calendar says a year, the store holds two months of it.
    _seed_figure_name(store, denominator, "US", "HOLE", date(2019, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    for year in (2020, 2021, 2022):
        for month in (1, 4, 7, 10):
            _seed_figure_name(
                store, denominator, "US", f"N{year}{month}", date(year, month, 1),
                _FIG_FLAT + _FIG_WIN,
            )

    us = _figures(store, denominator, "US")

    assert _year(us, 2019).sessions_collapsed is True
    # Not because its field thinned — the rate is ordinary, which is exactly why
    # the detections flag cannot stand in for the sessions one.
    assert _year(us, 2019).detections_collapsed is False


def test_a_year_the_window_only_half_covers_is_not_a_hole(store, denominator):
    """The other half of the same rule. A window that opens in November holds two
    months of that year because it opened in November, and a flag that fired on it
    would fire on every run — which teaches a reader to skip the one that means
    something."""
    _seed_figure_name(store, denominator, "US", "LATE", date(2019, 11, 1),
                      _FIG_FLAT + _FIG_WIN)
    for year in (2020, 2021):
        for month in (1, 4, 7, 10):
            _seed_figure_name(
                store, denominator, "US", f"N{year}{month}", date(year, month, 1),
                _FIG_FLAT + _FIG_WIN,
            )

    us = _figures(store, denominator, "US")

    assert _year(us, 2019).sessions < _year(us, 2020).sessions
    assert _year(us, 2019).sessions_collapsed is False


def test_a_break_the_window_ended_before_filling_is_counted_and_named(
    store, denominator
):
    """It triggered, and no session opened to fill it.

    That detection is in the trigger share — it *did* trade through its trigger —
    and in no arm's precision denominator, because no position was ever taken. Left
    unnamed it would sit in neither bucket and simply vanish from the arithmetic,
    which is how a population leaves a report without anyone noticing it went.
    """
    # The bars end on the session that decides the break.
    _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                      _FIG_FLAT + [110.0])

    us = _figures(store, denominator, "US")

    assert us.unfilled == 1
    assert us.triggered == Share(1, 1)
    assert us.arms[ARM_B].filled == 0
    assert us.arms[ARM_B].precision == Share(0, 0)


def test_every_detection_lands_in_exactly_one_bucket(store, denominator):
    """The four buckets are the whole population, and they add up.

    A bucket that does not reconcile is a population going somewhere unreported,
    and a rate computed over the rest is a rate over a denominator nobody can
    reconstruct.
    """
    _seed_figure_name(store, denominator, "US", "WINS", date(2020, 1, 1),
                      _FIG_FLAT + _FIG_WIN)
    _seed_figure_name(store, denominator, "US", "NONE", date(2020, 4, 1),
                      _FIG_FLAT + _FIG_NO_BREAK)
    _seed_figure_name(store, denominator, "US", "EDGE", date(2020, 8, 1),
                      _FIG_FLAT + [110.0])

    us = _figures(store, denominator, "US")

    assert us.detections == 3
    assert (us.no_break, us.unfilled, us.undecided) == (1, 1, 0)
    assert us.arms[ARM_B].filled == 1
    assert all(us.reconciles(arm) for arm in us.arms)


def test_the_price_scale_count_rides_on_the_figures_it_qualifies(
    store, denominator
):
    """The flag is reported beside every result built on it, and precision is built
    on entries priced in absolute terms.

    Yahoo's unlabelled rights-issue rescale is not visible in the R geometry, which
    is in ADR units and immune — but it is visible in the one absolute comparison
    the entry cannot avoid, and a precision figure quoted without the count is a
    figure whose inputs nobody checked.
    """
    det = _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                            _FIG_FLAT + _FIG_WIN)
    # The same detection, re-persisted with a close three times the bar's: a
    # rescale, not a price that moved.
    rescaled = dataclasses.replace(det, close=det.close * 3)
    denominator._cursor().execute(
        "UPDATE denominator_detections SET close = ? WHERE symbol = ?",
        [rescaled.close, "AAA"],
    )

    us = _figures(store, denominator, "US")
    report = figures_report(DEFAULT_CONTRACT, [us])

    assert us.price_scale_dropped == len(us.arms)
    assert report["markets"][0]["price_scale_dropped"] == len(us.arms)
    assert "price-scale flag would drop" in format_figures(report)


# -- pricing the regime posture (issue #192) -----------------------------------
#
# Phase 5's most product-relevant cell. The app prints "sit out" for HOSTILE and
# "reduced" for CHOPPY today, on no measured basis at all; this section is the
# measurement. Regime is a **conditioning variable and never a filter**, so every
# state trades and each one's expectancy is measured instead of assumed.
#
# Four claims are load-bearing, and each has a test that fails loudly on drift:
#
#   * **Nothing is excluded by regime.** Every trade lands in exactly one cell,
#     including the ones whose state is undefined, and the cells add back up.
#   * **The state is the app's own, read at t−1.** The detection session is the
#     night the candidate was listed with its posture; the break comes the session
#     after it. Reading the entry session instead would condition on a state
#     nobody had yet.
#   * **The postures are priced, not asserted.** The HOSTILE counterfactual is
#     computed in R, and CHOPPY's "reduced" is answered against FRIENDLY's
#     measured expectancy rather than against the word.
#   * **Breadth is reported and never conditioned on.** It is the column
#     survivorship corrupts most, and in a backtest the corruption is worse.

from typing import get_args

from backtest.contract import REGIME_ROLE_KEY, REGIME_SOURCE_KEY
from backtest.posture import (
    APP_STATES,
    REGIME_ROLE,
    REGIME_SOURCE,
    REPORTED_STATES,
    STATE_READ_AT,
    STATE_UNDEFINED,
    VERDICT_EARNED,
    VERDICT_REFUTED,
    VERDICT_TOO_THIN,
    VERDICT_UNDECIDED,
    RegimeSpine,
    bootstrap_difference,
    breadth_summary,
    check_regime_role,
    check_regime_source,
    choppy_reduced,
    follow_through_summary,
    for_market,
    format_posture,
    hostile_counterfactual,
    market_posture,
    posture_cell,
    posture_report,
    spine_for_market,
    state_of,
)
from screener.regime import RegimeState
from screener.regime import posture as app_posture


def _reading(state, *, breadth=0.5):
    """One session's regime observation, authored rather than computed."""
    return RegimeReading(
        state=state, breadth=breadth, broke_out=None, index_close=100.0
    )


def _spine(market, states, *, breadth=0.5):
    """A market's measured sessions and the state showing on each."""
    return RegimeSpine(
        market=market,
        readings={
            session: _reading(state, breadth=breadth)
            for session, state in states.items()
        },
    )


def _ptrade(symbol, session, r, *, market="US", arm=ARM_B):
    """One arm-B trade, detected on ``session``, whose before-cost R is ``r``.

    The entry sits **two sessions after** the detection, which is what the
    simulator's own mechanic produces: the break comes on the session after the
    detection and the fill on the open after that. The gap is what makes the
    t−1 test meaningful — a fixture whose entry and detection shared a date could
    not tell the two readings apart.
    """
    base = _mtrade(symbol, session.year, r, market=market, arm=arm,
                   month=session.month)
    return dataclasses.replace(
        base,
        detection_session=session,
        entry=Decision(session=session + timedelta(days=2), price=base.entry.price),
    )


def _cohort(sessions, states, rs, *, market="US", prefix=""):
    """Trades and a spine together: one symbol per R, so clusters are not one name."""
    trades = [
        _ptrade(f"{prefix}{i:02d}", session, r, market=market)
        for i, (session, r) in enumerate(zip(sessions, rs))
    ]
    spine = _spine(market, dict(zip(sessions, states)))
    return trades, spine


def _sessions(year, n):
    return [date(year, 3, 1) + timedelta(days=i) for i in range(n)]


def test_the_regime_source_and_role_are_the_contracts_own(store):
    """The state this module conditions on, and the role it plays, are read off the
    contract rather than restated beside it.

    A contract that made regime a filter while the code still measured every state
    would leave a run whose contract and behaviour disagree while both look right —
    and "nothing is excluded by regime" is precisely the claim the cell exists to
    hold fixed.
    """
    assert REGIME_SOURCE == DEFAULT_CONTRACT.value(REGIME_SOURCE_KEY)
    assert REGIME_ROLE == DEFAULT_CONTRACT.value(REGIME_ROLE_KEY)
    check_regime_source(DEFAULT_CONTRACT)
    check_regime_role(DEFAULT_CONTRACT)

    filtered = RunContract(
        contract_version=DEFAULT_CONTRACT.contract_version,
        label=DEFAULT_CONTRACT.label,
        cells=tuple(
            Cell(key=c.key, value="filter_hostile_out",
                 justification=c.justification)
            if c.key == REGIME_ROLE_KEY else c
            for c in DEFAULT_CONTRACT.cells
        ),
    )
    with pytest.raises(ContractDrift):
        check_regime_role(filtered)


def test_the_state_is_the_one_showing_on_the_detection_session(store):
    """t−1, which is what the detection session *is*.

    The candidate is listed on the night of the detection with the posture the app
    printed beside it; the break comes on the session after and the fill on the one
    after that. Reading the state off the entry session would condition on a
    reading nobody had when the trade was taken — look-ahead through the
    conditioning variable rather than through the price.
    """
    detected = date(2016, 3, 1)
    trade = _ptrade("AAA", detected, 1.0)
    spine = _spine("US", {detected: "FRIENDLY", trade.entry.session: "HOSTILE"})

    assert trade.entry.session != detected
    assert state_of(spine, trade) == "FRIENDLY"
    assert STATE_READ_AT == "detection_session"


def test_a_trade_whose_session_has_no_state_is_undefined_and_still_counted(store):
    """Below the regime's 25-bar warm-up the state is undefined, not defaulted — and
    a trade taken there is still a trade.

    Bucketing it into CHOPPY would invent a reading, and dropping it would be the
    one thing this module promises never to do: regime excludes nothing.
    """
    warm = date(2012, 3, 1)
    absent = date(2012, 3, 2)
    trades = [_ptrade("AAA", warm, 1.0), _ptrade("BBB", absent, -1.0)]
    spine = _spine("US", {warm: None})

    assert state_of(spine, trades[0]) == STATE_UNDEFINED
    assert state_of(spine, trades[1]) == STATE_UNDEFINED
    body = market_posture(DEFAULT_CONTRACT, trades, spine)
    undefined = next(
        s for s in body["states"] if s["state"] == STATE_UNDEFINED
    )
    assert undefined["windows"][0]["trades"] == 2


def test_every_trade_lands_in_exactly_one_cell_and_regime_excludes_nothing(store):
    """The partition, checked as arithmetic rather than asserted in prose.

    Three states and the undefined bucket cover every trade, and the counts add
    back up to the total handed in. That sum is the whole of "nothing is excluded
    by regime" — a filter anywhere upstream would show as cells that no longer
    total.
    """
    sessions = _sessions(2016, 4)
    trades, spine = _cohort(
        sessions,
        ["FRIENDLY", "CHOPPY", "HOSTILE", None],
        [2.0, -1.0, 0.5, 1.0],
    )
    body = market_posture(DEFAULT_CONTRACT, trades, spine)

    per_cell = {s["state"]: s["windows"][0]["trades"] for s in body["states"]}
    assert per_cell == {
        "FRIENDLY": 1, "CHOPPY": 1, "HOSTILE": 1, STATE_UNDEFINED: 1
    }
    assert sum(per_cell.values()) == len(trades)
    assert body["conditioning"]["excluded_by_regime"] == 0
    assert body["conditioning"]["trades"] == len(trades)
    assert set(per_cell) == set(REPORTED_STATES)


def test_a_state_with_no_trades_still_reports_its_zero(store):
    """A state nobody traded in is a measurement, not an absent row.

    An empty HOSTILE cell that simply vanished would read as a market that never
    saw a hostile tape, which is a different and much stronger claim than one that
    threw no signal there.
    """
    sessions = _sessions(2016, 2)
    trades, spine = _cohort(sessions, ["FRIENDLY", "FRIENDLY"], [1.0, 2.0])
    body = market_posture(DEFAULT_CONTRACT, trades, spine)

    hostile = next(s for s in body["states"] if s["state"] == "HOSTILE")
    assert hostile["windows"][0]["trades"] == 0
    assert hostile["windows"][0]["expectancy_r"] is None


def test_every_cell_shows_n_even_when_it_is_too_thin_to_read(store):
    """n regardless, so a cell too thin to read is visible as thin rather than
    quoted as a result.

    Two symbols is below the bootstrap's cluster floor, so the cell reports no
    interval — and says so where a reader looks for one.
    """
    sessions = _sessions(2016, 2)
    trades, spine = _cohort(sessions, ["HOSTILE", "HOSTILE"], [3.0, 4.0])
    body = market_posture(DEFAULT_CONTRACT, trades, spine)

    hostile = next(s for s in body["states"] if s["state"] == "HOSTILE")
    cell = hostile["windows"][0]
    assert cell["trades"] == 2 and cell["closed"] == 2
    assert cell["expectancy_r"] is not None
    assert cell["bootstrap"]["ci_low"] is None
    assert cell["bootstrap"]["suppressed"]

    printed = format_posture(
        posture_report(DEFAULT_CONTRACT, trades, {"US": spine}, markets=["US"])
    )
    assert "n=2" in printed
    assert "too thin" in printed


def test_the_states_report_the_2020_21_excluded_window_beside_the_full_one(store):
    """That tape rewarded momentum nearly everywhere, and it is FRIENDLY it would
    inflate — so a FRIENDLY expectancy that rests on it alone is a figure about the
    tape and not about the state."""
    mania = date(2020, 3, 1)
    ordinary = date(2016, 3, 1)
    trades = [_ptrade("AAA", mania, 5.0), _ptrade("BBB", ordinary, 1.0)]
    spine = _spine("US", {mania: "FRIENDLY", ordinary: "FRIENDLY"})

    body = market_posture(DEFAULT_CONTRACT, trades, spine)
    friendly = next(s for s in body["states"] if s["state"] == "FRIENDLY")
    full, excluded = friendly["windows"]

    assert full["label"].endswith(FULL_WINDOW)
    assert excluded["label"].endswith(EXCLUDED_YEARS_WINDOW)
    assert full["trades"] == 2 and excluded["trades"] == 1
    assert excluded["expectancy_r"] < full["expectancy_r"]
    assert excluded["excluded_years"] == list(EXCLUDED_YEARS)


def test_us_and_idx_never_pool_and_there_is_no_top_level_expectancy(store):
    """findings §8 measured that magnitudes do not transfer between the markets, so
    a pooled figure would be a number about neither — and the way to stop one being
    quoted is for it never to have been computed."""
    us_sessions = _sessions(2016, 2)
    idx_sessions = _sessions(2017, 2)
    us, us_spine = _cohort(us_sessions, ["HOSTILE"] * 2, [1.0, 2.0], prefix="U")
    idx, idx_spine = _cohort(idx_sessions, ["HOSTILE"] * 2, [-1.0, -1.0],
                             market="IDX", prefix="I")

    report = posture_report(
        DEFAULT_CONTRACT, us + idx,
        {"US": us_spine, "IDX": idx_spine}, markets=["US", "IDX"],
    )

    assert [m["market"] for m in report["markets"]] == ["US", "IDX"]
    assert "expectancy_r" not in report
    # The cohort refusal is inherited, and it is structural: a cell cannot be
    # built across two markets even by a caller that wants one.
    with pytest.raises(ValueError):
        posture_cell(DEFAULT_CONTRACT, us + idx, market="US", state="HOSTILE",
                     label=FULL_WINDOW)


def test_a_cell_cannot_be_conditioned_on_breadth(store):
    """Breadth is descriptive and never a cohort key, and that is enforced where the
    cohort is built rather than remembered at the call site.

    It is the measure survivorship corrupts most directly, and in a backtest the
    corruption is worse rather than better, because the missing names are
    disproportionately the ones that later died.
    """
    trade = _ptrade("AAA", date(2016, 3, 1), 1.0)
    with pytest.raises(ValueError):
        posture_cell(DEFAULT_CONTRACT, [trade], market="US", state=0.42,
                     label=FULL_WINDOW)
    with pytest.raises(ValueError):
        posture_cell(DEFAULT_CONTRACT, [trade], market="US",
                     state="breadth_above_median", label=FULL_WINDOW)


def test_breadth_is_reported_and_carries_its_survivorship_warning(store):
    """Reported, because the plan asks for it; warned, because a breadth number
    read as an equal of the state is the corruption arriving through the report."""
    sessions = _sessions(2016, 3)
    spine = _spine("US", dict(zip(sessions, ["FRIENDLY"] * 3)), breadth=0.4)

    summary = breadth_summary(spine)
    assert summary["sessions"] == 3
    assert summary["median"] == pytest.approx(0.4)
    assert summary["basis"] == BREADTH_BASIS
    assert "survivorship" in summary["warning"]
    assert summary["conditioned_on"] is False


def test_the_hostile_counterfactual_prices_what_sitting_out_would_have_cost(store):
    """The number the product actually needs, in R.

    HOSTILE trades that made money mean the posture the app prints would have cost
    the book exactly what they earned — and the counterfactual says so with a sign
    rather than leaving a reader to infer it.
    """
    sessions = _sessions(2016, 4)
    trades, spine = _cohort(
        sessions, ["HOSTILE", "HOSTILE", "FRIENDLY", "FRIENDLY"],
        [2.0, 3.0, 1.0, 1.0],
    )
    cf = hostile_counterfactual(DEFAULT_CONTRACT, trades, spine)

    assert cf["posture"] == app_posture("HOSTILE") == "sit out"
    assert cf["closed"] == 2
    assert cf["total_r"] > 0
    assert cf["delta_total_r"] == pytest.approx(-cf["total_r"])
    assert cf["effect"] == "cost"
    assert cf["book"]["all"]["closed"] == 4
    assert cf["book"]["without_hostile"]["closed"] == 2


def test_sitting_out_hostile_saves_when_the_state_lost_money(store):
    """The other direction, and the one the app's word assumes: a HOSTILE book that
    lost means sitting it out saves, and the saving is the loss it avoided."""
    sessions = _sessions(2016, 4)
    trades, spine = _cohort(
        sessions, ["HOSTILE", "HOSTILE", "FRIENDLY", "FRIENDLY"],
        [-1.0, -1.0, 2.0, 2.0],
    )
    cf = hostile_counterfactual(DEFAULT_CONTRACT, trades, spine)

    assert cf["total_r"] < 0
    assert cf["delta_total_r"] > 0
    assert cf["effect"] == "saved"
    assert cf["book"]["without_hostile"]["expectancy_r"] > (
        cf["book"]["all"]["expectancy_r"]
    )


def test_sit_out_is_earned_only_where_hostile_expectancy_is_measurably_negative(
    store
):
    """The verdict is the interval's, not the mean's.

    A hostile cohort that lost across enough independent names earns the word; one
    that made money refutes it; one whose interval straddles zero leaves it
    undecided — which is still an answer, and the one the app has today.
    """
    losing_sessions = _sessions(2016, 8)
    losing, losing_spine = _cohort(
        losing_sessions, ["HOSTILE"] * 8, [-1.0] * 8, prefix="L"
    )
    assert hostile_counterfactual(
        DEFAULT_CONTRACT, losing, losing_spine
    )["verdict"] == VERDICT_EARNED

    winning, winning_spine = _cohort(
        losing_sessions, ["HOSTILE"] * 8, [3.0] * 8, prefix="W"
    )
    assert hostile_counterfactual(
        DEFAULT_CONTRACT, winning, winning_spine
    )["verdict"] == VERDICT_REFUTED

    mixed_rs = [-3.0, 3.0, -2.5, 2.5, -2.0, 2.0, -1.0, 1.0]
    mixed, mixed_spine = _cohort(
        losing_sessions, ["HOSTILE"] * 8, mixed_rs, prefix="M"
    )
    assert hostile_counterfactual(
        DEFAULT_CONTRACT, mixed, mixed_spine
    )["verdict"] == VERDICT_UNDECIDED

    thin, thin_spine = _cohort(
        _sessions(2016, 2), ["HOSTILE"] * 2, [-1.0, -1.0], prefix="T"
    )
    assert hostile_counterfactual(
        DEFAULT_CONTRACT, thin, thin_spine
    )["verdict"] == VERDICT_TOO_THIN


def test_choppy_earns_reduced_only_against_friendlys_measured_expectancy(store):
    """'Reduced' is a *relative* posture, so it is judged against FRIENDLY rather
    than against zero — the question is whether the state is worse to trade, not
    whether it is unprofitable."""
    sessions = _sessions(2016, 16)
    states = ["CHOPPY"] * 8 + ["FRIENDLY"] * 8
    earned, earned_spine = _cohort(
        sessions, states, [-1.0] * 8 + [3.0] * 8, prefix="E"
    )
    verdict = choppy_reduced(DEFAULT_CONTRACT, earned, earned_spine)
    assert verdict["posture"] == app_posture("CHOPPY") == "reduced"
    assert verdict["verdict"] == VERDICT_EARNED
    assert verdict["delta_expectancy_r"] < 0

    flipped, flipped_spine = _cohort(
        sessions, states, [3.0] * 8 + [-1.0] * 8, prefix="F"
    )
    assert choppy_reduced(
        DEFAULT_CONTRACT, flipped, flipped_spine
    )["verdict"] == VERDICT_REFUTED

    thin, thin_spine = _cohort(
        _sessions(2016, 4), ["CHOPPY", "CHOPPY", "FRIENDLY", "FRIENDLY"],
        [-1.0, -1.0, 1.0, 1.0], prefix="T",
    )
    assert choppy_reduced(
        DEFAULT_CONTRACT, thin, thin_spine
    )["verdict"] == VERDICT_TOO_THIN


def test_the_difference_bootstrap_resamples_both_sides_by_cluster(store):
    """The difference of two means, with each side's clusters drawn whole.

    Resampling rows would let one name's fortnight of signals arrive as several
    independent observations on whichever side it sat, and would tighten the
    interval around the very comparison the posture turns on.
    """
    low = [(-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,), (-1.0,)]
    high = [(2.0,), (2.0,), (2.0,), (2.0,), (2.0,), (2.0,)]

    boot = bootstrap_difference(low, high)
    assert boot["difference"] == pytest.approx(-3.0)
    assert boot["ci_high"] < 0
    assert boot["clusters_a"] == 6 and boot["clusters_b"] == 6
    assert boot["cluster"] == BOOTSTRAP_CLUSTER

    thin = bootstrap_difference(low[:2], high)
    assert thin["ci_low"] is None and thin["suppressed"]


def test_the_posture_report_is_stamped_and_names_its_conditioning(store):
    """The contract travels with the result, and the report says in its own body
    that regime conditioned and never filtered."""
    sessions = _sessions(2016, 2)
    trades, spine = _cohort(sessions, ["HOSTILE", "FRIENDLY"], [1.0, 1.0])
    report = posture_report(
        DEFAULT_CONTRACT, trades, {"US": spine}, markets=["US"]
    )

    assert report["contract"] == DEFAULT_CONTRACT.to_dict()
    assert report["regime_source"] == REGIME_SOURCE
    assert report["regime_role"] == REGIME_ROLE
    assert report["arm"] == PRIMARY_ARM
    assert report["state_read_at"] == STATE_READ_AT


def test_the_posture_is_arm_bs_and_refuses_another_arms_trades(store):
    """The same refusal the headline carries, one level up: a posture priced on a
    mix of arms would report a number no arm produced."""
    trades = [
        dataclasses.replace(
            _ptrade("AAA", date(2016, 3, 1), 1.0), arm=ARM_A
        )
    ]
    with pytest.raises(ValueError):
        posture_cell(DEFAULT_CONTRACT, trades, market="US", state="HOSTILE",
                     label=FULL_WINDOW)


def test_the_printed_page_shows_every_state_with_its_n_and_both_verdicts(store):
    """The page a reader actually quotes from. Every state appears with its count
    whether or not it is readable, and the two postures the app prints are answered
    on the page rather than left in the payload."""
    sessions = _sessions(2016, 16)
    states = ["CHOPPY"] * 8 + ["FRIENDLY"] * 8
    trades, spine = _cohort(sessions, states, [-1.0] * 8 + [3.0] * 8)
    printed = format_posture(
        posture_report(DEFAULT_CONTRACT, trades, {"US": spine}, markets=["US"])
    )

    for state in REPORTED_STATES:
        assert state in printed
    assert "sit out" in printed and "reduced" in printed
    assert "survivorship" in printed
    assert "nothing is excluded by regime" in printed


def test_the_spine_is_built_off_the_persisted_denominator_sessions(
    store, denominator
):
    """The state comes from the rows the run already persisted, not from a second
    reading of the index — one computation of the regime, stored once.

    Burn-in sessions are out of the spine for the same reason they are out of the
    trades: a warm-up session is persisted and never measured.
    """
    denominator.stamp(DEFAULT_CONTRACT)
    measured = date(2016, 3, 2)
    warm = date(2016, 3, 1)
    for session, burn_in, state in ((warm, True, "FRIENDLY"),
                                    (measured, False, "HOSTILE")):
        denominator.append_session(
            SessionRow.of(
                "US", session, burn_in=burn_in, members=10, detections=1,
                regime=RegimeReading(
                    state=state, breadth=0.3, broke_out=None, index_close=99.0
                ),
            )
        )

    spine = spine_for_market(denominator, "US")

    assert set(spine.readings) == {measured}
    assert spine.readings[measured].state == "HOSTILE"
    trade = _ptrade("AAA", measured, 1.0)
    assert state_of(spine, trade) == "HOSTILE"


def test_the_posture_joins_a_simulated_trade_to_a_persisted_reading(
    store, denominator
):
    """The seam that matters: a trade the simulator produced, dated by a state the
    run persisted.

    Every other test here authors both sides so the arithmetic stays checkable;
    this one proves the two actually join on the session they agree about. The
    reading is persisted against the detection's own session — the night the
    candidate was listed — and the trade's entry lands two sessions later, so a
    join that reached for the entry instead would find no row at all and report a
    real trade as undefined.
    """
    denominator.stamp(DEFAULT_CONTRACT)
    bars = _sim_bars()
    det = _sim_detection(bars)
    trade = simulate_arm_b(bars, det, market="US", contract=DEFAULT_CONTRACT)
    denominator.append_session(
        SessionRow.of(
            "US", det.session, burn_in=False, members=10, detections=1,
            regime=RegimeReading(
                state="HOSTILE", breadth=0.25, broke_out=None, index_close=99.0
            ),
        )
    )

    spine = spine_for_market(denominator, "US")
    assert trade.entry.session > det.session
    assert state_of(spine, trade) == "HOSTILE"

    body = market_posture(DEFAULT_CONTRACT, [trade], spine)
    hostile = next(s for s in body["states"] if s["state"] == "HOSTILE")
    cell = hostile["windows"][0]

    assert cell["closed"] == 1
    assert cell["expectancy_r"] == pytest.approx(
        trade.r_multiple - cost_r(trade, DEFAULT_CONTRACT)
    )
    assert body["conditioning"]["excluded_by_regime"] == 0
    # The counterfactual is this one trade's, and it is the book's whole result:
    # sitting out HOSTILE here leaves nothing behind.
    cf = body["counterfactual"]
    assert cf["book"]["without_hostile"]["closed"] == 0
    assert cf["delta_total_r"] == pytest.approx(-cell["total_r"])


def test_the_reported_states_are_the_apps_own_plus_the_undefined_bucket(store):
    """The cells come from the app's own ``RegimeState``, not from a list retyped
    here.

    The module's whole claim is that it conditions on the state the product
    actually shows. A hardcoded list would break that claim quietly: a fourth state
    added to the app would fall into the undefined bucket and read as a warm-up
    hole rather than as a state nobody had thought to report.
    """
    assert APP_STATES == get_args(RegimeState)
    assert REPORTED_STATES == (*APP_STATES, STATE_UNDEFINED)
    # The two words the module prices are states the app really has, so a rename
    # in the app breaks this rather than silently emptying both counterfactuals.
    assert {"HOSTILE", "CHOPPY", "FRIENDLY"} <= set(APP_STATES)
    assert app_posture("HOSTILE") and app_posture("CHOPPY")


def test_the_simulator_produces_the_same_trades_whatever_the_regime_said(
    store, denominator
):
    """"Nothing is excluded by regime **anywhere in the run**", tested where the
    claim actually lives.

    The counts in `market_posture` cannot hold this promise: an upstream filter
    would drop trades before that function ever saw them and every sum there would
    still balance. What holds it is that the trade-producing path reads no regime
    column at all — so flipping the persisted state from FRIENDLY to HOSTILE, the
    two states whose postures would gate hardest, must return byte-identical
    trades. If a regime gate were ever introduced upstream, this is the test that
    fails.
    """
    denominator.stamp(DEFAULT_CONTRACT)
    det = _seed_figure_name(store, denominator, "US", "AAA", date(2016, 1, 1),
                            _FIG_FLAT + _FIG_WIN)
    denominator._cursor().execute(
        "UPDATE denominator_sessions SET regime_state = 'FRIENDLY'"
    )
    friendly = simulate_market(store, denominator, "US", DEFAULT_CONTRACT,
                               arms=(PRIMARY_ARM,))
    denominator._cursor().execute(
        "UPDATE denominator_sessions SET regime_state = 'HOSTILE'"
    )
    hostile = simulate_market(store, denominator, "US", DEFAULT_CONTRACT,
                              arms=(PRIMARY_ARM,))

    assert friendly and friendly == hostile
    assert det.session in {t.detection_session for t in friendly}

    # And the two runs land in different cells, which is the whole point: the
    # state changed what the trade is *reported under*, never whether it happened.
    spine = spine_for_market(denominator, "US")
    assert {state_of(spine, t) for t in hostile} == {"HOSTILE"}


def test_the_conditioning_block_accounts_for_the_two_declared_exclusions(store):
    """The exclusion accounting, which is narrower than it used to claim to be.

    Two trades are set aside before any cell is built — one from the other market,
    one from another arm — and both are counted and named. Neither is a regime
    exclusion, and the point of naming them is that "nothing was excluded by
    regime" is only worth reading beside the count of what *was* excluded and why.
    """
    session = date(2016, 3, 1)
    mine = _ptrade("AAA", session, 1.0)
    other_market = _ptrade("BBB", session, 1.0, market="IDX")
    other_arm = dataclasses.replace(_ptrade("CCC", session, 1.0), arm=ARM_A)
    spine = _spine("US", {session: "HOSTILE"})

    body = market_posture(
        DEFAULT_CONTRACT, [mine, other_market, other_arm], spine
    )
    cond = body["conditioning"]

    assert cond["handed_in"] == 3
    assert cond["excluded_other_markets"] == 1
    assert cond["excluded_other_arms"] == 1
    assert cond["trades"] == cond["in_cells"] == 1
    assert cond["excluded_by_regime"] == 0
    assert cond["partition_holds"] is True
    assert "backtest.simulate" in cond["upstream_guarantee"]


def test_a_counterfactual_called_directly_still_refuses_to_mix_arms(store):
    """The market and arm narrowing lives in the counterfactuals too, not only in
    the report above them.

    A direct caller must not be able to average arm A into a verdict the report a
    level up could not — the refusal is worth nothing if it only guards the path
    that was already safe.
    """
    session = date(2016, 3, 1)
    hostile = _ptrade("AAA", session, -2.0)
    stray_arm = dataclasses.replace(_ptrade("BBB", session, 9.0), arm=ARM_A)
    stray_market = _ptrade("CCC", session, 9.0, market="IDX")
    spine = _spine("US", {session: "HOSTILE"})

    cf = hostile_counterfactual(
        DEFAULT_CONTRACT, [hostile, stray_arm, stray_market], spine
    )
    assert cf["closed"] == 1
    assert cf["expectancy_r"] < 0  # the +9R strays never reached the cell

    red = choppy_reduced(
        DEFAULT_CONTRACT, [hostile, stray_arm, stray_market], spine
    )
    assert red["trades"] == 0 and red["trades_friendly"] == 0


def test_the_reduced_verdict_carries_both_sides_win_rate_and_distribution(store):
    """An expectancy never travels alone here, and a *difference* of two of them
    least of all.

    Two states with the same mean and different tails are not the same state to
    trade, and a bare gap between two means cannot show which tail produced it —
    which is exactly the question a sizing posture asks.
    """
    sessions = _sessions(2016, 16)
    states = ["CHOPPY"] * 8 + ["FRIENDLY"] * 8
    trades, spine = _cohort(sessions, states, [-1.0] * 8 + [3.0] * 8)

    red = choppy_reduced(DEFAULT_CONTRACT, trades, spine)

    assert red["shape"]["closed"] == 8 and red["shape_friendly"]["closed"] == 8
    assert red["shape"]["win_rate"] == 0.0
    assert red["shape_friendly"]["win_rate"] == 1.0
    for side in (red["shape"], red["shape_friendly"]):
        assert side["distribution"]["median"] is not None
        assert side["distribution"]["p90"] is not None

    printed = format_posture(
        posture_report(DEFAULT_CONTRACT, trades, {"US": spine}, markets=["US"])
    )
    # The relative verdict is the line most easily misread as an absolute one, so
    # both sides' n and win rate sit directly under it.
    assert "CHOPPY n=8" in printed and "FRIENDLY n=8" in printed


def test_follow_through_is_reported_and_named_unbiased_where_breadth_is_not(store):
    """Breadth's companion, and the only regime signal for which this backtest is a
    *better* instrument than the live app.

    The app captures it forward nightly because a survivorship-biased past cannot
    rebuild it; the index series carries no survivorship hole, so the run
    reconstructs it legitimately. Reported — and still never conditioned on.
    """
    sessions = _sessions(2016, 4)
    spine = RegimeSpine(
        market="US",
        readings={
            s: RegimeReading(state="FRIENDLY", breadth=0.4, broke_out=broke,
                             index_close=100.0)
            for s, broke in zip(sessions, [True, False, False, None])
        },
    )

    summary = follow_through_summary(spine)
    assert summary["sessions"] == 3
    assert summary["sessions_without_reading"] == 1
    assert summary["breakouts"] == 1
    assert summary["breakout_rate"] == pytest.approx(1 / 3)
    assert summary["basis"] == FOLLOW_THROUGH_BASIS
    assert summary["conditioned_on"] is False
    assert "unbiased where breadth is not" in summary["note"]

    trades, _ = _cohort(sessions, ["FRIENDLY"] * 4, [1.0] * 4)
    printed = format_posture(
        posture_report(DEFAULT_CONTRACT, trades, {"US": spine}, markets=["US"])
    )
    assert "follow-through (unbiased, never conditioned on)" in printed


def test_a_spine_filed_under_the_wrong_market_is_refused(store):
    """The market is the spine's own now, so a mapping whose key disagrees with the
    spine it points at is the one remaining way to date one market's trades off
    another market's index."""
    spine = _spine("IDX", {date(2016, 3, 1): "HOSTILE"})
    with pytest.raises(ValueError):
        posture_report(DEFAULT_CONTRACT, [], {"US": spine}, markets=["US"])


def test_the_report_says_why_the_states_are_not_also_cut_per_year(store):
    """Three states crossed with fourteen years is mostly cells below the cluster
    floor. That is a judgement, and it is recorded as one rather than left as a
    silent omission a reader has to notice."""
    sessions = _sessions(2016, 2)
    trades, spine = _cohort(sessions, ["HOSTILE", "FRIENDLY"], [1.0, 1.0])
    report = posture_report(
        DEFAULT_CONTRACT, trades, {"US": spine}, markets=["US"]
    )

    assert "per year" in report["per_year"]
    assert "2020–21" in report["per_year"]
    # And the multiple-testing count the plan asks to be stated rather than assumed.
    assert "nine views" in report["views"]
    assert "nine views" in format_posture(report)


# -- does the rubric rank, out of sample? (issue #194) -------------------------
#
# Phase 5's ranking cell, and the out-of-sample test §4a's claim has never had.
# §4a asked whether the star score separates the trader's *picks* from the field,
# on the same field the v2 weights had been fitted to — a fit statistic dressed as
# a test, and marginal anyway at p = 0.055. Here the outcome variable is R, which
# no weight was fitted to and which no detection's score could see. That is the
# whole point of the measurement, and it is why the two figures are carried side
# by side in the output rather than left for a reader to conflate.
#
# Three claims are load-bearing:
#
#   * **A tie never splits.** The replayed score is seven dimensions of eight
#     integral points, so its distribution is coarse and true deciles do not
#     exist. Every trade on the same score lands in the same bucket, the buckets
#     collapse to fewer than ten, and the decile positions each one covers are
#     named — a cut that split a tie would report two buckets differing by nothing
#     but which rows the sort happened to put first.
#   * **The score is the seven-dimension replayed one.** Never the app's nine
#     points: ≥3.5★ is 7 of 8 here and 7 of 9 there, and a ceiling read off the
#     wrong scale mislabels every band.
#   * **Clustered by symbol, as everywhere else.** A name detected three times in
#     a fortnight is one observation's worth of independence, not three.

from backtest.stats import MAX_UNDEFINED_SHARE, bootstrap_symbol_statistic
from backtest.ranking import (
    APP_MAX_POINTS,
    IN_SAMPLE_GAP,
    SCORE_DIMENSIONS,
    SCORE_LABEL,
    SCORE_MAX_POINTS,
    # Aliased: the posture section above imports its own verdict vocabulary into
    # this same namespace, and two `VERDICT_TOO_THIN`s in one file is a shadow
    # waiting to make one section's assertion silently test the other's constant.
    VERDICT_NO_EVIDENCE as RANKING_NO_EVIDENCE,
    VERDICT_RANKS as RANKING_RANKS,
    VERDICT_TOO_THIN as RANKING_TOO_THIN,
    Band,
    ScoredTrade,
    bands,
    check_seven_dimension_score,
    format_ranking,
    market_ranking,
    outcomes,
    rank_correlation,
    ranking_report,
    scored_trades,
    symbol_clusters,
    top_minus_bottom,
)


def _score(points: int) -> SevenDimScore:
    """A seven-dimension score worth exactly ``points``, out of eight.

    The breakdown is not read by anything under test — the buckets are cut on the
    total — so it is left empty rather than authored dimension by dimension, which
    would make every fixture below an assertion about the rubric instead of about
    the bucketing.
    """
    return SevenDimScore(
        stars=points / 2,
        points=points,
        max_points=SEVEN_DIM_MAX_POINTS,
        breakdown=[],
        label=SEVEN_DIM_LABEL,
    )


def _rtrade(
    symbol: str,
    points: int,
    r: float,
    *,
    year: int = 2016,
    market: str = "US",
    month: int = 3,
    arm: str = ARM_B,
    open_at_end: bool = False,
) -> ScoredTrade:
    """One arm-B trade at a known score and a known before-cost R.

    Authored on :func:`_mtrade`, the metric section's own fixture, because the
    ranking is arithmetic over the same trades priced the same way — a second
    trade fixture here would be a second cost model nobody compared.
    """
    return ScoredTrade(
        trade=_mtrade(
            symbol, year, r, market=market, arm=arm, month=month,
            open_at_end=open_at_end,
        ),
        score=_score(points),
    )


def _ladder(points_to_r: dict[int, float], *, per_score: int = 6) -> list[ScoredTrade]:
    """A cohort with ``per_score`` distinct symbols on each score, each paying its
    score's R. Enough symbols per band to clear the bootstrap's cluster floor."""
    return [
        _rtrade(f"S{points}_{i}", points, r)
        for points, r in points_to_r.items()
        for i in range(per_score)
    ]


def test_outcomes_are_bucketed_by_star_score_decile_with_n_on_every_bucket(store):
    """The measurement itself: buckets in ascending score order, each carrying the
    count behind it.

    n rides on every bucket because a bucket's expectancy is unreadable without it
    — one trade at +4R and six hundred at +0.1R print the same headline — and the
    counts sum to the cohort, so no trade is silently dropped between the cut and
    the report.
    """
    cohort = _ladder({2: -0.5, 4: 0.2, 6: 1.5})

    body = market_ranking(DEFAULT_CONTRACT, cohort, market="US")

    buckets = body["buckets"]
    assert [b["low_points"] for b in buckets] == [2, 4, 6]
    assert [b["closed"] for b in buckets] == [6, 6, 6]
    assert sum(b["trades"] for b in buckets) == len(cohort)
    assert [b["symbols"] for b in buckets] == [6, 6, 6]
    # Ascending in score, and the expectancy follows it here by construction.
    values = [b["expectancy_r"] for b in buckets]
    assert values == sorted(values)


def test_a_tie_never_splits_across_two_buckets(store):
    """The replayed score is eight integral points, so true deciles do not exist.

    A cut that split a tie would put two trades scoring identically in different
    buckets and report a difference between them, which would be a difference in
    sort order and nothing else. So a score value is atomic: the buckets collapse
    to fewer than ten and each one names the decile positions it covers.
    """
    # 80% of the cohort on one score: no decile boundary can pass through it.
    cohort = [_rtrade(f"L{i}", 3, 0.1) for i in range(80)]
    cohort += [_rtrade(f"H{i}", 6, 2.0) for i in range(20)]

    cut = bands(cohort)

    assert all(isinstance(b, Band) for b in cut)
    assert len(cut) < 10
    assert [(b.low_points, b.high_points) for b in cut] == [(3, 3), (6, 6)]
    # The band that swallowed eight deciles says so, rather than reporting as one.
    assert cut[0].deciles == tuple(range(1, 9))
    assert cut[1].deciles == (9, 10)


def test_the_bucket_a_trade_lands_in_never_depends_on_the_order_it_arrived(store):
    """Determinism, stated as the property the tie rule buys.

    The cut is a function of the score distribution, so shuffling the cohort moves
    nothing. A cut that read the incoming order would produce a different set of
    buckets on a re-run of the same data, with nothing in the output to show it.
    """
    cohort = _ladder({1: -1.0, 3: 0.0, 5: 1.0, 7: 2.0})
    shuffled = list(reversed(cohort))

    assert bands(cohort) == bands(shuffled)
    assert market_ranking(DEFAULT_CONTRACT, cohort, market="US") == market_ranking(
        DEFAULT_CONTRACT, shuffled, market="US"
    )


def test_a_score_that_ranks_shows_a_positive_gap_and_a_positive_rho(store):
    """The claim under test, in the shape that would confirm it.

    The top band beats the bottom, the rank correlation between score and outcome
    is positive, and both intervals sit above zero — which is the only combination
    the verdict rule reads as "ranks".
    """
    cohort = _ladder({1: -1.0, 3: -0.2, 5: 0.6, 7: 1.8}, per_score=8)

    body = market_ranking(DEFAULT_CONTRACT, cohort, market="US")

    assert body["gap"]["value"] > 0
    assert body["gap"]["bootstrap"]["ci_low"] > 0
    assert body["spearman"]["rho"] > 0
    assert body["spearman"]["bootstrap"]["ci_low"] > 0
    assert body["verdict"] == RANKING_RANKS


def test_a_score_that_does_not_rank_reports_no_evidence_rather_than_a_null_result(store):
    """A rubric whose bands pay the same is the outcome §4a's claim risks.

    The gap straddles zero, so the verdict says there is no evidence the score
    ranks — not that it is proven flat, which is a stronger claim than a bootstrap
    over one sample can license.

    Every band draws the *same* spread of outcomes, so the score carries no
    information about R and the true gap is zero. The spread inside a band is what
    makes the interval an interval: a band whose every trade paid the same would
    resample to a single number and print a certainty it has not earned.
    """
    spread = (-1.0, -1.0, -0.6, 0.3, 0.8, 2.2, -0.7, 1.1)
    cohort = [
        _rtrade(f"S{points}_{i}", points, r)
        for points in (1, 3, 5, 7)
        for i, r in enumerate(spread)
    ]

    body = market_ranking(DEFAULT_CONTRACT, cohort, market="US")

    assert body["gap"]["bootstrap"]["ci_low"] < 0 < body["gap"]["bootstrap"]["ci_high"]
    assert body["verdict"] == RANKING_NO_EVIDENCE
    assert "no evidence" in format_ranking(
        ranking_report(DEFAULT_CONTRACT, cohort, markets=("US",))
    )


def test_significance_is_clustered_by_symbol_not_by_row(store):
    """One name detected twenty times is not twenty independent observations.

    The same data bootstrapped by row and by symbol must not produce the same
    interval: the clustered one is wider and its p-value higher, and that widening
    *is* the correction. Run on the gap rather than on a mean, because the gap is
    the statistic the verdict is read off.
    """
    # One hot name at the top band, twenty times over, beside four cold names in
    # the same band; twenty distinct names at the bottom. By row the top band is
    # its hot name's twenty rows and the gap is decisive. By symbol the whole
    # result turns on whether that one name was drawn, and a third of the time it
    # is not — which is what the interval has to show.
    cohort = [_rtrade("HOT", 7, 3.0, month=1 + (i % 12)) for i in range(20)]
    cohort += [_rtrade(f"T{i}", 7, -1.5) for i in range(4)]
    cohort += [_rtrade(f"C{i}", 1, -1.0) for i in range(20)]
    cut = bands(cohort)
    clustered = symbol_clusters(cohort, DEFAULT_CONTRACT)

    by_symbol = bootstrap_symbol_statistic(
        clustered, lambda rows: top_minus_bottom(rows, cut)
    )
    by_row = bootstrap_symbol_statistic(
        [(row,) for cluster in clustered for row in cluster],
        lambda rows: top_minus_bottom(rows, cut),
    )

    assert by_symbol["clusters"] == 25
    assert by_row["clusters"] == 44
    assert (by_symbol["ci_high"] - by_symbol["ci_low"]) > (
        by_row["ci_high"] - by_row["ci_low"]
    )
    assert by_symbol["p_value"] > by_row["p_value"]
    assert by_symbol["cluster"] == BOOTSTRAP_CLUSTER


def test_a_bucket_too_thin_to_bootstrap_says_so_and_still_reports_its_n(store):
    """Per-year buckets are exactly where the symbol count goes thin.

    A single symbol resampled two thousand times returns its own mean two thousand
    times — a zero-width interval that prints as certainty from one observation.
    So the interval is refused and the count is not: "too few symbols to say" and
    "no result" are different findings.
    """
    cohort = [_rtrade("ONE", 6, 2.0, month=1 + i) for i in range(3)]
    cohort += _ladder({2: -1.0}, per_score=6)

    body = market_ranking(DEFAULT_CONTRACT, cohort, market="US")

    top = body["buckets"][-1]
    assert top["closed"] == 3
    assert top["symbols"] == 1
    assert top["bootstrap"]["ci_low"] is None
    assert "too thin" in top["bootstrap"]["suppressed"]
    assert body["verdict"] == RANKING_TOO_THIN
    assert "too thin" in format_ranking(
        ranking_report(DEFAULT_CONTRACT, cohort, markets=("US",))
    )


def test_every_year_of_the_measured_window_gets_a_row_on_the_same_bands(store):
    """Per market *and* per year, and the bands are cut once on the market's whole
    window.

    Cutting per year would make "the top bucket" a different score band in every
    row, so a year-on-year comparison would compare two different questions. The
    years run from the contract's measured start, so a market that traded nothing
    until later has its silent years on the page rather than missing from it.
    """
    cohort = _ladder({2: -0.5, 6: 1.5}, per_score=6)
    cohort += [_rtrade(f"N{i}", 6, 1.0, year=2017) for i in range(6)]

    body = market_ranking(DEFAULT_CONTRACT, cohort, market="US")

    years = {y["year"]: y for y in body["years"]}
    assert min(years) == int(DEFAULT_CONTRACT.value(WINDOW_MEASURED_START_KEY)[:4])
    assert max(years) == 2017
    window_bands = [b["band"] for b in body["buckets"]]
    for year in years.values():
        assert [b["band"] for b in year["buckets"]] == window_bands
    # 2017 traded only the top band; the bottom band's row is a zero, not a gap.
    assert [b["closed"] for b in years[2017]["buckets"]] == [0, 6]

    # On the page a silent year is one line rather than a band per bucket: it
    # stays visible — it is a measurement, and possibly a data hole — without
    # burying the years that traded under fourteen empty ladders.
    printed = format_ranking(
        ranking_report(DEFAULT_CONTRACT, cohort, markets=("US",))
    ).splitlines()
    assert "    2013  no trades" in printed
    assert sum(1 for line in printed if line.startswith("    2013")) == 1


def test_us_and_idx_never_pool(store):
    """findings §8 measured that magnitudes do not transfer, so a mean across the
    two markets is a number about neither — and a bucket built from both would
    hide it inside a band label that looked ordinary."""
    with pytest.raises(ValueError):
        market_ranking(
            DEFAULT_CONTRACT,
            [_rtrade("AAA", 6, 1.0), _rtrade("BBB.JK", 6, 1.0, market="IDX")],
            market="US",
        )


def test_the_ranking_is_arm_bs_and_refuses_another_arm(store):
    """Arm B is the pre-registered arm, and an arm A trade averaged into it would
    report a figure no arm produced under arm B's name."""
    with pytest.raises(ValueError):
        market_ranking(
            DEFAULT_CONTRACT,
            [_rtrade("AAA", 6, 1.0), _rtrade("BBB", 6, 1.0, arm=ARM_A)],
            market="US",
        )


def test_the_score_is_the_seven_dimension_one_and_the_apps_ceiling_is_named(store):
    """≥3.5★ is 7 of 8 here and 7 of 9 in the app. A band read off the wrong
    ceiling mislabels every bucket, so both scales ride on the output and the
    replayed one is labelled wherever it is printed."""
    report = ranking_report(
        DEFAULT_CONTRACT, _ladder({2: -0.5, 6: 1.5}), markets=("US",)
    )

    score = report["score"]
    assert score["label"] == SCORE_LABEL == SEVEN_DIM_LABEL
    assert score["dimensions"] == SCORE_DIMENSIONS == 7
    assert score["max_points"] == SCORE_MAX_POINTS == SEVEN_DIM_MAX_POINTS
    assert score["app_max_points"] == APP_MAX_POINTS == SCORE_MAX_POINTS + 1
    assert score["max_stars"] == 4.0
    printed = format_ranking(report)
    assert SEVEN_DIM_LABEL in printed
    assert "not the app's" in printed


def test_a_score_on_the_apps_nine_point_ceiling_is_drift_not_a_ninth_point(store):
    """The replayed score drops `Sector` and totals out of eight. A nine-point row
    arriving here means the field was scored by something else, and reading it as
    a seven-dimension one would re-base every band silently."""
    nine = SevenDimScore(
        stars=4.5, points=9, max_points=9, breakdown=[], label="star score"
    )

    check_seven_dimension_score(_score(6))
    with pytest.raises(ContractDrift):
        check_seven_dimension_score(nine)


def test_the_result_is_stated_against_4as_in_sample_gap(store):
    """The two are not the same measurement and must not be read as one.

    §4a's +5.59pp is a separation the v2 weights were *fitted* to, on the field
    they were fitted on, at p = 0.055. This one's outcome variable is R, which no
    weight ever saw. So §4a's figures ride on the payload with the reason they are
    not comparable, rather than being left for a reader to line up.
    """
    report = ranking_report(
        DEFAULT_CONTRACT, _ladder({2: -0.5, 6: 1.5}), markets=("US",)
    )

    prior = report["in_sample_reference"]
    assert prior["gap_pp"] == IN_SAMPLE_GAP["gap_pp"] == 5.59
    assert prior["p_value"] == 0.055
    assert "§4a" in prior["source"]
    assert "fitted" in prior["why_it_is_not_this_measurement"]
    printed = format_ranking(report)
    assert "§4a" in printed
    assert "in-sample" in printed


def test_a_trade_with_no_score_row_is_a_failure_rather_than_a_silent_drop(store):
    """The join between a trade and the detection that produced it is total.

    A trade whose detection row is missing is a broken denominator, and dropping
    it quietly would shrink the cohort the ranking is measured on with nothing in
    the output to show which trades left.
    """
    trade = _mtrade("AAA", 2016, 1.0)
    index = {(trade.detection_session, "AAA"): _cdetection("AAA", trade.detection_session)}

    assert [s.score.points for s in scored_trades([trade], index)] == [
        _cdetection("AAA", trade.detection_session).score.points
    ]
    with pytest.raises(ValueError):
        scored_trades([trade], {})


def test_rho_reads_the_score_against_the_outcome_and_ties_are_averaged(store):
    """The rank correlation is the statistic that answers "does a higher score
    predict a better result" over the whole cohort rather than at its two edges.

    Ties are the common case on an eight-point score, so they take the average
    rank: a tie broken by arrival order would make rho depend on the sort.
    """
    rising = _ladder({1: -1.0, 3: 0.0, 5: 1.0, 7: 2.0}, per_score=3)
    falling = _ladder({1: 2.0, 3: 1.0, 5: 0.0, 7: -1.0}, per_score=3)
    rho = lambda cohort: rank_correlation(outcomes(cohort, DEFAULT_CONTRACT))

    assert rho(rising) == pytest.approx(1.0)
    assert rho(falling) == pytest.approx(-1.0)
    # One score only: no variance in the ranks, so no correlation exists to report.
    assert rho(_ladder({4: 1.0})) is None


def test_the_cut_is_taken_over_outcomes_and_an_open_trade_moves_no_boundary(store):
    """A trade still running has no R and contributes to no statistic in the report.

    Letting it move a boundary would cut the measured population against a
    distribution that includes one that pays nothing — and the open trades are not
    a random sample of the field, since a name still running at the window's end is
    one the trail never took out.
    """
    closed = [_rtrade(f"C{i}", 2, 0.5) for i in range(9)]
    still_running = ScoredTrade(
        trade=_mtrade("OPEN", 2016, 3.0, open_at_end=True), score=_score(7)
    )

    assert [(b.low_points, b.high_points) for b in bands(closed)] == [(2, 2)]
    assert bands(closed + [still_running]) == bands(closed)

    body = market_ranking(DEFAULT_CONTRACT, closed + [still_running], market="US")
    only = body["buckets"][0]
    assert only["trades"] == 9
    assert only["closed"] == 9
    assert only["share_of_closed"] == 1.0
    # Its score is above every band the closed trades produced, so no bucket holds
    # it. It is counted rather than dropped or filed under the nearest edge: the
    # buckets have to add up to the field, and a 1.0★ band holding a 3.5★ trade
    # would be a mislabel.
    assert body["outside_the_cut"] == 1
    assert sum(b["trades"] for b in body["buckets"]) + body["outside_the_cut"] == 10


def test_an_interval_built_mostly_on_resamples_that_could_not_answer_is_refused(store):
    """A resample is undefined exactly when it drew no symbol from an edge band.

    Those are the draws carrying the most uncertainty about a gap resting on a thin
    edge, so reading the interval off the rest conditions on the statistic having
    been computable — which is a condition the confident draws satisfy. The remedy
    is to refuse the interval, not to repair it: there is no honest value to
    substitute, and zero is a measurement nobody made.
    """
    # One symbol alone in the top band: better than a third of resamples of 7
    # symbols draw none of it, and the gap is undefined in every one of those.
    cohort = [_rtrade("ONE", 6, 2.0, month=1 + i) for i in range(3)]
    cohort += _ladder({2: -1.0}, per_score=6)
    cut = bands(cohort)

    boot = bootstrap_symbol_statistic(
        symbol_clusters(cohort, DEFAULT_CONTRACT),
        lambda rows: top_minus_bottom(rows, cut),
    )

    assert boot["clusters"] >= BOOTSTRAP_MIN_CLUSTERS
    assert boot["undefined"] / boot["resamples"] > MAX_UNDEFINED_SHARE
    assert (boot["ci_low"], boot["ci_high"], boot["p_value"]) == (None, None, None)
    assert "could not be evaluated" in boot["suppressed"]

    # And a cohort whose bands are always drawable gets its interval.
    wide = _ladder({2: -1.0, 6: 2.0}, per_score=8)
    wide_cut = bands(wide)
    healthy = bootstrap_symbol_statistic(
        symbol_clusters(wide, DEFAULT_CONTRACT),
        lambda rows: top_minus_bottom(rows, wide_cut),
    )
    assert healthy["undefined"] == 0
    assert healthy["ci_low"] is not None


def test_the_bands_partition_the_ten_decile_positions_exactly(store):
    """Each band carries the decile boundaries that fall inside it, and between them
    the bands account for all ten.

    A band holding 49% carries the four boundaries below it and the fifth belongs to
    its neighbour — so a band's decile span says where its share sits rather than
    rounding that share, and no decile position goes unreported.
    """
    for cohort in (
        _ladder({1: -1.0, 3: 0.0, 5: 1.0, 7: 2.0}),
        [_rtrade(f"L{i}", 3, 0.1) for i in range(49)]
        + [_rtrade(f"H{i}", 6, 2.0) for i in range(51)],
        _ladder({4: 1.0}),
    ):
        covered = [d for band in bands(cohort) for d in band.deciles]
        assert covered == list(range(1, 11))


def test_the_count_of_intervals_the_report_states_rides_on_it(store):
    """Every year of every market gets its own gap, rho and verdict, so a report
    over fourteen years makes scores of significance statements at nominal alpha and
    some come up positive by construction. A budget a reader has to infer from the
    length of the page is a budget nobody is keeping."""
    report = ranking_report(
        DEFAULT_CONTRACT, _ladder({2: -0.5, 6: 1.5}, per_score=8), markets=("US",)
    )

    budget = report["multiple_testing"]
    assert budget["intervals_reported"] > 1
    assert budget["alpha_is_nominal"] is True
    assert "sweep" in budget["note"]
    # A suppressed cell states nothing, so it is not in the count of claims made.
    stated = sum(
        1
        for market in report["markets"]
        for slice_body in [market, *market["years"]]
        for cell in [*slice_body["buckets"], slice_body["gap"],
                     slice_body["spearman"]]
        if cell["bootstrap"]["ci_low"] is not None
    )
    assert budget["intervals_reported"] == stated


def test_the_ranking_report_is_stamped_and_serialises(store):
    """Like every figure the package emits: the contract rides on it, and two runs
    under different contracts differ in their output alone."""
    report = ranking_report(
        DEFAULT_CONTRACT, _ladder({2: -0.5, 6: 1.5}), markets=("US", "IDX")
    )

    assert report[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    assert [m["market"] for m in report["markets"]] == ["US", "IDX"]
    assert json.loads(json.dumps(report)) == report


def test_the_ranking_runs_off_the_denominator_end_to_end(store, denominator):
    """The seam that matters: persisted detections, their scores, and the trades
    the simulator took off them, joined by the session they were decided on."""
    det = _seed_figure_name(store, denominator, "US", "AAA", date(2020, 1, 1),
                            _FIG_FLAT + _FIG_WIN)
    trades = simulate_market(
        store, denominator, "US", DEFAULT_CONTRACT, arms=(ARM_B,)
    )
    scores = detection_index(denominator, "US")

    cohort = scored_trades(trades, scores)

    assert [s.trade.symbol for s in cohort] == ["AAA"]
    assert cohort[0].score.points == seven_dimension_score(
        det, prior_move=False
    ).points
    body = market_ranking(DEFAULT_CONTRACT, cohort, market="US")
    assert sum(b["trades"] for b in body["buckets"]) == 1


# -- do the registered candidates predict, or only select? (issue #195) --------
#
# ADR 0005 admits a dimension on a **selection contrast** — taken detections
# against not-taken ones, no outcome variable — because when it was written no
# outcome variable existed. Both registered candidates were measured on that
# instrument and neither shipped: `RS line` refused on criterion 4 for a wrong-way
# gap (findings §5d), `Relative move` positive on both fields and then stalled
# 0.06pp inside the one threshold the ADR itself calls a judgement (§5e).
#
# This section gives the same two dimensions an **outcome** variable. Four claims
# are load-bearing, and each is an acceptance criterion of #195:
#
#   * **Both registered candidates, per market.** The list is derived from
#     `replay.contrast.CANDIDATES` rather than typed here, so a registration this
#     module cannot read is drift rather than a silently missing column.
#   * **The cut is applied at read time**, off the value the persisted row
#     carries, by the rubric's own reader. No row is re-denominated retroactively.
#   * **Absence is absence.** `relative_move` is `None` when the name had not
#     listed six months back — and zero is a real value sitting exactly on the
#     pre-registered cut, so a coerced absence would be a hit-or-miss verdict
#     nobody measured. It gets its own group, its own n, and it enters no gap.
#   * **The outcome claim is never merged with the selection contrast.** They are
#     two different claims about one dimension, and a reader who lines them up as
#     one has read a stronger claim than either supports.
#
# Nothing here admits a dimension. `check_not_admitted` makes that executable
# rather than a sentence in a docstring.

from backtest.candidates import (
    ADMISSION_NOTE,
    CANDIDATES_UNDER_TEST,
    GROUP_ABSENT,
    GROUP_HIT,
    GROUP_MISS,
    GROUPS,
    SELECTION_CONTRAST,
    VALUE_BOOLEAN,
    VALUE_GRADED,
    VERDICT_RULE as VERDICT_RULE_CANDIDATES,
    # Aliased for the reason the ranking section aliases its own: three verdict
    # vocabularies now live in this namespace, and an unqualified
    # `VERDICT_TOO_THIN` would let one section's assertion test another's
    # constant.
    VERDICT_NO_EVIDENCE as CANDIDATE_NO_EVIDENCE,
    VERDICT_PREDICTS as CANDIDATE_PREDICTS,
    VERDICT_TOO_THIN as CANDIDATE_TOO_THIN,
    DetectedTrade,
    candidate_trades,
    candidates_report,
    check_not_admitted,
    check_registry,
    format_candidates,
    group_of,
    market_candidate,
    named_candidate,
    outcome_gap,
    outcomes as candidate_outcomes,
    rubric_reading_gap,
    split,
    value_correlation,
)
from backtest.cohort import detection_index
from backtest.stats import spearman
from replay.contrast import CANDIDATE_DIMENSIONS


_RS_LINE = "RS line"
_RELATIVE_MOVE = "Relative move"


def _cdetection(
    symbol: str,
    session: date,
    *,
    rs_line: bool | None = None,
    relative_move: float | None = None,
) -> ScoredDetection:
    """A persisted detection row carrying nothing but its two candidate values.

    The detector record and the score are the fixture's filler — this section
    measures what the candidate columns predict, and authoring a geometry to reach
    them would put the detector's behaviour inside a test about outcomes.
    """
    det = Detection(
        symbol=symbol, session=session, detector_version=DETECTOR_VERSION,
        trigger=10.0, stop=9.0, stopw_adr=1.0,
        base_len=10, move_gain=0.5, adr=0.05, close=9.5, cluster_k=3,
        cluster_high=10.0, cluster_low=9.0, cluster_range_adr=1.0,
        range_3bar_adr=1.0, line_ok=True, touch_zones=2, overshoot_adr=0.1,
        slope=0.0, line_end=9.5, base_low=9.0, churn_l=0.2, sma20_rising=True,
        dryup=0.8,
    )
    return ScoredDetection(
        symbol=symbol,
        detection=det,
        score=SevenDimScore(
            stars=2.0, points=4, max_points=SEVEN_DIM_MAX_POINTS,
            breakdown=[], label=SEVEN_DIM_LABEL,
        ),
        star_rank=1,
        not_taken=False,
        rs_line=rs_line,
        relative_move=relative_move,
    )


def _ctrade(
    symbol: str,
    r: float,
    *,
    rs_line: bool | None = None,
    relative_move: float | None = None,
    year: int = 2016,
    month: int = 3,
    market: str = "US",
    arm: str = ARM_B,
) -> DetectedTrade:
    """One arm-B trade beside the persisted row that produced it.

    Authored on :func:`_mtrade`, the metric section's own fixture, for the reason
    the ranking section gives: the measurement is arithmetic over trades priced the
    metric's way, and a second trade fixture would be a second cost model.
    """
    trade = _mtrade(symbol, year, r, market=market, arm=arm, month=month)
    return DetectedTrade(
        trade=trade,
        detection=_cdetection(
            symbol, trade.detection_session,
            rs_line=rs_line, relative_move=relative_move,
        ),
    )


def _ccohort(
    hits: dict[str, float],
    misses: dict[str, float],
    absent: dict[str, float] | None = None,
    *,
    market: str = "US",
) -> list[DetectedTrade]:
    """A cohort split three ways on ``Relative move``'s stored value.

    A hit is a positive value, a miss a negative one, and an absent row carries
    ``None`` — never 0.0, which is a real value sitting exactly on the cut and is
    the confusion this whole section exists to prevent.
    """
    rows = [_ctrade(s, r, relative_move=+1.5, market=market)
            for s, r in hits.items()]
    rows += [_ctrade(s, r, relative_move=-1.5, market=market)
             for s, r in misses.items()]
    rows += [_ctrade(s, r, relative_move=None, market=market)
             for s, r in (absent or {}).items()]
    return rows


def _spread(prefix: str, r: float, n: int) -> dict[str, float]:
    """``n`` distinct symbols all paying ``r`` — enough clusters to bootstrap."""
    return {f"{prefix}{i}": r for i in range(n)}


def _cbody(
    cohort: list[DetectedTrade], name: str, *, market: str = "US"
) -> dict[str, Any]:
    """One candidate's cell over one market — the shape most tests below read."""
    return market_candidate(
        DEFAULT_CONTRACT, named_candidate(name), cohort, market=market
    )


def _cfind(report: dict[str, Any], market: str, name: str) -> dict[str, Any]:
    """One candidate's cell out of a whole report."""
    body = next(m for m in report["markets"] if m["market"] == market)
    return next(c for c in body["candidates"] if c["candidate"] == name)


def test_both_registered_candidates_are_measured_against_outcomes_per_market():
    """#195's first criterion, and the reason the list is derived rather than typed.

    The candidates under test are exactly the ones ADR 0005 has registered, read
    off `replay.contrast.CANDIDATES`. A module holding its own list would keep
    measuring a retired candidate, or quietly miss a third one, with nothing in the
    output to say so.
    """
    assert [c.name for c in CANDIDATES_UNDER_TEST] == [
        name for name, _weight in CANDIDATE_DIMENSIONS
    ]
    assert {c.name for c in CANDIDATES_UNDER_TEST} == {_RS_LINE, _RELATIVE_MOVE}

    report = candidates_report(
        DEFAULT_CONTRACT,
        _ccohort(_spread("H", 1.0, 6), _spread("M", -0.2, 6)),
        markets=("US", "IDX"),
    )

    assert [m["market"] for m in report["markets"]] == ["US", "IDX"]
    for body in report["markets"]:
        assert [c["candidate"] for c in body["candidates"]] == [
            _RS_LINE, _RELATIVE_MOVE
        ]


def test_a_registration_this_module_cannot_read_is_drift_not_a_missing_column():
    """A third candidate registered upstream must stop this measurement, loudly.

    The registry here supplies what `CANDIDATES` does not — how to read the
    **value** off the row, and what absence means for it — so a name it has never
    heard of cannot be measured. Reporting the two it knows and dropping the third
    would answer #195's "both registered candidates" with a number that had quietly
    stopped meaning it.
    """
    with pytest.raises(ContractDrift, match="Third candidate"):
        check_registry((("Third candidate", 0, lambda d: True),))


def test_the_cut_is_applied_at_read_time_off_the_value_the_row_carries():
    """#195's second criterion: the row owns the value, the reader owns the verdict.

    Two rows on either side of the pre-registered cut land in different groups
    while carrying their stored values unchanged — so a later argument about where
    the cut belongs re-reads these rows rather than re-denominating them.
    """
    candidate = named_candidate(_RELATIVE_MOVE)
    above = _cdetection("AAA", date(2016, 3, 1), relative_move=+0.25)
    below = _cdetection("BBB", date(2016, 3, 1), relative_move=-0.25)

    assert group_of(candidate, above) == GROUP_HIT
    assert group_of(candidate, below) == GROUP_MISS
    # The value is untouched by the reading: the cut is a question asked of the
    # row, never a rewrite of it.
    assert candidate.value(above) == +0.25
    assert candidate.value(below) == -0.25


def test_absence_is_its_own_group_and_never_a_value_sitting_on_the_cut():
    """#195's third criterion, and the one with a trap under it.

    ``Relative move``'s cut is **zero**. So an absent value coerced to 0.0 would
    not merely be a guess — it would land exactly on the boundary, and the
    strictness of the comparison would decide a verdict nobody measured. Absence
    therefore gets its own group, and a row in it enters no gap.
    """
    candidate = named_candidate(_RELATIVE_MOVE)
    missing = _cdetection("AAA", date(2016, 3, 1), relative_move=None)

    assert group_of(candidate, missing) == GROUP_ABSENT
    assert candidate.value(missing) is None

    cohort = _ccohort(
        _spread("H", 1.0, 6), _spread("M", -0.2, 6), _spread("Z", 9.9, 6)
    )
    groups = split(candidate, cohort)

    assert sorted(groups) == sorted(GROUPS)
    assert [len(groups[g]) for g in (GROUP_HIT, GROUP_MISS, GROUP_ABSENT)] == [6, 6, 6]
    # The absent rows pay +9.9R and move the gap by nothing at all.
    rows = candidate_outcomes(candidate, cohort, DEFAULT_CONTRACT)
    asked = [row for row in rows if row.group != GROUP_ABSENT]
    assert outcome_gap(rows) == outcome_gap(asked)


def test_every_trade_lands_in_exactly_one_group_and_the_counts_add_up():
    """The three groups partition the cohort, so nothing leaves between the split
    and the report — and the absent count is reported rather than inferred from a
    subtraction a reader has to perform."""
    cohort = _ccohort(
        _spread("H", 1.0, 6), _spread("M", -0.2, 5), _spread("Z", 0.4, 4)
    )

    body = _cbody(cohort, _RELATIVE_MOVE)

    counts = {g: body["groups"][g]["trades"] for g in GROUPS}
    assert counts == {GROUP_HIT: 6, GROUP_MISS: 5, GROUP_ABSENT: 4}
    assert sum(counts.values()) == len(cohort) == body["trades"]


def test_the_rubric_reading_folds_absence_into_the_miss_side_and_says_which():
    """What the dimension would do **as shipped**, reported and never conflated.

    The pre-registered readers score an absent value ``False``
    (:func:`~screener.relative_strength.relative_move_hit`), so a shipped boolean
    would put those rows on the miss side. That reading is worth having — it is the
    one a rubric would actually apply — but it answers a different question from
    "does the measured quantity predict", so it rides beside the primary gap under
    its own name and never sets the verdict.
    """
    # The absent rows pay well, so folding them into the miss side must move the
    # secondary gap and leave the primary one exactly where it was.
    cohort = _ccohort(
        _spread("H", 1.0, 6), _spread("M", -1.0, 6), _spread("Z", 3.0, 6)
    )
    candidate = named_candidate(_RELATIVE_MOVE)
    rows = candidate_outcomes(candidate, cohort, DEFAULT_CONTRACT)

    body = _cbody(cohort, _RELATIVE_MOVE)

    assert body["gap"]["value"] == pytest.approx(outcome_gap(rows))
    assert body["rubric_reading"]["value"] == pytest.approx(rubric_reading_gap(rows))
    assert body["gap"]["value"] > body["rubric_reading"]["value"]
    assert "absent" in body["rubric_reading"]["reads_absence_as"]
    # And it is explicitly outside the verdict.
    assert body["rubric_reading"]["enters_the_verdict"] is False


def test_a_candidate_that_predicts_shows_a_gap_whose_interval_clears_zero():
    """The claim under test, in the shape that would confirm it: the hit group
    out-earns the miss group and the clustered interval sits entirely above zero."""
    cohort = _ccohort(_spread("H", 2.0, 8), _spread("M", -1.0, 8))

    body = _cbody(cohort, _RELATIVE_MOVE)

    assert body["gap"]["value"] > 0
    assert body["gap"]["bootstrap"]["ci_low"] > 0
    assert body["verdict"] == CANDIDATE_PREDICTS


def test_a_candidate_that_does_not_predict_reports_no_evidence_not_a_null_result():
    """"No evidence it predicts" is never "the dimension does not predict".

    One sample cannot license the second, and the vocabulary is where that
    discipline lives — a report saying "no" would be a claim this run has no
    standing to make.
    """
    cohort = _ccohort(_spread("H", 0.1, 8), _spread("M", 0.1, 8))

    body = _cbody(cohort, _RELATIVE_MOVE)

    assert body["verdict"] == CANDIDATE_NO_EVIDENCE
    assert "never" in VERDICT_RULE_CANDIDATES
    ci_low = body["gap"]["bootstrap"]["ci_low"]
    assert ci_low is None or ci_low <= 0


def test_a_side_too_thin_to_bootstrap_says_so_and_still_reports_its_n():
    """A gap is taken **between** two sides, so a thin one makes it unreadable
    however wide the other is. The n stays on the page: a thin cell is visible as
    thin rather than absent."""
    cohort = _ccohort(_spread("H", 2.0, 8), {"M0": -1.0, "M1": -1.0})

    body = _cbody(cohort, _RELATIVE_MOVE)

    assert body["verdict"] == CANDIDATE_TOO_THIN
    assert body["groups"][GROUP_MISS]["closed"] == 2
    assert body["groups"][GROUP_MISS]["bootstrap"]["suppressed"] is not None


def test_significance_is_clustered_by_symbol_never_by_row():
    """One name signalling repeatedly is one observation's worth of independence.

    Two cohorts with the same rows and different symbol counts must not produce the
    same interval — bootstrapping rows would make the second look as firm as the
    first.
    """
    spread = _ccohort(_spread("H", 2.0, 8), _spread("M", -1.0, 8))
    one_name = [
        _ctrade("SAME", 2.0, relative_move=+1.5, month=1 + i) for i in range(8)
    ] + [
        _ctrade("OTHER", -1.0, relative_move=-1.5, month=1 + i) for i in range(8)
    ]

    wide = _cbody(spread, _RELATIVE_MOVE)
    narrow = _cbody(one_name, _RELATIVE_MOVE)

    assert wide["gap"]["bootstrap"]["clusters"] == 16
    assert narrow["gap"]["bootstrap"]["clusters"] == 2
    assert narrow["gap"]["bootstrap"]["suppressed"] is not None
    assert narrow["verdict"] == CANDIDATE_TOO_THIN


def test_the_stored_value_is_correlated_with_the_outcome_where_one_exists():
    """The grading question ADR 0004 would ask later, asked here on the stored value.

    ``Relative move`` persists a real number in ADR units, so the degree can be
    ranked against the outcome. This is the statement the boolean cannot make, and
    it runs over the rows where the value **exists** — an absent row is not a low
    one.
    """
    cohort = [
        _ctrade("A", -1.0, relative_move=-2.0),
        _ctrade("B", 0.0, relative_move=-0.5),
        _ctrade("C", 1.0, relative_move=+0.5),
        _ctrade("D", 2.0, relative_move=+2.0),
        _ctrade("E", 9.9, relative_move=None),
    ]
    candidate = named_candidate(_RELATIVE_MOVE)
    rows = candidate_outcomes(candidate, cohort, DEFAULT_CONTRACT)

    rho = value_correlation(rows)

    assert rho == pytest.approx(1.0)
    # The absent row is excluded rather than ranked at the bottom: it pays the
    # most, and ranking it anywhere would move the figure.
    assert rho == pytest.approx(
        spearman(
            [-2.0, -0.5, 0.5, 2.0], [r.r for r in rows if r.value is not None]
        )
    )


def test_a_candidate_storing_only_a_boolean_reports_no_correlation_and_why():
    """``RS line`` persists a boolean, not a degree.

    So there is no value to rank, and the cell says that rather than printing a
    correlation between a verdict and an outcome — which would be the gap again
    under a second name, and would read as a second piece of evidence.
    """
    cohort = [
        _ctrade("A", -1.0, rs_line=False),
        _ctrade("B", 2.0, rs_line=True),
    ]

    body = _cbody(cohort, _RS_LINE)

    assert named_candidate(_RS_LINE).value_kind == VALUE_BOOLEAN
    assert named_candidate(_RELATIVE_MOVE).value_kind == VALUE_GRADED
    assert body["value_correlation"]["rho"] is None
    assert "boolean" in body["value_correlation"]["unavailable"]


def test_the_verdict_is_the_gaps_and_the_correlation_is_stated_beside_it():
    """One statistic decides, and the rule says which.

    The gap is the claim ADR 0005 would act on — the dimension is admitted as a
    boolean — so it is the gap's interval that reads the verdict. The correlation
    is a statement about a *graded* form nothing has proposed, and only one of the
    two candidates even has a value to compute it on; letting it into the verdict
    would make the rule mean different things for the two dimensions.
    """
    cohort = _ccohort(_spread("H", 2.0, 8), _spread("M", -1.0, 8))

    body = _cbody(cohort, _RELATIVE_MOVE)

    assert body["verdict"] == CANDIDATE_PREDICTS
    assert body["value_correlation"]["enters_the_verdict"] is False
    assert "gap" in VERDICT_RULE_CANDIDATES


def test_the_outcome_claim_is_reported_separately_from_the_selection_contrast():
    """#195's fourth criterion: two claims about one dimension, never merged.

    The published selection figures ride on the payload — the instrument, the Δ,
    and the verdict ADR 0005 reached on it — beside a sentence saying why the two
    cannot be added up. They are not the same claim: one says the trader picked
    these names, the other says the names paid.
    """
    report = candidates_report(
        DEFAULT_CONTRACT,
        _ccohort(_spread("H", 2.0, 8), _spread("M", -1.0, 8)),
        markets=("US",),
    )

    body = _cfind(report, "US", _RELATIVE_MOVE)
    prior = body["selection_contrast"]

    assert prior["instrument"] == "selection contrast"
    assert prior["delta_pp"] == pytest.approx(3.6)
    assert prior["adr_0005_verdict"] == "not admitted"
    assert "different claim" in report["selection_contrast_note"]
    # The two verdicts are separate keys, and neither is derived from the other.
    assert body["verdict"] != prior["adr_0005_verdict"]
    assert "selection" in format_candidates(report)


def test_the_published_selection_figures_are_the_ones_5d_and_5e_measured():
    """Quoted from the findings rather than recomputed, and pinned so a typo here
    cannot rewrite a published result on its way onto this payload."""
    assert SELECTION_CONTRAST[_RS_LINE]["delta_pp"] == pytest.approx(-2.1)
    assert SELECTION_CONTRAST[_RS_LINE]["source"].endswith("§5d")
    assert SELECTION_CONTRAST[_RELATIVE_MOVE]["delta_pp"] == pytest.approx(3.6)
    assert SELECTION_CONTRAST[_RELATIVE_MOVE][
        "not_taken_hit_rate"
    ] == pytest.approx(0.8494)
    assert SELECTION_CONTRAST[_RELATIVE_MOVE]["source"].endswith("§5e")


def test_nothing_here_admits_a_dimension_to_the_rubric():
    """#195's fifth criterion, made executable rather than promised in prose.

    A candidate that had entered `screener.score.DIMENSIONS` would mean this
    measurement was reporting on a live rubric row, which is a different thing
    entirely — so it is refused at the door, and the payload states that admission
    is ADR 0005's instrument and not this one's.
    """
    check_not_admitted()
    assert all(weight == 0 for _name, weight in CANDIDATE_DIMENSIONS)
    live = {name for name, _weight in DIMENSIONS}
    assert live.isdisjoint({c.name for c in CANDIDATES_UNDER_TEST})

    report = candidates_report(
        DEFAULT_CONTRACT, _ccohort(_spread("H", 2.0, 8), _spread("M", -1.0, 8))
    )

    assert report["admission"] == ADMISSION_NOTE
    assert "admits no dimension" in ADMISSION_NOTE


def test_a_candidate_that_had_entered_the_rubric_is_refused():
    """The other half of the same guard: the check has to be able to fire."""
    with pytest.raises(ContractDrift, match="Relative move"):
        check_not_admitted(dimensions=(("Relative move", 1),))


def test_us_and_idx_never_pool_and_there_is_no_top_level_gap():
    """Findings §8 measured that magnitudes do not transfer, so the way to stop a
    pooled figure being quoted is for it never to have been computed."""
    cohort = _ccohort(_spread("H", 2.0, 8), _spread("M", -1.0, 8))
    cohort += _ccohort(_spread("J", 2.0, 8), _spread("K", -1.0, 8), market="IDX")

    report = candidates_report(DEFAULT_CONTRACT, cohort, markets=("US", "IDX"))

    assert "gap" not in report
    assert "verdict" not in report
    assert _cfind(report, "US", _RELATIVE_MOVE)["groups"][GROUP_HIT]["symbols"] == 8
    assert _cfind(report, "IDX", _RELATIVE_MOVE)["groups"][GROUP_HIT]["symbols"] == 8


def test_the_measurement_is_arm_bs_and_refuses_another_arms_trades():
    """The pre-registered arm, for the reason the ranking gives: a cohort of arm A
    trades under this banner would price a dimension against a result no headline
    names."""
    cohort = _ccohort(_spread("H", 2.0, 6), _spread("M", -1.0, 6))
    cohort.append(_ctrade("X", 1.0, relative_move=+1.0, arm=ARM_A))

    with pytest.raises(ValueError, match="arm"):
        _cbody(cohort, _RELATIVE_MOVE)


def test_a_market_that_produced_no_trade_reports_its_zeros_rather_than_vanishing():
    """A silent market is a measurement — and possibly a data hole. An absent row
    and a market nobody measured are indistinguishable after the fact."""
    report = candidates_report(
        DEFAULT_CONTRACT,
        _ccohort(_spread("H", 2.0, 6), _spread("M", -1.0, 6)),
        markets=("US", "IDX"),
    )

    idx = _cfind(report, "IDX", _RELATIVE_MOVE)
    assert idx["trades"] == 0
    assert idx["verdict"] == CANDIDATE_TOO_THIN
    assert all(idx["groups"][g]["trades"] == 0 for g in GROUPS)


def test_the_report_says_why_it_is_not_also_cut_per_year():
    """The ranking reports per year and this does not, so the difference is stated
    rather than left as an omission a reader has to notice."""
    report = candidates_report(
        DEFAULT_CONTRACT, _ccohort(_spread("H", 2.0, 6), _spread("M", -1.0, 6))
    )

    assert "per year" in report["not_cut_per_year"]
    assert report["multiple_testing"]["intervals_reported"] >= 1


def test_the_count_of_intervals_the_candidate_report_states_rides_on_it():
    """Every group, gap and correlation is a claim at nominal alpha, so the budget
    is counted rather than left for a reader to infer from the page's length."""
    report = candidates_report(
        DEFAULT_CONTRACT,
        _ccohort(_spread("H", 2.0, 8), _spread("M", -1.0, 8)),
        markets=("US",),
    )

    counted = 0
    for body in report["markets"]:
        for cell in body["candidates"]:
            counted += sum(
                1 for g in GROUPS
                if cell["groups"][g]["bootstrap"]["ci_low"] is not None
            )
            counted += sum(
                1
                for key in ("gap", "rubric_reading", "value_correlation")
                if cell[key]["bootstrap"]["ci_low"] is not None
            )
    assert report["multiple_testing"]["intervals_reported"] == counted


def test_a_trade_with_no_persisted_detection_row_is_a_failure_not_a_drop():
    """The join from trade to row is **total** or the denominator is broken.

    Dropping an unmatched trade would shrink the cohort with nothing in the output
    to say which trades left, and the ones most likely to go missing are not a
    random sample.
    """
    with pytest.raises(ValueError, match="AAA"):
        candidate_trades([_mtrade("AAA", 2016, 1.0)], {})


def test_the_candidates_report_is_stamped_and_serialises():
    """Stamped with the contract that produced it, like every other result in the
    run, and JSON-clean so it can be committed beside them."""
    report = candidates_report(
        DEFAULT_CONTRACT, _ccohort(_spread("H", 2.0, 6), _spread("M", -1.0, 6))
    )

    assert report[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    assert json.loads(json.dumps(report)) == report


def test_the_printed_page_shows_every_group_with_its_n_and_both_claims():
    """A group's expectancy without its count is unreadable — six trades and six
    hundred print the same number — and the selection contrast prints above the
    outcome figures so a reader meets the older claim before the newer one."""
    report = candidates_report(
        DEFAULT_CONTRACT,
        _ccohort(_spread("H", 2.0, 8), _spread("M", -1.0, 8), _spread("Z", 0.1, 3)),
        markets=("US",),
    )

    page = format_candidates(report)

    assert _RELATIVE_MOVE in page and _RS_LINE in page
    assert "n=8" in page
    assert "absent" in page
    assert page.index("selection") < page.index("gap")


def test_the_candidate_measurement_runs_off_the_denominator_end_to_end(
    store, denominator
):
    """The seam that matters: persisted candidate values, the trades the simulator
    took off the same detections, joined by the session they were decided on."""
    _seed_figure_name(
        store, denominator, "US", "AAA", date(2020, 1, 1), _FIG_FLAT + _FIG_WIN,
        relative_move=+1.25,
    )
    trades = simulate_market(
        store, denominator, "US", DEFAULT_CONTRACT, arms=(ARM_B,)
    )

    cohort = candidate_trades(trades, detection_index(denominator, "US"))

    assert [c.trade.symbol for c in cohort] == ["AAA"]
    assert cohort[0].detection.relative_move == pytest.approx(1.25)
    body = _cbody(cohort, _RELATIVE_MOVE)
    assert body["groups"][GROUP_HIT]["trades"] == 1


def test_a_row_that_never_computed_the_dimension_reads_absent_not_a_miss():
    """The absence guard, followed one step further back than `group_of`.

    `group_of` reads absence off the stored value, so its claim is only as good as
    what the field wrote. A `ScoredDetection` built without the dimension computed
    at all defaults its value to **absent** rather than to `False` — until #195
    `rs_line` defaulted to `False`, which would have put a field nobody measured
    entirely on the miss side of a measurement whose whole subject is telling the
    two apart.
    """
    plain = build_field([_det("AAA", 6)], [])[0]

    assert plain.rs_line is None
    assert plain.relative_move is None
    assert group_of(named_candidate(_RS_LINE), plain) == GROUP_ABSENT
    assert group_of(named_candidate(_RELATIVE_MOVE), plain) == GROUP_ABSENT


def test_the_page_says_what_adr_0005_recorded_not_only_that_nothing_shipped():
    """"Not admitted" covers two different findings.

    `RS line` was refused on a wrong-way gap; `Relative move` landed on its own
    bound and the criteria failed to separate. A page printing only "not admitted"
    would flatten a refusal and an unresolved threshold into one word, and the
    second is the reason #195 exists.
    """
    report = candidates_report(
        DEFAULT_CONTRACT,
        _ccohort(_spread("H", 2.0, 6), _spread("M", -1.0, 6)),
        markets=("US",),
    )

    page = format_candidates(report)

    assert "criterion 4" in page
    assert "on_the_bound" in page
    assert (
        _cfind(report, "US", _RELATIVE_MOVE)["selection_contrast"]["recorded_as"]
        != _cfind(report, "US", _RS_LINE)["selection_contrast"]["recorded_as"]
    )

# -- anchor before believing (issue #197) --------------------------------------
#
# Phase 6's table, and the two things it exists to prevent. The run overlaps
# ground the reference study already measured, so it reproduces those figures
# before any new figure from it is read — a mismatch is a bug in the new store or
# the new chain, and every downstream number inherits it.
#
# Four claims are load-bearing:
#
#   * **Geometry first, and apart.** The three medians are measured from his bars
#     and hold whatever the detector does. If they fail, the gate-dependent
#     anchors are not read at all: nothing downstream is worth investigating yet.
#   * **Every anchor carries its detector stamp and its superseded pins.** An
#     anchor quoted from a stale pin fails for a reason that has nothing to do
#     with the pipeline it is testing, and `in_field` at v2 is a different number
#     from `in_field` at v3.
#   * **Detection recall and `in_field` are different quantities** — the
#     conflation #165 fixed, made unrepresentable rather than merely documented.
#   * **The #162 tolerance covers a few trades, never a sign flip.** A fresh build
#     shifts percentile denominators by ~0.5%; a difference that changes the sign
#     of §4b's gap is the bug the table is looking for.

from backtest.anchors import (
    ANCHOR_ARMS,
    ANCHORS,
    ANCHORS_BY_KEY,
    CONTAMINATION_TRADES,
    GATE_DEPENDENT,
    GATE_DEPENDENT_ANCHORS,
    gate_dependent_anchors,
    GEOMETRY,
    GEOMETRY_ANCHORS,
    QUANTITY_DETECTION_RECALL,
    QUANTITY_IN_FIELD,
    UNIVERSE_APP,
    UNIVERSE_STATELESS,
    _field_measurements,
    _universe_of,
    AnchorReport,
    GeometrySample,
    Measurement,
    anchors_report,
    check_anchors,
    check_geometry,
    coverage_measurement,
    format_anchors,
    geometry_measurements,
    in_field_measurement,
    measure_geometry,
    recall_measurement,
    trailing_range_adr,
)
from backtest.anchors import main as anchors_main
from backtest.simulate import ARM_A, ARM_B, ARM_C
from replay.funnel import StageRecall
from replay.discrimination_grid import (
    DETECTORS,
    FIELD_TRUNCATED,
    FIELD_WHOLE,
    CellMeasurement,
)
from replay.placement import RubricStarDistributions, StarDistribution
from replay.reference import REFERENCE_FIGURES
from screener.detection import DETECTOR_VERSION, range_3bar_adr
from screener.indicators import adr as _adr_of


def _geometry_measurements(
    *, three: float = 1.31, five: float = 1.86, adr: float = 0.0608
) -> list[Measurement]:
    """The three geometry measurements, at their committed values by default."""
    return [
        Measurement(anchor="median_range_3bar_adr", quantity="bar-geometry",
                    values={"median": three}),
        Measurement(anchor="median_range_5bar_adr", quantity="bar-geometry",
                    values={"median": five}),
        Measurement(anchor="median_adr_at_entry_eve", quantity="bar-geometry",
                    values={"median": adr}),
    ]


def _coverage_measurement(**overrides) -> Measurement:
    values = {
        "blind_spot_tickers": REFERENCE_FIGURES["blind_spot_tickers"],
        "blind_spot_trades": REFERENCE_FIGURES["blind_spot_trades"],
        "distinct_tickers": REFERENCE_FIGURES["distinct_tickers"],
        "total_rows": REFERENCE_FIGURES["total_rows"],
        "rows_with_outcomes": REFERENCE_FIGURES["rows_with_outcomes"],
        "blind_spot_r_share": REFERENCE_FIGURES["blind_spot_r_share"],
    }
    values.update(overrides)
    return Measurement(anchor="coverage_blind_spot",
                       quantity="reference-coverage", values=values)


def _recall(passed: int = 549, total: int = 656) -> StageRecall:
    return StageRecall(stage=STAGE_DETECTION, passed=passed, total=total,
                       passed_ex_continuation=passed, total_ex_continuation=total)


def _cell(
    *,
    version: int = 3,
    in_field: int = 397,
    picks_share: float = 0.1360,
    field_share: float = 0.1165,
    field_source=FIELD_WHOLE,
) -> CellMeasurement:
    """A grid cell whose ≥3.5★ shares land on the pair §4b's v3 row reports.

    The shares are built as histograms rather than stored as rates, because
    ``CellMeasurement.edge`` reads them off the distributions and a cell carrying
    a rate the histogram does not support would test nothing.
    """
    def dist(share: float, n: int = 10_000) -> StarDistribution:
        hits = round(share * n)
        return StarDistribution.from_stars([4.0] * hits + [1.0] * (n - hits))

    return CellMeasurement(
        detector=DETECTORS[version],
        field_source=field_source,
        measured_sessions=821,
        sessions_with_detections=821,
        field_detections=64_070,
        placed=in_field,
        in_field=in_field,
        eval_field_detections=64_070,
        by_rubric=[
            RubricStarDistributions(
                rubric_version=1,
                picks=dist(picks_share),
                field=dist(field_share),
                top_thirty=103,
            )
        ],
    )


def _all_measurements(**kwargs) -> list[Measurement]:
    """Every anchor's measurement, all at their committed values by default."""
    return [
        *_geometry_measurements(**kwargs.pop("geometry", {})),
        _coverage_measurement(**kwargs.pop("coverage", {})),
        recall_measurement(_recall(**kwargs.pop("recall", {}))),
        in_field_measurement(
            _cell(**kwargs.pop("cell", {})),
            replayable=kwargs.pop("replayable", 656),
            universe=UNIVERSE_APP,
        ),
    ]


# -- the table itself ----------------------------------------------------------


def test_the_table_holds_six_anchors_with_the_three_geometry_ones_first():
    """The plan's order is a claim about what is worth reading when: geometry
    anchors the store and the indicators, so it is checked before anything that
    depends on a gate.

    The table carries seven rows and a run is held to six of them. The extra row
    is ``in_field``'s second universe (#211), and a run screens its field with one
    set of gates or the other — never both — so exactly one of the two applies.
    """
    assert len(ANCHORS) == 7
    assert len(gate_dependent_anchors(UNIVERSE_APP)) == 3
    assert len(gate_dependent_anchors(UNIVERSE_STATELESS)) == 3
    assert len(GEOMETRY_ANCHORS) + len(gate_dependent_anchors(UNIVERSE_APP)) == 6
    assert [a.key for a in ANCHORS[:3]] == [a.key for a in GEOMETRY_ANCHORS]
    assert {a.kind for a in GEOMETRY_ANCHORS} == {GEOMETRY}
    assert {a.kind for a in GATE_DEPENDENT_ANCHORS} == {GATE_DEPENDENT}
    assert [a.committed["median"] for a in GEOMETRY_ANCHORS] == [1.31, 1.86, 0.0608]


def test_every_anchor_is_stamped_with_the_detector_version_it_was_measured_at():
    """Ticket criterion: a figure whose version is absent gets compared against a
    run built at another one, which is exactly how the `in_field` row went wrong."""
    stamps = {a.key: a.detector_stamp for a in ANCHORS}

    # Geometry holds whatever the detector does, and says so rather than going
    # unstamped — an empty stamp reads as "not recorded".
    for anchor in GEOMETRY_ANCHORS:
        assert stamps[anchor.key] == "detector-independent (bar geometry)"
    # Gate-invariant, and measured under both versions' geometry.
    assert ANCHORS_BY_KEY["detection_recall"].measured_at == (2, 3)
    assert ANCHORS_BY_KEY["detection_recall"].holds_at(2)
    # Per version, because the quantity is per version.
    assert ANCHORS_BY_KEY["in_field"].measured_at == (3,)
    assert not ANCHORS_BY_KEY["in_field"].holds_at(2)
    assert stamps["in_field"] == "detector v3"


def test_the_in_field_anchor_is_taken_at_the_live_detector_and_flagged_first():
    """397 of 656 at v3 is a first measurement with no second one agreeing with
    it, so a mismatch is investigated in both directions rather than charged
    straight to the new pipeline."""
    anchor = ANCHORS_BY_KEY["in_field"]

    assert anchor.committed["in_field"] == 397
    assert anchor.committed["of"] == 656
    assert anchor.measured_at == (DETECTOR_VERSION,)
    assert anchor.first_measurement is True
    assert not ANCHORS_BY_KEY["detection_recall"].first_measurement


def test_every_superseded_pin_is_recorded_beside_its_live_value():
    """An anchor quoted from a stale pin fails for a reason unrelated to the
    pipeline it is testing, so each superseded figure sits on the anchor with what
    moved it — not in a comment and not in the plan alone."""
    in_field = ANCHORS_BY_KEY["in_field"]
    values = [p.value for p in in_field.superseded]

    assert "349 of 656 at detector v2" in values
    assert any("159 of 656" in v for v in values)
    assert any("104 of 656" in v for v in values)
    assert any("104 of 658" in v for v in values)
    assert all(p.why for p in in_field.superseded)
    # The other two gate-dependent rows have moved too, and carry their own.
    assert any("380 of 658" in p.value
               for p in ANCHORS_BY_KEY["detection_recall"].superseded)
    assert ANCHORS_BY_KEY["coverage_blind_spot"].superseded


def test_the_coverage_anchor_reads_the_reference_modules_own_pins():
    """No second definition of the coverage figures: this table and
    ``replay.reference.assert_matches_reference`` check the same numbers, so they
    cannot come to disagree about what was committed."""
    committed = ANCHORS_BY_KEY["coverage_blind_spot"].committed

    assert committed["blind_spot_tickers"] == REFERENCE_FIGURES["blind_spot_tickers"]
    assert committed["blind_spot_trades"] == REFERENCE_FIGURES["blind_spot_trades"]
    assert committed["distinct_tickers"] == REFERENCE_FIGURES["distinct_tickers"]
    assert committed["total_rows"] == REFERENCE_FIGURES["total_rows"]


def test_the_field_rows_carry_the_reference_contamination_tolerance():
    """Both `in_field` values were measured on the store that ranks five
    references as candidates; the tolerance is that fix landing, and it says so."""
    anchor = ANCHORS_BY_KEY["in_field"]

    assert anchor.tolerance["in_field"] == CONTAMINATION_TRADES
    assert "#162" in (anchor.tolerance_reason or "")
    # Recorded on both field rows: the live v3 value and the superseded v2 one.
    assert any("v2" in p.value for p in anchor.superseded)
    # The denominator is not inside the tolerance — a changed replayable
    # population is coverage drift, which the coverage anchor owns.
    assert anchor.tolerance["of"] == 0


# -- the check -----------------------------------------------------------------


def test_the_six_anchors_check_through_the_drift_mechanism_and_report_apart():
    """The happy path: every anchor at its committed value, geometry reported in
    its own group ahead of the gate-dependent three."""
    report = check_anchors(_all_measurements())

    assert [c.anchor.key for c in report.geometry] == [
        "median_range_3bar_adr", "median_range_5bar_adr", "median_adr_at_entry_eve",
    ]
    assert [c.anchor.key for c in report.gate_dependent] == [
        "coverage_blind_spot", "detection_recall", "in_field",
    ]
    assert all(c.matched for c in report.checks)
    assert report.passes


def test_a_geometry_failure_stops_before_the_gate_dependent_anchors_are_read():
    """If the store's own geometry does not reproduce, no figure measured over
    that store is worth investigating yet — so the check says so and stops."""
    measurements = [
        *_geometry_measurements(three=1.31, five=2.60, adr=0.0608),
        _coverage_measurement(),
        recall_measurement(_recall()),
        in_field_measurement(_cell(), replayable=656, universe=UNIVERSE_APP),
    ]

    with pytest.raises(DriftError) as excinfo:
        check_anchors(measurements)

    message = str(excinfo.value)
    assert "median_range_5bar_adr" in message
    assert "gate-dependent" in message and "not read" in message
    # The gate-dependent anchors are absent from the failure entirely: reporting
    # them here would invite investigating a number that cannot be trusted.
    assert "in_field" not in message


def test_a_gate_dependent_mismatch_fails_loudly_with_both_figures():
    """The drift mechanism the study has used since #114: a mismatch raises rather
    than logging, and names what came back against what was committed."""
    with pytest.raises(DriftError) as excinfo:
        check_anchors(_all_measurements(recall={"passed": 500}))

    assert "detection_recall" in str(excinfo.value)
    assert "500" in str(excinfo.value) and "549" in str(excinfo.value)


def test_detection_recall_admits_no_tolerance():
    """It is gate-invariant and exact: the funnel evaluates every stage
    unconditionally, so nothing about a fresh build moves it by a trade."""
    assert ANCHORS_BY_KEY["detection_recall"].tolerance == {"passed": 0, "of": 0}

    with pytest.raises(DriftError):
        check_anchors(_all_measurements(recall={"passed": 548}))


def test_the_contamination_tolerance_absorbs_a_few_trades_on_the_field_row():
    """A fresh build shifts percentile denominators by ~0.5%, which moves decile
    membership at the margin. That is the fix landing, not a bug."""
    report = check_anchors(
        _all_measurements(cell={"in_field": 397 - CONTAMINATION_TRADES})
    )

    check = next(c for c in report.gate_dependent if c.anchor.key == "in_field")
    assert check.matched
    assert report.passes


def test_a_field_difference_past_the_contamination_band_fails():
    """The tolerance is bounded by what the denominator shift can do; past it the
    difference is not a denominator shift."""
    with pytest.raises(DriftError) as excinfo:
        check_anchors(
            _all_measurements(cell={"in_field": 397 - CONTAMINATION_TRADES - 1})
        )

    assert "in_field" in str(excinfo.value)


def test_a_sign_flip_in_the_gap_fails_inside_the_trade_tolerance():
    """The one thing the tolerance may not absorb. The trade count is well inside
    the band, and the anchor fails anyway, because a gap that changes sign is the
    bug this table exists to find."""
    with pytest.raises(DriftError) as excinfo:
        check_anchors(
            _all_measurements(
                cell={"in_field": 396, "picks_share": 0.1165, "field_share": 0.1360}
            )
        )

    message = str(excinfo.value)
    assert "gap_pp" in message
    assert "sign" in message and "tolerance does not cover" in message


def test_the_gaps_magnitude_is_free_to_move():
    """Only the sign is anchored. The gap is a rate on two populations a fresh
    build re-derives, so pinning its magnitude would fail every honest run."""
    report = check_anchors(
        _all_measurements(cell={"picks_share": 0.30, "field_share": 0.10})
    )

    gap = next(
        c for a in report.gate_dependent if a.anchor.key == "in_field"
        for c in a.components if c.name == "gap_pp"
    )
    assert gap.measured == pytest.approx(20.0)
    assert gap.matched and not gap.sign_flipped


def test_detection_recall_and_in_field_cannot_be_checked_against_each_other():
    """The conflation #165 fixed, made unrepresentable. Offering the funnel's
    recall as the field-membership measurement fails at the seam rather than
    failing an anchor that should have passed."""
    recall = recall_measurement(_recall())
    misfiled = dataclasses.replace(recall, anchor="in_field")

    with pytest.raises(DriftError) as excinfo:
        check_anchors([
            *_geometry_measurements(), _coverage_measurement(),
            recall, misfiled,
        ])

    message = str(excinfo.value)
    assert "different quantities" in message and "#165" in message
    assert QUANTITY_IN_FIELD in message and QUANTITY_DETECTION_RECALL in message


def test_the_two_field_measurements_come_from_two_different_types():
    """Structural, not documentary: recall is read off the funnel's detection
    stage and `in_field` off a grid cell, so neither adapter can produce the
    other's measurement."""
    assert recall_measurement(_recall()).quantity == QUANTITY_DETECTION_RECALL
    assert (
        in_field_measurement(
            _cell(), replayable=656, universe=UNIVERSE_APP
        ).quantity == QUANTITY_IN_FIELD
    )
    with pytest.raises(DriftError):
        recall_measurement(dataclasses.replace(_recall(), stage="liquidity"))


def test_in_field_is_anchored_on_the_whole_field_only():
    """Every figure over the truncated field is superseded: the two-year rank
    retention emptied 316 of 821 sessions, and #164 measured what that did."""
    with pytest.raises(DriftError) as excinfo:
        in_field_measurement(
            _cell(field_source=FIELD_TRUNCATED), replayable=656,
            universe=UNIVERSE_APP,
        )

    assert "whole field" in str(excinfo.value)


def test_a_field_measurement_from_another_detector_version_is_refused():
    """397 is v3's number. A run built at v3 checked against a v2 cell — or the
    reverse — fails an anchor it should pass, which is the error the per-version
    stamp exists to prevent."""
    with pytest.raises(DriftError) as excinfo:
        check_anchors(_all_measurements(cell={"version": 2, "in_field": 349}))

    assert "v2" in str(excinfo.value) and "built at" in str(excinfo.value)

    # And the anchor itself refuses to be quoted at a version it never measured.
    with pytest.raises(DriftError) as excinfo:
        check_anchors(_all_measurements(), detector_version=2)

    assert "no committed value at detector v2" in str(excinfo.value)


def test_an_anchor_with_no_measurement_fails_rather_than_vanishing():
    """A partially anchored run is not an anchored run, and an anchor that is
    silently absent from the report reads as one that passed."""
    with pytest.raises(DriftError) as excinfo:
        check_anchors([*_geometry_measurements(), _coverage_measurement(),
                       recall_measurement(_recall())])

    assert "in_field" in str(excinfo.value) and "no measurement" in str(excinfo.value)


def test_a_median_that_could_not_be_computed_fails_rather_than_passing():
    """An empty sample yields no median, which is a failure of the store — never
    an anchor quietly skipped."""
    empty = GeometrySample(
        n=0, median_range_3bar_adr=None, median_range_5bar_adr=None,
        median_adr_at_entry_eve=None, without_bars=828, short_history=0,
        no_prior_session=0,
    )

    with pytest.raises(DriftError) as excinfo:
        check_anchors([
            *geometry_measurements(empty), _coverage_measurement(),
            recall_measurement(_recall()),
            in_field_measurement(_cell(), replayable=656, universe=UNIVERSE_APP),
        ])

    assert "median_range_3bar_adr" in str(excinfo.value)


def test_a_divergence_written_up_is_recorded_and_never_prints_as_a_match():
    """The plan's "reproduce it, or explain the divergence in writing". A cause
    lets the run proceed; the anchor still reports as diverged, so the write-up
    cannot be mistaken for a reproduction."""
    report = check_anchors(
        _all_measurements(recall={"passed": 500}),
        explained={"detection_recall": "the crawl resolves 3 names the replay "
                                       "store never held; listed in the write-up"},
    )

    check = next(c for c in report.gate_dependent
                 if c.anchor.key == "detection_recall")
    assert not check.matched
    assert check.explained and check.passes
    assert check.verdict == "diverged (explained)"
    assert report.passes


def test_an_explanation_for_an_anchor_that_does_not_exist_is_refused():
    """A typo in an anchor key would otherwise silently explain nothing while
    reading as though it had explained something."""
    with pytest.raises(DriftError):
        check_anchors(_all_measurements(), explained={"in-field": "typo"})


# -- arms B and C --------------------------------------------------------------


def test_anchoring_uses_arms_b_and_c_only():
    """Arm A has no counterpart in the reference set, so it is measured and never
    anchored — and the fact is derived from the arm table, not restated here."""
    assert ANCHOR_ARMS == (ARM_B, ARM_C)
    assert ARM_A not in ANCHOR_ARMS

    with pytest.raises(DriftError) as excinfo:
        check_anchors(_all_measurements(), arms=(ARM_A,))

    assert "no counterpart in the reference set" in str(excinfo.value)


def test_a_measurement_tagged_with_arm_a_is_refused():
    """The refusal reaches the measurement too: an anchor taken on arm A would be
    an anchor against an exit the reference set never simulated."""
    recall = recall_measurement(_recall(), arm=ARM_A)

    with pytest.raises(DriftError) as excinfo:
        check_anchors([
            *_geometry_measurements(), _coverage_measurement(), recall,
            in_field_measurement(_cell(), replayable=656, universe=UNIVERSE_APP),
        ])

    assert "arm 'A'" in str(excinfo.value)


def test_an_arm_b_measurement_anchors_normally():
    report = check_anchors([
        *_geometry_measurements(), _coverage_measurement(),
        recall_measurement(_recall(), arm=ARM_B),
        in_field_measurement(_cell(), replayable=656, universe=UNIVERSE_APP,
                             arm=ARM_B),
    ])

    assert report.passes
    assert report.arms == ANCHOR_ARMS


# -- the geometry, measured off the store --------------------------------------


def _anchor_session(index: int) -> date:
    return date(2020, 1, 1) + timedelta(days=index)


def _geometry_bars(n: int = 40, *, spike_last: bool = False) -> list[Bar]:
    """A quiet series of identical-shaped bars, optionally with a wild last one.

    Every bar has the same 2% high/low span, so ADR and the trailing ranges are
    hand-checkable, and the last bar is the *entry* session — a measurement that
    read it instead of the eve would move by an order of magnitude.
    """
    bars = []
    for i in range(n):
        high, low = 102.0, 100.0
        if spike_last and i == n - 1:
            high, low = 300.0, 50.0
        bars.append(
            Bar(session=_anchor_session(i), open=101.0, high=high, low=low,
                close=101.0, adj_close=101.0, volume=1_000_000)
        )
    return bars


def test_the_five_bar_ruler_agrees_with_the_detectors_own_at_three_bars():
    """There is no second definition of the trailing range: the k-generic ruler
    here reduces to ``screener.detection.range_3bar_adr`` at k = 3, so the two
    cannot drift into disagreeing about the same number."""
    bars = _geometry_bars(30)
    # A ragged tail, so the identity is tested on a series where k actually
    # changes the answer rather than on flat bars where every k agrees.
    bars[-1] = dataclasses.replace(bars[-1], high=110.0, low=99.0)
    bars[-3] = dataclasses.replace(bars[-3], high=104.0, low=95.0)

    idx = len(bars) - 1
    adr_abs = _adr_of(bars) * bars[idx].close
    theirs = range_3bar_adr(
        [b.high for b in bars], [b.low for b in bars], idx, adr_abs
    )

    assert trailing_range_adr(bars, idx, 3) == pytest.approx(theirs)
    # And k = 5 is at least as wide, which is the property that makes k = 3 the
    # tightest window the cluster scan can see.
    assert trailing_range_adr(bars, idx, 5) >= trailing_range_adr(bars, idx, 3)


def test_the_geometry_is_measured_at_the_evaluation_session_not_the_entry(store):
    """Point-in-time, like every other value entering a decision: the entry
    session's own bar is ahead of the night the app would have had to name the
    stock, so it never enters the anchor."""
    bars = _geometry_bars(40, spike_last=True)
    store.append_bars("US", "AAA", bars)
    trades = parse_trades([_trade_record("AAA", bars[-1].session.isoformat())])

    measured = measure_geometry(store, trades, market="US")

    eve_index = len(bars) - 2
    expected_3 = trailing_range_adr(bars, eve_index, 3)
    assert measured.n == 1
    assert measured.median_range_3bar_adr == pytest.approx(expected_3)
    assert measured.median_adr_at_entry_eve == pytest.approx(_adr_of(bars[:-1]))
    # The spike would have trebled it, which is what makes this test worth having.
    assert trailing_range_adr(bars, len(bars) - 1, 3) > 3 * expected_3


def test_a_trade_contributes_to_all_three_medians_or_to_none(store):
    """The three figures are taken over one sample, so a divergence between them
    can never be a difference in who was included."""
    store.append_bars("US", "AAA", _geometry_bars(40))
    store.append_bars("US", "SHORT", _geometry_bars(5))
    entry = _anchor_session(39).isoformat()
    trades = parse_trades([
        _trade_record("AAA", entry),
        _trade_record("SHORT", entry),
        _trade_record("GONE", entry),
    ])

    measured = measure_geometry(store, trades, market="US")

    assert measured.n == 1
    assert measured.without_bars == 1     # GONE: the survivorship hole
    assert measured.short_history == 1    # SHORT: fewer than 20 bars at the eve
    assert measured.median_range_5bar_adr is not None


def test_the_geometry_sample_size_rides_on_the_report(store):
    """A median over a silently halved sample prints as a plausible number, so how
    many trades stood behind it travels with it."""
    store.append_bars("US", "AAA", _geometry_bars(40))
    entry = _anchor_session(39).isoformat()
    trades = parse_trades([_trade_record("AAA", entry), _trade_record("GONE", entry)])
    measured = measure_geometry(store, trades, market="US")

    report = check_anchors(
        [
            *geometry_measurements(
                dataclasses.replace(
                    measured,
                    median_range_3bar_adr=1.31,
                    median_range_5bar_adr=1.86,
                    median_adr_at_entry_eve=0.0608,
                )
            ),
            _coverage_measurement(),
            recall_measurement(_recall()),
            in_field_measurement(_cell(), replayable=656, universe=UNIVERSE_APP),
        ],
        sample=measured,
    )
    body = anchors_report(DEFAULT_CONTRACT, report)

    assert body["geometry_sample"]["n"] == 1
    assert body["geometry_sample"]["without_bars"] == 1


def test_coverage_is_measured_off_the_reference_report(store):
    """The coverage anchor reads the same report ``replay.reference`` builds — one
    classification of the reference set, not a second one that could disagree."""
    store.append_bars("US", "AAA", _geometry_bars(40))
    entry = _anchor_session(39).isoformat()
    trades = parse_trades([_trade_record("AAA", entry), _trade_record("GONE", entry)])

    measurement = coverage_measurement(build_report(trades, store, market="US"))

    assert measurement.values["blind_spot_tickers"] == 1
    assert measurement.values["total_rows"] == 2


# -- the result, and the command ------------------------------------------------


def test_the_anchor_report_is_stamped_and_serialises():
    """Like every figure the package emits: the contract rides on it, and the two
    groups stay separate keys rather than one list a reader has to sort."""
    report = check_anchors(_all_measurements())
    body = anchors_report(DEFAULT_CONTRACT, report)

    assert body[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    assert [c["anchor"] for c in body["geometry"]] == [
        a.key for a in GEOMETRY_ANCHORS
    ]
    assert [c["anchor"] for c in body["gate_dependent"]] == [
        a.key for a in gate_dependent_anchors(UNIVERSE_APP)
    ]
    assert body["arms_anchored"] == list(ANCHOR_ARMS)
    assert body["arms_measured_never_anchored"] == [ARM_A]
    assert json.loads(json.dumps(body)) == body


def test_the_stamp_and_the_pins_ride_on_the_serialised_result():
    """A report a reader can check without the plan open beside it."""
    body = anchors_report(DEFAULT_CONTRACT, check_anchors(_all_measurements()))
    in_field = next(c for c in body["gate_dependent"] if c["anchor"] == "in_field")

    assert in_field["detector_stamp"] == "detector v3"
    assert in_field["first_measurement"] is True
    assert "#162" in in_field["tolerance_reason"]
    assert len(in_field["superseded"]) == 4


def test_the_printed_report_separates_the_two_kinds_of_anchor():
    text = format_anchors(check_anchors(_all_measurements()))

    assert "geometry — measured from his bars" in text
    assert "gate-dependent — these move" in text
    assert text.index("geometry — measured") < text.index("gate-dependent — these")
    assert "measured, never anchored" in text


def test_an_unchecked_gate_dependent_group_is_reported_as_unchecked():
    """A run anchored on four of six is not anchored, and an empty section reads
    as three passes unless it says otherwise."""
    report = AnchorReport(
        detector_version=DETECTOR_VERSION,
        arms=ANCHOR_ARMS,
        geometry=check_geometry(_geometry_measurements()),
        gate_dependent=(),
        geometry_only=True,
    )

    assert not report.passes
    assert "NOT CHECKED" in format_anchors(report)


def _anchor_cli_store(tmp_path) -> tuple[Path, Path]:
    """A one-name store and a reference set whose geometry lands on the anchors.

    The store is written to disk because the command opens one; the bars are
    scaled so the three medians sit exactly on their committed values, which is
    what lets the command's *pass* path be exercised without a 649-trade fixture.
    """
    path = tmp_path / "backtest_anchor.duckdb"
    store = Store.open(path)
    store.append_bars("US", "AAA", _geometry_bars(40))
    store.close()

    reference = tmp_path / "trades.json"
    reference.write_text(
        json.dumps([_trade_record("AAA", _anchor_session(39).isoformat())])
    )
    return path, reference


def test_the_command_refuses_to_report_a_run_anchored_on_four_of_six(
    tmp_path, capsys
):
    """Without the run's own field measurements the two gate-dependent field
    anchors are not checked, and a report that printed the four it *could* check
    would read as an anchored run. It says what it did not check, and fails."""
    path, reference = _anchor_cli_store(tmp_path)

    code = anchors_main([
        "--store", str(path), "--reference", str(reference),
    ])

    assert code == 1
    printed = capsys.readouterr().out
    assert "NOT CHECKED" in printed
    assert "the run is not anchored" in printed
    # The geometry it did check is still reported — that is the point of running
    # it at all before the field pass exists.
    assert "Median trailing 3-bar range" in printed


def test_the_command_writes_a_stamped_result_when_every_anchor_is_offered(
    tmp_path, capsys
):
    """The whole Phase 6 path: geometry and coverage measured off the store, the
    two field anchors read from the run's own pass, the result stamped."""
    path, reference = _anchor_cli_store(tmp_path)
    field = tmp_path / "field.json"
    field.write_text(json.dumps({
        "detection_recall": {"passed": 549, "of": 656, "stage": "detection"},
        "in_field": {"in_field": 395, "of": 656, "gap_pp": 1.9,
                     "field": "whole", "universe": UNIVERSE_APP, "detector_version": 3},
    }))
    out_json = tmp_path / "anchors.json"

    code = anchors_main([
        "--store", str(path), "--reference", str(reference),
        "--field-measurements", str(field),
        "--out-json", str(out_json),
        # The one-name fixture cannot reproduce his 649-trade medians or the
        # 828-row coverage, so those divergences are written up — which is the
        # other half of "reproduce it, or explain it".
        "--explain", "median_range_3bar_adr=one-name fixture",
        "--explain", "median_range_5bar_adr=one-name fixture",
        "--explain", "median_adr_at_entry_eve=one-name fixture",
        "--explain", "coverage_blind_spot=one-name fixture",
    ])

    assert code == 0
    written = json.loads(out_json.read_text())
    assert written[CONTRACT_KEY] == DEFAULT_CONTRACT.to_dict()
    in_field = next(
        c for c in written["gate_dependent"] if c["anchor"] == "in_field"
    )
    assert in_field["verdict"] == "match"       # 395 is inside the #162 band
    assert written["passes"] is True
    geometry = written["geometry"][0]
    assert geometry["verdict"] == "diverged (explained)"
    assert capsys.readouterr().out.count("diverged (explained)") >= 1


def test_the_command_fails_on_a_field_anchor_from_the_wrong_version(tmp_path):
    """The failure the per-version stamp exists to catch, through the command:
    v2's 349 quoted at a run built on v3."""
    path, reference = _anchor_cli_store(tmp_path)
    field = tmp_path / "field.json"
    field.write_text(json.dumps({
        "detection_recall": {"passed": 549, "of": 656, "stage": "detection"},
        "in_field": {"in_field": 349, "of": 656, "gap_pp": 2.02,
                     "field": "whole", "universe": UNIVERSE_APP, "detector_version": 2},
    }))

    code = anchors_main([
        "--store", str(path), "--reference", str(reference),
        "--field-measurements", str(field),
        "--explain", "median_range_3bar_adr=one-name fixture",
        "--explain", "median_range_5bar_adr=one-name fixture",
        "--explain", "median_adr_at_entry_eve=one-name fixture",
        "--explain", "coverage_blind_spot=one-name fixture",
    ])

    assert code == 1


# -- what the #197 review found unguarded --------------------------------------

from backtest.anchors import MEASURED_NEVER_ANCHORED
from backtest.simulate import ARM_SPECS
from replay.reference import R_SHARE_TOL


def test_a_sign_flip_cannot_be_waived_by_writing_it_up():
    """The one failure this table exists to find, and the one no cause excuses.
    Every other divergence may be explained in writing; a flip in the sign of
    §4b's gap must stop the run and be investigated in the pipeline, or the anchor
    is waivable by a free-text argument and guards nothing."""
    flipped = _all_measurements(
        cell={"in_field": 396, "picks_share": 0.1165, "field_share": 0.1360}
    )

    with pytest.raises(DriftError) as excinfo:
        check_anchors(flipped, explained={"in_field": "a plausible-sounding cause"})

    assert "sign" in str(excinfo.value)
    # The same explain path *does* carry an ordinary divergence, so the refusal is
    # specific to the sign rather than the write-up being broken.
    assert check_anchors(
        _all_measurements(recall={"passed": 500}),
        explained={"detection_recall": "a written cause"},
    ).passes


def test_the_command_enforces_the_same_two_gates_its_adapters_do(tmp_path, capsys):
    """The file path is the one the documented reproduction command uses, so the
    conflation guard has to hold there too: a field row that does not name the
    whole field, or a recall row that does not name the detection stage, is
    refused rather than believed."""
    path, reference = _anchor_cli_store(tmp_path)
    explain = [
        "--explain", "median_range_3bar_adr=one-name fixture",
        "--explain", "median_range_5bar_adr=one-name fixture",
        "--explain", "median_adr_at_entry_eve=one-name fixture",
        "--explain", "coverage_blind_spot=one-name fixture",
    ]

    truncated = tmp_path / "truncated.json"
    truncated.write_text(json.dumps({
        "detection_recall": {"passed": 549, "of": 656, "stage": "detection"},
        "in_field": {"in_field": 397, "of": 656, "gap_pp": 1.95,
                     "field": "truncated", "universe": UNIVERSE_APP,
                     "detector_version": 3},
    }))
    assert anchors_main(["--store", str(path), "--reference", str(reference),
                         "--field-measurements", str(truncated), *explain]) == 1
    assert "whole field" in capsys.readouterr().out

    wrong_stage = tmp_path / "stage.json"
    wrong_stage.write_text(json.dumps({
        "detection_recall": {"passed": 549, "of": 656, "stage": "liquidity"},
        "in_field": {"in_field": 397, "of": 656, "gap_pp": 1.95,
                     "field": "whole", "universe": UNIVERSE_APP,
                     "detector_version": 3},
    }))
    assert anchors_main(["--store", str(path), "--reference", str(reference),
                         "--field-measurements", str(wrong_stage), *explain]) == 1
    assert "detection stage" in capsys.readouterr().out


def test_the_coverage_anchor_is_no_weaker_than_the_reference_assertion():
    """It checks all five of the reference module's pins, the realised-R share
    included. A run reproducing the counts while moving the share would have
    changed *which* trades are missing, and a coverage check that passed it would
    be weaker than the one this repo already had."""
    anchor = ANCHORS_BY_KEY["coverage_blind_spot"]

    assert set(anchor.committed) == set(REFERENCE_FIGURES)
    assert anchor.committed["blind_spot_r_share"] == (
        REFERENCE_FIGURES["blind_spot_r_share"]
    )
    # Pinned to the reference module's own band, not to a second one.
    assert anchor.tolerance["blind_spot_r_share"] == R_SHARE_TOL

    with pytest.raises(DriftError):
        check_anchors(_all_measurements(coverage={"blind_spot_r_share": 0.25}))


def test_the_contamination_tolerance_is_recorded_on_the_superseded_field_row_too():
    """Both `in_field` values were measured on the contaminated field, so the v2
    pin says so: a run built at v2 anchors on it under the same band, and a reader
    who found the note only on the live row would think the pin was clean."""
    v2 = next(
        p for p in ANCHORS_BY_KEY["in_field"].superseded
        if "at detector v2" in p.value
    )

    assert "#162" in v2.why
    assert "contaminated field" in v2.why


def test_the_arms_never_anchored_are_derived_once():
    """The module's own rule — an arm's comparability is one fact, read in one
    place — applied to the complement as well as to the set."""
    assert MEASURED_NEVER_ANCHORED == (ARM_A,)
    assert set(MEASURED_NEVER_ANCHORED) | set(ANCHOR_ARMS) == set(ARM_SPECS)


# -- the two universes, and the anchor scoped to each ---------------------------


def _stateless_cell(**overrides) -> CellMeasurement:
    """A grid cell landing on the pair the contract's own universe measured.

    ``in_field`` 165 of 503, and shares whose difference is §4b's gap with the
    sign #211 attributed to the ADR floor and the trend gate together.
    """
    return _cell(**{
        "in_field": 165, "picks_share": 0.1335, "field_share": 0.1836,
        **overrides,
    })


def _stateless_measurements(**overrides) -> list[Measurement]:
    """Every anchor's measurement for a run over the contract's stateless universe.

    Coverage and recall are left at their committed values: neither moves with the
    universe, and holding them still is what keeps these tests about the one
    anchor that does.
    """
    return [
        *_geometry_measurements(**overrides.pop("geometry", {})),
        _coverage_measurement(),
        recall_measurement(_recall()),
        in_field_measurement(
            _stateless_cell(**overrides.pop("cell", {})),
            replayable=overrides.pop("replayable", 503),
            universe=UNIVERSE_STATELESS,
        ),
    ]


def test_the_table_scopes_in_field_to_the_universe_it_was_measured_over():
    """§4b's +1.95pp and the run's own −5.01pp are one quantity over two different
    universes, and #211 measured that the pair is what the number is a property
    of. Two anchors, each naming its universe, is that finding as data: a run is
    checked against the pin measured over the universe it actually ran."""
    app = ANCHORS_BY_KEY["in_field"]
    stateless = ANCHORS_BY_KEY["in_field_stateless"]

    assert app.universe == UNIVERSE_APP
    assert stateless.universe == UNIVERSE_STATELESS
    assert app.quantity == stateless.quantity == QUANTITY_IN_FIELD
    assert app.committed["gap_pp"] == 1.95
    assert stateless.committed["in_field"] == 165
    assert stateless.committed["of"] == 503


def test_the_geometry_anchors_hold_over_either_universe():
    """They are medians off his bars and no gate touches them, so scoping them to
    a universe would invent a distinction the measurement does not have."""
    assert all(a.universe is None for a in GEOMETRY_ANCHORS)


def test_a_run_is_checked_against_the_pin_measured_over_its_own_universe():
    """The whole point of the second pin: the contract's stateless run reproduces
    −5.01pp and settles, without §4b's +1.95pp ever being quoted at it."""
    report = check_anchors(_stateless_measurements(), universe=UNIVERSE_STATELESS)

    assert report.passes
    assert report.universe == UNIVERSE_STATELESS
    assert [c.anchor.key for c in report.gate_dependent] == [
        "coverage_blind_spot", "detection_recall", "in_field_stateless",
    ]


def test_the_app_universe_run_still_anchors_on_findings_4b():
    """The second pin adds a row; it does not move the first one. A run over the
    app's universe is checked against §4b exactly as it was before."""
    report = check_anchors(_all_measurements(), universe=UNIVERSE_APP)

    assert report.passes
    assert [c.anchor.key for c in report.gate_dependent] == [
        "coverage_blind_spot", "detection_recall", "in_field",
    ]


def test_a_stateless_measurement_offered_against_findings_4b_is_refused():
    """The category error #211 named, made unrepresentable. Quoting §4b's gap at a
    measurement taken over the contract's universe is not a failing anchor, it is
    two different numbers being compared — so it raises rather than reporting a
    sign flip and charging it to the pipeline."""
    with pytest.raises(DriftError) as exc:
        check_anchors(_stateless_measurements(), universe=UNIVERSE_APP)

    assert UNIVERSE_APP in str(exc.value)
    assert UNIVERSE_STATELESS in str(exc.value)


def test_the_stateless_pin_keeps_its_own_sign_check():
    """The guard is scoped, never dropped. −5.01pp is what the contract's universe
    is pinned at, so a run coming back positive there has moved something and
    fails for it — the same refusal, now asked over the right pair."""
    flipped = {"picks_share": 0.1836, "field_share": 0.1335}

    with pytest.raises(DriftError) as exc:
        check_anchors(
            _stateless_measurements(cell=flipped), universe=UNIVERSE_STATELESS
        )

    assert "sign" in str(exc.value).lower()


def test_a_sign_flip_on_the_stateless_pin_is_still_unwaivable():
    """A written cause does not settle it, exactly as before. What #211 changed is
    which pin a run is compared against, not whether a flip can be explained."""
    flipped = {"picks_share": 0.1836, "field_share": 0.1335}

    with pytest.raises(DriftError):
        check_anchors(
            _stateless_measurements(cell=flipped),
            universe=UNIVERSE_STATELESS,
            explained={"in_field_stateless": "a cause written down"},
        )


def test_the_stateless_pin_says_it_is_a_first_measurement():
    """It was measured once, by the run it now anchors. That makes it a drift
    detector from here on rather than an independent check of this run, and the
    row says so rather than letting a reader assume otherwise."""
    stateless = ANCHORS_BY_KEY["in_field_stateless"]

    assert stateless.first_measurement
    text = format_anchors(
        check_anchors(_stateless_measurements(), universe=UNIVERSE_STATELESS)
    )

    assert "first measurement" in text
    assert UNIVERSE_STATELESS in text


def test_a_field_measurement_must_name_the_universe_it_was_counted_over():
    """No default, because the same grid measures both universes against two
    different stores — #211's isolation ran ``run_grid`` over the backtest store —
    so there is no universe a caller can be assumed to have meant."""
    with pytest.raises(TypeError):
        in_field_measurement(_cell(), replayable=656)


def test_the_serialised_report_names_the_universe_it_anchored():
    """#211's rule is that §4b's gap may not be cited without naming the field it
    was measured over. A payload carrying the verdict and not the universe is
    exactly that citation, so the universe rides on the result."""
    body = anchors_report(
        DEFAULT_CONTRACT,
        check_anchors(_stateless_measurements(), universe=UNIVERSE_STATELESS),
    )

    assert body["universe"] == UNIVERSE_STATELESS
    row = next(
        c for c in body["gate_dependent"] if c["anchor"] == "in_field_stateless"
    )
    assert row["universe"] == UNIVERSE_STATELESS
    assert json.loads(json.dumps(body)) == body


def test_the_field_measurement_file_must_name_its_universe(tmp_path):
    """The documented reproduction command reads this file, so a guard that only
    holds for in-process callers does not hold on the path that matters."""
    path = tmp_path / "field.json"
    path.write_text(json.dumps({
        "in_field": {"in_field": 165, "of": 503, "gap_pp": -5.01,
                     "field": "whole", "detector_version": 3}
    }))

    with pytest.raises(DriftError) as exc:
        _field_measurements(str(path))

    assert "universe" in str(exc.value)


def test_the_field_measurement_file_routes_by_the_universe_it_names(tmp_path):
    """The file names a universe and the row it becomes follows from it, so the
    one path the reproduction command uses cannot land on the wrong pin."""
    path = tmp_path / "field.json"
    path.write_text(json.dumps({
        "in_field": {"in_field": 165, "of": 503, "gap_pp": -5.01,
                     "field": "whole", "detector_version": 3,
                     "universe": UNIVERSE_STATELESS}
    }))

    [measurement] = _field_measurements(str(path))

    assert measurement.anchor == "in_field_stateless"
    assert measurement.universe == UNIVERSE_STATELESS


# -- bounding the survivorship hole (issue #196) --------------------------------
#
# Phase 2, and the measurement that gates believing any performance number. Four
# claims are load-bearing here, and each one below would fail loudly if the code
# drifted from it:
#
#   * **Coverage is decided by the bars, not by the symbol.** A ticker that
#     resolves today and carries bars beginning after the session being replayed
#     is a *recycled listing* — one company's session read against another
#     company's bars. It is a blind spot, and `FUSE` is the name that proved a
#     has-any-bars test gets it wrong (findings §2, #139).
#   * **The spine is verified before it is depended on.** A listing spine that
#     does not bracket the window cannot say a name was listed inside it, so the
#     count built on it would be a number about the spine's own edges.
#   * **The bound is a pair, never a single figure.** The headline and its
#     pessimistic twin are computed together and printed on one line, because a
#     survivor-biased number quoted alone is the failure this phase exists to
#     prevent.
#   * **The measured hole is read against findings §2's floor.** A 2012 start
#     reaches further back than the reference study's four years, so a *smaller*
#     hole is a reason for suspicion rather than a result.

from backtest.crawl import NOT_COMMON_STOCK, UNREAD_REFERENCE, Enumeration
from backtest.metric import NO_BOUND_LINE
from backtest.survivorship import (
    BARS_BEGIN_AFTER,
    BARS_END_BEFORE,
    COVERED,
    FINDINGS_FLOOR,
    FLOOR_SUSPICION_NOTE,
    NO_BARS,
    PESSIMISTIC_OUTCOME,
    PESSIMISTIC_R,
    SPINE_SOURCE,
    Absence,
    ListingSpine,
    Snapshot,
    SpineCoverageShortfall,
    SpineCoverageUnverified,
    BASIS_ENUMERATION,
    SurvivorshipHole,
    absences,
    against_floor,
    attach_bias_bound,
    bias_bound,
    bias_bound_line,
    enumeration_gap,
    format_survivorship,
    hole_from_counts,
    holes_by_market,
    is_blind_spot,
    missing_trade_count,
    coverage_census,
    fetch_spine,
    parse_snapshot,
    session_verdict,
    span_of,
    spine_path,
    survivorship_report,
    todays_roster,
    window_population,
)

_WINDOW = (date(2012, 1, 1), date(2026, 8, 26))


def _snap(as_of: date, *symbols: str, file: str = "nasdaqlisted.txt") -> Snapshot:
    return Snapshot(as_of=as_of, file=file, symbols=tuple(symbols))


def _listing_spine(*snapshots: Snapshot, market: str = "US") -> ListingSpine:
    return ListingSpine(market=market, source=SPINE_SOURCE, snapshots=tuple(snapshots))


def _bracketing(*snapshots: Snapshot) -> ListingSpine:
    """A spine whose snapshots bracket the measured window at both ends.

    Every absence test needs the brackets or the verification refuses it, and
    repeating the two edge snapshots in each fixture would bury the one line that
    differs between them.
    """
    edges = (
        _snap(date(2011, 12, 1), "EDGE"),
        _snap(date(2026, 9, 1), "EDGE"),
    )
    return _listing_spine(*edges, *snapshots)


# -- coverage is a fact about the bars, not about the symbol -------------------


def test_a_recycled_ticker_is_a_blind_spot_not_a_covered_name(store: Store):
    """`FUSE`'s shape: the symbol resolves today and has bars, and they are the
    wrong company's.

    The store holds `RECY` from 2022 onward because the ticker was reassigned to an
    unrelated listing. The session being replayed is in 2021, when the *original*
    listing traded under it. A test that asks "does this symbol have bars?" answers
    yes and replays one company's session against another company's series; the
    test that asks "do the bars cover this session?" calls it what it is.
    """
    store.append_bars("US", "RECY", [_bar(d) for d in _daily(date(2022, 3, 7), 5)])

    verdict = session_verdict(span_of(store, "US", "RECY"), date(2021, 1, 4))

    assert verdict == BARS_BEGIN_AFTER
    assert is_blind_spot(verdict)
    # And the weaker question gives the wrong answer, which is why it is not asked.
    assert store.bars("US", "RECY") != []


def test_coverage_separates_the_three_ways_a_session_goes_uncovered(store: Store):
    """Covered, never listed yet, listed and gone, and no bars at all.

    Four verdicts rather than a boolean, because the three failures have different
    causes — a recycled ticker, a delisting, and a name the crawl never reached —
    and a report that collapsed them would name none of them.
    """
    store.append_bars("US", "MID", [_bar(d) for d in _daily(date(2020, 5, 4), 5)])
    span = span_of(store, "US", "MID")

    assert session_verdict(span, date(2020, 5, 6)) == COVERED
    assert session_verdict(span, date(2020, 1, 2)) == BARS_BEGIN_AFTER
    assert session_verdict(span, date(2021, 1, 4)) == BARS_END_BEFORE
    assert session_verdict(span_of(store, "US", "ZZZ"), date(2020, 5, 6)) == NO_BARS
    assert is_blind_spot(COVERED) is False


# -- the spine is verified before it is depended on ----------------------------


def test_a_spine_that_does_not_bracket_the_window_is_refused(store: Store):
    """A spine whose oldest snapshot lands inside the window cannot say a name was
    listed before it — every name would look like a 2015 listing.

    Refused rather than reported as a caveat: the count is the deliverable, and a
    count whose edges are the source's edges is a measurement of the source.
    """
    spine = _listing_spine(_snap(date(2015, 6, 1), "AAA"), _snap(date(2026, 8, 1), "AAA"))

    with pytest.raises(SpineCoverageShortfall) as excinfo:
        spine.verify(*_WINDOW)

    assert "2012-01-01" in str(excinfo.value)


def test_an_unverified_spine_cannot_be_counted_against(store: Store):
    """The verification is a gate on the type, not a step a caller may skip.

    `absences` takes a verified spine and nothing else, so "check the coverage
    first" is enforced at the one place the spine is depended on rather than
    remembered at each call site.
    """
    spine = _bracketing(_snap(date(2015, 6, 1), "AAA"))

    with pytest.raises(SpineCoverageUnverified):
        absences(spine, enumerated_today=["AAA"], window=_WINDOW)


def test_a_verified_spine_reports_the_density_that_makes_the_count_a_floor(store: Store):
    """Bracketing is refused when absent; density is *reported* when thin.

    The two failures differ in kind. A spine that does not bracket the window gives
    a wrong count; a spine that brackets it with annual snapshots gives a count that
    is right about what it saw and blind to any name that listed and delisted
    between two of them. The first is refused above; the second rides on the result
    as the reason the number is a floor.
    """
    spine = _bracketing(_snap(date(2015, 6, 1), "AAA"))

    verified = spine.verify(*_WINDOW)

    assert verified.coverage.brackets_window is True
    assert verified.coverage.snapshots == 3
    # 2012 through 2026 with snapshots in 2011, 2015 and 2026: the silent years are
    # named, not summarised into a single "sparse".
    assert 2013 in verified.coverage.years_without_snapshot
    assert 2015 not in verified.coverage.years_without_snapshot
    assert verified.coverage.largest_gap_days > 365


# -- the dated count -----------------------------------------------------------


def test_the_count_is_names_listed_in_the_window_and_gone_from_todays_enumeration(
    store: Store,
):
    """The deliverable: who is missing, and between which dates they were listed.

    `GONE` was listed in 2013 and 2015 and is not enumerated today — the survivorship
    hole. `ALIVE` is enumerated today, so it is not one however long it has been
    listed. `LATER` is absent today too, but its only snapshot is after the window,
    so it never traded inside the window and is not this window's hole.
    """
    spine = _bracketing(
        _snap(date(2013, 2, 1), "GONE", "ALIVE"),
        _snap(date(2015, 6, 1), "GONE", "ALIVE"),
    )

    found = absences(
        spine.verify(*_WINDOW), enumerated_today=["ALIVE", "EDGE"], window=_WINDOW
    )

    assert found == (
        Absence(
            symbol="GONE",
            market="US",
            first_listed=date(2013, 2, 1),
            last_listed=date(2015, 6, 1),
            snapshots=2,
        ),
    )


def test_a_name_listed_only_after_the_window_is_not_this_windows_hole(store: Store):
    """The window is the claim's scope, and a name that never traded inside it is
    absent from today's enumeration for reasons this run is not measuring."""
    window = (date(2012, 1, 1), date(2014, 12, 31))
    spine = _listing_spine(
        _snap(date(2011, 12, 1), "EDGE"),
        _snap(date(2014, 12, 1), "EDGE"),
        _snap(date(2013, 1, 1), "INSIDE"),
    )
    # A later snapshot carrying a name that only ever appears after the window.
    later = _listing_spine(*spine.snapshots, _snap(date(2016, 1, 1), "AFTER"))

    found = absences(later.verify(*window), enumerated_today=["EDGE"], window=window)

    assert [a.symbol for a in found] == ["INSIDE"]


# -- the hole, and findings §2's floor -----------------------------------------


def test_the_hole_counts_the_recycled_names_beside_the_absent_ones(store: Store):
    """Survivorship here is delisting *plus* ticker recycling.

    A recycled name is absent from no list — it resolves today, and the absence
    count above cannot see it. It reaches the hole through the coverage verdict
    instead, which is why the two counts are summed rather than either being taken
    for the whole.
    """
    hole = hole_from_counts(
        market="US", covered_names=800, absent_names=150, recycled_names=50
    )

    assert isinstance(hole, SurvivorshipHole)
    assert hole.missing_names == 200
    assert hole.total_names == 1000
    assert hole.share == pytest.approx(0.2)


def test_a_hole_smaller_than_the_reference_floor_is_flagged_as_suspicious(store: Store):
    """findings §2 measured 92 of 312 tickers over four years. This run reaches
    back to 2012, so it should find *more*.

    A smaller number is reported with the suspicion attached rather than as a better
    result, because the likeliest cause of a shrinking hole is a coverage test that
    stopped asking the hard question.
    """
    thin = hole_from_counts(market="US", covered_names=990, absent_names=10,
                            recycled_names=0)
    fat = hole_from_counts(market="US", covered_names=600, absent_names=400,
                           recycled_names=0)


    assert against_floor(thin)["below_floor"] is True
    assert FLOOR_SUSPICION_NOTE in against_floor(thin)["note"]
    assert against_floor(fat)["below_floor"] is False
    assert against_floor(fat)["floor_share"] == pytest.approx(
        FINDINGS_FLOOR.tickers / FINDINGS_FLOOR.total_tickers
    )


def test_the_idx_gap_is_measured_from_the_enumeration_side(store: Store):
    """IDX has no free dated listing spine, so its hole is measured where it *is*
    visible: the provider enumerates fewer names than the exchange lists.

    The exchange's own count and the date it was read both ride on the figure —
    the screener's membership churns for live names on a scale of minutes, so an
    undated 123 is a number nobody could reproduce.
    """
    enumeration = Enumeration(
        market="IDX",
        listed=840,
        fetched=tuple(f"S{i}.JK" for i in range(840)),
        excluded=(),
        listed_by_exchange=962,
        listed_by_exchange_source="idx.co.id Company Profiles, read 2026-08-26",
    )

    gap = enumeration_gap(enumeration)

    assert gap.missing == 122
    assert gap.share == pytest.approx(122 / 962)
    assert "2026-08-26" in gap.source


def test_an_enumeration_with_no_exchange_count_measures_no_gap(store: Store):
    """US has no second listing count on the enumeration, and an absent count is
    reported as absent rather than as a gap of zero — the two readings are opposite
    findings."""
    enumeration = Enumeration(market="US", listed=1, fetched=("AAA",), excluded=())

    assert enumeration_gap(enumeration) is None


# -- the bound: the headline and its pessimistic twin --------------------------


def test_the_missing_population_is_scaled_off_the_covered_one(store: Store):
    """A hole of one name in five means the observed trades are four-fifths of the
    population, so the missing fifth is a quarter as many trades again.

    Stated as arithmetic rather than assumed: the assumption is that a missing name
    would have traded at the same rate as a covered one, which is conservative in
    the wrong direction — the names that died were the volatile ones a momentum
    screener surfaces most.
    """
    assert missing_trade_count(closed=800, hole_share=0.2) == 200
    assert missing_trade_count(closed=0, hole_share=0.5) == 0
    assert missing_trade_count(closed=100, hole_share=0.0) == 0


def test_the_bound_is_the_gap_between_the_headline_and_its_pessimistic_twin(store):
    """The deliverable: two numbers and the distance between them.

    Ten trades at +1R with a hole of one in three: the twin carries five more trades
    at a full stop, so the mean falls from +1R toward the pessimistic assignment and
    the gap is what survivorship could be worth.
    """
    trades = [_mtrade(f"S{i}", 2015, 1.0) for i in range(10)]
    cell = expectancy_cell(DEFAULT_CONTRACT, trades, market="US", label="2015")

    bound = bias_bound(cell, market="US", hole_share=1 / 3)

    assert bound.covered_trades == 10
    assert bound.missing_trades == 5
    assert bound.pessimistic_r < bound.headline_r
    assert bound.gap_r == pytest.approx(bound.headline_r - bound.pessimistic_r)
    # The twin is the mean over both populations, and it is checkable by hand.
    cost = cell["cost_r"]
    assert bound.pessimistic_r == pytest.approx(
        (10 * (1.0 - cost) + 5 * (PESSIMISTIC_R - cost)) / 15
    )
    assert bound.pessimistic_outcome == PESSIMISTIC_OUTCOME


def test_a_hole_of_nothing_leaves_the_headline_where_it_was(store):
    """No missing population, no bound — and the pair is still printed, because a
    bound of zero is a measurement and a missing bound is not."""
    cell = expectancy_cell(
        DEFAULT_CONTRACT, [_mtrade("AAA", 2015, 1.0)], market="US", label="2015"
    )

    bound = bias_bound(cell, market="US", hole_share=0.0)

    assert bound.gap_r == pytest.approx(0.0)
    assert bound.pessimistic_r == pytest.approx(bound.headline_r)
    assert "0.000R" in bias_bound_line(bound)


def test_the_bound_rides_on_every_result_as_one_line(store):
    """The line is attached to the metric report itself and printed by the metric's
    own formatter, so a reader cannot reach the headline without passing the bound.

    Attached rather than recomputed inside the metric: the hole is measured against
    the bar store and the listing spine, which the metric never reads, and a metric
    that reached for them would need the network to report a mean.
    """
    report = metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2015, 1.0)],
                           markets=["US"])

    bounded = attach_bias_bound(report, {"US": 0.25})

    line = bounded["markets"][0]["bias_bound"]["line"]
    assert "pessimistic" in line
    assert line in format_metric(bounded)


def test_an_unbounded_headline_says_so_where_the_bound_would_be(store):
    """A metric printed with no bound attached is survivor-biased by an unmeasured
    amount, and the page says that in the place a reader looks for the pair.

    A blank there would read as "no bias", which is the one reading Phase 2 exists
    to make impossible.
    """
    report = metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2015, 1.0)],
                           markets=["US"])

    printed = format_metric(report)

    assert NO_BOUND_LINE in printed


# -- the report -----------------------------------------------------------------


def test_the_survivorship_report_states_the_hole_against_the_floor(store: Store):
    """Both deliverables in one stamped payload: the dated count, and the bound.

    The floor is stated beside the measurement rather than left in the plan, so the
    figure arrives already compared to the only prior measurement of the same thing.
    """
    spine = _bracketing(
        _snap(date(2013, 2, 1), "GONE", "ALIVE"),
        _snap(date(2015, 6, 1), "GONE", "ALIVE"),
    )
    hole = hole_from_counts(market="US", covered_names=1, absent_names=1,
                            recycled_names=0)

    report = survivorship_report(
        DEFAULT_CONTRACT,
        holes=[hole],
        absent={"US": absences(spine.verify(*_WINDOW),
                               enumerated_today=["ALIVE", "EDGE"], window=_WINDOW)},
        coverage={"US": spine.verify(*_WINDOW).coverage},
        gaps=[],
    )

    assert report["markets"][0]["hole"]["share"] == pytest.approx(0.5)
    assert report["markets"][0]["versus_findings_floor"]["below_floor"] is False
    assert report["markets"][0]["absences"][0]["symbol"] == "GONE"
    assert report["markets"][0]["absences"][0]["last_listed"] == "2015-06-01"
    printed = format_survivorship(report)
    assert "GONE" in printed
    assert SPINE_SOURCE in printed


# -- reading the archive's own files -------------------------------------------

_ARCHIVAL_2012 = """Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size
GONE|Gone Industries Inc. - Common Stock|Q|N|N|100
WRNT|Warrant Co - Warrant|S|N|N|100
ZXZZT|NASDAQ TEST STOCK|G|Y|N|100
File Creation Time: 0622201218:02|||||
"""

_MODERN = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
ALIVE|Alive Corp Common Stock|N|ALIVE|N|100|N|ALIVE
File Creation Time: 0611202617:30|||||||
"""

# The live directory as served without a creation stamp, so its date can only come
# from the caller's own today — which is the point of fetching it at all.
_LIVE = """ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
ALIVE|Alive Corp Common Stock|N|ALIVE|N|100|N|ALIVE
"""


def test_the_spine_reads_an_archival_header_that_has_no_etf_column(store: Store):
    """A 2012 `nasdaqlisted.txt` carries no ETF column, and the live parser raises on
    it.

    Parsed here rather than through `screener.source.parse_us_listings` for exactly
    that reason. A spine that skipped the years it could not parse would report
    those years' listings as never having existed — which is the shape of the error
    this module was written to measure, arriving through the module itself.
    """
    snapshot = parse_snapshot(
        _ARCHIVAL_2012, file="nasdaqlisted.txt", fallback=date(2012, 6, 23)
    )

    # The exchange's own stamp, not the archive's crawl date: the archive fetched
    # this on the 23rd and the exchange wrote it on the 22nd.
    assert snapshot.as_of == date(2012, 6, 22)
    # The warrant and the test issue are not companies that later died.
    assert snapshot.symbols == ("GONE",)


def test_a_snapshot_with_no_creation_stamp_falls_back_to_the_crawl_date(store: Store):
    """Dated by the archive when the file dates itself by nothing — a snapshot with
    no date at all could not be placed in the window."""
    text = "Symbol|Security Name|Test Issue\nAAA|Aaa Corp - Common Stock|N\n"

    snapshot = parse_snapshot(text, file="nasdaqlisted.txt", fallback=date(2013, 4, 5))

    assert snapshot.as_of == date(2013, 4, 5)
    assert snapshot.symbols == ("AAA",)


def test_the_spine_is_fetched_through_a_seam_and_a_dead_capture_is_skipped(store):
    """The crawl is a data job; its one interesting branch is a capture the archive
    cannot replay.

    Skipped with the reason printed rather than aborting the spine: one unreplayable
    capture out of seventy is a thinner spine, and a spine that refused to build
    because of it would be no spine at all.
    """
    calls: list[str] = []
    seen: list[str] = []

    def get(url: str) -> str:
        calls.append(url)
        if "cdx" in url:
            return json.dumps([["timestamp"], ["20120623141057"], ["20260611001021"]])
        if not url.endswith("nasdaqlisted.txt"):
            raise RuntimeError("no capture")
        if "/20120623" in url:
            return _ARCHIVAL_2012
        if "web.archive.org" not in url:
            return _LIVE  # the live directory, dated by the caller's today
        return _MODERN

    spine = fetch_spine(
        files=("nasdaqlisted.txt", "otherlisted.txt"), get=get,
        today=date(2026, 8, 26), progress=seen.append,
    )

    assert spine.source == SPINE_SOURCE
    # Two archived captures and today's live roster, which is what brackets the far
    # end: the archive's newest capture trails the present by months.
    assert [s.as_of for s in spine.ordered()] == [
        date(2012, 6, 22), date(2026, 6, 11), date(2026, 8, 26)
    ]
    # otherlisted's captures — two archived and the live one — all raised, and each
    # is recorded on the spine rather than lost: a capture written off silently is
    # a date the count would report as having held no listings.
    assert sum("unread" in line for line in seen) == 3
    assert [row[0] for row in spine.unread] == ["otherlisted.txt"] * 3
    assert "no capture" in spine.unread[0][2]
    assert spine.coverage(*_WINDOW).unread_captures == 3


def test_a_recycled_name_never_counts_toward_the_covered_population(store: Store):
    """A recycled ticker and a genuine IPO look identical in the bars, and only one
    of them is a hole.

    `RECY` was listed in 2013 and its bars begin in 2019: on the 2013 snapshot the
    symbol was somebody else, so the run is blind there. `IPO` was never listed
    before its bars start — the company did not exist, and a run with no bars for it
    is right rather than blind. `LIVE` has been listed throughout. Only the spine
    separates the first two, which is why it is what this reads.
    """
    store.append_bars("US", "LIVE", [_bar(d) for d in _daily(date(2012, 1, 3), 3)])
    store.append_bars("US", "RECY", [_bar(d) for d in _daily(date(2019, 6, 3), 3)])
    store.append_bars("US", "IPO", [_bar(d) for d in _daily(date(2019, 6, 3), 3)])
    spine = _bracketing(
        _snap(date(2013, 2, 1), "LIVE", "RECY", "SILENT"),
        _snap(date(2020, 2, 1), "LIVE", "RECY", "IPO", "SILENT"),
    ).verify(*_WINDOW)

    census = coverage_census(
        store, "US", ["LIVE", "RECY", "IPO", "SILENT"], spine=spine,
        window_start=date(2012, 1, 1),
    )

    assert census.recycled == ("RECY",)
    assert census.covered == ("IPO", "LIVE")
    # `SILENT` is listed and the crawl asked about it and got nothing. It resolves,
    # it can price nothing, and it belongs in the hole rather than the denominator —
    # which is the difference between the two questions findings §2 had to switch
    # between.
    assert census.no_bars == ("SILENT",)


def test_an_unmeasured_recycled_half_is_not_reported_as_none_of_them(store: Store):
    """A market with no dated listing spine cannot tell a recycled ticker from an
    IPO, and saying "0 recycled" would claim it did.

    IDX is that market: no free source reconstructs a dated Jakarta roster, so its
    absent count comes from the enumeration side and its recycled half is reported
    unmeasured. The floor comparison carries that as a second reason the share is a
    floor, so the figure is never read as a total.
    """
    idx = hole_from_counts(
        market="IDX", covered_names=840, absent_names=122, recycled_names=None,
        basis=BASIS_ENUMERATION,
    )

    assert idx.recycled_measured is False
    assert idx.missing_names == 122
    assert idx.to_dict()["recycled_names"] is None
    assert "unmeasured" in against_floor(idx)["note"]
    assert against_floor(idx)["recycled_measured"] is False


def test_the_spine_round_trips_through_the_cache_beside_the_store(tmp_path):
    """The spine is committed beside the store, for the reason the coverage ledger
    is: a count whose inputs are re-downloaded on every read is a count that can
    change without anyone changing anything.

    The archive is also not a fixed corpus — a capture can be added or withdrawn
    between two runs — so "re-fetch and recompute" is not reproduction.
    """
    spine = dataclasses.replace(
        _bracketing(_snap(date(2015, 6, 1), "AAA", "BBB")),
        unread=(("otherlisted.txt", "20140101000000", "ConnectionResetError: reset"),),
    )
    path = spine_path(tmp_path / "backtest.duckdb")

    spine.write(path)

    assert path.name == "backtest.duckdb.spine.json"
    assert ListingSpine.load(path).ordered() == spine.ordered()
    assert ListingSpine.load(path).unread == spine.unread


def test_a_listed_etf_is_not_a_company_that_died(store: Store):
    """"Absent from today's enumeration" means the provider does not list it, not
    that the crawl declined to fetch it.

    `fetch_set` drops references nothing reads — several thousand US ETFs — and they
    are *listed* today. Counting them absent would report a live listing as a company
    that died, on a scale that would swamp the real hole. The instrument-type slice is
    a different case and stays dropped, because `parse_snapshot` narrows the spine by
    the same rule, so a warrant is missing from both sides and cancels.
    """
    enumeration = Enumeration(
        market="US",
        listed=5,
        fetched=("^IXIC", "ALIVE", "EDGE"),
        excluded=(("SPY", UNREAD_REFERENCE), ("ALIVEW", NOT_COMMON_STOCK)),
    )

    roster = todays_roster(enumeration)

    assert roster == {"^IXIC", "ALIVE", "EDGE", "SPY"}
    # And the count run against it leaves the ETF alone while still finding the
    # name that really left.
    spine = _bracketing(_snap(date(2013, 2, 1), "ALIVE", "SPY", "GONE"))
    found = absences(spine.verify(*_WINDOW), enumerated_today=roster, window=_WINDOW)
    assert [a.symbol for a in found] == ["GONE"]


def test_the_measured_hole_reaches_the_headline_without_hand_written_glue(store: Store):
    """The two deliverables join inside the package, not at a call site.

    `holes_by_market` is the join, and it is a function rather than a line somebody
    writes later so the count and the bound cannot be wired to different markets —
    the one way this pair goes wrong silently, since a mismatched bound still prints
    a plausible number.
    """
    hole = hole_from_counts(market="US", covered_names=3, absent_names=1,
                            recycled_names=0)
    report = survivorship_report(
        DEFAULT_CONTRACT, holes=[hole], absent={}, coverage={}, gaps=[]
    )

    shares = holes_by_market(report)

    assert shares == {"US": 0.25}
    bounded = attach_bias_bound(
        metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2015, 1.0)], markets=["US"]),
        shares,
    )
    printed = format_metric(bounded)
    assert NO_BOUND_LINE not in printed
    # The per-year cell carries its own bound too, not only the window figure a
    # reader skims to.
    assert printed.count("bound") >= 2


def test_the_share_is_counted_over_one_population_not_two(store: Store):
    """Both halves come from the names the spine sighted inside the window.

    The first version of this count did not do that — the absent names were counted
    over the spine's whole roster and the covered names over today's *fetch set*,
    5,498 against 20,923. A ratio of two different populations is not a share of
    anything, and it read as a hole two-thirds larger than the one that is there.

    A name sighted only outside the window is in neither half: it never traded in
    the window this run measures.
    """
    spine = _bracketing(
        _snap(date(2013, 2, 1), "GONE", "ALIVE"),
    ).verify(*_WINDOW)

    population = window_population(spine, _WINDOW)

    # `EDGE` is sighted at 2011-12 *and* 2026-09, so it spans the window and counts.
    assert sorted(population) == ["ALIVE", "EDGE", "GONE"]
    narrow = (date(2014, 1, 1), date(2015, 1, 1))
    assert sorted(window_population(spine, narrow)) == ["EDGE"]


def test_a_name_listed_for_a_year_is_not_a_name_listed_for_fourteen(store: Store):
    """The bound is scaled off time listed, not off name count.

    40% of the absent US names were listed for under two years. Counting each of
    them as one whole missing name credits an eighteen-month listing with as many
    chances to throw a signal as one listed throughout, and the bound is a statement
    about trades. So the share that feeds it is weighted by exposure, and the name
    share stays beside it because that is the figure findings §2's 92-of-312 is
    comparable to.
    """
    hole = hole_from_counts(
        market="US", covered_names=1, absent_names=1, recycled_names=0,
        covered_exposure_days=3650, missing_exposure_days=365,
    )

    assert hole.share == pytest.approx(0.5)
    assert hole.exposure_share == pytest.approx(365 / 4015)
    assert hole.to_dict()["exposure_weighted"] is True
    # And the join hands the bound the weighted one.
    report = survivorship_report(
        DEFAULT_CONTRACT, holes=[hole], absent={}, coverage={}, gaps=[]
    )
    assert holes_by_market(report)["US"] == pytest.approx(365 / 4015)


def test_an_unweighted_market_falls_back_to_the_name_share(store: Store):
    """IDX has no dated spine, so it has no durations. A zero there would read as
    "nothing missing" rather than "not weighted", so the name share stands in and
    the output says which it is."""
    idx = hole_from_counts(
        market="IDX", covered_names=840, absent_names=122, recycled_names=None,
        basis=BASIS_ENUMERATION,
    )

    assert idx.exposure_share == idx.share
    assert idx.to_dict()["exposure_weighted"] is False


# -- the full run: both markets, fourteen years (issue #198) -------------------
#
# Phase 3 at the scope the plan actually asks about, gated by Phase 6. Issue #188
# proved one market over a sliver of window ran; nothing below re-proves that.
# What is new only exists once there is more than one market and more than a
# sliver:
#
#   * **The window comes from the contract.** `scope.markets`, `window.store_start`,
#     `window.measured_start` and `window.measured_end` are committed cells, so the
#     run is reproducible from the contract and the store rather than from whoever
#     retyped the right dates. The store start is a *calendar boundary* and the
#     chain replays *sessions*, and 2011-01-01 is a holiday on both exchanges —
#     the one place a fixture calendar with no weekends could not have caught it.
#   * **The two markets are reported apart, and there is no pooled figure.**
#     Findings §8 measured that magnitudes do not transfer, so the cheapest way to
#     stop a combined number being read is to never build one.
#   * **Figures are gated on the anchors.** The plan's third rule made a refusal
#     rather than a sentence: a report over an unsettled anchor check raises.
#     The gate sits after the replay and before the figures, because the two
#     gate-dependent anchors are measured over the run's own field.

from backtest.full_run import (
    AnchorOutcome,
    read_anchor_report,
    LATEST_COMPLETE_SESSION,
    LONGEST_CLOSURE,
    AnchorsNotSettled,
    FullRun,
    MarketNotRun,
    contract_markets,
    contract_measured_start,
    contract_store_start,
    format_full_run,
    full_run_report,
    market_series,
    measured_end,
    run_full,
    store_window_start,
)
from backtest.full_run import main as full_run_main
from backtest.figures import detections_series, format_detections_grid
from backtest.contract import WINDOW_MEASURED_END_KEY
from backtest.anchors import (
    SETTLED_VERDICTS,
    VERDICT_EXPLAINED,
    VERDICT_FAILED,
)
from collections import Counter


def _contract_where(**by_key) -> RunContract:
    """``DEFAULT_CONTRACT`` with several cells' values replaced, justifications kept.

    The dotted contract keys are not identifiers, so they arrive as a mapping
    rather than as keyword arguments; ``_contract_with`` above does one cell and
    this does a window, which always moves at least two.
    """
    values = by_key.pop("values")
    assert not by_key
    return dataclasses.replace(
        DEFAULT_CONTRACT,
        cells=tuple(
            dataclasses.replace(c, value=values[c.key]) if c.key in values else c
            for c in DEFAULT_CONTRACT.cells
        ),
    )


def _idx_scale(hlc):
    """The same geometry, quoted in rupiah.

    IDX's contract gates are a different size, not a different shape: the
    liquidity floor is Rp 10B against the US's $10M and the data-validity trim is
    Rp 100. Pricing the fixture up keeps the *shape* the tests are about — the
    base, the run-up, the wide daily range — while clearing gates authored for a
    market that quotes in thousands.
    """
    return [(h * 100, l * 100, c * 100) for h, l, c in hlc]


def _seed_two_market_store(store: Store) -> list[date]:
    """One detectable name and its index in each market, at each market's scale."""
    dates = _daily(date(2020, 1, 1), FIXTURE_SESSIONS)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _wide_base_hlc()))
    store.append_bars(
        "US", MARKET_INDEX["US"], _bars_from_hlc(dates, _flat_index_hlc(FIXTURE_SESSIONS))
    )
    store.append_bars(
        "IDX", "BASE.JK",
        _bars_from_hlc(dates, _idx_scale(_wide_base_hlc()), volume=5_000_000),
    )
    store.append_bars(
        "IDX", MARKET_INDEX["IDX"],
        _bars_from_hlc(dates, _idx_scale(_flat_index_hlc(FIXTURE_SESSIONS))),
    )
    return dates


def _fixture_contract(dates: list[date]) -> RunContract:
    """The committed contract with its window moved onto the fixture's calendar.

    Only the window moves. Every gate the run is actually exercising — the
    stateless universe, the detection gate, the reference exclusion — stays as
    committed, so a test that passes here is a test about the run and not about a
    contract authored to make it pass.
    """
    return _contract_where(values={
        WINDOW_STORE_START_KEY: dates[0].isoformat(),
        WINDOW_MEASURED_START_KEY: dates[-5].isoformat(),
        WINDOW_MEASURED_END_KEY: LATEST_COMPLETE_SESSION,
    })


def _settled() -> AnchorReport:
    """An anchor report in which all six anchors matched.

    Over the **contract's** universe, because that is the field this run screens:
    an app-universe report anchors a different run, however green it is.
    """
    return check_anchors(_stateless_measurements(), universe=UNIVERSE_STATELESS)


def _unsettled() -> AnchorReport:
    """The report `backtest.anchors` builds when the field anchors never arrived.

    Not a hand-made failure: it is the exact shape the command produces when it
    can check four of six, which is the way an unanchored run actually reaches a
    reader.
    """
    return AnchorReport(
        detector_version=DETECTOR_VERSION,
        arms=ANCHOR_ARMS,
        geometry=check_geometry(_geometry_measurements()),
        gate_dependent=(),
        geometry_only=True,
    )


# -- the window comes from the contract ---------------------------------------


def test_the_contracts_window_and_markets_are_the_runs_whole_scope():
    """Ticket criterion: reproducible from the committed contract and the store.

    Nothing about "the full run" is a command-line argument — the markets, the
    burn-in's start and the measured start are all committed cells, so a
    reproduction cannot quietly differ from the run it reproduces.
    """
    assert contract_markets() == ("US", "IDX")
    assert contract_store_start() == date(2011, 1, 1)
    assert contract_measured_start() == date(2012, 1, 1)
    assert DEFAULT_CONTRACT.value(WINDOW_MEASURED_END_KEY) == LATEST_COMPLETE_SESSION


def test_the_store_window_boundary_resolves_to_the_first_session_on_or_after_it(store):
    """The contract names a calendar date; the chain replays sessions.

    ``window.store_start`` is 2011-01-01 — New Year's Day, which neither exchange
    has ever traded. Handed to the chain unresolved it asks for a session that
    cannot exist and fails a run that is in fact fully covered. Every fixture
    calendar in this file is built by `_daily`, which has no weekends and no
    holidays, so this is a gap only a real store could have shown.
    """
    dates = _daily(date(2011, 1, 3), 10)
    store.append_bars("US", "BASE", _bars_from_hlc(dates, _ramp_hlc(10)))
    contract = _contract_where(values={WINDOW_STORE_START_KEY: "2011-01-01"})

    # Two days before the first session, and covered: the exchange was shut.
    assert store_window_start(store, "US", contract) == date(2011, 1, 3)


def test_a_crawl_that_started_late_is_refused_rather_than_resolved_forward(store):
    """Resolving the boundary forward must not disarm the guard it works around.

    A crawl that began years after the contract's window also has a "first session
    on or after" it, and every count over the result would be computed correctly
    across the wrong window — the same silent failure `WindowNotCovered` exists
    for. A closure is days; a hole is months, and the two stay distinguishable.
    """
    late = _daily(date(2013, 5, 2), 10)
    store.append_bars("US", "BASE", _bars_from_hlc(late, _ramp_hlc(10)))
    contract = _contract_where(values={WINDOW_STORE_START_KEY: "2011-01-01"})

    with pytest.raises(WindowNotCovered):
        store_window_start(store, "US", contract)

    # The bound is a real closure, not a fudge: inside it, the same store is fine.
    inside = _contract_where(values={
        WINDOW_STORE_START_KEY: (date(2013, 5, 2) - LONGEST_CLOSURE).isoformat()
    })
    assert store_window_start(store, "US", inside) == date(2013, 5, 2)


def test_the_measured_end_resolves_per_market_not_once_for_both(store):
    """The two exchanges do not close on the same days.

    ``latest_complete_session`` is a sentinel because the store's last session
    moves every night. Resolved once and shared, it would either clip the market
    whose crawl finished later or ask the other for a session it does not hold —
    and `check_window_covered` would refuse the second for a reason that is really
    about the sentinel.
    """
    us = _daily(date(2020, 1, 1), 10)
    idx = _daily(date(2020, 1, 1), 8)
    store.append_bars("US", "BASE", _bars_from_hlc(us, _ramp_hlc(10)))
    store.append_bars("IDX", "BASE.JK", _bars_from_hlc(idx, _ramp_hlc(8)))

    assert measured_end(store, "US") == us[-1]
    assert measured_end(store, "IDX") == idx[-1]

    # A contract that pins the window shut is honoured as written.
    pinned = _contract_where(values={WINDOW_MEASURED_END_KEY: "2020-01-05"})
    assert measured_end(store, "US", pinned) == date(2020, 1, 5)


# -- both markets, end to end --------------------------------------------------


def test_both_markets_replay_end_to_end_over_the_full_window(store, denominator):
    """The acceptance criterion, whole: each market's own forward chain, persisted.

    Each market is replayed separately and neither is interleaved with the other —
    a market is a chain, and two chains sharing a session sequence would replay
    each on the other's calendar.
    """
    dates = _seed_two_market_store(store)
    contract = _fixture_contract(dates)

    run = run_full(store, denominator, contract)

    assert run.markets == ("US", "IDX")
    for market in ("US", "IDX"):
        market_run = run.for_market(market)
        assert [r.session for r in market_run.sessions] == dates
        assert denominator.sessions(market, burn_in=False) == list(market_run.measured)
    # Each market's rows are its own, keyed by market in the one store.
    assert denominator.universe("US", dates[-1]) == ["BASE"]
    assert denominator.universe("IDX", dates[-1]) == ["BASE.JK"]


def test_burn_in_is_persisted_and_excluded_from_measurement_in_both_markets(
    store, denominator
):
    """Ticket criterion. The burn-in is a date, and it is the same date in both
    markets — the sessions before it are computed, persisted and flagged, never
    skipped, because a warm-up session is a fact about the window rather than a
    hole in it."""
    dates = _seed_two_market_store(store)

    run = run_full(store, denominator, _fixture_contract(dates))

    for market in ("US", "IDX"):
        market_run = run.for_market(market)
        assert [r.session for r in market_run.measured] == dates[-5:]
        assert [r.session for r in market_run.burn_in] == dates[:-5]
        assert len(denominator.sessions(market)) == len(dates)
        assert denominator.universe(market, dates[-6]) != []


def test_each_market_replays_its_own_calendar_and_never_the_others(store, denominator):
    """Two markets, two calendars, and no session borrowed between them.

    The gap check cannot fire here and it is important to say why: each window is
    *sliced from* its own market's calendar, so it is contiguous by construction —
    which is exactly the reason `check_window_covered` and the per-session
    detection count both exist (stories 75 and 77). What can still go wrong once
    there are two markets is subtler and is what this pins: replaying IDX across
    US's session list. The two exchanges keep different calendars, so a shared
    sequence would ask IDX for sessions it never traded and silently drop the ones
    it did.
    """
    dates = _seed_two_market_store(store)
    # A session IDX did not trade and US did.
    store._con.execute(  # noqa: SLF001 — the fixture reaches in to author a closure
        "DELETE FROM bars WHERE market = 'IDX' AND session = ?", [dates[50]]
    )
    idx_calendar = [d for d in dates if d != dates[50]]

    run = run_full(store, denominator, _fixture_contract(dates))

    assert [r.session for r in run.for_market("US").sessions] == dates
    assert [r.session for r in run.for_market("IDX").sessions] == idx_calendar
    # Each is its own market's calendar, read back from the store rather than
    # asserted twice.
    for market, calendar in (("US", dates), ("IDX", idx_calendar)):
        assert window_sessions(
            store, market, start=calendar[0], end=calendar[-1]
        ) == calendar


def test_a_gapped_session_sequence_still_fails_loudly_under_the_full_run(
    store, denominator
):
    """The refusal the criterion names, reached through this module's own path.

    A backtest that quietly skips a session reports on a market that took the day
    off. `run_denominator` owns the check; what is asserted here is that the full
    run does not route around it — the window it builds per market is handed to
    the same chain, so a sequence with a hole in it raises before anything is
    computed.
    """
    dates = _seed_two_market_store(store)
    contract = _fixture_contract(dates)

    with pytest.raises(GapError):
        run_denominator(
            store, denominator, "IDX", contract,
            sessions=dates[:10] + dates[11:], measured_start=dates[-5],
        )


def test_no_session_is_recomputed_when_the_run_is_resumed(store, denominator, monkeypatch):
    """Ticket criterion: no session recomputed. Also how a long run is resumed.

    A fourteen-year two-market pass is measured in hours, so it has to be safe to
    re-run — and a re-run that recomputed would both cost the hours again and be
    unable to prove it had produced the same rows.
    """
    dates = _seed_two_market_store(store)
    contract = _fixture_contract(dates)
    first = run_full(store, denominator, contract)

    def refuse(*args, **kwargs):
        raise AssertionError("a persisted session was reclassified, not reused")

    monkeypatch.setattr("backtest.chain.classify", refuse)
    second = run_full(store, denominator, contract)

    assert [r.sessions for r in second.runs] == [r.sessions for r in first.runs]
    for market in ("US", "IDX"):
        assert len(denominator.sessions(market)) == len(dates)


def test_a_market_outside_the_contracts_scope_cannot_be_run(store, denominator):
    """`markets` narrows a run for a one-market reproduction; it never widens one.

    A market the contract does not scope has no committed window to run over, so
    running it would invent one — and the result would be stamped with a contract
    that never authorised it.
    """
    dates = _seed_two_market_store(store)

    with pytest.raises(ValueError):
        run_full(store, denominator, _fixture_contract(dates), markets=["US", "XETRA"])

    # Narrowing is allowed, and reports only what it ran.
    narrowed = run_full(store, denominator, _fixture_contract(dates), markets=["IDX"])
    assert narrowed.markets == ("IDX",)


def test_a_market_that_was_not_run_is_not_reported_as_an_empty_one(store, denominator):
    """A market that never ran and a market that ran and found nothing are
    different claims. Folded together, a one-market run would print an empty
    column for the other and read as a market that took fourteen years off."""
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), markets=["US"])

    with pytest.raises(MarketNotRun):
        run.for_market("IDX")


# -- detections per session, plotted, per market -------------------------------


def test_detections_per_session_are_plotted_across_the_window_for_each_market(
    store, denominator
):
    """Ticket criterion. A count that collapses in a given year is a data hole,
    and it reads as a quiet market until someone looks — so the series is reported
    per session and drawn across the whole window, per market."""
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), anchors=_settled())

    for market in ("US", "IDX"):
        series = run.detections_per_session(market)
        assert list(series) == dates[-5:]
        months = market_series(run.for_market(market))
        assert months, "the window produced no plotted series at all"
        assert format_detections_grid(months), "the series did not draw"

    text = format_full_run(run)
    assert text.count("detections per session") == 2


def test_the_plot_is_the_one_figures_draws_rather_than_a_second_one(
    store, denominator
):
    """The full run plots off the denominator alone — it does not pay for the
    simulation `figures_for_market` runs — but it must not thereby grow a second
    set of rules about what a hole looks like. Same series, same grid."""
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates))
    market_run = run.for_market("US")

    measured = market_run.measured
    expected = detections_series(
        [s.session for s in measured],
        Counter({s.session: s.detections for s in measured if s.detections}),
    )

    assert market_series(market_run) == [p.to_dict() for p in expected]


def test_a_month_the_store_never_covered_plots_as_a_hole_not_as_a_quiet_month(
    store, denominator
):
    """The distinction the plot exists for. A month with sessions and no
    detections is a real zero; a month the window skipped entirely is a hole, and
    a yearly mean cannot tell them apart — it drops by a twelfth and reads as a
    slow year."""
    # January into February, then April into May: March is inside the window and
    # has no session at all, and every session that exists detects nothing.
    dates = _daily(date(2020, 1, 1), 40) + _daily(date(2020, 4, 1), 40)

    points = detections_series(dates, Counter())

    assert {(p.year, p.month) for p in points if p.hole} == {(2020, 3)}
    # Every other month is a measured zero, not a hole — the distinction a yearly
    # mean cannot draw and the reason the series is plotted at all.
    assert {(p.year, p.month) for p in points if not p.hole} == {
        (2020, 1), (2020, 2), (2020, 4), (2020, 5)
    }
    assert all(p.detections == 0 for p in points)
    assert all(p.per_session == 0.0 for p in points if not p.hole)
    assert all(p.per_session is None for p in points if p.hole)


# -- the anchors gate ----------------------------------------------------------


def test_no_figure_is_read_until_the_anchors_are_settled(store, denominator):
    """Ticket criterion, and the plan's third rule made a refusal.

    Reading a new figure from a pipeline whose old figures have not reproduced is
    exactly the failure the rule exists to prevent, so the report raises rather
    than printing numbers a reader would have no way to distrust.
    """
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), anchors=_unsettled())

    assert run.settled is False
    with pytest.raises(AnchorsNotSettled):
        full_run_report(run)
    with pytest.raises(AnchorsNotSettled):
        format_full_run(run)


def test_a_run_nobody_anchored_is_not_an_anchored_run(store, denominator):
    """Anchors never checked is the same answer as anchors failed. The rule is
    about what has been *established* before a figure is read, not about what was
    attempted — and the replay itself still happened and still persisted, because
    the gate is on reading, not on working."""
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates))

    assert run.anchors is None
    assert run.settled is False
    with pytest.raises(AnchorsNotSettled):
        full_run_report(run)
    # The work was done regardless: the rows are on disk.
    assert len(denominator.sessions("US")) == len(dates)


def test_a_divergence_with_a_written_cause_settles_the_anchors(store, denominator):
    """The plan's "reproduce it, **or** explain the divergence in writing".

    A cause is not a pass — the check still records a divergence — but it is
    enough to license reading the run, which is the whole of what the third rule
    asks for.
    """
    dates = _seed_two_market_store(store)
    explained = check_anchors(
        _stateless_measurements(geometry={"three": 1.20}),
        universe=UNIVERSE_STATELESS,
        explained={
            "median_range_3bar_adr": "the backtest store excludes the reference "
            "ETFs his entries include (#162)"
        },
    )
    run = run_full(store, denominator, _fixture_contract(dates), anchors=explained)

    assert run.settled is True
    body = full_run_report(run)["anchors"]
    assert body["settled"] is True
    # The payload names *which* anchor did not reproduce, not merely that the
    # run was allowed to proceed.
    assert body["diverged_with_cause"] == ["median_range_3bar_adr"]
    # Recorded as a divergence, never reported as a match.
    check = next(c for c in explained.checks if c.anchor.key == "median_range_3bar_adr")
    assert check.verdict == "diverged (explained)"


# -- reported apart, never pooled ----------------------------------------------


def test_the_two_markets_are_reported_apart_with_no_pooled_figure(store, denominator):
    """Ticket criterion, and findings §8's result honoured rather than averaged away.

    Every count in the payload is inside a market's own block. There is no total
    across them — not because one was forgotten, but because a figure that
    describes neither market is worse than no figure at all.
    """
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), anchors=_settled())

    report = full_run_report(run)

    assert set(report["per_market"]) == {"US", "IDX"}
    for market in ("US", "IDX"):
        block = report["per_market"][market]
        assert block["market"] == market
        assert block["sessions_measured"] == 5
        assert block["sessions_burn_in"] == len(dates) - 5
    # No pooled count anywhere at the top level.
    assert "detections" not in report
    assert "sessions_measured" not in report
    assert not hasattr(run, "detections")


def test_the_payload_is_stamped_with_the_contract_that_produced_it(store, denominator):
    """Two runs under different contracts are distinguishable from their
    serialised output alone — the house rule for every result the package emits."""
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), anchors=_settled())

    assert CONTRACT_KEY in full_run_report(run)


def test_the_reference_exclusion_is_reported_per_market(store, denominator):
    """#162's exclusion is a reported fact about *this* run, per market, and not
    only a property of the code that ran it: each market's benchmarks are its own,
    and a reader of one market's block should not have to consult the other's."""
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), anchors=_settled())

    blocks = full_run_report(run)["per_market"]
    assert blocks["US"]["references_excluded"] == [MARKET_INDEX["US"]]
    assert blocks["IDX"]["references_excluded"] == [MARKET_INDEX["IDX"]]


def test_a_report_read_off_disk_gates_as_strictly_as_one_checked_in_process(tmp_path):
    """The gate the command-line path actually uses.

    The anchors are checked in a separate invocation, so all the run can see is
    what that invocation wrote down. The JSON here is produced by the real writer
    rather than authored by hand, so the reader cannot drift from the shape it is
    reading — a settled-ness check that silently stopped matching the file would
    wave every run through.
    """
    path = tmp_path / "anchors.json"
    path.write_text(
        json.dumps(anchors_report(DEFAULT_CONTRACT, check_anchors(_all_measurements())))
    )

    outcome = read_anchor_report(path)

    assert outcome.passes is True
    assert outcome.failed == ()
    assert outcome.failed == ()


def test_a_divergence_with_a_cause_survives_the_round_trip_to_disk(tmp_path):
    """A written cause licenses the run whether the check ran here or elsewhere.

    The verdict strings are the contract between the two, which is why they are
    named constants rather than literals repeated on both sides of a JSON file.
    """
    report = check_anchors(
        _all_measurements(geometry={"three": 1.20}),
        explained={"median_range_3bar_adr": "the reference ETFs are out of scope"},
    )
    path = tmp_path / "anchors.json"
    path.write_text(json.dumps(anchors_report(DEFAULT_CONTRACT, report)))

    assert read_anchor_report(path).passes is True
    assert VERDICT_EXPLAINED in SETTLED_VERDICTS
    assert VERDICT_FAILED not in SETTLED_VERDICTS


def test_four_of_six_read_off_disk_is_not_an_anchored_run(tmp_path, store, denominator):
    """The shape that most reads like a pass.

    A geometry-only report has three passing rows and no failing one, so a reader
    that decided settled-ness from the verdicts alone would let it through. The
    run is not anchored, and the refusal says which half was missing rather than
    naming an anchor that did not fail.
    """
    geometry_only = AnchorReport(
        detector_version=DETECTOR_VERSION,
        arms=ANCHOR_ARMS,
        geometry=check_geometry(_geometry_measurements()),
        gate_dependent=(),
        geometry_only=True,
    )
    path = tmp_path / "anchors.json"
    path.write_text(json.dumps(anchors_report(DEFAULT_CONTRACT, geometry_only)))

    outcome = read_anchor_report(path)
    assert outcome.passes is False
    assert outcome.geometry_only is True
    assert outcome.failed == ()  # nothing failed; the gate-dependent half is absent

    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), anchors=outcome)
    with pytest.raises(AnchorsNotSettled, match="four of six"):
        full_run_report(run)


def test_the_payload_names_the_universe_the_run_was_anchored_over(
    store, denominator
):
    """#211's rule, carried on the artefact a later phase actually reads. A
    settled-ness flag with no universe beside it is the citation that rule
    forbids: §4b's gap is +1.95pp under one universe and −5.01pp under the other,
    so "the anchors settled" is only a fact once it says which field."""
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), anchors=_settled())

    body = full_run_report(run)["anchors"]

    assert body["settled"] is True
    assert body["universe"] == UNIVERSE_STATELESS
    assert f"{UNIVERSE_STATELESS} universe" in format_full_run(run)


def test_the_payload_says_which_anchor_cannot_corroborate_this_run(
    store, denominator
):
    """"Settled" does not mean "independently confirmed", and the payload has to
    say so. The stateless pin was measured by the run it anchors, so it detects
    drift from here on and corroborates nothing yet — a later phase reading only
    this file would otherwise take a settled verdict for confirmation."""
    dates = _seed_two_market_store(store)
    run = run_full(store, denominator, _fixture_contract(dates), anchors=_settled())

    assert full_run_report(run)["anchors"]["first_measurement"] == [
        "in_field_stateless"
    ]


def test_the_first_measurement_flag_survives_the_round_trip_to_disk(tmp_path):
    """It reaches the gate whether the anchors were checked here or elsewhere,
    like every other name the two report kinds answer."""
    report = check_anchors(_stateless_measurements(), universe=UNIVERSE_STATELESS)
    path = tmp_path / "anchors.json"
    path.write_text(json.dumps(anchors_report(DEFAULT_CONTRACT, report)))

    assert report.first_measurement == ("in_field_stateless",)
    assert read_anchor_report(path).first_measurement == ("in_field_stateless",)


def test_a_field_file_with_no_in_field_row_names_no_universe(tmp_path):
    """There is no default to fall back on. A file carrying no field row records
    no universe, and choosing one at the command line would decide exactly the
    thing the file exists to record."""
    path = tmp_path / "field.json"
    path.write_text(json.dumps({
        "detection_recall": {"passed": 421, "of": 503, "stage": "detection"}
    }))

    with pytest.raises(DriftError, match="names no universe"):
        _universe_of(_field_measurements(str(path)), str(path))


def test_a_green_report_over_the_app_universe_does_not_anchor_this_run(
    store, denominator
):
    """The one failure a *passing* report can carry.

    Every anchor in it matched — over the app's universe, which is not the field
    this run screened. #211 measured that in_field and §4b's gap are properties of
    the pair, so a report over the other universe anchors a different run however
    green it is, and the gate has to see the difference between a report that
    passed and a report that passed about something else.
    """
    dates = _seed_two_market_store(store)
    app_universe = check_anchors(_all_measurements(), universe=UNIVERSE_APP)
    assert app_universe.passes is True

    run = run_full(
        store, denominator, _fixture_contract(dates), anchors=app_universe
    )

    with pytest.raises(AnchorsNotSettled, match=UNIVERSE_APP):
        format_full_run(run)


def test_an_anchor_report_written_before_the_second_pin_is_refused(tmp_path):
    """A report on disk with no ``universe`` key was written before #211 split the
    pin, so it anchored §4b's figure over whatever field it happened to have. It
    reads back as the app's universe — the honest default — rather than as this
    run's, so the gate refuses it instead of believing it."""
    body = anchors_report(DEFAULT_CONTRACT, check_anchors(_all_measurements()))
    del body["universe"]
    path = tmp_path / "anchors.json"
    path.write_text(json.dumps(body))

    assert read_anchor_report(path).universe == UNIVERSE_APP


def test_the_run_reports_which_anchors_were_not_settled(store, denominator):
    """A refusal that does not name the anchor sends its reader to the whole table."""
    dates = _seed_two_market_store(store)
    run = run_full(
        store, denominator, _fixture_contract(dates),
        anchors=AnchorOutcome(passes=False, failed=("in_field",)),
    )

    with pytest.raises(AnchorsNotSettled, match="in_field"):
        format_full_run(run)


def test_a_live_report_and_one_read_off_disk_answer_the_same_four_names():
    """The gate reads one interface, so there is no second code path to keep in
    step with the first. `AnchorOutcome` exists because a command-line run can only
    see what a previous invocation wrote down — not so that settled-ness can be
    decided twice."""
    report = check_anchors(
        _all_measurements(geometry={"three": 1.20}),
        explained={"median_range_3bar_adr": "scope"},
    )

    for name in ("passes", "failed", "explained", "geometry_only"):
        assert hasattr(report, name), name
        assert hasattr(AnchorOutcome(passes=True), name), name

    assert report.passes is True
    assert report.failed == ()
    assert report.explained == ("median_range_3bar_adr",)
    assert report.geometry_only is False


def test_the_geometry_only_refusal_reads_the_flag_rather_than_an_empty_failure_list():
    """A geometry-only report has passing rows and no failing one. Deducing "not
    anchored" from what failed would be deducing it from the very thing that makes
    it read like a pass, so the flag is carried and read."""
    geometry_only = AnchorReport(
        detector_version=DETECTOR_VERSION,
        arms=ANCHOR_ARMS,
        geometry=check_geometry(_geometry_measurements()),
        gate_dependent=(),
        geometry_only=True,
    )

    assert geometry_only.failed == ()      # nothing failed …
    assert geometry_only.passes is False   # … and it is still not anchored.
    assert geometry_only.geometry_only is True


def test_a_market_the_store_holds_no_sessions_for_is_refused_by_both_bounds(store):
    """One empty store, one answer. `measured_end` returning None where
    `store_window_start` raises would have meant "run to the store's own edge",
    which is how a run over nothing reports a clean empty window."""
    store.append_bars("US", "BASE", _bars_from_hlc(_daily(date(2020, 1, 1), 5), _ramp_hlc(5)))

    with pytest.raises(WindowNotCovered):
        store_window_start(store, "IDX")
    with pytest.raises(WindowNotCovered):
        measured_end(store, "IDX")


# -- sweeps, and the verdict (issue #199) --------------------------------------
#
# Phase 5's last cell and the decision it feeds. Two claims are load-bearing here,
# and neither is a calculation:
#
#   * **Order.** The pre-registered metric is computed and *recorded* before any
#     variant is swept. That is enforced by the type rather than documented: a
#     sweep needs a `RecordedMetric`, and the only way to make one is to read the
#     headline back off disk.
#   * **Precedence.** The pre-registered figure stands as the headline even where a
#     swept variant looks better, and no swept figure may enter the verdict — which
#     is why a swept report handed to `verdict_report` is refused rather than
#     quietly used.
#
# The criteria themselves are the contract's, evaluated where the contract says: the
# kill globally on the survivor-biased number, the ship per market and only where
# Phase 2's pessimistic bound stays above zero. The fixtures below author metric
# reports directly, because a verdict is arithmetic over two numbers per market and
# a fixture that ran a chain to reach them would put four phases' bugs inside this
# one's tests.

from backtest.sweep import (
    AXES,
    COST_AXIS,
    COST_MULTIPLIERS,
    HEADLINE_RULE,
    NOT_SWEPT,
    SCORE_FLOORS,
    SCORE_FLOOR_AXIS,
    SweptBeforeRecorded,
    SweptResult,
    best_variant,
    cost_variants,
    format_sweep,
    headline as sweep_headline,
    read_recorded,
    score_floor_variants,
    sweep_report,
    variant_contract,
    variants,
)
from backtest.sweep import main as sweep_main
from backtest.verdict import (
    INCONCLUSIVE,
    KILL,
    KILL_BASIS,
    LICENSED,
    NO_BOUND_REASON,
    ONE_MARKET_FAILURE,
    PRECEDENCE,
    SHIP,
    SweptVerdictRefused,
    check_kill_cell,
    DERIVED_BOUND_NOTE,
    WEAK_BASIS_CAVEAT,
    bound_bases,
    check_ship_cell,
    format_verdict,
    market_finding,
    verdict_report,
)
from backtest.verdict import main as verdict_main
from backtest.contract import (
    DECISION_KILL_KEY,
    DECISION_SHIP_KEY,
    DETECTION_GATE_KEY,
)
from backtest.survivorship import attach_bias_bound


def _recorded_metric(tmp_path, trades, *, name: str = "metric.json"):
    """The pre-registered metric, computed and written to disk — the ordering rule.

    Written and read back rather than passed in memory, because "recorded" is the
    load-bearing word in the acceptance criterion and a fixture that skipped the
    file would test a weaker claim than the code makes.
    """
    out = tmp_path / name
    out.write_text(json.dumps(metric_report(DEFAULT_CONTRACT, trades), indent=1))
    return read_recorded(out)


def _sweep_cohort(*scored):
    """Scored trades keyed by market, the shape `sweep_report` takes."""
    by_market: dict[str, list] = {"US": [], "IDX": []}
    for s in scored:
        by_market.setdefault(s.market, []).append(s)
    return by_market


def test_no_sweep_runs_before_the_pre_registered_metric_is_recorded(tmp_path):
    """The first acceptance criterion, made unrepresentable rather than documented.

    A sweep needs a recorded headline, and the only way to obtain one is to read a
    file. No file, no sweep — and the refusal arrives before a bar is opened, so a
    run cannot compute its variants and *then* discover the order was wrong.
    """
    with pytest.raises(SweptBeforeRecorded):
        read_recorded(tmp_path / "never-written.json")

    # The command refuses on a store path that does not exist either, which proves
    # the ordering check ran before anything reached for the bars.
    with pytest.raises(SweptBeforeRecorded):
        sweep_main([
            "--store", str(tmp_path / "no-such-store.duckdb"),
            "--recorded", str(tmp_path / "never-written.json"),
        ])


def test_a_sweep_of_a_sweep_is_refused_because_it_hides_the_first_count(tmp_path):
    """Sweeping a swept report would report the second count and drop the first —
    eight variants behind a figure would read as one."""
    already = metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2015, 1.0)])
    already["sweep"] = {"variants_tried": 4, "note": "already swept"}
    path = tmp_path / "swept.json"
    path.write_text(json.dumps(already))

    with pytest.raises(SweptBeforeRecorded):
        read_recorded(path)


def test_a_report_that_does_not_claim_pre_registration_is_not_a_headline(tmp_path):
    """Only the pre-registered metric may be swept against: a payload without the
    flag is some other number, and a swept variant reported beside it would be a
    comparison against nothing that was promised."""
    unmarked = metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2015, 1.0)])
    unmarked["pre_registered"] = False
    path = tmp_path / "unmarked.json"
    path.write_text(json.dumps(unmarked))

    with pytest.raises(SweptBeforeRecorded):
        read_recorded(path)


def test_a_headline_recorded_for_another_metric_is_drift(tmp_path):
    """A swept arm-B variant reported against an arm-A promise is the after-the-fact
    headline pre-registration exists to prevent, arriving through the file."""
    other = metric_report(DEFAULT_CONTRACT, [_mtrade("AAA", 2015, 1.0)])
    other["metric"] = "arm_a_after_cost_expectancy_r"
    path = tmp_path / "other.json"
    path.write_text(json.dumps(other))

    with pytest.raises(ContractDrift):
        read_recorded(path)


def test_every_swept_result_is_reported_with_the_count_of_variants_tried(tmp_path):
    """The count rides on the payload, on every variant, and on every market block.

    One number in three places rather than a total a reader has to compute: a
    variant quoted out of the report carries its own denominator.
    """
    trades = [_mtrade("AAA", 2015, 2.0), _mtrade("BBB", 2016, -1.0)]
    recorded = _recorded_metric(tmp_path, trades)
    cohort = _sweep_cohort(
        _rtrade("AAA", 6, 2.0, year=2015), _rtrade("BBB", 3, -1.0, year=2016)
    )

    report = sweep_report(recorded, cohort)
    tried = len(variants())

    assert tried == len(COST_MULTIPLIERS) + len(SCORE_FLOORS)
    assert report["variants_tried"] == tried
    assert [v["axis"] for v in report["variants"]].count(COST_AXIS) == len(
        COST_MULTIPLIERS
    )
    for variant in report["variants"]:
        assert variant["variants_tried"] == tried
        assert variant["is_headline"] is False
        for body in variant["markets"]:
            assert body["variants_tried"] == tried
            assert body["is_headline"] is False
    assert set(AXES) == {COST_AXIS, SCORE_FLOOR_AXIS}


def test_the_pre_registered_number_stands_even_where_a_swept_one_looks_better(tmp_path):
    """The third acceptance criterion. A score floor that drops the loser lifts the
    swept figure well above the headline — and the headline is still the headline."""
    trades = [_mtrade("AAA", 2015, 6.0), _mtrade("BBB", 2016, -1.0)]
    recorded = _recorded_metric(tmp_path, trades)
    # The 3-point trade is the loser, so every floor at 4 and above cuts it and the
    # remaining cohort is the winner alone.
    cohort = _sweep_cohort(
        _rtrade("AAA", 7, 6.0, year=2015), _rtrade("BBB", 3, -1.0, year=2016)
    )

    report = sweep_report(recorded, cohort)
    best = best_variant(report, market="US")

    assert best.beats_headline is True
    assert best.is_headline is False
    assert best.axis == SCORE_FLOOR_AXIS
    # The figure that stands is the recorded one, whatever the sweep found.
    assert sweep_headline(report, market="US") == recorded.expectancy("US")
    assert report["pre_registered"]["is_headline"] is True
    assert report["headline_rule"] == HEADLINE_RULE

    page = format_sweep(report)
    # The headline is printed before any swept figure: a reader who reaches the
    # flattering number has passed the one that stands to get there.
    assert page.index("the pre-registered headline") < page.index("most flattering")
    assert f"{best.variants_tried} variants tried" in page


def test_a_swept_figure_and_its_count_are_one_value_and_cannot_be_separated():
    """The count is a field on the result rather than a lookup beside it, so a
    swept figure quoted out of the report keeps the number of chances it had."""
    result = SweptResult(
        axis=SCORE_FLOOR_AXIS, label="score>=6", market="US", window=FULL_WINDOW,
        expectancy_r=1.25, variants_tried=8, headline_r=0.05,
    )

    assert "8 variants tried" in result.line()
    assert "+1.250R" in result.line() and "+0.050R" in result.line()
    assert result.beats_headline is True
    with pytest.raises(TypeError):
        SweptResult(axis="a", label="b", market="US", window=FULL_WINDOW,
                    expectancy_r=1.0)  # no count: not constructible


def test_a_cost_variant_scales_both_components_in_every_market_and_nothing_else():
    """Costs are swept together across markets: a variant that raised Jakarta's and
    left New York's alone would be two variants reported as one, and the per-market
    comparison the run is built on would stop being a comparison."""
    for variant in cost_variants():
        multiplier = float(variant.label.removeprefix("costs×"))
        for market, costs in DEFAULT_CONTRACT.value(COSTS_KEY).items():
            swept = variant.contract.value(COSTS_KEY)[market]
            assert swept["commission_bps"] == pytest.approx(
                costs["commission_bps"] * multiplier
            )
            assert swept["slippage_bps"] == pytest.approx(
                costs["slippage_bps"] * multiplier
            )
        # Every other cell is the committed one, so a cost variant measures costs.
        moved = [
            c.key for c in variant.contract.cells
            if c.value != DEFAULT_CONTRACT.value(c.key)
        ]
        assert moved == [COSTS_KEY]
        assert variant.min_points is None


def test_a_score_floor_variant_cuts_the_cohort_and_leaves_the_contract_alone():
    """A swept threshold is a cut over the cohort, never a cell. Inventing a cell
    for it would put a threshold chosen after the fact in the same object as the
    ones promised before it."""
    low = _rtrade("AAA", 3, 1.0)
    high = _rtrade("BBB", 7, 1.0)

    for variant in score_floor_variants():
        floor = int(variant.label.removeprefix("score>="))
        assert variant.contract is DEFAULT_CONTRACT
        assert variant.keep(low) is (3 >= floor)
        assert variant.keep(high) is (7 >= floor)


def test_the_detection_gate_is_not_swept_and_the_report_says_so(tmp_path):
    """The denominator was built against the contract's gate width, so a swept gate
    is a new crawl rather than a variant of this run — recorded as a named absence
    rather than left for a reader to notice."""
    recorded = _recorded_metric(tmp_path, [_mtrade("AAA", 2015, 1.0)])
    report = sweep_report(recorded, _sweep_cohort(_rtrade("AAA", 6, 1.0)))

    assert DETECTION_GATE_KEY in NOT_SWEPT
    assert DETECTION_GATE_KEY in report["not_swept"]["cells"]
    for variant in variants():
        assert variant.contract.value(DETECTION_GATE_KEY) == DEFAULT_CONTRACT.value(
            DETECTION_GATE_KEY
        )


def test_a_sweep_moves_no_committed_constant(tmp_path):
    """The last acceptance criterion. A variant contract is a value that is built,
    printed and thrown away: the committed contract's bytes are unchanged, and
    `DEFAULT_CONTRACT` still holds the pre-registered costs after a full sweep."""
    before = DEFAULT_CONTRACT_JSON.read_text()
    costs_before = json.dumps(DEFAULT_CONTRACT.value(COSTS_KEY), sort_keys=True)

    recorded = _recorded_metric(tmp_path, [_mtrade("AAA", 2015, 1.0)])
    sweep_report(recorded, _sweep_cohort(_rtrade("AAA", 6, 1.0)))

    assert DEFAULT_CONTRACT_JSON.read_text() == before
    assert json.dumps(DEFAULT_CONTRACT.value(COSTS_KEY), sort_keys=True) == costs_before
    # And the variant builder returns a new value rather than mutating its input.
    variant = variant_contract(
        DEFAULT_CONTRACT, key=COSTS_KEY, value={}, why="a swept variant"
    )
    assert variant is not DEFAULT_CONTRACT
    assert DEFAULT_CONTRACT.value(COSTS_KEY) != {}
    assert variant.label != DEFAULT_CONTRACT.label  # two contracts, distinguishable


# -- the verdict ---------------------------------------------------------------


def _window_cell(label: str, expectancy, *, closed: int = 100) -> dict:
    """One expectancy cell, authored — the two figures a criterion actually reads.

    `total_r` and `cost_r` are the ones `bias_bound` re-runs the cell with, so they
    are consistent with the expectancy by construction rather than by coincidence.
    """
    return {
        "label": label,
        "expectancy_r": expectancy,
        "closed": 0 if expectancy is None else closed,
        "cost_r": 0.0,
        "total_r": 0.0 if expectancy is None else expectancy * closed,
    }


def _vreport(markets: dict, *, hole: float | None = 0.1, swept: int = 0) -> dict:
    """A metric report as the verdict reads it: two windows per market, with a bound.

    `markets` maps a market to its (full, excluding-2020-21) expectancies. `hole`
    of `None` attaches no bound at all, which is the case the ship criterion must
    refuse rather than treat as a bound of zero.
    """
    report = {
        "contract": DEFAULT_CONTRACT.to_dict(),
        "metric": DEFAULT_CONTRACT.value(METRIC_PRIMARY_KEY),
        "arm": ARM_B,
        "pre_registered": True,
        "sweep": {"variants_tried": swept, "note": "fixture"},
        "markets": [
            {
                "market": market,
                "arm": ARM_B,
                "years": [],
                "windows": [
                    _window_cell(FULL_WINDOW, full),
                    _window_cell(EXCLUDED_YEARS_WINDOW, excluded),
                ],
            }
            for market, (full, excluded) in markets.items()
        ],
    }
    if hole is None:
        return report
    return attach_bias_bound(report, {market: hole for market in markets})


def test_the_kill_is_global_and_needs_both_markets_on_both_windows():
    """Findings §8 says magnitudes do not transfer, so one market failing is
    evidence about that market. The kill therefore needs every market in the
    contract's scope to fail, on the full window *and* with 2020–21 excluded."""
    both = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (-0.4, -0.6), "IDX": (-0.2, -0.3)})
    )
    assert both["verdict"] == KILL
    assert both["kill"]["fired"] is True
    assert both["kill"]["scope"] == "global"
    assert sorted(both["kill"]["failing"]) == ["IDX", "US"]

    # One window positive anywhere and the kill does not fire.
    one_window = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (-0.4, -0.6), "IDX": (-0.2, +0.3)})
    )
    assert one_window["verdict"] != KILL
    assert one_window["kill"]["fired"] is False


def test_the_kill_is_drawn_on_the_survivor_biased_figure_not_the_bounded_one():
    """Deliberately the biased number: survivorship inflates in a known direction,
    so a failure there is decisive because the honest figure can only be worse.
    Drawing the kill on the pessimistic twin instead would kill runs the contract
    does not kill — here, both markets are positive and both bounds are negative."""
    report = _vreport({"US": (+0.05, +0.02), "IDX": (+0.04, +0.03)}, hole=0.5)

    findings = [market_finding(body) for body in report["markets"]]
    assert all(w.pessimistic_r < 0 for f in findings for w in f.windows)
    assert not any(f.fails for f in findings)

    assert verdict_report(DEFAULT_CONTRACT, report)["verdict"] != KILL
    assert verdict_report(DEFAULT_CONTRACT, report)["basis"] == KILL_BASIS


def test_the_ship_is_per_market_and_requires_the_pessimistic_bound_above_zero():
    """A US pass licenses nothing in Jakarta, and a pass on the biased number
    proves much less than a failure does — which is why only this criterion has to
    clear Phase 2's bound."""
    report = verdict_report(
        DEFAULT_CONTRACT,
        _vreport({"US": (+2.0, +1.8), "IDX": (+0.05, +0.04)}, hole=0.2),
    )

    by_market = {body["market"]: body for body in report["markets"]}
    assert by_market["US"]["verdict"] == SHIP
    assert by_market["IDX"]["verdict"] == INCONCLUSIVE
    # Jakarta is positive on both windows and still does not ship: its bound sinks.
    assert all(w["expectancy_r"] > 0 for w in by_market["IDX"]["windows"])
    assert any(w["pessimistic_r"] <= 0 for w in by_market["IDX"]["windows"])
    assert report["ship"]["shipping"] == ["US"]
    assert report["ship"]["scope"] == "per_market"
    assert report["verdict"] == SHIP


def test_the_ship_reads_both_windows_and_not_the_full_one_alone():
    """The full window contains a mania that rewarded momentum nearly everywhere.
    A market positive there and negative without it has not passed."""
    report = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (+2.0, -0.1), "IDX": (-0.5, -0.5)})
    )

    by_market = {body["market"]: body for body in report["markets"]}
    assert by_market["US"]["verdict"] == INCONCLUSIVE
    assert by_market["US"]["ships"] is False
    assert "one window" in by_market["US"]["reason"]


def test_a_market_with_no_attached_bound_cannot_ship():
    """An absent bound is not a bound of zero. A market whose bias was never
    measured is unshippable and says which of the two it is."""
    report = verdict_report(
        DEFAULT_CONTRACT,
        _vreport({"US": (+2.0, +1.8), "IDX": (+2.0, +1.8)}, hole=None),
    )

    for body in report["markets"]:
        assert body["bound_attached"] is False
        assert body["verdict"] == INCONCLUSIVE
        assert body["reason"] == NO_BOUND_REASON
    assert report["verdict"] == INCONCLUSIVE


def test_the_one_market_failure_is_its_own_named_verdict():
    """Named in advance so it is not improvised in the moment: the method stands,
    and that market is off until a run explains why it differs."""
    report = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (+2.0, +1.8), "IDX": (-0.4, -0.6)})
    )

    by_market = {body["market"]: body for body in report["markets"]}
    assert report["verdict"] == ONE_MARKET_FAILURE
    assert by_market["IDX"]["verdict"] == ONE_MARKET_FAILURE
    assert "off until a run explains" in report["licenses"]
    # The passing market's own verdict is not swallowed by the run-level one.
    assert by_market["US"]["verdict"] == SHIP
    assert report["ship"]["shipping"] == ["US"]
    assert report["kill"]["fired"] is False


def test_neither_criterion_firing_is_reported_as_inconclusive():
    """The run is inconclusive and says so. The licence it grants is nothing —
    written out, because an unnamed licence is the one somebody improvises."""
    report = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (+0.05, -0.08), "IDX": (+0.1, -0.2)})
    )

    assert report["verdict"] == INCONCLUSIVE
    assert report["kill"]["fired"] is False
    assert report["ship"]["shipping"] == []
    assert "reaching for a swept variant" in report["licenses"]


def test_a_quiet_window_is_inconclusive_rather_than_a_failure():
    """A window with no closed trade has no expectancy to compare, and reading it
    as a failure would kill a market on missing data."""
    report = _vreport({"US": (None, None), "IDX": (-0.4, -0.6)})
    findings = [market_finding(body) for body in report["markets"]]
    by_market = {f.market: f for f in findings}

    assert by_market["US"].measured is False
    assert by_market["US"].fails is False
    assert by_market["US"].ships is False
    assert by_market["US"].verdict == INCONCLUSIVE
    assert verdict_report(DEFAULT_CONTRACT, report)["verdict"] == ONE_MARKET_FAILURE


def test_no_swept_figure_may_enter_the_verdict():
    """The contract's own sentence, made executable: reaching for a swept variant
    to break the tie is refused by the type, not discouraged by a comment."""
    with pytest.raises(SweptVerdictRefused):
        verdict_report(
            DEFAULT_CONTRACT,
            _vreport({"US": (+1.0, +1.0), "IDX": (+1.0, +1.0)}, swept=8),
        )

    not_registered = _vreport({"US": (+1.0, +1.0), "IDX": (+1.0, +1.0)})
    not_registered["pre_registered"] = False
    with pytest.raises(SweptVerdictRefused):
        verdict_report(DEFAULT_CONTRACT, not_registered)


def test_the_sweep_count_is_recorded_beside_a_verdict_none_of_it_informed(tmp_path):
    """The count rides on the verdict for the record — a reader sees how many
    variants were tried beside a decision none of them entered."""
    metric = _vreport({"US": (+2.0, +1.8), "IDX": (+2.0, +1.8)})
    recorded = _recorded_metric(tmp_path, [_mtrade("AAA", 2015, 1.0)])
    sweep = sweep_report(recorded, _sweep_cohort(_rtrade("AAA", 6, 1.0)))

    report = verdict_report(DEFAULT_CONTRACT, metric, sweep=sweep)

    assert report["sweep"]["variants_tried"] == len(variants())
    assert report["sweep"]["used_in_verdict"] is False
    assert report["verdict"] == SHIP  # the same verdict the sweep-free call gives
    assert verdict_report(DEFAULT_CONTRACT, metric)["verdict"] == SHIP


def test_a_verdict_cannot_be_reached_over_a_subset_of_the_contracts_markets():
    """The kill is global. Evaluating it over one market's block would fire the
    run's most consequential verdict on half the evidence."""
    with pytest.raises(ContractDrift):
        verdict_report(DEFAULT_CONTRACT, _vreport({"US": (-0.4, -0.6)}))


def test_a_kill_criterion_that_moved_out_from_under_the_code_is_drift():
    """The basis, the comparator and the both-markets requirement are pinned: a
    cell redrawn on the pessimistic figure describes a stricter kill than this code
    fires, and both would still print a verdict."""
    for value in (
        {**DEFAULT_CONTRACT.value(DECISION_KILL_KEY), "basis": "pessimistic_bound"},
        {**DEFAULT_CONTRACT.value(DECISION_KILL_KEY), "comparator": "<"},
        {**DEFAULT_CONTRACT.value(DECISION_KILL_KEY), "requires": ["full_window"]},
    ):
        moved = dataclasses.replace(
            DEFAULT_CONTRACT,
            cells=tuple(
                dataclasses.replace(c, value=value) if c.key == DECISION_KILL_KEY else c
                for c in DEFAULT_CONTRACT.cells
            ),
        )
        with pytest.raises(ContractDrift):
            check_kill_cell(moved)

    check_kill_cell(DEFAULT_CONTRACT)  # the committed one passes


def test_every_verdict_names_the_change_it_licenses_before_any_constant_moves():
    """`decision.licensed_changes` requires each verdict's licence to be written
    down in advance, so a result cannot be converted into an unguarded edit."""
    assert set(LICENSED) == set(PRECEDENCE)
    for licence in LICENSED.values():
        assert licence.strip()
    assert PRECEDENCE.index(KILL) < PRECEDENCE.index(ONE_MARKET_FAILURE)
    assert PRECEDENCE.index(ONE_MARKET_FAILURE) < PRECEDENCE.index(SHIP)
    assert PRECEDENCE.index(SHIP) < PRECEDENCE.index(INCONCLUSIVE)


def test_the_printed_verdict_carries_the_licence_beside_the_word():
    """A verdict read without its licence is a verdict somebody converts into an
    edit, so the licensed change is printed under it rather than in a footnote."""
    report = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (+2.0, +1.8), "IDX": (-0.4, -0.6)})
    )
    page = format_verdict(report)

    assert "verdict: ONE_MARKET_FAILURE" in page
    assert "licenses:" in page
    assert page.index("verdict: ONE_MARKET_FAILURE") < page.index("licenses:")
    assert "pessimistic" in page
    assert "swept variants tried: 0" in page


def test_the_verdict_and_the_sweep_move_no_committed_constant(tmp_path):
    """The ticket changes no detector, rubric or gate constant, and running the
    command end to end leaves the committed contract byte-identical."""
    before = DEFAULT_CONTRACT_JSON.read_text()
    gate_before = DEFAULT_CONTRACT.value(DETECTION_GATE_KEY)

    metric_path = tmp_path / "bounded.json"
    metric_path.write_text(
        json.dumps(_vreport({"US": (+2.0, +1.8), "IDX": (-0.4, -0.6)}))
    )
    assert verdict_main([
        "--metric-json", str(metric_path),
        "--out-json", str(tmp_path / "verdict.json"),
    ]) == 0

    assert DEFAULT_CONTRACT_JSON.read_text() == before
    assert DEFAULT_CONTRACT.value(DETECTION_GATE_KEY) == gate_before
    written = json.loads((tmp_path / "verdict.json").read_text())
    assert written["verdict"] == ONE_MARKET_FAILURE
    assert written["contract"] == DEFAULT_CONTRACT.to_dict()


def test_a_bound_counted_on_the_weaker_basis_carries_its_caveat_onto_the_verdict():
    """Phase 2 measured the two markets differently — US against a dated listing
    spine, IDX against the enumeration alone, where a recycled ticker cannot be
    told from an IPO. A ship licensed off the weaker basis is still a ship, but a
    reader who cannot see which basis it rests on cannot weigh it."""
    bases = {
        "US": {"basis": "listing_spine", "recycled_measured": True,
               "exposure_weighted": True},
        "IDX": {"basis": "enumeration_side", "recycled_measured": False,
                "exposure_weighted": False},
    }
    report = verdict_report(
        DEFAULT_CONTRACT,
        _vreport({"US": (+2.0, +1.8), "IDX": (+2.0, +1.8)}),
        bases=bases,
    )

    by_market = {body["market"]: body for body in report["markets"]}
    assert by_market["US"]["bound_caveat"] is None
    assert by_market["IDX"]["bound_caveat"] == WEAK_BASIS_CAVEAT
    assert by_market["IDX"]["bound_basis"]["basis"] == "enumeration_side"
    # Both still ship: the caveat weighs the licence, it does not withhold it.
    assert by_market["IDX"]["verdict"] == SHIP
    assert "caveat:" in format_verdict(report)

    # Without Phase 2's report there is no basis to report, and an absent caveat
    # is spelled as an absent one rather than as a clean bill.
    unweighed = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (+2.0, +1.8), "IDX": (+2.0, +1.8)})
    )
    assert all(body["bound_basis"] is None for body in unweighed["markets"])
    assert all(body["bound_caveat"] is None for body in unweighed["markets"])


def test_the_bound_basis_is_read_off_phase_twos_own_report():
    """Read rather than restated: the two markets' bases are a measurement #196
    made, and a second spelling of them here would drift from it silently."""
    survivorship = {
        "markets": [
            {"market": "US", "hole": {"basis": "listing_spine",
                                      "recycled_measured": True,
                                      "exposure_weighted": True}},
            {"market": "IDX", "hole": None},
        ]
    }

    bases = bound_bases(survivorship)

    assert set(bases) == {"US"}  # a market with no measured hole reports none
    assert bases["US"]["basis"] == "listing_spine"


def test_a_ship_criterion_that_moved_out_from_under_the_code_is_drift():
    """The kill has had this check since it was written and the ship needs it for
    the stronger reason: if `clears_phase2_pessimistic_bound` dropped out of the
    cell, this code would go on demanding the bound while the contract no longer
    did — and the disagreement would print as a verdict with a licence attached."""
    for value in (
        {**DEFAULT_CONTRACT.value(DECISION_SHIP_KEY), "scope": "global"},
        {**DEFAULT_CONTRACT.value(DECISION_SHIP_KEY), "requires": ["positive_result"]},
    ):
        moved = dataclasses.replace(
            DEFAULT_CONTRACT,
            cells=tuple(
                dataclasses.replace(c, value=value) if c.key == DECISION_SHIP_KEY else c
                for c in DEFAULT_CONTRACT.cells
            ),
        )
        with pytest.raises(ContractDrift):
            check_ship_cell(moved)
        with pytest.raises(ContractDrift):
            verdict_report(moved, _vreport({"US": (+2.0, +1.8), "IDX": (+2.0, +1.8)}))

    check_ship_cell(DEFAULT_CONTRACT)  # the committed one passes


def test_the_kills_threshold_and_both_windows_are_pinned_too():
    """A moved line kills a different set of runs, and a kill that stopped
    requiring the 2020–21-excluded window would fire on the mania alone."""
    for value in (
        {**DEFAULT_CONTRACT.value(DECISION_KILL_KEY), "threshold": -0.5},
        {**DEFAULT_CONTRACT.value(DECISION_KILL_KEY),
         "requires": ["both_markets", "full_window"]},
    ):
        moved = dataclasses.replace(
            DEFAULT_CONTRACT,
            cells=tuple(
                dataclasses.replace(c, value=value) if c.key == DECISION_KILL_KEY else c
                for c in DEFAULT_CONTRACT.cells
            ),
        )
        with pytest.raises(ContractDrift):
            check_kill_cell(moved)


def test_a_failing_market_does_not_revoke_the_other_markets_ship():
    """The ship is per market, so a Jakarta failure is evidence about Jakarta. The
    run-level verdict names the more consequential fact and its licence says in as
    many words that the other market keeps whatever its own verdict licensed —
    a run-level word that withdrew it would contradict the block beneath it."""
    report = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (+2.0, +1.8), "IDX": (-0.4, -0.6)})
    )

    assert report["verdict"] == ONE_MARKET_FAILURE
    assert report["ship"]["shipping"] == ["US"]
    assert "keeps its own verdict" in report["licenses"]
    page = format_verdict(report)
    assert page.index("US — ship") < page.index("IDX — one_market_failure")


def test_the_run_verdict_is_driven_off_the_declared_precedence():
    """The order a reader sees declared is the order the code takes: `run_verdict`
    walks `PRECEDENCE` rather than a hand-written chain that could drift from it."""
    ships = _vreport({"US": (+2.0, +1.8), "IDX": (+2.0, +1.8)})
    fails = _vreport({"US": (-0.4, -0.6), "IDX": (-0.2, -0.3)})
    mixed = _vreport({"US": (+2.0, +1.8), "IDX": (-0.4, -0.6)})
    neither = _vreport({"US": (+0.05, -0.08), "IDX": (+0.1, -0.2)})

    assert [
        verdict_report(DEFAULT_CONTRACT, r)["verdict"]
        for r in (fails, mixed, ships, neither)
    ] == list(PRECEDENCE)


def test_the_excluded_windows_pessimistic_figure_is_named_as_derived():
    """#196 attaches a bound to the full window only. The ship reads both, so the
    second twin is re-run here at the same hole share — an assumption, not a
    measurement, and one that makes the criterion stricter. It is recorded rather
    than left for a reader to infer from a figure Phase 2 never published."""
    report = verdict_report(
        DEFAULT_CONTRACT, _vreport({"US": (+2.0, +1.8), "IDX": (+2.0, +1.8)})
    )

    assert report["bound_note"] == DERIVED_BOUND_NOTE
    assert "same hole share" in report["bound_note"]
    for body in report["markets"]:
        assert all(w["pessimistic_r"] is not None for w in body["windows"])


def test_the_swept_page_prints_both_windows_for_every_variant(tmp_path):
    """A swept figure that only holds on the full window is a figure about the
    mania, and a table with one column would hide exactly that."""
    recorded = _recorded_metric(
        tmp_path, [_mtrade("AAA", 2015, 2.0), _mtrade("BBB", 2020, 4.0)]
    )
    report = sweep_report(
        recorded,
        _sweep_cohort(_rtrade("AAA", 6, 2.0, year=2015), _rtrade("BBB", 6, 4.0, year=2020)),
    )
    page = format_sweep(report)

    assert f"every variant — {FULL_WINDOW} | {EXCLUDED_YEARS_WINDOW}" in page
    # Both windows on every variant row, and the cohort size beside each figure.
    for variant in report["variants"]:
        for body in variant["markets"]:
            if body["market"] != "US":
                continue
            for label in (FULL_WINDOW, EXCLUDED_YEARS_WINDOW):
                cell = next(c for c in body["windows"] if c["label"] == label)
                if cell["expectancy_r"] is not None:
                    assert f"{cell['expectancy_r']:+.3f}R n={cell['closed']}" in page


def test_the_axes_a_sweep_reports_are_the_axes_it_ran(tmp_path):
    """One list. An axis added to the sweep and missing from its own report would
    be variants tried and never counted."""
    recorded = _recorded_metric(tmp_path, [_mtrade("AAA", 2015, 1.0)])
    report = sweep_report(recorded, _sweep_cohort(_rtrade("AAA", 6, 1.0)))

    assert [block["axis"] for block in report["axes"]] == list(AXES)
    assert {v.axis for v in variants()} == set(AXES)


# -- the write-up --------------------------------------------------------------
#
# Phase 7 (issue #200). The deliverables are documents and a command rather than
# a module, so what is testable about them is the one thing a document reliably
# gets wrong: **drift**. Every figure quoted below is re-read from the committed
# payload that produced it, so a rerun that moves a number and leaves the prose
# behind fails here rather than in a reader's hands.

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCES = REPO_ROOT / "references"
AUTHORITY_DOC = REFERENCES / "backtest_findings.md"
PLAIN_DOC = REFERENCES / "backtest_findings-plain.md"
HEADLINE_COMMAND = REPO_ROOT / "scripts" / "backtest_headline.sh"

SUMMARY_HEADING = "## The headline, and its bound"
LIMITS_HEADING = "## What this cannot say"


def _run_headline(*args: str) -> subprocess.CompletedProcess:
    """The committed command, run against the interpreter the tests run under.

    The script prefers ``backend/.venv/bin/python`` and honours ``PYTHON`` when
    that is not the environment in use — a git worktree has no venv of its own,
    and a test that silently fell back to a bare ``python3`` would be asserting on
    an import error rather than on the headline.
    """
    return subprocess.run(
        ["bash", str(HEADLINE_COMMAND), *args],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
        env={**os.environ, "PYTHON": sys.executable},
    )


def _committed(name: str) -> dict:
    return json.loads((REFERENCES / name).read_text())


def _section(page: str, heading: str) -> str:
    """One document section: the text under `heading`, up to the next one."""
    return page.split(heading, 1)[1].split("\n## ", 1)[0]


def _prose(path: Path) -> str:
    """A document's text with its typographic minus folded to the ASCII one.

    Prose in this repo sets a negative figure with U+2212, and a formatter prints
    it with a hyphen. Asserting on the glyph rather than the figure would make
    every one of these tests a test of punctuation.
    """
    return path.read_text().replace("\u2212", "-")


def _headline_cells() -> dict[str, dict[str, float | None]]:
    """The four pre-registered figures, read off the payload that produced them."""
    metric = _committed("backtest_primary_metric.json")
    return {
        body["market"]: {
            cell["label"]: cell["expectancy_r"] for cell in body["windows"]
        }
        for body in metric["markets"]
    }


def _verdict_markets() -> dict[str, dict]:
    return {body["market"]: body for body in _committed("backtest_verdict.json")["markets"]}


def test_the_authority_document_and_its_plain_companion_are_both_committed():
    """The convention findings §0 set: an authority document, and a plain-language
    companion beside it that assumes none of the vocabulary."""
    assert AUTHORITY_DOC.exists()
    assert PLAIN_DOC.exists()
    # Each names the other, or a reader who lands on one never learns of the other.
    assert PLAIN_DOC.name in _prose(AUTHORITY_DOC)
    assert AUTHORITY_DOC.name in _prose(PLAIN_DOC)


def test_the_machine_readable_results_are_committed_beside_both():
    """Every figure the write-up quotes has a payload behind it, and the document
    names the file rather than leaving the reader to guess which one."""
    page = _prose(AUTHORITY_DOC)
    for payload in (
        "backtest_primary_metric.json",
        "backtest_survivorship.json",
        "backtest_verdict.json",
        "backtest_sweep.json",
        "backtest_regime_posture.json",
        "backtest_candidate_outcomes.json",
        "backtest_score_ranking.json",
        "backtest_anchors.json",
        "backtest_full_run.json",
        "backtest_arms_US.json",
        "backtest_arms_IDX.json",
        "backtest_run_contract.json",
    ):
        assert (REFERENCES / payload).exists(), payload
        assert payload in page, payload


def test_the_headline_figures_in_both_documents_are_the_committed_ones():
    """The drift guard. A rerun that moves an expectancy and leaves the prose
    behind is the failure this test exists for — in both documents, because a
    plain-language companion quoting a stale number is no better than a stale
    authority."""
    cells = _headline_cells()
    authority = _prose(AUTHORITY_DOC)
    plain = _prose(PLAIN_DOC)
    for market, windows in cells.items():
        for expectancy in windows.values():
            assert expectancy is not None
            printed = f"{expectancy:+.3f}R"
            assert printed in authority, (market, printed)
            assert printed in plain, (market, printed)


def test_the_bias_bound_is_in_the_summary_and_not_in_a_footnote():
    """Phase 2's bound is larger than the effect the run is looking for, so a
    reader who stops after the summary must already have it. Both pessimistic
    figures appear above the summary section's end."""
    page = _prose(AUTHORITY_DOC)
    assert SUMMARY_HEADING in page
    summary = _section(page, SUMMARY_HEADING)
    for market, body in _verdict_markets().items():
        for cell in body["windows"]:
            assert f"{cell['pessimistic_r']:+.3f}R" in summary, (market, cell["label"])
    # And the size of the hole itself, per market, not just its consequence.
    for body in _verdict_markets().values():
        assert f"{body['hole_share'] * 100:.1f}%" in summary, body["market"]


def test_the_summary_carries_the_drag_the_hole_costs_the_headline():
    """`gap_r` is the drag on the mean; `hole_share` and the trades-per-covered
    ratio it implies are counts. They are different quantities and the first draft
    of the plain companion ran them together, quoting the count as an R amount. So
    the drag is asserted from the payload that computes it.
    """
    summary = _section(_prose(AUTHORITY_DOC), SUMMARY_HEADING)
    metric = _committed("backtest_primary_metric.json")
    us = next(b for b in metric["markets"] if b["market"] == "US")
    assert f"{us['bias_bound']['gap_r']:.3f}R" in summary
    # And the plain companion states the same drag rather than a second version.
    assert f"{us['bias_bound']['gap_r']:.3f}R" in _prose(PLAIN_DOC)


def test_both_markets_are_reported_separately_including_in_the_summary():
    """Findings §8: shapes travel between US and IDX and magnitudes do not, so a
    pooled figure describes neither market. The summary names both."""
    page = _prose(AUTHORITY_DOC)
    summary = _section(page, SUMMARY_HEADING)
    cells = _headline_cells()
    assert set(cells) == {"US", "IDX"}
    for market, windows in cells.items():
        assert market in summary
        for expectancy in windows.values():
            assert f"{expectancy:+.3f}R" in summary, (market, expectancy)


def test_the_verdict_is_stated_in_the_words_the_contract_fixed_in_advance():
    """The licence strings are the contract's own, written before the run. Quoting
    them verbatim is what stops the verdict being restated more warmly than it was
    decided."""
    page = _prose(AUTHORITY_DOC)
    # Collapsed, and with the blockquote markers dropped: prose wraps a quotation
    # across lines and marks each one, and the contract's words are the claim
    # under test rather than where the line breaks and the "> " fell.
    unwrapped = " ".join(
        " ".join(line.lstrip("> ") for line in page.splitlines()).split()
    )
    for market, body in _verdict_markets().items():
        assert body["verdict"] in page.lower(), market
        assert " ".join(body["licenses"].split()) in unwrapped, market


def test_the_licensed_change_is_named_before_any_constant_moves():
    """The ship verdict's own condition. IDX ships, so the write-up names the
    change it licenses — and no constant in the app moved to earn it."""
    page = _prose(AUTHORITY_DOC)
    assert "## The change this licenses" in page
    licensed = _section(page, "## The change this licenses")
    assert "IDX" in licensed
    # Named, and still unspent: the calibration rule is where it goes next.
    assert "findings §7" in licensed


def test_the_limits_are_stated_including_what_signal_level_cannot_say():
    """A limitation named in advance is a caveat; one discovered afterwards is a
    retraction. The four the plan fixed, plus the deferral in its own words."""
    for doc in (AUTHORITY_DOC, PLAIN_DOC):
        assert LIMITS_HEADING in _prose(doc), doc.name
    page = _prose(AUTHORITY_DOC)
    limits = _section(page, LIMITS_HEADING)
    for claim in (
        "capacity",
        "concurrency",
        "drawdown",
        "correlated clustering",
        "intraday",
    ):
        assert claim in limits, claim
    # The portfolio question is deferred rather than dismissed, in those words.
    assert "deferred rather than dismissed" in limits


def test_one_committed_command_reproduces_the_headline_figure():
    """A reader who has seen none of this runs one command and reads the four
    figures and their bounds off its output."""
    assert HEADLINE_COMMAND.exists()
    assert os.access(HEADLINE_COMMAND, os.X_OK), "the command must be runnable"
    printed = _run_headline().stdout
    for market, body in _verdict_markets().items():
        assert market in printed
        for cell in body["windows"]:
            assert f"{cell['expectancy_r']:+.3f}R" in printed, (market, cell["label"])
            assert f"{cell['pessimistic_r']:+.3f}R" in printed, (market, cell["label"])


def test_the_command_says_whether_it_recomputed_the_figure_or_read_it_back():
    """Two paths, and they are not the same claim. Reading a recorded headline off
    disk checks that the payload and the prose agree; recomputing it from the store
    checks the figure itself. A command that did the first and let a reader believe
    the second would be the whole write-up's credibility spent on a shortcut."""
    printed = _run_headline().stdout
    assert "recorded" in printed.lower()
    assert "--from-store" in printed, "the recomputing path is named in the output"
    # And the document tells the reader the same two things.
    assert HEADLINE_COMMAND.name in _prose(AUTHORITY_DOC)


def test_the_recomputing_path_cleans_up_after_itself():
    """`--from-store` works in a temp directory and removes it on the way out.

    Read off the source rather than by running it, because the recomputing path
    re-simulates fourteen years of two markets and takes minutes. The specific
    regression: `exec` on the last line replaces the shell image, so bash never
    runs the EXIT trap and every run leaves its temp directory behind. The trap
    is only as good as the absence of that `exec`, so both are asserted.
    """
    script = HEADLINE_COMMAND.read_text()
    assert "trap 'rm -rf \"$WORK\"' EXIT" in script
    assert "exec " not in script, "an exec after the trap would skip the cleanup"


def test_the_command_explains_itself_without_running_anything():
    """A reader who has seen none of this types --help first."""
    printed = subprocess.run(
        ["bash", str(HEADLINE_COMMAND), "--help"],
        capture_output=True, text=True, cwd=REPO_ROOT,
        env={**os.environ, "PYTHON": sys.executable},
    )
    assert printed.returncode == 0
    assert "--from-store" in printed.stdout


def test_a_missing_environment_is_named_rather_than_thrown():
    """The reader who runs this has cloned a repository, not installed a tool.

    Both paths import the backtest package, so both need duckdb even though the
    default one reads no bars. A `ModuleNotFoundError` traceback tells that reader
    nothing they can act on, so the command checks first and says what to install.
    """
    bare = subprocess.run(
        ["bash", str(HEADLINE_COMMAND)],
        capture_output=True, text=True, cwd=REPO_ROOT,
        # An interpreter that certainly cannot import the project's dependencies.
        env={**os.environ, "PYTHON": "/usr/bin/false"},
    )
    assert bare.returncode == 3
    assert "duckdb" in bare.stderr
    assert "requirements.txt" in bare.stderr
    assert "Traceback" not in bare.stderr


def test_the_write_up_moves_no_committed_constant():
    """Phase 7 writes. The ship verdict licenses a change and explicitly defers it,
    so the contract this run was measured under is byte-identical after it."""
    before = DEFAULT_CONTRACT_JSON.read_text()
    _run_headline()
    assert DEFAULT_CONTRACT_JSON.read_text() == before
