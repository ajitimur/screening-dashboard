# What does the digest report when the trigger no longer descends?

Type: grilling
Status: resolved
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

## Answer

**Ticket 14's rule survives intact and its taxonomy does not — because two of its three buckets turn
out to be unreachable rather than rare.** Nothing changes about which rows land in tonight's digest.
What changes is the justification underneath, and three things the map had wrong.

The prototype is [`18-digest-rule/`](../prototypes/18-digest-rule/); it is the first scan on this map
to run on **consecutive daily bars**. Every prior ticket sampled a 1-in-3 date grid, which cannot see
a night-over-night transition at all — so no earlier measurement of the crossing population was
possible even in principle. 251,321 bar-nights, 29,242 detections, 260 US + 72 IDX names, ~3 years.

### R1. The fitted line never sets the trigger. The trigger is the cluster high, always.

This is the finding everything else follows from, and it is an identity rather than a measurement.
`fit_line` anchors the envelope at the cluster's max high (`y_a = high[anchor]`, where `anchor` is the
argmax of the highs *inside* the cluster) and searches only non-positive slopes
(`linspace(-MAX_SLOPE_ADR * adr, 0)`). So

```
line_at(t+1) = cluster_high + m·(t+1 − anchor),   m ≤ 0,   t+1 > anchor
             ≤ cluster_high
```

for every detection without exception. **`max(line_at(t+1), cluster_high) ≡ cluster_high`** — the
`max()` is dead code. Measured at **100.0% of 29,242 detections**, which is what an identity looks
like when you measure it.

Two map entries are corrected in place:

- **Ticket 17's R3** records D5 as *"replaced by `max(line_at(t+1), cluster_high)`"*. It is replaced
  by **`cluster_high`**.
- **Ticket 16** measured the clamp binding on **82%** of detections. Superseded by 100%. (16 ran the
  clamp formula against ticket 08's window geometry, where the anchor is not the cluster's max high,
  so its 82% was measuring a different object.)

**No ticket reopens.** Nothing either ticket decided turns out differently: ticket 16 chose the
envelope over OLS and ticket 17 took the full split, and both were judged on the *drawing* and on the
**validity gate**, neither of which is affected. The fit still gates detection through `line_ok`
(touch zones, overshoot fraction) and is still what ticket 11's I5 draws. It simply never reaches the
trigger. Worth stating for ticket 19: **four of the split's 22 parameters are line-fit numbers that
cannot move the trigger**, only whether a detection exists at all.

### R2. Types 2 and 3 are structurally impossible, so A2 collapses to a single rule

`cluster_high` is the maximum high over the trailing k bars, and that window **includes today**.
With R1, therefore:

```
trigger_t = cluster_high_t ≥ high_t ≥ close_t
```

**A detected name is never above its own trigger.** Ticket 14's type 2 (the level descends to meet a
flat name) and type 3 (born triggered) are not depopulated — they are unreachable.

| | ticket 14 assumed | ticket 17 predicted | measured |
|---|---|---|---|
| type 1 — price rose through the level | reported | — | 1,051 |
| type 2 — level came down to meet a flat name | not reported | — | **0** |
| type 3 — born triggered | not reported, 16.4% | 0.2% | **2** (0.007%) |

So **"report only type 1" and "report every crossing" are the same rule**, and A2 is restated as the
second, which is simpler and no longer needs a taxonomy to explain itself:

> **A2 (restated).** A name is reported when it was detected yesterday, was below its level then,
> and `close_today > trigger_yesterday`. There is no second or third case.

The 2 type-3 events and the 3 rows where `close > trigger` are data artefacts where the cached bar
has `close > high`; they are noted so a build session does not mistake them for a live branch.

This is ticket 14's durable output doing its job. Its A4 principle — *the digest carries only what
the app structurally cannot show you* — is a **rule**, and the taxonomy was scaffolding under it. The
scaffolding came down and the rule is unmoved.

### R3. A3 is unchanged, on a justification that has been swapped out underneath it

`close_today > trigger_yesterday` stands verbatim. But **the reason ticket 14 gave for it is spent.**
A3 existed to perform *attribution*: D5's level descended nightly, so requiring the close to clear the
level as it stood before tonight's descent proved price did the work rather than the line. Under R1
the level cannot descend below today's close, so there is nothing left to attribute.

What A3 buys now is different, and it is worth naming because it was never argued for:

> **The yesterday-comparison is a recency requirement.** `trigger_yesterday` only exists if the name
> was detected yesterday. A name that lapsed out of detection had no valid base yesterday, so in the
> model's own terms there was nothing for it to break out of.

And A3 means something more literal than it did. `trigger_yesterday` is the highest high of the k
bars ending yesterday, so **A3 is a k-bar closing breakout** — where k is not a parameter but whatever
cluster length the tightness test picked:

| k | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|
| share of detections | 37.3% | 24.8% | 15.3% | 9.0% | 13.6% |

Median 4, mean 4.37. Worth stating plainly in the spec, because "close above the last four sessions'
high" is a sentence a trader can check by eye and `close_today > trigger_yesterday` is not.

**The cost of the recency requirement, measured.** Names that lapse and return above the level they
last carried are invisible to A3:

| lapse | n | median % above the stale level | US rows/night |
|---|---|---|---|
| 2 sessions | 213 | +0.78% | 1.4 |
| 3 | 241 | +1.18% | 1.5 |
| 4–5 | 401 | +1.56% | 2.4 |
| 6–10 | 704 | +3.57% | 4.6 |
| 11+ | 2,180 | +9.12% | 14.2 |

Closing the hole entirely takes US from **7.0 to 31.0 rows a night** against a level a median **13
sessions old** at **+4.92%** — that is not a break, it is a name that went away and came back higher.
A lapse tolerance of N sessions would fix only the top two rows and would be **the notification
layer's first tunable**, which A4 refused; the gradient is continuous, so there is no non-arbitrary N.

**Accepted cost, stated plainly:** the ~2.9 US rows a night at a 2–3 session lapse are break-shaped
(+0.78% / +1.18%) and are withheld. **A hypothesis the session tested and had to withdraw:** that
these are merely *deferred* — re-armed on their new cluster and reported when they clear it. Measured,
only **8.6% are reported within 5 sessions and 17.3% within 20**. They are withheld, not delayed.

This replaces ticket 14's accepted cost rather than adding to it. **14's cost is discharged**: it
withheld the earliest signal it produced on the grounds that D5's early trigger might be right, and
there is no withheld population at all now. The map carries exactly one cost here, and this is it.

### R4. The break is an event, not a state — 08's D1 and 11's I4 are amended

Ticket 17's knock-ons said D1's `WATCHING`→`TRIGGERED` transition survives the split. The transition
does; **the `TRIGGERED` state does not.**

Under D5 a broken name stayed above a descending line, so `TRIGGERED` was absorbing. Under R1 the
cluster rolls forward to swallow the breakout bar, so the level jumps above the close the same night.
Measured over the 1,051 breaks: **55.0% are still detected the next night, and 100% of those are back
below their new level.** Combined with R2 — a detected name is never above its own trigger — the state
is not merely usually `WATCHING`, it is **always** `WATCHING`.

- **Ticket 08's D1 is amended.** Detection emits a base, not a state. A **break** is an event against
  `(market, symbol, session)`, defined by A3. This costs ticket 12 nothing: detections are already
  dated append-only rows carrying their trigger, so the break is derivable from rows that exist, and
  ticket 14's A1 claim that **the digest stores nothing new** survives unchanged.
- **Ticket 11's I4 is amended.** Column 2 was *"score + state"*; the state half would render one value
  for every row on every night. It carries **the score alone**. Five columns, not six.

**The break stays digest-only.** A "broke today" badge in the list would carry real information and is
exactly the diff-first surface ticket 11's I2 refused — delivered inside the app rather than outside
it, which is the same reversal ticket 14's A1 rejected in the other direction. The asymmetry holds:
the break has one home, and it is the file you may ignore.

### R5. Every break is reported, and repeats are marked rather than suppressed

R4 creates a problem ticket 14 never faced: a name re-arms the night after it breaks, so it can be
reported again. Measured: **20.6% of breaks fall within 20 sessions of the same name's previous
break, 7.4% on consecutive sessions**, and 80.3% of reported names appear more than once in three
years (median gap 70 sessions — mostly genuinely separate moves).

**No suppression.** A repeat row carries a marker and the date the name was last reported:

```
AAOI   3★   Semiconductors   0.71   18.04   17.88   +0.89%   ↺ last reported 2026-07-28
```

The case for suppressing was put and lost on the evidence. Repeats within one detection episode land
at a **higher** price than the episode's previous break — median **+1.10%**, with only **0.7%** lower —
so they are continuation, not a name flapping across a level. And 85.5% of break-carrying episodes
contain exactly one break, so a rule would buy little:

| rule | US/night | IDX/night | rows kept |
|---|---|---|---|
| every break (no rule) | 7.0 | 0.9 | 100% |
| first break per detection episode | 5.9 | 0.8 | 86.1% |
| suppress a repeat within 5 sessions | 5.9 | 0.8 | 86.4% |
| suppress a repeat within 20 sessions | 5.5 | 0.7 | 79.4% |

The episode rule is parameter-free and was the serious alternative. It was declined because it
**silently withholds a second, higher break** — the digest would be making a judgement about which
continuation matters, which is the kind of decision A6 says the digest is structurally not for. The
window rules are tunables and refused per A4. The marker costs nothing, needs no threshold, and
answers the only question a repeat actually raises: *have I seen this one already?*

**A6 gains one column** (the repeat marker and last-reported date). Everything else in A6 stands.

### Volumes

| | breaks/night |
|---|---|
| US | ~7.0 |
| IDX | ~0.9 |

Scaled from the sample to the 1,966 / 288 universes of ticket 05, and **upper bounds**: ticket 08's
D15 decile gate is not applied in this prototype, so the real digest is shorter. Ticket 14's design
intent — a file you can ignore at no cost — is comfortably met at this length.

### The reopen condition, re-armed

Ticket 14 conditioned A2 on *"if ticket 15 revisits D5, this reopens."* D5 no longer exists, so that
condition can never fire and must not be left standing as though it might. Its replacement:

> **If ticket 19 moves `TIGHT_MULT`, `K_MIN` or `K_MAX`, the digest moves with them.** Those three
> numbers define the cluster, and by R1 the cluster high **is** the trigger. Ticket 17 measured
> `TIGHT_MULT` alone swinging the nightly list by 63%, and by R3 the k range is also the digest's
> breakout lookback. Nothing in this ticket's *rules* depends on their values; every *number* in it
> does.

By contrast, ticket 15 can no longer reopen this: the rubric sets the star column and the sort, and
the digest's membership does not consult either.

### Hand-offs

- **To ticket 19:** R1's four unreachable line-fit parameters, and the reopen condition above. Also
  worth its attention that `K_MIN`/`K_MAX` are doing double duty — they set the cluster *and* the
  breakout lookback — so fitting them on detection quality alone under-counts what they move.
- **To ticket 13:** the notification layer is one artifact and one rule, and both are now shorter than
  ticket 14 left them. A4's principle carries forward verbatim; the taxonomy does not carry forward at
  all. Amendments to 08 D1 and 11 I4 are recorded on those tickets.
- **To validation (map fog):** ticket 14 left a concrete first question — do type-2 crossings behave
  differently from type-1? — as the cheap alternative to the star-band question. **That question is
  now void**: there are no type-2 crossings to score. What replaces it is R3's withheld population,
  the ~2.9 US rows/night of short-lapse resumers, which is recorded in the archive (they are dated
  detection rows) and is the cheapest outcome question this map still has.
