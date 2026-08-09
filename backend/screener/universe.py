"""The tradeable universe: liquidity, instrument type, listing age, density and
hysteresis (spec §4.1, §3.4 rules 3/6, ticket 05 D2–D13).

Universe = **liquidity + instrument type + listing age**, and nothing else. The
governing principle behind every rule here is that *removal requires stronger
evidence than admission* — it shows up three times, as sticky membership, the
asymmetric hysteresis band, and (elsewhere) ADR living downstream of the gate.

Every gate but the liquidity floor is a hard yes/no. The floor alone is
hysteretic: a name enters at ≥ 1.0× it and leaves only below 0.8×, so the decile
denominators the rest of the app ranks against do not churn night after night on
names drifting across a single threshold with no price action behind them.

The classification is pure — it takes prepared :class:`Candidate` inputs and the
market's observed calendar, and returns the surviving symbols. :func:`rebuild_universe`
is the thin store-driven wrapper that reads bars, prior membership and the
calendar off the store, classifies, and appends one membership row per name.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .bars import Bar
from .source import Instrument
from .store import Store

# Liquidity floors, at their reference values (ticket 05 D12): median of
# unadjusted ``close × volume`` over the trailing 20 traded bars must clear these.
LIQUIDITY_FLOOR: dict[str, float] = {
    "IDX": 1_000_000_000.0,  # Rp 1B/day
    "US": 20_000_000.0,  # $20M/day
}

# A member leaves only once its median dollar volume drops below this multiple of
# the floor; a non-member enters at 1.0× (ticket 05 D11).
HYSTERESIS_EXIT = 0.8

# Window constants. 20 matches ADR's SMA20 — one window across the app (D2/D5).
LIQUIDITY_WINDOW = 20
MIN_LISTING_BARS = 20
DENSITY_WINDOW = 20
DENSITY_MIN = 16  # ≥ 16 of the last 20 sessions non-phantom (§3.4 rule 3)
DENSITY_MAX_GAP = 3  # latest bar within 3 sessions of the market's latest

# Instrument-type exclusion — the *only* non-behavioural rule in the system: it
# matches a security's name rather than testing what the name does (D13), with a
# second, symbol-based half below for the classes the name hides. Common
# stock only; every excluded class below is matched on a whole word so that
# **ADRs are kept** — "American Depositary Shares" contains none of these stems,
# and the preferred class is matched as \bPreferred\b|\bPreference\b|\bPfd\b,
# never "Depositary Sh". "Preference" is the same instrument under a second name
# ("... Series A Cumulative Redeemable Perpetual Preference Shares", #92) and is
# excluded on the same footing. It misfires both ways (it deletes an operating
# bank named "... Trust", ~22 REITs, MLP units, preferred-share ADRs); those
# costs are named and accepted (D13).
_EXCLUDED_INSTRUMENT = re.compile(
    r"\b(?:warrants?|rights?|units?|notes?|bonds?|debentures?"
    r"|preferred|preference|pfd|trusts?|funds?)\b",
    re.IGNORECASE,
)

# The same exclusion, read off the *symbol* where the name will not admit to it
# (#105). Nasdaq writes a preferred or depositary series with "$" — ``DBRG$H``,
# ``MET$E`` — and the names that go with them ("... 7.125% Series H", "MetLife,
# Inc. Depositary Shares") carry none of the stems above, so the name-based rule
# reads them as common stock. Nine of them were fetched every night, came back
# silent, and were counted against a floor they were never meant to be measured
# by. The symbol says what the name does not.
#
# Only "$" is an exclusion. A *dot* in a US symbol is a share class (``BRK.B``),
# which is ordinary common stock and belongs in the universe; that the provider
# spells it with a dash is a wire-format problem, solved at the fetch boundary
# (:func:`screener.source.provider_symbol`), not here.
_PREFERRED_SERIES_MARK = "$"


@dataclass(frozen=True)
class Candidate:
    """One candidate's inputs to classification.

    ``resolved`` is whether this run got fresh bars for it; an unresolved name
    carries yesterday's classification (sticky membership, §3.4 rule 6). ``bars``
    are the symbol's clean, phantom-dropped bars, oldest session first.
    """

    symbol: str
    name: str
    resolved: bool
    bars: list[Bar]


# -- the individual gates (pure) ----------------------------------------------


def _median(values: list[float]) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    ordered = sorted(values)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def median_dollar_volume(bars: list[Bar]) -> float:
    """Median of unadjusted ``close × volume`` over the trailing 20 traded bars.

    A *median*, so one block trade cannot lift an illiquid name over the floor —
    the question is "on a typical day, is there this much turnover here?" (D2).
    """
    recent = bars[-LIQUIDITY_WINDOW:]
    return _median([b.dollar_volume for b in recent])


def is_common_stock(symbol: str, name: str) -> bool:
    """Is this listing common stock — i.e. not in any excluded instrument class?

    Reads both halves of a listing's identity because neither alone is enough:
    the name catches the classes that say what they are ("... Warrant", "...
    Series A Preferred Stock"), and the symbol catches the preferreds and
    depositary shares whose name does not (#105).

    An empty name is common stock: IDX carries no security name and the screener
    already guarantees ``quoteType: EQUITY`` (D13). ADRs are kept.
    """
    if _PREFERRED_SERIES_MARK in symbol:
        return False
    return _EXCLUDED_INSTRUMENT.search(name) is None


def passes_density_gate(traded_sessions: set[date], market_sessions: list[date]) -> bool:
    """§3.4 rule 3: ≥ 16 of the market's last 20 sessions non-phantom for the
    name, *and* its most recent bar within 3 sessions of the market's latest.

    ``traded_sessions`` is the set of sessions the name has a (non-phantom) bar
    on; ``market_sessions`` is the observed exchange calendar, oldest first. The
    recency half doubles as suspension detection — a name that has not traded in
    the last few sessions is gone, no suspension list needed.
    """
    if not market_sessions:
        return False
    window = market_sessions[-DENSITY_WINDOW:]
    if sum(1 for s in window if s in traded_sessions) < DENSITY_MIN:
        return False
    recent = market_sessions[-(DENSITY_MAX_GAP + 1):]
    return any(s in traded_sessions for s in recent)


def _is_member(candidate: Candidate, market: str, market_sessions: list[date],
               was_member: bool) -> bool:
    if not candidate.resolved:
        # Silence is not evidence of absence: carry yesterday's classification
        # forward unchanged (§3.4 rule 6). Never evicted on a failed fetch.
        return was_member
    if not is_common_stock(candidate.symbol, candidate.name):
        return False
    if len(candidate.bars) < MIN_LISTING_BARS:
        return False
    traded = {b.session for b in candidate.bars}
    if not passes_density_gate(traded, market_sessions):
        return False
    floor = LIQUIDITY_FLOOR[market]
    threshold = floor * (HYSTERESIS_EXIT if was_member else 1.0)
    return median_dollar_volume(candidate.bars) >= threshold


def classify(
    market: str,
    candidates: list[Candidate],
    market_sessions: list[date],
    prior_members: set[str],
) -> list[str]:
    """Return the sorted symbols that are universe members this session.

    Hysteresis and stickiness both read ``prior_members`` — a member is held in
    the 0.8–1.0× band and an unresolved name keeps its prior state.
    """
    return sorted(
        c.symbol
        for c in candidates
        if _is_member(c, market, market_sessions, c.symbol in prior_members)
    )


# -- the store-driven pipeline stage ------------------------------------------


def rebuild_universe(
    store: Store,
    market: str,
    session: date,
    *,
    instruments: list[Instrument],
    unresolved: set[str],
) -> list[str]:
    """Rebuild ``market``'s universe for ``session`` and append the membership.

    Reads each candidate's clean bars, the observed calendar and yesterday's
    membership off the store, classifies, then writes one row per surviving name
    (spec §4.1, D11). References (indices, ETFs) are ingested but never rankable,
    so they are not candidates. ``unresolved`` is the set of candidate symbols
    whose fetch failed this run — those carry yesterday's classification.

    Bars must already be ingested (Seam 4): the density gate and the calendar
    are read from what is stored.

    Everything read is sliced to ``session``: a backfilled past night is
    resolved from only what was knowable *then*, never from bars that landed on
    later sessions (spec §7.3). In the normal single-session run ``session`` is
    the latest bar date, so the slice is a no-op.
    """
    market_sessions = [s for s in store.sessions(market) if s <= session]
    prior_members = set(store.universe_before(market, session))
    candidates = [
        Candidate(
            symbol=i.symbol,
            name=i.name,
            resolved=i.symbol not in unresolved,
            bars=[b for b in store.bars(market, i.symbol) if b.session <= session],
        )
        for i in instruments
        if i.role == "candidate"
    ]
    members = classify(market, candidates, market_sessions, prior_members)
    store.append_universe(market, session, members)
    return members
