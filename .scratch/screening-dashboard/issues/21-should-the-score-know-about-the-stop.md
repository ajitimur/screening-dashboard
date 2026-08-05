# Should the star score and the digest know about the stop?

Type: grilling
Status: open
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
