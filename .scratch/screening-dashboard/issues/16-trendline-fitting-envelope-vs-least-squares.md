# Trendline fitting: envelope or least squares?

Type: prototype
Status: resolved
Blocked by: —

## Question

Should the base's upper and lower boundaries be fitted as **envelopes** that ride the extremes, or
as the **least-squares** lines ticket 08 specified — and what does that change downstream?

Ticket 08's D2 fits the boundaries by ordinary least squares through the highs and the lows, and
D5 derives the trigger from the upper line's value at the last bar. An OLS line through the highs
runs through the *middle* of them by construction, so about half the highs sit above it.

The trader raised this after grading ticket 15's deck A — the drawn triangle "doesn't sit quite
well with my expectation" — and offered `~/Projects/q-scanner-v2` as a reference implementation.
There the upper line is **anchored at the base's max high** and extrapolated backwards, its slope
chosen from a descending grid by minimising an **asymmetric loss** weighting overshoot 3:1 against
undershoot: a ~75th-percentile upper envelope that rides the tops. The lower rail mirrors it as a
pinball-loss quantile fit hugging the lows from below, with a structural higher-lows check on swing
pivots. Validity is judged on touch zones and bounded overshoot, so piercing stays desirable per
§3.2 — the two implementations agree on that and disagree only on where the line sits.

**This is not a cosmetic question, which is why it is a ticket rather than a chart tweak.** Measured
on ticket 15's 120 deck-A cards ([the working](../prototypes/15-grading-round-2/TRIANGLE_FINDING.md)):

| fitted over | envelope vs OLS trigger | already-breached (trigger < close) |
| --- | --- | --- |
| the **primary** window | +0.09 ADR | **13.3% → 0.8%** |
| the longest window | +0.16 ADR | 13.3% → 9.2% |

So **ticket 09's F3 is largely an artefact of the fit.** F3 found 16.4% of setups emitted as
`WATCHING` with the trigger already below that day's close, and ticket 08 had flagged D5 as *"the
decision most likely to look wrong against real charts"*. It does look wrong — but the defect is
where the line sits, not the `min()` rule. The trigger need only move 0.09 ADR because it was
sitting barely on the wrong side.

Specifically:

- **Adopt the envelope, or keep OLS?** The evidence above is one-sided on the trigger, but the
  envelope buys parameters: a slope grid, an overshoot:undershoot weight, a touch tolerance, a
  minimum touch count. Ticket 08 resolved with **zero tunable parameters** and ticket 09 already
  cost that property (the count is two). Decide what the envelope is worth against what it costs,
  and say so explicitly rather than letting the count drift.
- **The stop and the affordability gate move too.** The stop is the base low and the gate rejects
  when trigger-to-stop exceeds 1×ADR. A higher trigger widens that distance, so the gate bites
  harder — and it already rejects **5,674 of 13,482** decile-gated bar-dates (ticket 15's R3). Size
  that before adopting anything.
- **Does validity change?** q-scanner judges a line by touch zones and bounded overshoot; ticket 08
  judges a window by the sign of two OLS slopes. Ticket 08's test is what makes the search
  self-capping. An envelope-based validity test may not be, and D14 has already been found false
  once (ticket 09).
- **What does the eye say?** The measurement says the OLS trigger is too low; it does not say the
  envelope trigger is right. Ticket 15's deck B was built to ask exactly this and cannot: its split
  is breached-vs-not from OLS triggers, and under an envelope the breached arm is 0.8% of the pool.
  A rebuilt deck B belongs to whichever line this ticket picks.

**A second, separable defect, already established and not up for decision here.** Ticket 11's I5
settled that the chart draws **the primary window only** — *"drawing D3's retained set would render
the degeneracy, not the setup"*. Ticket 09's `chart.py` draws both the retained-set band and the
primary band, and fits the triangle over the **longest** valid window while the trigger comes from
the **shortest**, so the deck's charts showed a triangle over one base and a trigger from another.
That is a conformance bug against a resolved decision, not an open question; it is recorded here
only because it is the other half of what the trader saw.

**Do not re-litigate** ticket 08's end-anchored backward search, its elimination of pivot detection,
or §3.2's principle that piercing bars are desirable. Both candidate fits honour all three.

---

## Resolution

Measured over the whole round-2 pool (31,553 detections) and, for the structural question, over
318,357 bar-dates. Full working in [`prototypes/16-trendline-fit/`](../prototypes/16-trendline-fit/),
headline numbers in its [`FINDINGS.md`](../prototypes/16-trendline-fit/FINDINGS.md).

**The ticket's question was not the load-bearing one.** "Envelope or least squares" is the smallest
of three separable choices, and answering it alone would have changed little.

### R1. F3 is confirmed as a fitting artefact

Already-breached goes **16.0% → 2.1%** under the envelope and **→ 0.2%** under q-scanner's clamp,
with residual breaches a median 0.003 ADR deep against 0.097 today. Ticket 08's suspicion that D5's
`min()` rule was the culprit is wrong; the defect was where the line sat.

### R2. The clamp is a bigger lever than the fit, and the two were conflated

q-scanner does not derive its trigger from the line at all: `trigger = max(line_at(t+1),
cluster_high)` — it clamps **up** to the recent high, where D5 clamps **down** to it. It also anchors
on the trailing 3–7 bar cluster, not the whole base, and stops at the **cluster low**, not the base
low. The `max()` clamp binds on 82% of detections, so where it binds the line is irrelevant — OLS and
envelope give numerically identical results. The ticket's +0.09 ADR headline understated the move
because it measured a mis-specified anchor.

### R3. D6 is no longer a gate — the stop is the trader's call

**Decided by the trader.** The 1×ADR affordability test is an entry-time judgement, not a screening
criterion: this is a scanner, its job is to identify setups, and the stop only matters once a trade
is being entered. D6 becomes a **displayed quantity and sort key, never a hard cut** — reversing
ticket 08's *"hard rejection, not a flag"*.

This does not stand alone. D6 was the only thing holding the list down: ungated, the nightly list
goes **~64 → ~314 US names** (IDX ~12 → ~47), against ticket 11's ~10-minute review. Ticket 08's own
justification shows why — *"this gate is what §3.4's first auto-reject (loose, wide-range
consolidation) looks like in numbers"*. **D6 was doing two jobs under one number**: §7 affordability
(the trader's) and §3.4 looseness (the app's).

**They are separated.** Stop width is shown, never enforced. A looseness cut stays, expressed as a
property of the **base** rather than of the trader's affordability.

Knock-on: **D7 must be repaired.** It scores tightness as only "narrowing", not "narrow", because
narrowness *"is already pass/fail"* via D6. With the gate gone, "narrow" is captured nowhere and the
×2 tightness dimension measures half of §3.5. Whatever cut replaces D6 has to restore it.

### R4. The window — D4 — is the real decision, and it is not this ticket's to make

D4 takes the **shortest** valid window as primary: **3 bars on 52%** of detections, ≤5 on 83.6%.
No fit means anything over three points, so R1 and R2 are nearly moot where the trigger is computed.
D4 accepted that degeneracy knowingly (every distance quantity over an end-anchored window is
monotone in L, so any argmax collapses to L=3) and defended it as the earliest, most affordable
entry — an argument that holds for tightness and MA proximity but does not carry to a **line fit**.
Ticket 08 flagged D5 twice as *"the decision most likely to look wrong against real charts"*.

Measured, q-scanner's base/cluster split answers R3's looseness cut and R4's window together:

- base = prior move's peak → today (median **14 bars**, IQR 8–22), with a 3–7 bar cluster spanning
  **≤ 1.5×ADR** inside it, on a rising MA;
- **the stop is bounded by construction** — trigger-to-stop cannot exceed the cluster's range,
  measured max **1.499 ADR** across 54,201 detections, so no affordability gate is needed at all;
- with q-scanner's own ≥25% prior-move floor the list lands at **~63 US / ~11 IDX per night**,
  against today's ~64 / ~12.

That is the looseness cut R3 needs, stated as a property of the base exactly as the trader asked.

**But adopting it replaces D2, D3 and D4 in ticket 08**, and D3's retained window set is what makes
contraction scorable in D7 — which ticket 15's rubric is built on and which is in flight. That is a
larger amendment than this ticket can carry, and the measurement here is **structural only**: it does
not check that the setups it finds are the ones the eye wants. Graduated to its own ticket, which
this one blocks.

### R5. The conformance bug is fixed, not decided

Ticket 09's `chart.py` drew the triangle over the **longest** window while the trigger came from the
**shortest**, against ticket 11's I5 — so deck A showed a triangle over one base and a trigger from
another. Given R4's 3-vs-13 bar gap this is very likely the bulk of what the trader's eye objected
to. `chart16.py` draws the primary window only, per I5.

### What this ticket does not settle

The eye question. `deck16.html` is built and verified (50 cards, blind A/B, seed 16) but was **not
graded**: its cards inherit the 3-bar median, so it would ask the eye to choose between two lines
through three points. It should be rebuilt over whatever window the successor ticket settles.

Status: resolved
