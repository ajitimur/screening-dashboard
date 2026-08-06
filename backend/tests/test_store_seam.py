"""Seam 1: seed a fixture store, run something, assert on rows.

This is the store-discipline seam every pipeline ticket writes its unit tests
against (spec §7.2). It also pins the two non-negotiable properties: append-only
(no rewrite of a written session) and quarantine below the resolution floor.
"""

from datetime import date, datetime

import duckdb
import pytest

from screener.pipeline import ENUMERATION_FLOOR, RESOLUTION_FLOOR, run_market
from screener.store import (
    SCHEMA_VERSION,
    SchemaDriftError,
    SessionExistsError,
    Store,
)


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


def test_materially_smaller_enumeration_is_quarantined_at_full_resolution(store: Store):
    # A good baseline of 100 enumerated names, all resolving.
    baseline = [f"S{i}" for i in range(100)]
    run_market(
        store, "US", date(2026, 8, 4),
        enumerated=baseline, resolved=baseline,
        now=datetime(2026, 8, 4, 22, 10),
    )
    # Next night the enumeration is truncated to 70 — every one resolves, so the
    # completeness gate passes at 100%, but the denominator itself moved (spec
    # §3.4 rule 8). A shrunk universe must fail, not silently publish.
    truncated = [f"S{i}" for i in range(70)]
    assert len(truncated) < ENUMERATION_FLOOR * len(baseline)

    record = run_market(
        store, "US", date(2026, 8, 5),
        enumerated=truncated, resolved=truncated,
        now=datetime(2026, 8, 5, 22, 10),
    )

    assert record.status == "quarantined"
    assert record.symbols_resolved == record.symbols_enumerated  # 100% resolved
    assert store.universe("US", date(2026, 8, 5)) == []
    # The last good run keeps serving behind the banner.
    assert store.latest_run("US").session == date(2026, 8, 4)


def test_modest_enumeration_shrinkage_within_tolerance_still_publishes(store: Store):
    # Enumeration counts breathe with real listings; a small drop is not a failed
    # run. 96 of a 100-name baseline stays above the floor and publishes.
    baseline = [f"S{i}" for i in range(100)]
    run_market(
        store, "US", date(2026, 8, 4),
        enumerated=baseline, resolved=baseline,
        now=datetime(2026, 8, 4, 22, 10),
    )
    smaller = [f"S{i}" for i in range(96)]
    assert len(smaller) >= ENUMERATION_FLOOR * len(baseline)

    record = run_market(
        store, "US", date(2026, 8, 5),
        enumerated=smaller, resolved=smaller,
        now=datetime(2026, 8, 5, 22, 10),
    )
    assert record.status == "published"
    assert store.latest_run("US").session == date(2026, 8, 5)


def test_enumeration_baseline_is_the_last_good_run_not_a_quarantined_one(store: Store):
    # The baseline for the shrink check is the last *published* run. A quarantined
    # run in between must not lower the bar, or a slow leak of shrinking pulls
    # would each pass against the previous (already shrunk) attempt.
    baseline = [f"S{i}" for i in range(100)]
    run_market(
        store, "US", date(2026, 8, 4),
        enumerated=baseline, resolved=baseline,
        now=datetime(2026, 8, 4, 22, 10),
    )
    truncated = [f"S{i}" for i in range(70)]
    run_market(
        store, "US", date(2026, 8, 5),
        enumerated=truncated, resolved=truncated,
        now=datetime(2026, 8, 5, 22, 10),
    )  # quarantined
    # A third night still shrunk vs the 100-name baseline is quarantined again,
    # even though it is *larger* than the quarantined 70.
    still_short = [f"S{i}" for i in range(80)]
    record = run_market(
        store, "US", date(2026, 8, 6),
        enumerated=still_short, resolved=still_short,
        now=datetime(2026, 8, 6, 22, 10),
    )
    assert record.status == "quarantined"
    assert store.latest_run("US").session == date(2026, 8, 4)


def test_quarantine_is_per_market(store: Store):
    # US quarantining leaves IDX's published session serving (spec §3.4 rule 7).
    idx = [f"I{i}" for i in range(100)]
    run_market(
        store, "IDX", date(2026, 8, 5),
        enumerated=idx, resolved=idx,
        now=datetime(2026, 8, 5, 19, 30),
    )
    us_enum = [f"U{i}" for i in range(100)]
    run_market(
        store, "US", date(2026, 8, 5),
        enumerated=us_enum, resolved=us_enum[:50],  # throttled, well below floor
        now=datetime(2026, 8, 5, 22, 10),
    )
    assert store.latest_run("US") is None
    assert store.latest_run("IDX").session == date(2026, 8, 5)


# -- opening a database that older code created ------------------------------


def test_a_store_from_older_code_is_brought_up_to_the_current_schema(tmp_path):
    # The schema only ever says "create if absent", so a table that already
    # exists keeps the shape it was born with. Opening such a store must
    # reconcile it rather than leave a narrower table for a later write to die
    # on, minutes into a pull (issue #49).
    path = tmp_path / "old.duckdb"
    con = duckdb.connect(str(path))
    # The detections table as an older version wrote it: without the star
    # score's three derived signals.
    con.execute(
        "CREATE TABLE detections (market TEXT NOT NULL, session DATE NOT NULL, "
        "symbol TEXT NOT NULL, detector_version INTEGER NOT NULL)"
    )
    con.close()

    store = Store.open(path)
    try:
        columns = {
            r[0]
            for r in store._con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'detections'"
            ).fetchall()
        }
        assert {"churn_l", "sma20_rising", "dryup"} <= columns
        # ...and the store now says on disk which schema it has been brought to.
        assert store._con.execute("SELECT version FROM schema_meta").fetchone()[0] == (
            SCHEMA_VERSION
        )
    finally:
        store.close()


def test_a_column_that_changed_type_is_refused_rather_than_reinterpreted(tmp_path):
    # Adding a column is safe; silently reading an old column as a new type is
    # not. That drift is a decision for a person, so it raises at open.
    path = tmp_path / "drifted.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE runs (market TEXT NOT NULL, session TEXT NOT NULL)")
    con.close()

    with pytest.raises(SchemaDriftError, match="runs.session"):
        Store.open(path)
