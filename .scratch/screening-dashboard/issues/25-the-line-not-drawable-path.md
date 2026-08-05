# Does the `line_not_drawable` rejection path discard setups you want?

Type: prototype
Status: claimed
Blocked by: —

## Question

[Ticket 23](23-the-rejected-candidates.md) answered the pooled question — the split's rejects grade
−0.90★ below its detections, so the detector is keeping the better names and the star score is
calibrated on the right population. **That answer is carried almost entirely by one of the two
sampled rejection paths.**

| path | n | mean eye | Δ vs detections (3.20) | 95% CI |
| --- | --- | --- | --- | --- |
| `no_cluster` | 10 | 1.80 | −1.40★ | −2.44 to −0.36 |
| `line_not_drawable` | 10 | 2.80 | −0.40★ | −1.22 to **+0.42** |

`no_cluster` separates even at n=10. `line_not_drawable` does not: the interval spans zero, −0.40★
is **below the eye's own 0.56★ noise floor**, and **3 of its 10 cards graded 4★** — CLMT 2017-09-20,
BELFB 2019-09-18, GGT 2020-07-23 — against a detection arm that itself only reaches 3.20 with 9 of
20 at ≥4★.

So this is not a null to be read as a pass. It is the one place ticket 23's answer does not reach,
and it is a live possibility that a whole rejection path is discarding tradeable setups.

**What it takes.** `PREREGISTRATION_R3.md` §2: a two-group mean-grade difference of 0.75★ needs
**33/arm** at 80% power. Ticket 23's deck had 10. A deck of 33 `line_not_drawable` rejects against
33 accepted detections, bare and mixed in the deck3 style, is the honest instrument — roughly 66
cards plus repeats, one more grading sitting. `build_deck3.py` already samples both populations, so
nothing new needs designing.

**Pre-register the rule before the deck is built**, in the deck3 style: name in advance what
Δ counts as "this path discards setups you want" and what the remedy is if it does — the path is
loosened, replaced, or downgraded from a hard reject to a scored penalty. Ticket 23's write-up is
explicit that a marginal result must be reported as marginal.

**Read against the ceiling.** Test–retest r is +0.831 on 18 pairs, mean absolute difference 0.56★.
A 0.75★ target sits only just above single-grade noise, which is exactly why the arm has to be
33 and not 20.

**Not in scope here:** the third rejection path, `not_caught_up` (1.6% of bar-dates, never sampled).
If the eye is being asked for another sitting anyway, decide deliberately whether to carry it —
but it is a separate population and a separate question.

## Comments

**The deck is built and the rule is pre-registered. This ticket now needs a grading sitting.**

Everything an agent can do without the eye is done:

- **[`PREREGISTRATION_DECK_F.md`](../prototypes/15-grading-round-2/PREREGISTRATION_DECK_F.md)** —
  written and committed *before* a card was rendered. Fixes the population, the size, the decision
  rule and the remedy menu.
- **`deckF.html`** — 105 bare cards, one sitting. 33 `line_not_drawable` / 33 detections /
  33 `not_caught_up` / 6 repeats. Grade with `1`–`5`, hit **export**, paste the string back.
- **`analyse_deckF.py F=<string>`** — runs the pre-registered rule mechanically and prints the
  verdict, so the answer is not a judgement made after seeing the numbers.

**Two things found while building it that change how this ticket's own premise reads.**

1. **Deck D3's arms were not drawn from the same population, twice over.** `build_deck3.py` gates
   and stratifies the detections arm (`population()`: `prior_move >= 0.90`, equal cards per
   provisional band) and does neither for the rejects (`rejects()`: a random draw from
   `has_base & move >= 25%`). Measured: only **6.7%** of the `line_not_drawable` pool clears the
   decile the detections arm was 100% inside. Both confounds push the reject arm down, so the
   **−0.40★ this ticket was opened on is an upper bound on how badly the path does** — the honest
   estimate is nearer zero or above it. Deck F gates both arms identically, draws both at random,
   and defines the reject arm as `tight & ~line_ok & caught_up` — failing on the line and nothing
   else, which is also exactly the set that would join the list if the test were deleted.

2. **The remedy is now priced.** Decile-gated, over 250 sampled nights: the US list is **5.98
   names/night** as specified, and deleting `line_ok` takes it to **9.5 — a 59% increase**. The
   path is 22.7% of the post-base pool, and it is not one test: ungated, 50% of its failures are
   overshoot and 23% touches; *after* the decile gate the deck's own arm runs the other way, 48%
   touches and 24% overshoot.

**The third path is carried.** `not_caught_up` is in the deck as a secondary arm, at 33 cards, with
no remedy pre-committed to it. It is worth 0.95 names/night (0.16× the list), which is small — but
it reuses the same detections arm as its control at no extra cost, and it is the last unmeasured
rejection path on the map. Leaving it out defers it a fourth time with no deck in sight.

**Ride-along, no grading required: the pooled test–retest ceiling is measured.** The map recorded
+0.808 on 12 pairs and two disjoint 18-pair readings (+0.854, +0.831) with the pooled figure owed.
`analyse3.py A= C= D= E=` over all 24 pairs gives **r = +0.855, mean |difference| 0.46★** — up
again on more data. The noise floor every result on this map is read against therefore tightens
from 0.56★ to **0.46★**, and deck F's decision rule was amended to it before any card was
rendered — which *narrows* the band in which the remedy fires, the conservative direction.

Deck F's 6 repeats will take the pool to 30 pairs.
