---
status: accepted
---

# What evidence licenses loosening a gate

PRD #114 wrote down a calibration rule to stop one number driving an unguarded change:

> A gate may be loosened on the strength of an A1 recall miss only when A3 shows that
> dimension has no signal *and* that dimension shows real spread.

The rule exists because **precision is not measurable**. The reference set records no setup
Kullamägi declined, so there is no control group and no false-positive rate; recall is
one-sided by construction, and widening a gate always improves it. The A3 two-condition test
was the instrument: a dimension may only be loosened away on a null that is not merely range
restriction.

The instrument does not fit every gate. The rule was written contemplating **score
dimensions**, and it silently assumed every gate has an A3 dimension standing behind it. The
decile gate does not. Its dimension, `Prior move`, is 100% in the executed trades *and* 100%
in the not-taken detections, with spread 0.000 in both — every detection cleared the decile
gate by construction, so the contrast that exists precisely to buy back missing variance
cannot restore it. No study this project can run will ever supply the evidence the rule asks
for.

That left the single largest measured loss in the funnel — the decile gate discards ~40% of
his real entries, against liquidity's 9% — governed by a test it can never pass. §7 of
`references/qullamaggie-replay-findings.md` resolved this by carve-out, ruling that the rule
governs score dimensions and that the decile gate, being "a cross-sectional cut whose loss is
measured directly by A1", falls outside it. That is technically correct and practically
inverted: it exempts the most expensive gate in the system from the only guard the project
has.

**Decided (#133): the calibration rule has two limbs, one per kind of gate.**

**A score dimension** may be loosened only when A3 shows that dimension has no signal *and*
that dimension shows real spread. Unchanged from #114.

**A cross-sectional cut** — a gate that ranks a name against the field rather than measuring
the name itself — may be loosened only when all four hold:

1. **The loss is measured directly.** A1 reports the stage's recall miss unconditionally, not
   inferred from an A3 null.
2. **The loss is shown not to be a coverage artefact.** The miss is decomposed into names
   absent from the replayed field and names present but ranked outside, and the ranking half
   is what is being acted on. A coverage gap is a defect in the replay, not evidence about
   the gate.
3. **The change is structural, not a threshold move.** A discrete widening of what the gate
   unions has no magnitude to get wrong. Moving a threshold does, and a threshold move still
   requires the score-dimension limb above.
4. **The population cost is stated.** The change must name how many more names the gate admits
   per trade recovered, as a share of the universe.

Condition 4 is the load-bearing one. It is the substitute for the precision measurement that
does not exist: false positives cannot be counted, but the *population* a looser gate admits
can be, and that ratio is the honest denominator. A recall improvement quoted without it is
the one-sided number the original rule was written to prevent.

## Considered options

- **Hold the original rule unchanged.** The decile gate can never be loosened, because A3 can
  never speak to `Prior move`. Rejected: a rule that cannot be satisfied by any obtainable
  evidence is not a guard, it is a freeze — and it freezes the stage costing the most.
- **Keep §7's carve-out.** Cross-sectional cuts sit outside the calibration rule and are
  argued from A1 alone. Rejected: A1 recall is exactly the one-sided metric the rule exists to
  guard, so an exemption from the rule for the gate with the largest recall miss inverts the
  rule's purpose.
- **Require a precision measurement.** Rejected as impossible, not merely expensive. It would
  need a record of setups he declined, which no part of the reference set contains.

## Consequences

- The rule now composes with ADR 0001's companion constraint (#128, Q2): the replay licenses a
  change's *direction*, never its *magnitude*. Condition 3 is why this bites less on
  cross-sectional cuts — a structural widening has no magnitude to license.
- §7 of `references/qullamaggie-replay-findings.md` cites this ADR rather than restating the
  rule. The rule's authoritative wording no longer lives in a GitHub issue body.
- The first change this licenses is not made here. ADR 0003 applies the four conditions to the
  decile gate and reaches `proposed`, not `accepted`, because condition 2 is only 46%
  measured pending #131.
- The rule is stated in terms of *kinds* of gate, and so says nothing about a change that
  alters a gate's **shape** rather than its position. ADR 0004 is the companion covering that
  case — a threshold replaced by a graded rubric input plus an outlier guard — and it is a
  companion rather than a correction: nothing in it says this rule is wrong.
- The rule is stated in terms of *kinds* of gate, so the liquidity floor — also
  cross-sectional through its hysteresis band — falls under the same four conditions if it is
  ever argued about. It currently costs 9% and nobody is arguing.
- This is hard to reverse in the direction that matters: any gate loosened under these
  conditions changes which detections exist, and every digest written afterwards freezes
  scores computed over a different field. Tightening back does not recover the record.
