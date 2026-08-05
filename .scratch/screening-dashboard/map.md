# Map: Qullamaggie Screening Dashboard v1

## Destination

A buildable v1 spec for a **locally-run**, single-user, EOD screening dashboard covering **IDX and US**,
implementing the **Breakout/Continuation setup only**: auto-detected setups with 1–5 star scores,
in-app charts, top-decile leaderboards per lookback, sector/theme leadership + rotation, and the
market regime filter. The spec is detailed enough to hand to a build session — no production code
is written during wayfinding.

## Notes

- **Domain**: equity momentum swing trading, Qullamaggie method. The canonical method reference is
  `references/qullamaggie-method.md` — every ticket should be resolved against it, and it already
  fixes many parameters (ADR definition, liquidity floors, stop and sizing rules, star rubric).
- **Skills to consult**: `/grilling` and `/domain-modeling` on every HITL ticket; `/research` for
  research tickets; `/prototype` for prototype tickets.
- **Standing constraints** (settled during charting, not up for re-litigation without saying so):
  - Both markets from day one.
  - Free data sources only — no paid feeds, no existing TradingView/broker subscription.
  - **Runs locally**, single user. No hosting, no free-tier limits, no auth in v1 — a local
    backend serving a local browser. Hosting is deferred (see Out of scope).
  - **A live backend is assumed.** The UI may query the store freely; it is not restricted to
    reading precomputed views. When hosting does arrive, a paid tier (~$10–20/mo) is accepted
    rather than contorting the design to fit a free tier.
  - EOD nightly cadence. No intraday, no streaming.
  - Python backend + TypeScript frontend.
  - Full auto-detection of the setup + a computed 1–5 star score (not just a ranked shortlist).
  - Charts rendered in-app, showing the evidence behind the score.
  - "Top decile" is ranked against the whole tradeable universe **per market**, not within sector.
- **Known risk carried into the map**: §3.5 double-weights *tightness* and *orderliness*, the two
  dimensions least amenable to automation. Setup detection is the highest-risk ticket on this map.
- **Standing property of the data layer** (found independently by tickets 01, 02 and 03): **Yahoo fails
  as silence.** Throttled requests return empty results — and for price history, the literal message
  "possibly delisted; no price data found". Every ingestion path must distinguish throttling from
  genuinely missing data, or bad runs silently shrink the universe while looking successful.

## Decisions so far

<!-- one line per resolved ticket: gist + link -->

- [Free EOD data sources for IDX](issues/01-idx-free-data-sources.md) — **yfinance `.JK`**, fallback a
  headless scrape of idx.co.id; Stockbit is ToS-barred and idx.co.id is Cloudflare-blocked. Universe
  enumeration solved (840 symbols in 0.8s); volume is **shares not lots**, so **292 names clear the
  Rp 1B/day floor**. Bulk OHLCV is fast (840 × 5y in 11.5s, ~50 MB) but rate limits bite immediately
  after. Two hazards: Yahoo applies **rights adjustments invisibly** (BBRI rescaled 10/11 with no
  split/dividend entry) so raw IDX prices are unrecoverable, and **4% of bars are phantom zero-volume**
  and must be dropped before any ADR or tightness math.

- [Free EOD data sources for US](issues/02-us-free-data-sources.md) — **yfinance is the single source
  for both markets** (same client, schema and sector taxonomy for `.JK` and US), fallback Massive
  (ex-Polygon) for US. Universe enumeration via Nasdaq Trader files → **5,711 symbols**. Rate limiting
  is mandatory: unthrottled returns only **52.9%** of the universe while reporting the losses as
  "possibly delisted"; **12 req/s gives 99.93% in 8.5 min**. Two hazards: the **last daily bar may be
  partial** while a session is open (proven — 14 minutes of trading dated as a full day), and delisted
  names return zero rows, so any backtest is survivorship-biased.

- [Free sector/industry classification for IDX and US](issues/03-sector-taxonomy-sources.md) —
  **Yahoo/Morningstar GECS is the sector axis for both markets**: one taxonomy, 99.7% measured coverage
  across 320 sampled tickers, no mapping table, no GICS licence exposure. IDX-IC is Cloudflare-blocked
  and not needed; GICS is contractually out. Two operational constraints fall out: sector costs one
  request per symbol (1–2h per full refresh, so cache incrementally) and **Yahoo throttling fails as
  silence** — must be distinguished from genuinely missing data. Theme *parity* across markets is the
  open scope risk, carried to ticket 07.

*(the hosting research also resolved, but its subject was subsequently ruled out of scope — see below)*

- [Universe definition and data hygiene](issues/05-universe-definition.md) — **288 IDX / 1,966 US names**,
  measured under the exact rule stack, not estimated. The universe is **liquidity + instrument type +
  listing age only**: median-20d `close × volume` ≥ Rp 1B / $20M, common stock only (ADRs kept), ≥ 20
  non-phantom bars. **ADR is a post-rank filter, not a gate** — gating would make decile denominators
  breathe with the volatility regime and would evict names on the eve of the move. Phantom bars
  (`volume == 0`) are dropped and windows count traded bars; an **80%/3-session density gate doubles as
  suspension detection**, so the Cloudflare-blocked IDX suspension list is never needed. **Absence of
  data means nothing** — membership is sticky, removal needs positive evidence, and runs resolving < 99%
  of symbols are quarantined rather than published. Provisional bars are dropped on an exchange-clock
  finality rule. **Adjusted everywhere except dollar volume, and no absolute-price rules** — which makes
  ticket 01's unrecoverable-raw-IDX-prices finding cost nothing, since almost every quantity in the
  method is a ratio and ratios survive adjustment. Nightly rebuild with a 0.8× hysteresis band. One
  principle unifies D3/D7/D11: **removal requires stronger evidence than admission.**

- [Market regime filter](issues/10-market-regime-filter.md) — **three states per market from one index
  each** (US `^IXIC`, IDX `^JKSE`), on simple `SMA10`/`SMA20` of daily closes. Slope is **sign-only**
  (`SMA[t]` vs `SMA[t-5]`), so the whole filter has **zero tunable parameters** — deliberate, because
  survivorship bias makes any threshold uncalibratable. `HOSTILE` = both falling and 10 below 20;
  `FRIENDLY` = close above both and both rising; `CHOPPY` = **the residual**, which is where §10's two
  named conditions leave a gap. The three are mutually exclusive by construction. Effect is **advisory
  only**: a per-market banner with a sizing posture (full / reduced / sit), and the candidate list is
  identical in all three states — regime never filters, reorders, or touches the star score. Breadth is
  **displayed but does not gate** (it is the measure survivorship bias corrupts most). Breakout
  follow-through is **captured nightly from day one but never shown or gated in v1** — it is the only
  unbiased regime signal available and is irrecoverable if not started at launch.

- [Ranking and decile model](issues/06-ranking-and-decile-model.md) — **the gate and the leaderboard are
  two different cuts**, which dissolves ticket 05's "a decile of 1,966 is unreviewable" hand-off. The
  §3.1 gate is a **union of top deciles across 1w/1m/3m/6m/12m** — measured at **566 US / 82 IDX**, so
  **"top decile" passes ~29% of the universe, not 10%**, and the 28.8%/28.5% agreement across two
  markets differing 7× in size shows a percentile gate is self-normalising. The leaderboard is **five
  separate boards per market, 30 rows each** — N=30 is simultaneously §1's "top 1–2% of gainers" on US
  and IDX's natural decile. Returns are **calendar-anchored on adjusted closes, which narrows D6**
  (traded-bar windows stay for ADR and dollar volume only). The model **reports rather than judges**:
  **pure return, no volatility adjustment** (normalising would replace up to 20 of 30 US rows), **no
  smoothing** (the 1w board turns over 16 of 30 nightly and that is honest), **ADR does nothing by
  default** — a column plus one toggle, off everywhere. Rows carry a **`k/5` breadth badge** (only 3 of
  1,964 US names lead all five windows) and a **`NEW` marker**; §1's "up ≥30% in 5 days" is a **flag on
  the 1w board**, with the accepted failure mode that a hot tape hides the names below rank 30. Ranking
  is a **shared service** — ticket 07 aggregates over its rank table rather than defining strength
  twice. Rank history persists nightly on a **rolling 2-year window**. The session also **reproduced
  ticket 05's universe exactly (1,966 / 288) from its written decisions alone**.

- [Sector/theme leadership and rotation model](issues/07-sector-theme-and-rotation-model.md) — **industry
  *is* the theme layer**, which dissolves ticket 03's four-way parity dilemma rather than deciding it:
  Yahoo returns `industry` in the *same* request as `sector`, so 145 industries arrive free on both
  markets — no scraper, no LLM line item, no curation, no staleness — and v1 stays entirely free-data. A
  narrative layer spanning industries ("nickel downstream", "GLP-1") is ruled **out of scope**. Sector
  strength is **share of members in that lookback's top decile, five numbers per sector** (1w/1m/3m/6m/12m),
  aggregated over ticket 06's rank table per R6 — per-lookback deciles, *not* the §3.1 union gate, which
  would park every sector near 29%. **Rotation is two sortable columns**: the **shape differential**
  `share(1w) − share(6m)` (zero tunables, no history, default sort) and a **20-session temporal delta**
  whose window is inherited from §2/§3.5's 10/20-day horizon, not invented — the trader overruled the
  session's sparkline-and-eyeball proposal and required it computed. **Quantization is an IDX problem**:
  one name moves IDX Utilities' share **10.0pp** (vs 0.3–1.7pp anywhere on US), and Technology topped the
  measured IDX rotation board at +21.4pp on *three stocks* — so a sector needs **`k ≥ 2` in the decile to
  top the board**, with `k/n` on every row; nothing is ever hidden, and shrinkage was rejected as smoothing.
  **IDX cannot carry an industry leaderboard** (87 industries, median size 2, 38 singletons), US can (139
  industries, median size 9, Biotechnology 107) — resolved as **one rule, `n ≥ 10` to be ranked**, yielding
  63 US rows and 7 IDX rows: parity of rule, not of result. §3.5's confirmation boolean is **leave-one-out
  sector share ≥ 10% on 1m** — the leave-one-out is load-bearing, because a candidate inflates its own
  sector and the naive rule fires 77–90%, making the point nearly free; the industry-peer alternative was
  rejected for swinging 24–55% (IDX) vs a flat 88–89% (US) and being unavailable to 38 IDX singletons. §10's pullback-RS is
  **emergent** — a decile is cross-sectional, so on a falling tape the 1m decile *is* what held up — surfaced
  as regime-conditional copy, with the washout inversion stated as a limit. Sector strength **never filters**.
  Cache: **new names block, 1/30th rolls nightly, a failed fetch never nulls**. The session also
  **reproduced the universe a third time (290/1,896)** and measured **1.2s Yahoo spacing as throttle-free**,
  halving ticket 03's assumed full-pass cost.

## Not yet specified

- **Validation / backtest.** How do we know the screen actually surfaces the right names? History depth
  is no longer the blocker — both markets have plenty (IDX back to ~2000–2004, US ample). The blockers
  are that detection isn't defined yet (ticket 08) and that **delisted names return zero rows on
  Yahoo**, so any replay is survivorship-biased upward with no free fix. The one concrete action is
  already assigned to ticket 12: start snapshotting listing files nightly, so a point-in-time universe
  accumulates from today whatever validation eventually looks like. **Ticket 05 added the layer above
  it** — nightly snapshots of universe *membership* (one row per name per night), so a future validation
  can ask what was actually rankable on a given night, not merely what was listed. **Ticket 10 adds a
  third** — every detected setup and its trigger level, written nightly from launch. All three exist for
  the same reason: they are unbiased *and* irrecoverable after the fact, so the clock has to start at
  launch. **Ticket 06 adds a fourth** — nightly percentile rank and raw return per (name, lookback), so
  a future validation can ask not just what was rankable but *where it ranked*. Together — what was
  listed, what was rankable, where it ranked, what was signalled — they are the seed of whatever
  validation eventually becomes possible. **Ticket 07 adds a fifth** — nightly sector and ranked-industry
  shares, so a future study can ask whether sector leadership actually preceded the moves, and can replay
  the rotation columns rather than only the per-name ranks. It is a few hundred KB a year and, like the
  other four, irrecoverable if not started at launch.
  **Two constraints ticket 06 puts on that seed, which sharpen this patch rather than clear it:** the
  rank stream is the first that **discards** — a rolling 2-year window was chosen deliberately, so a
  multi-year study is foreclosed unless a coarser permanent archive is added later (a few MB/year); and
  the stored ranks carry a **~1.5% noise floor** from denominator churn (30 US / 8 IDX names entering or
  leaving the universe overnight even with D11's hysteresis), so small percentile moves are not
  necessarily price moves. Whatever validation becomes possible has to be robust to both.
- **Alerting.** He hangs price alerts on the trendline. Whether v1 notifies at all, and through what
  channel, waits on detection being defined. Running locally narrows the options — a desktop
  notification or a nightly digest, not a push service.
- **Watchlist persistence and user state.** Whether the app remembers names you've marked, and what
  storage that implies, waits on the architecture ticket.
- **Chart rendering approach.** Library and how the detected trendline / MA context is drawn — waits
  on the dashboard IA ticket.
  <!-- "History depth" graduated into ticket 12: the data-source research it waited on is done, and
       ticket 05 fixed the demand side (24-month lookbacks + 20-bar minimum). It is now a storage
       decision, not fog. -->
  <!-- "Data quality handling on IDX" graduated: ticket 05 resolved phantom bars, rights adjustment
       and suspended names. The ARA/ARB remainder is now assigned to ticket 08, so it is no longer fog. -->
- **Survivorship bias.** Yahoo's screener enumerates only live names, so delisted history is not
  discoverable. Harmless for nightly scanning, potentially fatal for any backtest — folds into the
  validation patch above once that takes shape.

## Out of scope

- **Narrative theme layer spanning industries** — "nickel downstream", "GLP-1", "AI" as named, curated
  themes. Ruled out by [Sector/theme leadership and rotation model](issues/07-sector-theme-and-rotation-model.md):
  Yahoo's 145-industry level arrives free with sector and covers the theme question wherever the theme
  *is* an industry (most of the time on IDX). The remainder — genuinely cross-industry narratives — would
  cost either a paid LLM tagging pass, a US-only ETF-holdings scraper that breaks market parity, or
  ongoing hand-curation. Not on the route to a v1 spec. The option survey is preserved in
  [ticket 03's findings](research/03-sector-taxonomy.md) if it ever becomes its own effort.
- **Episodic Pivot (§4)** — deferred by the method reference itself; needs intraday/pre-market data.
- **Parabolic short (§5)** — not practically available on IDX, largest blow-up risk.
- **Position sizing calculator (§8)** — considered and ruled out of v1.
- **Trade journal / open position tracking (§9 sell-rule management)** — a second product.
- **Intraday or real-time data** — v1 is EOD only.
- **Multi-user / sharing** — single user.
- **Hosting, deployment, scheduling infrastructure, and auth** — v1 runs locally, so none of this is on
  the route to the destination. The research is already done and preserved for whenever hosting becomes
  a separate effort: [Free-tier hosting and scheduling](issues/04-free-tier-hosting-and-scheduling.md)
  → [findings](research/04-hosting-and-scheduling.md). Headline for that future effort: serverless
  execution timeouts rule out everything except GitHub Actions and Cloud Run Jobs, and no free hosted
  SQL can hold the bar history. A paid tier (~$10–20/mo) is pre-approved for it, so those free-tier
  findings are background rather than binding.
