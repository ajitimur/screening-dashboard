# Free EOD data sources for IDX

Type: research
Status: resolved
Blocked by: —

## Question

What free sources can supply daily OHLCV for the full IDX equity universe, and which one should v1 build on?

For each candidate (at minimum: Yahoo Finance `.JK` via yfinance, the IDX official site / IDX API,
Stockbit, Investing.com, Google Finance, Wikipedia/IDX listing pages, any Indonesian open-data project):

- **Universe coverage** — does it enumerate *all* listed tickers, or only ones you already know? Is there
  a free way to get the current listing plus delisted names?
- **History depth** — how many years of daily bars, and is it truncated for small caps?
- **Adjustment** — are prices adjusted for splits, reverse splits, dividends, and rights issues (very
  common on IDX)? If unadjusted, is there a corporate-actions feed to adjust with?
- **Volume units** — IDX quotes in lots (100 shares); confirm whether the source reports shares or lots,
  since the Rp 1B/day liquidity floor depends on getting value-traded right.
- **Rate limits, ToS, and stability** — is scraping required, is it against terms, how likely to break.
- **Freshness** — what time after the IDX close (16:00 WIB) is the day's bar available.
- **Sector/industry field** — does it carry one, and which taxonomy (IDX-IC vs GICS-like)?

Deliver a comparison table plus a recommendation, including a fallback source and what would make us
switch. Flag anything that makes a full-universe nightly pull infeasible on a free tier.

## Answer

Findings: [`research/01-idx-data-sources.md`](../research/01-idx-data-sources.md). Verified empirically
against live data on 2026-08-04, not read from docs.

**Recommendation: Yahoo Finance `.JK` via yfinance**, fallback a headless-browser scrape of idx.co.id.
Nothing else clears the free bar.

### Verified facts

- **Universe enumeration is solved.** `yf.screen(EquityQuery("eq",["exchange","JKT"]))` returns
  **840 symbols in 0.8s**, all `quoteType: EQUITY`, with marketCap / sharesOutstanding / ADV attached.
- **The 840-vs-963 gap is explained** (this closes ticket 05's open question): IDX lists 963; the ~120
  missing were probed and are **suspended or delisted** (WSKT, SRIL, ENVY, INAF, POLL, BIMA, TRAM,
  MYRX all absent). They remain fetchable *by symbol* but are not discoverable — so the screener
  carries **survivorship bias**, which matters for any backtest, not for tonight's scan.
- **Volume is shares, not lots.** Σ(close×volume) across 834 names = **Rp 12.07 trillion** for the
  session — a normal IDX day; lots would give Rp 1,207T. So `value_traded = Close × Volume`, no lot
  correction. **At the Rp 1B/day floor, 292 of 840 names survive** — that is the real tradeable IDX
  universe. Hand this number straight to tickets 05 and 06.
- **Throughput is a non-issue; rate limiting is the constraint.** All 840 × 5y downloaded in **11.5s**
  — 904,414 bars, ~50 MB, zero empties. The *very next* API call threw `YFRateLimitError` and it
  persisted for minutes across backoffs. Bulk OHLCV is cheap; per-symbol `.info` is what trips it
  (consistent with ticket 03's independent finding).
- **Small caps are not truncated** at the recent end — AMAR/HOMI/PGJO/GOTO all run from actual IPO.
  Truncation is at the *old* end: nothing before 2000 anywhere, and BBCA starts 2004 despite listing
  in 2000.
- **4.0% of bars have Volume == 0**, and 5.2% of tickers exceed 20% zero-volume bars. Suspended names
  emit *more* bars than active ones — phantom flat bars. These must be dropped before any ADR or
  tightness computation, or they will fabricate contraction.

### The finding that matters most

Yahoo's docs and yfinance's source both state Adj Close accounts for **splits + dividends only**. The
agent measured something worse than "rights issues are unadjusted": **BBRI's OHLC before 2021-09-08 is
rescaled by exactly 10/11, with no corresponding entry in either the `Stock Splits` or `Dividends`
column.** Yahoo *does* apply rights adjustments — invisibly and unauditably.

Consequences:
- You cannot recover raw traded prices, and cannot verify the adjustment is correct (whether 10/11 is
  even right here is unverified).
- **Momentum, MA and consolidation logic are safe** — the series is internally consistent, which is all
  those need.
- **Absolute-price rules are not safe** — tick bands, ARA/ARB reconstruction, and anything comparing a
  historical price to a real-world level. Ticket 05's "adjusted vs raw" question is therefore not a
  free choice on IDX: raw is simply unavailable.

### Ruled out, with the blocking clause

- **Stockbit** — ToS verbatim bans "data mining, robots, spiders". The best free IDX product; a hard
  rule-out, not a maybe.
- **idx.co.id** — Cloudflare **403 on every endpoint including `robots.txt`**, even with full browser
  headers. The data is a licensed paid product. (Matches ticket 03's independent result.)
- **Stooq** — now serves a JS proof-of-work challenge instead of CSV. Dead for IDX.
- **Sectors/Supertype** — excellent fit, but the API needs the paid Insider plan.
- **Dataset-Saham-IDX** — last data commit 2025-02-23, 17 months stale. Retained only as a stale
  universe seed, and as the primary citation that IDX volume is `dalam satuan lembar` (shares).
- **Google Finance** — API dead since 2012, Sheets-only.

### Honest gaps

Could not read idx.co.id content at all (only its access behaviour). Could not verify Investing.com's
scraping clause, nor the claimed legal takedown of investpy — its README cites only "API changes".
Could not pin exactly when Yahoo's EOD bar settles: the 2026-08-04 bar was final at 19:49 WIB, so a
**≥19:00 WIB** schedule is safe and anything earlier is unproven. Feed that to ticket 12.
