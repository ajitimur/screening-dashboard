"""The run-on-open coordinator: a single-flight background run per market.

``RunManager`` is what the tab's run-on-open drives (spec §7.3). It runs one
market's pipeline in the background, tracks its status so the UI can show a
progress state, and refuses to start a second run for a market already running —
so a run in progress never double-fires or leaves the UI showing a half-written
session.
"""

import threading

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
