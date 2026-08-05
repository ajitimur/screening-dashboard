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

- **Ticket 09 (star score calibration)** — two things land here.
  1. Per I3, the score is now the **default ordering** of the only list in the app, not a label on it.
     Calibration error shows up as the wrong name at the top of the screen, nightly.
  2. Per I8, v1 has **no rejected-candidates view**, so 09's prototype session is the only place the
     discarded set gets human eyes. It should look at rejects, not only accepts.
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
