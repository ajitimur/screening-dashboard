# Deck F — does `line_not_drawable` discard setups you want?

**Written before a single F card was rendered.** Ticket 25 asks for the rule to be named in
advance, in the deck3 style. Everything below is fixed now so it can be argued with *now* rather
than after the grades arrive.

The parent result is [`DECK_D_RESULTS.md`](DECK_D_RESULTS.md) §2: pooled rejects grade −0.90★
below detections, but `no_cluster` carries it (−1.40★, CI excludes zero) while
`line_not_drawable` does not separate (−0.40★, CI −1.22 to **+0.42**, 3 of 10 cards graded 4★).

Two things this document adds that ticket 25 did not anticipate, both measured rather than
assumed, both in §1 — deck D3's two arms were **not drawn from the same population**, in two
independent ways, and correcting either moves the estimate in the direction that makes the worry
worse.

---

## 1. Population — and the two confounds deck D3 carried

`build_deck3.py` built its arms with two different functions. `population()` applies D15's decile
gate (`prior_move >= 0.90`) and stratifies on the provisional score; `rejects()` applies neither —
it draws at random from `has_base & move_gain >= 25%`. So deck D3 compared:

| | decile gate | stratified | catch-up test |
| --- | --- | --- | --- |
| detections arm | **yes** | **yes, equal per band** | passed |
| reject arms | no | no, random | **not required** |

Measured on `split.pkl` (US, `has_base & move >= 25%`, 1,500-row samples):

| path | share of pool | clears `prior_move >= 0.90` | median prior-move pct |
| --- | --- | --- | --- |
| accepted | 21.2% | 8.7% | 0.801 |
| `no_cluster` | 54.4% | 7.9% | 0.775 |
| `line_not_drawable` | **22.7%** | **6.7%** | 0.753 |
| `not_caught_up` | 1.7% | 17.3% | 0.851 |

So roughly **93% of deck D3's reject cards sat outside the decile the detections arm was 100%
inside**, and some of its `line_not_drawable` cards additionally failed the catch-up test. Prior
move is a strength signal the eye can read off a bare chart. Both confounds push the reject arms
*down*, which means **−0.40★ is an upper bound on how badly this path does** — the honest estimate
is closer to zero or above it. Deck D3's headline direction (−0.90★, carried by `no_cluster` at
−1.40★) is large enough to survive this; the `line_not_drawable` sub-result was never large enough
to survive anything, which is why it is here.

**Deck F fixes both.** Every arm is drawn from the same gated population and differs in exactly one
bit — the rejection path under test:

- US only, `move_gain >= 25%`, **`prior_move >= 0.90`** (D15), from the same 2019-01 → 2023-06 sweep.
- **detections**: `tight & line_ok & caught_up`
- **`line_not_drawable`**: `tight & ~line_ok & caught_up` — fails on the line and nothing else
- **`not_caught_up`**: `tight & line_ok & ~caught_up` — fails on the catch-up test and nothing else

That reject definition is also the *operational* one. It is precisely the set that would join the
nightly list if the test were deleted, which is the counterfactual the remedy is about.

**No stratification, either arm.** Deck D3 stratified detections by provisional band and drew
rejects at random, which moves the two arms' means for a reason unrelated to the question. Deck F
draws **at random from each population as it actually occurs**, at most 2 cards per symbol. The
comparison is a mean-grade difference, so frequency-representative is the only sampling that makes
the difference mean what it says. Band mix is recorded in the manifest and reported.

**No card the eye has already seen.** Every `(symbol, end)` in `deck3_manifest.csv` or
`deckE_manifest.csv` is excluded, except the deliberate repeats in §4.

## 2. Size — 33 per arm, and why the third arm is here

`PREREGISTRATION_R3.md` §2's power table: a two-group mean difference of **0.75★ needs 33/arm** at
80% power. Deck D3 had 10. So:

**33 `line_not_drawable` + 33 detections + 33 `not_caught_up` + 6 repeats = 105 cards.**

The third arm is ticket 25's explicit open choice — *"if the eye is being asked for another sitting
anyway, decide deliberately whether to carry it."* It is carried, for one reason and against one:

- **For:** it costs 33 cards on a sitting that is happening regardless, it reuses the same
  detections arm as its control at no extra cost, and it closes the **last** unmeasured rejection
  path on this map. Left out, it is deferred a fourth time with no deck in sight.
- **Against:** it is small — 0.95 US names/night decile-gated, 0.16× the accepted list (§3). Even a
  total failure of the path is a small operational miss.

It is therefore **secondary and descriptive**. No remedy is pre-committed to it, and its result
does not gate anything. Two comparisons share one control arm, so a nominal 0.05 on the secondary
is not a discovery; it is reported with that stated.

**Grade in deck order if it has to be split** — the cards are shuffled, so any prefix is unbiased.
**Below 20 graded in either primary arm the result is reported as underpowered, not as a verdict.**

## 3. The price of the remedy, measured first

Decile-gated US list, 250 sampled nights, scaled for the 1-in-3 sweep:

| population | names / night | vs the accepted list |
| --- | --- | --- |
| accepted (as specified) | **5.98** | 1.00× |
| + `line_not_drawable` | +3.54 | → **9.5/night, ×1.59** |
| `no_cluster` (not under test) | 12.54 | 2.10× |
| `not_caught_up` | 0.95 | 0.16× |

So deleting `line_ok` **increases the nightly list by 59%**. That is the cost side of any remedy,
and it is fixed here so it cannot be re-argued once the grades are in.

The path is not one test. Among the marginal population (30,662 rows), what actually fails:

| failure | share |
| --- | --- |
| overshoot only (`> 1.0 ADR` max, or `> 20%` of bars over) | **50.2%** |
| touch zones only (`< 2` zones, and no single zone reaching back) | 23.1% |
| both | 24.2% |
| `MAX_OVERSHOOT_FRAC` alone | 2.5% |

The marginal names have **longer bases** (median 22 vs 14 bars) and **higher ADR** (5.29% vs
4.52%) than accepted ones. Both are reported as covariates; base length in particular, because
ticket 09 found the eye reads it inverted and ticket 17 found that did not reproduce on the split.

## 4. Repeats — 6 more, and the pooled ceiling

6 further deck-A3 cards are re-rendered under fresh ids and shuffled in, **disjoint from the 24
already used** across decks C3, D3 and E3. Same purpose as always: the test–retest ceiling every
correlation on this map is read against.

The map records +0.808 on 12 pairs (ticket 20), then +0.854 and +0.831 on two disjoint 18-pair
sets (tickets 22 and 23), and notes the **pooled 24-pair figure is unmeasured**. That number needs
no new grading at all — every grade already exists — so it is computed as a ride-along this
session and reported before deck F is graded. Deck F's 6 take the pool to **30 pairs**.

## 5. The decision rule — fixed now

Primary comparison: **mean eye grade, `line_not_drawable` arm minus detections arm**, call it Δ,
with a two-sample 95% CI.

| Δ (and its interval) | reading | consequence |
| --- | --- | --- |
| **CI entirely below 0** | the path rejects names the eye also rejects | `line_ok` **stands as specified**; ticket 23's discharge extends to it; nothing changes |
| **CI contains 0 and \|Δ\| ≤ 0.56★** (the eye's own noise floor) | the path is **indistinguishable from what the screen surfaces** | this is a **finding, not a pass** — the remedy in §6 fires |
| **CI entirely above 0, or Δ > 0** | the path is discarding the **better** names | remedy fires, and `line_ok` is presumed wrong rather than merely unproven |

Reported alongside, descriptive, none of them deciding: the grade distribution per arm; ≥4★ share
per arm; Δ controlling for base length; the secondary `not_caught_up` Δ; the band mix actually
drawn; and the repeats' contribution to the ceiling.

**The ceiling gates everything, as `PREREGISTRATION_R3.md` §2 already fixed.** A 0.75★ target sits
only just above the 0.56★ single-grade noise floor, which is exactly why the arms are 33 and not 20.

## 6. The remedy, named in advance

If row 2 or row 3 of §5 fires, `line_ok` is not left as it is. The choice among these is the
trader's, but the menu is fixed now and §3 has already priced it:

1. **Downgrade from a hard reject to a scored penalty.** The path is 22.7% of the pool and the
   marginal names cost 59% more list. A dimension in the §3.5 rubric — or a demotion in the sort —
   keeps them visible without doubling the sitting. This is the default if Δ is inside the noise
   floor, because "indistinguishable" is an argument against a *gate*, not for equal standing.
2. **Loosen the sub-test that fails.** §3 splits the path: overshoot carries 50%, touches 23%. If
   the graded cards concentrate on one of them, that sub-test is the one that moves — which is a
   smaller change than deleting `line_ok`, and ticket 19 already classified these parameters as
   borrowed rather than fitted.
3. **Delete `line_ok` from detection entirely**, keeping the fit for the chart and the envelope
   (which is all it does downstream — ticket 18 established the trigger is the cluster high by
   identity, so the line never reaches the trigger). Reserved for Δ > 0 with an interval clear of
   zero: the strongest evidence for the smallest defensible rule.

**What does not happen:** the rubric is not refit on these grades, and the thresholds are not
touched. Deck F is a reject-vs-detection comparison on a bare deck, not a calibration set — the
same discipline deck D3 kept.

## 7. What this deck does not settle

- **Anything about `no_cluster`.** It is 54.4% of the pool and 2.10× the accepted list, and deck D3
  already separated it at n=10. It is not sampled here.
- **The names the detector never sees at all.** Every arm is drawn from what the split *considered*,
  not from the universe.
- **Whether the eye is right.** The ceiling says the eye is reproducible (§4); it does not say it
  predicts returns. The map's standing note on that stands: ~672 triggered setups per band would be
  needed to let outcomes arbitrate, and nobody has them.
- **Ticket 19's borrowed parameters.** `TOUCH_TOL_ADR`, `MIN_TOUCHES`, `MIN_TOUCH_GAP`,
  `MAX_OVERSHOOT_ADR`, `MAX_OVERSHOOT_FRAC` and the `OVER_W`/`UNDER_W` ratio all shape this path and
  none was fitted. Deck F asks whether the path as a whole is wrong, not what the six numbers
  should be.
