# Qullamaggie Screening Dashboard — v1 Spec

**Status:** buildable. Assembled from the 27 resolved tickets of
[the wayfinding map](map.md) by [ticket 13](issues/13-assemble-v1-spec.md).

This document is written so a build session can work from it **without re-reading the map**. Every
section links back to the ticket that owns the decision; the ticket holds the reasoning, the
measurements and the rejected alternatives. Where a decision rests on an assumption that could not
be verified during wayfinding, it is marked **⚠ unverified** rather than presented as settled.

The method reference is [`references/qullamaggie-method.md`](../../references/qullamaggie-method.md);
`§n` citations throughout are to it.

---

## 1. Scope

### 1.1 What v1 is

A **locally-run, single-user, EOD screening dashboard** covering **IDX and US**, implementing the
**Breakout/Continuation setup only** (§3). Nightly, per market, it:

- rebuilds a tradeable universe from free data,
- ranks every name over five lookbacks and computes per-market deciles,
- computes sector and industry leadership and rotation,
- detects every name currently sitting in a valid base, scores it 1–5 stars, and draws the chart
  evidence behind the score,
- computes a three-state market regime and a sizing posture,
- writes a Markdown digest of the names that broke through their trigger today.

It is a **Python backend + TypeScript frontend**, one process, one local URL, one DuckDB file.

### 1.2 Non-goals (explicitly out of scope)

Pulled forward from the map's Out of scope section. None of these is deferred work inside v1 — each
was consciously ruled off the route.

| Out of scope | Why |
|---|---|
| **Narrative theme layer** ("nickel downstream", "GLP-1", "AI") | Yahoo's 145 industries arrive free and cover the theme question wherever the theme *is* an industry. The remainder costs a paid LLM pass, a US-only ETF scraper that breaks market parity, or hand-curation ([ticket 07](issues/07-sector-theme-and-rotation-model.md) S1) |
| **Episodic Pivot (§4)** | Deferred by the method reference itself; needs intraday/pre-market data |
| **Parabolic short (§5)** | Not practically available on IDX; largest blow-up risk |
| **Position sizing calculator (§8)** | Considered and ruled out |
| **Trade journal / open position tracking (§9)** | A second product |
| **Intraday or real-time data** | v1 is EOD only |
| **Multi-user, sharing, auth** | Single user |
| **Hosting, deployment infrastructure** | v1 runs locally. Research preserved in [ticket 04](issues/04-free-tier-hosting-and-scheduling.md) for a future effort; a paid tier (~$10–20/mo) is pre-approved for it |
| **Validation / backtesting** | Unsolved — see [§9.1](#91-validation-is-unsolved-and-v1-only-seeds-it) |
| **Watchlist persistence / any user state** | v1 remembers nothing you do. Not ruled out forever, but not specified — see [§9.6](#96-open-questions-parked-deliberately) |
| **Rejected-candidates view** | [Ticket 11](issues/11-dashboard-information-architecture.md) I8; the inspection happened in the wayfinding decks instead ([tickets 23](issues/23-the-rejected-candidates.md), [25](issues/25-the-line-not-drawable-path.md)) |

### 1.3 Standing constraints

- Both markets from day one.
- **Free data sources only.** No paid feeds, no TradingView/broker subscription.
- Runs **locally**, single user, live backend — the UI may query the store freely and is not
  restricted to precomputed views.
- **EOD nightly cadence**, per market. No intraday, no streaming.
- Full auto-detection plus a computed 1–5 star score, not a hand-curated shortlist.
- Charts rendered in-app, showing the evidence behind the score.
- "Top decile" is ranked against the whole tradeable universe **per market**, never within sector.

---

## 2. Domain glossary

This is the ubiquitous language. Code should speak it — table names, API fields, variable names,
UI labels.

| Term | Meaning |
|---|---|
| **Market** | `IDX` or `US`. The top-level axis of everything: runs, sessions, ranks, deciles, screens and digests are all per market. There is no global "tonight" ([ticket 11](issues/11-dashboard-information-architecture.md) I1) |
| **Session** | One market's trading date. Everything derived is keyed `(market, session, …)` |
| **Final bar** | A daily bar for session `D`, where `now > D`'s normal close + 30 min in the exchange's local timezone. Non-final bars are dropped at ingest |
| **Phantom bar** | A bar with `volume == 0` — no trade occurred. Removed from the series entirely, never zero-filled or carried forward |
| **Instrument** | Anything ingested. Carries `role ∈ {candidate, reference}`; reference instruments (index/ETF) are computed like anything else but are never rankable |
| **Universe** | The tradeable set for a market on a session: liquidity + instrument type + listing age. Membership is **sticky** — removal requires positive evidence |
| **ADR** | Average Daily Range, `SMA20(high / low − 1)`. The method's volatility unit; nearly every threshold in the system is denominated in it |
| **Lookback** | One of `1w`, `1m`, `3m`, `6m`, `12m`. Calendar-anchored |
| **Rank** | A name's **percentile** within its market and lookback on a session. The shared substrate — there is exactly one definition of "strong" |
| **Decile** | Top 10% of a lookback's own population. The **gate** is the union of the five deciles (~29% of the universe, *not* 10%) |
| **Board / leaderboard** | Top 30 names by raw return for one (market, lookback). Five boards per market |
| **Breadth badge `k/5`** | How many of the five lookbacks a name is currently top-decile in |
| **Sector** | Yahoo/Morningstar GECS sector, 11 values, same taxonomy on both markets |
| **Industry** | Yahoo's 145-industry level under sector. **Industry is the theme layer** — there is no separate theme concept |
| **Sector strength** | Share of a sector's members in that lookback's top decile. Five numbers per sector |
| **Shape differential** | `share(1w) − share(6m)`, in percentage points. Rotation's default sort |
| **Temporal delta** | `share(1m, tonight) − share(1m, 20 sessions ago)` |
| **Prior move** | The best low→high run-up ending at or before today, over windows of 21/42/63/126 bars. Its **peak** is where the base starts |
| **Base** | Prior-move peak → today, capped at 45 bars. Always ends today — there is no such thing as a base that ended last week |
| **Cluster** | The **largest** trailing 3–7 bar window spanning ≤ 1.5 × ADR. The tight end of the base |
| **Cluster length `k`** | Bars in the cluster. The ×2 tightness dimension of the star score |
| **Envelope** | The upper trendline: anchored at the cluster's max high, fitted backwards over the base's highs with non-positive slope only |
| **`line_ok`** | Whether the envelope is a *good* fit (touch zones and bounded overshoot). Not a gate — a silent tiebreak |
| **Trigger** | `cluster_high`. By identity — the envelope is anchored at the cluster's max high and can never exceed it |
| **Detection** | A name with a valid base + cluster + MA catch-up, inside the decile gate, on a session. A dated row |
| **Break** | An **event**, not a state: `close_today > trigger_yesterday`. Equivalently, *"today's close is above the last k sessions' high"* (k median 4) |
| **Star score** | §3.5's rubric: 8 dimensions, 10 weighted points, `points ÷ 2` = 0–5 stars. The sort key of the only list in the app |
| **Regime** | `FRIENDLY` / `CHOPPY` / `HOSTILE` per market, from one index each. Advisory only — never filters, reorders or scores |
| **Digest** | One dated Markdown file per market per session listing today's breaks. The whole notification layer |
| **Run** | One market's nightly pipeline execution. Publishes or is **quarantined** |

---

## 3. Data contract

Owner tickets: [01](issues/01-idx-free-data-sources.md), [02](issues/02-us-free-data-sources.md),
[03](issues/03-sector-taxonomy-sources.md), [05](issues/05-universe-definition.md),
[12](issues/12-architecture-and-deployment.md).

### 3.1 Sources

| What | Source | Notes |
|---|---|---|
| **Bars, both markets** | `yfinance` (`.JK` suffix for IDX) | One client, one schema, one taxonomy across both markets |
| **IDX enumeration** | Yahoo screener, `quoteType: EQUITY` | 840 symbols in ~0.8s. Fallback: headless scrape of idx.co.id (Cloudflare-403 to server-side requests, so headless only) |
| **US enumeration** | Nasdaq Trader files | 5,711 symbols; carries the `ETF` flag used for `role` |
| **Sector + industry** | Yahoo `.info` — `sector` and `industry` in the *same* request | Morningstar GECS. 99.7% measured coverage across 320 sampled tickers. No mapping table, no GICS licence exposure |
| **Index bars** | `^IXIC` (US), `^JKSE` (IDX) | Same ingest path as equities |

**Rejected and why:** Stockbit (ToS-barred), idx.co.id direct (Cloudflare-403), IDX-IC sector
taxonomy (blocked and unnecessary), GICS (contractually out). Massive (ex-Polygon) is the US
fallback if yfinance ever fails.

### 3.2 The standing property of this data layer

> **Yahoo fails as silence.** Throttled requests return empty results — for price history, literally
> *"possibly delisted; no price data found"*. Missing data and a dead stock produce byte-identical
> responses.

Found independently by tickets 01, 02 and 03. Every rule in §3.4 exists because of it. **No
per-symbol care can separate the two cases** — the only robust move is to make the ambiguous signal
non-actionable.

### 3.3 Pacing and failure modes

- **12 requests/second**, exponential backoff on 429. Measured: unthrottled returns only **52.9%**
  of the US universe *while reporting the losses as "possibly delisted"*; 12 req/s gives **99.93% in
  8.5 minutes** from a residential IP.
- **~6,550 symbols are ingested** (the *enumerated* universe, not the tradeable one — liquidity is
  measured *from* bars). ~9 minutes per market pass.
- **Persist each market's pull the moment it completes**, not at the end of the run. A ticket-06
  probe lost a completed 5,467-symbol US pull because the IDX screener rate-limited afterwards and
  the cache was written only after both markets had been fetched.
- **Sector costs one request per symbol.** Cache policy: **new names block** (a name with no
  industry cannot be placed on the axis), **1/30th of existing names roll nightly** (~73 names,
  ~2 min), **a failed fetch never nulls a cached value**. Measured throttle-free at 1.2s spacing
  across ~1,850 consecutive calls.

### 3.4 Hygiene rules (all non-negotiable)

1. **Phantom bars** (`volume == 0`) are **removed from the series** before any computation. A
   no-trade bar prints `high == low == close` and drags ADR toward zero, making a thin name screen
   as "slow". ~4% of IDX bars.
2. **Finality.** A bar dated `D` is final iff `now > D`'s normal session close + 30 min, exchange
   local time. Non-final bars are **discarded at ingest** — not stored flagged. Proven necessary:
   14 minutes of trading was once served as a full day. US early closes (13:00 ET) need no special
   handling — a rule keyed to the normal 16:00 close errs in the safe direction.
3. **Density gate.** A name stays in the universe only if ≥ **16 of the market's last 20 sessions**
   were non-phantom for it *and* its most recent final bar is within **3 sessions** of the market's
   latest. This doubles as **suspension detection**, which is why the (unobtainable) IDX suspension
   list is never needed.
4. **No trading-calendar table.** "The market's last 20 sessions" is the union of bar dates across
   that market's universe. That *is* the exchange calendar, observed.
5. **Zero rows is `unresolved`, never `absent`.** Retried with backoff. `unresolved` names carry
   yesterday's classification forward, visibly stale-marked.
6. **Sticky membership.** A name leaves the universe only on positive evidence — real bars failing
   the density gate. Never because a fetch failed.
7. **Run-level completeness gate.** If < ~99% of enumerated symbols resolve after retries, the run
   is **quarantined**: it does not replace the universe, the boards or the list. The last good run
   keeps serving, bannered.
8. **Enumeration is checked too.** A materially smaller symbol list than the last good run is a
   failed run, not a shrinking exchange. (Per-symbol failures are countable against a known
   denominator; a truncated enumeration moves the denominator and would pass rule 7 at 100%.)

### 3.5 Adjustment

- **Adjusted series** for returns, MAs, gaps, ADR, tightness, everything geometric.
- **Unadjusted `close × volume`** for dollar volume — Yahoo rescales prices for corporate actions
  but leaves volume alone.
- **Store both** (raw OHLC + `Adj Close` + dividends + splits arrive in one call).
- **No absolute-price rule anywhere in v1** — no minimum price filter, no tick bands.

This last point is load-bearing. Yahoo applies **rights adjustments invisibly** on IDX (BBRI
rescaled 10/11 with no split or dividend entry), so raw IDX prices are unrecoverable. Because nearly
every quantity in the method is a **ratio**, and ratios are invariant to multiplicative adjustment,
that finding costs exactly nothing.

### 3.6 Refresh cadence

- **Nightly:** incremental append — ask each symbol for bars since its last stored one.
- **Weekly:** full-universe 10-year refetch.
- **⚠ Known defect (accepted, [ticket 12](issues/12-architecture-and-deployment.md) A3):** there is
  **no adjustment-drift detector**. An appended bar arrives on a new adjustment basis while stored
  history sits on the old one, so **for up to six days a corporate action leaves a seam that reads
  as a real overnight gap** — which the detector reads as price action. Bounded, self-healing on the
  weekly refresh, confined to affected names. **It is the cheapest of the map's four knowing
  omissions to reverse**: a 20-bar overlap check costs *zero* extra requests (same request count),
  compares 19 overlapping adjusted closes, and full-refetches any symbol that disagrees. Turn it on
  the first time a seam artefact is seen on a chart.

---

## 4. Computation spec

### 4.1 Universe ([ticket 05](issues/05-universe-definition.md))

Universe = **liquidity + instrument type + listing age**. Nothing else.

| Rule | Value |
|---|---|
| **Liquidity floor** | **median** of `close × volume` over the trailing **20 traded bars** ≥ **Rp 1B** (IDX) / **$20M** (US), unadjusted |
| **Instrument type** | **Common stock only.** Excluded by security-name pattern: warrants, rights, units, notes/bonds, preferred, trusts/funds. **ADRs are kept** |
| **Listing age** | ≥ **20 non-phantom bars** (the minimum for ADR and median dollar volume to exist). Per-lookback eligibility handles the rest |
| **Density** | §3.4 rule 3 |
| **Hysteresis** | Enters at ≥ **1.0×** the floor, leaves only below **0.8×** |
| **Rebuild** | Nightly |

**Measured under this exact rule stack** (2026-08-04, live data; independently reproduced by three
separate sessions):

| stage | IDX | US |
|---|---|---|
| enumerated | 840 | 6,944 |
| passing density gate | 831 | 5,937 |
| median-20d ≥ floor | 288 | 2,004 |
| **after instrument exclusion** | **288** | **1,966** |
| in the 0.8–1.0× hysteresis band | 25 | 141 |

Notes the build must not lose:

- **Median, not mean.** On IDX a Rp 200M/day name printing one Rp 40B block clears a 20-day *mean*
  of Rp 1B without having become tradeable. Binds ~14% tighter than a single-day rule.
- **ADR is *not* a universe gate.** It is a post-rank column with a toggle (§4.4). Gating on it
  would make decile denominators breathe with the volatility regime, and would evict a name on the
  eve of its move — a 3.5-ADR name that starts moving is a name whose ADR is *becoming* 8.
- **The account-size / participation caveat is not encoded at all** — no gate, no config, no badge.
  The app surfaces median-20d dollar volume; the ≤5–10%-of-ADV rule is applied by the trader.
- **⚠ The instrument-type rule is the only non-behavioural rule in the system** — every other rule
  tests what a name *does*; this one matches its name. It misfires both ways: it deletes NTRS
  (an operating bank caught by its legal name), ~22 liquid REITs/BDCs, MLP common units, and ITUB /
  BNS (preferred-share ADRs). An earlier version of the pattern would have deleted **BABA, ARM, SE,
  PDD, NOK, SHEL, JD, VALE, UL, INFY, ARGX, SIMO** by matching "Depositary Sh" — the ADR structure.
  Use `\bPreferred\b|\bPfd\b`. **Spot-check the surviving list on the first real pipeline run.**
  Low stakes: the whole rule moves 1.9% of US names.
- **Governing principle, three rules are instances of it:** *removal requires stronger evidence than
  admission.* Sticky membership, the asymmetric band, and ADR-as-post-rank-filter.

### 4.2 Indicators

| Quantity | Definition | Window basis |
|---|---|---|
| **ADR** | `SMA20(high / low − 1)` | traded bars |
| **`adr_abs`** | `ADR × close` — ADR in price units | — |
| **Median dollar volume** | median of unadjusted `close × volume` over 20 traded bars | traded bars |
| **SMA 10 / 20 / 50** | simple, on adjusted closes | traded bars |
| **65 EMA** | §2's one daily exponential. **Chart only** — scores nothing, gates nothing | traded bars |
| **Return** | `AdjClose(last final bar ≤ D) / AdjClose(last final bar ≤ D − L) − 1` | **calendar** |
| **"Rising"** | `X[t] > X[t−5]`. **Sign only, no magnitude threshold** | traded bars |

**The traded-bar / calendar split is deliberate.** Rolling statistics (ADR, dollar volume) count
traded bars — "the last 20 days this thing actually traded" is the right question. **Returns are
calendar-anchored**, because a board must compare like with like: under traded-bar counting a
"3-month return" spans 3 calendar months for a name that trades every session and ~3.5 months for
one missing 15% of sessions, systematically flattering illiquid names. The "last bar on or before"
rule handles weekends, holidays and phantom-dropped bars uniformly, with no calendar table.

### 4.3 Ranking and deciles ([ticket 06](issues/06-ranking-and-decile-model.md))

**Five lookbacks:** `1w` (7 calendar days), `1m`, `3m`, `6m`, `12m` (calendar months).

**Per-lookback eligibility:** a name is ranked in a lookback iff it has a bar on or before `D − L`.
A 90-day-old IPO appears on the 1m and 3m boards and is **absent** — not zero-filled, not
backfilled — from 6m and 12m. Per-lookback denominators therefore differ by construction (US
1,966 → 1,912 across the five).

**Rank on pure return. No volatility adjustment.** Measured: normalising by ADR replaces up to
**20 of 30 rows** on the US boards. It is a different product, not a refinement — and it inverts the
trader's stated preference (he takes the 7.6-ADR name over the 2.4-ADR ETF).

> **⚠ Named cost, written here so nobody "fixes" it later:** the boards *will* be dominated by
> high-volatility names, and a quiet 2-ADR mega-cap making a genuinely unusual 40% move may never
> appear. This is the correct bias per §1, but it is a real blind spot.

**The gate and the leaderboard are two different cuts:**

- **The gate** (feeds detection): union of top deciles across **all five** lookbacks, any-of, not a
  composite. Each decile computed within that lookback's own population.

  > **⚠ "Top decile" passes ~29% of the universe, not 10%. State this in any downstream doc.**
  > Measured **566 US (28.8%) / 82 IDX (28.5%)**. The agreement across two markets differing 7× in
  > size is not coincidence — a percentile gate is self-normalising. Anyone reading "top decile of
  > 1–6 month returns" will build for a tenth of the load and be wrong by 3×.

  Any-of beats a composite because the names a composite loses are precisely the **sharp recent
  movers** (85th percentile 1m / 50th 3m / 40th 6m composites to nothing — but that is a stock that
  just woke up). No lookback is a passenger: every one admits names no other does.

- **The leaderboards:** **five separate boards per market, 30 rows each**, ten boards total. N=30 is
  over-determined — §1's "top 1–2% of gainers" is 20–39 names on 1,966, and IDX's natural decile is
  29. Distinct-name load per market: **112 US / 88 IDX**, a genuine ten-minute pass.
  *Named cost:* on IDX a top-30 board and a top-decile board nearly coincide; on US they differ 6×.

**Row furniture:**

- **`k/5` breadth badge** — count of lookbacks in which the name is currently top-decile. Free to
  compute. 55% of qualifying US names are `1/5`; only **3 of 1,964** are `5/5`. *It measures
  persistence, not magnitude, and must not be presented as a quality score.*
- **`NEW` marker** on rows absent from that board last session. **No smoothing anywhere**, including
  the 1w board, which turns over **16 of 30 nightly on US** — one session is 20% of a five-day
  window, and that churn is honest. The marker converts churn from noise-you-diff-by-eye into the
  most informative thing on the page.
- **≥30%-in-5-days flag** on the 1w board (§1's scan #1). Measured 20 US / 5 IDX names, **all
  already on the board** — zero missed.
  > **⚠ Accepted failure mode, explicitly chosen.** The US 1w cutoff is +26.2% and 20 of 30 slots
  > are already ≥30% names. In a hot tape more than 30 names clear 30% in five days and those below
  > rank 30 **vanish silently** — the flag under-reports exactly when the scan matters most. An
  > overflow rule was offered and the trader chose to accept the failure mode, keeping constant-30
  > without exception.

**Persistence:** one row per `(name, lookback, session)` carrying **percentile rank and raw return**,
for **every universe member** (not only board members), on a **rolling 2-year window**.

> **⚠ Two properties of this stream that constrain any future analysis:** it is the first stream
> that **discards** (2-year window forecloses a multi-year study unless a coarser permanent archive
> is added — a few MB/year), and stored ranks carry a **~1.5% noise floor from denominator churn**
> (30 US / 8 IDX names enter or leave the universe overnight even with hysteresis). "This name's 3m
> percentile fell from 94 to 92" may be denominator, not price.

**Ranking is a shared service.** There is to be no second, divergent notion of "strong": sector
strength (§4.4) and the detection gate (§4.5) both read this table.

### 4.4 Sector, industry and rotation ([ticket 07](issues/07-sector-theme-and-rotation-model.md))

**Industry *is* the theme layer.** 145 industries under 11 GECS sectors, same vocabulary on both
markets, arriving free in the sector request. A stock has exactly one industry.

**Sector strength** = **share of that sector's members in that lookback's top decile**, five numbers
per sector, aggregated over the rank table. Per-lookback deciles, **not** the union gate — the union
would park every sector near 29% and discriminate poorly, whereas a per-lookback decile makes 10%
the fair share by construction.

*Rejected:* equal/cap-weighted sector index return, and the US sector-ETF proxy. A sector where 8 of
40 names are ripping and 32 are flat has a mediocre index return but is exactly the sector to
surface — leadership concentrates before it broadens. The ETF route additionally needs a different
metric per market (IDX has no usable sector-ETF layer).

**Rotation is two sortable columns** (the trader overruled a sparkline-and-eyeball proposal and
required it computed):

| Column | Definition |
|---|---|
| **Shape differential** (default sort) | `share(1w) − share(6m)`, in pp. Zero tunables, no history needed |
| **Temporal delta** | `share(1m, tonight) − share(1m, 20 sessions ago)`. The 20 is inherited from §2/§3.5's swing horizon, not invented |

No composite of the two, and no threshold on either. They disagree usefully: a sector can be
structurally hot while its share has been *falling* for a month.

> **⚠ The temporal delta is the noisiest column on the board** (~1.5pp denominator noise floor, plus
> single-name quantization on thin sectors). It carries a noise caveat in the UI.

**Quantization guard — `k ≥ 2` to top the rotation board.** Measured: one name moves IDX Utilities'
share by **10.0pp** (vs 0.3–1.7pp anywhere on US), and Technology topped the measured IDX rotation
board at +21.4pp on **three stocks**. Sorted freely, the IDX board would be led by its smallest
sectors most nights. So a sector needs ≥2 members in the shorter lookback's decile to be eligible
for the top; single-name sectors sort into a separate group below, **still visible with their
numbers intact**. Every row carries `k/n` beside the share. This is §10's "strength clusters" stated
literally — one stock is not a sector rotating. *Shrinkage toward the 10% baseline was rejected as
smoothing.*

**One industry board per market, `n ≥ 10` to be ranked.** Yields **63 US rows and 7 IDX rows** —
parity of rule, not parity of result. `n ≥ 10` is derived, not picked: it is exactly the point at
which one name can move the share by at most 10pp, the decile baseline itself. IDX has 87 industries
across 289 names, median size 2, 38 singletons — it cannot carry a full board and is not forced to.
Industries below the floor are **not hidden**; they remain as the per-candidate tag.

**§3.5's sector confirmation boolean:** **leave-one-out sector share ≥ 10% on the 1m lookback.**
The leave-one-out is load-bearing — the naive rule fires **77–90%** because the candidate inflates
its own sector, making the point nearly free. Leave-one-out drops it to a stable **52% on IDX**
across 1m/3m/6m. *Rejected:* the industry-peer rule (24–55% IDX vs a flat 88–89% US, and
structurally unavailable to 38 IDX singleton industries).
*Named cost:* the rule is not symmetric — 52% IDX vs 61–79% US. It discriminates on both (all-names
baseline 36–46%) and is far more stable than the alternative.

**Industry appears on the candidate row as context and does not score**, so no name is penalised for
being alone in its industry.

**Sector strength never filters.** It contributes its one point to the star score and it is a board
you read. All 11 sectors always render, both markets, even at 0% on every lookback. Computed per
market, displayed on a shared 11-sector axis.

**§10's "pullbacks are information" is emergent, not a feature.** A decile is cross-sectional, so on
a tape that fell 8% over a month the 1m decile *is* what held up. Surfaced as **copy, not
computation**: when the regime banner reads `CHOPPY` or `HOSTILE`, the sector board carries a
one-line note that these shares are reading relative strength through a decline.
> **⚠ Named limit:** §10 says the *deep washout* case inverts — the first bounce is led by the most
> beaten-down junk. The shares cannot distinguish a mild pullback from a washout (that needs a
> drawdown threshold, which ticket 10 deliberately declined to introduce). The note states this.

### 4.5 Setup detection ([tickets 08](issues/08-setup-detection-algorithm.md) / [16](issues/16-trendline-fitting-envelope-vs-least-squares.md) / [17](issues/17-base-cluster-split.md) / [18](issues/18-digest-rule-under-the-clamped-trigger.md) / [19](issues/19-fit-the-split-parameters.md) / [25](issues/25-the-line-not-drawable-path.md) / [26](issues/26-the-line-penalty-and-the-longer-list.md))

Detection runs **against every universe member every night** and emits **a base, not a state** —
every name currently sitting in a valid base, with its trigger, regardless of whether anything
happened today.

Reference implementation: `prototypes/16-trendline-fit/split.py` (`scan()`), charted by
`prototypes/17-base-cluster/chart17.py`.

#### The algorithm, per `(symbol, session)`

Let `as_of` be today's index. Requires ≥ 80 bars of history and a positive ADR.

```
adr      = SMA20(high/low − 1)[as_of]
adr_abs  = adr × close[as_of]
```

**1. Prior move → where the base starts.**
Over each window `w ∈ {21, 42, 63, 126}` ending at `as_of`, take the window's lowest low as the
origin and the highest high after it as the peak; the gain is `high[peak] / low[origin] − 1`. Keep
the window with the **largest gain**. `base_start = peak`.

If `as_of − base_start + 1 > 45` (`MAX_BASE_LEN`), re-anchor: `base_start` becomes the highest high
within the last 45 bars. `base_len = as_of − base_start + 1`; require `base_len ≥ 3` (§3.1's
minimum). **The base always ends today.**

**2. MA catch-up test** (§3.1's "price back at the 10/20"):

```
caught_up  ⇔  close − SMA10 ≤ 1.0 × adr_abs   AND   close − SMA20 ≤ 2.0 × adr_abs
```

**3. Cluster.** Scan `k` from **7 down to 3** and take the **first (largest)** trailing window whose
span satisfies `(cluster_high − cluster_low) / adr_abs ≤ 1.5` (`TIGHT_MULT`). If none, the name is
rejected (`no_cluster`). `cluster_high = max(high)` over the cluster, `cluster_low = min(low)`.

**4. Envelope.** Anchor at the cluster's **max-high bar**. Search 200 slopes linearly spaced over
`[−0.5 × adr_abs, 0]` and pick the one minimising an asymmetric loss over the base's highs —
overshoot weighted **3.0**, undershoot **1.0**. (Only the *ratio* binds; the loss is scale-invariant.)

**5. `line_ok`** — a verdict on the fit's quality, **not a gate** (see below):

```
touches   = base bars before the cluster whose |residual| ≤ 0.35 × adr_abs
zones     = touches grouped with a minimum gap of 3 bars
reaches_back = first touch ≤ base_start + 0.6 × base_len
line_ok   ⇔ (zones ≥ 2  OR  (zones ≥ 1 AND reaches_back))
            AND  max overshoot ≤ 1.0 × adr_abs
            AND  overshoot fraction ≤ 20%
```

**6. Trigger and stop.**

```
trigger      = cluster_high
stop (watchlist) = trigger − cluster_low
stopw_adr    = (trigger − cluster_low) / trigger / adr
```

> **The trigger is the cluster high by identity, not by clamping.** The envelope is anchored at the
> cluster's max high and searched over non-positive slopes only, so the fitted line **can never
> exceed it** — measured at **100.0% of 29,242 detections**. The `max(line, cluster_high)` in the
> reference code is dead. The fitted line therefore **never reaches the trigger**: it gates
> `line_ok` and it draws the chart, nothing else.

**7. Gates.** A name is a **detection** iff:

| Gate | Rule |
|---|---|
| **Cluster** | a cluster exists (step 3) |
| **Catch-up** | `caught_up` (step 2) |
| **Decile** | top decile in **any of 1m / 3m / 6m**, off the rank table |

`line_ok` is **not** a gate — see below. The prior-move ≥25% floor from the reference
implementation is **deleted**: the decile gate cuts 89.4% of what the floor passes while the floor
cuts 7.7% of what the gate passes (Jaccard 10.5%).

The decile gate reads only 3 of the 5 ranking windows: **1w is a momentum burst**, not §3.1's "big
prior move", and **12m is stale** enough that a stock which topped out months ago still carries it.

#### `line_ok` is a silent tiebreak, not a gate

Graded on a 105-card matched deck, `line_not_drawable` names grade **−0.12★** against detections
(95% CI −0.73 to +0.48), **inside the eye's own 0.46★ noise floor**; scored by the rubric the
machine returns the same null (**−0.03★**). Two independent rulers agree there is nothing much to
demote.

So: **a name failing `line_ok` sorts below an accepted name at equal star score, and nothing else.**
No dimension, no refit, no tunable. **Nothing marks it** — no glyph, no column, and the chart draws
the fitted line exactly as for any other name (the envelope is always computable; `line_ok` judges
its quality, not its existence).

> **⚠ Accepted cost:** at equal score two rows swap for a reason the screen never shows. The defence
> is that the reason is visible in the drawing — the candles either touch that line twice or they do
> not.

This grows the nightly list by **+59%** (see §4.8 for the level). It is the smallest blast radius
any remedy on this map has had, because the line never reaches the trigger: demoting it changes no
trigger, no stop, no cluster and no parameter.

> **⚠ One non-eye signal, deliberately not priced in:** marginal names break through their trigger
> at **0.62× the accepted rate** (US 3.04% vs 4.90% of detection-nights), not explained by distance
> to the level and holding inside every base-length bucket. A lower break rate is not a worse setup
> with no return attached — a base that breaks less often may resolve later, or lower. Recorded for
> the validation patch, not scored.

#### The parameter table

Every number below is a **borrowed default from `q-scanner-v2`, fitted to nothing.** What ticket 19
established is which of them can move anything.

| Parameter | Value | Status |
|---|---|---|
| `TIGHT_MULT` | **1.5** | **live** — but it is the *stop budget*, not a detection knob (see §4.6) |
| `K_MIN` | **3** | **live** — 2–7 grows the list +49%, 4–7 shrinks it −37% |
| `MAX_BASE_LEN` | **45** | **live** — 30→60 swings the list 15.5% |
| `MAX_OVERSHOOT_ADR` | **1.0** | **live** — the number actually doing the line cutting (+20.2pp if dropped) |
| touch group (`TOUCH_TOL_ADR` 0.35, `MIN_TOUCHES` 2, `MIN_TOUCH_GAP` 3, `reaches_back` 0.6) | as listed | **live, but one decision expressed four ways.** The touch clauses are an OR — neither binds alone |
| `K_MAX` | 7 | frozen — 7→9 moves the list −1.7%, and k serves three consumers |
| `SLOPE_STEPS` | 200 | frozen — 25→800 moves the list ±0.1% |
| `MAX_SLOPE_ADR` | 0.5 | frozen — near saturation; 0.5→1.0 moves the list +1.1% |
| `OVER_W` / `UNDER_W` | 3.0 / 1.0 | frozen — **one number, not two**; only the ratio binds ((3,1) and (6,2) give byte-identical lists) |
| `MOVE_WINDOWS` | 21 / 42 / 63 / 126 | frozen |
| `MIN_BASE_LEN` | 3 | §3.1's own minimum |
| `CATCHUP_10` / `CATCHUP_20` | 1.0 / 2.0 | frozen |
| `MA_PROX_ADR` | — | **deleted** — defined and never read |
| `MAX_OVERSHOOT_FRAC` | — | **deleted** — catches only 4.4% of candidates the ADR test misses |
| prior-move floor 25% | — | **deleted** — redundant against the decile gate |

**One set of numbers serves both markets.** IDX tracks US across the whole `TIGHT_MULT` grid (k mean
3.66/4.51/5.44 vs US 3.70/4.41/5.32; stop medians identical to two decimals; ADR distributions
comparable at US median 4.49%, IDX 3.97%).

> **⚠ Ticket 17's headline "63% swing on `TIGHT_MULT`" was measured on the *ungated* list.** The
> decile gate runs first and is by far the stronger filter. Every list-length number in this spec is
> quoted after it.

#### What is *not* implemented, knowingly

| Omission | Why | Exposure |
|---|---|---|
| **§5's backside veto** | Needs 60-minute bars (10/20/65 EMA flipping to resistance). A daily-65-EMA substitute was available and declined — no substitute gates anything | A rolled-over name can reach the list. Partial cover: excluding 12m from the decile gate removes the most likely route |
| **IDX ARA/ARB limit days** | The auto-reject band is tiered by price and board, the table is behind Cloudflare, and raw IDX prices are unrecoverable so bands cannot be inferred | A limit-locked bar has a collapsed range. Measured harmless under the split: **98.5% of accepted IDX clusters contain zero collapsed bars** |
| **Volume expansion** | Exists only at the break, so scoring it would make the score state-dependent | §3.5's volume dimension is permanently half-measured — dry-up only. Break-day expansion **is** computed and persisted, never scored |
| **Adjustment drift** | §3.6 / ticket 12 A3 | Up to six days of seam artefacts on names with corporate actions |

### 4.6 The stop ([tickets 19](issues/19-fit-the-split-parameters.md) / [24](issues/24-should-the-score-know-about-the-stop.md))

**Stop width is shown and sorted on. It never filters, and the score never sees it.**

Two surfaces show **different** stops, deliberately:

| Surface | Stop | Why |
|---|---|---|
| **Watchlist** (pre-break) | `trigger − cluster_low` | Nothing better exists for a name still in its base |
| **Digest** (post-break) | `entry − breakout_day_low` | §7's *actual* default stop, and the breakout day's low is a **daily** bar — known at the close that renders the digest. Free: no new data, parameter or capture stream |

**Neither surface marks a no-trade.**

- The watchlist does not, because **~92% of the nightly list carries a cluster-low stop wider than
  §7's 1×ADR cap** (median row **1.28×**), and a flag that fires on 92% of a list is not a flag. The
  useful form is the **stop width in ADR as a sorted column, with the ≤1×ADR minority
  highlighted** — the inverse of "mark the failures".
- The digest does not, because the base rate under the corrected ruler is **unmeasured**.

**Restoring §7 as a gate was measured and declined.** It keeps only 8.5% of detections (39.7 → 16.9
US names/night), skews survivors toward high volatility (mean ADR 6% → 10%, mean prior move
104% → 177%), and removes **85% of the graded cards — the ones that graded *higher*** (2.91 removed
vs 2.44 kept). §7 is enforced by the human at entry, against the real intraday LOD stop the screen
cannot see. The screen's job is to make that check free, not to pre-empt it.

**The score stays stop-blind.** `stop_adr` **is** the cluster's range in ADR by identity (trigger is
the cluster high; the stop runs to the cluster low), which is the *narrowness* measure the rubric
already retired — the cluster is *selected* to fit under `TIGHT_MULT × ADR`, so its width is spent
by the selection. §7's cap and §3.5's ×2 tightness dimension are **one ruler, not two**.

> **⚠ Two things this rests on that are not measured** (put to the trader and declined; parked as
> fog): (1) whether §7 actually binds under its own ruler — the distribution of
> `(entry − breakout_day_low) / ADR` against the 1×ADR cap. If most land inside, **there was never
> an eye-versus-§7 disagreement** and the digest could legitimately flag no-trades. (2) whether
> cluster length `k` buys its bars by spending range, which would make the rubric's ×2 dimension
> partly a stop-width preference in disguise. The "eye prefers what §7 rejects" finding rests on
> **one** measurement at r = +0.140, p = 0.286, on a population every member of which was selected
> under 1.5.

### 4.7 The star score ([tickets 09](issues/09-star-score-calibration.md) / [15](issues/15-star-score-second-grading-round.md) / [20](issues/20-confirm-the-band-and-measure-the-ceiling.md) / [21](issues/21-the-fitting-objective-does-not-identify-the-dimensions.md) / [22](issues/22-idx-per-market-calibration.md) / [27](issues/27-level-or-order.md) / [28](issues/28-the-retired-dimensions.md))

**Eight boolean dimensions, ten weighted points, `points ÷ 2` = 0–5 stars.**

| Dimension | Weight | Rule | Source of the number |
|---|---|---|---|
| **Tightness** | ×2 | `cluster_k ≥ 5` | fitted (published, stable across folds) |
| **Orderliness** | ×2 | `0.30 ≤ churn/L ≤ 0.60` over the base | fitted (published) |
| **Prior move** | ×1 | decile percentile `≥ 0.90` | fixed by ticket 06 |
| **Base length** | ×1 | `base_len ≤ 14` | **unfitted at this n** — see below |
| **MA support** | ×1 | `SMA20` rising (sign-only) | structural |
| **Volume** | ×1 | `dryup ≤ 0.95` | **unfitted at this n** |
| **Sector** | ×1 | leave-one-out 1m sector share `≥ 0.10` | fixed by ticket 07 |
| **ADR** | ×1 | `ADR ≥ 0.05` | fixed by §3.5 |

where:

```
churn/L = (Σ daily ranges over the base ÷ (base_high − base_low)) ÷ base_len
dryup   = median base volume ÷ median volume over the 50 bars preceding the base
```

**Booleans, not continuous** (+0.255 vs +0.191 in the round that tested it) — the score is the
default sort of the only list in the app, and a sort key you cannot audit is one you will not trust.

**Fitted with a rank objective (`cindex`), not `mae`.** This is the map's single most consequential
methodological finding: `mae` is a *level* statistic on a flat surface and produced **no stable
threshold on any of five parameters across 25 fits**, while a rank objective returns three stable
thresholds and recovers the trader's own incumbent values from data. Three tickets' worth of "the
eye does not confirm this dimension" was measured with the broken instrument. The guardrail that had
blocked `cindex` (it missed the level tolerance by 0.01★) fell once every consumer of the score was
traced: **nothing reads the magnitude.** The watchlist reads *order*; §3.5's trading rule and the
trade line read *cut points* at 3 and 4; §7/§8 and the regime posture read **nothing**.

**Performance, honestly stated:**

| Measure | Value |
|---|---|
| Out-of-fold rank correlation with the eye (432 cards) | **ρ = +0.292** |
| Test–retest ceiling of the eye itself (30 pairs) | **+0.846**, mean \|difference\| **0.47★** |
| Precision at the 4★ trade line | **0.53** |
| Recall at the 4★ trade line | 0.28 |
| Calibration | monotone across predicted bands |

> **⚠ This is the map's largest surviving shortfall: the rubric captures about a third of what the
> eye makes achievable, and nothing on the map has moved it.** It is *not* a noisy-target problem —
> the eye is reproducible to within half a star, measured five times on disjoint sets. It is a weak
> rubric against a reproducible target.

**Settled negatives — do not re-open without new evidence:**

- **No per-market calibration.** One threshold set covers both markets. The eye *is* far harsher on
  IDX (mean 2.35 vs 3.23; ≥4★ 15% vs 48%) and **the pooled rubric already tracks that** — the
  difference is in the population, not the calibration. The score scores *better* off its home
  market (IDX mae 0.913 / r +0.298 vs US 1.11 / +0.255). An IDX-only fit swings `cluster_k` 3–6 and
  `len_ok` 4–26 across five folds; there is nothing stable to split into.
- **No additional dimensions.** All six candidates retired by the blind instrument were re-screened
  under the working objective on the largest pool available (432 cards) and **not one bought a tenth
  of its bar**. The strongest, `cluster_churn`, beats the incumbent on partial ρ by +0.337 to +0.261
  and buys **+0.001** out-of-fold when swapped in. The reason generalises: **the rubric does not
  consume a dimension, it consumes a threshold on one**, so a boolean cut extracts nearly the same
  information from any monotone re-expression of the same quantity. Adding a dimension also
  *destabilises thresholds that were stable*.
- **No stop input** (§4.6). **No regime input** (§4.9). **No isotonic level stage**, no separately
  fitted star boundaries — `÷ 2` stands.

**⚠ Provisional numbers, flagged as the ticket instructed:**

- **`len_ok` (14) and `dryup` (0.95) are unfitted at this n.** `len_ok`'s modal value ranges 4–26
  across fits. Adopting the fitted values would buy ~+0.019 ρ with two numbers that move across half
  their grid between folds. They stand at the trader's incumbent values.
- **The orderliness band's upper edge is barely tested** — only 5 of 432 cards lie in (0.60, 0.70],
  so its 25-of-25 stability is partly an empty tail. The **lower** edge does the work (38% of cards
  fall below the band, 7% above).
- **The band's functional form was chosen after seeing grades**, so cross-validation controls its
  values but not its shape. It failed its own pre-registered confirmation bar (+0.120 out-of-fold
  against +0.20) and was **kept anyway, trader's call**, because the same grades refute the remedy:
  dropping orderliness costs **62% of the rubric's ranking power** and it is the strongest single
  dimension on the map (partial ρ +0.365).
- **The rubric runs cold.** It prints ≥4★ for 18.3% of names at scale where the eye grades 35.2%.
  Harmless while **nothing gates on the cut** — the 4★ line is a *label*, not a gate. **Any change
  that makes the cut load-bearing (a star floor on the list, a digest rule firing on a band, a
  sizing posture computed from the score) reopens this.**

### 4.8 Nightly list size

> **⚠ Read this before quoting any list-length number.** No list level on this map was measured on
> the real universe. The detection scans ran over a **628-name US sample** against the measured
> **1,966**, and different tickets scaled for different things. **Every *ratio* survives; every
> *level* is provisional.**

Best current estimates, obtained by rescaling rather than by measuring:

| Quantity | US | IDX |
|---|---|---|
| Detections per night, as specified (`line_ok` gating) | ~18.7 | — |
| **Detections per night, with `line_ok` demoted to a tiebreak** | **~29.8** | — |
| Digest rows per night, as specified | ~7.0 | ~0.9 |
| **Digest rows per night, with `line_ok` demoted** | **~9.6** | **~1.2** |

The real number is **free to compute the day the pipeline exists**. Compute it on the first full run
and replace this table. **The pipeline now exists** (ticket 45):
`python -m screener.acceptance <IDX|US>` reads the published run and prints B4 (detections per night)
and B5 (digest rows per night) — among all ten §8.2 figures — measured against these estimates, so
the replacement is a one-command read, not a re-derivation. Until a live run has been recorded the
levels above stand as the best rescaled estimates; the measured values, once taken, overwrite this
table and the deviation flag on B4/B5 goes quiet.

### 4.9 Market regime ([ticket 10](issues/10-market-regime-filter.md))

One index per market, evaluated on the last **closed** session:

| Market | Index |
|---|---|
| US | Nasdaq Composite `^IXIC` |
| IDX | IHSG (Jakarta Composite) `^JKSE` |

*`^GSPC` rejected* — cap-weighted into mega-caps, its slope can read healthy while small/mid
momentum is in a downtrend. *`^RUT` rejected* — dominated by unprofitable micro-caps that can sit in
a downtrend for a year while momentum growth works. *LQ45 rejected* — 45 large caps, and the Rp 1B
floor puts most IDX candidates outside it.

`SMA10` and `SMA20` over index daily closes. Rising iff `SMA[t] > SMA[t−5]`, sign-only.

| State | Rule |
|---|---|
| **`HOSTILE`** | `SMA10` falling **AND** `SMA20` falling **AND** `SMA10 < SMA20` (§10 verbatim) |
| **`FRIENDLY`** | `close > SMA10` **AND** `close > SMA20` **AND** both rising |
| **`CHOPPY`** | **everything else — the residual** |

The three partition the space exactly (HOSTILE needs `SMA10` falling, FRIENDLY needs it rising), so
no precedence rule is needed. Chop as the residual maps §10 clause-for-clause, adds **zero
parameters**, and fails safe. Warm-up: 25 index bars; below that the state is **undefined**, not
defaulted.

**The whole filter has zero tunable parameters, deliberately** — survivorship bias makes any
threshold here uncalibratable, because delisted names return zero rows on Yahoo and every historical
series rebuilt from today's universe is biased upward.

**Effect is advisory only:**

- A **persistent banner per market** — two banners, never combined into a global verdict — carrying
  state, sizing posture (`FRIENDLY` → full size, `CHOPPY` → reduced, `HOSTILE` → sit out; **words,
  not a computed position size**), breadth, and the as-of session date.
- **The candidate list is identical in all three states.** Never filtered, never reordered. This is
  §10 read literally: *he does not stop looking, he stops sizing.*
- **The regime never touches the star score.**

**Breadth** (share of the market's universe above its own rising SMA10/SMA20) is **displayed and
does not gate** — it is the measure survivorship bias corrupts most directly, so any threshold
picked today would be fitted to a series wrong in a known direction. It costs nothing to compute, so
it goes on screen to be watched live and promoted later, with evidence.

**Breakout follow-through** is **captured nightly from day one and never shown or gated in v1**. It
is the only unbiased regime signal available (recorded forward, not reconstructed) and is
irrecoverable if not started at launch.

---

## 5. Screens and the nightly path ([ticket 11](issues/11-dashboard-information-architecture.md))

**Two screens. That is the whole app.**

### 5.1 Screen 1 — Market workbench (one per market, `IDX` / `US` as tabs)

| Region | Contents |
|---|---|
| **Regime banner** | State, sizing posture, breadth, **as-of session date** |
| **Candidate list** | Five columns, sorted by **star score descending** |
| **Chart panel** | Chart bundle + the §3.5 breakdown + a facts block |
| **Sector rotation table** | Ticket 07's table, candidate's own sector highlighted |

**Candidate list columns** (five, not six — the state column was removed once `TRIGGERED` was found
unreachable):

| Column | Why it earns the space |
|---|---|
| Ticker | — |
| **Star score** | §3.5 is the verdict, and the sort key |
| Distance to trigger | How soon; the number §3.2 makes actionable |
| Stop width ÷ 1×ADR | §7's check, visible before opening anything. **≤1×ADR minority highlighted**; never a filter |
| Industry | Where a theme cluster becomes visible |
| `k/5` breadth badge | How broadly the prior move leads |

*Deliberately not columns:* ADR, dollar volume, base length, the five decile ranks, sector — all in
the chart panel, which is where you already are when you need them. **The row decides whether to
open the chart; the chart decides whether to trade.**

**Sort is the star score, descending. Proximity to the trigger is a column, not the sort** — sorting
by distance puts a 2★ barcode above a 5★ base, and defending against that needs a star floor, which
is a tunable this map refuses everywhere.

> **⚠ This makes the score's ordering, not its labelling, the load-bearing property** — a
> miscalibrated score puts the wrong name at the top of the only list in the app, nightly. At
> ρ = +0.292 against a +0.846 ceiling, it is a real but partial ordering.

**Chart panel** renders:

- Candles, plus **SMA 10 / 20 / 50 and the 65 EMA** — §2's daily set exactly.
- **The base**, with **the cluster shaded** inside it.
- **The envelope**, drawn *as a fit* so candles pierce it — per §3.2 that is the correct picture and
  **must not be "fixed" in rendering**. Drawn identically for names failing `line_ok`.
- **The trigger** (cluster high) and **the cluster-low stop** as horizontal rules — §7's
  affordability test is read off the chart geometrically.
- **Volume, with base bars distinguished** (so dry-up is visible). **Expansion is not drawn** — it
  exists only at the break.

Adjacent: the **8-row §3.5 breakdown** — each dimension, its weight, whether it scored, and the
`n/10 → stars` arithmetic. Plus a facts block: base length, trigger, distance, stop ×ADR, ADR,
dollar volume, decile ranks, sector.

**Sector rotation table** carries, per ticket 07 plus one amendment: the five shares, the shape
differential (default sort), the temporal delta, `k/n` on every row, and a **`Δ20d` rank-change
column** (`▲2` / `▼1` / `—`) against 20 sessions ago. Rank movement **joins** the share columns
rather than replacing them (rank discards magnitude — three sectors bunched within 0.4pp can
reorder completely with nothing happening), and **a move resting on `k < 2` is greyed and marked
`?`**. Measured: IDX Utilities moves 6th → 3rd on **2 names of 10**, while every US move rests on
25–53.

### 5.2 Screen 2 — Boards

Five leaderboards × two markets, 30 rows each, exactly as ticket 06 fixed them. **A peer tab, off
the nightly path** — detection already gates on decile membership, so anything on the boards that
matters has already become a candidate.

### 5.3 Navigation

**One interaction: click a row, the chart panel changes.** Nothing else navigates. Click-a-sector-
see-its-members is not in v1 — with sector strength defined as a share of the decile, the members
are on the Boards tab already.

### 5.4 The nightly path

1. After the IDX close, open the app. It lands on `IDX`.
2. Read the regime banner — one line, tonight's sizing posture.
3. Scan the candidate list from the top. Score order, so you read best-base-first.
4. On anything at 4–5★, click the row. Chart, breakdown and sector context are already on screen.
5. Check the stop column against 1×ADR, the distance to trigger, and the breakdown's two ×2
   dimensions.
6. Stop when you stop. Repeat on `US` after the US close.

**Two sittings a night, each short.** This is the load-bearing rhythm decision: IDX and US close
hours apart, so **there is no coherent "tonight" spanning both**. Making market the top-level axis
retires the staleness problem instead of labelling it. The app has **no global "as of"** — every
date on screen belongs to a market. Opening a tab mid-session shows the last completed session with
its date on the banner: no dimming, no blocking, no stale state.

### 5.5 What the UI deliberately does not have

- **No "what changed since yesterday" surface anywhere.** The diff-first landing was built,
  prototyped and rejected. A name that crossed its trigger overnight appears in the list in score
  order like any other, and nothing pulls it to the top. This keeps the eye on the whole board
  rather than on a machine-chosen subset (§10's "he does not stop looking"). **The break's single
  home is the digest** — the file you may ignore at no cost.
- **No rejected-candidates view**, and no "why isn't ticker X on the list" lookup.
- **No star floor, no filtering by regime, no filtering by stop.**
- **No user state of any kind** — no watchlist, no marking, nothing remembered.

---

## 6. The notification layer ([tickets 14](issues/14-alerting-and-trigger-notification.md) / [18](issues/18-digest-rule-under-the-clamped-trigger.md) / [24](issues/24-should-the-score-know-about-the-stop.md) / [26](issues/26-the-line-penalty-and-the-longer-list.md))

**v1 does not alert.** No push, no email, no notification, no screen. The nightly run writes **one
dated Markdown digest per market** and that is the entire layer:

```
data/digests/IDX/2026-08-05.md
data/digests/US/2026-08-05.md
```

Dated with **that market's session date**, never the wall clock. Written after that market's run
completes.

A notification channel was rejected as the diff-first landing screen reintroduced by the back door:
an EOD app can only fire after the close, so an "alert" is that same rejected surface delivered
outside the app.

**Membership rule — one rule, no taxonomy:**

```
report a name iff  close_today > trigger_yesterday
```

Since `trigger_yesterday` is the highest high of the k bars ending yesterday (k median 4), this is
literally **"today's close is above the last four sessions' high"** — a sentence a trader can check
by eye. State it that way in the UI/docs.

`trigger_yesterday` exists only if the name was detected yesterday, so the rule carries a **recency
requirement**. Membership consults **neither the score nor the stop nor `line_ok`**.

> **⚠ Accepted cost, measured:** names that lapse out of detection for 2–3 sessions and return above
> their old level are invisible to this rule — **~2.9 US rows/night**, break-shaped (+0.78% /
> +1.18% above the stale level). Closing the hole entirely takes US from ~7.0 to ~31.0 rows a night
> against a level a median 13 sessions old at +4.92%, which is not a break but a name that went away
> and came back higher. A lapse tolerance of N sessions would be the layer's first tunable and the
> gradient is continuous, so there is no non-arbitrary N. The session's defence that these are
> merely *deferred* was **withdrawn**: only 8.6% surface by any route within 5 sessions.

**Every break is reported; repeats are marked, not suppressed.** A name re-arms the night after it
breaks (the cluster rolls forward to swallow the breakout bar), so it can be reported again — 20.6%
of breaks fall within 20 sessions of the same name's previous break. Repeats land at a **higher**
price (median +1.10%, only 0.7% lower), so they are continuation, not flapping. Suppression rules
were declined: the parameter-free one silently withholds a second, higher break, which is a
judgement the digest is structurally not for.

**Row format** — ordered by star score descending, matching the list:

| Column | Notes |
|---|---|
| Ticker | |
| Star score | |
| Industry | |
| **Stop width ÷ 1×ADR** | computed from **`entry − breakout_day_low`** (§7's real stop), *not* the cluster low. **Not marked** |
| Close | |
| Yesterday's trigger | the level the rule tests against |
| % through | how decisive the break was |
| Repeat marker + last-reported date | `↺ last reported 2026-07-28` |

```
AAOI   3★   Semiconductors   0.71   18.04   17.88   +0.89%   ↺ last reported 2026-07-28
```

**Deliberately absent:** the §3.5 breakdown, ADR, dollar volume, base length. §7's affordability
test is read off the chart geometrically, so **the digest is structurally incapable of settling a
trade decision** — by design. It tells you whether to open the chart.

**The governing rule for any future addition:** *the digest carries only what the app structurally
cannot show you.* That admits the break (the UI left it homeless) and excludes new 4–5★ setups
(already at the top of the star-sorted list, and a threshold would be the layer's first tunable).
**It also means the digest cannot grow into an alerting layer by accretion.**

**An empty night still writes the file**, containing an explicit "no breaks" line — so **a missing
file means a failed run.** This is the map's "Yahoo fails as silence" property, bought for free, and
it is the whole of v1's run-failure alerting.

---

## 7. Architecture ([ticket 12](issues/12-architecture-and-deployment.md))

### 7.1 Store

**One DuckDB file: `data/screener.duckdb`.** Bars and every derived table.

- Columnar, so the whole-universe scans that ranking and detection do are fast; full SQL, so the UI
  queries the store freely without precomputed views.
- **The reproducibility freeze is `cp`** — `cp data/screener.duckdb snapshots/<date>.duckdb`. One
  file, no partition layout, no manifest.
- Footprint **measured, not estimated**: a separate implementation of this universe holds 6,838
  tickers × ~900 days as parquet in 146 MB; scaled to ten years that is **~580 MB**.
- *SQLite rejected* on the iteration loop (row-store scans). *Parquet-on-disk rejected* because the
  accumulating streams want row-level appends.

**Ten years of bar history.** Ranking lookbacks run to 24 months so 3 years is the functional floor;
ten was chosen for headroom on whatever validation eventually becomes possible.

### 7.2 The write model

**Every derived table is dated rows, appended and never rewritten**, keyed `(market, session, …)`:
universe membership, ranks, sector shares, detections, scores, signal vectors. "Tonight" is
`WHERE session = (SELECT max(session) …)`.

This is the load-bearing architectural decision. It **collapses the map's seven owed capture streams
into the normal write path** — the thing the app reads *is* the archive, so they cannot disagree,
the digest is backfillable over history, and a corrected rubric can be replayed backwards.

**Derived rows are written once and never rewritten.** They are a point-in-time record of what was
knowable that night; rewriting them after a rescale would inject look-ahead into the very streams
that exist *because* they are unbiased. Backfill only ever fills **absent** sessions.

**Every detection row must carry a `detector_version`.** Two detector-definition changes have
already happened (the base/cluster swap, and `line_ok`'s demotion, which starts writing ~59% more
rows), and nothing marks the boundary. It is free today and irrecoverable afterwards. Treat it as a
column, not as a marker for one swap.

**Also written with every detection**, all free at the write path and all irrecoverable later: the
raw signal vector, the trigger level, the stop width, and break-day volume expansion.

### 7.3 Runs

**Two `launchd` jobs, one per market:** ≥ **19:00 WIB** for IDX (the 2026-08-04 bar was measured
final at 19:49 WIB against a 16:00 close; earlier is unproven), ≥ **17:00 ET** for US.
`StartCalendarInterval` fires a missed job once on wake, so a sleeping laptop delays a run rather
than losing it.

**Plus run-on-open:** opening a market tab whose last final session is missing from the store kicks
a run with a progress state. Two mechanisms deliberately — run-on-open alone was rejected because a
~9-minute pull does not fit the 10-minute nightly budget; manual-only was rejected because a
forgotten night is invisible until you notice the as-of date.

**Backfill:** everything derivable from bars (universe membership, ranks, detections, scores, signal
vectors) is recomputed for every session between the last computed one and the latest final session
— a week away costs seconds of compute and leaves **no hole**. **As-of-only** captures (listing-file
snapshots, sector/industry labels) are stamped with the run date and **never backfilled**, so a gap
there is visible and honest rather than fabricated.

*One accepted wrinkle:* backfilling uses today's adjusted basis for a past session. Ratios are
invariant to a uniform rescale, so this is immaterial — the same property that made unrecoverable
raw IDX prices cost nothing.

**Quarantine is per market** (§3.4 rule 7). First-run backfill is resumable by construction — a
symbol with bars at the target depth is done.

### 7.4 Pipeline stages, in order, per market run

1. Snapshot the listing files (as-of, never backfilled)
2. Ingest bars (incremental; full on the weekly pass) — **persist as soon as the market's pull
   completes**
3. Hygiene: drop phantom zero-volume bars, apply the finality rule
4. Resolve the universe (liquidity, instrument type, listing age, density gate, hysteresis)
5. Indicators (ADR, MAs, returns)
6. Ranks, 5 lookbacks
7. Sector and ranked-industry shares
8. Detection
9. Score
10. Write the digest
11. Write the run record

Stages 4–9 are recomputed **in full from bars** every run, and rerun per backfilled session. The
sector/industry label cache is the one incremental piece (§3.3).

### 7.5 API and repo

**Resource endpoints; the frontend composes the workbench.**

```
GET /api/regime/{market}
GET /api/candidates/{market}
GET /api/sectors/{market}
GET /api/boards/{market}
GET /api/chart/{market}/{symbol}
GET /api/runs/{market}
```

Screen-shaped endpoints were rejected: the workbench costs 3–4 round trips against a local backend,
which is free, and the surfaces stay independently addressable. A general query layer was rejected —
no schema contract to generate types from, and domain logic would migrate to the frontend.

```
backend/     Python package — pipeline stages, DuckDB access, FastAPI app
frontend/    Vite + React + TS
data/        screener.duckdb, digests/
CONTEXT.md   domain vocabulary (the glossary in §2)
docs/adr/    decisions that outlive this map
```

**One repo. TS types generated from the OpenAPI schema.** Pydantic response models give FastAPI an
OpenAPI schema for free; `openapi-typescript` turns it into committed `.d.ts`. A renamed field
becomes a **typecheck failure rather than a runtime `undefined`** — which matters under
resource endpoints, where five payloads compose one screen. **FastAPI serves the built frontend, so
it is one process on one URL.**

### 7.6 Charting

**lightweight-charts** (TradingView, Apache 2.0, ~45 KB, canvas). Candles, line series and histogram
volume are first-class; the trigger and stop are `createPriceLine`; **the envelope is a line series
over the base window**, which draws it *as a fit* with candles piercing it — exactly what §3.2
requires and what a purpose-built trendline widget would have "fixed".

**Port `~/Projects/q-scanner-v2/web/src/renderChart.ts`** as the starting point (lightweight-charts
v5, React 18, Vite; already draws candles, SMA 10/20/50, volume histogram and dashed trigger/stop
price lines against a FastAPI payload). Four additions it does not have: the **65 EMA**, the
**envelope over the base window**, the **shaded base with the cluster shaded inside it**, and
**volume with base bars distinguished**.

> **The rest of `q-scanner-v2` is deliberately not adopted** — it answers several questions
> differently (parquet+SQLite, ~2.5y depth, manual runs, hand-written frontend types, IDX-IC
> sectors, a tunable `PatternParams` engine with an eval sweep). Adopting it as the baseline was put
> as an explicit fork and declined. It is recorded because it is prior art a future session would
> otherwise rediscover — and because **it contains a working `adjusted_close` overlap drift detector
> of exactly the kind §3.6 declined**, which is where to look if that omission is ever reversed. Its
> `eval/labels` + `--sweep` machinery is also the shape of the grading-and-sweep loop.

---

## 8. Acceptance criteria

v1 is done when, on a given evening, the following all hold. Each is checkable in one sitting.

### 8.1 The run

| # | Criterion | How you know |
|---|---|---|
| A1 | The IDX run completes after 19:00 WIB and the US run after 17:00 ET, unattended | `digests/<market>/<session>.md` exists for the latest session, on both markets |
| A2 | A run that fetched < ~99% of enumerated symbols does **not** publish | Force a throttle; the previous session's data keeps serving behind a banner |
| A3 | A missing digest file is the failure signal, and there is no other | Kill a run mid-flight; the file is absent, the app still serves the last good session with its date |
| A4 | A market pull is persisted the moment it completes | Kill the second market's pull; the first market's data survives |
| A5 | A week of missed sessions backfills every derivable stream with no holes | Stop the job for 5 sessions, restart; ranks/detections/scores exist for each intervening session; listing snapshots and sector labels have a visible gap, not a fabricated one |
| A6 | A run takes ~9 min per market on the incremental path | Wall-clock the run |

### 8.2 The numbers

Reproduce these on the first full run. **Deviations are not automatically failures** — the universe
moves — but a deviation of more than ~10% on any of them means a rule was implemented differently
from this spec.

All ten are computed off the published run by `python -m screener.acceptance <IDX|US>` (ticket 45),
each paired with the expectation below and flagged when it deviates beyond ~10% — so B1–B10 are
*recorded*, not eyeballed, and the D2 spot check (the twelve ADRs) rides the same report. Do not
treat a mediocre-looking list as an implementation bug without checking these first: the rubric
captures about a third of what the eye achieves (§4.7), a measured shortfall, not a defect.

| # | Criterion | Expected |
|---|---|---|
| B1 | Universe size | **~288 IDX / ~1,966 US** |
| B2 | Union-of-five-deciles gate width | **~28–29% of the universe** on both markets (~82 IDX / ~566 US) |
| B3 | Distinct names across the five top-30 boards | ~88 IDX / ~112 US |
| B4 | Detections per night, after the decile gate, with `line_ok` demoted | **~30 US** (see §4.8 — this level is the least-verified number in the spec) |
| B5 | Digest rows per night | **~9.6 US / ~1.2 IDX** |
| B6 | Share of the list whose cluster-low stop exceeds 1×ADR | **~92%**, median row ~1.28× |
| B7 | Share of detections where the fitted line sets the trigger | **0%** — it is an identity. Any non-zero value is a bug |
| B8 | Cluster length distribution | k=3 on ~37%, median 4 |
| B9 | ≥4★ share of the nightly list | ~18% (the rubric runs cold — see §4.7) |
| B10 | Sector/industry coverage | ≥99% of universe members carry both |

### 8.3 The screens

| # | Criterion |
|---|---|
| C1 | The workbench opens on a market tab, banner first, list sorted by star score descending |
| C2 | Clicking a row swaps the chart panel and nothing else navigates |
| C3 | The chart draws candles, SMA 10/20/50, the 65 EMA, the shaded base with the cluster shaded inside it, the envelope **with candles piercing it**, the trigger and cluster-low stop as rules, and volume with base bars distinguished |
| C4 | The §3.5 breakdown next to the chart reconstructs the star score arithmetically — 8 rows, weights, hits, `n/10 → stars` |
| C5 | The stop column highlights the **≤1×ADR minority** and filters nothing |
| C6 | The rotation table sorts by shape differential by default, shows `k/n` on every row, and greys `Δ20d` where `k < 2` |
| C7 | Opening a tab mid-session shows the last **final** session, dated on the banner. No dimming, no blocking |
| C8 | The Boards tab shows 5 boards × 30 rows per market, with `k/5`, `NEW`, and the ≥30%/5d flag on the 1w board |
| C9 | The ADR toggle exists, is the same control on both surfaces, and defaults **off** on each |
| C10 | Nothing in the app remembers anything you did last night |

### 8.4 The judgement calls (the ones worth checking by eye on night one)

| # | Criterion | How you know |
|---|---|---|
| D1 | The detector's picks are *setups* | Open the top 10 rows. If more than one or two are not recognisable bases, the geometry is wrong, not the rubric |
| D2 | The instrument-type filter did not eat anything real | Spot-check the surviving US list for the ADR names (BABA, ARM, SE, PDD, NOK, SHEL, JD, VALE, UL, INFY, ARGX, SIMO). **All twelve must be present** |
| D3 | The score's ordering is defensible, not correct | At ρ ≈ +0.29 against a +0.85 ceiling, expect roughly one name in two at the 4★ line to be one you would trade. That *is* the spec |
| D4 | The digest is ignorable | ~10 US rows. If it is 30, the recency rule was implemented as a lapse tolerance |
| D5 | No seam artefacts on the chart | Open any name that had a split or dividend in the last week. A spurious overnight gap means §3.6's declined drift detector should be turned on |

---

## 9. Open risks carried into the build

### 9.1 Validation is unsolved, and v1 only seeds it

**There is no way to know the screen surfaces the right names**, and v1 does not attempt to find
out. Delisted names return zero rows on Yahoo, so any replay is survivorship-biased upward with no
free fix.

What v1 does instead is **accumulate seven streams that are unbiased and irrecoverable if not
started at launch** — all landing through the one dated, append-only write path:

1. Listing-file snapshots (what was listed)
2. Universe membership (what was rankable)
3. Percentile rank + raw return per (name, lookback) (where it ranked)
4. Detections with trigger levels (what was signalled)
5. The raw signal vector behind every detection (so a corrected rubric replays backwards)
6. Sector and ranked-industry shares (whether leadership preceded the moves)
7. Stop width per detection (so the eye-vs-§7 question is answerable)

**The cheapest questions forward history can answer, in order of cost:**

- **Was the detector swap an improvement?** ~140 cards per arm, affordable. The two populations are
  already distinguishable in the archive *provided `detector_version` is written*.
- **Do the ~2.9 US rows/night of lapsed resumers behave like breaks?**
- **Does §7 actually bind under its own ruler?** Pure computation on daily bars (§4.6).
- **What happens next to the two `line_ok` populations?** Their arms are already in the archive at
  23,605 vs 22,375 detections. They break at 0.62× the rate — but a rule about which setups
  *complete* is not a rule about which setups are *good*.
- **Does the star score predict returns?** **~672 triggered setups per band** to resolve 0.3R,
  against 33 available at five stars. Effectively unaffordable, and fragile: completing a single ×1
  dimension once reversed the ordering of the top two star bands.

> **⚠ The one result that could invalidate rather than calibrate the score.** On 27 graded charts
> **neither the trader nor the machine graded in the direction outcomes went.** At n=27 that means
> nothing on its own — but the eye is now known to be reproducible (+0.846 over 30 pairs), so
> "the grader is just noisy" is **no longer available** as an explanation. If a later study
> reproduces that finding at a workable n, it is a **real disagreement between the eye and returns**,
> and this map has no rule for which one wins. The eye is the arbiter only by necessity.

### 9.2 The score is weak against a reproducible target

ρ = +0.292 against a ceiling of +0.846 — about a third of what is achievable. Three tickets tried to
close it and the gap did not move. It is the largest known shortfall in v1, and it lands on the sort
order of the only list in the app.

**What would trigger a rethink:** any decision that makes the 4★ cut load-bearing (a star floor, a
digest rule firing on a band, a sizing posture computed from the score) — because the rubric runs
cold (18.3% ≥4★ against the eye's 35.2%) and its recall at the cut is currently only descriptive.

### 9.3 The detector swap rests on a null

The nightly list changed by **three quarters of its contents** on a name-level comparison that came
back **+0.40★ at p = 0.298** — directionally favourable, not significant. What *was* significant is
the **drawing**: the trader picked the base+cluster geometry **10 of 11 times** (p = 0.011) over the
old 3-bar window. The trader took the full swap knowing the split, and knowing the rubric was
refitted on the new structure in between, which makes it expensive to reverse.

**The cheap fallback, if the geometry ever looks wrong:** ticket 08's detector plus **only** the
cluster (`08 + a cluster ≤ 1.25 × ADR`) lands at today's list length for **one** parameter, with the
old rubric intact. Working preserved in `prototypes/17-base-cluster/hybrid.py`.

### 9.4 Twenty-two borrowed numbers, none fitted

Every detector parameter is a `q-scanner-v2` default. Ticket 19 classified them rather than fitting
them, because **the graded set cannot fit detector parameters** — it contains only names the
detector emitted, so it cannot see what a parameter change would newly admit.

**Five can move anything** (§4.5). **`TIGHT_MULT` is the one that matters, and it is not a detection
parameter — it is the stop budget.**

**What would trigger a rethink:** moving `TIGHT_MULT`, `K_MIN` or `K_MAX` moves the digest with them
— those three define the cluster, and the cluster high **is** the trigger. Nothing in the digest's
*rules* depends on their values; every *number* does.

### 9.5 The four knowing omissions

| Omission | Cost | Cheapest reversal |
|---|---|---|
| §5's backside veto unenforced | A rolled-over name can reach the list | Needs 60-min bars — not free |
| IDX limit days unhandled | A locked bar flatters both ×2 dimensions at once | Measured near-harmless under the split (98.5% clean) |
| Volume expansion unscored | §3.5's volume dimension permanently half-measured | Would make the score state-dependent — deliberate |
| **No adjustment-drift detector** | Up to six days of seam artefacts read as price action | **A 20-bar overlap check at zero extra requests.** One-line change |

Each is a **hypothesis that something does not matter**, and none is testable until there is forward
history.

### 9.6 Open questions, parked deliberately

Not blocking the build; recorded so they are not rediscovered from scratch.

- **Watchlist persistence and user state.** v1 remembers nothing. The storage half is trivial (one
  more dated table, and the append-only shape already fits a mark-and-unmark log); the product half
  was answered *by omission* — the screen inventory contains no marking of any kind. Nobody has
  explicitly ruled it in or out. **A one-session question.**
- **The catch-up test.** It **does not separate** (+0.03★ on a full 33-card arm, p = 0.910), same as
  the line test that was demoted. It stays a gate for two reasons: it is worth only 0.95 US names a
  night, and **catch-up is probably not a quality rule at all** — §3.1 wants price back at the 10/20
  so the *stop* is close, which is a statement about entry. *"Is there a setup here you would want
  to see tonight"* is the wrong ruler for it, and a null under the wrong ruler is not evidence. This
  is the map's pattern three times over (also the §7 stop, and ticket 24): **a risk rule measured
  with a quality ruler.** It needs a different question, not more cards.
- **List levels.** §4.8. Free to compute on the first real run.
- **The two owed stop measurements.** §4.6.

---

## 10. Appendix — every free number in v1, in one place

| Number | Value | Where | Status |
|---|---|---|---|
| IDX liquidity floor | Rp 1B/day median-20d | §4.1 | reference value, not tuned |
| US liquidity floor | $20M/day median-20d | §4.1 | reference value, not tuned |
| Minimum bars | 20 non-phantom | §4.1 | structural (ADR needs 20) |
| Density gate | 16 of 20 sessions, latest bar within 3 | §3.4 | default, "not sacred" |
| Hysteresis band | enter ≥1.0×, leave <0.8× | §4.1 | measured as targeted (25 IDX / 141 US names in band) |
| Finality margin | close + 30 min | §3.4 | structural |
| Request pacing | 12 req/s | §3.3 | measured (99.93% in 8.5 min) |
| Run completeness gate | ~99% | §3.4 | low bar in practice |
| Sector cache roll | 1/30th nightly | §3.3 | bounded 30-day staleness |
| Lookbacks | 1w / 1m / 3m / 6m / 12m | §4.3 | §3.1 widened deliberately at both ends |
| Board size | 30 rows | §4.3 | over-determined (§1's 1–2%; IDX's decile) |
| Rank retention | 2 years rolling | §4.3 | trader's call over unbounded |
| Rotation temporal window | 20 sessions | §4.4 | inherited from §2/§3.5, not invented |
| Rotation eligibility | `k ≥ 2` | §4.4 | §10's "strength clusters", literal |
| Industry board floor | `n ≥ 10` | §4.4 | derived (the point where one name ≤ 10pp) |
| Sector confirmation | LOO share ≥ 10% on 1m | §4.4 | 10% is the decile baseline itself |
| `MOVE_WINDOWS` | 21 / 42 / 63 / 126 | §4.5 | borrowed, frozen |
| `MAX_BASE_LEN` | 45 | §4.5 | **live** |
| `MIN_BASE_LEN` | 3 | §4.5 | §3.1's own minimum |
| `K_MIN` / `K_MAX` | 3 / 7 | §4.5 | K_MIN **live**, K_MAX frozen |
| `TIGHT_MULT` | 1.5 | §4.5 | **live — and it is the stop budget** |
| `CATCHUP_10` / `CATCHUP_20` | 1.0 / 2.0 ×ADR | §4.5 | borrowed, frozen |
| `OVER_W` : `UNDER_W` | 3 : 1 | §4.5 | ratio only |
| `SLOPE_STEPS` | 200 | §4.5 | discretisation, frozen |
| `MAX_SLOPE_ADR` | 0.5 | §4.5 | near-saturated, frozen |
| `TOUCH_TOL_ADR` | 0.35 ×ADR | §4.5 | **live** (one decision with the next three) |
| `MIN_TOUCHES` | 2 | §4.5 | decides nothing alone (OR clause) |
| `MIN_TOUCH_GAP` | 3 bars | §4.5 | **live** |
| `reaches_back` | 0.6 × base_len | §4.5 | **live** |
| `MAX_OVERSHOOT_ADR` | 1.0 ×ADR | §4.5 | **live — the number doing the cutting** |
| Detection decile gate | top decile in any of 1m/3m/6m | §4.5 | 1w and 12m excluded for stated reasons |
| `cluster_k` threshold | ≥ 5 | §4.7 | **fitted, published, stable** |
| `ord_lo` / `ord_hi` | 0.30 / 0.60 | §4.7 | **fitted, published**; upper edge barely tested |
| `len_ok` | ≤ 14 | §4.7 | **⚠ unfitted at this n** |
| `dryup` | ≤ 0.95 | §4.7 | **⚠ unfitted at this n** |
| Prior-move point | percentile ≥ 0.90 | §4.7 | fixed by ticket 06 |
| ADR point | ≥ 5% | §4.7 | fixed by §3.5 |
| Star mapping | `points ÷ 2` | §4.7 | §3.5's own, unchanged |
| Regime slope lookback | 5 sessions, sign-only | §4.9 | no magnitude threshold anywhere |
| Regime warm-up | 25 index bars | §4.9 | SMA20 + slope lookback |
| §7 stop cap (display only) | 1 × ADR | §4.6 | §3.5's own; **never a filter** |
| Bar history depth | 10 years | §7.1 | headroom for validation |

**Deleted, and staying deleted:** `MA_PROX_ADR` (dead code), `MAX_OVERSHOOT_FRAC` (redundant),
the prior-move 25% floor (redundant against the decile gate), the `max(line, cluster_high)` clamp
(dead by identity), the `TRIGGERED` state (unreachable), D10's MA-distance threshold (retired), and
every per-market parameter split (none is needed).
