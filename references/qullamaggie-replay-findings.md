# Replaying the Qullamägi trade record — findings

**Study:** the side-car replay of Kristjan Kullamägi's executed-trade record against the
app's funnel, field and rubric (PRD #114).
**Scope:** US, 2019–2022. All long, all breakout, all end-of-day. No IDX.
**Status of the app:** unchanged. This study produces evidence only. No constant in
`detection.py`, `score.py`, `universe.py` or `ranks.py` is touched by it, and none is
touched by this write-up (PRD "Out of Scope"; #114 acceptance).

**A plain-language version of this document** — same numbers, same conclusions, no assumed
vocabulary — is at [`qullamaggie-replay-findings-plain.md`](qullamaggie-replay-findings-plain.md).
This file remains the authority: its figures are the ones checked against the committed run output.

This document exists so that any constant later changed has a **citable provenance**
(user story 26): each figure below names the analysis and the module that produced it, and
each carries the caveat that bounds it. The caveats are given the same weight as the
results, because the results are not usable without them.

> **Every magnitude below is measured.** The study was last run end to end on **2026-08-19**
> against a `replay.duckdb` built from the live store (5,892,590 US bars, 7,529 tickers,
> 2019-04-01..2022-12-31) and the committed reference set
> (`references/trades_bo_gain10smaPct_desc.json`). The chain replayed all 947 sessions —
> 126 burn-in, 821 measured — in one forward pass, and all four analyses were computed
> against that single chain. Nothing here is projected or extrapolated; where a number is
> absent it is because the measurement is *impossible* (§9), not pending.
>
> That run's own outputs are committed beside this file — `replay_study_report.txt` and
> `replay_study_results.json` — so every figure below is checkable against the run that
> produced it rather than quoted from one. It closed the three figures the previous write-up
> still carried as pending: the paired A2 re-run (§4a, #136), the decile decomposition (§3,
> #133) and the cluster miss split (§3a, #132) — the last of which **contradicted** what §3a
> expected, and is recorded as such.
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
| Blind-spot tickers | **92** |
| Blind-spot trades | **172** |
| Blind-spot share of total realised R | **18.0%** |

> **The hole is larger than #114 first measured**, and the correction matters. The
> original 81 / 141 / 11.7% asked whether the provider returns the symbol *at all today*.
> The study actually needs a stricter question — does the ticker have bars **in the replay
> window** (`2019-04..2022-12`), which is the only condition under which the funnel or the
> field can say anything about the trade. The two differ by 11 tickers / 31 trades, and
> every one of those is a **symbol-reuse** case: APXT, BNKU, EYES, FNGU, FUSE, LAC, LAZR,
> NRGU, SI, SPWR, USLV all resolve today, but their bar history begins years *after* the
> entry they are paired with, because the ticker was recycled onto an unrelated listing.
> (Ten of the eleven were caught by the window test alone; `FUSE` needed the stricter
> covers-the-evaluated-session test #139 landed — see the note below.) Counting
> them replayable would not merely understate the hole — at any window overlap it would
> replay one company's trade against another company's bars. So survivorship here is not
> only delisting; it is delisting **plus ticker recycling**, and the recycled names are
> silent rather than absent.

> **#139 re-pinned these figures: the window test now asks whether the bars cover the
> session the trade is evaluated at**, not merely whether the symbol has bars somewhere in
> the window. The ten recycled names above were caught only by luck — their replacement
> listings all begin after `2022-12`, so the window build excluded them and a has-any-bars
> test happened to give the right answer. `FUSE` is where the luck ran out: it is paired
> with a `2021-01-04` entry, and its bars in the store run `2022-03-07..2022-12-22`. Under
> the old test its 2 trades were counted replayable, entered the funnel denominator, and
> failed the detector's `history` gate — charged to the detector as a stage failure when
> they are a coverage hole. The re-pinned figures supersede **91 / 170 / 18.15%** (658
> replayable), which every measured result in §§3–8 below was computed under; the R share
> moves *down* because `FUSE`'s two trades carried below-average R. Both moves are
> corrections, not improvements — the hole is the same size, measured properly — and both
> are small enough to leave every finding below standing as measured.

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

**656 replayable trades** (of 828; the other 172 are the blind spot), of which **79** are
tagged `continuation`.

> **Re-measured after #154.** The base-tightness restructure changed what the detector detects, so
> the detection row below is a **re-run** figure and the `cluster` line in the condition table
> collapses. Liquidity and decile are cross-sectional and untouched by that change — they
> reproduced to the row. The superseded detector-v1 figures are kept in each cell so the two
> are never quietly conflated: recall is only comparable within one `detector_version`.
> #139's re-pin of the denominator (658 → 656) applies throughout.

| Stage | Recall (headline) | Recall (ex-continuation) | Notes |
| --- | --- | --- | --- |
| Liquidity | **598/656 (91.2%)** | **523/577 (90.6%)** | The one stage where a rejected name never reaches any tab — a miss here is otherwise invisible (user story 7). Cheapest of the three. |
| Decile | **395/656 (60.2%)** | **340/577 (58.9%)** | The most aggressive filter — cut to **19.4%** of the universe before the detector looks. **The gate has since moved:** #149 admitted `12m`, taking it to **21.9%** of the universe and decile recall to **448/656 (68.3%)** — see §3e. This row is the measurement under the three-lookback gate and is left as measured. Depends on the replayed field → coverage attached. |
| Detection | **549/656 (83.7%)** | **487/577 (84.4%)** | Detector v2 (#154). Was 380/658 (57.8%) under the hard 1.5 cluster cut. Failures broken down by geometric condition below (user stories 9, 10). |

> **The decile gate is the expensive one.** Under the width measured here it discards **40%
> of his real entries on its own**, before the detector is ever consulted — the largest single loss in the funnel, and
> nearly five times the liquidity stage's. **Correction (#133):** this table originally
> quoted the gate as cutting to "~29% of the universe", following PRD #114 user story 8.
> That figure is the *five*-lookback union (`ranks.py`, 27.2% measured); the gate this row
> measures is `detection_gate`, which unions only `1m`/`3m`/`6m` and admits **19.4%**. The
> gate is a third tighter than the parent spec describes. See
> `docs/adr/0003-the-decile-gate.md`. Each stage is evaluated *unconditionally* on
> every row, so these are not sequential survivors: they are three independent
> measurements, not a funnel product. Under detector v1 decile (60.0%) and detection (57.8%)
> were close enough to argue about which was worse; after #154 the question is settled —
> **the decile gate is now the funnel's largest loss by 23 points**, and it is the one
> governed by a rule (ADR 0002's second limb) that it can be argued under.
>
> Detection is also the **only** stage whose ex-continuation recall (84.4%) is *higher*
> than its headline (83.7%). His repeat entries into a name are still marginally harder for
> the detector to see than his first ones, but the gap has narrowed to 0.7pp from 1.2pp: the
> `cluster` condition, which fired on exactly that pattern, is no longer doing the work.

### The decile miss decomposed (#133) — a third of it is the gate's width, not his names

The 40% is a headline, and on its own it invites the wrong fix. `decompose_decile_misses`
splits all **263** decile misses into three exclusive buckets, so the loss is attributed
before anything is widened on the strength of it:

| Bucket | Count | Share | What it is |
| --- | --- | --- | --- |
| Coverage gap (absent from the field) | **64** | 24.3% | Not a ranking verdict at all — the ticker was not a universe member that session. §2's hole, showing up inside the funnel. |
| Recovered by widening the gate 3→5 | **75** | 28.5% | Present, outside the **three**-union gate, but inside the **five**-union one. |
| Outside even the five-union gate | **124** | 47.1% | A genuine cross-sectional miss: the name was not top-decile on any lookback. |

**The middle bucket is the study's most concrete lead**, and §3e decomposes it one level
further, which is what settled it.

**The middle bucket is the study's most concrete lead.** 75 of his real entries — 11.4% of all
658 replayable trades — sat inside the five-lookback union and outside the three. That is a
*width* decision, not a judgement about his names, and it is the one decile change A1 measures
directly rather than inferring from an A3 null (§7).

Read it against the other two buckets before acting: a quarter of the "miss" is §2's coverage
hole wearing the decile gate's clothes and would not be recovered by any widening, and nearly
half are outside every union the app could plausibly offer. So the honest size of the gate's own
width problem is **75, not 263** — and the precision cost of admitting the wider union is still
unmeasurable (§7), so this is a lead to size, not a change licensed here.

Detection-failure breakdown (`condition_counts`) — which geometric condition to change:

| Failed condition | v1 count (of 278) | v2 count (of 107) |
| --- | --- | --- |
| `cluster` | **171** (61.5%) | **2** (1.9%) |
| `catch_up` | 47 (16.9%) | **47** (43.9%) |
| `base_length` | 37 (13.3%) | **37** (34.6%) |
| `history` | 23 (8.3%) | **21** (19.6%) |
| `adr` | 0 | 0 |
| `prior_move` | 0 | 0 |

Under v1, `cluster` alone cost more than the other three firing conditions combined; under v2
it is the smallest, and `catch_up` — price not yet back at the 10/20 MA — is the largest
remaining detection miss. The `history` row moves 23 → 21 for a different reason entirely:
#139 stopped charging two recycled-symbol trades to the detector. Neither `adr` nor
`prior_move` has ever rejected one of his entries: `prior_move` cannot (every detection clears
the decile gate by construction), and the ADR *hard gate* never bound — which is distinct from
the ADR *score point*, withheld on 30.7% of entries (§6, finding 2).

Blind-spot trades (ticker with no bars) get **no** funnel row — they are recorded as a blind
spot by `replay.reference`, never as a stage failure, so the replayable set and the blind
spot are each quantified rather than one silently absorbing the other (user story 34).

### 3a. Is the `cluster` condition's window mis-set for the way he re-enters names? (#132)

**Question.** `cluster` is the largest single detection miss — **171 of 278** (61.5%), more than
`catch_up`, `base_length` and `history` combined. Is its window too aggressive, or is it
declining trades it should decline?

**What the condition is.** A `cluster` miss means `_find_cluster` found *no* trailing window in
`K_MIN..K_MAX = 3..7` bars whose range sits under `TIGHT_MULT = 1.5 × ADR` — i.e. even the
**tightest 3-bar** trailing window spans more than 1.5 ADR. That is the geometry of a name **in
motion**, not one consolidating in a base: the recent bars are wide relative to the name's own
20-bar ADR. The detector emits *a base, not a state*, so by construction it declines a name that
is still running.

**Two independent signals say the misses are his re-entries, not the rule mis-firing on bases.**

1. **A1's ex-continuation inversion (§3).** Detection is the *only* funnel stage whose
   ex-continuation recall (**59.0%**) is *higher* than its headline (**57.8%**). Stripping his
   repeat entries makes the detector look better — the signature of a rule that penalises exactly
   the repeat-entry pattern. A continuation entry is an *add to a running position*, tagged not
   dropped (§1); it is not a fresh base, and the base detector was never going to fire on it. So
   the recall the `cluster` rule "costs" on those rows is recall on a pattern the app does not
   claim to detect.
2. **A3b's selection contrast (§5b).** **Tightness** — `cluster_k ≥ 5`, the cluster's own
   narrowness — is the **second-strongest selector in the whole rubric** (taken 59.4% vs
   not-taken 38.6%, **+20.8pp**), behind only ADR. His eye actively selects *for* tight clusters.
   A gate built on cluster tightness is therefore filtering on the very geometry his selection
   most depends on.

**Recommendation: leave the window unchanged. Do not loosen `TIGHT_MULT`, `K_MIN` or `K_MAX`.**
Provenance for the decision — all three legs measured, none newly asserted:

- **The calibration rule (§7) forbids it.** A gate may be loosened on an A1 recall miss *only when
  A3 shows the dimension has no signal **and** real spread*. Tightness has clear signal — it is
  §5b's +20.8pp selector — so the rule's precondition fails outright. Loosening the cluster window
  is precisely the "widen every gate to chase a recall number" trap the missing precision leaves
  open (§7): with no false-positive rate measurable, a recall gain from admitting wider, in-motion
  names cannot be weighed against the noise it lets in.
- **The misses are not the detector failing on bases.** They are the detector correctly declining
  names that are mid-move — disproportionately his continuation entries (signal 1). Recall on
  continuation entries is not a legitimate optimisation target; the study keeps them in every
  denominator (§1) but never as a target to be recovered.
- **No app change is made, so no A1 recall re-measurement is triggered** (acceptance criterion 3
  is conditional on a change). The `detection.py` cluster constants stand: `K_MIN, K_MAX = 3, 7`,
  `TIGHT_MULT = 1.5`.

**The characterisation machinery, so the verdict is checkable and re-openable.** The A1 funnel now
records, on every replayable trade, the *margin* of a cluster miss: `range_3bar_adr` — the
trailing 3-bar range in ADR, which is the tightest window the detector could find (§3b), taken
regardless of the 1.5× threshold (`screener.detection.range_3bar_adr`, a read-only diagnostic that
changes no detection verdict) — and `sessions_since_prior_entry`, the market-session distance to the nearest
prior entry in the same ticker. `funnel.characterise_cluster_misses` (`ClusterDecomposition`)
partitions the 171 misses two ways: **continuation vs fresh** (how far from a prior entry) and
**marginal vs far** against a reported `MARGINAL_TIGHT_MULT = 2.0` boundary (how far over the 1.5×
window — a marginal miss is one a modest widening would recover, a far miss a name genuinely in
motion). Both counts, plus the 3-bar-range and prior-distance distributions, ride the report
and the machine-readable `replay_study_results.json`, so the per-miss shape is recomputable
without another rebuild.

#### The split is now measured, and it did **not** confirm what this section expected

An earlier draft of this note predicted the split would come back continuation-heavy — "the
expected confirmation". It did not. Measured over the same 171 misses (`ClusterDecomposition`,
committed in `replay_study_report.txt`):

| Partition | Count | Share |
| --- | --- | --- |
| **Fresh entries** | **148** | **86.5%** |
| Continuation entries (re-entries) | **23** | 13.5% |
| **Marginal** (≤ 2.0× ADR — a modest widen recovers) | **113** | 66.1% |
| Far (name genuinely in motion, no base) | 58 | 33.9% |

3-bar range in ADR: median **1.85** (p25 1.68, p75 2.13, max 3.42) against the 1.5×
threshold. Continuation misses sit a median of 4.0 sessions from the prior entry.

**This is a real weakening of signal 1, and it is recorded rather than absorbed.** The
re-entry story explains **23 of 171**, not the bulk. The remaining 148 are fresh entries the
detector declined, and two thirds of the whole set are *marginal* — clustered just past the
threshold at a median 1.85× against a 1.5× gate, which is the shape of a boundary set slightly
tight, not of names wildly in motion.

**The verdict still stands, but now on one leg rather than three.** Leave `TIGHT_MULT`, `K_MIN`
and `K_MAX` unchanged — because the **calibration rule** (§7) forbids the loosening outright:
Tightness has clear signal (§5b's +20.8pp, the second-strongest selector in the rubric), so the
rule's precondition fails no matter how the misses are distributed. That was always the load-
bearing argument, and this section said so in advance: the split "cannot license a loosening
even if it came back continuation-light". It came back continuation-light. The rule holds.

What has changed is the **strength of the case, not its direction**. Signal 1 (the
ex-continuation inversion, §3) is still a true measurement — stripping re-entries does make the
detector look better — but it can no longer be read as explaining most of the `cluster` loss.
Anyone re-opening this should treat the 113 marginal misses as the open question, and note that
answering it properly needs the thing the study does not have: a measurable false-positive rate
(§7, §9). A widen that recovers 113 of his entries at an unmeasured cost in noise is exactly the
trade this study cannot price.

**What would re-open it (gather more evidence, not act now).** A dataset that makes precision
measurable — a control group of setups he *passed over* — so a recall gain could be weighed against
its false-positive cost; and an out-of-regime or IDX reference set, so the window is not tuned to a
once-in-a-decade US momentum regime (§8). Absent those, the question is re-openable rather than
settled by omission, and the machinery above is what a re-opening would read.

> **Superseded by #145/#154 — and not by finding the missing precision measurement.** The
> constants this section left standing are gone: `TIGHT_MULT = 1.5` no longer gates, and the
> cluster condition is now a **far-outlier guard** at `OUTLIER_MULT = 3.0` with base tightness
> graded by the rubric. It was re-opened on a different argument than the one this section
> anticipated. This section asked "is 1.5 the right cutoff", and answered correctly that no
> available evidence licenses moving it. §3b reframed the question as "should this be a cutoff
> at all", which the calibration rule's score-dimension limb does not govern — that limb
> governs *loosening a dimension away on a null*, and Tightness has signal on both axes. The
> change is a **shape** change with the weight held at ×2, priced with its population cost;
> the argument and the measurement are in §3b below. The 113 marginal misses this section left
> as its open question are recovered by the guard, but that is the change's *consequence*, not
> its licence — a recall number still licenses nothing on its own.
>
> The §3a figures above are **not restated** to the new detector: they characterise the 171
> misses the 1.5 cut produced, which is the evidence the decision was taken on, and
> `MARGINAL_TIGHT_MULT` is kept at 2.0 so they still reproduce.

---

### 3b. What "tight" is in the trade record itself — the shape of the tightness signal (prototype, side-car)

**Question.** §3a characterised the `cluster` **misses** and left the 113 marginal ones as its open
question. It never asked the complementary question: across the trades he *did* take, what geometry
did the tightness dimension actually have? `TIGHT_MULT = 1.5` and `TIGHT_K = 5` are borrowed
q-scanner-v2 defaults; nothing in the study had yet placed them against his own distribution.

**Method.** For each replayable trade, walk to the evaluation session (§1's convention — the last
session strictly before entry) and record the raw trailing k-bar range in ADR for **every** k in
3..7, gating nothing at measurement time. Same reference set, same ADR definition
(`screener.indicators.adr_abs`), same n as §6: **649 of 828 (78.4%)**, the missing rows being 170
tickers absent from the bar store, 7 short of 20 bars and 2 with no prior session. Because nothing
is gated during measurement, any threshold can be re-derived afterwards without a rebuild.

Produced by a **throwaway prototype**, not by `replay.study`: `backend/replay/prototype-tightness/`
on branch `worktree-prototype-tightness` (see that directory's `FINDINGS.md`). It is a side-car to a
side-car, and is **not** part of the reproducible study in §10 — the figures below are checkable by
re-running `measure_tightness.py`, not by `python -m replay.study`. Treated as preliminary in the
sense of §6, and flagged as such wherever cited.

#### The distribution `TIGHT_MULT` is cutting into

| Trailing window | p25 | median | p75 | p90 | max | share ≤ 1.5 ADR |
| --- | --- | --- | --- | --- | --- | --- |
| **k = 3** | 1.00 | **1.31** | 1.73 | 2.16 | 5.09 | **64.4%** |
| k = 4 | 1.20 | 1.55 | 2.05 | 2.48 | 7.65 | 47.3% |
| k = 5 | 1.36 | 1.86 | 2.31 | 2.84 | 13.12 | 33.1% |
| k = 6 | 1.61 | 2.06 | 2.55 | 3.24 | 17.03 | 20.3% |
| k = 7 | 1.77 | 2.25 | 2.81 | 3.55 | 17.50 | 13.9% |

`TIGHT_MULT = 1.5` sits at roughly his **64th percentile** on the binding window: it admits 418 of
his 649 replayable entries and declines 231. There is no gap, shoulder or inflection at 1.5 —
the distribution runs straight through it.

Note the last column against `TIGHT_K = 5`: only a third of his entries had a 5-bar window inside
1.5 ADR, so the rubric's ×2 tightness dimension is a genuinely selective test rather than a
formality — consistent with §5b's +20.8pp.

#### The cluster diagnostic is the 3-bar range, and only `K_MIN` can gate

Range is monotone in `k`: a longer trailing window can only contain more high and more low, never
less. So the minimum over `k ∈ 3..7` is **always** `k = 3` — confirmed on all 649 rows, identical to
the last decimal. Two consequences for how §3a's machinery should be read:

- `screener.detection.range_3bar_adr` reports **the 3-bar range**. §3a's "3-bar range in ADR:
  median 1.85" over the misses is therefore a 3-bar median. It was named `cluster_min_range_adr`
  when this section was written — a general name for a number that is always the 3-bar one — and
  #146 renamed the function, the `replay_study_results.json` row key and the report line it is
  quoted from.
- **`K_MAX` cannot affect pass/fail.** `_find_cluster` scans downward from `K_MAX` and returns the
  first window under the threshold, so widening or narrowing `K_MAX` changes only the *reported*
  `cluster_k` — which is what the rubric's ×2 dimension then scores. `K_MIN` alone decides whether a
  name clears the gate. The two constants sat together in `detection.py` as if they were a matched
  pair; they are doing unrelated jobs, and #146 split the declaration to say so.

#### The signal is graded, and the decline is smooth through 1.5

Grouping the taken trades by the 3-bar range they sat in, against the record's own 10-SMA exit:

| 3-bar range (ADR) | Trades | Mean R | Median R | Win rate |
| --- | --- | --- | --- | --- |
| 0.0–1.0 | 164 | **+2.02** | −1.00 | 23.2% |
| 1.0–1.5 | 254 | **+1.35** | −1.00 | 25.3% |
| 1.5–2.0 | 139 | **+0.84** | −1.00 | 18.0% |
| 2.0–3.0 | 82 | **+0.35** | −1.00 | 22.0% |
| 3.0+ | 10 | **−0.36** | −1.00 | 20.0% |

Monotone across the whole range and **smooth** — the decline through 1.5 looks like the decline
through 1.0 or 2.0. Median R is −1.00 in every bucket: most of his trades stop out and the record
lives in its tail, so mean R is the statistic here and the median is uninformative by construction.

At the shipped 1.5 the gate splits mean R **1.61 kept vs 0.61 rejected**, keeping 64.4% of his
trades and 82.6% of his summed R. Widened to ~3.0 it keeps 98.5% of trades and 100.4% of his R —
over 100% because the rejected tail is net negative.

**This corroborates §5b from the opposite direction.** §5b showed he *selects* for tightness
(+20.8pp, second-strongest selector); §3b shows the dimension also *predicts outcome* among the
trades he took, and does so continuously. Tightness is the best-evidenced dimension in the study.

#### The stop is not the base — a 3.8× gap between two things called "tight"

Measured on the same evaluation sessions:

| | p25 | median | p75 | max |
| --- | --- | --- | --- | --- |
| The base (3-bar range, ADR) | 1.00 | **1.310** | 1.73 | 5.09 |
| His stop width (ADR) | 0.238 | **0.345** | 0.490 | 2.753 |

**Ratio of medians 3.80×**; median of the per-trade ratio 3.77×. The stop row **reproduces §6
Finding 1 exactly** — every quantile, the 98.15% at-or-under-1.0-ADR share, and the same n — which
is the provenance of `STOP_CONVENTION_ADR = 0.345` (#127). That is an independent reproduction by a
different code path, not a new result, and is the main external check this prototype has passed.

What is new is the pairing: base tightness and stop width are **different quantities by ~3.8×**, and
both were called "tight" in the codebase and in the method notes. **Separated in the domain model by
#147**, before either was tuned: `CONTEXT.md` now defines **base tightness** (setup geometry — what
`TIGHT_MULT` gates and the rubric's ×2 dimension scores) and **stop width** (his risk — what
`STOP_CONVENTION_ADR` encodes) as distinct terms, citing this section for the pairing and §6 Finding 1
/ #127 for the convention.

> *Method note, recorded because the first pass got it wrong.* Both rows above are **ratios** — his
> stop as a fraction of entry, ADR as a fraction of close — so a split cancels and all 649 rows
> count. Measuring the stop as a *price difference* against a bar-derived ADR does **not** work: the
> reference set's prices are raw while the stored bars are split-adjusted, so any ticker that split
> after the trade puts the two on different scales, yielding a median of 0.36 and a max of 30.94
> ADR. Anyone extending the study should use the ratio form. The range-in-ADR figures are computed
> from bars alone and were never exposed to this.

#### Read against the entry-to-MA study (#143) — one mechanism confirmed, one method borrowed

Two points of contact with [`qullamaggie-entry-ma-distance.md`](qullamaggie-entry-ma-distance.md),
which landed independently and measured a different quantity on an overlapping subset (n=579).

**1. It supplies the mechanism for the 3.8× gap above.** That study finds stop width and
entry-to-SMA10 distance are **uncorrelated across his book (Spearman −0.002)**, and concludes he
stops at the low of the **entry day** — so the stop is set by that day's range, not by the base
geometry and not by how far price has travelled from the MA. That is exactly the shape §3b
measures from the other side: a stop at 0.345 ADR against a base of 1.310 ADR is not a base-derived
stop, and now it is clear what it *is* derived from. Three independent measurements of the stop now
agree (§6's 0.345, that study's 0.346 on a different subset and a different ADR basis, and §3b's
reproduction), and the mechanism is no longer a guess.

**2. Its method for setting a line is the right one, and applying it here gives the opposite
answer.** That study explicitly refuses to set "extended" at a percentile of his habits —
*"a percentile describes his habits; it does not describe where trades stop working. The two
disagree, and the outcome data should win"* — and sets the line at 1.5 × ADR above the SMA10
because the outcome data has a **feature** there: the ≥3R share halves between 1× and 2× while the
win rate holds, and expectancy reaches zero past 1.5×. A cliff exists, so a threshold is the honest
encoding of it.

Applying the same test to tightness gives the opposite result. §3b's outcome table has **no such
feature** — mean R declines monotonically and smoothly, and the decline through 1.5 is
indistinguishable from the decline through 1.0 or 2.0. So the two dimensions genuinely differ in
kind, and should not be encoded the same way:

| | Outcome shape | Honest encoding |
| --- | --- | --- |
| Entry-to-MA distance (#143) | A cliff — expectancy → 0 past 1.5 ×ADR, ≥3R share halves | A threshold (plus a hard no-trade line past 2.5 ×) |
| Tightness (§3b) | A smooth monotone decline, no feature anywhere | A graded score |

Note also that `TIGHT_MULT = 1.5` is currently justified by neither test: it is not a percentile
anyone chose (it is a borrowed q-scanner-v2 default that happens to land at his 64th) and it is not
sited on a feature in the outcome data, because there is no feature to site it on.

That study's **two-line design** — a soft zone that warns and a hard zone that refuses — is the
pattern worth borrowing if tightness is ever restructured: a graded rubric input across the range
where the signal varies, plus a far outlier guard, rather than one line doing both jobs. Filed as
#145.

#### What this does and does not license

**It does not license loosening `TIGHT_MULT`, and §3a's verdict stands unchanged.** The calibration
rule (§7) permits a loosening only when A3 shows the dimension has **no signal and real spread**.
§3b makes the precondition fail *harder*: tightness now has demonstrated selection signal (§5b)
*and* demonstrated outcome signal (above). Nothing here is a licence to widen a gate.

**What it adds is a price tag on the current shape.** §3a left the 113 marginal misses as the open
question and noted that answering it needs a false-positive rate the study does not have. §3b does
not supply that rate — it cannot, being conditioned entirely on trades he took. It supplies the
other half of the ledger: the hard cut at 1.5 declines **231 of his own entries (35.6%)** carrying
**17.4% of his summed R**, to express a signal that varies smoothly. That cost was previously
unquantified.

**The re-openable question this reframes.** The live proposal is no longer "is 1.5 the right cutoff"
but "should tightness be a cutoff at all, or a graded rubric input with a much looser outlier
guard". That is a larger change than §3a considered, it is still unpriceable without a control group
of setups he passed over (§7, §9), and it is filed rather than acted on. No constant is touched by
this section.

#### What was built on this — the restructure, and where it stands against the rule (#145/#154)

The proposal above was decided in #145 and implemented in #154. `TIGHT_MULT = 1.5` **no longer
gates**: it shapes the cluster window, the cluster falls back to the 3-bar window when nothing
tighter clears, and the only base-tightness rejection left is a **far-outlier guard** at
`OUTLIER_MULT = 3.0 × ADR` on the 3-bar range. The rubric's ×2 `Tightness` dimension is graded on
that same ungated quantity — 2 points at or under 1.0 ADR, 1 through 2.0, none beyond — at rubric
**v3**. The weight did not move.

**The position on the calibration rule, stated rather than left implicit.** ADR 0002's
score-dimension limb permits loosening a dimension "only when A3 shows that dimension has no
signal *and* real spread", and §3a refused the loosening on exactly that ground. Two things about
how this change sits against it:

- **The precondition is not met and is not claimed to be.** Tightness has selection signal (§5b,
  +20.8pp, second-strongest in the rubric) and outcome signal (the table above). It is the
  best-evidenced dimension in the study. Nothing here argues it is null.
- **The rule's limb governs *loosening a dimension away*; this is a change of *shape*.** The
  instrument exists because a null on a range-restricted dimension is not evidence the dimension is
  useless, and because recall alone would widen every gate. The claim here is the opposite of a
  null: the dimension is well evidenced, *and* the evidence says its outcome relation is a smooth
  monotone decline with no feature anywhere — so a threshold is the wrong encoding of a signal that
  strong, in the same sense that #143's cliff made a threshold the right encoding there. The
  dimension keeps its ×2 and now expresses more of what it measures, not less.

That reading is a **judgement about the rule's scope, not a finding**. It is not left as a note
in a write-up either: it is recorded as a decision, with the four conditions that have to hold
before the move can be reached for again, in
[`docs/adr/0004-replacing-a-threshold-with-a-graded-input.md`](../docs/adr/0004-replacing-a-threshold-with-a-graded-input.md). What it does not do is exempt the change from the rule's
purpose: precision is still not measurable, so the cost side is priced explicitly below, the way
#141 and #149 price theirs and the way ADR 0002's condition 4 requires of a cross-sectional cut.

**Both halves of the ledger, measured** (`scripts/base_tightness_restructure.py`, over the same replay
store; recall on the 828-trade reference set, field inflation over the 505 replayed sessions the
store holds ranks for):

| | Hard 1.5 cut | Far-outlier guard | Change |
| --- | --- | --- | --- |
| Detection-stage recall | 380/658 (57.8%) | **549/656 (83.7%)** | **+169 trades** |
| — ex-continuation | 341/578 (59.0%) | **487/577 (84.4%)** | +146 |
| `cluster` misses | 171 | **2** | −169 |
| Detections per session | 90.3 | **201.6** | **+111.3 (+123.2%)** |

**That last row's denominator is the 505 sessions, not the 821.** It is correct as stated and is
left as measured — but #164 later found those were the only sessions carrying a field at all, so
quoting 90.3 or 201.6 against a whole-chain figure compares two different denominators. On the
whole chain the same step is **83.6 → 180.5** detections per measured session (§4b), which
reproduces both figures above exactly when re-divided by the 505.

**The population cost is the headline, not the recall.** The field more than doubles: 111 more
names per session, or **0.66 additional names per session for each trade recovered**. That is a
large number and it is the honest denominator — precision cannot be measured, so this ratio is what
stands in for it (ADR 0002, condition 4). What absorbs it is the thing the change was made for: the
names admitted are exactly the ones the graded dimension scores *low*, so they enter the list at the
bottom of the sort rather than beside his own setups. The restructure moves work from the gate to
the sort key, and that is only a good trade if the sort key is trusted — which is why the grade is
banded and published on the breakdown rather than folded invisibly into a star.

**The guard is provisional, and here is its n.** The 3.0 bound is sited on the only feature §3b's
outcome table offers, and that feature is one bucket of **10 trades** at −0.36 mean R. Ten is far
too thin to carry a threshold on its own; what makes 3.0 the right *order of magnitude* rather than
a guess is the complementary figure — widening to ~3.0 keeps 98.5% of his trades and 100.4% of his
summed R, the excess over 100% being the net-negative tail the guard cuts. On his own record the
guard declines **2 trades**, at a 3-bar range of 3.18 and 3.42 ADR. What would firm it up is a
larger denominator in the negative tail, which is exactly what the out-of-sample backtest builds
(`docs/out-of-sample-backtest-plan.md`); until then the constant is not to be swept or tuned on an
in-sample number.

**What the recovered trades look like.** The 169 recovered entries sit at a 3-bar range of median
1.83 ADR (p25 1.68, p75 2.10, max 2.90) — clustered just past the old 1.5 line, which is §3a's
"marginal" population arriving as detections. Under the graded rubric almost all of them score 1 of
the 2 available tightness points rather than 2.

**The inflation was predictable from §3d, and it lands where §3d said it would.** That section
measured the recent 3-bar span on his entries against an ordinary-day background: **64.3% of his
entries sit inside 1.5 ADR against 34.4% of background days**. A gate at 1.5 was therefore cutting
roughly two thirds of the background while keeping two thirds of his entries, and removing it lets
that two thirds back in — which is the +123% almost exactly. It is the same number read from two
directions, and it is worth stating plainly: **the 1.5 cut was doing most of the detector's
filtering**, and the graded dimension now has to carry that load in the sort instead.

---

### 3c. How the base forms — length, depth, and when the tightening starts (prototype, side-car)

**Question.** §3b measured how *narrow* the final cluster was on the trades he took. It never
asked how the cluster got there: how long the base had been forming, how deep it was, what it was
resting on, or when the contraction began. The detector's cluster window sees a 3–7 bar snapshot;
nothing in the study had characterised the structure behind it.

**Method.** Same reference set, same conventions (§1's evaluation session; `adr_abs`), same n as
§3b — **649 of 828 (78.4%)**. For each trade: base length two independent ways, the ADR and
range-ratio curves over the 90 sessions before entry, the prior advance, and base depth. Nothing is
gated at measurement time. Continuation entries are tagged and kept in every denominator; they do
not move any figure below.

Produced by a **throwaway prototype**, not by `replay.study`: `backend/replay/prototype-base-length/`
on branch `worktree-prototype-base-length` (see that directory's `FINDINGS.md`). **Not** part of the
reproducible study in §10 — the figures are checkable by re-running `measure_base.py`, not by
`python -m replay.study`. Preliminary in the sense of §6.

> **Machinery cross-check.** The 5-bar range-ratio at the evaluation session comes back at a median
> of **1.86 ADR** — §3b's committed k=5 median, to the digit, computed by an independently written
> path. The two prototypes agree where they overlap.

#### There is no single base length, because it is not one measurement

**D1, overhead-supply age** (sessions from the highest high in the trailing 120 to the evaluation
session): median **24**, p25 11, p75 63. Broad and not unimodal — 12.0% break out of something ≤5
sessions old, 42.4% from 6–30, 19.3% from 31–60, and **26.3% from something older than 60
sessions**. 2.8% are censored at the lookback, so the right tail is a floor.

**D2, containment length** (the largest n whose trailing n-bar range still fits inside T × ADR):

| Threshold | p25 | median | p75 | p90 | max |
| --- | --- | --- | --- | --- | --- |
| within 1.5 ADR (`TIGHT_MULT`) | 2 | **3** | 5 | 7 | 13 |
| within 2.0 ADR | 3 | **5** | 8 | 10 | 16 |
| within 3.0 ADR | 7 | **11** | 14 | 17 | 41 |
| within 4.0 ADR | 12 | **17** | 22 | 29 | 121 |

Essentially uncensored (0.0–0.8%). **Read together:** the *tight* part of the base is short — a
median 3 sessions inside 1.5 ADR — while the structure it sits in is much longer. A base is a
multi-week formation whose final contraction is a handful of days, and the detector sees only the
second of those.

**This is a defence of `K_MIN, K_MAX = 3, 7` that §3a could not offer.** The window brackets the
1.5-ADR containment distribution almost exactly (median 3, p90 7). It is also why the window cannot
answer "is there a base": containment at 1.5 ADR runs out after a median of 3 sessions whether the
structure behind it is 8 sessions or 80.

#### ADR does not tighten into his entries at all

Median 20-day ADR across the 90 sessions before entry:

| Sessions before entry | 90 | 60 | 40 | 30 | 20 | 10 | 5 | 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Median ADR % | 5.77 | 5.90 | 5.90 | 6.01 | 5.98 | 6.13 | 6.19 | **6.08** |
| Median ratio to entry eve | 0.94 | 0.98 | 1.00 | 0.97 | 1.01 | 1.03 | 1.03 | 1.00 |

**Flat.** A per-trade "ADR now ÷ ADR at its 90-day peak" reads a median of 0.71 and looks like
contraction, but that is a ratio to the *maximum* of a noisy series and is biased downward by
construction. The flat median curve is the honest reading; the two are not in conflict.

What contracts is **travel**. The trailing 5-bar range over ADR, re-read at each historical session:

| Sessions before entry | 90 | 60 | 40 | 30 | 20 | 15 | 10 | 7 | 5 | 3 | 2 | 1 | 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Median 5-bar range / ADR | 2.38 | 2.39 | 2.37 | 2.29 | 2.44 | 2.43 | 2.38 | 2.24 | 2.26 | 2.18 | 2.07 | 1.99 | **1.86** |

A flat baseline of ~2.4 ADR from three months out to roughly ten sessions before entry, then a
monotone fall to 1.86. **The contraction is a late, ~7-to-10-session event, and it is a collapse in
how far price travels — not a decline in how much it moves per day.** The stock keeps its ~6% daily
range throughout; the days stop stacking and start overlapping.

That distinction is operational: a screen that waits for *ADR* to fall will wait forever on his
names, and one that ranks *by* falling ADR would rank his entries below quieter, worse ones.

**And the quiet is young when he buys.** Sessions the 5-bar range has been continuously inside
2 ADR: median **1**, p75 4, p90 8. 41.6% have a run of zero, and only 6.6% have been quiet for ten
sessions or more. Median distance since the 5-bar range was last wider than 2.5 ADR: **4 sessions**.
He is not buying the end of a long quiet stretch; he is buying a few days after the last expansion.

#### What the base is resting on, and how deep it is

| | p25 | median | p75 | censored |
| --- | --- | --- | --- | --- |
| Prior advance % (60-session cap) | 60 | **95** | 185 | 18.3% |
| Prior advance % (120-session cap) | 83 | **166** | 369 | 11.1% |
| Base depth from the pivot (%) | 18.1 | **30.6** | 48.6 | — |
| Base depth (ADR) | 3.45 | **5.78** | 10.19 | — |

Both length caps bind hard, so the advance reads as **"at least two to five months, at least a
doubling"** rather than as a point estimate; the magnitude is the solid part. The bases are not
shallow — a quarter give back half the pivot or more, which follows from the size of the move being
digested.

#### Outcome, and what it does and does not license

MFE under the 10sma exit, per §5a's convention. Across all 649: median MFE 4.5%, mean R +1.26,
R > 0 on 22.7%. Seeded 20,000-resample bootstrap on the median difference (MFE is heavily
right-skewed, so a t-test on these tails would be meaningless):

| Contrast | median MFE | p |
| --- | --- | --- |
| Quiet run ≥ 10 sessions vs rest (n=43) | 8.1 vs 4.2 | **0.006** |
| Prior advance ≥ 200% vs rest (n=154) | 7.6 vs 3.9 | **<0.001** |
| Base depth ≥ 50% vs rest (n=160) | 6.3 vs 4.0 | **0.001** |
| Base length 16–30 vs rest (n=110) | 5.4 vs 4.3 | 0.111 |

**Base *length* predicts nothing.** What carries signal is the size of the move being digested and
the duration of the quiet, not how old the structure is.

**No constant is touched, and none is licensed.** These are cuts on executed trades only, so none
is a precision measurement and §7/§9 stand unchanged; the advance and depth cuts are partly
tautological with his selection (he buys big movers, so "big prior advance" partly re-states "he
took it"); the strongest cut rests on n=43; and the regime caveat (§8) applies. The two candidate
dimensions this suggests — a quiet-run length and a prior-advance magnitude — would each need the
control group the study does not have before they could be scored.

---

### 3d. The recent 3 bars against the prior 3 (prototype, side-car) — real, redundant, outcome-blind

**Question.** §3b measured the *level* of the trailing 3-bar range and §3c the 90-session curve.
Neither asked the local question a screen could cheaply gate on: at the evaluation session, are the
**last 3 bars** quieter than the **3 immediately behind them**?

**What is new here — a partial control group.** Every result above is conditioned entirely on
trades he took, which is why §7/§9 keep repeating that precision is unmeasurable. This prototype
gets a *partial* control for free: **the same tickers on random ordinary days**. For each trade, 10
sessions of the same symbol are sampled within ±120 sessions, never within 5 sessions of any real
entry, seeded — **6,450 background sessions against 645 entries** (645 not 649: 4 more trades lack
the extra 3 bars of history this needs).

**This is not a false-positive rate and must not be cited as one.** "This stock on an ordinary day"
is not "a setup he passed over". It answers one narrower question exactly: *is a feature a property
of the entry, or just of the kind of stock he trades?* Every "lift" below means entry pass-rate ÷
background pass-rate on that question and nothing more. Produced by
`backend/replay/prototype-adr3/` on branch `worktree-prototype-base-length`; not part of §10.

> **Machinery cross-check.** The recent-3-bar span comes back at a median of **1.31 ADR** — §3b's
> committed k=3 median, to the digit, from an independently written path.

#### The contraction is real

| Feature | Entry p25 / **median** / p75 | Background p25 / **median** / p75 |
| --- | --- | --- |
| `adr3_ratio` — recent 3-bar avg daily range ÷ prior 3-bar | 0.69 / **0.89** / 1.10 | 0.77 / **0.99** / 1.29 |
| `span3_ratio` — recent 3-bar travel ÷ prior 3-bar | 0.57 / **0.78** / 1.08 | 0.70 / **0.99** / 1.43 |
| `vol3_ratio` — recent 3-bar avg volume ÷ prior 3-bar | 0.68 / **0.87** / 1.13 | 0.76 / **0.98** / 1.29 |
| Recent 3-bar span, in ADR | 1.00 / **1.31** / 1.73 | 1.34 / **1.74** / 2.32 |

The background sits at ~1.0 on every ratio, which is the sanity check working: a random day has no
reason to be quieter than the day before it. His entries sit below 1 on all three.

| Cut | Entry | Background | Lift |
| --- | --- | --- | --- |
| `adr3_ratio` ≤ 0.7 | 26.0% | 18.1% | 1.44× |
| `adr3_ratio` ≤ 0.9 | 51.8% | 39.3% | 1.32× |
| `vol3_ratio` ≤ 0.7 | 28.5% | 18.8% | 1.51× |
| **recent 3-bar span ≤ 1.5 ADR** (level, not ratio) | 64.3% | 34.4% | **1.87×** |
| **recent 3-bar span ≤ 1.0 ADR** (level, not ratio) | 25.0% | 7.7% | **3.25×** |

#### …and it adds nothing once the level is held fixed

If "recent quieter than prior" carried its own information, it would still lift inside a band where
the 3-bar span is roughly constant. Recomputed within span bands:

| Band | n (entry / bg) | `adr3_ratio` ≤ 0.7 | `adr3_ratio` ≤ 0.9 | `vol3_ratio` ≤ 0.7 | `vol3_ratio` ≤ 0.9 |
| --- | --- | --- | --- | --- | --- |
| span < 1.0 ADR | 161 / 496 | **0.90×** | **0.95×** | 1.06× | 1.05× |
| span 1.0–1.5 ADR | 254 / 1,723 | **0.94×** | **0.96×** | 1.04× | 1.02× |
| span 1.5–2.5 ADR | 202 / 2,978 | **0.85×** | **0.91×** | 1.04× | 0.89× |

**Every lift collapses to ~1.0, several below it.** The marginal 1.32–1.44× is the absolute
tightness of the last 3 days re-expressed — which the level already measures, and measures better.
Conditioned on the level, the change carries no extra information about whether he took the trade.

And it is outcome-blind: the bootstrap of §3c's form returns **p = 0.518** for `adr3_ratio` < 0.85,
**0.514** for `span3_ratio` < 0.8 and **0.527** for `vol3_ratio` < 0.7. Like §5a's dimensions, these
describe *what he buys*, not *which of his buys work*.

#### What this licenses

**Do not add a recent-versus-prior dimension.** It is real, redundant with the 3-bar level the
detector already gates on, and outcome-blind. This is a negative result recorded so the idea is not
re-proposed. `TIGHT_MULT`, `K_MIN` and `K_MAX` are untouched, and §3a/§3b's recommendations stand.

**What is worth carrying forward is the method, not the feature.** The same-name background sample
is cheap, seeded and reusable, and it supplied a redundancy test the study could not otherwise run:
*does this candidate still select his entries once the obvious correlate is held fixed?* Any future
dimension can be put through it before it is weighted. It remains bounded — same-name matched by
construction, so it says nothing about the wider universe; and its window straddles the entry, so
post-breakout expansion sits in the control, which makes the lifts conservative rather than
generous.

---

### 3e. What the 75 are made of, and what widening the gate is worth (#149)

**Question.** ADR 0003 made *widen the gate from three lookbacks to five* its leading
candidate on the strength of the 75-trade middle bucket above. But `1w` and `12m` are excluded
from `detection_gate` **on purpose** — `1w` as a momentum burst, `12m` as staleness — so 3→5
does not merely widen a gate, it reverses a stated rule. The 75 is a single number and cannot
say whether the reversal is worth it. `replay.gate_sweep` prices each width separately
(`references/detection_gate_sweep.txt` / `.json`; 821 measured sessions, **656** replayable
trades, 92 blind-spot tickers, detector **v2**). The sweep is read-only, and pins its own baseline to the
three-lookback width so it can still be re-run now that the verdict has moved the live one.

#### Every one of the 75 arrives through a deliberately excluded lookback

| Admitted by | Count | Share |
| --- | --- | --- |
| `12m` only | **49** | 65.3% |
| `1w` only | **22** | 29.3% |
| both | 4 | 5.3% |
| also by a lookback already gated | **0** | impossible by construction |

Seven of the 75 are continuation entries. Nothing arrives by `3m`/`6m` adjacency, because a
name top-decile in a gated window already clears the gate — so the widening's entire recall
gain is bought with the two windows the spec keeps out.

#### …but "admitted by `12m`" and "stale" turn out to be different populations

The exclusion's worry is a name that *topped out months ago and has done nothing since* — a
claim about recent ranks, not about which window admitted it. Measured:

| Group | n | dead on 1m/3m/6m | within reach of the cut | median 1m | median 3m | median 6m |
| --- | --- | --- | --- | --- | --- | --- |
| `12m` only | 49 | **1** | 29 | 0.475 | 0.628 | **0.798** |
| `1w` only | 22 | **8** | 3 | 0.517 | 0.194 | 0.356 |

*(dead = below the field median on **every** gated window; within reach = ≥80th percentile on
at least one.)*

**One of the 49.** The `12m`-only group sits at a median 6m percentile of 0.798 — just under
the cut, and quiet on 1m because it is *in a base*, which is the shape the detector exists to
find. The `1w`-only group is the opposite and is exactly what its exclusion describes: median
3m percentile 0.194, more than a third of it dead on every gated window.

The same holds field-wide, not only for his trades: of the detections each width **adds**,
**14.1%** are dead on the gated windows for `12m` against **35.0%** for `1w`. The window named
for staleness admits the less stale field of the two.

#### Field inflation, on #141's basis, against the funnel's own going rate

Precision is unmeasurable (§7, §9), so the cost is priced as **volume** — the same basis #141
sets for the cluster gate, so the funnel's two most expensive gates are comparable. The live
gate as measured spends **424.7 detections per entry surfaced** — 148,223 detections over 821
sessions for 349 entries — and that is the denominator a marginal cost has to be read against.

| Width | Universe | Decile recall (ex-cont) | Surfaced recall (ex-cont) | Added detections | Per recovered entry | Per surfaced entry | vs going rate | Board displacement | Stale share of added |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `1m/3m/6m` (as measured) | 19.3% | 395/656 (60.2%) / (58.9%) | 349/656 (53.2%) / (52.3%) | — | — | — | — | — | — |
| `+1w` | 24.2% | 421/656 (64.2%) / (62.9%) | 361/656 (55.0%) / (54.4%) | 17,842 | 686.2 | 1,486.8 | **3.50×** | 967 | 29.9% |
| **`+12m`** | **21.9%** | **448/656 (68.3%) / (67.4%)** | **397/656 (60.5%) / (60.0%)** | 27,323 | 515.5 | 569.2 | **1.34×** | 1,832 | 13.4% |
| five (3→5) | 26.5% | 470/656 (71.6%) / (70.7%) | 409/656 (62.3%) / (62.0%) | 43,430 | 579.1 | 723.8 | 1.70× | 2,571 | 20.1% |

*Three bookkeeping notes on this table.*

**The universe shares.** 19.3% and 26.5% are the same gates quoted at **19.4%** and **27.2%**
earlier in this section and in ADR 0003, over a different window: the sweep recomputes the rank
table in memory and covers all **821** measured sessions, where those figures covered the
**505** the store still held rank rows for. The gates are identical; the windows are not.

**The field volumes are detector v2** (#154's graded base tightness) and are not comparable
with anything measured under v1 — including the **14,239** that #141's ticket names as the
baseline to price against. That is why the "going rate" here is the sweep's own baseline rather
than that number: a marginal cost divided by an average from a different detector is not a ratio
of anything.

**The baseline row reproduces A2 exactly, and that is a cross-check rather than a coincidence.**
On A2's own basis — the sessions his trades were evaluated at — this sweep's baseline width
gives **54,399** detections, **349/656** in the field and **109/656** on the board: the same
three figures §4a reports. The two arrive independently. The sweep reconstructs the chain and
recomputes every session's ranks in memory; A2 reached the same place only once #141 stopped the
detection pass reading ranks from the store, where retention had pruned them. Both paths now
agree to the digit, which is the strongest statement either can make about the other.

Detection recall itself is **gate-invariant** — each stage is evaluated unconditionally — and
is 549/656 (83.7%), ex-continuation 487/577 (84.4%), at every width. *Surfaced* recall is the
joint decile ∧ detection figure: what the app would actually have shown. **The board barely
moves:** his own entries hold 109 of the top thirty under the gate as measured and 111 under
`+12m`, and the 1,832 places that change hands are spread over 821 sessions.

**Field inflation is a volume measure and never a false-positive rate.** The added names carry
no verdict; they are names he may never have seen (cf. the not-taken comparison group, §5b).

#### The two halves of 3→5 recover opposite kinds of trade

R is fat-tailed here — **every** group's median R is −1.00 — so the mean is a statement about
one name. The trimmed mean drops the top 5% of each group; the tail rate is where a breakout
method's edge lives.

| Group | n | mean R | trim-5% R | win rate | R≥3 rate | best trade's share of R | mean MFE% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| passing `1m/3m/6m` | 395 | 1.37 | 0.03 | 25.1% | 16.8% | 19.2% | 18.2 |
| recovered by 3→5 (all 75) | 75 | 0.91 | −0.36 | 17.3% | 13.3% | 95.1% | 9.5 |
| …`12m` only | 49 | 1.87 | 0.12 | **24.5%** | **20.4%** | 70.7% | 10.3 |
| …`1w` only | 22 | −0.88 | −0.99 | **4.5%** | **0.0%** | — (no net R) | 8.5 |
| …both | 4 | −1.00 | −1.00 | 0.0% | 0.0% | — | 5.5 |

**The `12m` half recovers trades indistinguishable from those the gate already passes.** The
`1w` half recovers 22 trades that won 4.5% of the time, not one of which reached 3R. The
blended "75 recovered" averages a defensible widening with an indefensible one.

#### Verdict: 3→5 rejected; `12m` adopted; `1w` refused on evidence

`DETECTION_LOOKBACKS` is now `("1m", "3m", "6m", "12m")`. ADR 0002's four conditions for
loosening a cross-sectional cut are met, and the population cost is stated: **2.6 points of
universe and 27,323 detections for 53 recovered entries, 48 of them surfaced.** The §4.5
exclusion is amended rather than ignored — `12m` was excluded on a prediction about what it
would admit, the prediction was measurable, and it was wrong. The reasoning is in
`docs/adr/0003-the-decile-gate.md` (amendment).

**What this does not claim.** Precision is still unmeasurable: 27,323 added detections are
27,323 names carrying no verdict, not 27,323 false positives — the out-of-sample backtest is
what prices them. n = 49 is small and 70.7% of its R is one trade, so the claim rests on
*absence of harm*, not on the recovered group being better. §2's coverage hole bounds this
like everything else. Scope is US 2019–2022.

**The earlier figures in this section are left as measured** under the three-lookback gate.
They are the evidence this verdict was reached from, and rewriting them to the new width would
destroy the record of what was decided and why. `references/replay_study_report.txt` and
`replay_study_results.json` likewise predate the change.

---

### 3f. How big the prior move actually is, and how much of it was the tape (prototype, side-car)

**Question.** `Prior move` is the one criterion this study has never been able to measure. Every
detection clears the decile gate by construction, so the dimension reads 100% in every group the
study can build, its spread is 0.000, and §5a/§5b can say nothing about it (§9 records this as a
standing limitation). The only handle found so far was a *proxy* — distance above the SMA50 in ADR
units, from the entry-to-MA study ([`qullamaggie-entry-ma-distance.md`](qullamaggie-entry-ma-distance.md)
§5). The quantity the gate is nominally about — the raw `1w/1m/3m/6m/12m` return standing behind
each entry — had never been taken at all.

**Method.** 582 of 828 logged breakout longs (70.2%) joined to daily bars: `data/screener.duckdb`
US `adj_close` first, the delisted remainder from the Yahoo cache the entry-to-MA study built.
Returns use the rank table's own definition — calendar-anchored `adj_close` ratios, `anchor_date`
transcribed from `screener/indicators.py` — measured **through the session strictly before entry**,
since at a 09:42 median entry the entry day's return is not on screen at the click. Skips: 153 with
no bar data, 77 whose logged fill fits no split ratio inside the entry day's range (the
recycled-symbol guard), 16 under 25 bars of history. Benchmarks are `QQQ` and `^IXIC`
(`MARKET_INDEX`), read on the name's own prior session; relative return is compounded,
`(1 + stock) / (1 + index) − 1`, because over these horizons a percentage-point difference and a
multiple are different quantities and only the second means "outran the market".

Produced by a **throwaway prototype**, not by `replay.study`:
`.scratch/screening-dashboard/prototypes/prior-move-at-entry/` (see that directory's `FINDINGS.md`).
**Not** part of the reproducible study in §10 — the figures are checkable by re-running
`prior_move_at_entry.py`. Preliminary in the sense of §6.

> **Machinery cross-check.** The same-name background is §3d's device, re-implemented here: same
> tickers, random ordinary days in the same window, one draw per entry, quarantined ±21 bars around
> his own entries. It is not a control group of rejected setups, so nothing below is a precision
> figure.

#### The prior move is a 3-to-12-month object, and the last week is not part of it

| Lookback | n | median % | mean % | p25 | p75 | p95 | negative | median ×ADR | ordinary day, median % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `1w` | 582 | **0.3** | 1.2 | −2.6 | 4.0 | 13.9 | 46.4% | 0.06 | 0.1 |
| `1m` | 582 | **7.0** | 17.1 | −1.7 | 20.2 | 84.5 | 28.2% | 1.32 | −0.1 |
| `3m` | 576 | **23.8** | 51.3 | 3.6 | 63.8 | 227.9 | 21.2% | 4.14 | −5.1 |
| `6m` | 567 | **55.8** | 105.4 | 15.1 | 124.0 | 370.7 | 16.8% | 10.60 | −11.2 |
| `12m` | 531 | **119.3** | 233.1 | 29.1 | 254.7 | 904.1 | 16.0% | 22.91 | 0.4 |

The median entry sits on a +56% six-month and +119% twelve-month advance, with means at roughly
twice the medians — the right tail carries it, which is the shape the method predicts and the reason
`ranks.py` ranks on pure return rather than a risk-adjusted one.

Against the same-name background the entry-vs-ordinary gap in ADR units runs +0.02 (`1w`),
+1.34 (`1m`), +5.25 (`3m`), **+12.41 (`6m`)**, +22.83 (`12m`). The `12m` gap is larger but noisier:
an ordinary day's `12m` median is +0.4%, so that column is set by a handful of ten-baggers.

The move is also not a uniform requirement. 26.8% of entries are positive on all five lookbacks,
35.1% on four, 9.1% on two or fewer, and **16.0% carry a negative twelve-month return** — which is
what a percentile gate permits and an absolute one would not.

#### QQQ takes about a third of it, and the selection survives

| Lookback | stock median | `QQQ` median | relative median | beats `QQQ` | ordinary day beats `QQQ` | `^IXIC` check |
| --- | --- | --- | --- | --- | --- | --- |
| `1w` | +0.3% | +0.9% | **−0.3%** | 48.1% | 49.1% | 47.9% |
| `1m` | +7.0% | +4.4% | **+4.3%** | 63.4% | 46.5% | 63.7% |
| `3m` | +23.8% | +7.8% | **+15.6%** | 73.2% | 38.0% | 73.4% |
| `6m` | +55.8% | +16.9% | **+35.0%** | **74.2%** | 37.8% | 75.1% |
| `12m` | +119.3% | +39.7% | **+59.9%** | 67.5% | 40.2% | 69.4% |

`QQQ` itself was up 39.7% median over the twelve months before his entries. Netting it out still
leaves +59.9% median relative on `12m` and +35.0% on `6m`, and 74.2% of entries beating the index
over six months against **37.8%** of the same names on an ordinary day. `^IXIC` reproduces every row
within two points, so none of this is a benchmark artefact.

**`6m` is the sharpest window against the index, not `12m`.** The raw `12m` number is larger but its
beat-rate is *lower* (67.5% against 74.2%), and 26.0% of entries underperformed the index over the
year. Read with the ADR-unit gaps above, `3m`–`6m` is where index-relative strength and his own
selection agree most closely.

#### The `1w` exclusion now has a third, independent line of evidence

ADR 0003 excludes `1w` from `detection_gate` on the reasoning that a name top-decile in the last week
alone is a momentum burst; #149 priced the exclusion on the gate sweep. His own trades say the same
thing twice more, from outside that argument entirely: the `1w` return at his entries is +0.3% median
with 46.4% of entries *down* on the week, and the `1w` beat-rate against `QQQ` is **48.1%** against an
ordinary day's 49.1% — a coin flip on both panels. This is the confirmation a future proposal to
re-admit `1w` has to answer, and it is recorded here so the proposal starts from it.

#### Joined to base age: the flat week is the base, for 62.5% of entries (#172)

The reading above — "he buys the quiet end of the base" — held two facts side by side without joining
them: §3c's base age on 649 rows, the `1w` return on 582. A +0.3% median is equally consistent with
weeks up 10% and down 10% that cancel. So base age was measured on this prototype's own rows, on the
same evaluation session the returns use — §3c's **D1**, sessions from the highest high of the trailing
120, transcribed from `measure_base.py` and pinned by a unit check before use.

> **Machinery cross-check.** D1 on this independently built 582-row set: median **24.5**, p25 **11**,
> p75 **62**, censored **2.6%**, bands **11.9 / 42.3 / 20.3 / 25.6%**. §3c, on its own 649 rows:
> 24, 11, 63, 2.8%, 12.0 / 42.4 / 19.3 / 26.3%. Every column agrees within a point. Two row sets, two
> measurement paths.

| Base age | n | share | median `1w` % | 95% CI | down on the week | ordinary day, same band |
| --- | --- | --- | --- | --- | --- | --- |
| ≤5 sessions | 69 | 11.9% | +1.61 | [−0.27, +3.73] | 43.5% | +3.42% |
| 6–30 | 246 | 42.3% | **−0.04** | [−0.71, +0.40] | 50.4% | −0.35% |
| 31–60 | 118 | 20.3% | **−0.28** | [−0.59, +0.88] | 51.7% | −1.27% |
| >60 | 149 | 25.6% | +1.73 | [+0.87, +2.45] | 36.9% | −0.86% |

CIs are a seeded percentile bootstrap (5000 draws). **The pooled +0.3% is a mixture over bases, not
over weeks.** In the two bands holding the modal entry — 6–30 and 31–60 sessions, **62.5% of
entries** — the week is *flatter* than pooled, both CIs straddle zero, and more than half of entries
are down on the week. The correction runs opposite to the one #172 anticipated: dropping the tails
sharpens the finding rather than dissolving it.

The tails are two different animals, both up on the week. The **>60 band** is the only one
significantly positive (+1.73%, CI clear of zero) — and its `3m` median is **−3.3%** against +44.5%
in the 6–30 band, its `6m` **+2.7%** against +77.8%. A stale 120-session high means no recent advance
to base out of, and there the entry week *is* the move; these are a different setup under the same
label. The **≤5 band** is partly definitional — a base age under a week means the trailing-120 high
was just made — and what stands out is how weak it is against that mechanism: +1.61% where ordinary
days at the same base age run +3.42%.

**The beat-rate survives the confound this exposed.** His entries break out of far younger structures
than an ordinary day sits in — base age median 24.5 against **75** — so §3f's 48.1%-vs-49.1% compared
two different base-age mixes. Re-scored band by band against ordinary days of the same base age, the
gaps are +3.3 (6–30), +6.7 (31–60) and +5.5 pp (>60), **every one inside two standard errors**
(12.1, 14.6, 9.8). The one real difference is the ≤5 band at −23.9 pp (2 s.e. 17.2): a random day
whose 120-session high is under a week old is a day inside a burst and beats the index 76.1% of the
time, where his own ≤5 entries manage 52.2%. Even buying a fresh high, he buys it flatter than the
day itself would suggest.

So the sentence this section can now defend per trade, rather than by inference across two
denominators, is the narrower one: **for entries breaking out of a 6-to-60-session structure, nothing
about the prior week distinguishes it from any other week, and roughly half are down on it.** For the
quarter of entries whose base is older than the lookback can see, the week is up — but so is nothing
else about them, and that band is a population question this study has not otherwise asked.

Measured by the same prototype (`prior_move_at_entry.py`, `report_base_age`); the base-age definition
is unit-checked in `test_base_age.py`.

#### Outcome, and what it does and does not license

Quartiled within each lookback, scored on the logged 10sma exit. Spearman is Pearson on the ranks —
scipy is not in the venv and a prototype is not a reason to add one.

| Lookback | ρ(move, R) | Q1 mean R | Q2 | Q3 | Q4 |
| --- | --- | --- | --- | --- | --- |
| `1m` | **−0.073** | 1.98 | 0.84 | 0.44 | 0.97 |
| `3m` | +0.059 | 0.60 | 1.07 | 0.24 | 2.38 |
| `6m` | +0.037 | 0.43 | 1.11 | 0.68 | 2.16 |
| `12m` | +0.016 | 0.67 | 0.87 | 1.08 | **1.97** |
| relative `6m` | +0.042 | 0.54 | 1.11 | 0.57 | 2.16 |
| relative `12m` | +0.019 | 0.61 | 0.71 | 1.33 | 1.95 |

The signs split exactly as the entry-to-MA study's did, and by the same mechanism: a large *recent*
move means an extended entry and a wide stop (§7 kills the trade), while a large *long-horizon* move
is the advance being digested. Netting out the index changes almost nothing, so the tape neither
produced these signs nor hid them.

**No constant is touched, and none is licensed.** All six correlations are weak (|ρ| ≤ 0.073) and the
quartile means are carried by a few large winners. These are cuts on executed trades only, with no
control group, so §7/§9 stand unchanged. What the section establishes is narrower and is the point:
**the quantity `Prior move` gates on has real, measurable spread once expressed continuously**, and
the favourable direction is the long lookbacks. That is the limb ADR 0005 requires and the binary
dimension cannot reach.

**The regime bound, stated once so later work can cite it.** `QQQ` was negative over the trailing
twelve months on **1.7%** of his entry dates. This record holds essentially no bear-market `12m`
observations, so any index-relative dimension fitted on it is fitted to one regime. §8's caveat
applies with full force, and #141/#149's pricing discipline applies to any dimension proposed from
here.

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

### Reported — **rubric v1** (the rubric live when A2 was first measured)

Every star figure in this section is **rubric v1**, the ten-point table superseded by #138.
Nothing here may be compared against a v2 figure without the stamp; §4a is the paired
measurement that makes the comparison legitimately.

| Result | Value |
| --- | --- |
| Appeared in the field at all (`in_field`) | **104/658 (15.8%)** |
| Landed inside the top 30 by star score (`top_thirty`, board size from `screener.boards.BOARD_SIZE`) | **41/658 (6.2%)** |

`in_field` is a property of the *field*, not the rubric — a name is present or it is not,
whatever the weights say — so it is the one figure here that survives a rubric change
unchanged. `top_thirty` does not: the board is a re-ranking (§4a).

> **The `in_field` anchor is re-pinned by #154: 104 → 159 of 656 (24.2%).** `in_field`
> survives a *rubric* change and not a *detector* one — it is exactly the figure the
> far-outlier guard moves, because the guard decides who is in the field at all. The rest of
> this section is **left at its v1 measurement and is not restated**: it is the record of what
> the ten-point rubric did to the field as it stood, and re-running it against a doubled field
> would answer a different question than the one §4 asked. Two figures from the re-run belong
> here because downstream work anchors on them:
>
> | | Detector v1 | Detector v2 (#154) |
> | --- | --- | --- |
> | His trades in the field (`in_field`) | 104/658 (15.8%) | **159/656 (24.2%)** |
> | The field itself, same sessions | 14,239 detections | **29,096** (+104%) |
> | Inside the top 30 (`top_thirty`, live rubric) | 45/104 (43.3%) | **45/159 (28.3%)** |
>
> Read the last row carefully, because it is the change's cost and benefit in one line: the
> **same 45 of his trades reach a board**, out of half again as many that are now detected at
> all. The 55 newly-visible picks land below the top 30 — which is the graded rubric doing
> what it was built to do, sorting the wider bases downward rather than gating them out, but
> it is also a plain statement that the board did not get better at surfacing his entries. The
> gain is that 55 more of them exist somewhere on the list instead of nowhere.

> **Corrected after the retention defect was found and fixed: `in_field` is 349 of 656, and
> the top-thirty count is 109, not 45.** The block above is left standing as the record of what
> was believed when #154 landed, but every figure in it was computed on a field that was
> **empty on 316 of the 821 measured sessions**, so all three of its "Detector v2" numbers are
> understated. See the subsection below for the defect. Re-run on the same store with the same
> detector, the fix applied:
>
> | | Detector v2, truncated field | Detector v2, whole field |
> | --- | --- | --- |
> | Sessions contributing any detection | 505/821 | **821/821** |
> | His trades in the field (`in_field`) | 159/656 (24.2%) | **349/656 (53.2%)** |
> | The field itself, same sessions | 29,096 | **54,399** |
> | Inside the top 30 (`top_thirty`, live rubric) | 45/159 | **109/349** |
>
> **This reverses the reading of the block above, which is why it is corrected rather than
> footnoted.** That block's load-bearing sentence — "the **same 45 of his trades reach a
> board**" — was the observation that #154 bought visibility without buying board places. On
> the whole field it is **109**, not 45. The graded rubric does surface materially more of his
> entries on the board the trader reads; the earlier conclusion was an artefact of two thirds
> of the board-sessions being missing from the measurement. The cost side is unchanged in
> direction — the field roughly doubles — and nothing here disturbs ADR 0004 or the A1 recall
> figures, which never read the store's rank rows and reproduce to the digit.

#### The defect: rank retention silently emptied the replayed field on 316 of 821 sessions

**What happened.** The replay's detection pass gated on the **store's** rank rows
(`screener.pipeline.rebuild_detections` → `Store.ranks`). `Store.append_ranks` keeps only
`RANK_RETENTION_YEARS = 2` and prunes as the chain advances, and `replay.study` builds the
*whole* 947-session chain before the detection pass runs. So by the time detection reached a
measured session older than two years before the chain's end, that session's rank rows were
already gone; `detection_gate` received an empty table, every member fell out, and the session
contributed nothing to the field — while looking exactly like a night that legitimately found
no setup.

It was invisible for three reasons worth naming, because they are what a similar defect will
hide behind next time. Nothing errored. The behaviour is deterministic, so re-runs agreed with
each other and the result looked stable. And `_session_detections` had a docstring explicitly
reasoning that an empty session reproduces deterministically — the retention interaction was
noticed and read as harmless.

**The fix.** `rebuild_detections` takes the session's rank table as an optional argument, and
the replay hands it the **chain's own ranks** — which the chain already recomputes in memory
per session for exactly this reason, and which the A1 funnel already reads its decile verdicts
from. The nightly run passes nothing and is unaffected: it detects the session it just ranked,
whose rows are always present. Pinned by
`test_field_detects_on_a_session_whose_stored_ranks_were_pruned`.

**How the diagnosis was confirmed.** Before the fix, gating on the store reproduced the
committed figures *exactly* — 505/821 sessions, 14,239 field detections on his evaluation
sessions, 104 `in_field`, 45 `top_thirty` under detector v1 — while gating on the chain's
ranks over the same chain gave 821/821, 27,116, 242 and 112. An exact reproduction of the
published numbers by the broken path is what establishes the cause, rather than a plausible
story about one.

**What this does and does not touch.** A1 is untouched in principle and in fact: the funnel
reads the chain's ranks and always did, and every A1 figure in §3 reproduces to the digit
across the fix. §4's historical rubric-stamped tables are left alone — they are the record of
what each rubric did to the field as it then stood. What changes is any figure describing how
much of the field existed, and every one of those is restated above.

**One thing this left open, and #165 closed.** The discrimination result — "the rubric does
not discriminate his picks from the field", **17.3% vs 17.8%** at ≥3.5★ — is computed over
this same field. Recomputed under rubric v1 on the whole field the run above gives **14.6%**
against **12.6%**, a +2.0pp edge where the published pair shows −0.5pp — but two changes are
confounded in that figure (the detector moved v1 → v2 with #154, and the truncation was fixed
here), so it corrects nothing. #164 marked §4/§5's discrimination figures pending rather than
restating them. **§4b separates the two changes and restates them**, and the answer is not the
one the confounded figure suggested: with the detector held at v1, the fix moves the pair to
**17.4% / 19.8%**, a gap of **−2.46pp**. §4's null hardens on the whole field.

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

**Picks at ≥3.5 stars: 17.3%. Field at ≥3.5 stars: 17.8%.** (Rubric v1, on the **truncated**
field — the pair as published. Under the live v2 rubric, on this same field, the gap opens to
+5.6pp — §4a, which is where this conclusion is revised. On the **whole** field with the
detector held at v1, the pair is **17.4% / 19.8%** and the gap widens to −2.46pp — §4b, which
is where the truncation is taken out of it.)

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

## 4a. A2 re-run — the paired measurement (#136)

**Question.** #136 asked to re-run A2 once the field was no longer missing a quarter of its
names, and warned that #138's reweight would move the rubric underneath it — so a naive re-run
would change two variables and attribute the result to neither.

**One of those two variables is now permanently frozen.** #129, which was to source
delisted/renamed bar history, is **closed won't-do**: every provider carrying that history is
paid, retail tiers start near $100/month, and there is no budget. The free tiers give listing
*identity*, never prices. So the fuller field is not late — it does not exist, and the §2 hole
is a permanent property of the study rather than a gap awaiting a ticket. The half of #136 that
depended on it cannot be delivered and is not deferred; it is closed.

What that leaves is the other half, and it is now clean rather than confounded: with the field
frozen, the rubric is the **only** variable, so the pairing measures it alone. The run is
`python -m replay.study` over the built `replay.duckdb` — one chain, one detection pass, the
same field scored and re-ranked under both rubrics (`PlacementReport.by_rubric`).

### The v1 block reproduces the committed result exactly

Before reading the v2 column, note that the v1 column is a **cell-for-cell reproduction** of
§4 above — 17.31% / 17.82%, 41/658 inside the board, and every one of the nine histogram rows.
That is the control: the field is demonstrably the same field §4 measured, so any v2 difference
is the rubric and nothing else.

> **The pairing survived a graded dimension (#154).** v3 grades `Tightness` on a real value
> instead of a boolean, which would have broken this measurement outright had the *grade* been
> stored on the breakdown row: a v2 re-score of a v3 row would then be impossible, and the
> comparison below would be silently comparing two fields while claiming to compare two
> rubrics. The row stores the **value** and the rubric owns the mapping, so a stored breakdown
> still re-scores exactly under every version — v2's `cluster_k >= 5` boolean is on the row
> too, unchanged and unread by v3.
>
> The block below is **left as measured**, on the detector-v1 field. On the re-run field
> (detector v2, all three rubrics over one field, `in_field` 159):
>
> | Result | v1 | v2 | v3 (live) |
> | --- | --- | --- | --- |
> | Inside the top 30 | 31/159 | 43/159 | **45/159** |
> | His picks at ≥3.5★ | 13.21% | 9.43% | **11.32%** |
> | The field at ≥3.5★ | 11.06% | 4.32% | **6.75%** |
> | Gap (picks − field) | +2.14pp | **+5.11pp** | **+4.57pp** |
>
> On a field twice the size, v3 keeps most of v2's discrimination (+4.57pp against +5.11pp)
> and puts two more of his trades on a board. The gap being *slightly* narrower than v2's is
> not a defect to tune away: v3 is separating his picks from a population that now includes
> every wider base v2 never had to rank at all.

### Reported — same field, both rubrics

| Result | **v1** (superseded) | **v2** (live, #138) |
| --- | --- | --- |
| Appeared in the field (`in_field`) | 104/658 (15.8%) | 104/658 (15.8%) — rubric-invariant |
| Inside the top 30 (`top_thirty`) | **41/658 (6.2%)** | **45/658 (6.8%)** |
| His picks at ≥3.5★ | **17.31%** (18/104) | **14.42%** (15/104) |
| The field at ≥3.5★ | **17.82%** (2,538/14,239) | **8.83%** (1,258/14,239) |
| Gap (picks − field) | **−0.52pp** | **+5.59pp** |
| Exact binomial p (picks ≥3.5★ vs the field rate) | 1.000 | **0.055** |
| Mean stars, his picks | 2.486 | 2.495 |
| Mean stars, the field | 2.400 | 2.214 |

Full histograms, both stamped (picks n=104, field n=14,239 under either rubric — the same
detections, only the weights move). These are seven-dimension scores, so the ceiling is **4.5★
under v1 and 4.0★ under v2**, not the app's 5.0/4.5 — see the note below the table:

| Stars | v1 picks | v1 field | | v2 picks | v2 field |
| --- | --- | --- | --- | --- | --- |
| 4.5 | 4 (3.8%) | 324 (2.3%) | | — | — |
| 4.0 | 5 (4.8%) | 1,049 (7.4%) | | 4 (3.8%) | 342 (2.4%) |
| 3.5 | 9 (8.7%) | 1,165 (8.2%) | | 11 (10.6%) | 916 (6.4%) |
| 3.0 | 20 (19.2%) | 2,822 (19.8%) | | 22 (21.2%) | 2,531 (17.8%) |
| 2.5 | 25 (24.0%) | 2,533 (17.8%) | | 36 (34.6%) | 3,014 (21.2%) |
| 2.0 | 22 (21.2%) | 2,394 (16.8%) | | 15 (14.4%) | 3,259 (22.9%) |
| 1.5 | 10 (9.6%) | 2,129 (15.0%) | | 9 (8.7%) | 2,649 (18.6%) |
| 1.0 | 6 (5.8%) | 1,511 (10.6%) | | 4 (3.8%) | 1,132 (7.9%) |
| 0.5 | 3 (2.9%) | 312 (2.2%) | | 3 (2.9%) | 396 (2.8%) |

**`>3.5★` does not mean what it meant.** These are *seven-dimension* scores: the replay strikes
`Sector` (§1, #130), so the ceilings behind both columns are the app's minus that row — **9
points under v1 and 8 under v2**, not 10 and 9. So ≥3.5★ is 7 of 9 in the v1 column and 7 of 8
in the v2 one, and the top bucket falls from 4.5★ to 4.0★ between them. That drop is the net of
three weight moves, not the zeroed `Base length` alone: Orderliness −1, Base length −1, ADR +1.
This is why the full histogram is reported and not only the top share — the v1→v2 move in the
≥3.5 share is partly a move in what the threshold *is*. The gap between his picks and the field
**on one scale** is the comparison that survives this; the level does not.

### Verdict: the ranking conclusion is **weakened, not reversed**

§4's null — *no evidence the star score ranks his picks above the field* — was measured under
v1 and remains exactly true under v1. Under v2 it no longer holds in the same form: his picks
sit at ≥3.5★ at **1.63× the field's rate** (14.4% vs 8.8%), the board hit rises 41→45, and the
direction is the one a discriminating rubric would produce. **The §4 statement may no longer be
quoted without its v1 stamp**, and this is a revision of that conclusion, not a restatement of
it.

It is **not** reversed into "the ranking is validated", for three reasons that are each
sufficient on their own:

1. **It is in-sample, and close to circular.** v2's weights were derived from §5b's selection
   contrast — taken vs not-taken detections — measured over *these* 69 taken detections on
   *this* field. A2 then asks whether those weights separate taken from not-taken on the same
   field. A rubric fitted to a separation will reproduce that separation; this is a fit
   statistic dressed as a test, and the only honest reading is "the reweight did what it was
   built to do", not "the rubric ranks".
2. **It is marginal even so.** Exact binomial p = 0.055 on n=104 — a positive result that,
   fitted in-sample, still fails to clear the conventional threshold.
3. **The field is still missing 29% of its names.** The coverage bound below did not improve
   and never will.

**The mechanism: the field fell, his picks did not rise.** Mean stars moved **+0.010** for his
picks and **−0.187** for the field — the reweight did not recognise his entries, it demoted the
population around them. That is exactly the shape §5b predicts (he hits `Base length` and
`Orderliness` *less* than the field he passed over, so zeroing one and halving the other costs
the field more than it costs him), and it is a weaker claim than "the rubric found his picks".
The measured picks-minus-field shift is **+0.196 stars** against §5c's computed expectation of
**+0.19** — agreement to about a hundredth of a star, so the arithmetic prediction was right,
and the ≥3.5★ share it declined to predict has now been measured.

### Coverage, restated so this result carries its own bound

Unchanged and now permanent: **92 blind-spot tickers / 172 trades / 18.0% of total realised R**
(§2), and only **104 of 658** replayable trades appeared in the field at all — **41** inside the
board under v1, **45** under v2. So this is a rubric comparison measured on a **sixth of his
record** against a field missing a quarter of its names, and the population missing is the one a
momentum screener surfaces. #139 has now **landed**: the coverage figures above are the
re-pinned ones (they were 91 / 170 / 18.15% when this run was measured), and the 658-trade
denominator is the pre-#139 one — `FUSE`'s 2 trades leave it at 656. That correction moves
nothing here, and the per-trade figures below are the ones this run measured.

**The no-percentile constraint stands, permanently.** #136 said to keep it "unless the coverage
hole is fully closed". With #129 closed won't-do the hole cannot be closed, so the constraint is
no longer conditional: no percentile and no rank position is emitted, only the top-thirty hit
and the star histogram.

_Reproduce: `python -m replay.study --store data/replay.duckdb`, which writes
`references/replay_study_report.txt` and `references/replay_study_results.json` — both committed
beside this document. The store's derived tables must be empty; bars are the only input a chain
reads (write-once rows from an earlier pass are read back, not recomputed)._

---

## 4b. The discrimination pair, with the two changes separated (#165)

**Question.** §4's pair — picks **17.3%** against field **17.8%** at ≥3.5★ — was measured under
detector v1 on the field the rank retention had truncated. #164 fixed the truncation and
reported that the same rubric on the whole field reads **14.6% / 12.6%**, an edge *in his
favour* where the published pair has him fractionally behind. It also said, correctly, that the
figure corrects nothing: the detector had moved v1 → v2 with #154 in the same interval, so two
variables moved between the two pairs and the movement is attributable to neither. This is the
re-derivation that separates them.

**Method.** The pair is re-measured at each detector version against each field, so exactly one
variable moves between any two cells read against each other. One read-only pass reconstructs
the forward chain from the universe rows the store holds with the ranks recomputed in memory —
`replay.gate_sweep`'s own path, nothing written back — and every cell is derived from that one
detection pass by filtering it. Two identities make that sound rather than convenient:

- **v1's field is a filter on v2's.** `detection._find_cluster` records it: the restructure
  grades what it used to gate, so a name inside the old 1.5×ADR cut keeps the same `k`, trigger
  and span under the guard. Striking the rows past 1.5 reconstructs the older population
  exactly, and the reconstruction is checkable — the committed store still holds the 45,600
  `detector_version = 1` rows that pass emitted, and the v1/truncated cell reproduces that count
  **to the row**.
- **The truncated field is the whole field restricted to the retained sessions.** A pruned
  session gated against an empty rank table, so it dropped every member: the truncation removed
  whole sessions rather than thinning them. The retained set is read off the store's own `ranks`
  table (505 sessions, 2020-12-30..2022-12-30) and handed in as a parameter.

### The grid — all rubric v1, the rubric §4's pair was published under

| Detector | Field | `in_field` | Field, his eval sessions | Detections / measured session | Picks ≥3.5★ | Field ≥3.5★ | Gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v1 | truncated | 104/656 | 14,239 | 55.5 (90.3 per contributing) | 17.31% | 17.82% | **−0.52pp** (as published) |
| v1 | whole | 242/656 | 27,116 | **83.6** | 17.36% | 19.81% | **−2.46pp** |
| v2 | truncated | 159/656 | 29,096 | 124.0 (201.6 per contributing) | 13.21% | 11.06% | +2.14pp |
| v2 | whole | 349/656 | 54,399 | **180.5** | 14.61% | 12.59% | +2.02pp |
| v3 (live) | whole | 397/656 | 64,070 | 213.8 | 13.60% | 11.65% | +1.95pp |

The per-session column carries both denominators, because the superseded 90.3 and 201.6 were
taken over the 505 sessions that survived the retention rather than the 821 measured — the two
truncated rows reproduce them exactly on that denominator, which is what identifies the
superseded figures as arithmetic on a partial field rather than a different measurement.

**The grid is checked against the record, not merely computed.** Four of the five cells have a
committed figure to reproduce and every one of them reproduces to the digit: §4's own
104 / 14,239 / 17.31 / 17.82 and its board hit of 41; §4a's inset block for the v2 truncated
field (159 / 29,096, and 13.21 / 11.06, 9.43 / 4.32, 11.32 / 6.75 across the three rubrics, with
31 / 43 / 45 on the board); #164's 349 / 54,399 and the committed report's rubric-v1 board hit of
78; and #164's own v1-on-the-whole-field diagnostic of **242 / 27,116**. The fifth cell is the
first measurement of `in_field` under the width #149 adopted.

### The two one-variable steps

**The retention fix alone — detector held at v1.** 17.31% / 17.82% → **17.36% / 19.81%**. His
picks do not move (+0.05pp); the **field's** share rises by 1.99pp. The gap goes from −0.52pp to
**−2.46pp**.

The mechanism is in *which* sessions were missing, and the grid measures it rather than leaving
it to be inferred — the **"what the deleted sessions held"** block of
`references/discrimination_grid.txt` reports it with its counts:

| On the 316 sessions the retention emptied | ≥3.5★ | Total | Share |
| --- | --- | --- | --- |
| His picks | 24 | 138 | **17.39%** |
| The field | 2,834 | 12,877 | **22.01%** |

On the 505 retained sessions the same two shares are 17.31% and 17.82%. So the population he
was being compared against was **materially stronger on the sessions the bug deleted**, and his
own picks were not. That is why cutting both sides on the same sessions still biased the
comparison, and biased it in the rubric's favour. §4 was right that both sides were truncated
together; that is not sufficient for the comparison to survive, and here it did not.

**The detector restructure alone — on the whole field.** −2.46pp → **+2.02pp**. The whole of the
edge #164 flagged is this step. It is also the mechanism §4a already named, arriving through the
detector rather than through the weights: the far-outlier guard admits ~80,000 detections whose
3-bar range sits past 1.5×ADR, rubric v1 scores `Tightness` off `cluster_k >= 5` and those names
miss it, so the field's ≥3.5★ share falls from 19.81% to 12.59% while his picks fall less
(17.36% → 14.61%). **The field fell; his picks did not rise** — the same sentence §4a wrote about
the reweight.

### Verdict — §4's null stands, and hardens

**The negative result is not weakened by the retention fix; it is strengthened.** On the whole
field, under the rubric and detector §4 published with, his hand-picked entries reach ≥3.5★
**less** often than the population they were drawn from — 17.4% against 19.8%, a gap two and a
half times the published one and in the same (unfavourable) direction. Nothing in this grid
supports reading §4's null as an artefact of the truncation.

**§4a's verdict — weakened, not reversed — survives the fix and is left standing.** Its claim is
about a *rubric* change on a fixed field, and it reproduces on the whole field in both directions:
on the v1 whole field the pair moves −2.46pp (v1) → +2.95pp (v2) → +3.60pp (v3), and on the v2
whole field +2.02pp → +4.05pp → **+5.14pp**. The three reasons §4a gives for refusing to read that
as validation are untouched by this ticket: it is in-sample and close to circular, it was marginal
where it was tested, and the coverage hole is permanent.

**What the live pair reads.** On the live detector (v3) and the live rubric (v3), on the whole
field: picks **12.09%**, field **7.41%**, gap **+4.68pp**, with **103 of 656** inside the board.
That is the pair to quote for the app as it stands today — and it carries §4a's three reasons
with it, because it is the same in-sample rubric measured on the same incomplete field.

**Coverage is unchanged and still bounds all of it.** 92 blind-spot tickers / 172 trades / 18.0%
of realised R (§2). The fix restored sessions, never tickers; #129 is closed won't-do and the
29% hole is permanent. Every cell above is measured against a field missing it.

_Reproduce: `python -m replay.discrimination_grid --store data/replay.duckdb`, which writes
`references/discrimination_grid.txt` and `references/discrimination_grid.json` — both committed
beside this document. Read-only: it reconstructs the forward pass from the universe rows the
store already holds and writes nothing back, so it runs against a built store in about four
minutes and leaves it re-runnable. Every detector version's cluster cut and gate width are
pinned in the module rather than read off the live constants, so it reproduces after a later
ticket moves either._

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

Weights are the **live v2** rubric (#138). They are shown for orientation only — a hit rate,
a spread and a point-biserial correlation are properties of the dimension, not of what the
rubric pays for it, so nothing in the three right-hand columns moves when the weights do.

| Dimension | Weight (v2) | Hit rate | Spread | Correlation vs MFE | Untestable |
| --- | --- | --- | --- | --- | --- |
| Tightness | ×2 | 44.7% | 0.497 | +0.076 | |
| Orderliness | ×1 | 30.1% | 0.459 | −0.060 | |
| Prior move | ×1 | 100.0% | 0.000 | — | **yes** (no spread) |
| Base length | ×0 | 48.5% | 0.500 | −0.083 | |
| MA support | ×1 | 76.7% | 0.423 | −0.158 | |
| Volume | ×1 | 36.9% | 0.483 | −0.125 | |
| ADR | ×2 | 81.6% | 0.388 | +0.092 | |

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
real but modest against A2's 17.3% / 17.8% gap — **−2.46pp once the truncation is out of it**
(§4b), which makes the gap the reweight is pushing against wider than this paragraph assumed,
not narrower — and says nothing about whether the **3.5★
share** moves, which depends on the joint distribution around the boundary. The numbers above
are the computed expectation; the **measured** paired A2 re-run is **§4a**, and it confirms them
— measured picks-minus-field shift **+0.196 stars** against the +0.19 predicted here, agreeing
to about a hundredth of a star. The 3.5★
share this paragraph declined to predict was also measured there, and it moves: **17.3% / 17.8%
under v1 → 14.4% / 8.8% under v2 on the same field**. That pair is stamped to the *truncated*
field; on the whole field the same rubric step reads **17.4% / 19.8% → 13.2% / 10.3%**, so the
reweight's direction survives the fix (§4b).

**#136 — the paired re-run is now wired, and separates the two variables by construction.**
The obstacle #136 was written against — "re-run A2 and risk moving the field *and* the rubric
at once, then attribute the null to neither" — is now closed at the seam rather than left to a
disciplined operator. `screener.score.RUBRIC_WEIGHTS` keeps the superseded **v1** ten-point
table beside the live **v2** nine-point one, keyed by the same `RUBRIC_VERSION` stamp, and
`stars_under(breakdown, weights)` re-totals a detection's *hit booleans* under either. The
hits are a property of the setup, not the rubric — only the weights move — so
`replay.placement.build_placement_report` now scores **one** replayed field under **both**
rubrics in a single pass and returns `by_rubric`: `RubricStarDistributions` for v2 (live) and
v1, each carrying its own version stamp and its own picks-vs-field histogram. The live pair is
identical to the headline `picks`/`field` by identity (the detections were scored under v2), so
nothing is scored twice. `format_report` prints the two stamped blocks and `study.py`
serialises `by_rubric`, so the machine-readable results file is the paired result.

`by_rubric` also carries the **top-thirty figure** per version, not only the histogram: a board
place is a re-ranking rather than a re-scoring, so the weights reorder the whole field around a
pick and can move it on or off the board even where its own hits never changed (41→45, §4a).
Reading the board under one rubric and the histogram under another would have reintroduced
exactly the cross-run comparison this pairing exists to prevent.

**What the pairing was for, and what it delivered.** It was built to separate a rubric change
from a field change when the fuller field (#129) landed. #129 is now **closed won't-do** — the
delisted-bar history is paid-only and there is no budget — so the field variable is frozen
permanently, which makes the pairing measure the rubric *alone* rather than disentangle two
movers. The measured result and the explicit verdict — the ranking conclusion is **weakened,
not reversed**, and the §4 null holds only under its v1 stamp — are in **§4a**, together with
why an in-sample gap at p = 0.055 is not a validation.

### 5d. `RS line` — an index-relative candidate dimension. **Rejected on criterion 4** (#160)

The first dimension pre-registered under `docs/adr/0005-what-admits-a-dimension-to-the-rubric.md`,
and the first measured against ship criteria fixed **before** the numbers were visible. It was
proposed for the slot `Prior move` cannot earn: a **constant dimension**, 100.0% in both groups,
pooled spread 0.000, occupying a point of a nine-point rubric that can never move the sort.

**The dimension, as registered.** `RS = adj_close(name) / adj_close(index)`, hit when
`RS_today >= RS_at_base_start` over the detection's own base. Non-decayed, not a new high — a
name that merely *matched* the index across its base passes, and the rule has no free
parameter. The window is the detector's actual `base_start`, which re-anchors to the highest
high within 45 bars on a capped base and is therefore not the prior-move peak there. The
benchmark is `MARKET_INDEX` as it stands, `^IXIC`. Both legs read `adj_close`; a missing bar on
either leg scores `False` and is never carried forward. **One variant, pass or fail** —
selecting among candidate booleans by whichever gap is largest is magnitude-fitting, which #128
Q2 forbids.

#### The harness reproduces §5b exactly before it is trusted

The contrast was re-run over the store's **persisted** detections first, all of which carry
`detector_version = 1`. It returns **69 taken / 14,354 not-taken** and reproduces every one of
§5b's seven gaps. That is the control: nothing below rests on a harness that could not first
reproduce the table it is being read against.

#### Two fields, because the detector moved twice since §5b

§5b's table describes a field the detector no longer produces. #154 replaced the hard tightness
cut with the far-outlier guard, and **#149 then admitted `12m` to the detection gate** — the
second of which landed *after* #160 was written, so the issue's "re-run under `DETECTOR_VERSION
= 2`" is already one version behind. The live detector is **v3**, and both field-widening
changes are in it. Both contrasts run over the **same 505 sessions**, the same persisted
universe and the same recomputed ranks, so the detector is the only thing that differs.

| | detector v1 | detector v3 (live) |
| --- | --- | --- |
| Detections | 45,600 | 123,558 |
| Per session | 90.3 | 244.7 (**+171%**) |
| Taken | 69 | 140 |
| Not-taken | 14,354 | 34,543 |

**The `RS line` result, both fields:**

| Field | Taken hit rate | Not-taken hit rate | Δ | Pooled spread | Disagreement |
| --- | --- | --- | --- | --- | --- |
| detector v1 | 7.2% (n=69) | 13.0% (n=14,354) | **−5.8** | 0.336 | 12.4% |
| detector v3 | 10.0% (n=140) | 12.1% (n=34,543) | **−2.1** | 0.326 | 11.2% |

#### Verdict against the four pre-registered criteria: **do not ship**

1. **Δ positive, pooled spread > 0 → ship.** Does not apply. Δ is negative on both fields.
2. **Δ positive, disagreement with price-at-new-high under ~15% → do not ship.** Does not apply
   on its own terms (Δ is not positive), but the disagreement figure is **11.2%** under v3 and
   **12.4%** under v1 — under the threshold on both. Had Δ come back positive, this criterion
   would have blocked the dimension anyway.
3. **Pooled spread 0.000 → do not ship.** Does not fire. Pooled spread is 0.326; the dimension
   is not `Prior move` again, and that is the one thing it clearly is not.
4. **Δ negative → do not ship, and record it.** **This is the criterion that fires.** He selects
   names whose strength against the index *decayed* through the base — 10.0% of his picks hold
   the ratio against 12.1% of the field he passed over.

**No rubric change follows.** `RUBRIC_VERSION` stays 3, `DIMENSIONS` is untouched, and the
follow-up (#161) has nothing to admit.

**And the scoring wiring came out with the verdict.** #160 asked for the dimension to be wired
through the four scoring callers, computed but not yet scored — scaffolding for a #161 that is
now moot. Carrying an inert parameter through `score.py`, `candidates.py`, `digest.py`,
`chart.py`, `app.py` and `pipeline.py` for a rejected dimension is documentation bought at the
price of six modules, which is the trade ADR 0005 refuses in the `Prior move` case. What stays
is what carries the evidence: `screener/relative_strength.py` (the pure helper), the replay's
**candidate dimension** column, and the study script. The live app does not compute the RS
line, and §5d is reproducible without it. If #161 is ever revived the wiring is one commit
back in history, and it was a keystroke either way — the measurement was always the hard part.

#### Why the gap is negative, and why it is small

The mechanism is in the definition, and it was not visible until the numbers were.
**`base_start` is a local high under both of the detector's branches.** On an uncapped base it
is the prior-move peak — the highest point of the run-up. On a base past the 45-bar cap it is
re-anchored to `_argmax(high, …)`, the highest high inside that window
(`detection.py:437-441`) — a *different* bar, but a local maximum just the same. Capped bases
are **1.9%** of the measured field (861 of 45,600 persisted detections at `base_len >= 45`;
median base length 12), so the uncapped branch dominates, and the property the dimension trips
over holds either way.

So the rule asks a name to hold its ratio to the index measured *from a local maximum*. Almost
nothing does: the hit rate is 10–13% across the whole field, in **both** groups. `RS line` is
therefore near-constant in the low direction, the mirror image of the `Prior move` dimension it
was proposed to replace.
It has real pooled spread where `Prior move` has none, so it is not the same defect — but a
dimension that fires on one detection in ten discriminates over a thin slice of the field, and
the −2.1pp gap is measured across that slice.

The **disagreement rate makes the redundancy concrete**, and it is asymmetric: of 3,897
disagreements under v3, **3,308 are names where `RS line` fires and price does not**, against
589 the other way. The dimension is close to a slightly-looser price-at-a-new-high test — which
is the break test the app already reports as an event — rather than an independent
index-relative reading. Criterion 2 was written for exactly this and it was right to be there.

#### The §5b re-run: the ordering did **not** move

#160 asked for the contrast to be re-measured under the current detector so `RS line`'s weight
could be read off an ordinal position in a table the detector still produces, and flagged that
this might reveal the live weights sitting on a superseded ordering. It does not. The seven
rubric dimensions rank **identically** on both fields:

| Dimension | Δ under v1 | Δ under v3 |
| --- | --- | --- |
| **ADR** | +29.3 | +26.4 |
| **Tightness** | +20.8 | +13.5 |
| MA support | +4.3 | +6.3 |
| Prior move | 0.0 | 0.0 |
| Volume | −3.9 | −0.3 |
| Orderliness | −9.1 | −5.9 |
| **Base length** | −13.4 | −7.8 |

Same order, same signs, every magnitude compressed toward zero — which is what a field grown
171% should do to a contrast against it. **The v2/v3 weights are not sitting on a superseded
ordering**, so #135's ordinal swap and PRD #138's recalibration stand on a table the current
detector reproduces. This is a positive result about the rubric that came out of a negative one
about `RS line`, and it is the more useful half of the run.

Note the scope this does and does not have: measuring all eight is not reweighting any of them.
The other seven keep their weights here, and nothing in this section licenses moving one.

#### Caveats carried with the result

- **Benchmark contamination, measured and not repaired.** `replay.chain.synthesize_instruments`
  tags every symbol with bars as a candidate, so `^IXIC` — the benchmark of the very ratio being
  measured — sits in the replay store's `universe` (928 rows) and `ranks` (2,525 = 505 × 5). It
  does **not** reach either comparison group: 0 rows in `detections`, and it clears the 0.90
  detection gate on 0 of 505 ranked sessions, global max 0.8246, never within 0.075 of the cut.
  Had it reached the not-taken group it would have scored a guaranteed tie against itself, which
  is circularity rather than noise. The residual effect is on **denominators only** — one extra
  name in ~1,000 per session, shifting every other percentile by ~0.1%, and the index sits
  mid-pack (median 0.38–0.47), displacing names nowhere near the boundary. Fixed separately in
  #162: rebuilding 4.7M rank rows would have run this study against a *different* field than
  §5b's, breaking the comparability the whole exercise depends on.
- **The coverage hole applies here as it does to §5b.** The taken group is the executed trades
  that survived into the reconstructed field, not his entry record. §2's survivorship hole and
  §5b's high-ADR keeping bias bound this contrast the same way.
- **Criterion 2's ~15% is a judgement, not a measurement.** It is the one magnitude in this
  design with nothing behind it, and it is recorded in ADR 0005 so an argument about it is an
  argument about a number on the record. It did not decide this verdict — criterion 4 did — but
  it would have, and it should be argued about before it decides the next one.
- **A negative result on one variant is not a verdict on index-relative strength.** What was
  measured is this rule, over this window, against this benchmark. A dimension anchored
  somewhere other than the prior-move peak is a different dimension and would need its own
  pre-registration; picking one now, after seeing these numbers, is precisely the
  magnitude-fitting ADR 0005's pre-registration clause exists to prevent.

#### What this leaves open

`Prior move` is still a constant dimension and still retirable under ADR 0005, and the slot it
occupies is still unfilled — this study removed a candidate for it, not the case against it.
Reproduce with `python scripts/rs_line_contrast.py --store <copy of replay.duckdb>`; the
machine-readable result is `references/rs_line_contrast.json`.

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

**Independently replicated since.** The entry-to-MA study
([`qullamaggie-entry-ma-distance.md`](qullamaggie-entry-ma-distance.md)) measured stop width
again from a different direction — a different matched subset (n=579, not 649), bars read
straight from the US store rather than through the replay chain, and ADR recomputed over the
20 sessions before entry rather than taken from the night's field. It lands on the same
numbers: median **0.346** ADR (here: 0.345), p25 **0.241** (0.238), p75 **0.488** (0.490),
share at or under 1.0 ADR **97.9%** (98.15%). Two independent paths to four matching figures
is about as firm as this record gets.

That study also settles a question this one leaves open — whether the tight stop is a
*consequence* of entering near the moving average, as `qullamaggie-method.md` §5 claims ("the
geometry rule and the stop rule are the same rule"). It is not: stop width and entry-to-SMA10
distance are uncorrelated across his book (Spearman −0.002). He stops at the entry day's low,
which is set by that day's range and not by how far price has travelled from the 10-day. The
stop convention in this finding is therefore its own constant, independent of any MA-distance
rule the app might later adopt.

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
  result carries `blind_spot_count`; the 92-ticker / 172-trade / 18.0%-of-R hole is quantified
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

The rule is stated in `docs/adr/0002-what-evidence-licenses-loosening-a-gate.md` and is not
restated here. It has two limbs — one for score dimensions, one for cross-sectional cuts —
and both exist to guard the same thing: precision is not measurable, so recall is never
optimised on its own.

**How the measured results sit against the rule.** Every testable dimension shows a null in
§5a *and* spread ≈0.4–0.5, so all six clear the score-dimension limb. `Prior move` clears
neither condition and never can: it is 100% in the executed trades, 100% in the not-taken
detections, and its spread is 0.000 in both. It must not be touched on the strength of this
study.

Two of the changes this study most directly supports are not dimension-loosenings and are
governed differently:

- the **stop convention** (§6, finding 1) is a detector output and a card claim, measured
  against his own risk rather than inferred from a null — outside the rule entirely; and
- the **base-tightness restructure** (§3b, #145/#154) is neither a loosening argued from a null
  nor a threshold move with the shape held fixed: it replaced a threshold with a graded rubric
  input plus a far outlier guard. ADR 0002 does not govern that, and ADR 0004 records what does;
  and
- the **decile gate** (§3), which costs 40% of his entries, is a **cross-sectional cut** and
  falls under the rule's second limb: the loss must be measured directly by A1, shown not to
  be a coverage artefact, addressed structurally rather than by a threshold move, and quoted
  with its population cost. This document originally exempted the gate from the rule
  altogether; that carve-out was wrong, and #133 replaced it — see ADR 0002. The gate's own
  option space is in `docs/adr/0003-the-decile-gate.md`.

---

## 8. What transfers to IDX

**The shape of the findings is a property of the method and travels. The magnitudes are a
property of a once-in-a-decade US momentum regime and do not.** Carry the structural lessons
to IDX — which gate is costing entries, that stop convention is measured against the trader's
own risk rather than assumed, that a dimension's null must be read against its spread — and
carry none of the figures. No number from this study is to be presented as an IDX
expectation; the reference set contains no IDX trade.

**The regime is now measured, not asserted.** §3f took the benchmark's own return over the same
windows on the same entry dates: `QQQ` was up **39.7%** median over the trailing twelve months
before his entries, and **negative on 1.7% of them**. Roughly ten observations of a falling
year, out of 582. That is what "once-in-a-decade momentum regime" amounts to in this reference
set, and it bounds every magnitude in this document — including the index-relative ones, which
survive the subtraction but were never tested against a tape that fell. ADR 0005 carries the
same bound for dimension proposals; `docs/out-of-sample-backtest-plan.md` is the only planned
measurement outside this window.

## 9. What the study cannot say

- It cannot claim the **ranking** is validated. A2 measured a flat null under the **v1**
  rubric (§4) on 104 of his 658 replayable trades against a field missing 29% of its
  tickers. The paired re-run under the live **v2** rubric on that same field (§4a) opens a
  gap in the discriminating direction — 14.4% of his picks at ≥3.5★ against the field's
  8.8% — which **weakens** that null without validating the ranking: the v2 weights were
  fitted to this very taken-vs-not-taken separation (§5b), so the gap is in-sample, and it
  is marginal (p = 0.055) even so. Neither the v1 null nor the v2 gap may be read as
  ranking validation.
- It cannot report a **precision** or **false-positive** rate. There is no control group of
  setups he passed over. **§3d adds a strictly weaker thing, and the distinction must be
  kept:** a same-name background — the tickers he traded, sampled on random ordinary days —
  which can say whether a feature belongs to the *entry* or merely to the *kind of stock*.
  That supports a **redundancy** test (does a candidate dimension still select his entries
  once the obvious correlate is held fixed?) and nothing more. A random day is not a rejected
  setup, so no lift computed against that background is a precision figure, and none may be
  cited as one. This limitation stands.
- It cannot say anything about **`Prior move`**. The dimension is 100% in every group the
  study can construct, so its spread is zero everywhere and no correlation exists to
  measure. **A partial route around this has since been found:** the entry-to-MA study
  ([`qullamaggie-entry-ma-distance.md`](qullamaggie-entry-ma-distance.md) §5) uses distance
  above the SMA50, in ADR units, as a *continuous* proxy for prior move — and unlike the
  binary dimension it has real spread (p5 −1.07 ×ADR to p95 +6.12 ×ADR). Over that spread it
  correlates weakly **positively** with realised R (Spearman +0.048), the opposite sign to
  distance above the SMA10 (−0.052). This does not validate the `Prior move` gate, which is
  still unmeasurable here; it establishes that the underlying quantity is measurable once
  expressed continuously, and that its sign is favourable. The caveat attached there —
  a 2020–21 tape rewarded distance-from-50 nearly everywhere — applies with full force.
  **The proxy is no longer the only route: §3f takes the quantity directly**, as the raw
  `1w/1m/3m/6m/12m` return behind each entry and as a return relative to `QQQ`/`^IXIC`, and
  finds real spread (`6m` median +55.8%, p25 +15.1 to p95 +370.7) with the same split of signs
  — long lookbacks favourable, `1m` adverse. What stays unmeasurable is the **gate**: §3f is
  still executed trades only, with a same-name background rather than a control group of
  rejected setups, so it cannot price the decile cut itself. The 2020–21 caveat is now
  bounded rather than removed — `QQQ` was negative over the trailing year on 1.7% of his entry
  dates, so the record holds almost no bear-market `12m` observations.
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

**Two things about the committed store, before that command is run again.**
`data/replay.duckdb` carries universe rows for 928 sessions but run records for only 19 — it
predates the #126 reuse marker — so `replay_chain` calls `rebuild_universe` on an
already-populated session and dies on `Store._guard_absent`. And its persisted detection rows
are all `detector_version = 1`, which `_session_detections` reads back without checking the
stamp, so a re-run on it would silently mix v1 rows into a v2 field. Rebuild the store from
step 1 rather than reusing the committed one.

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

**The gate-width sweep is separate, and read-only** (§3e, #149). It reconstructs the forward
pass from the universe rows the store already holds and recomputes the ranks in memory — the
chain's own reuse path with nothing written back — then runs the detector once over the union
of every width it prices. About four minutes on a built store, against the study's half hour,
because it never rebuilds the universe:

```
python -m replay.gate_sweep --store data/replay.duckdb \
    --out-report references/detection_gate_sweep.txt \
    --out-json   references/detection_gate_sweep.json
```

It baselines against the three-lookback width explicitly rather than reading
`DETECTION_LOOKBACKS`, so it reproduces byte-for-byte after its own verdict moved that
constant.

**The discrimination grid is separate and read-only too** (§4b, #165), and stands on the same
reconstruction for the same reason — it needs five fields over one chain, and rebuilding the
chain five times to get them is half a day for a measurement that is four minutes of filtering.
It runs the detector once over the union of every version's gate and derives each cell from that
one pass:

```
python -m replay.discrimination_grid --store data/replay.duckdb \
    --out-report references/discrimination_grid.txt \
    --out-json   references/discrimination_grid.json
```

Like the sweep, every detector version's cluster cut and gate width are pinned in the module
rather than read off `OUTLIER_MULT` and `DETECTION_LOOKBACKS`, so it keeps producing the same
grid after a later ticket moves either — and unlike a re-run of `replay.study`, it works on the
committed store as it stands, because it writes nothing and so never meets the write-once guard.

**Runtime.** The chain is 947 sessions (126 burn-in + 821 measured) and dominates: on the
2026-08-15 run the whole study took **29.8 minutes**, of which the chain was 29.1 and the
per-session detection pass that builds the field added 0.6. Treat it as an order of
magnitude, not a benchmark — it is one machine's cold run. A **second** run against a store
whose sessions are already persisted is far cheaper: the chain reuses them rather than
rebuilding (#126), which is what makes an added-column re-run affordable.

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
`backend/replay/`. Row-level seam: `backend/tests/test_replay_seam.py`. Decile decomposition
#133; cluster characterisation #132; recalibration #138; paired A2 re-run #136; the tightness
restructure #145/#154; the discrimination grid #165. Study last run **2026-08-22**, on detector
v2 and rubric v3 — the run that re-pinned §3's detection row, §3's condition table and §4's
`in_field` anchor. **§4b's grid is newer than that run** (`replay.discrimination_grid`,
2026-08-25, read-only over the same store): it carries the only figures measured under the live
detector v3, so §4's `in_field` anchor is pinned from §4b and not from the 2026-08-22 report.
Anything else in this document stamped detector v2 is awaiting the next full `replay.study` run
and says so where it matters. The
recall-and-inflation ledger in §3b is a side-car, `scripts/base_tightness_restructure.py`, run against
the same store and outside `replay.study`. The survivorship hole closed won't-do as #129._

_Side-car prototypes, outside §10 and outside `replay.study` — each rebuilt by running the
scripts in its own directory, each carrying its own `FINDINGS.md`: §3b
`backend/replay/prototype-tightness/` (branch `worktree-prototype-tightness`); §3c
`backend/replay/prototype-base-length/` and §3d `backend/replay/prototype-adr3/` (both on
branch `worktree-prototype-base-length`), run 2026-08-22._
