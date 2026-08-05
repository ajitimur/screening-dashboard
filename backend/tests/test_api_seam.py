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
    assert body["universe_size"] is None


def test_runs_endpoint_surfaces_tonights_universe_size(store: Store):
    # The market tab shows tonight's universe size (ticket 31 acceptance).
    from datetime import date, datetime

    from screener.pipeline import run_market

    run_market(
        store, "IDX", date(2026, 8, 4),
        enumerated=["AAA", "BBB", "CCC"], resolved=["AAA", "BBB", "CCC"],
        now=datetime(2026, 8, 4, 19, 30),
    )
    body = client_for(store).get("/api/runs/IDX").json()
    assert body["universe_size"] == 3


def test_market_is_case_insensitive(seeded_store: Store):
    assert client_for(seeded_store).get("/api/runs/idx").json()["latest"]["session"] == "2026-08-04"


def test_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/runs/LSE").status_code == 404


# -- /api/regime/{market} (ticket 36, spec §4.9) ------------------------------


def _regime_store() -> Store:
    """A store with a friendly IDX index and a universe of two members — one
    riding above rising MAs, one flat — plus a published run."""
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.pipeline import run_market

    store = Store.memory()
    cal = [date(2026, 6, 1) + timedelta(days=i) for i in range(30)]
    session = cal[-1]

    def bars(adj):
        return [Bar(s, c, c + 1, c - 1, c, c, 1000) for s, c in zip(cal, adj)]

    store.append_bars("IDX", "^JKSE", bars([100.0 + i for i in range(30)]))  # rising
    store.append_bars("IDX", "UP", bars([100.0 + i for i in range(30)]))     # friendly
    store.append_bars("IDX", "FLAT", bars([100.0] * 30))                     # not
    # run_market writes the universe (= the resolved members) as it publishes.
    run_market(
        store, "IDX", session,
        enumerated=["UP", "FLAT"], resolved=["UP", "FLAT"],
        now=datetime(2026, 6, 30, 19, 30),
    )
    return store


def test_regime_endpoint_reports_state_posture_breadth_and_session():
    store = _regime_store()
    try:
        body = client_for(store).get("/api/regime/IDX").json()
        assert body["market"] == "IDX"
        assert body["session"] == "2026-06-30"
        assert body["state"] == "FRIENDLY"          # the index is in a clean uptrend
        assert body["posture"] == "full size"       # words, not a number
        assert body["breadth"] == 0.5               # 1 of 2 members above rising MAs
    finally:
        store.close()


def test_regime_endpoint_is_empty_when_no_run_published(store: Store):
    body = client_for(store).get("/api/regime/US").json()
    assert body == {
        "market": "US", "session": None, "state": None,
        "posture": None, "breadth": None,
    }


def test_regime_state_undefined_below_the_warmup(store: Store):
    from datetime import date, datetime, timedelta

    from screener.bars import Bar
    from screener.pipeline import run_market

    cal = [date(2026, 6, 1) + timedelta(days=i) for i in range(10)]  # < 25 bars
    session = cal[-1]
    store.append_bars("IDX", "^JKSE", [Bar(s, 100.0, 101.0, 99.0, 100.0, 100.0, 1000) for s in cal])
    run_market(
        store, "IDX", session, enumerated=["AAA"], resolved=["AAA"],
        now=datetime(2026, 6, 10, 19, 30),
    )
    body = client_for(store).get("/api/regime/IDX").json()
    assert body["session"] == "2026-06-10"
    assert body["state"] is None        # undefined, not defaulted
    assert body["posture"] is None      # an undefined regime advises nothing


def test_regime_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/regime/LSE").status_code == 404


# -- /api/candidates/{market} (ticket 38, spec §4.5 / §5.1) -------------------


def _candidates_store() -> Store:
    """A store with a published US run and two detections — one tight (affordable)
    stop, one wide — plus ranks and one industry label."""
    from datetime import date, datetime

    from screener.detection import DETECTOR_VERSION, Detection
    from screener.ranks import Rank

    store = Store.memory()
    session = date(2026, 8, 5)
    store.append_run(
        "US", session, status="published",
        symbols_enumerated=2, symbols_resolved=2,
        created_at=datetime(2026, 8, 5, 22, 10),
    )
    store.append_universe("US", session, ["AAA", "ZZZ"])

    def det(symbol, cluster_low, adr=0.02):
        adr_abs = adr * 98.0
        stop = 100.0 - cluster_low
        return Detection(
            symbol=symbol, session=session, detector_version=DETECTOR_VERSION,
            trigger=100.0, stop=stop, stopw_adr=stop / adr_abs,
            base_len=30, move_gain=103.0, adr=adr, close=98.0,
            cluster_k=5, cluster_high=100.0, cluster_low=cluster_low,
            cluster_range_adr=0.99, line_ok=True, touch_zones=2, overshoot_adr=0.0,
            slope=-0.001, line_end=99.9, base_low=cluster_low,
        )

    # ZZZ: cluster_low 99.0 → stop 1.0 / adr_abs 1.96 ≈ 0.51 (affordable).
    # AAA: cluster_low 95.0 → stop 5.0 / adr_abs 1.96 ≈ 2.55 (the majority).
    store.append_detections("US", session, [det("AAA", 95.0), det("ZZZ", 99.0)])
    store.append_ranks("US", session, [
        Rank("AAA", "1m", 0.95, 1.2), Rank("AAA", "3m", 0.95, 1.1),
    ])
    store.upsert_label("US", "AAA", "Technology", "Semiconductors", session)
    return store


def test_candidates_endpoint_returns_ticker_ordered_five_column_rows():
    store = _candidates_store()
    try:
        body = client_for(store).get("/api/candidates/US").json()
        assert body["market"] == "US"
        assert body["session"] == "2026-08-05"
        # Ordered by ticker; the score sort is not yet live (ticket 39).
        assert body["ordered_by"] == "ticker"
        assert [c["symbol"] for c in body["candidates"]] == ["AAA", "ZZZ"]

        aaa = body["candidates"][0]
        assert aaa["score"] is None                 # placeholder until the rubric lands
        assert aaa["industry"] == "Semiconductors"  # the theme layer
        assert aaa["breadth"] == 2                   # top-decile in 2 of 5 lookbacks
        assert abs(aaa["dist_adr"] - (100.0 - 98.0) / (0.02 * 98.0)) < 1e-9
    finally:
        store.close()


def test_candidates_stop_column_flags_the_affordable_minority_and_filters_nothing():
    store = _candidates_store()
    try:
        rows = client_for(store).get("/api/candidates/US").json()["candidates"]
        assert len(rows) == 2  # the stop column never filters
        by_sym = {c["symbol"]: c for c in rows}
        assert by_sym["ZZZ"]["affordable"] is True   # sub-1×ADR, highlighted
        assert by_sym["AAA"]["affordable"] is False  # the wide majority
    finally:
        store.close()


def test_candidates_endpoint_is_empty_when_no_run_published(store: Store):
    body = client_for(store).get("/api/candidates/US").json()
    assert body == {
        "market": "US", "session": None, "ordered_by": "ticker", "candidates": [],
    }


def test_candidates_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/candidates/LSE").status_code == 404
