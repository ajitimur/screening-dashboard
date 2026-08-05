# Deck E3 — the band's confirmation set

**Written before a single E3 card was rendered.** This document adds no rules. Every number below
is derived from `PREREGISTRATION_R3.md` §2, §3 and §6; where a choice was genuinely open it is
named as a choice and the reasoning is given, so it can be argued with *now* rather than after the
grades arrive.

Ticket 15 resolved with out-of-fold **r = +0.255** on deck A3, and with an amendment (R3 §6) that
redefined orderliness as a band **after** A3 was graded. Cross-validation controls threshold
*values*, not the choice of functional form, so that +0.255 is optimistic and the band is a
hypothesis with fitted numbers. §6 fixed the bar in advance:

> the band is credited only if it reproduces out-of-fold on grades collected *after* this document,
> at r >= +0.20, on the split's population. If it does not, orderliness is dropped and its x2
> redistributed.

Decks C3 and D3 cannot serve. C3 is IDX and D3 is half rejects, so neither is the split's accepted
US population. **E3 is the deck §6 actually requires**, and this document fixes it.

---

## 1. Population — identical to A3, with one exclusion

US only. Split-accepted (`tight & line_ok & caught_up`), prior move >= 25%, and D15's decile gate
(`prior_move >= 0.90`), drawn from the same 2019-01 -> 2023-06 sweep. Rendered **bare** by the same
renderer, asked the same question, graded with the same keys.

The one addition: **no card whose `(symbol, end)` already appears in `deck3_manifest.csv`.** A3, C3
and D3 cards are excluded, so E3 is fresh grades on fresh cards — which is what "collected after
that document" requires. A card the eye has already seen is not independent evidence.

## 2. Size — 194 fresh cards

R3 §2's power table is the only place the +0.20 bar is tied to a sample size:

| test | effect | n |
| --- | --- | --- |
| eye vs machine correlation | r = 0.30 | 85 |
| " | r = 0.26 | 114 |
| **"** | **r = 0.20** | **194** |

The decision rule is a threshold at r = +0.20, so 194 is the row that applies: at n = 120 the
standard error on r near +0.25 is ~0.09, which is wider than the distance between the estimate and
the bar. A confirmation that cannot resolve its own threshold is not a confirmation.

**194 fresh cards, plus 12 repeats (§4) = 206 cards.** That is a long sitting, and it is the honest
price of §6. If it has to be split, grade it in order — the cards are already shuffled, so any
prefix is an unbiased sample, and `analyse3.py` accepts `-` for ungraded and reports the n it got
with its standard error. **Below 120 graded the confirmation is reported as underpowered rather
than as a verdict.**

## 3. Stratification — kept, and identical to A3's

A3 was stratified 24 per band of the provisional score. That range-stretches the correlation, which
R3 §3 already acknowledges and requires be reported both raw and frequency-reweighted.

E3 is stratified **the same way** — equal cards per provisional band, at most 2 per symbol,
shortfall redistributed over the bands with depth. This is a choice, and the reason is that +0.255
is a stretched number: comparing an unstretched confirmation against a stretched bar would fail the
band for a sampling artefact rather than for the band. Like A3, the provisional score used to
stratify is `rubric3.score3` under **`T3`'s pre-fit defaults**, not the values A3 fitted, so the
spreading device is the same device A3 used and does not bake the fitted band into the sample.

Both statistics are reported, as in round 2 and round 3.

## 4. Repeats — 12 more, for the ceiling

12 A3 cards are re-rendered under fresh ids and shuffled into E3, **disjoint from the 12 already
hidden in C3 and D3**. Same purpose: the test-retest ceiling that R3 §2 made a gate and that has
now gone unmeasured for two rounds.

They cost 12 cards and they mean E3 measures the ceiling **on its own**, so a trader who grades only
this deck still discharges the ticket's second obligation. If C3 and D3 are graded too, the pairs
pool to 24 and the ceiling estimate roughly halves its error. Repeats are excluded from every
confirmation statistic in §5 — they are A3 cards.

## 5. What is computed, and what decides

`analyse3.py E=<string>` adds section 8. Fixed now:

- **The decision number is the out-of-fold r from the same 5-fold procedure A3 used, refit on E3
  alone.** §6 says "reproduces out-of-fold"; the honest reading is to re-run the identical procedure
  on the new grades. Band credited iff **r >= +0.20**.
- **Reported alongside, descriptive:** A3's fitted thresholds applied frozen to E3 with no refit.
  This is the stricter test and the more informative one, but it is *not* the decision number,
  because §6 did not ask for it and choosing the more favourable of two numbers afterwards is
  exactly the freedom this document exists to remove.
- **Also reported, descriptive:** the orderliness band's own partial r against the eye controlling
  base length; the fraction of E3 cards inside the band (A3's failure mode was 99% inside a
  one-sided cut); and the fold spread on `ord_lo`/`ord_hi`.
- **If the decision number is below +0.20:** orderliness is dropped, its x2 redistributed, and the
  rubric refit without it — the outcome §6 names. That refit is reported at the same time so the
  cost of dropping it is visible.
- **The ceiling gates everything, as R3 §2 already fixed.** If test-retest r comes back below ~0.6,
  every number above is provisional whatever it fits — including a band that clears +0.20.

## 6. What this deck does *not* settle

- Per-market calibration — that is deck C3, and there are still zero graded IDX cards.
- The rejected candidates — that is deck D3, an obligation now carried by three tickets.
- Ticket 19's 22 borrowed detector parameters. `TIGHT_MULT` sets the cluster's range ceiling and
  therefore the distribution of k, the x2 tightness signal. **Ticket 19 can move this deck's primary
  signal**, and if it does, E3's numbers are measured against a detector that changed underneath
  them. The coupling is R3 §5's, unchanged and still live.
