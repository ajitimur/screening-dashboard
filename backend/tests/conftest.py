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
