"""The backtest's forward chain: the contract's universe on the replay's machinery
(issue #188, PRD #182 Phase 3).

This is not a second replay. :mod:`replay.chain` already runs sessions forward
with burn-in, rebuilds universe → ranks per session, rejects a gapped sequence and
reuses a session it has already computed — all through the app's own functions.
The backtest needs exactly that, with one gate swapped: the contract's **stateless**
universe (:mod:`backtest.universe`) in place of the app's sticky, hysteretic one
(PRD stories 65, 67). So this module supplies a
:data:`~replay.chain.UniverseBuilder` and calls the existing chain, and owns
nothing else.

What it does own is the **window**. The reference study's chain is bounded by a
session *count* — 126 burn-in sessions from a fixed 2019-04 start. The backtest is
bounded by *dates*: the contract carries a store start (2011-01-01) and a measured
start (2012-01-01), and the sessions between them are the burn-in. Expressing the
burn-in as a date rather than a count is what makes it mean something — "the
warm-up the detector's 80-bar minimum, the SMA50 gate and the regime's 25-bar
window all need" is a claim about calendar time, and a count would have to be
re-derived every time the window moved.

Why the burn-in survives a stateless universe
---------------------------------------------
The reason :mod:`replay.chain` burns in is gone here: with no stickiness and no
hysteresis band there is no membership state to settle, and the app's regime fits
nothing. What is left is ordinary indicator warm-up — SMA50, ADR20, the detector's
minimum history, the regime's 25 index bars — none of which is *wrong* before it is
satisfied, merely absent. The burn-in is kept anyway, and kept as a persisted,
excluded stretch rather than a shorter fetch, because a measured window whose first
sessions quietly carry a thinner universe than the rest is a hole that reads as a
result. Persisting them and excluding them (story 76) makes the thinness visible
instead.
"""

from __future__ import annotations

from datetime import date
from typing import Callable, Sequence

from replay.chain import (
    SessionField,
    UniverseBuilder,
    replay_chain,
    replay_references,
    synthesize_instruments,
)
from screener.source import Instrument
from screener.store import Store

from .contract import (
    WINDOW_MEASURED_START_KEY,
    WINDOW_STORE_START_KEY,
    RunContract,
)
from .universe import Candidate, classify


def stateless_universe(contract: RunContract) -> UniverseBuilder:
    """The chain's universe seam, bound to ``contract``'s stateless classifier.

    The one difference between this chain and the reference study's. Membership
    comes from :func:`backtest.universe.classify` — three gates and a market trim,
    no prior membership read anywhere — and is persisted through the same
    ``append_universe`` the app's rebuild uses, so the chain's reuse path reads it
    back identically (PRD story 67).

    Whole bar series are handed to the classifier rather than a slice, and that is
    deliberate: :func:`backtest.universe.is_member` slices to ``b.session <
    session`` itself, so the point-in-time claim lives in exactly one place. A
    defensive second slice here would copy every symbol's full history once per
    session for fourteen years to restate a guarantee the callee already makes.

    Synthesised instruments carry no security name, which is what the store left
    of them; :func:`~screener.universe.is_common_stock` reads an empty name as
    common stock, and the references were already struck by
    :func:`~replay.chain.synthesize_instruments` before they reached here.
    """

    def rebuild(
        store: Store, market: str, session: date, instruments: list[Instrument]
    ) -> list[str]:
        candidates = [
            Candidate(
                symbol=i.symbol,
                name=i.name or "",
                bars=store.bars(market, i.symbol),
            )
            for i in instruments
            if i.role == "candidate"
        ]
        members = classify(market, candidates, session, contract)
        store.append_universe(market, session, members)
        return members

    return rebuild


def window_sessions(
    store: Store,
    market: str,
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[date]:
    """The store's observed calendar for ``market``, clipped to ``[start, end]``.

    A contiguous run of the calendar by construction, which is the only way a
    dated window can be gapless: the chain's gap check compares a sequence against
    the calendar, and a date range that skips nothing in the calendar cannot fail
    it. A hole in the *calendar itself* — a session no symbol has a bar for — is a
    different fact and is not visible here; it shows up as the detection count
    collapsing, which is why the run reports that count per session (story 77).

    Both bounds are inclusive, and either may be omitted to run to the store's
    own edge.
    """
    return [
        s
        for s in store.sessions(market)
        if (start is None or s >= start) and (end is None or s <= end)
    ]


class WindowNotCovered(RuntimeError):
    """The store does not hold the window the run was asked to replay.

    Its own error, not a bare ``ValueError``, because a caller that wants to catch
    this wants exactly this. A window silently clipped to what the store happens
    to hold is the quietest failure in the whole run: every count below it is
    computed correctly, over a shorter history than the one that was asked for,
    and nothing in the output says so.
    """


def burn_in_count(sessions: Sequence[date], measured_start: date) -> int:
    """How many of ``sessions`` precede ``measured_start`` — the burn-in length.

    The bridge between the backtest's dated window and the replay chain's
    session-count burn-in. A ``measured_start`` after the whole window measures
    nothing, and is deliberately not clamped: an empty measured result is a caller
    error worth seeing, where a silently shortened one is not.
    """
    return sum(1 for s in sessions if s < measured_start)


def check_window_covered(
    store: Store, market: str, start: date, end: date | None
) -> None:
    """Refuse a window the store's calendar does not reach across.

    The gap check inside the chain compares a session sequence against the
    calendar, so a window sliced *from* that calendar can never fail it — which
    leaves the one gap that actually happens in a fetched store unguarded: the
    crawl stopped short, or started late, and the window quietly became whatever
    the bars covered. This is that guard, and it is the reason the acceptance
    criterion says "end to end" and "gapless" in the same breath.

    A hole *inside* the calendar — a session no symbol in the market has a bar for
    — is a different fact and is not detectable here, because the calendar is the
    union of bar dates and a market holiday looks exactly the same. That one shows
    up as the detection count collapsing, which is why the run reports the count
    per session (story 77).
    """
    calendar = store.sessions(market)
    if not calendar:
        raise WindowNotCovered(f"the store holds no {market} sessions at all")
    if start < calendar[0]:
        raise WindowNotCovered(
            f"the window starts {start} but the store's first {market} session is "
            f"{calendar[0]}: the run would silently replay a shorter history than "
            "it was asked for"
        )
    if end is not None and end > calendar[-1]:
        raise WindowNotCovered(
            f"the window ends {end} but the store's last {market} session is "
            f"{calendar[-1]}: the run would silently stop short of its window"
        )


def excluded_references(store: Store, market: str) -> list[str]:
    """The benchmark references that have bars in the store and are kept unranked.

    The exclusion (#162, story 73) reads off the symbol alone, because the copy
    into a purpose-built store keeps no role column and no security name: the
    index announces itself with ``^`` and the benchmark ETFs announce nothing at
    all, so they are named. That makes it a blocklist, and a blocklist rots in
    silence — a benchmark fetched later would be ranked exactly as these once
    were.

    This function is what a test pins against the store's own enumeration (story
    74): it reports which references the store actually holds, so a run over a
    store carrying a sixth benchmark can be caught rather than quietly
    contaminated.
    """
    references = replay_references(market)
    return sorted(s for s in store.symbols(market) if s in references)


def backtest_chain(
    store: Store,
    market: str,
    contract: RunContract,
    *,
    start: date | None = None,
    end: date | None = None,
    measured_start: date | None = None,
    sessions: Sequence[date] | None = None,
    progress: Callable[[int, int, date], None] | None = None,
) -> list[SessionField]:
    """Replay ``market``'s forward chain over a dated window, burn-in included.

    Universe membership and ranks per session, through :func:`replay.chain.replay_chain`
    with the contract's stateless classifier swapped in. Every session in the
    window is returned — the burn-in ones flagged ``burn_in=True`` — because the
    backtest persists them and excludes them at measurement rather than never
    computing them (story 76).

    ``start`` and ``end`` default to the contract's store-window start and the
    store's last session; ``measured_start`` defaults to the contract's measured
    start, and the sessions before it are the burn-in. A ``sessions`` sequence
    handed in directly overrides the window, and a *gapped* one — skipping an
    interior calendar session — raises :class:`~replay.chain.GapError` rather than
    running (story 75). A backtest that quietly skips a session reports on a
    market that took the day off.

    A window the store cannot reach across raises :class:`WindowNotCovered`
    before anything is computed, so a run over a crawl that stopped short fails
    rather than reporting correct counts over the wrong window.
    """
    if sessions is None:
        if start is None:
            start = date.fromisoformat(contract.value(WINDOW_STORE_START_KEY))
        check_window_covered(store, market, start, end)
        sessions = window_sessions(store, market, start=start, end=end)
    if measured_start is None:
        measured_start = date.fromisoformat(
            contract.value(WINDOW_MEASURED_START_KEY)
        )
    return replay_chain(
        store,
        market,
        burn_in=burn_in_count(sessions, measured_start),
        sessions=sessions,
        universe=stateless_universe(contract),
        include_burn_in=True,
        progress=progress,
    )


__all__ = [
    "WindowNotCovered",
    "backtest_chain",
    "burn_in_count",
    "check_window_covered",
    "excluded_references",
    "stateless_universe",
    "synthesize_instruments",
    "window_sessions",
]
