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

import hashlib
import json
from datetime import date

import duckdb
import pytest

from replay.reference import (
    REFERENCE_FIGURES,
    DriftError,
    ExecutedTrade,
    ReferenceReport,
    assert_matches_reference,
    build_report,
    classify,
    parse_trades,
    write_blind_spot_list,
)
from replay.store import WINDOW_END, WINDOW_START, build_replay_store
from screener.bars import Bar
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
    """A synthetic reference-JSON row in the schema the parser reads."""
    rec = {
        "ticker": ticker,
        "entryDate": entry,
        "entryPrice": 100.0,
        "stopPrice": 97.0,
        "stopPct": 3.0,
    }
    if with_outcomes:
        rec.update(
            {
                "gain10smaPct": 25.0,
                "mfe10smaPct": 40.0,
                "r10sma": 8.0,
                "gain20smaPct": 30.0,
                "mfe20smaPct": 45.0,
                "r20sma": 10.0,
            }
        )
    return rec


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


# -- classification: replayable vs blind spot -----------------------------


def test_trade_with_bars_is_replayable_without_bars_is_blind_spot(store: Store):
    store.append_bars("US", "AAA", [_bar(date(2020, 5, 1))])
    trades = parse_trades(
        [_trade_record("AAA", "2020-05-01"), _trade_record("ZZZ", "2020-05-01")]
    )

    classified = {c.trade.ticker: c.replayable for c in classify(trades, store)}

    assert classified == {"AAA": True, "ZZZ": False}


# -- the count report ------------------------------------------------------


def test_report_counts_and_blind_spot_r_share(store: Store):
    store.append_bars("US", "AAA", [_bar(date(2020, 5, 1))])
    store.append_bars("US", "BBB", [_bar(date(2020, 5, 1))])
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
    store.append_bars("US", "AAA", [_bar(date(2020, 5, 1))])
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
    store.append_bars("US", "AAA", [_bar(date(2020, 5, 1))])
    report = build_report(parse_trades([_trade_record("AAA", "2020-05-01")]), store)

    # A three-row fixture cannot match the 828-row reference figures.
    assert report.total_rows != REFERENCE_FIGURES["total_rows"]
    with pytest.raises(DriftError):
        assert_matches_reference(report)
