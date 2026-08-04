# Free EOD data sources for US

Type: research
Status: resolved
Blocked by: —

## Question

What free sources can supply daily OHLCV for the US equity universe at the scale this screen needs,
and which one should v1 build on?

Candidates to cover at minimum: Yahoo Finance (yfinance), Stooq, Nasdaq/NYSE listing files,
Alpha Vantage free tier, Tiingo free tier, Financial Modeling Prep free tier, EODHD free tier,
Polygon free tier, SEC/CIK reference data.

Evaluate on:

- **Universe enumeration** — a free, reliable list of currently listed common stocks across
  NYSE/Nasdaq/AMEX, with ETFs and funds separable (his universe is stocks; ETFs appear only as
  sector proxies).
- **Scale** — roughly 6,000+ symbols pulled nightly. Which sources survive that on a free tier, and
  what the wall-clock and rate-limit picture looks like.
- **History depth and adjustment** — years available; split/dividend adjustment; whether adjusted and
  raw are both obtainable (ADR and gap math want raw; return math wants adjusted).
- **Survivorship** — is delisted history retrievable? Matters for any later backtest.
- **Freshness** — availability after the 16:00 ET close.
- **Sector/industry field** and its taxonomy.
- **ToS and stability** — scraping vs. sanctioned API; known breakage history.

Deliver a comparison table plus a recommendation and a fallback. Note explicitly whether one source can
serve **both** IDX and US, since a single-source design is materially simpler.

## Answer

Findings: [`research/02-us-data-sources.md`](../research/02-us-data-sources.md). Measured against live
data — Yahoo publishes no rate limits, so every throughput number here is empirical.

**Recommendation: yfinance as the single primary source for *both* markets**, fallback Massive
(ex-Polygon) Basic for US.

### One source serves both markets

yfinance covers IDX via `.JK` with the same client, call, schema, adjustment fields and **the same
Yahoo sector taxonomy** as US — `BBCA.JK` returns 5,463 rows back to 2004-06-08 with splits and
dividends intact. No other viable candidate does this (FMP free is explicitly US-only; Massive is US
equities). So this ticket's key question is answered: **one ingester, not two**, and cross-market
sector rotation needs no mapping layer. This corroborates tickets 01 and 03 independently.

### Rate limiting is mandatory, not an optimisation

Full 5,711-symbol US universe, 2y bars:

| Approach | Result |
| --- | --- |
| Unthrottled | 75s but **only 52.9% of symbols** — 5,374 × HTTP 429 |
| **Capped at 12 req/s** | **8.5 min, 99.93% coverage, zero 429s** |

The unthrottled failure mode is the dangerous one: yfinance reports throttled symbols as
`"possibly delisted; no price data found"`. An unrated implementation ships a screener that silently
drops half the universe **and blames delisting for it**. This is the third independent sighting of
Yahoo failing as silence (see tickets 01 and 03) — treat it as a standing property of the data layer,
not three separate bugs.

**Caveat:** 12 req/s was measured from a **residential IP**. Yahoo is more aggressive toward datacenter
ranges. Since v1 runs locally this is favourable — the measurement matches the deployment — but it
becomes an upper bound to re-validate if the app is ever hosted.

### Three problems worth flagging rather than burying

1. **The partial live bar — proven.** At 09:44 ET, AAPL already had a bar dated that day with 8.5M
   volume: 14 minutes of trading presented as a daily bar. Any ADR, gap or volume computation touching
   the final bar is silently wrong. And because US and IDX sessions are disjoint, **there is no single
   safe run time** — this constrains ticket 12's scheduling and ticket 08's use of the latest bar.
2. **Survivorship bias.** TWTR, ATVI, VMW, SIVBQ all return **0 rows**. Any backtest is biased upward.
   Cheap mitigation worth starting day one regardless of when validation gets designed: **snapshot the
   Nasdaq listing files nightly** to accumulate a point-in-time universe going forward.
3. **ToS.** Yahoo prohibits volume constituting "excessive or abusive usage", judged at their "absolute
   and sole discretion". Single-user personal use does not trip the income or sharing clauses, but the
   honest characterisation is **tolerated, not authorised**. Say so in the spec rather than passing
   over it.

### Verified facts

- **Universe enumeration solved** — Nasdaq Trader files over HTTPS (not just FTP), with an `ETF` flag
  that separates funds cleanly → **5,711 symbols** after filtering, matching this ticket's ~6,000
  premise.
- **Memory** — the 2y in-memory pandas frame measured **161 MB**. Fine locally; worth noting that
  materialising the whole frame is a choice, and streaming per chunk is the alternative.

### Dead ends

- **Stooq is gone** — returns HTTP 200 with a JS proof-of-work interstitial (verified for both `.us`
  and `.jk`). Because it is a 200 with HTML, naive clients parse garbage rather than erroring.
  `pandas-datareader`'s Stooq path no longer imports.
- Eliminated on arithmetic alone: Alpha Vantage (**25 req/day**), Tiingo (**500 unique symbols/month**),
  FMP (**250/day**, US-only), EODHD (**20/day**, 1y history).

### For ticket 12

**Polygon.io rebranded to Massive.com** (2025-10-30); polygon.io URLs now 301, so any existing citation
of its pricing needs re-checking. Its grouped-daily endpoint returns the whole US market in **one
call** — nightly cost of 1 request — but it is US-only, capped at 2y history, and was **not** exercised
with a real key. Documented-only.
