"""The real network boundary's exception mapping (:class:`YFinanceSourceClient`).

Everything above the source client is faked at the ``client.fetch`` seam
(``test_source_seam``), so the one thing those tests can never see is how the
*real* client turns a yfinance exception into a fetch outcome. That mapping is
the whole of issue #47's second half: going through ``Ticker.history`` surfaces
the typed refusal the old ``yfinance.download`` swallowed — but it also surfaces
every other error ``download`` used to turn into an empty frame, and a dead
ticker's ``YFPricesMissingError`` must stay silence, not kill the run.

yfinance is imported lazily inside the client's methods and is not installed in
the test environment, so these tests inject a fake ``yfinance`` module whose
``Ticker.history`` raises a chosen exception. The client matches on the
exception's class *name*, so a stand-in class with the right name is enough.
"""

import sys
import types

import pytest

from screener.source import (
    PermanentlyUnavailableError,
    RateLimitedError,
    YFinanceSourceClient,
)


class _FakeFrame:
    """The minimal DataFrame surface the client touches on the success path."""

    def __init__(self, records):
        self._records = records
        self.empty = not records

    class _Columns:
        nlevels = 1

    columns = _Columns()

    def reset_index(self):
        return self

    def to_dict(self, _orient):
        return self._records


def _install_fake_yfinance(monkeypatch, *, history):
    """Put a fake ``yfinance`` module in ``sys.modules`` whose ``Ticker.history``
    calls ``history(symbol)`` — which returns a frame or raises."""

    module = types.ModuleType("yfinance")
    module.config = types.SimpleNamespace(debug=types.SimpleNamespace(hide_exceptions=True))

    class Ticker:
        def __init__(self, symbol):
            self._symbol = symbol

        def history(self, *, period, auto_adjust):
            return history(self._symbol)

    module.Ticker = Ticker
    monkeypatch.setitem(sys.modules, "yfinance", module)


def _raise_named(name):
    """A history callback that raises an exception whose class name is ``name`` —
    the client matches on the class name, mirroring yfinance's own error types."""
    exc_type = type(name, (Exception,), {})

    def history(symbol):
        raise exc_type(f"{symbol}: {name}")

    return history


def test_dead_ticker_missing_prices_is_silence_not_a_crash(monkeypatch):
    # A delisted / dead ticker raises YFPricesMissingError where the old
    # download() returned an empty frame. It is the silence spec §3.2 is about,
    # so the client answers with an empty list — the run resolves it as one
    # unresolved symbol instead of dying on it (issue #47, reopened).
    _install_fake_yfinance(monkeypatch, history=_raise_named("YFPricesMissingError"))

    bars = YFinanceSourceClient().fetch("DEAD")

    assert bars == []


def test_any_unexpected_error_is_silence_not_a_crash(monkeypatch):
    # download() swallowed *every* fetch error into an empty frame; only the two
    # carve-outs below are special. Anything else stays silence so one bad
    # listing can never take the whole pull down with it.
    _install_fake_yfinance(monkeypatch, history=_raise_named("YFTzMissingError"))

    assert YFinanceSourceClient().fetch("ODD") == []


def test_rate_limit_error_becomes_retryable(monkeypatch):
    _install_fake_yfinance(monkeypatch, history=_raise_named("YFRateLimitError"))

    with pytest.raises(RateLimitedError):
        YFinanceSourceClient().fetch("THROTTLED")


def test_invalid_period_becomes_a_stated_refusal(monkeypatch):
    # "Period 'max' is invalid, must be one of: 1d, 5d" — the one error that is
    # an answer, not silence. It must stay a refusal so it is answered once.
    _install_fake_yfinance(monkeypatch, history=_raise_named("YFInvalidPeriodError"))

    with pytest.raises(PermanentlyUnavailableError):
        YFinanceSourceClient().fetch("CAIIW")


def test_bars_return_flattened_records(monkeypatch):
    rows = [{"Date": "2026-08-01", "Close": 10.0}]
    _install_fake_yfinance(monkeypatch, history=lambda symbol: _FakeFrame(rows))

    assert YFinanceSourceClient().fetch("AAPL") == rows
