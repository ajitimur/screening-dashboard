"""The full crawl: both markets, 2011 onward, into one store (issue #187).

Phase 1's second half. :mod:`backtest.store` (issue #186) built the fetch loop and
its refusal ledger against an *explicit* enumeration, deliberately leaving out
everything that could only be tested by spending hours on the wire. This module
is that missing half — three decisions and a command:

* **Which symbols the enumeration holds** (:func:`crawl_enumeration`). The app's
  own pre-fetch filter, mirrored rather than reinvented.
* **Which years reach the store** (:data:`CRAWL_START`, read off the contract).
* **How the two markets are driven** (:func:`crawl_market`, :func:`main`) —
  one store, one coverage file per market, resumable.

The crawl itself is a data job, not a code path with interesting branches, so the
code here is thin and the seam is the one :mod:`backtest.store` already
established: a :class:`~screener.source.Source` handed in from outside. Tests
drive :func:`main` end to end over a fake client; the network appears only when
``--out`` meets ``default_source`` in a real terminal.

Run it::

    python -m backtest.crawl --out data/backtest.duckdb
    python -m backtest.crawl --out data/backtest.duckdb --market IDX --resume

``--resume`` is what an interrupted multi-hour crawl restarts with: symbols with
bars already on disk are not re-asked, and they still count as covered, because
they are.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

from screener.pipeline import emit_progress
from screener.source import (
    DEFAULT_RESOLVE_WORKERS,
    MARKET_INDEX,
    Instrument,
    Source,
    default_source,
)
from screener.universe import is_common_stock

from .contract import DEFAULT_CONTRACT, SCOPE_MARKETS_KEY, WINDOW_STORE_START_KEY
from .store import BuildCoverage, build_backtest_store, refuse_live_store

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


def crawl_enumeration(instruments: Iterable[Instrument], market: str) -> list[str]:
    """The symbols the crawl fetches, out of everything the market enumerates.

    Exactly the app's own pre-fetch filter (:func:`screener.pipeline.fetch_market`,
    issue #99), mirrored here for two reasons. The cheap one is cost: on US it is
    most of the enumeration, and this crawl pays for a wasted name in paced
    seconds across fourteen years of history. The load-bearing one is that the
    backtest's denominator is meant to be the *app's* — a looser fetch set would
    price names the product cannot trade.

    So what survives is the market's own index, whose bars the contract's regime
    reads at t−1 (``regime.source``), and the candidates that can enter a
    universe at all. The other references are enumerated but no code path reads
    their bars; a non-common-stock candidate is excluded by the universe's
    instrument-type rule whatever its bars say.

    Order is the enumeration's own, so a crawl's progress is reproducible and a
    resumed one asks in the same sequence.
    """
    index = MARKET_INDEX[market]
    return [
        i.symbol
        for i in instruments
        if (i.role == "reference" and i.symbol == index)
        or (i.role == "candidate" and is_common_stock(i.symbol, i.name))
    ]


def crawl_market(
    source: Source,
    *,
    market: str,
    out_path: str | Path,
    now: datetime,
    workers: int = DEFAULT_RESOLVE_WORKERS,
    resume: bool = False,
    progress: Callable[[str], None] = emit_progress,
) -> BuildCoverage:
    """Crawl one market end to end: enumerate, filter, fill, commit its coverage.

    The enumeration is taken *live*, through the same source the bars come from,
    so the coverage's denominator is the market as the provider lists it today —
    which is precisely the quantity Phase 2 bounds the survivorship hole against.
    Recording an enumeration from somewhere else would leave the two counts
    describing different populations.
    """
    instruments = source.enumerate(market)
    symbols = crawl_enumeration(instruments, market)
    progress(
        f"{market}: enumerated {len(instruments)} instruments, "
        f"crawling {len(symbols)} from {CRAWL_START}"
    )
    return build_backtest_store(
        source,
        symbols,
        out_path,
        market=market,
        now=now,
        start=CRAWL_START,
        workers=workers,
        resume=resume,
        progress=progress,
    )


def _utc_now() -> datetime:
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
        "--workers", type=int, default=DEFAULT_RESOLVE_WORKERS,
        help="resolves in flight; the provider's rate is paced regardless",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="skip symbols the store already holds bars for",
    )
    args = parser.parse_args(argv)

    # Before the first request, not after the last. `build_backtest_store` refuses
    # the live store too, but by then a multi-hour US pull has already been paid
    # for — and on a two-market run the second market would find out only once the
    # first had finished.
    out = refuse_live_store(args.out)
    markets = tuple(args.market) if args.market else CRAWL_MARKETS
    at = now or _utc_now()

    source = source_factory()
    for market in markets:
        coverage = crawl_market(
            source,
            market=market,
            out_path=out,
            now=at,
            workers=args.workers,
            resume=args.resume,
            progress=progress,
        )
        progress(
            f"{market}: {len(coverage.stored)} stored + {len(coverage.refusals)} "
            f"refused = {coverage.enumerated} enumerated"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry
    raise SystemExit(main())
