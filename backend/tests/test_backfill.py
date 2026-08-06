"""Backfill and as-of stamping (spec §7.2 / §7.3, ticket 44).

A week away must leave no hole in the accumulating streams. The run computes
**every session** between the last computed one and the latest final session, so
stopping the job for several nights and restarting fills every derivable stream
(universe, ranks, detections, scores) with no gap. The split is one line:
derivable-from-bars is backfilled; as-of-only captures (labels) are stamped with
the run date and never backfilled.

Backfill fills only **absent** sessions — a derived row already written is never
rewritten (spec §7.2): the rows are a point-in-time record of what was knowable
that night, and rewriting them after a rescale would inject look-ahead. The
source is injected so the whole loop is exercised without the network.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.pipeline import run_market_universe
from screener.source import Instrument, Source
from screener.store import Store

WIB = ZoneInfo("Asia/Jakarta")


def _weekdays_ending(last: date, n: int) -> list[date]:
    out: list[date] = []
    day = last
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return list(reversed(out))


SESSIONS = _weekdays_ending(date(2026, 8, 5), 130)
# ``now`` is comfortably past every session's close, so clean_bars keeps them all.
NOW = datetime(2026, 8, 10, 20, 0, tzinfo=WIB)


def _row(session, close, volume):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": close, "Volume": volume,
    }


class _FakeClient:
    def __init__(self, instruments, bars):
        self._instruments = instruments
        self._bars = bars

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol):
        return self._bars.get(symbol, [])

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}


def _source(volume_by_session=None) -> Source:
    """One liquid IDX candidate over the whole calendar, plus the index.

    ``volume_by_session`` optionally overrides LIQ's per-session volume so a
    name can be below the liquidity floor early and above it late — the as-of
    slicing test hangs on that.
    """
    def vol(s):
        return volume_by_session(s) if volume_by_session else 1_000_000

    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="LIQ", role="candidate", name="Liquid Tbk"),
    ]
    bars = {
        "^JKSE": [_row(s, 100.0, 1) for s in SESSIONS],
        "LIQ": [_row(s, 2000.0, vol(s)) for s in SESSIONS],
    }
    return Source(_FakeClient(instruments, bars), rate_per_sec=1000, sleep=lambda s: None)


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def test_restart_backfills_every_derivable_stream_with_no_gap(store, tmp_path):
    # Run once at an early target, then stop for five sessions and restart at the
    # latest — acceptance A5. The intervening nights must each carry a published
    # run and a rank table, not a hole.
    first, last = SESSIONS[-6], SESSIONS[-1]
    run_market_universe(store, _source(), "IDX", first, now=NOW, digests_dir=tmp_path)
    run_market_universe(store, _source(), "IDX", last, now=NOW, digests_dir=tmp_path)

    gap = [s for s in SESSIONS if first < s <= last]
    run_sessions = {r.session for r in store.runs("IDX")}
    for s in gap:
        assert s in run_sessions, f"no run for {s}"
        assert store.ranks("IDX", s), f"no ranks for {s}"
    assert store.latest_run("IDX").session == last


def test_backfill_only_fills_absent_sessions_and_never_rewrites(store, tmp_path):
    # A second run at the same target is a no-op: every session is already
    # recorded, so nothing is recomputed and no derived row is rewritten (the
    # store's write-once guard would raise if it tried). Backfill fills only
    # absent sessions (spec §7.2).
    first, last = SESSIONS[-4], SESSIONS[-1]
    run_market_universe(store, _source(), "IDX", first, now=NOW, digests_dir=tmp_path)
    run_market_universe(store, _source(), "IDX", last, now=NOW, digests_dir=tmp_path)

    before = {r.session for r in store.runs("IDX")}
    ranks_before = store.ranks("IDX", last)

    # Re-run the exact target: nothing is absent, so it returns None and touches
    # nothing.
    assert (
        run_market_universe(store, _source(), "IDX", last, now=NOW, digests_dir=tmp_path)
        is None
    )
    assert {r.session for r in store.runs("IDX")} == before
    assert store.ranks("IDX", last) == ranks_before


def test_labels_are_stamped_as_of_the_run_never_backfilled(store, tmp_path):
    # Derivable streams backfill; the label cache does not. After a five-session
    # gap is filled, every label carries the single run date as its as-of — no
    # per-session stamps for the missed nights, so a gap there stays visible and
    # honest (spec §7.3).
    first, last = SESSIONS[-6], SESSIONS[-1]
    run_market_universe(store, _source(), "IDX", first, now=NOW, digests_dir=tmp_path)
    run_market_universe(store, _source(), "IDX", last, now=NOW, digests_dir=tmp_path)

    as_ofs = {label.as_of for label in store.labels("IDX").values()}
    assert as_ofs == {last}  # stamped once at the target, not once per night


def _as_of_source(threshold: date) -> Source:
    """ANCHOR is liquid throughout (so no night is empty); LIQ only clears the
    floor on and after ``threshold``."""
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="ANCHOR", role="candidate", name="Anchor Tbk"),
        Instrument(market="IDX", symbol="LIQ", role="candidate", name="Liquid Tbk"),
    ]
    bars = {
        "^JKSE": [_row(s, 100.0, 1) for s in SESSIONS],
        "ANCHOR": [_row(s, 2000.0, 1_000_000) for s in SESSIONS],
        "LIQ": [_row(s, 2000.0, 1_000_000 if s >= threshold else 100) for s in SESSIONS],
    }
    return Source(_FakeClient(instruments, bars), rate_per_sec=1000, sleep=lambda s: None)


def test_backfilled_universe_is_resolved_as_of_that_session(store, tmp_path):
    # A name that only clears the liquidity floor late must NOT be a universe
    # member of an earlier backfilled session, even though its later (liquid)
    # bars are already ingested. Backfill resolves each night from what was
    # knowable then, not from today's bars (spec §7.3).
    # Liquid for the last 11 sessions, so its median-20 dollar volume clears the
    # floor only near the end of the calendar.
    src = _as_of_source(threshold=SESSIONS[-11])
    run_market_universe(store, src, "IDX", SESSIONS[-6], now=NOW, digests_dir=tmp_path)
    run_market_universe(store, src, "IDX", SESSIONS[-1], now=NOW, digests_dir=tmp_path)

    # An early backfilled night sees only LIQ's illiquid bars → not a member.
    assert "LIQ" not in store.universe("IDX", SESSIONS[-5])
    # The latest night sees the liquid bars → LIQ is a member.
    assert "LIQ" in store.universe("IDX", SESSIONS[-1])
