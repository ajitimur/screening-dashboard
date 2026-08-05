# Alerting on the trigger level

Type: grilling
Status: resolved
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

## Answer

**v1 does not alert. The nightly run writes a digest file per market, and that is the entire notification
layer.** No desktop notification, no push, no screen. Six decisions below; the first two are the ones that
matter, and the rest follow from them.

### A1. No alerting channel — a digest artifact instead

An EOD app has no intraday leg, so any alert can only fire after the close, which is exactly when you are
opening the dashboard anyway. The channel would carry no information the screen does not already carry
seconds later, and it would carry it *ahead* of the screen — which is the actual objection, not the noise.

Ticket 11 (I2) rejected a diff-first landing screen on the grounds that clearing a machine-chosen subset
is not the same as looking at the board (§10, "he does not stop looking"). **A notification is that same
diff delivered outside the app.** Adding one would reverse I2 by the back door, without I2 being
re-litigated. So the trigger event does not get promoted; it gets *recorded*.

The digest is the recording. You may read it or ignore it, and ignoring it costs nothing, because the
list is still there sorted by score. That asymmetry is the whole design: **the digest is never on the
critical path of the nightly review.**

Cheapness is not the argument but it is worth stating — ticket 08 (D1) already persists the
`WATCHING`→`TRIGGERED` transitions nightly and ticket 10's follow-through stream already depends on them,
so **the digest stores nothing new**. It is a *rendering* of an existing stream, which means it can be
regenerated or backfilled over the whole accumulated history, not only accumulated forward. Ticket 09's
standing lesson — persist the raw stream so a later recalibration replays backwards — is satisfied by the
stream, not by the digest, so the digest is free to change shape later without losing history.

### A2. Only real breaks are reported — and ticket 09's D10 is why this had to be decided at all

"Crossed its trigger" is not one event. Ticket 09 (D10) measured that **98.3% of triggers are set by the
fitted descending line**, so the `min()` against the flat max high is nearly dead code and virtually every
trigger level *falls every night*. That splits the crossing population three ways:

| | Event | In digest |
|---|---|---|
| 1 | **Price rose through the level** — a break | **Yes** |
| 2 | **The level fell to meet a flat name** — nothing moved | No |
| 3 | **Born triggered** — detected already past its own level (16.4% of detections, per 09 D10) | No |

**Only type 1 is reported.** Types 2 and 3 are still computed and still persisted — nothing in ticket 08's
or ticket 10's pipeline changes — they are simply never rendered.

The case *against* this was put and lost, and it is not weak: type 2 is precisely the event a human would
not spot on a chart, since by construction nothing happened on the chart. That is an argument for
surfacing it. It was overruled because a type-2 crossing is an artifact of ticket 08's D5 — which chose
the *lower* of the flat and sloped levels **deliberately, to trigger early**, accepting more signals and
more false breaks as the cost. Reporting the arrival of a level you designed to descend is reporting your
own parameter choice back to yourself. Type 3 is not a crossing at all; those names appear in the list
with their state, which is exactly what I2 says should happen to them.

**Accepted cost, stated plainly:** if D5's early trigger is the right call, v1 systematically withholds
the earliest signal it produces. Ticket 09 left D10 open and handed it to ticket 15 — so **if 15 revisits
D5, this decision must be revisited with it.** It is the one dependency this ticket leaves live.

### A3. A break is `close_today > trigger_yesterday`

Ticket 08 (D1) defines the transition as a state change but never fixes *which* price quantity crosses.
A2 makes that load-bearing, so it is fixed here:

> A name breaks when it was `WATCHING` yesterday and **`close_today > trigger_yesterday`**.

Comparing against *yesterday's* level, not tonight's, is what performs the attribution: the crossing must
survive holding the line still. If the close clears the level as it stood before tonight's descent, price
did the work. If it only clears tonight's lower level, the line did — and that is a type 2 non-event.

This is exact rather than a proxy, and it **adds no parameter** — ticket 10 already records the trigger
level nightly from launch, so both operands exist. The proxy alternative (`close > trigger_today` and
`close > close_yesterday`) was rejected for leaking: a name up 0.1% into a line that fell 2% passes it.
The strictest option (also require clearing the flat max high) was rejected because on a 98.3%
sloped-trigger population it reports §3.2's "obvious break", which is the thing the method exists to get
*ahead* of.

Measurement is on the **close**, consistent with ticket 05's finality rule — provisional bars are already
dropped, so a break is never reported off a partial session.

### A4. Breaks only — and the rule that governs any future addition

Nothing else goes in the digest. New setups entering `WATCHING`, names dropping out of `WATCHING` without
triggering, regime changes: none of it.

The principle, which is the durable output of this ticket and should govern later requests to add things:

> **The digest carries only what the app structurally cannot show you.**

Ticket 11 (I3) sorts the single list by star score descending, so a new 5★ setup is *already at the top of
the screen* the moment you open it — a second channel for it is pure duplication. The break is the one
event I2 deliberately left with no home in the UI. That is the entire gap, and A1–A3 fill exactly it.

The rejected option — breaks plus new setups at 4–5★ — also required a **star threshold**, which would be
the first tunable in the notification layer, on a rubric ticket 15 is still recalibrating. This map has
refused tunables at every turn (08's zero-parameter result, 10's argument that survivorship bias makes any
threshold uncalibratable), and it refuses one here.

**Consequence worth naming:** the digest cannot grow into an alerting layer by accretion. Anything added
to it has to first fail the test above, which a diff of the star-sorted list never will.

### A5. One dated Markdown file per market per session

Ticket 11 (I1) made market the top-level axis — **two sittings a night, each after its own close, with no
coherent "tonight" spanning both**. So there is no such thing as *the* digest:

```
digests/IDX/2026-08-05.md
digests/US/2026-08-05.md
```

Each is written by that market's own run, dated with **that market's session date**, never the wall clock —
the same rule I7 applies to the regime banner's as-of date.

**An empty night still writes the file**, containing an explicit "no breaks" line. This is the one piece of
operational hardening in the ticket, and it exists because of the map's standing data-layer property:
**Yahoo fails as silence** (tickets 01/02/03). A run that half-fails and reports nothing looks identical to
a quiet market. With this rule, a *missing* file means the run did not complete, and that distinction is
free.

Markdown over JSONL because you read it at 10pm; the queryable form already exists as the persisted
transition stream (A1), so the digest owes nothing to machines. Dated files over one rolling file so
history accumulates greppably without rewriting the whole file nightly.

### A6. The digest is a pointer, not a decision

It inherits ticket 11 (I4)'s split — *the row decides whether to open the chart; the chart decides whether
to trade* — and sits one step further out, so it carries I4's decision columns plus the numbers that
describe the break itself:

| Column | Source |
|---|---|
| Ticker | — |
| Star score | 11 I4; the ordering everywhere else |
| Industry | 11 I4; ticket 07 made industry *the* theme layer, so clusters are visible |
| Stop width ÷ 1×ADR | 11 I4; §7's veto, readable before opening anything |
| Close | the break |
| Yesterday's trigger | the break — the level A3 tests against |
| % through | how decisive the break was |

Rows are ordered by star score descending, matching the list, so the digest never asserts an ordering the
app disagrees with.

**Deliberately absent:** the §3.5 breakdown, ADR, dollar volume, base length. §7's affordability test is
read off the chart *geometrically* (11 I5), so the digest is structurally incapable of settling a trade
decision — by design, not by omission. It tells you whether to open the chart.

### Hand-offs

- **To ticket 12 (architecture and deployment):** the digest is a filesystem artifact written by the
  nightly run. Where `digests/` lives relative to the store, and whether writing it is part of the run's
  transaction or a post-step, is 12's call. Nothing in this ticket constrains it beyond "one file per
  market per session, written after that market's run completes."
- **To ticket 15 (star score second grading round):** A2 depends on ticket 09's D10 staying open in 15's
  favour. If 15 revisits D5's early trigger — or finds that the 16.4% born-triggered population is a
  detection bug rather than a property — A2's exclusion of types 2 and 3 must be reopened.
- **To ticket 13 (assemble v1 spec):** the notification layer is one artifact and one rule. It is the
  smallest section in the spec, and A4's principle is the part worth carrying forward verbatim.
