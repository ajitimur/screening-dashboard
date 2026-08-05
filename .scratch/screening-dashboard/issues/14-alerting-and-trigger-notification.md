# Alerting on the trigger level

Type: grilling
Status: open
Blocked by: 08, 11

## Question

Does v1 notify you when something crosses its trigger, and through what channel?

This graduated from the map's fog once ticket 08 defined a **stable trigger level** per detected setup —
`min(max high of the primary window, fitted descending line at today)`, emitted nightly for every name in
the `WATCHING` state. Until that existed there was nothing to hang an alert on. §3.2 is explicit that
hanging a price alert on the line is one of the trendline's only two jobs, so this is the method's own use
of the number ticket 08 now produces.

What has to be decided:

- **Does v1 alert at all**, or is the nightly dashboard review (§1: "nightly review, ~10 minutes") the whole
  interaction? An EOD app has no intraday leg to stand on, so an alert can only ever fire after the close —
  which is exactly when you would be looking at the dashboard anyway.
- **What event fires it.** Ticket 08's `WATCHING` → `TRIGGERED` transition is the obvious candidate, but
  ticket 08 (D5) chose the *lower* of a flat and a sloped level deliberately to trigger early, and noted the
  accepted cost is more signals and more false breaks. Decide whether alerting fires on every transition or
  on some narrower subset (star threshold, market regime, breadth).
- **The trigger descends nightly.** Because ticket 08's sloped component keeps falling while a base sits, a
  name can trigger without moving — the line came down to meet it. Decide whether that counts as an alert or
  is a distinct, weaker event, because it is the case a human would not have spotted on the chart.
- **The channel.** The map's standing constraint is that v1 **runs locally**, single user, which narrows
  this sharply: a desktop notification or a nightly digest file, not a push service. Hosting is out of scope,
  so nothing that assumes a server.
- **New-setup alerts vs trigger alerts.** A name *entering* the `WATCHING` state at 4–5 stars may be more
  actionable than one triggering, since §3.2's whole argument is that the setup is at the MA, days before
  the obvious break.

Blocked on ticket 11 as well as 08: whether alerting is a separate channel or simply a state in the
dashboard depends on what the dashboard is.

Resolve against `references/qullamaggie-method.md` §1, §3.2, §6.
