# Ticket 17 — what the measurement found before any grading

Ticket 16 measured the base/cluster split's **structure** and every number was good: 14-bar bases,
a stop bounded at 1.5×ADR by construction, ~63 US names a night against today's ~64. It said
plainly that it had not checked whether the setups it finds are the ones the eye wants.

This ticket checked. Reproduce with `overlap.py` → `grades.py` → `contraction.py` → `params.py` →
`hybrid.py` → `build_deck17.py`.

## F1. The same-sized list is a different list

Both scans share a grid, so the join is exact rather than approximate — 318,617 (symbol, night)
pairs evaluated by one or both.

| | both | 08 only | split only | Jaccard |
| --- | --- | --- | --- | --- |
| 08 D6-gated vs split + 25% floor | 10,369 | 29,308 | 26,929 | **0.156** |
| 08 ungated vs split | 46,830 | 143,214 | 7,371 | 0.237 |

Per night, per market:

| | 08 | split | shared |
| --- | --- | --- | --- |
| US | 21.3 | 20.4 | **5.5** |
| IDX | 3.9 | 3.4 | **1.1** |

(1-in-3 date sampling; multiply by ~3 for a real night.)

**Ticket 16's "the list lands where it already is" is true of the count and false of the contents.**
The split keeps 26% of what ticket 08 surfaces; three quarters of its list is new. This is not a
refinement of the incumbent detector, it is a different one that happens to be calibrated to the
same volume — and list length, the number ticket 16 reported, is the one property that cannot
distinguish them.

Two mechanisms, and neither is the cluster:

- the split drops 08's picks mostly on **line drawability** (58.8% of drops) — q-scanner's touch-zone
  and bounded-overshoot test, not the cluster (14.1%) and not the MA catch-up (6.0%);
- 08 drops the split's picks mostly on **D6's stop gate** (80.8%) — which ticket 16's R3 already
  removed, so under R3 the split is largely a *subset* of 08's ungated detections: 86.2% of its
  picks are names 08 also finds, and only 13.8% are geometry 08's triangle test refuses.

So the honest framing is not "two rival detectors" but **"D6's cut versus the split's cut, over
mostly the same pool"** — and those two cuts agree on 62.9% of detections.

## F2. The split's cut is uncorrelated with the trader's eye

Ticket 15's deck A is 120 blind grades that already exist. Evaluating the split at those exact bars
(`at_dates.py` — the two scans sweep different date grids, so 90 of 120 cards do not collide, and
comparing where the grids happen to coincide would silently sample):

| trader's grade | n | split accepts |
| --- | --- | --- |
| 1 | 25 | 44% |
| 2 | 33 | 27% |
| 3 | 30 | 23% |
| 4 | 26 | 50% |
| 5 | 6 | 17% |

**r = −0.009, permutation p = 0.87.** It keeps about a third of everything, regardless of grade.
4–5★ cards survive at 43.8%, 1–2★ at 34.5% — a 9pp gap on n=32 against n=58, which is noise.

This is the same shape of result ticket 09 found for the star score (r = −0.043), and it is the
measurement ticket 16 said was missing. **It bounds one direction only**: adopting the split costs
you over half of what you currently like, and it says nothing about whether the 74% it adds is
better. Deck 17 asks that, because nothing already recorded can.

## F3. The split does not escape ticket 09's base-length problem — it inherits it

Across the graded cards, the trader's grade against the **split's** base length: **r = −0.375**
(n = 108, significance 0.19). The same inverse preference ticket 09 found against ticket 08's base
length (−0.558), on a structure with a median base of 14–18 bars instead of 3.

That matters for what replaces D7's contraction, because every candidate tightness measure the
split makes available is a length proxy once you look:

| candidate | r vs eye | partial r, controlling for base length |
| --- | --- | --- |
| cluster range ÷ base range | +0.242 | **−0.020** |
| base height in ADR | −0.269 | **−0.022** |
| √L shortfall over trailing sub-windows | −0.138 | +0.034 |
| cluster range ÷ ADR (the "narrow" half) | +0.127 | +0.175 |
| **cluster length k** | +0.236 | **+0.260** |

The two that clear significance unadjusted (`narrowing_ratio`, `base_height_adr`) **collapse to zero**
when base length is partialled out: they are ticket 09's failure mode in new clothing. The
incumbent D7 as shipped correlates −0.338 with the eye — significantly *against* it — while round
2's `min(L, 20)` repair is length-free (0.010) and eye-free (+0.042).

**One thing survives the control: the cluster's own length, at +0.260.** The trader prefers a
*longer* tight cluster, independent of how long the base is. That is a signal the incumbent
structure has no analogue for, it is already computed, and it is the only new scoring information
this whole comparison produced.

`cluster range ÷ ADR` is the natural "narrow" half R3 owes, and it is nearly length-free (+0.175,
just under significance) — but it is **compressed by construction**: median 1.33, IQR 1.20–1.42,
ceiling 1.50, with 16.9% pinned within 0.05 of the ceiling. The cluster is *selected* to be under
the multiplier, so the quantity that remains is a poor ranking key even where it is a fine gate.

## F4. The parameter bill is 22, and one of them is the whole cut

Ticket 08 resolved with zero tunables, ticket 09 cost it two, round 2 fitted six thresholds. The
split adds **22 free numbers** — 4 move windows, base min/max, cluster k range, tightness
multiplier, two MA catch-up multiples, four line-fit numbers, six line-validity numbers, and the
prior-move floor. `MA_PROX_ADR` is defined and never read. **None is fitted to anything**; they are
q-scanner's defaults carried across.

Swept over 400 US names, list length against each parameter's plausible range:

| parameter | swing |
| --- | --- |
| `TIGHT_MULT` (1.25 / **1.5** / 1.75) | **63.2%** |
| `MAX_OVERSHOOT_FRAC` | 21.1% |
| `MAX_BASE_LEN` | 15.5% |
| `TOUCH_TOL_ADR` | 13.7% |
| `K_MAX` | 6.1% |

The tightness multiplier alone moves the nightly list by nearly two thirds across a range no one
could argue is wrong on principle. It is simultaneously the looseness cut R3 asked for, the thing
that bounds the stop, and an unfitted borrowed constant.

## F5. The cheap option the ticket did not name

The split is two separable things and only one of them answers R3:

- the **cluster** supplies the looseness cut and the bounded stop;
- the **base** supplies a longer window to fit a line over — R4's problem, not R3's — and it is the
  half that costs D3's retained set, breaks D7's contraction, and invalidates ticket 15's in-flight
  rubric.

So: ticket 08 exactly as it stands, ungated per R3, plus "a valid 3–7 bar trailing cluster must
exist" as the cut D6 was making implicitly (`hybrid.py`, over all 189,896 ungated detections):

| rule | US/night | IDX/night |
| --- | --- | --- |
| 08 ungated — no cut at all (ticket 16 R3) | 314.0 | 46.6 |
| 08 + D6's 1×ADR stop gate (today) | 63.7 | 12.3 |
| 08 + a cluster exists (≤1.5×ADR) | 165.9 | 26.6 |
| **08 + a cluster spanning ≤1.25×ADR** | **59.2** | **10.8** |
| 08 + cluster + 25% move floor + line drawable | 57.4 | 10.6 |
| the full split | ~63 | ~11 |

**One parameter — the tightness multiplier — restores today's list length**, and it is the parameter
that was doing the work in the full split anyway (F4). Under it:

- D2, D3, D4, D5, D7 and **ticket 15's entire in-flight rubric survive untouched**;
- the "narrow" half of D7 is restored as the cluster range in ADR, which is what R3 asked for;
- the stop is *shown* at the cluster low rather than the base low — median 0.91 ADR against 1.20,
  within 1.5 ADR on **94.2%** of detections against 64.1%. Tight, but **not structural**: 08's
  trigger is not anchored to the cluster, so the 1.499 ceiling the full split gets by construction
  is only an empirical 6.34 here.

The cluster cut and D6 agree on **62.9%** of detections, so this is a genuinely different screen
from today's, not a re-parameterisation of it — which is exactly why it needs the eye too.

## What the deck asks

`deck17.html`, 75 cards, two sections.

**Section 1 (60 cards, blind, graded 1–5).** 20 shared, 20 08-only, 20 split-only, drawn as bare
candles with the MA set and **no overlay at all** — a drawn base would label the arm, since 08's is
3 bars and the split's is 15. Every arm is decile-gated as it would be on a real night. This is the
question F2 cannot answer: are the names the split adds better than the names it drops?

**Section 2 (15 cards, blind A/B).** Names both detectors fire on, the same bars drawn twice at
identical scale — 08's primary window, OLS line, `min()` trigger and base-low stop against the
split's base + cluster, envelope, `max()` trigger and cluster-low stop. Median base 3 bars against
18. This is ticket 16's unasked eye question, now asked over bases long enough for a line to mean
something.
