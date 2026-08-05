# Star score calibration — prototype findings (pre-grading)

Prototype for ticket `09-star-score-calibration.md`. **As-of 2026-08-05.**

Everything below was measured before the human grading session, by implementing ticket 08's detector
literally and running it over real bars. These are the findings the machine can produce alone; the
questions they *don't* settle are what the grading session is for.

## Scope of the measurement

| | |
| --- | --- |
| US universe | 650 names fetched, 633 producing detections, 644 in the rank table |
| US sweep | 2019-01 → 2023-06, every 3rd bar → **24,664 detections** |
| IDX slice | 77 names, 2017 → 2024 → **6,946 detections** |
| Median eligible names/date | 180 (after ticket 05's $20M dollar-volume floor) |

**Honest limits, not fixable here.** The universe is a 650-name sample, not ticket 05's 1,966, so
decile boundaries are approximations; and it is survivorship-biased (Nasdaq Trader lists only live
names), exactly as ticket 02 predicted. Both were accepted: this prototype calibrates the *shape* of
the score, and comparisons *between* score bands are far less sensitive to those biases than absolute
levels are.

The detector was reimplemented twice — a readable reference (`detector.py`, polyfit) and a vectorised
sweep (`fastscan.py`, least-squares slopes from cumulative sums). They were checked field-by-field and
agree exactly; the fast one runs the full 24,664-detection sweep in **6 seconds**.

---

## F1. D7's contraction measure has its sign inverted in ticket 08's write-up

D7 says: *"a contracting base grows flatter than √L, because the older bars are wide and the recent
ones are tight"*, and scores contraction as **how far below** the √L baseline the curve sits.

That reasoning is backwards. The window is **end-anchored**, so extending it backwards *adds the wide
older bars* — which makes `range(L)` grow **faster** than √L, not flatter. The quantity is a perfectly
good contraction measure; it just runs the other way.

Confirmed by controlled synthetic bases (`synth.py`), envelope taper varied with per-bar disorder held
fixed:

| envelope | contraction ratio |
| --- | --- |
| flat channel (taper 1.0) | **0.86** |
| mild cone (0.7) | 0.92 |
| moderate cone (0.4) | 1.04 |
| tight cone (0.15) | **1.59** |

And on real data the distribution sits mostly **above** 1 (median 1.35, p90 2.38) — i.e. under 08's
literal reading, the median detected base would be scored as *expanding*.

**Consequence:** taken literally, D7 scores the tightness dimension — one of the two ×2 dimensions —
backwards. The prototype scores it as *higher = more contraction*.

**Also:** the measure needs ≥2 valid windows, and **19.8% of detections have only one**, so the ×2
tightness dimension is unmeasurable for a fifth of all candidates. The retained set is small in
general — median 3 windows.

## F2. D8's churn is not scale-free in the base length

D8 calls churn *"parameter-free and scale-free"*. It is scale-free in **price**, but not in **L**:
`churn = Σ(daily ranges) ÷ envelope` grows roughly linearly with the number of bars, because the
numerator accumulates per bar while the denominator does not.

Synthetic, per-bar disorder held **fixed**:

| L | churn | churn/√L | **churn/L** |
| --- | --- | --- | --- |
| 5 | 2.20 | 0.99 | **0.441** |
| 10 | 3.73 | 1.18 | **0.373** |
| 20 | 6.75 | 1.51 | **0.338** |
| 40 | 12.60 | 1.99 | **0.315** |
| 60 | 18.36 | 2.37 | **0.306** |

Raw churn drifts 8.3× across that range; `churn/L` drifts 1.4×. And `churn/L` still separates cleanly
on the thing the dimension is *about* (L=20, taper fixed): smooth drift 0.188 → barcode 0.618.

On real data raw churn correlates **+0.64** with base length; `churn/L` correlates **−0.54**. Neither
is zero, but the synthetic test — which is the only one that holds disorder constant — says the
normalisation itself is right and the residual real-data correlation reflects genuine differences
between short and long bases.

**Consequence:** with a fixed threshold on raw churn, orderliness — the other ×2 dimension — grades
short bases as orderly and long bases as barcodes, by length alone. `churn/L` ("mean daily range as a
fraction of the envelope") is the scale-free form. D8's *substance* survives intact; only its
normalisation changes.

## F3. D5's `min()` almost never binds, and 16% of setups are emitted already-triggered

Across 24,664 detections, the trigger was set by the **fitted line in 98.3%** of cases and by the flat
max-high in 1.7%. This is close to structural: with a non-rising highs fit, the line's value at the
last bar is its lowest, and generally below the window max.

More consequential: **16.4% of detections have a trigger below that day's close** — the setup is
emitted as `WATCHING` with its trigger already breached. Median trigger sits 1.4% above the close and
2.2% below the base high.

08 flagged D5 as *"the decision most likely to look wrong against real charts"*. It is the one measured
here with the clearest defect, and it is a question for the eye: is an already-breached trigger a
missed entry that should be suppressed, or a legitimately early one?

## F4. "Higher lows intact" is a free point

D9 makes the higher-lows dimension the low-side fit slope — but window validity **already requires**
that slope to be ≥ 0. So the boolean is true for **92%** of detections (the remaining 8% have a slope
of exactly 0). A dimension that is satisfied by construction contributes no information to the score;
it just shifts everything up by one point.

Either it should be graded on magnitude, or its weight belongs elsewhere.

## F5. Outcomes cannot arbitrate the rubric at this sample size — but the 4★ threshold survives

Forward outcomes modelled per §7 as closely as EOD allows: entry at the trigger on the first of the
next 10 bars to cross it, stop at the base low, 30-bar hold, result in **R**. Restricted to detections
passing D15's decile gate (1,241 detections, 1,063 triggered).

| boolean stars | n | trig % | mean R | win % |
| --- | --- | --- | --- | --- |
| ≤1.5 | 129 | 89.9 | 0.232 | 21.6 |
| 2 | 455 | 88.4 | 0.099 | 19.4 |
| 3 | 276 | 84.8 | 0.193 | 22.6 |
| **4** | 325 | 81.8 | **0.494** | **26.7** |
| 5 | 56 | 80.4 | 0.444 | 17.8 |

The 4★ band is the best on both mean R and win rate, which is weak support for §3.5's *"trade 4–5
stars"* line. But **the 5★ band is indistinguishable from it** — n=56, and the standard error on a
band mean at that size is **0.41R**, larger than the entire spread across bands.

Per-dimension, mean R by quintile is **non-monotone for every one of the eight dimensions**. Quintile
SE is 0.189R, so the 0.2–0.8R spreads are 1–4 SE: not pure noise, but no clean story either.

**To resolve a 0.3R difference between bands at 2 SE you would need ~672 triggered setups per band.**
We have 56 at five stars. So the outcome data cannot settle the weights, the thresholds, or the
boolean-vs-continuous question. **The eye is the arbiter** — which is what this ticket said, now with a
number attached to why.

## F6. D13's limit-day hazard is real, but inverted from how 08 stated it

Measured on the IDX slice. Collapsed-range (high == low) bars are common and concentrated: DEWA 57.3%
of bars, MEGA 18.0%, BRMS 15.9%; 2.18% across all IDX names.

Star score by share of collapsed bars **inside the base**:

| collapsed bars in base | n | mean ★ | ≥4★ | contraction | orderliness | ADR |
| --- | --- | --- | --- | --- | --- | --- |
| none | 6,403 | 2.74 | 16.6% | 1.45 | 0.360 | 4.2% |
| **1–20%** | 277 | **3.21** | **24.9%** | 1.80 | 0.243 | 5.0% |
| 20–50% | 129 | 2.66 | 11.6% | 1.92 | 0.239 | 3.3% |
| >50% | 137 | 1.92 | **0.0%** | 1.32 | 0.141 | 1.1% |

08 predicted a *dead stock scoring as a textbook base*. That does **not** happen: fully-locked names
reach 4★ **zero times**, because only 1.5% of them clear ADR ≥ 5%, and a fully-flat base doesn't even
score high on contraction (its range curve stays flat, which now reads as *no* narrowing).

The real exposure is the band 08 didn't name: **partially** locked bases — a live, high-ADR name with a
handful of limit days — which score **best of any group** (24.9% reach 4★) with visibly flattered
orderliness (0.243 vs 0.360).

**Consequence:** the generic liveness floor 08 designed and declined would have targeted the
fully-locked case that the ADR dimension already handles for free, and missed the partial case that is
actually exposed. If a fix is wanted it has to key on *individual* collapsed bars inside the base, not
on the base's median liveness.

## F7. The primary window is 3 bars over half the time

`L = 3` in **52.3%** of detections; median primary L is 3. D4 accepted this degeneracy deliberately
(monotonicity in L makes any argmax collapse) and defended it as yielding the earliest, nearest-the-MA
trigger. The measurement confirms the degeneracy is not a corner case but the **modal outcome**: for
most candidates the "base" whose high sets the trigger is three bars long, while the *visible* base
(the longest valid window) has a median length of 8 and reaches 60.

Not a defect on its own terms — but it means the trigger the app draws and the base the trader sees are
routinely different objects, which is a chart-and-eye question, not a maths one.

---

## What the grading session has to settle

1. Does the computed score match your eye, and in which direction does it miss? (the ticket's question)
2. **F3** — is an early or already-breached trigger buying strength or noise?
3. **F4** — regrade higher-lows on magnitude, or move its weight?
4. **F6** — do the partial-lock IDX charts look like real setups to you, or like artefacts?
5. **F7** — should the chart's trigger key off the 3-bar primary window or the visible base?
6. Booleans or continuous sub-scores — F5 says outcomes can't decide it, so it is a judgement call.
