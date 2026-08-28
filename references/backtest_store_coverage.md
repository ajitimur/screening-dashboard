# The backtest bar store — coverage evidence

Phase 1 of [the out-of-sample backtest plan](../docs/out-of-sample-backtest-plan.md)
(PRD #182, issue #187). The store is the run's raw material; this file is the evidence that
it is complete, because a store whose gaps are unrecorded is survivorship bias entering
through the back door.

Crawled **2026-08-26** with `python -m backtest.crawl --out data/backtest.duckdb`.

## Two records per market, because there are two ways to go missing

A name can be absent from the store because the crawl asked and got nothing, or because the
crawl never asked. The refusal ledger only sees the first. So each market commits both:

- `data/backtest.duckdb.enumeration.{US,IDX}.json` — everything the provider listed, the
  subset the crawl asked about, and every excluded name with the rule that excluded it.
- `data/backtest.duckdb.coverage.{US,IDX}.json` — of the names it asked about, which ended
  with bars and which ended with a refusal row naming why.

Between them every listed name carries exactly one of four verdicts. The store itself is not
committed — 850 MB, and `data/*.duckdb` is ignored — so these four files and this page are
what a later reader checks it against.

## What was crawled

| | US | IDX |
| --- | --- | --- |
| Listed by the provider | 13,141 | 840 |
| Excluded: reference nothing reads | 5,641 | 0 |
| Excluded: not common stock | 2,002 | 0 |
| **Crawled** | **5,498** | **840** |
| Stored (bars on disk) | 5,495 | 840 |
| Refused (a row naming why not) | 3 | 0 |
| Bar rows | 13,238,360 | 1,818,253 |
| Distinct symbols in the store | 5,495 | 841 |
| First session | 2011-01-03 | 2011-01-03 |
| Latest session | 2026-08-25 | 2026-08-24 |

`5,641 + 2,002 + 5,498 = 13,141` and `5,495 + 3 = 5,498`; `0 + 0 + 840 = 840` and
`840 + 0 = 840`. Both sums are asserted in code — `Enumeration.check` and
`BuildCoverage.check` — before either record is written.

The exclusions are not this crawl's own rule. `backtest.crawl.narrow` calls
`screener.pipeline.fetch_set`, the same function the nightly pull calls, so the backtest's
denominator is the app's by construction rather than by resemblance: the market's own index,
whose bars the contract's regime reads, plus the candidates that can enter a universe at all.
The 5,641 references are ETFs no code path reads; the 2,002 are listings the universe's
instrument-type rule excludes whatever their bars say. Crawling them would spend paced hours
on bars nothing will ever ask for, and would make the backtest wider than the product.

The two markets' latest sessions differ by a day because 2026-08-25 was not an IDX trading
session — Yahoo serves no bar for it on `^JKSE`, `BBCA.JK` or `BBRI.JK`. Both markets run
through their own latest complete session. Today's in-progress 2026-08-26 bar was dropped by
the app's finality rule, as at every ingest.

## The three US refusals

| Symbol | Reason |
| --- | --- |
| `ADBT` | `refused` — the provider states it will serve no history |
| `SNSC` | `refused` — same |
| `SVA` | `unresolved` — silent through the pull, and through four rests across two runs |

`refused` and `unresolved` are kept apart deliberately (#104): both are absences, but a
stated refusal is a fact about the listing, and silence may still be a fact about the pull.
`SVA` stayed silent through a one-minute rest and a five-minute one on the first crawl and
both again on the resumed one, which is the evidence that its silence is not the crawl's own
exhaustion.

That tail sweep is why the ledger can be read as survivorship evidence at all. The US pull's
first pass ended at **5,146 resolved, 350 silent** — and every one of those silences fell in
the last 500 symbols, the signature of a throttled tail rather than 350 dead listings. One
minute of rest recovered **349 of 350**. A fetcher that stopped at the first pass would have
committed a 350-name refusal ledger, and Phase 2 would have read a 6.4% survivorship floor
that is really 0.05%.

## The IDX enumeration against the exchange's own count

IDX's [Company Profiles](https://www.idx.co.id/en/listed-companies/company-profiles/) page
reported **962 listed companies** on 2026-08-26. Yahoo's screener enumerated **839 candidates**
(plus `^JKSE`). Both numbers are in the IDX enumeration record, the second as `listed`, the
first as `listed_by_exchange` with its source — provenance in the artefact rather than only
in this paragraph.

**The gap is 123 names, 12.8% of the exchange's listing.** That is the number Phase 2 starts
from, in place of the research note's earlier "~840 against ~963" impression. The gap sits
entirely upstream of the ledger: every name the screener listed resolved, with zero refusals.
IDX's survivorship hole is therefore in *what the provider will list at all*, and the ledger
cannot see it — the opposite shape from US, where the listing is broad and the ledger holds
the absences.

### The IDX screener's membership is not stable

Worth carrying into Phase 2, because it bounds how much that 123 can be trusted. The first
crawl enumerated 839 names at 09:37; the resumed one enumerated 840 at 09:54. The difference
is not one name but three — two arrived and one, **`SOHO.JK`**, left. `SOHO.JK` is not
delisted: the store holds 1,325 of its bars, through 2026-08-24, the latest IDX session.

So the screener dropped a live, actively-trading name from its listing inside seventeen
minutes. The 123-name gap is a snapshot of a membership that churns, not a stable roster of
the suspended and delisted, and a single enumeration understates coverage by however much it
happened to drop that minute. Reconstructing the listing spine from a second source — which
Phase 2 already plans — is the fix, not a longer look at this one.

It also means the store is worth more than any one enumeration: it still holds `SOHO.JK`,
which is why the IDX store carries 841 distinct symbols against a 840-name enumeration. A
crawl that rebuilt from scratch each time would have dropped it. Retaining names that fall
out of the provider's listing is the behaviour Phase 2 wants, so this is recorded rather than
reconciled away.

## The live store

`data/screener.duckdb` was
`sha256:f753cf065aed5f0a7d4a73ca4e6296f95addda8b87b96806c3f933d90fbcf5c9` before the crawl
and unchanged after it and after both resumed runs. Its mtime, 2026-08-26 09:06, predates the
first crawl at 09:18 — which is the part that stays checkable, since a hash of a file the
nightly run legitimately rewrites cannot be re-derived later.

The guarantee does not rest on that measurement. The backtest fetches its own history into
its own file and never writes live history (PRD story 49): `backtest.store.refuse_live_store`
refuses an output path that resolves to the live store, on the resolved path so a relative
spelling or a symlink is refused too, and `backtest.crawl` calls it before the first request
rather than after the last.
