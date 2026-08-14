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
from replay.chain import (
    BURN_IN_SESSIONS,
    GapError,
    replay_chain,
    synthesize_instruments,
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


def test_burn_in_default_matches_the_prd_window():
    assert BURN_IN_SESSIONS == 126
