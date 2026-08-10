"""The tail sweep: silence re-asked at the end of the pull, after a rest (#104).

A US pull resolves ~5,000 symbols nearly perfectly and then falls off a cliff in
its final stretch — 310 of 339 silent names arrive in the last 500 symbols, one
contiguous alphabetical block, every one of which resolves in full when asked
again a few minutes later. The silence is the pull running out of provider
goodwill near the ten-minute mark, not the listings; but it lands in the
completeness gate's numerator all the same, and quarantines every run.

Per-symbol backoff cannot fix that: four attempts spread over seven seconds are
all inside the same exhausted window. What the evidence says works is *rest* —
so a symbol that burns its retry budget is held back rather than written off, and
re-asked at the end of the run, gently, after the provider has had a pause.

These tests drive the source boundary with a fake client and an injected clock,
so nothing here touches the network and nothing sleeps in real time.
"""

import threading
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.pipeline import run_market_universe, summarize_pull
from screener.source import (
    SWEEP_PAUSES,
    Instrument,
    PermanentlyUnavailableError,
    RateLimitedError,
    Source,
    sweep_silence,
)
from screener.store import Store

NY = ZoneInfo("America/New_York")
NOW = datetime(2026, 8, 7, 22, 56, tzinfo=NY)

# A rest is what refills the provider's goodwill; a backoff sleep is not. The
# fakes below tell them apart by length, the same way the real difference shows
# up — backoff is seconds, a sweep's rest is minutes.
REST = min(SWEEP_PAUSES)


class FakeClock:
    """A monotonic clock whose ``sleep`` advances virtual time and records it."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        with self._lock:
            return self.t

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.slept.append(seconds)
            self.t += seconds

    def rests(self) -> list[float]:
        """The sleeps long enough to be a rest rather than a backoff wait."""
        return [s for s in self.slept if s >= REST]


class SequenceClient:
    """``responses`` maps a symbol to successive fetch outcomes (the last one
    repeats): ``[]`` is silence, ``"429"`` raises, ``"refused"`` raises, a list
    of rows is bars."""

    def __init__(self, responses=None) -> None:
        self._responses = responses or {}
        self.fetch_calls: list[str] = []
        self._lock = threading.Lock()

    def enumerate(self, market):  # pragma: no cover - not exercised here
        raise NotImplementedError

    def fetch(self, symbol, start=None):
        with self._lock:
            self.fetch_calls.append(symbol)
            seen = self.fetch_calls.count(symbol) - 1
        outcomes = self._responses.get(symbol, [[]])
        outcome = outcomes[min(seen, len(outcomes) - 1)]
        if outcome == "429":
            raise RateLimitedError(symbol)
        if outcome == "refused":
            raise PermanentlyUnavailableError(f"{symbol}: period 'max' is invalid")
        return outcome


def make_source(client, **kw):
    clock = FakeClock()
    source = Source(
        client,
        rate_per_sec=1000,
        max_attempts=4,
        backoff_base=1.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        **kw,
    )
    return source, clock


# -- the sweep itself ---------------------------------------------------------


def test_silence_that_survived_its_retries_resolves_after_a_rest():
    # The exact shape of the tail: the pull's four attempts all fell inside the
    # exhausted window and it handed the symbol here as silence; one rest later
    # the same request answers in full.
    client = SequenceClient({"TEVA": [[{"row": "TEVA"}]]})
    source, clock = make_source(client)

    results = list(sweep_silence(source, ["TEVA"], workers=1))

    assert [(r.symbol, r.status) for r in results] == [("TEVA", "resolved")]
    assert clock.rests() == [SWEEP_PAUSES[0]], "the sweep asked again without resting"
    assert client.fetch_calls == ["TEVA"], "a recovered symbol was asked twice"


def test_the_sweep_rests_before_it_asks_not_after():
    order: list[str] = []
    client = SequenceClient({"TEVA": [[{"row": "TEVA"}]]})
    clock = FakeClock()

    def sleep(seconds):
        order.append("rest" if seconds >= REST else "backoff")
        clock.sleep(seconds)

    source = Source(
        client, rate_per_sec=1000, max_attempts=4, monotonic=clock.monotonic, sleep=sleep
    )

    list(sweep_silence(source, ["TEVA"], workers=1))

    assert order and order[0] == "rest"
    assert client.fetch_calls == ["TEVA"]


def test_a_symbol_silent_through_every_rest_stays_unresolved():
    # Rest is not a cure for a dead listing. The sweeps are bounded, and what
    # comes out the far end is the same unresolved-not-absent verdict (§3.4
    # rule 5) — reported once, after the last rest, not after each one.
    client = SequenceClient({"DEAD": [[]]})
    source, clock = make_source(client)

    results = list(sweep_silence(source, ["DEAD"], workers=1))

    assert [(r.symbol, r.status) for r in results] == [("DEAD", "unresolved")]
    assert clock.rests() == list(SWEEP_PAUSES), "the sweep budget is fixed"
    # One full retry budget per sweep, and no sweep past the last pause.
    assert len(client.fetch_calls) == 4 * len(SWEEP_PAUSES)


def test_a_symbol_that_recovers_is_not_asked_again():
    client = SequenceClient({"BACK": [[{"row": "BACK"}]], "GONE": [[]]})
    source, _ = make_source(client)

    list(sweep_silence(source, ["BACK", "GONE"], workers=1))

    # BACK resolved on the first sweep; only GONE is carried into the second.
    assert client.fetch_calls.count("BACK") == 1
    assert client.fetch_calls.count("GONE") == 4 * len(SWEEP_PAUSES)


def test_a_stated_refusal_ends_the_sweep_for_that_symbol():
    # A refusal is an answer, not silence: resting changes nothing about it, so
    # it is yielded once and never carried to the next sweep (spec §3.2).
    client = SequenceClient({"UNIT": ["refused"]})
    source, clock = make_source(client)

    results = list(sweep_silence(source, ["UNIT"], workers=1))

    assert [r.status for r in results] == ["refused"]
    assert client.fetch_calls == ["UNIT"]
    assert clock.rests() == [SWEEP_PAUSES[0]]


def test_nothing_silent_means_no_rest_at_all():
    client = SequenceClient()
    source, clock = make_source(client)

    assert list(sweep_silence(source, [], workers=1)) == []
    assert clock.rests() == []
    assert client.fetch_calls == []


def test_the_sweep_announces_each_rest_before_it_takes_it():
    client = SequenceClient({"DEAD": [[]], "ALSO": [[]]})
    source, _ = make_source(client)
    rests: list[tuple[float, int]] = []

    list(sweep_silence(source, ["DEAD", "ALSO"], workers=1, on_rest=lambda p, n: rests.append((p, n))))

    assert rests == [(SWEEP_PAUSES[0], 2), (SWEEP_PAUSES[1], 2)]


def test_the_sweep_asks_for_each_symbols_own_window():
    # A sweep is the same fetch as the pull that failed, retried — including the
    # incremental window (spec §3.6), so a recovered symbol appends where it
    # left off rather than re-downloading ten years.
    starts: dict[str, date | None] = {}

    class RecordingClient(SequenceClient):
        def fetch(self, symbol, start=None):
            starts[symbol] = start
            return super().fetch(symbol, start)

    client = RecordingClient({"AAA": [[{"row": "AAA"}]]})
    source, _ = make_source(client)

    list(sweep_silence(source, ["AAA"], workers=1, start_for={"AAA": date(2026, 7, 1)}.get))

    assert starts == {"AAA": date(2026, 7, 1)}


def test_a_resolution_says_whether_the_silence_was_throttling():
    # 429s and empty answers are indistinguishable to the *policy* — both are
    # silence, both retried, both unresolved-not-absent — but not to a person
    # diagnosing the next quarantine, which is the whole reason this issue
    # needed a write-up.
    client = SequenceClient({"BUSY": ["429"], "EMPTY": [[]]})
    source, _ = make_source(client)

    assert source.resolve("BUSY").throttled
    assert not source.resolve("EMPTY").throttled


def test_the_sweeps_verdict_supersedes_the_pulls():
    # The record is meant to say what the silence *was* after everything the run
    # could do about it. A name the pull saw answer empty, and that the provider
    # then throttled through both rests, is a pacing problem — recording the
    # pull's first impression would point at the listing instead, which is the
    # opposite remedy.
    client = SequenceClient({"FLIP": [[], "429"]})
    source, _ = make_source(client)

    results = list(sweep_silence(source, ["FLIP"], workers=1))

    assert [r.status for r in results] == ["unresolved"]
    assert results[0].throttled


def test_a_resolved_symbol_is_never_marked_throttled():
    # Even one that was throttled on the way: it answered, so the flag would say
    # nothing about a failure the run needs explained.
    client = SequenceClient({"SLOW": ["429", [{"row": "SLOW"}]]})
    source, _ = make_source(client)

    result = source.resolve("SLOW")

    assert result.status == "resolved"
    assert not result.throttled


# -- the run: a throttled tail publishes instead of quarantining --------------


def _weekdays_ending(last: date, n: int) -> list[date]:
    out: list[date] = []
    day = last
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day -= timedelta(days=1)
    return list(reversed(out))


SESSIONS = _weekdays_ending(date(2026, 8, 7), 30)


def _bars(close=200.0, volume=1_000_000):
    return [
        {"Date": s, "Open": close, "High": close + 1, "Low": close - 1,
         "Close": close, "Adj Close": close, "Volume": volume}
        for s in SESSIONS
    ]


class BudgetClient:
    """A provider with a *sustained* budget rather than a per-second cap (#104).

    It serves ``budget`` requests and then throttles everything until the caller
    rests — which is the hypothesis the tail's shape points at, and the one thing
    a per-symbol backoff of a few seconds cannot wait out. ``outcomes`` overrides
    individual symbols: ``"429"`` is a name no rest ever helps, ``[]`` is
    genuine silence.
    """

    def __init__(self, instruments, clock, *, budget, outcomes=None) -> None:
        self._instruments = instruments
        self._clock = clock
        self._budget = budget
        self._outcomes = outcomes or {}
        self._spent = 0
        self._rests_seen = 0
        self.throttled: set[str] = set()

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol, start=None):
        rests = len(self._clock.rests())
        if rests > self._rests_seen:  # the provider forgives after a pause
            self._rests_seen, self._spent = rests, 0
        if symbol in self._outcomes:
            outcome = self._outcomes[symbol]
            if outcome == "429":
                raise RateLimitedError(symbol)
            return outcome
        if self._spent >= self._budget:
            self.throttled.add(symbol)
            raise RateLimitedError(symbol)
        self._spent += 1
        return _bars()

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}


def _us_instruments(n):
    return [
        Instrument(market="US", symbol="^IXIC", role="reference"),
        *(
            Instrument(market="US", symbol=f"S{i:03d}", role="candidate",
                       name=f"Corp {i} - Common Stock")
            for i in range(n)
        ),
    ]


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def test_a_tail_lost_to_a_sustained_limit_publishes_after_the_sweep(store, tmp_path):
    # The issue, reproduced: the pull resolves most of the market and is then
    # throttled through its last stretch, 94% against a 0.99 floor. Every one of
    # those names is fine — they resolve once the provider has rested — so the
    # run publishes rather than quarantining on the pull's own exhaustion.
    clock = FakeClock()
    instruments = _us_instruments(100)
    client = BudgetClient(instruments, clock, budget=81)  # 80 names + the index
    source = Source(client, rate_per_sec=1000, monotonic=clock.monotonic, sleep=clock.sleep)

    record = run_market_universe(
        store, source, "US", SESSIONS[-1], now=NOW, digests_dir=tmp_path,
        workers=1, progress=lambda line: None,
    )

    assert client.throttled, "the fixture must actually throttle the tail"
    assert record.status == "published"
    assert (record.symbols_resolved, record.symbols_enumerated) == (100, 100)
    assert store.run_failures("US", SESSIONS[-1]) == []


def test_the_run_says_it_is_resting_rather_than_going_quiet(store, tmp_path):
    # A pull that stops for five minutes with nothing on stdout is exactly the
    # wedged-or-working ambiguity the heartbeat exists to break (issue #96).
    clock = FakeClock()
    instruments = _us_instruments(100)
    client = BudgetClient(instruments, clock, budget=81)
    source = Source(client, rate_per_sec=1000, monotonic=clock.monotonic, sleep=clock.sleep)
    lines: list[str] = []

    run_market_universe(
        store, source, "US", SESSIONS[-1], now=NOW, digests_dir=tmp_path,
        workers=1, progress=lines.append,
    )

    sweep_lines = [ln for ln in lines if "sweep" in ln]
    assert sweep_lines, f"the sweep went unannounced: {lines}"
    assert "20 silent" in sweep_lines[0]
    assert "recovered 20" in sweep_lines[-1]
    # And the pull's last heartbeat, which counted those 20 as silent, is
    # corrected rather than left standing as the run's final word.
    # (101 fetched: the 100 candidates plus the market index.)
    assert "81 resolved, 20 silent" in [ln for ln in lines if ": pull " in ln][-2]
    assert "101 resolved, 0 silent" in lines[-1]


def test_the_record_tells_a_throttled_symbol_from_an_empty_one(store, tmp_path):
    # Both are silence and both count against the gate; they point at different
    # remedies, and until now ``run_failures`` could not tell them apart.
    clock = FakeClock()
    instruments = _us_instruments(100)
    outcomes = {f"S{i:03d}": "429" for i in range(90, 95)}
    outcomes.update({f"S{i:03d}": [] for i in range(95, 100)})
    client = BudgetClient(instruments, clock, budget=1000, outcomes=outcomes)
    source = Source(client, rate_per_sec=1000, monotonic=clock.monotonic, sleep=clock.sleep)

    record = run_market_universe(
        store, source, "US", SESSIONS[-1], now=NOW, digests_dir=tmp_path,
        workers=1, progress=lambda line: None,
    )

    assert record.status == "quarantined"
    by_symbol = {f.symbol: f for f in store.run_failures("US", SESSIONS[-1])}
    assert by_symbol["S090"].status == "throttled"
    assert by_symbol["S090"].counted, "throttled silence still counts against the gate"
    assert by_symbol["S095"].status == "unresolved"

    summary = summarize_pull(record, store.run_failures("US", SESSIONS[-1]))
    assert "10 silent and counted against the gate" in summary
    assert "5 throttled" in summary
