# Does the `line_not_drawable` rejection path discard setups you want?

Type: prototype
Status: open
Blocked by: —

## Question

[Ticket 23](23-the-rejected-candidates.md) answered the pooled question — the split's rejects grade
−0.90★ below its detections, so the detector is keeping the better names and the star score is
calibrated on the right population. **That answer is carried almost entirely by one of the two
sampled rejection paths.**

| path | n | mean eye | Δ vs detections (3.20) | 95% CI |
| --- | --- | --- | --- | --- |
| `no_cluster` | 10 | 1.80 | −1.40★ | −2.44 to −0.36 |
| `line_not_drawable` | 10 | 2.80 | −0.40★ | −1.22 to **+0.42** |

`no_cluster` separates even at n=10. `line_not_drawable` does not: the interval spans zero, −0.40★
is **below the eye's own 0.56★ noise floor**, and **3 of its 10 cards graded 4★** — CLMT 2017-09-20,
BELFB 2019-09-18, GGT 2020-07-23 — against a detection arm that itself only reaches 3.20 with 9 of
20 at ≥4★.

So this is not a null to be read as a pass. It is the one place ticket 23's answer does not reach,
and it is a live possibility that a whole rejection path is discarding tradeable setups.

**What it takes.** `PREREGISTRATION_R3.md` §2: a two-group mean-grade difference of 0.75★ needs
**33/arm** at 80% power. Ticket 23's deck had 10. A deck of 33 `line_not_drawable` rejects against
33 accepted detections, bare and mixed in the deck3 style, is the honest instrument — roughly 66
cards plus repeats, one more grading sitting. `build_deck3.py` already samples both populations, so
nothing new needs designing.

**Pre-register the rule before the deck is built**, in the deck3 style: name in advance what
Δ counts as "this path discards setups you want" and what the remedy is if it does — the path is
loosened, replaced, or downgraded from a hard reject to a scored penalty. Ticket 23's write-up is
explicit that a marginal result must be reported as marginal.

**Read against the ceiling.** Test–retest r is +0.831 on 18 pairs, mean absolute difference 0.56★.
A 0.75★ target sits only just above single-grade noise, which is exactly why the arm has to be
33 and not 20.

**Not in scope here:** the third rejection path, `not_caught_up` (1.6% of bar-dates, never sampled).
If the eye is being asked for another sitting anyway, decide deliberately whether to carry it —
but it is a separate population and a separate question.
