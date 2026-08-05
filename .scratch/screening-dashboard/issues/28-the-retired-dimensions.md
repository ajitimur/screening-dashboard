# Six dimensions were retired by an instrument that has since been shown blind

Type: prototype
Status: resolved
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

## Answer

**Nothing comes back. All six stay retired — and the reason is that the table at the top of this
ticket was denominated in a currency the rubric cannot spend.**

Run under [`PREREGISTRATION_R7.md`](../prototypes/15-grading-round-2/PREREGISTRATION_R7.md),
committed before the first fit; full write-up in
[`DIMENSIONS_FINDINGS.md`](../prototypes/15-grading-round-2/DIMENSIONS_FINDINGS.md).

**The headline is F1.** `cluster_churn` beats the incumbent `cluster_k` on partial rank correlation
by **+0.337 to +0.261** — a wider gap than the one that opened this ticket. Swapped into the ×2
tightness seat and refitted under `cindex` on all 432 cards it buys **+0.001 out-of-fold ρ**,
against a bar of +0.030. The reason is structural and it generalises: **the rubric does not consume
a dimension, it consumes a threshold on one.** A boolean cut extracts nearly the same information
from any monotone re-expression of the same quantity, and `cluster_k`, `cluster_churn` and `density`
are monotone re-expressions of each other (+0.83 to +0.92). Partial ρ scores how well a dimension
orders cards *continuously*; the rubric only ever asks it one binary question. R6 §7's flagging rule
was measuring the wrong thing, so its flags were never evidence of a missing dimension.

That half-dissolves the ticket's premise. `mae` **was** blind, exactly as ticket 21 proved — but the
screen built to correct for that blindness cannot cash its own findings, so **both instruments were
wrong in different directions and they cancel**: the dimensions `mae` retired are the dimensions a
working objective also declines.

**The six were never six.** Established from the candidates' mutual correlation alone — eye-free, so
it cannot dredge an outcome — they are **two families, each shadowing an incumbent**: a *packing*
family around `cluster_k` (`cluster_churn` +0.829, `density` +0.916) and a *shape* family around
`orderliness` (`narrowing_ratio` +0.921, `base_height_adr` −0.952, `ma_dist_adr` +0.831,
`sqrt_shortfall` −0.511), every member of which also runs |ρ| 0.27–0.82 with `base_len`. So nothing
here was ever an addition; the live question was only ever a **swap**, and both swaps lost. Control
for the incumbents as well as base length and **two candidates reverse sign**: `base_height_adr`
goes −0.235 → **+0.119** and `narrowing_ratio` +0.183 → **−0.168**. A dimension whose sign depends on
what else is in the rubric is not a dimension the rubric is missing.

**The |ρ| fix this ticket asked for was correct, and it changed nothing.** R6 §7's one-sided rule
genuinely was a bug — `base_height_adr` at −0.290 was recorded "correctly retired" purely for its
sign, which a scored dimension does not care about. Reading |ρ| admits it and `sqrt_shortfall` with
it; both then lose on the merits, `base_height_adr` scoring **−0.031 ρ** as a swap into the
orderliness seat, i.e. actively worse. A single cut on base height cannot replace the band, which is
ticket 15's "orderliness needs a band, not a one-sided cut" arriving from the other side. **A bug fix
that vindicated the buggy conclusion.** `ma_dist_adr` never reached a fit: at **+0.136** it fails the
+0.15 floor on the enlarged pool, so D10's retirement stands for a second, independent reason.

**The bar was never the binding constraint.** Every candidate threshold is unstable across the 25
fits (`cluster_churn` 3 grid steps against R6 §4's ≤2; `base_height_adr` 3–5), and worse, **adding
either destabilises thresholds that are stable without it** — `ord_lo` 64% → 48% modal share,
`cluster_k` 88% → 60% in the addition arm. A candidate worth +0.001 ρ costs the stability of two
numbers that had it.

**Ticket 27's published three reproduce, independently and stably** (F6). On a pool 18% larger
containing 66 cards no fit had seen, `cluster_k` **5** (88% modal), `ord_lo` **0.30** (64%),
`ord_hi` **0.60** (100%) all land where ticket 27 put them. Out-of-fold ρ on the full 432 is
**+0.292** against the +0.846 ceiling — ticket 20's "about a third of what is achievable" shortfall,
unmoved by everything this ticket tried. **`ord_hi`'s 100% is still partly an empty tail**, as 27
warned: deck F takes the (0.60, 0.70] region only from **1 of 366 to 5 of 432**.

**Ride-alongs** (F7). The **4★ line reads precision 0.53 / recall 0.28** out-of-fold on 432 — up
from 27's 0.49 on E3, and matching ticket 15 R5's 0.53, the number ticket 11's screen depends on.
The rubric **still runs cold and more so at scale**, printing ≥4★ on 18.3% where the eye grades
35.2%; it stays fog, since nothing gates on the cut. And **deck F's inclusion did not distort the
fit**: the machine now grades `line_not_drawable` −0.14★ below detections against the eye's −0.12★,
closer than ticket 26's −0.03★, and ranks the marginal arm **no worse** than the accepted one
(ρ +0.336 vs +0.300) — independent support for ticket 26's silent tiebreak, since putting those
names on the list unpenalised assumes exactly that they are rankable by the same rubric.

**Deck F is wired into the pool** as ticket 27 assigned: `grades3_F.txt` materialised from
`DECK_F_RESULTS.md`, `analyse3.manifest()` extended the way it was for deck E, and the
fast-path/`score3` NaN guard asserted on all 432 cards including the IDX ones that expose it.

Nothing graduates. **This ticket closes the map's last open decision** — ticket 13 is now unblocked.

Assets: [`PREREGISTRATION_R7.md`](../prototypes/15-grading-round-2/PREREGISTRATION_R7.md) ·
[`DIMENSIONS_FINDINGS.md`](../prototypes/15-grading-round-2/DIMENSIONS_FINDINGS.md) ·
`dimensions28.py` · `ROUND7_OUTPUT.txt` · `RIDEALONGS_28.txt` · `r7_result.json`
