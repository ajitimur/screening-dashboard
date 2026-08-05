# Ticket 26 — the line penalty is a silent tiebreak, and the list is three times what the map said

Working for [ticket 26](../../issues/26-the-line-penalty-and-the-longer-list.md). No new grading:
every number here comes from deck F's existing 105 grades, ticket 15's published rubric, ticket 25's
`split.pkl` scan and ticket 18's cached consecutive-bar scan.

| script | what it measures |
| --- | --- |
| `deckF_machine.py` | deck F's three arms scored with ticket 15 R4's rubric — the machine's view of cards only the eye had seen |
| `nightly_mix.py` | the merged nightly list: length, star distribution, and what sits at the top of ticket 11's sort |
| `digest_volume.py` | ticket 18's classifier re-run with the line test as a switch |

Environment: symlink ticket 09's `cache/` into `../09-star-score/cache` and use a pandas 3.x venv
(the cached pickles are `datetime64[s]`-backed). `digest_volume.py` reads ticket 18's `out/daily.pkl`
and finds it in the ticket-18 worktree if it is not local.

---

## 1. The machine does not separate them either

Ticket 25 measured the `line_not_drawable` arm against the eye. Nobody asked what the rubric that
sorts the list says about the same cards.

| arm | n | machine | eye | machine ≥4★ | eye ≥4★ |
| --- | --- | --- | --- | --- | --- |
| accepted detections | 33 | 2.92 | 2.97 | 21% | 39% |
| `line_not_drawable` | 33 | **2.89** | 2.85 | 15% | 33% |
| `not_caught_up` | 33 | 2.74 | 3.00 | 15% | 36% |

Machine Δ = **−0.03★** (95% CI −0.46 to +0.40) against the eye's −0.12★. **Both rulers return the
same null**, which is the fact the remedy has to be built on: the rubric is not quietly demoting
these names already, so whatever demotion they get has to be added deliberately — and the evidence
says it should be small.

Agreement with the eye is the same on both populations (r = +0.180 accepted, **+0.223** marginal,
pooled +0.198, mae 1.06★), so the rubric is not *worse* at reading marginal names. It is equally
weak on both, consistent with ticket 20's finding that it captures about a third of the achievable.

## 2. Where they land in the sort, and the one place they look worse

On 250 sampled nights, scored and sorted as ticket 11's screen would:

| | accepted | marginal |
| --- | --- | --- |
| mean machine star | 3.05 | 2.94 |
| share ≥ 4★ | 24% | **15%** |
| share ≥ 3★ | 64% | 60% |

So they interleave, with a mild thinning at the top: the list grows **+59%** but rows at ≥4★ grow
only **+38%** (1.43 → 1.97 a night, sample-scale). Marginal names take **35% of the top 3** and 37%
of the top 10, against a 37% share of the list — proportional, not concentrated.

**The one adverse signal is precision at the trade line.** On deck F, of cards the machine calls
≥4★, the share the eye also calls ≥4★ is **0.71 on detections alone and 0.58 once the marginal names
are merged in** (0.40 on the marginal arm by itself). Only 12 cards are called at all, so this is a
hint and cannot move a threshold — but it is the only measurement pointing at a real cost, and it
points at the exact row ticket 11 says gets read.

## 3. The sub-tests, in both rulers

| failure | n | machine | Δ | eye | Δ |
| --- | --- | --- | --- | --- | --- |
| touches only | 16 | 3.19 | +0.26 | 3.00 | +0.03 |
| overshoot only | 8 | 2.50 | **−0.42** | 2.12 | **−0.84** |
| both | 9 | 2.72 | −0.20 | **3.22** | **+0.25** |

The overshoot lead survives contact with the second ruler — both agree it is the only sub-test doing
work — but **the `both` group is what kills it as a shape**: it grades *above* detections by eye
(56% at ≥4★), and any rule keyed on overshoot demotes it hardest. A shape that gets its best-graded
group backwards is not a shape, at n=8 and n=9.

## 4. The digest: +37%, not +59%, because these names break less

Ticket 18's classifier, re-run with detection as `tight & caught_up` with and without `& line_ok`:

| | detections | digest rows/night (ungated) | break rate per detection-night |
| --- | --- | --- | --- |
| US, line_ok gates | 22,375 | 0.92 | **4.90%** |
| US, line_ok demoted | 45,980 | 1.92 | marginal names **3.04%** |
| IDX, line_ok gates | 6,867 | 0.22 | 3.66% |
| IDX, line_ok demoted | 13,261 | 0.47 | marginal names 2.28% |

**Marginal names break through their trigger at 0.62× the accepted rate**, so the digest grows by
less than the list: applying the gated +59% growth and the measured relative rate, ticket 18's
**7.0 → ~9.6 US rows a night**, and 0.9 → ~1.2 on IDX.

The rate gap is not the level sitting further away (distance to trigger 0.69 vs 0.65 ADR) and it is
not base length — it holds inside every length bucket, most extremely at L ≤ 10, where marginal
names break **0.74%** of detection-nights against **4.88%** for accepted ones:

| base length | marginal break rate | accepted break rate |
| --- | --- | --- |
| ≤ 10 | 0.74% (n=5,979) | 4.88% (n=7,151) |
| 11–15 | 3.08% | 5.38% |
| 16–20 | 4.41% | 5.01% |
| 21–30 | 3.68% | 4.81% |
| 31–45 | 3.92% | 4.32% |

This is the first non-eye evidence about this population on the map. It is **not** priced into the
score: a lower break rate is not a worse setup — there is no return attached to it, and these bases
may simply take longer. Recorded as a validation question, which is ticket 24's rule (do not judge a
rule with the wrong ruler) applied to a finding rather than to a rule.

## 5. The list is ~3× what the map has been saying

`split.pkl` covers **628 US symbols** — `universe.py` draws a random sample of Nasdaq common stock
plus a 39-name momentum core — against ticket 05's measured **1,966-name** universe. Ticket 25's
`lnd_cost.py` scales ×3 for the 1-in-3 date grid and **not** for the universe; ticket 18's
`crossings.py` scales for the universe explicitly (`scale = 1966 / names`). **The two numbers ticket
26 puts side by side are on different bases.**

| | as specified | with the demotion |
| --- | --- | --- |
| list, sample-scale (ticket 25's figures) | 5.98 | 9.52 |
| **list, universe-scale (×3.13)** | **18.7** | **29.8** |
| digest (already universe-scale) | 7.0 | ~9.6 |

`nightly_mix.py` reproduces ticket 25's 5.98 → 9.52 exactly before rescaling, so this is a scaling
error and not a disagreement about the population.

**The +59% ratio is unaffected** — it is a ratio inside one pool, and deck F priced it correctly.
What was wrong is the level, which is the number ticket 26's second half was framed around.

Two caveats. The scan pool is not ticket 05's liquidity-gated universe, so the rescale transfers a
per-name detection rate across populations of different composition — it is the map's own
convention, not a measurement. And ticket 19 reports 39.7 gated names/night using ticket 06's
**five-window union** gate; on ticket 08's D15 (top decile in any of 1m/3m/6m), which is what the
detector specifies, it is the 18.7 above. Neither level has ever been measured on the real universe.
