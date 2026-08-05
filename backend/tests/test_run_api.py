"""Run-on-open through the API seam (spec §7.3, ticket 43).

The runs endpoint tells the tab whether a run is *due* (its last final session
is missing) and whether one is *running*; ``POST /api/runs/{market}`` kicks the
background run. The clock is pinned so ``run_due`` is deterministic.
"""

import threading
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from screener.app import create_app
from screener.pipeline import run_market
from screener.runner import RunManager
from screener.store import Store


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


def _publish(store: Store, market: str, session: date, now: datetime) -> None:
    run_market(
        store, market, session,
        enumerated=[f"S{i}" for i in range(100)],
        resolved=[f"S{i}" for i in range(100)],
        now=now,
    )


# A clock well past the 2026-08-05 IDX close (20:00 WIB == 13:00 UTC), so the
# last final IDX session is 2026-08-05.
FIXED_NOW = datetime(2026, 8, 5, 13, 0, tzinfo=timezone.utc)


def test_run_due_true_when_the_last_final_session_is_missing(store: Store):
    _publish(store, "IDX", date(2026, 8, 4), datetime(2026, 8, 4, 19, 30))
    app = create_app(store=store, clock=lambda: FIXED_NOW)
    body = TestClient(app).get("/api/runs/IDX").json()
    assert body["run_due"] is True
    assert body["running"] is False


def test_run_due_false_when_the_store_has_the_last_final_session(store: Store):
    _publish(store, "IDX", date(2026, 8, 5), datetime(2026, 8, 5, 19, 30))
    app = create_app(store=store, clock=lambda: FIXED_NOW)
    body = TestClient(app).get("/api/runs/IDX").json()
    assert body["run_due"] is False


def test_run_due_true_when_no_run_has_published(store: Store):
    app = create_app(store=store, clock=lambda: FIXED_NOW)
    body = TestClient(app).get("/api/runs/US").json()
    assert body["latest"] is None
    assert body["run_due"] is True


def test_post_triggers_a_run_and_reports_running(store: Store):
    release = threading.Event()
    started = threading.Event()

    def runner(market: str) -> None:
        started.set()
        release.wait(timeout=5)

    manager = RunManager(runner)
    app = create_app(store=store, run_manager=manager, clock=lambda: FIXED_NOW)
    client = TestClient(app)

    resp = client.post("/api/runs/IDX")
    assert resp.status_code == 200
    assert resp.json() == {"market": "IDX", "triggered": True, "running": True}
    assert started.wait(timeout=5)

    # The GET now reports the run in flight, so the tab shows a progress state.
    assert client.get("/api/runs/IDX").json()["running"] is True
    # A second open mid-run joins rather than duplicating.
    assert client.post("/api/runs/IDX").json()["triggered"] is False

    release.set()
    manager.join("IDX")


def test_post_without_a_run_manager_is_503(store: Store):
    app = create_app(store=store, clock=lambda: FIXED_NOW)
    assert TestClient(app).post("/api/runs/IDX").status_code == 503


def test_post_unknown_market_is_404(store: Store):
    app = create_app(store=store, run_manager=RunManager(lambda m: None))
    assert TestClient(app).post("/api/runs/LSE").status_code == 404


def test_a_run_in_progress_never_serves_a_half_written_session(store: Store):
    # A published session, then a *newer* session's derived rows land — as they
    # would mid-run — but no run record has published for it yet. Every read
    # keys off the last published run (spec §7.2), so the tab still serves the
    # older, complete session: a run in progress never shows a half-written one.
    _publish(store, "IDX", date(2026, 8, 4), datetime(2026, 8, 4, 19, 30))
    store.append_universe("IDX", date(2026, 8, 5), ["AAA", "BBB"])  # half-written

    app = create_app(store=store, clock=lambda: FIXED_NOW)
    body = TestClient(app).get("/api/runs/IDX").json()
    # The served as-of session is still the last *published* one, not the
    # in-flight one whose derived rows are already on disk.
    assert body["latest"]["session"] == "2026-08-04"
    assert body["universe_size"] == 100  # the published session's universe
    # ...and it is flagged run_due, so the tab shows the run is still needed.
    assert body["run_due"] is True
