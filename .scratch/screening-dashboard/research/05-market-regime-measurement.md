# 05. Market regime measurement: US vs IDX

Research note, 2026-09-16. Question: what is the correct way to measure a market regime, and should the US and IDX legs of the dashboard treat regime differently?

## Findings first

1. There is no single "correct" regime measure. Each family answers a different question (trending or chopping, calm or stressed, broad or narrow, correlated or dispersed, bull or bear). Correctness is defined by the downstream use. For a screening/momentum system the requirement is a robust, low-lag, out-of-sample-stable filter, not the best in-sample fit.
2. The academic evidence favors simple measures for that use. A 10-month (roughly 200-day) moving average filter on the index has held up out of sample across markets and a century of data [S1]. Scaling exposure by inverse recent realized variance adds value across factors [S2]. Sophisticated Markov-switching models fit history beautifully and forecast badly: a small misclassification of the next regime erases the entire advantage of knowing the true model [S5].
3. The regime *framework* transfers from the US to IDX. The *parameters, data plumbing, and caveats* do not. IDX has a lunch break and a shorter continuous session, hard daily price limits (ARA/ARB) that censor the return distribution, an asymmetric limit regime since April 2025, no implied-volatility index and no listed IHSG options to build one from, short selling that was effectively absent until September 15, 2026, and an index dominated by a handful of banks. Every volatility- or breadth-based measure needs IDX-specific calibration, and volatility lookbacks must be segmented by ARB policy era because the limit width has been changed by decree four times since 2020.
4. Concrete answer to the title question: treat both markets with the same three-signal regime block (trend vs long MA, realized-vol percentile, breadth), but compute it per market with market-specific parameters, add USD/IDR volatility as the IDX risk-off proxy in place of VIX, and mark limit-hit days as censored observations in the IDX vol estimate.

## 1. The measurement families

### Trend vs range classifiers
Question answered: is the market directional enough for momentum entries to pay?
- Index vs long moving average (200-day, or Faber's 10-month monthly-close variant). Faber's rule: long when the index closes above its 10-month SMA, out otherwise; backtested on the S&P 500 from 1900 and out of sample on twenty-plus other markets, it matched buy-and-hold returns with materially lower volatility and drawdown [S1]. This is the practical benchmark every fancier regime model has to beat.
- MA slope/stacking and ADX (Wilder 1978, *New Concepts in Technical Trading Systems*, the primary source for ADX) and the Kaufman efficiency ratio (net move over path length, from Kaufman's *Smarter Trading*) are finer-grained but add parameters. ADX lags badly at turns; the ER is fast but noisy.
- Lag characteristics: a 200-day MA confirms a bear roughly 2-4 months after the peak. That lag is the price of its robustness.

### Volatility-state measures
Question answered: how hostile is the environment right now, regardless of direction?
- Realized-vol percentile: annualized stdev of the last ~21 daily returns, ranked against a trailing window. Needs nothing but daily closes. Moreira and Muir show inverse-realized-variance position scaling raised Sharpe ratios across the market and major factors, because volatility spikes are not compensated by proportionally higher expected returns [S2]. This is the strongest academic license for a vol-based regime filter in a retail system.
- VIX and its terciles: the Cboe VIX is 30-day option-implied volatility aggregated from OTM SPX puts and calls; methodology in Cboe's own white papers [S3]. Forward-looking, zero estimation lag, US only.
- GARCH: better conditional forecasts than rolling stdev, but parameter estimation adds fragility for little filter-level gain.
- Markov regime-switching / HMM: Hamilton (1989) is the original formulation, an autoregression whose parameters switch with an unobserved discrete Markov state [S4]. Ang and Timmermann's review confirms regimes in means, volatilities, and correlations are real features of return data [S6]. The pitfalls are equally well documented: Dacco and Satchell show out-of-sample forecasting gains evaporate under small state-classification errors [S5]; smoothed state probabilities use the full sample and are look-ahead-biased (only filtered probabilities are usable in a backtest); regime count is a researcher choice that standard likelihood tests handle awkwardly; and parameters are unstable when refit on expanding windows. Verdict for this project: a research tool, not a production filter.

### Breadth
Question answered: is the move carried by the market or by a few index heavyweights?
- Percent of stocks above their 200-day MA, advance-decline lines, net new highs/lows. Practitioner measures without a single canonical academic source; their value here is mechanical, and for IDX they are the direct antidote to index concentration (section 3). They require constituent-level prices, which is the binding constraint on a free data budget.

### Correlation / dispersion
Question answered: is this a stock picker's market or a single-factor market? Average pairwise correlation of constituents spikes in stress. Useful, but computationally the most expensive per unit of decision value for a screener; lowest priority.

### Drawdown-based bull/bear dating
Question answered: which half of the cycle are we in, for labeling and reporting? Pagan and Sossounov give the standard turning-point algorithm for dating bull and bear phases from the price series alone [S7]. Ex-post by construction (a peak is only confirmed after the subsequent trough qualifies), so it is for labeling history and evaluating the other filters, never for live signals.

## 2. "Correct" is relative to the use

An academic classifier is judged by likelihood and regime persistence. A screening-system filter is judged by whether flipping it on and off at its own signals improves the strategy out of sample, with realistic lag. Those objectives diverge: the literature above says the elaborate end of the spectrum wins the first contest and loses the second [S1][S5]. For this dashboard the defensible position is: simple measures as the production regime block, anything Markovian confined to offline research.

## 3. Structural differences, US vs IDX

### Sessions and hours
- US: continuous 09:30-16:00 ET, no lunch break, Monday-Friday (NYSE/Nasdaq core session; the LULD plan documents assume it [S8]).
- IDX: two sessions with a lunch break, normalized on April 3, 2023. Monday-Thursday: Session I 09:00-12:00, Session II 13:30-15:49:59 WIB. Friday: Session I 09:00-11:30, Session II 14:00-15:49:59 [S9]. NOT VERIFIED AGAINST PRIMARY: idx.co.id returns HTTP 403 to automated fetches, so the session table above rests on Indonesian financial press reporting the normalization decree, not the exchange page itself. Pre-opening/pre-closing auction minute marks are similarly unverified here; confirm on idx.co.id manually before hardcoding anything finer than the session boundaries.
- Consequence: daily bars are comparable, but any intraday logic (gap measures, first-hour range) needs separate handling per market, and Friday IDX bars have a different session shape than Monday-Thursday bars.

### Price limits
- US has no daily price limit. It has LULD: rolling 5-minute reference-price bands of 5% (Tier 1: S&P 500, Russell 1000, some ETPs) or 10% (Tier 2), doubled in the first 15 and last 25 minutes, with a 5-minute pause when the band binds for 15 seconds [S8]. LULD pauses trading briefly; it does not cap the daily move.
- IDX has hard daily limits with order rejection. Current regular-market rules (effective April 8, 2025, BEI decree Kep-00003/BEI/04-2025): ARA (upside) tiered at 35% (Rp50-200), 25% (>Rp200-5,000), 20% (>Rp5,000); ARB (downside) a flat 15% across all tiers, so the regime is asymmetric [S10][S11]. History matters for backtests: 7% flat ARB during the pandemic era (2020 to June 2023), 15% flat from June 5, 2023, symmetric-with-ARA from September 4, 2023 (Kep-00055/BEI/03-2023), then back to flat 15% ARB in April 2025 [S11][S12]. The full-call-auction watchlist board uses its own 10% symmetric band (Rp1 moves for stocks Rp1-10) [S10]. NOT VERIFIED AGAINST PRIMARY: the decree PDFs live on idx.co.id behind the same 403; percentages above are triangulated from multiple broker and press sources that quote the decree numbers. No source found showing a reversion after April 2025, but re-check before shipping constants; this parameter has changed four times in six years.

### Circuit breakers
- US market-wide: 7% / 13% / 20% single-day declines in the S&P 500; Levels 1-2 give a 15-minute halt, Level 3 closes the day [S13].
- IDX market-wide, revised April 8, 2025 (Kep-00002/BEI/04-2025): IHSG down more than 8% triggers a 30-minute halt, 15% a further 30-minute halt, 20% suspension to end of session or beyond with OJK approval. The previous 5/10/15 ladder actually fired on March 18, 2025 [S14][S15].

### Tick sizes
- US: $0.01 minimum quoting increment for stocks at or above $1 (Reg NMS Rule 612). The SEC's September 2024 amendments add a $0.005 tick for tick-constrained stocks; compliance was set for November 2025, was pushed to November 2026, and the D.C. Circuit upheld the rule in October 2025 [S16][S17]. So through late 2026 the operative US tick is still a penny.
- IDX: fractional ladder under Rule II-A (2016): Rp1 below Rp200, Rp2 for Rp200-500, Rp5 for Rp500-2,000, Rp10 for Rp2,000-5,000, Rp25 at Rp5,000 and above [S18]. Relative tick is far coarser than the US at the low end (a Rp50 stock moves in 2% increments), which fattens measured daily volatility of cheap IDX stocks purely mechanically.

### Volatility instruments
- US: VIX, published by Cboe from SPX option prices [S3], free daily history via Cboe or FRED (series VIXCLS).
- IDX: no implied-volatility index exists for the IHSG, and none can be built, because there are no listed IHSG options; IDX derivatives are limited to LQ45 and IDX30 futures with thin volume [S19]. Any IDX volatility state must come from realized measures.

### Short selling
- US: shorting is routine under Reg SHO; bear moves incorporate short-seller price discovery.
- IDX: exchange-regulated short selling only relaunched on September 15, 2026, after repeated OJK-ordered postponements (September 2025, March 2026), phased in with an eligible list (~243 securities in the 2025 draft) and initial restrictions on participants [S20]. For the entire history a backtest will train on, IDX downside price discovery was muted: declines proceed through bid withdrawal into the ARB, producing the characteristic multi-day limit-down staircases instead of single-day repricing.

### Concentration and foreign flows
- IHSG is heavyweight-dominated: BBCA alone was about 10% of total IDX market cap in September 2024, and the top five banks together roughly 19% [S21]. Index-level trend measures on the IHSG partly measure four banks; breadth is not a nice-to-have for IDX, it is the correction term.
- Foreign flows and the rupiah are coupled to the index: studies on Indonesian data find exchange-rate and foreign-flow effects on the IHSG at daily frequency [S22]. USD/IDR volatility is therefore a legitimate risk-off proxy where VIX does not exist.

### Free-tier data
- US: Yahoo Finance daily and intraday index/stock data; VIX history free (Cboe, FRED). Breadth for a custom universe must be computed from constituent downloads.
- IDX: Yahoo covers ^JKSE and .JK tickers at daily OHLCV (verified in this project's own pipelines; Yahoo's sustained rate limit refills in about a minute). There is no free intraday breadth feed for IDX; IDX publishes daily statistics on idx.co.id but the site blocks automated fetch, so breadth must be computed from constituent daily closes pulled through Yahoo.

## 4. Price limits bias the statistics

This deserves its own flag because it silently corrupts the IDX volatility inputs.

- Censoring: on a limit-hit day the observed return is the limit, not the equilibrium move. Sample stdev computed over such days understates true volatility exactly when volatility is highest, and the truncation is asymmetric under the current 35/25/20 ARA vs flat 15% ARB regime: crash days are clipped harder than melt-up days [S10].
- Spillover and delayed discovery: the canonical study, Kim and Rhee on Tokyo price limits, finds volatility spills into subsequent days, price discovery is delayed past the limit day, and trading is interfered with; all three effects argue limits move variance across days rather than removing it [S23]. Mechanically this induces positive autocorrelation in IDX daily returns around limit events (continuation into the next day), which flatters naive momentum backtests on exactly the names ARA/ARB touches most.
- Policy non-stationarity: the ARB width was 7%, then 15%, then symmetric up to 35%, then 15% again, by decree [S11][S12]. A rolling realized-vol percentile that spans a policy change compares returns generated under different truncation rules. Any IDX vol-percentile lookback must either stay inside one policy era or carry era boundary dates (2023-06-05, 2023-09-04, 2025-04-08) as metadata.

## 5. Should we treat the markets differently?

Same framework, different calibration and plumbing.

Transfers as-is: index-vs-200-day-MA trend state (the Faber result was explicitly validated out of sample on foreign markets [S1]); drawdown-based cycle labeling [S7]; the general logic of realized-vol percentile filters [S2].

Needs recalibration for IDX: realized-vol percentiles (era-segmented per section 4, and computed on ^JKSE whose vol level differs from SPX); anything using daily range or intraday structure (lunch break, Friday schedule); momentum/autocorrelation assumptions on names near their limits; breadth (mandatory rather than optional, because of bank concentration [S21], and computed over LQ45 or IDX30 constituents to keep the free-tier download count sane).

Unavailable for IDX, with substitutes: VIX-style implied vol (no options market [S19]); substitute a two-legged proxy of 21-day realized vol on ^JKSE plus 21-day realized vol on USD/IDR (Yahoo ticker IDR=X), the latter justified by the documented flow/currency coupling [S22]. Short-interest-based signals have no IDX history; the short-selling relaunch is one day old as of this note [S20].

## What this means for the dashboard

Compute one regime block per market, three signals plus a composite, all from free daily data:

US block:
- Trend: S&P 500 close vs 200-day SMA (or 10-month SMA on monthly closes, per Faber [S1]). Yahoo ^GSPC.
- Volatility: 21-day realized vol of ^GSPC, percentile over a 3-year window; plus VIX level bucketed into terciles over the same window (FRED VIXCLS). Risk-off when realized-vol percentile > 80 or VIX in top tercile.
- Breadth: % of the dashboard's own screened universe above its 200-day MA; thin regime when < 40% while the index trend is still up.

IDX block:
- Trend: ^JKSE close vs 200-day SMA, same rule. Do not shorten the MA to "adapt" to IDX; the lag is the feature.
- Volatility: 21-day realized vol of ^JKSE, percentile computed within the current ARB policy era only (era start 2025-04-08; store era boundaries as config, re-verify on idx.co.id when touched). Second leg: 21-day realized vol of IDR=X as the risk-off proxy standing in for VIX.
- Breadth: % of LQ45 (or IDX30) constituents above their 200-day MA, from Yahoo .JK daily closes; ~45 tickers stays well inside the rate limit. This is the guard against a four-bank rally reading as a healthy market [S21].
- Censoring flag: mark any .JK daily bar whose close sits on its ARA/ARB boundary (reconstruct the boundary from the price-tier table [S10]); exclude or winsorize such days when estimating per-stock vol, and treat limit-locked closes as "no fill possible" in backtests.

Do not build: an HMM/Markov-switching regime filter in production [S5]; a synthetic IDX implied-vol index; correlation-regime machinery (revisit only if the composite proves insufficient).

Re-verify by hand on idx.co.id (blocked to automation, HTTP 403): current ARA/ARB table, session times, halt thresholds. All three have changed by decree since 2023 and the April 2025 asymmetric-ARB state is the latest change this research could confirm.

## Sources

- [S1] Faber, M. (2007), "A Quantitative Approach to Tactical Asset Allocation", Journal of Wealth Management. SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=962461 (author's copy: https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf)
- [S2] Moreira, A. and Muir, T. (2017), "Volatility-Managed Portfolios", Journal of Finance 72(4), 1611-1644. https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12513
- [S3] Cboe volatility index methodology white papers: https://cdn.cboe.com/api/global/us_indices/governance/Volatility_Index_Methodology_Selected_Broad_Based_Index_Equity_and_ETF_Volatility_Indices.pdf
- [S4] Hamilton, J.D. (1989), "A New Approach to the Economic Analysis of Nonstationary Time Series and the Business Cycle", Econometrica 57, 357-384. https://www.econometricsociety.org/publications/econometrica/1989/03/01/new-approach-economic-analysis-nonstationary-time-series-and
- [S5] Dacco, R. and Satchell, S. (1999), "Why do regime-switching models forecast so badly?", Journal of Forecasting 18(1), 1-16. https://onlinelibrary.wiley.com/doi/abs/10.1002/(SICI)1099-131X(199901)18:1%3C1::AID-FOR685%3E3.0.CO;2-B
- [S6] Ang, A. and Timmermann, A. (2012), "Regime Changes and Financial Markets", Annual Review of Financial Economics 4, 313-337. https://www.annualreviews.org/doi/10.1146/annurev-financial-110311-101808
- [S7] Pagan, A.R. and Sossounov, K.A. (2003), "A Simple Framework for Analysing Bull and Bear Markets", Journal of Applied Econometrics 18(1), 23-46. https://onlinelibrary.wiley.com/doi/abs/10.1002/jae.664
- [S8] Nasdaq LULD FAQ (plan tiers, band percentages, pause mechanics): https://nasdaqtrader.com/content/MarketRegulation/LULD_FAQ.pdf
- [S9] IDX trading-hours normalization effective 2023-04-03, incl. Friday schedule: https://market.bisnis.com/read/20230330/7/1642329/sah-bursa-normalisasi-jam-perdagangan-mulai-3-april-2023 and https://www.bcasekuritas.co.id/help/faq/exchange-trading-hours
- [S10] Current ARA/ARB table citing Kep-00003/BEI/04-2025: https://snips.stockbit.com/investasi/ara-dan-arb-saham-arti-auto-reject-atas-dan-bawah-serta-batasannya-di-bei
- [S11] ARB reset to flat 15% effective 2025-04-08: https://www.metrotvnews.com/read/NOlCAaM6-bei-revisi-batas-auto-rejection-bawah-jadi-15-persen-ini-penjelasan-rinciannya
- [S12] 2023 normalization timeline (7% to 15% June 2023; symmetric from 2023-09-04, Kep-00055/BEI/03-2023): https://databoks.katadata.co.id/en/finance/statistics/2710e31ce226ba1/this-is-the-latest-2023-stock-auto-rejection-limit and https://aei.or.id/en/press-release/understanding-auto-rejection-in-the-indonesia-stock-exchange-mechanisms-and-post-pandemic-adjustments
- [S13] US market-wide circuit breakers 7/13/20%: https://www.investor.gov/introduction-investing/investing-basics/glossary/stock-market-circuit-breakers
- [S14] IDX halt thresholds raised to 8/15/20% (Kep-00002/BEI/04-2025): https://www.idnfinancials.com/news/53658/why-did-idx-and-ojk-raise-trading-halt-limit-to-8
- [S15] March 18, 2025 halt at the old 5% threshold: https://indonesiabusinesspost.com/3949/markets-and-finance/analyst-expounds-trading-halt-phenomenon-at-idx-ihsg-crash-on-tuesday (IDX's own press release https://www.idx.co.id/en/news/press-release/2544 blocks automated fetch)
- [S16] SEC Rule 612 amendments adopted 2024-09-18 (half-penny tick): https://www.sidley.com/en/insights/newsupdates/2024/10/sec-adopts-rules-modifying-minimum-pricing-increments-access-fee-caps-and-order-transparency
- [S17] Compliance postponed to November 2026; D.C. Circuit upheld the rule 2025-10-14: https://www.sidley.com/en/insights/newsupdates/2025/10/dc-circuit-upholds-sec-tick-size-fee-cap-rule
- [S18] IDX tick-size ladder, Rule II-A amendment PDF: https://www.idx.co.id/media/9410/perubahan_peraturan_ii_a_perdagangan_efek_bersifat_ekuitas.pdf (also https://www.nhis.co.id/fraksi-harga-saham/)
- [S19] IDX derivatives page (LQ45/IDX30 futures, no IHSG options): https://www.idx.co.id/en/products/derivatives
- [S20] IDX short-selling relaunch 2026-09-15 after postponements: https://www.thejakartapost.com/business/2026/09/15/idx-launches-short-selling-scheme-after-long-delay and https://www.idnfinancials.com/news/57459/indonesia-stock-exchange-delays-short-selling-again-until-next-year
- [S21] Market-cap concentration (BBCA ~10% of IDX cap, Sept 2024; top-5 banks ~19%): https://databoks.katadata.co.id/en/consumer-services/statistics/6708f327e350a/top-10-market-capitalization-emitents-in-indonesia-september-2024 and https://sectors.app/indonesia/banks
- [S22] Danila, N. et al. (2023), "Do Foreign Fund Flows Influence the Stock Market Index? Evidence From Indonesia", SAGE Open: https://journals.sagepub.com/doi/full/10.1177/21582440231201485
- [S23] Kim, K.A. and Rhee, S.G. (1997), "Price Limit Performance: Evidence from the Tokyo Stock Exchange", Journal of Finance 52(2), 885-901. https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.1997.tb04827.x

Verification notes: idx.co.id returned HTTP 403 to every automated fetch attempted for this note (press release 2544, trading-hours page), so IDX-rule claims are triangulated from Indonesian broker and financial-press sources that cite the decree numbers, and are marked accordingly in the text. ARA/ARB and halt thresholds should be re-checked manually before any constant is hardcoded. No post-April-2025 change to the flat 15% ARB was found as of 2026-09-16, but the short-selling relaunch dated 2026-09-15 shows this rulebook is actively moving.
