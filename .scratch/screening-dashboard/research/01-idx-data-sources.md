# Free EOD data sources for the IDX equity universe

Research note for ticket `01-idx-free-data-sources.md`.

**As-of date: 2026-08-04.** Everything below was either read from the source that owns the claim, or
**measured directly** on this date by installing `yfinance 1.5.2` in a throwaway venv and pulling live
data. Measured results are tagged **[MEASURED]** with the number observed. Claims that could not be
confirmed against a primary source are tagged **[UNVERIFIED]**.

Nothing was installed into the project. The probe scripts live in the job scratch dir
(`$CLAUDE_JOB_DIR/tmp/probe*.py`) and are disposable.

---

## 0. TL;DR

1. **Build on Yahoo Finance `.JK` via `yfinance`. There is no serious competitor on a free tier.**
   Every other candidate is either paywalled (IDX official, Sectors), contractually closed
   (Stockbit, Investing.com), bot-walled (idx.co.id, Stooq — both measured), or dead
   (Dataset-Saham-IDX, last data commit 2025-02-23).
2. **The universe problem is solved, but only for *actively traded* names.** `yfinance`'s screener
   (`EquityQuery("eq", ["exchange","JKT"])`) enumerates the whole exchange in one call —
   **[MEASURED] 840 symbols in 0.8 s**. IDX itself reports **963 listed companies as of July 2026**,
   so the screener is missing ~120. **[MEASURED]** the missing ones are suspended/delisted names
   (WSKT, SRIL, ENVY, INAF, POLL, BIMA, TRAM, MYRX all absent). For a momentum screener that
   omission is nearly free; for a backtest it is **survivorship bias** and must be flagged.
3. **Volume is in shares, not lots — verified by arithmetic, not by trusting docs.** [MEASURED]
   Σ(close × volume) across all 834 priced names on 2026-08-04 = **Rp 12.07 trillion**, which is
   the right order of magnitude for an IDX session. A lots reading would give Rp 1,207 trillion.
   The Rp 1B/day liquidity floor can be computed directly as `close × volume`.
4. **The adjustment story is the real risk.** Yahoo's `Adj Close` covers **splits and dividends
   only** — stated by Yahoo, confirmed in yfinance's source. But **[MEASURED]** Yahoo *also* applies
   an **unlabelled** retroactive rescale for rights issues: BBRI's OHLC before 2021-09-08 is scaled
   by exactly **10/11**, with **no corresponding entry in either the `Stock Splits` or `Dividends`
   column**. Consequence: you cannot recover the raw exchange-traded price from yfinance, and you
   cannot audit which corporate actions were applied.
5. **History depth is fine for the method and trivial to store.** [MEASURED] Yahoo's IDX history
   effectively begins in 2000 (nothing earlier across all 840 names); small caps are **not**
   truncated — they carry full history from their actual IPO. 5 years × 840 names = **904,414 bars**,
   ≈ 50 MB uncompressed, far inside every free-tier store in ticket 04.
6. **The operational constraint is rate limiting, not volume.** [MEASURED] A threaded (8-way) bulk
   `yf.download` of all 840 symbols × 5y finished in **11.5 s**, but the *next* API call returned
   `YFRateLimitError`, and the limit persisted for minutes. Nightly jobs must pace and retry.

**Recommendation: Yahoo Finance via `yfinance`, with the screener as the universe source, plus a
manually-maintained supplement list for suspended names.**
**Fallback: a headless-browser scrape of idx.co.id** (the only free path to the official data, and the
only source of true unadjusted prices + IDX-IC sectors) — see §7.

---

## 1. Comparison table

| Source | Enumerates universe? | History depth | Adjustment | Volume units | ToS / access | Freshness | Sector field | Free? |
|---|---|---|---|---|---|---|---|---|
| **Yahoo Finance `.JK` (yfinance)** | **Yes** — screener returns 840 (vs 963 listed); misses suspended | **[MEASURED]** effectively 2000→now; small caps full from IPO | Splits + divs, **plus an unlabelled rights rescale**; no raw prices | **Shares** [MEASURED] | Unofficial endpoints; Yahoo ToS says personal use; **works unauthenticated** [MEASURED] | Bar for 2026-08-04 present at 19:49 WIB; feed marked `exchangeDataDelayedBy: 10` min | Yahoo's own GICS-like taxonomy, **not IDX-IC** | Yes |
| **IDX official (idx.co.id)** | Yes (authoritative) | Full | Raw/unadjusted + official corporate actions | Shares (`dalam satuan lembar`) | **Cloudflare 403 to every server-side request** [MEASURED]; data is a *licensed paid product* | Same-day | **IDX-IC** (authoritative) | Web scrape only; API is paid |
| **Sectors (sectors.app)** | Yes, "99% of IDX" | [UNVERIFIED] | [UNVERIFIED] | [UNVERIFIED] | Clean REST API, but **requires paid "Insider" plan** | Daily | Own sub-sector taxonomy | **No** |
| **Stockbit** | Yes | Deep | Adjusted | Shares | **ToS explicitly bans robots/spiders** | Same-day | Yes | Closed |
| **Investing.com** | Partial | Deep | Adjusted | Shares | `investpy` broke on API changes; heavy anti-bot | Same-day | Yes | Closed in practice |
| **Google Finance** | No | Sheets only | Adjusted | Shares | **No API since 2012**; Sheets-only, not for professional use | ≤20 min delayed | No | Not usable programmatically |
| **Stooq** | ? | ? | ? | ? | **[MEASURED] JS proof-of-work challenge on every CSV URL** — automated access blocked | — | No | Blocked |
| **Dataset-Saham-IDX (GitHub, CC BY-NC)** | Yes (`List Emiten/all.csv`) | 2019 → **2025-02-23** | **Raw, unadjusted** + `listedShares` | Shares (documented) | CC BY-NC 4.0 (non-commercial only) | **Dead — last data commit 2025-02-23** [MEASURED] | Yes (`Sectors/`) | Yes, but stale |
| **Alpha Vantage / Twelve Data / Finnhub free tiers** | No | — | — | — | Free keys exist; **IDX coverage [UNVERIFIED]**, and free quotas (25–800 calls/day) cannot cover 840 symbols nightly | — | — | Effectively no |

---

## 2. Yahoo Finance / yfinance — measured in detail

### 2.1 Universe enumeration

`yfinance ≥ 0.2.5x` exposes Yahoo's screener. This is the single most useful finding in the ticket:

```python
from yfinance import EquityQuery
import yfinance as yf
yf.screen(EquityQuery("eq", ["exchange", "JKT"]), offset=0, size=250,
          sortField="dayvolume", sortAsc=False)
```

**[MEASURED]** `total: 840`, paginated 250 at a time, **all 840 retrieved in 0.8 s total**.
Every result had `quoteType: EQUITY` — no warrants, rights, or ETFs polluting the list.
Each row already carries `marketCap`, `sharesOutstanding`, `regularMarketVolume`,
`averageDailyVolume3Month`, `fiftyTwoWeekHigh/Low`, `fiftyDayAverage`, `twoHundredDayAverage`,
`firstTradeDateMilliseconds`, and `prevName`/`nameChangeDate` — enough to seed the universe table
without a second call per symbol.

**The gap.** IDX reported **963 listed companies as of 10 July 2026**
([Databoks, citing IDX](https://databoks.katadata.co.id/en/market/statistics/6a24e09f528c8/listed-companies-on-the-idx-remained-relatively-stagnant-through-april-2026)),
and Wikipedia's IDX article records 956 as of December 2025
([Indonesia Stock Exchange](https://en.wikipedia.org/wiki/Indonesia_Stock_Exchange)). So ~120 names
are missing from the screener.

**[MEASURED]** I probed 13 tickers directly. The pattern is unambiguous — the screener returns names
that traded, and drops names under suspension:

| Ticker | In screener? | `history()` result |
|---|---|---|
| BBRI, BUKA, ARTO | yes | 119 bars/6mo, last **2026-08-04**, real volume |
| INAF, POLL, BIMA | **no** | 121 bars/6mo, last 2026-08-03, **volume = 0**, price flat |
| WSKT, SRIL, ENVY, TRAM, HKMU | **no** | **1 bar in 2 years**, dated 2026-07-17, volume = 0 |
| KPAS | **no** | 228 bars, stops **2025-07-23** |
| MYRX | **no** | `possibly delisted; no price data found` |

Two consequences:

- **Suspended names are reachable by symbol but not discoverable.** If you want them, you need a
  symbol list from elsewhere. Yahoo's own search endpoint is *not* that list — **[MEASURED]**
  `query2.finance.yahoo.com/v1/finance/search?q=INAF` returns a US mutual fund and no `.JK` result.
- **Delisted names disappear entirely.** Any historical replay built on the screener universe will
  have survivorship bias baked in. This directly constrains the "Validation / backtest" item still
  open on the map.

**Practical fix:** persist your own universe table. Union the nightly screener result with everything
you have ever seen, and mark symbols `active` / `stale` by whether they appeared tonight. That gives
you delisting dates for free after a few months of running, and costs nothing.

### 2.2 History depth

**[MEASURED]** `firstTradeDateMilliseconds` across all 840 symbols, by year:

```
2000: 43   2005: 33   2010: 16   2015: 15   2020: 44   2025: 26
2001: 61   2006: 10   2011: 24   2016: 12   2021: 48   2026:  7
2002: 64   2007: 25   2012: 17   2017: 29   2022: 55
2003: 20   2008: 11   2013: 24   2018: 45   2023: 75
2004: 21   2009:  9   2014: 19   2019: 47   2024: 40
```

**Nothing before 2000** — that is Yahoo's epoch for this exchange, not a listing fact. The 2000–2002
cluster (168 names) is pre-2000 listings truncated to the epoch.

Depth is also **patchy in the early years**, and the reported `firstTradeDate` is Yahoo's earliest
bar, not the true listing date: **[MEASURED]** BBCA's `firstTradeDate` is **2004-06-08**
(5,463 bars), but BBCA has been listed since 2000. TLKM starts 2004-09-28, ANTM 2005-09-29,
BUMI 2001-06-07.

**Small caps are not truncated.** [MEASURED] AMAR from 2020-01-09, HOMI from 2020-09-10,
PGJO from 2020-01-20, GOTO from 2022-04-11 — all matching their actual IPO dates, all with full
daily coverage. The truncation risk is at the *old* end, not the *small* end. For a Qullamaggie
screener needing ~1–2 years of context per name, depth is a non-issue; for backtesting it caps you
at roughly 2005-onward for a clean cross-section.

### 2.3 Adjustment — the one place Yahoo will hurt you

**What the owners of the claim say.** Yahoo's own help page defines Adjusted Close as
"the closing price after adjustments for all applicable splits and dividend distributions,"
adhering to CRSP standards, with no mention of any other corporate action
([Yahoo Finance help, SLN28256](https://help.yahoo.com/kb/SLN28256.html)).
yfinance's fetcher agrees at the source level — it requests exactly
`params['events'] = 'div,splits,capitalGains'` and computes `df['Adj'] = df['Adj Close'] / df['Close']`
([`yfinance/scrapers/history.py`](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py)).
**Rights issues are not in that list.**

This matters disproportionately on IDX, where rights issues (HMETD/PMHMETD) are routine and often
deeply discounted.

**What I actually measured, which is worse than "not adjusted".** I pulled BBRI's September 2021
window (its large rights issue) with `auto_adjust=False`:

```
2021-09-07  Open 3536.30  Close 3554.48   Adj Close 2528.53   Splits 0.0   Divs 0.0
2021-09-08  Open 3820.00  Close 3730.00   Adj Close 2653.39   Splits 0.0   Divs 0.0
```

Every bar before 2021-09-08 has non-round prices; every bar from 2021-09-08 onward is round (IDX
trades on whole-rupiah ticks). The pre-event prices are scaled by exactly **10/11 ≈ 0.909091**
(`3536.30 / 0.909091 = 3890`, a real BBRI price). Yet `Ticker("BBRI.JK").splits` contains only
**2011-01-11 (2:1)** and **2017-11-10 (5:1)** — nothing in 2021 — and 2021's only dividend is
2021-04-06.

So: **Yahoo applied a rights-issue rescale to the OHLC series and exposed it in neither the
`Stock Splits` nor the `Dividends` column.** Three consequences for the build:

1. **`Close` from yfinance is not the raw exchange close.** Anything that depends on the actual
   traded price — IDX tick-size bands, ARA/ARB auto-rejection limits, "was this a Rp 50 floor stock"
   — cannot be computed from yfinance data alone.
2. **You cannot audit the adjustment.** `Adj Close / Close` recovers only the dividend factor; the
   split and rights factors are already folded into OHLC upstream and are not itemised.
3. **Whether the factor is *correct* is [UNVERIFIED].** 10/11 does not obviously match a
   theoretical-ex-rights-price calculation for BBRI's 2021 issue. If it is wrong, you get a phantom
   gap in the price series at the rights date — exactly the kind of artefact that a breakout detector
   will happily flag as a setup.

**Mitigation for v1:** since the series is *internally consistent* (continuously adjusted backwards),
momentum, ADR, moving averages and consolidation detection all work fine. The risk is confined to
(a) absolute-price rules, and (b) trusting an individual historical bar. A cheap guard is to flag
any single-bar move beyond ~±25% that has no `Stock Splits`/`Dividends` event as *suspect
corporate action* and exclude the name from that night's ranking.

### 2.4 Volume units — settled

The ticket asks whether IDX-sourced volume is lots or shares. Two independent confirmations:

- **IDX's own convention** is shares. The Dataset-Saham-IDX column dictionary, which mirrors the IDX
  daily trading summary field-for-field, documents `volume` as *"Volume perdagangan (dalam satuan
  lembar)"* — trading volume **in shares** — and carries a separate `value` field in rupiah
  ([Keterangan Nama Kolom.md](https://github.com/wildangunawan/Dataset-Saham-IDX/blob/master/Keterangan%20Nama%20Kolom.md)).
- **[MEASURED] on Yahoo's data directly.** Σ(`Close` × `Volume`) over all 834 priced names on
  2026-08-04 = **Rp 12.07 trillion**, a normal IDX session. Top contributors: BBCA Rp 903 bn,
  BBRI Rp 585 bn, TPIA Rp 517 bn, BMRI Rp 517 bn. Interpreting volume as lots would put the session
  at Rp 1,207 trillion (~US$74 bn), which is absurd for IDX.

**So `value_traded = Close × Volume` in rupiah, directly.** No ×100 correction.

**[MEASURED] what that does to the universe** under the method's liquidity floor (20-day median
value traded):

| Floor | Names passing (of 840) |
|---|---|
| Rp 1 bn/day | **292** |
| Rp 3 bn/day | 196 |
| Rp 5 bn/day | 165 |
| Rp 10 bn/day | 109 |

The tradeable IDX universe is ~290 names at the Rp 1B floor, not 840 and not 963. That is a
materially useful number for the universe-definition ticket (05) and for "top decile" sizing
(≈29 names per decile).

### 2.5 Data quality: zero-volume and phantom bars

**[MEASURED]** across 840 symbols × 5 years: the mean fraction of bars with `Volume == 0` is
**4.0%**, and **5.2% of tickers have >20% zero-volume bars**. Yahoo emits a bar with a carried-forward
price and zero volume on days a stock did not trade or was suspended — INAF/POLL/BIMA showed
*more* bars over 6 months (121) than actively traded names (119).

This aligns with IDX's own convention, where a suspended stock reports 0 for High, Low, Change,
Volume and Value ([same column dictionary](https://github.com/wildangunawan/Dataset-Saham-IDX/blob/master/Keterangan%20Nama%20Kolom.md)).

**Any ADR, range, or consolidation-tightness computation must drop `Volume == 0` bars**, or a
suspended stock will look like the tightest consolidation in the market. This is a concrete answer
to the map's open "Data quality handling on IDX" item.

### 2.6 Sector field — wrong taxonomy

**[MEASURED]** `Ticker.info` returns Yahoo's own taxonomy, with both display and key forms:

| Ticker | `sector` | `industry` |
|---|---|---|
| BBCA | Financial Services | Banks - Regional |
| ANTM | Basic Materials | Gold |
| TLKM | Communication Services | Telecom Services |
| BUMI | Energy | Thermal Coal |
| PGJO | Industrials | Marine Shipping |

This is a GICS-*like* scheme, **not IDX-IC** (the exchange's own Industrial Classification, in force
since 2021, with 12 sectors and a sub-industry level). Two implications:

- It is *consistent with the US market's* sector labels, which is actually an advantage for the
  cross-market sector-rotation view the map calls for — you get one taxonomy across IDX and US free.
- It will not match what an Indonesian trader sees on Stockbit or the IDX site, and the sector
  *indices* used for relative-strength (IDXENERGY, IDXFINANCE, …) are IDX-IC. Deciding which
  taxonomy wins belongs to ticket 03; this note just establishes that Yahoo gives you the
  GICS-like one and nothing else.
- Cost: `Ticker.info` is one request per symbol. Cache it and refresh monthly, not nightly.

### 2.7 Rate limits, stability, freshness

**[MEASURED] throughput.** `yf.download(840 symbols, period="5y", threads=8)` completed in
**11.5 seconds** and returned data for **all 840** (zero empties), **904,414 bars total**.

**[MEASURED] rate limit.** Immediately after that bulk pull, the next screener call and then ~10
consecutive `Ticker.history()` calls all raised `YFRateLimitError('Too Many Requests. Rate limited.
Try after a while.')`. The block persisted across several minutes and multiple 15–20 s backoffs;
requests only started succeeding again after a few minutes of near-idle. **The nightly job must
pace itself and retry with exponential backoff** — this is the single most likely thing to break a
scheduled run. In practice: use one batched `yf.download` for prices (cheap, 1 request per ~200
symbols) and *avoid* per-symbol `.info` calls in the same run.

**[MEASURED] endpoint stability.** `https://query1.finance.yahoo.com/v8/finance/chart/BBCA.JK`
answers **unauthenticated, with no crumb/cookie dance**, returning full metadata. The historically
fragile part of yfinance (the crumb/consent flow) is not currently on the critical path for chart
data.

**Freshness.** [MEASURED] at **19:49 WIB on 2026-08-04** — 3h49m after the 16:00 WIB close — the
2026-08-04 bar was present and final for every actively-traded name. Yahoo's quote metadata reports
`exchangeDataDelayedBy: 10` (minutes) and `sourceInterval: 10` for all 840 symbols, so the intraday
feed is 10-minute delayed. **[UNVERIFIED]:** the exact earliest time the settled EOD bar appears. A
nightly job scheduled at ~19:00 WIB / 12:00 UTC or later is comfortably safe; anything before
~17:00 WIB should be treated as unproven.

### 2.8 Storage footprint

**[MEASURED]** 5 years × 840 symbols = **904,414 daily bars**, ≈ **50 MB** as 6 float columns.
Extrapolating to full available history (effectively 2000-onward, most names much shorter) gives
roughly **2.5M bars / ~140 MB** [UNVERIFIED — estimated from the `firstTradeDate` distribution, not
downloaded].

This is important context for ticket 04's conclusion: **IDX alone fits inside a 500 MB hosted row
store comfortably.** Ticket 04's ~2 GB blocker is driven by the US universe (7,000 symbols), not by
IDX. If the storage design ever needs to degrade gracefully, IDX is not the part that breaks.

### 2.9 Terms of service — an honest reading

This is the weakest part of the recommendation and should be stated plainly.

- yfinance's own README: *"yfinance is **not** affiliated, endorsed, or vetted by Yahoo, Inc. It's an
  open-source tool that uses Yahoo's publicly available APIs, and is intended for research and
  educational purposes"* and *"Remember - the Yahoo! finance API is intended for personal use only"*
  ([README](https://github.com/ranaroussi/yfinance/blob/main/README.md)).
- Yahoo's Developer API ToS restricts commercial exploitation — *"Sell, lease, share, transfer, or
  sublicense the Yahoo APIs … or derive income from the use or provision of the Yahoo APIs"* — and
  bans usage that *"exceeds reasonable request volume, constitutes excessive or abusive usage"*
  ([Yahoo Developer API ToU](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html)).
- **Caveat on that citation:** those are the terms for Yahoo's *documented developer program*.
  `query1.finance.yahoo.com/v8/finance/chart` is an **undocumented internal endpoint** that no
  published Yahoo ToS explicitly covers. Anyone telling you the position is clear-cut is
  overstating it. **[UNVERIFIED]** whether these specific terms bind use of the chart endpoint.

**Where that leaves this project.** The map's constraints — *single user*, *hosted free tier*,
*no redistribution*, *EOD only* — land this squarely in the "personal use" framing that yfinance
itself invokes. There is no redistribution and no income. The volume constraint is the live one, and
§2.7 shows it is real and enforced. **If this ever became multi-user or commercial, the source has to
change.** That is the clearest "what would make us switch" trigger.

---

## 3. IDX official — free in principle, closed in practice

**[MEASURED] the site actively blocks automated access.** Every server-side request I made returned
Cloudflare **HTTP 403**, including with a full browser header set (UA, Accept, Referer, `sec-ch-ua`,
`Sec-Fetch-*`, compression):

- `https://www.idx.co.id/primary/StockData/GetSecuritiesStock?...` → **403**
- `https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles?...` → **403**
- `https://www.idx.co.id/en/market-data/stocks-data/stock-list/` → **403**
- even `https://www.idx.co.id/robots.txt` → **403** ("Sorry, you have been blocked")

I could not read IDX's robots.txt to check whether scraping is *permitted*, because the block also
covers robots.txt. That is itself the answer about intent.

**The data is a commercial product.** IDX sells market data under IDX Data Services, with a licence
catalogue and pricelist covering IDX Market Data, Connection, Index, Publication and Advertisement
licences, distinguishing Display vs Non-Display categories and requiring a Display licence to
redistribute ([IDX Data Services](https://www.idx.co.id/en/products/idx-data-services/),
[2024 catalogue and pricelist](https://www.idx.co.id/media/2qalvu4z/20240923_idx-data-catalogue-pricelist-2024.pdf),
[data.idx.co.id](https://data.idx.co.id/)). Free programmatic access is not on offer.

**But it is the only source of three things we cannot get elsewhere:** true unadjusted OHLC, the
authoritative IDX-IC sector classification, and an official corporate-actions record (which would
let us do rights adjustment properly). That is why it is the fallback, not a rejected option — see §7.

---

## 4. Sources whose terms forbid this use

**Stockbit — explicitly closed.** Their Terms of Use state, verbatim:

> "You agree not to reproduce, retransmit, distribute, disseminate, sell, publish, broadcast or
> circulate the content received through Stockbit.com to anyone, including but not limited to others
> in the same company or organization, nor any use of data mining, robots, spiders, or similar data
> gathering and extraction tools for any purpose without the express prior written consent of
> Stockbit"

([stockbit.com/terms](https://stockbit.com/terms)). That covers exactly what we would be doing.
**Rule it out.** It is otherwise the best free IDX data product in existence, which makes this a
genuine loss, not a formality.

**Investing.com — closed in practice.** `investpy`, the canonical Python client, carries a
maintainer warning that it *"is not working fine currently due to some Investing.com changes in
their APIs"* and redirects users to a stopgap replacement
([investpy README](https://github.com/alvarobartt/investpy/blob/master/README.md)). To be fair to
the source: the README does **not** allege legal action, only API changes — I could not verify the
frequently-repeated blog claim that Investing.com issued a takedown. **[UNVERIFIED].** I was unable
to fetch Investing.com's own terms page during this research, so their scraping clause is
**[UNVERIFIED]** — but a source whose only working client is abandoned is not a foundation for a
nightly job regardless.

**Google Finance — no programmatic access at all.** Google deprecated the Finance API in 2011 and
shut it down in 2012; the only supported access is the `GOOGLEFINANCE()` Sheets formula, whose data
is delayed and marked not for professional use
([GOOGLEFINANCE docs](https://support.google.com/docs/answer/3093281?hl=en)). A spreadsheet formula
cannot back a Python nightly job. **Dead end.**

**Stooq — bot-walled.** [MEASURED] every CSV URL (`stooq.com/q/d/l/?s=bbca.jk&i=d`,
`?s=bbca.id`, and the symbol-list endpoint `stooq.com/db/l/?g=44`) now returns a JavaScript
**proof-of-work challenge** ("This site requires JavaScript to verify your browser") instead of CSV.
Whatever its coverage used to be, it is no longer accessible to a headless Python job. **Dead end.**

---

## 5. Indonesian open-data projects — all stale or paid

**Sectors / sectors.app (Supertype)** — the most credible commercial-grade Indonesian API. Covers
IDX + SGX + KLSE, "99% coverage of IDX-listed stocks", daily updates, endpoints for company
profiles, historical prices, dividends, indices. **But:** *"Sectors Financial API is available to our
Insider plan subscribers"* ([docs.sectors.app](https://docs.sectors.app/)), and **[MEASURED]**
`api.sectors.app/v2/companies/` returns `{"error":"Authentication credentials were not provided."}`.
Their pricing page is behind a Vercel bot checkpoint, so the exact Insider price is **[UNVERIFIED]** —
but there is no free API tier. **Violates the free-sources-only constraint.**

**wildangunawan/Dataset-Saham-IDX** — a genuinely good dataset that is **dead**. [MEASURED] via the
GitHub API: **last data commit `2025-02-23` ("Update data per 23 Feb 25")**, ~17 months stale as of
today. Licence is **CC BY-NC 4.0** (non-commercial — fine for a single-user personal dashboard, not
for anything else). It scrapes the IDX daily summary and therefore carries fields Yahoo does not:
`value`, `frequency`, `listedShares`, `tradebleShares`, `foreignBuy`/`foreignSell`, `delistingDate`,
and both regular and non-regular market volume. Useful as a **historical reference for validating
Yahoo's numbers up to Feb 2025**, and its `List Emiten/all.csv` is a usable (if stale) seed for the
suspended names the Yahoo screener drops. Not a live source.

**baguskto/saham-mcp** — advertises "958 IDX stocks, 2019–2025" but is a thin wrapper that reads CSVs
from Dataset-Saham-IDX, so it inherits the same 2025-02 staleness
([README](https://github.com/baguskto/saham-mcp)). Not an independent source.

**goapi.io** — Indonesian commercial REST API for IDX with historical prices; free registration is
advertised but free-tier quotas are **[UNVERIFIED]** ([goapi.io](https://goapi.io/api-data-saham-indonesia/)).
Not investigated further because Yahoo already dominates on coverage and cost.

**Kaggle datasets** (`muamkh/ihsgstockdata`, `garethharrison/daily-IHSG`) — snapshots, not feeds. No
use for a nightly job.

---

## 6. Dead ends, stated plainly

- I **could not read idx.co.id at all**, by any server-side means, including robots.txt. Every claim
  about IDX's own endpoints in §3 is about *access*, not content — I never saw a payload.
- I **could not verify Investing.com's scraping clause** (fetch blocked), nor the widely repeated
  claim that they issued a legal takedown to `investpy`. The investpy README says only "API changes".
- I **could not verify Sectors' Insider price** (Vercel bot checkpoint), only that the API requires it.
- I **could not empirically pin the exact time** the settled EOD bar becomes available on Yahoo; that
  needs observation across a session boundary, not a single point-in-time probe.
- The BBRI 10/11 rescale is **verified as an unlabelled adjustment**, but whether it is the *correct*
  factor is **[UNVERIFIED]** — establishing that needs an authoritative corporate-actions record,
  which is exactly the thing no free source provides.
- I did **not** test Alpha Vantage / Twelve Data / Finnhub IDX coverage with real API keys. Their
  free quotas (25–800 calls/day) cannot support 840 symbols nightly regardless of coverage, so the
  question is moot. **[UNVERIFIED]** whether they carry `.JK` at all.

---

## 7. Recommendation

### Primary: Yahoo Finance via `yfinance`

Nothing else clears the bar. It is the only source that is simultaneously free, programmatically
accessible, covering the whole active universe, deep enough in history, and fast enough to pull
nightly inside a free-tier job. Concretely:

- **Universe:** nightly `yf.screen(EquityQuery("eq",["exchange","JKT"]))`, paginated 250 at a time.
  Union into a persisted universe table; mark anything not seen tonight as `stale`. Do **not** treat
  the screener as the historical universe.
- **Prices:** one batched `yf.download(symbols, period=..., auto_adjust=False, threads=8)`.
  **[MEASURED] 11.5 s for 840 × 5y.** Keep both `Close` and `Adj Close`.
- **Liquidity:** `Close × Volume` in rupiah, no lot correction. 20-day median ≥ Rp 1B leaves
  **~292 names [MEASURED]**.
- **Hygiene:** drop `Volume == 0` bars before any range/ADR/tightness computation. Flag any
  unexplained single-bar move >±25% (no split, no dividend) as a suspect corporate action.
- **Sectors:** cache `Ticker.info` sector/industry **monthly**, never in the nightly price run —
  per-symbol `.info` calls are what trip the rate limiter.
- **Pacing:** exponential backoff on `YFRateLimitError`; assume a cold-start budget of roughly one
  bulk download plus a small number of extra calls.

### Fallback: headless-browser scrape of idx.co.id

If Yahoo breaks — endpoint change, crumb wall returning, or the rate limit tightening below what a
nightly full-universe pull needs — the only remaining free path to IDX data is the exchange's own
site, driven by a real browser to satisfy Cloudflare (Playwright in the GitHub Actions runner ticket
04 already recommends). It is more work and more fragile per-run, but it is strictly better data:
raw unadjusted prices, official value/frequency/foreign-flow fields, IDX-IC sectors, and delisting
dates. Note that IDX sells this data commercially (§3), so this fallback is defensible only for
strictly personal, non-redistributed use.

**Secondary fallback for the universe list only:** `Dataset-Saham-IDX`'s `List Emiten/all.csv`
(CC BY-NC), stale at Feb 2025, as a seed for suspended tickers the Yahoo screener omits.

### What would make us switch

1. **Multi-user or any commercial use.** The "personal use" framing yfinance leans on stops applying.
2. **Rate limiting tightening** below the ~1-bulk-download-per-night budget measured in §2.7.
3. **A backtest that needs delisted names.** The Yahoo screener universe is survivorship-biased
   (§2.1); a serious historical replay forces the IDX scrape or a paid source.
4. **Rights-issue accuracy becoming load-bearing** — e.g. if absolute price levels, ARA/ARB bands, or
   tick-size rules enter the star score. Yahoo's opaque adjustment (§2.3) cannot support that.
5. **Sectors/Supertype introducing a free tier.** It is the best-shaped product for this use case and
   only price disqualifies it.

### Is a full-universe nightly pull feasible on a free tier?

**Yes, comfortably — for IDX.** [MEASURED] 840 symbols, 5 years, 11.5 seconds, ~50 MB. Even a full
backfill is minutes, not hours, and fits inside every free-tier store and every scheduler in ticket
04. The binding constraint is **Yahoo's rate limiter**, not compute, bandwidth, or storage.

---

## 8. Sources

- [yfinance README (legal disclaimer, personal-use statement)](https://github.com/ranaroussi/yfinance/blob/main/README.md)
- [yfinance `scrapers/history.py` (adjustment implementation)](https://github.com/ranaroussi/yfinance/blob/main/yfinance/scrapers/history.py)
- [Yahoo Finance help — Adjusted Close definition (SLN28256)](https://help.yahoo.com/kb/SLN28256.html)
- [Yahoo Developer API Terms of Use](https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html)
- [IDX Data Services (product page)](https://www.idx.co.id/en/products/idx-data-services/)
- [IDX Data Catalogue and Pricelist 2024 (PDF)](https://www.idx.co.id/media/2qalvu4z/20240923_idx-data-catalogue-pricelist-2024.pdf)
- [IDX Data Services Portal](https://data.idx.co.id/)
- [Stockbit Terms of Use](https://stockbit.com/terms)
- [investpy README (maintainer deprecation notice)](https://github.com/alvarobartt/investpy/blob/master/README.md)
- [GOOGLEFINANCE function docs](https://support.google.com/docs/answer/3093281?hl=en)
- [Sectors Financial API docs (Insider-plan gate)](https://docs.sectors.app/)
- [Sectors.app](https://sectors.app/)
- [wildangunawan/Dataset-Saham-IDX](https://github.com/wildangunawan/Dataset-Saham-IDX)
- [Dataset-Saham-IDX column dictionary (volume in shares; suspension = zeros)](https://github.com/wildangunawan/Dataset-Saham-IDX/blob/master/Keterangan%20Nama%20Kolom.md)
- [baguskto/saham-mcp](https://github.com/baguskto/saham-mcp)
- [goapi.io — API Data Saham Indonesia](https://goapi.io/api-data-saham-indonesia/)
- [Databoks — IDX listed company count, 2026](https://databoks.katadata.co.id/en/market/statistics/6a24e09f528c8/listed-companies-on-the-idx-remained-relatively-stagnant-through-april-2026)
- [Wikipedia — Indonesia Stock Exchange](https://en.wikipedia.org/wiki/Indonesia_Stock_Exchange)
