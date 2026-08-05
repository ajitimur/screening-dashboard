# The fitting objective does not identify the dimensions the eye is using

Type: prototype
Status: open
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
