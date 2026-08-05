# Does a 4★ have to mean 4★, or is the star number a label for a rank?

Type: grilling
Status: open
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
