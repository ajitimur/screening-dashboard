# Does IDX need its own thresholds?

Type: prototype
Status: resolved
Blocked by: —

## Question

**There are still zero graded IDX cards on any structure** — across ticket 09, round 2 and
ticket 17 — and the app ships both markets from day one. Does one threshold set cover both, or does
IDX need its own?

Nothing needs building. **`deck3_C.html` is rendered and waiting**: 58 cards, 52 IDX plus 6 repeats,
bare, same question and same keys as the deck already graded. Then re-run with the C string added:

    analyse3.py A=<grades3_A.txt> E=<grades3_E.txt> C=<string>

Section 5 is written and verified, and the rule is pre-registered in `PREREGISTRATION_R3.md` §4:
**IDX gets its own thresholds only if the pooled fit's mean residual on IDX differs from US by
> 0.5★, or an IDX-only fit beats pooled on IDX cards by > 0.15★ out-of-fold.** Naming it in advance
is what stops the answer being argued afterwards.

Two things ride along:

- **6 more repeat pairs.** [Ticket 20](20-confirm-the-band-and-measure-the-ceiling.md) measured the
  test–retest ceiling at **+0.808** on 12 pairs — a wide interval, roughly 0.6 to 0.94. These 6
  and deck D3's 6 would take it to 24 pairs and roughly halve the error on the number every
  correlation on this map is now read against.
- **D13's partial-lock probe is descriptive only, and stays that way.** 98.1% of accepted IDX
  detections have zero collapsed bars, so the population ticket 09 sized the probe for is gone;
  ticket 15 de-scoped it and deck C3 carries the 12 locked cards that exist as a subgroup, not a
  powered arm. Read it as colour, and do not let it turn into a threshold.

**Read against ticket 21.** Ticket 20 found the fitting objective does not reliably identify
dimensions the eye is using, so a *pooled-vs-IDX* comparison run under that objective inherits the
same instability. The pre-registered rule above still decides, but if it comes back marginal, that
is a reason to wait for ticket 21 rather than to split the thresholds.

## Answer

**One threshold set covers both markets.** Deck C3 graded — 58 cards, the first graded IDX cards
that have ever existed on this map. Both arms of `PREREGISTRATION_R3.md` §4 miss:

- **Arm 1**, pooled fit's mean residual IDX vs US: **0.33★** (US +0.04, IDX −0.29) against a 0.50★ bar.
- **Arm 2**, IDX-only fit beating pooled out-of-fold on IDX cards: **+0.125★** against a 0.15★ bar.

Arm 2 reads marginal, and the ticket said a marginal result was a reason to wait rather than to
split — so it was measured instead of eyeballed. Over **25 fold assignments the gain runs −0.077 to
+0.231, median +0.058, clearing the bar on 12%**: the headline draw is the upper tail of its own
distribution. The IDX-only thresholds confirm it — across five folds `cluster_k` runs 3–6, `ord_hi`
0.35–0.6, `len_ok` 4–26 on 52 cards. **There is nothing stable to split the thresholds into.**

**The eye is much harsher on IDX and the rubric already knows.** Mean eye **2.35 vs US 3.23**, ≥4★
**15% vs 48%** — a 0.88★ level difference, nearly three times arm 1's whole residual gap. The level
difference is in the **population, not the calibration**: IDX detections grade worse because they
are worse setups, and the pooled rubric reproduces that without being told. A per-market threshold
set would fit a difference the score already captures.

**The score does not degrade off its home market** — pooled, out of fold, on IDX cards: mae 0.913,
r +0.298, within-1 69%, against US's mae 1.11, r +0.255, within-1 60%. It performs *better* on the
market it was not fitted on. On 52 cards that is not a claim IDX is easier, but it retires the
worry this ticket was written for.

**This does not need to wait on the fitting-objective ticket.** Both arms run under mae, but a
rank-based objective is invariant to exactly the level offset that separates the markets, so it
would make pooling more justified rather than less. That is an argument from the objective's form,
not a measurement.

### The two ride-alongs

- **The ceiling tightened.** Deck C's 6 US repeats join ticket 20's 12: **18 pairs, test–retest
  r = +0.854** (was +0.808), mean |difference| **0.44★** (was 0.58★). It moved **up**, so the ~+0.25
  the rubric achieves stays a real shortfall rather than a noise ceiling. Deck D's 6 would take it to 24.
- **The limit-lock probe inverted, and stays descriptive.** Ticket 09 suspected limit days flatter
  both ×2 dimensions, so locked bases would grade high. They grade **low** — mean eye **1.75** (n=12)
  against **2.53** on the 40 clean cards. Colour only; 98.1% of accepted IDX detections have zero
  collapsed bars, so there is no population to build a threshold on.

### What the level difference does *not* create

A 0.88★ gap between markets would matter wherever the app applies a star **cut** or sorts the two
markets against each other. It does neither. Ticket 11's I3 sorts the list by star score descending
and **explicitly refused a star floor** as a tunable, ticket 18's R5 digest membership consults the
score not at all, and ticket 11's chosen variant C makes **market the top-level axis** — IDX and US
are separate tabs, never one mixed list. So there is no surface where a per-market cut would be
applied, and no ticket is needed. Had the app had a global 4★ cut, this finding would have opened one.

**Limits**: 52 IDX cards in one sitting, no power target was pre-registered for this rule, and deck C
is IDX *detections* — whether the detector rejects the wrong IDX names is deck D's question.

Full workings: [`PER_MARKET_FINDINGS.md`](../prototypes/15-grading-round-2/PER_MARKET_FINDINGS.md),
grades in `grades3_C.txt`, arm 2 in `per_market.py`, raw output in `ROUND5_*_OUTPUT.txt`.
