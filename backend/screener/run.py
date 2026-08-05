"""The scheduled run entry point: ``python -m screener.run <MARKET>`` (spec §7.3).

This is what the two ``launchd`` jobs invoke and what run-on-open drives in the
background. It is the thinnest possible wrapper around the gate and the pipeline:
compute ``now``, ask :func:`run_is_due` whether the last final session is
missing, and — only if it is — run :func:`run_market_universe` for that session.
Backfill of any absent sessions in between is the pipeline's own concern; this
layer decides *whether* tonight needs a run and for *which* session.

The source is a parameter so the decision logic is testable without the network.
``main`` builds the real one via :func:`screener.source.default_source`, which is
the single place the live Yahoo/Nasdaq client is wired — not yet implemented, so
a bare invocation fails loudly rather than pulling nothing.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .bars import EXCHANGE
from .models import RunRecord
from .pipeline import DEFAULT_DIGESTS_DIR, run_market_universe
from .schedule import last_final_session, run_is_due
from .source import Source
from .store import Store


def run_once(
    store: Store,
    source: Source,
    market: str,
    *,
    now: datetime,
    digests_dir: Path = DEFAULT_DIGESTS_DIR,
) -> RunRecord | None:
    """Run ``market``'s pipeline for the last final session, if it is missing.

    Returns the resulting :class:`RunRecord`, or ``None`` when the store already
    holds the last final session (nothing was due). ``now`` must be
    timezone-aware; it fixes both the finality decision and the session run.
    """
    latest = store.latest_run(market)
    latest_session = latest.session if latest else None
    if not run_is_due(latest_session, market, now):
        return None
    session = last_final_session(market, now)
    return run_market_universe(
        store, source, market, session, now=now, digests_dir=digests_dir
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: ``screener.run <MARKET>``. Opens the file-backed store, builds the
    live source and runs the due session for one market."""
    from .app import DEFAULT_DB_PATH
    from .source import default_source

    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0].upper() not in EXCHANGE:
        print("usage: python -m screener.run <IDX|US>", file=sys.stderr)
        return 2
    market = args[0].upper()
    now = datetime.now(ZoneInfo(EXCHANGE[market]["tz"]))
    store = Store.open(DEFAULT_DB_PATH)
    try:
        record = run_once(store, default_source(), market, now=now)
    finally:
        store.close()
    if record is None:
        print(f"{market}: already current, no run")
    else:
        print(f"{market}: {record.status} run for {record.session}")
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())
