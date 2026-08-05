"""Seam 7b: the /api/sectors/{market} endpoint, store-driven end to end.

Builds a fixture store with a published run, a rank table and a label cache,
then asserts the sector and industry boards on the payload (spec §4.4 / §7.5).
"""

from datetime import date, datetime

from fastapi.testclient import TestClient

from screener.app import create_app
from screener.ranks import Rank
from screener.store import Store

SESSION = date(2026, 8, 4)


def client_for(store: Store) -> TestClient:
    return TestClient(create_app(store=store))


def _publish(store: Store, market: str, session: date, symbols: list[str]) -> None:
    store.append_universe(market, session, symbols)
    store.append_run(
        market, session, status="published",
        symbols_enumerated=len(symbols), symbols_resolved=len(symbols),
        created_at=datetime(2026, 8, 4, 19, 30),
    )


def test_empty_state_still_renders_all_eleven_sectors(store: Store):
    body = client_for(store).get("/api/sectors/IDX").json()
    assert body["session"] is None
    assert len(body["sectors"]) == 11
    assert all(s["members"] == 0 for s in body["sectors"])
    assert body["industries"] == []


def test_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/sectors/LSE").status_code == 404


def test_sector_board_carries_shares_and_the_k_over_n_badge(store: Store):
    symbols = [f"S{i}" for i in range(4)]
    _publish(store, "IDX", SESSION, symbols)
    # Four Energy names, one top-decile on 1w -> share 1/4, k=1 n=4.
    rows = [Rank("S0", "1w", 0.95, 0.0)]
    rows += [Rank(s, "1w", 0.5, 0.0) for s in symbols[1:]]
    store.append_ranks("IDX", SESSION, rows)
    for s in symbols:
        store.upsert_label("IDX", s, "Energy", "Thermal Coal", SESSION)

    body = client_for(store).get("/api/sectors/IDX").json()
    assert body["session"] == "2026-08-04"
    energy = next(s for s in body["sectors"] if s["sector"] == "Energy")
    assert energy["members"] == 4
    assert energy["decile_counts"]["1w"] == 1
    assert abs(energy["shares"]["1w"] - 0.25) < 1e-9
    assert energy["rotation_eligible"] is False  # one name is not a rotation


def test_industry_board_ranks_only_ten_or_more(store: Store):
    big = [f"B{i}" for i in range(10)]
    small = [f"M{i}" for i in range(5)]
    _publish(store, "US", SESSION, big + small)
    rows = [Rank(s, "1w", 0.95 if i < 3 else 0.5, 0.0) for i, s in enumerate(big)]
    rows += [Rank(s, "1w", 0.95, 0.0) for s in small]
    store.append_ranks("US", SESSION, rows)
    for s in big:
        store.upsert_label("US", s, "Healthcare", "Biotechnology", SESSION)
    for s in small:
        store.upsert_label("US", s, "Technology", "Solar", SESSION)

    body = client_for(store).get("/api/sectors/US").json()
    assert [i["industry"] for i in body["industries"]] == ["Biotechnology"]
    bio = body["industries"][0]
    assert bio["members"] == 10
    assert bio["sector"] == "Healthcare"


def test_temporal_delta_differences_against_twenty_sessions_ago(store: Store):
    from datetime import timedelta

    cal = [SESSION - timedelta(days=20 - i) for i in range(21)]  # 21 sessions
    symbols = ["A", "B", "C", "D"]
    for s in symbols:
        store.upsert_label("IDX", s, "Energy", "Thermal Coal", cal[-1])
    # Past (session 0): 1 of 4 in the 1m decile. Now (session 20): 3 of 4.
    for i, session in enumerate(cal):
        strong = 3 if i == 20 else 1
        rows = [
            Rank(s, "1m", 0.95 if j < strong else 0.5, 0.0)
            for j, s in enumerate(symbols)
        ]
        store.append_ranks("IDX", session, rows)
    _publish(store, "IDX", cal[-1], symbols)

    body = client_for(store).get("/api/sectors/IDX").json()
    energy = next(s for s in body["sectors"] if s["sector"] == "Energy")
    # now 3/4 = 0.75, past 1/4 = 0.25 -> +0.50.
    assert abs(energy["temporal_delta"] - 0.5) < 1e-9


def test_temporal_delta_is_null_without_twenty_sessions(store: Store):
    symbols = ["A", "B"]
    _publish(store, "IDX", SESSION, symbols)
    store.append_ranks("IDX", SESSION, [Rank(s, "1m", 0.95, 0.0) for s in symbols])
    for s in symbols:
        store.upsert_label("IDX", s, "Energy", "Thermal Coal", SESSION)
    body = client_for(store).get("/api/sectors/IDX").json()
    energy = next(s for s in body["sectors"] if s["sector"] == "Energy")
    assert energy["temporal_delta"] is None
