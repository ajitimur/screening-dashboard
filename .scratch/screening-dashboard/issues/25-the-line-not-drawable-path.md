# Does the `line_not_drawable` rejection path discard setups you want?

Type: prototype
Status: resolved
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

## Answer

**The path does not separate, so it stops being a gate.** Full write-up:
[`DECK_F_RESULTS.md`](../prototypes/15-grading-round-2/DECK_F_RESULTS.md).

105 cards graded. `line_not_drawable` grades **−0.12★** against detections (95% CI **−0.73 to
+0.48**, p = 0.691; −0.18★ controlling base length) — inside the eye's own **0.46★** noise floor.
By §5 of the pre-registration that is row 2: **a finding, not a pass.** A rejection rule that
cannot be told apart from acceptance is not earning a gate.

Removing deck D3's two confounds moved the estimate from −0.40★ to −0.12★, the direction the
pre-registration predicted **before the deck was built**. The control arm confirms it independently:
band-stratified it read 3.20, drawn at random it reads **2.97**. The deck rules out any true gap
worse than −0.72★, so ticket 23 is not contradicted — only sharpened.

**Remedy: `line_ok` is downgraded from a hard reject to a scored penalty** — §6 option 1, the
pre-registered default, trader's call. Loosening only the touches sub-test and refusing the remedy
outright were both put and not taken. The accepted cost is the decile-gated US list going
**5.98 → 9.5 names a night (+59%)**.

**The remedy is nearly free geometrically.** Ticket 18 proved the fitted line can never exceed the
cluster high, so the trigger *is* the cluster high and the line never reaches it. `line_ok` feeds
one boolean and one chart overlay: demoting it changes **no trigger, no stop, no cluster and no
parameter**. It follows D6 out of the gate set, leaving the cluster and the decile as the tests
that do separate.

**Sub-tests, descriptive only** (pre-registered as such at these n): overshoot-only cards grade
−0.84★ (n=8), touches-only **+0.03★** (n=16), and cards failing **both** grade **+0.25★** (n=9, 56%
at ≥4★). The overshoot test is the only part doing work; the touches test is where the null comes
from. D15's decile gate inverts the ungated mix — 50% overshoot becomes 48% touches — so the
sub-test that survives is the one the gate makes rarest.

**The secondary arm did not separate either, at full power.** `not_caught_up` reads **+0.03★**
(CI −0.50 to +0.56, p = 0.910) on a full 33-card arm. No remedy fires and none was pre-committed.
It is parked as fog rather than ticketed for two reasons: it is worth 0.95 names a night (0.16× the
list), and **catch-up may not be a quality rule at all** — it governs where you *enter*, so *"is
this a setup you want to see"* is the wrong ruler for it. That is tickets 19 and 24's pattern for
the third time: a risk rule measured with a quality ruler. It needs a different question, not more
cards. The third path, `no_cluster`, is untouched and not in question.

**Two ride-alongs outlive the ticket.** The **base-length penalty reproduces** at r = −0.373,
p = 0.0001 (n=99, arm-demeaned, consistent in sign across all three arms) — so **ticket 17's
finding that ticket 09's length effect "did not reproduce" is itself wrong**, and ticket 15's
length term is earning its place rather than being inherited. And **cluster length k replicates a
fourth time** (+0.329, p = 0.001), the one signal on this map that has never failed to reproduce.

**The ceiling is now 30 pairs at +0.846** (mean |difference| 0.47★). The pooled 24-pair figure the
map recorded as owed was computed from existing grades at no cost (+0.855 / 0.46★) before the deck
was rendered; deck F's own 6 pairs read +0.773 and leave the number where it has sat since 12.

What the remedy does **not** fix — the penalty's shape, and whether ticket 11's scan-not-a-queue
list survives at 9.5 a night — graduated to
[ticket 26](26-the-line-penalty-and-the-longer-list.md).
