# Dashboard information architecture

Type: prototype
Status: resolved
Blocked by: 06, 07, 08

## Question

What do you see when you open this app, and what is the ten-minute nightly path through it?

His nightly review is ~10 minutes (§1). Design to that, not to a data-exploration tool. Build rough
screens to react to — outlines or a clickable stub, not production UI.

- **Landing screen** — regime verdict, tonight's candidate count, what changed since yesterday? What is
  the single thing you want to see before anything else?
- **Candidate list** — columns and default sort. Star score, ADR, decile ranks, sector, distance to
  the trendline/trigger, implied stop width vs 1×ADR, dollar volume. Which of these earn their space?
- **Chart view** — candles with 10/20/50 SMA and 65 EMA (§2), the detected trendline, the base
  highlighted, volume with the dry-up/expansion marked. Does the score breakdown sit next to it so you
  can see *why* it scored what it did?
- **Decile leaderboards** — one table per lookback, or one table with a column per lookback? How is
  change-over-time shown (per ticket 06's reading of "each period")?
- **Sector/rotation view** — follows from ticket 07's numeric definition of rotation. Quadrant chart,
  ranked bars with rank-change arrows, or a heatmap over time?
- **Two markets** — tabs, toggle, or side by side? They have different closes, so at any given hour one
  is fresher than the other. How is staleness communicated?
- **Navigation between them** — click a sector, see its members; click a name, see its chart.
- **Rejected candidates** — is there a view of what was screened out and why? Useful for trusting the
  screen early on, dead weight later.

Output: agreed screen inventory and the nightly path. Link the prototype rather than pasting it here.

**From ticket 10 (market regime filter):** the screens must carry **two persistent regime banners**, one
per market, each showing its state (`FRIENDLY` / `CHOPPY` / `HOSTILE`), a sizing posture, the as-of
session date, and a universe-breadth reading beside it. The candidate list is **identical in all three
states** — the regime never filters or reorders it — so the banner is the only place regime appears.

## Prototype

Three structurally different IAs, built as one throwaway page and switched with the bar at the bottom
(or `←`/`→`). Variant **C won**; it has since been folded to reflect the decisions below, and A and B
are retained as the rejected alternatives, which is the point of keeping the prototype at all.

- Source: [`prototypes/11-dashboard-ia.html`](../prototypes/11-dashboard-ia.html)
- Live: https://claude.ai/code/artifact/c000e66e-926e-41f9-b6ac-db2ef88ee6af

The three disagreed about the *shape of the nightly job*, not about styling:

| | Claim | Verdict |
|---|---|---|
| **A — Tonight** | The session is a **queue you finish**: the landing screen is a night-over-night diff (triggered / new 4–5★ / drifted), everything unchanged behind a fold, both markets stacked | Rejected |
| **B — Console** | The session is **one dense screen with no navigation**: every setup from both markets in one sortable table, chart and score to the right | Rejected |
| **C — Workbench** | **Market is the top-level axis**: IDX and US are tabs worked at different times, with sector context beside the candidate | **Chosen** |

## Answer

**Two screens. That is the whole app.** A per-market workbench (×2) and a Boards tab. Everything below
is a consequence of that plus the four decisions taken in session.

### I1. Market is the top-level axis — and this makes staleness structural rather than a warning

IDX and US close hours apart, so **at no point is there a coherent "tonight" spanning both**. Variant A's
combined stacked view and variant B's single cross-market table both had to paper over that with a
freshness label on one half of the screen.

Making market the top axis retires the problem instead: **you work one market at a time, after its own
close, as two short sessions rather than one**. The cost is real and accepted — it is two sittings a
night, not one — and it was chosen over the alternative of a single session where half the screen is
always a day old.

This is also the first decision on this map that is a *rhythm* decision rather than a layout one. It
implies the app has no global "as of" — every date on screen belongs to a market.

### I2. The nightly session is a surface you scan, not a queue you finish

Variant A's premise — that the landing screen should be a **diff** of what changed since last night, and
that clearing it means you are done — was put and **rejected**.

The consequence is worth stating plainly because it looks like a small UI call and is not: **there is no
"what changed since yesterday" surface anywhere in v1.** Ticket 08's `WATCHING`→`TRIGGERED` transition
is still computed and still persisted nightly (D1, and ticket 10's follow-through stream depends on it),
but it does not get a screen. A name that crossed its trigger overnight appears in the list in score
order like any other, marked with its state, and nothing pulls it to the top.

That is a deliberate trade — it keeps the eye on the whole board rather than on a machine-chosen subset,
consistent with §10's "he does not stop looking" — but it leaves the trigger event with **no home in the
UI**, which is precisely the gap ticket 14 now has to fill. See the hand-off.

### I3. The list sorts by star score, descending — which promotes ticket 09 from labelling to ordering

§3.5 is the verdict, so it orders the list. **Proximity to the trigger does not** — it is a column, not
the sort. The argument against was live: §3.2 insists the setup *is* at the MA days before the obvious
break, so a name sitting on its line tonight is the actionable one. It lost because sorting by distance
puts a 2★ barcode above a 5★ base, and defending against that needs a star floor — a tunable, which this
map has refused everywhere.

**This changes what ticket 09 is for.** Before this decision, a miscalibrated star score mislabelled rows.
After it, a miscalibrated score **puts the wrong name at the top of the screen every night** — it is the
primary ordering of the only list in the app. Ticket 09 was already carrying the map's residual detection
risk; it now carries the IA's as well.

### I4. Six columns — decision plus provenance

| Column | Why it earns the space |
|---|---|
| Ticker | — |
| Star score + state | §3.5 is the verdict, and the sort key |
| Distance to trigger | how soon, and it is the number §3.2 makes actionable |
| Stop width ÷ 1×ADR | §7's veto, visible before you open anything — a row at 0.97× is nearly dead |
| Industry | ticket 07 made industry *the* theme layer; this is where a cluster becomes visible |
| `k/5` breadth badge | ticket 06's measure of how broadly the prior move leads |

**Deliberately not columns:** ADR, dollar volume, base length `L`, the five decile ranks, sector. All are
in the chart panel, which is where you already are when you need them. The rejected "method-complete"
option put every §3.5 input in the row; it was turned down because most of those numbers are near-constant
night to night and would earn a horizontal scroll on IDX-width content for nothing.

The split is: **the row decides whether to open the chart; the chart decides whether to trade.**

### I5. The chart panel sits beside the list, with the score breakdown adjacent — and this settles ticket 08's provisional bundle

Ticket 08 (D16) shipped its chart evidence bundle explicitly provisional, noting it was designed against a
consumer that did not exist. It exists now. The bundle renders:

- Candles, plus **SMA 10 / 20 / 50 and the 65 EMA** — §2's daily set exactly, the 65 EMA included because
  §2 names it as the one exponential on the daily.
- The **primary window only**, shaded. Ticket 08 (D3) retains every valid window; the chart shows the
  shortest valid one and no other. Drawing the retained set would render the degeneracy D4 accepted rather
  than the setup being scored.
- **Both fitted lines** over that window — descending over highs, rising over lows. They are drawn as
  fits, so candles pierce them in both directions; per §3.2 that is the correct picture and must not be
  "fixed" in rendering.
- The **trigger level** (`min(flat max high, fitted line at today)`) and the **base low as the estimated
  stop**, both as horizontal rules, because §7's affordability test is the one thing read off the chart
  geometrically.
- Volume, with base bars distinguished, so ticket 08's dry-up dimension is visible. **Expansion is not
  drawn** — per D11 it exists only at the break, so there is nothing to render in the `WATCHING` state.

The **8-row §3.5 breakdown sits next to it**, showing each dimension, its weight, whether it scored, and
the `n/10 → stars` arithmetic. This is the answer to the ticket's own question: yes, adjacent — because
the score is the sort key (I3), and a sort key you cannot audit at a glance is not one you will trust.

### I6. Sector rotation sits beside the candidate; the leaderboards are a peer tab off the nightly path

**Sector** is *in* the workbench, in the third column, with the candidate's own sector highlighted. Ticket
07 made sector a **scoring input** (S6's leave-one-out share) rather than a report, so it belongs next to
the thing it scores. Its form was already fixed by ticket 07 — a sortable table with the shape differential
column, not a quadrant chart or heatmap — so no new decision was needed here.

**The five decile leaderboards are a peer tab**, visited when you want them, not nightly. The reasoning is
that ticket 08 (D15) already gates every candidate on top-decile membership, so anything on the boards that
matters has *already* become a candidate — the boards would be re-reading the input to a filter that has
already run. §1 does list the gainer scans as his nightly routine, but he had no detector doing that gating
for him.

Their content stays exactly as ticket 06 fixed it: five separate boards per market, 30 rows, no compositing.
The rejected middle option — surfacing the 1m board in the workbench — was turned down for privileging a
lookback that ticket 06 deliberately refused to privilege.

### I7. A market shows its last final close, labelled

Ticket 05's finality rule already drops provisional bars, so opening the US tab mid-session shows the last
completed session, with the as-of date on the regime banner. **No dimming, no blocking, no stale state.**

The stronger options were put and declined: an explicit stale treatment for the whole tab, and hiding the
tab entirely until tonight's run lands. Both were solving a problem that I1 had already dissolved — once
market is the top-level axis, you are never comparing a fresh half-screen against a stale one, so a date
label carries the whole load.

### I8. No rejected-candidates view in v1

Nothing shows what was screened out or why. Neither a browsable rejected table nor the narrower
"why isn't ticker X on the list" lookup survives into v1.

**The counter-argument was made and overruled, and is recorded because it is not weak:** ticket 08's
detector has **zero tunable parameters and has never been checked against a real chart**, and it shipped
three knowing omissions (D12's unenforced backside veto, D13's unhandled IDX limit days, D11's
half-measured volume). v1 is exactly the period when you would most want to see what it discarded.

The decision stands, so **the inspection has to happen somewhere that is not a screen**. It lands on
ticket 09, which is a prototype session where a human eye meets the computed score against real charts —
that session should look at the *rejected* set, not only the accepted one. This is a hand-off, not a
consolation: if 09 does not do it, nothing in v1 does.

## Amendment — sector rank movement (I6a)

Raised after the ticket was resolved: the sector table should show *movement* — if a sector used to rank
3rd and is now 1st, say so.

**Accepted.** The rotation table gains a **`Δ20d` rank-change column** — places moved, as `▲2` / `▼1` / `—`.

Three things constrain how, and all three come from ticket 07 rather than from taste:

1. **No new data and no new window.** Ticket 07 (S9) already persists nightly sector shares, so rank
   history is derivable. The comparison is against **20 sessions ago** — reusing the window S3 already
   established for the temporal delta, which S3 itself inherited from §2/§3.5's 10/20-day horizon rather
   than inventing. Comparing against *last night* was rejected: it would be a second window, chosen for
   no stated reason, on a series ticket 06 already showed is noisy night to night.

2. **Rank movement does not replace the share columns, it joins them.** Ticket 07 (S3) chose share
   deltas in percentage points deliberately, and rank discards magnitude — three sectors bunched within
   0.4pp can reorder completely without anything happening. The shape differential stays the default sort;
   `Δ20d` is a column beside it.

3. **It is guarded for quantization, because on IDX it is mostly noise.** Ticket 07 (S4) measured one
   name moving IDX Utilities' share by 10.0pp, against 0.3–1.7pp anywhere on US. So a rank arrow means
   "leadership rotated" on US and often "one stock moved" on IDX. Every row already carries `k/n` per S4;
   a move resting on `k < 2` is **greyed and marked `?`** rather than coloured, matching S4's existing rule
   that `k ≥ 2` is required to top the rotation board.

Measured against the prototype's fixtures, this is not hypothetical: IDX Utilities moves **6th → 3rd on
2 names out of 10**, while every US move rests on 25–53 names. The column is honest on US and needs its
guard on IDX — which is the same asymmetry ticket 07 found, surfacing again one layer up.

**Nothing here changes ticket 07's model.** Rotation is still the two columns S3 defined; this is a third
*presentation* of the same nightly share stream, which is ticket 11's remit.

## Screen inventory

**1. Market workbench** — one per market, `IDX` and `US` as tabs.
   - Regime banner (ticket 10): state, sizing posture, breadth, as-of session date.
   - Candidate list: six columns (I4), sorted by star score descending.
   - Chart panel: bundle per I5, plus the §3.5 breakdown and the facts block (base length, trigger and
     which of the two levels bound it, distance, stop ×ADR, ADR, dollar volume, decile ranks, sector).
   - Sector rotation table (ticket 07), candidate's sector highlighted.

**2. Boards** — five leaderboards × two markets, 30 rows each, per ticket 06. Off the nightly path.

Navigation is one interaction: **click a row, the chart panel changes.** Nothing else navigates. The
ticket asked about click-a-sector-see-its-members; it is not in v1 — with sector strength defined as a
share of the decile (ticket 07 S2), the members are on the Boards tab already.

## The nightly path

1. After the IDX close, open the app. It lands on `IDX`.
2. Read the regime banner — one line, gives you tonight's sizing posture.
3. Scan the candidate list from the top. It is in score order, so you are reading best-base-first.
4. On anything at 4–5★, click the row. Chart, breakdown and sector context are all already on screen.
5. Check the stop column against 1×ADR, the distance to trigger, and the breakdown's two ×2 dimensions.
6. Stop when you stop. Repeat on the `US` tab after the US close.

Two sittings, each short. The 10-minute budget is met by the list being score-ordered and the chart being
one click from the row — not by the app deciding what you are allowed to see.

## Hand-offs

- **Ticket 09 (star score calibration)** — ~~two things land here~~ **resolved concurrently with this
  ticket; both hand-offs are now settled or moved.** Recorded rather than deleted, because what 09
  found changes how I3 reads.
  1. Per I3, the score is the **default ordering** of the only list in the app, not a label on it.
     **09 collected on that risk immediately:** blind-graded over 27 charts the score is *uncorrelated*
     with the trader's eye (r = −0.043), largely because both ×2 dimensions proxy base length — which
     §3.5 never names and the trader reads inverted. 09 corrected the structure but explicitly did not
     set the thresholds, which is now ticket 15. **So the default sort currently orders by a number
     known not to agree with the eye.** I3 still stands — nothing better is available to sort on, and
     sorting by distance was rejected for reasons 09 does not touch — but it is running on borrowed
     time until 15 lands, and 15 is the ticket that makes the workbench's primary ordering trustworthy.
  2. Per I8, v1 has **no rejected-candidates view**, so 09 was made the only place the discarded set
     would get human eyes. **09 did not do it** — its grading deck was built from detections, not
     rejects. The obligation is therefore **unowned**, and belongs on **ticket 15**, which is running
     the larger grading round and already selects decks deliberately (breached triggers, IDX limit
     locks). A deck of *rejects* is the same kind of ask.
- **Ticket 14 (alerting)** — now unblocked, and I2 sharpens it considerably. The dashboard is a
  score-ordered surface you scan with **no diff view and nothing that surfaces a state transition**. So
  the `WATCHING`→`TRIGGERED` event, and a name newly entering the watch state at 4–5★, currently have no
  home in the UI at all. 14 is no longer "alert or dashboard?" — the dashboard has abstained, so 14 is
  deciding whether that event gets surfaced anywhere.
- **Ticket 12 (architecture and local runtime)** — three consequences.
  1. Two screens, both querying the store live per market; the map's standing "a live backend is assumed"
     holds and nothing here needs precomputed views.
  2. **Chart rendering library** is now a pure architecture choice — this ticket fixed *what* the chart
     draws (I5), so 12 picks *how*. This clears the map's chart-rendering fog patch without a new ticket.
  3. Per I1, runs are **per market**, gated on that market's own session finality. There is no global
     nightly job producing one dashboard.
- **Ticket 13 (assemble the v1 spec)** — screen inventory and nightly path above are the section it needs.

## Amendment — ticket 18

**I4's column 2 loses its state half: it carries the score alone, and the list is five columns, not
six.** [Ticket 18](18-digest-rule-under-the-clamped-trigger.md) R4 found `TRIGGERED` is unreachable as
a persistent state under ticket 17's trigger — every detected name is `WATCHING` by construction — so
the state half would render one value for every row on every night.

**I2 is reinforced rather than disturbed.** A "broke today" badge would carry real information and was
declined for exactly the reason I2 gives: it is the diff-first surface, moved inside the app. The
break keeps the single home ticket 14 gave it — the digest — which is the file you may ignore at no
cost.

---

## Amendment from ticket 19 — I4's stop column is right, its base rate is not

[Ticket 19](19-fit-the-split-parameters.md) R2 measured the quantity I4's fourth column displays and
found the column well chosen but described backwards.

I4 justifies "Stop width ÷ 1×ADR" as "§7's veto, visible before you open anything — **a row at 0.97×
is nearly dead**", which reads as though most rows sit comfortably below 1.0 and the column exists to
catch the occasional straggler. Measured over 19,527 detections: the median row is at **1.28×**, and
**~92% of the nightly list sits above 1.0** — because `TIGHT_MULT` (1.5) *is* the stop budget, and the
cluster's ≤1.5×ADR span is what bounds it.

Nothing about the column's presence or position changes. Two things about its treatment do:

- **The highlight inverts.** Marking the rows that exceed 1×ADR would mark 92% of the list, which is
  not a mark. The **≤1×ADR minority** is the exceptional, affordable case and is what should be
  visually distinguished.
- **It is never a filter.** Ticket 19 R2 measured what filtering costs — 85% of ticket 15's graded
  cards, and preferentially the ones that graded *highest* — and declined it. §7 is enforced by the
  human at entry, against the real LOD stop the screen cannot see. The column exists to make that
  check free, not to pre-empt it.

Whether the *sort* should also know about the stop is not settled here — that is
[ticket 24](24-should-the-score-know-about-the-stop.md). I4's sort key remains the star score.
