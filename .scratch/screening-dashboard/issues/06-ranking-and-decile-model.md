# Ranking and decile model

Type: grilling
Status: open
Blocked by: 05

## Question

How is "top decile" computed, over which periods, and what does the leaderboard actually show?

Settled during charting: ranking is against the **whole tradeable universe, per market**. Open:

- **Lookbacks** — §1 names 1/3/6/12/18/24 months for the gainers scan; §3.1 gates the setup on
  "top decile of 1–6 month returns". Which lookbacks does the app compute, which one gates the setup,
  and is the gate "top decile in *any* of 1/3/6m" or a composite?
- **Return calculation** — simple close-to-close on adjusted prices? Calendar months or trading days?
  What happens when a name lacks the full lookback (see universe minimum-age decision).
- **Composite RS score** — does the app produce a single weighted momentum rank (IBD-style) or keep the
  lookbacks separate? He talks in separate lookbacks; a composite is easier to sort by.
- **"Each period" in the ask** — the request was "top deciles each period". Does that mean a leaderboard
  per lookback, or a time series showing who has been in the top decile over successive weeks (i.e. how
  leadership is changing)? These are different features.
- **Decile vs top-N** — §1 says "top 1–2% of gainers" for a momentum leader; §3.1 says top decile.
  Reconcile: is the decile the universe gate and the top 1–2% a separate "leader" badge?
  **Ticket 05 makes this concrete and urgent.** Measured universe sizes are **288 IDX / 1,966 US**, so a
  top decile is **~29 names on IDX but ~197 on US** — unreviewable in a 10-minute nightly pass, and
  wildly lopsided between two markets shown side by side. §1's own top-1–2% gives ~30 on US, which
  matches IDX's decile almost exactly. So the real decision is whether the cut is constant **in rank**
  (a percentile, which scales with universe size) or constant **in count** (a top-N, which does not).
- **Per-lookback denominators differ** (ticket 05, D5). A name is ranked in a lookback only if it has
  that much history, so the 12-month population is smaller than the 1-month one. Ranking must handle a
  universe whose size varies by lookback — and "top decile" means a decile *of that lookback's*
  population.
- **Volatility adjustment** — should raw return be normalised by ADR? A 300% move in a 12-ADR name is a
  different thing from a 300% move in a 3-ADR name. He does not do this; decide whether we do.
- **Rank stability** — how much day-to-day churn is acceptable, and is any smoothing applied.
- **Persistence** — are historical ranks stored so leadership change is visible, and how far back.

This ticket also feeds the sector model — decide whether sector strength is aggregated from these same
member ranks or computed independently.
