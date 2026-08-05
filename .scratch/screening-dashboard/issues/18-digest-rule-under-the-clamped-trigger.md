# What does the digest report when the trigger no longer descends?

Type: grilling
Status: open
Blocked by: —

## Question

Ticket 14 fixed the nightly digest as *"only real breaks are reported"*, and that rule was built on
the shape of ticket 08's D5 trigger. Ticket 17 replaced D5. Which crossings are reportable now?

Ticket 14's A2 splits a crossing three ways and renders only the first:

1. price rose through the level — **reported**;
2. the fitted line descended to meet a flat name — **not reported**, because *"reporting the arrival
   of a level 08's D5 designed to descend is reporting a parameter choice back to yourself"*;
3. the name was born triggered — **not reported**, 16.4% of setups.

All three rest on facts ticket 17 changed. Under the split's `max(line_at(t+1), cluster_high)` clamp:

- **born triggered falls 16.0% → 0.2%**, so type 3 is now a rounding error rather than a sixth of
  the pool;
- the trigger is the **recent cluster high on 82% of detections**, so it is a level the tape actually
  printed rather than a fitted line's value — and where the clamp binds it does not descend at all;
- when the cluster rolls forward, the trigger can *rise* as well as fall, which ticket 14 never had
  to consider and which its "crossed" taxonomy has no bucket for.

Ticket 14 conditioned itself on exactly this: *"if ticket 15 revisits D5, this reopens."* It was
ticket 17 rather than 15, but the condition is met.

Specifically:

- **Does the three-way taxonomy survive at all?** If type 3 is 0.2% and type 2 shrinks to the 18% of
  detections where the line is not clamped, the rule may collapse to "report every crossing" — which
  is simpler, and ticket 14's durable output was a *rule* (the digest carries only what the app
  structurally cannot show you), not a taxonomy.
- **What happens when the trigger rises?** A name can clear a level and then have the level move up
  past it as the cluster re-forms. Ticket 14's break test is `close_today > trigger_yesterday`, which
  still evaluates, but the *meaning* changes: yesterday's level may no longer be today's.
- **Does the accepted cost still hold?** Ticket 14 accepted withholding the earliest signal it
  produces on the grounds that D5's early trigger might be right. The new trigger is *later*, not
  earlier (+0.513 ADR), so the trade-off it priced has inverted.
- **Anything to re-measure?** The digest is a rendering over persisted rows (ticket 12's A4), so any
  answer here is backfillable and testable over history rather than only forward.

**Do not re-litigate** ticket 14's core decision that v1 does not alert, the one-file-per-market
Markdown digest, or the rule that the digest carries only what the app structurally cannot show.
