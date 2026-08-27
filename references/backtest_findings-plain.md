# Testing the app's method against fourteen years of two markets — findings, in plain language

*This is a plain-language retelling of [`backtest_findings.md`](backtest_findings.md).
Same run, same numbers, same conclusions — just without assuming you already speak the
project's vocabulary. Where the two ever disagree, **the technical version is the
authority**, because that's the one whose figures are checked against the committed run
output.*

**Nothing in the app was changed by this run.** One change is *allowed* by it, and the
rules say that change has to be named in writing before anything moves. It's named below.
It hasn't been made.

---

## What this was for

The [earlier study](qullamaggie-replay-findings-plain.md) looked at 828 trades a real
trader actually made and asked how many of them the app would have shown him. That's a
useful question, but it has a hole in the middle of it: every trade in that record is a
trade he **chose to take**. Nobody wrote down the setups he looked at and passed on.

So the earlier study could say "the app would have caught 84% of his trades". It could
*not* say "and of everything the app shows you, this fraction is worth taking" — because
it never saw anything he didn't take. It had a numerator and no denominator.

This run builds the denominator. It takes **every single setup the app's detector names**,
over fourteen years, in two markets, and trades all of them mechanically by a fixed rule.
No judgement, no skipping, no picking. Then it asks the question the earlier study
couldn't:

> **Does the method have an edge, or did the trader?**

## The vocabulary, up front

- **R — profit compared to what was risked.** Risk $100 and make $200, that's "+2R".
  Lose the planned amount, that's "−1R". Using R instead of dollars lets a $5 stock and a
  $500 stock be compared fairly.
- **Expectancy** — the average R across every trade, winners and losers together. This is
  the headline number. Positive means the rule made money on average; negative means it
  lost.
- **A detection** — one setup the app's detector names on one evening. Fourteen years of
  US evenings produced about 97,000 of them.
- **The two markets** — US stocks and IDX (Indonesian stocks, on the Jakarta exchange).
  They are always reported separately, never averaged together. There's a reason for that
  below.
- **Survivorship bias** — the reason this whole document keeps two numbers instead of
  one. Explained in its own section, because it's the biggest thing here.

---

## The headline

Here is the whole result. Every row is "trade every setup the detector names, hold it on a
10-day moving-average trail, and see what the average trade earned."

| | period | what it earned | what it earned if you count the missing stocks | trades |
| --- | --- | ---: | ---: | ---: |
| **US** | all 14 years | **+0.050R** | **−0.363R** | 12,311 |
| **US** | with 2020–21 removed | **−0.081R** | **−0.446R** | 9,092 |
| **IDX** | all 14 years | **+0.680R** | **+0.418R** | 1,196 |
| **IDX** | with 2020–21 removed | **+0.284R** | **+0.072R** | 986 |

Read that as four separate results, not one. Three things explain the shape of the table.

**Why 2020–21 gets its own row.** 2020 and 2021 were a once-in-a-decade momentum tape —
almost anything that broke out kept going. A fourteen-year average that includes them
describes a market that mostly wasn't there. So every figure is reported twice: with those
two years and without. On the US, taking them out flips the result from barely positive to
slightly negative. That flip is the most honest single fact in the table.

**Why there are two money columns.** The right-hand column is the same result with the
missing stocks counted. That's the next section, and it's the important one.

**Why the two markets are never combined.** The earlier study established that the *shape*
of these findings travels between the US and Jakarta, but the *sizes* don't — Indonesian
stocks are more volatile and cost far more to trade. An average of the two would describe
neither. There is no combined number anywhere in either document.

## The missing stocks — the biggest limitation, stated before any result

The price data available for this run only covers companies that **still exist today**.
Every company that went bankrupt, got acquired, or was delisted somewhere in the last
fourteen years is simply absent from it.

That is not a small gap and it doesn't point in a random direction. The missing companies
are disproportionately the ones that *died*, which means the data is a study of survivors.
A backtest run on survivors will look better than reality, always.

So the run measured the gap instead of mentioning it. Someone reconstructed a dated list of
every US stock ticker that existed at various points since 2008 — 96 archived snapshots of
the official exchange listing files — and compared it to what's actually in the price data.

**The US is missing 37.7% of the trading history it should have.** (By raw count of
company names it's 51.8%; 37.7% is the fairer figure, because it weights each missing
company by how long it was actually listed.)

Then the run did the pessimistic thing: it re-ran the whole result assuming **every single
missing stock would have been a full losing trade**. That's the right-hand column in the
table. And here's the part that matters:

> At 37.7%, the missing stocks would contribute six losing trades for every ten real ones.
> That drags the result down by about 0.6R. **The US headline is +0.050R.** The correction
> is more than ten times the effect.

This is why the bound isn't a footnote. On the US, the size of what we can't see is larger
than the thing we're trying to measure. Any positive US result here should be read as "we
cannot rule out zero", not as "it works".

**Jakarta's version of this number is weaker, and that matters, because Jakarta is the
market that passed.** No free source exists that reconstructs a dated list of Indonesian
listings, so its 12.7% gap was counted a cruder way — by comparing what the data provider
lists today against what the exchange says is listed today. That count misses recycled
ticker symbols entirely and doesn't weight by time listed. **So Jakarta's 12.7% is
optimistic in a known direction: the real figure can only be worse.** The document says
so on the same line as the result, not underneath it.

## The verdict

Before any code was written, two rules were fixed in advance, so that nobody could look at
the result and then decide what counted as success.

**The "kill" rule:** if the method loses money in *both* markets across *both* periods, the
detector doesn't work and the app's claim shrinks to "we rank what a human picks."
**It didn't fire.** Jakarta was positive throughout and the US was barely positive over the
full window.

**The "ship" rule:** a market passes if it makes money across both periods *and* still
makes money after the missing-stocks correction.

**The US: inconclusive.** Positive over fourteen years, negative with 2020–21 removed. It
neither passes nor fails, and the rule written in advance says exactly what to do about
that:

> *nothing. The run is reported as inconclusive, and reaching for a swept variant to break
> the tie is the failure mode the contract exists to prevent*

That's worth unpacking, because there was a real temptation here. Afterwards, the run tried
eight variations — different cost assumptions, different quality thresholds. One of them
lifts the US to +0.153R, which looks like a pass. It isn't one, for the reason the rule
names: if you try enough variations, one of them wins by luck. That's why the number of
variations tried is printed next to every variant figure. The pre-registered number stands.

**Jakarta: passes.** +0.680R and +0.284R, and still positive after the correction (+0.418R
and +0.072R). It is the only market anything is allowed in.

Two cautions belong right next to that pass, and they're in the technical document too.
**+0.072R is thin** — that's the number the whole pass actually turns on. And **it rests on
the weaker of the two corrections**, the Jakarta one that can only be too generous.

## The change this allows

The rules say a passing market allows a change, and that the change must be **named in
writing before anything moves**. This is that naming.

Some background. The app scores each setup on several qualities. Two more qualities are
"registered candidates" — measured, written down, not yet used. One of them, called
**Relative move**, has been stuck for months: the rule for admitting a new quality asks
whether the trader *picked* stocks that had it, and Relative move landed **0.06 percentage
points** short of the line — a line the rule itself admits is a judgement call rather than a
measurement. Nothing could move it, because the same test kept landing in the same place.

This run asks a different question of it: not "did he pick these stocks" but **"did these
stocks make money"**. And on Jakarta, it's the one clear positive in the entire study:

| market | quality | with it | without it | difference | verdict |
| --- | --- | ---: | ---: | ---: | --- |
| US | RS line | −0.099R | +0.092R | −0.191R | no evidence |
| US | Relative move | +0.098R | −0.298R | +0.396R | no evidence |
| IDX | RS line | +1.066R | +0.541R | +0.525R | no evidence |
| IDX | **Relative move** | **+0.852R** | **−1.075R** | **+1.927R** | **predicts** |

Jakarta setups with Relative move earned +0.852R. The ones without it lost 1.075R. That's
a gap of nearly two full R, and it's the only one in the table statistically clear of zero.

**So: the change this allows is to settle Relative move's stuck threshold, on Jakarta,
using outcomes.** With four limits attached, all binding:

- **Jakarta only.** The same quality shows nothing on the US.
- **It still goes through the normal evidence rule** for changing anything in the app. An
  outcome result is evidence entering that process, not a way around it.
- **It is not an automatic admission.** The admission rule asks a different question, and
  the two don't convert into each other. What's allowed is *settling the threshold*, not
  overruling it.
- **It's allowed, not done.** Nothing has moved. Doing it is a separate piece of work.

## What else the run found

**Of everything the detector shows you, how much is any good?** This is the question the
earlier study literally could not answer. Now it can:

| | US | IDX |
| --- | ---: | ---: |
| Setups named | 96,914 | 12,821 |
| Of those, how many actually broke out | 12.8% | 9.5% |
| Of those, how many closed in profit | 3.1% | 2.4% |
| Of the trades actually taken, how many won | 24.4% | 25.3% |

Those bottom two rows are the same trades measured against different denominators, and the
difference is the point. **About one setup in thirty-two closes green** — that sounds
terrible until you notice that the thirty-one others mostly never trigger at all, and a
setup that never triggers costs nothing. Of the trades you'd actually be *in*, about one in
four wins. That's normal for this style: the winners are big enough to carry the losers.

**Does the star score predict which setups run? No evidence that it does — in either
market.** The score does one thing reliably: the *worst*-scoring US setups are reliably bad
(−0.335R, clearly below zero, over 2,608 trades). Above that floor it doesn't order
anything, and in both markets the *top* band is not the best band. So the honest description
is **"it filters, it doesn't rank"** — which is a narrower claim than the app currently
makes. Note carefully: "no evidence it ranks" is not "it doesn't rank". One study can't
prove that.

**Is the app's market-condition advice right?** The app tells you to "sit out" in a
`HOSTILE` market and trade "reduced" in a `CHOPPY` one, and until now that was written on
no evidence at all. The run priced it, and the answer is *undecided in both markets, and
the two markets disagree*:

- On the US, sitting out `HOSTILE` would have saved **450.6R** over 2,924 trades. The word
  points the right way.
- On Jakarta, sitting out `HOSTILE` would have **cost 95.0R**. There, `HOSTILE` was the
  middle state, not the worst one.
- "Reduced" for `CHOPPY` isn't supported either way. On the US `CHOPPY` was actually
  *slightly better* than the friendly state.

Neither result is statistically clear, so the run leaves the app's wording as unfounded as
it found it. But it does establish that the same word isn't earning the same thing in the
two markets, which is itself worth knowing.

## What this cannot say

These limits were written down before the run, not after it. A limitation named in advance
is a caveat; one discovered afterwards is a retraction.

- **It can't say what the trader would have done.** It takes everything the detector names,
  mechanically. He picked. Nobody knows what he'd have skipped.
- **It can't see inside a trading day.** Everything is decided on daily closing prices.
- **It can't tell you whether you could actually run this with real money.** This is a
  *signal-level* study: it takes every setup independently, with unlimited capital and no
  limit on how many positions are open at once. So it says nothing about how much money the
  method could absorb, how many trades pile up at the same time, how deep the losing
  stretches get, or what happens when all the winners arrive together — which, in a momentum
  method, is exactly what they do. That question is **deferred rather than dismissed**: it's
  specified and waiting, not answered.
- **It can't bring back the delisted companies.** It can only put a bound on how much their
  absence flatters the result, which is what the second money column does.

And three more this run added to the list. It **can't test a looser volatility filter**,
because it never generated the setups that filter excludes — answering that needs a fresh
run, not a query. It **can't compare Jakarta setups against the trader's picks**, because
the trade record contains no Indonesian trades at all. And it **can't settle the US**, which
is the actual content of an inconclusive result rather than a gap to be closed by picking a
friendlier variant.

## Checking this yourself

One command, from the top of the repository:

```
bash scripts/backtest_headline.sh
```

It prints both markets, both periods, each figure next to its missing-stocks correction,
and the verdict in the words that were fixed in advance. It reads the committed result files
under `references/` — so what it checks is that the recorded result and these documents
still say the same thing. It tells you that on its first line.

To recompute the numbers from the raw price data instead of reading them back, add
`--from-store data/backtest.duckdb`. That needs the price database built first, which is
about two hours of paced downloading and a gigabyte on disk — which is why it isn't in the
repository.
