# 06. Tracking sector rotation: where is money moving now

Research for the question "how do we better track sector rotation so the trader can see where money is currently moving". Date: 2026-09-16.

Constraints assumed: $0 for market data (free sources only), EOD nightly, Python backend, both US and IDX, and the repo's established philosophy that sector strength is **bottom-up** (aggregated from member ranks) rather than an index or ETF price. The current model, which this note does not re-derive, is in `backend/screener/sectors.py`, `CONTEXT.md` (Sector strength, Shape differential, Temporal delta) and `.scratch/screening-dashboard/v1-spec.md` §4.4. The RRG is spec'd as phase 2 in `.scratch/screening-dashboard/v2-frontend-spec.md` §4.5 and §11.3.

Every fetch below was run on 2026-09-16 from this machine with the backend venv (`yfinance 1.5.2`, `duckdb 1.5.5`) or `curl`. "Verified by fetching" means it worked today; "documented, not verified" means the claim rests on the cited page and was not exercised.

---

## TL;DR

- **The store already holds everything needed for two of the three recommended additions.** `bars` carries `open, high, low, close (unadjusted), adj_close, volume` for 12,353 US and 845 IDX symbols (`backend/screener/store.py:76-85`, censused below). Sector **dollar-volume share** and sector **breadth** (percent of members above a moving average, net new highs) need no new data.
- **The current model measures leadership concentration, not flow.** Decile share counts a sector's members in the market-wide top 10%; it says where the *winners* sit. It says nothing about how much capital is trading there or how many members participate. Those are the two questions the trader's "where is money moving" phrasing actually asks, and they are answered by volume and breadth, not by more return ranks.
- **RRG's formula is not public.** JdK RS-Ratio and RS-Momentum are trademarks of RRG Research; StockCharts documents definitions, quadrants and rotation direction but not the calculation, and Optuma states its implementation is proprietary. A bottom-up analogue (a smoothed, normalized ratio of a sector's aggregate to the universe, and its rate of change) can be built from data the repo has, and it is what the v2 spec's "dates x members matrix, EWM, per-date cross-section" already describes. It must not carry the JdK name.
- **The academic evidence supports the lookbacks already in use.** Industry momentum is real and accounts for much of stock momentum (Moskowitz and Grinblatt 1999), momentum pays at 3 to 12 month horizons (Jegadeesh and Titman 1993; Conrad and Kaul 1998), and business-cycle sector rotation delivers at best 2.3% a year even with perfect foresight (Jacobsen, Stangl and Visaltanachoti 2009). Nothing in the literature licenses a fancier phase model; it licenses measuring recent relative momentum, which the repo does.
- **Free data findings, verified today:** all 11 SPDR sector ETFs and RSP/SPY return daily bars from Yahoo; Yahoo exposes ETF `totalAssets`, `netAssets`, `sharesOutstanding` and top holdings but **no fund-flow field**; SSGA's daily holdings spreadsheet downloads (weights and shares held per name); FINRA's daily short-volume file downloads and covers 12,333 symbols including every US ETF; the **IDX sector indices exist on Yahoo (`IDXENERGY.JK` and ten siblings) but serve only today's quote, no history**; `idx.co.id` is 403 to automation as before.
- **Recommendation, in order:** (1) sector dollar-volume share and its 5d-vs-60d change, with an up/down split; (2) sector breadth: percent of members above their 20 and 50 day MA plus net 20-day new highs; (3) a bottom-up rotation trajectory that re-expresses the existing two rotation columns on a normalized scale with a short trail, as the phase-2 RRG band. Each is computed from `bars` and `ranks`, each needs a lead-lag measurement against stored history before it earns a column, and any use inside the star score is governed by ADR 0005's selection-contrast rule.

---

## 1. What the current model measures, and the gap

`sector_strengths()` in `backend/screener/sectors.py:151-200` counts, per sector and per lookback, how many members sit in the market-wide top decile of calendar return, divides by the sector's universe count, and reports two rotation columns: `share(1w) - share(6m)` and `share(1m, tonight) - share(1m, 20 sessions ago)` (`sectors.py:56-66`). The spec rejected an index return because "a sector where 8 of 40 names are ripping and 32 are flat has a mediocre index return but is exactly the sector to surface" (`v1-spec.md` §4.4).

That is a **leadership** measure. Three things it cannot see:

1. **Participation below the decile.** A sector whose 32 flat names start moving from the 40th to the 70th percentile has no change in decile share until they cross the 90th. Breadth measures (section 4) see it immediately.
2. **Capital.** Two sectors with the same decile share can differ tenfold in dollars traded. Volume measures (section 3) see it.
3. **Trajectory.** The two columns are point estimates. The phase-2 RRG band exists to add a trail (`v2-frontend-spec.md` lines 857-862).

The rest of this note is about filling those three gaps from data the store already has, and what would need to be measured first.

### Store census (verified by querying a copy of `data/screener.duckdb`, 2026-09-16)

| Market | Symbols with bars | Bars | Earliest | Latest | Zero-volume bars | Ranked names on latest session |
|---|---|---|---|---|---|---|
| US | 12,353 | 33,403,392 | 1962-01-02 | 2026-09-15 | 0 | 2,047 |
| IDX | 845 | 2,213,236 | 1995-05-12 | 2026-09-16 | 0 | 353 |

Zero-volume bars are absent by construction (the phantom-bar rule, `CONTEXT.md` "Phantom bar"). The `labels` table carries `(market, symbol, sector, industry, resolved_on)`, so the sector axis is already joinable to bars.

---

## 2. Relative Rotation Graphs

### 2.1 What is publicly documented

StockCharts' ChartSchool pages are the most complete public description and are written with RRG Research's cooperation (de Kempenaer is a StockCharts contributor). Verified by fetching, 2026-09-16:

- **JdK RS-Ratio**: "an indicator that measures the trend for relative performance", above 100 an uptrend in relative performance, below 100 a downtrend. **JdK RS-Momentum**: "an indicator that measures the momentum (rate-of-change) of RS-Ratio", used "to anticipate turns in RS-Ratio". Source: [ChartSchool, Relative Rotation Graphs](https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-types/relative-rotation-graphs-rrg-charts).
- **Normalization**: both lines are "expressed in the same unit of measure and fluctuate above/below the same level (100), regardless of the specific security being assessed", so RS-Ratio values are comparable across securities sharing a benchmark. "At least 50 data points are required" to compute them. Source: [ChartSchool, RRG Relative Strength](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/rrg-relative-strength).
- **Quadrants**: Leading (ratio > 100, momentum > 100), Weakening (ratio > 100, momentum < 100), Lagging (both < 100), Improving (ratio < 100, momentum > 100). "The arrows on the model Relative Rotation Graph above show the idealized rotation, which is clockwise." Examples use 12-week trails; "weekly rotations are stronger than daily". Same source as the first bullet.
- **Provenance**: "RRGs were developed in 2004-2005 by Julius de Kempenaer, who would later become the Director of RRG Research." Same source.

### 2.2 What is proprietary

- Neither ChartSchool page discloses the smoothing or the normalization formula (both fetched and read for exactly that).
- Optuma, a licensed implementation, documents RRG Lines as "a proprietary tool, based on the Relative Rotation Graph (RRG) work of Julius de Kempenaer" with a single user-facing "Sensitivity" parameter and no formula. Verified by fetching: [Optuma knowledge base, RRG Lines](https://www.optuma.com/kb/optuma/tools/rrg-tool-module/rrg-lines).
- RRG Research's own site ([relativerotationgraphs.com](https://www.relativerotationgraphs.com/)) carries a one-sentence description ("a unique visualization that shows trends in relative strength ... of multiple securities in a universe against a common benchmark AND each other") and no methodology page; `/rrg-explained` returned 404 today. RRG, JdK RS-Ratio and JdK RS-Momentum are registered trademarks (stated on the StockCharts pages and RRG Research's site; documented, the trademark registry itself was not checked).

Consequence: any implementation here is an **analogue**, and should be labeled as such in the UI and the API (for example `rotation_ratio` / `rotation_momentum`, never `rs_ratio` with the JdK name).

### 2.3 Can it be computed bottom-up from constituent deciles?

Yes, and the v2 spec already assumes so. The phase-2 cost line reads: "A `dates x members` matrix, EWM, a per-date cross-section, plus a second whole-universe pass, retaining a 3-week trail" (`v2-frontend-spec.md:112` and `:1595`). That is a bottom-up construction: a per-date aggregate over members, smoothed with an exponentially weighted mean, and normalized against the cross-section of sectors on each date.

Two candidate inputs, both already in the store:

- **The decile-share series itself.** `share(1m)` per sector is a stored quantity, one row per `(market, session)` in `ranks`. Its EWM level, normalized across the 11 sectors on each date, is a ratio-like axis; the EWM of its first difference is a momentum-like axis. This is the existing temporal delta re-expressed with smoothing and a trail, so it stays inside the model the trader accepted.
- **The equal-weighted member return** per sector against the equal-weighted universe return, compounded over a window, then smoothed and normalized the same way. This is closer to a conventional RRG (a return ratio) and is *not* the decile model; the spec's rejection of the index return in §4.4 applies to it as a strength measure, though not necessarily as a trajectory display.

The first is the one consistent with `v2-frontend-spec.md` §11.4 ("Both rotation models survive permanently ... breadth vs weight"): if the RRG band is built on the share series, the two bands stop disagreeing in kind and the permanent disclaimer line becomes unnecessary. If it is built on returns, the disclaimer stays. That is a product decision this note flags rather than makes.

One caution that is the repo's own: ticket 07 S3 records that the trader "overruled" a sparkline-and-eyeball proposal and required rotation "computed and sortable" (`.scratch/screening-dashboard/issues/07-sector-theme-and-rotation-model.md:97-100`). An RRG plot is the sparkline's two-dimensional cousin. It only satisfies S3 if the two axes and the quadrant label are also sortable columns in the companion list, which the v2 spec's "slimmed companion list (rank order / rank_score / trail arrow only)" should be read as requiring.

---

## 3. Money-flow and volume measures

All four below are computable from the `bars` columns the store has. Original definitions, verified by fetching the ChartSchool pages on 2026-09-16 (StockCharts is the canonical public statement of each formula; original authors are named where they exist):

| Measure | Definition | Author | Source |
|---|---|---|---|
| On-Balance Volume | "If the closing price is above the prior close price then: Current OBV = Previous OBV + Current Volume. If the closing price is below the prior close price then: Current OBV = Previous OBV - Current Volume." Unchanged on an equal close. | Joseph Granville, *Granville's New Key to Stock Market Profits* (1963) | [ChartSchool, OBV](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/on-balance-volume-obv) |
| Chaikin Money Flow | Money Flow Multiplier = `[(Close - Low) - (High - Close)] / (High - Low)`; Money Flow Volume = multiplier x volume; CMF = 20-period sum of MFV / 20-period sum of volume. Bullish above about +0.05, bearish below about -0.05. | Marc Chaikin | [ChartSchool, CMF](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/chaikin-money-flow-cmf) |
| Up/down volume (Arms Index) | TRIN = `(advances / declines) / (advancing volume / declining volume)`; below 1.0 accompanies advances, above 1.0 declines. | Richard W. Arms, 1967 | [ChartSchool, Arms Index](https://chartschool.stockcharts.com/table-of-contents/market-indicators/arms-index-trin) |
| Dollar-volume share | No canonical author. `sum over sector members of close x volume / sum over universe of close x volume`, using the **unadjusted** close, which is how the repo already defines dollar volume (`v1-spec.md:179`, `:255`). | (this repo) | `backend/screener/store.py:83` ("unadjusted, for dollar volume") |

### 3.1 Feasibility and fit

- **Dollar-volume share** is the cleanest "where is capital trading" number. It is a share of a total, so it has the same 0-to-1 semantics as decile share, it is robust to a sector's size in the same way (it is a share, not a count), and its change over a short window against a longer one (`share_5d - share_60d`, or a z-score of the 5-day share against its own trailing 60-day distribution) is directly comparable to the existing temporal delta. Both markets. The IDX quantization guard (`sectors.py:67-70`) has an analogue here: one liquid bank can be a third of IDX dollar volume, so the per-sector share should be shown beside a top-name concentration figure, otherwise a single name's volume day reads as a sector flow.
- **Up/down volume by sector** (advancing-day volume minus declining-day volume as a share of sector volume, the TRIN numerator turned into a sector breadth-of-volume measure) separates "traded heavily on the way up" from "traded heavily on the way down". Dollar-volume share alone cannot; a sector being sold hard also gains share. This is the single most important complement to the dollar-volume share, and it costs one sign per bar.
- **OBV by sector** (sum of member OBVs, or OBV on the sector's dollar-volume series) is a cumulative version of the same up/down split. Cumulative series have no natural zero and are compared by slope or divergence from price, which does not sort well into a column. Prefer the up/down share over a window.
- **CMF by sector** adds the intrabar close location. It needs `high` and `low`, which the store has. On IDX, days that close at the ARA/ARB limit have `close == high` or `close == low` by construction (research note 05 §4), so the multiplier saturates at +1 or -1 on exactly the days the limit censors; treat limit-locked bars the way note 05 recommends for volatility (flag, do not trust). On US it is clean. Lower priority than the up/down share because it adds a second parameter (the 20-period sum) for a modest gain.

### 3.2 What the literature says about volume as a leading signal

Gervais, Kaniel and Mingelgrin (2001) document that "stocks experiencing unusually high (low) trading volume over a day or a week tend to appreciate (depreciate) over the course of the following month", the high-volume return premium, and attribute it to visibility rather than autocorrelation, announcements, risk or liquidity. Journal of Finance 56(3), 877-919. [Wiley DOI](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00349); [EconPapers listing](https://econpapers.repec.org/RePEc:bla:jfinan:v:56:y:2001:i:3:p:877-919). Documented from the publisher abstract; full text not fetched. This is a stock-level result over one-day and one-week volume shocks and a one-month horizon, which matches the swing horizon and suggests the short window for dollar-volume share should be about 5 sessions, not 20.

---

## 4. Breadth-based rotation

Definitions, verified by fetching the ChartSchool pages on 2026-09-16 (ChartSchool credits no original author for any of the three):

| Measure | Definition | Thresholds stated | Source |
|---|---|---|---|
| Percent above moving average | "A breadth oscillator that measures the percentage of stocks above a specific moving average." 50-day for short-to-medium term, 150 and 200-day for medium-to-long. | Bullish bias above 50%; above 70% overbought, below 30% oversold | [ChartSchool](https://chartschool.stockcharts.com/table-of-contents/market-indicators/percent-above-moving-average) |
| High-Low Index | 10-day SMA of Record High Percent = `New Highs / (New Highs + New Lows) x 100` | Above 50 bullish; above 70 "usually coincide with a strong uptrend", below 30 with a strong downtrend | [ChartSchool](https://chartschool.stockcharts.com/table-of-contents/market-indicators/high-low-index) |
| Advance-Decline Line | `AD Line (previous) + Net Advances (current)`, net advances = advancing stocks minus declining | Divergence from the index "signal a change in participation" | [ChartSchool](https://chartschool.stockcharts.com/table-of-contents/market-indicators/advance-decline-line) |

### 4.1 What breadth adds over decile share

Decile share is a **cross-sectional** count: a member is counted only if it beats 90% of the *market*. Percent-above-MA is a **within-sector, absolute** count: a member is counted if it is above its own trend, however the market is doing. The two disagree exactly when rotation is beginning:

- Early rotation in: a sector's members climb above their 20-day MA while still ranking in the middle of the market. Percent-above-20d rises; decile share is flat. This is the case the current model cannot see.
- Late-stage concentration: a sector's decile share is high on three names while the rest have fallen below their 50-day MA. Decile share says leading; percent-above-50d says narrowing. The v1 spec's own words apply, "leadership concentrates before it broadens" (`v1-spec.md` §4.4), and the pair of numbers is what distinguishes the two phases.
- The High-Low Index per sector (net 20-day or 63-day new highs) is the breakout method's natural breadth measure: the setup the detector looks for is a move to a new high out of a base (`CONTEXT.md` "Trigger", "Base"), so a sector printing many new 63-day highs is a sector where the detector will find work. Note that no 52-week high is computed anywhere today (`v2-frontend-spec.md:113`), so a 20 or 63-day high is the cheap first version.

The A-D line is the weakest of the three for this repo: it is cumulative (same sort problem as OBV) and, on a per-sector basis with 10 to 40 members, its daily net advances are dominated by quantization. Percent-above-MA and net new highs are shares over windows, which fit the board.

### 4.2 Parameters that need no new decision

The repo already has a 20-session convention for the temporal delta ("inherited from the swing horizon, not invented", `sectors.py:61-62`) and reads SMA50 in the backtest universe (`CONTEXT.md` "Stateless universe"). Percent above the 20-day and 50-day MA reuses both. The 200-day belongs to the regime block (research note 05, "What this means for the dashboard"), not to rotation.

---

## 5. Academic evidence on sector and industry momentum

Documented from publisher and repository abstracts. Full texts were not fetched today (Wiley, SSRN and the Wharton mirror refused automated access); the citations are to the journals of record.

- **Jegadeesh and Titman (1993)**, "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency", Journal of Finance 48(1), 65-91. Buying past winners and selling past losers "generate significant positive returns over 3- to 12-month holding periods"; part of the first-year return "dissipates in the following two years". [Wiley DOI](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x); [EconPapers](https://econpapers.repec.org/RePEc:bla:jfinan:v:48:y:1993:i:1:p:65-91). This is the origin of the 3 to 12 month formation and holding grid that the repo's `1m/3m/6m/12m` detection lookbacks sit on.
- **Moskowitz and Grinblatt (1999)**, "Do Industries Explain Momentum?", Journal of Finance 54(4), 1249-1290. Documents "a strong and prevalent momentum effect in industry components of stock returns which accounts for much of the individual stock momentum anomaly"; stock momentum is "significantly less profitable once we control for industry momentum", and industry momentum strategies (buy past winning industries, sell past losing) are the larger driver. [Wiley DOI](https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00146); [EconPapers](https://econpapers.repec.org/RePEc:bla:jfinan:v:54:y:1999:i:4:p:1249-1290). This is the strongest academic license for sector-level tracking in a momentum screener at all: the industry is not a tag, it is a source of the return. The paper's finding that industry momentum is profitable even at the one-month horizon (where individual stock momentum reverses) is widely cited but was **not verified from the text today**; treat it as documented, not verified.
- **Conrad and Kaul (1998)**, "An Anatomy of Trading Strategies", Review of Financial Studies 11(3), 489-519. Of 120 return-based strategies, fewer than half yield significant profits; "a momentum strategy is usually profitable at the medium (three- to 12-month) horizon", contrarian profits only at long horizons and only in 1926-1947. [OUP DOI](https://doi.org/10.1093/rfs/11.3.489); [SSRN](https://www.ssrn.com/abstract=95168). A useful counterweight: most lookback and holding combinations do *not* work, so adding a sixth lookback or a composite of the two rotation columns should be measured, not assumed.
- **Hong, Torous and Valkanov (2007)**, "Do industries lead stock markets?", Journal of Financial Economics 83(2), 367-396. "A number of U.S. industry returns can forecast the stock market" at monthly frequency, attributed to gradual information diffusion across markets. [IDEAS listing](https://ideas.repec.org/a/eee/jfinec/v83y2007i2p367-396.html); [author copy, Columbia](http://www.columbia.edu/~hh2679/industry-12-05-05.pdf) (not fetched). Relevant because it says sector rotation carries information about the index, which is the regime block's business, not the rotation board's; it argues for keeping the two separate rather than folding rotation into regime.
- **Jacobsen, Stangl and Visaltanachoti (2009)**, "Sector Rotation across the Business Cycle", SSRN 1467457. Tests the conventional "which sector leads in which phase" wisdom on 1948-2007 and finds that "even with perfect foresight and ignoring transactions costs, sector rotation generates, at best, a 2.3 percent annual outperformance". [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1467457) (returned 403 to automation today; figure taken from the SSRN abstract as indexed). This closes the door on a business-cycle phase model for this dashboard: the ceiling is small even before the phase has to be guessed.

**What the evidence supports for lookbacks and horizons:** relative momentum formed over 1 to 12 months, read at roughly monthly cadence, with a one-month holding horizon being the point at which industry momentum still pays. The repo's `1m` temporal lookback and 20-session delta are inside that range. Nothing here supports a `1w` formation window as a *strength* measure on its own; the repo already treats `1w` as "a momentum burst, not a prior move" and excludes it from the detection gate (`CONTEXT.md` "Detection gate"), which is consistent.

---

## 6. Free data that could help

### 6.1 Verified by fetching on 2026-09-16

| Source | What was tried | Result |
|---|---|---|
| Yahoo, US sector ETFs | `yfinance` history for XLK, XLF, XLE, XLV, XLI, XLY, XLP, XLU, XLB, XLRE, XLC, RSP, SPY, 3 months daily | All 13 return 64 daily bars with volume, last bar 2026-09-16. |
| Yahoo, ETF fund flows | `Ticker("XLK").info` keys containing flow/asset/nav/shares | `totalAssets` (121.4B), `netAssets`, `navPrice`, `trailingThreeMonthNavReturns`, `sharesOutstanding` (272,056,000). **No flow field.** Shares outstanding is a point value; capturing it nightly would give a creation/redemption series, which is the flow proxy. |
| Yahoo, ETF holdings | `Ticker("XLK").funds_data` | `sector_weightings` (technology 1.0) and `top_holdings` (NVDA 14.4%, AAPL 12.5%, MSFT 10.1%) work. Top holdings only, not the full list. |
| SSGA daily holdings | `curl -L` on `https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xlk.xlsx` | 301 to `https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xlk.xlsx`, then 200, 22,884 bytes, OOXML. Columns: Name, Ticker, Identifier, SEDOL, Weight, Sector, Shares Held, Local Currency; "As of 15-Sep-2026". Full constituent list per fund, daily. SSGA's sheet carries a reproduction restriction in its disclaimer text; use for computation, do not redistribute the sheet. |
| FINRA daily short-sale volume | `curl https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260915.txt` (and 20260914, 20260911, 20250915) | All 200. 12,333 lines on 2026-09-15. Layout `Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market`, e.g. `20260915|AAPL|4652486|38051|11601145|B,Q,N`. ETFs included (`XLK` present). Layout document: [FINRA file layout PDF](https://www.finra.org/sites/default/files/2021-07/DailyShortSaleVolumeFileLayout.pdf) (fetched, 200). FINRA states the files cover "short sale trades executed and reported to a TRF, the ADF, or the ORF during normal market hours", posted "no later than 6:00:00pm ET of the same day", and that short volume "is not consolidated with exchange data": [FINRA, Daily Short Sale Volume Files](https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files). US only, off-exchange only. |
| Yahoo, IDX sector indices | `yfinance` history for `IDXENERGY.JK`, `IDXBASIC.JK`, `IDXINDUST.JK`, `IDXNONCYC.JK`, `IDXCYCLIC.JK`, `IDXHEALTH.JK`, `IDXFINANCE.JK`, `IDXPROPERT.JK`, `IDXTECHNO.JK`, `IDXINFRA.JK`, `IDXTRANS.JK` (the eleven IDX-IC sector indices) | Each resolves (`quoteType INDEX`, exchange `JKT`, `shortName "IDX SEC ENERGY"` and so on) and returns **exactly one bar, today's**, on `period="1y"`, and **zero bars on `period="max"`**. Yahoo has the quote, not the history. **Unusable for rotation.** |
| Yahoo, legacy IDX sector tickers | `^JKAGRI ^JKBIND ^JKCONS ^JKFINA ^JKINFA ^JKMING ^JKMISC ^JKPROP ^JKTRAD ^JKMNFG` and guessed `^JKENER`-style names | All empty. |
| Yahoo, IDX headline indices | `^JKLQ45`, `^JKSE` | Full history (`^JKLQ45` from 1997-02-24, 7,178 bars; `^JKSE` from 1990-04-06). LQ45 is a liquidity index, not a sector. |
| Yahoo chart API direct | `curl` on `query1.finance.yahoo.com/v8/finance/chart/^JKSE` | 200 with JSON, same data as yfinance. |
| idx.co.id | `curl -A Mozilla` on `/en/market-data/stock-index/` | 403, as in research note 03. |

### 6.2 What that means

- **US**: an ETF-flow series is buildable for free by capturing `sharesOutstanding` (Yahoo) or "Shares Held" totals (SSGA sheet) nightly and differencing. It would be a new nightly capture, and the v1 spec rejected the ETF layer as a *strength* proxy (§4.4). As a *flow* check it answers a question the decile model does not ask, and it is the only true "money moved in or out" measure on this list; the rest are trading-volume proxies. It has no IDX counterpart, which is the same asymmetry ticket 07 rejected the ETF proxy for. Treat as optional and US-only, and expect a start-from-zero history.
- **US**: FINRA short volume aggregated to sector (sum of ShortVolume over members / sum of TotalVolume) is a free daily "who is leaning against this sector" number. It is off-exchange only and FINRA itself warns short volume includes offsetting trades that "will not necessarily result in an open short position". Cheap to add, easy to over-read, US only.
- **IDX**: there is **no free sector index history and no ETF layer**, so the bottom-up model is not a philosophical preference on IDX, it is the only option. Everything recommended below is bottom-up for that reason.

---

## 7. Recommendations for this repo

Three additions, in priority order. All three are computed from `bars` and `ranks` in `data/screener.duckdb`; none needs a new data source. Each is proposed as a **column on the sector board**, not as a star-score input; anything that touches the rubric goes through ADR 0005's pre-registered selection contrast, and the RS line's refusal (`backend/screener/relative_strength.py`, findings §5d) is the reminder that intuitively obvious relative-strength measures have failed that test here before.

### 7.1 Sector dollar-volume share, with an up/down split

Compute per `(market, session, sector)`:

- `dv_share_5d = sum_members sum_{last 5 sessions} close x volume / sum_universe (same)`; the 60-session version as the base rate.
- `dv_delta = dv_share_5d - dv_share_60d` in percentage points, sortable, the money-flow analogue of the temporal delta.
- `updown_5d = (advancing-day dollar volume - declining-day dollar volume) / total sector dollar volume over 5 sessions`, in [-1, 1]. Sign of the day is `close > prior close` on `adj_close`, volume from the unadjusted bar. This separates accumulation from distribution.
- A concentration figure beside each: the top member's share of the sector's 5-day dollar volume. On IDX this will often be above 50%, and the row should be marked the way `delta_low_confidence` marks the Δ20d cell today (`sectors.py:196`).

Why first: it is the only proposal that measures capital rather than returns, both markets, zero new data, and its window (5 sessions) has a direct literature anchor in the high-volume return premium (section 3.2).

What to measure before adopting: a **lead-lag study on stored history**. For every `(market, session, sector)` over the two-year rank retention, cross-correlate `dv_delta` at `t` with the change in `share(1m)` over `t` to `t+20`. If dollar-volume share leads decile share, the column earns its place as an early-warning read; if it is coincident or lagging, it is a confirmation column and should be labeled as one. The replay store cannot be re-run in place (it holds detector v1 over 505 sessions), but this study reads `ranks` and `bars` only and needs no detector run.

### 7.2 Sector breadth: percent above MA and net new highs

Compute per `(market, session, sector)`:

- `pct_above_20d`, `pct_above_50d`: share of members whose `adj_close` is above their 20 and 50 session SMA. Two numbers, thresholds from ChartSchool (50% bias, 70/30) used as display bands only, not as gates.
- `net_new_highs_20d = (members at a 20-session closing high - members at a 20-session closing low) / n`; the same at 63 sessions once the sector detail page wants it.

Why second: it is the measure that sees rotation *starting* (members lifting off their trend before they reach the top decile) and rotation *narrowing* (decile share high, percent-above-50d falling). It reuses the 20-session convention and the SMA50 the repo already reads, so it introduces no new parameter.

What to measure before adopting: the same lead-lag study as 7.1, plus one contrast that matters to the method: among detections in the replay and backtest stores, does the sector's `pct_above_20d` at detection date separate taken from not-taken (ADR 0005's instrument), or forward capture (ADR 0006's)? A positive result would make it a candidate for the sector-confirmation slot in the rubric; a null leaves it as a board column, which is enough.

### 7.3 A bottom-up rotation trajectory (the phase-2 RRG band)

Build the RRG analogue on the **share series**, not on ETF or sector-index prices:

- `ratio_t = EWM_span_10( share(1m)_t )`, then standardized across the 11 sectors on each date (z-score, or rank-normalized to a 100-centered scale to keep the familiar reading).
- `momentum_t = EWM_span_10( ratio_t - ratio_{t-5} )`, standardized the same way.
- Quadrant label from the two signs; a 15-session trail (three weeks, the spec's number).
- Both axes and the quadrant are **columns** in the companion list, sortable, because ticket 07 S3 requires rotation to be computed and sortable and a plot alone does not satisfy that.

Name it `rotation_ratio` / `rotation_momentum`; the JdK names are trademarks and the formula here is not theirs (section 2.2).

Why third: it adds trajectory to numbers the trader has already accepted, and it makes `v2-frontend-spec.md` §11.4's "two models that permanently disagree" collapse into one model with a trail, which removes a permanent disclaimer from the screen. If instead the product wants a return-based RRG (pack return vs the composite, as the spec's subtitle reads), the §4.4 rejection of index returns should be re-argued first, and the disclaimer stays.

What to measure before adopting: the EWM span and the momentum lag are two tunables the current board has none of. Pre-register one pair (10 and 5 above, both inherited from the 5-session volume window and the 20-session delta's half), and check that the quadrant label at `t` predicts the sign of `share(1m)` change over `t` to `t+20` better than the raw temporal delta does. If it does not, the trail is decoration and the sorted columns already carry the information.

### 7.4 Not recommended now

- **Business-cycle phase rotation** (the "early cycle favors X" template): ceiling of 2.3% a year with perfect foresight (section 5), and this dashboard has no macro data feed.
- **ETF-flow and FINRA short-volume series** for US: both verified free, both real "money" signals, both US-only. They break the "same measure on both markets" rule that the sector model was built on (ticket 07 S2). Record them as available; add only if a US-only band is ever accepted.
- **Sector OBV and CMF as columns**: cumulative and parameterized respectively; the up/down share in 7.1 carries the same information in a sortable form. CMF additionally saturates on IDX limit days.
- **A composite of the rotation columns**: the spec forbids it (§4.4, "No composite of the two, and no threshold on either") and Conrad and Kaul is the reason to keep forbidding it until a composite is measured.

---

## Sources

Primary, verified by fetching on 2026-09-16 unless marked:

- StockCharts ChartSchool, Relative Rotation Graphs: https://chartschool.stockcharts.com/table-of-contents/chart-analysis/chart-types/relative-rotation-graphs-rrg-charts
- StockCharts ChartSchool, RRG Relative Strength (JdK RS-Ratio and RS-Momentum): https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/rrg-relative-strength
- Optuma knowledge base, RRG Lines: https://www.optuma.com/kb/optuma/tools/rrg-tool-module/rrg-lines
- RRG Research: https://www.relativerotationgraphs.com/ (methodology page `/rrg-explained` 404)
- StockCharts ChartSchool, On Balance Volume: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/on-balance-volume-obv
- StockCharts ChartSchool, Chaikin Money Flow: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/chaikin-money-flow-cmf
- StockCharts ChartSchool, Arms Index: https://chartschool.stockcharts.com/table-of-contents/market-indicators/arms-index-trin
- StockCharts ChartSchool, Percent Above Moving Average: https://chartschool.stockcharts.com/table-of-contents/market-indicators/percent-above-moving-average
- StockCharts ChartSchool, High-Low Index: https://chartschool.stockcharts.com/table-of-contents/market-indicators/high-low-index
- StockCharts ChartSchool, Advance-Decline Line: https://chartschool.stockcharts.com/table-of-contents/market-indicators/advance-decline-line
- FINRA, Daily Short Sale Volume Files: https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files
- FINRA, Regulation SHO Daily Short Sale Volume File Layout: https://www.finra.org/sites/default/files/2021-07/DailyShortSaleVolumeFileLayout.pdf
- FINRA daily file, example: https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260915.txt
- SSGA daily holdings, XLK: https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-xlk.xlsx

Journals of record, documented from publisher or repository abstracts (full text not fetched today):

- Jegadeesh, N. and Titman, S. (1993), Journal of Finance 48(1), 65-91: https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1993.tb04702.x
- Moskowitz, T. and Grinblatt, M. (1999), Journal of Finance 54(4), 1249-1290: https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00146
- Conrad, J. and Kaul, G. (1998), Review of Financial Studies 11(3), 489-519: https://doi.org/10.1093/rfs/11.3.489
- Gervais, S., Kaniel, R. and Mingelgrin, D. (2001), Journal of Finance 56(3), 877-919: https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00349
- Hong, H., Torous, W. and Valkanov, R. (2007), Journal of Financial Economics 83(2), 367-396: https://ideas.repec.org/a/eee/jfinec/v83y2007i2p367-396.html
- Jacobsen, B., Stangl, J. and Visaltanachoti, N. (2009), SSRN 1467457: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1467457

Repo files cited: `backend/screener/sectors.py`, `backend/screener/store.py`, `backend/screener/source.py`, `backend/screener/relative_strength.py`, `CONTEXT.md`, `.scratch/screening-dashboard/v1-spec.md` §4.4, `.scratch/screening-dashboard/v2-frontend-spec.md` §4.5, §11.3, §11.4, `.scratch/screening-dashboard/issues/07-sector-theme-and-rotation-model.md`, `docs/adr/0005-what-admits-a-dimension-to-the-rubric.md`, `.scratch/screening-dashboard/research/03-sector-taxonomy.md`, `.scratch/screening-dashboard/research/05-market-regime-measurement.md`.
