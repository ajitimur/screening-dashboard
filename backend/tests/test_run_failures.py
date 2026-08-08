"""What a run records about the symbols it failed to pull (issue #91).

A run record carries two integers — how many candidates were measurable and how
many resolved. That is enough to reach a verdict and not nearly enough to
explain one: a US run reporting 6,749 of 7,297 gives no way to tell whether 548
names went silent because the provider throttled the pull, or because the
listing file carries instruments it serves no history for. Those have opposite
fixes, and the per-symbol outcomes the run *did* observe were discarded the
moment it finished.

So every enumerated candidate that came back without bars is recorded, with the
source's stated outcome and whether it sat in the completeness gate's
denominator, for a quarantined session as much as a published one.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.pipeline import run_market_universe, summarize_pull
from screener.source import Instrument, PermanentlyUnavailableError, Source
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
    """Enumerates a fixed instrument list; ``outcomes`` decides each fetch.

    An outcome of ``"refused"`` raises :class:`PermanentlyUnavailableError` (the
    provider stating it serves no history), ``[]`` is silence that survives
    retries, and a list of rows is bars.
    """

    def __init__(self, instruments, outcomes):
        self._instruments = instruments
        self._outcomes = outcomes

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol):
        outcome = self._outcomes.get(symbol, [])
        if outcome == "refused":
            raise PermanentlyUnavailableError(f"{symbol}: period 'max' is invalid")
        return outcome

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}


def _source(instruments, outcomes) -> Source:
    return Source(
        _FakeClient(instruments, outcomes),
        rate_per_sec=1000,
        max_attempts=1,
        sleep=lambda s: None,
    )


def _us_market(*, silent_common: int, refused: int, warrants: int, resolved: int):
    """A US enumeration mixing every outcome the record has to tell apart."""
    instruments = [Instrument(market="US", symbol="^IXIC", role="reference")]
    outcomes: dict[str, object] = {"^IXIC": _bars(close=100.0, volume=1)}
    for i in range(resolved):
        instruments.append(
            Instrument(market="US", symbol=f"OK{i}", role="candidate",
                       name=f"Corp {i} - Common Stock")
        )
        outcomes[f"OK{i}"] = _bars()
    for i in range(silent_common):
        instruments.append(
            Instrument(market="US", symbol=f"SIL{i}", role="candidate",
                       name=f"Quiet Corp {i} - Common Stock")
        )
        outcomes[f"SIL{i}"] = []
    for i in range(refused):
        instruments.append(
            Instrument(market="US", symbol=f"REF{i}", role="candidate",
                       name=f"Refused Corp {i} - Common Stock")
        )
        outcomes[f"REF{i}"] = "refused"
    for i in range(warrants):
        instruments.append(
            Instrument(market="US", symbol=f"WAR{i}", role="candidate",
                       name=f"Corp {i} Warrant")
        )
        outcomes[f"WAR{i}"] = []
    return instruments, outcomes


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def test_a_quarantined_run_records_which_symbols_failed_and_why(store, tmp_path):
    # 80 of 95 measurable candidates resolve -> under the floor, quarantined.
    instruments, outcomes = _us_market(
        resolved=80, silent_common=15, refused=5, warrants=10
    )
    record = run_market_universe(
        store, _source(instruments, outcomes), "US", SESSIONS[-1],
        now=NOW, digests_dir=tmp_path,
    )

    assert record.status == "quarantined"
    assert (record.symbols_resolved, record.symbols_enumerated) == (80, 95)

    failures = store.run_failures("US", SESSIONS[-1])
    by_symbol = {f.symbol: f for f in failures}
    # Every candidate that produced no bars is here — and only those.
    assert len(failures) == 30
    assert not any(s.startswith("OK") for s in by_symbol)

    # The three populations the two integers cannot separate.
    assert by_symbol["SIL0"].status == "unresolved"
    assert by_symbol["SIL0"].counted, "silence in a common stock is what the gate is for"
    assert by_symbol["REF0"].status == "refused"
    assert not by_symbol["REF0"].counted, "a stated refusal sits outside the gate"
    assert by_symbol["WAR0"].status == "unresolved"
    assert not by_symbol["WAR0"].counted, "instrument-type exclusions sit outside it too"

    # The name survives with the symbol: a listing-quality problem is legible
    # from the name alone, which is the whole point of keeping it.
    assert by_symbol["WAR0"].name == "Corp 0 Warrant"


def test_references_are_not_in_the_failure_record(store, tmp_path):
    # The index is enumerated but never in the tradeable denominator (§3.4 rule
    # 7), so its silence is a different question than this record answers.
    instruments, outcomes = _us_market(
        resolved=80, silent_common=20, refused=0, warrants=0
    )
    outcomes["^IXIC"] = []  # the index goes silent too
    run_market_universe(
        store, _source(instruments, outcomes), "US", SESSIONS[-1],
        now=NOW, digests_dir=tmp_path,
    )

    assert "^IXIC" not in {f.symbol for f in store.run_failures("US", SESSIONS[-1])}


def test_a_published_run_records_its_failures_for_the_target_session_only(
    store, tmp_path
):
    # A clean common-stock pull that publishes: the warrants still went silent,
    # and that is still worth recording — a run explains itself either way.
    instruments, outcomes = _us_market(
        resolved=95, silent_common=0, refused=0, warrants=10
    )
    first, last = SESSIONS[-4], SESSIONS[-1]
    src = lambda: _source(instruments, outcomes)  # noqa: E731 - one fresh source per run
    run_market_universe(store, src(), "US", first, now=NOW, digests_dir=tmp_path)
    record = run_market_universe(store, src(), "US", last, now=NOW, digests_dir=tmp_path)

    assert record.status == "published"
    assert len(store.run_failures("US", last)) == 10

    # The backfilled nights between the two runs were computed from bars already
    # on disk — they had no pull of their own to fall short, so they carry no
    # failure rows rather than a copy of this pull's.
    backfilled = [s for s in SESSIONS if first < s < last]
    assert backfilled, "the fixture must actually backfill something"
    for session in backfilled:
        assert store.run_failures("US", session) == []


def test_a_clean_pull_records_nothing(store, tmp_path):
    instruments, outcomes = _us_market(
        resolved=95, silent_common=0, refused=0, warrants=0
    )
    run_market_universe(
        store, _source(instruments, outcomes), "US", SESSIONS[-1],
        now=NOW, digests_dir=tmp_path,
    )

    assert store.run_failures("US", SESSIONS[-1]) == []


# -- the log line the launchd files capture -----------------------------------


def test_the_summary_separates_throttling_from_listing_quality(store, tmp_path):
    instruments, outcomes = _us_market(
        resolved=80, silent_common=15, refused=5, warrants=10
    )
    record = run_market_universe(
        store, _source(instruments, outcomes), "US", SESSIONS[-1],
        now=NOW, digests_dir=tmp_path,
    )

    summary = summarize_pull(record, store.run_failures("US", SESSIONS[-1]))

    assert "quarantined run" in summary
    assert "80/95" in summary
    assert "15 silent and counted against the gate" in summary
    assert "5 refused by the provider" in summary
    assert "10 silent but excluded on instrument type" in summary
    assert "SIL0" in summary, "the log names symbols, not just counts"
    assert "run_failures" in summary, "and points at the full record"


def test_the_summary_of_a_clean_pull_is_one_line(store, tmp_path):
    instruments, outcomes = _us_market(
        resolved=95, silent_common=0, refused=0, warrants=0
    )
    record = run_market_universe(
        store, _source(instruments, outcomes), "US", SESSIONS[-1],
        now=NOW, digests_dir=tmp_path,
    )

    summary = summarize_pull(record, store.run_failures("US", SESSIONS[-1]))

    assert summary.splitlines() == [summary]
    assert "published run" in summary


def test_the_summary_caps_the_symbols_it_names(store, tmp_path):
    # 548 symbols in a log line buries the file; the table holds all of them.
    instruments, outcomes = _us_market(
        resolved=80, silent_common=40, refused=0, warrants=0
    )
    record = run_market_universe(
        store, _source(instruments, outcomes), "US", SESSIONS[-1],
        now=NOW, digests_dir=tmp_path,
    )

    summary = summarize_pull(record, store.run_failures("US", SESSIONS[-1]))

    assert "+20 more" in summary
