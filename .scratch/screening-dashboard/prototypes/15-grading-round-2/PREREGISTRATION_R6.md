# Round 6 pre-registration — the fitting objective

Ticket 21. Written **before** any objective other than `mae` has been run against the grades, and
before any threshold produced by one has been looked at. Ticket 20 is the argument for this
discipline: the one rule on this map chosen after seeing grades is the rule that produced this
ticket.

Nothing is collected. All 430 graded cards already exist (A3 120 · C3 58 · D3 46 · E3 206, of which
the populations below are the split-accepted subsets). This is computation over them.

---

## §0. What is being tested

Every threshold on this map was fitted by minimising **mean absolute error** over a fixed grid.
`mae` is a *level* statistic. The app sorts by score (ticket 11), so the quantity that matters is an
*order*. On a flat loss surface a rubric can lower `mae` by flattening toward the mean grade while
destroying the ranking — which is what ticket 15 caught round 2's fitter doing, and what ticket 20
saw again as instability: every fold ran `ord_lo` to 0.1 and `ord_hi` to 0.6, walking away from the
dimension with the strongest partial correlation on the map (+0.302), then scoring worse out of fold
than the band it abandoned.

**The hypothesis under test:** the instability is a property of the *objective*, not of the
dimension or of the data. If it is, a rank-based objective recovers a stable band. If it is not, the
flatness is in the grades and the remedy is something else — and that answer is equally publishable.

## §1. The objectives compared

Three, all searched **exhaustively** over the identical `rubric3.GRIDS` in boolean mode, with ties
broken toward the incumbent `T3` exactly as `rubric3.fit` already does:

| id | loss (minimised) | rationale |
| --- | --- | --- |
| `mae` | mean absolute error in stars | the incumbent. Reported for comparison, not defended. |
| `spearman` | `1 − ρ(pred, eye)` | matches the use: the app sorts. Ties handled by average ranks. |
| `cindex` | `1 − c` where `c` is pairwise concordance | as above, but **restricted to pairs the eye can actually tell apart**. |

`cindex` is the one that carries an assumption, so it is stated here: pairs are counted only when
the two cards differ by **≥ 1 star**. Ticket 23 measured the eye's own mean absolute test–retest
difference at **0.56★** (18 pairs, r = +0.854), so a pair separated by less than a star is inside
the grader's noise and asking the rubric to order it correctly is asking it to fit noise. Concordant
pairs score 1, discordant 0, ties 0.5.

## §2. The primary criterion, fixed in advance

**Median out-of-fold Spearman ρ**, over **5 folds × 5 fold assignments (25 fits)**, ranks computed
**within deck**.

Three things about this criterion are deliberate and are not to be revisited after the numbers land:

- **Out-of-fold**, because ticket 20's failure was invisible in sample.
- **Median over 25 assignments**, because ticket 20 had to discover fold-luck by hand; a single
  5-fold split is one draw and this map has already been misled by one.
- **Within deck**, because A3 and E3 differ by +0.30★ (p ≈ 0.035) in *level*. A rank criterion
  computed within deck is invariant to that offset, which is the property §3 tests.

Two guardrails, both of which can veto a winner:

1. **Level guardrail.** The winner's out-of-fold `mae` may not exceed the incumbent's by more than
   **0.15★**. The score is displayed as 1–5 stars, not only as an order, so an objective that
   ranks well while drifting a star off the eye is not adopted.
2. **Margin.** A challenger replaces `mae` only if it beats it by **≥ 0.030 median ρ**. Below that
   the incumbent stands. This is a conservative rule and it is meant to be: the cost of churning
   the objective is that every number on this map is re-derived.

Ties between `spearman` and `cindex` break toward `cindex`, on the §1 noise-floor argument.

## §3. Poolability — the cheapest win available, tested honestly

`mae` cannot pool A3 with E3: the decks differ by +0.30★ in level and `mae` is a level statistic.
A rank objective should be invariant to exactly that offset. So:

- Fit on **A3 + E3 pooled** (and, separately, **+ C3**) under the winning objective.
- Evaluate out-of-fold ρ **on E3 cards only**, ranks within deck, same 25 assignments.
- **Rule:** pooling is adopted if the pooled fit scores **≥ (E3-only fit − 0.020)** on E3. Equal or
  near-equal accuracy on more data is a win, because it is what makes the thresholds stable.

C3 is tested as a separate step rather than folded in silently, because ticket 22 settled that one
threshold set covers both markets on a *level* argument (residual 0.33★ against a 0.50★ bar) and it
is worth knowing whether the rank objective agrees.

## §4. Stability is a reported number, not a footnote

Ticket 20's real finding was that `ord_lo` moved 0.1 → 0.6 across folds, which means it is not a
threshold. From here every fitted threshold is published with:

- its **modal value** across the 25 fits and the **share of fits landing on it**;
- its **min–max spread in grid steps**.

**A threshold is called stable** when the modal share is **≥ 60%** and the spread is **≤ 2 grid
steps**. An unstable threshold is reported as unstable and its dimension is not credited on the
strength of its fitted value, whatever the primary criterion says.

## §5. Regularisation toward the incumbent

Tested, not assumed: loss + `λ × (grid steps moved from T3, summed over thresholds)`, at
**λ ∈ {0, 0.001, 0.003, 0.010}** in units of the primary loss.

**Rule:** a non-zero λ is adopted only if it improves median out-of-fold ρ by **≥ 0.010** over
λ = 0 under the winning objective. Otherwise λ = 0 and the finding is that the shrinkage was not
needed. λ is chosen on the primary criterion only — never on the stability numbers, which would be
circular, since shrinkage buys stability by construction.

## §6. The orderliness verdict, re-run

Ticket 20 dropped orderliness by R3 §6 when it scored out-of-fold r +0.120 against a +0.20 bar. That
decision was made **under `mae`**. It is re-run here under the winning objective, on E3, keep vs
drop, same 25 assignments.

**Rule — orderliness is restored** to the rubric only if **both** hold:

1. keeping the band beats dropping it by **≥ 0.030 median ρ** on E3; **and**
2. both `ord_lo` and `ord_hi` are **stable** by §4.

If (1) holds and (2) does not, the dimension is credited as **real but unfittable** — it carries
signal the rubric cannot spend, and it goes to the trader as a question about form, not a threshold.
If (1) fails, the objective was not the culprit and ticket 20's drop stands. All three outcomes are
publishable; none is a failure of the round.

## §7. Re-test of the retired dimensions

If `mae` cannot identify orderliness, its verdicts on the dimensions already dropped are suspect.
Re-measured under the winning objective's own statistic — **Spearman partial ρ against the eye,
controlling base length by rank residuals** — on the pooled population:

`ma_dist_adr` (D10, retired at partial r +0.010) · `narrow_cluster` · `narrowing_ratio` ·
`sqrt_shortfall` · `base_height_adr` · `cluster_churn` · density (`cluster_k ÷ cluster_range_adr`).

**Rule:** a retired dimension is **flagged for reinstatement** only if its partial ρ is **≥ +0.15**
(the floor this map already pre-registered for k, R3 §1) **and** its sign agrees on A3 and E3
separately. A flagged dimension is **not** added to the rubric in this round — it goes to a new
ticket, because adding a dimension is a fitting decision and this round is about the fitter.
Everything unflagged is recorded as **correctly retired**, which is the answer the ticket asks for.

## §8. What is not in scope

- **No re-grading.** Whatever wins is re-fitted, not re-graded.
- **No detector changes.** Ticket 19 froze the 22 split parameters; refitting the rubric on top of a
  moving detector is the mistake this ticket exists to avoid repeating one level down.
- **No new dimensions.** §7 can flag; it cannot adopt.
- **The eye-versus-outcomes question stays shut.** This round fits the eye. Whether the eye is right
  is the map's standing open question and needs forward history, not a better objective.
