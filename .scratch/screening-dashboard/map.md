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
  computed score. **Ticket 09 collected on that risk.** The score as 08 specified it is *uncorrelated*
  with the trader's eye (r = −0.043), because both ×2 dimensions turned out to track **base length**,
  which §3.5 never names and the trader reads the opposite way. 08's zero-parameter property does not
  survive the correction — the count is now two. The structure is fixed; the numbers are not, and the
  remainder is ticket 15. **Ticket 16 reopened the structure below the score.** The trigger geometry and
  the *window* it is computed over are both in question — D4's primary window is 3 bars on 52% of
  detections — and D6 has stopped being a hard gate, which leaves D7's ×2 tightness dimension owing the
  "narrow" half it had delegated to that gate. Ticket 17 carries all of it; ticket 15 is blocked behind
  it, because a rubric calibrated on the current detector would be calibrated on a shape that may move.
  **Ticket 17 moved it.** The base/cluster split is adopted whole, so the shape ticket 15 must calibrate
  on is the new one — and the risk did not so much move as *concentrate*: the ×2 tightness dimension now
  has **no working definition at all**, because every candidate that correlates with the eye turns out to
  be base length in disguise. The map has therefore spent three tickets (09, 15, 17) discovering the same
  thing — **that the two ×2 dimensions §3.5 leans hardest on are the two the eye does not confirm** — and
  ticket 15 is where it either gets scored or gets declared unscorable. The other half of the risk is
  newer and blunter: the detector was swapped on a **null** name-level comparison, so the nightly list is
  three-quarters new on the strength of a *drawing* preference rather than a *name* preference.
  **Ticket 18 found the swapped geometry is simpler than either 16 or 17 recorded it**: the fitted line
  cannot reach the trigger at all — the trigger is the cluster high by identity — so the drawing the
  trader endorsed 10 of 11 times and the level the screen fires on are **two separate objects**, and
  only the second is what ticket 19 will be fitting. This does not reopen the swap, but it narrows
  what the endorsement covered. **Ticket 19 fitted neither, and found a third thing instead**: the
  parameter it was sent to fit is a *risk* parameter, not a detection one, and on what it recorded as three
  independent measurements **the trader's eye prefers the setups the trader's own §7 stop rule rejects**.
  The map's standing risk is therefore no longer only that the two ×2 dimensions are unconfirmed — it is
  that the score, the eye and the risk rule may not be measuring the same thing at all. **Ticket 24 shrank
  that risk without measuring anything new.** Stop width *is* the cluster's height by identity, so §7's cap
  and §3.5's ×2 tightness dimension read **one ruler, not two** — which collapses ticket 19's "three
  independent measurements" into **one**, at r = +0.140, p = 0.286, on a population entirely selected under
  1.5. And the cluster-low stop is a floor §7 never names: §7's stated default is the **breakout day's low**,
  a *daily* quantity, so the 92% figure may be an artefact of the ruler rather than a disagreement. That
  measurement is named, cheap, and knowingly unrun — parked below.
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
  that ticket 01's unrecoverable raw IDX prices cost nothing. **D2/D5 are now qualified**: the boundaries are
  fitted by least squares, which puts the upper line through the *middle* of the highs, and that alone accounts
  for the already-breached triggers ticket 09 found (13.3% → 0.8% under an envelope fit). Reopened as
  [Trendline fitting: envelope or least squares?](issues/16-trendline-fitting-envelope-vs-least-squares.md).

- [Star score calibration](issues/09-star-score-calibration.md) — **the score does not agree with the
  eye, and it is not a threshold problem**: blind-graded over 27 charts the two are *uncorrelated*
  (r = **−0.043**, 44% within one star, machine +0.74★ too generous). The errors lie on one axis —
  **the star score is largely a proxy for base length**, with share reaching ≥4★ running **0.9% → 63.6%**
  as the base grows from 3–5 to 41–60 bars, because contraction rises with L and churn/L falls with it.
  So **4 of the 10 points collapse onto an axis §3.5 never names**, and the trader reads it *inverted*
  (L correlates −0.558 with him, +0.622 with the machine — the only signal clearing significance).
  **Root cause: 08's D14 is false** — the triangle test does not self-cap (22.9% of bases ≥ 30 bars,
  1.8% hit the 60-bar "never binds" bound), so §3.4's *"months of sideways"* anti-pattern is what tops
  the score. Two more 08 corrections: **D7's contraction sign is inverted** (end-anchored windows grow
  *faster* than √L, not flatter — flat channel 0.86 vs tight cone 1.59 on controlled synthetics) and
  **D8's churn is not scale-free in L** (2.20 → 18.36 at fixed disorder; `churn/L` fixes it). The fix
  that works is **decoupling the measurement**, not penalising the symptom: a length penalty alone moves
  agreement to only +0.076, while measuring both ×2 dims over `min(L, 20)` reaches **+0.259 and 63%
  within one star**. Base length is a **penalty, not a gate** (trader's call), paid for by the
  higher-lows point, which F4 showed is **free** — true for 92% of detections by construction. Unmeasurable
  dimensions now score **neutral, not zero** (they were penalising the tight 3-bar bases hardest). **The
  thresholds are still not set** — at n=27 significance needs |r| > 0.38 and the best variant reaches
  0.26 — so the ticket's asked-for "concrete thresholds" is a **shortfall**, carried to ticket 15.
  **D13 inverted**: fully-locked IDX bases reach 4★ *zero* times (the ADR dimension kills them free),
  while **partially** locked ones score best of any group (24.9% ≥4★) — so 08's declined liveness floor
  would have aimed at the wrong case. **D5's trigger survives unexamined** (the eye was indifferent,
  r = +0.012, which is not vindication). Outcomes cannot arbitrate any of it: ~672 triggered setups per
  band are needed to resolve 0.3R, and the top band flipped ordering when one ×1 dimension completed.

- [Dashboard information architecture](issues/11-dashboard-information-architecture.md) — **two screens,
  and market is the top-level axis**: `IDX` and `US` are tabs worked as **two short sittings**, each after
  its own close, which dissolves the staleness problem rather than labelling it — there is no coherent
  "tonight" spanning two markets that close hours apart. Three IAs were built and switched side by side
  ([prototype](prototypes/11-dashboard-ia.html)); the two rejected ones are the finding. **The session is a
  surface you scan, not a queue you finish** — the diff-first landing was put and rejected, so **v1 has no
  "what changed since yesterday" surface anywhere**, and ticket 08's `WATCHING`→`TRIGGERED` transition is
  computed and persisted but never surfaced. That abstention is what ticket 14 now has to answer. The list
  sorts by **star score descending** — proximity to the trigger is a column, not the sort, because sorting
  by distance puts a 2★ barcode above a 5★ base and defending against that needs a star floor, i.e. a
  tunable. **This promotes ticket 09 from labelling to ordering**: a miscalibrated score now puts the wrong
  name at the top of the only list in the app, nightly. **Ticket 09 then collected on exactly that** —
  the score is *uncorrelated* with the eye (r = −0.043) and its thresholds are still unset, so until
  ticket 15 lands the default sort orders by a number known not to agree with the trader. The IA
  decision stands; what changed is that its cost is now measured rather than hypothetical. **Six columns** (ticker, score+state, distance,
  stop ÷1×ADR, industry, `k/5`) — the row decides whether to open the chart, the chart decides whether to
  trade; ADR, dollar volume, `L` and the five ranks were cut as near-constant night to night. The chart
  panel **settles ticket 08's provisional D16 bundle**: §2's full MA set including the 65 EMA, the
  **primary window only** (drawing D3's retained set would render the degeneracy, not the setup), both
  fitted lines drawn *as fits* so candles pierce them per §3.2, trigger and base-low stop as rules, and
  volume dry-up but **no expansion** — it exists only at the break. The §3.5 breakdown sits adjacent
  because a sort key you cannot audit is one you will not trust. **Sector rotation is in the workbench**
  (ticket 07 made it a scoring input, not a report), and carries a **`Δ20d` rank-movement column** added by
  amendment — no new data and no new window (ticket 07 S9 already persists nightly shares, and 20 sessions
  is S3's own), joining rather than replacing the share deltas, and **greyed where the move rests on `k < 2`
  names**: on the fixtures IDX Utilities moves 6th→3rd on **2 names of 10** while every US move rests on
  25–53, so ticket 07's quantization asymmetry resurfaces one layer up. **The five leaderboards are a peer
  tab off the nightly path**, since ticket 08's D15 already gates on decile membership so the boards
  re-read an input to a filter that has already run. **No rejected-candidates view in v1** — overruled against a live
  counter-argument (a zero-parameter detector, never checked against a real chart, with three knowing
  omissions), so the inspection of the discarded set was handed to ticket 09 as the only place it could
  happen — **and ticket 09 did not do it**: its deck graded detections, not rejects, so that obligation
  is currently unowned and belongs on ticket 15. **I5 was never implemented**: ticket 09's chart draws the
  retained set *and* fits the triangle over the longest window while the trigger comes from the shortest —
  the exact rendering I5 ruled out. A conformance bug against a resolved decision, noted in
  [ticket 16](issues/16-trendline-fitting-envelope-vs-least-squares.md) alongside the fitting question the
  trader raised from the same charts.

- [Trendline fitting: envelope or least squares?](issues/16-trendline-fitting-envelope-vs-least-squares.md) —
  **the fit was the smallest of three levers, and the answer is mostly "not this ticket".** Ticket 09's
  F3 is confirmed an artefact of where the line sits (already-breached **16.0% → 2.1%** under an
  envelope, → 0.2% under q-scanner's clamp) — so D5's `min()` rule was not the culprit ticket 08
  suspected. But the reference implementation **does not derive its trigger from the line at all**: it
  clamps **up** to the cluster high where D5 clamps **down**, anchors on the trailing cluster, and stops
  at the cluster low. That clamp binds on 82% of detections, making OLS and envelope numerically
  identical where it applies. Underneath both, **D4's primary window is 3 bars on 52% of detections**, so
  no fit means much where the trigger is computed — a degeneracy ticket 08 accepted knowingly for
  tightness and MA proximity, whose defence does not carry to a line fit. **D6 is no longer a gate**
  (trader's call: the stop is an entry-time judgement, not a screening criterion) — but that alone takes
  the list from ~64 to **~314 US names a night**, because D6 was silently doing §3.4's looseness
  auto-reject as well as §7's affordability test. The two are separated: stop width is shown and
  sorted on, never cut; a looseness cut stays as a property of the **base**. Leaves **D7 owing its
  "narrow" half**, which it had delegated to the gate. Ticket 11's I5 conformance bug fixed in
  `chart16.py`. The eye question was **not** asked — a blind A/B deck is built but its cards inherit
  the 3-bar median. Window and looseness cut graduated to
  [ticket 17](issues/17-base-cluster-split.md).

- [Replace the window rule with a base/cluster split?](issues/17-base-cluster-split.md) — **yes, whole:
  detection and description.** Ticket 16's reassurance that "the list lands where it already is" is true
  of the count and **false of the contents** — the two detectors overlap on **26%** of picks (per night
  US 21.3 vs 20.4 names, **5.5 shared**), so list length is the one property that cannot tell them apart.
  The 75-card blind deck splits cleanly: on **the names** the split's picks beat the ones it drops by only
  +0.40★, **p = 0.298** — null, and it would need ~140 cards an arm rather than 20; on **the drawing** the
  trader picked the split's base+cluster **10 of 11** (p = 0.011) over a median 3-bar window against an
  18-bar base, answering ticket 16's unasked question *against the window* rather than between the two
  line fits. The session recommended taking the geometry only and keeping 08's search (measured: `08 +
  a cluster ≤1.25×ADR` restores today's ~59 US/night for **one** parameter, leaving ticket 15's rubric
  intact — kept in R6 as the cheap fallback); **the trader took the full split**, accepting that the list
  changes by three quarters of its contents on a name-level result that did not clear significance, and
  that refitting ticket 15 in between makes it hard to reverse. **D3, D4, D5, D9/D14 are deleted or
  replaced** (trigger clamps *up* to the cluster high, stop moves to the cluster low and is bounded
  ≤1.5×ADR by construction, so D6 is unnecessary rather than merely un-gated); §3.2's piercing, the
  elimination of pivot detection, end-anchoring and D15 stand. **D7 is the open wound**: with the retained
  set gone, every candidate tightness measure that correlates with the eye **collapses to zero under a
  base-length control** — ticket 09's failure mode in new clothing — and the "narrow" half is compressed
  by construction (ceiling 1.50, IQR 1.20–1.42), so whether the ×2 dimension is scorable at all is now
  ticket 15's risk. **One new signal, the only length-free one either ticket found**: cluster length k,
  partial r **+0.260** in-sample and **+0.218** out-of-sample. **The zero-parameter property is gone for
  good — the bill is 22, none fitted**, and `TIGHT_MULT` alone swings the list **63%** (→ ticket 19). The
  session also **corrected its own finding**: the split does *not* inherit ticket 09's base-length problem
  (−0.375 in-sample did not reproduce, +0.029 on fresh grades — an artefact of deck A's population).
  Knock-ons: ticket 11's I5 amended (the chart draws the base with the cluster shaded), ticket 15
  re-scoped, ticket 14 reopened as ticket 18.

- [Alerting on the trigger level](issues/14-alerting-and-trigger-notification.md) — **v1 does not alert.**
  The nightly run writes **one dated Markdown digest per market** (`digests/<market>/<session>.md`) and that
  is the whole notification layer — no notification, no push, no screen. A channel was rejected as ticket
  11's I2 reversed by the back door: an EOD app can only fire after the close, so an alert is the
  diff-first landing screen I2 already refused, delivered outside the app. The digest **stores nothing new**
  — ticket 08's D1 transitions are already persisted for ticket 10 — so it is a *rendering*, backfillable
  over history rather than only forward. **Only real breaks are reported**, which ticket 09's D10 forced:
  98.3% of triggers are the fitted line, so the level falls nightly and "crossed" splits three ways —
  price rose through it (**reported**), the line descended to meet a flat name (**not**), or the name was
  born triggered (16.4%, **not**). Types 2 and 3 stay computed and persisted, never rendered; reporting the
  arrival of a level 08's D5 *designed* to descend is reporting a parameter choice back to yourself. The
  accepted cost is that if D5's early trigger is right, v1 withholds the earliest signal it produces —
  **so if ticket 15 revisits D5, this reopens.** A break is fixed as **`close_today > trigger_yesterday`**
  (08 D1 never fixed which quantity crosses): comparing to yesterday's level makes the crossing survive
  holding the line still, which is exact attribution with **no new parameter**. The durable output is a
  rule — **the digest carries only what the app structurally cannot show you** — which admits the break
  (I2 left it homeless) and excludes new 4–5★ setups (already top of the star-sorted list, and a threshold
  would be the layer's first tunable). It also means the digest cannot grow into an alerting layer by
  accretion. Rows carry I4's decision columns plus close, yesterday's trigger and % through: **a pointer,
  never enough to trade from**, since §7's affordability is read off the chart geometrically. **Empty
  nights still write the file**, so a missing file means a failed run — the map's "Yahoo fails as silence"
  property, bought for free. *(A2's three-way taxonomy and A3's attribution argument are superseded by
  ticket 18 below: the rule and the artifact stand, the reasoning under them does not, and the 16.4%
  born-triggered figure is void.)*

- [What does the digest report when the trigger no longer descends?](issues/18-digest-rule-under-the-clamped-trigger.md) —
  **ticket 14's rule survives whole and its taxonomy does not, because two of its three buckets turn
  out to be unreachable rather than rare.** The finding underneath is an identity, not a measurement:
  the envelope is anchored at the cluster's max high and searched over non-positive slopes only, so
  **the fitted line can never exceed the cluster high and the `max()` clamp is dead code** — the
  trigger *is* the cluster high, at 100.0% of 29,242 detections, superseding ticket 16's 82% and
  correcting ticket 17's R3. Ticket 16's envelope-vs-OLS work is not wasted but never reaches the
  trigger; it gates `line_ok` and draws the chart. Because the cluster window **includes today**,
  `trigger ≥ high ≥ close` always, so a detected name is never above its own level: type 2 measured
  **0** and type 3 **2 in 29,242** against the 16.4% ticket 14 assumed. "Report only type 1" and
  "report every crossing" are therefore the same rule, and **A2 becomes the second** — the taxonomy was
  scaffolding under A4's principle, and the rule stands unmoved when it comes down. **A3 survives
  verbatim with its justification swapped**: attribution is spent, and what the yesterday-comparison
  now buys is **recency** — and it means something more literal, since `trigger_yesterday` is the
  highest high of the k bars ending yesterday, making the digest **a k-bar closing breakout** where k
  is the tightness test's pick (median 4). Its cost is the lapsed resumers it cannot see: closing that
  hole takes US from **7.0 to 31.0 rows a night** against a level a median 13 sessions old at +4.92%,
  so ~2.9 US rows/night of 2–3 session lapses are knowingly withheld — **and the session withdrew its
  own defence** that these are merely deferred (only 8.6% surface within 5 sessions). That replaces
  ticket 14's accepted cost, which is **discharged**: nothing is withheld on D5's early-trigger grounds
  now. **The break is an event, not a state** — the cluster rolls forward to swallow the breakout bar,
  so 100% of names still detected the night after a break are back below their new level, which amends
  **08's D1** and costs **11's I4** its state column (five columns, not six), while I2 is reinforced:
  the break keeps its single home in the file you may ignore. That re-arming lets one name be reported
  twice, so **every break is reported and repeats are marked**, not suppressed — they land at a
  *higher* price (median +1.10%, 0.7% lower), and both suppression rules were declined, the
  parameter-free one for silently withholding a second, higher break. Volume **~7.0 US / 0.9 IDX per
  night** (upper bound, no decile gate). **The reopen condition is re-armed against ticket 19, not 15**:
  `TIGHT_MULT`/`K_MIN`/`K_MAX` define the cluster and the cluster high is the trigger, so no *rule*
  here depends on them and every *number* does. First scan on this map to run **consecutive daily
  bars** — every prior ticket's 1-in-3 grid could not see a night-over-night transition at all.

- [Second grading round: fix the star-score thresholds](issues/15-star-score-second-grading-round.md) —
  **the rubric is fitted on the split, and it agrees with the eye for the first time on this structure**:
  out-of-fold **r = +0.255** (n=120, significance 0.180), mean error 1.11★, within one star 60%,
  calibration **monotone** across predicted bands for the first time on this map. **Tightness is a
  packing count, not a width** — D3's retained set is gone, every measure of *narrowness* fails on the
  population the rubric ranks, and **cluster length k** is the only candidate that replicates
  (+0.196 fresh, +0.327 on mixed cards, both length-free), because the cluster is *selected* to fit
  under `TIGHT_MULT × ADR` so its width is spent by the selection. k clears its pre-registered floor,
  so **ticket 17's R6 fallback does not fire**. **Orderliness needed a new shape**: on a ~14-bar base
  the one-sided cut is counterproductive and the fit gave its point to 99% of cards — not a sign error
  (a synthetic control confirms churn/L still measures disorder at every length) but a **leak**, since
  the gap between an *orderly* base and a *gap-then-dead* one narrows 2.9× → **1.8×** → 1.65× as L goes
  3 → 14 → 30, so a low churn/L stops meaning orderly and starts meaning quiet. Now a **band**,
  `0.275 ≤ churn/L ≤ 0.50`, losing the point at both ends — trader's call, and **chosen after seeing
  the grades**, so it is a hypothesis with fitted numbers rather than a confirmed result. **D10's MA
  distance is retired** (partial r +0.010, p = 0.93; the split's catch-up test already gates every
  survivor) leaving "SMA20 rising", so the free numbers went 6 → 4 → 5. **The 4★ cut stands a third
  time and precision at the trade line is 0.53**, up from 0.37 — the number ticket 11 depends on,
  since the score sorts the only list in the app. Two method findings outlive the numbers: round 2's
  **coordinate-descent fitter does not reach the optimum of its own objective** here (mae 1.0875 vs
  1.0292 exhaustive on the identical grid) and settled somewhere degenerate that read +0.060
  out-of-fold — fixed, with round 2's own thresholds re-checked and unaffected; and **the two earlier
  graded sets are not poolable** (+0.69★, p = 0.044), which is why round 3 re-collected on the split's
  population with every card rendered **bare**. **D13's partial-lock probe is de-scoped** — 98.1% of
  accepted IDX detections have zero collapsed bars, so the population ticket 09 sized it for is gone.
  **What it could not settle graduated to [ticket 20](issues/20-confirm-the-band-and-measure-the-ceiling.md)**:
  the band's confirmation, per-market calibration (**still zero graded IDX cards on any structure**),
  the rejected candidates, and **the test–retest ceiling — unmeasured for the second round running**,
  so by its own pre-registration none of the thresholds above is final.

- [Confirm the orderliness band, and measure the ceiling every correlation is judged against](issues/20-confirm-the-band-and-measure-the-ceiling.md)
  — **the eye is reproducible and the rubric is weak, which is the opposite of what was feared.**
  The **test–retest ceiling is +0.808** (12 pairs, mean absolute difference 0.58★), measured for the
  first time after two rounds of going unmeasured, so R3 §2's "published against an unmeasured
  ceiling" caveat is **discharged** — and every correlation on this map now reads against +0.81
  rather than an unknown maximum. That reframes ticket 15: **+0.255 is not a rubric against a noisy
  target but a weak rubric against a reproducible one**, capturing about a third of what is
  achievable, so closing that gap is the highest-value move left on the score. **The band FAILED its
  pre-registered bar** — out-of-fold **+0.120** against +0.20 on 194 fresh cards, and not a fold-split
  artefact (median +0.171 over 25 assignments, clearing the bar 20% of the time) — **so it is not
  credited and ticket 15's +0.255 stays optimistic. But §6's remedy was refused**, trader's call,
  because the same grades refute it: dropping orderliness costs 0.10 r and 13pp of within-one-star,
  while the dimension's partial r controlling base length is **+0.302**, the strongest single
  dimension on this map, 43% of cards fall inside the band (against A3's 99%-degenerate failure), and
  A3's thresholds applied **frozen** score **+0.240**, above the bar. Orderliness is kept and A3's
  thresholds stand as **explicitly provisional**. **What failed is the objective, not the band** —
  refit on E3 every fold runs `ord_lo` to 0.1 and `ord_hi` to 0.6, the widest values on the grid,
  then scores worse than the band it abandoned; mae is a level statistic on a flat surface, which is
  `REFIT_FINDINGS.md`'s round-2 complaint returning as instability rather than a local minimum. So
  **no threshold on this map is final, for a reason that is now named**, and that graduated to
  [ticket 21](issues/21-the-fitting-objective-does-not-identify-the-dimensions.md). Pooling A3 with
  E3 was **recorded and refused** (+0.204 at n=314, but a +0.30★ level offset at p ≈ 0.035 — the same
  ground R3 refused round 2 on). The two carried obligations are ticketed rather than passed a fourth
  time: [ticket 22](issues/22-idx-per-market-calibration.md) and
  [ticket 23](issues/23-the-rejected-candidates.md), whose decks are already rendered and whose 12
  further repeats would halve the ceiling's error.

- [Architecture and local runtime shape](issues/12-architecture-and-deployment.md) — **one DuckDB file,
  one command per market, and every derived table is dated rows.** A4 is the load-bearing one: universe
  membership, ranks, sector shares, detections, scores and signal vectors are all keyed by
  `(market, session, …)` and appended, which **collapses the map's six owed capture streams into the normal
  write path** — the thing the app reads *is* the archive, so they cannot disagree, ticket 14's digest is
  backfillable as it assumed, and ticket 15 can replay a corrected rubric backwards. Derived rows are
  **written once and never rewritten** (rewriting after a rescale would inject look-ahead into the streams
  that exist *because* they are unbiased), so backfill fills only absent sessions. The store is one file
  because **the freeze tickets 08/09/15 need is then `cp`** — footprint measured at ~580 MB for 10y × 6,550
  symbols, not estimated. The ingest set is the **enumerated** universe (~6,550, not 2,254) since liquidity
  is measured *from* bars. Runs are **per market** per ticket 11's I1 — two `launchd` jobs (≥19:00 WIB,
  ≥17:00 ET, firing on wake if missed) plus run-on-open, because a ~9-minute US pull does not fit §1's
  10-minute budget. Missed sessions are **backfilled for everything derivable**; listing files and sector
  labels are stamped as-of and never faked. **A3 is a stated defect, not a clean decision**: ingest is
  incremental with a weekly full refresh and **no drift detector** — two repairs were put and declined
  (a 20-bar overlap check costing *zero* extra requests, and an off-cycle refetch on reported actions) — so
  for up to six days a corporate action leaves a **seam that reads as a real overnight gap**, which ticket
  08's detector reads as price action. Bounded, self-healing, and the **cheapest of the map's four knowing
  omissions to reverse**. Also: resource endpoints with the frontend composing, one repo with TS types
  generated from OpenAPI, 10 years of history, and **lightweight-charts** — ticket 11's handed-down "how" —
  porting `renderChart.ts` from `~/Projects/q-scanner-v2`, whose remaining architecture was put as an
  explicit fork and **declined**.

- [Fit the split's 22 parameters, or accept them as borrowed defaults](issues/19-fit-the-split-parameters.md) —
  **nothing is fitted, and that is the answer.** Of 22 numbers **five can move anything**; three are
  provably redundant and deleted (`MA_PROX_ADR` dead; `OVER_W`/`UNDER_W` are one *ratio* — measured
  byte-identical lists; `MAX_OVERSHOOT_FRAC` catches 4.4% the ADR test misses; and the **prior-move floor
  duplicates the decile gate**, which cuts 89.4% of what the floor passes against the floor's 7.7%).
  `SLOPE_STEPS` converges at 25 of 800 steps and `K_MAX` moves the list −1.7% at 9 — frozen, not fitted.
  The headline is that **`TIGHT_MULT` is not a detection parameter, it is the stop budget**: the cluster
  spans ≤ `TIGHT_MULT`×ADR and the stop runs trigger→cluster-low, and against §7's 1×ADR cap **92% of the
  nightly list is a no-trade**. Ticket 08 gated exactly this (D6); ticket 17 deleted the gate on an argument
  about *form* that was never paired with this number. Restoring the gate was measured and **declined**: it
  keeps only 8.5% of detections, skews survivors to high volatility (ADR 6%→10%, prior move 104%→177%), and
  **removes 85% of ticket 15's graded cards — the ones that graded *higher*** (2.91 removed vs 2.44 kept).
  That is one of three measurements all pointing the same way: **the eye prefers what the stop rule
  rejects**. So §7 moves to the *display* — stop width is shown and sorted on, never filtered on — and
  enforcement stays with the human at entry, where the real LOD stop is visible. Also: **one parameter set
  serves both markets** (IDX tracks US to two decimals across the grid), D13's collapsed-bar hole stays
  closed at 98.5%, ticket 18's reopen condition is **discharged** (none of `TIGHT_MULT`/`K_MIN`/`K_MAX`
  moved), and ticket 17's 63% swing is restated: it was measured on the **ungated** list, and the decile
  gate is the far stronger filter. What it could not settle became
  [ticket 24](issues/24-should-the-score-know-about-the-stop.md) — the score sorts a list that is 92%
  unaffordable, and the rubric has already learned to reward wide stops without anyone deciding it should.

- [Should the star score and the digest know about the stop?](issues/24-should-the-score-know-about-the-stop.md)
  — **no, because "stop width" is not a risk quantity — it is the cluster's height, by identity.** The
  trigger is the cluster high (ticket 18) and the stop runs to the cluster low, so `stop_adr` **is** the
  cluster's range in ADR — the *narrowness* measure [ticket 15](issues/15-star-score-second-grading-round.md)
  already retired, because the cluster is selected to fit under `TIGHT_MULT × ADR` and its width is spent
  by the selection. Two things follow. **§7's cap and §3.5's ×2 tightness dimension are one ruler**, so the
  "eye vs rubric" and "eye vs stop rule" tensions the map recorded separately are one tension — and ticket
  19's *three independent measurements* are **one**, the same scalar binned two ways, at **r = +0.140,
  p = 0.286** on a population every member of which was selected under 1.5. **The score therefore learns
  nothing about the stop** — no dimension, no penalty, no tiebreak (ticket 19 R2's sortable column already
  serves that). The ticket's own premise that the rubric "has already learned to reward wide stops" is
  **unproven and mis-routed**: ticket 15's ×2 tightness is **cluster length k**, a bar count, not a width —
  but k and stop width move together across ticket 19's grid, so k may **buy its bars by spending range**.
  The grid cannot say, because it moves the cap; the within-setting sign is genuinely unknown. So the
  decision rests on the stronger reason — **do not add a penalty that may be fighting k, the one dimension
  on this map that replicates.** **The bigger finding is that part 3 was never an intraday question**: §7's
  stated default stop is the **low of the breakout day**, a *daily* bar, known at the close that renders the
  digest — so the cluster low is a floor §7 never names, and **ticket 19's "92% are no-trades" may be an
  artefact of the ruler, not a disagreement with the eye.** Hence the split: the **watchlist** shows
  `trigger − cluster_low` (pre-break, nothing better exists), the **digest** shows `entry − breakout_day_low`
  (§7's actual rule, free — no new data, parameter or capture stream), and **neither marks a no-trade** —
  the watchlist because a flag firing on 92% is not a flag, the digest because the base rate under the
  corrected ruler is unmeasured. Digest *membership* still ignores the stop entirely (18 R5 stands; ~7.0 US
  rows a night is too small to cut on a pessimistic proxy). **The measurement was put and declined** —
  trader's call — so every decision here is the conservative one under that ignorance, and the two owed
  numbers are parked as fog rather than ticketed. Ticket 19 R2's show-don't-filter was not re-litigated.

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
  **Ticket 08 adds a fifth stream** — the raw signal vector behind every detected setup, persisted nightly
  even though the emitted interface only carries the score and the chart bundle. It exists for the same
  reason as the other four: it is the only way a later recalibration can be replayed *backwards* over
  accumulated history rather than merely applied forward. It also sharpens what validation must eventually
  measure, because ticket 08 shipped three knowing omissions — the unenforced backside veto, unhandled IDX
  limit days, and a half-measured volume dimension — each of which is a hypothesis about what does not
  matter, and none of which can be tested until there is something to test against.
  **Ticket 09 sharpened this patch considerably rather than adding to it.** It ran the first real
  measurement against forward outcomes and found the noise floor: **~672 triggered setups per band** to
  resolve a 0.3R difference, against 33 available at five stars. It also demonstrated the fragility
  concretely — completing a single ×1 dimension reversed the ordering of the top two star bands. And on
  the 27 graded charts **neither the trader nor the machine graded in the direction outcomes went**,
  which at n=27 means nothing on its own but is exactly the kind of result a later study will
  rediscover and over-read. Whatever validation becomes possible needs to clear that bar before any
  claim about score quality is made from returns.
  **Ticket 20 sharpened that warning by removing one of its escape routes.** The test–retest ceiling
  is **+0.808**, so the eye is reproducible to within half a star and "the grader is just noisy" is no
  longer available as an explanation for an eye-versus-outcome disagreement. If a later study
  reproduces ticket 09's finding at a workable n, it is a **real disagreement between the eye and
  returns** — and the map has no rule for which one wins, because the eye is the arbiter only by
  necessity (~672 triggered setups per band to resolve 0.3R). That question is not fog to be cleared
  by more grading, and it is the one place where a validation result could invalidate the star score
  rather than merely calibrate it.
  **Ticket 14 added a sixth stream and a named hypothesis.** Its A2 excludes two of the three crossing
  types from the digest — line-descent crossings and the 16.4% born triggered — while still persisting
  them. That is a claim that neither is actionable, and like ticket 08's three omissions it is untestable
  until there is forward history: the excluded types are exactly the population a later study can score
  against outcomes, because they were recorded rather than discarded. Validation therefore inherits a
  concrete first question — do type-2 crossings behave differently from type-1 ones? — which is cheaper
  than the star-band question the noise floor above makes nearly unaffordable. **Ticket 18 voided that
  question rather than narrowing it**: type 2 measures **0** and type 3 **2 in 29,242 detections**,
  because the trigger is the cluster high and the cluster includes today, so neither population exists
  to be scored. What replaces it is the population ticket 18 knowingly withholds — the ~2.9 US rows a
  night of names that lapse out of detection for 2–3 sessions and return above their old level. They
  are recorded (dated detection rows under ticket 12's A4), they are break-shaped (+0.78% / +1.18%
  above the stale level), and only 8.6% are reported by any later route within 5 sessions. That is now
  **the cheapest outcome question this map has**, and unlike the star-band question it does not need
  hundreds of samples per cell to answer.
  **Ticket 17 left the sharpest question on this patch, and a dated one.** Its name-level comparison —
  are the split's picks better than ticket 08's? — came back **+0.40★ at p = 0.298**, and it sized the
  shortfall: **~140 cards per arm** against the 20 it graded, which is affordable in a way the
  672-per-band outcome question is not. So the first thing forward history can settle is not "does the
  score work" but **"was the detector swap an improvement"** — and the two populations are *already
  distinguishable in the archive*, since ticket 12's A4 writes every detection as a dated row. The dating
  is load-bearing here: detections recorded before the swap are under a different definition, and nothing
  marks the boundary unless **the detector version is written alongside them**. That is a small, free
  addition to the write path today and irrecoverable afterwards — the same shape as the map's other five
  capture streams.
  **Ticket 12 made this patch tractable and then put one stain on it.** Tractable, because A4 lands all six
  streams through a single dated, append-only write path from launch — the archive is no longer six
  bolt-on captures but the thing the app itself reads, so it cannot quietly diverge from what was shown on
  the night, and derived rows are never rewritten, so no rescale injects look-ahead. The stain is A3: with
  no adjustment-drift detector, a name with a corporate action can carry up to **six days of seam
  artefacts** in its stored bars, where the old and new adjustment bases meet and read as a real overnight
  gap. Any future study has to treat the week around a split or dividend as suspect — and because detection
  runs on those bars, some detections in that window are artefacts of the ingest path rather than of the
  tape.
  **Ticket 19 left the cheapest question this patch has yet acquired, and it is not about the score.**
  The eye prefers wide-stop setups; §7 forbids them; nobody knows which is right, and forward outcomes
  can say. Unlike the star-band question (672 triggered setups per band, unaffordable) this one splits the
  nightly list into two populations at a **fixed, known threshold** — inside or outside 1×ADR — at roughly
  8%/92%, so the minority arm is the binding constraint rather than a per-band count. It is answerable the
  moment there is forward history *provided the stop width is written with every detection*, which is a
  free addition to ticket 12's A4 write path and irrecoverable afterwards — the same shape as the map's
  other capture streams, and the seventh of them. Note the trap the answer has to survive: §7's real stop
  is the entry-day LOD, not the cluster low, so a study on the proxy measures a quantity the trader never
  actually risks. Ticket 24 owns the live half of this.
  **Ticket 24 then took the trap away and left two measurements in its place.** The proxy problem is not
  "the screen cannot see §7's stop" — it is that the screen measures from the **wrong low**. §7 names three
  stops and only two are intraday: the **breakout day's low** is a daily bar, visible at the close that
  renders the digest. So the map owes two numbers, both pure computation on daily bars, both needing the
  same fresh pull, neither needing a human — **put to the trader and declined this session**, and parked
  here rather than ticketed because neither blocks the spec:
  1. **Does §7 actually bind?** Distribution of `(entry − breakout_day_low) / ADR` over detected breaks,
     against the 1×ADR cap. If most land inside, **there was never an eye-versus-§7 disagreement** —
     ticket 19's headline 92% was the ruler, and what it would change downstream is a marking rule: the
     digest could then legitimately flag no-trades, which ticket 24 R3 declined to do for want of this
     base rate.
  2. **Does k spend range to buy bars?** Correlation of cluster length k with stop width at fixed
     `TIGHT_MULT = 1.5`, across names. If strongly positive, the rubric's ×2 tightness dimension is
     partly a **stop-width preference** wearing a bar count's clothes — which would make ticket 24 R2's
     "do not fight k" argument a statement about §7 rather than about geometry.
  A residual trap survives even measurement 1: §6 usually enters on the opening range, so the breakout-day
  low is itself a proxy — but it errs **narrow-to-wide**, the safe direction, unlike the cluster low.
  <!-- "Alerting" graduated into ticket 14 and is now resolved: v1 does not alert; a per-market digest of
       real breaks only. See Decisions so far. -->
- **Watchlist persistence and user state.** **Narrowed by ticket 12, not cleared.** The storage half is
  now trivial and needs no decision — it would be one more dated table in the same DuckDB file, and A4's
  append-only shape already fits a mark-and-unmark log. What remains is a product question, and ticket 11
  answered it *by omission*: its two-screen inventory contains no watchlist, no marking, and no user state
  of any kind, and no endpoint was defined for one in ticket 12's A8. So v1 as currently specified does not
  remember anything you do. Nobody has explicitly ruled it in or out, which is why this stays fog rather
  than graduating — but it is now a one-session question, and it is the last patch on this map that is
  cheap.
  <!-- "Chart rendering approach" cleared by ticket 11: I5 fixed what the chart draws (§2's MA set
       including the 65 EMA, the primary window only, both fitted lines as fits, trigger and base-low
       stop, volume with base bars distinguished). The remaining library choice is a pure architecture
       question and was handed to ticket 12 — it is not fog and does not need its own ticket. -->
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
