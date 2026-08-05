# Round 2 — pre-registration

**Written before a single card was graded.** Ticket 15 says to size the round from the observed
grade variance and to decide it *before* grading, so this file exists to stop the thresholds from
being chosen after the fact and then justified. Everything below — deck sizes, sampling, the
objective the thresholds are fitted to, the boolean-vs-continuous tie-break, the trigger for
splitting IDX out — is fixed here. What round 2 produces is the *numbers*, not the rules.

Round 1 (ticket 09) is the input: 27 blind grades, mean **2.48★**, **SD 1.282★**. Every sizing
number below comes off that SD.

---

## 1. How many charts

| test | effect to detect | n |
| --- | --- | --- |
| eye vs machine correlation | r = 0.26 (round 1's best corrected variant) | **114** |
| " | r = 0.35 | 62 |
| " | r = 0.50 | 29 |
| two-group mean grade difference | Δ = 1.00★ | **26/arm** |
| " | Δ = 0.75★ | 46/arm |
| " | Δ = 0.50★ | 103/arm |

All at α = 0.05 two-sided, 80% power, SD = 1.282★.

The headline number is **114**: the round has to be able to *confirm* the effect round 1 actually
observed, not just a hoped-for larger one. Detecting Δ = 0.5★ on the two probe splits would cost
another 206 cards and is refused — the probes are sized to catch a **1-star** difference, which is
the size that would actually change a decision, and a null there is reported as "no 1-star effect",
not as "no effect".

### The decks

| deck | n | what it is for |
| --- | --- | --- |
| **A — core** | 120 | the primary endpoint; threshold fitting |
| **B — trigger probe** | 52 | 26 already-breached vs 26 comfortably-above (09 D10 / 08 D5) |
| **C — IDX lock probe** | 52 | 26 partial-lock (1–20% collapsed bars) vs 26 clean IDX (09 D9 / 08 D13) |
| **D — false-negative probe** | 40 | 20 detector **rejects** vs 20 detections, overlays off |
| **repeats** | 12 | drawn from A, re-shown inside the later decks, to measure test–retest |
| **total** | **276** | |

**Deck A is the only one that must be complete.** It alone answers the ticket's primary question
and fits the thresholds. B, C and D each answer one carried-in question and can be graded in
separate sittings; a deck that goes ungraded is reported as unanswered, not silently dropped.

### Why deck D has its overlays off

Ticket 11 ruled there is **no rejected-candidates view in v1** and handed the inspection of the
discarded set to ticket 09, which did not do it — its deck graded detections only. That obligation
is the reason deck D exists. A reject has no base, no trigger and no fitted lines, so drawing the
usual overlays would label every card before it was graded. Deck D therefore draws **bare candles
plus MAs for every card, rejects and detections alike**, and asks a different question: *is there a
tradeable breakout/continuation setup on this chart, 1–5?* It is the only deck where the grader
cannot tell what the machine did.

---

## 2. Sampling (fixed here, executed by `sample.py`, seed 15)

- **Deck A** — decile-gated detections (`prior_move ≥ 0.90`, `risk_pct ≥ 0.005`), stratified into
  **24 per provisional star band** (≤1.5 / 2 / 3 / 4 / 5), at most **2 cards per symbol** across the
  whole deck, drawn from the whole 2019-01 → 2023-06 sweep. Stratifying on the *provisional* score
  is deliberate: it spreads the cards over the range being calibrated. The correlation it produces
  is therefore a **range-stretched** estimate and is reported as such, alongside the same statistic
  reweighted to the pool's natural band frequencies.
- **Deck B** — 26 with `trigger ≤ close` (already breached) and 26 with `trigger ≥ close × 1.02`,
  matched on provisional star band as closely as the pool allows so the split is about the trigger
  and not about score.
- **Deck C** — IDX only: 26 with collapsed-bar share in `(0, 0.20]`, 26 with share exactly 0,
  matched on star band.
- **Deck D** — 20 rejects sampled from decile-gated rejections, **10 `no_window` and 10
  `stop_too_wide`**, and 20 detections sampled to match their star-band mix, all rendered bare.
- **Repeats** — 12 deck-A cards, re-rendered with a different card id and re-shuffled into decks
  B/C/D. The grader is not told which they are.

**Nothing is revealed during grading.** Round 1's deck revealed the score card by card, which is
harmless over 27 charts and not harmless over 276: seeing what the machine rewarded teaches the
grader the rubric, and grades stop being independent of it. The round-2 decks show no score, no
dimensions and no forward outcome until the deck is submitted. This is the reason the decks can be
graded in any order and across sittings without contaminating the result.

---

## 3. What gets fitted, and how

Free thresholds — exactly the five the ticket names, six numbers:

`contraction` · `orderliness (churn/L)` · `ma_dist` · `dryup` · `len_ok` · `len_bad`

Not free, because another ticket already fixed them: `adr ≥ 0.05` (§3.5 states it), `sector_share
≥ 0.10` (ticket 07), `prior_move ≥ 0.90` (the decile gate). The **structure** is ticket 09's and is
not re-litigated: contraction sign, churn/L, `min(L,20)` decoupled measurement, length as a penalty
paid for by the free higher-lows point, neutral scoring for unmeasurable dimensions.

- **Objective**: mean absolute error between computed stars and the grade, minimised by coordinate
  descent over a fixed grid (`rubric2.GRIDS`), ties breaking toward the incumbent value so a
  threshold only moves on evidence.
- **Honesty**: **5-fold cross-validation on deck A**. Every headline number is computed from
  out-of-fold predictions. The in-sample number is reported next to it; if they diverge by more than
  0.15★ the fit is declared overfitted and the incumbent thresholds stand.
- **Ceiling**: the 12 repeats give the grader's own test–retest correlation. No rubric can be
  expected to beat it, so it is reported as the ceiling next to every r. If test–retest is itself
  below ~0.6, that is the finding and the thresholds are reported as provisional whatever they fit.

### Boolean or continuous

Both are fitted on the same folds with the same objective. Continuous carries **no extra free
parameters** — every ramp is the fitted cut ± a half-width fixed in advance at 0.5× the signal's
population IQR — so it cannot win by having more knobs.

**Decision rule, fixed now:** continuous wins only if it beats boolean out-of-fold on **both** mean
absolute error (by ≥ 0.10★) **and** within-one-star rate. Otherwise boolean stands. Ticket 11 made
the score the default sort of the only list in the app and argued a sort key you cannot audit is one
you will not trust; boolean is the auditable one, so it holds the ground on a tie. If it comes down
to a coin-flip, that is recorded as a coin-flip, per the ticket.

### The 4★ trade threshold

Reported as a confusion matrix of machine ≥ 4★ against eye ≥ 4★ on out-of-fold predictions, with
precision and recall. **Pre-registered rule:** the cut moves off 4★ only if some other cut reaches
≥ 10 percentage points better precision at no worse recall. Otherwise §3.5's line stands and the
measured precision is published with it. Forward outcomes are **not** used to move it — ticket 09
measured that they cannot (≈672 triggered setups per band needed; 33 available at 5★).

### Per-market calibration

Fit pooled first. IDX gets its own threshold set **only if** the pooled fit's mean residual on IDX
cards differs from the US mean residual by **> 0.5★**, or the IDX-only fit beats the pooled one on
IDX cards by **> 0.15★** out-of-fold. Otherwise one set of numbers covers both markets and the fact
that it does is the finding.

---

## 4. Known limits carried in, not fixed here

- The pool is ticket 09's reduced, survivorship-biased ~650-name US universe. Decile boundaries —
  and therefore the `prior_move` and `sector` dimensions — differ from the real 1,966/288 universe.
  The ticket's own caution. A separate check against the full universe runs alongside the grading;
  no threshold is called final until it survives that check.
- The eye is the arbiter by necessity, not by preference: outcomes cannot arbitrate at this sample
  size, and round 1 found neither the trader nor the machine graded in the direction outcomes went.
- Deck A's stratification stretches the score range. Both the raw and the reweighted correlation are
  reported; the reweighted one is the honest estimate of nightly behaviour.
