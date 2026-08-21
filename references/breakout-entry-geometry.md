# The geometry of a breakout trader's entries

**What this is.** An empirical description of *where*, geometrically, one successful
breakout trader placed his entries — measured against his own executed-trade record
rather than against any stated method. Two independent properties are measured: how
**quiet** the stock had been in the days before entry, and how **far from its moving
averages** he bought. Both are then set against realised outcome.

It is a standalone reference. Nothing here depends on any particular screening
implementation, and no figure is a recommendation.

---

## The record

**828 executed entries**, October 2019 – November 2022, 312 US stocks. All long, all
breakout setups, all end-of-day. Each row is a **real entry** — the date and price he
actually bought — paired with a **simulated exit** reconstructed by a trailing rule (exit
on a close below the 10-day SMA), because his actual exits were not recorded. The entry is
fact; the exit is a consistent counterfactual applied uniformly.

Two subsets are used, and they differ, so figures are not interchangeable between the two
halves of this document:

| | n | what it required |
|---|---|---|
| **Quietness measurements** | **649** | 20 bars of history before entry |
| **Moving-average measurements** | **579** | 50 bars, plus a stricter price-scale match |

The shortfall from 828 is almost entirely companies since delisted or renamed, whose price
history is no longer retrievable — see **Limits**.

## Two units

Everything is expressed in two normalised units so that a $4 stock and a $400 stock are
comparable.

**ADR — average daily range.** The mean of `high / low − 1` over the last 20 sessions,
times the latest close. One ADR is "a normal day's travel" for that stock. Median ADR at
his entries is **5.9%** of price, so 1 ADR ≈ a 5.9% move on the median name.

**R — realised return in units of initial risk.** Risking 1% of equity and making 2% is
`+2R`; a full stop-out is `−1R`.

**The evaluation point** is always the **session strictly before entry** — the last data
that existed while the trade was still ahead of him. Nothing is measured using the entry
day's own bar, so no figure here is contaminated by hindsight about the breakout itself.

> **A statistical property that governs how everything below must be read.** His hit rate
> is about **23%**. The median trade is a −1R stop-out **in every bucket of every table in
> this document**. The median is therefore uninformative by construction, and every result
> here uses **mean R** and the **share of ≥3R trades**. Reading these tables by their
> typical trade would show a loss everywhere and conclude that nothing works.

---

## Part A — How quiet the stock was before entry

For each entry, the trailing `k`-session range `(max high − min low) ÷ ADR` was computed
for every `k` from 3 to 7, at the evaluation point.

### The distribution

| Trailing window | p10 | p25 | **median** | p75 | p90 | max |
|---|---|---|---|---|---|---|
| **3 sessions** | 0.80 | 1.00 | **1.31** | 1.73 | 2.16 | 5.09 |
| 4 sessions | 0.94 | 1.20 | 1.55 | 2.05 | 2.48 | 7.65 |
| 5 sessions | 1.13 | 1.36 | 1.86 | 2.31 | 2.84 | 13.12 |
| 6 sessions | 1.29 | 1.61 | 2.06 | 2.55 | 3.24 | 17.03 |
| 7 sessions | 1.43 | 1.77 | 2.25 | 2.81 | 3.55 | 17.50 |

**The typical entry follows three sessions that together covered about 1.31 ADR** — barely
more than a single normal day's travel, compressed into three. That is a genuinely coiled
base.

But he is **not strict about it**: a quarter of his entries follow a 3-day stretch wider
than 1.73 ADR, and the tail runs past 5. Quietness describes a *tendency*, not a rule he
refuses to break.

> **A measurement note worth knowing before designing anything around this.** Trailing
> range is **monotone in `k`** — a longer window can only contain more high and more low,
> never less. So the minimum across any range of window lengths is *always* the shortest
> window. Verified across all 649 entries: the "tightest window in 3–7 sessions" and the
> "3-session range" are identical to the last decimal. Any scan across window lengths
> looking for the tightest one is computing the shortest window with extra steps.

### Quietness against outcome

| 3-session range (ADR) | n | **mean R** | win % |
|---|---|---|---|
| under 1.0 | 164 | **+2.02** | 23.2 |
| 1.0 – 1.5 | 254 | **+1.35** | 25.3 |
| 1.5 – 2.0 | 139 | **+0.84** | 18.0 |
| 2.0 – 3.0 | 82 | **+0.35** | 22.0 |
| over 3.0 | 10 | **−0.36** | 20.0 |

**Monotone, and smooth.** Entries out of the quietest bases returned nearly six times
those out of loose ones. Critically, **there is no discontinuity anywhere** — the decline
across 1.5 looks exactly like the decline across 1.0 or 2.0.

**So quietness is a matter of degree, not a threshold.** A base at 1.6 ADR performs about
like one at 1.4. Any rule that draws a hard line here is imposing a step function on
something the data says is a gradient, and will misclassify everything near the line.

---

## Part B — How far above the moving averages he bought

Distance from the prior close to each moving average, at the evaluation point, n = 579.

| | median (%) | **median (×ADR)** | p25 (×ADR) | p75 (×ADR) | p95 (×ADR) |
|---|---|---|---|---|---|
| above the 10-day SMA | 4.09 | **0.71** | 0.38 | 1.09 | 2.21 |
| above the 20-day SMA | 5.37 | **0.93** | 0.46 | 1.71 | 3.34 |
| above the 50-day SMA | 11.74 | **2.11** | 0.87 | 3.46 | 6.12 |

- **70.1%** of entries sit within 1 ADR of the 10-day; **92.4%** within 2.
- Only **21.5%** are within 1 ADR of the 50-day. The median entry is **2.11 ADR above it.**
- He buys *below* the 10-day on **7.1%** of trades — pullback entries, not breakouts away.
- **Stable year to year.** Median distance above the 10-day was 3.55 / 4.17 / 4.09 / 4.28 %
  across 2019 / 2020 / 2021 / 2022, while ADR itself swung from 4.64% to 6.35%. The habit
  holds even as volatility does not.

**"Close to the moving average" is only true of the 10-day.** Describing this style as
hugging the 10-, 20- and 50-day in one breath is wrong: he is not near the 50-day in any
meaningful sense, and Part C shows that distance from it is not a defect but the setup.

### Distance from the 10-day against outcome

| bucket (×ADR above 10-day) | n | mean R | win % | ≥3R % |
|---|---|---|---|---|
| below the MA (≤ 0) | 41 | **−0.20** | 14.6 | 7.3 |
| 0 – 0.5 | 165 | **+1.39** | 22.4 | 16.4 |
| 0.5 – 1.0 | 202 | **+1.11** | 23.8 | 16.3 |
| 1.0 – 1.5 | 89 | +0.80 | 27.0 | 12.4 |
| 1.5 – 2.0 | 38 | +0.43 | 21.1 | 7.9 |
| 2.0 – 3.0 | 28 | −0.32 | 7.1 | 7.1 |
| over 3.0 | 15 | **−1.00** | 0.0 | 0.0 |

Splitting the whole book at each cutoff:

| cutoff | at or below | beyond |
|---|---|---|
| 1.0 × ADR | 408 → +1.09R, 22.3% win | 170 → +0.37R, 20.0% win, 9.4% ≥3R |
| **1.5 × ADR** | 497 → +1.04R, 23.1% win | **81 → −0.09R, 12.3% win, 6.2% ≥3R** |
| 2.0 × ADR | 535 → +1.00R, 23.0% win | 43 → −0.56R, 4.7% win |
| **2.5 × ADR** | 554 → +0.96R, 22.6% win | **24 → −0.99R, 0.0% win, 0.0% ≥3R** |
| 3.0 × ADR | 563 → +0.93R, 22.2% win | 15 → −1.00R, 0.0% win |

Three distinct things happen, and they happen at different points:

1. **Expectancy crosses zero between 1.5 and 2.0 ADR** above the 10-day. Below that line
   the book returns about +1.0R per trade; above it, nothing.
2. **The big-win rate decays first.** The ≥3R share is ~16–17% inside 1 ADR, halves by
   1.5–2.0, and hits zero past 2.5. **You lose the tail before you lose the win rate.**
3. **Past 2.5 ADR, not one of 24 trades worked.** Past 3 ADR, all 15 were full stop-outs.

### Why buying extended hurts — not for the usual reason

The intuitive explanation is stop survivability: buy far from the average and your stop is
either too wide or too easily hit. **The data rejects that.**

Median adverse excursion is essentially **flat** walking outward — −2.4%, −2.6%, −2.5%,
−2.0%, −2.5% — deepening only past 3 ADR. The stop he actually set is near-constant at
~2.0–2.3% until the far tail. And the **win rate holds at 21–27% right through 2 ADR**.
Extended entries are not being shaken out more often at moderate distance.

**What collapses is the upside.** The ≥3R share halves between 1 and 2 ADR while the win
rate is unchanged. The trades still *work* about as often — they just stop *paying*.

The reading: buying well above the 10-day means buying **late into a thrust that is
already largely spent**, leaving a normal win rate on truncated moves. A book with a 23%
hit rate cannot survive on truncated moves; it needs the tail.

> **This distinction determines what a remedy could even look like.** If the problem were
> stop survivability, a wider stop or smaller size would rescue an extended entry. Because
> the problem is a spent move, **no amount of position management rescues it.** The only
> action that helps is not taking the trade.

### Below the average is a different problem

Entries *below* the 10-day are the second-worst bucket in the study: **−0.20R at a 14.6%
win rate** — worse than entries just above it. Proximity to the average is not the
objective; proximity **on the correct side** is. Below the 10-day means the breakout has
already failed or has not yet happened, and the trade is a different setup wearing a
breakout's clothes.

Any "too extended" criterion must therefore be **one-sided**: it should disqualify
far-above and stay silent about below, which is its own separate failure.

### A working definition of "extended"

> **Extended: more than 1.5 × ADR above the prior-close 10-day SMA.** Beyond that line
> expectancy is zero (−0.09R across 81 trades) and the big-win rate has already halved.
> **Past 2.5 × ADR, treat it as untradeable** — 0 winners in 24.

At the median 5.9% ADR that is roughly **9% above the 10-day**, with the hard line near
**15%**. Notably, that lands close to a rule of thumb the trader had stated himself from
entirely different reasoning — that once price is ~14% past the trigger, the move is gone.

**Two lines rather than one**, because the data has two features: a zone where the edge
thins (worth a warning) and a zone where it is absent (worth a refusal). Collapsing them
into a single number discards the distinction.

**Not the 95th percentile (2.21 ADR)**, even though that is the obvious "describe his
habits" answer. A percentile says where he *usually* is; it does not say where trades stop
working. Here the two disagree, and **the outcome data should win**.

---

## Part C — The 50-day measures something else, and its sign is reversed

| bucket (×ADR above 50-day) | n | mean R | win % | ≥3R % |
|---|---|---|---|---|
| below the MA (≤ 0) | 69 | +0.88 | 23.2 | 8.7 |
| 0 – 0.5 | 47 | +0.68 | 21.3 | 10.6 |
| 0.5 – 1.0 | 38 | +0.31 | 18.4 | 15.8 |
| 1.0 – 1.5 | 53 | +0.88 | 17.0 | 15.1 |
| 1.5 – 2.0 | 67 | +0.10 | 16.4 | 9.0 |
| 2.0 – 3.0 | 112 | +0.99 | 21.4 | 17.0 |
| **over 3.0** | **190** | **+1.27** | **25.3** | **15.3** |

**The best bucket is the farthest one — and it is also the largest.** A third of his book
sits more than 3 ADR above the 50-day. Rank correlation with R is **+0.048** for the
50-day against **−0.052** for the 10-day: weak both times, but **opposite in sign**.

So "extended" cannot be defined on the 50-day, and a filter rejecting candidates for
sitting far above it **would reject his best trades.**

This makes sense once stated plainly. **Distance from the 10-day measures how late in the
current thrust you are buying. Distance from the 50-day measures how strong the trend has
been** — and a strong prior trend is the setup, not a defect. The two are only loosely
coupled (Pearson 0.489, against 0.793 between the 10- and 20-day), so the 50-day carries
genuinely independent information.

### The combination is what separates the book

Splitting on both at once — "established trend" as ≥2 ADR above the 50-day, "not extended"
as ≤1.5 ADR above the 10-day:

| above 50-day | vs 10-day | n | **mean R** | win % | ≥3R % |
|---|---|---|---|---|---|
| **≥ 2 × ADR** | **≤ 1.5 × ADR** | **247** | **+1.57** | **27.1** | **18.6** |
| ≥ 2 × ADR | extended | 55 | **−0.65** | 9.1 | 3.6 |
| < 2 × ADR | ≤ 1.5 × ADR | 248 | +0.52 | 19.4 | 11.3 |
| < 2 × ADR | extended | 26 | +1.08 | 19.2 | 11.5 |

**The signature trade — far above the 50-day, still close to the 10-day — is 43% of the
book and the best cell by every measure**: +1.57R at a 27% hit rate with an 18.6% big-win
rate. Its mirror image, far above the 50-day *and* extended from the 10-day, is the worst
cell in the study at −0.65R and a 9% hit rate.

**Same trend strength. The only difference is whether he bought the pause or chased the
thrust.**

Within the non-extended book alone, mean R still climbs with distance from the 50-day
(+1.10 / 0.00 / +0.57 / +1.27 / **+1.76** across ≤0, 0–1, 1–2, 2–3, >3 ADR, n = 495), so
the 50-day adds signal on top of the 10-day rather than echoing it.

> **Practical reading: the 50-day belongs on the "is this a real trend?" question, and only
> the 10-day belongs on the "is this entry too late?" question.** The bottom-right cell is
> small (n = 26) and should not be over-read; the two large cells carry the conclusion.

---

## Part D — Where the stop actually sits

| measured on the same sessions | p25 | **median** | p75 | max |
|---|---|---|---|---|
| The base — 3-session range | 1.00 | **1.310 ADR** | 1.73 | 5.09 |
| **His stop distance** | 0.238 | **0.345 ADR** | 0.490 | 2.753 |

**A 3.8× gap.** **98.15%** of his stops sit within 1 ADR; the median is about **2.2–2.3% of
price**.

He does **not** stop below the consolidation he bought out of. Two independent lines of
evidence say the stop is set by the **entry day's own range**:

- Its width is uncorrelated with distance from the moving average (rank correlation
  **−0.002**) and near-constant at ~2.0–2.3% across every distance bucket until the far
  tail.
- It is roughly a quarter of the base's width, sitting well *inside* it rather than
  beneath it.

**So "tight" names two different quantities that differ by nearly 4×** — how quiet the
stock has been, and how much he is willing to lose. Conflating them, by placing a stop
below the base instead of below the entry day, would nearly **quadruple risk per trade**.

These are separate, independently-tunable properties and deserve separate names.

---

## What generalises: two dimensions, two shapes

The most useful cross-cutting result is that these two geometric properties, both
plausible-sounding filters, behave **completely differently** against outcome:

| | Shape against outcome | What honestly encodes it |
|---|---|---|
| **Distance from the 10-day** | A **cliff** — expectancy → 0 past 1.5 ADR, big-win rate → 0 past 2.5 | A threshold (plus a hard refusal line) |
| **Pre-entry quietness** | A **smooth monotone slope**, no feature anywhere | A graded score |

**Measure the shape before choosing the encoding.** A threshold imposed on a gradient
misclassifies everything near the line; a gradient applied where a genuine cliff exists
fails to refuse trades that never work.

## Transferable method notes

Four things that cost real effort to get right here, and would cost it again elsewhere:

1. **Use the mean, not the median, on a fat-tailed book.** At a 23% hit rate the median
   trade is a stop-out in every bucket. Medians here are not conservative — they are blind.
2. **Percentiles describe habits; outcomes describe edges.** Where they disagree, the
   outcome data should set the line. His 95th percentile of MA distance (2.21 ADR) sits
   well past where expectancy actually died (1.5 ADR).
3. **Normalise by volatility, or cross-sectional comparison is meaningless.** Every figure
   here is in ADR units. A 5% move is nothing on one stock and enormous on another.
4. **Compare ratios, not price differences, when prices come from two sources.** Trade
   records typically store raw prices while historical bars are split-adjusted. Any stock
   that split after the trade puts the two on different scales — computing a stop width as
   `(entry − stop) ÷ ADR` produced a median of 0.36 and a maximum of **30.94 ADR**, which
   is nonsense. Expressing both sides as ratios (stop as a fraction of entry, ADR as a
   fraction of close) makes splits cancel and needs no exclusions. The correct figure is
   0.345.

---

## Limits

- **Survivor-conditioned, and this is the big one.** Every number describes trades he
  **took**. There is no record of setups he examined and passed over, so there is **no
  control group and no false-positive rate**. This measures "when he did X, what
  happened" — never "X is optimal". A filter that looks good here could still reject
  enormous numbers of good trades; that cost is unmeasurable from this data.
- **Extended entries are him breaking his own guideline.** The extended buckets describe
  what happened when he violated a rule he mostly followed, on a self-selected set of
  occasions. That is not the same population as "all extended setups".
- **Missing data is not random.** Roughly a fifth to a quarter of the record is
  unrecoverable — companies delisted, acquired or renamed since. Those skew toward names
  that later collapsed, which is exactly the population a momentum screen surfaces. A
  further trap: ticker symbols get **recycled onto unrelated companies**, so a symbol that
  resolves today may return a different company's history for the same date. Those must be
  excluded by checking that history actually covers the trade's date, not merely that the
  symbol exists.
- **One regime.** US, 2019–2022, with **86.6% of entries from 2020–21** — a
  once-in-a-decade momentum market. The 50-day result is the most regime-exposed finding
  here: a tape that rewarded distance-from-the-50-day almost everywhere will make that
  dimension look better than it is.
- **Exits are simulated, not his.** Realised R comes from a mechanical 10-day-SMA trailing
  rule. His actual exits were discretionary and are unrecorded, so R measures *the setup
  under a fixed exit*, not his trade management.
- **The two halves use different subsets** (649 and 579) and slightly different ADR bases.
  Figures are consistent within each half; do not compute across them.
