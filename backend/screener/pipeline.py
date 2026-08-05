"""The run: the thin slice of the nightly pipeline the skeleton carries.

The full pipeline is eleven stages (spec §7.4). Here it is just the two that
write the record every later stage hangs off: resolve a universe, then write the
run row — published, or quarantined if it resolved < ~99% of enumerated symbols
(spec §3.4 rule 7 / acceptance A2). This is the "runs something" that Seam 1
drives before asserting on rows.
"""

from __future__ import annotations

from datetime import date, datetime

from .models import RunRecord
from .source import Source, resolve_market
from .store import Store

# A run that resolved less than this share of enumerated symbols is quarantined
# behind a banner rather than published (spec §3.4 rule 7).
RESOLUTION_FLOOR = 0.99


def run_market(
    store: Store,
    market: str,
    session: date,
    *,
    enumerated: list[str],
    resolved: list[str],
    now: datetime,
) -> RunRecord:
    """Resolve the universe for one session and record the run.

    ``enumerated`` is the symbol list pulled from the listing files; ``resolved``
    is the subset that returned usable bars. The universe rows are appended only
    when the run publishes — a quarantined run must not replace good data.
    """
    published = len(resolved) >= RESOLUTION_FLOOR * len(enumerated)
    if published:
        store.append_universe(market, session, resolved)
    return store.append_run(
        market,
        session,
        status="published" if published else "quarantined",
        symbols_enumerated=len(enumerated),
        symbols_resolved=len(resolved),
        created_at=now,
    )


def run_market_from_source(
    store: Store,
    market: str,
    session: date,
    source: Source,
    *,
    now: datetime,
) -> RunRecord:
    """Drive the source client, then record the run.

    Enumerates the market's candidates and resolves each through the paced,
    backed-off source (spec §3.3). A candidate whose result is ``unresolved`` —
    silence that survived retries — is *not* counted as resolved, so a
    throttled pull falls below the completeness floor and quarantines rather
    than silently shrinking the universe (spec §3.4 rules 5, 7).
    """
    _instruments, resolutions = resolve_market(source, market)
    enumerated = [r.symbol for r in resolutions]
    resolved = [r.symbol for r in resolutions if r.status == "resolved"]
    return run_market(
        store, market, session, enumerated=enumerated, resolved=resolved, now=now
    )
