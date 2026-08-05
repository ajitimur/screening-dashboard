# Ranking and decile model

Type: grilling
Status: resolved
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

## Answer

Resolved 2026-08-04 in a grilling session. Twelve decisions below. Every number in the "Measured"
section was produced during this session against live Yahoo data (`yfinance 1.5.2`, throwaway venv in
the job scratch dir, nothing installed into the project), applying the ticket-05 rule stack exactly as
written.

**The rule stack is reconstructible.** Rebuilding ticket 05's universe from its written decisions
alone reproduced its numbers exactly — **1,966 US / 288 IDX**. That is a check on the map itself, not
just on this ticket: the decisions are specified well enough that an independent session gets the same
population.

One principle runs through the answers: **the ranking model reports, it does not judge.** R8 (ADR does
nothing), R9 (pure return), R10 (no smoothing) and R12 (flag, don't promote) are all instances. Every
place where a filter, a normalisation or a damping could have been folded into the rank, it was instead
made a visible column, badge or toggle. The rank answers exactly one question — who moved most — and
every other judgement stays separable and inspectable. This is deliberate: §3.5 already scores quality
and ticket 08 already detects setups, so a ranking that also judged would be the third opinion in the
system and the only one you couldn't see inside.

### R1 — The §3.1 gate and the §1 leaderboard are two different cuts

Ticket 05 handed this over as urgent ("a decile of 1,966 is ~197, unreviewable"). The premise
conflated two consumers of the ranking:

- **The gate** feeds setup detection (ticket 08). Nothing human reads it. Its job is **recall** — never
  lose a real leader on a technicality — and 197 names passing is a compute cost, not a review cost.
- **The leaderboard** is read by a human in ~10 minutes and must be short.

Once separated, the "unreviewable" objection only ever applied to the leaderboard, and the two can take
different cuts without contradiction. Everything below follows from this split.

### R2 — Gate = union of top deciles across **1w / 1m / 3m / 6m / 12m**, per market

Any-of, not a composite. Each decile computed within that lookback's own population (D5).

Wider than §3.1's literal "1–6 month" on both ends, chosen deliberately: **1w** is §1's own scan #1
("up ≥ 30% in the past 5 days"); **12m** catches the long grinder that has been basing for a quarter
and whose short lookbacks have gone flat.

Rationale for any-of over a composite:
- A composite smears the horizons into one number, and the names it loses relative to the union are
  precisely the **sharp recent movers** — 85th percentile on 1m, 50th on 3m, 40th on 6m composites to
  nothing, but that is a stock that just woke up, which is what the method trades.
- **D5 makes a composite structurally awkward:** a 90-day-old IPO is *absent* from the 6m population,
  so a composite would need either to drop it or to fudge the weights around a missing leg. Under
  any-of it simply qualifies via 1m or 3m. The method explicitly wants freshly-listed movers.

**⚠ "Top decile" does not mean 10% and the spec must say so.** Unioned across five windows the gate
passes **~29% of the universe** (566 US / 82 IDX, measured). Anyone reading "top decile of 1–6 month
returns" will build for a tenth of the load and be wrong by 3×.

**No lookback is a passenger** — every one admits names no other does (measured below), so the
five-window choice is not padded.

### R3 — Five separate boards per market, not one merged board

Ten boards total. A merged board with per-lookback columns was proposed and **rejected by the trader**.

Recorded because it has a consequence: the merged design carried a signal — *how many windows a name
leads simultaneously* — that separate boards destroy. That signal is restored explicitly in R11 rather
than lost.

### R4 — Every board is **top 30**, constant in count

Not a percentile. The number is over-determined in a way worth recording:
- §1's own definition — a momentum leader is the **top 1–2% of gainers** — is 20–39 names on 1,966.
- IDX's natural decile is **29**.

So one constant serves both markets and is justified from the reference on both, rather than by
convenience. Measured, the distinct-name load across five top-30 boards is **112 US / 88 IDX** — a
genuine ten-minute pass, against 566/82 if the boards were deciles.

**Named cost:** on IDX a top-30 board and a top-decile board nearly coincide; on US they differ by 6×.
Accurate — it reflects the markets' real sizes — but it will feel inconsistent when switching markets.

### R5 — Rank history persists nightly, on a rolling **2-year** window

One row per (name, lookback, night), carrying **percentile rank and raw return**, for **every universe
member** — not only board members, or a name's history has holes exactly on the nights it was
interesting-but-not-quite.

Percentile rather than ordinal position, because ordinal rank is not comparable across nights when the
denominator moves — and D5 and D11 both move it.

This is the map's **fourth irrecoverable nightly stream** (with D11 universe membership, ticket 12
listing files, ticket 10 detected setups). Last night's ranks cannot be reconstructed later because the
universe they were ranked against is gone — hysteresis, sticky membership and the density gate together
make it unreproducible from today's data.

**It is also the first stream that discards.** Unbounded retention was recommended (~50 MB/year, and
locally there is no storage ceiling); the trader chose a bounded 2-year window. At steady state that
always covers the longest lookback twice over, so no in-app feature ever outruns it. **The sole casualty
is a future multi-year validation study** — and validation is already unsolved fog on the map. Cheap
hedge if it ever matters: a coarser permanent archive (weekly, or board members only) at a few MB/year.
Recorded as an accepted cost, not a gap.

### R6 — Ranking is a **shared service**; sector strength aggregates over it

The ranking emits a percentile rank per (name, lookback, night) — the R5 table — and ticket 07 defines
sector strength as an aggregation over it. There is to be no second, divergent notion of "strong."

Rationale:
- **Share-of-members-in-top-decile beats an index return**, and the difference is the whole point. A
  sector of 40 names where 8 are ripping and 32 are flat has a mediocre equal-weighted index return but
  a high share of top-decile members. That is exactly the sector to surface — leadership concentrates
  before it broadens, and the method trades leaders, not averages. An index dilutes the signal being
  hunted.
- **It erases a market asymmetry for free.** Per D1, IDX has essentially no sector-ETF reference set,
  so an index-based approach needs a computed index on IDX and could use a real ETF on US — two
  different metrics on two markets. Aggregating member ranks is identical on both by construction.

**Recommended primary metric for ticket 07: share of members in the top decile.** Ticket 07 still owns
the rotation definition and the exact aggregation; this ticket only guarantees the substrate and
forbids a competing definition.

**Named cost:** sector strength inherits every quirk of the ranking model — per-lookback denominators
(D5), the hysteresis band (D11). A sector whose membership shifts for liquidity reasons will show a
small strength move with no price action behind it.

### R7 — Returns are **calendar-anchored**, and this narrows D6

`return(D, L) = AdjClose(last final bar on or before D) / AdjClose(last final bar on or before D − L) − 1`,
with L in calendar terms (1w = 7 days, 1m/3m/6m/12m = calendar months). Adjusted closes per D9.

**This is a deliberate narrowing of D6**, which currently reads as universal ("windows count traded
bars, not calendar days"). D6 was aimed at ADR and median dollar volume, where "the last 20 days this
thing actually traded" is the right question. Returns are a different kind of window:

- **A board must compare like with like.** Under traded-bar counting, "3-month return" spans 3 calendar
  months for a name that trades every session and ~3.5 months for one missing 15% of sessions. They sit
  adjacent on the same board measured over different amounts of real time — and the longer window has
  more time to accumulate return, so **illiquid names are systematically flattered**.
- **The density gate bounds this but does not remove it.** D6 guarantees ≥ 16 of the last 20 sessions —
  a *recent*-window guarantee. Over 252 bars a name can carry a long past suspension and still qualify
  today, making its "12-month return" reach back 15 calendar months.
- **The distortion is worst on IDX**, where phantom bars live (ticket 01: 4% of bars).

So: **traded-bar windows for rolling statistics, calendar anchoring for returns.** The "last bar on or
before" rule handles weekends, holidays and phantom-dropped bars uniformly and needs no calendar
table — it falls out of the observed session set D6 already builds.

**D5's eligibility rule reads better under this**: a name is ranked in a lookback if it has a bar on or
before `D − L` — i.e. it was actually listed and trading that long ago. That is a truer statement of
"has that much history" than a bar count, and it stops a name with a sparse history from qualifying for
the 12m board on 252 bars spread over two years.

*Caveat on the measurements below: they were computed under traded-bar counting, before this decision.
The effect of calendar anchoring is a re-ordering at the margin, not a change in gate width.*

### R8 — ADR does **nothing** by default; one toggle, off, on both surfaces

ADR is a **column**. No filtering, no greying, no de-emphasis. A toggle hides sub-4% names; it is the
same control on the leaderboards and on the detected-candidate list, and it defaults **off** on each.

D3 left "post-rank filter" ambiguous once boards became constant-length — filter-then-take-30 (always
30 rows, but the market's biggest gainer silently absent if it is a 3-ADR name) versus
take-30-then-filter (honest, but variable length, possibly 12 rows).

Both were rejected. **Filtering before the cut reintroduces the exact failure D3 exists to prevent:**
D3 refused ADR as a universe gate because "a 3.5-ADR name that starts moving is a name whose ADR is
*becoming* 8," and gating evicts it on the eve of the move. A name that just ripped 40% in a week is by
construction a name whose trailing 20-day ADR has not caught up yet. Filtering the board commits that
error one stage later.

A split default was recommended (off on leaderboards, on for candidates) and **rejected by the trader
in favour of off everywhere** — one behaviour to remember instead of two. Nothing is ever hidden unless
the user hides it.

### R9 — Rank on **pure return**. No volatility adjustment

Measured, this is a large lever, not a refinement: normalising by ADR **replaces up to 20 of 30 rows**
on the US boards.

Rejected on three grounds:
1. **It answers a question the method does not ask.** §1's scans are "biggest gainers"; §3.1's gate is
   "top decile of returns." Both raw, consistently. The quantity hunted is *a big prior move*, not a
   big risk-adjusted move — the flag that forms afterwards does not care how volatile the ride was.
2. **ADR is already priced twice** — §3.5 scores it, R8 filters on it. Normalising would make it a third
   input and the only one **invisible**, buried inside the sort key. No row could be explained.
3. **It inverts his stated preference.** He explicitly takes the 7.6-ADR name over the 2.4-ADR ETF.
   Dividing return by ADR systematically demotes high-ADR names in favour of low-ADR names that moved
   less — the 3-ADR name that somehow gained 300% would top the board, and it is the name he rejects on
   sight.

**Named cost, to be written into the spec so nobody "fixes" it later:** the boards *will* be dominated
by high-volatility names, and a quiet 2-ADR mega-cap making a genuinely unusual 40% move may never
appear. Per point 3 this is the correct bias, but it is a real blind spot.

### R10 — No smoothing anywhere; new entrants carry a `NEW` marker

Measured churn is not one phenomenon:

- **Return churn** — the 1w board turns over **16 of 30 overnight on US**; every other board moves 1–4
  rows. The 1w figure is *honest*: one session is 20% of a five-day window. Smoothing it would lag the
  fastest signal in the system, and §1's scan #1 exists precisely to catch things the day they happen.
- **Denominator churn** — the universe moved under the ranking: **30 US and 8 IDX names** entered or
  left overnight, *even with D11's hysteresis band already damping it*. Pure artefact — a name's rank
  moves because 30 other names appeared.

Decision: no smoothing of returns, including on the 1w board. Instead a **`NEW` marker** on rows absent
from that board last session — which converts churn from noise-you-diff-by-eye into the most
informative thing on the page. On the 1w board, the 16 new names *are* tonight's news.

Denominator churn is **not corrected but is recorded**: ranks are computed against that night's
universe, and D11's membership snapshot already records what it was, so any future analysis can
reconstruct it. Holding the denominator fixed would mean ranking against a stale universe — worse.

**⚠ Consequence for future validation:** stored percentile ranks carry a **~1.5% noise floor** from
denominator churn. "This name's 3m percentile fell from 94 to 92" may be denominator, not price.

### R11 — Breadth badge `k/5` on every row

The count of lookbacks in which the name is currently top-decile. Free to compute — the gate (R2)
already computes all five deciles.

This restores the signal R3 destroyed. On separate boards, a name at #7 on the 3m board looks identical
whether it is a one-window spike or one of the three names leading every window at once — and those are
very different stocks. Measured, the distinction is real and non-degenerate: **55% of qualifying US
names are `1/5`, 111 are `≥3/5`, and only 3 of 1,964 are `5/5`.**

**Named cost:** it measures persistence, not magnitude, so it will sometimes disagree with intuition —
a name can be `1/5` and still be the biggest gainer of the week. It is **not** a quality score and must
not be presented as one.

### R12 — §1's "up ≥ 30% in 5 days" is a **flag on the 1w board**, not a separate board

Measured tonight: **20 US / 5 IDX** names clear the threshold, and **all of them are already on the 1w
top-30 board** — zero missed. So the flag captures the scan exactly, keeps the constant-30 rule intact,
and keeps ten boards from becoming twelve.

It is an absolute threshold rather than a rank, which is why it cannot *be* a board without breaking
R4: in a dead tape it returns zero rows, in a hot one it returns a hundred.

**⚠ Accepted failure mode, explicitly chosen.** The US 1w board's cutoff is **26.2%**, and 20 of its 30
slots are already ≥30% names. In a hot tape more than 30 names clear 30% in five days and those ranked
below 30 **vanish silently** — the flag under-reports exactly when the scan matters most. Tonight's
zero-missed is a quiet-tape result, not a structural guarantee. An overflow rule (show the top 30 *or*
all names ≥30%, whichever is longer) was offered and **the trader chose to accept the failure mode
instead**, keeping the constant-count rule without exception.

---

## Measured — live Yahoo data, 2026-08-04, `yfinance 1.5.2`

Universe rebuilt from ticket 05's written decisions: **1,966 US / 288 IDX** — matching it exactly.
(The probe-2 run reports 1,964 / 286: it applies an explicit `≥ 20 bars` guard that ticket 05's script
left implicit. A two-name difference, noise not signal.)

### Gate width — union of top deciles

| | US | IDX |
|---|---|---|
| universe | 1,966 | 288 |
| **union of 5 deciles (1w/1m/3m/6m/12m)** | **566 — 28.8%** | **82 — 28.5%** |
| union of §3.1's 3 (1m/3m/6m) | 427 — 21.7% | 59 — 20.5% |
| cost of adding 1w and 12m | +139 (+33%) | +23 (+39%) |
| union of five **top-30** boards | 112 | 88 |

**The 28.8% / 28.5% agreement across two markets differing 7× in size is not coincidence** — a
percentile gate is self-normalising by construction. This is the measured form of R1's argument for
keeping the *gate* a percentile while the *board* is a count.

Per-lookback populations and decile cutoffs:

| lookback | US pop | US decile | US cutoff | IDX pop | IDX decile | IDX cutoff |
|---|---|---|---|---|---|---|
| 1w | 1,966 | 197 | +13.3% | 288 | 29 | +13.0% |
| 1m | 1,965 | 196 | +15.8% | 282 | 28 | +35.8% |
| 3m | 1,954 | 195 | +36.9% | 282 | 28 | +23.1% |
| 6m | 1,939 | 194 | +55.2% | 281 | 28 | +33.5% |
| 12m | 1,912 | 191 | +124.8% | 275 | 28 | **+285.7%** |

Two observations:
- **Populations shrink with the lookback** (1,966 → 1,912 on US), which is D5 working as designed.
- **IDX's 12m decile cutoff is +285.7%** — at the decile boundary an IDX 12-month leader has nearly
  quadrupled, against +124.8% on US. IDX momentum is far more extreme at the top than US.

Marginal contribution — names *only* that lookback admits:

| lookback | US unique / shared | IDX unique / shared |
|---|---|---|
| 1w | 70 / 127 | 11 / 18 |
| 1m | 101 / 95 | 10 / 18 |
| 3m | 58 / 137 | 3 / 25 |
| 6m | 32 / 162 | 9 / 19 |
| 12m | 49 / 142 | 9 / 19 |

### Breadth — top-decile in k of 5 lookbacks (R11)

| k | US | IDX |
|---|---|---|
| 1 | 311 (54.9%) | 42 (51.2%) |
| 2 | 144 (25.4%) | 26 (31.7%) |
| 3 | 74 (13.1%) | 10 (12.2%) |
| 4 | 34 (6.0%) | 3 (3.7%) |
| **5** | **3 (0.5%)** | **1 (1.2%)** |

### Volatility adjustment — top-30 overlap, raw return vs return/ADR (R9)

| lookback | US | IDX |
|---|---|---|
| 1w | 10/30 | 19/30 |
| 1m | 17/30 | 17/30 |
| 3m | 12/30 | 23/30 |
| 6m | 12/30 | 21/30 |
| 12m | 18/30 | 27/30 |

Normalising is a different product, not a refinement — and it bites hardest on US, the market with the
wider ADR spread.

### Churn — top-30 turnover vs the previous session (R10)

| lookback | US | IDX |
|---|---|---|
| 1w | **16 in / 16 out** | 10 in / 10 out |
| 1m | 4 | 4 |
| 3m | 2 | 2 |
| 6m | 4 | 2 |
| 12m | 1 | 2 |
| universe membership change | **30 names** | **8 names** |

### §1 scan #1 — "up ≥ 30% in the past 5 days" (R12)

| | US | IDX |
|---|---|---|
| 1w top-30 cutoff | +26.2% | +12.8% |
| up ≥ 20% in 5 bars | 80 (**50 missed** by the board) | 13 (0 missed) |
| **up ≥ 30% in 5 bars** | **20 (0 missed)** | **5 (0 missed)** |
| up ≥ 50% in 5 bars | 4 (0 missed) | 3 (0 missed) |

The ≥20% row is the warning: at a slightly lower threshold the board already misses 50 of 80 US names.
The ≥30% flag works tonight because only 20 names clear it — see R12's accepted failure mode.

## An operational note worth carrying forward

Probe 2 lost a completed 5,467-symbol US pull because the IDX screener rate-limited immediately
afterwards and the cache was written only after *both* markets had been fetched. This is **ticket 05's
D7 hazard biting a first-party script**, not a third-party surprise: the pull succeeded, the process
died, the work evaporated.

**Hand to ticket 12:** the nightly pipeline must **persist each market's pull the moment it completes**,
not at the end of the run. Two markets in one run means one market's rate limit can otherwise discard
the other's completed work — and D7's run-level completeness gate would then quarantine a run whose
data had actually been fetched successfully.

## Findings handed to other tickets

- **→ Ticket 07 (sector/theme and rotation):** ranking is a shared service (R6). Sector strength is an
  aggregation over the (name, lookback, night) percentile-rank table, with **share of members in the
  top decile** the recommended primary metric — it surfaces concentrated leadership, which an
  equal-weighted index return dilutes. Ticket 07 still owns rotation and the exact aggregation.
- **→ Ticket 08 (setup detection):** the §3.1 precondition gate is the **union of top deciles across
  1w/1m/3m/6m/12m**, which passes **~29% of the universe (566 US / 82 IDX)** — not 10%. Size the
  detection pass for that load.
- **→ Ticket 11 (dashboard IA):** ten boards (5 lookbacks × 2 markets), 30 rows each; every row carries
  ADR, the `k/5` breadth badge, a `NEW` marker, and a ≥30%-in-5-days flag on the 1w board; one
  ADR-toggle control, default off. Distinct-name load per market is 112 US / 88 IDX.
- **→ Ticket 12 (architecture):** persist rank history nightly — (name, lookback, night) with percentile
  and raw return, all universe members, **rolling 2-year window**. Plus the operational note above:
  persist each market's pull as it completes.
- **→ Ticket 13 (v1 spec):** two things must be stated explicitly or they will be misread — **"top
  decile" passes ~29%, not 10%** (R2), and **the boards are deliberately biased toward high-ADR names**
  (R9).

## Amendment to a ticket-05 decision

**D6 is narrowed by R7.** "Windows count traded bars, not calendar days" applies to rolling statistics
(ADR, median dollar volume) — its original target. **Returns are calendar-anchored.** Ticket 05's D6
should be read with this qualification.

## Probe scripts

Disposable, in the job scratch dir — `rank_union.py`, `rank_probe2.py`, `scan1.py`, plus cached bar
pickles. Throwaway venv; nothing installed into the project.
