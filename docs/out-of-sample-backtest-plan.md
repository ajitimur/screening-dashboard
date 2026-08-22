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

## Phase 0 — Write the run contract

Fix every parameter **before** any code runs, so no threshold is chosen after seeing its
result. Fill this table in and commit it; treat a later change as a new run with a new
contract, recorded beside the old one.

| Parameter | Value | Why this value |
| --- | --- | --- |
| Markets | US, IDX — **reported separately** | Findings §8: shapes travel, magnitudes do not. Pooling them destroys both. |
| Window | 2012-01-01 → latest complete session | |
| Burn-in | 126 sessions before the window (`replay.chain.BURN_IN_SESSIONS`) | Universe hysteresis is path-dependent and needs to settle |
| Setup | Long breakout, EOD only | The reference set's scope; the detector's scope |
| Entry | The detection's own trigger, filled next session | |
| Stop | The detection's own stop | Findings §6 measured this as ~4× the trader's; the backtest prices that gap |
| Exits | 10-day-SMA **and** 20-day-SMA trailing, both reported | Matches the reference set's two simulated exits, so results compare directly |
| Position risk | Fixed fraction of equity per trade | |
| Costs | Per-market commission + slippage | IDX carries real fees and spread; US is near-zero. Assume, state, and sweep. |
| Primary metric | Expectancy in R, after costs, per market per year | One pre-registered metric. Everything else is secondary. |
| Kill criterion | | State in advance what result would make you abandon the method |

**Done when** every row has a value and a one-line justification, committed. An empty cell
at the end of Phase 0 is a threshold that will get chosen to flatter the result.

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
replay. It already replays sessions forward with burn-in, rejects a gapped sequence
(`GapError`), and rebuilds universe → ranks → detections per session through the same modules
the nightly run uses. The work is generalising it past its `REPLAY_MARKET = "US"` and its
2019–2022 window.

Persist, per session: universe membership, the rank table, and every detection with its full
`Detection` record and `star_score` breakdown. **These rows are the denominator** — the object
this whole exercise exists to produce, and the input to every metric in Phase 5.

**Done when** both markets replay end to end with no gap and no session recomputed, burn-in
sessions are persisted but excluded from measurement, and the detection count per session is
plotted across the window. A count that collapses in a given year is a data hole, and reads
as a quiet market until you look.

## Phase 4 — Simulate the trades

One position per symbol at a time. Every price — trigger, fill, stop, trailing exit — derives
from bars at or before the session that decides it.

Two disciplines carry most of the risk here:

- **Prove the point-in-time claim with a test, not with care.** Write one that shifts a future
  bar into an entry decision and asserts the simulated result is unchanged. A look-ahead bug
  produces a beautiful equity curve and no error message.
- **Keep the two price scales apart.** Yahoo's adjusted bars carry an *unlabelled* retroactive
  rescale for rights issues (measured on BBRI: pre-2021-09-08 OHLC scaled by exactly 10/11,
  with no split or dividend row to explain it). Geometry in ADR units is immune, because both
  terms rescale together; absolute prices are not. `prototype-tightness` hit this and carries
  a `price_scale_ok` flag for it — do the same, and report how many trades the flag drops.

**Done when** every simulated trade carries its entry, stop and exit with the session each was
decided on, the shifted-bar test passes, and the trades from the trader's own tickers in the
2019–2022 overlap can be listed beside his real ones.

## Phase 5 — Measure

Report per market, **per year**, and never pooled only. The window contains a crash and a
mania; a pooled fourteen-year number describes neither.

- **The denominator figures** that no prior study could produce: detections per session, the
  share that trigger, and the share that reach a favourable outcome — precision, at last.
- **Expectancy in R** after costs, with the win-rate and R-distribution behind it. The
  reference set's own shape is the comparison: 22.7% of his trades made money, and the mean R
  was positive anyway (§3c). A method with a 20% win rate is not broken; a method with a 20%
  win rate and a small right tail is.
- **Does the rubric rank?** Bucket outcomes by `star_score` decile. §4a found a gap that was
  in-sample by construction (the v2 weights were fitted to that separation) and marginal at
  p = 0.055. This is the out-of-sample test that claim has never had.
- **Does the regime gate pay?** Split by `screener.regime` posture at entry.

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
and an adjusted bar. Keep geometry in ADR units wherever possible.

**Path dependence.** Universe membership moves through stickiness and a hysteretic liquidity
floor, so sessions must run in an unbroken forward sequence. `replay.chain` enforces this
already — keep using it rather than sampling sessions.

**Phantom bars.** Zero-volume rows are removed at ingest, never zero-filled (see `CONTEXT.md`).
A backtest that reintroduces them will trade on days the stock did not trade.

**Recycled tickers** (Phase 2) pass every absence check and still poison a trade: the symbol
resolves, the bars are real, and they belong to a different company. Gate on whether the bar
history covers the session being replayed, which is what findings §2 had to switch to.

**Pooling the markets.** IDX magnitudes are not US magnitudes (findings §8). Report separately
throughout, including in the summary.

**Multiple testing.** Pre-register one primary metric in Phase 0, report the variant count
beside any swept figure, and let the pre-registered number stand as the headline even when a
swept one looks better.

**The 2020–21 tape.** It rewarded momentum nearly everywhere. Report every year separately,
and report the result with 2020–21 excluded beside the full-window figure.

## What this still cannot say

Even run perfectly, this measures **the detector as encoded**, on **free adjusted EOD data**,
over **one fourteen-year sample of two markets**. It cannot say what he would have traded, it
cannot recover intraday behaviour, and it cannot make the delisted names reappear — it can
only bound their absence. Findings §9 remains the model for stating this: a limitation named
in advance is a caveat; one discovered afterwards is a retraction.
