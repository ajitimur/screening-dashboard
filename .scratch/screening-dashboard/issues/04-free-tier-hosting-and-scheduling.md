# Free-tier hosting and scheduling for a Python worker + TS frontend

Type: research
Status: resolved
Blocked by: —

## Question

What free-tier deployment options can host this app — a nightly Python data/compute job, a persistent
store, and a TypeScript frontend — for a single user?

Cover at minimum: Vercel, Netlify, Fly.io, Railway, Render, Cloudflare (Workers/Pages/D1/R2),
GitHub Actions as the scheduler, Supabase, Neon, Turso, and plain SQLite-on-disk.

Evaluate on:

- **Scheduled jobs** — can a cron-triggered Python process run on the free tier, and for how long?
  Nightly pulls of thousands of symbols may take many minutes. What are the hard timeouts?
- **Two market calendars** — IDX closes 16:00 WIB, US 16:00 ET, ~12 hours apart. Does the option allow
  two schedules, and does that double any quota?
- **Persistence** — free row/storage limits versus the likely footprint (years of daily bars ×
  thousands of symbols). Does anything force us to a file-based store (Parquet/DuckDB on object
  storage) instead of a hosted DB?
- **Python + TS together** — one platform, or a split deploy? What the split costs in complexity.
- **Cold starts, sleeping, and free-tier eviction** — does the app go to sleep and does that matter for
  a once-a-day user?
- **Auth** — cheapest way to keep a public URL private for one user.

Deliver two or three concrete viable stacks end to end (job runner + store + frontend + scheduler +
auth), with the tradeoffs and a recommendation, plus the first thing that would break if the universe
or history depth grew.

## Answer

Findings: [`research/04-hosting-and-scheduling.md`](../research/04-hosting-and-scheduling.md)
(~400 lines, primary-source citation per number, as-of 2026-08-04, 12 claims flagged `[UNVERIFIED]`).

**Three hard blockers found, and they largely determine the architecture:**

1. **Execution timeout disqualifies almost every serverless free tier.** Netlify scheduled functions
   30s; Supabase Edge Functions 150s; Vercel Hobby functions 300s (default *and* max); Cloudflare
   Workers free 10ms *CPU* per cron invocation. Only **GitHub Actions (6h/job)** and **Cloud Run Jobs
   (168h max)** clear a multi-minute nightly pull. Render cron has a 12h limit but carries a $1/month
   minimum, so it is not free.

2. **No free hosted row store holds the bar history.** Neon 0.5 GB/project, Supabase 500 MB, D1
   500 MB/database, against an estimated ~2 GB in Postgres for 10y × 7,000 symbols. Turso's 5 GB fits
   by size, but its 10M rows-written/month cap means one 17.6M-row backfill consumes a month's quota.
   Conclusion: **bars must live as Parquet/DuckDB on object storage**, not in a hosted SQL DB.

3. **GitHub Actions as scheduler is viable.** Documented cron delay is real but irrelevant to EOD —
   schedule off-the-hour. The 60-day inactivity auto-disable applies to **public** repos only, so a
   private repo sidesteps it, at the cost of the 2,000 min/month budget.

**Recommended — Stack A:** GitHub Actions (private repo) → Parquet in Cloudflare R2 → precomputed JSON
artifacts → static TS frontend on Vercel Hobby → Vercel Authentication. $0, no credit card anywhere.
The load-bearing move is that **the frontend never queries bar history** — it reads ~3 MB of nightly
precomputed artifacts, which is what removes the need for a queryable free DB over 17M rows. First
thing to break: 2,000 Actions minutes/month (escape hatch: flip the repo public).

Alternatives costed: **Stack B** (Actions + Turso + Cloudflare Pages + Cloudflare Access) buys edge SQL
for interactive drill-down, breaks first on Turso's write quota during backfill. **Stack C** (Cloud Run
Jobs + GCS + Cloud Scheduler) has the largest compute ceiling but requires a billing account and bills
on overrun.

**Caveats to carry forward:** Vercel Hobby is contractually non-commercial/personal use only. Two
previously-common answers are now dead — Hugging Face Spaces requires a paid plan for anything but
Static, and Fly.io has no free tier for new orgs. All per-row storage estimates are the agent's own
arithmetic, not vendor figures.

## Superseded — subject ruled out of scope

After this research landed, v1 was scoped to **run locally**, with hosting deferred to a later effort
and a paid tier (~$10–20/mo) pre-approved for it. The findings above are therefore **background for
that future effort, not binding constraints on v1**:

- The free-tier execution timeouts and storage caps do not apply to a local run.
- The precomputed-artifact model — the one architectural conclusion that would have shaped v1's
  backend/frontend boundary — **no longer applies**. Ticket 12 assumes a live local backend that the
  UI may query freely.

The research itself remains valid as of 2026-08-04; free-tier terms move fast, so re-verify before
relying on it.
