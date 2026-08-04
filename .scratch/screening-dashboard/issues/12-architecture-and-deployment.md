# Architecture and local runtime shape

Type: grilling
Status: open
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

Resolve against ticket 05's universe size. Ticket 04's free-tier findings are **background only** —
v1 is not constrained by them.

**Owed to ticket 10 (market regime filter):** a **nightly setup-snapshot table** (symbol, date, trigger
level) written every run from launch, alongside the listing-file snapshot this ticket already carries.
Both are forward-accumulating and irrecoverable if skipped. Ticket 10 also needs index bars for `^IXIC`
and `^JKSE` ingested on the same path as equities.
