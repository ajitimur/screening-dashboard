"""Rolling 1/30 full-depth slice, replacing the weekly full refetch (issue #101).

§3.6 mandates a periodic full-history refetch on top of the incremental append
(#100), to repair old-history corrections the ~20-session overlap window is too
narrow to catch. Doing it as a single weekly full-universe pull just moves the
5.5k-full-history throttle wall from every night to one night a week — the very
wall #98 exists to tear down.

Instead each night a **1/30 slice** of the fetch set is fetched at full depth
(``period="max"``) *instead of* incrementally. Membership is a deterministic hash
partition of the symbol against the session date — a pure function, no persisted
"last full fetch" state, exactly reproducible in tests and self-balancing across
~5,500 names. One fetch per symbol per night, always: a symbol in tonight's slice
is fetched at full depth *instead of* incrementally, never both, so the nightly
request count stays flat and ``status[symbol]`` stays single-valued.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from screener.pipeline import (
    FULL_DEPTH_CYCLE,
    OVERLAP_SESSIONS,
    _full_depth_today,
    run_market_universe,
)
from screener.source import Instrument, Source
from screener.store import Store

NY = ZoneInfo("America/New_York")


def _weekdays_ending(last: date, n: int) -> list[date]:
    out: list[date] = []
    day = last
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return list(reversed(out))


SESSIONS = _weekdays_ending(date(2026, 8, 6), 40)


def _row(session, close=200.0, volume=1_000_000):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": close, "Volume": volume,
    }


def _now_after(session: date) -> datetime:
    return datetime(session.year, session.month, session.day, 22, 10, tzinfo=NY)


class _RecordingClient:
    """A fake source client that records the ``start`` each fetch was called with."""

    def __init__(self, instruments, cold, *, incremental=None):
        self._instruments = instruments
        self._cold = cold
        self._incremental = incremental or {}
        self.calls: list[tuple[str, object]] = []

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol, start=None):
        self.calls.append((symbol, start))
        if start is None:
            return self._cold.get(symbol, [])
        return self._incremental.get(symbol, self._cold.get(symbol, []))

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}

    def starts_for(self, symbol):
        return [start for sym, start in self.calls if sym == symbol]


def _source(client) -> Source:
    return Source(client, rate_per_sec=1000, max_attempts=1, sleep=lambda s: None)


def _liquid_market(symbols):
    instruments = [Instrument(market="US", symbol="^IXIC", role="reference")]
    cold = {"^IXIC": [_row(s, close=100.0, volume=1) for s in SESSIONS]}
    for sym in symbols:
        instruments.append(
            Instrument(market="US", symbol=sym, role="candidate",
                       name=f"{sym} Inc - Common Stock")
        )
        cold[sym] = [_row(s) for s in SESSIONS]
    return instruments, cold


def _pick(in_slice: bool, session: date, taken: set) -> str:
    """A candidate symbol that is (or is not) in ``session``'s full-depth slice."""
    i = 0
    while True:
        sym = f"S{i}"
        if sym not in taken and _full_depth_today(sym, session) is in_slice:
            return sym
        i += 1


# -- the pure partition -------------------------------------------------------


def test_full_depth_membership_is_a_deterministic_function_of_symbol_and_date():
    # No persisted state: the same (symbol, session) always yields the same verdict.
    for sym in ("AAPL", "MSFT", "^IXIC", "BRK.A"):
        for session in (date(2026, 8, 6), date(2026, 9, 1), date(2027, 1, 2)):
            assert _full_depth_today(sym, session) is _full_depth_today(sym, session)


def test_every_symbol_gets_one_full_depth_fetch_across_the_cycle():
    # Across FULL_DEPTH_CYCLE consecutive nights, every symbol lands in the
    # full-depth slice on exactly one of them — no name is ever starved of a
    # periodic full refetch, and no name is refetched twice in a cycle.
    base = date(2026, 8, 6)
    nights = [base + timedelta(days=d) for d in range(FULL_DEPTH_CYCLE)]
    for sym in (f"SYM{i}" for i in range(200)):
        hits = sum(1 for night in nights if _full_depth_today(sym, night))
        assert hits == 1, f"{sym} got {hits} full-depth nights in one cycle"


def test_the_nightly_slice_is_about_one_thirtieth_of_the_fetch_set():
    # Self-balancing: on any single night, ~1/30 of the names are full-depth.
    symbols = [f"SYM{i}" for i in range(3000)]
    share = sum(1 for s in symbols if _full_depth_today(s, date(2026, 8, 6)))
    expected = len(symbols) / FULL_DEPTH_CYCLE
    assert 0.6 * expected < share < 1.4 * expected, share


# -- one fetch per symbol per night -------------------------------------------


def test_a_symbol_in_tonights_slice_is_fetched_full_depth_not_incremental(
    store: Store, tmp_path
):
    inslice = _pick(True, SESSIONS[-1], set())
    outslice = _pick(False, SESSIONS[-1], {inslice})
    instruments, cold = _liquid_market([inslice, outslice])

    # Night one seeds both symbols' bars.
    run_market_universe(
        store, _source(_RecordingClient(instruments, cold)), "US", SESSIONS[-2],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )
    last = store.last_session("US", outslice)
    calendar = store.sessions("US")

    # Night two: the in-slice name is refetched at full depth (start=None) even
    # though it has bars; the out-of-slice name is fetched incrementally.
    client = _RecordingClient(instruments, cold)
    run_market_universe(
        store, _source(client), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    assert client.starts_for(inslice) == [None]
    expected = calendar[calendar.index(last) - OVERLAP_SESSIONS]
    assert client.starts_for(outslice) == [expected]


def test_a_slice_symbol_is_fetched_exactly_once_never_both_depths(
    store: Store, tmp_path
):
    inslice = _pick(True, SESSIONS[-1], set())
    outslice = _pick(False, SESSIONS[-1], {inslice})
    instruments, cold = _liquid_market([inslice, outslice])
    run_market_universe(
        store, _source(_RecordingClient(instruments, cold)), "US", SESSIONS[-2],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    client = _RecordingClient(instruments, cold)
    record = run_market_universe(
        store, _source(client), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    # Single fetch per symbol regardless of depth -> flat request count and a
    # single-valued status per symbol, so the completeness gate needs no change.
    assert len(client.starts_for(inslice)) == 1
    assert len(client.starts_for(outslice)) == 1
    assert record.status == "published"
    assert record.symbols_resolved == 2
