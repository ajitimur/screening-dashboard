"""Seam 1: seed a fixture store, run something, assert on rows.

This is the store-discipline seam every pipeline ticket writes its unit tests
against (spec §7.2). It also pins the two non-negotiable properties: append-only
(no rewrite of a written session) and quarantine below the resolution floor.
"""

from datetime import date, datetime

import pytest

from screener.pipeline import RESOLUTION_FLOOR, run_market
from screener.store import SessionExistsError, Store


def test_run_writes_run_and_universe_rows(store: Store):
    record = run_market(
        store, "US", date(2026, 8, 4),
        enumerated=["AAA", "BBB", "CCC"],
        resolved=["AAA", "BBB", "CCC"],
        now=datetime(2026, 8, 4, 22, 10),
    )

    assert record.status == "published"
    assert record.symbols_resolved == 3
    assert store.universe("US", date(2026, 8, 4)) == ["AAA", "BBB", "CCC"]
    assert store.latest_run("US") == record


def test_tonight_is_the_max_session(seeded_store: Store):
    assert seeded_store.latest_run("IDX").session == date(2026, 8, 4)
    assert [r.session for r in seeded_store.runs("IDX")] == [
        date(2026, 8, 4),
        date(2026, 8, 3),
    ]


def test_rewriting_a_session_is_refused(store: Store):
    run_market(
        store, "IDX", date(2026, 8, 4),
        enumerated=["X"], resolved=["X"], now=datetime(2026, 8, 4, 19, 30),
    )
    with pytest.raises(SessionExistsError):
        run_market(
            store, "IDX", date(2026, 8, 4),
            enumerated=["X", "Y"], resolved=["X", "Y"],
            now=datetime(2026, 8, 4, 19, 35),
        )
    # The original rows survive the refused rewrite untouched.
    assert store.universe("IDX", date(2026, 8, 4)) == ["X"]


def test_run_below_resolution_floor_is_quarantined_and_writes_no_universe(store: Store):
    enumerated = [f"S{i}" for i in range(100)]
    resolved = enumerated[:90]  # 90% < 99% floor
    assert len(resolved) < RESOLUTION_FLOOR * len(enumerated)

    record = run_market(
        store, "US", date(2026, 8, 5),
        enumerated=enumerated, resolved=resolved,
        now=datetime(2026, 8, 5, 22, 10),
    )

    assert record.status == "quarantined"
    # A quarantined run must not replace good data: no universe rows, and it is
    # not the as-of session the tab would render.
    assert store.universe("US", date(2026, 8, 5)) == []
    assert store.latest_run("US") is None
