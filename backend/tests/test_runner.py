"""The run-on-open coordinator: a single-flight background run per market.

``RunManager`` is what the tab's run-on-open drives (spec §7.3). It runs one
market's pipeline in the background, tracks its status so the UI can show a
progress state, and refuses to start a second run for a market already running —
so a run in progress never double-fires or leaves the UI showing a half-written
session.
"""

import threading
from datetime import date

import pytest

from screener.runner import RunManager


def test_trigger_runs_the_market_and_returns_to_idle():
    ran: list[str] = []
    manager = RunManager(lambda market: ran.append(market))

    assert manager.status("IDX") == "idle"
    assert manager.trigger("IDX") is True
    manager.join("IDX")

    assert ran == ["IDX"]
    assert manager.status("IDX") == "idle"
    assert manager.is_running("IDX") is False


def test_trigger_is_single_flight_per_market():
    started = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def runner(market: str) -> None:
        calls.append(market)
        started.set()
        release.wait(timeout=5)

    manager = RunManager(runner)
    assert manager.trigger("IDX") is True
    assert started.wait(timeout=5)
    # While IDX is mid-run it reports running, and a second trigger is refused.
    assert manager.is_running("IDX") is True
    assert manager.trigger("IDX") is False

    release.set()
    manager.join("IDX")
    assert calls == ["IDX"]  # the refused trigger never ran the pipeline again


def test_markets_run_independently():
    release = threading.Event()

    def runner(market: str) -> None:
        release.wait(timeout=5)

    manager = RunManager(runner)
    assert manager.trigger("IDX") is True
    # US is not blocked by IDX being mid-run — one job per market.
    assert manager.trigger("US") is True
    assert manager.is_running("IDX") is True
    assert manager.is_running("US") is True

    release.set()
    manager.join("IDX")
    manager.join("US")


def test_a_failed_run_is_recorded_and_the_market_is_runnable_again():
    def boom(market: str) -> None:
        raise RuntimeError("pull throttled")

    manager = RunManager(boom)
    assert manager.trigger("IDX") is True
    manager.join("IDX")

    assert manager.status("IDX") == "failed"
    assert manager.is_running("IDX") is False
    # A failed run does not wedge the market: the running flag was cleared, so
    # trigger accepts a retry (which booms again — still not wedged).
    assert manager.trigger("IDX") is True
    manager.join("IDX")
    assert manager.status("IDX") == "failed"


def test_trigger_recompute_drives_the_recompute_runner_with_its_session():
    # The operator override (issue #111): trigger_recompute runs the second
    # callable, handing it the market and the session to correct.
    calls: list[tuple[str, date | None]] = []
    manager = RunManager(
        lambda market: calls.append((market, "run")),
        lambda market, session: calls.append((market, session)),
    )

    assert manager.trigger_recompute("IDX", date(2026, 8, 5)) is True
    manager.join("IDX")

    assert calls == [("IDX", date(2026, 8, 5))]
    assert manager.status("IDX") == "idle"


def test_recompute_shares_the_single_flight_flag_with_run_on_open():
    # A recompute and a run-on-open of the same market must not race: whichever is
    # in flight blocks the other rather than both writing the session at once.
    started = threading.Event()
    release = threading.Event()

    def slow_run(market: str) -> None:
        started.set()
        release.wait(timeout=5)

    manager = RunManager(slow_run, lambda market, session: None)
    assert manager.trigger("IDX") is True
    assert started.wait(timeout=5)
    # The run-on-open holds the flag, so a recompute is refused mid-run.
    assert manager.trigger_recompute("IDX") is False

    release.set()
    manager.join("IDX")


def test_trigger_recompute_without_a_runner_is_an_error():
    manager = RunManager(lambda market: None)  # no recompute runner wired
    with pytest.raises(RuntimeError):
        manager.trigger_recompute("IDX")
