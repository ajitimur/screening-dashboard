# The drawn triangle is a least-squares fit where the method wants an envelope

Raised by the trader after grading deck A: the triangle "doesn't sit quite well with my
expectation", with `~/Projects/q-scanner-v2` offered as a reference. It is not a cosmetic
complaint — measured below, it reaches ticket 08's trigger rule and ticket 09's F3.

## What the two implementations do

**Here (ticket 08 D2/D5, `fastscan.py`)** — the upper and lower boundaries are **ordinary
least-squares** fits through the highs and the lows. An OLS line through the highs runs through the
*middle* of them, so roughly half the highs sit above it. The trigger is that line's value at the
last bar.

**q-scanner-v2 (`qscan/pattern/lines.py`)** — the upper line is **anchored at the base's max high**
and extrapolated backwards, with its slope chosen from a descending grid by minimising an
**asymmetric loss** that weights overshoot 3:1 against undershoot. That is a ~75th-percentile upper
*envelope*: it rides the tops rather than bisecting them. The lower rail is the mirror image, a
pinball-loss quantile fit hugging the lows from below, plus a structural higher-lows check on swing
pivots. Validity is judged on touch zones and bounded overshoot — piercing is expected, per §3.2.

Both agree candles should pierce the lines. They disagree on where the line sits.

## Measured on deck A's 120 cards

Re-fitting the upper boundary as q-scanner's envelope and comparing the trigger it implies:

| fitted over | envelope vs OLS trigger | already-breached (trigger < close) |
| --- | --- | --- |
| the **primary** window | +0.09 ADR | **13.3% → 0.8%** |
| the longest window | +0.16 ADR | 13.3% → 9.2% |

**Ticket 09's F3 is largely an artefact of the fit.** F3 found 16.4% of setups emitted as
`WATCHING` with the trigger already below that day's close, and ticket 08 had flagged D5 as *"the
decision most likely to look wrong against real charts"*. It does look wrong — but not because the
`min()` rule is wrong. The OLS line sits below the highs by construction, so on a base whose recent
highs are near the close it lands under the close. Move to an envelope over the primary window and
the anomaly nearly vanishes: **0.8%**. The trigger only moves 0.09 ADR on average; it does not need
to move far, because it was sitting just barely on the wrong side.

## A second, separate defect: the deck drew the wrong window

Ticket 11's I5 settled that the chart draws **the primary window only** — *"drawing D3's retained
set would render the degeneracy, not the setup"*. `chart.py` draws both the retained-set band and
the primary band, and fits the triangle over the **longest** valid window while the trigger comes
from the **shortest**. So the deck's charts show a triangle over one base and a trigger derived from
another. That is ticket 09's prototype predating ticket 11's decision, inherited unexamined into
round 2.

## What this does and does not touch

**Deck A's grades stand.** The six thresholds fitted from them — contraction, orderliness, MA
distance, dry-up and the two length bounds — are computed from the bars, not from the drawn lines,
and none of them involves the trigger. The candles the trader graded were correct.

**Deck B does not stand.** Its entire split is *already-breached vs comfortably-above*, drawn from
OLS triggers. Under an envelope fit the breached arm is 0.8% of the pool — it barely exists. As
built, deck B would spend 52 graded cards probing an artefact of the fitting method rather than a
property of the setup.

## Where this belongs

Not in ticket 15. The rubric's thresholds are ticket 15's question; **which line the detector fits
is ticket 08's D2/D5, and what the chart draws is ticket 11's I5.** Both are resolved tickets, so
this is an amendment to them, not a re-litigation inside a grading round — and it needs its own
decision about whether to adopt an envelope fit, which is a change to the detector with knock-on
effects on the trigger, the stop and the affordability gate that rejected 5,674 gated dates.
