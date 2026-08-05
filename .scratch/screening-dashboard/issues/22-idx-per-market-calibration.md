# Does IDX need its own thresholds?

Type: prototype
Status: open
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
