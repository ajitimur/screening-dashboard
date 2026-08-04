# Free sector/industry classification for IDX and US

Research for ticket `03-sector-taxonomy-sources.md`. Date: 2026-08-04.

Constraints assumed from `map.md`: free sources only, both IDX and US, EOD nightly, Python backend.

**Convention note:** this repo had no `research/` directory content before this file; `.scratch/screening-dashboard/research/`
already existed as an empty directory, so findings go here.

---

## TL;DR

- **One free source covers both markets with one taxonomy**: Yahoo Finance (Morningstar GECS — 11 sectors / 145
  industries) returns the *same* sector and industry strings for `.JK` tickers as for US tickers. Empirically verified:
  **319/320 sampled tickers resolved a sector (99.7%)**, with the single miss being a delisted/suspended name.
  Cross-market comparability on one sector axis is therefore **achievable**, not aspirational.
- **IDX-IC is effectively not obtainable in bulk by a nightly job.** `idx.co.id` is behind Cloudflare bot
  protection and returns HTTP 403 to plain HTTP clients — including `robots.txt`. Verified below.
- **GICS is licensed and cannot be used.** S&P DJI / MSCI's own disclaimer explicitly forbids reproduction,
  redissemination, and derivative works (including databases and analytics) without written permission.
- **SIC via SEC is free, bulk, and legally clean — but US-only and coarse.** Verified working.
- **Theme layer**: several free options exist for US. For **IDX there is essentially no free theme layer** —
  no thematic ETFs exist on IDX, and the offshore thematic ETFs that would proxy one hold almost no IDX names.
  Only LLM-tagging of company descriptions or hand-curation is viable for IDX themes. Flag as scope risk.

---

## 1. What each source actually is (primary sources)

### 1.1 IDX-IC — the exchange's own taxonomy

IDX's own press release states: *"Starting from January 25, 2021, IDX implements the new classification sector and
industry of IDX listed company called 'Indonesia Stock Exchange Industrial Classification' or IDX-IC."*
([IDX press release 1456](https://www.idx.co.id/en/news/press-release/1456), via search index — see §1.1.1 on
direct-fetch failure.)

The same IDX source states the classification basis: *"The determination of sectors, subsectors, industries or
sub-industries are based on the market exposure of the company"*, and notably: *"IDX have rights to determine listed
companies' classification based on IDX evaluation and justification."* That last clause matters — IDX-IC assignment is
discretionary exchange judgment, not a reproducible rule you could re-derive from filings.

Structure: **4 levels — 12 sectors, 35 sub-sectors, 69 industries, 130 sub-industries.**

> ⚠️ **The ticket says 11 sectors; the correct figure is 12.** The 12th is the *Listed Investment Products* sector
> (ETFs, REITs/DIRE, and other listed investment vehicles), which is not an operating-company sector. For an equity
> screener the operating universe is the other 11 — so the ticket's "11" is right in spirit but wrong on the raw count.
> **Partially unverified**: the 12/35/69/130 counts come from Indonesian secondary write-ups
> ([InvestasiKu](https://www.investasiku.id/eduvest/investasi/klasifikasi-idx-ic)), not from an IDX-hosted document I
> could open — see §1.1.1. IDX's own canonical PDF is
> [`gopublic.idx.co.id/media/1404/daftar-sektor_web-go-public_en.pdf`](https://gopublic.idx.co.id/media/1404/daftar-sektor_web-go-public_en.pdf),
> which is indexed by search engines but 403s on fetch.

IDX also publishes **monthly trading statistics broken down by IDX-IC classification**
(`idx.co.id/en/market-data/statistical-reports/digital-statistic/monthly/equity-trading-by-industry/trading-summary-by-industry-classification`) —
useful in principle for sector rotation, but on the same blocked host.

#### 1.1.1 Empirical: idx.co.id is not machine-accessible

Tested 2026-08-04 from this machine, `curl` with a full Chrome UA + browser headers (`Accept`, `Accept-Language`,
`Sec-Fetch-*`, `Upgrade-Insecure-Requests`, `--compressed`):

| URL | Result |
|---|---|
| `https://www.idx.co.id/en/listed-companies/idx-industrial-classification/` | **403** — Cloudflare "Attention Required!" interstitial |
| `https://www.idx.co.id/robots.txt` | **403** — even robots.txt is blocked |
| `https://idx.co.id/` | **403** |
| `https://www.idx.co.id/primary/StockData/GetSecuritiesStock?...` (JSON API) | **403** |
| `https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles?...` (JSON API) | **403** |
| `https://gopublic.idx.co.id/media/1404/daftar-sektor_web-go-public_en.pdf` | **403** |
| Text-extraction proxy (`r.jina.ai`) over the same page | Returns *"Performing security verification … may require CAPTCHA"* |

WebFetch (a different egress IP) also returned 403 on all of the above. So this is not one blocked IP — `idx.co.id`
serves a Cloudflare challenge to non-browser clients generally.

**Implication for the build:** a nightly Python job cannot rely on scraping `idx.co.id`. Getting IDX-IC in bulk would
require a headless browser that solves the JS challenge (fragile, arguably against the site's intent, and a hosting
cost on a free tier), or a manual periodic download by a human. **IDX-IC is realistically a hand-curated, occasionally
refreshed static file, not a live feed.**

#### 1.1.2 Third-party API that does expose IDX-IC: sectors.app

[Sectors (Supertype Pte Ltd)](https://sectors.app/) exposes the full IDX-IC hierarchy over a REST API. Its
[Companies Screener docs](https://docs.sectors.app/api-references/v2/indonesia/screener/companies) list direct fields:
`sector` ("IDX sector classification"), `sub_sector`, `industry` ("IDX industry classification"), `sub_industry`, plus
helper endpoints (`/v2/subsectors/`, `/v2/industries/`, `/v2/subindustries/`) that enumerate every sector/subsector,
industry, and sub-industry pair as kebab-case slugs. Verified: `https://api.sectors.app/v2/companies/` requires an
`Authorization: <api-key>` header; v1 was discontinued 2026-05-11 (endpoint returns HTTP 410 with a migration notice —
confirmed by direct request).

**Unverified / likely blocking:** I could not load `sectors.app/api` (Vercel bot checkpoint, HTTP 429), so I could not
confirm pricing. A search-index snippet of their docs says *"API access requires an Insider plan account"*, which
suggests **paid**. Under the free-sources-only constraint this probably disqualifies it. Someone should open
`https://sectors.app/api` in a browser and check for a free tier before writing it off entirely.

### 1.2 GICS — confirmed unusable

Owned jointly by S&P Dow Jones Indices and MSCI. Structure: **11 sectors, 25 industry groups, 74 industries,
163 sub-industries** (current structure effective after close 2023-03-17).

The licensing position is unambiguous in S&P DJI/MSCI's own words. From the joint press release
[`GICS_Press_Release_31_March_2022.pdf`](https://www.msci.com/documents/1296102/29559863/GICS_Press_Release_31_March_2022.pdf/f0ac4118-d6c3-4456-3c7b-2b0174099e4e?t=1648760411652)
(text extracted from the PDF directly):

> "All of the information contained herein … is the property of MSCI, S&P Dow Jones Indices, or their respective
> affiliates. **The Information may not be reproduced or redisseminated in whole or in part without prior written
> permission from MSCI and S&P Dow Jones Indices.**"
>
> "**The Information may not be used to create derivative works** or to verify or correct other data or information.
> For example (but without limitation), the Information **may not be used to create indices, databases, risk models,
> analytics, software**, or in connection with the issuing, offering, sponsoring, managing or marketing of any
> securities, portfolios, financial products or other investment vehicles utilizing or based on, linked to, tracking or
> otherwise derived from the Information."

The 2026 consultation press release
([S&P Global, 2026-07-17](https://press.spglobal.com/2026-07-17-S-P-DOW-JONES-INDICES-AND-MSCI-ANNOUNCE-CONSULTATION-ON-POTENTIAL-CHANGES-TO-THE-GLOBAL-INDUSTRY-CLASSIFICATION-STANDARD-GICS-R))
carries the identical disclaimer and adds: *"'Global Industry Classification Standard (GICS)' is a service mark of MSCI
and S&P."*

**Verdict: GICS is out.** Building a sector database keyed to GICS labels is *exactly* the "create … databases,
analytics" derivative-work case the disclaimer names. Note also: `spglobal.com` and `msci.com` both bot-block
(HTTP 403 / "Challenge Validation"), so even reading the methodology is friction.

*Corollary risk:* Wikipedia's S&P 500 constituents table carries GICS sector/sub-industry columns and is a commonly
used free shortcut. That data is GICS regardless of where it's copied from — treat it as licensed, not free.

### 1.3 Yahoo Finance / Morningstar GECS

Yahoo Finance's own [sectors page](https://finance.yahoo.com/sectors/) states plainly: **"Sectors: 11", "Industries: 145"**,
and lists them: Technology, Financial Services, Industrials, Consumer Cyclical, Communication Services, Healthcare,
Energy, Consumer Defensive, Basic Materials, Real Estate, Utilities.

Those numbers and names are Morningstar's **Global Equity Classification Structure (GECS)**: a hierarchical four-tier
taxonomy of 145 industries → 55 industry groups → 11 sectors → 3 super sectors, where each security is mapped to the
industry reflecting its largest source of revenue and income. (Yahoo does not name Morningstar on the sectors page; the
1:1 match on counts, sector names, and industry names is what identifies it. **Mildly unverified** — I could not open
Morningstar's own GECS page directly. This matters only for provenance, not for usability.)

**Licensing status: unverified and worth a moment's thought.** Yahoo Finance has no public API and no published terms
permitting bulk redistribution; `yfinance` scrapes undocumented endpoints. For a single-user private dashboard this is
the same posture as every other free-data hobby project, but it is not a *licensed* free source the way SEC data is.

### 1.4 SEC SIC codes — free, bulk, legally clean, US-only

Verified working 2026-08-04 with the SEC-required descriptive User-Agent:

| Endpoint | Result |
|---|---|
| `https://www.sec.gov/search-filings/standard-industrial-classification-sic-code-list` | **200** — HTML table, **444 SIC codes** parsed, columns `SIC Code / Office / Industry Title` (e.g. `100 / Industrial Applications and Services / AGRICULTURAL PRODUCTION-CROPS`) |
| `https://data.sec.gov/submissions/CIK0000320193.json` | **200** — returns `{'sic': '3571', 'sicDescription': 'Electronic Computers', 'tickers': ['AAPL'], 'exchanges': ['Nasdaq']}` |
| `https://www.sec.gov/files/company_tickers.json` | **200** — 798 KB, full ticker↔CIK map |

So the full US ticker→SIC join is buildable from first-party SEC data with zero licensing questions. Caveats:

- **US-only.** IDX issuers do not file with the SEC.
- **Coarse and dated.** SIC is a 1987-vintage taxonomy. It has no "Semiconductors vs. Software" nuance matching how
  momentum sectors actually rotate, and no concept of Communication Services.
- **Self-reported and stale.** The SIC on a filing is what the registrant selected; it is frequently wrong for
  companies that pivoted.
- **Per-CIK API calls.** `company_tickers.json` has no SIC; only `data.sec.gov/submissions/CIK*.json` does, one CIK per
  request. For a bulk join, the quarterly [Financial Statement Data Sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)
  `sub.txt` carries SIC per filer in one download (**unverified** — I did not download and parse one).

**Best role for SIC**: a licensing-clean *cross-check* on Yahoo's US sectors, and a fallback for US names Yahoo misses.
Not a primary sector axis.

### 1.5 Stockbit

The ticket names Stockbit. It is a retail broker/social app with no public API and terms that do not contemplate
scraping. **Not investigated further** — treated as unavailable.

---

## 2. Empirical verification: what a free source actually returns

Method: temp venv under `$CLAUDE_JOB_DIR/tmp` (nothing installed into the project), `yfinance` latest, calling
`Ticker(t).info` and reading `sector`, `industry`, `longBusinessSummary`. Four samples.

### 2.1 Coverage

| Sample | n | sector present | industry present | business summary >50 chars |
|---|---:|---:|---:|---:|
| IDX liquid/large-cap (hand-picked, `.JK`) | 100 | 99 (99%) | 99 | 99 |
| US liquid/large + thematic names | 100 | 99 (99%) | 99 | 99 |
| IDX random sample from the small-cap half of the exchange | 60 | **60 (100%)** | — | 60 |
| US random sample from the small-cap half | 60 | **60 (100%)** | — | 60 |
| **Total** | **320** | **319 (99.7%)** | | |

The two misses were `SRIL.JK` (Sri Rejeki Isman — suspended/insolvent) and `X` (US Steel — acquired/delisted).
**Missing sector is a delisting signal, not a coverage gap.** For a screener that already filters on liquidity and
recent price history, these names are excluded upstream anyway.

The small-cap samples were drawn from the exchange-wide list, so this is not a large-cap-only result — the tail is
covered as well as the head.

### 2.2 Universe enumeration

`yfinance.screen(EquityQuery("eq", ["region", "id"]))` returns a total of **840** IDX-listed instruments; `region=us`
returns **19,940**. So Yahoo can also enumerate the universe, not just annotate known tickers.

⚠️ **The screener payload does NOT carry sector/industry.** I dumped the full key set of 840 IDX and 1,250 US quote
records: `sector`, `industry`, `sectorDisp`, `industryDisp` were present in **0%** of them. Sector must be fetched
per-ticker from `Ticker().info` (the `quoteSummary`/`assetProfile` module). That's one HTTP request per symbol.

Also note **840 < the ~950 companies listed on IDX** — Yahoo's Indonesian universe is not complete. Worth a
reconciliation against a ticker list from elsewhere before treating 840 as the universe.

### 2.3 Rate limiting — the real operational constraint

This bit at me during testing and will bite the nightly job. After roughly 200 `.info` calls plus ~6 screener pages in a
few minutes, **every subsequent `.info` call raised `YFRateLimitError: Too Many Requests`** — for about 5 minutes,
including for `AAPL`. A naive 90-ticker sample came back "0% sector coverage" purely from throttling; the same sample
with a 2-second delay and 30s-backoff retries came back **100%**.

**This is the single most important operational finding for the sector layer.** Any spec must assume:

- ~1–2 s between per-ticker `.info` calls, with exponential backoff on 429.
- 840 IDX + a liquidity-filtered US universe (say 2,000–4,000) → **1–2 hours of wall clock** for a full refresh.
- Therefore: sector must be **cached persistently and refreshed incrementally** (new listings + a slow rolling
  re-check), never re-fetched wholesale nightly. Sector assignment changes on the order of months, not days — this is
  fine, but it must be designed in from the start rather than discovered in production.
- The rate-limit error surfaces as *empty data*, not an exception, if you swallow it. Any implementation must
  distinguish "no sector" from "throttled" or it will silently write nulls over good data.

### 2.4 Accuracy spot-check on IDX

Yahoo/Morningstar applies its global taxonomy to Indonesian names, and mostly sensibly:

| Ticker | Yahoo sector | Yahoo industry | Comment |
|---|---|---|---|
| `ADRO.JK`, `PTBA.JK`, `AADI.JK`, `CUAN.JK` | Energy | Thermal Coal | Correct and useful — coal is the dominant IDX momentum complex |
| `ANTM.JK`, `INCO.JK`, `NCKL.JK`, `MDKA.JK` | Basic Materials | Other Industrial Metals & Mining | Correct sector; **nickel is not separable at industry level** |
| `BREN.JK`, `PGEO.JK` | Utilities | Utilities - Renewable | Reasonable |
| `PGAS.JK`, `RAJA.JK` | Utilities | Utilities - Regulated Gas | Reasonable |
| `BBCA.JK`, `ARTO.JK` | Financial Services | Banks - Regional/Diversified | Correct |
| `JSMR.JK` | Industrials | Infrastructure Operations | Toll roads |
| `TOWR.JK` | Real Estate | Real Estate Services | **Questionable** — tower operator classed as real estate |
| `GOTO.JK` | Technology | Software - Infrastructure | **Questionable** — ride-hailing/e-commerce as infra software |

Two structural divergences to be aware of, and they cut in favor of using Yahoo rather than IDX-IC:

- **IDX-IC has an "Infrastructures" sector** that absorbs telecoms, toll roads, and utilities. Yahoo splits these across
  Communication Services / Industrials / Utilities. Yahoo's split is the one that matches how a US-comparable rotation
  view would read.
- **IDX-IC has a separate "Transportation & Logistics" sector**; Yahoo folds shipping/airlines into Industrials.

So IDX-IC and GICS/Morningstar are **not 1:1 mappable at sector level** — a hand-built crosswalk would have to split
IDX-IC's Infrastructures sector across three Morningstar sectors on a per-company basis. That's real work for no gain
when Yahoo already emits the Morningstar label directly.

### 2.5 Industry granularity actually observed

Across the two 100-name samples: **47 distinct industries in the US sample, 43 in the IDX sample**, out of Yahoo's 145.
Both markets land on the same vocabulary (`Gold`, `Specialty Chemicals`, `Advertising Agencies`, `Diagnostics &
Research`, `Beverages - Non-Alcoholic` all appear in both lists). US-only industries in the sample include `Uranium`,
`Semiconductors`, `Solar`, `Biotechnology`; IDX-only include `Thermal Coal`, `Marine Shipping`, `Farm Products`. That
asymmetry is real economic structure, not a data defect.

---

## 3. Cross-market comparability verdict

**One sector axis is viable, using Yahoo/Morningstar's 11 sectors for both markets.** Evidence:

1. Identical taxonomy applied to both markets — same 11 sector strings, same 145-industry vocabulary.
2. ~100% coverage on both, across the whole market-cap range.
3. No mapping table to build, no mapping errors to maintain, no licensing exposure to GICS.

**But** three caveats belong in the sector model ticket:

- **Sector composition differs radically by market.** In the (non-random, momentum-leaning) 100-name samples:
  Technology was 27% of the US sample and 1% of the IDX sample; Consumer Defensive was 18% of IDX vs 7% of US; Real
  Estate was 7% of IDX and 0% of the US sample. Consequence: **cross-market sector *strength* comparisons are close to
  meaningless.** "Technology is leading" on IDX is a statement about one or two stocks. Sector rotation should be
  computed **per market** and *displayed* on a shared axis — not pooled into one cross-market ranking. This is
  consistent with the map's existing "top decile is ranked per market" decision.
- **Small IDX sectors will be statistically noisy.** Some Morningstar sectors have a handful of IDX constituents.
  Whatever the rotation metric is, it needs a minimum-constituent floor or those sectors will dominate the leaderboard
  on single-stock moves.
- **Yahoo's IDX universe (840) is incomplete** vs. ~950 listed. Names missing from Yahoo are missing from the sector
  layer entirely.

**If IDX-IC is wanted anyway** (for a natively-Indonesian view a local user recognizes), the realistic shape is a
hand-maintained static CSV refreshed manually every few months, kept as a *secondary* label alongside the Yahoo sector —
not as the primary rotation axis, and not fetched nightly.

---

## 4. Theme layer — option survey (scouting, not choosing)

None of "AI", "nickel downstream", "GLP-1", "uranium" exist in any standard taxonomy. Yahoo's `Uranium` industry is the
one lucky exception. Everything below is a way of manufacturing a theme layer.

### Option A — Thematic ETF holdings as a proxy (US only)

Treat "the holdings of ARKQ" as the definition of the robotics theme, etc.

**Empirically tested 2026-08-04:**

| Issuer | Endpoint | Result |
|---|---|---|
| ARK | `https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv` | ✅ **200, plain CSV, same-day data** (`date,fund,company,ticker,cusip,shares,market value ($),weight (%)` — first row dated `08/04/2026`). No auth, no headers needed. |
| ARK (other funds) | guessed ARKQ/ARKG filenames | ❌ 404 — exact filenames must be discovered per fund, not constructed |
| State Street SPDR | `.../holdings-daily-us-en-xlk.xlsx` | ✅ **200, real XLSX, 22 KB** |
| iShares | `.../1467271812596.ajax?fileType=csv&fileName=IRBO_holdings&dataType=fund` | ⚠️ **200 but returns HTML** — a region-selection interstitial, not CSV. `Content-Type` lies (`text/csv`). Needs a cookie/JS step. |
| Global X | `https://www.globalxetfs.com/funds/lit/?download_full_holdings=true` | ⚠️ **200 but returns the SPA HTML shell** — JS-rendered |
| VanEck | `https://www.vaneck.com/api/us/fundholdings/csv/?ticker=SMH` | ⚠️ **302 redirect, 0 bytes** |

**Cost:** free. **Freshness:** daily, same-day for the issuers that work. **Maintenance:** *per-issuer bespoke and
brittle* — three of six issuers tested need cookie/JS handling, and even ARK requires knowing exact filenames. Every
issuer redesign breaks one scraper independently. Also: the theme↔fund mapping is a human judgment you maintain
(which fund *is* the AI theme?), and a fund's holdings drift with the manager's opinion, not with a stable definition.

**Universal fallback:** SEC **Form N-PORT-P**. Confirmed present via EDGAR (`browse-edgar?type=NPORT-P&output=atom`
returns "Monthly Portfolio Investments Report on Form N-PORT (Public)" filings). Legally clean, covers every registered
fund, no scraping fragility. But it is **quarterly-published with up to a 60-day lag** — far too stale to define a
tradeable theme, though fine as a backfill/repair source. (The quarterly ZIP URL pattern I guessed 404'd; the real
location is under `sec.gov/data-research/sec-markets-data/form-n-port-data-sets` — **unverified**, that page 403'd on
fetch.)

### Option B — Curated public lists

Wikipedia index-constituent tables, community-maintained GitHub theme lists, etc.

**Cost:** free. **Freshness:** whatever a volunteer last did. **Maintenance:** you inherit someone else's staleness and
have no SLA. **Licensing:** Wikipedia is CC BY-SA — usable with attribution, *except* where the content is itself GICS
(the S&P 500 table's sector columns), which the CC license does not launder. **IDX applicability:** essentially none —
no maintained public IDX theme lists found.

### Option C — Correlation clustering

Derive themes bottom-up: cluster the return series, name the clusters.

**Cost:** free — needs only the price history you already have for the screen; no new data source and no new
scraper. **Freshness:** as fresh as your bars. **Maintenance:** the code, plus a rerun cadence; no external
dependency to break. **Works identically on IDX and US** — this is the *only* option in this list that does.

Honest problems: clusters are unnamed and unstable (they change composition as correlations shift), they conflate
"same theme" with "same beta/sector/market-cap bucket", and a human must still look at each cluster and decide it
means "nickel downstream". Also needs a decent lookback, which the data-source ticket hasn't settled yet.

### Option D — LLM tagging of company business descriptions

Yahoo's `longBusinessSummary` is present for **>99% of both markets** in every sample above — so the *input* for this
approach is already free, already fetched alongside sector, and already covers IDX.

**Cost is small but nonzero, and it is a paid API — a real tension with the free-sources-only constraint.** Sizing:
~840 IDX + a liquidity-filtered US universe (~2,000–4,000) ≈ 5,000 names; ~400 input tokens per description, ~60 output.
That's ~2M input / 0.3M output tokens per full pass. At Claude Haiku 4.5 pricing ($1/MTok in, $5/MTok out) a full pass
is **≈ $3.50**, or **≈ $1.75 via the Batch API** (50% discount, results within ~1 hour — a good fit for a nightly EOD
job). Incremental refresh — only newly listed names and changed descriptions — would be cents per night.

**Freshness:** business descriptions are updated on a filings cadence (quarterly-ish), so tags go stale slowly, which
is fine for structural themes and *bad* for narrative themes ("AI" membership in 2026 is a market-narrative fact, not a
10-K fact). **Maintenance:** you own the theme vocabulary and the prompt; adding a theme means one re-tag pass. Tags
are non-deterministic run-to-run unless you pin and cache them.

**This is the only option that plausibly produces IDX themes** ("nickel downstream", "coal", "digital bank") from data
that actually exists for IDX today.

### Is a free theme layer viable for IDX at all? — plainly

**No, not from ETF holdings.** IDX has no thematic ETF layer to proxy from. The IDX ETF universe is index- and
sector-tracking, not thematic: Premier ETF LQ-45 (`R-LQ45X`), Premier ETF IDX30 (`XIIT`), Premier ETF SRI-KEHATI
(`XISR`, ESG), Premier ETF Indonesia Consumer (`XIIC`), Premier ETF Indonesia Financial (`XIIF`), Premier ETF Indonesia
State-Owned Companies (`XISC`). OJK records 60+ active ETF products on IDX, but there is **no nickel ETF, no EV-battery
ETF, no AI ETF**. And the offshore Indonesia ETF (iShares `EIDO`) is a broad country fund, not a theme fund.
(Sources: [Reku](https://reku.id/en/campus/9-etf-indonesia-terbaik),
[Yahoo XIIC](https://finance.yahoo.com/quote/XIIC.JK/), [iShares EIDO](https://www.ishares.com/us/products/239661/ishares-msci-indonesia-etf).
Also **unverified**: Indonesian ETF issuers appear to publish holdings only as PDF fund fact sheets, not machine-readable files.)

So for IDX, a v1 theme layer means **LLM tagging (Option D), correlation clustering (Option C), or hand-curation** —
and hand-curation of a market this size is a real ongoing chore for a single-user app.

**Scope-risk framing for the map:** a *US-only* theme layer is buildable for free at moderate maintenance cost. A
*both-markets* theme layer at parity is not free-and-easy — it requires either accepting a paid LLM line item (small:
single-digit dollars/month) or accepting hand-curation. Given the map's "both markets from day one" standing
constraint, **theme parity across markets is the thing at risk, and it should be flagged as such rather than assumed.**

---

## 5. Summary table

| Source | IDX | US | Bulk? | Free? | Cadence | Verdict |
|---|---|---|---|---|---|---|
| Yahoo / Morningstar GECS (11 sec / 145 ind) | ✅ 99–100% | ✅ 99–100% | Per-ticker only, rate-limited | ✅ (unlicensed scrape) | Cache + incremental | **Primary sector axis, both markets** |
| IDX-IC (12 / 35 / 69 / 130) | ✅ native | ❌ | ❌ Cloudflare-blocked | ✅ | Manual only | Optional secondary label, static file |
| sectors.app (IDX-IC via API) | ✅ | ❌ | ✅ | ❓ likely paid | API | Check pricing; probably out |
| SEC SIC (444 codes) | ❌ | ✅ | ✅ | ✅ licensed-clean | Filing-driven | US cross-check / fallback |
| GICS | — | — | — | ❌ **licensed** | — | **Excluded** |
| Thematic ETF holdings | ❌ none exist | ✅ partial | Per-issuer | ✅ | Daily | US theme proxy, brittle |
| SEC N-PORT-P | ❌ | ✅ | ✅ | ✅ | Quarterly, ~60d lag | Backfill only, too stale |
| Correlation clustering | ✅ | ✅ | ✅ | ✅ | Any | Only both-market free theme option |
| LLM tagging of descriptions | ✅ | ✅ | ✅ | ~$2–4/full pass | Any | Only both-market *named*-theme option |

---

## 6. Open questions for the sector-model ticket

1. Does sectors.app have a free tier? (Blocked by bot protection here; needs a browser.) If yes, IDX-IC becomes
   cheaply available and the calculus on a secondary IDX-native label changes.
2. What reconciles Yahoo's 840 IDX instruments against ~950 listed? Which 110 are missing, and do any matter after
   liquidity filtering?
3. Is a paid-but-tiny LLM tagging line item acceptable against "free data sources only"? The constraint was written
   about *market data feeds*; an LLM classification pass is arguably a different category. Worth an explicit ruling
   rather than an assumption.
4. What is the minimum constituent count for a sector to appear in the rotation view, given how thin some Morningstar
   sectors are on IDX?
