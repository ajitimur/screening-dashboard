# Architecture and local runtime shape

Type: grilling
Status: resolved
Blocked by: 05

## Question

What is the runtime shape of this app, end to end, running on your own machine?

v1 runs locally with a live backend — the UI may query the store freely rather than reading precomputed
views. Hosting is out of scope (see the map), so this ticket is about the local pipeline and the local
serving path, not deployment.

- **Pipeline stages** — ingest → adjust/normalise → compute indicators (ADR, MAs, returns) → rank →
  detect setups → score. Which run nightly in full, which are incremental, and what is materialised
  versus computed on request? Locally, compute is cheap and the tradeoff is your patience, not a quota.
- **Store** — DuckDB file, SQLite, or Parquet on disk queried by DuckDB? Driven by the actual footprint
  from ticket 05's universe size × history depth, and by which one makes the detection work (ticket 08)
  fastest to iterate against.
- **Two calendars** — IDX closes 16:00 WIB, US 16:00 ET, ~12 hours apart, with different holidays.
  Two scheduled runs or one that handles whichever market last closed? And what actually triggers them
  on a laptop that is sometimes asleep — cron, a launchd job, or you running a command?
  **Ticket 01 pins the IDX side:** the 2026-08-04 bar was final at 19:49 WIB, so a **≥19:00 WIB**
  schedule is safe; earlier is unproven and would need measuring.
- **Rate-limit pacing — settled empirically, needs implementing.** Tickets 01, 02 and 03 all hit
  throttling independently. Ticket 02 measured it: unthrottled returns **52.9%** of the US universe,
  **12 req/s returns 99.93% in 8.5 minutes**. Yahoo fails as silence — throttled symbols come back as
  "possibly delisted; no price data found" — so the pipeline must pace, back off, and **distinguish
  throttling from genuinely missing data**, or a bad night silently halves the universe and blames
  delisting. (The 12 req/s figure was measured from a residential IP, which is what a local v1 is.)
- **The partial-bar problem (ticket 02)** — while a session is open, Yahoo already serves a bar dated
  today containing only the hours traded so far. US and IDX sessions are disjoint, so **there is no
  single safe run time**. Decide the guard: run each market only after its own close (≥19:00 WIB for
  IDX per ticket 01), discard any bar dated today unless the session has closed, or validate bar
  completeness explicitly. This is a correctness issue, not a scheduling nicety — a partial bar
  corrupts ADR, gap and volume math silently.
- **Point-in-time universe snapshots** — ticket 02 recommends snapshotting the Nasdaq listing files
  (and the IDX screener result) nightly from day one, accumulating a survivorship-free universe going
  forward. Cheap now, impossible to backfill later. Decide whether v1 does this even though validation
  is not yet designed.
- **Missed runs** — a laptop misses nights. Does the app detect a gap on next launch and backfill it
  automatically? This matters more locally than it would on a server.
- **Backend/frontend boundary** — a local Python API (FastAPI or similar) that the TS frontend queries.
  Confirm, and settle what the API surface looks like: per-screen endpoints, or a general query layer?
- **Failure handling** — the nightly pull will fail sometimes (rate limits, source breakage). Does the
  app serve yesterday's data with a staleness banner? Retries? How do you find out it failed, given
  there is no alerting infrastructure?
- **Backfill** — the first run pulls years of history for thousands of symbols. How long does that
  take, is it resumable, and is the snapshot committed/archived so it survives a machine rebuild?
- **Reproducibility for the detection work** — tickets 08 and 09 need a frozen data snapshot to iterate
  against, so results don't shift under them as new bars arrive. How is that snapshot pinned?
- **Repo layout** — one repo, two apps (Python + TS)? Where the shared domain vocabulary lives, and how
  the frontend learns the backend's types.
- **Portability** — how much of this design would survive being hosted later? Note the choices that
  would be expensive to reverse, without designing for hosting now.

- **History depth — graduated from the map's fog into this ticket by ticket 05.** The data-source
  research it was waiting on is done, and ticket 05 fixed the demand side, so this is now purely a
  storage decision. Constraints: ranking lookbacks run to **24 months** (§1), so ~3 years is the
  functional minimum and 5 years gives comfortable headroom; ticket 01 measured **5 years × 840 IDX
  names ≈ 904k bars ≈ 50 MB**, and running locally removes any storage ceiling. Depth is therefore
  cheap — decide it, don't agonise.
- **Two nightly snapshots to store**, both cheap and both only useful if started early: listing files
  (already on this ticket) and, added by ticket 05 (D11), **universe membership** — one row per name per
  night, so a future validation can ask what was *rankable* that night, not merely what was listed.
- **Pipeline invariants this ticket must preserve**, all from ticket 05: an `unresolved` third state
  distinct from absent; **sticky membership** (removal needs positive evidence, never a failed fetch);
  **run quarantine** when < ~99% of symbols resolve, leaving the last good run serving with a banner;
  an **exchange-clock finality rule** dropping provisional bars at ingest; and the exchange calendar
  derived from observed bar dates rather than a hardcoded holiday table. The store needs to hold **both**
  adjusted and unadjusted series (D9).
- **Rate limiting is a hard requirement, not a nicety.** Ticket 02 measured an unthrottled pull
  returning only **52.9%** of the universe while reporting the losses as "possibly delisted"; 12 req/s
  gives 99.93% in 8.5 min. Combined with run quarantine, an unthrottled ingester would simply never
  publish.

Resolve against ticket 05's universe size — now measured: **288 IDX / 1,966 US** names, ~2,250 total
symbols to pull nightly. Ticket 04's free-tier findings are **background only** — v1 is not constrained
by them.

**Owed to ticket 10 (market regime filter):** a **nightly setup-snapshot table** (symbol, date, trigger
level) written every run from launch — a third forward-accumulating capture alongside the listing files
and universe membership already on this ticket. Ticket 10 also needs index bars for `^IXIC` and
`^JKSE` ingested on the same path as equities.

## Answer

**One DuckDB file, one command per market, and every derived table is dated rows.** Everything below is
that plus nine decisions, three of which went against the session's recommendation and are recorded with
their costs rather than smoothed over.

The ingest set is the **enumerated** universe, not the tradeable one — liquidity is measured *from* bars,
so **~6,550 symbols** are pulled (840 IDX + 5,711 US per tickets 01/02) of which 288/1,966 survive ticket
05's gate. That number, not 2,250, sizes every cost below.

### A1. The store is a single DuckDB file

`data/screener.duckdb` holds bars and every derived table. Columnar, so the whole-universe scans that
ranking (5 lookbacks × 2,254 names) and detection do are fast; full SQL, so the map's standing "a live
backend is assumed — the UI may query the store freely" holds without precomputed views.

The decisive property is **the reproducibility freeze tickets 08/09/15 need is `cp`**. One file, no
partition layout, no manifest — a pinned snapshot is a filename. SQLite was rejected on the iteration loop
(row-store scans, and this project keeps returning to that loop); Parquet-on-disk was rejected because the
six accumulating streams want row-level appends and Parquet is bad at exactly that.

**Footprint is a non-issue and is measured, not estimated.** A separate implementation of this same
universe (`~/Projects/q-scanner-v2`, see A10) holds 6,838 tickers × ~900 days as parquet in **146 MB**;
scaled to A7's ten years that is **~580 MB**, and DuckDB compresses at least as well.

### A2. Ingest is incremental append with a weekly full refresh

Nightly asks each symbol for bars since its last stored one. A **full-universe 10y refetch runs weekly**.

This went against the session's recommendation, which was to refetch everything nightly on the grounds
that **the ingest cost is per-request, not per-bar** — 6,550 requests at ticket 02's measured 12 req/s is
~9 minutes whether you ask for one day or ten years, so a full rebuild is free in wall clock and immune to
ticket 01's invisible rights adjustments. The trade taken instead is bandwidth (~600 MB/night saved) and
compute against a bounded correctness window. Recorded because A3 is where the bill arrives.

### A3. No drift detector — the weekly refresh is the only repair, and the append seam is a knowing omission

Ticket 01 established that Yahoo applies **rights adjustments invisibly** (BBRI rescaled 10/11 with no
split or dividend entry), so an incrementally-appended adjusted series can go wrong undetectably.

Two repairs were put and both declined, in favour of one mechanism rather than two:

1. A **20-bar overlap check** — request the last 20 bars instead of the new one (identical request count,
   so still ~9 minutes), compare the 19 overlapping adjusted closes and volumes against the store, and
   full-refetch any symbol that disagrees. Declined.
2. An **off-cycle refetch of symbols with a Yahoo-reported split or dividend** — a handful nightly,
   covering every *visible* action and leaving only the invisible IDX rights cases to leak. Declined.

**The accepted cost, stated plainly:** an appended bar arrives on the new basis while stored history sits
on the old one, so for up to six days the seam reads as a **real overnight gap** — and ticket 08's detector
reads gaps as price action. The failure is not "slightly stale numbers"; it is a spurious detection or a
wrong ADR on any name that had a corporate action that week. It is bounded, self-healing on the weekly
refresh, and confined to the affected names, which are a small fraction nightly.

This is the fourth knowing omission on this map, alongside ticket 08's three. Like those, it is a
hypothesis — that a six-day seam on a handful of names does not change what reaches the top of the list —
and like those it is untestable until there is forward history. **It is also the cheapest of the four to
reverse:** repair 1 costs no extra requests, so if a seam artefact is ever seen on a chart, turning it on
is a one-line change rather than a redesign.

### A4. Every derived table is dated rows, appended and never rewritten

Universe membership, ranks, sector shares, detections, scores, signal vectors — all keyed by
`(market, session, …)`. "Tonight" is `WHERE session = (SELECT max(session) …)`.

This **collapses the map's six owed capture streams into the normal write path** rather than bolting six
captures alongside a current-state store. There is one set of facts, and the thing the app reads *is* the
thing the archive holds, so they cannot disagree. It also makes ticket 14's digest backfillable over
history exactly as 14 assumed, and lets ticket 15 replay a corrected rubric backwards over accumulated
signal vectors.

**Derived rows are written once and never rewritten.** They are a point-in-time record of what was
knowable that night; rewriting them after a rescale would inject look-ahead into the very streams the map
is accumulating *because* they are unbiased. Backfill (A6) therefore only ever fills **absent** sessions.

### A5. Runs are per market — two `launchd` jobs, with run-on-open as the fallback

Ticket 11's I1 made market the top-level axis, so there is no global nightly job. Two jobs:
**≥19:00 WIB** for IDX (ticket 01 measured the 2026-08-04 bar final at 19:49 WIB; earlier is unproven) and
**≥17:00 ET** for US. `launchd`'s `StartCalendarInterval` fires a missed job once on wake, so a sleeping
laptop delays a run rather than losing it.

On top of that, **opening a market tab whose last final session is missing from the store kicks a run**
with a progress state. Two mechanisms, and the second is deliberate: it is the honest answer to "the
machine was shut", and it means the app is never silently a day stale. Run-on-open alone was rejected
because a ~9-minute US pull does not fit inside §1's 10-minute nightly budget; manual-only was rejected
because a forgotten night is invisible until you notice the as-of date.

### A6. Missed sessions are backfilled for everything derivable; as-of captures are stamped, never faked

Bar history heals itself for free — you ask for everything since the last stored bar. The derived rows
split on one line:

- **Derivable from bar history** — universe membership, ranks, detections, scores, signal vectors. These
  are deterministic functions of bars, so recomputing session T−3 today gives what it would have given on
  the night. The run computes every session between the last computed one and the latest final session, so
  a week away costs seconds of compute and leaves **no hole** in the accumulating streams.
- **As-of only** — listing-file snapshots and sector/industry labels. These cannot be reconstructed
  (that is ticket 02's survivorship point). They are stamped with the run date and **never backfilled**, so
  a gap there is visible and honest rather than fabricated.

One wrinkle is accepted: backfilling from today's bars uses today's adjusted basis for a past session.
Ticket 05 established that almost every quantity in the method is a **ratio**, and a uniform rescale
cancels in a ratio, so this is immaterial — the same property that made ticket 01's unrecoverable raw IDX
prices cost nothing.

### A7. Ten years of bar history

Ranking lookbacks run to 24 months (§1), so 3 years is the functional floor. Ten was chosen over the
recommended five for headroom on whatever validation eventually becomes possible — the map's largest fog
patch — at roughly **~580 MB** (A1) and a longer weekly refresh. Local running removes any ceiling and
the weekly refresh re-pulls this depth anyway, so it is a fixed cost, not a growing one. IDX history
reaches back to ~2000–2004 and US is ample, so ten years is available on both.

### A8. Resource endpoints; the frontend composes the workbench

`/api/regime/{market}`, `/api/candidates/{market}`, `/api/sectors/{market}`, `/api/boards/{market}`,
`/api/chart/{market}/{symbol}`, `/api/runs/{market}`.

Chosen over screen-shaped endpoints (one call returning the whole workbench). The workbench costs 3–4
round trips against a local backend, which is free, and the surfaces stay independently addressable. The
cost is that assembly moves to the frontend and there are now five payloads to keep in sync — which is
what A9 pays for. A general query layer was rejected: no schema contract to generate types from, and the
domain logic would migrate to the frontend.

### A9. One repo; TS types generated from the OpenAPI schema

```
backend/     Python package — pipeline stages, DuckDB access, FastAPI app
frontend/    Vite + React + TS
data/        screener.duckdb, digests/
CONTEXT.md   domain vocabulary (glossary only)
docs/adr/    decisions that outlive this map
```

Pydantic response models give FastAPI an OpenAPI schema for free; `openapi-typescript` turns it into
committed `.d.ts`, regenerated by a script. A renamed field becomes a **typecheck failure rather than a
runtime `undefined`** — which matters more under A8, where five payloads compose one screen. FastAPI
serves the built frontend, so it is **one process on one URL**.

### A10. lightweight-charts, porting `renderChart.ts` from `q-scanner-v2`

TradingView's renderer (Apache 2.0, ~45 KB, canvas). Candles, line series and histogram volume are
first-class; ticket 11's I5 trigger and base-low stop are `createPriceLine`; **the two fitted trendlines
are line series over the base window**, which draws them *as fits* with candles piercing them in both
directions — exactly what §3.2 requires and what a purpose-built trendline widget would have "fixed".

`~/Projects/q-scanner-v2/web/src/renderChart.ts` (lightweight-charts v5, React 18, Vite) already draws
candles, SMA 10/20/50, volume histogram, and dashed trigger/stop price lines against a FastAPI payload.
**It is ported as the starting point.** I5 then needs four additions it does not have: the **65 EMA**
(§2's one daily exponential), the **two fitted lines** over the base window, the **shaded base window**,
and **volume with base bars distinguished** for ticket 08's dry-up dimension. Expansion is not drawn — per
08's D11 it exists only at the break.

**The rest of `q-scanner-v2` is deliberately not adopted.** It is a working implementation of
substantially this app and its architecture answers several questions above differently (parquet+SQLite,
~2.5y depth, manual runs, hand-written frontend types, and — notably — a working `adjusted_close` overlap
drift detector of exactly the kind A3 declined). It also diverges from the *map*: its pattern engine is
built on tunable `PatternParams` with an eval sweep where ticket 08 arrived at a zero-tunable detector by a
different method, and its IDX sectors come from the exchange's IDX-IC xlsx where ticket 03 ruled IDX-IC out
in favour of Yahoo GECS on both markets. Adopting it as the baseline was put as an explicit fork and
declined; this map's decisions stand as taken. Recorded because it is prior art a future session would
otherwise rediscover — and because its `eval/labels` + `--sweep` machinery is the shape of what ticket 15
is specified to build.

### Forced by earlier tickets, not decided here

Listed so the build session does not have to re-derive them:

- **Pacing.** 12 req/s (ticket 02: unthrottled returns 52.9% of the universe while reporting the losses as
  "possibly delisted"; 12 req/s gives 99.93% in 8.5 min, measured from a residential IP, which is what a
  local v1 is). Exponential backoff on 429. **An empty result is `unresolved`, never absent** — the map's
  standing "Yahoo fails as silence" property.
- **Quarantine is per market.** A run resolving < ~99% of symbols is quarantined and does not publish; the
  last good run keeps serving with a banner (ticket 05 D3/D7/D11). Membership is sticky — removal needs
  positive evidence, never a failed fetch.
- **Partial-bar guard.** The exchange-clock finality rule drops provisional bars at ingest (ticket 05), and
  the exchange calendar is derived from observed bar dates rather than a hardcoded holiday table. A5's
  schedule means a run only ever sees its own market's closed session.
- **Both series stored.** Adjusted and unadjusted (ticket 05 D9); dollar volume is the one unadjusted
  quantity.
- **Index bars.** `^IXIC` and `^JKSE` ingest on the same path as equities (ticket 10).
- **How you find out a run failed.** Ticket 14 already answered this: **empty nights still write the
  digest file**, so a missing `digests/<market>/<session>.md` means a failed run. No alerting layer is
  needed and none is built.
- **First-run backfill** is resumable by construction — a symbol with bars at the target depth is done, so
  an interrupted backfill resumes by re-running. ~9 minutes per market pass; ten years of payload makes
  the first run bandwidth-bound rather than request-bound.
- **Reproducibility freeze** for tickets 08/09/15 is `cp data/screener.duckdb snapshots/<date>.duckdb`
  (A1). Nothing else is needed because nothing lives outside the file.

### Pipeline stages, in order, per market run

1. Snapshot the listing files (as-of, never backfilled) → 2. ingest bars (incremental, or full on the
weekly pass) → 3. hygiene: drop phantom zero-volume bars, apply the finality rule → 4. resolve the
universe (liquidity, instrument type, listing age, 80%/3-session density) → 5. indicators (ADR, MAs,
returns) → 6. ranks, 5 lookbacks → 7. sector and ranked-industry shares → 8. detection → 9. score →
10. write the digest → 11. write the run record.

Stages 4–9 are recomputed in full from bars every run and rerun per backfilled session (A6). The
sector/industry label cache is the one incremental piece and its policy is already fixed by ticket 07:
**new names block, 1/30th rolls nightly, a failed fetch never nulls.**

### Portability — what would be expensive to reverse if hosting ever happens

Hosting is out of scope, but two choices are worth naming. **A1 travels well**: ticket 04's research
independently landed on file-based columnar storage for this footprint, so a DuckDB file on object storage
is the same shape. **A2 does not travel**: a weekly full refetch of 6,550 symbols × 10y assumes a
residential IP and unmetered bandwidth, and ticket 04 found serverless execution timeouts rule out
everything except GitHub Actions and Cloud Run Jobs. A5's `launchd` is macOS-specific and trivially
replaced. Nothing here is designed for hosting, and nothing here forecloses it.

### Hand-offs

- **Ticket 13 (assemble the v1 spec)** — A1–A10 plus the stage list and table shape are the architecture
  section. Note that A3 is a stated defect with a bounded cost, not a clean decision; the spec should carry
  it as such.
- **Ticket 15 (star-score thresholds)** — A1's `cp` freeze is the pinned snapshot 15 needs, and A4's
  dated signal vectors are what let a corrected rubric be replayed backwards. Separately, `q-scanner-v2`'s
  `eval/labels` + `qs eval --sweep` (A10) is a working instance of the grading-and-sweep loop 15 is
  specified to build; it currently holds 10 labels, and 15's own question is how many charts are enough.
- **The validation fog patch** — A4 is what makes the patch tractable: all six streams now land through
  one write path, dated, from launch. A3 adds a small caveat to it — a name with a corporate action may
  carry up to six days of seam artefacts in its stored history, so a future study should treat the week
  before a split as suspect.
