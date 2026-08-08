"""Incremental nightly fetch, safe against permanent refusals (issue #100).

The nightly pull used to ask every symbol for ``period="max"`` — a full ~10-year
history, every night. §3.6 mandates an *incremental* append instead: a symbol
that already has bars is fetched from ``last_stored_session − 20 sessions``, and
only a cold-start symbol (no bars yet) asks for the whole history.

The 20-bar overlap is load-bearing, not an optimisation. §3.4 rule 5 is "zero
rows is ``unresolved``, never ``absent``": a naive incremental fetch of an
up-to-date name returns zero new rows, byte-identical to a throttled response, so
every healthy run would quarantine. Always re-requesting the overlap means a
healthy fetch always returns rows, and ``append_bars``'s ``ON CONFLICT DO
NOTHING`` makes the re-sent rows a free no-op.

The refusal signal is the catch. ``YFInvalidPeriodError`` — the *stated* refusal
mapped to :class:`PermanentlyUnavailableError` — fires only when ``period`` is
set; passing ``start=`` sets ``period`` to ``None``, so it can never fire and a
refused listing would collapse into ordinary silence and start dragging the gate
again (this is #47). So a symbol's *first* fetch (cold start, ``period="max"``)
is where refusal is detected, that verdict is persisted per symbol, and every
later night a persisted-refused symbol is skipped entirely — never re-probed,
never counted against the gate.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from screener.pipeline import OVERLAP_SESSIONS, run_market_universe
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


SESSIONS = _weekdays_ending(date(2026, 8, 6), 40)


def _row(session, close=200.0, volume=1_000_000):
    return {
        "Date": session, "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Adj Close": close, "Volume": volume,
    }


def _now_after(session: date) -> datetime:
    return datetime(session.year, session.month, session.day, 22, 10, tzinfo=NY)


class _RecordingClient:
    """A fake source client that records the ``start`` each fetch was called with.

    ``cold`` maps a symbol to the bars ``period="max"`` returns; ``incremental``
    maps it to the bars a ``start=`` fetch returns (defaulting to ``cold``).
    ``refuse_on_cold`` names symbols the provider refuses when ``period`` is set —
    and, exactly as yfinance behaves, *cannot* refuse under ``start=`` (period is
    ``None``), where the refusal collapses into silence.
    """

    def __init__(self, instruments, cold, *, incremental=None, refuse_on_cold=()):
        self._instruments = instruments
        self._cold = cold
        self._incremental = incremental or {}
        self._refuse = set(refuse_on_cold)
        self.calls: list[tuple[str, object]] = []

    def enumerate(self, market):
        return self._instruments

    def fetch(self, symbol, start=None):
        self.calls.append((symbol, start))
        if start is None:  # cold start: period="max", the one place refusal fires
            if symbol in self._refuse:
                raise PermanentlyUnavailableError(f"{symbol}: period 'max' is invalid")
            return self._cold.get(symbol, [])
        # start= sets period to None, so a refusal can never fire here — a refused
        # listing surfaces as ordinary silence (the #47 failure mode).
        if symbol in self._refuse:
            return []
        return self._incremental.get(symbol, self._cold.get(symbol, []))

    def fetch_info(self, symbol):
        return {"sector": "Technology", "industry": "Software"}

    def starts_for(self, symbol):
        return [start for sym, start in self.calls if sym == symbol]


def _source(client) -> Source:
    return Source(client, rate_per_sec=1000, max_attempts=1, sleep=lambda s: None)


def _liquid_market(symbols):
    """An enumeration of common stocks plus the index, all resolving liquid."""
    instruments = [Instrument(market="US", symbol="^IXIC", role="reference")]
    cold = {"^IXIC": [_row(s, close=100.0, volume=1) for s in SESSIONS]}
    for sym in symbols:
        instruments.append(
            Instrument(market="US", symbol=sym, role="candidate",
                       name=f"{sym} Inc - Common Stock")
        )
        cold[sym] = [_row(s) for s in SESSIONS]
    return instruments, cold


# -- cold start vs incremental ------------------------------------------------


def test_a_symbol_with_no_bars_is_fetched_at_period_max(store: Store, tmp_path):
    instruments, cold = _liquid_market(["OK"])
    client = _RecordingClient(instruments, cold)

    run_market_universe(
        store, _source(client), "US", SESSIONS[-2],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    # Nothing was stored before the run, so every symbol is a cold start: the
    # fetch asks for the whole history (start=None -> period="max").
    assert client.starts_for("OK") == [None]


def test_a_symbol_with_bars_is_fetched_from_last_session_minus_the_overlap(
    store: Store, tmp_path
):
    instruments, cold = _liquid_market(["OK"])
    # Night one seeds the store with OK's bars for every session.
    run_market_universe(
        store, _source(_RecordingClient(instruments, cold)), "US", SESSIONS[-2],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )
    last = store.last_session("US", "OK")
    calendar = store.sessions("US")

    # Night two fetches OK incrementally, from ~20 sessions before its last bar.
    client = _RecordingClient(instruments, cold)
    run_market_universe(
        store, _source(client), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    expected = calendar[calendar.index(last) - OVERLAP_SESSIONS]
    assert client.starts_for("OK") == [expected]
    assert expected < last, "the start is strictly before the last stored session"


def test_a_healthy_incremental_fetch_returns_the_overlap_not_silence(
    store: Store, tmp_path
):
    # The overlap is what keeps rule 5 intact: an up-to-date name still returns
    # rows, so zero rows stays unambiguously silence. Night two's incremental
    # fetch returns only the ~20 overlap bars, and the symbol must still resolve.
    instruments, cold = _liquid_market(["OK"])
    run_market_universe(
        store, _source(_RecordingClient(instruments, cold)), "US", SESSIONS[-2],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )
    overlap = {"OK": [_row(s) for s in SESSIONS[-OVERLAP_SESSIONS:]]}
    client = _RecordingClient(instruments, cold, incremental=overlap)

    record = run_market_universe(
        store, _source(client), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    assert record.status == "published"
    assert record.symbols_resolved == 1  # OK resolved off the overlap, not silence


# -- the persisted refusal verdict --------------------------------------------


def test_a_cold_start_refusal_is_persisted(store: Store, tmp_path):
    instruments, cold = _liquid_market([f"OK{i}" for i in range(20)])
    instruments.append(
        Instrument(market="US", symbol="REF", role="candidate",
                   name="Refused Corp - Common Stock")
    )
    client = _RecordingClient(instruments, cold, refuse_on_cold=["REF"])

    record = run_market_universe(
        store, _source(client), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    assert record.status == "published"
    assert "REF" in store.refusals("US")
    # A stated refusal sits outside the gate, exactly as today.
    assert record.symbols_enumerated == 20


def test_a_persisted_refused_symbol_is_never_reprobed_and_stays_out_of_the_gate(
    store: Store, tmp_path
):
    # The #47 reproduction. Night one: REF refuses at period="max", the verdict
    # is persisted. Night two the provider would answer REF's request with
    # *silence* (a start= fetch cannot draw the refusal, and even a re-probe could
    # be throttled) — under response-shape inference REF would re-enter the gate
    # as an unresolved common stock and drag it. The persisted verdict catches
    # it: REF is skipped entirely, never fetched, and stays out of the gate.
    instruments, cold = _liquid_market([f"OK{i}" for i in range(20)])
    instruments.append(
        Instrument(market="US", symbol="REF", role="candidate",
                   name="Refused Corp - Common Stock")
    )
    run_market_universe(
        store, _source(_RecordingClient(instruments, cold, refuse_on_cold=["REF"])),
        "US", SESSIONS[-2], now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )
    assert "REF" in store.refusals("US")

    # Night two: REF now answers with silence, not a refusal — proving the
    # exclusion is driven by the persisted verdict, not by re-reading the shape.
    night_two = _RecordingClient(instruments, cold)  # REF is no longer in refuse set
    record = run_market_universe(
        store, _source(night_two), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    assert night_two.starts_for("REF") == [], "a persisted-refused symbol was re-probed"
    assert record.status == "published"
    assert record.symbols_enumerated == 20, "REF re-entered the completeness gate"


def test_a_short_of_floor_cold_start_reports_which_symbols_were_short(
    store: Store, tmp_path
):
    # Night one is allowed to be slow and may quarantine (issue #98). When it
    # does, it must say *why* using #91's per-symbol failure rows — a first night
    # that got 91% reads as "short, retrying tomorrow", not an opaque failure.
    from screener.pipeline import summarize_pull

    instruments, cold = _liquid_market([f"OK{i}" for i in range(90)])
    for i in range(10):  # ten common stocks go silent -> under the 99% floor
        instruments.append(
            Instrument(market="US", symbol=f"SIL{i}", role="candidate",
                       name=f"Quiet Corp {i} - Common Stock")
        )
    client = _RecordingClient(instruments, cold)  # SIL* absent from cold -> silence

    record = run_market_universe(
        store, _source(client), "US", SESSIONS[-1],
        now=_now_after(SESSIONS[-1]), digests_dir=tmp_path,
    )

    assert record.status == "quarantined"
    summary = summarize_pull(record, store.run_failures("US", SESSIONS[-1]))
    assert "quarantined run" in summary
    assert "90/100" in summary
    assert "10 silent and counted against the gate" in summary
    assert "SIL0" in summary
