# Deck D3 — what the detector threw away

46 blind grades, collected for [ticket 23](../../issues/23-the-rejected-candidates.md). The deck was
bare: 20 split rejects, 20 accepted detections and 6 deck-A3 repeats, with nothing on a card saying
which was which, and the question deliberately the different one — *is there a setup here you would
want to see tonight?*

Grades: `1133414223141431314114544211434353443242225523`

Run with `analyse3.py A=<grades3_A.txt> E=<grades3_E.txt> D=<the string above>`.

---

## 1. The headline: the detector is keeping the better names

| arm | n | grade distribution 1★→5★ | mean | ≥4★ |
| --- | --- | --- | --- | --- |
| accepted detections | 20 | 2, 3, 6, 7, 2 | **3.20** | 45% |
| reject: `no_cluster` | 10 | 7, 1, 0, 1, 1 | **1.80** | 20% |
| reject: `line_not_drawable` | 10 | 1, 3, 3, 3, 0 | **2.80** | 30% |
| repeats (A3 re-shown) | 6 | 1, 1, 1, 2, 1 | 3.17 | 50% |

**Pooled rejects minus detections: −0.90★** (se 0.40, 95% CI −1.67 to −0.13).

The interval excludes zero, so the **direction is real**: the names the split throws away grade
*worse* than the ones it surfaces. The obligation carried since ticket 11 — passed to 09, to 15, to
20, discharged by none of them — is **discharged here, in the detector's favour**. The star score is
not calibrated on the wrong population.

By `PREREGISTRATION_R3.md` §2 this deck was sized to resolve a 1.00★ gap at 20/arm; 0.75★ needs
33/arm. −0.90★ sits between the two, so **the size is provisional and only the sign is established.**

## 2. …but one of the two rejection paths carries the whole result

Split by path, against the same 20 detections:

| path | Δ vs detections | se | 95% CI |
| --- | --- | --- | --- |
| `no_cluster` | **−1.40★** | 0.53 | −2.44 to −0.36 |
| `line_not_drawable` | **−0.40★** | 0.42 | −1.22 to **+0.42** |

`no_cluster` is doing real work — **7 of its 10 cards graded 1★**, and its interval excludes zero
even at n=10. It rejects things the eye also rejects.

`line_not_drawable` does not separate. Its interval spans zero, its −0.40★ is **below the eye's own
noise floor** (§3: mean absolute difference between repeat gradings is 0.56★), and **3 of its 10
cards graded 4★** — CLMT 2017-09-20, BELFB 2019-09-18, GGT 2020-07-23. Against a detection arm that
itself only reaches 3.20 with 9 of 20 at ≥4★, this path is close to indistinguishable from what the
screen surfaces.

So the pooled answer is honest but coarse. **The detector as a whole keeps better names; that is
almost entirely `no_cluster`.** Whether `line_not_drawable` discards setups the trader wants is
*not* answered here, and n=10 could never have answered it — resolving 0.75★ on that path alone
needs 33/arm. Carried to [ticket 24](../../issues/24-the-line-not-drawable-path.md).

The third path, `not_caught_up`, is 1.6% of bar-dates and was deliberately not sampled. It remains
unmeasured.

## 3. The ceiling: 12 pairs → 18, and it holds

Deck D's 6 repeats join deck E's 12.

| | pairs | test–retest r | mean abs. difference |
| --- | --- | --- | --- |
| ticket 20 | 12 | +0.808 | 0.58★ |
| **now** | **18** | **+0.831** | **0.56★** |

The number every correlation on this map is read against **survives the extra data and tightens**.
Ticket 20's reading stands unchanged: the eye is reproducible to within about half a star, so
"the grader is just noisy" remains unavailable as an explanation for anything. Deck C3's 6 repeats
would take it to 24 ([ticket 22](../../issues/22-idx-per-market-calibration.md)).

## 4. Nothing else moved

Deck D carries no deck-A or deck-E cards, so sections 1–4 and 8 are unchanged by these grades:
tightness still clears its gate at partial r +0.196, boolean still beats continuous (+0.255 vs
+0.191), the 4★ cut still stands, and **the orderliness band still fails its pre-registered bar**
(out-of-fold r +0.120 on deck E against the +0.20 required). Section 5 remains unanswered — zero
IDX cards graded.

## 5. What this result is, and is not

It is a **direction with a provisional size**, on a bare deck, against the split as ticket 17 left
it — not against ticket 08's detector, which is why the question survived three hand-offs without
going stale.

It is **not** a claim that the split's rejections are correct in general. It measures two of three
rejection paths, one of which is unresolved, at a power that could only ever have caught a large
effect. And it says nothing about the names the split never sees at all: the deck sampled from
what the detector considered and rejected, not from the universe it never looked at.
