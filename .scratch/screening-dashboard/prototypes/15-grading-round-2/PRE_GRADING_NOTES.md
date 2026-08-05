# Round 2 — what the machine could measure before the grading session

Everything here was produced without a single grade, by rebuilding ticket 09's pipeline and running
ticket 09's *settled structure* over it. None of it answers ticket 15's question — that needs the
eye — but three of these change what the grading round is looking for.

**As-of 2026-08-05.** Scale reproduced from ticket 09 almost exactly, which is the first result:

| | ticket 09 | round 2 |
| --- | --- | --- |
| US names fetched | 650 | 648 |
| US detections (2019-01 → 2023-06, every 3rd bar) | 24,664 | 24,604 |
| IDX names / detections | 77 / 6,946 | 77 / 6,949 |
| IDX collapsed-range bars | 2.18% | 2.18% |
| US sector coverage | 649 of 650 | 647 of 648 |

The two-name US difference is names delisted since; nothing else moved. Ticket 09's numbers
reproduce from its written record, which is the third time on this map a session has done that.

---

## R1. The corrected rubric is far *more* generous than the one it replaces

Ticket 09's complaint about the original score was that it ran **+0.74★ too generous**. Under the
round-2 structure with ticket 09's provisional thresholds, on decile-gated affordable detections:

| stars | share |
| --- | --- |
| ≤1.5★ | 0.6% |
| 2★ | 19.5% |
| 3★ | 41.8% |
| 4★ | 35.9% |
| 5★ | 2.3% |

**38.1% of gated detections reach 4★**, against **16.6%** under ticket 09's boolean rubric, and the
mean is 3.45★. The floor also rose: nothing scores below 1.5★ any more, so the band ticket 09
sampled 229 detections from is now empty.

This is not a defect of the structure — it is what a rubric looks like when its thresholds were
inherited rather than fitted, and it is precisely why deck A's bands had to be redrawn over four
levels instead of five. But it does fix the direction of travel: **the thresholds almost certainly
need to tighten, not loosen**, and a fit that moves them the other way should be treated as
suspicious.

## R2. Ticket 09's decoupling had a second effect it did not claim: it made tightness measurable

Ticket 09 F1 found the ×2 tightness dimension **unmeasurable for 19.8% of detections**, because the
contraction measure needs two valid windows and a fifth of detections have only one. That is why
ticket 09 introduced neutral-instead-of-zero scoring (its S5) in the first place.

Measuring contraction over `min(L, 20)` as a half-vs-half range ratio — which ticket 09 adopted to
break the base-length proxy — has no such requirement. On the round-2 pool tightness is
**measurable for 100.0% of US detections** and 99.3% of IDX ones.

**Consequence:** S5 barely binds any more. The neutral-scoring rule was carrying 4 of the 10 points
for a fifth of all candidates in ticket 09's analysis; under the structure ticket 09 itself settled
on, it applies to almost nobody. Whatever the grades say, that rule is no longer doing the work
ticket 09 credited it with.

## R3. The detector discards eleven bar-dates for every one it keeps

Ticket 11 ruled there is no rejected-candidates view in v1 and handed the inspection of the discarded
set to ticket 09, which graded detections only. So this is the first time the discarded set has been
counted. Over the same sweep, restricted to dates that would have cleared D15's decile gate:

| | n |
| --- | --- |
| detections (gated, affordable) | 1,232 |
| **rejections (gated)** | **13,482** |
| — no valid window at all | 7,808 |
| — valid base, but stop wider than 1×ADR | 5,674 |

**A decile-gated bar-date produces a setup 8.4% of the time.** The 5,674 in the second row are the
uncomfortable ones: the detector *found* ticket 08's triangle there and threw it away on D6's
affordability rule alone. Deck D exists to ask whether the eye agrees with either rejection, and it
is the reason deck D draws bare candles — a reject has no base, trigger or fitted lines to draw, so
any overlay would announce which cards are which.

## R4. Yahoo failed as silence again, and the retry is not optional

The map carries this as a standing property of the data layer. It bit twice in one afternoon:

- the IDX pull returned **53 of 80** names, reporting the missing 27 as *"possibly delisted"* — a
  rerun recovered all 77, including DEWA, the 57%-collapsed-bar name that ticket 09's D13 finding
  rests on;
- the sector pull returned **47 of 648 as UNKNOWN** (7.3%) while other fetches ran concurrently.
  Purging the UNKNOWNs and refetching brought it to **1** — ticket 03's claimed coverage exactly.

Had either been accepted at face value the sector dimension would have been silently wrong on 7% of
cards and the IDX probe would have been drawn from a pool missing its most important name. The
operational point for the build: **a first-pass failure and a genuine absence are indistinguishable
at the call site, so an ingestion run has to retry the failures and compare resolution rates before
it publishes anything** — which is ticket 05's D-series quarantine rule, arrived at from the other
direction.

**The retry is also the discriminator.** The full-universe pull (R5) resolved 3,808 of 4,758
symbols — 80%, below this script's own 90% guard — and a second identical pass recovered **exactly
zero** additional names. That null is the useful result: throttle silence clears on a retry and
genuine absence does not, so *"retry once and compare the counts"* separates the two cases without
needing to know which is which in advance. Here the missing 950 are names without 250 daily bars in
the window — recent IPOs and short histories — not losses.

## R5. The ticket's caution, executed: the reduced universe was hiding ~5% of one dimension and ~9% of another

Ticket 15 warned that ticket 09's numbers come off a 650-name sample, so the decile boundaries — and
therefore the two **cross-sectional** dimensions, `prior_move` and `sector` — are approximations.
Every other scored quantity is a within-name ratio and cannot move with the denominator.

Rebuilt over the full common-stock universe (3,808 names with usable history; **median 1,055
eligible names per date** after ticket 05's $20M dollar-volume floor, against ~180 in the prototype —
a **5.9× larger denominator**), and re-evaluated on exactly the 224 US cards that were drawn for the
decks:

| | 650-name | full |
| --- | --- | --- |
| prior-move percentile (mean) | 0.957 | 0.961 |
| **D15 decile gate flips** | — | **10 of 224 (4.5%)**, all losses |
| sector leave-one-out share (mean) | 0.112 | 0.128 |
| **sector boolean flips** | — | **20 of 224 (8.9%)** |

**The caution is discharged, and the answer is reassuring.** Neither cross-sectional dimension moves
far enough to invalidate a threshold fitted on the reduced pool: the prior-move gate is a
percentile, and ticket 06 already showed a percentile gate is self-normalising across universes
differing 7× in size — this is that result again, one layer down. The sector dimension is the
looser of the two at 8.9%, worth half a star when it flips.

Two honesty notes. The 1,055 figure is **not** ticket 05's 1,966: that was measured on today's
universe with today's dollar volumes, while this is a 2019–2023 average over names that still exist
today. And this pull carries the same survivorship bias as every other on this map — it is a larger
denominator, not an unbiased one.
