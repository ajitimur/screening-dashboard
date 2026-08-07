"""Seam 2 (v2): the /api/leaders/{market} endpoint, and /api/boards kept as its
alias (spec §4.4 / §10.2, issue #76).

``Boards`` is renamed **Leaders** — the name *Board* now belongs to the composite
home screen, so leaving ``/api/boards`` behind under its old meaning is the worst
outcome. The endpoint and its models rename to ``leaders`` / ``Leader`` /
``LeaderRow`` / ``LeadersResponse``, and ``/api/boards`` stays an alias for the
branch's lifetime so the whole backend lands on ``main`` ahead of any frontend
work without breaking v1 (spec §10.2 constraint 1).

Two phase-1 leaders-row fields land here — ``sector`` and ``dollar_volume`` —
both cheap: the read already loads exactly these names' bars for the ADR column,
and sector is a store lookup (spec §4.4). ``tier``, ``rs_pctile`` and a
per-lookback ``cutoffs`` block are typed nullable phase-2 and return null.
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


def test_leaders_endpoint_returns_five_boards(seeded_store: Store):
    body = client_for(seeded_store).get("/api/leaders/IDX").json()
    assert body["market"] == "IDX"
    assert [b["lookback"] for b in body["boards"]] == list(LOOKBACKS)


def test_boards_alias_responds_identically(seeded_store: Store):
    # The alias is what lets the backend land on main without breaking v1: both
    # paths serve the same session's boards, byte-for-byte (spec §10.2).
    client = client_for(seeded_store)
    assert client.get("/api/boards/IDX").json() == client.get("/api/leaders/IDX").json()


def test_leaders_endpoint_empty_state_when_no_run(store: Store):
    body = client_for(store).get("/api/leaders/US").json()
    assert body["session"] is None
    assert body["boards"] == []


def test_unknown_market_is_404(store: Store):
    assert client_for(store).get("/api/leaders/LSE").status_code == 404


def test_rows_carry_sector_and_dollar_volume(store: Store):
    session = date(2026, 8, 4)
    _publish(store, "US", session)
    store.append_bars("US", "WIN", _flat_bars(140.0))
    store.upsert_label("US", "WIN", "Technology", "Semiconductors", session)
    store.append_ranks("US", session, [Rank("WIN", "1w", 1.0, 0.40)])

    row = next(
        b for b in client_for(store).get("/api/leaders/US").json()["boards"]
        if b["lookback"] == "1w"
    )["rows"][0]
    assert row["symbol"] == "WIN"
    assert row["sector"] == "Technology"  # a store lookup
    # median close×volume over the trailing window: 100 × 1000.
    assert row["dollar_volume"] == 100_000.0


def test_sector_is_null_when_label_never_fetched(store: Store):
    session = date(2026, 8, 4)
    _publish(store, "US", session)
    store.append_bars("US", "NOLABEL", _flat_bars(140.0))
    store.append_ranks("US", session, [Rank("NOLABEL", "1w", 1.0, 0.40)])

    row = next(
        b for b in client_for(store).get("/api/leaders/US").json()["boards"]
        if b["lookback"] == "1w"
    )["rows"][0]
    assert row["sector"] is None


def test_phase2_fields_are_typed_null(store: Store):
    session = date(2026, 8, 4)
    _publish(store, "US", session)
    store.append_bars("US", "WIN", _flat_bars(140.0))
    store.append_ranks("US", session, [Rank("WIN", "1w", 1.0, 0.40)])

    board = next(
        b for b in client_for(store).get("/api/leaders/US").json()["boards"]
        if b["lookback"] == "1w"
    )
    # cutoffs sits beside the rows, one block per lookback board — never repeated
    # on every row (spec §4.4). Phase-2, so null now.
    assert board["cutoffs"] is None
    row = board["rows"][0]
    assert row["tier"] is None
    assert row["rs_pctile"] is None
