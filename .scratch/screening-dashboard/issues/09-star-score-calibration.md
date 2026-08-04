# Star score calibration

Type: prototype
Status: open
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
