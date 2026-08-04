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
