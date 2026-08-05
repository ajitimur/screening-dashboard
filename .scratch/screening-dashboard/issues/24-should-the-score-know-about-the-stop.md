# Should the star score and the digest know about the stop?

Type: grilling
Status: resolved
Blocked by: 20

## Question

[Ticket 19](19-fit-the-split-parameters.md) R2 decided the screen **shows** every detection with its
stop width and marks the ones outside §7's 1 × ADR cap, rather than filtering on a proxy the screen
cannot measure properly. That settles what the *list* contains. It does not settle what the *sort*
means, and the two are not independent, because the star score is what orders the only list in the
app (ticket 11).

The numbers that make this live:

- **~92% of the nightly list is outside §7's cap** on the cluster-low proxy, so the score is
  currently sorting a population that is mostly, on its face, untradeable.
- **The eye prefers exactly what §7 rejects.** Looser cluster → wider stop → higher eye grade, on
  every measurement ticket 19 took: grade rises monotonically with cluster looseness (2.54 → 2.75 →
  2.94), and the cards a §7 gate would remove graded **2.91 against the 2.44 it would keep**.
- Ticket 15's rubric was fitted on grades collected from that population, so the score has, in
  effect, already learned to *reward* wide stops — without anyone deciding it should.

So the question in three parts:

1. **Should stop width enter the star score?** As a dimension, a penalty, a tiebreak, or not at all.
   The case for: a 5★ the trader cannot afford is a worse recommendation than a 4★ they can. The
   case against: §3.5's rubric is about the *setup*, and affordability is a property of the trade,
   not the base — and ticket 15 has just spent a session establishing that adding dimensions to this
   rubric is expensive and easy to get wrong.
2. **Should the digest's membership consult it?** [Ticket 18](18-digest-rule-under-the-clamped-trigger.md)
   R5 reports every break, and its membership consults neither the score nor the stop. If ~92% of
   breaks are §7 no-trades on the proxy, the nightly digest is mostly reporting trades that cannot
   be taken — or it is correctly reporting them and the proxy is the thing at fault.
3. **Is the disagreement real, or is the proxy wrong?** The cluster-low stop is deliberately
   conservative: §7's actual stop is the entry-day LOD or opening-range low, which sits *above* the
   cluster low. If the true stop is usually inside 1 × ADR where the proxy says it is not, there is
   no disagreement to resolve and parts 1 and 2 dissolve. **This is the cheapest of the three to
   attack and should go first** — but it needs intraday data the map has ruled out of v1, so it may
   only be answerable as a forward-history question.

**Blocked by [ticket 20](20-confirm-the-band-and-measure-the-ceiling.md)** for the same reason
ticket 19 was blocked by 15: two of the rubric's dimensions are unconfirmed and its ceiling is
unmeasured, so weighing a *new* dimension against them would be weighing it against numbers that may
not survive. If 20 finds the band does not reproduce, the rubric has a free ×2 slot and part 1 gets
easier rather than harder.

**Do not re-litigate** ticket 19 R2's decision to show rather than filter — that was taken against
the measured price of filtering. This ticket is about the sort and the digest, not the list.

---

## Answer

**No, to both halves — and the reason is that "stop width" is not the quantity this ticket assumed
it was.** It is the cluster's height, by identity, which makes it the *narrowness* measure ticket 15
already retired rather than a new risk input. The ticket's three parts survive the reframe but two
of them shrink: part 1 dissolves into a duplicate, part 2 becomes a question about which *number* the
digest prints rather than which *rows* it contains, and part 3 turns out to be answerable on daily
bars for exactly the population part 2 cares about — but was not measured this session, by decision.

No prototype. This is a grilling ticket resolved against the code and the existing findings; the two
measurements it generated were deliberately not run (see R5).

### R1. Stop width **is** cluster height — an identity, not a correlation

From [`split.py`](../prototypes/16-trendline-fit/split.py):

- cluster selection (line 79): `(ch - cl) / adr_abs <= TIGHT_MULT`
- trigger (line 152): `max(line_end, ch)` — and ticket 18 proved this is `ch` in 29,242 of 29,242
- stop width (line 157): `(trigger - clow) / trigger / a`

So `stop_width_adr = (cluster_high − cluster_low) / ADR`, which is the cluster's range in ADR units.
The only daylight between it and the selection ratio is `close` versus `trigger` in the denominator —
a couple of percent, since `trigger = ch ≥ close`.

Three consequences:

- **The screen's stop column and §3.5's "narrow" are the same ruler.** Ticket 15 found that every
  measure of narrowness fails on this population *because the cluster is selected to fit under
  `TIGHT_MULT × ADR`, so its width is spent by the selection*. That verdict applies unchanged to
  stop width. Adding it to the rubric re-adds a retired measure under a new name.
- **§7's cap and §3.5's tightness dimension are not two constraints.** They read the same number and
  want the same direction. The "eye versus rubric" and "eye versus stop rule" tensions the map
  records separately are one tension.
- **Ticket 19's two eye measurements are one measurement.** "Grade rises monotonically with cluster
  looseness (2.54 → 2.75 → 2.94)" and "the cards a §7 gate removes graded 2.91 against 2.44 kept"
  are the same scalar binned two ways — three bins versus a cut at 1.0. The map's Notes call these
  *three independent measurements*; they are one, at **r = +0.140, p = 0.286**, on a population
  every member of which was selected under 1.5. Corrected in the map and in ticket 19.

### R2. The score does not learn about the stop

**No dimension, no penalty, no tiebreak.** The tiebreak case is already served — ticket 19 R2 makes
stop width a shown, sorted column, so a trader who wants to order by affordability can.

The first reason is R1: it is a duplicate of something already tested and dropped.

The second is better, and it emerged late enough that it corrects this ticket's own premise. The
ticket asserts the rubric "has already learned to reward wide stops without anyone deciding it
should." That is **unproven, and if true it runs through a different mechanism than the ticket
supposed.** Ticket 15's ×2 tightness dimension is not a width at all — it is **cluster length k**, a
bar count, the best-replicated signal on this map (+0.196 fresh, +0.327 mixed, +0.218 out-of-sample
in ticket 17). Width is not scored anywhere. But k and stop width move together across ticket 19's
`TIGHT_MULT` grid (k 3.70/4.41/4.87 against stop medians 0.88/1.28/1.47), which raises the
possibility that **k buys its bars by spending range** — that a longer cluster is a wider one, and
the rubric is rewarding wide stops through the back door.

**The grid cannot answer this**, because it moves the cap: it is a between-configuration
relationship, and the live question is the within-configuration correlation across names at
`TIGHT_MULT = 1.5`. The sign is genuinely unknown — a very quiet name can support k = 7 inside a
small range, while a volatile one may support only k = 3 near the cap, which would push the
correlation *negative*.

So the decision stands on the stronger of the two reasons: **do not add a penalty that may be
fighting the one dimension on this map that replicates, without knowing whether it does.** That is
a different and more durable argument than "it is a duplicate", and it is the one the spec should
carry.

### R3. The digest ignores the stop for membership — and prints a different stop than the watchlist

**Membership: unchanged.** Ticket 18 R5 reports every real break, ~7.0 US and ~0.9 IDX rows a night.
Filtering that on a ruler R4 shows is systematically pessimistic would empty most of a one-page file
to no benefit, and it is ticket 19 R2's decision applied to a second surface.

**The number it prints: corrected, for free.** §7's default stop is *the low of the day you enter*,
and §6 puts the entry on the breakout day. The breakout day is a daily bar, and the digest fires
after that day's close — **so §7's actual stop is already in the ingested data at the moment the
digest is rendered.** No intraday, no new parameter, no new capture stream.

| surface | stop shown | why |
| --- | --- | --- |
| watchlist (still in base) | `trigger − cluster_low` | the breakout day has not happened; nothing better exists |
| **digest (broke out today)** | **`entry − breakout_day_low`** | §7's actual rule, and the bar is already there |

**Neither surface marks a no-trade.** Ticket 19's caveat — a flag firing on 92% of rows is not a
flag — is the watchlist's reason. The digest's reason is different and narrower: under the corrected
ruler the base rate is simply **unmeasured** (R5), and a mark implies a rate we do not have.

This does not disturb ticket 14/18's digest rule; it changes one column's definition. Amendment
recorded on ticket 14.

### R4. Part 3 is not an intraday question, and it was the load-bearing one

The ticket judged part 3 — *is the disagreement real, or is the proxy wrong?* — cheapest to attack
and possibly answerable only from forward history, "because it needs intraday data the map has ruled
out of v1". **That is false for post-break names.** §7 names three stops and only two are intraday:

| stop | width | visible EOD? |
| --- | --- | --- |
| cluster low (what the map measures) | widest | yes |
| **low of the breakout day** (§7's stated default) | narrower | **yes** |
| opening-range low, 1/5/60-min (§6's usual choice) | narrowest | no |

And §6 selects *the shortest timeframe whose stop you can afford*, so the real stop is tighter still
— making the breakout-day low a conservative **upper bound** on §7's stop, and the cluster low a
bound on nothing in particular.

The consequence is that **ticket 19's headline number may be an artefact of the ruler.** "92% of the
nightly list is a §7 no-trade" is measured from a floor that can sit several sessions and a full
cluster-height below the low §7 actually names. If the breakout-day figure lands mostly inside
1×ADR, there was never an eye-versus-§7 disagreement to resolve — the eye was endorsing setups the
trader's own rule also accepts, and the screen was mismeasuring them.

**This was put and the measurement was declined** (the bar caches from tickets 09/15/19 are gone, so
it needs a fresh pull). The decisions above are therefore taken *without* it, and each is the
conservative choice under that ignorance: do not add a dimension, do not filter, do not mark.

### R5. Two measurements owed — parked as fog, not ticketed

Both are pure computation on daily bars, both need the same fresh pull, and neither needs a human:

1. **Does §7 bind under the correct ruler?** Distribution of `(entry − breakout_day_low) / ADR` over
   detected breaks, against the 1×ADR cap. Answers R4 and would settle whether the digest should
   mark no-trades.
2. **Does k spend range to buy bars?** Correlation of cluster length k with stop width at fixed
   `TIGHT_MULT = 1.5`, across names. Answers R2's open sign, and if strongly positive it means the
   rubric's ×2 tightness dimension is partly a stop-width preference.

**Parked in the map's Not yet specified rather than ticketed** — trader's call. Neither blocks the
spec: R2 and R3 are decided in both directions of either answer, and what a positive result would
change is confidence and a marking rule, not a structure.

Note the standing trap R4 inherits from ticket 19: even the breakout-day low is a proxy, since §6
usually enters on the opening range. A study on it measures a quantity slightly wider than the one
the trader risks — which biases in the safe direction, unlike the cluster low, which biases hard the
other way.

### What this ticket did not touch

Ticket 19 R2's decision to **show rather than filter** stands, unexamined by request. The watchlist
column, its sort, and the absence of a gate are all unchanged. What changed is (a) the score stays
out of it, (b) the digest prints a better number, and (c) the map's belief that the eye and §7
disagree is downgraded from three measurements to one weak one — with the measurement that could
settle it now named, cheap, and knowingly unrun.
