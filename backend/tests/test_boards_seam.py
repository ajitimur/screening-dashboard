"""Seam 2: the /api/boards/{market} endpoint against a fixture store.

The boards are a read-time cut of the persisted rank table (spec §5.2): the
endpoint reads tonight's ranks, last session's ranks (for the ``NEW`` marker) and
each board member's bars (for the ADR column), and returns five boards of up to
30 rows. This seam drives it end to end through TestClient.
"""

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from screener.app import create_app
from screener.bars import Bar
from screener.indicators import LOOKBACKS
from screener.ranks import Rank
from screener.store import Store


def client_for(store: Store) -> TestClient:
    return TestClient(create_app(store=store))


def _flat_bars(symbol_last_adj, n=25):
    """A 25-bar series with a fixed range (ADR ≈ 2/100) ending at a given close."""
    cal = [date(2026, 7, 1) + timedelta(days=i) for i in range(n)]
    series = [Bar(s, 100.0, 101.0, 99.0, 100.0, 100.0, 1000) for s in cal[:-1]]
    series.append(Bar(cal[-1], 100.0, 101.0, 99.0, 100.0, symbol_last_adj, 1000))
    return series


def _publish(store: Store, market: str, session: date) -> None:
    store.append_run(
        market, session, status="published",
        symbols_enumerated=3, symbols_resolved=3, created_at=datetime(2026, 8, 4, 20),
    )


def test_boards_endpoint_returns_five_boards(seeded_store: Store):
    body = client_for(seeded_store).get("/api/boards/IDX").json()
    assert body["market"] == "IDX"
    assert [b["lookback"] for b in body["boards"]] == list(LOOKBACKS)


def test_boards_endpoint_empty_state_when_no_run(store: Store):
    body = client_for(store).get("/api/boards/US").json()
    assert body["session"] is None
    assert body["boards"] == []


def test_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/boards/LSE").status_code == 404


def test_boards_rank_on_raw_return_and_carry_furniture(store: Store):
    session = date(2026, 8, 4)
    _publish(store, "US", session)
    # Three names, WIN > MID > LOW on 1w; WIN also tops the 3m decile (breadth 2).
    store.append_bars("US", "WIN", _flat_bars(140.0))
    store.append_bars("US", "MID", _flat_bars(120.0))
    store.append_bars("US", "LOW", _flat_bars(105.0))
    rows = [
        Rank("WIN", "1w", 1.0, 0.40), Rank("WIN", "3m", 0.95, 0.9),
        Rank("MID", "1w", 0.66, 0.20),
        Rank("LOW", "1w", 0.33, 0.05),
    ]
    store.append_ranks("US", session, rows)

    body = client_for(store).get("/api/boards/US").json()
    one_w = next(b for b in body["boards"] if b["lookback"] == "1w")
    syms = [r["symbol"] for r in one_w["rows"]]
    assert syms == ["WIN", "MID", "LOW"]  # sorted by raw return, highest first

    win = one_w["rows"][0]
    assert win["raw_return"] == 0.40
    assert win["breadth"] == 2  # top-decile in 1w and 3m
    assert win["surge"] is True  # up ≥30% over the week
    assert win["adr"] is not None  # the ADR column rides the row
    assert one_w["rows"][1]["surge"] is False  # MID up only 20%


def test_new_marker_diffs_against_last_session(store: Store):
    yday, today = date(2026, 8, 3), date(2026, 8, 4)
    _publish(store, "US", today)
    for s in ("STAY", "FRESH"):
        store.append_bars("US", s, _flat_bars(130.0))
    store.append_ranks("US", yday, [Rank("STAY", "1w", 0.9, 0.5)])
    store.append_ranks("US", today, [
        Rank("STAY", "1w", 0.9, 0.5), Rank("FRESH", "1w", 0.8, 0.4),
    ])

    one_w = next(
        b for b in client_for(store).get("/api/boards/US").json()["boards"]
        if b["lookback"] == "1w"
    )
    by_symbol = {r["symbol"]: r for r in one_w["rows"]}
    assert by_symbol["STAY"]["is_new"] is False
    assert by_symbol["FRESH"]["is_new"] is True
