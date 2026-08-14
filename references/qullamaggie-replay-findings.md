# Replaying the Qullamägi trade record — findings

**Study:** the side-car replay of Kristjan Kullamägi's executed-trade record against the
app's funnel, field and rubric (PRD #114).
**Scope:** US, 2019–2022. All long, all breakout, all end-of-day. No IDX.
**Status of the app:** unchanged. This study produces evidence only. No constant in
`detection.py`, `score.py`, `universe.py` or `ranks.py` is touched by it, and none is
touched by this write-up (PRD "Out of Scope"; #114 acceptance).

This document exists so that any constant later changed has a **citable provenance**
(user story 26): each figure below names the analysis and the module that produced it, and
each carries the caveat that bounds it. The caveats are given the same weight as the
results, because the results are not usable without them.

> **How to read the magnitudes.** The reference set
> (`references/trades_bo_gain10smaPct_desc.json`) and the purpose-built `replay.duckdb` are
> the two inputs the magnitudes are computed from. The analysis code (`backend/replay/`) is
> complete and pinned by the row-level seam (`backend/tests/test_replay_seam.py`), and each
> command below reproduces its section's numbers once both inputs are present. Where a
> magnitude is not yet transcribed here it is marked _(pending the built store)_ and the
> command that fills it is given. The **shape** of every finding — what is measured, how it
> is bounded, and which conclusions transfer to IDX — is fixed by the method and is stated
> in full now. The two preliminary #114 findings are direct measurements and stand as
> recorded (see [§6](#6-the-two-preliminary-findings-from-114)).

---

## 1. Method and scope

**The reference set.** 828 real long-breakout entries, 2019-10 to 2022-11, 312 tickers, all
US. Each row is an **observed entry** paired with two **simulated exits** (a 10-day-SMA and
a 20-day-SMA trailing rule, applied after the fact). The entry is real; the exits are
counterfactual, and the study never blurs the two. The primary exit — the one named in the
file — is `10sma`; realised R and R-share are taken over it.

**Evaluation session.** Every funnel stage and every feature vector is computed at the last
market session **strictly before** the trade's entry date, so the test measures whether the
app would have named the stock while the entry was still ahead of the trader (user story 3).
Whether the trade also registered as a break on the entry session itself is kept as a
separate secondary field (`entry_session_break`), so anticipating a trade is never confused
with confirming one after the fact.

**Continuation entries.** A trade within 5 sessions of a prior entry in the same ticker is
_tagged_ `continuation`, not dropped. It stays in every denominator. Every recall is
reported as the headline figure over all replayable trades **and** the ex-continuation
figure together; the ex-continuation figure is never surfaced on its own (user stories 5, 6).

**Seven-dimension replay score.** The rubric's eighth dimension, **Sector**, is dropped
outright: the labels table is the store's one in-place write and carries no history, so a
symbol's 2020 sector is unrecoverable. The replayed score is therefore out of **nine**
weighted points, not ten, and is always labelled a _seven-dimension score_ so it can never
be confused with the app's own. The dimension is dropped, not repaired.

**Reuse of the app.** The universe, ranks, detector, indicators and star rubric are the
app's own functions, unmodified (`screener.universe`, `screener.pipeline`,
`screener.detection`, `screener.indicators`, `screener.score`). The study measures the app
that exists, not a reimplementation of it (user story 31). The replay runs against a
purpose-built DuckDB store; the live store is opened read-only and never written to
(user story 28).

---

## 2. Coverage — the survivorship hole (attach to every field-derived result)

The store is built from today's listing snapshot, so it is missing every name delisted,
acquired or renamed between the session and now. Those blind-spot names are
disproportionately the ones that later died — precisely the population a momentum screener
surfaces. This is the study's largest single caveat and it rides on **every** field-derived
result below as a coverage number (`blind_spot_count`), never absorbed silently into a
stage failure or an absent-from-field verdict.

| Reference-set figure (#114, recomputed each run) | Value |
| --- | --- |
| Total rows (executed entries) | 828 |
| Rows with outcomes | 827 |
| Distinct tickers | 312 |
| Blind-spot tickers | 81 |
| Blind-spot trades | 141 |
| Blind-spot share of total realised R | 11.7% |

These counts are **computed, never hard-coded**; `REFERENCE_FIGURES` records the #114
figures only to detect drift, and `assert_matches_reference` stops the run with a
`DriftError` if the recomputed counts diverge (integers exactly; the R-share within 0.1%).
The sorted **blind-spot ticker list** is committed to `references/` so the size of the hole
is a fixed, citable fact rather than a vague worry (user story 23).

```
python -m replay.reference --store <replay.duckdb> --trades references/trades_bo_gain10smaPct_desc.json
```

---

## 3. A1 — the funnel / recall test

**Question.** Which of the app's three gates throws away the trades it exists to find?

For each replayable trade, evaluated at the session before entry, the funnel walks three
ordered stages — **liquidity → decile → detection** (`FUNNEL_STAGES`) — records pass/fail at
each, and identifies the `first_failing_stage` in funnel order. Each stage is evaluated
independently on every row, so per-stage recall is unconditional and **no single blended
number can hide a catastrophic failure at one stage** (user story 2).

A **detection** failure is attributed to the specific geometric condition that failed
(`failed_condition`), taken in the detector's own gate order: `history`, `adr`,
`prior_move`, `base_length`, `catch_up`, `cluster`. The verdict is always the app's `detect`
unmodified; the walk only attributes a failure the detector already returned. (Line fit —
slope, touches, overshoot — is not a hard gate and never appears as a miss.)

**Absent-from-field is distinguished from outside-the-decile.** A trade whose ticker was not
a universe member at the evaluation session (`decile_present = False`) is a **coverage gap**,
not a ranking verdict, and is kept apart from a ticker that was present but ranked outside
the top decile. The decile depends on the replayed field's population, so every
decile-dependent output carries `blind_spot_count`.

### Per-stage recall — report headline and ex-continuation together

| Stage | Recall (headline) | Recall (ex-continuation) | Notes |
| --- | --- | --- | --- |
| Liquidity | _(pending the built store)_ | _(pending the built store)_ | The one stage where a rejected name never reaches any tab — a miss here is otherwise invisible (user story 7). |
| Decile | _(pending the built store)_ | _(pending the built store)_ | The most aggressive filter — cuts to ~29% of the universe before the detector looks (user story 8). Depends on the replayed field → coverage attached. |
| Detection | _(pending the built store)_ | _(pending the built store)_ | Failures broken down by geometric condition below (user stories 9, 10). |

Detection-failure breakdown (`condition_counts`) — which geometric condition to change:
_(pending the built store; per-condition counts over `history / adr / prior_move / base_length / catch_up / cluster`)._

```
python -m replay.funnel --store <replay.duckdb> --trades references/trades_bo_gain10smaPct_desc.json
```

Blind-spot trades (ticker with no bars) get **no** funnel row — they are recorded as a blind
spot by `replay.reference`, never as a stage failure, so the replayable set and the blind
spot are each quantified rather than one silently absorbing the other (user story 34).

---

## 4. A2 — the full replay: field placement

**Question.** Would the trade have appeared on the part of the star-ranked list the trader
actually reads, and does the star score discriminate his picks from the field?

The field is reconstructed as an **unbroken forward chain** — every session in the window
replayed in order with no gaps, from a cold start with empty prior membership, preceded by
**126 sessions of burn-in** from 2019-04 so the hysteresis band settles before any measured
session (user stories 13, 14). Universe membership is path-dependent through stickiness and
the hysteretic liquidity floor, so a gapped session sequence is rejected by construction
(`GapError`); burn-in sessions are computed and persisted but excluded from the reported
results. Each trade is then placed within its night's field.

### Reported

| Result | Value |
| --- | --- |
| Appeared in the field at all (`in_field`) | _(pending the built store)_ |
| Landed inside the top 30 by star score (`top_thirty`, board size from `screener.boards.BOARD_SIZE`) | _(pending the built store)_ |
| Star distribution of his picks vs the replayed field (histogram, multiples of 0.5) | _(pending the built store)_ |

```
python -m replay.placement --store <replay.duckdb> --trades references/trades_bo_gain10smaPct_desc.json
```

**No percentile and no rank-position figure is emitted anywhere.** The field is missing
roughly a quarter of its names, and those missing names skew toward the ones that later
died. A top-thirty hit and a star-distribution histogram are coarser statements that survive
the missing field; a percentile would look precise while quietly flattering the rubric.

> **A2 rests on the weakest foundation of the three, and no statement here claims the ranking
> is validated.** It ranks each executed trade against a field missing roughly a quarter of
> its names, and that hole is not random — it is concentrated in exactly the population a
> momentum screener surfaces. This was raised and accepted as the price of getting any
> ranking evidence at all. A1 and A3 give strong, directly actionable results about how
> setups are _built_; A2 is the only analysis that speaks to _ranking_, and it speaks softly.
> The star score is also **stop-blind and regime-blind** by construction, so the stop-width
> finding below cannot move ranking at all.

---

## 5. A3 — the feature study (two analyses, kept apart)

The two A3 analyses are separate in code and separate here, because they answer different
questions and must never be reported as though they were the same: the outcome regression
asks whether the rubric **predicts a run**; the selection contrast asks whether the rubric
**encodes his eye** (user story 17).

### 5a. Outcome regression — which dimensions predict a run

Across executed trades only, each of the seven replayable score dimensions (sector absent)
is regressed against **maximum favourable excursion** (MFE) under the 10sma exit. MFE, not
realised R, is the target: most of his trades exited at the stop, so regressing against R
would mostly teach us about stop widths, not about whether the setup ran (user story 15).
The **realised R distribution** is reported alongside as a descriptive statistic only, never
as the target (user story 16).

Each dimension reports its **spread** within the sample next to its correlation
(point-biserial against MFE). A dimension with no spread (or fewer than two points) is
labelled **untestable**, its correlation `None` — a null there is evidence of the trader's
discipline, not of the dimension's uselessness. **"Prior move" is untestable by
construction**: every detection cleared the decile gate, so it never varies within the field.

| Dimension | Weight | Hit rate | Spread | Correlation vs MFE | Untestable |
| --- | --- | --- | --- | --- | --- |
| _(seven dimensions, sector absent — pending the built store; see `DimensionStat`)_ | | | | | |

Descriptive distributions (`Distribution`: n, min, p25, median, p75, max, mean):
realised R, MFE — _(pending the built store)_.

```
python -m replay.regression --store <replay.duckdb> --trades references/trades_bo_gain10smaPct_desc.json
```

### 5b. Selection contrast — which dimensions he selects on

The executed-trade detections (the **taken** group) are contrasted, per dimension, against
the **not-taken** detections — field members present on the nights he traded, in names he
did not enter. **No outcome variable appears anywhere in this analysis**: there is no MFE, no
realised R, no gain. For each dimension the report gives each group's hit rate and spread,
the pooled spread, and the **testability re-check**.

> **The not-taken detections are a comparison group, never a rejection.** _"The not-taken
> detections are a comparison group: field members present on nights he traded, in names he
> did not enter and may never have seen. Their absence from his trade record carries no
> verdict on them."_ No output labels them declined, rejected or negative (user story 25).

> **Precision is not measurable.** _"Precision is not measurable: the reference set records
> only the trades he entered, never a setup he passed over, so there is no control group and
> no false-positive rate is claimed. This comparison group is the nearest honest substitute,
> and no precision is asserted."_ (user story 24).

**Testability restored.** A dimension flat within his trades alone — the same untestable
label the regression uses — but with spread across the pooled taken+not-taken sample is
flagged `testability_restored`. This is the range-restriction repair the not-taken
detections buy back: variance the executed trades lack (user story 19).

| Dimension | Weight | Taken hit rate | Not-taken hit rate | Untestable within executed | Testability restored |
| --- | --- | --- | --- | --- | --- |
| _(seven dimensions, sector absent — pending the built store; see `DimensionContrast`)_ | | | | | |

```
python -m replay.contrast --store <replay.duckdb> --trades references/trades_bo_gain10smaPct_desc.json
```

---

## 6. The two preliminary findings from #114

Both are direct measurements over the reference set and its entry-session bars — they do not
depend on the A2 chain. The replay reconstructs each as a full **distribution** so the
headline figures can be confirmed or refuted against the whole entry set, not just re-quoted.

### Finding 1 — the detector's proposed stop is roughly four times wider than the trader's own. **Confirmed (preliminary).**

| | Median stop width | At or under 1.0 ADR |
| --- | --- | --- |
| Live US detections (the app proposes) | 1.28 ADR | 14.2% |
| Kullamägi's executed trades (what he uses) | 0.34 ADR | 98.1% |

The stop the detector proposes is ~4× the stop the trader actually uses. This makes the
affordability affordance on the Board and Setups cards nearly dead — not because candidates
are unaffordable, but because the stop convention is wrong. The replay reconstructs his side
as `stop_width_adr_distribution` (his stop as a multiple of the night's ADR, over every
replayable trade) with `share_le(1.0)` for the at-or-under-1.0 figure; the final
distribution over the built store either holds or moves the median 0.34 / 98.1% figures.
_(Distribution over the built store: pending.)_

> This is the strongest preliminary finding, and it is worth stating what it can and cannot
> do. The star score is stop-blind by construction, so the gap **cannot move ranking at
> all**. It changes what the detector proposes and what a card claims about risk, and nothing
> else.

### Finding 2 — the ADR floor withholds its score point on 31% of his real entries. **Confirmed (preliminary).**

`ADR_MIN = 0.05` withholds its score point on **31%** of his real entries; his ADR at entry
runs **4.58% at the 25th percentile** against the 5% floor. The replay reconstructs the ADR
at entry as `adr_distribution` over every replayable trade; the share below the 5% floor
either holds or moves the 31% figure. _(Distribution over the built store: pending.)_

---

## 7. Caveats — carried with the same weight as the results

- **Survivorship coverage.** Everything derived from the field is read against a store
  missing ~a quarter of the names, skewed toward names that later died. Every field-derived
  result carries `blind_spot_count`; the 81-ticker / 141-trade / 11.7%-of-R hole is quantified
  in [§2](#2-coverage--the-survivorship-hole-attach-to-every-field-derived-result) and the
  ticker list is committed.
- **Range restriction (A3).** Every trade in the sample already passed the trader's eye, so
  the dimensions he applies most consistently show the least variance and correlate with
  nothing. A null on such a dimension is evidence of his discipline, not the dimension's
  uselessness — hence the spread column and the **untestable** label, and the selection
  contrast that partly buys the variance back.
- **Precision is not measurable, and recall must never be optimised on its own.** The
  reference set records no setup he declined, so there is no control group and no
  false-positive rate. Widening every gate to chase a recall number is exactly the trap the
  missing precision leaves open.
- **Cold-start divergence.** A cold-started chain differs from the true 2019–22 chain for
  names sitting in the hysteresis band; 126 burn-in sessions settle the band before the first
  measured session, but the divergence for band names is real and is recorded, not engineered
  away. Absolute price levels are split-adjusted and will not match a 2020 broker screen —
  though the detector's geometry is scale-invariant and dollar volume replays correctly.
- **Scope.** US, 2019–2022, with roughly **85% of entries from 2020–21** — a once-in-a-decade
  US momentum regime.

### The calibration rule

A gate may be loosened on the strength of an A1 recall miss **only when A3 shows that
dimension has no signal _and_ that dimension shows real spread.** This is the guard against
the one-sided recall metric: because precision is not measurable, recall is never optimised
on its own, and a dimension is never widened away on a null that is really range restriction.

---

## 8. What transfers to IDX

**The shape of the findings is a property of the method and travels. The magnitudes are a
property of a once-in-a-decade US momentum regime and do not.** Carry the structural lessons
to IDX — which gate is costing entries, that stop convention is measured against the trader's
own risk rather than assumed, that a dimension's null must be read against its spread — and
carry none of the figures. No number from this study is to be presented as an IDX
expectation; the reference set contains no IDX trade.

## 9. What the study cannot say

- It cannot claim the **ranking** is validated. A2 rests on the weakest foundation of the
  three, and no statement in this write-up may be read as ranking validation.
- It cannot report a **precision** or **false-positive** rate. There is no control group.
- It cannot speak to **Episodic Pivot** or **Parabolic Short** setups, to **intraday**
  entries, or to any name in the **blind-spot** list. The reference set is entirely US
  end-of-day breakouts, and the blind-spot hole is measured and documented, not filled.

---

_Provenance: PRD #114; A1 funnel #116/#119; A2 chain/field/placement #117/#118/#120; A3
outcome regression #121; A3 selection contrast #122; this write-up #123. Analysis code:
`backend/replay/`. Row-level seam: `backend/tests/test_replay_seam.py`._
