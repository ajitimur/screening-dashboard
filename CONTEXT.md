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
Membership is sticky: removal requires positive evidence.
_Avoid_: watchlist, screen.

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
Top 10% of a lookback's own population. The gate is the union of the five deciles
(~29% of the universe, not 10%).

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
The largest trailing 3–7 bar window spanning at most 1.5 × ADR. The tight end of the base.

**Cluster length `k`**:
Bars in the cluster. The double-weighted tightness dimension of the star score.

**Envelope**:
The upper trendline — anchored at the cluster's max high, fitted backwards over the base's
highs with non-positive slope only.

**`line_ok`**:
Whether the envelope is a good fit (touch zones and bounded overshoot). Not a gate — a
silent tiebreak.

**Trigger**:
`cluster_high`, by identity — the envelope is anchored at the cluster's max high and can
never exceed it.

**Detection**:
A name with a valid base, cluster and MA catch-up, inside the decile gate, on a session.
A dated row.

**Break**:
An event, not a state: today's close above yesterday's trigger. Equivalently, today's
close is above the last `k` sessions' high.

**Star score**:
The rubric — 8 dimensions, 9 weighted points, halved to stars. The sort key of the only list
in the app. Its range is 0.5–4.5, never 0–5: one dimension always fires and one is weighted
zero. Derived on read everywhere except a digest, which freezes the value it was written with.

**Calibration target**:
What the rubric is fitted to encode — the method's revealed selection, evidenced by the
executed trades. Neither our own grading (a superseded proxy) nor outcome (measured, null).
_Avoid_: ground truth, benchmark.

**Constant dimension**:
A score dimension true for every detection by construction, so it shifts every score equally
and can never move the sort. `Prior move` is one, and is kept for what it documents, not for
what it discriminates.

**Rubric version**:
The stamp identifying which weights and thresholds produced a star score. A star figure quoted
without one cannot be compared to another.

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
An executed trade whose ticker has bars in the replay store. 658 of 828. Its complement is
the blind spot, never a funnel-stage failure — a trade the store cannot see was never
offered to a gate.

**Blind-spot ticker**:
A ticker in the reference set the replay store holds no usable bars for, so no trade of its
can be evaluated at all. 91 of 312 tickers, 170 trades, 18.1% of total R — the measured size
of the store's survivorship hole. Measured **in the replay window**, not over all history:
the operative question is whether the trade can be replayed, which is stricter than whether
the provider still answers to the symbol.
_Avoid_: missing ticker, delisted (delisting is one cause of a blind spot, not the term for
it — see **Recycled symbol** for the other).

**Recycled symbol**:
A ticker whose bars belong to a *different* listing than the trade paired with it, because
the symbol was reassigned after the original company left the market. The other half of
survivorship, and the dangerous half: a delisted name is **absent** and fails loudly, while
a recycled one is **silent** — it resolves, it has bars, and replaying against them would
score one company's trade on another company's price history. Ten are known in the reference
set (APXT, BNKU, EYES, FNGU, LAC, LAZR, NRGU, SI, SPWR, USLV). Caught by a window check —
does the ticker have bars covering this trade's entry? — never by a fetch.
_Avoid_: renamed, reused ticker. A rename carries one company's history forward under a new
symbol; recycling puts a different company under an old one.

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

**Not-taken detection**:
A member of the replayed field on a session where he entered something else. Not a
declined setup — he may never have seen it — so it is a comparison group, never a
negative label.
_Avoid_: rejected setup, negative example.

**Selection contrast**:
The comparison of feature distributions between executed trades and not-taken detections.
Answers which features he selects on. Carries no outcome and is never reported alongside
an outcome regression as though it were predictive.
