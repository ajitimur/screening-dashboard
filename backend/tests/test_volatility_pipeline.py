"""Seam 6g: the nightly volatility capture, store-driven (spec §4.10).

Display is compute-on-read, as the regime's is. What the nightly path leaves
behind is the **forward record**: one write-once row per ``(market, session)``
carrying the raw 21-day vol, its percentile, the sample size that percentile
came from, the ARB policy era that bounded it, and the second leg — everything a
future vol-managed-sizing study needs and nothing a display convention would
freeze into it (the state word is deliberately not stored, ADR 0006).

It is captured from the first run because it cannot be rebuilt afterwards: a
future era change makes the right denominator for a past session genuinely
ambiguous. So this seam asserts the three things that keep the record honest —
one row per session, never rewritten, and preserved through an operator
recompute exactly as follow-through is.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.pipeline import capture_volatility, run_market_universe
from screener.source import Instrument, Source
from screener.store import SessionExistsError, Store

WIB = ZoneInfo("Asia/Jakarta")
# Long enough for a 21-day reading to exist at all, short of the 60-reading
# warm-up: the record starts on day one, the *display* waits for its denominator.
CAL = [date(2026, 3, 1) + timedelta(days=i) for i in range(40)]
SESSION = CAL[-1]
NOW = datetime(2026, 4, 20, 20, 0, tzinfo=WIB)  # past every session's close


def _row(session, *, close, volume, adj_close=None):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": adj_close if adj_close is not None else close,
        "Volume": volume,
    }


def _index_rows(calendar=CAL):
    """An index that actually moves, so its realized vol is not zero."""
    return [
        _row(s, close=1000.0 + (i % 3) * 5 + i, volume=1_000_000)
        for i, s in enumerate(calendar)
    ]


def _second_leg_rows(calendar=CAL):
    """USD/IDR: real bars that print **no volume at all** (§4.10)."""
    return [_row(s, close=16000.0 + (i % 5) * 20, volume=0) for i, s in enumerate(calendar)]


def _liquid(calendar=CAL, adj_start=100.0):
    return [
        _row(s, close=2000.0, volume=1_000_000, adj_close=adj_start + i)
        for i, s in enumerate(calendar)
    ]


class _MutableClient:
    """A fake client whose enumeration and bars can be swapped between runs."""

    def __init__(self, instruments, bars):
        self.instruments = instruments
        self.bars = bars

    def enumerate(self, market):
        return self.instruments

    def fetch(self, symbol, start=None):
        return self.bars.get(symbol, [])

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}


def _instruments():
    return [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="IDR=X", role="reference"),
        Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
    ]


def _client():
    return _MutableClient(
        _instruments(),
        {"^JKSE": _index_rows(), "IDR=X": _second_leg_rows(), "AAA": _liquid()},
    )


def _source(client, **kwargs):
    return Source(client, rate_per_sec=1000, sleep=lambda s: None, **kwargs)


def _seed_bars(store, calendar=CAL):
    from screener.bars import parse_bars

    store.append_bars("IDX", "^JKSE", parse_bars(_index_rows(calendar)))
    store.append_bars("IDX", "IDR=X", parse_bars(_second_leg_rows(calendar)))


def test_capture_appends_one_reading_per_market_session(store: Store):
    _seed_bars(store)

    captured = capture_volatility(store, "IDX", SESSION)
    assert captured is not None

    [row] = store.volatility_readings("IDX")
    assert row.session == SESSION
    assert row.index_vol > 0
    assert 0 <= row.percentile <= 100
    assert row.sample_size == len(CAL) - 21  # the readings behind the rank
    assert row.era_start == date(2025, 4, 8)  # the current ARB policy era
    assert row.second_leg > 0                # USD/IDR realized vol, not a level


def test_capture_is_a_noop_before_a_first_reading_exists(store: Store):
    # Ten bars cannot produce a 21-day reading, so there is nothing to record —
    # and nothing is recorded, rather than a zero standing in for a measurement.
    _seed_bars(store, CAL[:10])
    assert capture_volatility(store, "IDX", CAL[9]) is None
    assert store.volatility_readings("IDX") == []


def test_a_session_older_than_every_decree_is_not_ranked_at_all(store: Store):
    """An IDX session before the first recorded era has no denominator (ADR 0006).

    Its censoring regime is unknown, so ranking it would rank *across* decrees —
    the one thing within-era ranking exists to prevent. Undefined, not defaulted,
    and nothing written into the forward record either.
    """
    old = [date(2024, 1, 1) + timedelta(days=i) for i in range(40)]
    _seed_bars(store, old)

    assert capture_volatility(store, "IDX", old[-1]) is None
    assert store.volatility_readings("IDX") == []


def test_a_captured_session_is_never_rewritten(store: Store):
    _seed_bars(store)
    capture_volatility(store, "IDX", SESSION)

    with pytest.raises(SessionExistsError):
        capture_volatility(store, "IDX", SESSION)


def test_published_run_captures_the_reading(store: Store, tmp_path):
    record = run_market_universe(
        store, _source(_client()), "IDX", SESSION, now=NOW, digests_dir=tmp_path
    )
    assert record.status == "published"
    assert [r.session for r in store.volatility_readings("IDX")] == [SESSION]


def test_quarantined_run_captures_no_reading(store: Store):
    # Every candidate is silent, so the run falls below the completeness floor.
    client = _MutableClient(
        _instruments(), {"^JKSE": _index_rows(), "IDR=X": _second_leg_rows()}
    )
    record = run_market_universe(
        store, _source(client, max_attempts=1), "IDX", SESSION, now=NOW
    )
    assert record.status == "quarantined"
    assert store.volatility_readings("IDX") == []


def test_recompute_keeps_the_forward_volatility_record_write_once(tmp_path):
    """Operator recovery must never destroy the unbiased record (ADR 0006).

    The reading is a function of the index and the second leg, not of the
    candidate enumeration, so correcting the enumeration leaves it exactly as
    captured — the same guarantee follow-through carries beside it.
    """
    store = Store.memory()
    try:
        client = _client()
        run_market_universe(
            store, _source(client), "IDX", SESSION, now=NOW, digests_dir=tmp_path
        )
        before = store.volatility_readings("IDX")
        assert [r.session for r in before] == [SESSION]

        client.instruments.append(
            Instrument(market="IDX", symbol="BBB", role="candidate", name="Beta Tbk")
        )
        client.bars["BBB"] = _liquid()
        run_market_universe(
            store, _source(client), "IDX", SESSION, now=NOW,
            digests_dir=tmp_path, recompute=True,
        )

        assert store.universe("IDX", SESSION) == ["AAA", "BBB"], "the enumeration fix landed"
        assert store.volatility_readings("IDX") == before, (
            "the forward record is untouched by the recompute"
        )
    finally:
        store.close()
