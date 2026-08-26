# Does the rubric rank, out of sample?

Issue #194, PRD #182 Phase 5. The machinery landed with #206 and then sat unused for want of
a denominator over the full window. #198 built that denominator, #211 established what it does
and does not mean, and this page is that measurement, finally run.

Companion to [the gate isolation](backtest_gate_isolation.md), which answers a different
question and is not a substitute for this one. That page asks whether **his picks out-score
the field** — a selection contrast. This asks whether **a higher score predicts a better
result** — an outcome contrast. Settling the first says nothing about the second.

## The verdict

**No evidence it ranks, in both markets.**

| | trades | symbols | gap, bottom → top | Spearman's rho | verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| US | 12,350 | 1,637 | **+0.461R** [−0.38, +1.60] | **+0.038** [+0.02, +0.06] | no evidence it ranks |
| IDX | 1,201 | 249 | **−0.191R** [−1.72, +1.54] | **+0.075** [+0.01, +0.13] | no evidence it ranks |

`VERDICT_RULE` requires the gap and rho to have symbol-clustered intervals **both** entirely
above zero. In both markets rho clears and the gap does not. That is not a technicality — it
is the exact case the rule was written to catch. A rho of +0.038 is positive and negligible,
and the rule says so in as many words: *"a rho can be positive and negligible."*

Read the last clause of the rule before quoting any of this: **"'no evidence it ranks' is
never 'the score does not rank': one sample cannot license that."** This is a null, not a
refutation.

## What the ladder actually looks like

**US**, six bands over the whole measured window:

| band | deciles | n | symbols | after cost | clustered 95% |
| --- | --- | ---: | ---: | ---: | --- |
| 0.5–1.5★ | D1–D2 | 2,608 | 889 | **−0.335R** | [−0.56, −0.10] |
| 2.0★ | D3–D4 | 2,828 | 997 | +0.185R | [−0.07, +0.43] |
| 2.5★ | D5–D7 | 3,515 | 1,056 | **+0.226R** | [−0.03, +0.50] |
| 3.0★ | D8 | 2,002 | 877 | +0.068R | [−0.27, +0.40] |
| 3.5★ | D9 | 1,027 | 576 | −0.006R | [−0.38, +0.38] |
| 4.0★ | D10 | 331 | 255 | +0.125R | [−0.64, +1.25] |

**IDX**:

| band | deciles | n | symbols | after cost | clustered 95% |
| --- | --- | ---: | ---: | ---: | --- |
| 0.5–1.5★ | D1 | 228 | 107 | −0.201R | [−1.02, +0.82] |
| 2.0★ | D2–D4 | 263 | 125 | −0.071R | [−0.98, +0.91] |
| 2.5★ | D5–D6 | 342 | 151 | +0.571R | [−0.52, +1.95] |
| 3.0★ | D7–D8 | 180 | 107 | +1.337R | [−0.45, +3.59] |
| 3.5★ | D9 | 147 | 84 | **+3.099R** | **[+1.00, +5.51]** |
| 4.0★ | D10 | 36 | 31 | −0.392R | [−1.73, +1.25] |

Six bands rather than ten because a score value is atomic and never splits across buckets —
an eight-point score cannot produce ten of them. Every closed trade landed inside a band:
`outside_the_cut` is 0 in both markets.

Two things in these tables are worth more than the headline.

**The top band is not the best band in either market.** The US peaks at 2.5★ and IDX peaks
hard at 3.5★, and both then fall at 4.0★. A rubric that ranks does not do that. Whatever the
top of the scale is selecting for, it is not outcome — and on IDX the 3.5★ band is the only
band anywhere whose interval sits entirely above zero, with the band above it negative.

**The bottom US band is reliably bad.** −0.335R, interval entirely below zero, on 2,608 trades
across 889 symbols. It is the only band in either market whose interval sits entirely below
zero. So the score does separate the worst material from everything else. It just does not
order anything above that floor. "Filters, does not rank" is the shape of these tables, and it
is a narrower claim than the product's.

## The year rows, and why not to mine them

Fifteen years per market, and they are diagnostics rather than measurements — the cut is made
once per market on the whole window precisely so a band means the same score in every row.

| | too thin to say | no evidence | ranks |
| --- | ---: | ---: | ---: |
| US | 3 | 12 | 0 |
| IDX | 13 | 1 | **1** |

**IDX 2022 is the single row anywhere that reads "ranks"** — gap +2.969R [+0.22, +7.56], rho
+0.254 [+0.05, +0.42], on 116 trades in 41 symbols. Both statistics clear zero, so the rule
fires.

Do not quote it. The payload carries `multiple_testing.intervals_reported: 217` with
`alpha_is_nominal: true`, and its own reading of what that means: *"one positive year among
many is what this count exists to make visible."* One row in 217 at nominal alpha is what
chance produces. The counter exists so that this specific temptation is answered before
anyone reaches for it.

The IDX year rows are mostly unreadable anyway. Thirteen of fifteen are too thin, the top band
is routinely five trades or fewer, and 2012, 2014 and 2015 have **no closed 4.0★ trades at
all**, so their gap is undefined rather than small.

## What this does and does not license

- **It is not shippable.** The denominator it reads comes from a run whose `in_field` anchor
  is still failing. #211 established that the sign flip is a property of the contracted gates
  rather than a defect, and explicitly did not waive the anchor. `backtest.full_run` still
  emits no figure, plot or payload.
- **#196's bound is the harder obstacle, and this run walks into it.** The survivorship twin
  goes negative for any headline below **+0.605R**. The US gap here is +0.461R and the IDX gap
  is −0.191R. Neither reaches it. So this is not a result waiting on more evidence; on its own
  numbers it does not clear the bar the plan set.
- **It does not fire or clear the kill criterion**, and says so in the payload. That criterion
  is the pre-registered metric's. What this measurement decides, *if* the criterion fires, is
  whether the app's claim reduces to ranking what a human selects rather than selecting on its
  own.
- **It is not comparable to findings §4a.** §4a is carried in the payload as
  `in_sample_reference` — picks 14.42% against the field's 8.83% at ≥3.5★, +5.59pp,
  p = 0.055 exact binomial — with the reason it cannot be lined up beside the gap above.
  Rubric v2's weights were fitted to the selection contrast on that same field, so §4a asked
  whether they reproduced a separation they had been fitted to. That is a fit statistic. It is
  also a different *shape*: a rate of scores between two populations, against a mean outcome
  between score bands of one.
- **It does not answer #211 and #211 does not answer it.** Selection and outcome are different
  questions over the same store.

## Reproducing this page

```
python -m backtest.ranking --store data/backtest.duckdb \
    --out-json references/backtest_score_ranking.json
```

Both markets, arm B — the pre-registered arm — over the contract's own scope. Roughly ninety
seconds: it reads the persisted denominator beside the store rather than re-simulating, and it
writes neither. The run is deterministic, and re-running it reproduces
[`backtest_score_ranking.json`](backtest_score_ranking.json) **byte for byte**; the two runs
made for this page hash identically.

Everything the tables above report is in that payload, along with the per-year rows and the
band edges. What governs how to read it:

- `verdict_rule` — the two-statistic rule, quoted from `ranking.VERDICT_RULE`
- `multiple_testing` — the 217 nominal-alpha intervals, and what a lone positive year is worth
- `in_sample_reference` — §4a, and why it is not this measurement
- `bootstrap` — 2,000 resamples clustered by symbol, seed 191, 95% confidence
- `score` — the seven-dimension replayed score, 8 points and a 4.0★ ceiling, one dimension
  short of the nine the product prints because the replay strikes `Sector`
- `year_attributed_to` — `entry_session`
- `contract` — version 1, *out-of-sample backtest — US+IDX, 2012 onward (PRD #182)*

One note on reading the printed table: a band's symbol count covers every trade **taken** in
that band while `n` counts only those **closed**, and the bootstrap clusters over closed
trades alone. In the live year those three numbers differ — a band can print `n=5`, six
symbols and four bootstrap clusters. It is an unfinished year, not an inconsistency.
