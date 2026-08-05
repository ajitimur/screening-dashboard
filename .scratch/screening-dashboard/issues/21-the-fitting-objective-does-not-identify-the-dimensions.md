# The fitting objective does not identify the dimensions the eye is using

Type: prototype
Status: resolved
Blocked by: —

## Question

Every threshold on this map is fitted by minimising **mean absolute error** over a fixed grid. Can
that objective actually recover a dimension the eye is demonstrably using — and if not, what
replaces it?

[Ticket 20](20-confirm-the-band-and-measure-the-ceiling.md) turned this from a suspicion into a
measurement. On deck E3's 194 fresh cards the orderliness band failed its pre-registered bar
(out-of-fold r = +0.120 against +0.20) — but the failure is not the band's:

- the dimension's **partial r against the eye, controlling base length, is +0.302** — the strongest
  single-dimension number on this map, ahead of cluster k's +0.196
- **dropping** it costs 0.10 r (median +0.171 → +0.069 over 25 fold assignments) and 13pp of
  within-one-star
- A3's thresholds applied **frozen** to E3 score **+0.240** — above the bar
- yet refit on E3, **every fold** runs `ord_lo` to 0.1 and `ord_hi` to 0.6, the widest values on the
  grid and very nearly no band at all, plus `len_ok` to 4 — then scores worse out of fold than the
  band it walked away from

The exhaustive search is not broken; ticket 15 already replaced coordinate descent for reaching
mae 1.0875 where exhaustive finds 1.0292, and this search does reach the optimum of its objective.
**The objective is what is wrong.** mae is a level statistic on what `REFIT_FINDINGS.md` already
described as a flat loss surface, so a rubric can lower mae by flattening toward the mean grade
while destroying the ranking the app actually sorts on — which is exactly the degeneracy ticket 15
caught round 2's fitter in, arriving this time as instability instead of a local minimum.

This is now load-bearing. Ticket 20 measured the **test–retest ceiling at +0.808**, so the target is
reproducible and the ~+0.25 the rubric achieves is a real shortfall rather than noise. Closing that
gap is the highest-value move left on the score, and an objective that discards its best dimension
is the first thing in the way.

## What to look at

Nothing needs collecting — **314 graded cards already exist** (A3's 120 and E3's 194), and this is
computation over them, not a new sitting.

- **Rank-based objectives.** The app sorts by score ([ticket 11](11-dashboard-information-architecture.md)),
  so Spearman or a pairwise-ranking loss matches the use. mae never did.
- **The level/ranking split.** A3 and E3 differ by +0.30★ (p ≈ 0.035) and are therefore not poolable
  under mae — but a rank objective may be **invariant to exactly that offset**, which would unlock
  all 314 cards instead of 194. Worth checking early; it is the cheapest win available.
- **Regularisation toward the incumbent**, so a fold cannot buy a trivial mae gain by running a
  threshold to the edge of its grid.
- **Stability as a reported statistic.** Ticket 20 had to discover the fold spread by hand. Whatever
  objective wins should report threshold spread across folds as a first-class number, since a
  threshold that moves 0.1 → 0.6 between folds is not a threshold.
- **Re-test the retired dimensions.** If mae cannot identify orderliness, its verdicts on the ones
  already dropped are suspect — D10's MA distance (partial r +0.010) and every narrowness candidate
  ticket 17 R4 collapsed. Cheap to re-run, and this is the ticket that should say whether they were
  correctly retired or merely invisible to a bad objective.

**Whatever wins is re-fitted, not re-graded**, and the pre-registration discipline holds: fix the
objective and the decision rule before looking at what it does to the thresholds. Ticket 20's
outcome is the argument for that — the one rule chosen after seeing grades is the one that
generated this ticket.

**Coupled to [ticket 19](19-fit-the-split-parameters.md), and the order matters.** `TIGHT_MULT`
sets the cluster's range ceiling and therefore the distribution of k, the ×2 tightness signal.
Refitting the rubric under a new objective on top of 22 unfitted borrowed detector defaults repeats
round 3's mistake one level down.

## Answer

**mae cannot recover the dimension the eye is using, and the proof is that a rank objective walks
straight back to the band the trader adopted.** On the same 194 E3 cards, the same exhaustive search
over the same grid, changing only the loss: `mae` lands at `ord_lo` 0.10 / `len_ok` 4 — the grid's
corner, a band so wide it is nearly no band — while **both** rank objectives return `ord_lo` 0.30,
`ord_hi` 0.60, `cluster_k` 5, which is the incumbent `T3` (0.275 / 0.60 / 5) to within one grid step,
recovered from data that had never been fitted that way. On the pooled 366 cards `cindex` says it
again. Ticket 20's "every fold runs `ord_lo` to 0.1" was never fold-luck and never the dimension's
fault: **under `mae` not one of the five thresholds is stable across 25 fits; under either rank
objective `cluster_k`, `ord_lo` and `ord_hi` all are, and `ord_hi` lands on 0.60 in 25 fits out of
25.** `len_ok` and `dryup` stay unstable under every objective — those two are simply unfitted at
this n, and no loss function rescues them.

**And the rank objective is still not adopted, by 0.01★.** `cindex` beats `mae` by **+0.111 median
out-of-fold ρ** (+0.326 vs +0.215) and halves the fold-to-fold spread, but costs **+0.16★ of mean
absolute error against R6 §2's pre-registered 0.15★ tolerance**. The rule is not being relaxed after
the fact — this ticket exists because a rule was once chosen after seeing grades. What a guardrail
missed by one hundredth of a star means is that **the choice was never between two objectives**:
`mae` fits the *level* (how many stars to print), `cindex` fits the *order* (the only list the app
has, ticket 11), and on this data they genuinely disagree. The obvious two-stage remedy was measured
**post hoc and labelled as such** and does not get both — an isotonic level map restores mae to 0.93
but collapses the score's spread (SD 1.24 → 0.44), and the ties that creates cost ρ 0.326 → 0.233.
It is still the best pair on the table (beating the incumbent on both axes), but it buys level with
resolution. **So this ticket ends on a trader question, not a computation:** does a 4★ have to
*mean* 4★, or is the number a label for a rank? That is [ticket 27](27-level-or-order.md), and every
threshold on this map waits behind it.

**Ticket 20's drop of orderliness must not proceed.** Keep versus drop on E3, ×2 redistributed:
**ρ +0.231 against +0.088** — dropping the band costs **+0.143 ρ, 62% of the rubric's out-of-fold
ranking power**, and makes the level worse too. R3 §6's instruction to drop it on a failed +0.20 bar
is comprehensively wrong. By R6 §6 the band is **real but unfittable** — it clears the keep/drop bar
four times over and its thresholds are unstable *under `mae` only*. Orderliness stays in the rubric;
whether it gets a fitted threshold depends on ticket 27. For scale, its Spearman partial ρ against
the eye controlling base length is **+0.365, the strongest dimension on this map**, ahead of
`cluster_k`'s +0.233.

**No thresholds are published from this round.** Under the objective that survives (`mae`, with
λ = 0.001 shrinkage adopted on a +0.016 ρ gain), the pooled fit is `cluster_k` 7 · `ord_lo` 0.10 ·
`ord_hi` 0.70 · `len_ok` 26 — the degenerate corner again, on 366 cards instead of 194, every
threshold unstable. **The objective that passes the guardrail produces no usable thresholds; the
objective that produces stable thresholds is blocked by the guardrail.** The incumbent `T3` stands,
unmoved and un-refitted — and F1 is now independent evidence for it.

**Half the retired dimensions were retired by a blind instrument.** Re-measured as Spearman partial
ρ on rank residuals, sign required to agree on A3 and E3 separately: `cluster_churn` **+0.313**,
`density` **+0.286**, `narrowing_ratio` **+0.211**, `ma_dist_adr` **+0.183** — all flagged, and
`ma_dist_adr` is the sharpest case, killed by `REFIT_FINDINGS.md` F2 at Pearson partial r +0.010,
p = 0.93. **R6 §7's own rule was mis-written**: one-sided, so `base_height_adr` at **−0.290** (a
stronger relationship than `cluster_k`'s, consistent on both decks — the eye reliably dislikes tall
bases) is recorded as "correctly retired" when a scored dimension does not care about the sign of
its correlation. That defect is reported rather than quietly patched, and the rule is fixed in the
next pre-registration. Six candidates, adopted by nobody here, go to
[ticket 28](28-the-retired-dimensions.md).

**Two things fell out along the way.** *Poolability:* on a rank criterion A3 + E3 + C3 pool (ρ on E3
+0.217 vs +0.215 E3-only), so **all 366 graded cards are usable together** — the +0.30★ level offset
`REFIT_FINDINGS.md` F3 called disqualifying is invisible to a rank criterion, and ticket 22's
US/IDX pooling survives a rank test as well as the level test it was made on. It buys nothing until
ticket 27, because every pooled fit under `mae` is degenerate. *A defect in the machinery:*
`rubric3._vector_predictor` (what `rubric3.fit` optimises) and `score3` (what produced every
published prediction) disagree on any card with a missing `prior_move` or `sector_share` — **every
IDX card** — because `score3` scores a NaN as zero and still counts its weight. Nothing published is
affected, since every fit to date ran on deck A's US core, but the first fit to pool IDX would have
optimised one rubric and reported another. Noted in `rubric3.py`; `objective6.Fast` matches `score3`
and asserts it on every population before any number is computed.

*One number worth carrying:* under 5 fold assignments `mae` scores median ρ +0.215 / Pearson r
+0.197 on E3, where ticket 20's single assignment reported **+0.120** — a draw from a distribution
running +0.130 to +0.284. No future decision on this map should rest on one fold split.

Assets: [`PREREGISTRATION_R6.md`](../prototypes/15-grading-round-2/PREREGISTRATION_R6.md) ·
[`OBJECTIVE_FINDINGS.md`](../prototypes/15-grading-round-2/OBJECTIVE_FINDINGS.md) ·
`objective6.py` · `posthoc_calibration.py` · `ROUND6_OUTPUT.txt` · `R6_THRESHOLDS.txt` ·
`POSTHOC_CALIBRATION.txt`
