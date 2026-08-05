# Confirm the orderliness band, and measure the ceiling every correlation is judged against

Type: prototype
Status: open
Blocked by: —

## Question

Is ticket 15's fitted rubric real, and how good could any rubric be?

[Ticket 15](15-star-score-second-grading-round.md) resolved with a working rubric — out-of-fold
**r = +0.255**, the first time the score has cleared significance on ticket 17's structure — but it
resolved with two numbers it could not stand behind, and both are cheap to settle because **the
decks are already built and rendered**.

### 1. The band was chosen after seeing the grades

Ticket 15's R2 redefined orderliness from a one-sided cut to a **band**, `0.275 ≤ churn/L ≤ 0.50`,
because on a ~14-bar base the one-sided form was counterproductive and the fit responded by awarding
its point to 99% of cards. The change has a mechanism behind it — a synthetic control shows the gap
between an *orderly* base and a *gap-then-dead* one narrowing 2.9× → 1.8× → 1.65× as L goes 3 → 14 →
30, so a one-sided cut leaks the point to lifeless bases — and the trader adopted it on that
reasoning.

But it was chosen **after** deck A3 was graded. Cross-validation controls the threshold *values*, not
the choice of functional form, so **+0.255 is optimistic and the band is a hypothesis with fitted
numbers**. §6 of
[`PREREGISTRATION_R3.md`](../prototypes/15-grading-round-2/PREREGISTRATION_R3.md) already fixes the
bar: **the band is credited only if it reproduces out-of-fold at r ≥ +0.20 on grades collected after
that document, on the split's population.** If it does not, orderliness is dropped and its ×2 is
redistributed.

### 2. The test–retest ceiling has gone unmeasured for two rounds

Every correlation on this map — ticket 09's −0.043, round 2's +0.189, ticket 15's +0.255 — is
reported against an **unknown maximum**. Round 2's 12 repeats lived in decks that were never graded;
round 3's live in decks C3 and D3, which are rendered and were deferred.

This is not bookkeeping. At r = +0.255 the live question is whether the rubric is weak or the target
is noisy, and nothing else on the map can answer it. By ticket 15's own pre-registration **no
threshold it published is final until this is measured**, and if the ceiling comes back below ~0.6
the thresholds are provisional whatever they fit.

### 3. Two obligations ticket 15 could not discharge

- **Per-market calibration.** There are still **zero graded IDX cards on any structure**, across
  ticket 09, round 2 and ticket 17. Deck C3 is the first IDX deck that has ever existed. The rule is
  pre-registered: IDX gets its own thresholds only if the pooled fit's mean residual on IDX differs
  from US by > 0.5★, or an IDX-only fit beats pooled on IDX cards by > 0.15★ out-of-fold.
- **The rejected candidates.** Ticket 11 ruled there is no rejected-candidates view in v1 and handed
  the inspection of the discarded set to ticket 09, which did not do it; round 2's deck D was never
  graded; ticket 15 rendered deck D3 and stopped. **The obligation has now been passed along three
  tickets without being discharged.** If the rejects grade as well as the detections, the detector is
  throwing away setups the trader wants — and ticket 17 changed *which* names are rejected, so the
  question is live rather than inherited.

## What to do

Nothing needs building. Grade the two rendered decks and run the existing analysis:

| deck | cards | carries |
| --- | --- | --- |
| `prototypes/15-grading-round-2/deck3_C.html` | 58 | IDX calibration · 12 locked cards (descriptive) · 6 repeats |
| `prototypes/15-grading-round-2/deck3_D.html` | 46 | 20 rejects vs 20 detections · 6 repeats |

Then `analyse3.py A=<grades3_A.txt> C=<string> D=<string>` — sections 5, 6 and 7 are already written
and verified on synthetic grades, and section 7 is the ceiling.

**One caution.** The confirmation in §1 needs grades on the split's population collected *after* the
band was chosen. Deck C3 is IDX and deck D3 is half rejects, so **neither is a clean confirmation
set for the band** — they settle the ceiling, the market question and the rejects, but a fresh US
deck on the split's accepted population is what §1 actually requires. Size it from
`PREREGISTRATION_R3.md` §2 and re-use `build_deck3.py` with a new seed.

Needs **pandas 3.x** — the cached pickles use its string dtype; a `.venv` exists in the ticket-15
worktree.
