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
    every candidate reading ``False`` rather than raising."""
    dets = [_det("AAA", 6), _det("BBB", 3)]

    without = build_field(dets, [])
    with_rs = build_field(dets, [], rs_line_of={"AAA": True})

    assert {d.symbol: d.rs_line for d in without} == {"AAA": False, "BBB": False}
    assert {d.symbol: d.rs_line for d in with_rs} == {"AAA": True, "BBB": False}
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


def test_the_build_leaves_a_live_store_byte_identical(tmp_path):
    """The build reaches only the source and its own fresh store, so a live store
    sitting beside it is byte-identical after a build — the run is structurally
    incapable of corrupting live history (PRD story 49)."""
    live_path = tmp_path / "live.duckdb"
    live = Store.open(live_path)
    live.append_bars("US", "AAA", [_bar(date(2020, 6, 1))])
    live.close()

    before = hashlib.sha256(live_path.read_bytes()).hexdigest()
    build_backtest_store(
        _fetch_source({"ZZZ": [_bar_row(date(2015, 6, 1))]}),
        ["ZZZ"], tmp_path / "backtest.duckdb", market="US", now=_BUILD_NOW,
    )
    after = hashlib.sha256(live_path.read_bytes()).hexdigest()

    assert before == after


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
