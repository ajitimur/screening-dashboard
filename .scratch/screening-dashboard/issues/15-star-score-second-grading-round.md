# Second grading round: fix the star-score thresholds

Type: prototype
Status: claimed
Blocked by: 17

## Question

What are the concrete thresholds for the corrected star rubric?

Ticket 09 corrected the *structure* of the score but explicitly did not settle its numbers. Its
grading round was 27 charts; at that size a correlation needs |r| > 0.38 to clear p<0.05 and the best
corrected variant reached **+0.26**. So the rubric currently sits at "weakly positive, typical error
~1.24 stars" rather than calibrated.

This ticket runs the larger round. Everything it needs already exists — the prototype, the sweep and
the blind-grading deck are in [`prototypes/09-star-score/`](../prototypes/09-star-score/) and
`build_deck.py` regenerates a deck of any size from the cached sweep.

Specifically:

- **How many charts?** Ticket 09 measured the noise floor: ~672 triggered setups per band to resolve a
  0.3R outcome difference, but the eye is a much lower-variance instrument than forward returns, so
  the grading target is far smaller. Size it from the observed grade variance rather than guessing —
  and decide it *before* grading, not after.
- **Fix the thresholds** in `calibrated.py`: the contraction cut, the churn/L cut, the MA-distance
  band, dry-up, and the base-length penalty band (currently 20/40 bars, read off §2's horizon and
  §3.4's anti-pattern but never calibrated).
- **Is the 4-star trade threshold in the right place** once the structure is corrected? Ticket 09
  could not test this: its outcome data put 4★ and 5★ ahead but with a 1.41 SE gap on n=33, and the
  ordering of the top two bands flipped when a single ×1 dimension was completed.
- **Booleans or continuous?** Still undecided. Continuous gave a slightly lower mean error in every
  ticket-09 variant but never a better within-one-star rate, and outcomes cannot decide it. Pick on
  evidence this time or record it as a deliberate coin-flip.
- **Per-market calibration.** Ticket 09 never got to this — its IDX cards were too few to separate.
  Every scored quantity is a ratio, so scale alone does not force it; the open question is whether
  IDX's quantization and limit days do.

**Carried in from ticket 09, needing charts chosen to probe them rather than a general sample:**

- **D5's trigger rule (09 D10).** 98.3% of triggers are set by the fitted line, and **16.4% of setups
  are emitted with the trigger already below that day's close**. Ticket 08 called this the decision
  most likely to look wrong against real charts; ticket 09's grades were *indifferent* to it
  (r = +0.012), which is not the same as vindicating it. Grade a set selected for already-breached vs
  comfortably-above triggers and see whether the eye separates them.
- **D13's partial limit-lock (09 D9).** Bases with 1–20% collapsed bars score best of any group
  (24.9% reach 4★) with flattered orderliness. Ticket 09's five IDX cards showed no pattern. Needs an
  IDX-heavy deck split explicitly on collapsed-bar share.

**Do not re-litigate** what ticket 09 settled: the contraction sign, churn/L normalisation, neutral
scoring for unmeasurable dimensions, base length as a penalty rather than a gate, or spending the
free higher-lows point on it.

**One caution.** Ticket 09's numbers all come from a reduced, survivorship-biased 650-name universe.
Before treating any threshold as final, check it against the real universe from ticket 05 (1,966 US /
288 IDX) — the decile boundaries and therefore the prior-move and sector dimensions both move.

---

## Progress — deck A graded, decks B/C blocked on ticket 16

**Deck A is graded (120 cards) and the thresholds are fitted.** Full working in
[`ROUND2_RESULTS.md`](../prototypes/15-grading-round-2/ROUND2_RESULTS.md). Headline: the score now
correlates with the eye at **r = +0.189 out-of-fold**, which clears significance (|r| > 0.181) for
the first time on this map, against ticket 09's −0.043. Mean error 1.24★ → **1.04★**, within one
star 44% → **67%**, generosity bias +0.74★ → **+0.25★**. Four of six thresholds moved and every move
tightened: contraction 1.15 → **1.80**, MA distance 1.0 → **0.60**, `len_ok` 20 → **10**, dry-up
0.85 → 0.95. **Boolean beats continuous** on the pre-registered rule. **The 4★ cut stays**, though
≥3.5★ dominates it on both precision and recall and survives only because the rule demanded a 10pp
precision gain to move it; at 4★ roughly one name in three the machine calls tradeable is one the
trader would.

**What is still open, and why.** Decks B and C are **blocked on
[ticket 16](16-trendline-fitting-envelope-vs-least-squares.md)**. The trader's observation that the
drawn triangle looks wrong turned out to reach the trigger: the boundaries are least-squares fits
where the method wants an envelope, and that alone accounts for ticket 09's already-breached
triggers (13.3% → 0.8%). Deck B's entire split is breached-vs-not off those triggers, so as built it
would spend 52 graded cards probing an artefact. Both decks are rebuilt once ticket 16 picks a line.

So this ticket still owes: **per-market calibration** (deck A is entirely US), **both carried-in
probes**, the **test–retest ceiling** (the 12 repeats live in decks B and C, so the bound on every
correlation above is still unmeasured), and **deck D's rejected candidates**, which is gradeable now
— it draws bare candles and no fitted line touches it.

Built in [`prototypes/15-grading-round-2/`](../prototypes/15-grading-round-2/):

- **[`PREREGISTRATION.md`](../prototypes/15-grading-round-2/PREREGISTRATION.md)** — deck sizes,
  sampling, fitting objective and every decision rule, fixed *before* any card was graded. Sized off
  round 1's measured grade SD of 1.282★: **114 cards** to confirm an r of 0.26, **26 per arm** to
  catch a 1-star difference on a probe.
- **Four decks, 276 cards**: A core 120 · B trigger probe 52 · C IDX lock probe 52 · D
  false-negative probe 40 · plus 12 repeats for a test–retest ceiling. Deck A is the only one that
  must be complete. Nothing is revealed until submission — round 1's card-by-card reveal would teach
  the rubric over 276 cards.
- **[`PRE_GRADING_NOTES.md`](../prototypes/15-grading-round-2/PRE_GRADING_NOTES.md)** — the four
  things measurable without grades, including that the corrected rubric is *more* generous than the
  one it replaces (38.1% reach 4★ vs 16.6%), and that the detector discards **11 decile-gated
  bar-dates for every one it keeps**.
- **`analyse2.py`** — the pre-registered analysis, verified end to end on synthetic grades, so the
  grades run the moment they arrive.

**To resume:** open `decks/deck_A.html`, grade, hit export, and run
`analyse2.py grades.txt`.

---

## Re-scoped by ticket 17 — the structure under the rubric moved

[Ticket 17](17-base-cluster-split.md) adopted the base/cluster split for detection as well as
description, which changes what several of the fitted numbers above are measured over. **The deck A
fit is not discarded — the method, the pre-registration and the boolean-beats-continuous result all
stand — but four of its six thresholds now describe an object that no longer exists.**

What moved:

- **The contraction threshold (1.80) has no domain.** It is defined over D3's retained window set,
  which ticket 17 deleted. Ticket 17 measured every candidate replacement and found that the ones
  correlating with the eye are **base-length proxies that collapse to zero** under a length control
  (working in [`contraction.py`](../prototypes/17-base-cluster/contraction.py)). The "narrow" half is
  available as the cluster range in ADR but is **compressed by construction** — hard ceiling 1.50,
  IQR 1.20–1.42, 16.9% pinned at the top. **So the open question is no longer "what threshold" but
  whether the ×2 tightness dimension is scorable on this structure at all.** That is the largest
  single risk this ticket now carries.
- **Churn, dry-up and MA distance change domain** — they now measure a median 14-bar base rather than
  a 3-bar window. `churn/L` normalisation still applies; the fitted cuts (0.35, 0.95, 0.60) do not
  transfer and must be refitted. D10's MA distance additionally **overlaps the split's own MA
  catch-up test**, so one of the two is redundant.
- **`len_ok` 10 / `len_bad` 40 are measured against a different length.** The base is now 14 bars
  median instead of 3, so the penalty band is no longer positioned where it was fitted.
- **Deck B is moot, not merely blocked.** Its split is already-breached versus comfortably-above, and
  already-breached is **0.2%** under the new clamped trigger (16.0% before). The carried-in D5 probe
  is answered by ticket 17's R2 rather than by grading: the eye chose the clamped-trigger drawing
  10 of 11 times.
- **One new dimension arrives with evidence attached.** **Cluster length k** correlates with the eye
  at partial r **+0.260** in-sample and **+0.218** on ticket 17's fresh grades, *free of base length*
  — the only length-free signal either ticket found. It is already computed. Whether it earns a
  §3.5 point or feeds tightness is this ticket's call.

What is unaffected: deck C's IDX limit-lock probe, deck D's rejected candidates (still unowned,
still gradeable, and now more valuable — ticket 17 changed which names are rejected), the
test–retest ceiling, per-market calibration, and the caution about the reduced 650-name universe.

**One inherited risk to state plainly.** Ticket 17's name-level comparison came back **null**
(+0.40 stars, p = 0.298): the split's added names were not shown to be better than the ones it
drops. The trader adopted it anyway on the strength of the geometry result. Refitting the rubric on
the new structure is what makes that hard to reverse, so if this ticket finds tightness unscorable,
say so loudly rather than working around it — ticket 17's R6 records a cheaper fallback that keeps
this ticket's existing fit intact.

---

## Progress — the structure is settled on the new geometry; round 3 is rendered and waiting to be graded

Measurement pass over the grades that already exist, re-measured on the split. Full working in
[`REFIT_FINDINGS.md`](../prototypes/15-grading-round-2/REFIT_FINDINGS.md).

**The ×2 tightness dimension is scorable, and it is a packing count rather than a width.** Every
*narrowness* candidate fails on the population the rubric actually ranks (cluster range ÷ ADR
+0.100, narrowing +0.076, √-shortfall −0.115, base height −0.027, all partial on base length,
none significant). **Cluster length k is the only measure that replicates** — partial r **+0.327**
(p = 0.002) on the 81 split-accepted graded cards, +0.260 on deck A, +0.216 on ticket 17's fresh
cards. The reason is structural: the cluster is *selected* to fit under `TIGHT_MULT × ADR`, so its
width is spent by the selection and the information left is how many bars pack into it. Cluster
churn measures the same object (r = 0.850 with k, +0.098 marginal) — **one new dimension, not two**.
The eye rises monotonically in k and flattens at 6; the best boolean cut is **k ≥ 5**.

**D10's MA distance is dropped and the dimension keeps its ×1.** The split's catch-up test already
gates 100% of survivors, and the distance carries nothing once length is controlled (partial r
**+0.010**, p = 0.93) while correlating +0.606 with the gap that test already reads. The half that
does carry signal is **SMA20 rising** (r = +0.291), which costs no threshold. **Free numbers fall
from six to four**: `cluster_k`, `orderliness`, `dryup`, and the length band. Structure is
`rubric3.py`.

**The thresholds cannot be fitted on the grades that exist, and this is the reason round 3 exists.**
The two graded sets are **not poolable**: deck A was stratified on the old provisional score and
ticket 17's deck was not, and on the *same* population they differ by **+0.69★, p = 0.044** —
presentation and sampling moved together, so it cannot be untangled after the fact. Fitting anyway
on the 81 gives out-of-fold **r = +0.007** against +0.179 in-sample, with the two sources
disagreeing on four of five thresholds and `cluster_k` ranging over the whole grid fold to fold.
Round 2's thresholds merely re-pointed at the new domain score **+0.221**, better than anything
fitted. **No thresholds are published from this pass.** The one thing the fit does establish is
that the k dimension earns its place: out-of-fold +0.059 with it against **−0.152** when tightness
scores neutral.

**D13's partial-lock probe is de-scoped from a powered probe to a descriptive subgroup.** Over 2,244
accepted IDX detections, **98.1% have zero collapsed bars** and only 1.8% are partially locked — a
26-per-arm split cannot be drawn from it. The base moving from ~3 bars to ~14 is what did it.

**There are still zero graded IDX cards on any structure.** Round 2's deck A, round 2's ungraded
deck C and ticket 17's deck are all US.

### What is now waiting on the trader

[`PREREGISTRATION_R3.md`](../prototypes/15-grading-round-2/PREREGISTRATION_R3.md) fixes the round in
advance — including the trigger that would declare tightness unscorable (k's partial r below +0.15,
sending ticket 17's R6 fallback back to the trader). `build_deck3.py` has rendered **224 cards, all
bare**, which is the fix for round 2's confound:

| deck | cards | question |
| --- | --- | --- |
| `deck3_A.html` | 120 | the core round — fits the four free numbers. **The one that must be finished.** |
| `deck3_C.html` | 58 | IDX, asked for the first time: does it need its own thresholds? |
| `deck3_D.html` | 46 | the detector's own rejects vs its detections — ticket 11's unowned obligation |

12 repeats are hidden inside C3 and D3 for the **test–retest ceiling**, which has now gone
unmeasured twice; by the pre-registration no threshold is final until it is measured.

**To resume:** open `deck3_A.html`, grade, hit export, and run
`analyse3.py A=<string> [C=<string>] [D=<string>]`. The analysis is verified end to end on synthetic
grades (`analyse3.py --selftest`), so the numbers land the moment the grades do. Everything needs
**pandas 3.x** — the cached pickles use its string dtype.
