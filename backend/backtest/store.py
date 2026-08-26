"""Phase 1 of PRD #182: the paced bar fetcher and its refusal ledger (issue #186).

The mechanics of filling a purpose-built backtest store. Every enumerated symbol
is fetched through the app's *own* source layer — the same paced, backed-off,
unresolved-not-absent client the nightly run drives (:mod:`screener.source`) — so
the backtest ingests exactly what the app ingests, rather than a second fetch
path that could drift from it. The IDX exchange suffix is applied at the fetch
boundary (:func:`market_symbol`), because IDX's identity in the store is the
``.JK`` form (PRD user story 50).

The load-bearing property is the **ledger**. A crawl of thousands of names over
fourteen years cannot be trusted to have covered its enumeration unless the
coverage is a checkable fact: every enumerated symbol ends with either bars in
the store *or* a refusal row naming why it has none, and the two counts sum to
the enumeration (user stories 53, 54). A symbol that is silently absent is
survivorship bias entering through the back door, and the ledger is what makes an
absence a fact rather than a gap.

That is also why the pull's tail sweep is part of this loop rather than an
optimisation left out of it (:func:`~screener.source.sweep_silence`, issue #104).
On this provider, silence at the end of a long crawl is overwhelmingly a fact
about the *pull* — the same request answers in full once the provider has been
left alone for a minute. A fetcher that stopped at the first pass would write its
throttled tail into the ledger as refusals, and Phase 2 would read that inflated
count as the survivorship bound. An absence is only honest if it is a fact about
the symbol, so the run rests and asks again before letting a name reach the
ledger.

This is deliberately split from the full crawl (PRD): the fetch loop is small
code testable against a seeded fixture in one sitting, while the crawl itself is
hours of wall clock. So the network never appears here — the loop drives a
:class:`~screener.source.Source`, and every test fakes that one seam.

What the app's ingest hygiene guarantees is inherited unmodified
(:func:`screener.bars.clean_bars`): zero-volume phantom bars are dropped at
ingest and never zero-filled or carried forward (user story 55), and a non-final
session is discarded rather than stored as a partial day. A symbol that resolves
but leaves no clean bars is a refusal too — ``no_bars`` — so the invariant holds
over it as well.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Literal

from screener.bars import clean_bars, parse_bars
from screener.pipeline import (
    PROGRESS_EVERY,
    emit_progress,
    progress_line,
    sweep_rest_line,
    sweep_result_line,
)
from screener.source import (
    DEFAULT_RESOLVE_WORKERS,
    SWEEP_WORKERS,
    Resolution,
    Source,
    resolve_all,
    sweep_silence,
)
from screener.store import Store

# The exchange suffix IDX listings carry in the store and on the wire. IDX's whole
# enumeration is keyed by the ``.JK`` form (``BBCA.JK``) — it is the name for the
# thing, the same way the Nasdaq symbol is for US — so the suffix is applied here,
# at the fetch boundary, and a bare enumeration form is normalised to it.
IDX_SUFFIX = ".JK"

# The vocabulary of a refusal, spelled as a type for the same reason
# :data:`~screener.source.ResolutionStatus` is: the ledger's whole worth is that
# a reason means one of a closed set of things, and a set enumerated only in a
# comment is one typo away from a row nothing can group by.
#
# ``unresolved``/``throttled``/``refused`` mirror the source's own outcomes (a
# stated 429 kept apart from an empty answer, #104); ``no_bars`` is the one this
# layer adds — a symbol the source resolved but whose bars all fell to ingest
# hygiene (every bar a zero-volume phantom, say), so it ends with no bars in the
# store and must carry a row like any other absence.
RefusalReason = Literal["unresolved", "throttled", "refused", "no_bars"]


def market_symbol(market: str, symbol: str) -> str:
    """The form a symbol is fetched and stored under for ``market``.

    The market-level sibling of :func:`~screener.source.provider_symbol`, which
    does the same job one layer down for a dotted US share class. Identity for
    everything but an IDX listing, which carries the ``.JK`` exchange suffix —
    applied here so the backtest fetches ``BBCA.JK`` and keys its bars by it (PRD
    user story 50). A symbol already suffixed is left untouched, so an enumeration
    that already carries the convention is a safe no-op, and a ``^``-marked index
    (``^JKSE``) is left alone too — a reference is not a JKT equity and takes no
    exchange suffix.
    """
    if market == "IDX" and not symbol.startswith("^") and not symbol.endswith(IDX_SUFFIX):
        return symbol + IDX_SUFFIX
    return symbol


@dataclass(frozen=True)
class Refusal:
    """One enumerated symbol that ended with no bars, and why (user story 53).

    ``symbol`` is the stored form (IDX suffixed); ``reason`` is one of the
    :data:`RefusalReason` vocabulary. This is the ledger row that makes an absence
    a recorded fact rather than a silent gap.
    """

    symbol: str
    reason: RefusalReason

    def to_dict(self) -> dict:
        return {"symbol": self.symbol, "reason": self.reason}

    @staticmethod
    def from_dict(d: dict) -> "Refusal":
        return Refusal(symbol=d["symbol"], reason=d["reason"])


@dataclass(frozen=True)
class BuildCoverage:
    """The store's coverage as a committable value (user story 54).

    ``stored`` are the symbols that ended with bars in the store; ``refusals`` are
    the rows naming why the rest have none. ``stored`` rather than "resolved"
    deliberately: :data:`~screener.source.ResolutionStatus` already owns that
    word, and the two are not the same set — a symbol the source *resolved* whose
    every bar fell to ingest hygiene ends here as a ``no_bars`` refusal. What this
    field means is bars on disk.

    The invariant this exists to make checkable — ``len(stored) + len(refusals) ==
    enumerated`` — is asserted by :meth:`check`, and the whole object round-trips
    through JSON so both counts can be committed beside the store rather than
    recomputed on trust.
    """

    market: str
    enumerated: int
    stored: tuple[str, ...]
    refusals: tuple[Refusal, ...]

    def check(self) -> "BuildCoverage":
        """Assert the coverage invariant and return self, so a build cannot report
        a store whose bars and refusals do not sum to its enumeration."""
        total = len(self.stored) + len(self.refusals)
        if total != self.enumerated:
            raise ValueError(
                f"coverage does not sum to the enumeration: "
                f"{len(self.stored)} stored + {len(self.refusals)} refused "
                f"= {total}, enumerated {self.enumerated}"
            )
        return self

    def to_dict(self) -> dict:
        return {
            "market": self.market,
            "enumerated": self.enumerated,
            "stored": list(self.stored),
            "refusals": [r.to_dict() for r in self.refusals],
        }

    @staticmethod
    def from_dict(d: dict) -> "BuildCoverage":
        return BuildCoverage(
            market=d["market"],
            enumerated=d["enumerated"],
            stored=tuple(d["stored"]),
            refusals=tuple(Refusal.from_dict(r) for r in d["refusals"]),
        )


def _refusal_reason(resolution: Resolution) -> RefusalReason:
    """Why a non-resolved outcome left the symbol with no bars.

    The 429 flavour of silence is kept apart from an empty answer the same way the
    run's own failure record keeps them apart (#104): both are silence and both
    were retried, but they point at different remedies, and a ledger that cannot
    say which one it hit can only be diagnosed by re-running the crawl by hand.
    """
    if resolution.status == "unresolved" and resolution.throttled:
        return "throttled"
    return "refused" if resolution.status == "refused" else "unresolved"


def _outcome(
    store: Store, market: str, resolution: Resolution, now: datetime
) -> Refusal | None:
    """Ingest one resolution and return the ledger row it earns, or ``None`` if it
    ended with bars in the store.

    Bars go through the app's own ingest hygiene (:func:`clean_bars`) — phantoms
    dropped, a non-final session discarded — and ``append_bars`` is idempotent
    (``ON CONFLICT DO NOTHING``), so a resumed or repeated build re-fetches
    without duplicating a stored bar. A symbol that resolved but kept no clean
    bars is an absence like any other and earns a row.
    """
    if resolution.status != "resolved":
        return Refusal(resolution.symbol, _refusal_reason(resolution))
    bars = clean_bars(parse_bars(resolution.bars), market, now)
    if not bars:
        return Refusal(resolution.symbol, "no_bars")
    store.append_bars(market, resolution.symbol, bars)
    return None


def build_backtest_store(
    source: Source,
    symbols: Iterable[str],
    out_path: str | Path,
    *,
    market: str,
    now: datetime,
    workers: int = DEFAULT_RESOLVE_WORKERS,
    progress: Callable[[str], None] = emit_progress,
) -> BuildCoverage:
    """Fetch every enumerated symbol into a fresh store, ledgering every absence.

    ``symbols`` is the enumeration — the tradeable names Phase 2 will measure
    coverage against. Each is normalised to its stored form (:func:`market_symbol`,
    IDX suffixed) and resolved through ``source`` by :func:`resolve_all`, which
    paces the whole crawl at the provider's sustained rate regardless of how many
    are in flight, so a long pull finishes rather than stalling (user story 51).
    Progress is emitted every :data:`~screener.pipeline.PROGRESS_EVERY` symbols so
    a multi-hour crawl is never killed for having printed nothing (user story 52).

    The pull's silent tail is then rested and re-asked
    (:func:`~screener.source.sweep_silence`, issue #104), and each answer
    *supersedes* the verdict the first pass reached rather than adding to it — a
    swept symbol is one symbol however many times it was asked, so the sum
    invariant holds across the sweep. This is why the ledger can be read as
    survivorship evidence at all: without it the crawl's throttled tail would be
    indistinguishable from listings with no history.

    Every enumerated symbol therefore ends as exactly one entry — bars on disk, or
    a :class:`Refusal` naming why not — and :meth:`BuildCoverage.check` proves the
    two sum to the enumeration before the value is handed back.

    The live store is never opened here at all — the build reaches only ``source``
    and the fresh store at ``out_path`` — so the run is structurally incapable of
    corrupting live history (user story 49). ``now`` must be timezone-aware for the
    finality rule.
    """
    # Distinct stored forms, in enumeration order. The ledger is keyed by symbol,
    # so a name listed twice — or listed once bare and once already suffixed — is
    # one symbol with one verdict, and counting it twice in the enumeration would
    # make the sum invariant unsatisfiable rather than informative.
    to_fetch = list(dict.fromkeys(market_symbol(market, s) for s in symbols))
    total = len(to_fetch)
    counts: Counter[str] = Counter()
    # One entry per enumerated symbol, keyed by symbol so the sweep revises rather
    # than appends: ``None`` means bars reached the store, a Refusal means they did
    # not. Keying is what keeps a twice-asked symbol from being counted twice.
    ledger: dict[str, Refusal | None] = {}
    started = time.monotonic()

    store = Store.open(out_path)
    try:
        for done, resolution in enumerate(
            resolve_all(source, to_fetch, workers=workers), 1
        ):
            counts[resolution.status] += 1
            ledger[resolution.symbol] = _outcome(store, market, resolution, now)
            if done % PROGRESS_EVERY == 0 or done == total:
                progress(
                    progress_line(
                        market, done, total, counts,
                        elapsed=time.monotonic() - started,
                    )
                )

        # The tail sweep. Same loop body as above, deliberately: a swept symbol is
        # ingested and ledgered exactly as it would have been had it answered the
        # first time.
        silent = [
            symbol
            for symbol, row in ledger.items()
            if row is not None and row.reason in ("unresolved", "throttled")
        ]
        recovered = revised = 0
        for resolution in sweep_silence(
            source,
            silent,
            # Never wider than the pull itself: a caller that asked for a
            # sequential pull gets a sequential sweep.
            workers=min(SWEEP_WORKERS, workers),
            on_rest=lambda pause, waiting: progress(
                sweep_rest_line(market, waiting, pause)
            ),
        ):
            # Every result here supersedes a verdict already counted, so the counts
            # move rather than grow. Only silence is swept, so the verdict being
            # superseded is always ``unresolved``.
            if resolution.status != "unresolved":
                counts["unresolved"] -= 1
                counts[resolution.status] += 1
                revised += 1
            ledger[resolution.symbol] = _outcome(store, market, resolution, now)
            recovered += resolution.status == "resolved"
        if silent:
            progress(sweep_result_line(market, recovered, len(silent)))
        if revised:
            # The pull's last heartbeat counted silence the sweep has since
            # answered, and left alone it is the build's final word on stdout.
            progress(
                progress_line(
                    market, total, total, counts,
                    elapsed=time.monotonic() - started,
                )
            )
    finally:
        store.close()

    # Sorted by symbol so the committed coverage is diff-stable: :func:`resolve_all`
    # yields in completion order, which varies run to run under concurrency, and a
    # committable ledger (user story 54) must not reorder on a re-run that changed
    # no verdict.
    return BuildCoverage(
        market=market,
        enumerated=total,
        stored=tuple(sorted(s for s, row in ledger.items() if row is None)),
        refusals=tuple(
            sorted((r for r in ledger.values() if r is not None), key=lambda r: r.symbol)
        ),
    ).check()
