# Second grading round: fix the star-score thresholds

Type: prototype
Status: open
Blocked by: —

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
