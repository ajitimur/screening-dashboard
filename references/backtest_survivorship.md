# The survivorship hole — how big it is, and what it could be worth

Phase 2 of [the out-of-sample backtest plan](../docs/out-of-sample-backtest-plan.md)
(PRD #182, issue #196). Two deliverables, both ahead of believing any performance number:
a **dated count** of names that traded inside the measured window and are gone from today's
enumeration, and a **sensitivity** — the pre-registered headline metric re-run with that
missing population assigned a full stop-out. The gap between the two is the bias bound, and
it rides on every result as one line.

Measured **2026-08-26** with:

```
python -m backtest.survivorship --store data/backtest.duckdb --fetch-spine \
    --out-json references/backtest_survivorship.json
```

The spine crawl took 101 minutes and read 96 archived captures. The dated count is
committed at `references/backtest_survivorship.json`; the spine it was built from is
cached at `data/backtest.duckdb.spine.json`, which `data/*` does not track.

**The headline of this page.** The US hole is **51.8% of the names** listed in the
window, or **37.7% weighted by how long each was listed** — well above findings §2's
29.5% floor, which is the direction a 2012 start should move it. At that weight the
pessimistic twin is negative for any headline below **+0.605R**. The bound is not a
footnote on this run; it is larger than the effect the run is looking for.

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

| US | Value |
| --- | --- |
| Spine captures read | 96 (`nasdaqlisted.txt` + `otherlisted.txt` + today's live files) |
| Spine span | 2008-01-04 .. 2026-08-26 |
| Years of the window with no capture | 0 |
| Largest gap between captures | 552 days |
| Captures the archive would not replay (retried, then recorded) | 8 |
| **Names sighted in the window** | **15,171** |
| Absent from today's enumeration | **7,346** |
| Recycled — listed today, bars begin after the spine first saw the symbol | **512** |
| Asked about, no bars at all | 3 |
| Covered | 7,310 |
| **Hole, by name** | **51.8%** |
| **Hole, weighted by time listed** | **37.7%** |

The count is over one population — every common-stock symbol the spine sighted inside
2012-01-01..2026-08-25 — so both halves of the share are counted over the same thing.
That is worth stating because the first version of this measurement did not do it: the
absent names were counted over the spine's whole roster and the covered names over
today's *fetch set*, 5,498 against 20,923, which is not a share of anything and read as
a hole two-thirds larger than the one that is there.

The three no-bars names are #187's three US refusals, arrived at independently. They
sit in the hole rather than in the covered population: they resolve, the crawl asked
about them, and they can price nothing — which is the difference between the question
findings §2 started with and the one it had to switch to.

**Two shares, because they answer different questions.** The name count is what
findings §2's 92-of-312 is comparable to. The exposure weighting is what the bound is
scaled off, and the two differ by fourteen points because the absent names are
short-lived: their median listed span inside the window is **2.65 years** and **40.3%
of them were listed for under two**. Counting each as one whole missing name would
credit an eighteen-month listing with as many chances to throw a signal as one listed
throughout.

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
was some other listing. That pair is what `coverage_census` reads, and it is the reason this
phase needs a spine rather than only a bar store.

Coverage is therefore decided by `session_verdict` — does the bar history cover the session
being replayed — and never by whether the symbol resolves. It returns four verdicts rather than
a boolean, because "no bars at all", "bars begin after" and "bars end before" have different
causes and a report that collapsed them would name none of them.

## IDX, measured from the other side

No free source reconstructs a dated Jakarta listing roster back to 2012, so IDX has no spine.
Its hole is measured where it *is* visible: the exchange lists names the provider never
enumerated. #187's crawl made that pair exact.

| IDX | Value |
| --- | --- |
| Enumerated by the provider | 840 |
| Listed by the exchange | 962 (`idx.co.id` Company Profiles, read 2026-08-26) |
| **Gap** | **122 (12.7%)** |

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

At the measured US weight of 37.7%, the observed trades are 62.3% of the population, so
the missing population contributes **0.605 trades for every covered trade** — each one a
full stop-out after the same costs. The twin is therefore

```
pessimistic = (headline − 0.605 × (1 + cost)) / 1.605
```

which is checkable without a denominator, and it says something the run has not
measured yet:

| Headline | Pessimistic twin | Bound |
| --- | --- | --- |
| +0.10R | −0.315R | 0.415R |
| +0.25R | −0.221R | 0.471R |
| +0.40R | −0.128R | 0.528R |
| **+0.605R** | **0.000R** | 0.605R |

**A headline below +0.605R has a negative pessimistic twin.** No breakout expectancy
this repo has measured is near that, so on today's hole the bound does not qualify the
result — it exceeds it. That is a finding about the *store*, not about the method, and
it is the reason Phase 2 sits ahead of believing any performance number.

**The numbers in this section are the bound's arithmetic, not a result.** Phase 3 and 4
have not run — issue #198, the full fourteen-year denominator, is still open — so no
simulated trades exist to put a real headline in the left column. The wiring is in
place and needs no further code:

```
python -m backtest.metric --store data/backtest.duckdb \
    --out-json references/backtest_primary_metric.json
python -m backtest.survivorship --store data/backtest.duckdb \
    --metric-json references/backtest_primary_metric.json \
    --out-metric-json references/backtest_primary_metric_bounded.json
```

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

| | findings §2 | This run |
| --- | --- | --- |
| Window | 2019-04 .. 2022-12 (3.7 years) | 2012-01 .. 2026-08 (14.6 years) |
| Population | 312 tickers a trader executed | 15,171 names the directory listed |
| Hole | **92 of 312 — 29.5%** | **7,861 of 15,171 — 51.8%** |
| Recycled inside it | 11 | 512 |
| Blind-spot trades | 172 of 828 — 20.8% | not measurable until #198 |
| Blind-spot share of realised R | 18.0% | not measurable until #198 |

The measured hole is **larger** than the floor, which is the direction a longer window
should move it, and by roughly the ratio the extra decade implies. Had it come back
*smaller*, `against_floor` would have flagged it — a shrinking hole over a longer window
is far more likely to mean the coverage test stopped asking the hard question than that
the store got better.

The two populations are not the same object and the comparison is of rates only: §2
counts tickers one trader chose to execute, this counts every name an exchange listed.
A trader's 312 are the liquid, volatile names a momentum screener surfaces, so if
anything they should carry a *higher* death rate than the listing at large — which makes
51.8% against 29.5% the more striking of the two readings.

## What this still cannot say

- The count is a **floor** twice over: once for the spine's density, and once because a name
  that listed and delisted between two captures appears in neither.
- IDX's hole is a standing count from the enumeration side, with no dates and no recycled half.
- The missing-trade scaling assumes the missing names traded at the covered names' rate, which
  understates the population most likely to have been surfaced.
- The bound prices the missing names at a full stop each. It does not price what a *portfolio*
  holding them would have done, which is deferred with the rest of the portfolio level.
- **The population includes instruments the run would never trade.** The spine is narrowed by
  `screener.universe.is_common_stock`, the app's own rule, but that rule reads a security's
  name and an ETF whose name says neither "Fund" nor "Trust" passes it. Those survive on
  *both* sides of the share — a closed ETF lands in the absent count, a live one in the
  covered count — so the effect on the ratio is largely self-cancelling, but the population
  is wider than the universe the metric is computed over.
- **Nothing here is filtered by the universe gates.** A name listed for four months in 2021
  is counted as a missing name at its full exposure, even though ADTV ≥ $10M, ADR20 ≥ 3.5%,
  close > SMA50 and the detector's 80-bar minimum would between them have admitted it on few
  sessions or none. The exposure weighting narrows this considerably against a raw name
  count, but the honest reading of 37.7% is still *an upper bound on the missing
  opportunity*, not an estimate of it.
