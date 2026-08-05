# Star score calibration

Type: prototype
Status: resolved
Blocked by: 08

## Question

Does the computed 1–5 star score agree with your eye?

§3.5 gives the rubric — 8 dimensions, tightness and orderliness weighted ×2, max 10, stars = score ÷ 2,
trade 4–5 stars full size. Ticket 08 makes each dimension computable. This ticket checks whether the
composition actually produces the grades you'd give.

Build a throwaway prototype that scores real historical setups and puts the chart next to the score, then
sit with it and disagree with it. Specifically:

- Pull a set of known-good historical examples (his own named ones where available — the ZM / AR / APPS
  worked examples in §3.2 — plus names you recall) and a set of known-bad ones ("barcode", wide and
  loose, low ADR, no prior move).
- Score them. Where does the score disagree with your judgement, and in which direction?
- Are the ×2 weights right, or does one dimension dominate in practice?
- Is the 4-star trade threshold in the right place, or does it admit junk / reject winners?
- Are the sub-scores better as booleans (§3.5's "1 point if…") or as continuous 0–1 values? Booleans are
  faithful to the rubric but throw away information near thresholds.
- Does the score need to be per-market calibrated? IDX and US have different volatility regimes.

Output: a calibrated rubric with concrete thresholds, plus a record of the disagreements — the failure
cases are as valuable as the parameters. Link the prototype rather than pasting it here.

## Added by ticket 08

Ticket 08 resolved and made every §3.5 dimension computable. Three items land here beyond this ticket's
original scope, all of them things only a session sitting with real charts can settle:

- **The trigger rule (08 D5).** The trigger is `min(max high of primary window, fitted descending line)` —
  chosen to bias toward the earliest, nearest-the-MA entry, with the accepted cost of more signals and more
  false breaks. 08 flags this as the decision most likely to look wrong against real charts. Check whether
  the early trigger is buying strength or noise.
- **IDX limit-day flattery (08 D13).** No ARA/ARB handling ships in v1. A limit-locked bar has a collapsed
  high/low range, which flatters BOTH ×2 dimensions at once — extreme contraction and minimal churn — so a
  dead stock can score as a textbook base. A generic liveness floor (median base daily range vs the name's
  longer-run ADR) was designed and declined; adopt it if the prototype shows false five-star IDX setups.
- **Half-measured volume (08 D11).** Only dry-up is scored; break-day expansion is persisted but never
  touches the score, so §3.5's volume dimension carries half its intended content. Check whether dry-up
  alone discriminates, or whether the score needs a `TRIGGERED` variant after all.

Also relevant to this ticket's "booleans or continuous values" question: 08 D16 keeps the raw signal vector
internal but **persists it nightly**, specifically so recalibration here can be replayed over accumulated
history rather than only applied forward.

Two properties of 08's output shape this ticket inherits: the detector has **zero tunable parameters** (the
only numeric constants are the method's own — L ≥ 3 and 1×ADR), and **every scored quantity is a ratio**, so
per-market calibration is not forced by scale differences alone.

---

## Answer

**No — the score as ticket 08 specifies it does not agree with the trader's eye, and the reason is
structural rather than a matter of thresholds.** Blind-graded against 27 charts the two are
uncorrelated (pearson **−0.043**, 44% within one star, machine **+0.74★** too generous on average).

That is the headline, but the useful part is that the disagreement lies on a single axis, which makes
it fixable. Full measurements in
[the prototype's findings](../prototypes/09-star-score/FINDINGS.md); the deck itself is
[`deck.html`](../prototypes/09-star-score/deck.html).

Scope of the evidence: 650 US names → **24,664 detections** (2019–2023) plus 77 IDX names → **6,946**,
with ticket 08's detector implemented twice (readable reference + vectorised sweep, verified
field-identical). The universe is a reduced, survivorship-biased sample, exactly as ticket 02
predicted — accepted because every conclusion below is a *comparison between* score bands, not a
level.

### D1. The star score is largely a proxy for base length — and ticket 08's D14 is why

The share of candidates reaching ≥4★ rises from **0.9%** (bases of 3–5 bars) to **63.6%** (41–60 bars),
monotonically. Both ×2 dimensions carry base length: contraction rises with L, churn/L falls with it.
So **4 of the 10 points collapse onto one axis §3.5 never names**.

The trader reads that axis the other way: `L_longest` correlates **−0.558** with his grades and
**+0.622** with the machine — the strongest correlate on both sides, opposed, and the only one in the
graded set clearing significance.

**Root cause: D14 is false.** D14 argues no `Lmax` is needed because reaching back into the momentum
leg tips the highs fit positive, so the 60-bar compute bound *"never binds"*. It binds — **22.9% of
detections have bases ≥ 30 bars and 1.8% hit the 60-bar bound** (p95 = 54). The triangle test does not
self-cap, so §3.4's *"months of sideways with no momentum leg in front of it → skip"* is not merely
unenforced: it is what tops the score. This is the ticket's most consequential finding and it
invalidates a decision ticket 08 counted among its zero-parameter wins.

### D2. Base length is a score penalty, not a gate — but the penalty is not the fix

**Trader's call: penalty, not gate.** Detection is left alone (08's end-anchored search stands, no
`Lmax`), and long bases lose a point instead of disappearing.

Measured, the penalty alone is close to useless — agreement moves only −0.043 → **+0.076**. One ×1
point shifts the grade half a star while 4 points of length-driven ×2 signal push the other way. **The
fix is to decouple the measurement**: score both ×2 dimensions over `min(L, 20)` — §2's own 10/20-day
horizon, not a new invention — with contraction as *older-half range ÷ recent-half range*, which is
length-matched by construction and drops the √L baseline entirely.

| rubric | r | mean abs error | within 1★ |
| --- | --- | --- | --- |
| ticket 08 as written | −0.043 | 1.77★ | 44% |
| + length penalty only | +0.076 | 1.57★ | 48% |
| + length-decoupled ×2 measures | **+0.259** | 1.33★ | **63%** |
| both | +0.252 | **1.24★** | 56% |

Adopt both: decoupled measurement (does the work) plus the penalty (best mean error, and it makes
§3.4's anti-pattern visible in the grade rather than silent).

### D3. D7's contraction has its sign inverted in ticket 08

D7 reasons that a contracting base's `range(L)` curve grows *flatter* than √L. It does not — the
window is **end-anchored**, so extending it backwards adds the wide older bars and the curve grows
**faster**. Controlled synthetics with per-bar disorder held fixed: flat channel **0.86**, tight cone
**1.59**. On real data the median is **1.35**, so under 08's literal reading the median detected base
scores as *expanding*. The measure is sound; the sign is backwards.

Superseded in part by D2 — the replacement half-vs-half measure has no √L baseline to invert — but
recorded because anything reusing D7's formulation needs the correction.

### D4. D8's churn is not scale-free in base length; divide by L

D8 calls churn *"parameter-free and scale-free"*. It is scale-free in **price**, not in **L**: at
fixed disorder it runs **2.20 → 18.36** as L goes 5 → 60, because the numerator accumulates per bar
and the denominator does not. `churn / L` runs 0.441 → 0.306 and still separates smooth drift (0.188)
from barcode (0.618). D8's substance survives; only its normalisation changes.

### D5. A single valid window scores neutral on tightness, not zero

**Trader's call.** 19.8% of detections have only one valid window, making D7's contraction
unmeasurable; scoring a ×2 dimension **zero** there penalises hardest exactly the short tight bases the
trader graded 3–4 (MBUU, ENPH, HXL all scored 1–1.5). Unmeasurable means *no evidence*, so it takes
half credit. Same treatment for an unmeasurable dry-up.

### D6. The length point is paid for by "higher lows intact", which is free

§3.5's higher-lows dimension is true for **92%** of detections **by construction** — D9 makes it the
low-side fit slope, and window validity already requires that slope ≥ 0. It carries no information.
Spending it on base length keeps §3.5's eight dimensions, its max of 10 and `stars = score ÷ 2` — no
ninth dimension, no rescaling.

### D7. Thresholds remain provisional — this is the ticket's shortfall

The ticket asked for *"a calibrated rubric with concrete thresholds"*. **The structure is corrected;
the thresholds are not settled.** At n=27 a correlation needs |r| > 0.38 to clear p<0.05 and the best
variant reaches **+0.26**. The corrected rubric moves the score from *actively uncorrelated* to
*weakly positive* and cuts typical error from 1.77 to ~1.24 stars — real, but not calibration.

**A second grading round is required**, and it is now a sharp question rather than fog — see
[Second grading round: fix the star-score thresholds](15-star-score-second-grading-round.md).

### D8. Outcomes cannot arbitrate the rubric, at any point in this ticket

Forward outcomes modelled per §7 (entry at trigger within 10 bars, stop at base low, 30-bar hold, in
R). Over the gated set the 4★ and 5★ bands lead, which supports §3.5's *"trade 4–5 stars"* line — but
the 5★ band is **n=33 against a 0.48R standard error**, a 1.41 SE gap, and **every one of the eight
dimensions is non-monotone against R**. Resolving a 0.3R difference between bands needs **~672
triggered setups per band**.

Two cautions recorded for whoever revisits this. First, the top band is **unstable**: an early run with
the sector dimension still downloading put 4★ ahead of 5★; completing one ×1 dimension reversed them.
Second, on the 27 graded charts **neither party graded in the direction outcomes went** — the trader's
≥4★ picks averaged −0.12R against +0.77R for the rest, the machine's −0.51R against +1.44R. At n=27
with R's standard deviation near 2.75 this is uninterpretable alone, and is written down only so a
later round does not mistake it for news.

### D9. D13's limit-day hazard is real but sits where ticket 08 did not look

Collapsed-range bars are common and concentrated on IDX (DEWA 57.3% of bars, MEGA 18.0%, BRMS 15.9%;
2.18% across all names). But 08's predicted failure — *a dead stock scoring as a textbook base* —
**does not occur**: bases more than half composed of locked bars reach 4★ **zero times**, because only
1.5% clear ADR ≥ 5% and a flat base does not score high on contraction either.

The exposure is the band 08 did not name: **partially** locked bases (1–20% locked bars) score **best
of any group** — 24.9% reach 4★ — with visibly flattered orderliness (0.243 vs 0.360 baseline).
Consequently **the generic liveness floor 08 designed and declined would have been aimed at the wrong
case**: it targets median-liveness, catching the fully-locked bases the ADR dimension already handles
for free, and missing the partial ones. Any fix must key on *individual* collapsed bars inside the
base. Not fixed in v1; the graded IDX cards (3, 1, 4 against 2, 3 for clean bases) show nothing at this
sample size.

### D10. D5's trigger rule survives unexamined

98.3% of triggers are set by the fitted line, so the `min()` against the flat max-high is nearly dead
code, and **16.4% of detections are emitted `WATCHING` with the trigger already below that day's
close**. 08 flagged D5 as the decision most likely to look wrong against real charts — but
trigger-vs-close correlates **+0.012** with the grades, i.e. the eye was indifferent to how early the
trigger sat. **Still open**, carried into the second grading round, where it needs charts chosen to
probe it rather than a general sample.

### Two properties of the result

**Ticket 08's zero-parameter property does not survive.** The corrected rubric introduces a
**20-bar measurement horizon** and a length penalty band. Both are read off the method (§2's 10/20-day
MAs, §3.4's anti-pattern) rather than fitted, but they are choices where 08 had none — the honest
statement is that the parameter count went from zero to two, and D1 is why it had to.

**Every scored quantity is still a ratio.** Ticket 05's prediction continues to hold: nothing in the
corrected score is anchored to an absolute price level on either market.
