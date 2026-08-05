# The 4-star cut under the adopted objective

Measurement for [ticket 27](../../issues/27-level-or-order.md), run *after* the trader had answered
its two questions and therefore **reporting a consequence, not choosing anything**. No threshold,
cut or rule is selected here. Reproduce with `cutpoints.py`; raw output in `CUTPOINTS_OUTPUT.txt`.

Ticket 27 settled that the star number is a label for a rank plus its cut points, so R6 §2's mae
guardrail falls and `cindex` is adopted; and that §3.5's `points ÷ 2` mapping stands unchanged. The
second choice leaves exactly one number open — [ticket 15](../../issues/15-star-score-second-grading-round.md)
R5 measured precision at the 4★ line as 0.53 under the incumbent `T3`, and under `cindex`'s
thresholds the printed level is no longer what any loss controls.

## 1. The trade line is not damaged — it improves

Like-for-like, both objectives fitted the same way (5 folds × 5 assignments, out-of-fold, E3):

| objective | precision @4★ | recall @4★ | n called |
| --- | --- | --- | --- |
| `mae` (incumbent) | 0.47 (0.39–0.54) | 0.26 | 35 |
| **`cindex`** | **0.49** (0.40–0.52) | **0.40** | **50** |

`cindex` wins on **both** axes: it calls half again as many names and is slightly more precise doing
it. The worry that motivated R6 §2's guardrail — that adopting a rank objective would wreck the
level where the level is actually read — does not materialise at the one place it is read.

Frozen (no fitting, no folds) on E3, precision at 4★ goes **0.50 → 0.51**.

## 2. Which thresholds are worth publishing

The incumbent `T3` **already** carries `cluster_k` 5 and `ord_hi` 0.60 — exactly `cindex`'s picks.
So of the three thresholds R6 §4 calls stable, adopting `cindex` moves precisely one, by one grid
step: `ord_lo` 0.275 → 0.30. Everything else `cindex` won comes from the two R6 §4 calls **unstable**.

| published set | ρ (E3 / pooled) | mae | precision @4★ | recall @4★ |
| --- | --- | --- | --- | --- |
| `T3` incumbent | +0.327 / +0.358 | 1.18 / 1.15 | 0.50 / 0.53 | 0.45 / 0.37 |
| **stable-only** (`T3` + `ord_lo` 0.30) | +0.338 / +0.361 | 1.17 / 1.15 | **0.52 / 0.54** | 0.44 / 0.31 |
| full `cindex` (+ `dryup` 0.85, `len_ok` 20) | **+0.357 / +0.374** | **1.12 / 1.12** | 0.51 / 0.54 | 0.40 / 0.30 |

Full adoption buys ~+0.019 ρ and pays with two numbers that move across half their grid between
folds (`len_ok` modal 20 but ranging 4–26; `dryup` modal 0.85 at 52%). **Trader published the stable
three.**

## 3. `ord_hi` 0.60 versus 0.70 is a distinction without a difference

R6 F1 reports `cindex` returning `ord_hi` 0.60 on E3 and 0.70 on the pooled 366, which reads as the
two populations disagreeing. They do not: **0 of 194 E3 cards and 1 of 366 pooled cards have an
orderliness value in (0.60, 0.70]**. The region is empty, the two settings are behaviourally
identical on every card either fit saw, and their predictions match to every digit.

This also qualifies F2's headline that `ord_hi` is the most stable threshold on the map, landing on
0.60 in 25 fits out of 25. Part of that stability is the upper tail having nothing in it to move
the boundary across. The threshold is not wrong — it is less *tested* than the count suggests.

## 4. The rubric runs cold, and always did

At the 4★ line the machine prints ≥4★ for **25.3%** of E3 where the eye grades 32.0% (pooled:
19.1% against 35.0%), a level bias of −0.24★ to −0.31★. This is **not** caused by adopting `cindex`
— the incumbent `T3` does the same thing (28.9% / 24.0%) — and it inverts round 2's problem, where
the machine was too generous by +0.74★, later +0.25★.

It is harmless under v1 as specified, because **nothing gates on the cut**: ticket 11's I3 refused a
star floor as a tunable, and ticket 18's digest excludes new 4–5★ setups. The star is a label, so
recall at the cut is descriptive. Recorded as fog on the map rather than fixed, because it would
start mattering the moment anything did gate on it.
