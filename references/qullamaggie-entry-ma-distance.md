# How far above the MA does he actually enter — and what "extended" means

**Study:** the entry-to-moving-average distance of Kristjan Kullamägi's executed-trade
record — against the 10-, 20- and 50-day — and whether that distance predicts the outcome.
**Scope:** US, 2019-10 to 2022-11. All long, all breakout. No IDX.
**Status of the app:** unchanged. This study produces evidence only. No constant in
`detection.py`, `score.py`, `universe.py` or `ranks.py` is touched by it, and none is
touched by this write-up. The threshold proposed in §6 is a **proposal with provenance**,
not an applied change.

**Headline:** the 10-day and the 50-day point in opposite directions. Far above the 10-day
is a warning; far above the 50-day is a *recommendation*. §5 is the useful part.

**Reproduce:** `python scripts/entry_ma_distance.py --fetch`
(per-trade output: `references/qullamaggie-entry-ma-distance.csv`)

---

## 1. The question and why it has an answer

[`qullamaggie-method.md`](qullamaggie-method.md) §5 makes a qualitative claim and stakes a
lot on it:

> Correct trendline geometry produces entries hugging the rising 10/20/50-day (affordable
> stop); the swing-high break happens after price has left the MA behind (stop too wide →
> §7 kills the trade). **If you find yourself entering far from a moving average, you drew
> the line wrong.**

"Far" is doing all the work in that sentence and the document never quantifies it. His
published trade log does, because every row carries a real entry price and date. So the
distance is measurable, and — since the log also carries a simulated exit — so is whether
the distance mattered.

## 2. Method

828 logged breakout longs joined to daily bars: US bars already in the screener store
(`data/screener.duckdb`) for 231 of 312 tickers, Yahoo backfill for the delisted
remainder. **579 of 828 trades matched (70%).** The local store did nearly all the work:
568 of the 579 matched trades came from `screener.duckdb`, the Yahoo backfill added 11.

**Prior-close MAs.** SMA10 and SMA20 are computed through the session *strictly before*
the entry date. He enters intraday and early — median logged entry time **09:42**, with
79% of entries before 10:00 — so the entry-day SMA is not knowable at the click, and the
prior close is the value actually on screen.

**Distance in ADR units.** Reported both as a percentage of the MA and as a multiple of
ADR (`ADR% = SMA20(High/Low − 1)`, the definition `screener/indicators.py` uses, over the
20 bars before entry). The ADR-relative number is the one that transfers across names: 7%
above the 10-day is unremarkable for a 15%-ADR biotech and preposterous for a 3%-ADR
mega-cap. §7 denominates the stop cap in ADR for exactly this reason.

**Split frames.** Logged prices are as-traded; bar series are split-adjusted to today, so a
name that split after the entry lands in a different price frame and `entry / SMA` would be
off by the ratio. For each trade the script recovers the ratio that puts the entry back
inside its own day's range — applied to 120 of the 579 matched trades — and **drops the
trade unless exactly one candidate ratio fits.** Uniqueness is not pedantry here: GME on
2021-02-24 ranged 44.70–91.71, and both 3:1 and 4:1 place the logged 46.50 fill inside it.
Nearest-fit picks 3; GME split 4:1. On a day whose high is 2× its low, adjacent ratios are
simply not discriminable, and a wrong one manufactures a plausible-looking distance out of
nothing — so those trades are dropped instead.

### What the 249 unmatched trades cost us

| reason | n | bias it introduces |
|---|---|---|
| no bar data (delisted, ticker reused) | 153 | Skews *against* blown-up small caps — the 2020–21 SPAC/meme cohort. Those had the widest ADRs, so the true distribution is likely a touch wider than measured. |
| split ratio absent or ambiguous | 79 | Heavily-split names and very wide-range days. Wide-range days correlate with high ADR, so this thins the high-ADR tail slightly. |
| < 25 bars of history | 16 | Recent IPOs — structurally the *closest* entries (no extended MA to be far from). Small, and biases measured distance slightly **up**. |
| implausible (data fault) | 1 | NVDA 2020-09-27; compounding splits past the candidate list. |

70% coverage is enough for the distributional claim in §3. It is thinner than ideal for the
tail buckets in the outcome analysis, and the caveats section says so plainly.

### The pipeline checks out against an independent study

The replay study ([`qullamaggie-replay-findings.md`](qullamaggie-replay-findings.md) §6)
measured his stop width over the same trade record, but by a different route: a different
matched subset (n=649), bars read through the replay chain, and ADR taken from the night's
field rather than recomputed here. Running the same statistic over this study's 579 rows
reproduces it to three decimals:

| | replay study | this pipeline |
|---|---|---|
| median stop width | 0.345 ADR | **0.346 ADR** |
| p25 / p75 | 0.238 / 0.490 | **0.241 / 0.488** |
| share ≤ 1.0 ADR | 98.15% | **97.93%** |

Two independent paths agreeing to that tolerance is the best available evidence that the
split-frame recovery and the ADR computation above are not quietly wrong.

## 3. Result: he enters close, and the tail is short

Distance above the MA at entry, prior-close basis, n = 579:

| | mean | **median** | p5 | p25 | p75 | p95 |
|---|---|---|---|---|---|---|
| above SMA10, % | 5.55 | **4.09** | −0.48 | 2.26 | 7.05 | 16.40 |
| above SMA20, % | 8.28 | **5.37** | −1.97 | 2.49 | 10.00 | 30.39 |
| above SMA50, % | 16.85 | **11.74** | −8.12 | 4.29 | 21.88 | 63.35 |
| above SMA10, ×ADR | 0.86 | **0.71** | −0.06 | 0.38 | 1.09 | 2.21 |
| above SMA20, ×ADR | 1.16 | **0.93** | −0.33 | 0.46 | 1.71 | 3.34 |
| above SMA50, ×ADR | 2.28 | **2.11** | −1.07 | 0.87 | 3.46 | 6.12 |

SMA50 rows are over the 577 of 579 trades with the 50 bars it needs.

Context from the same rows: median ADR at entry **5.90%**, median stop he actually set
**2.19%** — comfortably inside §7's 1 × ADR cap, and roughly *a third* of it.

- **70.1%** of entries sit within 1 × ADR of the SMA10; **92.4%** within 2 ×.
- 52.2% within 1 × ADR of the SMA20; 81.7% within 2 ×.
- Only **21.5%** are within 1 × ADR of the SMA50, and 44.4% within 2 ×. He is not hugging
  the 50-day in any meaningful sense — the median entry is 2.11 × ADR above it.
- He enters *below* the SMA10 on **7.1%** of trades (below SMA20: 9.7%, below SMA50:
  12.0%) — pullback entries into the MA, not breakouts away from it.
- Stable year to year: median distance above SMA10 is 3.55 / 4.17 / 4.09 / 4.28 % for
  2019 / 2020 / 2021 / 2022, while ADR itself swings 4.64 → 6.35%.

**§5's description survives contact with the data.** The modal entry is about 0.7 × ADR
above the 10-day; "hugging the rising 10/20-day" is a fair account of what he does. Its
stated *explanation* does not survive — see the outcome analysis below.

## 4. Does the distance predict the outcome?

Realised R uses the file's primary `10sma` trailing exit (`rr10sma`); 578 of the 579
matched rows carry one. His hit rate is ~23%, so **the median trade is a −1R stop-out in
every bucket** and the median tells us nothing; mean R and the share of ≥ 3R trades are
what separate them.

**By distance above the SMA10, in ADR units:**

| bucket (×ADR) | n | mean R | win % | ≥3R % |
|---|---|---|---|---|
| below the MA (≤ 0) | 41 | −0.20 | 14.6 | 7.3 |
| 0 – 0.5 | 165 | **+1.39** | 22.4 | 16.4 |
| 0.5 – 1.0 | 202 | **+1.11** | 23.8 | 16.3 |
| 1.0 – 1.5 | 89 | +0.80 | 27.0 | 12.4 |
| 1.5 – 2.0 | 38 | +0.43 | 21.1 | 7.9 |
| 2.0 – 3.0 | 28 | −0.32 | 7.1 | 7.1 |
| > 3.0 | 15 | **−1.00** | 0.0 | 0.0 |

**Splitting the whole book at each cutoff:**

| cutoff | at-or-below: n / mean R / win% | beyond: n / mean R / win% / ≥3R% |
|---|---|---|
| 1.0 × ADR | 408 / +1.09 / 22.3% | 170 / +0.37 / 20.0% / 9.4% |
| **1.5 × ADR** | 497 / +1.04 / 23.1% | **81 / −0.09 / 12.3% / 6.2%** |
| 2.0 × ADR | 535 / +1.00 / 23.0% | 43 / −0.56 / 4.7% / 4.7% |
| 2.5 × ADR | 554 / +0.96 / 22.6% | **24 / −0.99 / 0.0% / 0.0%** |
| 3.0 × ADR | 563 / +0.93 / 22.2% | 15 / −1.00 / 0.0% / 0.0% |

Three things are visible and they are not the same thing:

1. **Expectancy crosses zero between 1.5 and 2.0 × ADR above the SMA10.** Below the line
   the book returns ~+1.0R per trade; above it, nothing.
2. **The ≥3R rate — the thing that actually pays for the strategy — decays first.** It is
   ~16–17% inside 1 × ADR, halves by 1.5–2.0 ×, and reaches zero past 2.5 ×. You lose the
   big winners *before* you lose the win rate.
3. **Beyond 2.5 × ADR, not one of 24 trades worked.** Past 3 ×, all 15 were full stop-outs.

The SMA20 view tells the same story with a looser threshold (the 20-day is naturally
further from price): mean R stays positive through 3 × ADR and collapses to −0.97 beyond,
with a 0% big-win rate.

### The mechanism is *not* the one §5 predicts

§5's stated reason for staying near the MA is stop survivability: enter far away and the
stop is too wide or too easily hit. The data does not support that as the mechanism here.
Median MAE is essentially **flat** across the buckets — −2.4%, −2.6%, −2.5%, −2.0%, −2.5%
walking outward — and only deepens in the last bucket (−2.9% past 3 ×). The stop width he
actually set is likewise near-constant (~2.0–2.3% until the far tail). Extended entries are
**not** getting shaken out more often at moderate distance: the win rate holds at 21–27%
right through 2 × ADR.

What collapses is the **upside**. The ≥3R share falls from ~16% to 8% between 1 × and 2 ×
ADR while the win rate is unchanged. The trades still work about as often; they just stop
*paying*. That points at a different mechanism than §5's: buying 2 × ADR above the 10-day
means buying late into a thrust that is already largely spent, so what remains is a normal
win rate on truncated moves — and a breakout book with a 23% hit rate cannot survive on
truncated moves. It needs the tail.

This matters for how a rule gets built. If the problem were stop survivability, a
wider-stop or smaller-size adjustment could rescue an extended entry. If the problem is a
spent move, nothing about position management rescues it, and the only correct action is
to not take the trade.

### The one result that complicates the picture

Entries *below* the SMA10 do badly (mean −0.20R, 14.6% win) — worse than entries just
above it. Being close to the MA is not the objective; being close *on the correct side*
is. Below the 10-day means the breakout has already failed or has not happened yet, and
the trade is a different setup wearing a breakout's clothes. Any "extended" rule must be
**one-sided**: it disqualifies far-above, and says nothing about below, which is a
separate problem.

## 5. The 50-day measures something else entirely — and its sign is reversed

§5 of the method doc names "the rising 10/20/50-day" in one breath, as if the three were
interchangeable supports. They are not, and the difference is the most useful thing in
this study.

**Distance from the 50-day carries no warning at all.** Bucketed exactly as before:

| bucket (×ADR above SMA50) | n | mean R | win % | ≥3R % |
|---|---|---|---|---|
| below the MA (≤ 0) | 69 | +0.88 | 23.2 | 8.7 |
| 0 – 0.5 | 47 | +0.68 | 21.3 | 10.6 |
| 0.5 – 1.0 | 38 | +0.31 | 18.4 | 15.8 |
| 1.0 – 1.5 | 53 | +0.88 | 17.0 | 15.1 |
| 1.5 – 2.0 | 67 | +0.10 | 16.4 | 9.0 |
| 2.0 – 3.0 | 112 | +0.99 | 21.4 | 17.0 |
| **> 3.0** | **190** | **+1.27** | **25.3** | **15.3** |

The best bucket is the *farthest* one, and it is also the largest — a third of his book
sits more than 3 × ADR above the 50-day. Spearman against R is **+0.048** for the 50-day
versus **−0.052** for the 10-day: weak both times, but **opposite in sign**. Whatever
"extended" means, it cannot be defined on the 50-day, and a rule that rejected candidates
for being far above it would reject his best trades.

That makes sense once stated plainly. Distance from the 10-day measures *how late in the
current thrust you are buying*. Distance from the 50-day measures *how strong the trend
has been* — and strong prior trend is the setup, not a defect. It is closer to a momentum
score than to a risk gauge. The two distances are only loosely coupled (Pearson 0.489,
against 0.793 between the 10- and 20-day), so the 50 genuinely carries independent
information rather than restating the 10.

### The combination is what separates the book

Splitting on both at once — "established trend" as ≥ 2 × ADR above the SMA50, "not
extended" as ≤ 1.5 × ADR above the SMA10:

| above SMA50 | vs SMA10 | n | mean R | win % | ≥3R % |
|---|---|---|---|---|---|
| **≥ 2 × ADR** | **≤ 1.5 × ADR (tight)** | **247** | **+1.57** | **27.1** | **18.6** |
| ≥ 2 × ADR | extended | 55 | **−0.65** | 9.1 | 3.6 |
| < 2 × ADR | tight | 248 | +0.52 | 19.4 | 11.3 |
| < 2 × ADR | extended | 26 | +1.08 | 19.2 | 11.5 |

The signature trade — **far above the 50-day, still tight to the 10-day** — is 43% of the
book and returns +1.57R at a 27% hit rate with an 18.6% big-win rate, the best cell by
every measure. Its mirror image, far above the 50-day *and* extended from the 10-day, is
the worst cell in the study at −0.65R and a 9% hit rate. Same trend strength; the only
difference is whether you bought the pullback or chased the thrust.

Within the non-extended book alone, mean R still climbs with distance from the 50-day
(+1.10 / 0.00 / +0.57 / +1.27 / **+1.76** across ≤0, 0–1, 1–2, 2–3, >3 × ADR, n = 495), so
the 50-day is adding signal on top of the 10-day rather than echoing it.

**Practical reading: the 50-day belongs on the "is this a real trend?" side of the
screen, and only the 10-day belongs on the "is this entry too late?" side.** The bottom-
right cell is small (n = 26) and should not be over-read, but the two large cells carry
the conclusion.

## 6. So: what does "extended" mean?

Grounded in the outcome analysis above, and stated in the ADR units the method already uses:

> **Extended (proposed): an entry more than 1.5 × ADR above the prior-close SMA10.**
> Beyond that line the book's expectancy is zero (mean −0.09R over 81 trades) and the
> ≥3R rate has already halved. **Past 2.5 × ADR, treat it as no-trade** — 0 winners in 24.

In the more familiar units, at the median 5.9% ADR, 1.5 × ADR ≈ **9% above the 10-day**,
and the hard line ≈ 15%. That is reassuringly close to §6's independent rule of thumb from
the stream ("missed both the 1-min and 5-min ORH and it's already ~14%+ past the trigger:
it's gone"), which was derived from a completely different observation and lands in the
same place.

Why *this* line rather than the obvious alternatives:

- **Not the p95 (2.21 × ADR).** A percentile describes his habits; it does not describe
  where trades stop working. The two disagree, and the outcome data should win.
- **Not 1.0 × ADR**, even though it is the tidy match to §7's stop cap. The 1.0–1.5 bucket
  still returns +0.80R over 89 trades. Cutting there discards a profitable slice to buy a
  rule that is only cosmetically consistent.
- **Two lines, not one**, because the data has two features: a soft zone where the edge
  thins (1.5–2.5 ×, worth a warning) and a hard zone where it is absent (> 2.5 ×, worth a
  refusal). Collapsing them into one number throws away the distinction.

**Relation to §7 — it is a genuinely separate filter, and the method doc is wrong to
conflate them.** §5 argues the MA-distance rule and the 1 × ADR stop cap "are the same
rule". In this record they are not even correlated. Stop width, expressed in ADR, is
0.28 / 0.32 / 0.36 / 0.42 / 0.45 / 0.37 / 0.59 × across the seven distance buckets, and the
Spearman correlation between MA distance and stop width is **−0.002**. The share of trades
whose stop actually breaches the 1 × ADR cap stays under 5% until past 3 × ADR. Because he
stops at the low of the *entry day*, the stop is set by that day's range, not by how far
price has travelled from the 10-day.

So an extended-entry check is **not** a restatement of §7 measured earlier, as §5 claims —
it catches trades §7 lets through. Both are needed, and they fail for different reasons:
§7 rejects trades you cannot size; this rejects trades whose move is already spent.

## 7. Caveats, which bound the above

- **Survivor-conditioned sample, and this is the big one.** These are trades he *took*.
  The book contains no counterfactual for the extended setups he passed on, so this
  measures "when he broke his own rule, what happened" — not "what is the optimal
  threshold over all setups". It can justify a rule against extended entries; it cannot
  claim the rule is optimally placed.
- **Small n in exactly the buckets that carry the conclusion.** The decisive cells are
  n = 24 and n = 15. Mean R does fall monotonically across all six above-MA buckets
  (+1.39 → +1.11 → +0.80 → +0.43 → −0.32 → −1.00), which is stronger evidence than any
  single cell, but a 1.5 × line placed to two decimals would be false precision. Treat it
  as "about 1.5", and the hard line as "about 2.5".
- **Rank correlation is weak** (Spearman −0.05 for SMA10, −0.11 for SMA20 against R).
  Distance is **not** a good continuous predictor and must not be used to rank or score
  candidates. It identifies a dead zone; it does not sort the live one. A monotone
  penalty term in `score.py` would be reading more into this than it supports.
- **The exits are counterfactual.** R is computed on the file's simulated 10-day-SMA
  trailing rule, not his actual exits (§1 of the replay findings makes the same point).
  A different exit rule could move the thresholds, though the ≥3R collapse is about the
  entry and should be robust to it.
- **Regime.** 2020–21 dominates the sample (502 of 579). Whether a 1.5 × line holds in a
  low-ADR, low-dispersion tape is untested here.
- **Missing cohort.** The 153 unmatched delisted tickers were disproportionately the
  widest-ADR names of the 2020–21 cohort; see the method section.
- **The 50-day's positive slope is confounded with the era.** 2020–21 was a market in
  which being far above the 50-day was rewarded almost everywhere. §5's finding that
  distance-from-50 does not predict failure is safe (it is a *null* result, and a null
  survives a favourable regime). The stronger reading — that distance-from-50 is actively
  *good* — is not: that is exactly the claim a momentum regime would manufacture. Do not
  build a positive scoring term on it without an out-of-sample check.
- **The 2×2 is descriptive, not causal.** The cells are not randomised; the tight-to-10
  and far-from-50 cell may differ from its neighbours in ways not measured here (sector,
  float, catalyst). The bottom-right cell is n = 26 and should carry no weight at all.

## 8. What this does not authorise

No constant changes on the strength of this document. If an extended-entry check is later
built, this file is its provenance — and the honest form of the check, given §7, is a
**displayed warning at 1.5 × ADR above the SMA10 and a hard gate at 2.5 ×**, not a scoring
term.

The 50-day authorises **nothing** on its own. Its one firm, usable conclusion is negative:
**do not treat distance above the 50-day as extension.** A screen that filtered candidates
for sitting too far above the 50-day would have rejected the largest and best-performing
third of his book.
