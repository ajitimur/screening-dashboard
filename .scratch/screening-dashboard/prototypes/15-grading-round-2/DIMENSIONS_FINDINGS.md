# Round 7 — the retired dimensions

Ticket [28](../../issues/28-the-retired-dimensions.md), run under
[`PREREGISTRATION_R7.md`](PREREGISTRATION_R7.md), which was committed before `dimensions28.py` was
run. Raw output: [`ROUND7_OUTPUT.txt`](ROUND7_OUTPUT.txt) ·
[`RIDEALONGS_28.txt`](RIDEALONGS_28.txt) · `r7_result.json`.

**Verdict: nothing clears. All six dimensions stay retired.** Not one candidate bought a tenth of
its bar, and every candidate threshold was unstable across the 25 fits.

---

## F1 — The screen's ρ is not the currency the rubric spends

This is the finding that outlives the ticket, and it dissolves the ticket's own premise.

Ticket 28 opened on a table showing four retired dimensions beating the incumbent `cluster_k` on
partial rank correlation, `cluster_churn` hardest at **+0.313 against +0.233**. On the enlarged pool
the gap is wider still — **+0.337 against +0.261**. Swapping `cluster_churn` into the ×2 tightness
seat and refitting buys:

| | out-of-fold ρ | mae | within 1★ |
| --- | --- | --- | --- |
| baseline (incumbent rubric) | **+0.292** | 1.16 | 59% |
| swap `cluster_churn` → tightness | **+0.293** | 1.13 | 61% |
| add `cluster_churn` at ×1 | +0.293 | 1.17 | 47% |

**+0.001.** A +0.076 advantage in partial ρ converts to one thousandth of out-of-fold ranking power,
against a bar of +0.030.

The reason is structural, and it applies to every screen of this kind the map has run. **The rubric
does not consume the dimension; it consumes a threshold on the dimension.** A boolean cut placed at
the right quantile extracts nearly the same information from any monotone re-expression of the same
underlying quantity — and `cluster_churn`, `density` and `cluster_k` are monotone re-expressions of
each other (Spearman +0.83 to +0.92). Partial ρ measures how well a dimension orders cards
*continuously*; the rubric only ever asks one binary question of it. The two are not the same
currency, and R6 §7's flagging rule was denominated in the wrong one.

So ticket 28's premise — "`mae` was blind, therefore its verdicts are suspect" — is half right.
`mae` **was** blind, exactly as ticket 21 proved. But the screen built to correct for that blindness
is measuring a quantity the fit cannot cash, so its flags were never evidence of a missing
dimension. Both instruments were wrong, in different directions, and they cancel: the dimensions
`mae` retired are the dimensions a working objective also declines.

## F2 — The six candidates are two families, and the families are the incumbents

Established from the candidates' mutual correlation alone, before any fit and without reference to
the eye (R7 §2, so it cannot be a way of dredging an outcome):

| family | members | correlation with the incumbent it shadows |
| --- | --- | --- |
| **packing** | `cluster_k` (incumbent), `cluster_churn`, `density` | +0.829, +0.916 |
| **shape** | `orderliness` (incumbent), `narrowing_ratio`, `base_height_adr`, `ma_dist_adr`, `sqrt_shortfall` | +0.921, −0.952, +0.831, −0.511 |

Every member of the shape family also runs |ρ| **0.27–0.82 with `base_len`**.

The diagnostic column makes the point sharper than the fit does. Controlling `base_len` *and both
incumbents*, rather than base length alone:

| candidate | ctrl `base_len` | + incumbents |
| --- | --- | --- |
| `cluster_churn` | +0.337 | **+0.178** |
| `density` | +0.291 | **+0.114** |
| `base_height_adr` | −0.235 | **+0.119** — *sign flips* |
| `narrowing_ratio` | +0.183 | **−0.168** — *sign flips* |
| `sqrt_shortfall` | −0.182 | **+0.014** |
| `ma_dist_adr` | +0.136 | −0.076 |

Two candidates **reverse sign** once the incumbents are held. `base_height_adr` — screened in on the
perfectly sensible reading that *the eye dislikes tall bases* — says the opposite once you know the
base's orderliness and cluster packing: among cards alike on those, taller is mildly better. A
dimension whose sign depends on what else is in the rubric is not a dimension the rubric is missing.

## F3 — The |ρ| fix was correct, and it changed nothing

Ticket 28 §2 was right that R6 §7's one-sided rule was a bug: `base_height_adr` at −0.290 was
recorded as "correctly retired" purely for having the wrong sign, which a scored dimension does not
care about. Reading |ρ| admits it, and `sqrt_shortfall` with it.

Both then lose on the merits. `base_height_adr` swapped into the orderliness seat scores **−0.031 ρ
against the baseline** — actively worse — and added at ×1, −0.007. The band that ticket 20 fought
for and ticket 21 recovered is not replaceable by a single cut on the base's height, which is the
same result ticket 15 found when it discovered orderliness needed a band rather than a one-sided
cut, arriving from the other side.

So the rule was wrong and the verdict was right. Worth recording precisely because the opposite is
the more common shape: this is a bug fix that vindicated the buggy conclusion.

## F4 — `ma_dist_adr` fails the floor on the enlarged pool

+0.136 against R6 §7's +0.15, having passed at +0.183 on A3+E3. It is screened out by the ticket's
own rule applied to the pool ticket 27 mandated — no new rule. Ticket 28 had already named it
"simultaneously the cleanest indictment of the old instrument and the weakest candidate"; the
enlarged pool retires it without a fit. D10's retirement in ticket 15 stands, now for a second
reason.

## F5 — Every candidate threshold is unstable, so the bar was never the binding constraint

`cluster_churn`'s fitted cut takes its modal value in 72–76% of the 25 fits but spans **3 grid
steps**, failing R6 §4's ≤2. `base_height_adr` is worse (44% modal share, 3 steps as a swap; 5 steps
as an addition). Adding either also **destabilises thresholds that are stable without it** — `ord_lo`
falls from 64% modal share to 48%, and in the addition arm `cluster_k` falls from 88% to 60%.

That last effect is the practical argument against all of this. A candidate that buys +0.001 of
ranking power costs the stability of two thresholds that were stable, which is the exact pathology
[ticket 21](../../issues/21-the-fitting-objective-does-not-identify-the-dimensions.md) diagnosed and
[ticket 20](../../issues/20-confirm-the-band-and-measure-the-ceiling.md) published by accident.

## F6 — Ticket 27's published three reproduce on 432 cards, and are stable

The first independent check of ticket 27's thresholds, on a pool 18% larger and containing 66 cards
no fit had ever seen:

| threshold | published (27) | modal on 432 | modal share | spread |
| --- | --- | --- | --- | --- |
| `cluster_k` | 5 | **5** | 88% | 2 steps |
| `ord_lo` | 0.30 | **0.30** | 64% | 1 step |
| `ord_hi` | 0.60 | **0.60** | 100% | 0 steps |

All three land where ticket 27 put them, all three stable. The rubric's out-of-fold ρ on the full
432 is **+0.292**, against a test–retest ceiling of +0.846 — so it still captures about a third of
what is achievable, which is ticket 20's shortfall unmoved.

**`ord_hi`'s 100% remains partly an artefact, as ticket 27 warned.** Deck F barely fills the empty
region: cards with orderliness in (0.60, 0.70] go from **1 of 366 to 5 of 432**, with 2 above 0.70.
The threshold is still far less *tested* than its modal share suggests, and adding deck F did not
fix that.

## F7 — Ride-alongs

**The 4★ line, out-of-fold on 432**: precision **0.53**, recall 0.28, calling 79 of 432. Precision
is up from ticket 27's 0.49 on E3 and matches ticket 15 R5's 0.53 — the number ticket 11's screen
depends on, now measured on the largest pool the map has and with the marginal names included.

**The rubric still runs cold**, and more so on the bigger pool: it prints ≥4★ on **18.3%** where the
eye grades **35.2%**. Ticket 27 carried this as harmless-while-nothing-gates-on-the-cut and parked
it as fog; it stays parked, but it is now measured at nearly a 2× shortfall rather than 27's
25.3%-vs-32.0%.

**Including deck F in the fit did not distort it, and the two rulers converged.** On F3 the machine
now grades `line_not_drawable` **−0.14★** below detections against the eye's −0.12★ — closer
agreement than ticket 26's −0.03★ vs −0.12★, measured before those cards were ever fitted on. And
the rubric ranks the marginal arm **no worse than the accepted one** (ρ +0.336 against +0.300). That
is independent support for ticket 26's silent tiebreak: these names are rankable by the same rubric,
which is what putting them on the list without a score penalty assumes.
