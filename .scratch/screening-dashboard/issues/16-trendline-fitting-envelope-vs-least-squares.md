# Trendline fitting: envelope or least squares?

Type: prototype
Status: open
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
