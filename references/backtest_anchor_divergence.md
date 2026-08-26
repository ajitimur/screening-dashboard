# The geometry anchors, and why the backtest store does not reproduce them

Phase 6 of [the out-of-sample backtest plan](../docs/out-of-sample-backtest-plan.md)
(PRD #182, issue #198). The plan's third rule is anchor before believing, and its escape
hatch is "reproduce the figure, **or** explain the divergence in writing". This is that
writing, for the one anchor group that diverges.

Issue #197 built the table and found the divergence; it left it unresolved and left the
anchors pinned at their committed values rather than widened to accommodate it. This page
resolves it, and the resolution is the reason the run below it is allowed to be read.

## The divergence

The three geometry anchors are medians measured from his bars at his entries. They hold
whatever the detector does, so they anchor the **store and the indicators** — which is why
they are checked first and why a failure stops everything downstream.

| | 3-bar range | 5-bar range | ADR20 at entry eve | n |
| --- | --- | --- | --- | --- |
| Committed (findings §3b) | 1.31 ADR | 1.86 ADR | 6.08% | 649 |
| `data/replay.duckdb` | 1.3105 | 1.8633 | 6.0812% | 649 |
| `data/backtest.duckdb` | **1.2752** | **1.7674** | **6.4277%** | **496** |

The replay store reproduces all three to the digit. The backtest store — the store this
run is built on — does not, and it is not close: the 5-bar median is off by 0.10 ADR and
the ADR median by 0.35 percentage points, both far outside the anchors' tolerances.

## The cause: the sample, not the bars

The bars are identical. Of the 496 trades both stores can measure, **all 496 carry
bit-identical geometry** — every 3-bar range, every 5-bar range and every ADR agrees to
within 1e-9. There is no adjustment bug, no ingest bug and no indicator drift. The stores
disagree about *which trades are in the sample*, and about nothing else.

Measured off `replay.duckdb` alone, changing only which trades are kept:

| Sample | n | 3-bar | 5-bar | ADR20 |
| --- | --- | --- | --- | --- |
| A — every trade with bars (the committed sample) | 649 | 1.3105 | 1.8633 | 6.0812% |
| B — A minus references excluded by design (#162) | 499 | 1.2768 | 1.7685 | 6.4076% |
| C — B minus names never enumerated | 496 | 1.2752 | 1.7674 | 6.4277% |
| `backtest.duckdb`, measured directly | 496 | 1.2752 | 1.7674 | 6.4277% |

Row C and the backtest store agree to every digit printed. The backtest store's geometry
*is* the replay store's geometry over the same names.

The 153 trades between them split two ways, and the split matters because one half is the
design working and the other is a known defect:

**150 trades, 43 tickers — the reference exclusion, working as intended.** They are ETFs:
`SOXL`, `TQQQ`, `TNA`, `NUGT`, `JNUG`, `GBTC`, `ETHE`, `UVXY`, `LABU`, `ARKK` and thirty-three
more. Every one carries the enumeration reason `unread_reference`. The backtest's universe
ranks candidates, and reference instruments are computed like anything else and never
ranked (#162, and CONTEXT.md's *Instrument*). He traded them; the denominator this run
builds cannot, so a store scoped to what the run can rank will never carry them.

This half of the divergence is **not a bug and must not be tolerance-widened away.** The
committed anchors were measured over a sample that includes his ETF trades, and the
backtest store is scoped to exclude them. The two are measuring different populations on
purpose, and an anchor quietly widened to span both would stop being able to detect the
thing it exists to detect.

**3 trades, 1 ticker — survivorship.** `BBBY` is common stock, not a reference. It appears
in neither the listed nor the excluded set of `data/backtest.duckdb.enumeration.US.json`:
it was never enumerated at all, because the crawl enumerates from a current listing snapshot
and Bed Bath & Beyond was delisted in 2023. This is survivorship bias, it is a real defect,
and it is **not** fixed here — [#196](../docs/out-of-sample-backtest-plan.md) owns bounding
it.

Its effect on this anchor is small (row B → row C: 0.0016 ADR, 0.0011 ADR, 0.02pp) but its
effect on the wider run is not, and the small number here should not be read as reassurance.
Across the whole 828-trade reference set the same enumeration gap swallows **82 tickers and
144 trades** — the geometry anchor happens to sit on the part of it that is nearly empty,
because most never-enumerated names also lack the bar history the anchor needs.

## What follows from this

- The geometry divergence is **explained**, and the cause is sample composition, proven by
  the fact that the shared 496 trades agree bit-for-bit and that row C reproduces the
  backtest store exactly.
- The anchors stay **pinned at their committed values**, as #197 left them. They are correct
  for the population they were measured over.
- The store and the indicators are **anchored**: whatever else is wrong with this run, the
  bars are the bars the reference study measured.
- The survivorship residual rides on every result out of this run as one line, and is
  bounded by #196 rather than by this page.

The divergence is recorded through the mechanism rather than only here — the run is
anchored with an explicit written cause per diverging anchor, so a reader who never opens
this file still cannot mistake a divergence for a match:

```
python -m backtest.anchors --store data/backtest.duckdb \
    --field-measurements references/backtest_field_anchors.json \
    --explain median_range_3bar_adr="..." \
    --explain median_range_5bar_adr="..." \
    --explain median_adr_at_entry_eve="..." \
    --out-json references/backtest_anchors.json
```

A sign flip in §4b's gap is not explainable and no cause written here or anywhere else
waives it; that one stops the run.

## Reproducing this page

Every number above comes from the two committed stores and the committed reference set:

- the medians, from `backtest.anchors.measure_geometry` against each store;
- the split, from `data/backtest.duckdb.enumeration.US.json`'s exclusion reasons and
  `data/backtest.duckdb.coverage.US.json`'s `stored` list;
- rows A, B and C, by applying those two lists as filters to the replay store's sample.
