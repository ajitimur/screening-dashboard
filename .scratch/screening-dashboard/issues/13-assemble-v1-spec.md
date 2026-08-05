# Assemble the v1 spec

Type: grilling
Status: claimed
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
