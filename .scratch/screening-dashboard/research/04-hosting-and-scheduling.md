# Free-tier hosting and scheduling for a Python nightly job + TS frontend

Research note for ticket `04-free-tier-hosting-and-scheduling.md`.

**As-of date: 2026-08-04.** Every number below was read from the vendor's own docs/pricing page on this
date. Free-tier terms change frequently — treat anything older than ~3 months as stale and re-verify
before committing. Claims that could **not** be confirmed against a primary source are marked
**[UNVERIFIED]**.

---

## 0. TL;DR

1. **No hosted free-tier row store is big enough** for years of daily bars across thousands of symbols.
   Neon 0.5 GB, Supabase 500 MB, Cloudflare D1 500 MB/database. The footprint estimate is ~2 GB in
   Postgres for 10y × 7,000 symbols. This forces a **file-based columnar store (Parquet/DuckDB) on
   object storage** for the bar history. Turso (5 GB) is the one hosted SQL exception, and it breaks on
   *write quota* during backfill rather than on size.
2. **Almost every serverless free tier's execution timeout is a hard blocker**: Netlify scheduled
   functions 30 s, Supabase Edge Functions 150 s, Vercel Hobby functions 300 s, Cloudflare Workers free
   10 ms *CPU*. Only **GitHub Actions (6 h/job)** and **Cloud Run Jobs (up to 168 h)** comfortably fit a
   multi-minute nightly pull.
3. **GitHub Actions is viable as the scheduler**, with two caveats that both have workarounds: cron
   timing is explicitly best-effort (delays are documented, worst around the top of the hour), and
   scheduled workflows in **public** repos auto-disable after 60 days of no repository activity. For an
   EOD job, timing slop of tens of minutes is harmless.
4. Recommended stack: **GitHub Actions (private repo) → Parquet/DuckDB in Cloudflare R2 → precomputed
   JSON → static TS frontend on Vercel Hobby, protected by Vercel Authentication.** Cost $0. First
   thing to break: the 2,000 Actions minutes/month private-repo budget.

---

## 1. The two hard blockers, measured

### 1.1 Maximum execution time for a scheduled job, per free tier

| Platform | Scheduled-job mechanism | Max execution time (free) | Python? | Source |
|---|---|---|---|---|
| **GitHub Actions** | `on: schedule` cron | **6 hours per job** (GitHub-hosted runners) | Yes, any | [Actions limits](https://docs.github.com/en/actions/reference/limits) |
| **Google Cloud Run Jobs** | Cloud Scheduler → job | **168 hours (7 days)** max task timeout, 10 min default | Yes, any container | [Task timeout](https://docs.cloud.google.com/run/docs/configuring/task-timeout) |
| **Render cron jobs** | Native cron service | 12 h, but **min $1/month per cron job service** — not free | Yes | [Render cron jobs](https://render.com/docs/cronjobs) |
| **Vercel Hobby** | Vercel Cron → Function | **300 s** (Hobby default *and* maximum) | Yes (Python runtime) | [Function limits](https://vercel.com/docs/functions/limitations) |
| **Supabase** | `pg_cron` → Edge Function | **150 s** wall clock (free), 2 s CPU, 256 MB | No — Deno/TS only | [Edge Function limits](https://supabase.com/docs/guides/functions/limits) |
| **Netlify** | Scheduled functions | **30 s** ("Background functions are more appropriate for tasks that must run longer" — but background functions are *not* schedulable) | No — JS/TS, Go | [Scheduled functions](https://docs.netlify.com/build/functions/scheduled-functions/) |
| **Cloudflare Workers (free)** | Cron Triggers | 15 min wall clock but **10 ms CPU per Cron Trigger invocation** | Python Workers = Pyodide, restricted packages | [Workers limits](https://developers.cloudflare.com/workers/platform/limits/) |
| **Cloudflare Containers** | — | **No free tier** — "does not include any billable resources for vCPU, memory, or disk"; requires Workers Paid $5/mo | Yes | [Containers pricing](https://developers.cloudflare.com/containers/pricing/) |
| **Fly.io** | Machines / `fly machine run` | **No free tier for new orgs.** "Fly.io no longer offers plans to new customers"; free allowances only grandfathered for pre-2024-10-07 Hobby/Launch/Scale orgs. Card required. | Yes | [Fly pricing](https://fly.io/docs/about/pricing/) |
| **Railway** | Cron service | Free plan gives **$1/month usage credit**, 1 vCPU / 0.5 GB / 1 replica | Yes | [Railway pricing](https://railway.com/pricing), [plans](https://docs.railway.com/reference/pricing/plans) |

**Verdict on the timeout blocker.** A nightly pull of thousands of symbols is network-bound and will
plausibly take 5–30 minutes even with batched requests and concurrency. That rules out Netlify (30 s),
Supabase Edge Functions (150 s), Cloudflare Workers free (10 ms CPU), and makes Vercel Hobby (300 s)
uncomfortably marginal — you would have to shard the universe across multiple cron invocations, and
Hobby crons are capped at **once per day each** (see §1.3), so sharding means N separate daily crons at
fixed hours. Workable but fragile.

GitHub Actions' 6-hour job budget makes the timeout question disappear entirely. That is the single
biggest architectural fact in this ticket.

**Railway free-plan cost model** (rates: $10/GB-RAM/month, $20/vCPU/month, $0.15/GB-month volume,
$0.05/GB egress — [Railway pricing reference](https://docs.railway.com/reference/pricing)):
a 15-min nightly job × 2 markets × 30 days = 900 min/month ≈ $0.42 CPU + $0.10 RAM ≈ **$0.52/month**,
which does fit inside the $1 credit. But a 24/7 frontend service at 0.5 GB would cost ≈ $5/month —
5× the credit. So Railway free can host *the job* or *nothing else*, and with essentially no headroom.

### 1.2 GitHub Actions as scheduler — the specific risks

Primary-source facts:

- **Cron is best-effort.** "The `schedule` event can be delayed during periods of high loads of GitHub
  Actions workflow runs. High load times include the start of every hour."
  ([Events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows))
- **Finest granularity is 5 minutes.** "The shortest interval you can run scheduled workflows is once
  every 5 minutes." (same source)
- **Public repos auto-disable after 60 days.** "In a public repository, scheduled workflows are
  automatically disabled when no repository activity has occurred in 60 days."
  ([Disable and enable workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows))
  Note the doc scopes this to **public** repositories; nothing equivalent is stated for private ones.
- **Scheduled workflows only run on the default branch**, on its latest commit.
- **Minutes:** public repos on standard GitHub-hosted runners are **free**: "GitHub Actions usage is
  free for self-hosted runners and for public repositories that use standard GitHub-hosted runners."
  Private repos on the Free plan get **2,000 minutes/month**, 500 MB artifact storage, 10 GB cache/repo.
  ([Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions))
- **Concurrency:** 20 concurrent jobs on Free.

**[UNVERIFIED]** Whether a commit pushed *by the workflow itself* (using `GITHUB_TOKEN`) counts as
"repository activity" for the 60-day timer is not stated in GitHub's docs. Community reports suggest
bot-authored commits may not reset it. Do not rely on the nightly data commit to keep a public repo's
schedule alive; either use a private repo, or add a monthly human commit / `workflow_dispatch` ping.

**Is this viable?** Yes, for an EOD screener. The failure mode of cron slop is "the leaderboard is ready
at 22:40 UTC instead of 22:05 UTC", which is irrelevant for a once-a-day user. Mitigations:

- Schedule at an odd minute well away from `:00` (e.g. `17 22 * * 1-5`) to dodge the documented
  top-of-hour load spike.
- Make the job idempotent and add a `workflow_dispatch` trigger so a missed/failed run can be replayed.
- Have the job assert "did yesterday's bars land?" and self-heal by backfilling gaps, so a skipped run
  costs nothing.
- Prefer a **private** repo: it sidesteps the 60-day disable rule entirely, at the cost of the 2,000
  min/month budget.

### 1.3 Two market calendars

- **GitHub Actions**: a workflow may declare multiple `schedule` entries, or you can use two workflow
  files. There is no quota on *number of schedules* — only on minutes consumed, so two runs/day
  doubles minute usage but not any other limit. IDX close 16:00 WIB = 09:00 UTC; US close 16:00 ET =
  20:00 UTC (21:00 UTC during EST). Give each a couple of hours of settle time.
- **Vercel Hobby**: 100 cron jobs per project, but **"Hobby accounts are limited to cron jobs that run
  once per day"** and scheduling precision is **per-hour (±59 min)** — "a cron job configured as
  `0 1 * * *` will trigger anywhere between 1:00 am and 1:59 am."
  ([Cron usage & pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing)). Two daily crons is
  fine; ±59 min is fine for EOD.
- **Cloudflare Workers**: max **5 Cron Triggers per account** on free. Two is fine.
- **Cloud Scheduler**: **3 jobs/month free per billing account**, $0.10/job/month after.
  ([Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing)). Two is fine; the third is
  your headroom.
- **Supabase Cron (pg_cron)**: jobs "can run anywhere from every second to once a year"; guidance is
  "Each Job should run no more than 10 minutes" and "no more than 8 Jobs run concurrently".
  ([Supabase Cron](https://supabase.com/docs/guides/cron)). **[UNVERIFIED]** the Supabase pricing page
  does not state Cron plan availability; the extension is Postgres-level so it is expected to work on
  Free, but confirm before depending on it.

Nothing about two calendars doubles a *quota* except compute minutes.

---

## 2. Persistence: footprint vs. free caps

### 2.1 The footprint estimate

Assumptions (adjust once the data-source ticket lands):

- US tradeable universe after liquidity filtering: ~3,000–6,000 symbols. Full listed universe incl.
  ETFs is larger (~8,000+ tickers).
- IDX: ~950 listed companies.
- Worst case combined: **~7,000 symbols**.
- 252 trading days/year.

| History | Rows (7,000 symbols) |
|---|---|
| 5 years | ~8.8 M |
| 10 years | ~17.6 M |
| 20 years | ~35 M |

Per-row on-disk cost (OHLCV + volume + symbol + date), engineer's estimates:

| Format | Bytes/row (incl. index) | 10y × 7,000 symbols |
|---|---|---|
| PostgreSQL heap + PK btree | ~110–130 | **~2.0–2.3 GB** |
| SQLite / libSQL (D1, Turso) | ~45–60 | **~0.8–1.1 GB** |
| Parquet (zstd, dictionary + delta) | ~8–20 | **~150–350 MB** |

These are my calculations from format overheads, not vendor figures — **[UNVERIFIED]**, but the
order-of-magnitude conclusion is robust: Postgres is ~5–10× larger than Parquet for this shape of data.

### 2.2 Free storage caps

| Store | Free cap | Verdict for full bar history | Source |
|---|---|---|---|
| **Cloudflare R2** | **10 GB-month storage, 1 M Class A ops, 10 M Class B ops, egress free** | ✅ 30× headroom for Parquet. Zero egress fees is the standout. | [R2 pricing](https://developers.cloudflare.com/r2/pricing/) |
| **GitHub Releases** | 2 GiB per file; **"There is no limit on the total size of a release, nor bandwidth usage"**; 1,000 assets/release | ✅ Effectively unlimited free object store. | [About releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases) |
| **Turso** | **5 GB storage**, 100 databases, **500 M rows read/mo**, **10 M rows written/mo**, 3 GB syncs | ⚠️ Size fits; **write quota does not** — a 17.6 M-row backfill exceeds a month's writes in one shot. | [Turso pricing](https://turso.tech/pricing) |
| **Cloudflare D1** | **500 MB per database**, 5 GB per account, 10 DBs, 50 queries/invocation, 30 s query timeout | ❌ 500 MB/DB ≈ 5–6 years at best; would require manual sharding across 10 DBs. | [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) |
| **Neon** | **0.5 GB/project**, 100 CU-hours/project/mo, 5 GB egress, autosuspend after 5 min (**"cannot disable"** on Free) | ❌ ~1.5–2 years of the full universe. Writes fail when over cap. | [Neon plans](https://neon.com/docs/introduction/plans), [pricing](https://neon.com/pricing) |
| **Supabase** | **500 MB database**, 1 GB file storage, 5 GB egress, 2 active projects, **"Free projects are paused after 1 week of inactivity"** | ❌ Same as Neon. File storage 1 GB is also thin for Parquet. | [Supabase pricing](https://supabase.com/pricing) |
| **Google Cloud Storage** | Always Free: **5 GB-months regional (US only)**, 5,000 Class A, 50,000 Class B, 100 GB egress from NA | ✅ for Parquet; needs a billing account. | [GCP Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features) |
| **Git repo (files in-tree)** | 100 MiB hard block per file; **"repositories remain small, ideally less than 1 GB, and less than 5 GB is strongly recommended"** | ⚠️ Only for small precomputed artifacts, never the full history — and daily commits of a binary blob balloon git history. | [Large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) |
| **Actions artifacts** | 500 MB on Free plan | ❌ Too small, and artifacts expire. | [Actions limits](https://docs.github.com/en/actions/reference/limits) |
| **Render free Postgres** | 1 GB, **"expire 30 days after creation"**, 14-day grace then deleted | ❌ Self-destructs monthly. | [Render free](https://render.com/docs/free) |
| **Plain SQLite on disk** | Render free has **no persistent disks**; Fly volumes are $0.15/GB-mo (no free tier for new orgs); Railway free volume 0.5 GB | ❌ as a *server-attached* disk. ✅ as a **SQLite/DuckDB file pulled from object storage at job start and pushed back at job end**. | [Render free](https://render.com/docs/free), [Fly pricing](https://fly.io/docs/about/pricing/) |

**Answer to the ticket's question: yes, storage forces a file-based store.** No free hosted row store
holds 10 years × 7,000 symbols. The sane shape is:

- **Bars → Parquet (partitioned by market/year) in R2**, read by the nightly job with DuckDB/Polars.
- **Precomputed outputs → small JSON/Parquet artifacts** (leaderboards, star scores, sector rotation,
  chart series for the ~100–300 surfaced candidates). This is a few MB, servable statically.
- **App state (watchlist, marked names, run metadata) → tiny SQL DB**, where 500 MB is absurdly
  generous. Turso, D1, Neon, or Supabase all work here. Or just a JSON blob in R2.

The crucial design move: **the frontend never queries the bar history.** It reads precomputed
artifacts. That removes the need for a queryable hosted DB over 17 M rows, which is exactly the thing
no free tier provides.

Rough artifact sizing: 300 candidates × 250 daily bars × ~40 bytes of JSON ≈ **3 MB**. Trivially inside
Vercel's 100 GB Fast Data Transfer or Netlify's 100 GB bandwidth.

---

## 3. Python + TS on one platform, or split?

Nothing free hosts both well:

- **Vercel** has a Python runtime for Functions, so a single repo *could* hold both — but the 300 s cap
  and Hobby's once-per-day cron make the nightly job awkward, and Hobby is **non-commercial only**:
  "the Hobby plan restricts users to non-commercial, personal use only"
  ([Hobby plan](https://vercel.com/docs/plans/hobby)). A personal trading screener is fine; a paid
  product is not.
- **Netlify** functions are JS/TS and Go — **no Python at all**. Netlify is a frontend host only here.
- **Cloudflare** Python Workers are **open beta**, Pyodide-based: "Python Workers support pure and
  PyEmscripten Python packages on PyPI" plus Pyodide-bundled packages; you **cannot install arbitrary
  PyPI packages**, and only async HTTP clients (aiohttp/httpx) work
  ([Python Workers](https://developers.cloudflare.com/workers/languages/python/),
  [packages](https://developers.cloudflare.com/workers/languages/python/packages/)). Combined with the
  10 ms free CPU cap, Cloudflare is a **storage + edge + auth** layer on free, not a Python runner.
- **Hugging Face Spaces** — previously a common free Python host — is now out: "Gradio and Docker
  Spaces run on compute and **require a paid plan** to create"; only Static Spaces are free.
  ([Spaces overview](https://huggingface.co/docs/hub/spaces-overview))

**So a split deploy is unavoidable.** The complexity cost is small if you split along the artifact
boundary: the Python job's only contract with the frontend is "write these JSON/Parquet files to this
bucket with this schema". No shared runtime, no RPC, no CORS-authenticated DB from the browser. Version
the artifact schema and stamp each with a `generated_at` and `schema_version`.

---

## 4. Cold starts, sleeping, eviction

For a once-a-day user, sleeping is nearly a non-issue — but eviction is not.

| Platform | Behaviour | Matters? |
|---|---|---|
| Render free web service | Spins down after **"15 minutes without receiving any inbound traffic"**, **"about one minute"** to spin back up; 750 free instance hours/month/workspace | One-minute wait once a day. Annoying but survivable. |
| Neon free | Autosuspend **after 5 min**, "Always on for Free", cannot disable. Data is not deleted. | Sub-second-to-seconds resume. Fine. |
| Supabase free | **Projects paused after 1 week of inactivity**; 2 active projects | Fine while the nightly job touches it daily; a 2-week holiday pauses it. |
| Render free Postgres | **Deleted 30 days after creation** (+14-day grace) | **Disqualifying.** |
| Vercel Hobby | Static assets on CDN; functions cold-start | Negligible. |
| Cloudflare Pages/Workers/R2 | No sleep concept | Negligible. |
| GitHub Actions (public repo) | Schedule disabled after **60 days** no repo activity | Real risk — see §1.2. |
| Fly.io | Machines auto-stop/suspend to save cost — but there is no free tier to save into | N/A. |

**Static-first frontends (Vercel/Cloudflare Pages/Netlify) have no sleep problem at all**, which is
another argument for the precomputed-artifact architecture.

---

## 5. Auth — cheapest way to keep a public URL private for one user

| Option | Cost | Notes |
|---|---|---|
| **Vercel Authentication** (deployment protection) | **Free on Hobby** | Listed under Deployment Protection for Hobby: "Vercel Authentication". Password Protection is a **Pro add-on**. Requires you to be logged into the Vercel account that owns the project. Zero code. ([Hobby plan](https://vercel.com/docs/plans/hobby)) |
| **Cloudflare Access** (Zero Trust) | Free plan exists; **[UNVERIFIED]** the widely-cited 50-seat free cap is not restated on any current `developers.cloudflare.com` page I could find — only in Cloudflare blog/community posts. Docs confirm a "Zero Trust Free plan" exists and that Access covers "SaaS, self-hosted, and non-HTTP applications" with One-time PIN login. ([Cloudflare One setup](https://developers.cloudflare.com/cloudflare-one/setup/), [Access policies](https://developers.cloudflare.com/cloudflare-one/policies/access/)) | Works in front of *any* origin proxied through Cloudflare, including Pages and a Worker API. One-time-PIN to your email, or Google/GitHub IdP. The most portable option. |
| **Netlify password protection** | **Paid** | Not on Free. |
| **GitHub Pages private sites** | Enterprise only | Out. |
| **Roll your own** (signed cookie / shared secret in Worker or Next middleware) | Free | ~30 lines. Adequate for one user, but you own the security. Use for the API layer if Access/Vercel Auth already covers the UI. |

Recommendation: **Vercel Authentication** if the frontend is on Vercel (zero effort), **Cloudflare
Access** if anything is on Cloudflare or you want one gate across multiple origins. Do not put secrets
in the frontend; the R2 bucket should either be private (proxied through an authenticated route) or
hold only non-sensitive derived data.

---

## 6. Three end-to-end stacks

### Stack A — Actions + R2 + Vercel  *(recommended)*

| Layer | Choice | Free-tier headroom |
|---|---|---|
| Job runner | **GitHub Actions**, private repo, `ubuntu-latest` | 6 h/job cap (never binding); 2,000 min/mo |
| Scheduler | Two `schedule` crons in one workflow (IDX ~11:00 UTC, US ~22:00 UTC), off-the-hour minutes, plus `workflow_dispatch` | No quota on schedule count |
| Bar store | **Cloudflare R2**, Parquet partitioned by market/year; job pulls with DuckDB/Polars, writes back | 10 GB free vs ~300 MB used; egress free |
| Output artifacts | Small JSON (leaderboards, scores, chart series) written to R2 or committed to repo | few MB |
| App state | JSON blob in R2, or Turso if you want SQL | trivial |
| Frontend | **Next.js/TS static + a few routes on Vercel Hobby** | 100 GB transfer, 1 M invocations |
| Auth | **Vercel Authentication** (free on Hobby) | — |
| **Total cost** | **$0** | |

**Tradeoffs.** Simplest thing that clears both hard blockers. No hosted DB to outgrow. The frontend
cannot do ad hoc queries over history — everything must be precomputed nightly, which constrains
interactive features (e.g. "re-rank with a different lookback on the fly" needs to be enumerated
ahead of time). Debugging a job means reading Actions logs.

**First thing that breaks as the universe/history grows:** the **2,000 private-repo Actions minutes per
month**. Two runs/day × 30 days leaves ~33 min average per run; add retries, backfills, and a widening
universe and you hit it. Escapes, in order of preference: (a) flip the repo public → unlimited standard-
runner minutes, accepting the 60-day inactivity rule and public code; (b) move only the heavy pull to
Cloud Run Jobs; (c) trim the universe with a liquidity pre-filter so you only fetch names that can
possibly qualify.

Second thing to break: R2 Class A (write) operations at 1 M/month — only if you write one object per
symbol per day (7,000 × 2 × 30 = 420 k, still inside, but a per-symbol-per-day layout is the wrong
choice anyway; partition by year).

### Stack B — Actions + Turso + Cloudflare Pages

| Layer | Choice |
|---|---|
| Job runner + scheduler | **GitHub Actions** (same as A) |
| Store | **Turso** — 5 GB, 100 DBs, 500 M rows read/mo, 10 M rows written/mo |
| Frontend | **Cloudflare Pages** + a Worker API querying Turso over HTTP |
| Auth | **Cloudflare Access** |
| **Total cost** | **$0** |

**Tradeoffs.** You get real SQL at the edge, so the UI *can* do ad hoc ranking and drill-down without
precomputing every view. Costs: a second vendor, and the Worker API sits inside the free Workers
envelope (100 k req/day, 10 ms CPU, 50 subrequests/request) — fine for one user, but the 10 ms CPU cap
means the Worker must be a thin proxy, not a compute layer.

**First thing that breaks:** **Turso's 10 M rows written per month.** A single full historical backfill
(~17.6 M rows for 10y × 7,000 symbols) blows through a whole month's write quota in one run. You would
have to backfill across two calendar months, or backfill into Parquet and only keep a recent window
(e.g. 2 years ≈ 3.5 M rows) in Turso. Steady-state nightly writes (~7,000 rows/day ≈ 210 k/month) are
nowhere near the limit — it is purely a cold-start / re-backfill problem. Second to break: the 500 M
rows-read budget, if the UI does full-universe scans (a 1-year × 7,000-symbol scan reads ~1.76 M rows,
so ~280 such scans/month).

### Stack C — Cloud Run Jobs + GCS + Vercel

| Layer | Choice |
|---|---|
| Job runner | **Cloud Run Jobs** — task timeout up to 168 h; Always Free 180,000 vCPU-s, 360,000 GiB-s, 2 M requests/month |
| Scheduler | **Cloud Scheduler** — 3 jobs/month free (we need 2) |
| Store | **GCS** 5 GB Always Free (US regions) as Parquet, or R2 |
| Frontend | **Vercel Hobby** static + routes |
| Auth | **Vercel Authentication** |
| **Total cost** | **$0**, but a **credit card is required**: "A Google Cloud billing account is required to access the Google Cloud Free Tier" |

**Tradeoffs.** The most generous compute ceiling by far — 180,000 vCPU-s = 50 vCPU-hours/month, against
a nightly need of maybe 15 h. Real container images, real dependency management, real logs. The costs
are operational: GCP setup (project, service account, Artifact Registry, IAM) is materially more work
than a `.github/workflows/*.yml`, and unlike every other option here, **overrunning the free tier bills
you rather than stopping you**. Set a budget alert and a hard `--max-retries` on the job.

**[UNVERIFIED]:** whether the Cloud Run Always Free allowance applies to **Jobs** as well as Services.
The GCP Free Tier page lists Cloud Run without distinguishing the two, and I could not fetch the full
Cloud Run pricing page (truncated/redirect-looped) to confirm. Verify before relying on it.

**First thing that breaks:** GCS Always Free is **5 GB in US regions only** and 5,000 Class A ops/month
— the op count is the sharper edge (a per-symbol-per-day write layout would exceed it immediately).
After that, the 180,000 vCPU-s compute allowance at ~35 min/run × 60 runs.

---

## 7. Recommendation

**Stack A.** Reasons, in order:

1. It is the only stack where the nightly job's runtime is a **non-question** (6 h budget vs a job that
   should take under 30 min), and job timeout was the ticket's stated hard blocker.
2. It requires **no credit card anywhere** and cannot silently bill.
3. Parquet-in-R2 has ~30× headroom on the realistic footprint, so the storage blocker is also
   answered outright, and it is the format DuckDB/Polars are fastest against — which matters for the
   compute half of the nightly job (indicators over 17 M rows).
4. Auth is one toggle (Vercel Authentication), not an IdP integration.
5. Every piece is independently replaceable: swap Vercel for Cloudflare Pages, swap R2 for GCS, swap
   Actions for Cloud Run Jobs — the contract between layers is "files in a bucket".

**Add Stack B's Turso later, not now**, and only if the dashboard turns out to need interactive queries
that cannot be precomputed. Keep it as a *hot window* (last 1–2 years) alongside the Parquet archive of
record, which sidesteps the 10 M-writes/month backfill wall.

**Do not** build on: Netlify (30 s scheduled functions, no Python), Supabase or Neon as the bar store
(500 MB), Render free Postgres (deleted after 30 days), Fly.io (no free tier for new orgs),
Cloudflare Containers (paid only), Hugging Face Spaces (now paid for Docker/Gradio).

---

## 8. Open items to re-verify before build

- **[UNVERIFIED]** Does a `GITHUB_TOKEN`-authored commit reset the 60-day public-repo schedule timer?
  (Moot if the repo is private.)
- **[UNVERIFIED]** Does Cloud Run's Always Free tier cover Jobs, not just Services?
- **[UNVERIFIED]** Cloudflare Zero Trust free seat count (widely reported as 50; not found on a current
  primary docs page today).
- **[UNVERIFIED]** Supabase Cron / pg_cron availability specifically on the Free plan.
- **[UNVERIFIED]** All per-row storage estimates in §2.1 are my own arithmetic from format overheads,
  not vendor figures. Measure with a real 1,000-symbol sample before committing to a store.
- The real universe size and history depth are still open (`map.md` §"Not yet specified"). If the data
  source only gives 2–5 years, Turso and even D1-with-sharding come back into play and Stack B becomes
  more attractive.
- Netlify's free plan has moved to a **credits** model ("300 credit limit") whose conversion rates I
  could not read from a primary page today; the commonly cited legacy figures are 100 GB bandwidth /
  300 build minutes / 125,000 function invocations. **[UNVERIFIED]** — but Netlify is disqualified on
  the 30 s scheduled-function limit and lack of Python regardless.

## Sources

- [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits)
- [GitHub Actions: events that trigger workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
- [GitHub Actions: disable and enable workflows](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows)
- [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
- [GitHub: about large files](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)
- [GitHub: about releases](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Cloudflare D1 limits](https://developers.cloudflare.com/d1/platform/limits/)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/) / [R2 limits](https://developers.cloudflare.com/r2/platform/limits/)
- [Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/)
- [Cloudflare Containers pricing](https://developers.cloudflare.com/containers/pricing/)
- [Cloudflare Python Workers](https://developers.cloudflare.com/workers/languages/python/) / [packages](https://developers.cloudflare.com/workers/languages/python/packages/)
- [Cloudflare One setup](https://developers.cloudflare.com/cloudflare-one/setup/) / [Access policies](https://developers.cloudflare.com/cloudflare-one/policies/access/)
- [Vercel function limits](https://vercel.com/docs/functions/limitations) / [Vercel limits](https://vercel.com/docs/limits) / [Hobby plan](https://vercel.com/docs/plans/hobby) / [cron usage & pricing](https://vercel.com/docs/cron-jobs/usage-and-pricing)
- [Netlify scheduled functions](https://docs.netlify.com/build/functions/scheduled-functions/) / [Netlify pricing](https://www.netlify.com/pricing/)
- [Render free tier](https://render.com/docs/free) / [Render cron jobs](https://render.com/docs/cronjobs)
- [Railway pricing](https://railway.com/pricing) / [plans](https://docs.railway.com/reference/pricing/plans) / [rates](https://docs.railway.com/reference/pricing)
- [Fly.io pricing](https://fly.io/docs/about/pricing/)
- [Neon plans](https://neon.com/docs/introduction/plans) / [Neon pricing](https://neon.com/pricing)
- [Supabase pricing](https://supabase.com/pricing) / [Edge Function limits](https://supabase.com/docs/guides/functions/limits) / [Supabase Cron](https://supabase.com/docs/guides/cron)
- [Turso pricing](https://turso.tech/pricing)
- [Google Cloud Free Tier](https://docs.cloud.google.com/free/docs/free-cloud-features) / [Cloud Run task timeout](https://docs.cloud.google.com/run/docs/configuring/task-timeout) / [Cloud Scheduler pricing](https://cloud.google.com/scheduler/pricing)
- [Hugging Face Spaces overview](https://huggingface.co/docs/hub/spaces-overview)
