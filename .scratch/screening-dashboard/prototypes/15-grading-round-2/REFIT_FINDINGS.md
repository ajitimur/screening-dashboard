# Refitting the rubric on the base/cluster structure — what the existing grades can and cannot say

Ticket 17 adopted the base/cluster split whole and re-scoped this ticket: four of round 2's six
fitted thresholds now describe a window that no longer exists, and it left the largest open
question as *"whether the ×2 tightness dimension is scorable on this structure at all"*.

This is the measurement pass. It uses only grades that already exist — round 2's deck A (120 cards)
and ticket 17's section 1 (60 cards) — re-measured over the split's geometry by
`split_signals.py`. **172 of the 180 graded cards have computable split geometry; 81 of them are
setups the split would actually surface.**

Reproduce: `split_signals.py` → `split_tightness.py` → `split_diag.py` → `split_refit.py`.

---

## F1. Tightness is scorable — but as a packing count, not a width

Ticket 17's R4 tested five candidates on deck A alone and found the two that look significant
collapse under a base-length control. Re-run on three populations, including the one that matters:

| candidate | deck A (n=114) | deck 17 (n=58) | **split-accept (n=81)** |
| --- | --- | --- | --- |
| cluster range ÷ ADR — the "narrow" half | +0.175 | −0.013 | **+0.100** (p = .38) |
| cluster range ÷ base range — narrowing | −0.020 | +0.024 | **+0.076** (p = .51) |
| √-shortfall over the base | +0.056 | −0.275 | **−0.115** (p = .31) |
| base height in ADR | −0.030 | −0.289 | **−0.027** (p = .82) |
| **cluster length k** | **+0.260** | **+0.216** | **+0.327** (p = .002) |
| **cluster churn** (new here) | +0.238 | +0.266 | **+0.327** (p = .002) |
| density, k ÷ cluster range | +0.154 | +0.227 | +0.285 (p = .014) |

All partial correlations, controlling for base length. **Every measure of *narrowness* fails on the
population the rubric actually ranks. Cluster length k is the only one that replicates**, and it is
the only one that replicates on all three.

The reason is structural, and it says what tightness *is* on this detector. The cluster is
**selected** as the largest 3–7 bar window fitting under `TIGHT_MULT × ADR`, so its range is
compressed by construction — median 1.33, IQR 1.20–1.42, hard ceiling 1.50, 16.9% pinned within
0.05 of it. The width is spent by the selection. What survives is **how many bars pack into that
fixed range** — which is a count, not a width.

Cluster churn measures the same object: r = 0.850 with k, and it adds only +0.098 once k is in.
**One new dimension, not two.** k is kept: already computed, an integer, and auditable on a chart —
which is what ticket 11 asked of a sort key.

The eye rises monotonically in k, and flattens:

| k | n | mean eye | ≥4★ |
| --- | --- | --- | --- |
| 3 | 21 | 2.52 | 33% |
| 4 | 28 | 2.79 | 36% |
| 5 | 12 | 3.25 | 42% |
| 6 | 10 | 3.40 | 60% |
| 7 | 10 | 3.40 | 50% |

Best boolean cut is **k ≥ 5** (+0.67★). 36.6% of the population sits at k = 3.

## F2. D10's MA distance is dead weight; only "SMA20 rising" survives

Ticket 17's R3 flagged that D10 overlaps the split's own MA catch-up test and left the
reconciliation here. Measured:

- The catch-up test is a **gate**, so 100% of the 54,201 surviving detections already satisfy it.
- `ma_dist` against the eye: r = +0.177, but **partial r = +0.010, permutation p = 0.93**. Nothing
  survives the length control.
- `ma_dist` correlates +0.606 with the close-to-SMA20 gap the catch-up test already reads.
- The other half of the dimension does carry signal: **SMA20 rising, r = +0.291**, true on 81.5%.

So the dimension keeps its ×1 and loses its threshold: **`ma_support` = SMA20 rising**. Free numbers
fall from six to four (`cluster_k`, `orderliness`, `dryup`, and the length band).

## F3. The thresholds cannot be fitted on the grades that exist

This is the finding that decides what happens next.

**The two graded sets are not poolable.** Deck A was stratified on the *old* provisional score — 24
cards per band, deliberately range-stretched — and ticket 17's deck was not. On the same
population (names both detectors fire on, deck 17's `shared` arm) the two differ by **+0.69★,
p = 0.044**. Mean absolute error is a level statistic, so a 0.7★ offset between the halves of the
sample lands directly on every fitted threshold. The confound cannot be untangled after the fact:
deck A also drew overlays and deck 17 drew bare candles, so presentation and sampling moved
together.

Fitting anyway, on the 81 split-accepted cards:

| | r | mae | within 1★ |
| --- | --- | --- | --- |
| round 2's thresholds, re-pointed at the new domain | **+0.221** | 1.09 | 64% |
| fitted, in-sample | +0.179 | 1.01 | — |
| **fitted, out-of-fold** | **+0.007** | 1.18 | 59% |

**The fit is worse than not fitting.** Out-of-fold r is +0.007, and the two sources disagree on four
of five thresholds:

| | deck A | deck 17 |
| --- | --- | --- |
| `cluster_k` | 5 | 3 |
| `orderliness` | 0.20 | 0.325 |
| `dryup` | 1.1 | 0.9 |
| `len_ok` | 20 | 10 |
| `len_bad` | 40 | 40 |

Fold-to-fold, `cluster_k` ranges over the whole grid (3–6). At n = 81 against a pre-registration
that sized the round at 114, this is noise being fitted.

**No thresholds are published from this pass.** The one thing the fit does show is that the k-based
tightness dimension is worth having at all: scoring it from k gives out-of-fold r = +0.059 against
**−0.152** when it scores neutral.

## F4. D13's partial-lock probe is no longer runnable — the population has gone

Ticket 09 found partially limit-locked IDX bases (1–20% collapsed bars) scored best of any group
and carried the probe here as a 52-card deck. Under the split, measured over 2,244 accepted IDX
detections:

- **98.1% have *zero* collapsed bars in the base**;
- 1.8% are partially locked;
- 0.7% are more than 20% locked.

A 26-per-arm probe cannot be drawn from 1.8% of the population. The question is **de-scoped from a
powered probe to a descriptive subgroup** — deck C carries the 12 locked cards that exist and
reports them as such. The change of base from 08's ~3-bar window to the split's ~14-bar base is
what moved it: a single limit day is a third of a 3-bar base and a fourteenth of this one.

## F5. There are still zero graded IDX cards, on any structure

Round 2's deck A was entirely US, ticket 17's deck was entirely US, and round 2's deck C was never
graded. Per-market calibration has never once been asked. Round 3's deck C is the first IDX deck
that exists.

---

## What this means

The rubric's **structure** is now settled on the new geometry — tightness is k, `ma_support` is
"SMA20 rising", orderliness / dry-up / length keep their form over the split's base. Its **numbers**
are not, and cannot be, until there are grades collected on the split's own population under one
consistent rendering.

`PREREGISTRATION_R3.md` fixes that round in advance and `build_deck3.py` has rendered it: **224
cards, all bare**, A3 120 US core · C3 58 IDX · D3 46 rejects-and-detections, with 12 repeats hidden
inside C3 and D3 for the test–retest ceiling that has now gone unmeasured twice.
`analyse3.py` implements the pre-registered analysis and is verified end to end on synthetic grades,
so the numbers land the moment the grades do.

One thing the pre-registration names that this pass could not: **if round 3 puts k's partial r below
+0.15 on the split-accept population, the ×2 tightness dimension is unscorable on this structure**,
and ticket 17's R6 fallback — 08's detector plus only the cluster, which leaves round 2's rubric
intact — goes back to the trader. Naming the trigger now is the point; k clears it comfortably on
today's 81 cards (+0.327), but those 81 are not the round.
