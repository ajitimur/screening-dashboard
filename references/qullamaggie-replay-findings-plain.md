# Testing the app against Qullamägi's real trades — findings, in plain language

*This is a plain-language retelling of [`qullamaggie-replay-findings.md`](qullamaggie-replay-findings.md).
Same study, same numbers, same conclusions — just without assuming you already
speak the project's vocabulary. Where the two ever disagree, **the technical
version is the authority**, because that's the one whose figures are checked
against the committed run output.*

**Nothing in the app was changed by this study.** It produces evidence only. The
point is that if a setting is ever changed later, there's a written record of
*why*, with the measurement that justified it and the limitations that go with it.

---

## The vocabulary, up front

Five terms carry most of the document:

- **ADR — the stock's average daily swing.** How far a stock typically travels
  from its low to its high in one day, averaged over the last 20 days. Used as a
  measuring stick so a wild stock and a sleepy one can be compared fairly.
- **R — profit compared to what was risked.** Risking $100 and making $200 is
  "+2R". Losing the planned amount is "−1R".
- **MFE — how far a trade went in your favour at its best moment**, whether or
  not you kept it. Used to ask "did this setup actually run?" separately from
  "did the exit rule capture it?"
- **The field** — every stock the app would have shown on a given evening.
- **The funnel** — the three checks a stock must pass to appear at all:
  *is it liquid enough*, *is it among the strongest performers*, and *does it
  look like a valid setup*.

Two more that come up constantly:

- **Recall** — of the trades he really made, what fraction would the app have
  shown him? High recall means it isn't missing his trades.
- **Precision** — of the stocks the app shows, what fraction are actually any
  good? **This study cannot measure precision at all**, and that limitation
  shapes almost every decision in it. See "the one-sided ruler" below.

---

## What was tested, and against what

**The trade record:** 828 real trades by Kristjan Kullamägi, from October 2019 to
November 2022, across 312 stocks. All US, all long, all breakout setups, all
end-of-day.

Each trade has a **real entry** — the date and price he actually bought — paired
with a **simulated exit**, because his actual exits aren't recorded. The exit is
reconstructed by a trailing rule (sell when price closes below its 10-day
average). The study never blurs these two: the entry is fact, the exit is a
reasonable guess.

**The timing rule that makes this a fair test.** Every check is run against the
**evening before he bought** — never the day of. So the question is always
"*would the app have pointed at this stock while the trade was still ahead of
him?*", not "can the app recognise a winner after the fact". That distinction is
the whole value of the exercise.

**Repeat entries are kept, not hidden.** When he adds to a position he already
holds (another entry in the same stock within 5 trading days), that trade is
*labelled* as a repeat but stays in every total. Every recall number is reported
twice — once for all trades, once excluding repeats — and never with the repeats
quietly removed to flatter the result.

**One scoring category had to be dropped.** The app scores setups on eight
qualities; one of them is the stock's business sector. Historical sector labels
weren't kept, so a stock's 2020 sector can't be recovered. That category is
**dropped rather than guessed**, which means every score in this study is out of
9 points instead of 10 — always labelled as such so it's never mistaken for the
app's own score.

**The app is tested as-is.** The study calls the app's real functions rather than
reimplementing them, so what's measured is the app that exists.

---

## The biggest limitation, stated before any result

**About 29% of the stocks are simply missing, and not at random.**

The price history is built from today's list of traded companies. Any company
that was delisted, acquired or renamed since then has no history left to fetch.
Those vanished companies are disproportionately the ones that *later blew up* —
which is exactly the population a momentum screener surfaces. So the missing data
is missing in the least convenient possible way.

| | |
|---|---|
| Total trades in the record | 828 |
| Stocks affected by the hole | **91** |
| Trades lost to it | **170** |
| Share of his total profit in those lost trades | **18.1%** |

**The hole is bigger than first thought, for an interesting reason.** The first
count asked "does this ticker symbol exist today?" But the study needs a stricter
question: "does this symbol have price history *during the years we're
replaying*?" Ten symbols pass the first test and fail the second — APXT, BNKU,
EYES, FNGU, LAC, LAZR, NRGU, SI, SPWR, USLV. Each is a case of a **ticker symbol
being recycled onto a completely unrelated company**. Counting them as usable
wouldn't just overstate coverage — it would test one company's trade against a
different company's price history. So survivorship here means delisting *plus*
symbol recycling, and the recycled ones are dangerous precisely because they look
fine.

**This hole is now permanent.** Buying the missing history was investigated and
closed: every provider that carries it charges money, retail plans start around
$100/month, and there's no budget. Free sources give company *identity* but never
historical *prices*. So this isn't a gap waiting on a ticket — it's a permanent
property of the study, and every field-based result below carries it.

---

## The one-sided ruler (why this study refuses to "improve" things)

**We can measure what the app misses. We cannot measure what it wrongly
includes.** The trade record lists only stocks he *bought*. It never records a
setup he looked at and rejected. So there's no way to compute a false-positive
rate.

This creates an obvious trap: you could raise recall to 100% simply by loosening
every filter until the app shows everything. The numbers would look like a
triumph, and the app would be useless.

So the study adopts a strict rule, and enforces it throughout:

> **A filter may only be loosened when the evidence shows that quality genuinely
> doesn't matter *and* that there was enough variety in the data to have detected
> it if it did.**

That second half matters more than it sounds. Every trade in the sample already
passed his judgement, so the qualities he applies *most* consistently barely vary
— and anything that barely varies will correlate with nothing. **A flat result on
such a quality is evidence of his discipline, not of the quality's
irrelevance.** Confusing those two would systematically dismantle the parts of
the method that work best.

---

## Test 1 — Which filter throws away his trades?

**658 of the 828 trades could be replayed** (the other 170 are the coverage
hole). 80 of those are repeat entries.

Each of the three filters was tested *independently* on every trade, so no single
blended number can hide a disaster at one stage:

| Filter | Would have kept | Excluding repeat entries |
|---|---|---|
| Liquid enough? | **598/658 (90.9%)** | 523/578 (90.5%) |
| Strong enough performer? | **395/658 (60.0%)** | 340/578 (58.8%) |
| Valid-looking setup? | **380/658 (57.8%)** | 341/578 (59.0%) |

**The "strongest performers" filter is the expensive one.** It discards **40% of
his real trades on its own**, before the setup detector even looks — nearly five
times what the liquidity check costs.

**One oddity worth noting:** the setup detector is the only stage that scores
*better* once repeat entries are removed (59.0% vs 57.8%). His add-on buys are
harder for it to see than his first entries — which makes sense, since an add-on
isn't a fresh setup and the detector was never designed to catch one.

### Why the 40% figure shouldn't be acted on directly

Broken into three groups, that loss is not one problem:

| What the 263 misses actually are | Count | Share |
|---|---|---|
| The stock was missing from our data entirely | **64** | 24.3% |
| Would be recovered by widening the filter modestly | **75** | 28.5% |
| Genuinely not among the strongest performers by any measure | **124** | 47.1% |

So a quarter of the "miss" is the coverage hole wearing a disguise, and nearly
half were nowhere near qualifying. **The filter's real width problem is 75 trades,
not 263** — and even that can't be acted on, because widening it would admit
unknown amounts of junk that we have no way to count.

### Which part of "valid setup" does the rejecting

| Reason a setup was rejected | Count | Share of 278 |
|---|---|---|
| **Not quiet enough beforehand** ("cluster") | **171** | 61.5% |
| Price too far from its moving average | 47 | 16.9% |
| Base too long or too short | 37 | 13.3% |
| Not enough price history | 23 | 8.3% |
| Daily swing too small | 0 | — |
| No prior run-up | 0 | — |

The quietness check alone rejects more than the other three combined. Notably,
the daily-swing requirement never rejected a single trade — though it does
withhold a *scoring point* from a third of them, which is a separate issue
covered later.

---

## Test 1a — Is the quietness check set too strictly?

Since quietness causes 61.5% of setup rejections, it got its own investigation.

**What the check does:** it looks at the last 3 to 7 days and asks whether any
stretch was calm enough — specifically, covering 1.5 ADR or less. If even the
calmest 3-day stretch was wider than that, the stock is judged to be *still in
motion* rather than *coiled and resting*, and it's rejected.

**An earlier draft predicted these rejections would mostly be his add-on buys.
That prediction was wrong, and it's recorded as wrong rather than quietly
dropped:**

| The 171 rejections | Count | Share |
|---|---|---|
| **Fresh entries** (not add-ons) | **148** | 86.5% |
| Add-on buys | 23 | 13.5% |
| **Only just missed** (within 2.0 ADR) | **113** | 66.1% |
| Genuinely wide open, no base at all | 58 | 33.9% |

Two thirds only *just* missed, clustered at a typical 1.85 against a 1.5 cutoff.
That's the shape of a boundary drawn slightly too tight — not of stocks wildly in
motion.

**The recommendation is still "change nothing", but now for one reason instead of
three.** The one-sided-ruler rule forbids loosening it: quietness has clearly
demonstrated signal (see Test 1b below), so the rule's precondition fails no
matter how the rejections are distributed. That was always the load-bearing
argument. The 113 near-misses are logged as **the open question**, and answering
them properly needs the false-positive rate we don't have.

---

## Test 1b — What "tight" actually means in his own trades

*This section comes from a separate throwaway experiment, not from the main
study — see `backend/replay/prototype-tightness/` on the
`worktree-prototype-tightness` branch. Treat it as preliminary.*

The check above rejects stocks for not being quiet enough. But nobody had asked
the reverse question: **among the trades he actually took, how quiet were they?**
The 1.5 cutoff was inherited from an older tool and never checked against him.

Measured over the same 649 trades:

| Stretch examined | typical (median) | share under 1.5 ADR |
|---|---|---|
| **last 3 days** | **1.31 ADR** | **64.4%** |
| last 4 days | 1.55 | 47.3% |
| last 5 days | 1.86 | 33.1% |
| last 6 days | 2.06 | 20.3% |
| last 7 days | 2.25 | 13.9% |

**Finding 1 — the 1.5 cutoff sits at about his 64th percentile.** It admits 418
of his 649 trades and rejects 231. There's no gap or natural break at 1.5; his
distribution runs straight through it. The number is reasonable, but it's a
choice rather than something discovered in the data.

**Finding 2 — one of the two settings can't do anything.** The "3 to 7 days"
range is really just "3 days": a longer stretch can only contain *more* movement,
never less, so the calmest stretch is always the 3-day one. Confirmed on all 649
trades. This means **only the lower bound decides pass or fail** — the upper bound
merely affects the *score* a stock gets afterwards. The two settings sit side by
side in the code looking like a matched pair, but they do unrelated jobs.

**Finding 3 — quietness genuinely predicts profit, and it does so smoothly.**

| How quiet beforehand | Trades | Average result |
|---|---|---|
| under 1.0 ADR | 164 | **+2.02R** |
| 1.0–1.5 | 254 | **+1.35R** |
| 1.5–2.0 | 139 | **+0.84R** |
| 2.0–3.0 | 82 | **+0.35R** |
| over 3.0 | 10 | **−0.36R** |

A clean, steady decline — and crucially, **nothing special happens at 1.5**. A
trade at 1.6 performs about the same as one at 1.4.

> **Why averages and not typical values here:** the typical trade in *every* row
> above loses exactly what was risked. Most of his trades stop out; he makes
> money because the occasional winner is enormous. Looking at the typical trade
> would show a loss everywhere and suggest nothing works.

At the current 1.5 cutoff, the trades kept average +1.61R and those rejected
average +0.61R — so the cutoff does separate better from worse. But it costs
**231 of his own trades (35.6%), carrying 17.4% of his total profit**, to express
something that varies gradually.

**Finding 4 — his stop-loss is a completely different measurement.**

| measured on the same days | typical |
|---|---|
| width of the calm stretch | **1.310 ADR** |
| his actual stop-loss distance | **0.345 ADR** |

A **3.8× gap** between two things both called "tight". He risks that single day's
move, not the whole base. This exactly reproduces a figure the main study already
established (Test 4 below), by a different route — a good sign the measurement is
sound.

**What this does and doesn't justify.** It does **not** justify loosening the
cutoff — if anything it makes the case against loosening stronger, since quietness
now has *both* selection signal and outcome signal. What it adds is a **price tag**:
we now know what the hard cutoff costs. The live question is no longer "is 1.5 the
right number" but "should this be a pass/fail gate at all, rather than a graded
score with a much looser safety net" — and that still can't be settled without the
false-positive rate we don't have.

---

## Test 2 — Would his trades have appeared on the list he actually reads?

Only **104 of 658** trades (15.8%) appeared in the app's field at all, and only
**41** landed in the top 30 by score.

**The headline result was negative, and it's the study's most consequential
finding.** Under the scoring system live at the time, his hand-picked entries
scored 3.5 stars or better **17.3%** of the time. The general population of
setups scored that well **17.8%** of the time.

In other words: his real, high-conviction trades landed at the top of the scale
at *the same rate as the random background they were drawn from*. The scoring
system was not distinguishing his picks from anything else.

### The re-run, after the scoring weights changed

The weights were later revised (see Test 3c). Re-run on the identical field, with
the weights as the only thing that changed:

| | Old weights | New weights |
|---|---|---|
| Appeared in the field | 15.8% | 15.8% — unaffected by scoring |
| In the top 30 | 41/658 | **45/658** |
| **His picks at ≥3.5★** | 17.31% | **14.42%** |
| **The field at ≥3.5★** | 17.82% | **8.83%** |
| **Gap** | **−0.52pp** | **+5.59pp** |
| Statistical significance | none | **p = 0.055** |

**Verdict: the negative result is weakened, not reversed.** His picks now score
well at 1.63× the field's rate, in the right direction. But this must not be read
as "the scoring works", for three independent reasons:

1. **It's circular.** The new weights were *derived from* this very comparison of
   his picks against the field, then tested on that same comparison. A scoring
   system fitted to a separation will reproduce that separation. The honest
   reading is "the reweight did what it was built to do", not "the scoring
   ranks".
2. **It's marginal anyway.** p = 0.055 — fitted in-sample and *still* short of
   the conventional threshold.
3. **29% of the field is still missing**, permanently.

**And the mechanism is unflattering.** His picks' average score rose by +0.010.
The field's average *fell* by −0.187. The reweight didn't recognise his entries —
**it demoted everyone around them.** That's a considerably weaker claim than "the
system found his picks".

> **This test rests on the weakest foundation of the three.** It ranks his trades
> against a field missing a quarter of its names, using a sixth of his record. No
> ranking claim should be argued from it in either direction. Deliberately, **no
> percentile or rank-position figure is ever produced** — those would look precise
> while quietly flattering the system.

---

## Test 3a — Does the scoring predict which setups run?

Each scoring quality was checked against how far trades actually ran, across the
104 detected trades.

**Nothing in the scoring predicts a run.** Every correlation is negligible; the
largest is 0.158 and it points the *wrong way*. Four of the six testable
qualities correlate *negatively* with how far a trade ran. On this sample size,
none is distinguishable from zero.

**Read this narrowly.** It says the scoring doesn't predict how far a trade runs
*among trades he already chose*. That's the range-restriction problem from
earlier doing real work: these all passed his eye already. And one quality — the
prior run-up — is **untestable by construction**, since every setup examined had
already cleared the strength filter, so it's 100% throughout and there's nothing
to correlate.

Also reported here, and worth pausing on — the shape of his results:

| | typical | best | average |
|---|---|---|---|
| Realised R | **−1.00** | +104.02 | **+1.245** |

The typical trade loses exactly what was risked. The average is strongly
positive. One trade returned 104×. That's the whole method in one line: **be
wrong cheaply, often, and be right enormously, rarely.**

---

## Test 3b — Which qualities does his eye actually select on?

This compares the 69 setups he took against the 14,354 he didn't take on the same
evenings. **No outcome data is involved** — this asks only what his eye favours.

| Quality | Weight then | He took | He passed over | Difference |
|---|---|---|---|---|
| **Big daily swing (ADR)** | ×1 | **87.0%** | 57.6% | **+29.4** |
| **Quietness before entry** | ×2 | **59.4%** | 38.6% | **+20.8** |
| Near moving-average support | ×1 | 76.8% | 72.5% | +4.3 |
| Volume pattern | ×1 | 36.2% | 40.1% | −3.9 |
| Orderly base | ×2 | 27.5% | 36.6% | **−9.1** |
| **Base length** | ×1 | **44.9%** | 58.3% | **−13.4** |
| Prior run-up | ×1 | 100% | 100% | 0.0 |

> **This is where the signal is, and it explains Test 2.** Two qualities separate
> his picks sharply: **big daily swing** and **quietness**. That's what his eye is
> doing.
>
> Three go the *other way*. He takes setups that hit the "orderly base" and "base
> length" criteria **less** often than the ones he passes over — and orderliness
> carried a **double** weight. So the app was **paying double for a property he
> systematically avoids, and single for the one he selects on hardest.** That's a
> coherent explanation for why Test 2 came back flat: a score built partly on the
> inverse of his criteria won't rank his picks above the field.

> **Important framing:** the setups he didn't take are a **comparison group, not a
> rejection list**. He may never have seen most of them. Nothing here labels them
> bad.

---

## Test 3c — The rescoring that shipped

The selection contrast above justified a change, with one strict rule:

> **The evidence justifies the *direction* of a weight, never its exact size.**

The *signs* survive the coverage hole; the *magnitudes* don't. So each weight was
set from the **ordering** of the differences — no weight reads a number off the
table.

| Quality | Was | Now | Why |
|---|---|---|---|
| Quietness | ×2 | ×2 | +20.8pp — second-strongest selector |
| **Daily swing (ADR)** | ×1 | **×2** | **+29.4pp — the sharpest selector** |
| **Orderly base** | ×2 | **×1** | **−9.1pp — hit less often than the field** |
| **Base length** | ×1 | **×0** | **−13.4pp — the largest wrong-way signal** |
| Prior run-up | ×1 | ×1 | identical in both groups — kept as documentation |
| Moving-average support | ×1 | ×1 | +4.3pp — within noise |
| Volume | ×1 | ×1 | −3.9pp — within noise |

Base length keeps a **visible ×0 row** rather than being deleted, so a reader sees
it was measured and found worthless, and gets routed to the reasoning. The ×0
says *the quality as currently defined* earns nothing — not that base length is
irrelevant. A specific suspect (the 14-day maximum) is named and left open.

---

## Test 4 — Two direct measurements

### The app's suggested stop-loss was about 4× too wide. **Confirmed.**

| | typical stop | within 1.0 ADR |
|---|---|---|
| What the app proposed | 1.28 ADR | 14.2% |
| What he actually used | **0.345 ADR** | **98.15%** |

The app was proposing a stop nearly four times wider than the trader's own
convention. This made the "can I afford this position?" indicator nearly
meaningless — not because positions were unaffordable, but because the stop
convention was simply wrong.

**Adopted.** The app now places its suggested stop at his measured convention —
0.345 ADR below the trigger. Note carefully what this does and doesn't do: the
score never looks at the stop, so **this cannot change the ranking at all.** It
changes what the app proposes and what a card claims about risk. Nothing else.

### The daily-swing requirement silently withholds a point from a third of his trades. **Confirmed.**

The minimum daily swing is set at 5%. His actual swing at entry is 4.7% at the
25th percentile — so the requirement withholds its scoring point from **30.7%** of
his real entries.

Since daily swing is the quality he selects on *most* sharply, a floor that
withholds credit from the bottom third of his own trades is blunting the single
dimension the record says matters most to him. Note this costs a *score point*
only — the swing requirement never rejected a trade outright.

---

## The limitations, carried with the same weight as the results

- **Survivorship.** 29% of stocks missing, skewed toward those that later died.
  Permanent.
- **Everyone already passed his eye.** The qualities he applies most consistently
  vary least, so they correlate with nothing. A flat result there is evidence of
  his discipline.
- **No precision, ever.** No control group exists. Recall must never be optimised
  on its own.
- **Cold-start drift.** The simulation starts from nothing, so borderline stocks
  may drift from what really happened. 126 days of warm-up settle this before any
  measured day, but the drift is real and recorded rather than engineered away.
  Prices are split-adjusted and won't match a 2020 broker screen.
- **Scope.** US only, 2019–2022, with **86.6% of trades from 2020–21** — a
  once-in-a-decade momentum market.

---

## What transfers to the Indonesian market

**The *shape* of these findings travels. The *numbers* do not.**

Carry the structural lessons — which filter is costing entries, that stop
conventions should be measured against the trader's own risk rather than assumed,
that a flat result must be read against how much variety there was. Carry **none**
of the figures. No number here should be presented as an expectation for IDX; the
trade record contains no IDX trade.

---

## What this study cannot say

- **It cannot claim the ranking works.** Test 2's flat result under the old
  weights is real. The improvement under new weights is in-sample and marginal.
  Neither may be read as validation.
- **It cannot give a false-positive rate.** No control group.
- **It cannot say anything about the prior run-up quality.** It's 100% in every
  group that can be constructed, so there is nothing to measure.
- **It cannot speak to other setup types** (Episodic Pivot, Parabolic Short), to
  intraday entries, or to any stock in the missing-data list.

---

## Reproducing it

```
python -m replay.study --store data/replay.duckdb
```

One command rebuilds the field once and computes coverage plus all four analyses
against it, writing both a readable report and a machine-readable results file —
both committed next to this document, so every figure above is checkable against
the run that produced it rather than quoted from memory.

The Test 1b figures are the exception: they come from the throwaway experiment
and are rebuilt with `backend/replay/prototype-tightness/measure_tightness.py`.
