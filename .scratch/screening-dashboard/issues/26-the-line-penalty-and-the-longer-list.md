# What does the line penalty look like, and does the list survive at 9.5 a night?

Type: grilling
Status: open
Blocked by: —

## Question

[Ticket 25](25-the-line-not-drawable-path.md) downgraded `line_ok` from a hard reject to a **scored
penalty** — the pre-registered remedy for a path that graded −0.12★ against detections, inside the
eye's own 0.46★ noise floor. It fixed *that* `line_ok` stops gating. It did not fix **how the
penalty is expressed, or what the longer list does to the app.**

Two halves, and they are coupled.

**1. Where does the penalty live?** Three shapes, none costed:

- a **dimension in §3.5's rubric**, which means ticket 15's fitted thresholds are refit with a new
  term on a population that has just grown by 59% — the largest disturbance of the three
- a **sort demotion** below the star score, which touches no threshold and no fitted number, but
  puts a second key on the only list in the app (ticket 11 sorts by star score descending, and
  chose that over distance-to-trigger for a stated reason)
- a **flat badge with no ordering effect**, the cheapest, which is close to admitting the names
  without acting on the null at all

Ticket 25 §3 offers the only lead on *shape*: the overshoot sub-test separates (−0.84★) and the
touches sub-test does not (+0.03★), so a penalty keyed on overshoot alone is defensible in a way a
flat one is not. But n=8 and n=9, so it is a lead, not a finding — pre-registered as descriptive.
**Deciding to collect more cards on that split is itself one of the options here.**

**2. Does ticket 11's list survive at 9.5 a night?** The decile-gated US list goes **5.98 → 9.5**.
Ticket 11 fixed the session as *"a surface you scan, not a queue you finish"* and rejected a
diff-first landing on that basis. A 59% longer list is the first real test of that decision, and
the rejected names are by construction the ones whose ceiling is hardest to read off a chart — so
the marginal row costs more attention than the average one.

Knock-ons to check rather than assume:

- **Ticket 18's digest.** Membership grows, so the ~7.0 US rows a night rises. The *geometry* does
  not move — ticket 18 proved the trigger is the cluster high by identity and the fitted line never
  reaches it — so this is volume only, but the digest's rule was chosen against a volume.
- **Ticket 12's write path.** `line_ok` becomes a stored signal rather than a filter. It is already
  in the persisted signal vector, so this is likely free — confirm rather than assume.
- **The star score's precision at the trade line** (0.53, ticket 15) was measured on the pre-remedy
  population. It is not obviously unchanged when the population grows by 59%.

## What would settle it

Grilling, not grading. Every number this needs already exists — ticket 25's deck and
`DECK_F_RESULTS.md`, ticket 15's rubric, ticket 11's IA decisions. What is missing is a decision
about where a signal that does not separate belongs in a ranking, and whether the app ticket 11
specified still works at the new size.

If the answer is "refit the rubric with a new dimension", that is a second grading round and should
be split out rather than absorbed here.
