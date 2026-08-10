"""Operator recompute of a published session (issue #111).

There was no supported way to correct a published session built from a
known-buggy enumeration (e.g. the truncated IDX universe of #110): the store's
write-once guard refused to discard a published session and the scheduler refused
to re-run one. ``run_market_universe(..., recompute=True)`` is that supported
path — it re-pulls and replaces the session *only if* the fresh pull clears the
completeness gate, so a throttled retry can never downgrade good data to an empty
session. The forward regime record (follow-through) stays write-once even here.

The source is injected so the whole swap is exercised without the network; its
enumeration is mutable so a test can widen it between the first publish and the
recompute, exactly as the #110 fix widened the live one.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from screener.pipeline import run_market_universe
from screener.source import Instrument, Source
from screener.store import Store

WIB = ZoneInfo("Asia/Jakarta")
CAL = [date(2026, 7, 1) + timedelta(days=i) for i in range(30)]
NOW = datetime(2026, 8, 20, 20, 0, tzinfo=WIB)  # past every session's close
SESSION = CAL[-1]


def _row(session, *, close, volume, adj_close=None):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": adj_close if adj_close is not None else close,
        "Volume": volume,
    }


class _MutableClient:
    """A fake client whose enumeration and bars can be swapped between runs."""

    def __init__(self, instruments, bars):
        self.instruments = instruments
        self.bars = bars

    def enumerate(self, market):
        return self.instruments

    def fetch(self, symbol, start=None):
        return self.bars.get(symbol, [])

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}


def _index_bars():
    # Climbs to a fresh high on the last session, so the run captures a breakout.
    return [_row(s, close=1000.0 + i, volume=1_000_000) for i, s in enumerate(CAL)]


def _liquid(adj_start=100.0):
    return [
        _row(s, close=2000.0, volume=1_000_000, adj_close=adj_start + i)
        for i, s in enumerate(CAL)
    ]


def _source(client, **kwargs):
    return Source(client, rate_per_sec=1000, sleep=lambda s: None, **kwargs)


def test_recompute_replaces_the_universe_from_a_widened_enumeration():
    # The #110 shape: publish under a buggy enumeration that only saw one
    # candidate, then fix the enumeration and recompute the same session. The
    # universe must grow to reflect the fix while the session stays a single
    # published run.
    store = Store.memory()
    try:
        client = _MutableClient(
            [
                Instrument(market="IDX", symbol="^JKSE", role="reference"),
                Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
            ],
            {"^JKSE": _index_bars(), "AAA": _liquid(), "BBB": _liquid()},
        )
        first = run_market_universe(store, _source(client), "IDX", SESSION, now=NOW)
        assert first.status == "published"
        assert store.universe("IDX", SESSION) == ["AAA"]

        # The enumeration is fixed: BBB was always there, the buggy pull just
        # never enumerated it.
        client.instruments.append(
            Instrument(market="IDX", symbol="BBB", role="candidate", name="Beta Tbk")
        )
        record = run_market_universe(
            store, _source(client), "IDX", SESSION, now=NOW, recompute=True
        )

        assert record is not None and record.status == "published"
        assert store.universe("IDX", SESSION) == ["AAA", "BBB"], "universe widened"
        assert [r.session for r in store.runs("IDX")] == [SESSION], "still one run"
    finally:
        store.close()


def test_recompute_keeps_the_forward_regime_record_write_once():
    # follow-through is a function of the index, not the candidate enumeration, so
    # correcting the enumeration must not rewrite it (spec §7.2, §4.9). One row
    # before, the same one row after.
    store = Store.memory()
    try:
        client = _MutableClient(
            [
                Instrument(market="IDX", symbol="^JKSE", role="reference"),
                Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
            ],
            {"^JKSE": _index_bars(), "AAA": _liquid()},
        )
        run_market_universe(store, _source(client), "IDX", SESSION, now=NOW)
        before = store.follow_through("IDX")
        assert [r.session for r in before] == [SESSION]

        run_market_universe(
            store, _source(client), "IDX", SESSION, now=NOW, recompute=True
        )

        after = store.follow_through("IDX")
        assert [(r.session, r.broke_out, r.index_close) for r in after] == [
            (r.session, r.broke_out, r.index_close) for r in before
        ], "the forward record is untouched by the recompute"
    finally:
        store.close()


def test_a_throttled_recompute_keeps_the_good_published_session():
    # The safety property: a recompute whose fresh pull falls below the
    # completeness floor must not downgrade the served session to an empty one. It
    # returns None and the original universe stands (the atomic swap).
    store = Store.memory()
    try:
        client = _MutableClient(
            [
                Instrument(market="IDX", symbol="^JKSE", role="reference"),
                Instrument(market="IDX", symbol="AAA", role="candidate", name="Alpha Tbk"),
            ],
            {"^JKSE": _index_bars(), "AAA": _liquid()},
        )
        run_market_universe(store, _source(client), "IDX", SESSION, now=NOW)
        assert store.universe("IDX", SESSION) == ["AAA"]

        # The recompute pull goes silent on every candidate — only the index
        # answers — so it falls under the resolution floor and quarantines.
        client.bars = {"^JKSE": _index_bars()}
        record = run_market_universe(
            store,
            _source(client, max_attempts=1),
            "IDX",
            SESSION,
            now=NOW,
            recompute=True,
        )

        assert record is None, "the throttled recompute recorded nothing"
        assert store.universe("IDX", SESSION) == ["AAA"], "the good universe stands"
        run = store.run("IDX", SESSION)
        assert run.status == "published", "the published record is intact"
    finally:
        store.close()
