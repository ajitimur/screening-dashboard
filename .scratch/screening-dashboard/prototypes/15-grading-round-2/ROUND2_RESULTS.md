# Round 2 — deck A results (120 blind grades)

Deck A is graded. Decks B, C and D are not, so the two carried-in probes, the per-market question
and the test–retest ceiling are all still open. Everything below follows `PREREGISTRATION.md`
exactly; no rule was chosen after seeing a grade.

## The headline: the score now agrees with the eye, weakly but for the first time honestly

| | ticket 09 (n=27) | round 2 (n=120) |
| --- | --- | --- |
| r, score vs eye | −0.043 as written / +0.259 best variant, in-sample | **+0.189 out-of-fold** |
| mean abs error | 1.24★ | **1.04★** |
| within one star | 44% → 63% | **67%** |
| bias | +0.74★ too generous | **+0.25★** |

At n=120 significance needs |r| > 0.181, so **+0.189 clears it — barely, and out-of-fold**, which
is a different claim from ticket 09's +0.259 in-sample on 27 cards. The incumbent thresholds scored
r = +0.171, mae 1.22, bias **+0.65** — R1's prediction that the corrected rubric was too generous,
confirmed against the eye.

The fit is **not overfitted** by the pre-registered test: in-sample mae 0.97 against out-of-fold
1.04 is a 0.07★ gap, inside the 0.15★ tolerance. So the thresholds stand.

Read it plainly: the rubric went from *uncorrelated with the trader* to *weakly and significantly
correlated*, with a typical error of one star. That is progress, not calibration.

## The thresholds

| threshold | ticket 09 provisional | **round 2 fitted** | direction |
| --- | --- | --- | --- |
| contraction (tightness ×2) | 1.15 | **1.80** | much tighter — the point now goes to the top ~27% |
| orderliness, churn/L (×2) | 0.35 | **0.35** | unchanged |
| MA distance | 1.00 | **0.60** | tighter |
| dry-up | 0.85 | **0.95** | looser |
| base length `len_ok` | 20 | **10** | much tighter |
| base length `len_bad` | 40 | **40** | unchanged |

Four of six moved, and five of the six are stable across folds (`ma_dist` is the exception, ranging
0.6–2.6 — treat it as the least settled number here).

**Contraction and `len_ok` both landed on the edge of the pre-registered grid, so the grids were
re-opened as a check** — contraction to 3.0, `len_ok` down to 3, `ma_dist` to 0.2. The optimum did
not move: still 1.80 and 10. Out-of-fold it got *worse* (r +0.115 vs +0.189), because the extra
freedom let one fold run to 2.6. The pre-registered grid stands, and the edge values are genuine
interior optima, not censoring. This check is recorded because it was not pre-registered.

The direction of every move is the same one: **tighten**. §3.4's "months of sideways" anti-pattern
now costs its point at 10 bars rather than 20, and the tightness point is genuinely scarce.

## Boolean or continuous — boolean, by the pre-registered rule

| | out-of-fold r | mae | within 1★ |
| --- | --- | --- | --- |
| **boolean** | +0.189 | 1.04 | **67%** |
| continuous | +0.232 | 1.04 | 55% |

Continuous has the better correlation and an identical mae, but the rule required it to beat
boolean on mae by ≥0.10★ **and** on within-one-star. It does neither. **Boolean stands** — which is
also what ticket 11 wanted, having made the score the default sort of the only list in the app and
argued that a sort key you cannot audit is one you will not trust.

This is the round-1 pattern repeating: continuous edges the correlation, boolean wins the error
rate. It is now decided on a pre-registered rule rather than a coin-flip.

## The 4★ trade threshold — stays, but it is dominated

Out-of-fold, machine ≥N★ against eye ≥4★:

| cut | n flagged | precision | recall |
| --- | --- | --- | --- |
| ≥3.0★ | 66 | 0.33 | 0.69 |
| **≥3.5★** | 35 | **0.43** | **0.47** |
| ≥4.0★ | 19 | 0.37 | 0.22 |
| ≥4.5★ | 5 | 0.60 | 0.09 |

The rule said the cut moves only on ≥10pp better precision at no worse recall. Nothing clears that,
so **§3.5's 4★ line stands**. But the table has a result the rule does not capture: **≥3.5★
dominates ≥4.0★ on both precision and recall** (0.43 vs 0.37, 0.47 vs 0.22). The 4★ cut is not the
best available cut; it is merely not beaten by enough to move it under a rule fixed in advance.

And the precision is the number to sit with: at the 4★ line, **roughly one in three names the
machine calls tradeable is one the trader would call tradeable**. Ticket 11 made this score the
default sort of the only list in the app, so that ratio is what the top of the nightly list is worth
today.

## Still open

- **Per-market calibration** — deck A is entirely US. Untestable until deck C is graded.
- **The two carried-in probes** — D5's trigger (deck B) and D13's partial limit-lock (deck C).
- **The test–retest ceiling** — the 12 repeats live in decks B and C, so the grader's own
  repeatability, which bounds every r above, is still unmeasured. A +0.189 against an unknown
  ceiling is a weaker statement than it looks.
- **Deck D, the rejected candidates** — ticket 11's unowned obligation.
