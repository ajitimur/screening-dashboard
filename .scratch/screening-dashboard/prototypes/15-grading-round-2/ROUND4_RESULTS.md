# Deck E3 — the band's confirmation, and the ceiling

206 cards graded in one sitting: 194 fresh US cards on the split's accepted population, plus 12
repeats from A3. Grade mix 22 / 58 / 61 / 45 / 20 across 1–5★, mean 2.93★.

Run: `analyse3.py A=<grades3_A.txt> E=<grades3_E.txt>`. Rules fixed in advance by
[`PREREGISTRATION_R4.md`](PREREGISTRATION_R4.md); nothing below chose a rule after the fact.

---

## 1. The ceiling: r = +0.808 — and it changes how every other number reads

**Measured for the first time on this map**, after going unmeasured for two rounds.

| | |
| --- | --- |
| test–retest r | **+0.808** |
| pairs | 12 |
| mean absolute difference | **0.58★** |

R3 §2 made 0.6 the gate, and this clears it. With n = 12 the interval is wide — roughly 0.6 to 0.94
— but it lands on the right side either way.

**The finding is that the target is not noisy.** The eye reproduces itself to within about half a
star. So ticket 15's +0.255 is not a rubric bumping against a noisy ceiling; it is a **weak rubric
against a reproducible target**, capturing roughly a third of the achievable correlation. Every
correlation on this map — ticket 09's −0.043, round 2's +0.189, ticket 15's +0.255 — should now be
read against +0.81, not against an unknown maximum. R3 §2's "published against an unmeasured
ceiling" caveat is **discharged**.

## 2. The band: FAILED its pre-registered bar

R3 §6 required the band reproduce out-of-fold at **r ≥ +0.20** on grades collected after that
document. R4 §5 named the decision number in advance: the identical 5-fold procedure, refit on E3.

| | |
| --- | --- |
| **decision number** | **r = +0.120** (se 0.071, n = 194) |
| bar | +0.20 |
| verdict | **FAIL** |

Checked for fold-split luck over 25 fold assignments: median **+0.171**, range +0.094 to +0.259,
clearing the bar in **20%** of assignments. The failure is not a seed artefact. mae 1.04,
within-one-star 65%.

## 3. …and §6's remedy is refuted by the same grades

§6 said that on failure orderliness is dropped and its ×2 redistributed. Dropping it makes the
rubric **strictly worse**:

| E3, 25 fold assignments | median r | range | clears +0.20 |
| --- | --- | --- | --- |
| with the band | +0.171 | +0.094 … +0.259 | 20% |
| **orderliness dropped** | **+0.069** | +0.033 … +0.106 | **0%** |

Within-one-star falls 70% → 57%. Every descriptive number says the dimension is carrying signal:

- orderliness **partial r vs the eye, controlling base length: +0.302** — the strongest
  single-dimension number on this map, against cluster k's +0.196.
- **43%** of E3 cards fall inside A3's band, so it discriminates. A3's failure mode — the one that
  forced the band in the first place — was a one-sided cut awarding its point to 99% of cards.
- A3's thresholds applied to E3 **frozen, no refit: r = +0.240**, mae 1.15, bias +0.07. That is the
  stricter out-of-sample test and it clears the bar.

## 4. What actually failed is the fitter, not the band

Refit on E3, every fold runs to the same degenerate corner:

| threshold | folds pick | A3 fitted |
| --- | --- | --- |
| `ord_lo` | 0.1, 0.1, 0.1, 0.1, 0.1 | 0.275 |
| `ord_hi` | 0.6, 0.6, 0.6, 0.6, 0.6 | 0.5 |
| `len_ok` | 4, 20, 4, 4, 4 | 26 |
| `cluster_k` | 5, 7, 5, 5, 7 | 4 |

`ord_lo` 0.1 / `ord_hi` 0.6 are the **widest values on the grid** — very nearly no band at all. The
fitter is not finding a better band; it is abandoning the band, and then scoring worse out of fold
than the band it abandoned. A3's values generalise to E3 at +0.240; nothing E3's own fit finds
comes close.

This is the same complaint [`REFIT_FINDINGS.md`](REFIT_FINDINGS.md) raised about round 2's
optimiser — mae is a level statistic on a flat loss surface — surfacing this time as **instability
rather than a local minimum**. The exhaustive search reaches the true optimum of its objective; the
objective is the problem. **That is the graduated question, and it is not one deck E3 can answer.**

## 5. Pooling, and why the pooled numbers are not the answer

| n = 314 (A3 + E3) | out-of-fold r |
| --- | --- |
| with the band | +0.204 (se 0.054) |
| orderliness dropped | +0.180 (se 0.055) |

Tempting, and not usable: mean grade is **3.23★ on A3 against 2.93★ on E3**, a +0.30★ offset at
t = 2.11, p ≈ 0.035. mae is a level statistic, so that offset lands on every fitted threshold —
which is the exact ground R3 refused to pool round 2 with round 3 on (+0.69★, p = 0.044). The
offset here is smaller but the shape is identical, so the pooled fit is **recorded and not used**.

## 6. Resolution — trader's call, ticket 20

**The band failed, and the remedy was not executed.** Recording the failure honestly costs nothing;
carrying out a repair that these grades show to be damaging would trade a working dimension for
adherence to a rule written before the dimension was measured. So:

- the band is **not credited** — ticket 15's +0.255 stays optimistic, as R3 §6 always said it would
  unless confirmed
- orderliness is **kept**, and A3's thresholds stand as **explicitly provisional**
- **no threshold on this map is final**, and the reason is now named rather than vague: the fitting
  objective does not identify the dimensions the eye is using

## 7. What deck E3 did not settle

Per-market calibration and the rejected candidates. Both decks are rendered and still ungraded, and
both carry 6 repeats each that would tighten the n = 12 ceiling above. They are ticketed
separately rather than carried a fourth time inside someone else's ticket.
