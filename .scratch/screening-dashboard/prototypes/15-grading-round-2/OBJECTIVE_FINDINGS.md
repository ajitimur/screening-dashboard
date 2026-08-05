# Round 6 — the fitting objective. What mae can and cannot recover

Ticket 21. Rules fixed in `PREREGISTRATION_R6.md` before any objective other than `mae` was run.
Nothing was collected: 430 graded cards already existed. Reproduce:

    python objective6.py --selftest      # pins the fast search to score3 and to rubric3.fit
    python objective6.py                 # the pre-registered run -> ROUND6_OUTPUT.txt
    python posthoc_calibration.py        # F6 only, explicitly post hoc

The incumbent pipeline was re-run first and reproduces round 5 exactly (r +0.255, mae 1.11,
identical thresholds), so everything below is measured against a baseline known to be intact.

---

## F1. mae walks away from the band. A rank objective walks straight back to it

The same exhaustive search over the same grid, on the same 194 E3 cards, changing only the loss:

| objective | `cluster_k` | `ord_lo` | `ord_hi` | `dryup` | `len_ok` |
| --- | --- | --- | --- | --- | --- |
| **mae** (incumbent) | 5 | **0.10** | 0.60 | 0.85 | **4** |
| **spearman** | 5 | **0.30** | 0.60 | 0.85 | 20 |
| **cindex** | 5 | **0.30** | 0.60 | 0.85 | 20 |
| *the band the trader adopted (T3)* | *5* | *0.275* | *0.60* | *0.95* | *14* |

`mae` lands in the corner ticket 20 reported — `ord_lo` at the grid's minimum, `len_ok` at its
minimum, which is a band so wide it is nearly no band and a length rule that fails almost every
card. **Both rank objectives independently recover the trader's band**, to within one grid step on
`ord_lo` and exactly on `ord_hi`. On the pooled 366 cards `cindex` returns the same answer again
(0.30 / 0.70 / k 5).

Nothing about the search changed. The optimum of `mae` simply is not where the eye is.

## F2. The instability was the objective's, and it is fixed by changing it

Across 25 fits (5 folds × 5 fold assignments), modal value and share:

| threshold | mae | spearman | cindex |
| --- | --- | --- | --- |
| `cluster_k` | 5 (80%), range 3–7 | 5 (80%), range 5–7 ✔ | 5 (84%), range 5–7 ✔ |
| `ord_lo` | **0.10** (92%), range 0.1–0.3 | **0.30** (96%), range 0.275–0.3 ✔ | **0.30** (88%) ✔ |
| `ord_hi` | 0.60 (92%), range 0.45–0.6 | 0.60 (**100%**) ✔ | 0.60 (**100%**) ✔ |
| `len_ok` | 4 (92%), range 4–24 | 20 (68%), range 4–26 | 20 (60%), range 4–26 |
| `dryup` | 0.85 (64%), range 0.6–1.2 | 0.85 (48%) | 0.85 (52%) |

By R6 §4's rule (modal share ≥ 60% **and** spread ≤ 2 grid steps) the rank objectives make
`cluster_k`, `ord_lo` and `ord_hi` **stable** — `ord_hi` lands on 0.60 in 25 fits out of 25 — while
under `mae` **not one threshold is stable**. Ticket 20's "every fold runs `ord_lo` to 0.1" was not
fold-luck and not a property of the dimension. It is what minimising a level statistic on this
surface does.

**`len_ok` and `dryup` stay unstable under every objective.** Those two are genuinely unfitted at
this sample size, and no objective rescues them.

## F3. The rank objective is nonetheless NOT adopted — it misses the level guardrail by 0.01★

The primary criterion, median out-of-fold ρ over 25 fits, ranks within deck:

| objective | median ρ | ρ range | mae | within 1★ |
| --- | --- | --- | --- | --- |
| mae | +0.215 | +0.130 … +0.284 | **0.98** | 70% |
| spearman | +0.315 | +0.264 … +0.331 | 1.14 | 61% |
| **cindex** | **+0.326** | +0.260 … +0.338 | **1.15** | 61% |

`cindex` beats the incumbent by **+0.111 ρ** — half again as much ranking power, and against a
test–retest ceiling of +0.854 that is a real fraction of the remaining gap. It also **halves the
fold-to-fold spread** (0.078 wide against 0.154).

And it costs **+0.16★ of mean absolute error against a pre-registered tolerance of 0.15★.**

By R6 §2, `mae` stands. The margin of failure is one hundredth of a star, and the rule is not being
relaxed after the fact — ticket 20 is on this map precisely because a rule was once chosen after
seeing grades. But a guardrail missed by 0.01★ is a **finding, not a verdict**: what it says is that
the choice was never really between two objectives. See F5.

*Aside on the baseline:* under 5 fold assignments `mae` scores median ρ +0.215 / Pearson r +0.197 on
E3, where ticket 20's single assignment reported +0.120. Ticket 20's headline number was a draw from
a distribution running +0.130 to +0.284, which is worth remembering before any future number is read
off one split.

## F4. Ticket 20's drop of orderliness must not proceed — it costs more than half the ranking

Re-decided on E3 under the winning objective, keep versus drop with the ×2 redistributed:

| | median ρ | mae |
| --- | --- | --- |
| keep the band | **+0.231** | 0.97 |
| drop it, ×2 redistributed | **+0.088** | 1.03 |

**Dropping orderliness costs +0.143 ρ — 62% of the rubric's out-of-fold ranking power — and makes the
level worse too.** R3 §6's instruction to drop it on a failed +0.20 bar is comprehensively wrong, and
ticket 20 was right to stop short of executing it.

By R6 §6 the band is **real but unfittable**: it clears the keep-versus-drop bar four times over, and
its thresholds are unstable *under `mae`*. Under either rank objective they are stable (F2). So the
verdict is conditional in a way worth stating plainly: **orderliness stays in the rubric, and whether
it gets a fitted threshold depends entirely on the F5 decision.**

For scale, Spearman partial ρ against the eye controlling base length, on the pooled 314:
**orderliness +0.365**, the strongest dimension on this map — ahead of `cluster_k`'s +0.233.

## F5. The real finding: the score is being asked to do two jobs, and one grid cannot do both

`mae` fits the **level** — how many stars to print. `cindex` fits the **order** — which name sits
above which in the only list the app has (ticket 11). These are different objects and on this data
they disagree: the ordering optimum costs 0.16★ of level, the level optimum costs 0.111 ρ of order.

The obvious remedy is two-stage — fit the order, then map score to stars monotonically. **It was
measured, post hoc and labelled as such** (`posthoc_calibration.py`), and it does *not* get both:

| fit | ρ | mae | within 1★ | predicted SD |
| --- | --- | --- | --- | --- |
| mae | +0.215 | 0.98 | 70% | 0.80 |
| mae + isotonic level map | +0.158 | 0.93 | 64% | 0.36 |
| cindex | +0.326 | 1.15 | 61% | 1.24 |
| **cindex + isotonic level map** | **+0.233** | **0.93** | 63% | 0.44 |

Calibrating to the level **collapses the score's spread** (SD 1.24 → 0.44) and the ties that creates
cost ρ 0.326 → 0.233. Isotonic regression cannot reorder anything, so every point lost is a pair the
calibrated score can no longer separate. The two-stage fit is still the best pair of numbers on the
table — it beats the incumbent on *both* axes (+0.018 ρ, −0.05 mae) — but it buys level with
resolution, and that is a trade someone has to authorise.

**So the question this ticket ends on is not a fitting question.** It is: *does the star number have
to be accurate as a level, or is it a label for a rank?* If the app sorts and the stars are a legend
for the sort, the guardrail in F3 should never have been binding and `cindex` wins outright, band
included. If a 4★ has to mean 4★ — because §7 sizing or a trade decision reads the number — the
level matters and the collapse in the table above is the price. That is a trader question, and it
goes to ticket 26.

## F6. Half the retired dimensions were retired by a blind instrument

Spearman partial ρ against the eye, controlling base length, on the pooled 314 (A3 + E3), with the
sign required to agree on both decks separately:

| dimension | pooled | A3 | E3 | R6 §7 verdict |
| --- | --- | --- | --- | --- |
| `cluster_churn` | **+0.313** | +0.236 | +0.334 | **flagged** |
| `density` (k ÷ cluster range) | **+0.286** | +0.228 | +0.298 | **flagged** |
| `narrowing_ratio` | **+0.211** | +0.201 | +0.190 | **flagged** |
| `ma_dist_adr` (D10) | **+0.183** | +0.144 | +0.198 | **flagged** |
| `base_height_adr` | **−0.290** | −0.270 | −0.272 | "correctly retired" — **see below** |
| `sqrt_shortfall` | −0.211 | −0.156 | −0.250 | "correctly retired" — **see below** |
| `narrow_cluster` | −0.148 | −0.169 | −0.155 | correctly retired |
| *`cluster_k` (incumbent)* | *+0.233* | | | *context* |
| *`orderliness` (incumbent)* | *+0.365* | | | *context* |

Two things fall out, and the second is a defect in this round's own pre-registration.

**`ma_dist_adr` was retired on a number produced by the wrong statistic.** F2 of `REFIT_FINDINGS.md`
killed it at Pearson partial r **+0.010, p = 0.93**. On rank residuals it is **+0.183**, consistent
on both decks, and above the +0.15 floor this map pre-registered for `cluster_k`. It is not obviously
a *useful* dimension — it correlates +0.606 with a gate every surviving detection already passes —
but "carries no information" was measured with an instrument this ticket has just shown to be blind.

**R6 §7's rule was written one-sided, and it is wrong.** It flags a dimension only at partial
ρ ≥ +0.15, so `base_height_adr` at **−0.290** — a stronger relationship than `cluster_k`'s, with the
sign agreeing on both decks — is recorded as "correctly retired" when what the number says is *the
eye reliably dislikes tall bases*. A scored dimension does not care about the sign of its
correlation; the sign only sets which way the point is awarded. The rule should have read |ρ| and
did not. Stating it rather than quietly re-running it is the point: `base_height_adr` and
`sqrt_shortfall` go forward as **flagged by the number, against the rule**, and the rule is fixed in
the next round's pre-registration.

Nothing is adopted here — R6 §7 forbids it, and adding a dimension is a fitting decision that has to
wait on F5. Six candidates go to ticket 27.

## F7. No thresholds are published from this round either, and now the reason is precise

Under the objective that survives (`mae`, λ = 0.001 adopted by R6 §5 on a +0.016 ρ gain), the fit on
the adopted pooled population is:

    cluster_k 7 · ord_lo 0.10 · ord_hi 0.70 · dryup 0.90 · len_ok 26     — every one UNSTABLE

`cluster_k` at the grid's maximum, the orderliness band at both grid extremes: the degenerate corner
again, on 366 cards instead of 194. **The objective that passes the guardrail produces no usable
thresholds, and the objective that produces stable thresholds is blocked by the guardrail.** That is
the whole ticket in one sentence, and it is why F5 is a decision rather than a computation.

The incumbent `T3` — which the trader adopted and which F1 shows both rank objectives recover — is
still what the rubric runs on. It was not re-fitted and does not need to be.

## F8. Poolability: the decks pool on a rank criterion, and it buys nothing yet

R6 §3, out-of-fold ρ scored on E3 cards only:

| fitted on | n | ρ on E3 | vs E3-only (+0.215) |
| --- | --- | --- | --- |
| A3 + E3 | 314 | +0.198 | −0.017 → **pool** |
| A3 + E3 + C3 | 366 | +0.217 | +0.002 → **pool** |

Both clear the −0.020 tolerance, so **all 366 graded cards are usable together** — the +0.30★ level
offset between A3 and E3 that `REFIT_FINDINGS.md` F3 called disqualifying is invisible to a rank
criterion, exactly as predicted, and ticket 22's ruling that IDX pools with US survives a rank test
as well as the level test it was made on.

The caveat is that it buys nothing *yet*: every pooled fit under `mae` is degenerate and unstable
(F7). More cards do not fix a blind objective. They become valuable the moment F5 is decided.

## F0. A defect in the incumbent machinery, found by the pin

`rubric3._vector_predictor` — the fast path `rubric3.fit` optimises through — and `score3`, which
produced every published *prediction*, disagree on any card with a missing `prior_move` or
`sector_share`. `score3` treats a NaN as a scored zero and still counts its weight; the fast path
drops it from both. **Every IDX card has neither**, so the two differ on all of them.

Nothing published is affected: every fit on this map to date was run on deck A's US core. But the
next fit that pools IDX — which F8 has just declared legitimate — would have optimised one rubric
and reported another. `objective6.Fast` matches `score3` and asserts it on every population before
any number is computed; the two incumbent functions are left as they are, with the divergence noted
in `rubric3.py`, because changing them would move published numbers.
