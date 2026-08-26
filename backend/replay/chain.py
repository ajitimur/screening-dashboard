"""The forward replay chain (A2): universe membership and ranks, session by
session, over the whole window (PRD #114 "A2 replay chain", issue #117).

This is the part of the replay most likely to go wrong, so it lands on its own
and is inspectable before anything rides on it. Universe membership is
**path-dependent**: stickiness and the hysteretic liquidity floor both read the
previous session's membership (:mod:`screener.universe`), so membership at a
session is *not* a function of that session's bars alone. The chain must
therefore run forward with no gaps, from a cold start with empty prior
membership, preceded by :data:`BURN_IN_SESSIONS` burn-in sessions from 2019-04 so
the hysteresis band settles before any measured session.

Two consequences fall out of the path dependence and are enforced here:

- **No gaps.** Replaying only the sessions that happen to carry an entry would
  make membership depend on which dates were picked, so a gap in the session
  sequence is a hard :class:`GapError`, not a silent skip. The chain runs over
  the store's observed calendar (the union of bar dates, §3.4 rule 4), which is
  gapless by construction; a caller handing in a subset is rejected.
- **Synthesised instruments.** The app's enumeration returns today's listing
  snapshot, so it cannot be used to reconstruct a 2020 field. Instruments are
  synthesised from the bars present in the replay store instead — which is the
  survivorship hole made concrete: the field is missing every name delisted
  between the session and now, and each session carries a coverage number against
  the committed blind-spot tickers recording it (user story 22).

The universe and ranks are rebuilt with the app's *own* functions, unmodified —
:func:`screener.universe.rebuild_universe` and
:func:`screener.pipeline.rebuild_ranks` — and persisted per session in the replay
store, so the study measures the app that exists rather than a reimplementation
of it (user story 31). Burn-in sessions are computed and persisted too (the band
only settles if they are), but excluded from the reported results.

Nothing here touches the live store: the chain reads and writes only the
purpose-built replay store handed to it (user story 28).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable, Iterable, Sequence

from screener.pipeline import rebuild_ranks
from screener.ranks import Rank, rank_table
from screener.source import MARKET_INDEX, Instrument
from screener.store import Store
from screener.universe import is_common_stock, rebuild_universe

from .caching_store import CachingStore

# The reference set is entirely US breakout trades (PRD "Out of Scope: IDX").
REPLAY_MARKET = "US"

# Every reference whose bars reached the replay store, named because nothing else
# can name them (#162). :mod:`replay.store` copies bars filtered by market and
# date, not by role, and role is never persisted — not in the replay store, not
# in the live one either; it exists only at enumeration, read off the Nasdaq
# listing file's ETF flag (:mod:`screener.source`). So the copy brings the
# references' bars across with no way left to recognise them.
#
# The index announces itself with "^" and ``is_common_stock`` rejects it on that.
# An ETF announces nothing: ``SPY`` is four letters with no "$" and no name, which
# is exactly what a common stock looks like. These four were fetched as study
# benchmarks (``QQQ`` is §3f's headline contrast) and each carried 928 ``universe``
# rows and 2,525 ``ranks`` rows in ``data/replay.duckdb``, the same as ``^IXIC``.
#
# This is a blocklist and it rots silently: a benchmark fetched later would be
# ranked exactly as these were. A test pins it against what the store holds, which
# turns the rot into a failing test rather than a quiet contamination.
REPLAY_REFERENCES = {MARKET_INDEX[REPLAY_MARKET], "SPY", "QQQ", "IWM", "DIA"}

# The blocklist per market (#183). Market is threaded through the whole chain, so
# the reference exclusion must be the *replayed* market's rather than a constant
# fixed to US: ``QQQ`` is a US benchmark but an ordinary common stock on IDX, and
# applying :data:`REPLAY_REFERENCES` to another market would strike it wrongly.
# Only US has study benchmarks copied into a replay store; a market with none
# named falls back to its own index alone — which :func:`is_common_stock` already
# rejects on the ``^`` mark, so the fallback restates the existing exclusion
# rather than adding one, and keeps the set a function of the market either way.
REPLAY_REFERENCES_BY_MARKET: dict[str, set[str]] = {REPLAY_MARKET: REPLAY_REFERENCES}


def replay_references(market: str) -> set[str]:
    """The benchmark references to exclude from ``market``'s ranked field (#162).

    US carries the five benchmarks copied into ``data/replay.duckdb``
    (:data:`REPLAY_REFERENCES`); any other market has none named and falls back to
    its own :data:`~screener.source.MARKET_INDEX`, which is a no-op restatement of
    the ``^``-mark exclusion. Reading the set off the market is what keeps the
    blocklist from being a US-only constant applied to whatever the chain replays.
    """
    return REPLAY_REFERENCES_BY_MARKET.get(market, {MARKET_INDEX[market]})


# A fixed, deterministic stamp for the run record the chain writes as each
# session's "already computed" marker (issue #126). The replay has no wall clock —
# the same store rebuilt twice must produce byte-identical run records — so the
# stamp is a constant, never ``datetime.now()``. Its value is inert: nothing in
# the study reads a run's ``created_at``; only the row's *presence* is consulted.
_REPLAY_RUN_STAMP = datetime(2019, 1, 1, 0, 0, 0)

# Burn-in sessions before the first measured session (PRD "A2 replay chain" /
# user story 14): the cold-started universe has empty prior membership, and the
# hysteresis band needs a stretch of sessions to settle before any result is
# recorded. 126 sessions ≈ six trading months from 2019-04, the window's start.
BURN_IN_SESSIONS = 126


class GapError(RuntimeError):
    """The session sequence to replay is not a gapless run of the calendar.

    Raised loudly rather than skipped: universe membership is path-dependent
    through stickiness and the hysteretic floor, so a missing interior session
    would silently change every later session's membership. Rejecting the gap by
    construction is what keeps the replayed field independent of which dates were
    picked (PRD "A2 replay chain").
    """


@dataclass(frozen=True)
class SessionField:
    """One session's replayed field: its universe members, their ranks, and the
    coverage against the blind-spot tickers.

    ``burn_in`` marks a session computed only to settle the chain. It is dropped
    from the chain's result unless the caller asks for it
    (``replay_chain(..., include_burn_in=True)``), so a reported result carries
    ``burn_in=False`` unless someone deliberately opted the settling sessions in.
    ``blind_spot_count`` is the
    number of known names missing from the field entirely — the coverage figure
    every field-derived output must carry (user story 22). It cannot be dated
    (a blind-spot ticker has no bars), so it is the same standing count on every
    session: the size of the survivorship hole the field is read against.
    """

    session: date
    burn_in: bool
    members: list[str]
    ranks: list[Rank]
    blind_spot_count: int

    @property
    def field_size(self) -> int:
        """How many names the field carried this session."""
        return len(self.members)


def synthesize_instruments(store: Store, market: str = REPLAY_MARKET) -> list[Instrument]:
    """One ``candidate`` :class:`Instrument` per rankable symbol with bars in the store.

    The app's enumeration returns today's listing snapshot, so it is useless for
    reconstructing a past field; the replay's instrument set is instead exactly
    the names the store holds bars for (PRD "A2 replay chain"). Synthesised
    instruments carry no security name, which
    :func:`screener.universe.is_common_stock` reads as common stock (the live pull
    already filtered instrument types before the bars were stored).

    Not every symbol with bars is a candidate, though, and for a while this
    function said otherwise (#162). References — indices, ETFs — are never
    rankable, but :mod:`replay.store` copies bars filtered by market and date and
    not by role, so their bars are here too, with no role column and no security
    name left to read them by. The symbol is the whole of the identity that
    survived the copy, so both halves of the exclusion are read off it:
    ``is_common_stock`` rejects the index on its ``^``, and
    :func:`replay_references` names the benchmark ETFs for ``market``, which carry
    no mark at all.
    """
    references = replay_references(market)
    return [
        Instrument(market=market, symbol=s, role="candidate")
        for s in store.symbols(market)
        if s not in references and is_common_stock(s, "")
    ]


def _check_no_gaps(sessions: Sequence[date], calendar: Sequence[date]) -> None:
    """Reject a session sequence that skips an interior calendar session.

    The sequence must be a contiguous run of the store's observed calendar — the
    same order, no missing session between the first and last. A session absent
    from the calendar, or a jump over one that is present, is a hard error
    (PRD "A2 replay chain": gapped sessions are rejected by construction).
    """
    if not sessions:
        return
    index = {s: i for i, s in enumerate(calendar)}
    positions: list[int] = []
    for s in sessions:
        if s not in index:
            raise GapError(f"session {s} is not in the replay store's calendar")
        positions.append(index[s])
    for prev, cur in zip(positions, positions[1:]):
        if cur != prev + 1:
            raise GapError(
                f"gapped session sequence: {calendar[prev]} -> {calendar[cur]} "
                f"skips {cur - prev - 1} calendar session(s)"
            )


# The universe seam (PRD #182 story 67). The chain rebuilds membership through a
# callable rather than by naming :func:`~screener.universe.rebuild_universe`
# directly, because the backtest replays the *contract's* stateless universe
# while the reference study replays the app's sticky, hysteretic one — and the
# two differ in nothing else. A seam keeps one chain measuring the app that
# exists (user story 31) rather than forking a second replay over one gate.
#
# The contract a builder honours: given the store, the market, the session and
# the synthesised candidate instruments, return that session's members **and
# persist them**, because the reuse path below reads membership back off the
# store rather than recomputing it.
UniverseBuilder = Callable[[Store, str, date, list[Instrument]], list[str]]


def app_universe(
    store: Store, market: str, session: date, instruments: list[Instrument]
) -> list[str]:
    """The app's own universe, rebuilt and persisted — the chain's default.

    :func:`screener.universe.rebuild_universe` unmodified, with an empty
    ``unresolved`` set: a replay re-reads bars already in the store, so no fetch
    can have failed this session and nothing carries yesterday's classification
    on that account. Path dependence still enters through stickiness and the
    hysteresis band, which is why the chain runs forward with no gaps.
    """
    return rebuild_universe(
        store, market, session, instruments=instruments, unresolved=set()
    )


def _replay_session(
    store: Store,
    market: str,
    session: date,
    instruments: list[Instrument],
    universe: UniverseBuilder = app_universe,
) -> tuple[list[str], list[Rank]]:
    """Compute a session's universe and ranks, or reuse them if already persisted.

    The reuse that makes a replay store re-runnable instead of single-use (issue
    #126). ``rebuild_universe`` and ``rebuild_ranks`` append through the store's
    write-once guard, so a second forward chain over the same store used to die
    with :class:`~screener.store.SessionExistsError` on the first session already
    carrying rows. Here a session already computed on an earlier chain is *read
    back* rather than recomputed:

    - The **run record** is the session's "already computed" marker. The chain
      stamps one (write-once itself) after building a fresh session; on a later
      chain its presence means the universe was persisted, so membership is read
      from the store rather than rebuilt — and the expensive
      :func:`rebuild_universe`, which re-reads every candidate's full history, is
      skipped entirely. The write-once guarantee is untouched: nothing is ever
      rewritten, only skipped.
    - The **ranks are recomputed in memory** on reuse, never read from the store.
      :meth:`~screener.store.Store.append_ranks` prunes rows outside the two-year
      retention window as the chain advances, so an early session's persisted
      ranks are gone by the time the pass ends — but :func:`rank_table` over the
      members' bars is deterministic and reproduces exactly what the first chain
      returned, so the reused session is identical to the original.

    Returns ``(members, ranks)`` — the same pair :func:`rebuild_universe` /
    :func:`rebuild_ranks` return, whether freshly computed or reused.
    """
    if store.run(market, session) is not None:
        members = store.universe(market, session)
        members_bars = {symbol: store.bars(market, symbol) for symbol in members}
        return members, rank_table(members_bars, session)

    members = universe(store, market, session, instruments)
    ranks = rebuild_ranks(store, market, session)
    store.append_run(
        market,
        session,
        status="published",
        symbols_enumerated=len(instruments),
        symbols_resolved=len(members),
        created_at=_REPLAY_RUN_STAMP,
    )
    return members, ranks


def replay_chain(
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
    universe: UniverseBuilder = app_universe,
    include_burn_in: bool = False,
    progress: Callable[[int, int, date], None] | None = None,
) -> list[SessionField]:
    """Replay the forward chain of universe membership and ranks over the window.

    Runs forward over every session with no gaps, cold-starting with empty prior
    membership, rebuilding the universe then the ranks for each session with the
    app's own functions and persisting both in the replay store. The first
    ``burn_in`` sessions are computed and persisted — the band only settles if
    they are — but excluded from the returned :class:`SessionField` list, so no
    reported result rests on an unsettled chain.

    ``sessions`` defaults to the store's observed calendar (gapless by
    construction). A caller may hand in a sub-run to replay, but a *gapped*
    sequence — one skipping an interior calendar session — raises :class:`GapError`
    rather than run, since membership is path-dependent and a skipped session
    would silently reshape every later one.

    ``blind_spot_tickers`` is the committed list of names with no bars; its size
    is stamped onto every returned field as the coverage figure that scope is read
    against. Returns one :class:`SessionField` per measured (non-burn-in) session,
    in order.

    ``universe`` is the membership seam: the default rebuilds the app's own sticky,
    hysteretic universe (:func:`app_universe`), and the backtest passes the
    contract's stateless classifier instead (PRD #182 story 67). Everything else
    about the session — the ranks, the run-record reuse marker, the gap check — is
    identical whichever universe is replayed.

    ``include_burn_in`` returns the burn-in sessions too, each flagged
    ``burn_in=True``, rather than dropping them. They are computed and persisted
    either way; the flag decides only whether the caller sees them, which is what
    lets the backtest persist a burn-in session's rows while still excluding it
    from measurement (story 76). The default drops them, so every existing caller
    keeps receiving measured sessions alone.

    ``progress`` is called as ``progress(i, total, session)`` after each session is
    computed (1-based ``i`` over the whole session list, burn-in included), so a
    long forward pass reports rather than hanging silently — the failure the first
    attempt at this study hit, killed at 60 minutes for having printed nothing.
    """
    # Cache bar reads for the life of the run (issue #125). Every session's
    # rebuild_universe and rebuild_ranks re-reads each symbol's whole history —
    # ~7.1M identical round-trips over a full replay. Bars are immutable here (only
    # the derived streams are written), so a run-scoped cache at the store boundary
    # is semantics-preserving and leaves the app's screening functions unmodified.
    # ``wrap`` shares one cache when a caller (e.g. replay_field) already passed a
    # cached store in.
    store = CachingStore.wrap(store)

    calendar = store.sessions(market)
    if sessions is None:
        sessions = calendar
    _check_no_gaps(sessions, calendar)

    instruments = synthesize_instruments(store, market)
    blind_spot_count = len(set(blind_spot_tickers))

    total = len(sessions)
    fields: list[SessionField] = []
    for i, session in enumerate(sessions):
        members, ranks = _replay_session(
            store, market, session, instruments, universe
        )
        if progress is not None:
            progress(i + 1, total, session)
        is_burn_in = i < burn_in
        if is_burn_in and not include_burn_in:
            continue  # computed and persisted, but not a reported result
        fields.append(
            SessionField(
                session=session,
                burn_in=is_burn_in,
                members=members,
                ranks=ranks,
                blind_spot_count=blind_spot_count,
            )
        )
    return fields
