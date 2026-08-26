"""Bounding the survivorship hole (issue #196, PRD #182 Phase 2).

A measurement with its own deliverable, and it comes **before** any performance
number. The bar store holds names that resolve today; a fourteen-year backtest run
over today's tickers is a study of the ones that lived. This module measures how
much of the population that is, and what the headline would be if every missing
name had gone to zero.

Two deliverables, and they are different objects
------------------------------------------------
1. **A dated count** (:func:`absences`). How many names traded inside the measured
   window and are absent from today's enumeration, with the dates they were listed
   between. Reconstructed from a listing spine, named in :data:`SPINE_SOURCE`, and
   the spine's coverage of the window is verified before anything is counted
   against it.
2. **A sensitivity** (:func:`bias_bound`). The pre-registered headline metric
   re-run with the missing population assigned a full stop-out. The gap between the
   two numbers is the bias bound, and :func:`attach_bias_bound` puts it on the
   metric's own report so it rides on every result as one line.

Coverage is a fact about the bars, never about the symbol
---------------------------------------------------------
The weaker question — "does the provider still return this ticker?" — is the one
that let findings §2 under-report its own hole by eleven tickers. The right
question is whether the store's bars for a symbol **cover the session being
replayed** (:func:`session_verdict`), which is what #139 landed and what
:class:`~replay.reference.BarSpan` already answers. It is imported rather than
re-typed: two implementations of "does this cover that session" is two places for
the recycled-ticker case to be got wrong, and the recycled-ticker case is the
whole point.

The silent half of the hole
---------------------------
A delisted name is absent from today's enumeration and the count above sees it. A
**recycled** name is absent from no list at all: the ticker was reassigned to an
unrelated listing, so it resolves today, it has bars, and the bars are a different
company's. findings §2 found eleven of them in a four-year window — `FUSE` had bars
*inside* the window and passed every absence check. So the hole is delisting
**plus** recycling (:attr:`SurvivorshipHole.recycled_names`), and the two counts
are summed rather than either being taken for the whole.

Why the spine is a snapshot series
----------------------------------
:data:`SPINE_SOURCE` is the Nasdaq Trader symbol directory — the same two files
:func:`screener.source.parse_us_listings` reads live — recovered at past dates from
the Internet Archive. Each snapshot is a point-in-time roster of every US listing,
with tickers and with an exact as-of date on the file's own ``File Creation Time``
line. That makes it a *spine*: a name present in a 2013 snapshot and absent from
today's enumeration was listed then and is gone now, which is the claim the count
needs and the one a single enumeration differenced against an exchange count
cannot make (the provider's membership churns for live names on a scale of minutes
— #187 watched `SOHO.JK` leave and return inside seventeen minutes).

Two properties of the spine are checked, and they fail differently:

* **Bracketing is refused.** Without a snapshot at or before the window's start and
  one at or after its end, the spine cannot say a name was listed inside the
  window — every name would appear to have been listed at the spine's own edges.
  :meth:`ListingSpine.verify` raises :class:`SpineCoverageShortfall`.
* **Density is reported.** The archive's snapshots are roughly annual and unevenly
  spaced, so a name that listed *and* delisted between two of them is invisible.
  That does not make the count wrong; it makes it a **floor**, and the silent years
  and the largest gap ride on the result as the reason
  (:class:`SpineCoverage`).

IDX has no such spine
---------------------
No free source reconstructs a dated Jakarta listing roster back to 2012. So IDX's
hole is measured where it *is* visible — from the enumeration side
(:func:`enumeration_gap`): the provider enumerates fewer names than the exchange
lists, and #187's crawl made the pair exact. That figure is undated and is a
standing snapshot rather than a history, which is stated on the figure rather than
left for a reader to infer.

The pessimistic assignment, and what it assumes
-----------------------------------------------
Every missing trade is assigned :data:`PESSIMISTIC_R` — a full stop-out — after the
same costs the covered trades paid. How many missing trades there are is scaled off
the covered ones (:func:`missing_trade_count`): a hole of one name in five means
the observed trades are four-fifths of the population. That assumes a missing name
would have traded at the same rate as a covered one, which is an assumption in the
*optimistic* direction — the names that died are the volatile ones a momentum
screener surfaces most often — and it is stated on the output rather than buried
here.

Read against the floor, and a smaller number is not a better one
----------------------------------------------------------------
findings §2 measured 92 of 312 tickers over 2019-04..2022-12
(:data:`FINDINGS_FLOOR`). This run starts in 2012 and reaches further back, so it
should find *more*. :func:`against_floor` therefore flags a measured hole below the
floor rather than reporting it as an improvement: the likeliest cause of a
shrinking hole is a coverage test that stopped asking the hard question.

Run it::

    python -m backtest.survivorship --store data/backtest.duckdb \\
        --out-json references/backtest_survivorship.json
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

from replay.reference import BarSpan
from screener.store import Store
from screener.universe import is_common_stock

from .contract import (
    DEFAULT_CONTRACT,
    SCOPE_MARKETS_KEY,
    WINDOW_MEASURED_START_KEY,
    RunContract,
)
from .crawl import UNREAD_REFERENCE, Enumeration, enumeration_path
from .metric import BIAS_BOUND_KEY, FULL_WINDOW, format_metric
from .result import stamp_result

# -- what the listing spine is, and where it comes from ------------------------

# The source, named on every figure built from it (acceptance: "the listing source
# is named"). The Nasdaq Trader symbol directory is the app's own US enumeration —
# ``screener.source.parse_us_listings`` reads these two files live — so a spine
# built from its past snapshots is the same roster the store was crawled against,
# read at a different date. That is what makes the two differencable.
SPINE_SOURCE = "nasdaqtrader_symbol_directory_via_wayback_plus_live"
SPINE_FILES: tuple[str, ...] = ("nasdaqlisted.txt", "otherlisted.txt")
SPINE_MARKET = "US"

_CDX_URL = "http://web.archive.org/cdx/search/cdx"
_DIRECTORY_URL = "http://www.nasdaqtrader.com/dynamic/SymDir/{file}"
# ``id_`` asks the archive for the *stored bytes* rather than a rewritten page, so
# what arrives is the pipe-delimited file the exchange published, not HTML with a
# banner around it.
_SNAPSHOT_URL = "https://web.archive.org/web/{timestamp}id_/" + _DIRECTORY_URL

# The exchange stamps its own as-of on the last line ("File Creation Time:
# 0622201218:02"). Preferred over the archive's crawl timestamp, which is when the
# archive *fetched* the file and can trail the file's own date by days.
_CREATION_TIME = re.compile(r"File Creation Time:\s*(\d{2})(\d{2})(\d{4})")


class SpineCoverageShortfall(RuntimeError):
    """The spine does not bracket the window, so it cannot be counted against.

    Its own error because the remedy is specific: find more snapshots, or narrow
    the claim. A spine whose oldest snapshot lands inside the window would report
    every name as first listed at that snapshot, which is a measurement of the
    source's edges wearing the count's name.
    """


class SpineCoverageUnverified(TypeError):
    """Something asked the spine a question before its coverage was verified.

    Raised where the spine is *depended on* rather than where it is built, so the
    check cannot be skipped by a caller who forgot it — which is the failure the
    acceptance criterion is written against.
    """


@dataclass(frozen=True)
class Snapshot:
    """One dated, point-in-time roster of a market's listings.

    ``as_of`` is the exchange's own file-creation date where the file carries one
    and the archive's crawl date otherwise. ``symbols`` is the common-stock
    listings only, filtered by :func:`screener.universe.is_common_stock` — the same
    rule the crawl's own enumeration narrows with, so a warrant absent from today's
    enumeration is not counted as a company that died.
    """

    as_of: date
    file: str
    symbols: tuple[str, ...]


@dataclass(frozen=True)
class SpineCoverage:
    """Whether the spine can carry the count, and how thin it is where it can.

    ``brackets_window`` is the load-bearing one and is a precondition rather than a
    caveat. The rest describe density: ``years_without_snapshot`` and
    ``largest_gap_days`` are why the count is a floor, because a name that listed
    and delisted inside a gap appears in no snapshot and is invisible to a spine
    that never saw it.
    """

    source: str
    market: str
    first: date | None
    last: date | None
    snapshots: int
    window_start: date
    window_end: date
    brackets_window: bool
    years_without_snapshot: tuple[int, ...]
    largest_gap_days: int
    unread_captures: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "market": self.market,
            "first": self.first.isoformat() if self.first else None,
            "last": self.last.isoformat() if self.last else None,
            "snapshots": self.snapshots,
            "window": [self.window_start.isoformat(), self.window_end.isoformat()],
            "brackets_window": self.brackets_window,
            "years_without_snapshot": list(self.years_without_snapshot),
            "largest_gap_days": self.largest_gap_days,
            "unread_captures": self.unread_captures,
            "note": DENSITY_NOTE,
        }


DENSITY_NOTE = (
    "the snapshots are unevenly spaced, so a name listed and delisted between two "
    "of them appears in none: the count is a floor, not a total"
)


@dataclass(frozen=True)
class ListingSpine:
    """A market's dated listing rosters, oldest first, from one named source.

    Unverified by construction. Nothing may be counted against it until
    :meth:`verify` has checked it brackets the window, which is why the counting
    functions take a :class:`VerifiedSpine` and refuse this.
    """

    market: str
    source: str
    snapshots: tuple[Snapshot, ...]
    unread: tuple[tuple[str, str, str], ...] = ()
    """Captures the archive would not replay: ``(file, timestamp, reason)``.

    Recorded rather than dropped. A capture written off after its retries is a
    date the spine cannot see, and a spine that silently skipped it would report
    that date's listings as never having existed — which is the same back-door
    survivorship the crawl's refusal ledger exists to close, one layer up.
    """

    def ordered(self) -> tuple[Snapshot, ...]:
        return tuple(sorted(self.snapshots, key=lambda s: (s.as_of, s.file)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "source": self.source,
            "snapshots": [
                {
                    "as_of": s.as_of.isoformat(),
                    "file": s.file,
                    "symbols": list(s.symbols),
                }
                for s in self.ordered()
            ],
            "unread": [list(row) for row in self.unread],
        }

    @staticmethod
    def from_dict(d: dict) -> "ListingSpine":
        return ListingSpine(
            market=d["market"],
            source=d["source"],
            snapshots=tuple(
                Snapshot(
                    as_of=date.fromisoformat(s["as_of"]),
                    file=s["file"],
                    symbols=tuple(s["symbols"]),
                )
                for s in d["snapshots"]
            ),
            unread=tuple(tuple(row) for row in d.get("unread", ())),
        )

    def to_json(self, *, indent: int = 1) -> str:
        return json.dumps(self.to_dict(), indent=indent) + "\n"

    def write(self, path: str | Path) -> None:
        """Cache the spine beside the store.

        Cached rather than re-fetched, for the reason the coverage ledger is
        committed: a count whose inputs are re-downloaded on every read is a count
        that can change without anyone changing anything. The archive is not a
        fixed corpus either — a capture can be added or withdrawn between two runs —
        so "re-fetch and recompute" is not reproduction.
        """
        Path(path).write_text(self.to_json())

    @staticmethod
    def load(path: str | Path) -> "ListingSpine":
        return ListingSpine.from_dict(json.loads(Path(path).read_text()))

    def coverage(self, window_start: date, window_end: date) -> SpineCoverage:
        """What the spine covers, whether or not that is enough.

        Computed rather than asserted, so the shortfall :meth:`verify` refuses is
        the same object a report prints — one description of the coverage, read
        two ways.
        """
        ordered = self.ordered()
        dates = sorted({s.as_of for s in ordered})
        gaps = [
            (b - a).days for a, b in zip(dates, dates[1:])
        ] if len(dates) > 1 else []
        years = {d.year for d in dates}
        return SpineCoverage(
            source=self.source,
            market=self.market,
            first=dates[0] if dates else None,
            last=dates[-1] if dates else None,
            snapshots=len(ordered),
            window_start=window_start,
            window_end=window_end,
            brackets_window=bool(dates)
            and dates[0] <= window_start
            and dates[-1] >= window_end,
            years_without_snapshot=tuple(
                y for y in range(window_start.year, window_end.year + 1)
                if y not in years
            ),
            largest_gap_days=max(gaps) if gaps else 0,
            unread_captures=len(self.unread),
        )

    def verify(self, window_start: date, window_end: date) -> "VerifiedSpine":
        """Check the spine brackets the window, and return it licensed to be counted.

        The one door into :func:`absences`. Density is carried through as a
        reported property; bracketing is the condition, and its absence raises.
        """
        coverage = self.coverage(window_start, window_end)
        if not coverage.brackets_window:
            raise SpineCoverageShortfall(
                f"the {self.source} spine for {self.market} runs "
                f"{coverage.first}..{coverage.last} and cannot say who was listed "
                f"across {window_start}..{window_end}: it needs a snapshot at or "
                f"before {window_start} and one at or after {window_end}"
            )
        return VerifiedSpine(spine=self, coverage=coverage)


@dataclass(frozen=True)
class Listing:
    """One symbol's life as the spine saw it: first snapshot, last, and how many."""

    symbol: str
    first_listed: date
    last_listed: date
    snapshots: int


@dataclass(frozen=True)
class VerifiedSpine:
    """A spine whose coverage of the window has been checked (:meth:`ListingSpine.verify`).

    A separate type rather than a boolean flag, because the check is the thing the
    acceptance criterion asks to be unskippable: a function that takes this cannot
    be handed a spine nobody verified.
    """

    spine: ListingSpine
    coverage: SpineCoverage

    def listings(self) -> dict[str, Listing]:
        """Every symbol the spine ever carried, with the dates it was seen between."""
        seen: dict[str, Listing] = {}
        for snapshot in self.spine.ordered():
            for symbol in snapshot.symbols:
                prior = seen.get(symbol)
                seen[symbol] = (
                    Listing(symbol, snapshot.as_of, snapshot.as_of, 1)
                    if prior is None
                    else Listing(
                        symbol,
                        prior.first_listed,
                        snapshot.as_of,
                        prior.snapshots + 1,
                    )
                )
        return seen


@dataclass(frozen=True)
class Absence:
    """One name that was listed inside the window and is gone from today's enumeration.

    Dated at both ends, because "92 names are missing" is a number nobody can
    check and "GONE, listed 2013-02-01 through 2015-06-01" is a claim somebody can
    go and refute.
    """

    symbol: str
    market: str
    first_listed: date
    last_listed: date
    snapshots: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "first_listed": self.first_listed.isoformat(),
            "last_listed": self.last_listed.isoformat(),
            "snapshots": self.snapshots,
        }


def todays_roster(enumeration: Enumeration) -> set[str]:
    """Every name the provider **lists today**, which is what "absent" is measured against.

    Not the fetch set, and the difference is the whole reason this function exists.
    :func:`~screener.pipeline.fetch_set` drops two slices the crawl has no use for:
    references nothing reads, and listings the instrument-type rule excludes. An ETF
    in the first slice is *listed* today — it simply is not fetched — so counting it
    absent would report several thousand live listings as companies that died, and
    every share built on that count would be wrong by that much.

    So the reference slice is folded back in. The instrument-type slice is not, and
    the reason is symmetry rather than taste: :func:`parse_snapshot` narrows the
    spine's own snapshots by the same :func:`~screener.universe.is_common_stock`
    rule, so a warrant is missing from both sides and cancels. A name dropped from
    one side and kept on the other is the only way this count can be wrong by
    construction, and these two slices are where that could happen.
    """
    return set(enumeration.fetched) | {
        symbol
        for symbol, reason in enumeration.excluded
        if reason == UNREAD_REFERENCE
    }


def absences(
    spine: VerifiedSpine,
    *,
    enumerated_today: Iterable[str],
    window: tuple[date, date],
) -> tuple[Absence, ...]:
    """The dated count: names listed inside ``window`` and absent from today's list.

    Two conditions, and both are needed. *Listed inside the window* is what makes
    the name this run's business — a company that listed in 2027 is absent from a
    2012 roster for reasons no backtest is measuring. *Absent today* is the
    survivorship claim itself.

    Sorted by symbol, so the committed artefact diffs against the next run's rather
    than reordering under it.
    """
    if not isinstance(spine, VerifiedSpine):
        raise SpineCoverageUnverified(
            "absences() takes a spine whose coverage of the window has been "
            "verified (ListingSpine.verify): counting against an unverified spine "
            "is how a source's own edges get reported as a survivorship hole"
        )
    start, end = window
    today = set(enumerated_today)
    return tuple(
        Absence(
            symbol=listing.symbol,
            market=spine.spine.market,
            first_listed=listing.first_listed,
            last_listed=listing.last_listed,
            snapshots=listing.snapshots,
        )
        for listing in sorted(spine.listings().values(), key=lambda l: l.symbol)
        if listing.symbol not in today
        and listing.first_listed <= end
        and listing.last_listed >= start
    )


# -- coverage: a fact about the bars, never about the symbol -------------------

# The four verdicts. A closed vocabulary rather than a boolean, for the reason
# :data:`~backtest.store.RefusalReason` is one: the three failures have different
# causes — a recycled ticker, a delisting, a name the crawl never reached — and a
# report that collapsed them into "not covered" would name none of them.
COVERED = "covered"
NO_BARS = "no_bars"
BARS_BEGIN_AFTER = "bars_begin_after_session"
BARS_END_BEFORE = "bars_end_before_session"

# The vocabulary as a type, so the annotation carries it the way
# :data:`~backtest.store.RefusalReason` does: a verdict that is not one of these
# four cannot be spelled, rather than being caught by whatever reads it next.
Verdict = Literal[
    "covered",
    "no_bars",
    "bars_begin_after_session",
    "bars_end_before_session",
]

BLIND_SPOT_VERDICTS: tuple[Verdict, ...] = (
    NO_BARS, BARS_BEGIN_AFTER, BARS_END_BEFORE
)


def span_of(store: Store, market: str, symbol: str) -> BarSpan | None:
    """The sessions a symbol's bars run between, or ``None`` when it has none.

    A thin wrapper on :meth:`replay.reference.BarSpan.of`, and it exists to keep
    the store read in one place: every caller here needs the span and none needs
    the bars, so the whole series is never carried past this line.
    """
    return BarSpan.of(store.bars(market, symbol))


def session_verdict(span: BarSpan | None, session: date) -> Verdict:
    """Does this symbol's bar history cover the session being replayed?

    **Not** "does the provider still return this symbol?" — the question findings
    §2 started with and had to abandon. The two answers diverge on a recycled
    ticker: a symbol reassigned to an unrelated listing resolves today and carries
    bars that begin years after the session it is paired with. The weak test calls
    that covered and reads one company's session against another company's series.

    A gap *inside* the span still counts as covered: a halt is not a delisting, and
    the question is whether the listing existed that night.
    """
    if span is None:
        return NO_BARS
    if session < span.first:
        return BARS_BEGIN_AFTER
    if session > span.last:
        return BARS_END_BEFORE
    return COVERED


def is_blind_spot(verdict: Verdict) -> bool:
    """True for the three verdicts that mean the session is not covered.

    Membership in :data:`BLIND_SPOT_VERDICTS` rather than "anything but
    :data:`COVERED`": the two differ only on a verdict that is not in the
    vocabulary at all, and a string nobody defined should not be silently promoted
    to a blind spot — the count it lands in is the deliverable.
    """
    return verdict in BLIND_SPOT_VERDICTS


@dataclass(frozen=True)
class Census:
    """Today's tradeable names, split by whether the bars cover the window's start.

    The population count, and it is decided by :func:`session_verdict` on every
    name rather than by whether the symbol resolves. That distinction is the one
    findings §2 had to switch to, and it is easy to lose here: a name the crawl
    asked about and got *nothing* for still resolves, and counting it covered would
    denominate the whole hole on symbol resolution one layer above the test that
    gets it right.

    ``unlisted`` are names in today's fetch set the spine never saw at all — a
    listing newer than the spine's last capture, or a symbol form the two sources
    spell differently. They are held apart rather than folded into either side,
    because "the spine cannot speak to this name" is not a finding about the name.
    """

    covered: tuple[str, ...]
    recycled: tuple[str, ...]
    no_bars: tuple[str, ...]
    unlisted: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "covered": len(self.covered),
            "recycled": len(self.recycled),
            "no_bars": len(self.no_bars),
            "unlisted_in_spine": len(self.unlisted),
        }


def coverage_census(
    store: Store,
    market: str,
    symbols: Iterable[str],
    *,
    spine: "VerifiedSpine",
    window_start: date,
) -> Census:
    """Split today's tradeable names by :func:`session_verdict` at their first sighting.

    The sighting is the earliest date inside the window at which the spine saw the
    symbol listed. Asking the verdict *there* is what separates the two shapes that
    look identical in the bars alone:

    * A name the spine listed in 2013 whose bars begin in 2019 is **recycled** — on
      the 2013 sighting the symbol was somebody else's listing.
    * A name the spine first listed in 2019 whose bars begin in 2019 is an ordinary
      **IPO**, and a run with no bars before it is right rather than blind.

    A name with no bars at all is a blind spot too, and it is the case that makes
    this a census rather than a filter: it resolves, the crawl asked about it, and
    it can price nothing.
    """
    listings = spine.listings()
    covered, recycled, no_bars, unlisted = [], [], [], []
    for symbol in symbols:
        listing = listings.get(symbol)
        if listing is None:
            unlisted.append(symbol)
            continue
        sighted = max(listing.first_listed, window_start)
        if sighted > listing.last_listed:
            # Listed only before the window opened; the window has no sighting to
            # ask the verdict at, so this name is not the window's business.
            unlisted.append(symbol)
            continue
        verdict = session_verdict(span_of(store, market, symbol), sighted)
        if verdict == BARS_BEGIN_AFTER:
            recycled.append(symbol)
        elif verdict == NO_BARS:
            no_bars.append(symbol)
        else:
            # COVERED, and BARS_END_BEFORE — a name whose series stops mid-window is
            # covered *at its sighting*, which is what this census asks. Its later
            # silence is a delisting the absence count holds if the provider has
            # dropped it, and a stale series otherwise.
            covered.append(symbol)
    return Census(
        covered=tuple(sorted(covered)),
        recycled=tuple(sorted(recycled)),
        no_bars=tuple(sorted(no_bars)),
        unlisted=tuple(sorted(unlisted)),
    )


# -- the hole, and findings §2's floor -----------------------------------------


@dataclass(frozen=True)
class SurvivorshipFloor:
    """findings §2's measured hole — the only prior measurement of this thing.

    Recorded to be compared against, not to be reproduced: the window and the
    population differ (a trader's 828 executed trades over four years, against this
    run's mechanical denominator over fourteen). What transfers is the *rate* and
    the direction: reaching further back should find more.
    """

    window: str
    tickers: int
    total_tickers: int
    trades: int
    total_trades: int
    r_share: float


FINDINGS_FLOOR = SurvivorshipFloor(
    window="2019-04..2022-12",
    tickers=92,
    total_tickers=312,
    trades=172,
    total_trades=828,
    r_share=0.180,
)

FLOOR_SUSPICION_NOTE = (
    "a measured hole below findings §2's floor is a reason for suspicion, not "
    "celebration: this window starts in 2012 and reaches further back than the "
    "four years that floor was measured over, so it should find more"
)


@dataclass(frozen=True)
class SurvivorshipHole:
    """One market's missing population: the delisted and the recycled, together.

    ``absent_names`` come from the listing spine and ``recycled_names`` from the
    coverage verdicts, and they are disjoint by construction — an absent name is
    not in today's enumeration and a recycled one is. Summing them is the only
    honest total, because either alone understates the hole in a way findings §2
    had to correct for after `FUSE`.

    ``recycled_names`` is ``None`` on a market with no dated listing spine, and that
    is not the same reading as zero. Telling a recycled ticker from a genuine IPO
    needs a dated sighting of the symbol before its bars begin, and a market with no
    spine has none — so the half is reported as **unmeasured**, and the hole is
    marked a floor for that reason as well as for the spine's own density.
    ``basis`` names where the absent count came from, because IDX's comes from the
    enumeration side rather than from a spine and the two are not the same claim.
    """

    market: str
    covered_names: int
    absent_names: int
    recycled_names: int | None
    basis: str
    no_bars_names: int = 0
    """Names the crawl asked about and got nothing for.

    Part of the hole, not part of the covered population. They *resolve* — the
    provider lists them and the crawl asked — and they can price nothing, which is
    exactly the difference between the question findings §2 started with and the
    one it had to switch to.
    """

    @property
    def recycled_measured(self) -> bool:
        return self.recycled_names is not None

    @property
    def missing_names(self) -> int:
        return self.absent_names + (self.recycled_names or 0) + self.no_bars_names

    @property
    def total_names(self) -> int:
        return self.covered_names + self.missing_names

    @property
    def share(self) -> float:
        return self.missing_names / self.total_names if self.total_names else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "basis": self.basis,
            "covered_names": self.covered_names,
            "absent_names": self.absent_names,
            "recycled_names": self.recycled_names,
            "recycled_measured": self.recycled_measured,
            "missing_names": self.missing_names,
            "total_names": self.total_names,
            "share": self.share,
            "no_bars_names": self.no_bars_names,
        }


# Where a market's absent count came from. Two bases, and they are different
# claims: a spine says *who* left and *when*, the enumeration side says only *how
# many* are missing right now against the exchange's own listing count.
BASIS_SPINE = "listing_spine"
BASIS_ENUMERATION = "enumeration_side"


def hole_from_counts(
    *,
    market: str,
    covered_names: int,
    absent_names: int,
    recycled_names: int | None,
    basis: str = BASIS_SPINE,
    no_bars_names: int = 0,
) -> SurvivorshipHole:
    """Assemble a hole from its counts, refusing a negative one.

    A constructor rather than the dataclass directly, so the one invariant worth
    checking is checked in the one place holes are made.
    """
    counted = [covered_names, absent_names, no_bars_names]
    if recycled_names is not None:
        counted.append(recycled_names)
    if min(counted) < 0:
        raise ValueError(
            f"a survivorship hole counts names: got covered={covered_names}, "
            f"absent={absent_names}, recycled={recycled_names}"
        )
    return SurvivorshipHole(
        market=market,
        covered_names=covered_names,
        absent_names=absent_names,
        recycled_names=recycled_names,
        basis=basis,
        no_bars_names=no_bars_names,
    )


def against_floor(hole: SurvivorshipHole) -> dict[str, Any]:
    """State the measured hole against findings §2's, and flag it when it is smaller.

    The comparison is by share rather than by count, because the two populations
    are different sizes and 92 tickers of 312 is the transferable figure.
    """
    floor_share = FINDINGS_FLOOR.tickers / FINDINGS_FLOOR.total_tickers
    below = hole.share < floor_share
    note = FLOOR_SUSPICION_NOTE if below else ""
    if not hole.recycled_measured:
        unmeasured = (
            "the recycled half of this market's hole is unmeasured (no dated "
            "listing spine), so the share is a floor for that reason too"
        )
        note = f"{note} — {unmeasured}" if note else unmeasured
    return {
        "measured_share": hole.share,
        "floor_share": floor_share,
        "floor_window": FINDINGS_FLOOR.window,
        "floor_tickers": f"{FINDINGS_FLOOR.tickers} of {FINDINGS_FLOOR.total_tickers}",
        "floor_trades": f"{FINDINGS_FLOOR.trades} of {FINDINGS_FLOOR.total_trades}",
        "floor_r_share": FINDINGS_FLOOR.r_share,
        "below_floor": below,
        "recycled_measured": hole.recycled_measured,
        "note": note,
    }


# -- IDX: the hole measured from the enumeration side --------------------------


@dataclass(frozen=True)
class EnumerationGap:
    """How many names the exchange lists that the provider never enumerated.

    IDX's only measurable hole, because no free source reconstructs a dated Jakarta
    listing roster. Undated and standing rather than a history: it says how many
    names are missing *now*, not when each left, and the read date rides on
    ``source`` so the figure is reproducible against a churning membership.
    """

    market: str
    enumerated: int
    listed_by_exchange: int
    source: str

    @property
    def missing(self) -> int:
        return max(0, self.listed_by_exchange - self.enumerated)

    @property
    def share(self) -> float:
        return self.missing / self.listed_by_exchange if self.listed_by_exchange else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "enumerated": self.enumerated,
            "listed_by_exchange": self.listed_by_exchange,
            "source": self.source,
            "missing": self.missing,
            "share": self.share,
            "note": ENUMERATION_GAP_NOTE,
        }


ENUMERATION_GAP_NOTE = (
    "measured from the enumeration side: the count is a standing snapshot of a "
    "churning membership, not a dated history of who left when"
)


def enumeration_gap(enumeration: Enumeration) -> EnumerationGap | None:
    """The gap between the provider's listing and the exchange's, or ``None``.

    ``None`` when the crawl obtained no exchange count — which is the US case. An
    absent count and a gap of zero are opposite findings, so the absent one is not
    reported as the number.

    ``enumerated`` is the provider's *listing*, not the fetch set: the narrowing to
    common stock is the crawl's own rule and is accounted for in the enumeration
    record, whereas this gap is about names the provider never listed at all.
    """
    if enumeration.listed_by_exchange is None:
        return None
    return EnumerationGap(
        market=enumeration.market,
        enumerated=enumeration.listed,
        listed_by_exchange=enumeration.listed_by_exchange,
        source=enumeration.listed_by_exchange_source,
    )


# -- the sensitivity: the headline, and its pessimistic twin -------------------

# A full stop-out, in the unit the headline is denominated in. The pessimistic
# assignment is a *rule*, not a parameter, so no run can soften it after seeing the
# number it produces.
PESSIMISTIC_R = -1.0
PESSIMISTIC_OUTCOME = "full_stop_out_at_minus_one_r_before_costs"

MISSING_POPULATION_ASSUMPTION = (
    "the missing names are assumed to have traded at the same rate per name as the "
    "covered ones, which is optimistic: the names that died were the volatile ones "
    "a momentum screener surfaces most"
)

def missing_trade_count(*, closed: int, hole_share: float) -> int:
    """How many trades the missing population would have contributed.

    The observed trades are the covered share of the population, so the missing
    ones are ``n · h / (1 − h)``. Rounded to a whole trade, because a fractional
    trade in a count reads as precision the construction does not have.

    A hole of 1.0 is refused rather than returning infinity: every name missing
    means there is no covered population to scale off, and a bound built on that
    would be a number about nothing.
    """
    if not 0.0 <= hole_share < 1.0:
        raise ValueError(
            f"a hole share is in [0, 1): got {hole_share}; a share of 1 leaves no "
            "covered population to scale the missing one off"
        )
    return round(closed * hole_share / (1.0 - hole_share))


@dataclass(frozen=True)
class BiasBound:
    """The headline, its pessimistic twin, and the distance between them.

    Never one number. ``gap_r`` is the bound: what survivorship could be worth on
    this cell if every missing name had stopped out. It is not a correction and the
    twin is not an estimate of the truth — the truth is somewhere between them, and
    the pair is the honest statement of that.
    """

    market: str
    label: str
    headline_r: float | None
    pessimistic_r: float | None
    gap_r: float | None
    covered_trades: int
    missing_trades: int
    hole_share: float
    pessimistic_outcome: str = PESSIMISTIC_OUTCOME

    def to_dict(self) -> dict[str, Any]:
        return {
            "market": self.market,
            "label": self.label,
            "headline_r": self.headline_r,
            "pessimistic_r": self.pessimistic_r,
            "gap_r": self.gap_r,
            "covered_trades": self.covered_trades,
            "missing_trades": self.missing_trades,
            "hole_share": self.hole_share,
            "pessimistic_outcome": self.pessimistic_outcome,
            "assumption": MISSING_POPULATION_ASSUMPTION,
            "line": bias_bound_line(self),
        }


def bias_bound(
    cell: Mapping[str, Any], *, market: str, hole_share: float
) -> BiasBound:
    """Re-run one expectancy cell with the missing population stopped out.

    Arithmetic over the cell rather than over synthesised trades. Expectancy is a
    mean, so the twin is ``(Σr + m·p) / (n + m)`` — exact, checkable by hand, and it
    never invents a fake bar series whose own bugs would land inside the bound.

    The missing trades pay the same costs the covered ones did — the cell's own mean
    ``cost_r``, read off the cell rather than recomputed from the contract, because a
    second reading of the costs is a second place for the twin to be charged
    differently from the headline it is compared against.
    """
    n = int(cell["closed"])
    missing = missing_trade_count(closed=n, hole_share=hole_share)
    headline = cell["expectancy_r"]
    if headline is None:
        # A quiet slice: no closed trade to average, and a bound over nothing would
        # be zero — indistinguishable from a measured bound of zero.
        return BiasBound(
            market=market, label=str(cell["label"]), headline_r=None,
            pessimistic_r=None, gap_r=None, covered_trades=n,
            missing_trades=missing, hole_share=hole_share,
        )
    cost = cell["cost_r"] or 0.0
    total = float(cell["total_r"]) + missing * (PESSIMISTIC_R - cost)
    pessimistic = total / (n + missing)
    return BiasBound(
        market=market,
        label=str(cell["label"]),
        headline_r=headline,
        pessimistic_r=pessimistic,
        gap_r=headline - pessimistic,
        covered_trades=n,
        missing_trades=missing,
        hole_share=hole_share,
    )


def bias_bound_line(bound: BiasBound) -> str:
    """The bound as the one line it travels on.

    One line, and both numbers on it. A pair split across two lines is a pair a
    reader can quote half of.
    """
    if bound.headline_r is None:
        return (
            f"  bias bound: no closed trades to bound "
            f"(hole {bound.hole_share:.1%} of names)"
        )
    return (
        f"  bias bound: {bound.headline_r:+.3f}R headline vs "
        f"{bound.pessimistic_r:+.3f}R pessimistic — gap {bound.gap_r:.3f}R "
        f"({bound.missing_trades} missing trades at {PESSIMISTIC_R:+.0f}R over "
        f"{bound.covered_trades} covered, hole {bound.hole_share:.1%} of names)"
    )


def attach_bias_bound(
    report: dict[str, Any], holes: Mapping[str, float]
) -> dict[str, Any]:
    """Put each market's bound on the metric report, computed off its full-window cell.

    Attached rather than computed inside :mod:`backtest.metric`, and the direction
    matters: the hole is measured against the bar store and the listing spine,
    neither of which the metric reads. A metric that reached for them would need a
    crawl and a network to report a mean.

    The bound is taken from the **full-window** cell, because that is the figure a
    reader quotes; the per-year cells carry their own bounds beside them so a year
    is never read under the whole window's hole.
    """
    markets = []
    for body in report["markets"]:
        share = holes.get(body["market"])
        if share is None:
            markets.append(body)
            continue
        full = next(c for c in body["windows"] if c["label"] == FULL_WINDOW)
        markets.append(
            {
                **body,
                BIAS_BOUND_KEY: bias_bound(
                    full, market=body["market"], hole_share=share
                ).to_dict(),
                "years": [
                    {
                        **cell,
                        BIAS_BOUND_KEY: bias_bound(
                            cell, market=body["market"], hole_share=share
                        ).to_dict(),
                    }
                    for cell in body["years"]
                ],
            }
        )
    return {**report, "markets": markets}


# -- fetching the spine --------------------------------------------------------


# How hard a capture is tried before it is written off. The archive resets
# connections and truncates replies under load — a first pass measured two
# failures in seven captures — and a capture written off is a year of listings the
# spine never saw. That is the same silent-absence failure the crawl's refusal
# ledger exists to prevent, arriving one layer up, so it is retried and then
# *recorded* rather than dropped.
FETCH_ATTEMPTS = 4
FETCH_BACKOFF_SECONDS = 5.0


def _http_get(url: str, *, attempts: int = FETCH_ATTEMPTS) -> str:
    """One GET, retried, with a User-Agent that names the caller.

    The archive rate-limits anonymous clients, so naming the project is the
    condition of the free access this phase depends on. The retry is for the two
    failures it hands back under load — a reset connection and a truncated body —
    both of which are transient and neither of which means the capture is gone.
    """
    request = urllib.request.Request(
        url, headers={"User-Agent": "screening-dashboard backtest (#196)"}
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(FETCH_BACKOFF_SECONDS * attempt)
    raise AssertionError("unreachable")


def snapshot_timestamps(file: str, *, get: Callable[[str], str] = _http_get) -> tuple[str, ...]:
    """Every archived capture of one directory file, as archive timestamps.

    Collapsed to one capture per month at the source (``collapse=timestamp:6``) and
    filtered to 200s, because a listing roster does not move enough inside a month
    to be worth a second fetch and a 404 capture is an outage rather than an empty
    exchange.
    """
    query = urllib.parse.urlencode(
        {
            "url": _DIRECTORY_URL.format(file=file).replace("http://", ""),
            "output": "json",
            "fl": "timestamp",
            "collapse": "timestamp:6",
            "filter": "statuscode:200",
        }
    )
    rows = json.loads(get(f"{_CDX_URL}?{query}"))
    return tuple(row[0] for row in rows[1:])


def parse_snapshot(text: str, *, file: str, fallback: date) -> Snapshot:
    """One archived directory file as a dated roster of common-stock symbols.

    Parsed here rather than through :func:`screener.source.parse_us_listings`, and
    the reason is in the data: the archival headers differ from today's. A 2012
    ``nasdaqlisted.txt`` has no ``ETF`` column at all, so the live parser raises on
    it — and a spine that silently skipped the years it could not parse would
    report those years' listings as never having existed, which is the exact shape
    of the error this module measures.

    Common-stock narrowing is :func:`screener.universe.is_common_stock`, the app's
    own rule, called rather than re-typed: a warrant absent from today's
    enumeration is not a company that died, and deciding that twice is deciding it
    two ways.
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return Snapshot(as_of=fallback, file=file, symbols=())
    header = [h.strip() for h in lines[0].split("|")]

    def index(*names: str) -> int | None:
        for name in names:
            if name in header:
                return header.index(name)
        return None

    sym_i = index("Symbol", "ACT Symbol")
    name_i = index("Security Name")
    test_i = index("Test Issue")
    if sym_i is None:
        return Snapshot(as_of=fallback, file=file, symbols=())

    as_of = fallback
    symbols: list[str] = []
    for line in lines[1:]:
        stamped = _CREATION_TIME.search(line)
        if stamped:
            month, day, year = (int(g) for g in stamped.groups())
            as_of = date(year, month, day)
            continue
        fields = line.split("|")
        if len(fields) <= sym_i:
            continue
        if test_i is not None and len(fields) > test_i and fields[test_i].strip() == "Y":
            continue
        symbol = fields[sym_i].strip()
        name = fields[name_i].strip() if name_i is not None and len(fields) > name_i else ""
        if symbol and is_common_stock(symbol, name):
            symbols.append(symbol)
    return Snapshot(as_of=as_of, file=file, symbols=tuple(sorted(set(symbols))))


def fetch_spine(
    *,
    files: Sequence[str] = SPINE_FILES,
    get: Callable[[str], str] = _http_get,
    today: date | None = None,
    progress: Callable[[str], None] = lambda _: None,
) -> ListingSpine:
    """Build the US listing spine: the archive's captures, and today's live roster.

    The live files are fetched as the spine's final snapshot, and that is not a
    convenience. The archive's newest capture trails the present by months — it was
    2026-06-11 when this was first run, against a window ending 2026-08-25 — so a
    spine of archived captures alone cannot bracket the window and
    :meth:`ListingSpine.verify` would refuse it. The live directory is the *same
    source* read at today's date rather than a past one, which is exactly the far
    bracket the verification asks for, and it is the roster "absent from today's
    enumeration" is a claim about.

    ``get`` is the seam every test drives this through: the crawl is a data job with
    no interesting branches, and the branches that *are* interesting — a header with
    no ETF column, a file with no creation stamp — live in :func:`parse_snapshot`,
    which needs no network at all.
    """
    fetched_on = today or datetime.now(timezone.utc).date()
    snapshots: list[Snapshot] = []
    unread: list[tuple[str, str, str]] = []
    for file in files:
        captures = [
            (timestamp, _SNAPSHOT_URL.format(timestamp=timestamp, file=file),
             datetime.strptime(timestamp[:8], "%Y%m%d").date())
            for timestamp in snapshot_timestamps(file, get=get)
        ]
        captures.append(("live", _DIRECTORY_URL.format(file=file), fetched_on))
        for timestamp, url, fallback in captures:
            try:
                text = get(url)
            except Exception as exc:  # a capture the archive would not replay
                unread.append((file, timestamp, f"{type(exc).__name__}: {exc}"))
                progress(f"{file} {timestamp}: unread — {type(exc).__name__} {exc}")
                continue
            snapshot = parse_snapshot(text, file=file, fallback=fallback)
            progress(f"{file} {snapshot.as_of}: {len(snapshot.symbols)} listings")
            if snapshot.symbols:
                snapshots.append(snapshot)
    return ListingSpine(
        market=SPINE_MARKET,
        source=SPINE_SOURCE,
        snapshots=tuple(snapshots),
        unread=tuple(unread),
    )


def spine_path(store_path: str | Path) -> Path:
    """Where the fetched spine is cached beside the bar store.

    Cached rather than re-fetched, for the reason the coverage ledger is committed:
    a count whose inputs are re-downloaded on every read is a count that can change
    without anyone changing anything.
    """
    out = Path(store_path)
    return out.with_name(out.name + ".spine.json")


# -- the report, and the command that produces it ------------------------------


def holes_by_market(report: Mapping[str, Any]) -> dict[str, float]:
    """Each market's hole share, keyed the way :func:`attach_bias_bound` wants it.

    The join between the two deliverables, and it is a function rather than a line
    at a call site so the count and the bound cannot be wired to different markets.
    """
    return {
        body["market"]: body["hole"]["share"]
        for body in report["markets"]
        if body["hole"]
    }


def survivorship_report(
    contract: RunContract,
    *,
    holes: Sequence[SurvivorshipHole],
    absent: Mapping[str, Sequence[Absence]],
    coverage: Mapping[str, SpineCoverage],
    gaps: Sequence[EnumerationGap],
    censuses: Mapping[str, "Census"] = {},
) -> dict[str, Any]:
    """Both deliverables as one stamped payload, market by market.

    The floor comparison sits inside each market's block rather than in a footnote,
    because the figure is only interpretable beside it: this window reaches further
    back than findings §2's, so the direction of the difference is the finding.
    """
    by_market = {hole.market: hole for hole in holes}
    gap_by_market = {gap.market: gap for gap in gaps}
    markets = []
    for market in contract.value(SCOPE_MARKETS_KEY):
        hole = by_market.get(market)
        found = absent.get(market, ())
        markets.append(
            {
                "market": market,
                "spine": (
                    coverage[market].to_dict() if market in coverage else None
                ),
                "hole": hole.to_dict() if hole else None,
                "census": (
                    censuses[market].to_dict() if market in censuses else None
                ),
                "versus_findings_floor": against_floor(hole) if hole else None,
                "absences": [a.to_dict() for a in found],
                "absent_count": len(found),
                "enumeration_gap": (
                    gap_by_market[market].to_dict()
                    if market in gap_by_market
                    else None
                ),
            }
        )
    return stamp_result(
        contract,
        {
            "measured_at": datetime.now(timezone.utc).date().isoformat(),
            "listing_source": SPINE_SOURCE,
            "pessimistic_outcome": PESSIMISTIC_OUTCOME,
            "pessimistic_r": PESSIMISTIC_R,
            "assumption": MISSING_POPULATION_ASSUMPTION,
            "markets": markets,
        },
    )


def format_survivorship(report: Mapping[str, Any]) -> str:
    """The count and the bound as a page a terminal can print."""
    lines = [
        f"survivorship — listing spine: {report['listing_source']}",
        f"  measured {report['measured_at']}; missing names assigned "
        f"{report['pessimistic_r']:+.0f}R ({report['pessimistic_outcome']})",
    ]
    for body in report["markets"]:
        lines += ["", f"{body['market']}"]
        spine = body["spine"]
        if spine:
            lines.append(
                f"  spine {spine['first']}..{spine['last']} — {spine['snapshots']} "
                f"snapshots, largest gap {spine['largest_gap_days']}d, "
                f"{len(spine['years_without_snapshot'])} silent years, "
                f"{spine['unread_captures']} captures unread"
            )
        else:
            lines.append("  spine none — no free dated listing roster for this market")
        hole = body["hole"]
        if hole:
            recycled = (
                f"{hole['recycled_names']} recycled"
                if hole["recycled_measured"]
                else "recycled unmeasured"
            )
            lines.append(
                f"  hole {hole['share']:.1%} ({hole['basis']}) — "
                f"{hole['absent_names']} absent + {recycled} of "
                f"{hole['total_names']} names"
            )
            floor = body["versus_findings_floor"]
            lines.append(
                f"  findings §2 floor {floor['floor_share']:.1%} "
                f"({floor['floor_tickers']} over {floor['floor_window']})"
                + ("  ** below the floor **" if floor["below_floor"] else "")
            )
            if floor["below_floor"]:
                lines.append(f"    {floor['note']}")
        gap = body["enumeration_gap"]
        if gap:
            lines.append(
                f"  enumeration gap {gap['missing']} of {gap['listed_by_exchange']} "
                f"({gap['share']:.1%}) — {gap['source']}"
            )
        if body["absences"]:
            lines.append(f"  absent from today's enumeration: {body['absent_count']}")
            for absence in body["absences"][:_ABSENCE_PREVIEW]:
                lines.append(
                    f"    {absence['symbol']:<8} listed "
                    f"{absence['first_listed']}..{absence['last_listed']} "
                    f"({absence['snapshots']} snapshots)"
                )
            if body["absent_count"] > _ABSENCE_PREVIEW:
                lines.append(
                    f"    … and {body['absent_count'] - _ABSENCE_PREVIEW} more; the "
                    "full dated list is in the committed JSON"
                )
    return "\n".join(lines)


# How many absences the printed page shows before deferring to the artefact. The
# committed JSON holds every one — the terminal is a summary, and a page that
# printed 1,200 names would bury the figures above it.
_ABSENCE_PREVIEW = 20


def main(argv: list[str] | None = None) -> int:
    """Measure the hole against a crawled store, and record the count and the bound.

    ``--fetch-spine`` is what goes to the network; without it the cached spine
    beside the store is read, so the count is reproducible from committed inputs.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="path to the backtest bar store")
    parser.add_argument(
        "--fetch-spine", action="store_true",
        help="rebuild the listing spine from the archive (goes to the network)",
    )
    parser.add_argument(
        "--out-json", default=None,
        help="where to write the machine-readable, contract-stamped result",
    )
    parser.add_argument(
        "--metric-json", default=None,
        help="a metric report from `python -m backtest.metric --out-json`; its "
             "headline is re-run against the measured hole and reprinted with the "
             "bound on it",
    )
    parser.add_argument(
        "--out-metric-json", default=None,
        help="where to write the bounded metric report (needs --metric-json)",
    )
    args = parser.parse_args(argv)

    contract = DEFAULT_CONTRACT
    window_start = date.fromisoformat(str(contract.value(WINDOW_MEASURED_START_KEY)))
    cache = spine_path(args.store)
    if args.fetch_spine:
        fetch_spine(progress=print).write(cache)
    # Read back from the cache either way, so the figures are the ones a later run
    # reproduces from the committed file rather than the ones in memory now.
    spine = ListingSpine.load(cache) if cache.exists() else None

    store = Store.open(args.store)
    try:
        holes: list[SurvivorshipHole] = []
        found: dict[str, tuple[Absence, ...]] = {}
        coverage: dict[str, SpineCoverage] = {}
        censuses: dict[str, Census] = {}
        gaps: list[EnumerationGap] = []
        for market in contract.value(SCOPE_MARKETS_KEY):
            enumeration = Enumeration.load(enumeration_path(args.store, market))
            gap = enumeration_gap(enumeration)
            if gap:
                gaps.append(gap)
            # Two rosters, because they answer two questions. ``listed`` is what
            # "absent from today's enumeration" is measured against — everything
            # the provider lists, references folded back in. ``tradeable`` is the
            # fetch set, the names the run can actually price, and it is what the
            # covered population is counted from.
            listed = todays_roster(enumeration)
            tradeable = sorted(enumeration.fetched)
            sessions = store.sessions(market)
            window_end = sessions[-1] if sessions else window_start
            if spine is not None and market == spine.market:
                verified = spine.verify(window_start, window_end)
                coverage[market] = verified.coverage
                found[market] = absences(
                    verified,
                    enumerated_today=listed,
                    window=(window_start, window_end),
                )
                census = coverage_census(
                    store, market, tradeable, spine=verified,
                    window_start=window_start,
                )
                censuses[market] = census
                holes.append(
                    hole_from_counts(
                        market=market,
                        covered_names=len(census.covered),
                        absent_names=len(found[market]),
                        recycled_names=len(census.recycled),
                        no_bars_names=len(census.no_bars),
                        basis=BASIS_SPINE,
                    )
                )
            elif gap is not None:
                # No dated spine for this market, so the hole is measured where it
                # *is* visible: the exchange lists names the provider never
                # enumerated. That count says how many are missing and not who or
                # when, and the recycled half cannot be told from an IPO at all
                # without a dated sighting — so it is reported unmeasured rather
                # than zero, which would read as "no recycled names here".
                holes.append(
                    hole_from_counts(
                        market=market,
                        covered_names=gap.enumerated,
                        absent_names=gap.missing,
                        recycled_names=None,
                        basis=BASIS_ENUMERATION,
                    )
                )
    finally:
        store.close()

    report = survivorship_report(
        contract, holes=holes, absent=found, coverage=coverage, gaps=gaps,
        censuses=censuses,
    )
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(report, indent=1) + "\n")
    print(format_survivorship(report))
    if args.out_json:
        print(f"\nwrote {args.out_json}")

    # The second deliverable, and it is produced by the same command rather than by
    # glue somebody writes later: the measured hole goes straight onto the
    # pre-registered headline, and the bounded report is what gets read.
    if args.metric_json:
        bounded = attach_bias_bound(
            json.loads(Path(args.metric_json).read_text()), holes_by_market(report)
        )
        if args.out_metric_json:
            Path(args.out_metric_json).write_text(json.dumps(bounded, indent=1) + "\n")
        print()
        print(format_metric(bounded))
        if args.out_metric_json:
            print(f"\nwrote {args.out_metric_json}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
