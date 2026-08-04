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
  **Discharged by ticket 08** — both dimensions proved scorable (contraction against a √L baseline;
  churn ratio for orderliness), and the resulting detector has **zero tunable parameters**. The residual
  risk moved rather than vanished: it now sits in ticket 09, which is where a human eye first meets the
  computed score.
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

- [Setup detection algorithm](issues/08-setup-detection-algorithm.md) — **the highest-risk ticket resolved with
  zero tunable parameters**, which was not the expected outcome. Detection emits a **state, not an event**:
  every name currently in a valid base, nightly, with the breakout as a `WATCHING`→`TRIGGERED` transition —
  forced by ticket 10, since you cannot record a trigger for a break that already happened. The base is found
  by an **end-anchored backward search** (always ends on the last bar, only the start is searched), which
  **eliminates pivot detection** — the trap, because §3.2 says undercuts and overshoots are *desirable*, so a
  pivot detector fights the method at exactly the bars that mark the best setups. Validity is **§3.2's triangle
  test executed literally**: highs fit slopes ≤ 0, lows fit slopes ≥ 0, L ≥ 3 — and because a *fit* is not a
  monotonic test, piercing bars are the stated ideal rather than a tolerated exception. That test also
  **self-caps the search**, deleting the one free parameter: reaching back into the momentum leg tips the highs
  fit positive, so §3.1's "consolidation *after* the move" is enforced by geometry. **Every distance quantity
  over an end-anchored window is monotone in L**, so ranking windows by tightness *or* by MA proximity both
  collapse to L=3; the degeneracy is accepted rather than corrected — primary is the **shortest valid window**,
  which yields the earliest, nearest-the-MA trigger §3.2 argues for. Trigger is the **lower of the flat max-high
  and the fitted descending line**, so a base that sits still eventually triggers on its own. §7 gets teeth:
  stop estimated at the **base low**, and width > 1×ADR **rejects outright**. Both ×2 dimensions turned out
  scorable: **contraction** = how far the retained set's `range(L)` curve sits below its **√L random-walk
  baseline** (the affordability gate already measures *narrow*, so tightness scores only *narrowing*), and
  **orderliness** = **churn ratio**, Σ daily ranges ÷ envelope — which required correcting the ticket's own
  candidate: net-drift efficiency scores every good base as maximally disorderly, because a base is sideways by
  definition. MA catch-up is **one number** carrying §3.1's 20-over-10 preference for free. **Three knowing
  omissions**: §5's backside veto is unenforced (needs 60-min bars; a daily-65-EMA substitute was declined),
  IDX limit days are unhandled (they flatter *both* ×2 dimensions at once — carried to ticket 09), and only
  **dry-up** is scored, since expansion exists only at the break and scoring it would make the score
  state-dependent. Gate is **top decile in any of 1m/3m/6m** off ticket 06's rank table — 06's 1w and 12m
  windows excluded as burst and stale. **Every scored quantity is a ratio**, confirming ticket 05's prediction
  that ticket 01's unrecoverable raw IDX prices cost nothing.

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
  validation eventually becomes possible.
  **Two constraints ticket 06 puts on that seed, which sharpen this patch rather than clear it:** the
  rank stream is the first that **discards** — a rolling 2-year window was chosen deliberately, so a
  multi-year study is foreclosed unless a coarser permanent archive is added later (a few MB/year); and
  the stored ranks carry a **~1.5% noise floor** from denominator churn (30 US / 8 IDX names entering or
  leaving the universe overnight even with D11's hysteresis), so small percentile moves are not
  necessarily price moves. Whatever validation becomes possible has to be robust to both.
  **Ticket 08 adds a fifth stream** — the raw signal vector behind every detected setup, persisted nightly
  even though the emitted interface only carries the score and the chart bundle. It exists for the same
  reason as the other four: it is the only way a later recalibration can be replayed *backwards* over
  accumulated history rather than merely applied forward. It also sharpens what validation must eventually
  measure, because ticket 08 shipped three knowing omissions — the unenforced backside veto, unhandled IDX
  limit days, and a half-measured volume dimension — each of which is a hypothesis about what does not
  matter, and none of which can be tested until there is something to test against.
  <!-- "Alerting" graduated into ticket 14: ticket 08 defined a stable trigger level per detected setup,
       which is the thing an alert hangs on. It is now a channel-and-threshold decision, not fog. -->
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
