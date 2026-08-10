"""The scheduled entry point: ``python -m screener.run <MARKET>`` (spec §7.3).

What launchd invokes and what run-on-open drives in the background. It gates on
:func:`run_is_due` — the last final session missing — and, when due, runs the
market's pipeline for that session. The source is injected so the gate and
session-selection logic are tested without the network.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from screener.run import main, recompute_once, run_once
from screener.store import Store
from screener.source import Instrument, Source

WIB = ZoneInfo("Asia/Jakarta")


def _weekdays_ending(last: date, n: int) -> list[date]:
    out: list[date] = []
    day = last
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return list(reversed(out))


class _FakeClient:
    def __init__(self, instruments, bars):
        self._instruments = instruments
        self._bars = bars

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol, start=None):
        return self._bars.get(symbol, [])

    def fetch_info(self, symbol):
        return {}


def _row(session, close, volume):
    return {
        "Date": session, "Open": close, "High": close, "Low": close,
        "Close": close, "Adj Close": close, "Volume": volume,
    }


def _source() -> Source:
    # One liquid candidate over 25 sessions ending 2026-08-05, so a real universe
    # forms — the gate and session selection are what these tests assert.
    sessions = _weekdays_ending(date(2026, 8, 5), 25)
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="LIQ", role="candidate", name="Liquid Tbk"),
    ]
    bars = {
        "^JKSE": [_row(s, 100.0, 1) for s in sessions],
        "LIQ": [_row(s, 2000.0, 1_000_000) for s in sessions],  # 2B/day > 1B floor
    }
    return Source(_FakeClient(instruments, bars), rate_per_sec=1000, sleep=lambda s: None)


def test_run_once_runs_the_due_session(tmp_path):
    store = Store.memory()
    try:
        now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)  # past IDX close: 08-05 final
        record = run_once(
            store, _source(), "IDX", now=now, digests_dir=tmp_path
        )
        assert record is not None
        assert record.session == date(2026, 8, 5)  # the last final session
    finally:
        store.close()


def test_run_once_retries_a_quarantined_last_final_session(tmp_path):
    # The last final session has a run record, so nothing is *missing* — but it
    # quarantined and published nothing, so the fix that lets the pull succeed
    # has to get its retry today rather than waiting for the calendar to roll
    # (issue #103). Before this, the retry paid the whole pull and then died on
    # the write-once guard.
    store = Store.memory()
    try:
        from screener.pipeline import run_market

        enumerated = [f"S{i}" for i in range(100)]
        run_market(
            store, "IDX", date(2026, 8, 5),
            enumerated=enumerated, resolved=enumerated[:50],  # under the floor
            now=datetime(2026, 8, 5, 19, 30),
        )
        assert store.last_run("IDX").status == "quarantined"

        now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)
        record = run_once(store, _source(), "IDX", now=now, digests_dir=tmp_path)

        assert record is not None
        assert (record.session, record.status) == (date(2026, 8, 5), "published")
    finally:
        store.close()


def test_run_once_is_a_noop_when_not_due(tmp_path):
    store = Store.memory()
    try:
        # Publish the last final session already, so nothing is due.
        from screener.pipeline import run_market

        run_market(
            store, "IDX", date(2026, 8, 5),
            enumerated=["AAA"], resolved=["AAA"],
            now=datetime(2026, 8, 5, 19, 30),
        )
        now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)
        record = run_once(
            store, _source(), "IDX", now=now, digests_dir=tmp_path
        )
        assert record is None  # already current — no run
    finally:
        store.close()


def _wide_source() -> Source:
    """``_source`` plus a second liquid candidate — a *fixed* enumeration."""
    sessions = _weekdays_ending(date(2026, 8, 5), 25)
    instruments = [
        Instrument(market="IDX", symbol="^JKSE", role="reference"),
        Instrument(market="IDX", symbol="LIQ", role="candidate", name="Liquid Tbk"),
        Instrument(market="IDX", symbol="LIQ2", role="candidate", name="Liquid Two Tbk"),
    ]
    bars = {
        "^JKSE": [_row(s, 100.0, 1) for s in sessions],
        "LIQ": [_row(s, 2000.0, 1_000_000) for s in sessions],
        "LIQ2": [_row(s, 2000.0, 1_000_000) for s in sessions],
    }
    return Source(_FakeClient(instruments, bars), rate_per_sec=1000, sleep=lambda s: None)


def test_recompute_once_replaces_a_published_session_that_is_not_due(tmp_path):
    # The #111 gap: the last final session already published, so run_once is a
    # no-op (nothing is due) — yet a fixed enumeration must still be able to
    # correct it. recompute_once bypasses the due-gate and replaces the universe.
    store = Store.memory()
    try:
        now = datetime(2026, 8, 5, 20, 0, tzinfo=WIB)
        run_once(store, _source(), "IDX", now=now, digests_dir=tmp_path)
        assert store.universe("IDX", date(2026, 8, 5)) == ["LIQ"]
        # run_once now sees nothing due — the exact dead end #111 describes.
        assert run_once(store, _wide_source(), "IDX", now=now, digests_dir=tmp_path) is None

        record = recompute_once(
            store, _wide_source(), "IDX", date(2026, 8, 5), now=now, digests_dir=tmp_path
        )

        assert record is not None and record.status == "published"
        assert store.universe("IDX", date(2026, 8, 5)) == ["LIQ", "LIQ2"]
    finally:
        store.close()


def test_main_rejects_a_malformed_recompute_date(capsys):
    # A mistyped session is caught before any pull is attempted, so a typo never
    # opens the live store or spends the network.
    assert main(["IDX", "--recompute", "not-a-date"]) == 2
    assert "expected YYYY-MM-DD" in capsys.readouterr().err


def test_main_rejects_an_unknown_market(capsys):
    assert main(["MARS"]) == 2
