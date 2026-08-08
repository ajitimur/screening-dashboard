"""The nightly fetch set is shrunk *before* the resolve loop runs (issue #99).

The pull's cheapest win is to not ask for what it will throw away. Two slices of
the US enumeration can never be a universe member and are known so from the
enumeration alone:

- **Non-index references.** Only ``MARKET_INDEX[market]`` (``^IXIC``) has its
  bars read by any code path; the other ~5,581 ETFs are enumerated but never
  looked at. So only the index is fetched among reference-role instruments.
- **Instrument-type exclusions.** ``is_common_stock`` already drops warrants,
  rights, units and preferreds from the universe (§4.1) and ``measurable``
  already refuses to count them, but the filter ran *after* the fetch. Run it
  first and an excluded name is never fetched.

Neither changes what the universe *is*: the completeness gate's denominator is
identical, because both slices were already outside it. This is a placement
change that deletes ~7,500 requests a night, nothing more.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.pipeline import run_market_universe
from screener.source import Instrument, Source
from screener.store import Store

WIB = ZoneInfo("Asia/Jakarta")
CAL = [date(2026, 7, 1) + timedelta(days=i) for i in range(40)]


def _row(session, *, close, volume):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": close, "Volume": volume,
    }


class RecordingBarClient:
    """Fakes enumerate + fetch, and records every symbol ``fetch`` was asked for."""

    def __init__(self, instruments, bars_by_symbol):
        self._instruments = instruments
        self._bars = bars_by_symbol
        self.fetched: list[str] = []

    def enumerate(self, market):
        return self._instruments[market]

    def fetch(self, symbol):
        self.fetched.append(symbol)
        return self._bars.get(symbol, [])

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def test_only_the_index_and_common_stocks_are_ever_fetched(store, tmp_path):
    sessions = CAL[:25]
    now = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)
    instruments = [Instrument(market="US", symbol="^IXIC", role="reference")]
    # The other references — ETFs — are enumerated but never read (only the
    # index is), so they must never be fetched.
    instruments += [
        Instrument(market="US", symbol=f"ETF{i}", role="reference", name=f"Fund {i} ETF")
        for i in range(8)
    ]
    # Common-stock candidates that resolve.
    instruments += [
        Instrument(market="US", symbol=f"S{i}", role="candidate", name=f"Corp {i} - Common Stock")
        for i in range(5)
    ]
    # Instrument-type exclusions the provider serves no history for anyway.
    instruments += [
        Instrument(market="US", symbol=f"W{i}", role="candidate", name=f"Corp {i} Warrant")
        for i in range(4)
    ]
    bars = {"^IXIC": [_row(s, close=100.0, volume=1) for s in sessions]}
    bars.update({f"S{i}": [_row(s, close=2000.0, volume=1_000_000) for s in sessions] for i in range(5)})

    client = RecordingBarClient({"US": instruments}, bars)
    source = Source(client, rate_per_sec=1000, sleep=lambda s: None)

    record = run_market_universe(store, source, "US", date(2026, 8, 20), now=now, digests_dir=tmp_path)

    assert record.status == "published"
    # Exactly the index and the five common stocks were fetched — no ETF, no warrant.
    assert sorted(set(client.fetched)) == sorted(["^IXIC", "S0", "S1", "S2", "S3", "S4"])
    assert not any(s.startswith("ETF") for s in client.fetched)
    assert not any(s.startswith("W") for s in client.fetched)
