# Screening Dashboard

A locally-run, EOD swing-trading screener for two markets (`IDX`, `US`), built on the
Qullamaggie Breakout/Continuation method. This file is the ubiquitous language: code
should speak it — table names, API fields, variable names, UI labels.

This glossary was extracted from `.scratch/screening-dashboard/v1-spec.md` §2, which is
a design document and will be superseded. The language outlives it, so it lives here.

## Language

### Time and scope

**Market**:
`IDX` or `US`. The top-level axis of everything — runs, sessions, ranks, deciles, screens
and digests are all per market. There is no global "tonight".

**Session**:
One market's trading date. Everything derived is keyed `(market, session, …)`.

**Final bar**:
A daily bar for session `D`, where now is past `D`'s normal close plus 30 minutes in the
exchange's local timezone. Non-final bars are dropped at ingest.

**Phantom bar**:
A bar with zero volume — no trade occurred. Removed from the series entirely, never
zero-filled or carried forward.

**Run**:
One market's nightly pipeline execution. Publishes or is quarantined.

**Digest**:
One dated Markdown file per market per session listing today's breaks. The whole
notification layer.

### Universe and strength

**Instrument**:
Anything ingested. Carries a role of `candidate` or `reference`; reference instruments
(index, ETF) are computed like anything else but are never rankable.

**Universe**:
The tradeable set for a market on a session — liquidity, instrument type and listing age.
Membership is sticky: removal requires positive evidence. Unqualified, the word means the
**app's**, which is the one the product ships; the backtest's is a **stateless universe**
and is always named as one.
_Avoid_: watchlist, screen.

**Stateless universe**:
The backtest's tradeable set (PRD #182, `backtest.universe`) — close above SMA50, ADTV over
the contract's floor, ADR20 at or above **3.5%**, plus IDX's **Rp 100** data-validity trim,
all measured through **t−1** and with no reference to prior membership. A second classifier
beside the app's, never a replacement: the app's floors are $20M / Rp 1B against the
contract's $10M / Rp 10B, the app has no trend or ADR gate at all, and the app reads
yesterday's membership for both stickiness and its hysteresis band. Dropping that band
reintroduces the boundary churn it exists to damp — a name oscillating around a floor enters
and leaves day by day — which is **nearly free at signal level**, since each signal is
evaluated on its own session, and real at portfolio level. Recorded as a known difference,
not fixed. Its 3.5% sits **deliberately below** the rubric's `score.ADR_MIN` of 5%, because
findings §6 Finding 2 measured that 5% floor withholding a score point from 31% of his real
entries, so a universe cut at 5% would leave the ADR dimension no spread to test.
_Avoid_: backtest universe filter; reading the Rp 100 trim as a penny-stock filter — it is
**data validity**, and below it IDX quotes hit the tick grid hard enough that ADR and range
geometry stop meaning what they mean elsewhere.

**ADR**:
Average Daily Range, `SMA20(high / low − 1)`. The method's volatility unit; nearly every
threshold in the system is denominated in it.
_Avoid_: volatility, ATR.

**Lookback**:
One of `1w`, `1m`, `3m`, `6m`, `12m`. Calendar-anchored.

**Rank**:
A name's percentile within its market and lookback on a session. The shared substrate —
there is exactly one definition of "strong".

**Decile**:
Top 10% of a lookback's own population. The union of all five lookbacks' deciles is the
breadth substrate — **26.5%** of the universe, not 10%. It is not the gate the detector runs;
see **Detection gate**.

**Detection gate**:
The union of the top deciles of the *four* detection lookbacks (`1m`, `3m`, `6m`, `12m`) —
**21.9%** of the universe. The cut a name must clear before the detector is consulted.
Still distinct from the five-lookback union (26.5%), which adds `1w`: a name top-decile in
the last week alone is a momentum burst, not a prior move, and it is the one window measured
to be worth excluding. It unioned only three lookbacks, at 19.3%, until #149 measured what
`12m` admits and found the staleness the exclusion assumed did not occur — 1 of the 49
entries it recovers is dead on the other three windows (ADR 0003, amendment).

Three widths now exist in this codebase's history — **19.3%, 21.9% and 26.5%** — and quoting
one against a result measured under another misattributes the gate's cost. All three are from
`references/detection_gate_sweep.txt`, over the replay's 821 measured sessions
(2019-09-30 to 2022-12-30). ADR 0003 and findings §3 quote **19.4%** and **27.2%** for the
outer two: the same gates over the 505 sessions the store still held ranks for. The gates are
identical; the windows are not.

**Board / leaderboard**:
Top 30 names by raw return for one market and lookback. Five boards per market.

**Breadth badge `k/5`**:
How many of the five lookbacks a name is currently top-decile in.

### Themes

**Sector**:
Yahoo/Morningstar GECS sector, 11 values, same taxonomy on both markets.

**Industry**:
Yahoo's 145-industry level under sector. Industry is the theme layer — there is no
separate theme concept.

**Sector strength**:
Share of a sector's members in that lookback's top decile. Five numbers per sector.

**Shape differential**:
`share(1w) − share(6m)`, in percentage points. Rotation's default sort.

**Temporal delta**:
`share(1m, tonight) − share(1m, 20 sessions ago)`.

### The setup

**Prior move**:
The best low-to-high run-up ending at or before today, over windows of 21/42/63/126 bars.
Its peak is where the base starts.

**Base**:
Prior-move peak through today, capped at 45 bars. Always ends today — there is no such
thing as a base that ended last week.

**Cluster**:
The largest trailing 3–7 bar window spanning at most 1.5 × ADR, falling back to the 3-bar
window when none does. The quiet end of the base, and where **base tightness** is measured —
never a stop level. Since #154 the 1.5 shapes the window and does not gate: whether a name is
a detection at all is settled by the **far-outlier guard**, and the 7 is only a reporting
bound.

**Cluster length `k`**:
Bars in the cluster, and the only thing the upper bound of 7 can move. It is what the star
score's `Tightness` dimension read *until rubric v3*, which grades the **3-bar range**
instead; `k` is still persisted, still what the chart draws, and still what a v2 re-score
reads.

**3-bar range**:
A name's trailing 3-bar high-to-low span, in ADR (`range_3bar_adr`). The tightest window the
cluster scan can find — range is monotone in the window length — and so the **ungated**
measure of **base tightness**. Two jobs since #154: the number the far-outlier guard tests,
and the number the rubric's ×2 `Tightness` dimension is graded on. Persisted on every
detection, and reported on a cluster miss to say by how much it missed.
_Avoid_: cluster_min_range_adr (the pre-#146 name).

**Far-outlier guard**:
What the detector's `cluster` condition tests since #154: a detection requires a **3-bar
range** inside `OUTLIER_MULT = 3.0 × ADR`. It replaced the hard 1.5 cut, and does a different
job — it rejects a name genuinely in motion, rather than ranking how quiet a base is, which
the rubric now grades. **Provisional**, and sited on the one feature findings §3b's outcome
table offers: mean R is positive in every 3-bar-range bucket up to 2.0–3.0 and turns negative
only in the 3.0+ bucket, on **n = 10**. Not a percentile of his habits (#143). The evidence
that licenses it, and the sense in which ADR 0002 does not, is
`docs/adr/0004-replacing-a-threshold-with-a-graded-input.md`.
_Avoid_: tightness gate; `TIGHT_MULT`, which no longer gates. (`cluster` stays the name of the
detector's condition and of the funnel's `failed_condition` value — it is persisted.)

**Base tightness**:
How quiet the stock was *before* the break — the span of a trailing 3–7 bar window in ADR.
Setup geometry: it is what the **far-outlier guard** tests and what the rubric's ×2
`Tightness` dimension grades. Measured two ways, and the difference matters: the **3-bar
range** (`range_3bar_adr`) is the **ungated** measure, which is what findings §3b puts at a
median of **1.310 ADR** over his 649 replayable entries, and it is the one both the guard and
the rubric read; `cluster_range_adr` is the **gated** span of the window that cleared
`TIGHT_MULT`, so a *quieter* name can report a *wider* span by earning a longer window, which
makes it non-monotone in the thing being measured and unfit to grade on. Never a stop level —
**stop width** is 3.8× narrower on the same trades (see below), and reading a stop off this
quantity is the mistake issue #127 removed.
_Avoid_: tightness or tight, unqualified, in prose (the `TIGHT_*` constants and the published
`Tightness` rubric label keep their names); tight zone; tight stop.

**Envelope**:
The upper trendline — anchored at the cluster's max high, fitted backwards over the base's
highs with non-positive slope only.

**`line_ok`**:
Whether the envelope is a good fit (touch zones and bounded overshoot). Not a gate — a
silent tiebreak.

**Trigger**:
`cluster_high`, by identity — the envelope is anchored at the cluster's max high and can
never exceed it.

**Stop width**:
How much of the entry he is willing to lose — trigger to stop, in ADR (`stopw_adr`). Position
sizing, not setup geometry: a detector output and a card claim, fixed at
`STOP_CONVENTION_ADR = 0.345`, the median of his 649 executed stops (findings §6 Finding 1,
issue #127; reproduced quantile-for-quantile by §3b). It is **not** the consolidation low and
never was — he risks the **entry bar** (`references/qullamaggie-entry-ma-distance.md`).
Why it is a separate term from **base tightness**: findings §3b measured both on the same 649
entries at the same evaluation sessions — base 1.310 ADR against stop width 0.345 ADR, a
**ratio of medians of 3.80×** (median per-trade ratio 3.77×). Reasoning that "the stop sits
below the tight zone" places it near 1.3 ADR and nearly quadruples risk per trade. The two
are independently tunable and independently evidenced.
_Avoid_: risk_adr, tight stop, cluster-low stop, risk.

**Detection**:
A name with a valid base, a cluster inside the **far-outlier guard**, and MA catch-up, inside
the detection gate, on a session. A dated row.

**Break**:
An event, not a state: today's close above yesterday's trigger. Equivalently, today's
close is above the last `k` sessions' high.

**Star score**:
The rubric — 8 dimensions, 9 weighted points, halved to stars. The sort key of the only list
in the app. Its range is 0.5–4.5, never 0–5: one dimension always fires (`Prior move`) and one
is weighted zero (`Base length`). Seven dimensions are booleans; `Tightness` is a **graded
dimension**. Derived on read everywhere except a digest, which freezes the
value it was written with. Recalibrated to the method's revealed selection by PRD #138:
`Tightness` and `ADR` weigh ×2 (the two sharpest §5b selectors), `Base length` ×0 (its largest
wrong-way gap), everything else ×1. Weights come from the *ordering* of the measured selection
gaps, never their magnitude. The three-weight ordinal swap inside that recalibration — `ADR`
×1→×2, `Orderliness` ×2→×1, `Base length` ×1→×0 — is ticketed as #135.

**Graded dimension**:
A score dimension that maps a real-valued quantity to points in bands, rather than awarding
its whole weight on a boolean. `Tightness` is the only one (rubric v3, #145/#154): 2 points
at or under 1.0 ADR of **3-bar range**, 1 through 2.0, none beyond. Its shape is what findings
§3b licenses — a smooth monotone decline in outcome with no feature to hang a threshold on,
the opposite of the cliff #143 found in entry-to-MA distance. Two rules keep it replayable:
the points stay **integral**, so the nine-point ceiling and the `÷ 2` arithmetic do not move;
and the stored breakdown row carries the **value**, never one version's verdict about it, so
any **rubric version** can re-score a stored row exactly.
_Avoid_: continuous dimension, fractional score.

**Calibration target**:
What the rubric is fitted to encode — the method's revealed selection, evidenced by the
executed trades. Neither our own grading (a superseded proxy) nor outcome (measured, null).
_Avoid_: ground truth, benchmark.

**Calibration rule**:
What evidence licenses loosening a gate. Two limbs — one for score dimensions, one for
cross-sectional cuts — because precision is not measurable and recall alone would widen
every gate. Stated in `docs/adr/0002-what-evidence-licenses-loosening-a-gate.md`; not
restated anywhere else.

**Constant dimension**:
A score dimension true for every detection by construction, so it shifts every score equally
and can never move the sort. `Prior move` is the only one, measured at pooled spread 0.000 in
findings §5b and again in §5d, on a field 171% larger.

**It stays at ×1, and is retired only when something takes its slot** (#160/#161). ADR 0005
(`proposed`) calls keeping it "documentation bought at the price of a point", but that presumes
the point is **scarce** — and it is not: the ceiling is the sum of the weights, not a budget, so
a ninth dimension can be added without retiring the eighth and retiring this one frees nothing.
The measurement is not in doubt; what fails is the case for acting on it alone. Because the
dimension hits on every row its weight lands on every score, so zeroing *or* deleting it moves
the scale identically — ceiling 9 → 8, stars 0.5–4.5 → 0.0–4.0 — which re-bases every frozen
digest, `HERO_MIN` and acceptance B9 **while reordering nothing**. It is also the only breakdown
row recording that the name cleared the decile gate ADR 0003 is about, so retiring it before
that metadata exists loses information outright.
_Avoid_: reading §5b's 0.000 as a standing instruction to retire it; the spread says the
dimension cannot discriminate, not that removing it is free.

**Candidate dimension**:
A dimension **under measurement**, not in the rubric: computed on every detection in the
replay, carried beside the star score, reported as a column of the **selection contrast**, and
weighted by nothing. It is how ADR 0005's admission rule is exercised — a dimension earns a
rubric slot on a measured non-zero gap with non-zero pooled spread, and until that measurement
exists it must be unable to move a star, a sort or a board place. So it lives on a field member
of its own (`RS line` on `replay.field.ScoredDetection.rs_line`), never inside `SevenDimScore`,
and nothing in `screener` scores it. Two are registered, both measured, neither admitted —
`RS line` (rejected on a wrong-way gap) and **Relative move** (a positive gap that landed on its
own refusal threshold, #171). **Pre-registered as one variant, pass or fail** — trying several
and keeping the largest gap is magnitude-fitting (#128 Q2). A study may report further columns
beside a candidate, as §5e does for the raw and other-window moves; those are **descriptive and
permanently inadmissible**, and they are handed to `contrast_dimensions` as readers rather than
listed in `CANDIDATES`, so the registered list cannot quietly grow one. A candidate that fails
leaves its measurement behind and takes its wiring with it.
_Avoid_: experimental dimension, provisional dimension (a **graded dimension** is live; this
is not).

**RS line**:
`adj_close(name) / adj_close(index)`, hit when today's ratio is at or above the ratio at the
detection's own `base_start` — non-decayed, **not** a new high, so merely matching the index
passes. The benchmark is `MARKET_INDEX`; both legs read `adj_close`, and a missing bar on
either makes the value **absent** (`None`) — the question was never asked, which is a
different fact from asking it and getting no. The pre-registered boolean reads absence as a
miss (`rs_line_hit`) and never carries it forward, exactly as §5d published; the **stored**
row keeps the value, so a name whose benchmark had no bar is never confused with one that
genuinely decayed. It needs a second symbol's bars, so it
could only ever be computed in a caller (`screener.relative_strength`), never in `score.py`.
The first **candidate dimension**, and **rejected** (findings §5d, #160): Δ −2.1pp, a wrong-way
gap, on 11.2% disagreement with the break test it nearly restates. The live app does not
compute it — only the replay and the study script do, so §5d stays reproducible. The slot it
was proposed for is still open, and **Relative move** is the second candidate for it.

**Relative move**:
The `6m` return **relative to `MARKET_INDEX`**, compounded — `(1 + stock) / (1 + index) − 1` —
divided by the name's own `ADR`, taken at the session being scored and never past it. Hit when it is above zero: the name outran the index over six
months. The second **candidate dimension** (#170), **measured and not admitted** (findings §5e,
#171): Δ **+3.6pp** under the live detector — positive, unlike `RS line` — on a not-taken hit
rate of **84.94%** against a pre-registered ~85% ceiling, 0.29 standard errors inside it. The
criteria do not separate, so `Prior move` keeps its ×1 and `RUBRIC_VERSION` stays 3. Both legs read `calendar_return`, so the anchor is
calendar-dated and resolves to the last bar on or before it, and a missing leg is **absent**,
scoring `False` and never carried forward. Named apart from `Prior move` on purpose — a
**rubric version** re-scores a stored row by dimension name, so one label cannot mean two
quantities. The cut sits at zero, which makes the boolean ADR-invariant; the units are there
for the *value* a row would carry, so a later grading question can be asked without re-scoring
history.
_Avoid_: RS, outperformance. "Relative strength" names the *module* both candidates live
in (`screener.relative_strength`) and nothing narrower — never the dimension.

**Rubric version**:
The stamp identifying which weights and mappings produced a star score (`score.RUBRIC_VERSION`,
currently 3 — v2's nine weights with `Tightness` graded, #154; v2 was the PRD #138 nine-point
boolean rubric, v1 the ten-point one). Rides the API candidates payload and the digest header.
A star figure quoted without one cannot be compared to another. Every superseded version stays
live in `score.RUBRICS` so the paired A2 re-run can hold a field fixed and swap only the
rubric; adding a version never edits an older one.

**Regime**:
`FRIENDLY`, `CHOPPY` or `HOSTILE` per market, from one index each. Advisory only — never
filters, reorders or scores.

### Validation against the Qullamaggie trade record

Terms for the study of the ~828-row reference set of Kristjan Kullamägi's own breakout
trades (`references/trades_bo_gain10smaPct_desc.json`, entries 2019-10 to 2022-11).

**Executed trade**:
One of his real, actually-taken entries — ticker, date, time, entry price, stop price.
The only part of the reference set that is observed fact.
_Avoid_: trade, signal.

**Simulated exit**:
An exit rule applied to an executed trade after the fact, in two variants (10sma and
20sma), yielding gain, R, holding days, MAE and MFE. Not what he actually did — a
counterfactual. Never blur it with the executed trade's entry.
_Avoid_: exit, result.

**Replayable trade**:
An executed trade whose ticker has bars in the store **covering the session the trade is
evaluated at** — not merely bars somewhere under that symbol, which a **recycled symbol**
also has. 656 of 828. The test is "can this trade be evaluated?", so the same ticker can be
replayable at one entry and a blind spot at another.

**Blind-spot ticker**:
A ticker in the reference set whose bars cannot cover a trade it is paired with, because
the provider returns nothing for delisted, acquired or renamed names, or because the symbol
was recycled onto a later listing. 92 of 312 tickers, 172 trades, 18.0% of total R,
measured in the replay window (`2019-04..2022-12`). The measured size of the store's
survivorship hole. Superseded measurements: 81 / 141 / 11.7% over all history, and
91 / 170 / 18.15% under the has-any-bars test #139 replaced.
_Avoid_: missing ticker, delisted.

**Recycled symbol**:
A ticker reassigned to an unrelated listing, so the bars the store holds under it belong to
a different company than the one traded. Its bar history begins *after* the entry it is
paired with (`FUSE`: entry 2021-01-04, bars from 2022-03-07). It is a **blind spot**, and
the dangerous kind — absent from no list, it arrives looking replayable and, uncaught, is
charged to the detector as a `history` stage failure.
_Avoid_: reused ticker, symbol collision.

**Coverage gap**:
A ticker that has bars in the store but was not a universe member at the evaluation
session, so the replayed field could not rank it. A defect in the replay, not a verdict
about the name — kept apart from a ticker present but ranked outside the gate, which is a
real ranking verdict. Distinct from a **blind-spot ticker**, which has no bars at all: two
different holes, and conflating them corrupts the decile stage's accounting.
_Avoid_: missing from field, not in universe.

**Funnel stage**:
One gate an executed trade must pass for the app to have surfaced it, evaluated at the
session before entry: liquidity, decile, detection. Recall is reported per stage, never
as a single number.

**Continuation entry**:
An executed trade within 5 sessions of a prior entry in the same ticker — an add to a
position, not a fresh base. Counted in the recall denominator and tagged, never removed
from it.

**Outcome label**:
The dependent variable a study regresses features against. `rr10sma` is the headline
label; `mfe10smaPct` is the label used to calibrate the detector, because it measures
whether the setup worked independently of how the trade was managed.

**Recall**:
The share of executed trades the app would have surfaced. Measurable. Its counterpart,
precision, is not — the reference set records no setup he declined, so there is no true
control group and no false-positive rate. Recall is never optimised on its own.

**Replayed field**:
The full candidate list reconstructed for one past session, from a cold-started forward
chain of universe membership. The population an executed trade is ranked against. Always
reported with its coverage against the blind-spot tickers.

**Denominator**:
Every setup the detector named over a replayed window, taken mechanically, whether anyone
traded it or not (PRD #182, `backtest.denominator`). The reference study has the other
half — 828 trades he **took** — which is why it can report no precision and no
false-positive rate. Persisted per session: universe membership, the three regime columns,
the rank table, and every detection with its full `Detection` record, its seven-dimension
star-score breakdown and both candidate dimensions as values. It lives in a store of its
own beside the bar store, because `Store.append_ranks` prunes outside the app's two-year
retention and a fourteen-year denominator would finish holding the last two years of ranks
and nothing else. **Burn-in sessions are persisted and flagged, never measured** — a
warm-up session is a fact about the window, not a hole in it.
_Avoid_: backtest results, the field — the denominator is the *population*, and what any
later phase measures against.

**Regime companions**:
The two columns stored beside the regime state, and never read as its equals. **Breadth is
descriptive only** and carries its survivorship warning in the row itself: it is the
measure survivorship bias corrupts most directly, and worse in a reconstructed past than
live, because the names missing from it are disproportionately the ones that later died.
**Follow-through is unbiased** and the one regime signal the live app can never backfill —
the app captures it forward nightly precisely because a survivorship-biased past cannot
rebuild it, but the index series carries no survivorship hole, so a backtest reconstructs
it legitimately across the whole window.
_Avoid_: conditioning on breadth; it conditions on the **state**.

**Simulated trade**:
One detection from the **denominator**, taken mechanically on one **exit arm** (PRD #182,
`backtest.simulate`). Entry is the detection's own **trigger**, signalled by a close through
it on the session after the detection and filled at the next open; the stop is the
detection's own, unmodified. Every price it carries is stamped with the session that decided
it, so any trade can be audited back to its inputs. A counterfactual, like a **simulated
exit** — but a whole trade rather than an exit bolted onto one he really took, which is the
difference between the denominator and the reference set. A detection whose next session does
not close through its trigger produces **no trade**, and that is a measurement: the share of
detections that trigger is one of the figures the denominator exists to produce.
_Avoid_: backtest trade, mechanical entry — and never **executed trade**, which is observed
fact.

**Exit arm**:
One of three exit rules — A, B and C — run off **one shared entry and one shared stop**, so a
difference between them is attributable to the exit alone. **B is a pure 10MA trail** and the
arm the pre-registered primary metric is computed on; A is the trader's documented behaviour
(50% off at the close of the fifth session after entry, remainder trailed on a 10MA) and C a
pure 20MA trail. B and C are the two directly comparable to the reference set's **simulated
exits**, which is what keeps its anchors usable; **A has no counterpart there, so it is
measured and never anchored**. A trail **signals on a close through the MA and fills at the
next open**, and that mechanic — like "day 5" — is recorded as *arbitrary*, so a later run
varies it deliberately instead of rediscovering it. The trail reads the **unadjusted** close
the trigger and the stop are quoted in, never `indicators.sma`'s adjusted one.
_Avoid_: exit strategy, variant.

**Exit leg**:
One part of a position coming off, carrying **the share of the position it was** (`ExitLeg`).
Arm A takes its position off in two legs, so its R is **position-weighted per leg and
summed** — half a position exiting at +2R contributes **1R**, not 2R and not the average of
the legs. A trade whose legs do not add up to a whole position is still **open** and has no R:
an equity curve built from the legs that happened to close is the same bias as marking an
open trade at the last close, only harder to see, because the trade would look closed.
_Avoid_: partial, tranche; and never call a **scale** an exit — it is a planned partial taken
because the calendar said so, not because the market did anything.

**Price-scale validity**:
The per-trade flag saying whether a **simulated trade**'s absolute-price comparison can be
trusted (`price_scale_ok`). Yahoo applies an *unlabelled* retroactive rescale for rights
issues — measured on BBRI as pre-2021-09-08 OHLC scaled by exactly 10/11, with no split or
dividend row to explain it. **Geometry in ADR units is immune**, because both terms rescale
together, which is why R is denominated by the detection's stop width in ADR priced off the
bars' own ADR. Absolute prices are not immune, and one such comparison is unavoidable: a
trigger persisted earlier against a bar read now. Flagged, never silently dropped, and **the
count it would drop is reported beside every result**.
_Avoid_: adjustment flag, bad data — the trade is not wrong, its scale is unverified.

**Pre-registered metric**:
The one headline the run promised in advance (PRD #182, `backtest.metric`): **arm B's
after-cost expectancy in R, per market per year**. Arm B because it is the reference
set's primary **simulated exit**, which keeps the headline comparable to figures already
committed here. It is computed and recorded **before any swept variant exists**, and every
report carries the count of variants standing behind it — every threshold tried is a test,
and enough of them produce a winner from noise. A trade counts in the year of its **entry
session**, the year the decision was taken, so a trade's year never moves with the exit
rule under test.
_Avoid_: the headline number, our main result — and never quote a swept variant under this
name.

**After-cost expectancy**:
The mean R of the closed **simulated trades** in one cell, net of the contract's own
per-market commission and slippage. Both are bps of the traded price **charged on each
side** — the entry once for the whole position and every **exit leg** weighted by its
share — divided by the trade's stop width, which keeps the cost in R and immune to a
retroactive rescale. IDX carries real fees and spread against US's near-zero; a market the
`costs.per_market` cell does not name is drift, never a free trade. Never reported without
the **win rate and the R-distribution** behind it: 22.7% of his trades made money and his
mean R was positive anyway, so a 20% win rate is not a broken method — a 20% win rate with
a small right tail is. **Never pooled only**: per market, per year, and the
**2020–21-excluded** figure beside the full-window one, because that tape rewarded momentum
nearly everywhere and the window also holds a crash. An **open** trade has no R and is
counted as open, never marked to the last close.
_Avoid_: net expectancy, edge per trade; and never average US and IDX — findings §8
measured that magnitudes do not transfer.

**Clustered bootstrap**:
The run's significance test (`backtest.metric.bootstrap_expectancy`): resample **symbols**
with replacement, pooling every row inside a drawn symbol, and read the interval and the
one-sided p off the resampled means. The cluster is the symbol because overlapping signals
in one name are not independent observations — a stock throwing three signals in a
fortnight contributes three correlated rows — so bootstrapping *rows* makes the effective
sample larger than it is and flatters every p-value. Seeded, and the seed and resample
count ride on every cell, because a significance figure that moved between two runs of the
same data would be unreproducible with nothing in the output to show it.
_Avoid_: bootstrapping the trades, resampling the rows — the row is not the unit.

**Not-taken detection**:
A member of the replayed field on a session where he entered something else. Not a
declined setup — he may never have seen it — so it is a comparison group, never a
negative label.
_Avoid_: rejected setup, negative example.

**Selection contrast**:
The comparison of feature distributions between executed trades and not-taken detections.
Answers which features he selects on. Carries no outcome and is never reported alongside
an outcome regression as though it were predictive.
