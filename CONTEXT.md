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
Top 10% of a lookback's own population. The union of all five lookbacks' deciles is the
breadth substrate — 27.2% of the universe, not 10%. It is not the gate the detector runs;
see **Detection gate**.

**Detection gate**:
The union of the top deciles of the *three* detection lookbacks (`1m`, `3m`, `6m`) — 19.4%
of the universe. The cut a name must clear before the detector is consulted. Distinct from
the five-lookback union, and materially tighter; conflating the two misattributes the
gate's cost.

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
Whether a name *has* a cluster is settled entirely by its 3-bar range: range is monotone in
the window length, so the 3-bar window is the tightest one there is. The 7 is a scoring
bound, not a gate.

**Cluster length `k`**:
Bars in the cluster. The double-weighted tightness dimension of the star score, and the only
thing the upper bound of 7 can move.

**3-bar range**:
A name's trailing 3-bar high-to-low span, in ADR. The tightest window the cluster scan can
find, and so the number the cluster gate actually tests. Reported as `range_3bar_adr` on a
cluster miss, to say by how much it missed.

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
A name with a valid base, cluster and MA catch-up, inside the detection gate, on a session.
A dated row.

**Break**:
An event, not a state: today's close above yesterday's trigger. Equivalently, today's
close is above the last `k` sessions' high.

**Star score**:
The rubric — 8 dimensions, 9 weighted points, halved to stars. The sort key of the only list
in the app. Its range is 0.5–4.5, never 0–5: one dimension always fires (`Prior move`) and one
is weighted zero (`Base length`). Derived on read everywhere except a digest, which freezes the
value it was written with. Recalibrated to the method's revealed selection by PRD #138:
`Tightness` and `ADR` weigh ×2 (the two sharpest §5b selectors), `Base length` ×0 (its largest
wrong-way gap), everything else ×1. Weights come from the *ordering* of the measured selection
gaps, never their magnitude. The three-weight ordinal swap inside that recalibration — `ADR`
×1→×2, `Orderliness` ×2→×1, `Base length` ×1→×0 — is ticketed as #135.

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
and can never move the sort. `Prior move` is one, and is kept for what it documents, not for
what it discriminates.

**Rubric version**:
The stamp identifying which weights and thresholds produced a star score (`score.RUBRIC_VERSION`,
currently 2 — the PRD #138 nine-point rubric; v1 was the ten-point one). Rides the API candidates
payload and the digest header. A star figure quoted without one cannot be compared to another.

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

**Not-taken detection**:
A member of the replayed field on a session where he entered something else. Not a
declined setup — he may never have seen it — so it is a comparison group, never a
negative label.
_Avoid_: rejected setup, negative example.

**Selection contrast**:
The comparison of feature distributions between executed trades and not-taken detections.
Answers which features he selects on. Carries no outcome and is never reported alongside
an outcome regression as though it were predictive.
