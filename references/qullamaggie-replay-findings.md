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

> **Every magnitude below is measured.** The study was run end to end on 2026-08-15
> against a `replay.duckdb` built from the live store (5,892,590 US bars, 7,529 tickers,
> 2019-04-01..2022-12-31) and the committed reference set
> (`references/trades_bo_gain10smaPct_desc.json`). The chain replayed all 947 sessions —
> 126 burn-in, 821 measured — in one forward pass, and all four analyses were computed
> against that single chain. Run time 29.8 minutes. Nothing here is projected or
> extrapolated; where a number is absent it is because the measurement is *impossible*
> (§9), not pending.
>
> **How to reproduce it.** See [§10](#10-reproducing-the-study). Build the store once, then
> run `python -m replay.study` against it: one command builds the field once and computes
> coverage plus all four analyses against it, writing both the reports and a machine-readable
> results file and printing progress with an ETA (#131). The four analyses also keep their
> own per-study commands, runnable in any order against the built store — the chain reuses
> the sessions the first run persisted, so no run poisons the next (#126).

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
| Blind-spot tickers | **91** |
| Blind-spot trades | **170** |
| Blind-spot share of total realised R | **18.1%** |

> **The hole is larger than #114 first measured**, and the correction matters. The
> original 81 / 141 / 11.7% asked whether the provider returns the symbol *at all today*.
> The study actually needs a stricter question — does the ticker have bars **in the replay
> window** (`2019-04..2022-12`), which is the only condition under which the funnel or the
> field can say anything about the trade. The two differ by 10 tickers / 29 trades, and
> every one of those is a **symbol-reuse** case: APXT, BNKU, EYES, FNGU, LAC, LAZR, NRGU,
> SI, SPWR, USLV all resolve today, but their bar history begins years *after* the entry
> they are paired with, because the ticker was recycled onto an unrelated listing. Counting
> them replayable would not merely understate the hole — at any window overlap it would
> replay one company's trade against another company's bars. So survivorship here is not
> only delisting; it is delisting **plus ticker recycling**, and the recycled names are
> silent rather than absent.

These counts are **computed, never hard-coded**; `REFERENCE_FIGURES` records the pinned
figures only to detect drift, and `assert_matches_reference` stops the run with a
`DriftError` if the recomputed counts diverge (integers exactly; the R-share within 0.1%).
The sorted **blind-spot ticker list** is committed at
`references/blind_spot_tickers.json` so the size of the hole is a fixed, citable fact
rather than a vague worry (user story 23).

```
python -m replay.reference --store data/replay.duckdb
# --reference defaults to references/trades_bo_gain10smaPct_desc.json
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

**658 replayable trades** (of 828; the other 170 are the blind spot), of which **80** are
tagged `continuation`.

| Stage | Recall (headline) | Recall (ex-continuation) | Notes |
| --- | --- | --- | --- |
| Liquidity | **598/658 (90.9%)** | **523/578 (90.5%)** | The one stage where a rejected name never reaches any tab — a miss here is otherwise invisible (user story 7). Cheapest of the three. |
| Decile | **395/658 (60.0%)** | **340/578 (58.8%)** | The most aggressive filter — cuts to ~29% of the universe before the detector looks (user story 8). Depends on the replayed field → coverage attached. |
| Detection | **380/658 (57.8%)** | **341/578 (59.0%)** | Failures broken down by geometric condition below (user stories 9, 10). |

> **The decile gate is the expensive one.** It discards **40% of his real entries on its
> own**, before the detector is ever consulted — the largest single loss in the funnel, and
> nearly five times the liquidity stage's. Each stage is evaluated *unconditionally* on
> every row, so these are not sequential survivors: decile (60.0%) and detection (57.8%)
> are close because they are two independent measurements, not a funnel product.
>
> Detection is also the **only** stage whose ex-continuation recall (59.0%) is *higher*
> than its headline (57.8%). His repeat entries into a name are harder for the detector to
> see than his first ones — consistent with the `cluster` condition below, which fires on
> exactly that pattern.

Detection-failure breakdown (`condition_counts`) — which geometric condition to change:

| Failed condition | Count | Share of the 278 detection misses |
| --- | --- | --- |
| `cluster` | **171** | 61.5% |
| `catch_up` | 47 | 16.9% |
| `base_length` | 37 | 13.3% |
| `history` | 23 | 8.3% |
| `adr` | 0 | — |
| `prior_move` | 0 | — |

`cluster` alone costs more than the other three firing conditions combined. Neither `adr`
nor `prior_move` rejected a single one of his entries: `prior_move` cannot (every detection
clears the decile gate by construction), and the ADR *hard gate* never bound — which is
distinct from the ADR *score point*, which is withheld on 30.7% of entries (§6, finding 2).

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
| Appeared in the field at all (`in_field`) | **104/658 (15.8%)** |
| Landed inside the top 30 by star score (`top_thirty`, board size from `screener.boards.BOARD_SIZE`) | **41/658 (6.2%)** |

Star distribution of his picks against the replayed field, on the same sessions:

| Stars | His picks | Share | The field | Share |
| --- | --- | --- | --- | --- |
| 4.5 | 4 | 3.8% | 324 | 2.3% |
| 4.0 | 5 | 4.8% | 1,049 | 7.4% |
| 3.5 | 9 | 8.7% | 1,165 | 8.2% |
| 3.0 | 20 | 19.2% | 2,822 | 19.8% |
| 2.5 | 25 | 24.0% | 2,533 | 17.8% |
| 2.0 | 22 | 21.2% | 2,394 | 16.8% |
| 1.5 | 10 | 9.6% | 2,129 | 15.0% |
| 1.0 | 6 | 5.8% | 1,511 | 10.6% |
| 0.5 | 3 | 2.9% | 312 | 2.2% |
| **Total** | **104** | | **14,239** | |

### The rubric does not discriminate his picks from the field

**Picks at ≥3.5 stars: 17.3%. Field at ≥3.5 stars: 17.8%.**

His real, high-conviction, hand-picked entries land in the top of the star scale at
essentially **the same rate as the general population of detections they were drawn
from**. This is not a weak positive or an underpowered null — the two distributions are
close to indistinguishable at the top end, which is the end the board actually shows.

This is the study's most consequential result and it is a **negative** one. The write-up's
original framing — that A2 "speaks softly" and claims no validation — was correctly
cautious, but the measurement is stronger than agnosticism: on this evidence the star
score does not rank the trades he chose above the ones he didn't.

Read it with §5b, which supplies a mechanism rather than leaving the null unexplained: he
selects hard *for* ADR and Tightness and *against* Base length and Orderliness, and the
rubric rewards two of the dimensions he actively avoids. A score that partly rewards the
opposite of his selection criteria is expected to produce exactly this flat result.

**Bounding it honestly.** The field is missing 29% of its tickers (§2), skewed toward names
that later died, and only 104 of his 658 replayable trades appeared in it at all — so this
is a null measured on a *sixth* of his record against an incomplete field. What it
supports is "no evidence the ranking discriminates", not "proof it cannot". It is
nonetheless the direct opposite of what a validated rubric would have produced, and no
loosening of the star weights should be argued *from* A2 in either direction.

**No percentile and no rank-position figure is emitted anywhere.** The field is missing
29% of its tickers, and those missing names skew toward the ones that later
died. A top-thirty hit and a star-distribution histogram are coarser statements that survive
the missing field; a percentile would look precise while quietly flattering the rubric.

> **A2 rests on the weakest foundation of the three, and no statement here claims the ranking
> is validated.** It ranks each executed trade against a field missing 29% of
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

Across the **104 detected** trades (of 658 replayable), n=103 carry an MFE:

| Dimension | Weight | Hit rate | Spread | Correlation vs MFE | Untestable |
| --- | --- | --- | --- | --- | --- |
| Tightness | ×2 | 44.7% | 0.497 | +0.076 | |
| Orderliness | ×2 | 30.1% | 0.459 | −0.060 | |
| Prior move | ×1 | 100.0% | 0.000 | — | **yes** (no spread) |
| Base length | ×1 | 48.5% | 0.500 | −0.083 | |
| MA support | ×1 | 76.7% | 0.423 | −0.158 | |
| Volume | ×1 | 36.9% | 0.483 | −0.125 | |
| ADR | ×1 | 81.6% | 0.388 | +0.092 | |

> **Nothing in the rubric predicts a run.** Every testable correlation is negligible —
> the largest is MA support at **−0.158**, and even that points the *wrong* way. Four of
> the six testable dimensions correlate negatively with MFE. On n=103 none of these is
> distinguishable from zero.
>
> Read this narrowly. It says the rubric does not predict *how far a trade runs among the
> trades he already chose*. Range restriction (§7) is doing real work here: these are all
> trades that passed his eye, so the dimensions he applies most consistently vary least.
> **"Prior move" is untestable by construction** — every detection cleared the decile gate,
> so it is 100% throughout and its correlation is `None`, which is evidence of the gate, not
> of the dimension.
>
> Under the calibration rule (§7) a null here permits loosening **only** alongside real
> spread. Six dimensions show spread ≈0.4–0.5, so they qualify on that test; `Prior move`
> does not and never can from this analysis.

Descriptive distributions (`Distribution`: n, min, p25, median, p75, max, mean):

| Statistic | n | min | p25 | median | p75 | max | mean |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Realised R (10sma) | 657 | −1.000 | −1.000 | −1.000 | −0.490 | 104.020 | 1.245 |
| Stop width in ADR | 649 | 0.000 | 0.238 | 0.345 | 0.490 | 2.753 | 0.395 |
| ADR at entry | 649 | 0.014 | 0.047 | 0.061 | 0.089 | 0.652 | 0.082 |

Realised R is reported **descriptively only, never as the regression target** (user story
16). Its shape is the reason: median −1.00 with a mean of +1.245 and a max of +104 R — a
distribution where most trades stop out and a thin tail carries everything. Regressing
against it would have measured stop placement, not setup quality.

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

**69 taken detections** against **14,354 not-taken detections**:

| Dimension | Weight | Taken hit rate | Not-taken hit rate | Δ | Untestable within executed | Testability restored |
| --- | --- | --- | --- | --- | --- | --- |
| **ADR** | ×1 | **87.0%** | 57.6% | **+29.4** | no | no |
| **Tightness** | ×2 | **59.4%** | 38.6% | **+20.8** | no | no |
| MA support | ×1 | 76.8% | 72.5% | +4.3 | no | no |
| Volume | ×1 | 36.2% | 40.1% | −3.9 | no | no |
| Orderliness | ×2 | 27.5% | 36.6% | −9.1 | no | no |
| **Base length** | ×1 | **44.9%** | 58.3% | **−13.4** | no | no |
| Prior move | ×1 | 100.0% | 100.0% | 0.0 | **yes** | **no** — flat in both groups |

> **This is where the signal is, and it explains A2.** Two dimensions separate his picks
> sharply from the field he passed over — **ADR (+29.4pp)** and **Tightness (+20.8pp)**.
> Those are what his eye is actually doing.
>
> Three move the *other* way. He takes setups that hit **Base length** 13.4pp *less* often
> and **Orderliness** 9.1pp less often than the field — and Orderliness carries a ×2
> weight. The rubric is therefore paying double for a property he systematically avoids,
> and paying single for ADR, the property he selects on hardest. That is a coherent
> mechanism for the A2 null in §4: a score built partly on the inverse of his criteria will
> not rank his picks above the field.
>
> **The testability repair did not fire.** No dimension is flagged `testability_restored`,
> because none needed it: all six non-`Prior move` dimensions already showed spread within
> his executed trades. `Prior move` is the one dimension the not-taken group could not
> rescue — it is 100% in *both* groups (pooled spread 0.000), since every field member and
> every executed detection clears the same decile gate. It is untestable in the regression
> and stays untestable here.

> **Coverage caveat — the 87.0% ADR hit rate is over a preferentially-kept subset (attach
> here, not only to A2).** The taken group is **69 detections** — the executed trades that
> survived into the reconstructed field — not his full entry record. §6 measures ADR at entry
> over **649 entries** (his own entry-session bars, independent of the A2 chain) and finds
> **30.7% at or under the 5% floor**, p25 4.7%. These two figures describe *different
> populations and pull opposite ways*: if nearly a third of his real entries are sub-5% ADR yet
> **87.0% of the ones that reached the field clear it**, the field reconstruction is
> **preferentially keeping his high-ADR trades**. That is a coverage bias in **§5b itself**,
> not only in A2 (§4) — and §5b is the evidence the ADR ×2 reweight (#135/#138) rests on, so
> the bias bounds the selection contrast the whole recalibration is built on. The **sign** of
> the ADR gap (he selects hard for ADR) is robust to it; the **magnitude** (+29.4pp) is
> inflated by exactly the trades the field dropped. Read +29.4pp as a ceiling, not a point
> estimate. The same discrepancy is recorded against §6's floor finding, because it is a
> statement about both populations at once.

### 5c. The recalibration that shipped (PRD #138)

The selection contrast above licensed a rubric change, landed by PRD #138 against the
calibration target ADR 0001 settled (**the rubric encodes the method's revealed selection**).
The rule that turns this evidence into an edit: **the replay licenses the *direction* of a
weight, never its magnitude.** The *signs* of the §5b gaps survive the §2 coverage hole; the
*values* do not. So each weight is assigned from the **ordering** of the measured Δ — nothing
reads a gap's value.

| Dimension | Was | Now | Ordinal basis (§5b) |
| --- | --- | --- | --- |
| Tightness | ×2 | ×2 | +20.8pp — second-strongest selector |
| **ADR** | ×1 | **×2** | **+29.4pp — the sharpest selector** |
| **Orderliness** | ×2 | **×1** | **−9.1pp — hit less than the field he passed over** |
| **Base length** | ×1 | **×0** | **−13.4pp — the largest wrong-way gap** |
| Prior move | ×1 | ×1 | constant (100% both groups) — kept as documentation |
| MA support | ×1 | ×1 | +4.3pp — inside the noise of a 69-row group |
| Volume | ×1 | ×1 | −3.9pp — same |
| Sector | ×1 | ×1 | unmeasurable, dropped from the replay (§1, #130) |

**Ceiling 9, not 10; star range 0.5–4.5.** `points ÷ 2` is preserved, so the floor is
`Prior move`'s permanent point (0.5) and the ceiling is the zeroed `Base length` (4.5). The
scale was never truly 0–5; the ×0 makes that visible. `Base length` keeps a visible ×0 row in
the breakdown — a reader sees it measured, sees it worth nothing, and is routed here.
`BASE_LEN_MAX = 14` is the named suspect behind its wrong-way sign and is left open: the ×0
says the dimension *as specified* earns nothing, not that base length is irrelevant. `ADR_MIN`
holds at 0.05 (§6). A **rubric version stamp** (`score.RUBRIC_VERSION`) now rides the API
candidates payload and the digest header, so a frozen digest star and a derived-on-read app
star stay comparable across the change.

**No return claim.** §5a is null: nothing in the rubric predicts a run. This is an argument
from **selection only** — the reweight makes the score track his revealed criteria, not his
outcomes.

**Paired before/after, computed from the reported marginals.** The mean is exact —
`Δpoints = 1[ADR] − 1[Orderliness]` and expectation is linear, so no independence assumption
is needed:

| | ADR hit | Orderliness hit | Mean Δpoints | Mean Δstars |
| --- | --- | --- | --- | --- |
| His picks (taken, n=69) | 87.0% | 27.5% | +0.595 | **+0.298** |
| The field (not-taken, n=14,354) | 57.6% | 36.6% | +0.210 | **+0.105** |

The swap moves his picks **~0.19 stars more than the field** — the first quantified statement
that a rubric change pushes in the direction A2 (§4) says the current rubric does not. It is
real but modest against A2's 17.3% / 17.8% gap, and says nothing about whether the **3.5★
share** moves, which depends on the joint distribution around the boundary. The **measured**
paired A2 re-run — same field, both rubrics, one variable — is #136, and waits on the fuller
field (#129); it cannot be run against the §2-holed field without the null having two
candidate explanations (the rubric moved, or the field did). The numbers above are the
computed expectation, not the measured result.

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
are unaffordable, but because the stop convention is wrong.

**The replay confirms it almost exactly.** Over the full `stop_width_adr_distribution`
(n=649, his stop as a multiple of the night's ADR):

| | #114 preliminary | Replay (full distribution) |
| --- | --- | --- |
| Median stop width | 0.34 ADR | **0.345 ADR** |
| Share at or under 1.0 ADR | 98.1% | **98.15%** |

The quartiles show how tight the convention is: p25 **0.238**, p75 **0.490**, max 2.753.
The headline was not an artefact of a small sample — it holds across every replayable
entry. (The `min` of 0.000 is the single degenerate row where entry equals stop; it is one
row and is pinned as such in the seam.)

> This is the strongest preliminary finding, and it is worth stating what it can and cannot
> do. The star score is stop-blind by construction, so the gap **cannot move ranking at
> all**. It changes what the detector proposes and what a card claims about risk, and nothing
> else.

**Adopted by issue #127.** The detector's proposed stop is now placed at the trader's own
convention — `STOP_CONVENTION_ADR = 0.345` in `screener/detection.py`, the measured median of
this distribution — a fixed 0.345 ADR below the trigger, replacing the ~1.28 ADR cluster-low
default. The Board and Setups cards' `stopw_adr` (risk), `affordable` flag and `stop_price`
(the drawn stop line) all follow from it; the cluster geometry (`cluster_low`) is unchanged and
still carried on the row, it is simply no longer what the detector proposes. As this finding
predicts, **ranking is untouched** — the star score never reads the stop — and the acceptance
metric that tracked the old cluster-low width (B6, "share of list whose proposed stop > 1×ADR")
now expects ≈0.0, since every proposed stop sits under the 1×ADR affordability cap. The
constant cites this table as its provenance.

### Finding 2 — the ADR floor withholds its score point on 31% of his real entries. **Confirmed (preliminary).**

`ADR_MIN = 0.05` withholds its score point on **31%** of his real entries; his ADR at entry
runs **4.58% at the 25th percentile** against the 5% floor.

**The replay confirms this too.** Over `adr_distribution` (n=649):

| | #114 preliminary | Replay (full distribution) |
| --- | --- | --- |
| Share at or under the 5% floor | 31% | **30.7%** |
| ADR at the 25th percentile | 4.58% | **4.7%** |

Median ADR at entry is 6.1%, mean 8.2%, max 65.2%. So the floor is not mis-set for the
bulk of his entries — it is mis-set for the bottom third, and it withholds the point from
them silently.

ADR is the dimension he selects on most sharply (§5b), so a floor that withholds its point
on the bottom third of his entries is blunting the dimension the trade record says matters
most to him. Note also (§3) that the ADR *hard gate* rejected none of his entries — the cost
here is entirely in the score point, not in detection.

**Where the floor bites, across the whole distribution — not one number.** The 30.7% headline
is one point on a distribution whose shape matters more than the count. ADR at entry runs min
1.4%, p25 4.7%, median 6.1%, p75 8.9%, mean 8.2%, max 65.2% (§5a). So:

- the floor **does not bind for the median entry** (6.1% > 5%), nor for anything above p25 —
  roughly the top two-thirds of his entries score the point untouched;
- the withheld tail is **not marginal-and-clustered**. p25 sits at 4.7%, only just under the
  floor, but the tail runs all the way down to 1.4% — barely a quarter of the floor. The
  withheld point is denied to entries scattered from just-below-5% to far-below, not bunched
  against the threshold, so no single small nudge recovers most of them;
- every sub-floor entry was still **detected** and then **silently docked its ADR point** (the
  hard gate never bound, §3). The cost is entirely in the score, never in recall.

Moving the floor to his p25 (~4.7%) would recover the point for the entries sitting just under
it — and would also admit the **entire sub-5% ADR tail of the live universe** to the same
reward, a constant fitted to one trader's entry distribution, in one market, in one regime.

**Decision (#128): the floor holds at `ADR_MIN = 0.05`. The remedy is the weight, not the
threshold.** #128's evidence rule licenses the *direction* of a change from a measured gap,
never its *magnitude* — and a threshold value is magnitude. A graded ADR point was the other
candidate remedy and is *not available*: `score.py` records booleans-not-continuous as a
founding decision with its own measured basis (+0.255 vs +0.191) and an auditability rationale
("a sort key you cannot audit is one you will not trust"). That left *move* or *leave*, and the
floor is left — see §5b's coverage caveat for why the evidence for moving it is itself biased.

**The withheld point now costs double.** Under #135/#138 ADR moves from ×1 to ×2 — it is the
sharpest selector in the rubric (+29.4pp, §5b). The floor now withholds a point on a dimension
worth twice as much, so the 30.7% of entries docked lose *two* points, not one. This does not
argue for moving the floor; it makes the question **more consequential and better posed** — a
reason to re-ask it with better evidence, not to answer it now with this.

**What would reopen it.** The floor is left open, not closed. It should be revisited given
evidence that survives the objections above — specifically: (1) an ADR-at-entry distribution
measured on a field **without** the §2 coverage hole and the §5b high-ADR keeping bias, so the
sub-5% share is not an artefact of which trades the reconstruction dropped; (2) a live-universe
sub-5% ADR base rate, so the cost of admitting that tail can be weighed against the point
recovered; and (3) ideally an out-of-regime or IDX reference set, so the threshold is not fit to
a once-in-a-decade US momentum window (§8). Absent those, the question is reopenable rather than
settled by omission.

**A population caveat this finding must carry — 30.7% and §5b's 87.0% are not one argument.**
Earlier framing read them as mutually reinforcing. They are not: **30.7% is over 649 entries**
(his own entry-session bars, independent of the A2 chain), while **§5b's 87.0% is over 69 taken
detections** (the executed trades that survived into the reconstructed field). They describe
different populations and pull *opposite* ways — if nearly a third of his real entries are sub-5%
ADR yet 87.0% of the ones that reached the field clear it, the field is **preferentially keeping
his high-ADR trades**. This is the same coverage bias recorded as a caveat on §5b above; it is
kept in both places because it bounds §5b — the evidence the ADR reweight rests on — not only A2.

---

## 7. Caveats — carried with the same weight as the results

- **Survivorship coverage.** Everything derived from the field is read against a store
  missing 29% of its tickers, skewed toward names that later died. Every field-derived
  result carries `blind_spot_count`; the 91-ticker / 170-trade / 18.1%-of-R hole is quantified
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
- **Scope.** US, 2019–2022, with **86.6% of entries from 2020–21** (395 in 2020, 322 in
  2021, against 55 in 2019 and 56 in 2022) — a once-in-a-decade
  US momentum regime.

### The calibration rule

A gate may be loosened on the strength of an A1 recall miss **only when A3 shows that
dimension has no signal _and_ that dimension shows real spread.** This is the guard against
the one-sided recall metric: because precision is not measurable, recall is never optimised
on its own, and a dimension is never widened away on a null that is really range restriction.

**How the measured results sit against the rule.** Every testable dimension shows a null in
§5a *and* spread ≈0.4–0.5, so all six clear both conditions. `Prior move` clears neither and
never can: it is 100% in the executed trades, 100% in the not-taken detections, and its
spread is 0.000 in both. It must not be touched on the strength of this study.

The rule governs the *score dimensions*. It does not license the two changes the study most
directly supports, which are not dimension-loosenings at all:

- the **stop convention** (§6, finding 1) is a detector output and a card claim, measured
  against his own risk rather than inferred from a null; and
- the **decile gate** (§3), which costs 40% of his entries, is a cross-sectional cut whose
  loss is measured directly by A1 rather than argued from an A3 null.

---

## 8. What transfers to IDX

**The shape of the findings is a property of the method and travels. The magnitudes are a
property of a once-in-a-decade US momentum regime and do not.** Carry the structural lessons
to IDX — which gate is costing entries, that stop convention is measured against the trader's
own risk rather than assumed, that a dimension's null must be read against its spread — and
carry none of the figures. No number from this study is to be presented as an IDX
expectation; the reference set contains no IDX trade.

## 9. What the study cannot say

- It cannot claim the **ranking** is validated. A2 measured a flat null (§4) on 104 of his
  658 replayable trades against a field missing 29% of its tickers. That is evidence
  *against* discrimination, not proof of its absence — and in neither direction may it be
  read as ranking validation.
- It cannot report a **precision** or **false-positive** rate. There is no control group.
- It cannot say anything about **`Prior move`**. The dimension is 100% in every group the
  study can construct, so its spread is zero everywhere and no correlation exists to
  measure.
- It cannot speak to **Episodic Pivot** or **Parabolic Short** setups, to **intraday**
  entries, or to any name in the **blind-spot** list. The reference set is entirely US
  end-of-day breakouts, and the blind-spot hole is measured and documented, not filled.

---

## 10. Reproducing the study

**The replay store is re-runnable.** `rebuild_universe`, `rebuild_ranks` and
`rebuild_detections` all append through `Store`'s write-once guard
(`Store._guard_absent`), which exists so a derived row is never rewritten. That guard used
to make the store *single-use*: a second `replay_chain()` over the same store died with
`SessionExistsError` on its first session that already carried rows, so only whichever
analysis ran first could succeed (#126).

The chain now **reuses** a session it has already computed instead of recomputing it
(`replay.chain._replay_session`, `replay.field._session_detections`). Each session the chain
builds is stamped with a run record; a later chain sees that marker and reads the persisted
universe back rather than rebuilding it, and reads the persisted detections back rather than
re-detecting. Ranks are recomputed in memory on reuse — never read from the store, whose
two-year retention prunes an early session's rank rows before the pass ends — from the same
`rank_table` over the same bars, so the reused session is identical to the original. The
write-once guarantee is untouched: nothing is ever rewritten, only skipped. A second run
produces the same results as the first, and reusing the persisted chain avoids re-reading
every candidate's full history for each analysis.

**One command reproduces the whole study.** `replay.study` builds the field **once** and
computes coverage plus all four analyses against it — the A1 funnel, A2 placement, and both
A3 analyses share a single forward chain and a single per-session detection pass, so four
rebuilds of the 947-session chain collapse into one (issue #131). It writes both the
human-readable reports and a machine-readable results file, and prints a running count and
an ETA per session to stderr while the chain runs, so a silent hour is never mistaken for a
hang — the failure that killed the first attempt at 60 minutes. The result rows survive in
the JSON, so #133's decile decomposition can be recomputed without another rebuild.

```
# 1. build the store from the live one (read-only on the live side) — ~2 min
python -c "from replay.store import build_replay_store; \
           print(build_replay_store('data/screener.duckdb', 'data/replay.duckdb'))"

# 2. reproduce the whole study — coverage + all four analyses against one built store.
#    Coverage is asserted against the #114 figures; progress + ETA print to stderr.
python -m replay.study --store data/replay.duckdb \
    --out-report references/replay_study_report.txt \
    --out-json    references/replay_study_results.json
```

Each analysis also still carries its own `python -m` entry point (user story 30), and
because the built store is re-runnable (#126) the four can be run as separate commands
against it, **in any order**, when only one is wanted:

```
python -m replay.reference  --store data/replay.duckdb   # coverage + blind-spot list
python -m replay.funnel      --store data/replay.duckdb
python -m replay.placement   --store data/replay.duckdb
python -m replay.regression  --store data/replay.duckdb
python -m replay.contrast    --store data/replay.duckdb
```

Run separately, each rebuilds (or, on a built store, reuses) the whole chain; `replay.study`
is the way to get all four for the price of one forward pass.

**Runtime.** The chain is 947 sessions (126 burn-in + 821 measured) and dominates: the
whole study ran in **29.8 minutes**, of which the chain was 29.1 and the per-session
detection pass that builds the field added 0.6.

That figure depends on caching bar reads. `rebuild_universe` reads every candidate's full
bar history on every session — 7,529 symbols × 947 sessions ≈ **7.1M identical DuckDB
round-trips at ~1.24 ms each, about 147 minutes of pure re-fetching**. Bars are immutable
during a replay (only `universe`, `ranks` and `detections` are written) and no caller
mutates the returned list, so memoizing `Store.bars` for the life of the run is
semantics-preserving and cuts the chain from ~90 minutes to ~29. Uncached, budget two hours
or more.

---

_Provenance: PRD #114; A1 funnel #116/#119; A2 chain/field/placement #117/#118/#120; A3
outcome regression #121; A3 selection contrast #122; this write-up #123. Analysis code:
`backend/replay/`. Row-level seam: `backend/tests/test_replay_seam.py`. Study run
2026-08-15._
