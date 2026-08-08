"""Seam 3: the source boundary, faked.

The source client is the one module that touches the network (spec §3.1), so it
is the only thing a test ever fakes. Everything above it sees a result type,
never a bare empty list — because Yahoo *fails as silence* (spec §3.2): a
throttled request returns an empty result byte-identical to a genuinely dead
name. So an empty result must surface as ``unresolved`` and be retried; it is
never reported as ``absent`` (spec §3.4 rule 5).

These tests drive that boundary with a fake client and an injected clock, so no
test touches the network and none sleeps in real time.
"""

from datetime import date, datetime

import pytest

from screener.pipeline import run_market_from_source
from screener.source import (
    Pacer,
    PermanentlyUnavailableError,
    RateLimitedError,
    Source,
    parse_idx_screener,
    parse_us_listings,
    resolve_market,
)
from screener.store import Store


# -- a clock that records sleeps and advances in virtual time ----------------


class FakeClock:
    """A monotonic clock whose ``sleep`` advances virtual time and records it."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


# -- a fake source client -----------------------------------------------------


class FakeClient:
    """Fakes the two network operations: enumerate and per-symbol fetch.

    ``responses`` maps a symbol to a list of successive fetch outcomes, so a
    symbol can return empty (silence), then data, on retries. An outcome of
    ``"429"`` raises :class:`RateLimitedError`, ``"refused"`` raises
    :class:`PermanentlyUnavailableError`; a list is returned as bars.
    """

    def __init__(self, instruments=None, responses=None) -> None:
        self._instruments = instruments or {}
        self._responses = responses or {}
        self.fetch_calls: list[str] = []

    def enumerate(self, market):
        return self._instruments[market]

    def fetch(self, symbol):
        self.fetch_calls.append(symbol)
        outcomes = self._responses.get(symbol, [[]])
        seen = self.fetch_calls.count(symbol) - 1
        outcome = outcomes[min(seen, len(outcomes) - 1)]
        if outcome == "429":
            raise RateLimitedError(symbol)
        if outcome == "refused":
            raise PermanentlyUnavailableError(f"{symbol}: period 'max' is invalid")
        return outcome


def make_source(client, **kw):
    clock = FakeClock()
    src = Source(
        client,
        rate_per_sec=12,
        max_attempts=4,
        backoff_base=1.0,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        **kw,
    )
    return src, clock


# -- enumeration and role derivation -----------------------------------------


def test_parse_us_listings_derives_role_and_reference_index():
    nasdaqlisted = "\n".join(
        [
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares",
            "AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N",
            "QQQ|Invesco QQQ Trust|Q|N|N|100|Y|N",
            "ZTEST|Nasdaq Test Issue|Q|Y|N|100|N|N",
            "File Creation Time: 0804202617:00|||||||",
        ]
    )
    otherlisted = "\n".join(
        [
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol",
            "SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY",
            "BRK.A|Berkshire Hathaway|N|BRK.A|N|100|N|BRK.A",
        ]
    )

    instruments = parse_us_listings(nasdaqlisted, otherlisted)
    by_symbol = {i.symbol: i for i in instruments}

    assert by_symbol["AAPL"].role == "candidate"
    assert by_symbol["BRK.A"].role == "candidate"
    assert by_symbol["QQQ"].role == "reference"  # ETF flag -> reference
    assert by_symbol["SPY"].role == "reference"
    assert by_symbol["^IXIC"].role == "reference"  # the market index
    assert "ZTEST" not in by_symbol  # test issues excluded
    assert all(i.market == "US" for i in instruments)


def test_parse_idx_screener_all_candidate_plus_reference_index():
    instruments = parse_idx_screener(["BBCA.JK", "BBRI.JK", "GOTO.JK"])
    by_symbol = {i.symbol: i for i in instruments}

    assert by_symbol["BBCA.JK"].role == "candidate"
    assert by_symbol["^JKSE"].role == "reference"
    assert sum(1 for i in instruments if i.role == "candidate") == 3
    assert all(i.market == "IDX" for i in instruments)


# -- pacing and backoff -------------------------------------------------------


def test_pacer_paces_at_the_configured_rate():
    clock = FakeClock()
    pacer = Pacer(12, monotonic=clock.monotonic, sleep=clock.sleep)

    pacer.wait()  # first request is free
    pacer.wait()  # second must wait one interval
    pacer.wait()

    assert clock.slept == [pytest.approx(1 / 12), pytest.approx(1 / 12)]


def test_resolve_backs_off_exponentially_on_429_then_resolves():
    client = FakeClient(responses={"AAA": ["429", "429", ["bar"]]})
    src, clock = make_source(client)

    result = src.resolve("AAA")

    assert result.status == "resolved"
    assert client.fetch_calls == ["AAA", "AAA", "AAA"]
    # Two 429s -> two backoff sleeps, doubling. Pacing sleeps are separate (the
    # clock advances past every interval), so these are the backoff waits.
    assert 1.0 in clock.slept and 2.0 in clock.slept


# -- unresolved vs absent -----------------------------------------------------


def test_empty_result_is_unresolved_never_absent_and_is_retried():
    client = FakeClient(responses={"DEAD": [[]]})  # silence, always
    src, clock = make_source(client)

    result = src.resolve("DEAD")

    assert result.status == "unresolved"  # never "absent"
    assert result.bars == []
    assert client.fetch_calls == ["DEAD"] * 4  # retried up to max_attempts


def test_empty_then_data_resolves_on_retry():
    client = FakeClient(responses={"SLOW": [[], [], ["bar"]]})
    src, _ = make_source(client)

    result = src.resolve("SLOW")

    assert result.status == "resolved"
    assert result.bars == ["bar"]
    assert client.fetch_calls == ["SLOW", "SLOW", "SLOW"]


def test_data_resolves_on_first_try_without_retry():
    client = FakeClient(responses={"OK": [["bar"]]})
    src, _ = make_source(client)

    result = src.resolve("OK")

    assert result.status == "resolved"
    assert client.fetch_calls == ["OK"]


# -- the run record carries the counts ---------------------------------------


def _us_instruments():
    return parse_us_listings(
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        "AAA|A Corp|Q|N|N|100|N|N\n"
        "BBB|B Corp|Q|N|N|100|N|N\n"
        "EEE|An ETF|Q|N|N|100|Y|N\n",
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n",
    )


def test_resolve_market_counts_only_candidates_and_excludes_references():
    client = FakeClient(
        instruments={"US": _us_instruments()},
        responses={"AAA": [["bar"]], "BBB": [["bar"]]},
    )
    src, _ = make_source(client)

    instruments, resolutions = resolve_market(src, "US")

    resolved_symbols = {r.symbol for r in resolutions}
    # References (^IXIC, EEE) are enumerated but not resolved for the count.
    assert resolved_symbols == {"AAA", "BBB"}
    assert any(i.symbol == "^IXIC" for i in instruments)


def test_run_market_from_source_records_enumerated_and_resolved_counts(store: Store):
    client = FakeClient(
        instruments={"US": _us_instruments()},
        responses={"AAA": [["bar"]], "BBB": [["bar"]]},
    )
    src, _ = make_source(client)

    record = run_market_from_source(store, "US", date(2026, 8, 5), src, now=datetime(2026, 8, 5, 22, 10))

    assert record.status == "published"
    assert record.symbols_enumerated == 2  # two candidates; references excluded
    assert record.symbols_resolved == 2


def test_run_quarantines_when_candidates_stay_unresolved(store: Store):
    instruments = {
        "US": parse_us_listings(
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
            + "".join(f"S{i}|Corp {i}|Q|N|N|100|N|N\n" for i in range(100)),
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n",
        )
    }
    # 90 resolve, 10 stay silent -> below the 99% floor.
    responses = {f"S{i}": [["bar"]] for i in range(90)}
    responses.update({f"S{i}": [[]] for i in range(90, 100)})
    client = FakeClient(instruments=instruments, responses=responses)
    src, _ = make_source(client)

    record = run_market_from_source(store, "US", date(2026, 8, 6), src, now=datetime(2026, 8, 6, 22, 10))

    assert record.status == "quarantined"
    assert record.symbols_enumerated == 100
    assert record.symbols_resolved == 90
    assert store.universe("US", date(2026, 8, 6)) == []


# -- a stated refusal is not silence -----------------------------------------


def test_a_stated_refusal_is_answered_once_not_retried():
    # Yahoo will not serve full history for some listings (warrants and units,
    # typically) and says so instead of returning an empty frame. That is an
    # answer, so there is nothing to wait out: one attempt, no backoff sleeps,
    # unlike the four-attempt retry silence earns (issue #47).
    client = FakeClient(
        instruments={"US": _us_instruments()},
        responses={"AAA": ["refused"], "BBB": [[]]},
    )
    src, clock = make_source(client)
    # The clock records the pacer's sub-second waits too; the backoff sleeps are
    # the ones this test is about.
    backoff = lambda: [s for s in clock.slept if s >= 1.0]  # noqa: E731

    refused = src.resolve("AAA")

    assert refused.status == "refused"
    assert refused.bars == []
    assert client.fetch_calls.count("AAA") == 1, "a refusal was retried"
    assert backoff() == [], "a refusal burned backoff sleeps"

    # Silence still gets the full retry budget — the policy it exists for.
    src.resolve("BBB")
    assert client.fetch_calls.count("BBB") == 4
    assert backoff() == [1.0, 2.0, 4.0]


def test_refused_listings_do_not_drag_the_completeness_gate(store: Store):
    # The floor exists to catch a throttled pull. Listings the provider refuses
    # outright are not throttling and can never resolve, so counting them in the
    # denominator would quarantine a pull that fetched everything obtainable —
    # a market's warrants alone are enough to do it (issue #47).
    instruments = {
        "US": parse_us_listings(
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
            + "".join(f"S{i}|Corp {i}|Q|N|N|100|N|N\n" for i in range(100)),
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n",
        )
    }
    # 90 resolve, 10 are refused outright — nothing was lost to silence.
    responses = {f"S{i}": [["bar"]] for i in range(90)}
    responses.update({f"S{i}": ["refused"] for i in range(90, 100)})
    client = FakeClient(instruments=instruments, responses=responses)
    src, _ = make_source(client)

    record = run_market_from_source(
        store, "US", date(2026, 8, 6), src, now=datetime(2026, 8, 6, 22, 10)
    )

    assert record.status == "published"
    assert record.symbols_enumerated == 90, "refusals stayed out of the denominator"
    assert record.symbols_resolved == 90


def test_instrument_type_excluded_listings_do_not_drag_the_completeness_gate(store: Store):
    # The far larger sibling of the refusal case (issue #90). Warrants, rights,
    # units and preferreds are ~a quarter of the US enumeration; the provider
    # serves no history for them, so they come back as *silence* (unresolved),
    # not a stated refusal. The instrument-type rule throws them out of the
    # universe on their name anyway, but it runs after resolution — so left in
    # the denominator they fail every night as silence and hold US permanently
    # under the floor. They must sit outside the gate the same as refusals do.
    instruments = {
        "US": parse_us_listings(
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
            + "".join(f"S{i}|Corp {i} - Common Stock|Q|N|N|100|N|N\n" for i in range(90))
            + "".join(f"W{i}|Corp {i} Warrant|Q|N|N|100|N|N\n" for i in range(10)),
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol\n",
        )
    }
    # Every common stock resolves; the ten warrants come back as silence.
    responses = {f"S{i}": [["bar"]] for i in range(90)}
    responses.update({f"W{i}": [[]] for i in range(10)})
    client = FakeClient(instruments=instruments, responses=responses)
    src, _ = make_source(client)

    record = run_market_from_source(
        store, "US", date(2026, 8, 6), src, now=datetime(2026, 8, 6, 22, 10)
    )

    assert record.status == "published"
    assert record.symbols_enumerated == 90, "instrument-type exclusions stayed out of the denominator"
    assert record.symbols_resolved == 90
