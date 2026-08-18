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
from datetime import date
from typing import Iterable, Sequence

from screener.pipeline import rebuild_ranks
from screener.ranks import Rank
from screener.source import Instrument
from screener.store import Store
from screener.universe import rebuild_universe

from .caching_store import CachingStore

# The reference set is entirely US breakout trades (PRD "Out of Scope: IDX").
REPLAY_MARKET = "US"

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

    ``burn_in`` marks a session computed only to settle the chain; the reported
    results carry ``burn_in=False`` exclusively. ``blind_spot_count`` is the
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
    """One ``candidate`` :class:`Instrument` per symbol with bars in the store.

    The app's enumeration returns today's listing snapshot, so it is useless for
    reconstructing a past field; the replay's instrument set is instead exactly
    the names the store holds bars for (PRD "A2 replay chain"). Every synthesised
    instrument is a candidate — references (indices, ETFs) are never rankable and
    the reference set is all common-stock breakouts — and carries no security
    name, which :func:`screener.universe.is_common_stock` reads as common stock
    (the live pull already filtered instrument types before the bars were stored).
    """
    return [
        Instrument(market=market, symbol=s, role="candidate")
        for s in store.symbols(market)
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


def replay_chain(
    store: Store,
    market: str = REPLAY_MARKET,
    *,
    blind_spot_tickers: Iterable[str] = (),
    burn_in: int = BURN_IN_SESSIONS,
    sessions: Sequence[date] | None = None,
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

    fields: list[SessionField] = []
    for i, session in enumerate(sessions):
        members = rebuild_universe(
            store, market, session, instruments=instruments, unresolved=set()
        )
        ranks = rebuild_ranks(store, market, session)
        if i < burn_in:
            continue  # computed and persisted, but not a reported result
        fields.append(
            SessionField(
                session=session,
                burn_in=False,
                members=members,
                ranks=ranks,
                blind_spot_count=blind_spot_count,
            )
        )
    return fields
