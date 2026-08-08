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
from pathlib import Path

from .bars import clean_bars, parse_bars
from .detection import Detection, detect, detection_gate
from .digest import build_digest, render_digest
from .labels import select_fetches
from .models import ResolutionFailure, RunRecord
from .ranks import Rank, rank_table
from .regime import index_broke_out
from .source import MARKET_INDEX, Instrument, Source, resolve_market
from .store import Store
from .universe import is_common_stock, rebuild_universe

# Where the nightly digest files land: data/digests/<market>/<session>.md, one
# dated Markdown file per market per session (spec §6 / §7.5). Resolved from this
# file so it is stable regardless of the process's working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIGESTS_DIR = _REPO_ROOT / "data" / "digests"

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


def write_digest(
    store: Store,
    market: str,
    session: date,
    *,
    digests_dir: Path = DEFAULT_DIGESTS_DIR,
) -> Path:
    """Pipeline stage 10: write the dated digest file for ``session`` (spec §6).

    Reads **yesterday's** detections (the setups carrying a ``trigger_yesterday``)
    and each of their bars on ``session`` off the store, reports every name whose
    today close cleared its yesterday trigger, and renders one dated Markdown file
    at ``digests_dir/<market>/<session>.md``. The score is derived from yesterday's
    detection and rank table exactly as the list derives it; the repeat marker
    reads the reported-break archive. The reported breaks are then persisted so a
    later night can mark them repeats.

    Membership consults **neither the score nor the stop nor ``line_ok``** — only
    ``close_today > trigger_yesterday``. An empty night still writes the file with
    an explicit no-breaks line, so a *missing* file means the run failed. Returns
    the path written. Called after the run's detections are in the store.
    """
    yesterday = store.detections_before(market, session)
    today_bars = {}
    for det in yesterday:
        bar = next(
            (b for b in store.bars(market, det.symbol) if b.session == session), None
        )
        if bar is not None:
            today_bars[det.symbol] = bar
    ranks_yesterday = store.ranks(market, yesterday[0].session) if yesterday else []
    labels = store.labels(market)
    industry_of = {sym: label.industry for sym, label in labels.items()}
    sector_of = {sym: label.sector for sym, label in labels.items()}
    last_reported = store.digest_reports_before(market, session)

    breaks = build_digest(
        yesterday, today_bars, ranks_yesterday, industry_of, sector_of, last_reported
    )
    store.append_digest_breaks(market, session, [b.symbol for b in breaks])

    market_dir = digests_dir / market
    market_dir.mkdir(parents=True, exist_ok=True)
    path = market_dir / f"{session.isoformat()}.md"
    path.write_text(render_digest(market, session, breaks))
    return path


# How many failing symbols the run's log line names before it defers to the
# stored record. The table holds every one of them; the log exists so a person
# reading a launchd file can tell throttling from listing quality at a glance,
# and 20 names is enough to see which it is without burying the file.
FAILURE_SAMPLE = 20


def summarize_pull(record: RunRecord, failures: list[ResolutionFailure]) -> str:
    """One human-readable block explaining how a run's pull went (issue #91).

    The scheduled jobs capture stdout to a log file, and until now the only
    thing that landed there was a single status line — a quarantined run said
    that it had quarantined and nothing about why. This is what a person reads
    first: the gate's own arithmetic, the failures split by stated outcome, and
    a bounded sample of the symbols. The full list is in the store's
    ``run_failures`` table, which this deliberately does not try to replace.
    """
    lines = [
        f"{record.market}: {record.status} run for {record.session} — "
        f"{record.symbols_resolved}/{record.symbols_enumerated} measurable "
        "candidates resolved"
    ]
    if not failures:
        return lines[0]
    counted = [f for f in failures if f.counted]
    unresolved = [f for f in counted if f.status == "unresolved"]
    refused = [f for f in failures if f.status == "refused"]
    excluded = [f for f in failures if not f.counted and f.status != "refused"]
    lines.append(
        f"{record.market}: {len(failures)} enumerated candidates left no bars — "
        f"{len(unresolved)} silent and counted against the gate, "
        f"{len(refused)} refused by the provider, "
        f"{len(excluded)} silent but excluded on instrument type"
    )
    for label, group in (
        ("silent, counted", unresolved),
        ("refused", refused),
    ):
        if not group:
            continue
        sample = ", ".join(f.symbol for f in group[:FAILURE_SAMPLE])
        more = "" if len(group) <= FAILURE_SAMPLE else f", … +{len(group) - FAILURE_SAMPLE} more"
        lines.append(f"{record.market}:   {label}: {sample}{more}")
    lines.append(
        f"{record.market}: full per-symbol detail in run_failures "
        f"({record.market}, {record.session})"
    )
    return "\n".join(lines)


def _resolution_failures(
    market: str,
    session: date,
    candidates: list[Instrument],
    status: dict[str, str],
) -> list[ResolutionFailure]:
    """Every enumerated candidate that came back with no bars, and why (#91).

    One row per candidate whose outcome was not ``resolved``, carrying the
    source's stated outcome and whether the symbol sat in the completeness
    gate's denominator. The two together are what separate the diagnoses a bare
    count cannot: a wall of ``unresolved`` names that *count* is a throttled
    pull, and a wall of ``refused`` or instrument-type-excluded ones that do not
    is a listing file carrying instruments the provider never serves (#90).

    References — the index, ETFs — are not here: they are enumerated but were
    never part of the tradeable denominator (§3.4 rule 7), so their silence is a
    different question than the one this record exists to answer.
    """
    return [
        ResolutionFailure(
            market=market,
            session=session,
            symbol=i.symbol,
            name=i.name,
            status=status[i.symbol],
            # Mirrors the gate above: only a common-stock listing the source did
            # not refuse was ever measured against the floor.
            counted=is_common_stock(i.name) and status[i.symbol] != "refused",
        )
        for i in candidates
        if status[i.symbol] != "resolved"
    ]


def _sessions_to_backfill(store: Store, market: str, target: date) -> list[date]:
    """Every session the run must compute, ascending, up to and including ``target``.

    Backfill closes gaps: everything derivable from bars is recomputed for every
    session between the last computed one and the latest final session (spec
    §7.3). The observed exchange calendar is the union of stored bar dates (spec
    §3.4 rule 4), so the sessions to fill are exactly the bar dates lying past
    the last published session and no later than ``target`` — a week away costs
    a handful of these and leaves no hole.

    Only **absent** sessions are returned: a session that already carries a run
    record (published *or* quarantined) is skipped, because derived rows are
    written once and never rewritten (spec §7.2). ``target`` is always included
    when it is itself absent, so a holiday with no bar still stamps a run and the
    tab stops re-triggering. On a *first* run — no prior published session — only
    ``target`` is computed rather than the entire ten-year history.
    """
    recorded = {r.session for r in store.runs(market)}
    latest = store.latest_run(market)
    out: list[date] = []
    if latest is not None:
        out = [s for s in store.sessions(market) if latest.session < s <= target]
    if target not in out:
        out.append(target)
    return sorted(s for s in out if s not in recorded)


def _compute_session(
    store: Store,
    source: Source,
    market: str,
    session: date,
    *,
    instruments: list[Instrument],
    unresolved: set[str],
    digests_dir: Path,
    refresh_labels_now: bool,
) -> None:
    """Recompute one session's derivable streams from stored bars (stages 4–10).

    Universe, ranks, detections, the index follow-through and the digest are all
    deterministic functions of the bars, so a backfilled past night reproduces
    what that night would have produced (spec §7.3). Runs in ascending session
    order so sticky membership and the digest's "yesterday" read the freshly
    written prior session.

    The label cache is the one **as-of-only** stream (spec §7.3): it is stamped
    with the run date and never backfilled, so ``refresh_labels`` fires only on
    the target session (``refresh_labels_now``) — a missed night leaves a visible
    gap in ``labels.as_of`` rather than a fabricated per-session stamp.
    """
    members = rebuild_universe(
        store, market, session, instruments=instruments, unresolved=unresolved
    )
    rebuild_ranks(store, market, session)
    rebuild_detections(store, market, session)
    if refresh_labels_now:
        refresh_labels(store, source, market, members, session)
    capture_follow_through(store, market, session)
    write_digest(store, market, session, digests_dir=digests_dir)


def run_market_universe(
    store: Store,
    source: Source,
    market: str,
    session: date,
    *,
    now: datetime,
    digests_dir: Path = DEFAULT_DIGESTS_DIR,
) -> RunRecord | None:
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
    Finally the digest is written: yesterday's breaks made into one dated Markdown
    file, the whole notification layer, so a *missing* file means a failed run
    (§6). ``now`` must be timezone-aware for the finality rule.

    ``session`` is the *target* — the latest final session (spec §7.3). The bars
    are pulled once, then **every absent session** between the last computed one
    and the target is recomputed from them, ascending, so stopping the job for a
    week and restarting leaves no hole in any derivable stream (acceptance A5).
    Backfill fills only absent sessions; a session already recorded is never
    rewritten. An absent session that nonetheless carries derived rows is debris
    from an interrupted run — the run record is stamped last, so a run that died
    mid-session left rows belonging to no session — and is discarded before the
    session is recomputed, so one killed run cannot wedge a market for good.
    The returned record is the target session's run.
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

    candidate_instruments = [i for i in instruments if i.role == "candidate"]
    candidates = [i.symbol for i in candidate_instruments]
    # The gate exists to catch a *throttled* pull — silence it cannot tell from a
    # dead name (spec §3.4 rule 7). A listing the provider has explicitly refused
    # to serve history for is neither: it is a stated answer, and no amount of
    # pacing will ever turn it into bars. And a listing the instrument-type rule
    # will exclude on its name — warrants, rights, units, preferreds, ~a quarter
    # of the US enumeration — is thrown out of the universe regardless (§4.1), but
    # that rule runs *after* resolution and the provider serves it no history, so
    # it arrives as silence, not a refusal (issue #90). Both would let listings
    # the universe never keeps drag a complete pull under the floor, so the gate
    # is measured over the tradeable candidates that *could* resolve.
    tradeable = [i.symbol for i in candidate_instruments if is_common_stock(i.name)]
    measurable = [s for s in tradeable if status[s] != "refused"]
    resolved = [s for s in measurable if status[s] == "resolved"]
    published = len(resolved) >= RESOLUTION_FLOOR * len(measurable)
    # Why the pull fell short, per symbol, before the counts collapse it to two
    # integers (issue #91). The per-symbol outcomes live only inside this
    # function; a quarantine that records nothing else can be diagnosed no other
    # way than re-running the pull by hand against the live provider.
    failures = _resolution_failures(market, session, candidate_instruments, status)
    if not published:
        # A throttled pull quarantines the whole run: no universe, no ranks, no
        # backfill — the last good data keeps serving (spec §3.4 rule 7). The
        # failure rows are written *first*: the run record is the commit point,
        # so a run that dies in between leaves them as debris the next run
        # clears, never a run record pointing at an explanation that is missing.
        store.append_run_failures(market, session, failures)
        return store.append_run(
            market,
            session,
            status="quarantined",
            # The gate's own denominator, so the record's two numbers are the
            # ones the verdict was reached on rather than a ratio that reads as
            # a failed gate on a run that passed it.
            symbols_enumerated=len(measurable),
            symbols_resolved=len(resolved),
            created_at=now,
        )

    # Sticky classification (spec §3.4 rule 6) carries yesterday's verdict for
    # every candidate that produced no bars tonight — a refused listing among
    # them, which is right: it has no bars to reclassify from either.
    unresolved = {s for s in candidates if status[s] != "resolved"}
    record: RunRecord | None = None
    for backfill_session in _sessions_to_backfill(store, market, session):
        # A previous run may have died after writing some of this session's
        # derived streams but before stamping its run record — rows that belong
        # to no session, and that the write-once guard would otherwise refuse to
        # let this run recompute, wedging the market permanently. The sessions
        # reaching here are by construction unrecorded, so anything found is
        # debris from an interrupted run and is cleared before recomputing.
        store.discard_session(market, backfill_session)
        _compute_session(
            store,
            source,
            market,
            backfill_session,
            instruments=instruments,
            unresolved=unresolved,
            digests_dir=digests_dir,
            # The label cache is as-of-only: stamp it once, on the target session,
            # never per backfilled night (spec §7.3).
            refresh_labels_now=backfill_session == session,
        )
        if backfill_session == session:
            # The failures describe *this* pull, so they belong to the target
            # session only — a backfilled night was computed from bars already on
            # disk and had no pull of its own to fall short (issue #91). Written
            # inside the loop, after ``discard_session`` has cleared the session
            # and before its run record commits it.
            store.append_run_failures(market, session, failures)
        record = store.append_run(
            market,
            backfill_session,
            status="published",
            symbols_enumerated=len(measurable),
            symbols_resolved=len(resolved),
            created_at=now,
        )
    return record


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

    A candidate the provider ``refused`` outright drops out of the denominator
    for the same reason it is not retried: it is a stated answer, not the silence
    the floor is there to detect, and it would otherwise pull a complete pull
    under the floor.

    An instrument-type-excluded listing — a warrant, right, unit or preferred —
    drops out for the same reason, and it is the larger population (issue #90):
    the universe throws it away on its name regardless (§4.1), but that rule runs
    *after* resolution, and the provider serves no history for most of them, so
    they arrive as silence rather than a stated refusal. Left in the denominator
    they fail every night and hold a complete common-equity pull under the floor.
    """
    instruments, resolutions = resolve_market(source, market)
    names = {i.symbol: i.name for i in instruments}
    tradeable = [r for r in resolutions if is_common_stock(names.get(r.symbol, ""))]
    enumerated = [r.symbol for r in tradeable if r.status != "refused"]
    resolved = [r.symbol for r in tradeable if r.status == "resolved"]
    return run_market(
        store, market, session, enumerated=enumerated, resolved=resolved, now=now
    )
