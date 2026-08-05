# What does the line penalty look like, and does the list survive at 9.5 a night?

Type: grilling
Status: resolved
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

## Answer

**The penalty is a silent tiebreak, and the list this ticket was framed around is three times the
size the map recorded.** Full working: [`FINDINGS.md`](../prototypes/26-line-penalty/FINDINGS.md).

Grilling only — no new grades. Every number below comes from deck F's existing 105 grades, ticket
15's published rubric, ticket 25's `split.pkl` scan and ticket 18's cached consecutive-bar scan.

### R1. The rubric does not demote them already, so any demotion is deliberate

Deck F's cards had only ever been read by the eye. Scored with ticket 15 R4's thresholds, the
machine returns **the same null**: `line_not_drawable` grades **−0.03★** against detections (95% CI
−0.46 to +0.40) where the eye read −0.12★. Agreement with the eye is if anything slightly better on
the marginal arm (r = +0.223 vs +0.180; pooled +0.198). **Two independent rulers, one null** — so
the remedy is not "restore a demotion the score is already applying", it is "add one, knowing the
evidence says it should be small".

### R2. A tiebreak, keyed on any line failure, and nothing more

`line_ok` sorts **below** an accepted name **at equal star score**, and has no other effect.
Trader's call. It touches no fitted number, adds no dimension, invents no tunable, and forces no
second grading round — while still honouring ticket 25's pre-registered "scored penalty" rather
than quietly reverting to a flat admission. It is insurance against the gap deck F could not
exclude: anything worse than −0.72★ is ruled out, −0.5★ is not.

**Keyed on the whole path, not the overshoot sub-test.** The overshoot lead survives contact with
the second ruler — machine −0.42★ against the eye's −0.84★, the only sub-test either ruler thinks
is working — but the cards failing **both** sub-tests grade **+0.25★ by eye, above detections**,
56% at ≥4★, and an overshoot key demotes that group hardest. A shape that gets its best-graded
group backwards is not a shape at n=8. Collecting more cards on the split was put as an option in
its own right and **declined**: a tiebreak is already the smallest effect available, so refining
its shape is precision the map cannot spend twice.

### R3. Nothing marks it — not in the row, not on the chart

Trader's call, against the live argument that a sort key you cannot audit is one you will not trust
(ticket 15 R4's own reasoning, and the reason the rubric is boolean). No glyph, no column, and
ticket 11's I4 inventory is unchanged. **The chart draws the fitted line exactly as for any other
name** — checked in the detector: the envelope is always computable, `line_ok` is a verdict on the
fit's quality and not on whether one exists, so there is always a line to draw. Ticket 18's identity
makes it decoration either way, since the line never reaches the trigger.

The consequence, stated plainly: at equal score two rows swap for a reason the screen never shows.
The defence is that the reason is visible in the drawing the chart already renders — the candles
either touch that line twice or they do not.

### R4. The digest takes them: ~7.0 → ~9.6 US rows a night

Measured, not assumed, by re-running ticket 18's own classifier with the line test as a switch.
Membership ignores `line_ok`, consistent with 18 R5, which already fixed that digest membership
ignores quality cuts (it ignores the stop entirely). Keeping the line test as a digest gate would
reinstate as a filter, in one place, the test just removed everywhere else for not separating.

The growth is **+37%, not +59%**, because **marginal names break through their trigger at 0.62× the
accepted rate** (US 3.04% vs 4.90% of detection-nights; IDX 2.28% vs 3.66%). IDX goes 0.9 → ~1.2.

### R5. The break-rate gap is real, and is not priced into the score

It is not the level sitting further away (distance to trigger 0.69 vs 0.65 ADR) and it is not base
length — it holds inside every length bucket, most extremely at L ≤ 10 (**0.74% vs 4.88%**). This is
the **first non-eye evidence about this population on the map**, and it points the same way a
penalty would.

It is still **not** a score input, trader's call. A lower break rate is not a worse setup: no return
is attached to it, and these bases may simply take longer or resolve down. Pricing it in would be
ticket 24's error for the fourth time — judging with the wrong ruler — with the rulers reversed.
Recorded as a validation question instead.

### R6. Ticket 11's screen is unchanged

I2's scan-not-a-queue argument was never about length; it was a refusal to read a machine-chosen
subset. A cap, a star floor and a default filter were all available and all cost a tunable. Raising
the trade line above 4★ was put and declined — ticket 15 R5 already tested ≥4.5★ and rejected it on
a pre-registered bar, and the only evidence for re-opening is 12 called cards.

**The one adverse measurement is recorded rather than acted on**: precision at the 4★ line reads
0.71 on detections alone and **0.58 once the marginal names are merged in** (deck F, 12 cards
called). It is a hint, it cannot move a threshold, and it points at the exact row ticket 11 says
gets read. Ticket 15 R5's headline 0.53 was measured on a different deck and is not directly
comparable.

### R7. The correction: every list-size level on this map is a sample count

This ticket's second half was framed as "does the list survive at 9.5 a night?" — and **9.5 is not
the app's list length.** `split.pkl` scans **628 US symbols** (a random Nasdaq draw plus a 39-name
momentum core, `universe.py`) against ticket 05's measured **1,966**. Ticket 25's `lnd_cost.py`
scales ×3 for the 1-in-3 date grid and **not** for the universe. Ticket 18's `crossings.py` scales
for the universe explicitly. **The two figures this ticket set side by side were on different
bases.**

| | as specified | with the demotion |
| --- | --- | --- |
| list, sample-scale (as ticket 25 wrote it) | 5.98 | 9.52 |
| **list, universe-scale (×3.13)** | **18.7** | **29.8** |
| digest (already universe-scale) | 7.0 | ~9.6 |

`nightly_mix.py` reproduces 5.98 → 9.52 exactly before rescaling, so this is a scaling error, not a
disagreement about the population. **The +59% ratio is unaffected** — it is a ratio inside one pool,
and deck F priced it correctly. R6 was decided against the corrected ~19 → ~30, not against 9.5.

Two caveats keep this a correction rather than a measurement: the scan pool is not ticket 05's
liquidity-gated universe, so the rescale transfers a per-name rate across populations of different
composition; and ticket 19's 39.7 gated names/night uses ticket 06's five-window union gate rather
than ticket 08's D15 three-window decile. **No list level on this map has been measured on the real
universe** — parked as fog, because no spec decision depends on it and ticket 12's ingest makes it
free to measure the day it exists.

### R8. The write path needs a version bump, not a schema change

`line_ok`, `touch_zones` and `overshoot_adr` are already in ticket 08 D16's persisted signal vector,
so storing the demoted signal is free, as this ticket guessed. What is **not** free: 59% more rows
start being written as detections under a changed definition, and nothing in the stream marks the
boundary. The map's validation patch already requires the **detector version** to be written
alongside each detection (from ticket 17's swap); this remedy is a second detector-definition
change and needs the same bump. Free today, irrecoverable afterwards.
