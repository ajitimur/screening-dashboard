# Out-of-sample backtest — US and IDX, 2012 onward

**Status: plan. Nothing here has been run.** Every figure this produces will be new; the
figures it must *reproduce* are named in [Phase 6](#phase-6--anchor-before-believing).

## The question

[`references/qullamaggie-replay-findings.md`](../references/qullamaggie-replay-findings.md)
measures one trader's 828 executed entries. Every result there is conditioned on trades he
**took**, which is why §9 says the study cannot report a precision or false-positive rate.
It has a numerator and no **denominator**.

This backtest builds the denominator: **every setup the detector names, taken mechanically,
across two markets and fourteen years.** It answers what the replay cannot — does the
*method* have an edge, or did the *trader*?

Three outcomes are all worth having, and the plan commits to publishing whichever lands:

| If | Then |
| --- | --- |
| The mechanical rules are profitable out of sample | The app is screening for something real |
| They are flat, but his selection beat them | His edge is discretionary, and the rubric's job is to *rank*, not to *decide* |
| They lose across both markets and every regime | The detector encodes a pattern that does not pay, and §4a's ranking claim must be revised |

## Three rules that make the result worth reading

Everything below serves these. A run that breaks one produces a number that cannot be cited.

1. **Point-in-time.** Every value that enters a decision is computed from bars at or before
   that decision's session. This is what the replay's evaluation-session convention already
   enforces (findings §1); the backtest extends it to entries, stops and exits.
2. **Survivorship is measured, not mentioned.** The bar store holds names that still resolve
   today. A 2012 backtest on today's tickers is a study of winners. [Phase 2](#phase-2--bound-the-survivorship-hole)
   makes the size of that hole a computed number and carries it into every result.
3. **Anchor before believing.** The run must reproduce figures already committed to this repo
   before any new figure from it is read ([Phase 6](#phase-6--anchor-before-believing)).

---

# Phase 0 — The run contract

Fixed **before** any code runs, so no threshold is chosen after seeing its result. A later
change is a new run with a new contract, recorded beside this one.

## Scope

| Parameter | Value | Why |
| --- | --- | --- |
| Markets | US, IDX — **reported separately** | Findings §8: shapes travel, magnitudes do not |
| Measured window | 2012-01-01 → latest complete session | |
| Store window | **2011-01-01** → latest | Warm-up for a 2012 start: `detection.MIN_HISTORY` (80 bars), the SMA50/ADR20 universe gates, and `regime.REGIME_WARMUP` (25 index bars). The app's regime fits nothing, so no burn-in beyond its own warm-up is owed. |
| Setup | Long breakout, EOD only | The reference set's scope, and the detector's |
| Study level | **Signal-level primary; portfolio-level deferred** | [Below](#study-level) |

## Screening universe

Three gates, plus one market-specific trim. **All measured through t−1**, so a signal on
session *t* uses only what was knowable the night before.

| Gate | US | IDX |
| --- | --- | --- |
| Trend | close > SMA50 | close > SMA50 |
| Liquidity (ADTV) | ≥ **$10M** | ≥ **Rp 10B** |
| Volatility | ADR20 ≥ **3.5%** | ADR20 ≥ **3.5%** |
| Data-validity trim | — | nominal price ≥ **Rp 100**, split-corrected |

**The Rp 100 trim is data validity, not cost control.** Below it, IDX quotes hit the tick
grid hard enough that ADR and range geometry stop meaning what they mean elsewhere. State it
that way in the write-up so nobody reads it as a penny-stock filter with an implied cost
story. Apply it on the same split-corrected series every other figure uses, and hold that
choice consistent — Yahoo's unlabelled rights-issue rescaling (see
[Traps](#traps)) makes "nominal price" ambiguous otherwise.

**ADTV is the 20-day median of unadjusted close × volume**, reusing
`universe.median_dollar_volume`, so one block trade cannot lift an illiquid name over the
floor. Flip it to a mean only deliberately — it changes which spiky small caps qualify.

Three consequences, each of which will otherwise get misread later:

- **This universe is stateless, and the app's is not.** `universe.py` carries a hysteresis
  band (`HYSTERESIS_EXIT`) so members leave at a lower floor than they enter. A hard daily
  threshold reintroduces boundary churn: a name oscillating around $10M enters and leaves
  day by day. **At signal level this is nearly free** — each signal is evaluated on its own
  session and churn costs nothing. It becomes real at portfolio level, so record it as a
  known difference rather than fixing it now.
- **ADR20 ≥ 3.5% sits deliberately below the rubric's `score.ADR_MIN` of 5%.** That gap is
  the point: findings §6 Finding 2 measured the 5% floor silently withholding a score point
  from 31% of his real entries, so a universe cut at 5% would leave the ADR dimension with no
  spread left to test. Keep the looser floor and let the scorer's floor be measured.
- **The 50MA gate overlaps the detector's own trend logic.** Detection counts will fall
  against an unfiltered run. That is the gate working, not the detector becoming more
  selective — say so when reporting counts, or the two effects get conflated.

## Regime

**Use the app's regime — [`screener.regime`](../backend/screener/regime.py) as it stands.**
A conditioning variable, never a filter: nothing is excluded by regime, and every result is
*reported* by state.

| | Definition |
| --- | --- |
| State | `regime_state(index_bars)` → `FRIENDLY` / `CHOPPY` / `HOSTILE`, or undefined below `REGIME_WARMUP` (25 index bars) |
| Read on | The market's own index — `^IXIC` (US), `^JKSE` (IDX), per `source.MARKET_INDEX` |
| Evaluated at | t−1, like every other input |
| Reported beside it | `breadth()` and follow-through, both descriptive |

**Why this is the right call.** The app's regime has **zero tunable parameters** — two SMAs
and a sign-only slope, no thresholds fitted to anything. That buys three things at once: no
percentile machinery to build, no burn-in beyond 25 index bars, and no risk of fitting a
regime scale to the same window whose results it will condition. It also means the backtest
conditions on **the state the app actually shows**, so a finding here is directly actionable
in the product rather than being about a parallel definition that ships nowhere.

Three states rather than nine cells also keeps the cells populated. **Report n per state**
regardless.

**Price the posture.** `HOSTILE` advises "sit out" and `CHOPPY` advises "reduced" — words the
app prints today on no measured basis. This backtest can price that advice directly: what
expectancy did signals taken in each state actually deliver? That is the single most
product-relevant number in the whole run.

**Two companions, reported and kept in their place:**

- **Breadth is descriptive only, and carries its own warning.** `regime.breadth()` is the
  measure survivorship bias corrupts most directly — its own docstring says so, which is why
  the app displays it and gates nothing on it. In a backtest the corruption is worse, not
  better, because the missing names are disproportionately the ones that later died. Report
  it; condition on the state, not on breadth. Phase 2's bound applies to this column with
  full force.
- **Follow-through is reconstructable here, and only here.** `index_broke_out` is captured
  forward nightly because the app cannot rebuild it from a survivorship-biased past. **The
  index series carries no survivorship hole**, so this backtest *can* reconstruct it
  legitimately across fourteen years — the one regime signal the live app can never backfill.
  Compute it, report it, and say plainly that it is unbiased where breadth is not.

## Entry, stop, exits

| | Value |
| --- | --- |
| Entry | The detection's own trigger, filled next session |
| Stop | The detection's own stop |
| Exits | **Three arms**, identical entry and stop |

| Arm | Rule |
| --- | --- |
| **A** | 50% off at day 5, remainder on a 10MA trail |
| **B** | Pure 10MA trail |
| **C** | Pure 20MA trail |

Because the arms share an entry and a stop, any difference between them is attributable to
the exit alone — which is the only reason to run three.

- **Arm A is the trader's documented behaviour**, and it is the one with no counterpart in
  the reference set. **Arms B and C are directly comparable** to the reference set's two
  simulated exits (findings §1), which is what keeps [Phase 6](#phase-6--anchor-before-believing)'s
  anchors usable.
- **Arm A's R is two-legged**: position-weight each leg and sum. Half a position exiting at
  +2R contributes 1R.
- **Specify the mechanics as contract, not as code comments**: "day 5" is the close of the
  fifth session after entry; a trail signals on a close through the MA and fills at the next
  open. Both choices are point-in-time and both are arbitrary — record them so a later run
  can vary them deliberately.

## Study level

**Signal-level is primary.** Every qualifying signal is taken independently, equal-weighted,
denominated in R. No capital constraint, no concurrency cap, no position limit. This measures
**the signal**, which is the open question.

**Portfolio-level is specified now and deferred**: capital, a concurrency cap, sizing,
correlation clustering, and the drawdown path. Specified now so the signal-level work records
what it will need.

Two consequences to carry:

- **Signal-level cannot speak to capacity, concurrency, drawdown path, or correlated
  clustering.** In a momentum method the winners arrive together, so the portfolio question is
  not a detail — it is deferred, not dismissed.
- **Overlapping signals in one name are not independent observations.** A stock throwing three
  signals in a fortnight contributes three correlated rows. When testing significance, bootstrap
  **clustered by symbol** rather than by row; otherwise the effective sample is smaller than the
  row count and every p-value is flattering.

## Costs, metric, and the kill line

| Parameter | Value | Why |
| --- | --- | --- |
| Costs | Per-market commission + slippage, swept | IDX carries real fees and spread; US is near-zero |
| Primary metric | Expectancy in R, after costs, per market per year, **arm B** | One pre-registered metric. Arm B is the reference set's primary exit, so the headline stays comparable. |
| Kill criterion | | State in advance what result would make you abandon the method |

**Done when** every cell above has a value and a one-line justification, committed. The kill
criterion is the one still blank, and it is the one that matters most: fill it before Phase 1.

---

## Phase 1 — Build the bar store

Extend the pattern in [`backend/replay/store.py`](../backend/replay/store.py): a purpose-built
DuckDB file, the live store opened read-only, never written. Fetch through
`screener.source` (Yahoo via `yfinance`, `.JK` suffixes for IDX — see
[`.scratch/screening-dashboard/research/01-idx-data-sources.md`](../.scratch/screening-dashboard/research/01-idx-data-sources.md)).

Pace the fetch. The sustained rate limit recovers in roughly a minute of rest, so a paced
crawl finishes and a burst stalls.

**Done when** every enumerated symbol has either bars in the store or a row naming why it has
none, the two counts sum to the enumeration, and both are committed. A symbol that is
silently absent is survivorship bias entering through the back door.

## Phase 2 — Bound the survivorship hole

Treat this as a measurement with its own deliverable, ahead of any performance number.

**The floor is already known.** Findings §2 measured it over a four-year window: **91 of 312
tickers (29.2%)** and **170 of 828 trades (20.5%)** absent from the store, carrying **18.1% of
the trader's realised R** — names delisted, acquired or renamed inside four years. A 2012 start
reaches further back, so expect worse. For IDX the research note measured the same hole from
the other side: the Yahoo screener enumerates ~840 names against IDX's ~963 listed, and the
missing ones are the suspended and delisted.

**And the hole has a silent half.** §2's correction is the part to carry: ten of those tickers
*resolve today* but their bar history begins years after the entry they are paired with,
because the symbol was recycled onto an unrelated listing. Survivorship here is delisting
**plus ticker recycling**, and recycled names are absent from no list — they arrive as
plausible bars for the wrong company.

Two deliverables:

1. **A count.** How many names traded in the window and are absent from today's enumeration,
   with dates. Reconstruct the listing spine from a free source and name which one you used;
   candidates worth testing are exchange delisting notices and index-constituent change
   histories. Verify the source covers your window before depending on it.
2. **A sensitivity.** Re-run the headline metric with the missing population assigned a
   pessimistic outcome. The gap between the two numbers is the bias bound, and it travels with
   every result as one line.

**Done when** both the count and the bound are computed, and the write-up states the headline
figure *and* its pessimistic twin together.

## Phase 3 — Replay the field, point-in-time

Reuse [`backend/replay/chain.py`](../backend/replay/chain.py) rather than writing a second
replay. It already replays sessions forward with burn-in and rebuilds universe → ranks →
detections per session through the same modules the nightly run uses. The work is generalising
it past its `REPLAY_MARKET = "US"` and its 2019–2022 window, and swapping the app's universe
for the contract's.

Persist, per session: universe membership, the regime state with its breadth and
follow-through companions, the rank table, and every detection with its full `Detection`
record and `star_score` breakdown. **These rows are the denominator** — the object this whole
exercise exists to produce, and the input to every metric in Phase 5.

The contract's universe is stateless and the app's regime reads only the index, so sessions
no longer depend on each other. Run them forward in an unbroken sequence anyway, and let a
gap fail loudly: a missing session is a data hole, and a backtest that quietly skips it
reports on a market that took the day off.

**Done when** both markets replay end to end with no gap and no session recomputed, burn-in
sessions are persisted but excluded from measurement, and detections per session are plotted
across the window. A count that collapses in a given year is a data hole, and reads as a quiet
market until you look.

## Phase 4 — Simulate the trades

Every price — trigger, fill, stop, trail, day-5 scale-out — derives from bars at or before the
session that decides it. All three exit arms run off one entry and one stop, so a trade
appears once per arm and the arms stay comparable.

Two disciplines carry most of the risk here:

- **Prove the point-in-time claim with a test, not with care.** Write one that shifts a future
  bar into an entry decision and asserts the simulated result is unchanged. A look-ahead bug
  produces a beautiful equity curve and no error message.
- **Keep the two price scales apart.** Yahoo's adjusted bars carry an *unlabelled* retroactive
  rescale for rights issues (measured on BBRI: pre-2021-09-08 OHLC scaled by exactly 10/11,
  with no split or dividend row to explain it). Geometry in ADR units is immune, because both
  terms rescale together; absolute prices are not — including the Rp 100 trim.
  `prototype-tightness` hit this and carries a `price_scale_ok` flag for it; do the same, and
  report how many trades the flag drops.

**Done when** every simulated trade carries its entry, stop and per-arm exit with the session
each was decided on, the shifted-bar test passes, and the trades from the trader's own tickers
in the 2019–2022 overlap can be listed beside his real ones.

## Phase 5 — Measure

Report per market, **per year**, and by regime cell — never pooled only. The window contains a
crash and a mania; a pooled fourteen-year number describes neither.

- **The denominator figures** that no prior study could produce: detections per session, the
  share that trigger, and the share that reach a favourable outcome — precision, at last.
- **Expectancy in R** after costs, with the win rate and R-distribution behind it, for each of
  the three arms. The reference set's own shape is the comparison: 22.7% of his trades made
  money and the mean R was positive anyway (§3c). A method with a 20% win rate is not broken;
  a method with a 20% win rate and a small right tail is.
- **What the third arm buys.** Arm A trades tail for hit rate by construction. Report whether
  it raises expectancy or merely smooths it — those are different results and only one of them
  is a reason to adopt it.
- **Does the rubric rank?** Bucket outcomes by `star_score` decile. §4a found a gap that was
  in-sample by construction (the v2 weights were fitted to that separation) and marginal at
  p = 0.055. This is the out-of-sample test that claim has never had.
- **Does the app's regime condition the edge?** Expectancy per state, per market, with n
  shown — and the counterfactual the product actually needs: what sitting out `HOSTILE` would
  have cost or saved, and whether `CHOPPY` earns its "reduced". This is the payoff of treating
  regime as a conditioning variable rather than a filter: every state gets to trade, so each
  one's expectancy is measured instead of assumed.

Sweep thresholds only after the pre-registered metric is computed and recorded, and report the
count of variants tried beside any swept result. Every threshold tried is a test, and enough
of them will produce a winner from noise.

## Phase 6 — Anchor before believing

The run overlaps ground already measured. Reproduce it, or explain the divergence in writing,
before reading any new figure:

| Anchor | Committed value | Source |
| --- | --- | --- |
| Median trailing 3-bar range at his entries | **1.31 ADR** | Findings §3b |
| Median trailing 5-bar range at his entries | **1.86 ADR** | Findings §3b, §3c |
| Median 20-day ADR at entry eve | **6.08%** | Findings §3c |
| Blind-spot tickers / trades, 2019–2022 | **91 / 170** (of 312 / 828) | Findings §2 |
| Trades detected by the funnel | **104 of 658 replayable** | Findings §4 |

These are the same reference set through a differently-built pipeline. Matching them says the
new pipeline computes what the old one computed; a mismatch is a bug in the new store or the
new chain, and every downstream number inherits it.

Anchor against **arms B and C**, whose exits match the reference set's two simulated ones.
Arm A has no counterpart there and is measured, never anchored.

**Done when** each anchor matches its committed value or its divergence is written up with a
cause.

## Phase 7 — Write it up

Follow the convention the study already set: an authority document under `references/`, a
plain-language companion beside it, the machine-readable results committed next to both, and
one command that reproduces the run. Carry the caveats with the same weight as the results —
findings §7 is the model.

State the bias bound from Phase 2 in the summary, not in a footnote.

**Done when** a reader who has seen none of this can reproduce the headline figure from the
committed command, and can state its bound without reading the code.

---

## Traps

Each has already cost this repo time, or is guaranteed to.

**The equity curve that is a bug.** Look-ahead never announces itself. The shifted-bar test in
Phase 4 is the cheapest insurance in this plan.

**Rights-issue rescaling** (Phase 4) silently breaks any comparison between a recorded price
and an adjusted bar, and makes IDX's Rp 100 trim ambiguous. Keep geometry in ADR units
wherever possible.

**Recycled tickers** (Phase 2) pass every absence check and still poison a trade: the symbol
resolves, the bars are real, and they belong to a different company. Gate on whether the bar
history covers the session being replayed, which is what findings §2 had to switch to.

**Phantom bars.** Zero-volume rows are removed at ingest, never zero-filled (see `CONTEXT.md`).
A backtest that reintroduces them will trade on days the stock did not trade.

**Breadth is the corrupted column.** Survivorship hits it harder than anything else reported
here, because the names missing from the store are disproportionately the ones that later
died. Condition on the regime *state*, which reads only the index, and let breadth stay
descriptive.

**Row-counting the significance.** Overlapping signals in one name are correlated; bootstrap
clustered by symbol.

**Pooling the markets.** IDX magnitudes are not US magnitudes (findings §8). Report separately
throughout, including in the summary.

**Multiple testing.** Pre-register one primary metric in Phase 0, report the variant count
beside any swept figure, and let the pre-registered number stand as the headline even when a
swept one looks better. Three exit arms and three regime states is nine views of one dataset
before any threshold is swept.

**The 2020–21 tape.** It rewarded momentum nearly everywhere. Report every year separately,
and report the result with 2020–21 excluded beside the full-window figure.

## What this still cannot say

Even run perfectly, this measures **the detector as encoded**, on **free adjusted EOD data**,
over **one fourteen-year sample of two markets**, at **signal level**. It cannot say what he
would have traded, it cannot recover intraday behaviour, it cannot speak to capacity or
drawdown until the portfolio level is built, and it cannot make the delisted names reappear —
it can only bound their absence. Findings §9 remains the model for stating this: a limitation
named in advance is a caveat; one discovered afterwards is a retraction.
