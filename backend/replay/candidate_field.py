"""The read-only field reconstruction the **candidate dimension** studies share.

Both pre-registered candidates were measured by a side-car script rather than by
:mod:`replay.study` — `RS line` (#160, findings §5d) and `Relative move` (#170,
measured by #171, findings §5e) — and both needed the same three things from the
committed replay store, for the same three reasons:

- **The measured sessions**, which are the 505 the store holds detections for and
  the window findings §5b was published on. A candidate is contrasted against
  §5b's own table, so it has to be measured over §5b's own sessions.
- **The session's ranks, recomputed in memory**, never read back from the store.
  :meth:`screener.store.Store.append_ranks` prunes rows outside
  :data:`screener.store.RANK_RETENTION_YEARS` as the chain advances, so the
  persisted table cannot serve the early sessions and a decile gate read off it
  would silently return an empty field for most of the window (#141/#164). This
  is the same reuse path :func:`replay.chain._replay_session` takes.
- **The session's detections under the live detector**, computed and *not*
  persisted. §5b's field is the one detector v1 produced, and ADR 0005 requires a
  candidate to be measured under the detector it would ship against, so both
  studies run two fields over one set of sessions and let the detector be the
  only thing that differs.

**Nothing here writes.** ``data/replay.duckdb`` cannot be re-run in place — its
detections are detector v1 over 505 sessions and a full chain re-run raises
``SessionExistsError`` — so the studies read the persisted rows for the v1
control and recompute the live field in memory. Appending the recomputed rows
would leave the store holding two detectors' rows under one ``(market, session)``
key and would destroy the v1 control on the next run.
:class:`~screener.store.Store` migrates on open and so cannot be handed a
read-only connection; the studies run against a working copy, which is belt and
braces on the same guarantee.

This module exists because the second study needed the first study's harness. Two
copies of the rank-retention workaround is one copy too many: a correction to it
would have to land twice, and the run that failed to get the second copy would
still print a table.
"""

from __future__ import annotations

from datetime import date

from screener.detection import Detection, detection_gate, detect
from screener.ranks import Rank, rank_table
from screener.store import Store


def measured_sessions(store: Store, market: str) -> list[date]:
    """The sessions the store holds detections for — findings §5b's own window.

    Both of a study's fields run over exactly these, so the detector is the only
    thing that moves between them. They are also the sessions the store retained
    ranks for, which is why the persisted field stops at 505 of the chain's 947.
    """
    rows = store._cursor().execute(
        "SELECT DISTINCT session FROM detections WHERE market = ? ORDER BY 1",
        [market],
    ).fetchall()
    return [r[0] for r in rows]


def session_ranks(
    store: Store, market: str, session: date
) -> tuple[list[str], list[Rank]]:
    """The session's members and its rank table, recomputed over its universe.

    Recomputed rather than read back, for the retention reason in the module
    docstring. :func:`screener.ranks.rank_table` is deterministic over the same
    members' bars, so this reproduces what the chain computed rather than
    approximating it.
    """
    members = store.universe(market, session)
    return members, rank_table(
        {s: store.bars(market, s) for s in members}, session
    )


def live_detections(
    store: Store, market: str, session: date, ranks: list[Rank]
) -> list[Detection]:
    """The session's detections under the **live** detector, computed not read.

    :func:`screener.pipeline.rebuild_detections` is the app's own stage and this
    is its loop exactly — every universe member, the decile gate deciding
    eligibility, :func:`screener.detection.detect` on the gated ones — with the
    single difference that the rows are *not* appended. The write is what is
    omitted, never a gate.
    """
    gated = detection_gate(ranks)
    out = []
    for symbol in store.universe(market, session):
        if symbol not in gated:
            continue
        found = detect(symbol, store.bars(market, symbol), session)
        if found is not None:
            out.append(found)
    return out
