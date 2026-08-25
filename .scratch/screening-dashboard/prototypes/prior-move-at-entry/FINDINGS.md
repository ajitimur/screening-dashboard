# How big is the prior move before his entries? (prototype, side-car)

**Written up as** `references/qullamaggie-replay-findings.md` §3f (plain-language mirror:
Test 1e). This file is the working record; the findings document is what other work cites.

**Status:** prototype. Evidence only — no constant in `detection.py`, `ranks.py` or
`score.py` is touched, and nothing here is proposed for the rubric yet.

**Run:** `backend/.venv/bin/python .scratch/screening-dashboard/prototypes/prior-move-at-entry/prior_move_at_entry.py`
(per-trade rows: `prior_move_at_entry.csv`, including the QQQ leg)

## Why this did not exist already

`Prior move` is the one dimension the replay study cannot measure: every detection clears
the decile gate by construction, so the dimension is 100% in every group and has zero spread
(`qullamaggie-replay-findings.md` §5a, §9). The only continuous handle found so far was a
*proxy* — distance above the SMA50 in ADR units (`qullamaggie-entry-ma-distance.md` §5).
Nobody had measured the quantity itself: the raw `1w/1m/3m/6m/12m` return standing behind
each of his entries.

## Method

582 of 828 logged breakout longs (70%) joined to daily bars — `data/screener.duckdb` US
`adj_close` first, the delisted remainder from the Yahoo cache the entry-to-MA study already
built. Returns are the rank table's own definition: calendar-anchored `adj_close` ratios
(`indicators.calendar_return`), measured **through the session strictly before entry** —
he enters at 09:42 median, so the entry day's return is not on screen at the click.

Skips: 153 no bar data (delisted / reused ticker), 77 whose logged fill fits no split ratio
inside the entry day's range — the recycled-symbol guard — 16 with under 25 bars of history.
The survivorship hole of findings §2 attaches here in full: the drops are the blown-up
2020–21 small-cap cohort, so the true tail is likely wider than measured.

**Background:** the same tickers on random ordinary days in the same window, one draw per
entry, quarantined ±21 bars around his own entries (the §3d device). Not a control group of
rejected setups — none exists — so this supports no precision claim, only "is this a property
of the *entry* or of the *kind of stock*".

## The distribution

Prior move at entry, raw % and in ADR units (`move% / ADR%`), against the same-name background:

| lookback | n | median % | mean % | p25 | p75 | p95 | negative | median ×ADR | ordinary-day median % |
|---|---|---|---|---|---|---|---|---|---|
| 1w | 582 | **0.3** | 1.2 | −2.6 | 4.0 | 13.9 | 46.4% | 0.06 | 0.1 |
| 1m | 582 | **7.0** | 17.1 | −1.7 | 20.2 | 84.5 | 28.2% | 1.32 | −0.1 |
| 3m | 576 | **23.8** | 51.3 | 3.6 | 63.8 | 227.9 | 21.2% | 4.14 | −5.1 |
| 6m | 567 | **55.8** | 105.4 | 15.1 | 124.0 | 370.7 | 16.8% | 10.60 | −11.2 |
| 12m | 531 | **119.3** | 233.1 | 29.1 | 254.7 | 904.1 | 16.0% | 22.91 | 0.4 |

Four things this says.

**1. The prior move is a 3–12 month object, and it is enormous.** The median entry sits on a
+56% six-month and +119% twelve-month run. Means run 2× the medians — the distribution is
long-tailed to the right, which is the shape the method predicts and the reason the app ranks
on pure return rather than a risk-adjusted one (`ranks.py`).

**2. The last week is flat, and that is the whole point.** Median 1w is +0.3% — statistically
indistinguishable from the same names on an ordinary day (+0.1%), and 46% of entries are
*down* on the week. He buys the quiet end of the base. This is independent support for the
`1w` exclusion from the detection gate that #149 measured and ADR 0003 records: a name
top-decile on the week alone has momentum, not a prior move, and at his own entries the week
carries no signal at all.

**3. The signal separates from the background at 1m and peaks at 6m.** In ADR units the
entry-vs-ordinary gap is +0.02 (1w), +1.34 (1m), +5.25 (3m), **+12.4 (6m)**, +22.8 (12m). The
6m gap is where the ordinary day is most clearly *not* what he buys (its own median is −11%).
The 12m gap is larger but noisier — an ordinary day's 12m median is 0.4%, so the panel's 12m
column is dominated by a handful of 10-baggers.

**4. It is not a uniform requirement.** 27% of entries are positive on all five lookbacks;
35% on four; 9% on two or fewer, and 16% of entries have a *negative* twelve-month return.
The gate is a percentile, not an absolute, so a name can be top-decile while down 30% on the
year in a market that is down more — which is exactly what a 2022 entry looks like.

ADR at entry is 5.9% median against 5.5% on an ordinary day: he trades volatile names, and
buys them at slightly-above-their-own-normal volatility. Small, but the direction is up.

## Netted against the tape (QQQ)

The objection every result in this window attracts: 2020–21 paid for long-horizon momentum
almost everywhere, so is a +119% median 12m move the *stock* or the *market*? Measured — QQQ
on the same entry dates, over the same calendar windows, from the same store; `^IXIC` (the
app's actual `MARKET_INDEX`, §5d) run alongside as a check that the answer is about his
entries and not about the benchmark. Relative return is compounded,
`(1 + stock) / (1 + QQQ) − 1`, not differenced: +900% against a +30% tape is ×7.7, and that
is the quantity that means "outran the market".

| lookback | stock median | QQQ median | relative median | share beating QQQ | ordinary day beats QQQ | ^IXIC check |
|---|---|---|---|---|---|---|
| 1w | +0.3% | +0.9% | **−0.3%** | 48.1% | 49.1% | 47.9% |
| 1m | +7.0% | +4.4% | **+4.3%** | 63.4% | 46.5% | 63.7% |
| 3m | +23.8% | +7.8% | **+15.6%** | 73.2% | 38.0% | 73.4% |
| 6m | +55.8% | +16.9% | **+35.0%** | **74.2%** | 37.8% | 75.1% |
| 12m | +119.3% | +39.7% | **+59.9%** | 67.5% | 40.2% | 69.4% |

**The tape was a third of it, and the selection survives.** QQQ itself was up 39.7% median over
the twelve months before his entries and *negative on only 1.7% of them* — this record sits
almost entirely inside a bull tape, and it is a real caveat. But netting it out leaves +59.9%
median relative on 12m and +35.0% on 6m, and 74% of entries beating the index over six months
against **38% of the same names on an ordinary day**. That 36-point spread is the selection,
and it is not the market's.

**6m is the sharpest window against the index, not 12m.** The raw 12m number is bigger, but
its beat-rate is *lower* (67.5% vs 74.2%) and a quarter of entries actually **underperformed**
QQQ over the year. Read together with §3's ADR-unit gaps, 3m–6m is where "strong relative to
the market" and "strong in his book" line up best — which is the window the method's own
literature names.

**The week is a coin flip against the index too.** Relative 1w median −0.3%, 48.1% beating —
indistinguishable from the 49.1% an ordinary day scores. Third independent line now pointing at
the same conclusion as the `1w` exclusion (#149, ADR 0003).

`^IXIC` reproduces QQQ to within 2 points on every row, so nothing here is a benchmark artefact.

On outcome, netting changes little: relative 12m top quartile 1.95R vs 0.61R bottom
(Spearman +0.019), relative 6m 2.16R vs 0.54R (+0.042), relative 1m still perverse
(−0.037, best bucket is the *worst* relative month). Same weak signs as the raw table below —
the tape was not what produced them, and it was not what hid them either.

## Does the size of the prior move predict the outcome?

Quartiled within each lookback, scored on his own logged 10-SMA exit (mean R; his hit rate
is ~23% so the median trade is a stop-out in every bucket):

| lookback | Spearman(move, R) | Q1 mean R | Q2 | Q3 | Q4 |
|---|---|---|---|---|---|
| 1m | **−0.073** | 1.98 | 0.84 | 0.44 | 0.97 |
| 3m | +0.059 | 0.60 | 1.07 | 0.24 | 2.38 |
| 6m | +0.037 | 0.43 | 1.11 | 0.68 | 2.16 |
| 12m | +0.016 | 0.67 | 0.87 | 1.08 | **1.97** |

The signs split the way the entry-to-MA study's did, and for the same mechanical reason: a big
*recent* (1m) move means an extended entry and a wide stop, a big *long-horizon* (6–12m) move
means a real prior advance to base out of. The top 12m quartile returns 1.97R against 0.67R
for the bottom; the top 1m quartile is *worse* than the bottom (0.97 vs 1.98).

All four correlations are weak (|ρ| ≤ 0.073) and the quartile means are carried by a few large
winners — 2020–21 rewarded long-horizon momentum nearly everywhere, the same caveat the
entry-to-MA study carries. **This licenses nothing on its own.** What it does establish is
that the quantity `Prior move` gates on has real, measurable spread once expressed
continuously, and that the spread's favourable direction is the *long* lookbacks — which is
the ADR 0005 criterion the binary dimension cannot meet.

## Open, and deliberately not done here

- The natural next step is a rubric proposal: a continuous `Prior move` graded on 6m or 12m
  return in ADR units, replacing the constant dimension ADR 0005 flags as retirable. That
  needs the pre-registration ADR 0002 requires, and this prototype is not it.
- Coverage is 70% and skewed against the blown-up cohort. Any dimension proposal has to
  price that, in the way #141 and #149 price theirs.
- IDX is untouched. The whole trade record is US, and the QQQ comparison is US-only by
  construction — an IDX version needs its own benchmark (`^JKSE`).
- The bull-tape caveat is now *bounded*, not removed: QQQ was negative on 1.7% of his entry
  dates over 12m, so the record has essentially no bear-market 12m observations. A relative
  dimension fitted here would still be fitted to one regime.
