---
status: accepted
---

# Replacing a threshold with a graded input

ADR 0002 says what evidence licenses **loosening** a gate. It does not say what licenses
*changing the shape* of one, and #145 needed exactly that: the argument for restructuring base
tightness was never that the dimension is null — it is the best-evidenced dimension in the
study — but that a pass/fail line is the wrong encoding for what was measured.

Left in a docstring, that argument reads as a gate loosening that walked around the rule. This
ADR records it as a decision, with the conditions that have to hold before it can be reached
for again.

## What the rule says, and why it does not fit as written

ADR 0002's **score-dimension limb**: a dimension may be loosened only when A3 shows it has no
signal *and* real spread. Findings §3a applied that limb to `TIGHT_MULT` and refused the
loosening, correctly — Tightness is §5b's +20.8pp selector, so the precondition fails outright.

ADR 0002's **cross-sectional limb** does not apply: the cluster cut measures the name against
itself, not against the field. And that limb's own condition 3 points back the other way —
"a threshold move still requires the score-dimension limb above".

So on the face of it `TIGHT_MULT 1.5 → OUTLIER_MULT 3.0` is a threshold move governed by a
limb whose precondition is not met, and is not licensed. **That reading is right about the
threshold and wrong about the change**, because the change is not a threshold move with the
shape held fixed. The gate was removed. What replaced it is two different objects doing two
different jobs: a graded rubric input across the range where the signal varies, and a far
outlier guard where it does not.

## Decided (#145, implemented in #154)

**A threshold may be replaced by a graded input plus an outlier guard when all four hold.**

1. **The dimension has demonstrated signal.** Not a null — the opposite of the score-dimension
   limb's precondition. A null dimension should be weighted down or dropped, never elaborated.
   Tightness has selection signal (§5b, +20.8pp) *and* outcome signal (§3b).
2. **The outcome relation is smooth over the gated range, with no feature at the line.** This
   is the load-bearing condition and it is what distinguishes this from a loosening. It is
   #143's test, run in the other direction: that study set a *threshold* for entry-to-MA
   distance because the outcome data has a cliff there, and refused to site it at a percentile
   of his habits. §3b's table has no cliff anywhere — mean R declines monotonically and the
   decline through 1.5 is indistinguishable from the decline through 1.0 or 2.0 — so the same
   test that licensed a threshold there forbids one here.
3. **The dimension's weight does not move.** A shape change and a weight change must not ride
   together, or neither is attributable. Tightness stayed ×2.
4. **The population cost is stated**, as ADR 0002 condition 4 requires of any widening: how
   many more names the change admits, against what it recovers. Measured for #154 at **+111.3
   detections per session (+123%)**, or 0.66 additional names per session per executed trade
   recovered — reported in findings §3b beside the recall.

**The guard itself is a magnitude, and ADR 0001 does not license magnitudes from the replay.**
"The replay licenses the *direction* of a change, never its *magnitude*" (#128 Q2) is why the
rubric's weights are read off the *ordering* of the selection gaps and never their size.
`OUTLIER_MULT = 3.0` is a size. It is adopted anyway, under one explicit condition:

- **A guard sited on a magnitude is provisional, and carries its n.** 3.0 is sited on the only
  feature §3b's outcome table offers — the one bucket where mean R turns negative — and that
  bucket is **10 trades**. The constant is published as provisional in `detection.py`,
  `CONTEXT.md` and findings §3b, it is not to be swept or tuned on an in-sample number, and it
  is re-derived by the out-of-sample backtest (`docs/out-of-sample-backtest-plan.md`), which
  builds the denominator the negative tail needs.

The graded **bands** are not in that position: their edges (1.0 and 2.0 ADR) are §3b's own
published bucket boundaries and the points follow the *ordering* of the buckets, so they sit
inside ADR 0001's constraint as the weights do.

## Considered options

- **Leave the threshold at 1.5.** §3a's verdict, and correct on the evidence it had. Rejected
  once §3b measured the shape of the signal: the cut declines 35.6% of his own entries carrying
  17.4% of his summed R in order to express a quantity that varies smoothly, and the study now
  says the smoothness is real rather than unmeasured.
- **Move the threshold to a looser value.** The change ADR 0002 actually forbids, and rightly:
  it keeps the wrong shape, needs a magnitude the replay cannot license, and buys recall with
  nothing on the other side of the ledger.
- **Grade the dimension with no guard at all.** Rejected. A name with no quiet stretch is not a
  base at a low score, it is not a base — and the rubric would be asked to express, on a
  bounded scale, a distinction that is categorical.
- **Amend ADR 0002 rather than add this one.** Rejected: 0002 answers "what licenses a
  loosening" and that answer is unchanged. This is a companion, not a correction. The
  precedent for correcting a rule in place is 0002 itself replacing §7's carve-out, which was
  a case of the earlier rule being *wrong*; nothing here says 0002 is wrong.

## Consequences

- **The detector's population changed, so every field-derived figure is re-pinned.**
  `DETECTOR_VERSION` is 2, and rows from v1 and v2 are drawn from different populations — the
  stamp exists so that comparison cannot happen silently. Findings §3's detection row, §3's
  condition table and §4's `in_field` anchor (104 → **159 of 656**) are re-pinned from the
  2026-08-22 re-run. **Amended (#165, 2026-08-25):** that `in_field` pair was measured on the
  field the two-year rank retention had truncated (#164). On the whole chain the same
  restructure moves it **242 → 349 of 656**, and the live detector v3 reads **397 of 656**
  (findings §4b). The 104 → 159 above is left as the record of what this ADR was decided on;
  it is not the pin to anchor against.
- **Work moved from the gate to the sort key.** The names the guard admits are the ones the
  graded dimension scores low, so they arrive at the bottom of the list rather than beside his
  own setups. That is only a good trade if the sort key is trusted, which is why the grade is
  **banded to integral points** and published on the breakdown — a partial score has to read
  as a measurement the user can check, not as a number that appeared.
- **A graded dimension constrains what a breakdown row may store.** The row carries the
  *value*; the rubric version owns the value → points mapping. Storing a grade would make a v2
  re-score of a v3 row impossible and silently break the paired A2 re-run (#136), which exists
  precisely to separate a rubric change from a field change. See `screener.score.Rubric`.
- **This is hard to reverse in the direction that matters**, for the same reason ADR 0002 gives:
  every digest written after it freezes scores computed over a different field, and tightening
  back does not recover the record.
- **Condition 2 is the one that will be argued about.** "No feature in the outcome data" is a
  judgement over a table, not a test with a p-value, and §3b's is a side-car prototype on 649
  trades in one regime (§8). A future dataset that finds a cliff in the tightness relation
  would re-open this, and the honest response then is a threshold, not a defence of the grade.
