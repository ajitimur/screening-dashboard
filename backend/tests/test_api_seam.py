"""Seam 2: hit an endpoint via TestClient against a fixture store.

This is the API-contract seam every read-endpoint ticket writes its tests
against (spec §7.5). The app is constructed against an in-memory fixture store,
so the payload is asserted without touching the on-disk file.
"""

from fastapi.testclient import TestClient

from screener.app import create_app
from screener.store import Store


def client_for(store: Store) -> TestClient:
    return TestClient(create_app(store=store))


def test_runs_endpoint_returns_as_of_session(seeded_store: Store):
    client = client_for(seeded_store)

    resp = client.get("/api/runs/IDX")
    assert resp.status_code == 200
    body = resp.json()

    assert body["market"] == "IDX"
    assert body["latest"]["session"] == "2026-08-04"
    assert body["latest"]["status"] == "published"
    assert [r["session"] for r in body["runs"]] == ["2026-08-04", "2026-08-03"]


def test_runs_endpoint_empty_state_when_no_run(store: Store):
    # No run has published yet — the tab shows an explicit empty state.
    body = client_for(store).get("/api/runs/US").json()
    assert body["latest"] is None
    assert body["runs"] == []


def test_market_is_case_insensitive(seeded_store: Store):
    assert client_for(seeded_store).get("/api/runs/idx").json()["latest"]["session"] == "2026-08-04"


def test_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/runs/LSE").status_code == 404
