"""The whole of v1, end to end: one nightly run composes the whole workbench.

This is the umbrella acceptance test for PRD #26. Every other test pins one
stage or one endpoint against a hand-seeded store; none proves the property the
umbrella issue actually asserts — that a *single* nightly run, driven only
through the faked source boundary, leaves a store the six read endpoints compose
into one coherent, same-dated workbench for both screens.

So this drives one real ``run_market_universe`` for US through a fake source
carrying a rising index and a leader sitting in a clean base, then reads that one
run back through all six endpoints (spec §7.5) and the digest file (spec §6),
asserting:

- the run **published** (not quarantined), and every surface is stamped the same
  session — the trader is never shown a fresh half-screen against a stale one
  (user story 1, 6);
- the **regime** banner reads FRIENDLY / full size off the rising index (§4.9);
- the **leader** is on the candidate list with a score and an industry, and is
  the top row of the board it led (§4.5, §5.2);
- its **chart** bundle carries the candles, the MA set, the facts block and the
  setup overlay with the eight-row breakdown, all from that one run (§5.1);
- the **sector** board renders all eleven sectors with the leader's sector
  populated (§4.4);
- the **digest** file was written for the session (§6).

The source boundary is the only fake; there is no network and no second
definition of any computation here — every figure is read through the app's own
paths, so a failure is a real integration gap, never a measurement artefact.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from screener.app import create_app
from screener.indicators import LOOKBACKS
from screener.pipeline import run_market_universe
from screener.source import Instrument, Source
from screener.store import Store

ET = ZoneInfo("America/New_York")
# A calendar of 105 consecutive dated sessions; the leader's base is fitted in
# bar space, and 3 calendar months back lands in its flat pre-move floor.
CAL = [date(2026, 1, 1) + timedelta(days=i) for i in range(105)]
TARGET = CAL[-1]
# Long after the last session's close + finality margin, so every bar is final.
NOW = datetime(2026, 8, 1, 18, 0, tzinfo=ET)


def _row(session, *, open_, high, low, close, volume):
    return {
        "Date": session, "Open": open_, "High": high, "Low": low,
        "Close": close, "Adj Close": close, "Volume": volume,
    }


def _leader_series():
    """A clean detectable base: 60 flat @50, a run-up 50→99, a 30-bar tight top
    ending today (the STRONG series ticket 37's detector test already detects)."""
    hlc = [(50.5, 49.5, 50.0)] * 60
    for i in range(1, 16):
        p = 50.0 + (99.0 - 50.0) * i / 15
        hlc.append((p + 0.5, p - 0.5, p))
    hlc += [(100.5, 99.5, 100.0)] * 30
    return [
        _row(CAL[i], open_=c, high=h, low=lo, close=c, volume=1_000_000)
        for i, (h, lo, c) in enumerate(hlc)
    ]


def _flat_series(close):
    """A liquid, common-stock member that never moves — in the universe and the
    rank denominators, but well below the decile the leader tops."""
    return [
        _row(s, open_=close, high=close + 1, low=close - 1, close=close, volume=1_000_000)
        for s in CAL
    ]


def _rising_index():
    """The market index, a clean uptrend — close above both rising MAs → FRIENDLY."""
    return [
        _row(s, open_=100.0 + i, high=101.0 + i, low=99.0 + i, close=100.0 + i, volume=1_000)
        for i, s in enumerate(CAL)
    ]


class FakeBarClient:
    def __init__(self, instruments, bars_by_symbol, info_by_symbol):
        self._instruments = instruments
        self._bars = bars_by_symbol
        self._info = info_by_symbol

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol, start=None):
        return self._bars.get(symbol, [])

    def fetch_info(self, symbol):
        return self._info.get(symbol, {})


@pytest.fixture
def workbench(tmp_path):
    """Run one full US nightly run through the fake source; yield (client, digests)."""
    store = Store.memory()
    instruments = [
        Instrument(market="US", symbol="^IXIC", role="reference"),
        Instrument(market="US", symbol="LEAD", role="candidate", name="Lead Inc. - Common Stock"),
        Instrument(market="US", symbol="FLATA", role="candidate", name="Flata Inc. - Common Stock"),
        Instrument(market="US", symbol="FLATB", role="candidate", name="Flatb Inc. - Common Stock"),
    ]
    bars = {
        "^IXIC": _rising_index(),
        "LEAD": _leader_series(),
        "FLATA": _flat_series(120.0),
        "FLATB": _flat_series(130.0),
    }
    info = {
        "LEAD": {"sector": "Technology", "industry": "Semiconductors"},
        "FLATA": {"sector": "Energy", "industry": "Oil & Gas"},
        "FLATB": {"sector": "Financials", "industry": "Banks"},
    }
    source = Source(FakeBarClient(instruments, bars, info), rate_per_sec=1000, sleep=lambda s: None)

    record = run_market_universe(store, source, "US", TARGET, now=NOW, digests_dir=tmp_path)
    assert record is not None and record.status == "published"

    client = TestClient(create_app(store=store))
    try:
        yield client, tmp_path
    finally:
        store.close()


def test_one_run_publishes_a_same_dated_workbench_across_all_six_endpoints(workbench):
    client, _ = workbench
    stamp = TARGET.isoformat()

    # runs — published for the target session, carrying tonight's universe size.
    runs = client.get("/api/runs/US").json()
    assert runs["latest"]["session"] == stamp
    assert runs["latest"]["status"] == "published"
    assert runs["universe_size"] == 3  # the three candidates; the index excluded

    # regime — FRIENDLY off the rising index, advising full size, same session.
    regime = client.get("/api/regime/US").json()
    assert regime["session"] == stamp
    assert regime["state"] == "FRIENDLY"
    assert regime["posture"] == "full size"

    # candidates — the leader is on the list with a score and its industry.
    candidates = client.get("/api/candidates/US").json()
    assert candidates["session"] == stamp
    assert candidates["ordered_by"] == "score"
    by_symbol = {c["symbol"]: c for c in candidates["candidates"]}
    # Only the leader — the flat fillers are members and ranked but neither
    # top-decile nor sitting in a base, so the gate and the detector really ran.
    assert set(by_symbol) == {"LEAD"}
    lead = by_symbol["LEAD"]
    assert 1.0 <= lead["score"] <= 5.0
    assert len(lead["breakdown"]) == 8
    assert lead["industry"] == "Semiconductors"

    # leaders — five boards, and the leader tops the board it led (3m: +100%).
    boards = client.get("/api/leaders/US").json()
    assert boards["session"] == stamp
    assert [b["lookback"] for b in boards["boards"]] == list(LOOKBACKS)
    three_m = next(b for b in boards["boards"] if b["lookback"] == "3m")
    assert three_m["rows"][0]["symbol"] == "LEAD"  # ran +100% off the floor

    # sectors — all eleven rendered, the leader's sector populated, same session.
    sectors = client.get("/api/sectors/US").json()
    assert sectors["session"] == stamp
    assert len(sectors["sectors"]) == 11
    technology = next(s for s in sectors["sectors"] if s["sector"] == "Technology")
    assert technology["members"] >= 1

    # chart — the whole evidence bundle for the leader, from that one run.
    chart = client.get("/api/chart/US/LEAD").json()
    assert chart["session"] == stamp
    assert len(chart["candles"]) == len(CAL)
    for line in ("sma10", "sma20", "sma50", "ema65"):
        assert len(chart[line]) > 0
    facts = chart["facts"]
    assert facts is not None
    assert facts["trigger"] == chart["setup"]["trigger"]  # one trigger, both blocks
    assert len(chart["setup"]["breakdown"]) == 8


def test_the_run_writes_the_digest_file_for_the_session(workbench):
    _, digests = workbench
    written = list(digests.glob("US/*.md"))
    assert [p.name for p in written] == [f"{TARGET.isoformat()}.md"]
