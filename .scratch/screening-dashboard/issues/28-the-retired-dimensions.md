# Six dimensions were retired by an instrument that has since been shown blind

Type: prototype
Status: claimed
Blocked by: 27

## Question

[Ticket 21](21-the-fitting-objective-does-not-identify-the-dimensions.md) showed that `mae` cannot
identify a dimension the eye is demonstrably using. Its verdicts on the dimensions already dropped
are therefore suspect, and re-measuring them on rank residuals says so:

| dimension | pooled partial ρ | A3 | E3 | how it was retired |
| --- | --- | --- | --- | --- |
| `cluster_churn` | **+0.313** | +0.236 | +0.334 | folded into k as "one dimension, not two" |
| `density` (k ÷ cluster range) | **+0.286** | +0.228 | +0.298 | R4, below k |
| `narrowing_ratio` | **+0.211** | +0.201 | +0.190 | R4, "collapses under length control" |
| `ma_dist_adr` (D10) | **+0.183** | +0.144 | +0.198 | Pearson partial **r +0.010, p = 0.93** |
| `base_height_adr` | **−0.290** | −0.270 | −0.272 | R4, "no signal" |
| `sqrt_shortfall` | **−0.211** | −0.156 | −0.250 | R4, "no signal" |

Context: `cluster_k`, the incumbent ×2 tightness dimension, is **+0.233**. Four of these six beat it.

Two distinct problems are mixed in that table and the ticket has to separate them.

**1. The ones flagged by R6 §7's rule** — `cluster_churn`, `density`, `narrowing_ratio`,
`ma_dist_adr`. `ma_dist_adr` is the cleanest indictment of the old instrument (+0.010 Pearson vs
+0.183 Spearman partial) and simultaneously the weakest candidate, because it correlates +0.606 with
a gate every surviving detection already passes. `cluster_churn` is the strongest but is **the same
object as k** (r = 0.850 with it, `REFIT_FINDINGS.md` F1) — so the live question there is not
"add it" but **"is churn the better representation of the dimension the rubric already has?"**, and
that is a swap, not an addition.

**2. The ones the rule got wrong.** R6 §7 flagged only at ρ ≥ +0.15, so `base_height_adr` at −0.290
— stronger than `cluster_k`, sign agreeing on both decks, and meaning something perfectly sensible
(*the eye dislikes tall bases*) — was recorded as "correctly retired". A scored dimension does not
care about the sign of its correlation; the sign only sets which way the point is awarded. **Fix the
rule to read |ρ| in this round's pre-registration** and re-screen everything, including candidates
already dismissed on one-sided grounds.

**Why it was blocked on [ticket 27](27-level-or-order.md) — now resolved, so this is takeable.**
Adding or swapping a dimension is a fitting decision, and ticket 21 established there is no usable
fitter until the level-versus-order question is settled: under `mae` every threshold on 366 cards is
degenerate and unstable, so a fit that "adds churn" would be measuring nothing. This is a re-fit over
grades that already exist — **no grading sitting is required**.

**What ticket 27 hands down:**

- **The objective is `cindex`.** The mae guardrail fell, because nothing in v1 reads the star as a
  magnitude. Fit on order.
- **The baseline is the published three** — `cluster_k` 5, `ord_lo` 0.30, `ord_hi` 0.60 — with
  `len_ok` 14 and `dryup` 0.95 held at `T3`, both **deliberately unfitted** at this n. A candidate
  dimension is judged against that set, not against the full `cindex` five.
- **The pool is 432 cards**: ticket 21's 366 (A3 + E3 + C3) plus deck F's 33 detections and 33
  `line_not_drawable`, excluding its 33 `not_caught_up` (still gated out, so the rubric would learn
  to rank names the app never shows) and its 6 A3 repeats. **Loading deck F's grades is work this
  ticket owns** — `objective6.load_cards` reads `grades3_{A,C,D,E}.txt`, and deck F's grades live in
  `DECK_F_RESULTS.md` / `analyse_deckF.py`.
- **Keep `rubric3`'s fast-path/`score3` NaN fix live.** The pool now contains IDX cards, which are
  exactly what expose the disagreement, and `objective6.Fast` asserts the match before computing.
- **`ord_hi`'s stability is partly an artefact**: 0 of 194 E3 and 1 of 366 pooled cards lie in
  (0.60, 0.70], so its 25-of-25 modal share reflects an empty upper tail. Do not read it as the
  best-tested threshold on the map.
- §3.5's `÷ 2` mapping is fixed, so **adding a dimension changes what every printed star means** —
  the points total is renormalised over a larger maximum. Ticket 15's warning that one completed ×1
  dimension once reversed the top two bands applies with full force, and ticket 27 measured the
  rubric already running cold at the 4★ line (25.3% against the eye's 32.0%).

**Pre-register before fitting**, in the deck3 style: how much out-of-fold ρ an added dimension must
buy to earn its place (ticket 15's history is that added dimensions reorder the top bands), whether
a swap is judged on the same bar as an addition, and what happens to the ×2 weights if two
correlated candidates both clear it. Ticket 15's warning stands: **completing a single ×1 dimension
once reversed the ordering of the top two star bands**, so nothing here is cosmetic.

**Out of scope:** collecting new grades, and changing the detector (ticket 19 froze its 22
parameters).
