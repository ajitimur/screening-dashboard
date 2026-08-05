"""Seam 6f: the nightly regime capture, store-driven.

Two things the regime stage leaves behind on a published run: nothing that gates
(the candidate list, ranks and score are untouched), and one thing captured
forward — **breakout follow-through**, appended nightly and never displayed
(spec §4.9). This seam drives the capture through the store.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from screener.pipeline import capture_follow_through, run_market_universe
from screener.source import Instrument, Source
from screener.store import Store

WIB = ZoneInfo("Asia/Jakarta")
CAL = [date(2026, 7, 1) + timedelta(days=i) for i in range(30)]


def _row(session, *, close, volume, adj_close=None):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": adj_close if adj_close is not None else close,
        "Volume": volume,
    }


class FakeBarClient:
    def __init__(self, instruments, bars_by_symbol, info_by_symbol=None):
        self._instruments = instruments
        self._bars = bars_by_symbol
        self._info = info_by_symbol or {}

    def enumerate(self, market):
        return self._instruments[market]

    def fetch(self, symbol):
        return self._bars.get(symbol, [])

    def fetch_info(self, symbol):
        return self._info.get(symbol, {})


def test_capture_follow_through_appends_one_index_row():
    from screener.bars import Bar

    store = Store.memory()
    # A flat index that pops to a new high on the last session → a breakout.
    bars = [Bar(s, 100.0, 101.0, 99.0, 100.0, 100.0, 1000) for s in CAL[:-1]]
    bars.append(Bar(CAL[-1], 100.0, 102.0, 99.0, 101.0, 101.0, 1000))
    store.append_bars("IDX", "^JKSE", bars)

    broke = capture_follow_through(store, "IDX", CAL[-1])
    assert broke is True

    rows = store.follow_through("IDX")
    assert len(rows) == 1
    assert rows[0].session == CAL[-1]
    assert rows[0].broke_out is True
    assert rows[0].index_close == 101.0
    store.close()


def test_capture_is_a_noop_before_a_full_trailing_window():
    from screener.bars import Bar

    store = Store.memory()
    store.append_bars("IDX", "^JKSE", [Bar(s, 100.0, 101.0, 99.0, 100.0, 100.0, 1000) for s in CAL[:5]])
    assert capture_follow_through(store, "IDX", CAL[4]) is None
    assert store.follow_through("IDX") == []
    store.close()


def test_published_run_captures_follow_through(store: Store):
    session = CAL[-1]
    now = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
        Instrument(market="IDX", symbol="BBB", role="candidate", name="Beta Tbk"),
    ]
    # Index climbs to a fresh high on the last session; members are liquid.
    idx = [_row(s, close=1000.0 + i, volume=1_000_000) for i, s in enumerate(CAL)]
    aaa = [_row(s, close=2000.0, volume=1_000_000, adj_close=100.0 + i) for i, s in enumerate(CAL)]
    bbb = [_row(s, close=2000.0, volume=1_000_000, adj_close=100.0) for s in CAL]
    source = Source(
        FakeBarClient({"IDX": instruments}, {"^JKSE": idx, "AAA": aaa, "BBB": bbb}),
        rate_per_sec=1000, sleep=lambda s: None,
    )

    record = run_market_universe(store, source, "IDX", session, now=now)
    assert record.status == "published"

    rows = store.follow_through("IDX")
    assert [r.session for r in rows] == [session]
    assert rows[0].broke_out is True  # the index made a new high


def test_quarantined_run_captures_no_follow_through(store: Store):
    session = CAL[-1]
    now = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
        Instrument(market="IDX", symbol="BBB", role="candidate", name="Beta Tbk"),
    ]
    idx = [_row(s, close=1000.0 + i, volume=1_000_000) for i, s in enumerate(CAL)]
    # Only the index resolves — every candidate is silent, so the run quarantines.
    source = Source(
        FakeBarClient({"IDX": instruments}, {"^JKSE": idx}),
        rate_per_sec=1000, sleep=lambda s: None, max_attempts=1,
    )

    record = run_market_universe(store, source, "IDX", session, now=now)
    assert record.status == "quarantined"
    assert store.follow_through("IDX") == []  # a quarantined run leaves nothing
