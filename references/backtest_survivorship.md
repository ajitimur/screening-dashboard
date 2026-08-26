# The survivorship hole — how big it is, and what it could be worth

Phase 2 of [the out-of-sample backtest plan](../docs/out-of-sample-backtest-plan.md)
(PRD #182, issue #196). Two deliverables, both ahead of believing any performance number:
a **dated count** of names that traded inside the measured window and are gone from today's
enumeration, and a **sensitivity** — the pre-registered headline metric re-run with that
missing population assigned a full stop-out. The gap between the two is the bias bound, and
it rides on every result as one line.

Measured with:

```
python -m backtest.survivorship --store data/backtest.duckdb --fetch-spine \
    --out-json references/backtest_survivorship.json
```

## The listing source, and why this one

The count needs a **listing spine**: a dated roster of who was listed when. Differencing one
enumeration against an exchange's own count cannot supply it — #187 watched Yahoo's screener
drop `SOHO.JK`, a live name still trading, from its listing and restore it inside seventeen
minutes, so a single enumeration is a snapshot of a churning membership rather than a roster.

The source used is the **Nasdaq Trader symbol directory** — `nasdaqlisted.txt` and
`otherlisted.txt`, the same two files `screener.source.parse_us_listings` reads live — read at
past dates from the **Internet Archive**, with today's live files as the final snapshot. Each
capture is a point-in-time roster of every US listing, carries tickers rather than CIKs, and
dates itself on its own `File Creation Time` line. A name present in a 2013 capture and absent
from today's enumeration was listed then and is gone now, which is exactly the claim the count
needs.

Two candidates named in the plan were tested and set aside:

- **Exchange delisting notices** reach EDGAR as Form 25 / 25-NSE and are complete back to
  2001, but the filings identify the issuer by **CIK and company name only** — no ticker. The
  delisted names are precisely the ones absent from every current CIK-to-ticker mapping, so
  closing that gap would mean fetching a filing per company to recover a symbol the spine
  already carries.
- **Index-constituent change histories** are dated and free, and they cover the S&P 500. A
  momentum screener's hole is in small caps, so a large-cap spine measures the wrong
  population.

### The coverage was verified before the count was taken

`ListingSpine.verify` refuses a spine that does not **bracket** the window, and the refusal is
not a formality: a spine whose oldest capture landed inside the window would report every name
as first listed at that capture, and the count would be a measurement of the source's own
edges. The archive's newest capture of `nasdaqlisted.txt` was **2026-06-11** against a window
running to 2026-08-25, which is why the live files are fetched as the final snapshot — the
same source read at today's date rather than a past one.

**Density is reported rather than refused**, because it fails differently. The captures are
roughly annual and unevenly spaced, so a name that listed *and* delisted between two of them
appears in neither and is invisible to the count. That does not make the number wrong; it
makes it a **floor**. The silent years and the largest gap ride on the committed result for
that reason.

## What was measured

<!-- FIGURES -->

## The hole has a silent half, and it needs the spine to be seen at all

A delisted name is absent from today's enumeration and the count above finds it. A **recycled**
name is absent from no list: the ticker was reassigned to an unrelated listing, so it resolves
today, it has bars, and for part of the window the bars are a different company's. findings §2
found eleven of them in a four-year window, and `FUSE` — paired with a 2021-01-04 entry, bars
running 2022-03-07..2022-12-22 — had bars *inside* the window and passed every absence check.

The thing worth stating is that **bars alone cannot find them**. A first bar in 2019 says only
"no bars before 2019", which is exactly what a genuine 2019 IPO looks like — and an IPO is no
survivorship hole at all: the company did not exist, and a run with no bars for it is right
rather than blind. What separates the two is the *pair*: the spine listed this symbol on a
dated snapshot, and the store's bars for it begin after that date, so on that date the symbol
was some other listing. That pair is what `recycled_symbols` reads, and it is the reason this
phase needs a spine rather than only a bar store.

Coverage is therefore decided by `session_verdict` — does the bar history cover the session
being replayed — and never by whether the symbol resolves. It returns four verdicts rather than
a boolean, because "no bars at all", "bars begin after" and "bars end before" have different
causes and a report that collapsed them would name none of them.

## IDX, measured from the other side

No free source reconstructs a dated Jakarta listing roster back to 2012, so IDX has no spine.
Its hole is measured where it *is* visible: the exchange lists names the provider never
enumerated. #187's crawl made that pair exact.

<!-- IDX -->

That figure says how many names are missing **now**, not who left or when — it is a standing
snapshot of a churning membership, and the read date rides on it for that reason. And IDX's
recycled half is reported as **unmeasured**, not as zero: telling a recycled ticker from an IPO
needs a dated sighting, and without a spine there is none. "We could not tell" and "there are
none" are opposite findings, and the committed JSON carries `recycled_names: null` rather than
`0` so no later reader can mistake the first for the second.

## The bound

The sensitivity re-runs the headline metric with the missing population assigned
`PESSIMISTIC_R = −1.0` — a full stop-out — after the same costs the covered trades paid. How
many missing trades there are is scaled off the covered ones: a hole of one name in five means
the observed trades are four-fifths of the population.

**That scaling is an assumption, and it is optimistic.** It supposes a missing name would have
traded at the same rate as a covered one. The names that died are the volatile ones a momentum
screener surfaces most, so the true missing population is likely larger than the scaling
implies, and the true bound wider.

The bound is arithmetic over the expectancy cell rather than over synthesised trades —
expectancy is a mean, so the twin is `(Σr + m·p) / (n + m)`. It is checkable by hand, and it
never invents a bar series whose own bugs would land inside the bound.

<!-- BOUND -->

The pair is not a correction and the twin is not an estimate of the truth. The truth is
somewhere between them, and the pair is the honest statement of that.

### It rides on every result as one line

`backtest.survivorship.attach_bias_bound` puts the bound on the metric's report and
`backtest.metric.format_metric` prints it, so a reader cannot reach a headline without passing
its bound. When nothing attached one, the line prints **as the absence**:

```
  bias bound: not attached — this figure is survivor-biased by an unmeasured amount (backtest.survivorship)
```

A blank there would read as "no bias", which is the one reading this phase exists to make
impossible.

## Against findings §2's floor

<!-- FLOOR -->

## What this still cannot say

- The count is a **floor** twice over: once for the spine's density, and once because a name
  that listed and delisted between two captures appears in neither.
- IDX's hole is a standing count from the enumeration side, with no dates and no recycled half.
- The missing-trade scaling assumes the missing names traded at the covered names' rate, which
  understates the population most likely to have been surfaced.
- The bound prices the missing names at a full stop each. It does not price what a *portfolio*
  holding them would have done, which is deferred with the rest of the portfolio level.
