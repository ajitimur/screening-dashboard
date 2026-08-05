# Assemble the v1 spec

Type: grilling
Status: resolved
Blocked by: 06, 07, 08, 09, 10, 11, 12, 14, 15, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28

## Question

Write the v1 spec — the destination of this map.

Every decision on the map is recorded in its own ticket. This ticket assembles them into one document a
build session can work from without re-reading the map:

- Scope and non-goals (pull the Out of scope section forward explicitly).
- Domain glossary — universe, candidate, base, setup, star score, leader, regime, rotation. Use
  `/domain-modeling`; this is the ubiquitous language the code should speak.
- Data contract — sources, schemas, refresh cadence, adjustment rules, failure modes.
- Computation spec — every formula with its parameters: ADR, liquidity, returns, deciles, sector
  strength, rotation, setup detection, star score, regime.
- Screen inventory and the nightly path.
- Architecture and deployment.
- Acceptance criteria — what makes v1 done. Concretely: on a given evening, what should the app show
  and how would you know it's right?
- Open risks carried into the build, and what would trigger a rethink.

Where a decision was made under an assumption that could not be verified during wayfinding, say so
in the spec rather than presenting it as settled.

## Answer

**The spec is [`v1-spec.md`](../v1-spec.md).** Ten sections, assembled from the 27 resolved tickets;
every claim in it links back to the ticket that owns the decision. The map is no longer required
reading for a build session.

Nothing new was decided here — that was the point. Assembly turned out to be a reconciliation job
rather than a writing one, because several decisions had been amended two or three times by later
tickets and the *current* state of each had to be recovered from the amendments rather than from
the resolving ticket's own text.

### What assembly had to reconcile

Recorded because each is a place where reading a single ticket would give a build session the wrong
answer:

- **The detector is not what ticket 08 resolved.** D2/D3/D4/D5/D9/D14 are deleted or replaced by
  ticket 17's base/cluster split, D6's stop gate is gone (16, then 17), and D1's `TRIGGERED` state
  is unreachable (18). §4.5 of the spec is written from `split.py`'s actual control flow, checked
  line by line against the ticket text, and states the algorithm once.
- **The published rubric thresholds are ticket 27's, not ticket 15's.** 15's R4 table
  (`cluster_k ≥ 4`, band 0.275–0.50, `len_ok ≤ 26`, `dryup ≤ 0.90`) was fitted under an objective
  ticket 21 then showed to be blind. The live set is **`cluster_k ≥ 5`, band 0.30–0.60,
  `len_ok ≤ 14`, `dryup ≤ 0.95`**, confirmed on 432 cards by ticket 28. The spec carries only the
  live set, and marks `len_ok`/`dryup` as unfitted at this n.
- **Two surfaces show two different stops** (24 R3) — cluster-low on the watchlist, breakout-day
  low in the digest. Easy to collapse into one by accident; called out explicitly in §4.6.
- **The trigger identity** (18 R1) is stated as an identity, and turned into an acceptance
  criterion — B7: *the fitted line sets the trigger in 0% of detections; any non-zero value is a
  bug.*
- **`line_ok` is a tiebreak with nothing marking it** (25, 26), which is invisible in the screen
  inventory ticket 11 wrote before it existed.
- **Every list-length level is provisional** (26 R7). §4.8 carries the numbers with the warning
  attached rather than quoting them inline elsewhere, so no downstream reader picks one up clean.

### What the spec adds that no ticket had

- **§2, the glossary** — the ubiquitous language, 30 terms. Several were being used loosely across
  tickets (base vs cluster vs window; detection vs break vs trigger; gate vs board).
- **§8, acceptance criteria** — 30 checks in four groups: the run (A1–A6), the numbers (B1–B10,
  every one a figure a ticket measured, so the first real run is a regression test against the
  wayfinding), the screens (C1–C10), and five judgement calls to make by eye on night one (D1–D5).
  D2 is the instrument-filter spot-check ticket 05 asked for and nothing had owned since.
- **§10, one table of every free number in v1** — 43 rows, each marked live / frozen / fitted /
  unfitted / structural, plus the deleted list. The map had these scattered across five tickets.

### The seven capture streams are stated as a build requirement

§7.2 makes the `detector_version` column non-optional and lists all seven irrecoverable streams in
one place. They are free at the write path today and impossible to reconstruct later, and they are
the only thing standing between v1 and a permanently unanswerable validation question.

### What the spec says is unfinished

Not smoothed over — §9 carries six risks with their reopen triggers, and the four knowing omissions
with the cost and cheapest reversal of each. The headline is unchanged from the map: **the rubric
captures about a third of what the eye makes achievable** (ρ +0.292 against a +0.846 ceiling), and
that shortfall lands on the sort order of the only list in the app.

No fog graduated and nothing was ruled out of scope. **This ticket was the destination; the map is
complete.**
