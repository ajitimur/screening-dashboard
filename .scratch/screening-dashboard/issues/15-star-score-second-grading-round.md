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
