# Round 3 — deck A results (120 blind grades on the split's population)

Deck A3 is graded: 120 cards, all bare, drawn from the setups ticket 17's detector actually
surfaces. Decks C3 (IDX) and D3 (rejects) are not, so per-market calibration, the rejected-candidate
question and **the test–retest ceiling** are all still open. Grades in `grades3_A.txt`; everything
below follows `PREREGISTRATION_R3.md`, and the two places it did not anticipate reality are called
out as such rather than quietly patched.

Grade distribution: mean **3.23★**, SD **1.268** (1:9 · 2:35 · 3:18 · 4:35 · 5:23). Significance at
n=120 needs **|r| > 0.180**.

## The headline: the score misses significance, and two of its dimensions are dead

| | round 2 (old structure, overlays) | **round 3 (split, bare)** |
| --- | --- | --- |
| r, score vs eye, out-of-fold | +0.189 | **+0.159** |
| mean abs error | 1.04★ | 1.15★ |
| within one star | 67% | 56% |
| bias | +0.25★ | +0.10★ |

The two are not directly comparable — different detector, different population, different
rendering — but the direction is the honest summary: **refitting on the new structure did not buy
agreement with the eye.** +0.159 sits just under the 0.180 the sample needs.

Fitted (boolean, out-of-fold, in-sample mae 1.03 vs out-of-fold 1.15, gap 0.12 inside the 0.15
tolerance, so publishable by the pre-registered test):

| threshold | fitted | share of cards awarded the point |
| --- | --- | --- |
| tightness, `cluster_k ≥` | **7** | **15%** |
| orderliness, `churn/L ≤` | **0.60** | **99%** |
| dry-up `≤` | **0.85** | 27% |
| base length `len_ok ≤` | **26** | **95%** |
| `ma_support`, SMA20 rising | — | 81% |

**Two dimensions have been fitted into constants.** Orderliness (×2) is awarded to 99% of cards and
base length (×1) to 95%: the fitter's best move for both was to switch them off. That leaves the
score running on tightness, dry-up, and the three fixed dimensions — and it is why the predicted
score has an SD of only 0.65★ against the grades' 1.27★.

**Boolean stands** over continuous (+0.159 vs +0.112), by the pre-registered rule and comfortably.

## The pre-registered optimiser was broken, and fixing it was worth +0.10 of correlation

Reported first because every number above depends on it. Round 2 fitted by **coordinate descent**
over a fixed grid, and `rubric3.fit` inherited it. On round 3's grades that search **does not reach
the optimum of its own objective**:

| | thresholds | mae | r | predicted SD |
| --- | --- | --- | --- | --- |
| coordinate descent | `k≥3, ord≤0.225, dry≤0.85, len≤26` | 1.0875 | +0.144 | 0.45 |
| **exhaustive, same grid, same objective** | `k≥7, ord≤0.60, dry≤0.85, len≤26` | **1.0292** | **+0.296** | 0.65 |

The point it settled on was **degenerate**: `cluster_k ≥ 3` awards the ×2 tightness point to 100% of
cards, because 3 is the detector's own minimum cluster length. With the ranking dimension switched
off, the fitter was using the biggest weight in the rubric as a bias knob to pull the mean toward
the grades — minimising error by making the score nearly constant. Out-of-fold that read **r =
+0.060**.

Replacing the local search with an exhaustive pass is **not a change of rule**: same grid, same
objective, same tie-break toward the incumbent. There is one global optimum and nothing to choose,
so it removes researcher freedom rather than adding it. A vectorised predictor makes it 0.3s, pinned
to `score3` by assertion so the speed-up cannot alter the rubric.

Also fixed: `len_bad` is only read by the continuous ramps, so leaving it free in boolean mode made
eleven identical copies of every grid point and let an arbitrary tie pick it.

**Round 2's published thresholds are not affected.** Re-checked directly — coordinate descent from
60 random restarts on round 2's own grades returns the published optimum (mae 0.9750) every time.
The defect bites here and not there because the split's domain flattens the loss surface.

## The orderliness dimension does not survive the move to the split's base

This is the round's real finding, and it is a structural one.

On the split's ~14-bar base the eye prefers **high** churn/L, which is the opposite of what the
dimension rewards:

| | r vs eye | partial r, controlling base length |
| --- | --- | --- |
| churn/L over the base (the dimension) | +0.184 | +0.193 |
| raw churn over the base | +0.221 | **+0.353** |
| churn over the cluster | +0.290 | +0.299 |

Sorted into quartiles of churn/L, mean grade runs **2.90 → 3.33 → 3.37** from the quietest quarter
upward. That is why the fit sets the cut at the top of its grid and gives the point to everyone.

**It is not a sign error, and it should not be flipped.** A synthetic control — bases of identical
length and identical envelope, differing only in orderliness — confirms the quantity still measures
disorder mechanically at every length:

| base style | L=3 | L=14 | L=30 |
| --- | --- | --- | --- |
| orderly | 0.286 | 0.176 | 0.160 |
| disorderly | 0.586 | 0.424 | 0.397 |
| **gap-then-dead** | 0.099 | **0.097** | 0.097 |

Disorderly always scores highest, so low-is-better is right by construction. What changes is the
**gap between orderly and dead**: 2.9× at L=3, 1.8× at L=14, 1.65× at L=30. Over a long base, a low
churn/L stops meaning "orderly" and starts meaning "quiet" — so the point drifts toward the
lifeless base §3.4 warns about. On 08's 3-bar window that leak was small; on the split's base it is
what the dimension mostly measures.

The observed deck sits well above the dead region (median churn/L 0.305, only 6% below the
synthetic orderly reference), so the mechanism is a **drift, not a cliff** — but the direction is
consistent and the dimension is counterproductive across the range that actually occurs.

Three ways out, none of them takeable from this deck without becoming post-hoc:

1. **Drop it** and redistribute its ×2. Simplest, and honest about what was measured.
2. **Redefine it as a band** rather than a one-sided cut. Fitting a band post-hoc on this deck
   reaches in-sample r **+0.387** against the one-sided +0.296 — encouraging, and exactly the kind
   of two-sided parameter chosen after seeing grades that the pre-registration exists to stop.
3. **Replace it with cluster churn** (partial +0.299), which is already the tightness signal — so
   this collapses §3.5's two ×2 dimensions into one measurement of packing.

For the record, inverting the dimension outright takes out-of-fold r from +0.159 to **+0.241**.
That number is reported because it is large, and it is *not* adopted, because the synthetic control
says the inversion would be renaming a disorder measure rather than correcting one.

## Tightness clears its pre-registered gate, but only just

`cluster_k` partial r = **+0.196**, above the +0.15 floor that would have declared the ×2 dimension
unscorable and sent ticket 17's R6 fallback back to the trader. **So the gate does not fire.**

It is weaker than the +0.327 measured on the 81 mixed cards, and non-monotone on the fresh deck
(mean grade by k: 2.90 · 3.42 · 3.30 · 3.08 · 3.72). Two relatives measured on the same deck are
stronger and both length-free: **cluster churn +0.299** and **density, k ÷ cluster range, +0.242**.
The pre-registration named k, so k is what is reported; the alternatives are noted for whatever
round settles the orderliness question, since they are the same measurement.

## The 4★ cut stands — for the third time

Out-of-fold, machine ≥N★ against eye ≥4★:

| cut | n | precision | recall |
| --- | --- | --- | --- |
| ≥3.0★ | 97 | 0.49 | 0.83 |
| ≥3.5★ | 62 | 0.52 | 0.55 |
| **≥4.0★** | 36 | **0.53** | **0.33** |
| ≥4.5★ | 18 | 0.61 | 0.19 |

Precision now rises monotonically with the cut, which it did not in round 2. ≥4.5★ is +8pp on
precision but half the recall, so it does not clear the pre-registered rule (≥10pp at no worse
recall) and **§3.5's 4★ line stands**. Precision at the trade line is **0.53** — up from round 2's
0.37, so roughly one in two names the machine calls tradeable is one the trader would, against one
in three before.

That is the one number that improved unambiguously, and it is the one ticket 11 cares about, since
the score is the default sort of the only list in the app.

## Still open

- **The test–retest ceiling, unmeasured for the second round running.** Every r above is against an
  unknown maximum. The 12 repeats live in decks C3 and D3. By the pre-registration **no threshold is
  final until it is measured** — and at r ≈ 0.16–0.24 the question of whether the rubric is weak or
  the target is noisy is the whole question.
- **Per-market calibration** — deck C3 ungraded. Still zero graded IDX cards on any structure.
- **The rejected candidates** — deck D3 ungraded. Ticket 11's obligation, unowned since ticket 09.
- **The orderliness dimension** — needs a decision and then a fresh pre-registered test.
