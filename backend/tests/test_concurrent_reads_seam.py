"""Seam: concurrent reads across the four Board endpoints (issue #93).

The Board fires four reads in parallel on mount (`candidates`, `leaders`,
`sectors`, `regime`). A single process-wide DuckDB connection shared by every
`def` route handler — each dispatched to Starlette's threadpool — is not safe
for concurrent use, so under parallel load some requests intermittently 500.

This regression test issues the four reads concurrently, many rounds, and
asserts every response is 200. It fails against the shared-connection code and
passes once each query gets its own cursor over the shared database.
"""

from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from screener.app import create_app
from screener.store import Store

BOARD_READS = (
    "/api/candidates/IDX",
    "/api/leaders/IDX",
    "/api/sectors/IDX",
    "/api/regime/IDX",
)


def test_board_reads_survive_concurrent_load(seeded_store: Store):
    client = TestClient(create_app(store=seeded_store))

    # Many rounds of the four-abreast Board mount. A single shared connection
    # 500s intermittently here; the failure showed at ~3-in-12 in the field, so
    # repeat generously to make it deterministic in CI.
    with ThreadPoolExecutor(max_workers=len(BOARD_READS)) as pool:
        for _ in range(40):
            responses = list(pool.map(client.get, BOARD_READS))
            statuses = [(path, r.status_code) for path, r in zip(BOARD_READS, responses)]
            assert all(code == 200 for _, code in statuses), statuses
