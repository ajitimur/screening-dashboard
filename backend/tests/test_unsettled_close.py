"""The unsettled-close guard: a shell bar is silence, not a resolution.

Yahoo can answer a session with the *scaffolding* of a bar — ``Open``, ``High``,
``Low`` and ``Volume`` all populated — and no ``Close`` at all (it arrives NaN).
On 2026-09-22 it did so for 5,320 of 5,338 US bars, and because
:meth:`Source.resolve` measured resolution as "the payload was non-empty", every
one of those symbols counted as resolved: the run recorded 5,481/5,481 and
published. Downstream, ``float('nan')`` propagated silently — 2,065 of 2,070
names carried a NaN return, every percentile collapsed to 1.0 (NaN sorts as
greatest, so the whole universe tied at the top), breadth read 0%, all eleven
sectors read 0% strength and the index volatility went NaN.

The rule these tests pin: a payload whose **newest** bar carries no close is
silence in disguise (spec §3.2's ambiguous emptiness), so it is retried and then
``unresolved`` — which drops it out of the resolved count and lets the existing
completeness floor quarantine the night (§3.4 rules 5, 7) instead of publishing
a universe that cannot be ranked.

Newest, not *any*: a real history carries the odd NaN close deep in the past (a
healthy 2026-09-21 pull had four), and quarantining on those would refuse every
night. It is the session the run is about to ingest that has to have printed.
"""

from datetime import date, datetime

from screener.models import SILENT_STATUSES
from screener.pipeline import run_market_from_source
from screener.source import Source, parse_us_listings, sweep_silence
from screener.store import Store

NAN = float("nan")


def _row(session, *, close=10.5, adj_close=None, volume=1000):
    """A raw source bar row, keyed as yfinance emits it (auto_adjust=False)."""
    return {
        "Date": session,
        "Open": 10.0,
        "High": 11.0,
        "Low": 9.0,
        "Close": close,
        "Adj Close": close if adj_close is None else adj_close,
        "Volume": volume,
    }


def _settled_history():
    """Two settled sessions — an ordinary healthy payload."""
    return [_row(date(2026, 9, 21)), _row(date(2026, 9, 22))]


def _unsettled_history():
    """The 2026-09-22 shape: history settled, newest session's close never printed."""
    return [_row(date(2026, 9, 21)), _row(date(2026, 9, 22), close=NAN)]


class FakeClient:
    """Fakes enumerate + fetch, returning raw bar rows per successive attempt."""

    def __init__(self, instruments=None, responses=None) -> None:
        self._instruments = instruments or {}
        self._responses = responses or {}
        self.fetch_calls: list[str] = []

    def enumerate(self, market):
        return self._instruments[market]

    def fetch(self, symbol, start=None):
        self.fetch_calls.append(symbol)
        outcomes = self._responses.get(symbol, [[]])
        seen = self.fetch_calls.count(symbol) - 1
        return outcomes[min(seen, len(outcomes) - 1)]


def _source(client, **kw):
    return Source(
        client, rate_per_sec=1000, max_attempts=4, backoff_base=1.0,
        sleep=lambda s: None, **kw,
    )


# -- the guard at the resolve seam -------------------------------------------


def test_payload_whose_newest_bar_never_printed_a_close_is_unresolved():
    client = FakeClient(responses={"AAPL": [_unsettled_history()]})
    src = _source(client)

    result = src.resolve("AAPL")

    assert result.status == "unresolved"  # silence, not a resolution


def test_an_unsettled_close_is_asked_once_not_retried():
    """The provider answered; seven seconds of backoff cannot settle a close.

    Retrying it would cost four fetches a symbol — market-wide, the whole pull's
    runtime again — for an answer that does not change. Recovering a late close
    is the tail sweep's minutes-long job, not this call's.
    """
    client = FakeClient(responses={"AAPL": [_unsettled_history()]})
    src = _source(client)

    src.resolve("AAPL")

    assert client.fetch_calls == ["AAPL"]


def test_an_empty_answer_is_still_retried_to_the_full_budget():
    """The no-retry rule is about an *answered* payload, and must not leak."""
    client = FakeClient(responses={"DEAD": [[]]})
    src = _source(client)

    assert src.resolve("DEAD").status == "unresolved"
    assert client.fetch_calls == ["DEAD"] * 4


def test_a_newest_bar_missing_only_its_adjusted_close_is_unresolved():
    """§3.5 splits the series: the adjusted close is what every return rides.

    A row with a finite ``Close`` and a NaN ``Adj Close`` reproduces the whole of
    2026-09-22, so guarding the unadjusted series alone would leave it reachable.
    """
    history = [_row(date(2026, 9, 21)), _row(date(2026, 9, 22), adj_close=NAN)]
    src = _source(FakeClient(responses={"AAPL": [history]}))

    assert src.resolve("AAPL").status == "unresolved"


def test_unsettled_silence_is_carried_apart_from_an_empty_answer():
    """Both are silence; they point at opposite remedies, so the verdict says which."""
    unsettled = _source(FakeClient(responses={"AAPL": [_unsettled_history()]}))
    empty = _source(FakeClient(responses={"DEAD": [[]]}))

    assert unsettled.resolve("AAPL").unsettled is True
    assert empty.resolve("DEAD").unsettled is False


def test_the_tail_sweep_recovers_a_close_that_prints_late():
    """The rest that *can* settle a close is the sweep's, measured in minutes."""
    client = FakeClient(
        responses={"AAPL": [_unsettled_history(), _settled_history()]}
    )
    src = _source(client)

    assert src.resolve("AAPL").status == "unresolved"
    # One rest later — the sweep re-asks on that same "unresolved" verdict.
    swept = list(sweep_silence(src, ["AAPL"], pauses=(0.0,), workers=1))

    assert [r.status for r in swept] == ["resolved"]


def test_a_nan_close_deep_in_history_still_resolves():
    """Only the session being ingested has to have printed (a healthy pull carries old gaps)."""
    history = [
        _row(date(2026, 9, 18), close=NAN),  # an old gap
        _row(date(2026, 9, 21)),
        _row(date(2026, 9, 22)),
    ]
    src = _source(FakeClient(responses={"AAPL": [history]}))

    assert src.resolve("AAPL").status == "resolved"


def test_a_volumeless_index_level_resolves_on_its_close_alone():
    """A volatility index prints no volume by design (§4.10); its close is what matters."""
    level = [_row(date(2026, 9, 21), volume=0), _row(date(2026, 9, 22), volume=0)]
    src = _source(FakeClient(responses={"^VIX": [level]}))

    assert src.resolve("^VIX").status == "resolved"


# -- the night quarantines ----------------------------------------------------


def _listings(n: int):
    return {
        "US": parse_us_listings(
            "Symbol|Security Name|Market Category|Test Issue|Financial Status|"
            "Round Lot Size|ETF|NextShares\n"
            + "".join(f"S{i}|Corp {i}|Q|N|N|100|N|N\n" for i in range(n)),
            "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|"
            "Test Issue|NASDAQ Symbol\n",
        )
    }


def test_a_night_of_unsettled_closes_quarantines_instead_of_publishing(store: Store):
    """The 2026-09-22 regression: a whole market of shell bars must not publish."""
    responses = {f"S{i}": [_unsettled_history()] for i in range(100)}
    src = _source(FakeClient(instruments=_listings(100), responses=responses))

    record = run_market_from_source(
        store, "US", date(2026, 9, 22), src, now=datetime(2026, 9, 22, 22, 10)
    )

    assert record.status == "quarantined"
    assert record.symbols_resolved == 0
    # A quarantined run writes no universe, so nothing downstream can read it.
    assert store.universe("US", date(2026, 9, 22)) == []


def test_a_settled_night_still_publishes(store: Store):
    """The guard must not refuse a healthy pull."""
    responses = {f"S{i}": [_settled_history()] for i in range(100)}
    src = _source(FakeClient(instruments=_listings(100), responses=responses))

    record = run_market_from_source(
        store, "US", date(2026, 9, 22), src, now=datetime(2026, 9, 22, 22, 10)
    )

    assert record.status == "published"
    assert record.symbols_resolved == 100


def test_unsettled_is_reported_as_silence_counted_against_the_gate():
    """It produced no usable bars and no explanation, so it reads as silence.

    :data:`SILENT_STATUSES` is the pull summary's vocabulary — what the operator
    is told counted against the gate — not what drives the sweep (the sweep asks
    on the ``unresolved`` status itself).
    """
    assert "unsettled" in SILENT_STATUSES
