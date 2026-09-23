from datetime import date, datetime

import pytest

from screener.pipeline import run_market
from screener.store import Store


@pytest.fixture
def store() -> Store:
    s = Store.memory()
    yield s
    s.close()


@pytest.fixture
def seeded_store(store: Store) -> Store:
    """A fixture store with two published IDX sessions and one US session."""
    run_market(
        store, "IDX", date(2026, 8, 3),
        enumerated=[f"S{i}" for i in range(100)],
        resolved=[f"S{i}" for i in range(100)],
        now=datetime(2026, 8, 3, 19, 30),
    )
    run_market(
        store, "IDX", date(2026, 8, 4),
        enumerated=[f"S{i}" for i in range(100)],
        resolved=[f"S{i}" for i in range(100)],
        now=datetime(2026, 8, 4, 19, 30),
    )
    run_market(
        store, "US", date(2026, 8, 4),
        enumerated=[f"U{i}" for i in range(200)],
        resolved=[f"U{i}" for i in range(200)],
        now=datetime(2026, 8, 4, 22, 10),
    )
    return store


def answered_row(symbol: str) -> dict:
    """A raw source row as the provider emits it, for a **settled** session.

    Stands in for "the provider answered with bars", which now means a newest bar
    whose close printed in both series: a payload carrying only the scaffolding
    of a session is silence, not a resolution
    (:func:`screener.bars.newest_bar_has_close`). The symbol rides in the row so
    a test can still tell two payloads apart.

    Shared because two pull-loop suites need exactly this row and nothing else;
    a suite that cares about a bar's *contents* still builds its own, which is
    why the per-file ``_row`` helpers elsewhere stay where they are.
    """
    return {
        "Date": date(2026, 9, 22),
        "Open": 10.0,
        "High": 11.0,
        "Low": 9.0,
        "Close": 10.5,
        "Adj Close": 10.5,
        "Volume": 1000,
        "row": symbol,
    }
