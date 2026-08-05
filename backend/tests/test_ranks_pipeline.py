"""Seam 6d: the nightly rank stage, store-driven end to end.

``rebuild_ranks`` reads the session's published universe and each member's clean
bars off the store, computes the rank table, and appends it — so a published
per-market run leaves rank rows for **every universe member** (spec §4.3), and a
quarantined run leaves none (it wrote no universe to rank).
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from screener.pipeline import rebuild_ranks, run_market_universe
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
    def __init__(self, instruments, bars_by_symbol):
        self._instruments = instruments
        self._bars = bars_by_symbol

    def enumerate(self, market):
        return self._instruments[market]

    def fetch(self, symbol):
        return self._bars.get(symbol, [])


def test_run_market_universe_leaves_a_rank_row_per_member(store: Store):
    session = CAL[-1]
    now = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
        Instrument(market="IDX", symbol="BBB", role="candidate", name="Beta Tbk"),
    ]
    # Both liquid common stocks; AAA finishes strong, BBB flat over the last week.
    aaa = [_row(s, close=2000.0, volume=1_000_000, adj_close=100.0) for s in CAL[:-1]]
    aaa.append(_row(session, close=2000.0, volume=1_000_000, adj_close=130.0))
    bbb = [_row(s, close=2000.0, volume=1_000_000, adj_close=100.0) for s in CAL]
    source = Source(
        FakeBarClient({"IDX": instruments}, {"^JKSE": bbb, "AAA": aaa, "BBB": bbb}),
        rate_per_sec=1000, sleep=lambda s: None,
    )

    record = run_market_universe(store, source, "IDX", session, now=now)
    assert record.status == "published"

    ranks = store.ranks("IDX", session)
    ranked = {r.symbol for r in ranks}
    assert ranked == {"AAA", "BBB"}  # both members; the index is a reference
    # A 1w row exists for each member, carrying percentile and raw return.
    one_w = {r.symbol: r for r in ranks if r.lookback == "1w"}
    assert set(one_w) == {"AAA", "BBB"}
    assert one_w["AAA"].raw_return > one_w["BBB"].raw_return
    assert one_w["AAA"].percentile == 1.0  # the stronger of the two


def test_rebuild_ranks_reads_the_universe_and_returns_the_gate(store: Store):
    session = CAL[-1]
    # Seed a universe of two members and their bars directly.
    from screener.bars import Bar

    def bars(adj_last):
        series = [Bar(s, 0, 0, 0, 0, 100.0, 1000) for s in CAL[:-1]]
        series.append(Bar(session, 0, 0, 0, 0, adj_last, 1000))
        return series

    store.append_bars("IDX", "UP", bars(150.0))
    store.append_bars("IDX", "DOWN", bars(90.0))
    store.append_universe("IDX", session, ["DOWN", "UP"])

    rows = rebuild_ranks(store, "IDX", session)
    assert {r.symbol for r in rows} == {"UP", "DOWN"}
    # Persisted, and readable back.
    assert {r.symbol for r in store.ranks("IDX", session)} == {"UP", "DOWN"}
