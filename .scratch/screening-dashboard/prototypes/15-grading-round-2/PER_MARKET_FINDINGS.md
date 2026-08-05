# Per-market calibration: one threshold set covers both markets

Deck C3, graded. 58 cards — 40 clean IDX, 12 partially limit-locked IDX, 6 US repeats. **The first
graded IDX cards that have ever existed on this map**, across ticket 09, round 2 and ticket 17.

Reproduce with:

    python analyse3.py A=<grades3_A.txt> E=<grades3_E.txt> C=<grades3_C.txt>   # section 5 = arm 1
    python per_market.py A=<grades3_A.txt> C=<grades3_C.txt>                    # arm 2

Raw output is in `ROUND5_ANALYSE_OUTPUT.txt` and `ROUND5_PERMARKET_OUTPUT.txt`.

## The decision

`PREREGISTRATION_R3.md` §4 gives IDX its own thresholds if **either** arm fires. Both miss.

| arm | statistic | bar | measured | fires? |
| --- | --- | --- | --- | --- |
| 1 | pooled fit's mean residual, IDX vs US | > 0.50★ | **0.33★** (US +0.04, IDX −0.29) | no |
| 2 | IDX-only fit beats pooled on IDX cards, out-of-fold | > 0.15★ | **+0.125★** | no |

**One threshold set covers both markets.** No IDX split, no second rubric, no per-market grids.

### Arm 2 is not as close as +0.125 makes it look

The ticket said that a marginal result was a reason to wait for the fitting-objective ticket rather
than to split. +0.125 against a 0.15 bar reads marginal, so it was measured rather than eyeballed:
over **25 fold assignments the gain runs −0.077 to +0.231, median +0.058, and clears the bar on
12% of them**. The headline draw sits in the upper tail of its own distribution, and on the median
draw the IDX-only fit wins less than half the bar.

The IDX-only thresholds say the same thing more bluntly. Across five folds `cluster_k` runs 3–6,
`ord_hi` 0.35–0.6 and `len_ok` 4–26 on 52 cards — this is the instability the fitting-objective
ticket names, arriving here as a fit that cannot hold a threshold still long enough to be worth
publishing. **There is nothing to split the thresholds into.**

## The eye is much harsher on IDX, and the rubric already knows

|  | US (deck A core, n=120) | IDX (deck C, n=52) |
| --- | --- | --- |
| mean eye | 3.23 | **2.35** |
| eye ≥ 4★ | 48% | **15%** |

That is a **0.88★ level difference between markets** — nearly three times arm 1's whole 0.33★
residual gap. The two numbers together are the finding: the level difference is in the
**population**, not in the **calibration**. IDX detections grade worse because they *are* worse
setups by the trader's eye, and the pooled rubric tracks that drop without being told about it.
A per-market threshold set would be fitting a difference the score already reproduces.

**The rubric also performs better on IDX than on the market it was fitted on** — pooled, out of
fold, on IDX cards: mae 0.913, r +0.298, within-one-star 69%, bias +0.01, against US's mae 1.11,
r +0.255, within-one-star 60%. On 52 cards that is not a claim that IDX is easier, but it is a
clean refutation of the worry the ticket was written for: the score does not degrade off its home
market.

## The ceiling is tighter

Deck C's 6 US repeats join ticket 20's 12 pairs: **18 pairs, test–retest r = +0.854** (was +0.808
on 12), mean absolute difference **0.44★** (was 0.58★). Every correlation on this map is read
against this number, and it moved **up** — so the ~+0.25 the rubric achieves remains a real
shortfall rather than a noise ceiling. Deck D's 6 repeats would take it to 24.

## The limit-lock probe inverts ticket 09's suspicion

Descriptive only, and it stays that way — 98.1% of accepted IDX detections have zero collapsed
bars, so this is a 12-card subgroup, not a powered arm.

Ticket 09 suspected IDX limit days **flatter** both ×2 dimensions at once, so limit-locked bases
would grade *high*. They grade **low**: mean eye **1.75** on the 12 locked cards against **2.53**
on the 40 clean ones. Whatever the collapsed bars do to contraction and orderliness arithmetically,
the trader's eye marks those bases down rather than up. Read as colour. It is not a threshold, and
on n=12 it is not evidence for one either.

## Limits

- **52 IDX cards**, one sitting. The pre-registration set no power target for the per-market rule,
  so both arms are point estimates — which is exactly why arm 2's fold spread is reported above.
- Both arms are computed under the **mae objective**. A rank-based objective would be invariant to
  the 0.88★ level offset that separates the markets, so it would make pooling *more* justified, not
  less — this decision does not need to wait on the fitting-objective ticket. That is an argument
  from the objective's form, not a measurement.
- Deck C is IDX **detections**. Whether the detector rejects the wrong IDX names is deck D's
  question, not this one.
