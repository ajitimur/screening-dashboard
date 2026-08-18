---
status: accepted
---

# The star score is calibrated against the method's revealed selection

The star score's eight thresholds were fitted against **our own grading** of charts — the only
measured calibration on record is precision 0.53 / recall 0.28 at 4★ against that grading
(ticket #53). Nothing in the repo ever wrote down what the rubric was *supposed* to encode, so
when the Qullamägi replay (#114) measured the rubric against Kullamägi's own 658 replayable
entries and found it wanting, there was no way to tell whether that was a defect report or
merely a measurement that two eyes differ.

**Decided (#128): the star score is calibrated against the method's revealed selection.**
Kullamägi's executed trades are the best available evidence of what the Qullamaggie
Breakout/Continuation method actually selects; our grading was a proxy adopted because nothing
better existed at the time, and something better now does. Findings from the replay are
therefore admissible against the rubric.

## Considered options

- **Our own eye.** The rubric encodes how we grade a chart, and §5b of the findings is not a
  defect report but a measurement that our eye and Kullamägi's differ. Rejected: if this were
  true, `references/qullamaggie-replay-findings.md` could never say anything about the rubric
  at all, and the entire validation half of PRD #114 was scoped wrong from the start.
- **Outcome.** The rubric predicts which setups run. Not available: §5a of the findings found
  no dimension predicts MFE (largest |r| = 0.158, pointing the wrong way).

## Consequences

- The trade record is **evidence, not authority**. A companion rule (#128, Q2) bounds it: the
  replay licenses the *direction* of a change, never its magnitude, because the signs of the
  measured selection gaps are robust to the field's 29% coverage hole and the values are not.
- Any future study may argue against the rubric from selection contrast. None may argue from
  **outcome** (§5a is null) or from **A2** (a null on 104 of 658 trades against a holed field —
  evidence against discrimination, not proof of its absence).
- This is hard to reverse in practice: the reweighting it licensed (#128) changes the rubric's
  ceiling and star range, and the digests written under each rubric are not retroactively
  recomputed. A reversal would have to unpick both.
