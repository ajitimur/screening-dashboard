"""The run: the thin slice of the nightly pipeline the skeleton carries.

The full pipeline is eleven stages (spec §7.4). Here it is just the two that
write the record every later stage hangs off: resolve a universe, then write the
run row — published, or quarantined if too few enumerated symbols resolved
(spec §3.4 rule 7 / acceptance A2) or the enumeration itself shrank materially
from the last good run (rule 8). This is the "runs something" that Seam 1 drives
before asserting on rows.
"""

from __future__ import annotations

from datetime import date, datetime

from .bars import clean_bars, parse_bars
from .detection import Detection, detect, detection_gate
from .labels import select_fetches
from .models import RunRecord
from .ranks import Rank, rank_table
from .regime import index_broke_out
from .source import MARKET_INDEX, Source, resolve_market
from .store import Store
from .universe import rebuild_universe

# A run that resolved less than this share of enumerated symbols is quarantined
# behind a banner rather than published (spec §3.4 rule 7).
RESOLUTION_FLOOR = 0.99

# A run whose *enumeration* is materially smaller than the last good run's is
# quarantined too (spec §3.4 rule 8). Per-symbol failures are countable against a
# known denominator (RESOLUTION_FLOOR); a truncated enumeration moves the
# denominator and would otherwise pass the completeness gate at 100%. Enumeration
# counts breathe with real listings, so the floor is looser than the resolution
# gate — a drop past 10% of the last good run is a failed pull, not a shrinking
# exchange (~84 IDX / ~694 US names vanishing overnight).
ENUMERATION_FLOOR = 0.90


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

    A run publishes only if it clears *both* gates: enough of the enumerated
    symbols resolved (rule 7), and the enumeration itself is not materially
    smaller than the last good run's (rule 8). The enumeration baseline is the
    last *published* run — a quarantined run must not lower the bar, or a slow
    leak of shrinking pulls would each pass against the previous shrunk attempt.
    """
    last_good = store.latest_run(market)
    enumeration_ok = (
        last_good is None
        or len(enumerated) >= ENUMERATION_FLOOR * last_good.symbols_enumerated
    )
    published = enumeration_ok and len(resolved) >= RESOLUTION_FLOOR * len(enumerated)
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


def ingest_market_bars(
    store: Store,
    source: Source,
    market: str,
    *,
    now: datetime,
) -> dict[str, int]:
    """Pipeline stages 2–3: ingest every enumerated symbol's bars, hygienic.

    For each instrument (candidates *and* references — the index rides the same
    ingest path, spec §3.1) the bars are resolved through the paced, backed-off
    source, parsed, then cleaned: zero-volume phantoms dropped and non-final
    sessions discarded (spec §3.4 rules 1–2). Each symbol's clean bars are
    persisted the moment they resolve, so a pull killed partway leaves every
    already-persisted symbol — and the other market's completed pull — intact
    (spec §3.3). ``now`` must be timezone-aware for the finality rule.

    Returns the count of bars newly stored per symbol.
    """
    stored: dict[str, int] = {}
    for instrument in source.enumerate(market):
        resolution = source.resolve(instrument.symbol)
        if resolution.status != "resolved":
            continue  # silence is unresolved, not absent — nothing to ingest
        bars = clean_bars(parse_bars(resolution.bars), market, now)
        if bars:
            stored[instrument.symbol] = store.append_bars(market, instrument.symbol, bars)
    return stored


def rebuild_ranks(store: Store, market: str, session: date) -> list[Rank]:
    """Pipeline stage: rank every universe member for ``session`` (spec §4.3).

    Reads the session's published universe and each member's clean bars off the
    store, computes the (name, lookback) percentile/raw-return table, and appends
    it — pruning outside the rolling 2-year window. References are not members, so
    they are never ranked. Returns the rank rows written.

    Must run after the universe for ``session`` is published: it ranks exactly
    the members that session recorded.
    """
    members = store.universe(market, session)
    members_bars = {symbol: store.bars(market, symbol) for symbol in members}
    rows = rank_table(members_bars, session)
    store.append_ranks(market, session, rows)
    return rows


def capture_follow_through(store: Store, market: str, session: date) -> bool | None:
    """Pipeline stage: record the index's breakout follow-through for ``session``.

    Reads the market index's clean bars up to ``session`` and appends one
    follow-through row — whether the index closed to a new trailing-window high,
    and its close (spec §4.9). Returns ``None`` (and writes nothing) before a full
    trailing window of index bars exists. This is captured **from the first run**
    and is **never displayed or gated**: it is the only unbiased regime signal,
    recorded forward and irrecoverable if not started at launch. Appended only on
    a published run, so a quarantined run leaves no forward record.
    """
    index_bars = [
        b for b in store.bars(market, MARKET_INDEX[market]) if b.session <= session
    ]
    broke = index_broke_out(index_bars)
    if broke is None:
        return None
    store.append_follow_through(market, session, broke, index_bars[-1].adj_close)
    return broke


def rebuild_detections(store: Store, market: str, session: date) -> list[Detection]:
    """Pipeline stage: detect every eligible universe member for ``session``.

    Detection runs against **every universe member every night**, not only recent
    movers (spec §4.5): the loop visits each member and the **decile gate** —
    top decile in any of 1m/3m/6m, off the rank table — decides eligibility, not
    a "did it move today" pre-filter. Each gated member is handed its clean bars
    and detected; the cluster and catch-up gates live inside :func:`detect`.

    A member that is gated but not sitting in a base simply yields no detection
    (it was still evaluated); a strong member with a base is emitted with its
    trigger, stop and signal vector. Returns — and appends — the detection rows.

    Must run after the universe **and** the ranks for ``session`` are written: it
    reads both. A quarantined run wrote neither, so it never calls this.
    """
    members = store.universe(market, session)
    gated = detection_gate(store.ranks(market, session))
    rows: list[Detection] = []
    for symbol in members:
        if symbol not in gated:
            continue
        found = detect(symbol, store.bars(market, symbol), session)
        if found is not None:
            rows.append(found)
    store.append_detections(market, session, rows)
    return rows


def run_market_universe(
    store: Store,
    source: Source,
    market: str,
    session: date,
    *,
    now: datetime,
) -> RunRecord:
    """The nightly per-market run: ingest bars, rebuild the universe, record it.

    Enumerates the market, resolves every instrument once through the paced,
    backed-off source, and persists each resolved symbol's clean bars the moment
    they arrive (spec §3.1–3.4). The completeness gate is measured over
    *candidates* only — references (the index, ETFs) are enumerated but not part
    of the tradeable denominator (§3.4 rule 7). Below the floor the run is
    quarantined and writes no universe (and no ranks), so a throttled pull cannot
    shrink good data. Above it the universe is rebuilt from the freshly-ingested
    bars — with the candidates that stayed unresolved carrying yesterday's
    classification (§3.4 rule 6) — then ranked, so the session leaves the shared
    rank substrate every downstream stage reads (§4.3). With ranks in hand the
    detector runs against every member, emitting a dated detection row for each
    name sitting in a valid base (§4.5). Once the membership is known the label
    cache is kept warm too — new members block, a rolling 1/30th of the rest
    refresh (§3.3, stage 7) — and the index's breakout follow-through is captured,
    the forward, unbiased regime record that is never displayed or gated (§4.9).
    ``now`` must be timezone-aware for the finality rule.
    """
    instruments = source.enumerate(market)
    status: dict[str, str] = {}
    for instrument in instruments:
        resolution = source.resolve(instrument.symbol)
        status[instrument.symbol] = resolution.status
        if resolution.status == "resolved":
            bars = clean_bars(parse_bars(resolution.bars), market, now)
            if bars:
                store.append_bars(market, instrument.symbol, bars)

    candidates = [i.symbol for i in instruments if i.role == "candidate"]
    resolved = [s for s in candidates if status[s] == "resolved"]
    published = len(resolved) >= RESOLUTION_FLOOR * len(candidates)
    if published:
        unresolved = {s for s in candidates if status[s] != "resolved"}
        members = rebuild_universe(
            store, market, session, instruments=instruments, unresolved=unresolved
        )
        rebuild_ranks(store, market, session)
        rebuild_detections(store, market, session)
        refresh_labels(store, source, market, members, session)
        capture_follow_through(store, market, session)
    return store.append_run(
        market,
        session,
        status="published" if published else "quarantined",
        symbols_enumerated=len(candidates),
        symbols_resolved=len(resolved),
        created_at=now,
    )


def refresh_labels(
    store: Store,
    source: Source,
    market: str,
    members: list[str],
    session: date,
) -> set[str]:
    """Pipeline stage 7's label cache: keep every member's sector/industry warm.

    Both labels arrive in one request (spec §3.1). The nightly cost is bounded by
    the cache policy (spec §3.3): every member with no cached label is fetched
    *first* — it blocks, because a name with no industry cannot be placed on the
    axis — and only a rolling ``1/30`` slice of the already-cached members
    refreshes, stalest first. A fetch that comes back ``unresolved`` (silence or
    a persistent 429) leaves the cached value untouched and is retried next
    night by construction: its ``as_of`` did not move, so it stays among the
    stalest, and a never-cached new name stays uncached and blocks again.

    Returns the members that carry both labels after this run — the set that may
    appear on a surface. A newly-admitted name whose fetch failed is absent from
    it, so it cannot be placed until a later night resolves it.
    """
    cached = store.labels(market)
    new, refresh = select_fetches(members, cached)
    for symbol in new + refresh:
        resolution = source.resolve_labels(symbol)
        if resolution.status == "resolved":
            store.upsert_label(
                market, symbol, resolution.sector, resolution.industry, session
            )
    after = store.labels(market)  # one read, not one per member
    return {s for s in members if s in after}


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
