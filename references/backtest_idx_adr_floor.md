# Does the 3.5% ADR floor suit IDX?

Companion to [the gate isolation](backtest_gate_isolation.md), which attributed `in_field`'s
sign flip to the ADR20 floor and the trend gate acting together, reported `ADR_FLOOR = 0.035`
as a finding, and measured **only the US**. This page asks the question that leaves open: the
floor is one constant serving two markets, and nobody had looked at the other one.

## The verdict

**Keep 3.5%, and do not make the constant per-market on this evidence.** Two findings, and the
first one is structural rather than numerical.

**The selection contrast cannot be run on IDX at all.** The trade record
(`trades_bo_gain10smaPct_desc.json`) is 828 trades over 312 distinct tickers. 181 of them
resolve against the store's bars, and **every one is US**. There are no IDX picks, so there is
no picks-versus-field gap to measure there — not now and not with this record. #211's whole
apparatus is a contrast between his trades and the field; on IDX only the field half exists.
Anything said about IDX here is a statement about the field alone.

**On the field half, the shared constant is behaving almost identically on both markets.**
Inside each market's own measured window, the field clears the rubric's 5% ADR dimension 84.36%
of the time on IDX against 84.92% on the US. Half a percentage point apart. Whatever is wrong
with a 3.5% floor is wrong with it in both places to the same degree, which is not an argument
for splitting the constant.

## Why the question is worth asking

Every other market-sensitive gate in `backtest/universe.py` **is** per-market, read from the
contract: the liquidity floor is $10M for the US and Rp 10B for IDX
(`universe.liquidity_floor`), and the Rp 100 nominal-price trim exists for IDX alone
(`universe.idx_price_floor`). `ADR_FLOOR = 0.035` is a bare module-level constant applied to
both. It is the one gate whose level nobody chose per market.

That is not obviously wrong — ADR is already a ratio, so it is dimensionless in a way a dollar
floor is not. But IDX is the more volatile market, and a threshold that is dimensionless still
lands in a different place on a different distribution.

## The field, before any detector runs

ADR20 across the liquidity-only field — the app-shaped universe of
[the isolation's](backtest_gate_isolation.md) fifth row, rebuilt over 2019-04-01 .. 2022-12-30:

| | 10th | 25th | median | 75th | 90th | name-sessions | symbols |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| IDX | 2.25% | 2.98% | **4.08%** | 5.82% | 8.32% | 85,358 | 329 |
| US | 1.16% | 1.88% | **2.83%** | 4.39% | 6.73% | 2,017,502 | 3,621 |

IDX is the more volatile market at every percentile, by roughly 1.2 points at the median. So
the same 3.5% cut bites much less hard there — it keeps 62.4% of the IDX field against 36.6%
of the US one.

That asymmetry is the obvious reason to reach for a per-market floor, and it is a trap. What
the floor is for is not selectivity. It is spread.

| floor | IDX kept / clears 5% | US kept / clears 5% |
| ---: | ---: | ---: |
| 3.0% | 74.6% / 46.0% | 46.1% / 42.2% |
| **3.5%** | **62.4% / 55.0%** | **36.6% / 53.2%** |
| 4.0% | 51.7% / 66.4% | 29.4% / 66.1% |
| 4.5% | 41.7% / 82.3% | 23.9% / 81.6% |
| 4.8% | 37.0% / 92.7% | — |
| 5.0% | 34.3% / 100% | 19.5% / 100% |

Read the clearance columns, not the kept ones: at any given floor the two markets leave the
rubric's ADR dimension with **the same** amount of spread, to within a couple of points, all
the way up. The constant is as well set on IDX as on the US, which as far as the code records
is luck — nothing in the docstring says IDX was checked.

Matching the *US's selectivity* on IDX would mean a floor near 4.8%. At 4.8% the IDX field
clears the 5% dimension 92.7% of the time. That is the dimension dead, and what it buys is a
smaller field that no part of the method asked for.

## The field the run actually scores

The table above is over universe members. The rubric scores **detections**, which are a
volatile subset of any universe — a name that has built a base and tightened is not a typical
name. So the numbers that matter are these, taken from the store's own persisted detections
inside each market's measured window:

| | detections | sessions | clears the 5% dimension |
| --- | ---: | ---: | ---: |
| IDX | 3,957 | 782 | **84.36%** |
| US | 35,971 | 821 | **84.92%** |

Detection-level clearance runs about 30 points above universe-level, in both markets, and the
two markets still land on top of each other.

Sweeping the floor upward from where it sits, on IDX detections:

| floor | field kept | clears 5% |
| ---: | ---: | ---: |
| **3.5%** | **99.5%** | **84.8%** |
| 4.0% | 95.6% | 88.2% |
| 4.5% | 89.9% | 93.9% |
| 5.0% | 84.4% | 100% |
| 6.0% | 73.5% | 100% |

Raising the floor on IDX is a bad trade at every level. It removes almost none of the field —
89.9% survives a 4.5% floor — because detections are volatile already, and it takes the
dimension from 84.8% to 93.9%. All cost, no benefit.

**The one direction that could help cannot be measured from this store.** The run never generated
detections below the gate, so a floor under 3.5% cannot be swept here any more than #211 could
read a dropped gate off the persisted `universe` rows. Answering it needs re-detection over a
wider universe, which is a run, not a query.

## What this does and does not license

- **It does not license moving `ADR_FLOOR`, in either direction.** Nothing here proposes a
  change, and a change would still go through ADR 0002's evidence rule, still re-open the
  findings §6 trade-off, and still invalidate the run's persisted denominator.
- **It does not license a per-market split.** The evidence points the other way: the two
  markets track each other closely enough that one constant is defensible.
- **It does not soften #211's finding — it extends it.** At 84–85% clearance the ADR dimension
  has little spread left to discriminate on in *either* market. The docstring's claim that
  1.5pp of clearance below the rubric's 5% preserves that spread does not hold on IDX either.
- **It says nothing about whether the rubric ranks on IDX.** That is an outcome question and
  belongs to `backtest.ranking`, not here.
- **It cannot be turned into an IDX `in_field` figure.** No IDX picks exist. If an IDX
  selection contrast is ever wanted, it needs an IDX trade record first, and that is a
  data-collection problem rather than a measurement one.

## Reproducing this page

- **The universe-level rows** rebuild the liquidity-only field from `data/screener.duckdb`
  bars over 2019-04-01 .. 2022-12-30: ADR20 as `SMA20(high / low − 1)`
  (`screener.indicators.adr`), ADTV as the 20-bar median of unadjusted `close × volume`
  (`screener.universe.median_dollar_volume`) against the contract's per-market floor, plus
  IDX's Rp 100 trim on `adj_close`.
- **The detection-level rows** read `data/backtest.duckdb`'s `detections` directly. Every
  detection sits inside the store's persisted `universe` — checked, 0 of 13,080 IDX and 0 of
  99,034 US rows fall outside it. The measured window per market is 2019-04-01 .. 2022-12-30
  with the first 126 sessions dropped for burn-in, matching `field_gate_isolation`'s
  `WINDOW_BURN_IN`.
- **The dimension** is `det.adr >= 0.05` — `screener.score.ADR_MIN`, read straight off the
  stored detection rather than re-derived.

### Checking this against #211

The US measured window reconstructs #211's field **exactly**: 35,971 detections over 821
sessions, the same two figures its cell reports. Restricted further to the evaluation sessions
of his replayable trades — the denominator `dimension_contrasts` uses — this page's method
gives 89.88% against the committed **90.7%**. The residual is `field_match`'s held-cell
restriction, which drops detections this page's SQL keeps; it is under a point and does not
move any conclusion here.

A note on the boundary: the lowest ADR among stored detections is 2.874% on IDX and 2.588% on
the US, both under the 3.5% gate. That is not a leak. The gate reads ADR through t−1 while the
detection records ADR at the signal bar, so a name can pass on Monday's series and print a
quieter Tuesday. It is why the 3.5% row above keeps 99.5% of detections rather than all of
them.
