# The out-of-sample backtest — findings

**Study:** every setup the detector names, taken mechanically, across two markets and
fourteen years ([the plan](../docs/out-of-sample-backtest-plan.md), PRD #182).
**Scope:** US and IDX, 2012-01-01 through each market's latest complete session, reported
separately throughout. Long breakout, end-of-day, **signal level**.
**Status of the app:** unchanged. No constant in `detection.py`, `score.py`, `universe.py`,
`ranks.py` or `relative_strength.py` is touched by this run or by this write-up. One change is
*licensed* by it and named below; naming it is what the contract required, and spending it is
a separate ticket.

**A plain-language version of this document** — same numbers, same conclusions, no assumed
vocabulary — is at [`backtest_findings-plain.md`](backtest_findings-plain.md). This file
remains the authority: its figures are the ones checked against the committed run output.

[`qullamaggie-replay-findings.md`](qullamaggie-replay-findings.md) measured 828 entries a
trader **took**, which is why its §9 reports no precision and no false-positive rate: it had a
numerator and no denominator. This run built the denominator. It answers what that study could
not — does the *method* have an edge, or did the *trader*?

> **Every magnitude below is measured**, against `data/backtest.duckdb` — 15.1M bars, US
> 5,495 symbols and IDX 840, 2011-01-03 onward, crawled 2026-08-26 (#187) and replayed forward
> in one unbroken pass per market (#198). 96,914 US detections over 3,682 measured sessions and
> 12,821 IDX over 3,542. The figures were readable only because all six of
> [Phase 6](#the-anchors)'s anchors settled first. Nothing here is projected; where a number is
> absent it is because the measurement is impossible, and it says so.

---

## The headline, and its bound

**One pre-registered metric, fixed before any code ran**: arm B's after-cost expectancy in R,
per market, per year. Arm B is the pure 10MA trail — the reference set's primary exit, so the
headline stays comparable to it. Both windows are reported because the sample contains a
crash and a mania: the full window, and the same window with 2020–21 taken out.

Each figure is printed beside its **pessimistic twin** — the same metric re-run with the
survivorship hole assigned a full stop-out. The twin is not a footnote and never was. On the
US it is larger than the effect the run is looking for.

| | window | expectancy | pessimistic | trades | symbols |
| --- | --- | ---: | ---: | ---: | ---: |
| **US** | full | **+0.050R** | **−0.363R** | 12,311 | 1,631 |
| **US** | excluding 2020–21 | **−0.081R** | **−0.446R** | 9,092 | 1,396 |
| **IDX** | full | **+0.680R** | **+0.418R** | 1,196 | 247 |
| **IDX** | excluding 2020–21 | **+0.284R** | **+0.072R** | 986 | 225 |

Costs are charged both sides at the contract's per-market rates — 0bps commission + 5bps
slippage per side on the US, 15bps + 25bps on IDX. Intervals are a 2,000× bootstrap
**clustered by symbol**, because a stock throwing three signals in a fortnight contributes
three correlated rows and row-counting the significance flatters every p-value.

**The bias bound, stated here rather than later.** The two markets' holes were counted by
different instruments and are not the same quality of number:

- **US — 37.7%**, weighted by how long each missing name was listed (51.8% by raw name count),
  measured against a dated listing spine of 96 archived Nasdaq Trader captures. At that weight
  the missing population contributes 0.605 trades for every covered trade, each a full stop.
  That costs the US headline **0.413R**, taking +0.050R to −0.363R, and it means **the
  pessimistic twin is negative for any headline below +0.605R** — a figure no breakout
  expectancy in this repo comes near. On the US the bound does not qualify the headline; it
  is eight times the size of it, and it points down.

  The two numbers are different quantities and are easy to run together: **0.605 is a count**
  (missing trades per covered trade) and **0.413R is the drag on the mean** that count
  produces. Neither is the other.
- **IDX — 12.7%**, counted from the enumeration side, because no free source reconstructs a
  dated Jakarta roster. It is neither exposure-weighted nor separated from recycled tickers, so
  **IDX's bound is optimistic in a known direction: the true bound can only be lower.** Its
  recycled half is reported *unmeasured* rather than zero — "we could not tell" and "there are
  none" are opposite findings.

**The markets are never pooled**, here or anywhere below. Findings §8 measured that shapes
travel between US and IDX and magnitudes do not, so a combined figure would describe neither.
There is no total in this document to read.

## The verdict, in the words the contract fixed in advance

Both criteria were written into [Phase 0](../docs/out-of-sample-backtest-plan.md#phase-0--the-run-contract)
before a line of the run existed, and each carries the change it licenses, so the decision was
made then rather than in the moment. Evaluated by `python -m backtest.verdict`; the payload is
[`backtest_verdict.json`](backtest_verdict.json).

**The kill did not fire.** It is global by design — it needs *both* markets at or below zero
on *both* windows, because findings §8 says magnitudes do not transfer, so one market failing
is evidence about that market rather than about the method. The US is +0.050R on the full
window and Jakarta is positive on both.

**US — inconclusive.** +0.050R on the full window and −0.081R with 2020–21 excluded: positive
on one window and not the other, so it neither ships nor fails. What it licenses, verbatim:

> nothing. The run is reported as inconclusive, and reaching for a swept variant to break the
> tie is the failure mode the contract exists to prevent

That clause has a live temptation behind it. A score floor of 4 lifts the US to +0.153R on the
full window — one of eight variants tried, and itself +0.007R once 2020–21 comes out. It is not
in the verdict and it does not break the tie.

**IDX — ship**, and it is the only market anything is licensed in. +0.680R and +0.284R across
the two windows, with the pessimistic bound holding at +0.418R and +0.072R. What it licenses,
verbatim:

> the change this licenses is named in the write-up before any constant moves, and goes through
> the calibration rule (findings §7) like any other; it is licensed only in the market that
> passed

**Read the second IDX window before quoting the first.** +0.072R is thin, it is the figure the
ship criterion actually turns on, and it rides on the weaker of the two bounds. The verdict
carries that caveat on the market's own block rather than in a note, and this document does the
same.

**Why the kill line is drawn on the survivor-biased number and the ship line is not.**
Survivorship inflates in a known direction, so a failure on the biased figure is decisive — the
honest number can only be worse. A *pass* proves much less, which is why ship has to clear the
bound and kill does not.

## The change this licenses

The ship verdict's own condition is that the change be **named in the write-up before any
constant moves**. This is that naming. Nothing in the app moved to earn it and nothing moves
here.

**The change: settle `Relative move`'s admission threshold, on IDX, against outcomes.**

ADR 0005 admits a candidate dimension on a **selection contrast** — did he pick names the
dimension fires on — because when the rule was written no outcome variable existed. `Relative
move` was measured on both fields and then stalled: it landed **0.06pp inside** a threshold the
ADR itself calls a judgement rather than a measurement, and nothing has shipped and no third
candidate has registered since. That threshold cannot be settled by the contrast that keeps
colliding with it.

This run gives the same dimension an outcome variable, and on IDX it is the one cell in the
whole matrix that comes back **predicts**: a hit-minus-miss gap of **+1.927R** with a
symbol-clustered interval of [+0.57, +3.14] entirely above zero, on 1,087 hits against 92
misses ([below](#do-the-registered-candidates-predict-or-only-select)). It is also the only
market that ships, which is the coincidence that makes the licence usable rather than merely
interesting.

Four limits on the licence, all of them binding:

- **It is licensed only in the market that passed.** Nothing here licenses a `Relative move`
  change on the US, where the same dimension returns no evidence it predicts.
- **It goes through the calibration rule** — ADR 0002, as findings §7 restates it — like any
  other change. An outcome result is evidence entering that rule, not a bypass around it.
- **It is not an ADR 0005 admission.** That rule's instrument is the selection contrast; an
  outcome claim is a different claim about the same dimension and neither converts into the
  other. What this licenses is *settling the threshold*, not overriding it.
- **It is licensed, not spent.** No weight moved, the rubric is still v3, and the register is
  unchanged. Spending it is a separate ticket with its own evidence rule.

**Spent in #221**, which wrote that evidence rule as
[ADR 0006](../blob/main/docs/adr/0006-what-an-outcome-result-licenses.md) and then applied it.
Two corrections to the four limits above, both recorded in that ADR:

- **The calibration-rule citation was loose.** ADR 0002 governs *loosening a gate* and does not
  govern admission — the same distinction §7 already draws for the stop convention and the
  tightness restructure. Admission is ADR 0005's, as narrowed by 0006.
- **The market limit held, and the licence still reached both markets.** Not on the +1.927R,
  which is a magnitude and stays in Jakarta, but on **sign agreement across both markets** —
  `Relative move` positive in each, `RS line` negative in one — which is a shape and travels
  under §8. `Relative move` was admitted at ×1 as `RUBRIC_VERSION = 4`, provisionally, in #222.

---

## What was measured, and how

**Point-in-time throughout.** Every value entering a decision is computed from bars at or
before that decision's session — universe gates and regime at t−1, the entry filled the session
after the trigger. A look-ahead bug produces a beautiful equity curve and no error message, so
the claim is held by a test that shifts a future bar into an entry decision and asserts the
result is unchanged, not by care.

**The universe is the contract's, not the app's.** Three gates measured through t−1 — close >
SMA50, ADTV ≥ $10M (US) or Rp 10B (IDX) as a 20-day median, ADR20 ≥ 3.5% — plus a Rp 100
nominal-price trim on IDX. That trim is **data validity, not cost control**: below it Jakarta
quotes hit the tick grid hard enough that range geometry stops meaning what it means elsewhere.
It is not a penny-stock filter and carries no implied cost story.

Two consequences worth stating before any count is read. The contract's universe is
**stateless** where the app's carries a hysteresis band, so names oscillating around the
liquidity floor churn in and out day by day — nearly free at signal level, where each signal is
evaluated on its own session, and a real difference at portfolio level. And the SMA50 gate
**overlaps the detector's own trend logic**, so detection counts fall against an unfiltered run:
that is the gate working, not the detector becoming more selective.

**Regime conditions and never filters.** Nothing is excluded by regime anywhere in the run;
every state got to trade, and each state's expectancy is measured rather than assumed. That is
what makes the counterfactual below arithmetic instead of a model.

**Three exit arms off one entry and one stop** — A (half off at day 5, remainder on a 10MA
trail), B (pure 10MA trail), C (pure 20MA trail) — so any difference between them is
attributable to the exit alone. Arm B is the headline and the only arm the verdict reads.

## The denominator — precision, at last

The figures no prior study in this repo could produce, because none had a control group.
Committed at [`backtest_figures.json`](backtest_figures.json), printed at
`backtest_figures.txt`.

| | US | IDX |
| --- | ---: | ---: |
| Measured sessions | 3,682 | 3,542 |
| Detections | 96,914 | 12,821 |
| Detections per session | 26.3 | 3.6 |
| **The share that trigger** | **12.8%** (12,362 of 96,830) | **9.5%** (1,203 of 12,727) |
| Never broke — asked, and the market said no | 84,468 | 11,524 |
| Undecided — the bars could not answer | 84 | 94 |
| **Precision, arm B** | **3.1%** (3,010 of 96,779) | **2.4%** (302 of 12,720) |
| Win rate, arm B | 24.4% (3,010 of 12,311) | 25.3% (302 of 1,196) |

**That is the false-positive rate findings §9 could not report**, and #149 could only record
as *volume carrying no verdict*. Roughly one detection in eight trades at all, and about one in
thirty-two closes green before costs. Read the two rates as the different questions they are:
the detector names thirty-two setups for every one that pays, and the trader who takes all
thirty-two wins on one trade in four, because the ones it never asks about never cost anything.

**Detections per session are not stable across the window** — the US runs 7.7 per session in
2012 against 73.7 in the eight months of 2026, and IDX's tall 2020 cell is the same volatility
arriving in a second market rather than a like-for-like magnitude. Read the panels for shape,
not for level. **No month in either market is a hole**: 176 months each, all covered.

## What the third arm buys

Arm A takes half the position off at the close of day 5 and trails the rest — the trader's own
documented behaviour, and the one arm with no counterpart in the reference set. It trades tail
for hit rate **by construction**, so the question Phase 5 asks is whether it raises expectancy
or merely smooths it. Those are different results and only one of them is a reason to adopt it.

The hit-rate half is visible before any expectancy is read: precision runs 3.6% / 3.1% / 2.6%
on the US for arms A / B / C and 2.8% / 2.4% / 2.2% on IDX, with the win rate ordering the same
way (28.4% / 24.4% / 20.6% on the US). The longer the trail, the fewer trades close green and
the larger the survivors have to be.

The expectancy half, **before costs** — the arms are simulated ahead of the phase that charges
commission and slippage, so these are not comparable to the headline and are not a second
headline. Payloads at [`backtest_arms_US.json`](backtest_arms_US.json) and
[`backtest_arms_IDX.json`](backtest_arms_IDX.json):

| arm | US, per trade | IDX, per trade |
| --- | ---: | ---: |
| A — half off day 5, remainder trailed | +0.096R (n=12,311) | +0.683R (n=1,196) |
| B — 10MA trail | +0.096R (n=12,311) | +1.062R (n=1,196) |
| C — 20MA trail | +0.279R (n=12,283) | +1.002R (n=1,194) |

**Arm A smooths; it does not raise expectancy.** It matches arm B on the US to three decimals
and gives up 0.379R per trade on IDX, in exchange for the four-point-higher hit rate above.
Taking half off at day 5 sells exactly the part of the distribution the method lives on, which
is what a momentum method's own arithmetic predicts and is now measured rather than assumed.

**Arm C is the best US arm here, and that changes nothing.** The pre-registered metric is arm B
alone, chosen before the run because it is the reference set's primary exit and keeps the
headline comparable. Promoting arm C on this table would be the same failure mode as promoting
a swept threshold, arriving through a different door — three arms are three views of one
dataset before any threshold is swept. The result is recorded as what it is: a question worth a
run of its own, with its own contract.

Two rates that are routinely quoted as one, kept apart here because they differ in the
denominator and the difference is the point. **Precision** is favourable outcomes over every
*answered* detection, the ones that never broke included — a figure about the **detector**: of
everything it named, what share paid. **The win rate** is favourable outcomes over the trades
actually taken — a figure about the **exit**, and the one comparable to the reference set's own
shape, where 22.7% of his trades made money and the mean R was positive anyway. A method with a
24% win rate is not broken; a method with a 24% win rate and no right tail is.

Every rate carries its coverage, and two ways of deflating one silently are refused by
construction. **A detection the bars cannot answer is not a miss** — one sitting on the last
session of the window has not failed to trigger, nothing has asked it yet — so the trigger
share's denominator is the decided detections only. **A trade still running is not a loss**;
closing it at the last available close would invent an exit the rules never gave,
systematically, for every name open when the window ended, so an open trade leaves precision's
denominator and is counted separately. Both errors push the same way — they make the method look
worse — which is the direction nobody investigates.

The denominator figures are computed **before costs**, and the payload carries `costs_applied:
false` beside every one of them. The overstatement is larger on IDX, where the contract's fees
and spread are an order of magnitude above the US's.

## Does the rubric rank, out of sample?

**No evidence it ranks, in either market.** Full working in
[`backtest_score_ranking.md`](backtest_score_ranking.md), payload at
[`backtest_score_ranking.json`](backtest_score_ranking.json).

| | trades | symbols | gap, bottom → top | Spearman's rho | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| US | 12,350 | 1,637 | +0.461R [−0.38, +1.60] | +0.038 [+0.02, +0.06] | no evidence it ranks |
| IDX | 1,201 | 249 | −0.191R [−1.72, +1.54] | +0.075 [+0.01, +0.13] | no evidence it ranks |

The rule requires the gap **and** rho to have symbol-clustered intervals entirely above zero.
In both markets rho clears and the gap does not, which is the exact case the rule was written
to catch: a rho can be positive and negligible.

Two things in the bands are worth more than the headline. **The top band is not the best band
in either market** — the US peaks at 2.5★ and IDX peaks hard at 3.5★, and both fall at 4.0★. A
rubric that ranks does not do that. And **the bottom US band is reliably bad**: −0.335R on
2,608 trades across 889 symbols, interval entirely below zero, the only band in either market
that clears zero downward. So the score separates the worst material from everything else and
does not order anything above that floor. *Filters, does not rank* is the shape of these
tables, and it is a narrower claim than the product's.

**This is a null, not a refutation.** "No evidence it ranks" is never "the score does not
rank": one sample cannot license that. And it is not findings §4a — that measured a rate of
scores between his picks and the field, on the field v2's weights had been *fitted* to, at
p = 0.055. This measures after-cost R by score band on trades nobody selected, so the outcome
variable is independent of the weights. The two are never to be lined up as one.

## Do the registered candidates predict, or only select?

ADR 0005 admits a dimension on a selection contrast because outcomes were unavailable. They are
available now. Committed at
[`backtest_candidate_outcomes.json`](backtest_candidate_outcomes.json) and printed at
`backtest_candidate_outcomes.txt`.

| market | dimension | hit | miss | gap (hit − miss) | clustered 95% | verdict |
| --- | --- | ---: | ---: | ---: | --- | --- |
| US | `RS line` | −0.099R (n=2,705) | +0.092R (n=9,603) | −0.191R | [−0.45, +0.07] | no evidence it predicts |
| US | `Relative move` | +0.098R (n=11,014) | −0.298R (n=1,217) | +0.396R | [−0.03, +0.77] | no evidence it predicts |
| IDX | `RS line` | +1.066R (n=318) | +0.541R (n=874) | +0.525R | [−0.73, +1.89] | no evidence it predicts |
| IDX | **`Relative move`** | **+0.852R (n=1,087)** | **−1.075R (n=92)** | **+1.927R** | **[+0.57, +3.14]** | **predicts** |

One cell of four comes back positive, and it is [the one the ship
licenses](#the-change-this-licenses). The US `Relative move` gap points the same way and does
not clear — +0.396R on an interval that crosses zero at −0.03, which is a near miss and is
reported as a miss.

Three disciplines this table keeps, each of which would otherwise be misread:

- **The verdict is the gap's alone**, because ADR 0005 admits a dimension as a boolean. The
  rank correlation is reported beside it and excluded — and on the US it is *negative*
  (−0.021), which is worth seeing next to a positive gap.
- **The absent group is not a miss.** Detections whose candidate value is `NULL` — the question
  was never asked, because the name had not listed six months back or a price was missing at an
  anchor — get their own n and enter no gap. `Relative move`'s cut sits at **zero**, so an
  absence coerced to a number would land exactly on the boundary and let the strictness of a
  comparison decide a verdict nobody measured. What a shipped boolean would do with it is
  reported separately and sets no verdict.
- **This measurement admits no dimension and retires none.** It is not ADR 0005's instrument.
  Neither candidate's weight, the rubric version, nor the register moved.

## The regime posture, priced

The app prints "sit out" for `HOSTILE` and "reduced" for `CHOPPY` today, on no measured basis
at all. This is the measurement — the most product-relevant figure in the run. Payload at
[`backtest_regime_posture.json`](backtest_regime_posture.json), printed at
`backtest_regime_posture.txt`. State is the app's own, read off each market's index on the
**detection session** (t−1) — the night the candidate was listed with its posture beside it.

| state | US, full | US, excl. 2020–21 | IDX, full | IDX, excl. 2020–21 |
| --- | ---: | ---: | ---: | ---: |
| `FRIENDLY` | +0.070R (n=5,605) | −0.075R (n=3,783) | +1.502R (n=414) | +0.942R (n=330) |
| `CHOPPY` | +0.177R (n=3,782) | −0.050R (n=2,916) | +0.207R (n=465) | −0.100R (n=377) |
| `HOSTILE` | −0.154R (n=2,924) | −0.131R (n=2,393) | +0.300R (n=317) | +0.024R (n=279) |

**"Sit out" for `HOSTILE` — undecided in both markets, and the point estimates disagree.**
Sitting the state out would have changed the book by **+450.6R** over 2,924 US trades and by
**−95.0R** over 317 IDX trades. On the US the word points the right way; on IDX `HOSTILE` was
the middle state, not the worst, and sitting it out cost money. Neither interval decides it, so
the run leaves the app's word as unfounded as it found it — but it does establish that the same
word is not earning the same thing in the two markets.

**"Reduced" for `CHOPPY` — undecided, and on the US the point estimate points the wrong way.**
Judged against `FRIENDLY`, because "reduced" claims the state is worse to trade rather than
unprofitable, `CHOPPY` came in **+0.107R better** than `FRIENDLY` on the US full window and
−1.295R worse on IDX. A word that advises trading smaller in the state that paid slightly more
is not supported by this run in either direction.

Both verdicts are the **interval's, never the mean's**, and both are priced at **signal
level**: sitting a state out here removes its trades and frees no capital, because this run has
no shared position budget to redeploy. The figure is what the posture costs or saves directly,
never what it might buy — which is a portfolio question and is deferred.

**The two regime companions, reported and never conditioned on.** Breadth: median 49.1% (US)
and 46.2% (IDX). It is the column survivorship corrupts most directly — worse in a backtest
than live, because the names missing from the store are disproportionately the ones that later
died — so it is descriptive only and gates nothing. Follow-through: the index broke out on
22.5% of US sessions and 16.3% of IDX ones, and it is **unbiased where breadth is not**. The
index series carries no survivorship hole, so this run could legitimately reconstruct across
fourteen years the one regime signal the live app can never backfill.

## The sweep, and why the headline stands

Eight variants, swept **after** the pre-registered figure was computed and recorded — an
ordering the code enforces rather than the convention asks for: `backtest.sweep` cannot run
without a recorded headline to read off disk, and a sweep of a sweep is refused because it
would report the second count and hide the first. Two axes: the contract's per-market costs at
0.5×, 2× and 3×, and a floor on the replayed score at 3 through 7 of 8. Committed at
[`backtest_sweep.json`](backtest_sweep.json).

| | the pre-registered headline | the most flattering swept figure |
| --- | ---: | --- |
| US, full | +0.050R | +0.153R (score ≥ 4) |
| US, excl. 2020–21 | −0.081R | +0.007R (score ≥ 4) |
| IDX, full | +0.680R | +2.412R (score ≥ 7, n=183) |
| IDX, excl. 2020–21 | +0.284R | +1.628R (score ≥ 7, n=136) |

**None of these entered the verdict, and the headline stands against every one of them.** The
IDX score ≥ 7 row is worth reading precisely as the illustration it is: +2.412R on 183 trades
is what a winner-from-noise looks like, and the count of variants tried is printed beside it as
a field rather than a number the reader has to reconstruct. Three exit arms and three regime
states are already nine views of one dataset before any threshold is swept.

**The detection gate is not swept**, and the payload says so. The denominator was built against
the contract's four-lookback width, so a swept gate is a new crawl rather than a variant of this
run.

## The anchors

The plan's third rule is *anchor before believing*: the run had to reproduce figures already
committed to this repo, or explain the divergence in writing, before any new figure from it was
read. All six settled — one matches and five diverge with a written cause. The table as it
printed is at `backtest_anchors.txt`, the payload at
[`backtest_anchors.json`](backtest_anchors.json), and the causes are set out in
[`backtest_anchor_divergence.md`](backtest_anchor_divergence.md).

The one that matches is the one built to detect drift from here on: `in_field` over the
contract's stateless universe, **165 of 503, gap −5.01pp**. Getting there meant splitting that
anchor into one pin per universe, because §4b's gap is a property of the pair (rubric,
universe) — **+1.95pp under the app's universe, −5.01pp under the contract's** — so holding a
stateless-universe run to the app-universe figure was a subtraction between two numbers that
were never the same number. **No constant moved, no tolerance widened, and the sign check was
not waived**; a stateless run coming back positive still fails.

**Never cite findings §4b's gap without naming the field it was measured over.** That is the
rule the split leaves behind, and it applies to every future quotation of that figure.

## The caveats, carried with the same weight as the results

- **Survivorship, and it is the big one.** The US hole is 37.7% exposure-weighted, which is
  larger than the effect the run is looking for. Every US figure in this document should be
  read as an upper bound on a quantity whose pessimistic twin is negative.
- **The two bounds are not the same instrument.** The US bound rests on a dated listing spine;
  IDX's is an enumeration-side count with its recycled half unmeasured, so it is optimistic in a
  known direction. The market that ships is the market with the weaker bound.
- **The spine's count is a floor.** Its captures are roughly annual, so a name that listed
  *and* delisted between two of them appears in neither and is invisible to the count. The
  largest gap between captures is 552 days.
- **2020–21.** The tape rewarded momentum nearly everywhere. Every year is reported separately
  and every window figure has its 2020–21-excluded twin beside it, which is why the US verdict
  is inconclusive rather than positive.
- **IDX is thin.** 1,196 closed trades over 247 symbols across fourteen years, against 12,311
  over 1,631 on the US. The per-year IDX cells run to double digits and swing from −1.582R to
  +3.495R; they are diagnostics, not measurements.
- **`in_field` moves with the pair it is measured over**, and the stateless pin is a first
  measurement made by this run, so it detects drift rather than confirming this run.
- **Free adjusted EOD data.** Yahoo carries an *unlabelled* retroactive rescale for rights
  issues — measured on BBRI, pre-2021-09-08 OHLC scaled by exactly 10/11 with no split or
  dividend row to explain it. Geometry in ADR units is immune because both terms rescale
  together; absolute prices are not, including IDX's Rp 100 trim.
- **Cold start.** The contract's stateless universe has no hysteresis band, so this run and the
  app disagree about names oscillating around the liquidity floor. Nearly free at signal level;
  real at portfolio level; recorded rather than engineered away.

## What this cannot say

Named in advance, in [the plan](../docs/out-of-sample-backtest-plan.md#what-this-still-cannot-say),
and restated here unchanged. A limitation named in advance is a caveat; one discovered
afterwards is a retraction.

Even run perfectly, this measures **the detector as encoded**, on **free adjusted EOD data**,
over **one fourteen-year sample of two markets**, at **signal level**.

- **It cannot say what he would have traded.** It measures the detector's names taken
  mechanically, not a trader's selection from among them.
- **It cannot recover intraday behaviour.** Every decision is made on a daily close; what
  happened inside a session is invisible to it, including whether a stop that filled at the next
  open would have filled there.
- **It cannot speak to capacity, concurrency, drawdown path, or correlated clustering.** This is
  signal level: every qualifying signal is taken independently and equal-weighted, with no
  capital constraint, no concurrency cap and no position limit. In a momentum method the winners
  arrive together, so the portfolio question is **deferred rather than dismissed** — specified in
  the plan and not built.
- **It cannot make the delisted names reappear.** It can only bound their absence, which is what
  the pessimistic twin on every figure above is doing.

Three narrower ones this run adds to the list. It **cannot sweep the ADR floor downward**,
because the run never generated detections below the gate — answering that needs re-detection
over a wider universe, which is a crawl rather than a query. It **cannot measure an IDX
selection contrast**, because the trade record holds no IDX picks: on Jakarta only the field
half of that comparison exists. And it **cannot settle the US**, which is the honest content of
an inconclusive verdict rather than a gap to be closed by choosing a different variant.

## Reproducing this

**One command**, from the repository root:

```
bash scripts/backtest_headline.sh
```

It prints both markets, both windows, each figure beside its pessimistic twin, and the verdict
in the words the contract fixed — read back from the payloads committed under `references/`.
That path touches no bar, and it says so on its first line: what it checks is that the committed
result and this document still agree.

To recompute the figure from the bars themselves:

```
bash scripts/backtest_headline.sh --from-store data/backtest.duckdb
```

which re-runs the pre-registered metric, attaches Phase 2's bound, sweeps, and re-reaches the
verdict. **That path was run against the store on 2026-08-27 and reproduced all four figures and
both bounds exactly**, so the committed payloads are the ones the bars produce rather than a
recording that has drifted from them.

It needs the store built first, and the store is 1.1GB of bars that `.gitignore` keeps out of
the repository:

```
python -m backtest.crawl                                    # ~2h, paced; goes to the network
python -m backtest.full_run --store data/backtest.duckdb \
    --anchors references/backtest_anchors.json
```

The window and the markets come from [`backtest_run_contract.json`](backtest_run_contract.json)
rather than from the command line, so "the full run" is a fact about the contract instead of a
set of dates someone has to retype correctly.

**The other measurements**, each reproducing one section above:

```
python -m backtest.figures    --store data/backtest.duckdb --market US --market IDX
python -m backtest.ranking    --store data/backtest.duckdb
python -m backtest.candidates --store data/backtest.duckdb
python -m backtest.posture    --store data/backtest.duckdb
python -m backtest.simulate   --store data/backtest.duckdb --market US   # and --market IDX
python -m backtest.survivorship --store data/backtest.duckdb   # --fetch-spine goes to the network
```

Each takes `--out-json` and writes a contract-stamped payload; the committed ones are listed
below. `backtest.survivorship` without `--fetch-spine` reads the cached spine beside the store,
so the count is reproducible from committed inputs rather than from a second 101-minute crawl of
the Internet Archive.

## The committed payloads

Every figure above has one of these behind it, and each is stamped with the contract that
produced it.

| File | What it holds |
| --- | --- |
| [`backtest_run_contract.json`](backtest_run_contract.json) | The contract, fixed before any code ran |
| [`backtest_primary_metric.json`](backtest_primary_metric.json) | The pre-registered headline, per market per year, with the bound attached |
| [`backtest_survivorship.json`](backtest_survivorship.json) | The dated count of the hole, and the sensitivity |
| [`backtest_verdict.json`](backtest_verdict.json) | The contract's criteria evaluated, with the licence on each market |
| [`backtest_sweep.json`](backtest_sweep.json) | Eight variants, none of which entered the verdict |
| [`backtest_figures.json`](backtest_figures.json) | Detections per session, the trigger share, precision |
| [`backtest_arms_US.json`](backtest_arms_US.json), [`backtest_arms_IDX.json`](backtest_arms_IDX.json) | All three exit arms off one entry and one stop, before costs |
| [`backtest_score_ranking.json`](backtest_score_ranking.json) | Outcomes by score band, per market and per year |
| [`backtest_candidate_outcomes.json`](backtest_candidate_outcomes.json) | Both registered candidates against outcomes |
| [`backtest_regime_posture.json`](backtest_regime_posture.json) | Expectancy per regime state, and both counterfactuals |
| [`backtest_full_run.json`](backtest_full_run.json) | The run *over* the denominator — sessions persisted and measured, detections per market and per session, the references each market excluded, and the anchor gate it passed |
| [`backtest_anchors.json`](backtest_anchors.json) | Phase 6's table, as it settled |

**Two things this table does not hold, and the distinction matters to anyone reproducing.**
The **bar store** (`data/backtest.duckdb`, 1.1GB) and the **denominator store** beside it
(`data/backtest.duckdb.denominator.duckdb`, 446MB) are what *the denominator* names — one
persisted row per session per market, carrying universe membership, the regime state with its
companions, the rank table, and every detection with its full record and score breakdown.
`.gitignore` keeps both out of the repository, so every figure above is committed and the rows
underneath them are not. Rebuilding them is the `backtest.crawl` / `backtest.full_run` pair
[above](#reproducing-this); `backtest_full_run.json` is the *report* that run printed, not the
rows it read.

Their printed pages sit beside them as `.txt`, and the prose companions to individual
measurements are [`backtest_survivorship.md`](backtest_survivorship.md),
[`backtest_score_ranking.md`](backtest_score_ranking.md),
[`backtest_anchor_divergence.md`](backtest_anchor_divergence.md),
[`backtest_gate_isolation.md`](backtest_gate_isolation.md),
[`backtest_idx_adr_floor.md`](backtest_idx_adr_floor.md) and
[`backtest_store_coverage.md`](backtest_store_coverage.md).
