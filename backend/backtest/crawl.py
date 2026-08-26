"""The full crawl: both markets, 2011 onward, into one store (issue #187).

Phase 1's second half. :mod:`backtest.store` (issue #186) built the fetch loop and
its refusal ledger against an *explicit* enumeration, deliberately leaving out
everything that could only be tested by spending hours on the wire. This module
is that missing half — three decisions and a command:

* **Which symbols the enumeration holds.** The app's own fetch set
  (:func:`screener.pipeline.fetch_set`), called rather than re-typed.
* **Which years reach the store** (:data:`CRAWL_START`, read off the contract).
* **How the two markets are driven** (:func:`crawl_market`, :func:`main`) —
  one store, and per market a coverage ledger *and* an enumeration record.

The crawl itself is a data job, not a code path with interesting branches, so the
code here is thin and the seam is the one :mod:`backtest.store` already
established: a :class:`~screener.source.Source` handed in from outside. Tests
drive :func:`main` end to end over a fake client; the network appears only when
``--out`` meets ``default_source`` in a real terminal.

Two committed artefacts, not one
--------------------------------
:class:`~backtest.store.BuildCoverage` accounts for every symbol the crawl was
*handed*. But the crawl narrows the provider's listing before handing anything
over — on US, 5,498 names out of 13,141 — and the coverage ledger cannot see the
7,643 it never asked about. Left there, the plan's own standard ("a symbol that
is silently absent is survivorship bias entering through the back door") would be
met for the fetch set and quietly unmet for the listing.

So :class:`Enumeration` is committed beside the coverage: the provider's listed
count, the fetch set, and every excluded symbol with the rule that excluded it.
Between the two files, every name the provider listed is accounted for by one of
four verdicts — bars, a refusal, or one of the two exclusion rules — and the
counts sum at both levels.

Run it::

    python -m backtest.crawl --out data/backtest.duckdb
    python -m backtest.crawl --out data/backtest.duckdb --market IDX --resume

``--resume`` is what an interrupted multi-hour crawl restarts with: symbols with
bars already on disk are not re-asked, and they still count as covered, because
they are.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from screener.pipeline import emit_progress, fetch_set
from screener.source import Instrument, Source, default_source

from .contract import DEFAULT_CONTRACT, SCOPE_MARKETS_KEY, WINDOW_STORE_START_KEY
from .store import (
    BuildCoverage,
    LiveStoreWriteRefused,
    build_backtest_store,
    market_symbol,
    refuse_live_store,
)

# The first session the store carries, read off the contract rather than spelled
# again here: ``window.store_start`` is a Phase 0 choice with a justification
# attached (a year of warm-up before the 2012 measured window satisfies the
# detector's 80-bar minimum, the SMA50 and ADR20 gates, and the regime's 25-bar
# warm-up), and a constant duplicated in the runner is a constant that can drift
# from the contract the results are stamped with.
CRAWL_START: date = date.fromisoformat(DEFAULT_CONTRACT.value(WINDOW_STORE_START_KEY))

# Both markets, in the contract's own order (``scope.markets``). Reported
# separately throughout, and crawled one after the other rather than at once:
# the pacer's rate is a property of the provider, so two concurrent markets would
# share one budget and finish no sooner.
CRAWL_MARKETS: tuple[str, ...] = tuple(DEFAULT_CONTRACT.value(SCOPE_MARKETS_KEY))

# Why a listed name is not in the fetch set. The same closed-vocabulary argument
# :data:`~backtest.store.RefusalReason` makes: an exclusion whose reason lives
# only in a comment is one typo away from a row nothing can group by. Both mirror
# the two slices :func:`~screener.pipeline.fetch_set` drops.
UNREAD_REFERENCE = "unread_reference"
NOT_COMMON_STOCK = "not_common_stock"


@dataclass(frozen=True)
class Enumeration:
    """What the provider listed, and what the crawl narrowed it to (user story 53).

    The coverage ledger's companion. ``listed`` is every instrument the provider
    enumerated; ``fetched`` are the symbols handed to the crawl; ``excluded`` maps
    each dropped symbol to the rule that dropped it. ``listed_by_exchange`` is the
    exchange's own count of its listings where one was obtained, which is what
    turns "the provider seems to miss some IDX names" into a number.

    Committed rather than returned, for the reason the coverage is: a count that
    lives in a log is recomputed on trust by whoever asks next.
    """

    market: str
    listed: int
    fetched: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    listed_by_exchange: int | None = None
    listed_by_exchange_source: str = ""

    def check(self) -> "Enumeration":
        """Assert the narrowing accounts for every listed instrument."""
        total = len(self.fetched) + len(self.excluded)
        if total != self.listed:
            raise ValueError(
                f"the enumeration does not sum to the listing: "
                f"{len(self.fetched)} fetched + {len(self.excluded)} excluded "
                f"= {total}, listed {self.listed}"
            )
        return self

    def to_dict(self) -> dict:
        return {
            "market": self.market,
            "listed": self.listed,
            "listed_by_exchange": self.listed_by_exchange,
            "listed_by_exchange_source": self.listed_by_exchange_source,
            "fetched": list(self.fetched),
            "excluded": [{"symbol": s, "reason": r} for s, r in self.excluded],
        }

    @staticmethod
    def from_dict(d: dict) -> "Enumeration":
        return Enumeration(
            market=d["market"],
            listed=d["listed"],
            listed_by_exchange=d.get("listed_by_exchange"),
            listed_by_exchange_source=d.get("listed_by_exchange_source", ""),
            fetched=tuple(d["fetched"]),
            excluded=tuple((e["symbol"], e["reason"]) for e in d["excluded"]),
        )

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent) + "\n"

    def write(self, path: str | Path) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.to_json())

    @staticmethod
    def load(path: str | Path) -> "Enumeration":
        return Enumeration.from_dict(json.loads(Path(path).read_text()))


def enumeration_path(out_path: str | Path, market: str) -> Path:
    """Where a crawl commits its enumeration record, beside the store.

    Derived from the store and keyed by market, exactly as
    :func:`~backtest.store.coverage_path` is and for the same two reasons.
    """
    out = Path(out_path)
    return out.with_name(f"{out.name}.enumeration.{market}.json")


def narrow(instruments: Sequence[Instrument], market: str) -> Enumeration:
    """The provider's listing narrowed to the crawl's enumeration, with the drops.

    The narrowing rule is the app's own — :func:`screener.pipeline.fetch_set`,
    called rather than restated, so the backtest's denominator cannot drift from
    the product's. This adds only the *record* of what that call dropped, which
    the nightly pull has no need of and the backtest does.

    Symbols are recorded in their stored form (:func:`~backtest.store.market_symbol`,
    IDX suffixed), so the enumeration and the coverage speak the same names.
    """
    fetched = fetch_set(instruments, market)
    keep = set(fetched)
    # A reference that is not the market's index, and a candidate that is not
    # common stock, are the only two ways `fetch_set` drops a name.
    excluded = tuple(
        (
            market_symbol(market, i.symbol),
            UNREAD_REFERENCE if i.role == "reference" else NOT_COMMON_STOCK,
        )
        for i in instruments
        if i.symbol not in keep
    )
    return Enumeration(
        market=market,
        listed=len(instruments),
        fetched=tuple(market_symbol(market, s) for s in fetched),
        excluded=excluded,
    ).check()


def crawl_market(
    source: Source,
    *,
    market: str,
    out_path: str | Path,
    now: datetime,
    resume: bool = False,
    listed_by_exchange: int | None = None,
    listed_by_exchange_source: str = "",
    progress: Callable[[str], None] = emit_progress,
) -> tuple[Enumeration, BuildCoverage]:
    """Crawl one market end to end: list, narrow, fill, commit both records.

    The listing is taken *live*, through the same source the bars come from, so
    the record's denominator is the market as the provider lists it today — which
    is precisely the quantity Phase 2 bounds the survivorship hole against. A
    listing captured from somewhere else would leave the two counts describing
    different populations.
    """
    instruments = source.enumerate(market)
    enumeration = replace(
        narrow(instruments, market),
        listed_by_exchange=listed_by_exchange,
        listed_by_exchange_source=listed_by_exchange_source,
    )
    enumeration.write(enumeration_path(out_path, market))
    progress(
        f"{market}: provider listed {enumeration.listed}, "
        f"crawling {len(enumeration.fetched)} from {CRAWL_START}"
    )
    coverage = build_backtest_store(
        source,
        enumeration.fetched,
        out_path,
        market=market,
        now=now,
        start=CRAWL_START,
        resume=resume,
        progress=progress,
    )
    return enumeration, coverage


def _utc_now() -> datetime:
    # Duplicated from ``screener.app`` rather than imported, for the reason
    # ``backtest.store.live_store_path`` imports that module inside a function:
    # keeping the web app out of this module's import graph is worth two lines.
    return datetime.now(timezone.utc)


def main(
    argv: Sequence[str] | None = None,
    *,
    source_factory: Callable[[], Source] = default_source,
    now: datetime | None = None,
    progress: Callable[[str], None] = emit_progress,
) -> int:
    parser = argparse.ArgumentParser(
        prog="backtest.crawl", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "--out", required=True, help="the backtest store to fill (never the live store)"
    )
    parser.add_argument(
        "--market",
        action="append",
        choices=CRAWL_MARKETS,
        help="crawl one market (repeatable); both by default",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="skip symbols the store already holds bars for",
    )
    # The exchange's own count of its listings, and where it came from. Operator-
    # supplied because no free API serves it — IDX publishes it on a Cloudflare-
    # fronted page — and recorded in the enumeration rather than left in a
    # write-up because that is what turns "the provider seems to miss some IDX
    # names" into a number Phase 2 can bound (issue #187). It describes one
    # market's listing, so pair it with --market.
    parser.add_argument(
        "--listed-by-exchange", type=int,
        help="the exchange's own count of its listings, recorded as provenance",
    )
    parser.add_argument(
        "--listed-by-exchange-source", default="",
        help="where that count was read, and when",
    )
    try:
        args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit:
        return 2

    # Before the first request, not after the last. `build_backtest_store` refuses
    # the live store too, but by then a multi-hour US pull has already been paid
    # for — and on a two-market run the second market would find out only once the
    # first had finished.
    try:
        out = refuse_live_store(args.out)
    except LiveStoreWriteRefused as exc:
        print(f"{exc}", file=sys.stderr)
        return 2

    markets = tuple(args.market) if args.market else CRAWL_MARKETS
    at = now or _utc_now()
    source = source_factory()
    for market in markets:
        enumeration, coverage = crawl_market(
            source,
            market=market,
            out_path=out,
            now=at,
            resume=args.resume,
            listed_by_exchange=args.listed_by_exchange,
            listed_by_exchange_source=args.listed_by_exchange_source,
            progress=progress,
        )
        progress(
            f"{market}: {len(coverage.stored)} stored + {len(coverage.refusals)} "
            f"refused = {coverage.enumerated} crawled, "
            f"of {enumeration.listed} listed"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())
