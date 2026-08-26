# The backtest bar store — coverage evidence

Phase 1 of [the out-of-sample backtest plan](../docs/out-of-sample-backtest-plan.md)
(PRD #182, issue #187). The store is the run's raw material; this file is the evidence that
it is complete, because a store whose gaps are unrecorded is survivorship bias entering
through the back door.

Crawled **2026-08-26** with `python -m backtest.crawl --out data/backtest.duckdb`.

## What was crawled

| | US | IDX |
| --- | --- | --- |
| Instruments enumerated by the provider | 13,141 | 839 |
| In the crawl set | **5,498** | **839** |
| Stored (bars on disk) | 5,495 | 839 |
| Refusals (a row naming why not) | 3 | 0 |
| Bar rows | 13,238,360 | 1,815,216 |
| First session | 2011-01-03 | 2011-01-03 |
| Latest session | 2026-08-25 | 2026-08-24 |

`5,495 + 3 = 5,498` and `839 + 0 = 839`. Both sums are asserted by
`BuildCoverage.check` before the ledger is written, and the per-symbol ledgers are committed
beside this file as `data/backtest.duckdb.coverage.US.json` and
`…coverage.IDX.json`. The store itself is not committed — it is 848 MB, and `data/*.duckdb`
is ignored — so these two files and this table are what a later reader checks the store
against.

The crawl set is smaller than the enumeration because it is the app's own pre-fetch filter
(`backtest.crawl.crawl_enumeration`, mirroring `screener.pipeline.fetch_market`): the
market's own index, whose bars the contract's regime reads, plus the candidates that can
enter a universe at all. On US that is 5,498 of 13,141 — the rest are ETFs and other
references no code path reads, and non-common-stock listings the universe's instrument-type
rule excludes whatever their bars say. Crawling them would spend paced hours on bars nothing
will ever ask for, and would make the backtest's denominator wider than the product's.

The two markets' latest sessions differ by a day because 2026-08-25 was not an IDX trading
session — Yahoo serves no bar for it on `^JKSE`, `BBCA.JK` or `BBRI.JK`. Both markets
therefore run through their own latest complete session. Today's in-progress 2026-08-26 bar
was dropped by the app's finality rule, as it is at every ingest.

## The three US refusals

| Symbol | Reason |
| --- | --- |
| `ADBT` | `refused` — the provider states it will serve no history |
| `SNSC` | `refused` — same |
| `SVA` | `unresolved` — silent through the pull, the rest, and both sweeps |

`refused` and `unresolved` are kept apart deliberately (#104): both are absences, but a
stated refusal is a fact about the listing and silence is a fact that may still be about the
pull. `SVA` survived a one-minute rest and a five-minute one, which is the evidence that its
silence is not the crawl's own exhaustion.

That tail sweep is why the ledger can be read as survivorship evidence at all. The US pull's
first pass ended at **5,146 resolved, 350 silent** — and every one of those silences fell in
the last 500 symbols, the signature of a throttled tail rather than 350 dead listings. One
minute of rest recovered **349 of 350**. A fetcher that stopped at the first pass would have
written a 350-name refusal ledger, and Phase 2 would have read a 6.4% survivorship floor
that was really 0.05%.

## The IDX enumeration against the exchange's own count

IDX's [Company Profiles](https://www.idx.co.id/en/listed-companies/company-profiles/) page
reported **962 listed companies** on 2026-08-26. The crawl enumerated **838 candidates**
(plus `^JKSE`).

**The gap is 124 names, 12.9% of the exchange's listing.** That is the number Phase 2 needs
as a starting point rather than the research note's earlier "~840 against ~963" impression.
The gap is a property of Yahoo's IDX screener, not of this crawl: every name the screener
enumerated resolved, with zero refusals. So IDX's survivorship hole is entirely upstream of
the ledger — it is in what the provider will list at all — and the ledger cannot see it.
This is the opposite shape from US, where the enumeration is broad and the ledger holds the
absences.

Bounding that 124 is Phase 2's first deliverable, not this one's. What Phase 1 owes is the
number, and 124 is a number.

## The live store

`data/screener.duckdb` was `sha256:f753cf065aed5f0a7d4a73ca4e6296f95addda8b87b96806c3f933d90fbcf5c9`
before the crawl and the same after it. The backtest fetches its own history into its own
file and never writes live history (PRD story 49); `backtest.store.refuse_live_store` refuses
an output path that resolves to the live store, and `backtest.crawl` checks it before the
first request rather than after the last.
