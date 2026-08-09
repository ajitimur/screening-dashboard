"""Seam 1: seed a fixture store, run something, assert on rows.

This is the store-discipline seam every pipeline ticket writes its unit tests
against (spec §7.2). It also pins the two non-negotiable properties: append-only
(no rewrite of a written session) and quarantine below the resolution floor.
"""

from datetime import date, datetime

import duckdb
import pytest

from screener.models import ResolutionFailure
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


# -- retrying a quarantined session (issue #103) ------------------------------


def test_last_run_is_the_last_row_of_any_status(store: Store):
    # ``latest_run`` answers "what does the tab render" and so skips quarantines;
    # the scheduler needs the other question — "what has this market already
    # written" — or a quarantined session looks absent and is pulled again from
    # scratch every firing.
    enumerated = [f"S{i}" for i in range(100)]
    run_market(
        store, "US", date(2026, 8, 4),
        enumerated=enumerated, resolved=enumerated,
        now=datetime(2026, 8, 4, 22, 10),
    )
    run_market(
        store, "US", date(2026, 8, 5),
        enumerated=enumerated, resolved=enumerated[:50],
        now=datetime(2026, 8, 5, 22, 10),
    )  # quarantined

    assert store.latest_run("US").session == date(2026, 8, 4)
    assert store.last_run("US").session == date(2026, 8, 5)
    assert store.last_run("US").status == "quarantined"


def test_last_run_is_none_on_an_untouched_market(store: Store):
    assert store.last_run("US") is None


def test_a_quarantined_session_is_discarded_so_it_can_be_retried(store: Store):
    # A quarantined session published nothing — no universe, no ranks, nothing any
    # reader ever saw — so clearing it rewrites no history. Without this the
    # write-once guard turns a bad night into a permanent one: every retry dies on
    # the run row the failed attempt left behind (issue #103).
    enumerated = [f"S{i}" for i in range(100)]
    run_market(
        store, "US", date(2026, 8, 5),
        enumerated=enumerated, resolved=enumerated[:50],
        now=datetime(2026, 8, 5, 22, 10),
    )
    assert store.last_run("US").status == "quarantined"

    store.discard_session("US", date(2026, 8, 5))

    assert store.last_run("US") is None, "the quarantined row is gone"
    record = run_market(
        store, "US", date(2026, 8, 5),
        enumerated=enumerated, resolved=enumerated,
        now=datetime(2026, 8, 5, 23, 0),
    )
    assert record.status == "published"
    assert store.latest_run("US").session == date(2026, 8, 5)


def test_discarding_a_quarantined_session_clears_its_failure_rows(store: Store):
    # The failure rows explain *that* attempt's shortfall. Left behind they would
    # outlive the run record they belong to and be read as the retry's own
    # account of itself, so they go with it.
    session = date(2026, 8, 5)
    enumerated = [f"S{i}" for i in range(100)]
    run_market(
        store, "US", session,
        enumerated=enumerated, resolved=enumerated[:50],
        now=datetime(2026, 8, 5, 22, 10),
    )
    store.append_run_failures(
        "US",
        session,
        [
            ResolutionFailure(
                market="US", session=session, symbol="S99",
                name="Ninety Nine Inc", status="unresolved", counted=True,
            )
        ],
    )

    discarded = store.discard_session("US", session)

    assert discarded == 2, "the failure row and the quarantined run record"
    assert store.run_failures("US", session) == []


def test_a_quarantined_session_behind_a_published_one_is_still_discardable(store: Store):
    # The guard is about the session's *own* status, not the market's: a
    # quarantined night stays discardable with a published night in front of it,
    # and discarding it leaves that published night untouched.
    enumerated = [f"S{i}" for i in range(100)]
    run_market(
        store, "US", date(2026, 8, 4),
        enumerated=enumerated, resolved=enumerated[:50],
        now=datetime(2026, 8, 4, 22, 10),
    )  # quarantined
    run_market(
        store, "US", date(2026, 8, 5),
        enumerated=enumerated, resolved=enumerated,
        now=datetime(2026, 8, 5, 22, 10),
    )  # published

    store.discard_session("US", date(2026, 8, 4))

    assert [r.session for r in store.runs("US")] == [date(2026, 8, 5)]
    assert store.universe("US", date(2026, 8, 5)) == sorted(enumerated)


def test_discarding_a_published_session_is_still_refused(store: Store):
    # The other half of the rule: what a run *published* is never rewritten
    # (spec §7.2), and making quarantines retriable must not soften that.
    enumerated = [f"S{i}" for i in range(100)]
    run_market(
        store, "US", date(2026, 8, 5),
        enumerated=enumerated, resolved=enumerated,
        now=datetime(2026, 8, 5, 22, 10),
    )
    with pytest.raises(SessionExistsError):
        store.discard_session("US", date(2026, 8, 5))
    assert store.universe("US", date(2026, 8, 5)) == sorted(enumerated)


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


# -- the persisted refusal verdict (issue #100) -------------------------------


def test_a_refusal_verdict_is_persisted_and_read_back_per_market(store: Store):
    # The stated refusal fires only on a cold start, so it is recorded once and
    # read back to skip re-probing the listing (spec §3.6). It is a per-market
    # fact and never bleeds across markets.
    store.mark_refused("US", "CAIIW", date(2026, 8, 4))
    store.mark_refused("US", "TRTN$A", date(2026, 8, 4))
    store.mark_refused("IDX", "XXXX.JK", date(2026, 8, 4))

    assert store.refusals("US") == {"CAIIW", "TRTN$A"}
    assert store.refusals("IDX") == {"XXXX.JK"}
    assert store.refusals("SG") == set()


def test_marking_a_refusal_is_idempotent(store: Store):
    # A persisted-refused symbol is never re-probed, so a second write should not
    # happen — but the guard keeps the first verdict if one ever does, rather
    # than raising like the write-once dated streams do.
    store.mark_refused("US", "CAIIW", date(2026, 8, 4))
    store.mark_refused("US", "CAIIW", date(2026, 8, 5))

    assert store.refusals("US") == {"CAIIW"}


def test_the_refusals_table_is_added_to_an_older_store(tmp_path):
    # A database from before the verdict existed gains the table on open, like
    # every other additive schema change (issue #100 rides the v7->v8 bump).
    path = tmp_path / "old.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE runs (market TEXT NOT NULL, session DATE NOT NULL)")
    con.close()

    store = Store.open(path)
    try:
        store.mark_refused("US", "CAIIW", date(2026, 8, 4))
        assert store.refusals("US") == {"CAIIW"}
        assert store._con.execute(
            "SELECT version FROM schema_meta"
        ).fetchone()[0] == SCHEMA_VERSION
    finally:
        store.close()
