# Does a 4★ have to mean 4★, or is the star number a label for a rank?

Type: grilling
Status: resolved
Blocked by: —

## Question

[Ticket 21](21-the-fitting-objective-does-not-identify-the-dimensions.md) went looking for a better
fitting objective and found that the question is not answerable without this one.

The score is doing two jobs and one fitted grid cannot do both:

- **`mae` fits the level** — how many stars to print. It is the incumbent, and on 194 E3 cards it
  produces **no stable threshold at all** and lands in the grid's degenerate corner (`ord_lo` 0.10,
  `len_ok` 4).
- **`cindex` fits the order** — the only list the app has (ticket 11 sorts by score). It recovers
  the trader's own band (`ord_lo` 0.30, `ord_hi` 0.60, `cluster_k` 5 ≈ `T3`), makes three of five
  thresholds stable, and beats `mae` by **+0.111 median out-of-fold ρ**.

`cindex` was **not adopted**, because it costs **+0.16★ of mean absolute error against R6 §2's
pre-registered 0.15★ tolerance**. Missing by a hundredth of a star is not a verdict about which
objective is better; it is the map discovering that nobody has ever decided what the star number is
*for*.

The two-stage fix was measured post hoc and is not free: an isotonic level map restores mae to 0.93
(better than the incumbent) but collapses the score's spread — predicted SD **1.24 → 0.44** — and
the ties that creates cost ρ **0.326 → 0.233**. Level is bought with resolution. Someone has to
authorise that trade, or rule it unnecessary.

**So the question, in the form the fit needs it:**

1. **What reads the star number as a number?** Not as an ordering — as a magnitude. If nothing does,
   the level guardrail should never have been binding and `cindex` wins outright, band included.
   Candidates to check: §3.5's rubric language, the digest (ticket 18 R5), the watchlist cards
   (ticket 11 I5), anything downstream of §7 sizing (ticket 24 ruled the score stop-blind, which
   argues nothing sizes off it).
2. **Is 3.2★ meaningful, or only "above 3 and below 4"?** The isotonic map's collapse is only a cost
   if the intermediate values were carrying something. If the app renders whole stars anyway, the
   SD collapse may be invisible on screen and free.
3. **What happens to the 1–5 scale if the answer is "order only"?** A pure rank score still has to
   be *printed*. Fixed quantile bands per market? A fixed mapping? This is where the decision turns
   back into something the fit can execute.

**What rides on it.** Every threshold on this map. Ticket 21 published none, because the objective
that passes the guardrail produces degenerate thresholds and the objective that produces stable ones
is blocked by the guardrail. Also: the 366 pooled cards ticket 21 unlocked buy nothing until this is
settled, and **orderliness** — the strongest dimension on the map at partial ρ +0.365 — is currently
"real but unfittable" purely because `mae` cannot hold a band. Under a rank objective it is stable
and fittable.

**Do not re-litigate** ticket 24 (the score stays stop-blind) or ticket 22 (one threshold set covers
both markets). Both survive either answer.

## Answer

**The star number is a label for a rank plus its cut points, and nothing on this map reads it as a
magnitude — so the guardrail that blocked a rank objective by 0.01★ was defending a property no
consumer has.** Every reader of the score was traced before the question was put:

| consumer | reads |
| --- | --- |
| the watchlist sort ([ticket 11](11-dashboard-information-architecture.md) I3) | **order** — it is the sort key |
| row column 2 and the digest's star column ([ticket 18](18-digest-rule-under-the-clamped-trigger.md)) | **displayed**, and the one rendered example is a whole star, `AAOI 3★` |
| §3.5's own trading rule, *"4–5 at full size; 3 at half size or not at all; below 3, don't"* | **two cut points**, at 4 and at 3 |
| ticket 15 R5's trade line | **one cut point**, at 4★ |
| §7 / §8 sizing, ticket 10's regime posture | **nothing** — [ticket 24](24-should-the-score-know-about-the-stop.md) made the score stop-blind, §8 is out of scope, and the regime posture is advisory words |

Nothing consumes 3.2 as a quantity. The difference between a card at 3.2 and one at 3.4 changes
nothing on screen, nothing in the digest and nothing about sizing, unless it crosses 4. That is the
escape clause [ticket 21](21-the-fitting-objective-does-not-identify-the-dimensions.md) pre-registered
for itself — *"if nothing does, the level guardrail should never have been binding and `cindex` wins
outright, band included"* — so **`cindex` is adopted as the fitting objective**, and with it the
orderliness band and R6 F2's stable thresholds. The rule is not relaxed after the fact; the rule is
found to have been measuring the wrong object, which is what this ticket existed to determine.

**§3.5's `points ÷ 2` mapping stands unchanged — trader's call, and it costs nothing.** No isotonic
stage, no separately fitted band boundaries, **no new tunable**. The alternative on the table was to
split the sort key from the printed label (sort raw, print a five-bucket star), which would have
preserved ρ in full at the price of an amendment to ticket 11's I4; it was put and declined. The
open number that choice left — where the 4★ line lands once the thresholds move — was then measured
rather than assumed, and the answer is that **the trade line improves**: out-of-fold, `cindex` beats
`mae` on precision (**0.49 vs 0.47**) *and* recall (**0.40 vs 0.26**), calling 50 names where `mae`
calls 35. Frozen on E3, precision at 4★ goes 0.50 → 0.51. The worry that motivated R6 §2's guardrail
does not materialise at the one place the level is read.

It also turns out **nothing gates on the cut** — ticket 11's I3 refused a star floor as a tunable and
ticket 18's digest excludes new 4–5★ setups — so the 4★ line is a **label, not a gate**, and its
recall is descriptive. No screen behaviour rides on where it falls.

**Three thresholds are published: `cluster_k` 5, `ord_lo` 0.30, `ord_hi` 0.60.** The incumbent `T3`
already carried `cluster_k` 5 and `ord_hi` 0.60, so **adopting the rank objective moves exactly one
published number, by one grid step** (`ord_lo` 0.275 → 0.30). `len_ok` and `dryup` stay at `T3`'s 14
and 0.95, on R6 §4's own finding that those two are unfitted at this n and no loss function rescues
them — `len_ok`'s modal 20 ranges 4–26 across fits. Full adoption of all five would buy ~+0.019 ρ
and pay for it with two numbers that move across half their grid between folds; stable-only is equal
or better at the 4★ line everywhere (precision 0.52 / 0.54 against 0.51 / 0.54). **This is the first
round on this map to publish a threshold since ticket 15.**

**The fitting pool becomes 432 cards.** Ticket 21's 366 (A3 + E3 + C3, which pool on a rank
criterion because the +0.30★ level offset `REFIT_FINDINGS.md` F3 called disqualifying is invisible
to one) plus deck F's **33 detections and 33 `line_not_drawable`** — the latter now live, since
[tickets 25](25-the-line-not-drawable-path.md) and [26](26-the-line-penalty-and-the-longer-list.md)
demoted that rule from a gate to a silent tiebreak, so those names appear on the nightly list. Deck
F's 33 `not_caught_up` are **excluded** (still gated out, so the rubric would learn to rank names the
app never shows) and its 6 repeats are excluded as A3 duplicates. Wiring deck F's grades into
`load_cards` is work, and it belongs to ticket 28.

**Two corrections to what ticket 21 recorded.** `ord_hi` 0.60 (E3) versus 0.70 (pooled) is **not a
disagreement between the populations**: 0 of 194 E3 cards and 1 of 366 pooled have an orderliness
value in (0.60, 0.70], so the region is empty and the two settings are behaviourally identical on
every card either fit saw. That also qualifies F2's headline — part of `ord_hi`'s 25-of-25 stability
is an empty upper tail, so it is less *tested* than the count suggests.

**Carried, not fixed:** the rubric runs **cold**, printing ≥4★ for 25.3% of E3 where the eye grades
32.0% (pooled 19.1% against 35.0%), a bias of −0.24★ to −0.31★. It inverts round 2's generosity
problem, it is **not** caused by this decision (the incumbent does it too, at 28.9% / 24.0%), and it
is harmless while nothing gates on the cut. Parked as fog rather than ticketed.

**No amendment to ticket 11.** Under the ÷2 decision the sort key and the printed star remain one
object, which is what I4 already assumes. **Ticket 28 unblocks**, inheriting the 432-card pool, the
published three, and `rubric3`'s fast-path/`score3` NaN defect — which must stay fixed, because
pooling now includes the IDX cards that expose it.

**Not re-litigated**, per this ticket's own instruction: ticket 24 (the score stays stop-blind) and
ticket 22 (one threshold set covers both markets). Both survive this answer, and ticket 22 gets
stronger — a rank objective is invariant to exactly the level offset separating the markets.

Assets: [`CUTPOINT_FINDINGS.md`](../prototypes/15-grading-round-2/CUTPOINT_FINDINGS.md) ·
`cutpoints.py` · `CUTPOINTS_OUTPUT.txt`
