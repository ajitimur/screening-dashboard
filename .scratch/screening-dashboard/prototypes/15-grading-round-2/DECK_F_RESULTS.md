# Deck F — `line_not_drawable` does not separate, and stops being a gate

105 blind grades, collected for [ticket 25](../../issues/25-the-line-not-drawable-path.md). Bare
cards, three arms drawn from one gated population differing in exactly one bit, plus 6 repeats.
Rules fixed in advance by [`PREREGISTRATION_DECK_F.md`](PREREGISTRATION_DECK_F.md), committed
before a card was rendered.

Grades: `342443144532212342111434311434253524334334252443334444223325421431224312222223244354422234245233422234221`

Reproduce with `analyse_deckF.py F=<the string above>`.

---

## 1. The headline: the path is indistinguishable from what the screen surfaces

| arm | n | 1★→5★ | mean | ≥4★ |
| --- | --- | --- | --- | --- |
| accepted detections | 33 | 4, 9, 7, 10, 3 | **2.97** | 39% |
| `line_not_drawable` | 33 | 4, 12, 6, 7, 4 | **2.85** | 33% |
| `not_caught_up` | 33 | 2, 8, 11, 12, 0 | **3.00** | 36% |
| repeats (A3 re-shown) | 6 | 1, 3, 1, 1, 0 | 2.33 | 17% |

**Primary: Δ = −0.12★** (se 0.30, 95% CI **−0.73 to +0.48**, p = 0.691). Controlling base length,
−0.18★ (CI −0.76 to +0.39).

By §5 this is row 2: the interval spans zero and |Δ| = 0.12★ sits **inside the eye's own 0.46★
noise floor**. The path does not separate from the names the screen already shows. Per the
pre-registration this is **a finding, not a pass** — a rejection rule that cannot be told apart
from acceptance is not earning a gate.

**The deck rules out any true gap worse than −0.72★.** Ticket 23's −0.40★ sits inside that
interval, so nothing here contradicts it — but the point estimate moved from −0.40★ to −0.12★
once its two confounds were removed, which is the direction §1 of the pre-registration predicted
before the deck was built.

That prediction is separately confirmed by the control arm. Deck D3 band-stratified its detections
and got **3.20**; deck F drew the same population at random and got **2.97**. The stratification
was lifting the control arm, exactly as suspected.

## 2. The remedy, and why it is nearly free

**Trader's call: `line_ok` is downgraded from a hard reject to a scored penalty** — §6 option 1,
the pre-registered default for this outcome. The two alternatives were put and not taken: loosening
only the touches sub-test (§3 below points there, but at n=16 vs n=8 it is descriptive), and
refusing the remedy outright as the trader did on ticket 20's band.

The cost is priced and accepted: the decile-gated US list goes **5.98 → 9.5 names a night (+59%)**.

What makes it cheap is that **`line_ok` gates nothing geometric.** Ticket 18 established that the
fitted line can never exceed the cluster high, so the trigger *is* the cluster high by identity and
the line never reaches it. `line_ok` therefore feeds one boolean and one chart overlay. Demoting it
changes **no trigger, no stop, no cluster, and no parameter** — it changes which rows appear and
where they sort. That is the smallest blast radius any remedy on this map has had.

It also puts `line_ok` where `D6` already went. Ticket 16 took the stop-width test out of the gate
set on an argument about form; ticket 19 confirmed it; this takes the line test out on a measured
null. The detector's gate set is shrinking toward the two tests that do separate — the cluster
(`no_cluster`, −1.40★ at n=10 in deck D3) and the decile.

## 3. Which sub-test the failures come from

| failure | n | mean | Δ vs detections | ≥4★ |
| --- | --- | --- | --- | --- |
| touches only | 16 | 3.00 | **+0.03★** | 31% |
| overshoot only | 8 | 2.12 | **−0.84★** | 12% |
| both | 9 | 3.22 | **+0.25★** | 56% |
| `MAX_OVERSHOOT_FRAC` only | 0 | — | — | — |

The overshoot test is the only part that looks like it is doing work, and the touches test is
where the null comes from — cards failing touches grade level with detections, and the 9 cards
failing **both** grade *above* them, 56% at ≥4★.

**Descriptive only.** n=8 and n=9 cannot carry a remedy and the pre-registration said so in
advance (§8). It is recorded because it is the sharpest available lead if the penalty in §2 ever
needs to become a shape rather than a flat demotion, and because it inverts the ungated
expectation: D15's decile gate shifts this path's failures from 50% overshoot toward 48% touches,
so the sub-test that survives is the one the gate makes rarest.

## 4. The secondary arm: the catch-up test does not separate either

`not_caught_up` grades **+0.03★** against detections (CI −0.50 to +0.56, p = 0.910) — and unlike
deck D3's ten-card arms this is a **full 33-card arm**, as well powered as the primary. Two of the
detector's three rejection paths now fail to separate from acceptance.

**No remedy fires and none was pre-committed** (§2 fixed it as secondary: two comparisons share one
control arm). Two reasons to leave it there rather than extend §2's logic to it:

1. **It is worth 0.95 names a night**, 0.16× the list. Even a wholly wrong gate is a small miss.
2. **It may not be a quality rule at all.** Catch-up is about where you *enter* — §3.1 wants price
   back at the 10/20 so the stop is close — not about whether the base is good. A null on *"is this
   a setup you want to see"* is the wrong question for an entry-timing rule. This is ticket 19 and
   ticket 24's pattern for the third time: **a risk rule measured with a quality ruler.** Ticket 24
   named it for the stop; it applies here unchanged.

That second point is why this is parked as fog rather than ticketed. It needs a different question,
not more cards.

## 5. Two ride-alongs that outlive the ticket

**The base-length penalty reproduces, and ticket 17's correction of it was wrong.** Across deck F
the eye's grade falls with base length at **r = −0.373, p = 0.0001** (n=99, arm-demeaned so it is a
within-arm effect, not arm composition), and the sign is consistent in all three arms
(−0.269 / −0.429 / −0.425). Ticket 09 found −0.558 and made length a penalty; ticket 17 reported
it "did not reproduce" (+0.029 on fresh grades) and attributed 09's number to deck A's population.
**On a fourth, freshly drawn population it reproduces.** Ticket 15's rubric already carries a
length term, so nothing needs refitting — but the term is earning its place rather than being
inherited, and ticket 17's dismissal of the effect should not be relied on again.

**Cluster length k replicates a fourth time**: +0.329 within-arm, p = 0.001. Ticket 15's ×2
tightness dimension is the one signal on this map that has never failed to reproduce.

## 6. The ceiling: 24 pairs → 30

| | pairs | test–retest r | mean abs. difference |
| --- | --- | --- | --- |
| ticket 20 | 12 | +0.808 | 0.58★ |
| tickets 22 / 23 (disjoint 18s) | 18 | +0.854 / +0.831 | 0.44★ / 0.56★ |
| pooled, computed this ticket | 24 | **+0.855** | **0.46★** |
| **with deck F's 6** | **30** | **+0.846** | **0.47★** |

The pooled figure was owed by the map and needed no new grading — every grade already existed.
Deck F's own 6 pairs read +0.773 / 0.50★, and pooling to 30 leaves the number where it has sat
since 12 pairs. **The eye is reproducible to within about half a star**, and every correlation on
this map is read against ~+0.85.

## 7. What this deck does not settle

- **`no_cluster` is untouched** — 54.4% of the pool, 2.10× the list, and the one path deck D3
  separated at n=10. Not sampled here, and not in question.
- **The names the detector never sees.** Every arm was drawn from what the split *considered*.
- **What the penalty in §2 actually looks like** — a rubric dimension, a sort demotion, or a shape
  keyed on §3's sub-tests — and whether ticket 11's scan-not-a-queue list survives at 9.5 names a
  night. That is [ticket 26](../../issues/26-the-line-penalty-and-the-longer-list.md).
- **Whether the eye is right.** The ceiling says it is reproducible, not that it predicts returns.
