# Free EOD data sources for US (and IDX)

Research note resolving `issues/02-us-free-data-sources.md`.
Date of investigation: 2026-08-04. All rate limits and prices verified against vendor pages on that date.

Empirical tests were run in a throwaway venv (`yfinance 1.5.2`, Python 3.12.6) outside the project.
Nothing was installed into the repo.

---

## TL;DR

**Recommend: yfinance (Yahoo Finance) as the single primary source for both US and IDX.**
It is the only free source that survives a ~6,000-symbol nightly pull, and — the material finding —
**it serves IDX and US from one client, one schema, one code path** (`BBCA.JK` alongside `AAPL`),
including sector/industry for both. That collapses the two-market design into one ingester.

Measured: **full 5,711-symbol US universe, 2 years of daily bars, in 8.5 minutes with zero HTTP 429s**
at a self-imposed 12 req/s cap.

**Fallback: Polygon — now Massive — free "Basic" tier**, whose whole-market grouped-daily endpoint
returns every US ticker for a date in *one* request. It is sanctioned, has a real ToS, and covers
delisted names — but it is **US-only** (so it does not solve IDX) and capped at **2 years** of history.

Three honest problems with the recommendation, detailed below: **Yahoo's ToS**; **survivorship bias**
(delisted US names are largely purged from Yahoo); and a **partial live bar** for any in-progress
session, which will silently corrupt volume and range math unless explicitly guarded against.

Also note two traps that would bite a naive implementation: an **unthrottled** full pull silently loses
~47% of the universe while reporting the losses as "possibly delisted", and **Stooq is now blocked** by
an anti-bot wall that returns HTTP 200 with HTML.

---

## Comparison table

| Source | Free-tier limit | Nightly 6k feasible? | History | Raw + adjusted? | Delisted | Sector | IDX too? | Sanctioned |
|---|---|---|---|---|---|---|---|---|
| **yfinance / Yahoo** | Undocumented; empirically ~12 req/s sustained OK, ~75 req/s fails | **Yes — 8.5 min measured** | To 1980 for AAPL; 22y for BBCA.JK | **Yes** — OHLC raw + `Adj Close` + `Dividends` + `Stock Splits` in one call | **Mostly no** | Yes, via `.info` | **Yes** (`.JK`) | **No** — unofficial |
| **Polygon / Massive (Basic)** | 5 API calls/min | **Yes** — 1 call/day covers whole market | **2 years** | `adjusted=true|false` param | **Yes** (`active=false`, `delisted_utc`) | Not in tickers endpoint | **No** — US only | Yes |
| **Nasdaq Trader symbol files** | None (public FTP/HTTPS) | N/A — reference only | N/A | N/A | No (current listings only) | No | No | Yes |
| **SEC `company_tickers*.json`** | Fair-access policy (UA required) | N/A — reference only | N/A | N/A | Registrants only | SIC via submissions API | No | Yes |
| **Stooq** | — | **No — blocked** | — | — | — | — | — | **Dead end** |
| **Alpha Vantage** | **25 requests/day** | No | — | — | — | — | — | Yes |
| **Tiingo (Starter)** | **500 unique symbols/month**, 50 req/hr, 1000/day | No | — | — | — | — | — | Yes |
| **FMP (Basic)** | **250 requests/day**, US only | No | 5y | — | — | — | No | Yes |
| **EODHD (Free)** | **20 calls/day**, 1 year range | No | 1y | — | — | — | — | Yes |

---

## 1. The metered APIs are all dead on arrival

Every keyed free tier fails on arithmetic alone against a ~6,000-symbol nightly pull. Numbers taken
verbatim from vendor pricing pages:

- **Alpha Vantage — 25 API requests per day.** "the majority of our API endpoints can be accessed for
  free" with a limit of **"25 API requests per day"**. Source: <https://www.alphavantage.co/premium/>.
  At 25/day, one pass over 6,000 symbols takes 240 days. Not viable at any batching.
- **Tiingo Starter (free) — 500 unique symbols per month.** The pricing table lists "Unique Symbols
  per Month: 500", "Max Requests Per Hour: 50", "Max Requests Per Day: 1000", "Max Bandwidth Per
  Month: 1 GB". Source: <https://www.tiingo.com/about/pricing>. The *symbol* cap is the binding one —
  6,000 symbols is 12x the monthly allowance. Also marked **"Internal Use Only"**, footnoted as "you
  may only use the data for your own personal use and you may not display or share the data with
  another person or organization."
- **EODHD Free — 20 API calls/day, "Past year" of data, "Personal use".** Source:
  <https://eodhd.com/pricing>. A 500-call welcome bonus does not change the steady state.
- **FMP Basic — 250 requests/day, US exchanges only.** FMP's own site states the free plan allows
  "up to 250 market data API requests per day" and covers "all stocks within the US exchanges", with
  global exchanges requiring an upgrade. Sources: <https://site.financialmodelingprep.com/pricing-plans>,
  <https://site.financialmodelingprep.com/faqs>.
  *Caveat on citation:* both FMP pages return **HTTP 403 to programmatic fetches**; these figures come
  from FMP-authored page content surfaced via search rather than a direct read. **Treat as
  first-party-but-not-directly-verified.** An unauthenticated probe of
  `financialmodelingprep.com/api/v3/historical-price-full/AAPL?apikey=demo` returns
  `{"Error Message": "Invalid API KEY..."}` — there is no usable demo key.

None of these can be rescued by clever batching, because the limits are on *symbols* or *calls*, not
bandwidth.

## 2. Stooq is a dead end (this is a change from its historical reputation)

Stooq's CSV endpoint is frequently recommended as the no-key fallback, and `pandas-datareader` ships a
Stooq reader. **It no longer works unattended.**

`https://stooq.com/q/d/l/?s=aapl.us&i=d` returns **HTTP 200 with an HTML anti-bot interstitial**, not
CSV — a JavaScript proof-of-work challenge:

> `<noscript>This site requires JavaScript to verify your browser. Please enable JavaScript and reload.</noscript>`
> followed by a script that brute-forces a SHA-256 hash with a 4-hex-zero prefix and POSTs the nonce to `/__verify`.

Verified 2026-08-04 for both `aapl.us` and `bbca.jk`. Because the failure is a 200 with an HTML body,
naive clients will silently parse garbage rather than raise. Additionally, the installed
`pandas-datareader` exposes no working Stooq path (`data_source='stooq' is not implemented`;
`pandas_datareader.stooq` does not import). **Rule Stooq out.**

## 3. Universe enumeration — solved, free, and reliable

The Nasdaq Trader symbol directory is the right answer. Both transports work:

- FTP: `ftp://ftp.nasdaqtrader.com/SymbolDirectory/nasdaqlisted.txt` and `.../otherlisted.txt`
- **HTTPS (preferred, works from restricted hosts):**
  `https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt` — verified HTTP 200, 345,641 bytes,
  byte-identical line count to the FTP copy.

Pipe-delimited, with the fields the ticket asks for. `nasdaqlisted.txt` header:
`Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares`.
`otherlisted.txt` header: `ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol`.

**Measured composition (2026-08-04), after dropping `Test Issue == Y` (8 Nasdaq + 25 other):**

| Slice | Count |
|---|---|
| nasdaqlisted rows | 5,568 |
| otherlisted rows | 7,524 |
| Nasdaq, ETF=N | 4,307 |
| NYSE (`N`), ETF=N | 2,850 |
| NYSE American/AMEX (`A`), ETF=N | 308 |
| NYSE Arca (`P`), ETF=N | 17 |
| Cboe BZX (`Z`), ETF=N | 4 |
| **Nasdaq + NYSE + AMEX, ETF=N** | **7,465** |
| **After stripping warrants/rights/units/preferreds/notes and `$`/`.` symbols** | **5,711** |

The **`ETF` flag separates funds cleanly** — 1,253 on Nasdaq, 4,320 on the other-listed file — which is
exactly what the ticket needs (stocks universe; ETFs retained separately as sector proxies). Arca and
BZX are almost entirely ETFs (2,693 and 1,573 of them), so excluding those venues costs ~21 real stocks.

5,711 matches the ticket's "~6,000 symbols" premise well. Note the residual junk: my name-based filter
left rights like `AACBR` (the security name says "Rights", my regex tested `\bRight\b`) — a real
implementation should filter on the security-name suffix more carefully, and cross-check `quoteType`
from Yahoo.

**SEC reference data** also works and is a good CIK cross-walk, but requires a descriptive `User-Agent`
(WebFetch and bare curl get **HTTP 403**; curl with a UA gets 200):

- `https://www.sec.gov/files/company_tickers.json` — **10,432 entries**, fields `cik_str, ticker, title`.
- `https://www.sec.gov/files/company_tickers_exchange.json` — **10,411 rows**, fields `cik, name, ticker, exchange`.
  Exchange distribution: Nasdaq 4,342, NYSE 3,309, **OTC 2,542**, null 191, CBOE 27.

SEC is *not* a substitute for the Nasdaq files for this purpose: it includes 2,542 OTC names we don't
want, has no ETF flag, and no price data. Use it only if CIK linkage or SIC codes are later needed.

## 4. yfinance — measured behaviour, including the rate-limit cliff

This is where the empirical work matters most, because Yahoo publishes **no rate limits at all**. What
follows is observed, not documented.

### Throughput and the cliff

`yf.download` issues **one HTTP request per symbol** (measured by patching `curl_cffi.Session.request`;
1,095 requests for 1,000 symbols — the ~95 extra are cookie/crumb handshakes).

| Test | Rate cap | Result |
|---|---|---|
| 10 syms, `period=max` | none | 0.98 s |
| 200 syms, 2y | none | 2.9 s, 200/200 |
| 1,000 syms, 2y | none | 13.3 s (75.3 sym/s), 1,000/1,000, **0 × 429** |
| **5,711 syms (full), 2y** | **none** | **75.6 s but only 3,020/5,711 (52.9%) — 5,374 × HTTP 429** |
| 300 syms, 2y | 5 req/s | 62.7 s, 299/300, 1 × 429 |
| 400 syms, 2y | 10 req/s | 43.5 s, 400/400, 0 × 429 |
| 400 syms, 2y | 20 req/s | 22.9 s, 400/400, 0 × 429 |
| **5,711 syms (full), 2y** | **12 req/s** | **511.9 s (8.5 min), 5,707/5,711 (99.93%), 0 × 429** |

**The headline risk and its mitigation.** Unthrottled, the full pull *appears* fast (75 s) but is a
silent disaster: **47% of symbols came back empty**, and yfinance reports the failures as
`"$TICKER: possibly delisted; no price data found"` — a message that looks like a data condition, not a
throttling condition. Anyone building this without a rate cap will ship a screener that quietly drops
half the universe and blames delisting. **A client-side rate limiter is mandatory, not an optimisation.**

At **12 req/s the full universe completes in 8.5 minutes with zero rejections** — comfortably inside a
nightly window. Bursts to ~20 req/s were fine over 400 requests but were not validated at scale;
12 req/s is the rate I would actually ship.

Once rate-limited, Yahoo stays hostile for minutes: subsequent calls raise
`yfinance.exceptions.YFRateLimitError: Too Many Requests` from the cookie/crumb handshake, and a later
500-symbol run returned nothing until a multi-minute cooldown. Build in backoff and a "did we get
≥95% of the universe?" assertion before publishing a night's screen.

**Caveat — these numbers are from a residential IP.** Yahoo is materially more aggressive toward
datacenter ranges, which is exactly where a free hosting tier lives. **The 12 req/s figure should be
re-validated from the actual host before it is treated as settled.** Treat it as an upper bound.

### Fields, history, adjustment

One `yf.download(..., auto_adjust=False, actions=True)` call returns all eight columns:

`Open, High, Low, Close, Adj Close, Volume, Dividends, Stock Splits`

This **satisfies the ticket's raw-and-adjusted requirement in a single request** — raw OHLC for ADR and
gap math, `Adj Close` for return math, plus the split/dividend events to do your own adjustment.

History is deep: `AAPL` returns **11,501 rows from 1980-12-12** to 2026-08-03 on `period="max"`.

### Sector / industry

Available per symbol via `Ticker(s).info` (~0.15 s each), on **Yahoo's own taxonomy** (roughly 11
sectors / ~145 industries — the specific counts are **not verified here**):

| Symbol | sector | industry |
|---|---|---|
| AAPL | `Technology` | `Consumer Electronics` |
| XOM | `Energy` | `Oil & Gas Integrated` |
| BBCA.JK | `Financial Services` | `Banks - Regional` |
| TLKM.JK | `Communication Services` | `Telecom Services` |

Two practical notes: `.info` is a **separate request per symbol** (so a full-universe refresh roughly
doubles the request budget — cache it and refresh weekly, not nightly), and it also yields
`quoteType` (`EQUITY`) and `exchange` (`NMS`/`NYQ`/`JKT`), giving a second, independent ETF filter to
cross-check the Nasdaq `ETF` flag against.

### Survivorship — the real weakness

Delisted and acquired US names are **largely purged from Yahoo**. Measured:

| Symbol | Fate | `period="max"` result |
|---|---|---|
| TWTR | acquired 2022 | **0 rows** |
| ATVI | acquired 2023 | **0 rows** |
| VMW | acquired 2023 | **0 rows** |
| SIVBQ | failed 2023 | **0 rows** |
| FRCB | failed 2023 | 3,934 rows, 2010-12-09..2026-08-03 |

Only `FRCB` survives, and probably only because the ticker still quotes OTC. **Any backtest built on a
yfinance history will be survivorship-biased upward**, and this bears directly on the map's open
"Validation / backtest" item. If historical replay is going to be used to calibrate star thresholds,
that calibration will be optimistic. Mitigations, in order of cost: (a) snapshot the Nasdaq listing
file nightly from day one, so that *going forward* you accumulate your own point-in-time universe —
cheap, and worth starting immediately even before backtesting is designed; (b) use Massive's
`active=false` ticker history for the last 2 years; (c) accept the bias and state it.

### Freshness

**Yahoo emits a partial, live bar for the in-progress session. Confirmed empirically, and this is a
correctness trap for the whole screen.**

Measured at **2026-08-04 13:44 UTC = 09:44 ET — 14 minutes after the US open**:

| Symbol | Last bar date | Close | Volume |
|---|---|---|---|
| AAPL | **2026-08-04** (today, market open) | 303.57 | **8,538,070** |
| MSFT | **2026-08-04** (today, market open) | 485.65 | **6,686,919** |
| BBCA.JK | 2026-08-04 (IDX closed) | 6,500.00 | 138,953,100 |

AAPL's "2026-08-04" bar is **14 minutes of trading**, not a day. Its close is the last trade, its high
and low cover minutes, and its volume is a small fraction of a session. An earlier run the same day had
shown AAPL's last bar as 2026-08-03 — the bar *appeared* the moment the session opened.

Consequences for a nightly EOD job:

- Any ADR, gap, range-tightness or volume calculation that consumes the final bar will be **silently
  wrong** if the job runs while a session is open anywhere. Volume-based liquidity floors would reject
  nearly the whole universe.
- The two markets have **disjoint sessions**, so there is no single safe wall-clock time: 09:44 ET is
  safe for IDX (closed) and unsafe for US (open).
- **Mitigation:** do not trust the run time. Per market, drop any bar whose date equals the current
  local trading date unless that market's session is confirmed closed, and prefer scheduling each
  market's ingest after its own close. A cheap sanity assertion — final-bar volume within a plausible
  band of the trailing median — would catch this class of bug directly.

### Storage

At 5,711 symbols × ~502 bars/year:

| Window | Rows | Uncompressed (float32 OHLCV+adj) |
|---|---|---|
| 2 years | ~2.87 M | ~86 MB |
| 10 years | ~14.3 M | ~430 MB |

Parquet typically compresses this 3–5x. This comfortably fits free-tier object storage; it does **not**
comfortably fit the row limits of some free hosted Postgres tiers at 10 years, which is a consideration
for the architecture ticket. The in-memory pandas frame for the 2-year full pull measured **161 MB**,
which *is* a real constraint on a 512 MB free dyno — stream and write per-chunk rather than
materialising the whole universe.

## 5. Polygon → Massive — the strongest sanctioned fallback

**Polygon.io rebranded to Massive.com effective 2025-10-30 16:00 ET.** Existing API keys, accounts and
the `api.polygon.io` base URL continue to work, with `api.massive.com` running in parallel.
Sources: <https://massive.com/blog/polygon-is-now-massive>, corroborated by
<https://natlawreview.com/press-releases/polygonio-now-massive>. All `polygon.io` doc and pricing URLs
now 301 to `massive.com`. **Anything in the codebase or in older research citing polygon.io pricing
should be re-checked against massive.com.**

Free "Basic" Stocks tier, verbatim from <https://massive.com/pricing>:

- **"5 API Calls / Minute"**
- **"2 Years Historical Data"**
- **"End of Day Data"**

The reason this survives 5 calls/min where Alpha Vantage does not is the **grouped daily / daily market
summary** endpoint, which returns "daily OHLC (open, high, low, close), volume, and volume-weighted
average price (VWAP) data for **all U.S. stocks** on a specified trading date" in a single call, and is
**"Included in all Stocks plans"** including Basic.
Source: <https://massive.com/docs/rest/stocks/aggregates/daily-market-summary>.

Consequences:

- **Nightly cost: 1 request.** Not 6,000. This is by far the most robust nightly story of any source.
- **Backfill cost:** 2 years ≈ 500 trading days ≈ 500 calls ≈ **100 minutes** at 5/min. One-time.
- Split adjustment is a parameter: `adjusted` defaults to true, `false` gives unadjusted — so raw and
  adjusted are both obtainable, though at the cost of a second pass.
- **Delisted tickers are available**: the tickers endpoint supports `active=false` and returns
  `delisted_utc`. Source: <https://massive.com/docs/rest/stocks/tickers/all-tickers>. Better
  survivorship than Yahoo, within the 2-year window.

Why it is the fallback and not the primary:

1. **US-only.** It does nothing for IDX, so choosing it means building and maintaining a second,
   entirely different IDX ingester. That is the single biggest strike against it.
2. **2 years of history** on Basic. Adequate for the method's 1/3/6-month momentum lookbacks and a
   200-day MA, thin for any meaningful backtest.
3. **No sector/industry** in the tickers endpoint (SIC is not documented as returned), so sector
   leadership and rotation would still need a second source.

**Not empirically verified.** I did not create a Massive account, so the 5/min limit, the grouped-daily
payload shape, and Basic-tier access to it are **documented-only**. Given it is the designated fallback,
a 10-minute spike with a real free key would be worth doing before the architecture ticket closes.

## 6. Can one source serve both IDX and US? — Yes, and only one can

This was the ticket's flagged question, and it has a clean answer.

**yfinance covers IDX via the `.JK` suffix with the same client, same call, same schema, same
adjustment fields, and same sector taxonomy as US.** Measured 2026-08-04:

- A single `yf.download` over `["BBCA.JK","BBRI.JK","TLKM.JK","ASII.JK","GOTO.JK","ANTM.JK","MDKA.JK","BREN.JK","UNVR.JK","ICBP.JK"]`
  returned **479 rows each** over 2 years, 2024-08-05..2026-08-04, with sane closes and volumes
  (e.g. BBCA close 6,500, volume 138,953,100).
- Deep history: `BBCA.JK` `period="max"` gives **5,463 rows from 2004-06-08**, with **2 splits and 46
  dividends** recorded — corporate actions are present, not just prices. `GOTO.JK` gives 1,032 rows
  from its 2022-04-11 IPO, correctly.
- Sector/industry resolve on the same Yahoo taxonomy (see table above), so **cross-market sector
  leadership and rotation are directly comparable** — no mapping layer between two vendors' taxonomies.
  This is a larger simplification than it first appears.

**No other candidate does this.** FMP free is explicitly US-only. Massive is US equities. Alpha Vantage,
Tiingo and EODHD are eliminated on volume regardless of coverage. Stooq nominally carries `.jk` symbols
but is blocked. So the choice is genuinely: **one source (Yahoo), or two ingesters.**

Open IDX gaps this note does *not* close, and which belong to the IDX ticket:

- **IDX universe enumeration is unsolved here.** The Nasdaq files obviously don't cover IDX, and Yahoo
  offers no listing endpoint. A separate source for the ~900 IDX tickers is still needed. **Unverified.**
- The map's suspected IDX data-quality issues (ARA/ARB limit days, suspensions, no-trade days) were
  **not** examined. Yahoo returning 479 identical row counts across ten liquid names is encouraging but
  says nothing about thin ones.

## 7. ToS and stability — the honest problems

**yfinance is not a sanctioned API.** Its README states it is "**not** affiliated, endorsed, or vetted
by Yahoo, Inc. It's an open-source tool that uses Yahoo's publicly available APIs", is "intended for
research and educational purposes", and — explicitly — "Remember - the Yahoo! finance API is intended
for **personal use only**." Source:
<https://raw.githubusercontent.com/ranaroussi/yfinance/main/README.md>.

Yahoo's own API terms (<https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html>)
prohibit, verbatim:

- **"Sell, lease, share, transfer, or sublicense the Yahoo APIs or access or access codes thereto or derive income from the use or provision of the Yahoo APIs"**
- **"Use the Yahoo APIs in a manner that exceeds reasonable request volume, constitutes excessive or abusive usage"**
- Yahoo reserves the right to impose rate limits **"at Yahoo's absolute and sole discretion"**.

Assessment against this project's actual shape — **single user, personal, non-commercial, not
redistributing, ~6k requests once nightly**:

- The **"derive income"** and sharing prohibitions are **not** implicated. This is a personal tool.
- The **"reasonable request volume"** clause is the live one and is deliberately vague. 6,000 requests
  once a night at 12 req/s is modest by any absolute measure, but it is unambiguously automated bulk
  access, and Yahoo is the sole judge. **There is no reading under which this is explicitly
  permitted** — the honest characterisation is "tolerated in practice, not authorised."
- The terms' **24-hour data-retention clause** applies to *Yahoo user data*, not market data. It is
  **not obviously applicable** to OHLCV bars, but I am flagging it because a strict reading would
  forbid the historical store this project depends on. **This is my interpretation, not a verified
  legal position.**

**Practical stability risk.** yfinance breaks when Yahoo changes its endpoints — the cookie/crumb
handshake visible in the stack traces above exists precisely because Yahoo added anti-automation
measures that the library had to work around. Historically this has meant periodic outages until a new
release lands. Plan for it: pin the version, keep the ingester behind an interface so the fallback can
be swapped in, and alert on the "≥95% of universe" assertion rather than discovering breakage in the
screen output.

Given the constraints are fixed at *free sources only* and *single user*, and the alternative is a
US-only vendor plus a separate IDX ingester, **yfinance is the right call — but it should be chosen
with the ToS ambiguity acknowledged in the spec, not silently.**

---

## Recommendation

1. **Primary: yfinance**, for both markets, with a **client-side cap of 12 req/s** and mandatory
   backoff. Full US universe in ~8.5 min; IDX adds negligible time.
2. **Universe: Nasdaq Trader `nasdaqlisted.txt` + `otherlisted.txt` over HTTPS**, filtering
   `Test Issue == N`, `ETF == N`, and name-suffix junk → ~5,700 symbols. **Snapshot these files nightly
   from day one** to build a point-in-time universe and blunt survivorship bias later.
3. **Sector/industry: cached `Ticker.info`**, refreshed weekly, not nightly — it is a second request
   per symbol.
4. **Fallback: Massive (ex-Polygon) Basic**, grouped-daily, 1 request/night, for US. Keep the ingester
   behind an interface so this is a swap, not a rewrite. Accept that IDX would need its own path.
5. **Reject outright:** Alpha Vantage, Tiingo, FMP, EODHD (volume limits), Stooq (anti-bot wall).

### Things a build session must not assume from this note

- The 12 req/s ceiling was measured **from a residential IP**. Re-validate from the deployment host.
- **Massive's free tier was not exercised with a real key** — documented-only.
- **IDX universe enumeration is unsolved.**
- IDX data-quality behaviour (ARA/ARB, suspensions, thin names) was not tested.
- Yahoo's 24-hour retention clause and its applicability to market data is my reading, not legal advice.

---

## Sources

Primary, fetched 2026-08-04:

- <https://www.alphavantage.co/premium/> — Alpha Vantage limits
- <https://www.tiingo.com/about/pricing> — Tiingo Starter limits
- <https://eodhd.com/pricing> — EODHD free plan
- <https://massive.com/pricing> — Massive (ex-Polygon) Basic tier
- <https://massive.com/docs/rest/stocks/aggregates/daily-market-summary> — grouped daily endpoint
- <https://massive.com/docs/rest/stocks/tickers/all-tickers> — tickers/delisted
- <https://massive.com/blog/polygon-is-now-massive> — rebrand
- <https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html> — Yahoo API ToS
- <https://raw.githubusercontent.com/ranaroussi/yfinance/main/README.md> — yfinance disclaimer
- <https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt>, `.../otherlisted.txt`
- <https://www.sec.gov/files/company_tickers.json>, <https://www.sec.gov/files/company_tickers_exchange.json>
- <https://stooq.com/q/d/l/?s=aapl.us&i=d> — anti-bot interstitial

Secondary / weaker citation, flagged in text:

- <https://site.financialmodelingprep.com/pricing-plans> and `/faqs` — FMP-authored but 403 to direct fetch
- <https://natlawreview.com/press-releases/polygonio-now-massive> — corroborates rebrand date
