"""Retrying a session that quarantined (issue #103).

Two invariants met here and used to be in conflict. A **published** session is
never rewritten (spec §7.2) — that is what makes the derived streams unbiased. A
**quarantined** session published nothing: the pull fell below the completeness
floor, so no universe, no ranks, no detections were written and no reader ever
saw it (spec §3.4 rule 7). Yet its run row was enough to make the write-once
guard refuse a second attempt, so a fix that would let the pull succeed could not
be tried until the calendar rolled to a new final session — every retry paid the
full ~9-minute pull and then died on ``append_run``.

So a quarantined session is *superseded*: its own rows go, the retry recomputes
it, and the published-session guard is untouched.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.pipeline import run_market_universe
from screener.source import Instrument, Source
from screener.store import SessionExistsError, Store

NY = ZoneInfo("America/New_York")


def _weekdays_ending(last: date, n: int) -> list[date]:
    out: list[date] = []
    day = last
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return list(reversed(out))


SESSIONS = _weekdays_ending(date(2026, 8, 6), 30)
NOW = datetime(2026, 8, 6, 22, 10, tzinfo=NY)


def _row(session, close, volume):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": close, "Volume": volume,
    }


def _bars(sessions=SESSIONS, close=200.0, volume=1_000_000):
    return [_row(s, close, volume) for s in sessions]


class _FakeClient:
    def __init__(self, instruments, outcomes):
        self._instruments = instruments
        self._outcomes = outcomes

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol, start=None):
        # ``[]`` — the default — is silence that survives retries, which is the
        # shape of the throttled pull every quarantine here stands for.
        return self._outcomes.get(symbol, [])

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}


def _source(instruments, outcomes) -> Source:
    return Source(
        _FakeClient(instruments, outcomes),
        rate_per_sec=1000,
        max_attempts=1,
        sleep=lambda s: None,
    )


def _us_market(*, resolved: int, silent: int):
    """A US enumeration of ``resolved + silent`` common stocks, plus the index."""
    instruments = [Instrument(market="US", symbol="^IXIC", role="reference")]
    outcomes: dict[str, object] = {"^IXIC": _bars(close=100.0, volume=1)}
    for i in range(resolved):
        instruments.append(
            Instrument(market="US", symbol=f"OK{i}", role="candidate",
                       name=f"Corp {i} - Common Stock")
        )
        outcomes[f"OK{i}"] = _bars()
    for i in range(silent):
        instruments.append(
            Instrument(market="US", symbol=f"SIL{i}", role="candidate",
                       name=f"Quiet Corp {i} - Common Stock")
        )
        outcomes[f"SIL{i}"] = []
    return instruments, outcomes


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def _throttled():
    return _us_market(resolved=80, silent=20)  # 80/100 — under the floor


def _healthy():
    return _us_market(resolved=100, silent=0)


def test_a_quarantined_session_is_retried_and_published_the_same_day(store, tmp_path):
    target = SESSIONS[-1]
    first = run_market_universe(
        store, _source(*_throttled()), "US", target, now=NOW, digests_dir=tmp_path
    )
    assert first.status == "quarantined"

    # The same session, same day, with the pull that now completes.
    retry = run_market_universe(
        store, _source(*_healthy()), "US", target, now=NOW, digests_dir=tmp_path
    )

    assert retry is not None and retry.status == "published"
    assert store.last_published_run("US").session == target
    assert store.universe("US", target), "the retry computed the session's streams"
    assert store.ranks("US", target)
    # One row per session, always: the retry superseded the quarantine rather
    # than adding a second record for the same night.
    assert [r.session for r in store.runs("US")] == [target]


def test_the_retrys_failure_rows_replace_the_quarantines(store, tmp_path):
    target = SESSIONS[-1]
    run_market_universe(
        store, _source(*_throttled()), "US", target, now=NOW, digests_dir=tmp_path
    )
    assert len(store.run_failures("US", target)) == 20

    run_market_universe(
        store, _source(*_healthy()), "US", target, now=NOW, digests_dir=tmp_path
    )

    # The failures explained the attempt that quarantined; the session's record
    # now belongs to the pull that published it, which lost no symbols.
    assert store.run_failures("US", target) == []


def test_a_retry_that_quarantines_again_records_the_new_attempt(store, tmp_path):
    # The retry path cannot depend on the retry succeeding: a still-throttled
    # second attempt has to land as a quarantine, not a crash.
    target = SESSIONS[-1]
    run_market_universe(
        store, _source(*_throttled()), "US", target, now=NOW, digests_dir=tmp_path
    )
    instruments, outcomes = _us_market(resolved=60, silent=40)

    again = run_market_universe(
        store, _source(instruments, outcomes), "US", target,
        now=NOW, digests_dir=tmp_path,
    )

    assert again.status == "quarantined"
    assert (again.symbols_resolved, again.symbols_enumerated) == (60, 100)
    last = store.last_run("US")
    assert (last.session, last.status) == (target, "quarantined")
    assert last.symbols_resolved == 60, "the second attempt's numbers, not the first's"
    assert len(store.run_failures("US", target)) == 40


def test_a_published_session_is_never_re_run(store, tmp_path):
    # The invariant the retry must not cost: once a session published, no later
    # run recomputes it, however it is invoked.
    target = SESSIONS[-1]
    run_market_universe(
        store, _source(*_healthy()), "US", target, now=NOW, digests_dir=tmp_path
    )
    members = store.universe("US", target)

    again = run_market_universe(
        store, _source(*_throttled()), "US", target, now=NOW, digests_dir=tmp_path
    )

    assert again is None, "nothing was left to compute"
    assert store.universe("US", target) == members, "the published session is intact"
    with pytest.raises(SessionExistsError):
        store.discard_session("US", target)


def test_an_older_quarantined_night_is_filled_by_a_later_run(store, tmp_path):
    # A night that quarantined is a hole in the derived streams. A later healthy
    # run backfills every session past the last published one, and a quarantined
    # night in that range is exactly such a session — it is filled from the bars
    # now on disk rather than left permanently empty.
    hole, target = SESSIONS[-3], SESSIONS[-1]
    run_market_universe(
        store, _source(*_throttled()), "US", hole, now=NOW, digests_dir=tmp_path
    )
    assert store.universe("US", hole) == []

    run_market_universe(
        store, _source(*_healthy()), "US", target, now=NOW, digests_dir=tmp_path
    )

    assert store.universe("US", hole), "the quarantined night was recomputed"
    assert {r.status for r in store.runs("US")} == {"published"}
    assert store.last_published_run("US").session == target
