# Round 3 — pre-registration

**Written before a single round-3 card was rendered**, and after the round-2 grades had been
analysed on the new structure. Same discipline as `PREREGISTRATION.md`: what round 3 produces is
the *numbers*, not the rules.

Round 2's deck A stands as a method and is retired as a fitting set. Ticket 17 replaced D3/D4, so
four of the six thresholds deck A fitted describe a window that no longer exists, and — measured in
`split_refit.py` — the grades that exist cannot fit replacements:

- Only **81 of 172** graded cards are setups the split would actually surface.
- The two graded sets **are not poolable**. Deck A was stratified on the *old* provisional score
  (24 cards per band, deliberately range-stretched); ticket 17's deck was not. On the same
  population — names both detectors fire on — they differ by **+0.69★, p = 0.044**. Mean absolute
  error is a level statistic, so that offset lands directly on every fitted threshold.
- Fitting on the 81 anyway gives out-of-fold **r = +0.007** against an in-sample +0.179, and the
  two sources disagree on **four of five** thresholds. That is not a fit.

So round 3 re-collects on the split's own population. Everything below is fixed in advance.

---

## 1. What changed in the rubric, and what is therefore being fitted

Structure is `rubric3.py`. Ticket 09's S1–S5 still stand and are not re-litigated. Three changes,
all forced by ticket 17 and all measured in `split_tightness.py` / `split_diag.py` before this
document was written:

| dimension | round 2 | round 3 | why |
| --- | --- | --- | --- |
| tightness ×2 | contraction over D3's retained set | **cluster length k** | the retained set is gone; every *narrowness* candidate collapses under a base-length control, k does not |
| orderliness ×2 | churn / L over `min(L,20)` | churn / L over the **split's base** | same form, new domain (median 14 bars, not 3) |
| base length ×1 | penalty vs 08's longest window | penalty vs the **split's base** | same |
| MA support ×1 | `|ma_dist| ≤ T` **and** SMA20 rising | **SMA20 rising only** | the distance half carries nothing once length is controlled (partial r **+0.010**, p = 0.93) and the split's catch-up test already gates 100% of survivors |
| volume ×1 | dry-up | dry-up over the **split's base** | same |

**Free numbers fall from six to four**: `cluster_k`, `orderliness`, `dryup`, and the length band
(`len_ok`, `len_bad`). `ma_dist` is retired as a threshold, not refitted.

Still not free, because another ticket fixed them: `adr ≥ 0.05` (§3.5), `sector_share ≥ 0.10`
(ticket 07), `prior_move ≥ 0.90` (the decile gate).

### Why tightness is a packing count and not a width

The cluster is *selected* as the largest 3–7 bar window fitting under `TIGHT_MULT × ADR`. Its range
is therefore compressed by construction — median 1.33, IQR 1.20–1.42, hard ceiling 1.50, 16.9%
pinned within 0.05 of it — so the width cannot rank anything. What the selection leaves behind is
**how many bars fit inside that fixed range**. Cluster churn measures the same thing (r = 0.850 with
k, and it adds +0.098 over k once k is in) so it is **not** a second dimension; k is kept because it
is already computed and is an integer a human can audit.

**Pre-registered:** if round 3's grades put k's partial r below +0.15 on the split-accept
population, the ×2 tightness dimension is declared **unscorable on this structure** and scores
neutral for every card, and ticket 17's R6 fallback is put to the trader. That is the outcome this
round exists to rule in or out, and naming the trigger now stops it being argued afterwards.

---

## 2. How many cards

Round 2 measured a grade SD of 1.282★ on a stratified deck. Ticket 17's deck, **unstratified and
bare**, measures **1.083★** — the honest nightly variance, and the number round 3 sizes from.

| test | effect | n |
| --- | --- | --- |
| eye vs machine correlation | r = 0.26 | **114** |
| " | r = 0.30 | 85 |
| " | r = 0.20 | 194 |
| two-group mean grade difference | Δ = 1.00★ | 19/arm |
| " | Δ = 0.75★ | **33/arm** |

At α = 0.05 two-sided, 80% power.

### The decks

| deck | n | question |
| --- | --- | --- |
| **A3 — core** | 120 | the primary endpoint; fits the four free numbers. US, split population |
| **C3 — IDX** | 52 | per-market calibration **and** D13's partial-lock probe. 26 partial lock (1–20% collapsed bars) vs 26 clean |
| **D3 — rejects** | 40 | 20 split rejects vs 20 detections, bare. Ticket 11's unowned obligation |
| **repeats** | 12 | A3 cards re-shown inside C3 and D3, to measure the test–retest ceiling |
| **total** | **224** | |

**A3 is the only deck that must be complete.** C3 and D3 each answer one carried-in question and
can be graded in a later sitting; an ungraded deck is reported as unanswered, not dropped.

Three round-2 decks are **retired, not merely ungraded**:

- **Deck B is moot.** Its split was already-breached vs comfortably-above, and already-breached is
  **0.2%** under the clamped trigger. Ticket 17's R2 answered the D5 probe by other means — the eye
  picked the clamped-trigger drawing 10 of 11 times.
- **Decks A and C as built** measure a detector that no longer runs.

### The test–retest ceiling is a gate this time

Round 2's 12 repeats lived in decks that were never graded, so **every correlation on this map is
still reported against an unknown ceiling**. In round 3 the repeats sit inside C3 and D3, which are
optional decks — so the ceiling is measured only if they are graded. **Pre-registered:** if the
ceiling goes unmeasured again, every round-3 correlation is published as *"against an unmeasured
ceiling"*, and no threshold is called final. If the measured test–retest r is below ~0.6, that is
the finding, and the thresholds are provisional whatever they fit.

---

## 3. Sampling (seed 3, executed by `build_deck3.py`)

- **A3** — split detections that pass `tight & line_ok & caught_up`, the ≥25% prior-move floor and
  D15's decile gate (`prior_move ≥ 0.90`), US only, drawn from the whole 2019-01 → 2023-06 sweep.
  **Stratified 24 per band of the round-3 provisional score** (≤1.5 / 2 / 3 / 4 / 5), at most **2
  cards per symbol**. Stratification is kept because it spreads cards over the range being
  calibrated — but the correlation it produces is **range-stretched**, and both the raw and the
  frequency-reweighted statistic are reported, as in round 2.
- **C3** — IDX only, same gates. 26 with collapsed-bar share in `(0, 0.20]`, 26 with share exactly
  0, matched on provisional band as closely as the pool allows.
- **D3** — 20 rejects, split evenly between the split's **own** two rejection paths (10 `no_cluster`,
  10 `line_not_drawable`), and 20 accepted detections matched to their provisional band mix. The
  third path, `not_caught_up`, is 1.6% of bar-dates and is not sampled.
- **Repeats** — 12 A3 cards re-rendered with a different card id and shuffled into C3 and D3. The
  grader is not told which they are.

**All cards are rendered bare** — candles and §2's moving averages, no base, no cluster, no
trigger, no stop. Round 2 rendered deck A with overlays and deck D without, which is exactly the
axis the +0.69★ gap sits on, and it cannot be untangled after the fact. Rendering everything bare
costs the ability to grade the drawing — already answered by ticket 17's R2, 10 of 11 — and buys a
single population that can be pooled.

**Nothing is revealed until submission.**

---

## 4. What gets fitted, and how

Unchanged from round 2 except where §1 changes the inputs:

- **Objective**: mean absolute error between computed stars and the grade, minimised by coordinate
  descent over `rubric3.GRIDS`, ties breaking toward the incumbent so a threshold only moves on
  evidence.
- **Honesty**: 5-fold cross-validation on A3. Every headline number is out-of-fold. In-sample is
  reported next to it; **if they diverge by more than 0.15★ the fit is declared overfitted and no
  thresholds are published** — which is precisely what happened when the round-2 grades were pushed
  at the new structure, and is the reason this round exists.
- **Boolean vs continuous**: both fitted on the same folds. Continuous carries no extra free
  parameters (each ramp is the fitted cut ± a half-width fixed in advance). Continuous wins only if
  it beats boolean out-of-fold on **both** mae (by ≥ 0.10★) **and** within-one-star. Round 2 decided
  **boolean** on this rule; it holds the ground again.
- **The 4★ cut**: confusion matrix of machine ≥N★ against eye ≥4★, out-of-fold. The cut moves off
  4★ only on ≥10pp better precision at no worse recall. Round 2 found ≥3.5★ dominates ≥4★ on both
  and still did not clear the rule; if round 3 reproduces that, the rule is **reported as the thing
  standing in the way** rather than silently reapplied a third time.
- **Per-market**: fit pooled. IDX gets its own numbers only if the pooled fit's mean residual on IDX
  differs from US by > 0.5★, or an IDX-only fit beats pooled on IDX cards by > 0.15★ out-of-fold.
  There are currently **zero graded IDX cards on any structure**, so this is the first time the
  question can be asked at all.

---

## 5. Known limits carried in

- The pool is still ticket 09's reduced, survivorship-biased ~650-name US universe. `full_universe_check.py`
  runs alongside; no threshold is final until it survives that check.
- Ticket 17's name-level comparison was **null** (+0.40★, p = 0.298). Refitting the rubric on the
  new structure is what makes the detector swap hard to reverse. If tightness comes back unscorable
  under §1's trigger, that is reported **loudly**, with R6's fallback, rather than worked around.
- The eye remains the arbiter by necessity: ~672 triggered setups per band are needed to resolve a
  0.3R outcome difference, against 33 available at 5★.
- 22 of the split's parameters are unfitted borrowed defaults, and `TIGHT_MULT` alone swings the
  list 63% — which is ticket 19's, but it means round 3 fits a rubric **on top of** an unfitted
  detector. `TIGHT_MULT` also directly sets the cluster's range ceiling, and therefore the
  distribution of k, which is now the ×2 tightness dimension. **Ticket 19 can move this round's
  primary signal**, and the two tickets are coupled in that order.
