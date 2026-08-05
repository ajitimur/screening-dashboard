# Pre-registration R7 — the retired dimensions

For [ticket 28](../../issues/28-the-retired-dimensions.md). Written and committed **before any fit
was run**, on a map where a threshold once moved because a tolerance was relaxed after the fact.
[Ticket 21](../../issues/21-the-fitting-objective-does-not-identify-the-dimensions.md) exists
because of that, and it refused a +0.111 ρ gain rather than reopen a 0.15★ rule it had missed by
0.01★. Nothing below may be edited after `dimensions28.py` runs.

Ticket 28's question: six dimensions were retired by `mae`, an instrument ticket 21 then showed
cannot identify a dimension the eye is demonstrably using. Which of them come back?

---

## §1. The pool — 432 cards, fixed by ticket 27

| population | n | rule |
| --- | --- | --- |
| A3 | 120 | deck A, `split_ok` |
| E3 | 194 | deck E, `split_ok`, tag `confirm` |
| C3 | 52 | deck C, `split_ok`, IDX, non-repeat |
| F3 | 66 | deck F, tags `detection` + `line_not_drawable`, `tight & caught_up` |
| **total** | **432** | |

Deck F's 33 `not_caught_up` cards are **excluded** — still gated out, so the rubric would learn to
rank names the app never shows. Its 6 repeats are excluded as deck A duplicates.

F3's `line_not_drawable` arm carries `line_ok = False`, so it fails `split_ok`. It is admitted
anyway, and the membership rule for deck F is `tight & caught_up` rather than `split_ok`, because
[tickets 25](../../issues/25-the-line-not-drawable-path.md) and
[26](../../issues/26-the-line-penalty-and-the-longer-list.md) demoted `line_ok` from a gate to a
silent sort tiebreak. Those names appear on the nightly list, so the rubric that sorts the list must
be fitted on them. This is the first fit on this map to include them.

Loading deck F is work ticket 27 assigned here: `grades3_F.txt` is materialised from
`DECK_F_RESULTS.md`, and `analyse3.manifest()` gains `deckF_manifest.csv` the same way it gained
deck E.

## §2. The screen — the |ρ| fix, and a control the old screen did not have

R6 §7 flagged at **ρ ≥ +0.15**, one-sided, so `base_height_adr` at −0.290 was recorded as
"correctly retired" for having the wrong sign. A scored dimension does not care about the sign of
its correlation; the sign only sets which way the point is awarded. **The screen reads |ρ|.**

**Stage 1 — the corrected R6 screen.** Partial Spearman of the candidate against the eye,
controlling `base_len`, on the 432 pool. A candidate passes with **|ρ| ≥ 0.15** and **sign agreement
across all four decks** (A3, E3, C3, F3).

**Stage 2 — families.** Stage 1 controls base length alone, which is not enough to tell a new
dimension from one the rubric already has. Candidates are therefore grouped into families by their
**mutual Spearman correlation**, computed on the 432 pool **without reference to the eye** — so this
grouping is not a choice about outcomes and cannot be a way of dredging one. The grouping is fixed
here, from the matrix already computed:

| family | members | shadows |
| --- | --- | --- |
| **packing** | `cluster_k` (incumbent), `cluster_churn` (+0.829 with it), `density` (+0.916) | the ×2 tightness seat |
| **shape** | `orderliness` (incumbent), `narrowing_ratio` (+0.921 with it), `base_height_adr` (−0.952), `ma_dist_adr` (+0.831), `sqrt_shortfall` (−0.511) | the ×2 orderliness seat, and `base_len` (|ρ| 0.27–0.82 across the family) |

A candidate in a family containing an incumbent is a **swap** for that incumbent's seat, never an
addition. A candidate in neither family would be an **addition**; on the current matrix there are
none, and if the screen produces one it enters at ×1 per §4.

**Stage 3 — one seat per family.** At most one candidate per family is carried to a fit: the one
with the highest |ρ| at stage 1. Two members of one family are the same object measured twice, and
adopting both would double-count it. Recorded here rather than decided later.

**Reported, not decisive:** partial ρ controlling `base_len` *and* both incumbents, for every
candidate. It is diagnostic — it says how much of a candidate is new — and no adoption turns on it,
because a rank-partial on a discrete rubric's inputs is not the same object as the fit.

## §3. The bars — trader's call, taken before the fit

Primary criterion: **median out-of-fold Spearman ρ**, deck-weighted, over **5 fold assignments ×
5 folds** (seeds 11–15), exactly the protocol `objective6.cv` already runs. The objective is
**`cindex`**, adopted by ticket 27.

| change | must buy | why this bar |
| --- | --- | --- |
| **swap** | **+0.030 ρ** | R6 §2's existing margin. A swap replaces one threshold with another in the same seat: §3.5's `÷2` denominator does not move, so every printed star keeps its meaning. |
| **addition** | **+0.050 ρ** | Higher, because an addition renormalises the score over a larger maximum and **changes what every printed star means**. Ticket 15 saw one completed ×1 dimension reverse the ordering of the top two star bands. |

**Both must also be stable**, on R6 §4's existing definition: the new threshold's modal value takes
**≥ 60% of the 25 fits** and spans **≤ 2 grid steps**. An unstable threshold is what ticket 20
published by accident and ticket 21 diagnosed; a gain carried by a number that moves across half its
grid between folds is not adopted here.

Failing either test, **the incumbent stands**. Ties break toward the incumbent.

## §4. Weights — trader's call

A dimension adopted as an **addition** enters at **×1**. §3.5's ×2 weights are the method's own and
were never fitted; inventing a new ×2 is a larger claim than a rank-correlation gain can support,
and it doubles the effect on the renormalised denominator. A **swap** inherits the ×2 seat it
replaces, unchanged. The ×2 seats remain exactly two: tightness and orderliness.

## §5. The fit

Baseline and challenger are fitted **identically, per fold**, so the comparison is of dimensions and
not of protocols:

- **Baseline**: the incumbent rubric. `cluster_k`, `ord_lo`, `ord_hi` refit on each training fold
  under `cindex` over `rubric3.GRIDS`; **`len_ok` = 14 and `dryup` = 0.95 held frozen** at `T3`,
  per ticket 27 — R6 §4 found both unfitted at this n and no loss function rescues them.
- **Swap arm**: the candidate replaces its incumbent in the ×2 seat. Candidate threshold, plus the
  surviving incumbent's thresholds, refit per fold. Same frozen pair.
- **Addition arm**: incumbents unchanged in their seats, candidate added at ×1 with its threshold
  refit per fold. Same frozen pair.

**Candidate grids** are the **9 deciles (10%–90%) of the candidate's own distribution over the 432
pool**, computed without reference to the eye. **Direction is fixed by the sign of its stage-1
partial ρ, recorded in §7 below before fitting** — positive means the point is awarded above the
threshold, negative below. A missing value scores **0.5**, the rubric's existing neutral convention
for an unmeasurable dimension (ticket 09: unmeasurable dimensions score neutral, not zero, because
zero penalised the tight short bases hardest).

## §6. The machinery guard

`objective6.Fast` is asserted equal to `rubric3.score3` on every population before any number is
computed, and the extension in `dimensions28.py` must pass the same assertion in every arm. Ticket
27 flagged this specifically: the pool now contains IDX cards, which are exactly the cards that
expose the `rubric3.fit` fast-path / `score3` NaN disagreement (`OBJECTIVE_FINDINGS` F0). A fit that
optimised one rubric and reported another is the failure mode being guarded against.

## §7. The candidates, and their directions — fixed before fitting

Stage-1 partial ρ on the 432 pool, controlling `base_len`. **These numbers are the screen's input,
computed before the bars in §3 were chosen and before any fit was run.**

| candidate | ρ (432) | direction | family | stage 1 |
| --- | --- | --- | --- | --- |
| `cluster_churn` | **+0.337** | higher is better | packing | **passes** |
| `density` | **+0.291** | higher is better | packing | **passes** |
| `base_height_adr` | **−0.235** | lower is better | shape | **passes** (|ρ|, the fix) |
| `narrowing_ratio` | **+0.183** | higher is better | shape | **passes** |
| `sqrt_shortfall` | **−0.182** | lower is better | shape | **passes** |
| `ma_dist_adr` | +0.136 | — | shape | **fails the floor** |
| `narrow_cluster` | −0.090 | — | packing | fails floor and sign agreement |
| `dryup` | −0.082 | — | — | fails floor and sign agreement |

Incumbents, for scale: `orderliness` **+0.297**, `cluster_k` **+0.261**.

By §2 stage 3 the fitted candidates are therefore **`cluster_churn`** (packing, swap for
`cluster_k`) and **`base_height_adr`** (shape, swap for `orderliness`). The remaining three are
screened out as same-family runners-up and reported with their numbers.

`ma_dist_adr` fails on the enlarged pool having passed at +0.183 on R6's A3+E3. That is the ticket's
own rule applied to the pool ticket 27 mandated, not a new rule — and ticket 28 already named it
"simultaneously the cleanest indictment of the old instrument and the weakest candidate", at +0.606
with a gate every surviving detection passes.

## §8. Adoption authority — trader's call

A swap that clears §3's bar **is adopted in this ticket**, and the thresholds are republished. The
bar is the decision; that is what pre-registering it is for.

## §9. Out of scope

Collecting new grades. Changing the detector — ticket 19 froze its 22 parameters. Revisiting
`len_ok` and `dryup`, which ticket 27 held frozen. Re-deciding the objective, which ticket 27
adopted. Re-litigating ticket 24 (the score stays stop-blind) or ticket 22 (one threshold set covers
both markets).

## §10. What this ticket reports if nothing clears

That is a live outcome, not a failure. The map has spent tickets 09, 15, 17, 20 and 21 discovering
that the two ×2 dimensions are hard to measure; a pre-registered null on five candidates, on the
largest pool ever assembled here and under the objective that finally works, is the strongest
statement this map can make that the incumbent rubric is the right shape. It would also close
ticket 21's last loose end.
