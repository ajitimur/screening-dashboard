"""Seam 4: bar ingest and hygiene.

Bars for both markets land in the store, clean enough that every downstream
stage can trust them (spec §3.4, §3.5, §7.4 stages 2–3). Three hygiene rules,
all applied at ingest so no downstream computation has to remember them:

- **Phantom bars** (``volume == 0``) are removed entirely (rule 1).
- **Finality**: a bar dated ``D`` is final only once ``D``'s normal exchange
  close + 30 min has passed in the exchange's local time; non-final bars are
  discarded, not stored flagged (rule 2).
- **Both series stored**: unadjusted OHLC (for dollar volume) and the adjusted
  close (for everything geometric) — the source rescales prices for corporate
  actions but leaves volume alone (§3.5).

Each market's pull is persisted the moment it completes, so killing the second
market's pull cannot discard the first's finished work (§3.3).

The source boundary is faked (Seam 3), the clock is injected, and no test
touches the network or sleeps in real time.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from screener.bars import (
    Bar,
    clean_bars,
    drop_phantom_bars,
    is_final,
    parse_bars,
)
from screener.pipeline import ingest_market_bars
from screener.source import Instrument, Source
from screener.store import Store

ET = ZoneInfo("America/New_York")
WIB = ZoneInfo("Asia/Jakarta")


def _row(session, *, open=10.0, high=11.0, low=9.0, close=10.5, adj_close=10.5, volume=1000):
    """A raw source bar row, keyed as yfinance emits (auto_adjust=False)."""
    return {
        "Date": session,
        "Open": open,
        "High": high,
        "Low": low,
        "Close": close,
        "Adj Close": adj_close,
        "Volume": volume,
    }


# -- parsing: both series preserved -------------------------------------------


def test_parse_keeps_unadjusted_and_adjusted_series():
    [bar] = parse_bars([_row(date(2026, 8, 4), close=100.0, adj_close=90.0, volume=2000)])

    assert bar.session == date(2026, 8, 4)
    assert bar.close == 100.0  # unadjusted, for dollar volume
    assert bar.adj_close == 90.0  # adjusted, for everything geometric
    assert bar.dollar_volume == 100.0 * 2000  # dollar volume uses unadjusted close


def test_parse_accepts_timestamp_and_string_dates():
    rows = [_row(datetime(2026, 8, 3, 0, 0)), _row("2026-08-04")]
    assert [b.session for b in parse_bars(rows)] == [date(2026, 8, 3), date(2026, 8, 4)]


# -- rule 1: phantom bars ------------------------------------------------------


def test_zero_volume_bars_are_dropped_entirely():
    bars = [
        Bar(date(2026, 8, 3), 10, 11, 9, 10, 10, 1000),
        Bar(date(2026, 8, 4), 10, 10, 10, 10, 10, 0),  # phantom: no trade
        Bar(date(2026, 8, 5), 10, 11, 9, 10, 10, 500),
    ]
    kept = drop_phantom_bars(bars)
    assert [b.session for b in kept] == [date(2026, 8, 3), date(2026, 8, 5)]


# -- rule 2: finality ----------------------------------------------------------


def test_bar_is_final_only_after_normal_close_plus_30_min():
    session = date(2026, 8, 4)
    # US normal close 16:00 ET; final only after 16:30 ET.
    assert not is_final(session, "US", datetime(2026, 8, 4, 16, 15, tzinfo=ET))
    assert not is_final(session, "US", datetime(2026, 8, 4, 16, 30, tzinfo=ET))
    assert is_final(session, "US", datetime(2026, 8, 4, 16, 45, tzinfo=ET))


def test_us_early_close_needs_no_special_handling():
    # A US early-close day closes 13:00 ET. A rule keyed to the normal 16:00
    # close waits until 16:30 — longer than necessary, never shorter. At 13:45
    # (past the real 13:00+30) the normal-close rule still holds the bar back.
    session = date(2026, 11, 27)  # day after Thanksgiving, 13:00 ET close
    assert not is_final(session, "US", datetime(2026, 11, 27, 13, 45, tzinfo=ET))
    assert is_final(session, "US", datetime(2026, 11, 27, 16, 45, tzinfo=ET))


def test_finality_is_exchange_local():
    session = date(2026, 8, 4)
    # IDX close 16:00 WIB -> final after 16:30 WIB, regardless of the US clock.
    assert not is_final(session, "IDX", datetime(2026, 8, 4, 16, 15, tzinfo=WIB))
    assert is_final(session, "IDX", datetime(2026, 8, 4, 16, 45, tzinfo=WIB))


def test_clean_bars_drops_phantoms_and_non_final():
    now = datetime(2026, 8, 5, 16, 15, tzinfo=ET)  # 04's close+30 passed, 05's not
    bars = [
        Bar(date(2026, 8, 4), 10, 11, 9, 10, 10, 1000),  # final, real
        Bar(date(2026, 8, 4), 10, 10, 10, 10, 10, 0),  # phantom
        Bar(date(2026, 8, 5), 10, 11, 9, 10, 10, 800),  # not yet final
    ]
    kept = clean_bars(bars, "US", now)
    assert [b.session for b in kept] == [date(2026, 8, 4)]


# -- storage: both series land, keyed (market, symbol, session) ---------------


def test_store_persists_both_series_and_reads_back(store: Store):
    bars = [
        Bar(date(2026, 8, 3), 10, 11, 9, 10.5, 9.4, 1000),
        Bar(date(2026, 8, 4), 11, 12, 10, 11.5, 10.3, 1200),
    ]
    store.append_bars("US", "AAA", bars)

    got = store.bars("US", "AAA")
    assert [b.session for b in got] == [date(2026, 8, 3), date(2026, 8, 4)]
    assert got[0].close == 10.5 and got[0].adj_close == 9.4
    assert store.last_session("US", "AAA") == date(2026, 8, 4)
    assert store.last_session("US", "MISSING") is None


def test_append_bars_never_rewrites_an_existing_session(store: Store):
    store.append_bars("US", "AAA", [Bar(date(2026, 8, 3), 10, 11, 9, 10, 10, 1000)])
    # Re-ingesting the same session (e.g. an incremental pass overlapping) is a
    # no-op: bars are written once, never rewritten (spec §7.2).
    store.append_bars(
        "US",
        "AAA",
        [
            Bar(date(2026, 8, 3), 99, 99, 99, 99, 99, 9),  # would-be rewrite
            Bar(date(2026, 8, 4), 11, 12, 10, 11, 11, 1200),  # genuinely new
        ],
    )
    got = store.bars("US", "AAA")
    assert [b.session for b in got] == [date(2026, 8, 3), date(2026, 8, 4)]
    assert got[0].close == 10  # original survives, not the 99 rewrite


def test_sessions_are_the_observed_bar_dates_not_a_holiday_table(store: Store):
    # The exchange calendar is the union of observed bar dates (spec §3.4 rule
    # 4) — a gap (weekend/holiday) simply has no bars, no table consulted.
    store.append_bars("US", "AAA", [
        Bar(date(2026, 8, 6), 10, 11, 9, 10, 10, 1000),
        Bar(date(2026, 8, 7), 10, 11, 9, 10, 10, 1000),
    ])
    store.append_bars("US", "BBB", [
        Bar(date(2026, 8, 7), 10, 11, 9, 10, 10, 1000),
        Bar(date(2026, 8, 10), 10, 11, 9, 10, 10, 1000),  # Mon; 8-9 is a weekend
    ])
    assert store.sessions("US") == [date(2026, 8, 6), date(2026, 8, 7), date(2026, 8, 10)]


# -- pipeline: fake source, per-market persistence ----------------------------


class FakeBarClient:
    """Fakes enumerate + fetch, returning raw bar rows. ``fail_on`` raises a
    hard error when a given symbol is fetched (a killed pull, not a 429)."""

    def __init__(self, instruments, bars_by_symbol, fail_on=None):
        self._instruments = instruments
        self._bars = bars_by_symbol
        self._fail_on = fail_on

    def enumerate(self, market):
        return self._instruments[market]

    def fetch(self, symbol):
        if symbol == self._fail_on:
            raise RuntimeError(f"pull killed at {symbol}")
        return self._bars.get(symbol, [])


def _source(client):
    # rate high + no real sleep: virtual pacing, no network, no real time.
    return Source(client, rate_per_sec=1000, sleep=lambda s: None)


def test_ingest_stores_clean_bars_for_candidates_and_index(store: Store):
    now = datetime(2026, 8, 5, 16, 15, tzinfo=ET)
    instruments = [
        Instrument(market="US", symbol="^IXIC", role="reference"),
        Instrument(market="US", symbol="AAA", role="candidate"),
    ]
    bars = {
        "AAA": [
            _row(date(2026, 8, 4), volume=1000),
            _row(date(2026, 8, 4), volume=0),  # phantom, dropped
            _row(date(2026, 8, 5), volume=800),  # not yet final, discarded
        ],
        "^IXIC": [_row(date(2026, 8, 4), volume=500)],
    }
    client = FakeBarClient({"US": instruments}, bars)
    ingest_market_bars(store, _source(client), "US", now=now)

    # index bars are ingested on the same path (spec §3.1)
    assert [b.session for b in store.bars("US", "^IXIC")] == [date(2026, 8, 4)]
    # candidate: phantom and non-final gone, one clean final bar left
    assert [b.session for b in store.bars("US", "AAA")] == [date(2026, 8, 4)]


def test_killing_the_second_market_pull_leaves_the_first_intact(store: Store):
    now = datetime(2026, 8, 5, 8, 0, tzinfo=ET)  # past both closes for 08-04

    us = [Instrument(market="US", symbol="U1", role="candidate")]
    us_bars = {"U1": [_row(date(2026, 8, 4), volume=1000)]}
    ingest_market_bars(store, _source(FakeBarClient({"US": us}, us_bars)), "US", now=now)

    # IDX pull dies on the second symbol after the first has been persisted.
    idx = [
        Instrument(market="IDX", symbol="I1", role="candidate"),
        Instrument(market="IDX", symbol="I2", role="candidate"),
    ]
    idx_bars = {"I1": [_row(date(2026, 8, 4), volume=1000)]}
    idx_now = datetime(2026, 8, 5, 8, 0, tzinfo=WIB)
    with pytest.raises(RuntimeError):
        ingest_market_bars(
            store,
            _source(FakeBarClient({"IDX": idx}, idx_bars, fail_on="I2")),
            "IDX",
            now=idx_now,
        )

    # The first market's bars — and IDX's already-persisted symbol — survive.
    assert [b.session for b in store.bars("US", "U1")] == [date(2026, 8, 4)]
    assert [b.session for b in store.bars("IDX", "I1")] == [date(2026, 8, 4)]
