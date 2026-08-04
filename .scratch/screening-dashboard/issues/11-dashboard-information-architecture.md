# Dashboard information architecture

Type: prototype
Status: open
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
