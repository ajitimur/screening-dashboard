"""Seam 7c: the nightly detection stage, store-driven end to end (spec §4.5).

``rebuild_detections`` reads the session's published universe, the rank table and
each member's clean bars off the store, applies the decile gate (top decile in
any of 1m/3m/6m), detects each gated member, and appends the detection rows.

Detection runs against **every universe member every night**, not only recent
movers: the gate decides eligibility, and a gated member that is not sitting in a
base is evaluated but simply emits nothing.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.bars import Bar
from screener.pipeline import rebuild_detections, run_market_universe
from screener.ranks import Rank
from screener.source import Instrument, Source
from screener.store import Store

WIB = ZoneInfo("Asia/Jakarta")
CAL = [date(2026, 1, 1) + timedelta(days=i) for i in range(200)]
SESSION = CAL[104]


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def _bars(hlc):
    return [
        Bar(CAL[i], close, high, low, close, close, 1_000_000)
        for i, (high, low, close) in enumerate(hlc)
    ]


def _base_series():
    """A clean base: flat, a run-up 50→99, then a 30-bar tight top ending today."""
    hlc = [(50.5, 49.5, 50.0)] * 60
    for i in range(1, 16):
        p = 50.0 + (99.0 - 50.0) * i / 15
        hlc.append((p + 0.5, p - 0.5, p))
    hlc += [(100.5, 99.5, 100.0)] * 30
    return hlc


def _no_cluster_series():
    """98 flat bars then 7 ragged bars — no trailing window is tight enough."""
    hlc = [(50.5, 49.5, 50.0)] * 98
    for h in (60, 55, 62, 54, 63, 56, 61):
        hlc.append((h + 0.5, h - 0.5, h))
    return hlc


def _seed(store: Store, market: str):
    """Three IDX members: STRONG (gated, has a base), WEAK (not gated, has a base),
    WILD (gated, no base). Bars, a published universe and a 3m rank row each."""
    store.append_bars(market, "STRONG", _bars(_base_series()))
    store.append_bars(market, "WEAK", _bars(_base_series()))
    store.append_bars(market, "WILD", _bars(_no_cluster_series()))
    store.append_universe(market, SESSION, ["STRONG", "WEAK", "WILD"])
    store.append_ranks(market, SESSION, [
        Rank("STRONG", "3m", 0.95, 1.0),   # top decile -> gated
        Rank("WEAK", "3m", 0.40, 0.1),     # below the decile -> not gated
        Rank("WILD", "3m", 0.99, 2.0),     # top decile -> gated
    ])


def test_rebuild_detections_emits_only_gated_members_with_a_base(store: Store):
    _seed(store, "IDX")
    rows = rebuild_detections(store, "IDX", SESSION)

    # STRONG is gated and sits in a base; WEAK has the same base but is not gated;
    # WILD is gated but has no tight cluster, so it is evaluated and emits nothing.
    assert {r.symbol for r in rows} == {"STRONG"}
    assert {r.symbol for r in store.detections("IDX", SESSION)} == {"STRONG"}
    d = next(r for r in rows if r.symbol == "STRONG")
    assert d.trigger == d.cluster_high      # the trigger is the cluster high
    assert d.line_end <= d.trigger          # the fitted line never sets it


def test_an_ungated_universe_detects_nothing(store: Store):
    # Every member sits in a base, but none is top decile in 1m/3m/6m — so the
    # decile gate, read off the rank table, admits nobody and nothing is emitted.
    store.append_bars("IDX", "AAA", _bars(_base_series()))
    store.append_bars("IDX", "BBB", _bars(_base_series()))
    store.append_universe("IDX", SESSION, ["AAA", "BBB"])
    store.append_ranks("IDX", SESSION, [
        Rank("AAA", "3m", 0.50, 0.1),
        Rank("BBB", "3m", 0.20, 0.0),
    ])
    assert rebuild_detections(store, "IDX", SESSION) == []
    assert store.detections("IDX", SESSION) == []


def test_run_market_universe_wires_in_detection(store: Store, tmp_path):
    # The 30-bar fake publishes a universe and ranks but has too little history to
    # detect, so the stage runs and writes an empty session rather than crashing —
    # proving detection is wired into the nightly run.
    session = CAL[29]
    now = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
        Instrument(market="IDX", symbol="BBB", role="candidate", name="Beta Tbk"),
    ]

    def row(session, close):
        return {"Date": session, "Open": close, "High": close + 1, "Low": close - 1,
                "Close": close, "Adj Close": close, "Volume": 1_000_000}

    series = [row(s, 2000.0) for s in CAL[:30]]

    class FakeBarClient:
        def enumerate(self, market):
            return instruments

        def fetch(self, symbol):
            return series

        def fetch_info(self, symbol):
            return {}

    source = Source(FakeBarClient(), rate_per_sec=1000, sleep=lambda s: None)
    record = run_market_universe(store, source, "IDX", session, now=now, digests_dir=tmp_path)
    assert record.status == "published"
    assert store.detections("IDX", session) == []  # wired, nothing to detect
