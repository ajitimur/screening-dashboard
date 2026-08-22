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
| Stocks affected by the hole | **92** |
| Trades lost to it | **172** |
| Share of his total profit in those lost trades | **18.0%** |

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

**And an eleventh was hiding in plain sight.** Asking "does this symbol have any
price history in the replay years?" still isn't strict enough — the right question
is "does it have history covering *the night we'd have had to spot the trade*?"
`FUSE` was traded in January 2021, but the price history the store holds under
that symbol starts in March 2022: a different company. The first ten escaped only
because their replacement listings begin after the replay window ends, so the
looser test happened to give the right answer. `FUSE` is where that luck ran out —
its two trades were being counted as replayable and then blamed on the app for
"not enough history". Fixing the question moved the count from 91 / 170 / 18.15%
to the 92 / 172 / 18.0% in the table above. The hole didn't grow; it was measured
properly.

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

The rule has **two limbs**, because the app has two different kinds of filter, and
what counts as evidence differs between them:

- **Scoring qualities** (is the base tidy? is the stock swinging enough?) — the
  test above applies as written.
- **Cross-sectional cuts** (is this among the strongest performers?) — these can't
  be tested the same way, because everything that reaches the scoring stage has
  already passed them, so there's no variety left to measure. Instead the loss must
  be measured directly, shown *not* to be an artefact of missing data, fixed
  **structurally** rather than by nudging a threshold, and quoted with its cost in
  how much wider the net gets.

An earlier version of this study exempted cross-sectional cuts from the rule
entirely. **That exemption was wrong** and was replaced — the second limb exists so
those cuts are governed rather than unguarded.

That second half matters more than it sounds. Every trade in the sample already
passed his judgement, so the qualities he applies *most* consistently barely vary
— and anything that barely varies will correlate with nothing. **A flat result on
such a quality is evidence of his discipline, not of the quality's
irrelevance.** Confusing those two would systematically dismantle the parts of
the method that work best.

---

## Test 1 — Which filter throws away his trades?

**658 of the 828 trades could be replayed** (the other 170 are the coverage
hole). 80 of those are repeat entries. Those counts are the ones this run measured;
the stricter coverage question described above puts them at 656 and 172, which
moves nothing in the percentages below.

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

> **This filter is a third tighter than every document said.** There are two
> versions of "strongest performers" in the code, and they were being conflated.
> One combines five time horizons and lets through 27.2% of all stocks; the other —
> **the one the detector actually uses** — combines only three (1-month, 3-month,
> 6-month) and lets through just **19.4%**. Every write-up quoted the looser figure
> while measuring the tighter gate. Corrected throughout; the glossary now names
> them separately.

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

### The near-misses now have a price tag: about **400 extra stocks per real trade recovered**

That "open question" was left open because nobody could price the trade-off. The
worry is real — loosening the check would let more stocks through, and we have no
way to know how many of the extra ones would have been duds. That part is still
true and always will be.

But "how many duds?" and "how many *extra stocks*?" are different questions, and
the second one is just counting. So it was counted, on every one of the 821 days
the study covers:

| Quietness cutoff | Trades of his the app now finds | Extra stocks on the whole list | **Extra stocks per real trade recovered** |
|---|---|---|---|
| **1.5 ADR** (today) | 57.9% | — | — |
| 1.75 ADR | 68.1% | +25,813 | **385** |
| 2.0 ADR | 75.2% | +45,625 | **404** |
| 2.25 ADR | 80.2% | +59,997 | **411** |

**The answer is about 400.** Loosening to 2.0 recovers *all 113* of the
near-misses and takes the app from finding 57.9% of his trades to 75.2% — a big
gain. It does it by putting **45,625 more stocks** onto the list across those 821
days. Each real trade recovered costs roughly 400 extra names to look at.

**And there's a second result that points the same way.** The whole point of finding
a setup is that it appears on the **top-30 board** — the list he'd actually read.
Loosening the check makes *fewer* of his real trades reach that board, not more:
**112 → 109 → 104 → 103** as the cutoff widens. The extra stocks crowd his own out.
So the change buys a better "did we spot it at all?" number and gives some of it
back where it counts.

That said, keep the size in view: nine trades out of 656, across 821 days. It isn't
a big enough move to decide anything by itself. What makes it worth mentioning is
that it goes the *same* direction at every cutoff, and the *opposite* direction to
the recall gain it's supposed to come with.

**Verdict: change nothing, and now there's a measurement behind it.** The one-sided
ruler still forbids the loosening outright, and nothing measured here changes
that — this number describes the cost, it doesn't license the change. Two of the
three reasons are new: the cost is a stated ~400 rather than an unknown, and the
board result argues against the change on its own terms.

**What this number is not.** It counts *stocks*, not *mistakes*. Nothing here says
any of those 45,625 extra names would have lost money — the record contains no
setup he turned down, so there's nothing to check them against. Test 1b gives the
newly-admitted band a rough quality (his own trades in that range averaged +0.84R,
positive but weaker than the tighter band's +1.35R), but that's measured on trades
he *took*, so it doesn't supply a dud rate either.

### A bug found along the way, which affects Test 2's headline

Setting this measurement up meant looking closely at how the study builds its daily
list — and it turned out the list is **empty on 316 of the 821 days**, about 38% of
them.

The cause is mundane: the strength rankings are only kept for two years, and the
study builds all 947 days of rankings *first* and only then goes looking for
setups. By the time it looks, the early days' rankings have been thrown away, so
those days find nothing and nobody noticed.

It was measured directly, and the broken version reproduces the committed figures
exactly — which is how we know that's the cause:

| Where the rankings are read from | Days with any setups | His trades that reached the list | Reached the top 30 |
|---|---|---|---|
| The stored rankings (what the study did) | **505 / 821** | **104** | **45** |
| The rankings the study just computed | **821 / 821** | **242** | **112** |

So Test 2's headline — "only 104 of his trades, 15.8%, ever reached the list" — is
substantially an artefact. Read properly it's **242 (36.9%)**, and 112 reached the
top 30 rather than 45. This ticket fixed it *for the quietness measurement above*
(which is why those numbers are trustworthy) and recorded it; correcting Test 2
itself is a separate job needing a full re-run.

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
move, not the whole base.

**And we now know exactly where his stop comes from.** A separate study (Test 5
below) found that his stop width has **no relationship at all** to how far the
stock is from its moving average — the correlation is essentially zero. Its
conclusion: **he places his stop at the low of the day he buys.** So the stop is
set by that one day's trading range. Not by the calm stretch before it, not by
anything else. That's the mechanism behind the 3.8× gap.

Three separate measurements of his stop now agree with each other (Test 4, Test 5,
and this one — different subsets of trades, different calculation routes, same
answer). This is about as solid as anything in the project gets.

**What this does and doesn't justify.** It does **not** justify loosening the
cutoff — if anything it makes the case against loosening stronger, since quietness
now has *both* selection signal and outcome signal. What it adds is a **price tag**:
we now know what the hard cutoff costs. The live question is no longer "is 1.5 the
right number" but "should this be a pass/fail gate at all, rather than a graded
score with a much looser safety net" — and that still can't be settled without the
false-positive rate we don't have.

### A useful contrast with the "extended" study

Test 5 below sets a hard cutoff for a *different* quality, and its reasoning is
worth borrowing. It explicitly refuses to draw the line at "wherever most of his
trades fall", on the grounds that **where his habits sit and where trades stop
working are two different questions, and the outcome data should win.**

Applying that same test to quietness gives the *opposite* answer, and that's the
point:

| | What the results look like | So the honest way to encode it |
|---|---|---|
| Distance from the moving average (Test 5) | A **cliff** — profit collapses past a specific point | A hard cutoff |
| Quietness (Test 1b) | A **smooth slope** — no special point anywhere | A graded score |

These two qualities genuinely differ in kind, so they shouldn't be built the same
way. And note that the current 1.5 cutoff satisfies *neither* test: it isn't a
percentile anyone deliberately chose (it was inherited, and merely happens to land
at his 64th), and it isn't placed at a feature in the results, because there is no
feature there to place it at.

---

## Test 1c — How long the base takes to build, and when it goes quiet

*Another throwaway experiment — see `backend/replay/prototype-base-length/` on the
`worktree-prototype-base-length` branch. Treat it as preliminary.*

Test 1b asked how quiet the last few days were. It never asked how they *got*
quiet. Same 649 trades, four questions: how long had the stock been going
sideways, how far had it fallen while doing so, what had it done before that, and
when did the calming actually start?

### How long is the base? Two answers, because it's two questions

**How long since the stock was last this high** — the overhang it's breaking
through: typically **24 trading days**, about five weeks. But it varies enormously:
one in eight breaks out of something less than a week old, and **one in four breaks
out of something more than three months old**.

**How long it's been trading in a narrow band** — the actual quiet stretch:

| Width of the band | How long price stayed inside it |
|---|---|
| Very tight (1.5 ADR) | **3 days** |
| Tight (2 ADR) | **5 days** |
| Moderate (3 ADR) | **11 days** |
| Loose (4 ADR) | **17 days** |

So: a base is a **multi-week structure whose genuinely tight part is only a few
days long**. Those are two different things, and the app only sees the second one.

That's actually good news about one setting. The app looks at stretches of 3 to 7
days — which brackets the tight part almost exactly. It's the right window. It just
can't tell you whether there's a real base behind it, because the tight part runs
out after ~3 days whether the structure behind it is two weeks or four months old.

### The surprise: the daily swing never actually shrinks

Everyone assumes a stock "goes quiet" before a breakout — that its daily movement
shrinks. **It doesn't.** Measured across the three months before he buys:

| Trading days before he buys | 90 | 60 | 30 | 20 | 10 | 5 | 0 |
|---|---|---|---|---|---|---|---|
| Typical daily swing | 5.8% | 5.9% | 6.0% | 6.0% | 6.1% | 6.2% | **6.1%** |

Flat as a board. The stock is swinging about 6% a day the whole time.

What *does* change is how much **ground it covers**. A stock can swing 6% every day
and still end the week where it started, if the days cancel each other out. That's
exactly what happens:

| Trading days before he buys | 90 | 60 | 30 | 20 | 10 | 5 | 3 | 1 | 0 |
|---|---|---|---|---|---|---|---|---|---|
| Ground covered over 5 days (in daily swings) | 2.4 | 2.4 | 2.3 | 2.4 | 2.4 | 2.3 | 2.2 | 2.0 | **1.9** |

Dead flat for three months, then it falls — **but only in the last week or two.**

Two things follow, and both matter for how the app is built:

1. **The tightening is late.** It starts about 7–10 days before he buys, not weeks
   before. There's no long slow wind-up to detect.
2. **Screening for a "calming" stock is the wrong instrument.** If you wait for the
   daily swing to shrink, you'll wait forever on his kind of stock — it never
   shrinks. Worse, if you *rank* stocks by how much they've calmed down, you'll rank
   his trades below quieter, worse ones.

And the quiet is young when he buys. The typical trade has been in a narrow band for
just **one day**; four in ten aren't in one at all on the day before entry. He's
buying a few days after the last burst of movement, not at the end of a long sleep.

### What the base is sitting on

The stock has usually **doubled** before the base even starts — typically **+95%** in
the three months prior, and often far more. And the base isn't shallow: price
typically gives back **31%** from the high while going sideways, with a quarter
giving back half or more.

### Does any of this tell you which trades made money?

Partly — and not the part you'd guess.

| | Effect on how far the trade ran | Real or noise? |
|---|---|---|
| Longer quiet stretch (10+ days) | Ran roughly **twice as far** | Real |
| Bigger prior run (200%+) | Ran roughly **twice as far** | Real |
| Deeper base (50%+) | Ran meaningfully further | Real |
| **How old the base is** | **Nothing** | Noise |

**Base age doesn't matter. The size of the move being digested does.** But two
health warnings: the "bigger prior run" result is partly circular (he buys big
movers, so of course his winners had big prior moves), and the strongest result
rests on only 43 trades. Nothing in the app was changed on the strength of this.

---

## Test 1d — Are the last 3 days quieter than the 3 before? (Yes. It doesn't help.)

*Throwaway experiment — see `backend/replay/prototype-adr3/` on the
`worktree-prototype-base-length` branch.*

A natural screening idea: compare the last 3 days against the 3 days before them.
If they've calmed down, that's your setup. Is there anything in it?

**This test introduced something the whole study had been missing: a comparison
group.** Every other result here looks only at trades he took, which is why the
study keeps admitting it can't measure false alarms. Here we can get halfway: take
the *same stocks on 6,450 random ordinary days* — days he wasn't buying — and run
the identical measurement. That doesn't tell us about false alarms (a random day
isn't a setup he rejected), but it does answer one clean question: **is this a
feature of his entries, or just of the kind of stock he likes?**

### Step 1: yes, the calming is real

| | On the day before he buys | On a random day |
|---|---|---|
| Daily swing, last 3 days vs the 3 before | **0.89×** (11% calmer) | 0.99× (no change) |
| Ground covered, same comparison | **0.78×** | 0.99× |
| Volume, same comparison | **0.87×** | 0.98× |

The random days sit at 1.00, exactly as they should. His entries are genuinely
calmer, cover less ground and trade less stock. So there *is* something there.

### Step 2: but it's the same fact you already have

"Calmer than last week" and "tight right now" are nearly the same statement. So
group the trades by how tight they are *right now*, and ask again within each group
whether the calming still picks out his entries:

| Trades that are... | Does "calmer than before" still help? |
|---|---|
| Very tight right now | **No** — 0.90×, slightly *worse* than random |
| Moderately tight | **No** — 0.94× |
| Not tight | **No** — 0.85× |

It vanishes. Meanwhile plain tightness — which the app already measures — picks his
entries **1.9× more often than random days, and 3.3× when it's very tight**. The
comparison idea is the tightness check wearing a disguise, and it's the weaker of
the two.

### Step 3: and it doesn't predict profit

Sorting his trades by how much they calmed down, or how much volume dried up, makes
no difference to how far the trade ran. The formal test comes back at a coin flip.
Same pattern as everywhere else in this study: these qualities describe **what he
buys**, not **which of his buys work**.

### The verdict

**Don't build it.** It's real, it's redundant, and it doesn't predict anything. Recorded
here so nobody proposes it again.

**But the trick behind it is worth keeping.** Comparing his entries against the same
stocks on ordinary days is cheap, and it caught a redundant idea before it reached
the code. Any future idea can be put through the same question: *does it still pick
out his trades once you hold the obvious thing constant?* If not, it isn't a new
idea.

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

**Independently confirmed twice since.** A later study (Test 5) measured his stop
again on a different subset of trades, reading prices from a different source and
calculating the daily swing a different way. It got **0.346** where this got
0.345, and matched on every other quartile too. The tightness experiment (Test 1b)
makes a third. Two independent routes to four matching figures is about as firm as
this record gets.

### The daily-swing requirement silently withholds a point from a third of his trades. **Confirmed.**

The minimum daily swing is set at 5%. His actual swing at entry is 4.7% at the
25th percentile — so the requirement withholds its scoring point from **30.7%** of
his real entries.

Since daily swing is the quality he selects on *most* sharply, a floor that
withholds credit from the bottom third of his own trades is blunting the single
dimension the record says matters most to him. Note this costs a *score point*
only — the swing requirement never rejected a trade outright.

---

## Test 5 — How far above the moving average does he actually buy?

*Full detail in [`qullamaggie-entry-ma-distance.md`](qullamaggie-entry-ma-distance.md).
Matched on 579 trades.*

The method notes claim his entries "hug the rising 10/20/50-day average", and that
this is really the same rule as his stop-size limit. Neither half had a number
attached. Both turn out to be checkable.

**He does enter close — to the 10-day.** The typical entry sits **4.1% above the
10-day average** (about 0.7× a normal day's swing). 70% of entries are within one
day's swing of it; 92% within two.

**But "10/20/50-day" is not one thing.** The typical entry is **2.11× ADR above the
50-day** — he is not hugging that one in any meaningful sense. Only 21.5% are
within one day's swing of it. Lumping the three together, as the method notes do,
hides a real distinction.

### Why buying "extended" hurts — not for the reason anyone assumed

The assumed reason for staying near the average is that buying far away forces a
wider stop, or gets you shaken out. **The data says that's wrong.** Trades bought
far from the average get stopped out at about the *same* rate — the win rate holds
steady out to 2× ADR, and the stop size he sets barely changes.

**What collapses is the upside.** The share of big winners (3R or better) roughly
halves between 1× and 2× ADR while the win rate stays flat. The trades still
*work* about as often — they just stop *paying*.

The interpretation: buying well above the 10-day means buying late into a move
that's already largely spent. You get a normal win rate on truncated gains. And a
strategy that only wins 23% of the time **cannot survive on truncated gains** — it
needs the huge winners to carry everything.

> **This distinction decides what a fix would even look like.** If the problem were
> getting shaken out, a wider stop or smaller position would rescue an extended
> entry. Since the problem is a spent move, **nothing about position management
> rescues it.** The only correct action is to not take the trade.

### The proposed definition of "extended"

> **More than 1.5× ADR above the 10-day average.** Past that, the strategy's
> expected return is zero. **Past 2.5× ADR, don't trade it at all** — that bucket
> contains 24 trades and *zero* winners.

At a typical 5.9% daily swing, 1.5× ADR is roughly **9% above the 10-day**, and the
hard line about 15%. Encouragingly, that lands close to a rule of thumb he'd stated
himself on stream from completely different reasoning ("already ~14% past the
trigger — it's gone").

**Two lines rather than one**, deliberately, because the data has two features: a
zone where the edge thins (worth a warning) and a zone where it's absent (worth a
refusal). One number would throw that distinction away.

### One result that complicates it

Entries *below* the 10-day do **badly** — worse than entries just above it
(−0.20R average, 14.6% win rate). So being *near* the average isn't the goal;
being near it **on the correct side** is. Below the 10-day means the breakout has
already failed, or hasn't happened yet — a different setup wearing a breakout's
clothes. Any "extended" rule must therefore be **one-sided**: it should disqualify
far-above and stay silent about below, which is a separate problem.

### And it settles a claim in the method notes

The notes say the moving-average rule and the stop-size rule "are the same rule".
**In this record they aren't even correlated** (essentially zero). Because he stops
at the low of the day he buys, his stop is set by that day's range — not by how far
price has run from the average.

So these are two genuinely separate filters that fail for different reasons: one
rejects trades you can't size, the other rejects trades whose move is already
spent. **Both are needed.**

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
- **It cannot say anything about the prior run-up quality** — it's 100% in every
  group that can be constructed, so there's nothing to measure. **A partial way
  around this has since been found:** Test 5 uses *distance above the 50-day
  average* as a continuous stand-in for "how far has this already run". Unlike the
  yes/no version, that has real variety in it, and across that range it correlates
  weakly **positively** with results — the opposite sign to distance above the
  10-day. This doesn't validate the existing check, which stays unmeasurable. It
  shows the underlying quantity becomes measurable once expressed as a *degree*
  rather than a *yes/no* — the same move proposed for quietness in Test 1b. The
  caveat attached there applies at full force: a 2020–21 market rewarded
  distance-from-the-50-day almost everywhere.
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

Several sets of figures sit outside that command:

- **Test 1b** comes from a throwaway experiment — rebuild with
  `backend/replay/prototype-tightness/measure_tightness.py`.
- **Test 1c** likewise — `backend/replay/prototype-base-length/measure_base.py`, then
  `summarize.py` beside it.
- **Test 1d** likewise — `backend/replay/prototype-adr3/measure_adr3.py`, then
  `summarize.py`. `build_html.py` beside it writes a page you can open and drive:
  move the threshold, then hold tightness fixed and watch the advantage disappear.
- **Test 5** is its own study — rebuild with `scripts/entry_ma_distance.py`, which
  writes `references/qullamaggie-entry-ma-distance.csv` alongside its write-up.
