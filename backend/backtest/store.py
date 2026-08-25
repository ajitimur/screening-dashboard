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
from typing import Callable, Iterable

from screener.bars import clean_bars, parse_bars
from screener.pipeline import PROGRESS_EVERY, emit_progress, progress_line
from screener.source import (
    DEFAULT_RESOLVE_WORKERS,
    Source,
    resolve_all,
)
from screener.store import Store

# The exchange suffix IDX listings carry in the store and on the wire. IDX's whole
# enumeration is keyed by the ``.JK`` form (``BBCA.JK``) — it is the name for the
# thing, the same way the Nasdaq symbol is for US — so the suffix is applied here,
# at the fetch boundary, and a bare enumeration form is normalised to it.
IDX_SUFFIX = ".JK"

# The vocabulary of a refusal. ``unresolved``/``throttled``/``refused`` mirror the
# source's own outcomes (a stated 429 kept apart from an empty answer, #104);
# ``no_bars`` is the one this layer adds — a symbol the source resolved but whose
# bars all fell to ingest hygiene (every bar a zero-volume phantom, say), so it
# ends with no bars in the store and must carry a row like any other absence.
RefusalReason = str


def market_symbol(market: str, symbol: str) -> str:
    """The form a symbol is fetched and stored under for ``market``.

    Identity for everything but an IDX listing, which carries the ``.JK`` exchange
    suffix — applied here so the backtest fetches ``BBCA.JK`` and keys its bars by
    it (PRD user story 50). A symbol already suffixed is left untouched, so an
    enumeration that already carries the convention is a safe no-op, and a
    ``^``-marked index (``^JKSE``) is left alone too — a reference is not a JKT
    equity and takes no exchange suffix.
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

    ``resolved`` are the symbols that ended with bars in the store; ``refusals``
    are the rows naming why the rest have none. The invariant this exists to make
    checkable — ``len(resolved) + len(refusals) == enumerated`` — is asserted by
    :meth:`check`, and the whole object round-trips through JSON so both counts can
    be committed beside the store rather than recomputed on trust.
    """

    market: str
    enumerated: int
    resolved: tuple[str, ...]
    refusals: tuple[Refusal, ...]

    def check(self) -> "BuildCoverage":
        """Assert the coverage invariant and return self, so a build cannot report
        a store whose bars and refusals do not sum to its enumeration."""
        total = len(self.resolved) + len(self.refusals)
        if total != self.enumerated:
            raise ValueError(
                f"coverage does not sum to the enumeration: "
                f"{len(self.resolved)} resolved + {len(self.refusals)} refused "
                f"= {total}, enumerated {self.enumerated}"
            )
        return self

    def to_dict(self) -> dict:
        return {
            "market": self.market,
            "enumerated": self.enumerated,
            "resolved": list(self.resolved),
            "refusals": [r.to_dict() for r in self.refusals],
        }

    @staticmethod
    def from_dict(d: dict) -> "BuildCoverage":
        return BuildCoverage(
            market=d["market"],
            enumerated=d["enumerated"],
            resolved=tuple(d["resolved"]),
            refusals=tuple(Refusal.from_dict(r) for r in d["refusals"]),
        )


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

    Each resolved symbol's bars are parsed and cleaned through the app's own ingest
    hygiene (:func:`~screener.bars.clean_bars`) — phantoms dropped, non-final
    sessions discarded — then appended. ``append_bars`` is idempotent
    (``ON CONFLICT DO NOTHING``), so a resumed or repeated build re-fetches without
    duplicating a stored bar (acceptance criterion). Everything else — silence, a
    stated refusal, or a resolve that left no clean bars — becomes a
    :class:`Refusal` row. The returned :class:`BuildCoverage` therefore accounts
    for every enumerated symbol exactly once, and :meth:`BuildCoverage.check`
    proves it before the value is handed back.

    The live store is never opened here at all — the build reaches only ``source``
    and the fresh store at ``out_path`` — so the run is structurally incapable of
    corrupting live history (user story 49). ``now`` must be timezone-aware for the
    finality rule.
    """
    enumerated = [market_symbol(market, s) for s in symbols]
    total = len(enumerated)
    counts: Counter[str] = Counter()
    resolved: list[str] = []
    refusals: list[Refusal] = []
    started = time.monotonic()

    store = Store.open(out_path)
    try:
        for done, resolution in enumerate(
            resolve_all(source, enumerated, workers=workers), 1
        ):
            counts[resolution.status] += 1
            if resolution.status == "resolved":
                bars = clean_bars(parse_bars(resolution.bars), market, now)
                if bars:
                    store.append_bars(market, resolution.symbol, bars)
                    resolved.append(resolution.symbol)
                else:
                    # Resolved, but every bar fell to ingest hygiene — no bars in
                    # the store, so it is an absence like any other and gets a row.
                    refusals.append(Refusal(resolution.symbol, "no_bars"))
            else:
                # Silence (empty or a stated 429) or a stated refusal — a verdict
                # the caller records, not data. The 429 flavour is kept apart from
                # an empty answer the same way the run failure record does (#104).
                reason = (
                    "throttled"
                    if resolution.status == "unresolved" and resolution.throttled
                    else resolution.status
                )
                refusals.append(Refusal(resolution.symbol, reason))
            if done % PROGRESS_EVERY == 0 or done == total:
                progress(
                    progress_line(
                        market, done, total, counts,
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
        resolved=tuple(sorted(resolved)),
        refusals=tuple(sorted(refusals, key=lambda r: r.symbol)),
    ).check()
