# Ticket 19 — fitting the split's 22 parameters

Short version: **none of them gets fitted, and that is the finding rather than a failure.** Only
five can move anything at all; three of the twenty-two are provably redundant and were deleted; and
the one that moves most — `TIGHT_MULT` — turned out not to be a detection parameter at all. It is
the **stop budget**, and once that was measured the question stopped being "what value fits" and
became "does the screen enforce §7", which is a trader's call and was taken as one.

All numbers below are US unless marked, on a fixed 400-name sample (seed 19), 1-in-3 date grid,
172,991 bar-dates, 19,527 accepted detections at the defaults. IDX is the full 288-name universe.

---

## 1. The bill is not 22 live numbers. It is five.

| verdict | numbers | evidence |
| --- | --- | --- |
| **dead** | `MA_PROX_ADR` | 0 references in any function body |
| **not two numbers** | `OVER_W`, `UNDER_W` | only their *ratio* binds — measured identical lists |
| **discretisation** | `SLOPE_STEPS` | 25 → 800 steps moves the list ±0.1% |
| **redundant** | `MAX_OVERSHOOT_FRAC` | catches 4.4% the ADR test misses (r = +0.32) |
| **redundant** | prior-move floor 25% | the decile gate already cuts 89.4% of what it passes |
| **near-inert** | `K_MAX` | 7 → 9 moves the list −1.7% |
| **live** | `TIGHT_MULT`, `K_MIN`, `MAX_BASE_LEN`, `MAX_OVERSHOOT_ADR`, the touch group | below |

`OVER_W`/`UNDER_W` is the cleanest of these: the fit loss is `OVER_W·max(r,0) + UNDER_W·max(-r,0)`,
which is scale-invariant, so `(3.0, 1.0)` and `(6.0, 2.0)` produce **byte-identical** lists, as do
`(6.0, 1.0)` and `(3.0, 0.5)`. Two numbers, one degree of freedom.

**Ticket 18's trigger identity replicates** on a fresh sample: the fitted line set the trigger in
**0 of 19,527** detections (0.0%). `OVER_W`/`UNDER_W`, `SLOPE_STEPS` and `MAX_SLOPE_ADR` therefore
price as *existence-and-drawing* parameters only, exactly as ticket 18 said. `MAX_SLOPE_ADR` is
additionally near its saturation point: 0.5 → 1.0 moves the list +1.1%, so the slope cap almost
never binds upward.

## 2. Line validity is one decision and a spare, not six numbers

`line_ok` passes 53.1% of the 53,922 candidates that reach it — this is what ticket 17's 58.8% drop
of ticket 08's picks is made of. Instrumented so each clause reports separately (the duplicated fit
reproduces `split.py`'s own `line_ok` at **100.0000%** agreement, so these are exact):

| clause | passes | `line_ok` if dropped |
| --- | --- | --- |
| `over_max ≤ 1.0 ADR` | 68.9% | 73.3% (**+20.2pp**) |
| `over_frac ≤ 20%` | 86.1% | 56.2% (+3.1pp) |
| `zones ≥ 2` | 44.7% | 64.5% |
| `zones ≥ 1 & reaches 60% back` | 84.3% | 64.5% |

The two touch clauses are an **OR**, so neither binds alone — dropping *either* gives the same
64.5%, and dropping both costs +11.4pp. `MIN_TOUCHES = 2` therefore decides nothing by itself, and
the four numbers behind the touch test (`TOUCH_TOL_ADR`, `MIN_TOUCHES`, `MIN_TOUCH_GAP`, the 0.6
reach-back) are **one decision expressed four ways**.

`MAX_OVERSHOOT_ADR` is the number that does the cutting. Everything else in this group is a rounding
error on it.

## 3. `TIGHT_MULT` is the stop budget, not a detection parameter

The cluster spans ≤ `TIGHT_MULT` × ADR and the stop runs trigger → cluster low, so `TIGHT_MULT`
*is* the worst-case stop in ADR units. §7 of the method reference caps stop width at **1 × ADR** and
calls anything wider a no-trade. Ticket 08 gated exactly this quantity (D6, rejecting 30–69%);
ticket 17 deleted the gate on the argument that the cluster bounds the stop "as a side effect rather
than as a gate". That argument is about form. This is the substance:

| `TIGHT_MULT` | /night (sample) | gated, full universe | k mean | k=3 | stop median | **within §7** |
| --- | --- | --- | --- | --- | --- | --- |
| 1.000 | 13.5 | 23.1 | 3.70 | 59% | 0.88 | **100%** |
| 1.125 | 19.8 | 26.1 | 3.84 | 53% | 0.98 | 57% |
| 1.250 | 26.4 | 30.7 | 4.02 | 47% | 1.08 | 28% |
| **1.500** | **39.9** | **39.7** | **4.41** | **37%** | **1.28** | **8%** |
| 1.750 | 49.9 | 46.4 | 4.87 | 26% | 1.47 | 3% |
| 2.500 | 63.0 | 54.9 | 6.07 | 9% | 1.94 | 1% |

**At the inherited default, 92% of the nightly list carries a cluster-low stop that §7 calls a
no-trade.** Nobody had measured this: ticket 17 recorded the *bound* (≤1.5, max measured 1.499) but
never the distribution against the cap.

"Gated" is after ticket 06's union-of-deciles precondition and scaled to the full 1,966-name US
universe — the number the trader actually sees. Worth noting on its own: ticket 17's 63% swing was
measured on the **ungated** list, and the gate is by far the stronger filter (it cuts 89.4% of
floor-passing detections; the floor cuts 7.7% of gate-passing ones, Jaccard 10.5%).

### The eye wants the opposite

On ticket 15's 164 graded cards, the eye grades **looser** clusters *higher*, monotonically:

| cluster range (ADR) | mean eye | n |
| --- | --- | --- |
| (0.75, 1.0] | 2.54 | 13 |
| (1.0, 1.25] | 2.75 | 60 |
| (1.25, 1.5] | 2.94 | 90 |

r = +0.140; tight (≤1.0) 2.50 vs loose 2.87, p = 0.286 by permutation. Not significant, and every
card was selected under `TIGHT_MULT = 1.5` so this can only speak about *tightening* — but the sign
is the finding, and it does not support tightening. **`TIGHT_MULT` cannot be fitted against the eye
in the direction §7 pulls.**

### What enforcing §7 would have cost

A restored 1×ADR gate at `TIGHT_MULT = 1.5` leaves the rubric's k dimension nearly intact
(4.41 → 4.23, against 3.70 if `TIGHT_MULT` were re-tightened to 1.0 instead) — but it is not a
neutral filter:

- **8.5% of detections survive** (39.7 → 16.9 names/night gated, US).
- Survivors are **more volatile and bigger movers**: mean ADR 6% → 10%, mean prior move 104% → 177%.
  Mechanical — the stop is measured in ADR units, so a high-ADR name passes with a wider absolute
  cluster.
- **Only 25 of ticket 15's 164 graded cards survive (15%), and the removed cards graded higher**
  (eye 2.91 removed vs 2.44 kept).

So the eye and the stop rule disagree, consistently and in the same direction throughout: looser
cluster → wider stop → higher eye grade → §7 rejects it.

## 4. Per-market: the ADR normalisation transfers

IDX tracks US almost exactly across the grid, which is the case for one set of numbers rather than
two:

| `TIGHT_MULT` | k mean US / IDX | stop median US / IDX | within §7 US / IDX |
| --- | --- | --- | --- |
| 1.00 | 3.70 / 3.66 | 0.88 / 0.88 | 100% / 100% |
| 1.50 | 4.41 / 4.51 | 1.28 / 1.28 | 8% / 8% |
| 2.00 | 5.32 / 5.44 | 1.65 / 1.65 | 2% / 2% |

ADR distributions are comparable (US median 4.49%, IDX 3.97%), and **ticket 09's D13 hole stays
closed under the split**: 98.5% of accepted IDX clusters contain zero collapsed (zero-range) bars,
against the 98.1% ticket 15 measured on the old detector. The cluster is *selected* for tightness,
which is exactly where a limit-day bar would hide, so this was worth re-checking — it did not get
worse.

## 5. The k range

`K_MIN` is the live half; `K_MAX` is nearly inert.

| K_MIN–K_MAX | /night | vs 3–7 | k mean |
| --- | --- | --- | --- |
| 2–7 | 57.9 | +49.1% | 3.62 |
| **3–7** | **39.9** | — | **4.41** |
| 3–9 | 39.4 | −1.7% | 4.50 |
| 4–7 | 26.5 | −36.6% | 5.23 |

k is doing three jobs at once — detection, the digest's effective breakout lookback (ticket 18 R3),
and ticket 15's tightness dimension — so this grid moves the sort and the digest, not just the list.
Nothing here argues for moving it off 3–7, and three consumers is a strong argument for leaving a
non-binding number alone.

---

## Files

| file | what it does |
| --- | --- |
| `harness.py` | fixed sample, cached re-scans under parameter overrides, the decile gate |
| `bill.py` | the audit — dead, discretisation, drawing-only, redundant |
| `lines.py` | instrumented line-validity test; per-clause attribution (verified 100% vs `split.py`) |
| `tight.py` | the `TIGHT_MULT` grid, the §7 columns, the eye-vs-looseness check, the k range |
| `market.py` | IDX: collapsed bars, the sweep, ADR comparability |
| `shift.py` | what a §7 gate does to the population ticket 15 fitted on |

Run order: `bill.py` → `lines.py` → `tight.py` → `market.py` → `shift.py`. Needs `pandas numpy` and
ticket 09's bar cache (`cache/` is a symlink to it). Scans are cached in `out/scans/` keyed by the
override set.
