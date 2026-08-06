# q-scanner-v2 — What It Computes Behind The Screens

Research note for issue #54. A **fact sheet**, not a design: for each concept q-scanner-v2
serves that this backend has no equivalent of, it states what the concept means, what it is
computed from, what history it needs, and what it costs.

Sources are primary throughout: the q-scanner-v2 source tree and its own docs. Paths written
`qscan/...`, `docs/...`, `web/...` are relative to `/Users/ajitimur/Projects/q-scanner-v2`
(read-only — nothing was lifted). Paths written `backend/screener/...` are this repo.

Where q-scanner has its own words for a term, they are quoted from `docs/glossary.md` or the
ADRs rather than paraphrased.

---

## 0. The three populations everything is measured against

Nothing below is interpretable without knowing which denominator it used. q-scanner names
three and refuses to mix them (`docs/glossary.md:6-17`):

| Term | Definition (glossary's words) | Computed in |
|---|---|---|
| **universe** | "Every ticker listed in `data/universe_<market>.txt` that has a cached frame." | `qscan/scan/panel.py:76-83` |
| **stale** | "Last bar is more than 7 calendar days before `as_of`, where `as_of` is the panel's own latest bar — not wall-clock." | `qscan/scan/panel.py:23-33` |
| **live** | universe minus stale | `qscan/scan/panel.py:100` |
| **gated** | "Passes the scanner's tradability gates (price, liquidity, ADR). The denominator for the **leaders** tables." | `qscan/scan/panel.py:102-106` |
| **liquid** | "Trailing-63-bar *median* daily value traded ≥ `SectorConfig.liq_floor`. The denominator for RRG **pack** membership. Distinct from *gated*." | `qscan/scan/sectors.py:169-184` |

`gated` in code (`panel.py:102-106`) is exactly:

```
live  &  dollar_vol_med >= profile.min_dollar_volume  &  adr_pct >= 4.0
```

where `dollar_vol_med` is the median of `close × volume` over the last 30 bars
(`panel.py:58-60`, window `indicators.DOLLAR_VOL_WINDOW = 30`) and `adr_pct` is the mean of
`high/low − 1` over the last 20 bars × 100 (`panel.py:54-56`; the TradingView ADR definition,
`qscan/indicators.py:28-29`).

> **Gap note.** This backend has no `gated` set. Its analogue is the **decile gate** — the
> union of five per-lookback top deciles (`backend/screener/ranks.py:103-107`) — which is a
> *momentum* filter, not a tradability one. It applies no liquidity or ADR floor at the
> universe level at all. Every q-scanner percentage below ("top 1% of gainers") is taken over
> a tradability-filtered denominator, and would mean something different over this backend's.

The panel is built by taking a **last-bar snapshot per ticker on that ticker's own contiguous
series**, then ranking only the final numbers cross-sectionally — deliberately, because "IDX
names trade sparsely; a union-date wide frame would poison rolling windows with NaNs"
(`qscan/scan/panel.py:1-6`).

---

## 1. `/api/setups` — the pattern verdict and its entry arithmetic

### 1.1 `verdict`

**What it means.** One of three states (`qscan/pattern/types.py:11-14`):

| Verdict | Meaning |
|---|---|
| `READY` | The name is in a valid, tight base with a drawable trigger and stop — tradeable tonight. |
| `NEEDS_MORE_TIME` | The structure is real but immature: base too short, cluster not tight yet, or price not yet caught up to the 10/20-day. |
| `NO_SETUP` | Failed a hard gate — too slow, backside, no prior move, barcode, or no drawable line. |

The distinction between the second and third is load-bearing: `NEEDS_MORE_TIME` names come
back tomorrow; `NO_SETUP` names (notably barcode, `engine.py:126-133`) are "wide and loose,
skip permanently".

**Computed from.** `detect_pattern` (`qscan/pattern/engine.py:27-243`) — a pure,
point-in-time function over one enriched OHLCV frame plus an optional cross-sectional
`TickerContext`. Eight steps, each of which can terminate the verdict:

| Step | Test | Fails to | Source |
|---|---|---|---|
| 0 | ≥ `min_bars` (60) bars of history | `NO_SETUP` | `engine.py:41-42` |
| 0 | `adr_pct ≥ 4.0` — "slow stock, no edge" | `NO_SETUP` | `engine.py:47-49` |
| 0 | not backside: reject `close < sma50` while `sma50` declining; reject `sma10 < sma20` with both declining | `NO_SETUP` | `engine.py:52-62` |
| 1 | prior move: best low→high run-up over windows (21, 42, 63, 126) must clear a gate | `NO_SETUP` | `engine.py:68-85`, `qscan/pattern/move.py:20-35` |
| 2 | base window = bars since the move high, re-anchored if > 45; needs ≥ 3 bars | `NEEDS_MORE_TIME` | `engine.py:88-99` |
| 3 | a tight 3–7 bar cluster spanning ≤ `1.5 × ADR`, sitting on a rising MA; plus a "caught-up" test (close within 1×ADR of SMA10 and 2×ADR of SMA20) | `NEEDS_MORE_TIME` | `engine.py:113-146`, `qscan/pattern/cluster.py:45-90` |
| 3b | **barcode**: over a fixed trailing 15 bars, contraction ratio ≥ 0.90 *and* flip rate ≥ 0.55 | `NO_SETUP` (permanent) | `engine.py:119-133` |
| 4 | an upper line anchored at the cluster's max high and extrapolated *backwards*, with ≥ 2 touches within `0.35×ADR` and bounded overshoot; fitted by a 200-step slope grid search with asymmetric loss (over-weight 3, under-weight 1) | `NEEDS_MORE_TIME` if base < 10 bars, else `NO_SETUP` | `engine.py:150-167`, `qscan/pattern/lines.py`, params at `qscan/pattern/params.py:38-44` |
| 5 | higher lows on the lower rail, ≤ 1 violation within `0.25×ADR` tolerance | `NO_SETUP` | `engine.py:169-177` |
| 6 | contraction + volume dry-up — **scored, never gated** | — | `engine.py:179-190` |
| 7 | entry feasibility → `trigger`, `stop`, `risk_adr`, `entry_quality` | — | `engine.py:192-206` |
| 8 | star rubric | — | `engine.py:208-221`, `qscan/pattern/verdict.py` |

The prior-move gate (step 1) is the one step that is **not** computable from the chart alone.
With cross-sectional context it is `move_pctile ≥ 90` (`params.py:20`); without it, an
absolute fallback of +25% (1m windows) / +40% (longer) (`engine.py:71-83`, `params.py:21-22`).

**History needed.** ≥ 60 daily bars hard minimum; ≥ 127 to let the longest prior-move window
(126) evaluate; `indicators.enrich` computes SMA200 so a full frame is normally passed. Own
symbol only. Daily bars only — nothing intraday anywhere in q-scanner.

**Cost.** Per-symbol and pure — no cross-sectional pass, no prior session. The heaviest inner
loop is the 200-step slope grid over a ≤ 45-bar base (`params.py:39`), i.e. trivial. The
pipeline bounds the work by only running it on **candidates**: gated names with
`move_pctile ≥ 85`, unioned with every leader that is also gated
(`qscan/scan/pipeline.py:18, 49-56`).

> **Gap note.** This backend already computes an equivalent detection (base, cluster,
> envelope, trigger, stop, `line_ok`) in `backend/screener/detection.py` and persists it in a
> `detections` table (`backend/screener/store.py:122-156`). What it does **not** produce is a
> *verdict*: detection either emits a row or it doesn't. There is no `NEEDS_MORE_TIME`
> state — the "structure is real but early" population is silently absent rather than named.
> Nor is `line_ok` a verdict: by design it is "a verdict on the fit's quality, NOT a gate"
> and demotes a row in the sort only (`backend/screener/detection.py:128`,
> `backend/screener/candidates.py:100-102`).

### 1.2 `entry_quality`

**What it means.** Two values, `"ok"` and `"late_stop_wide"` (`qscan/pattern/types.py:61`).
It answers "is this entry still affordable, or did I miss it?" — a wide cluster means the
stop is far from the trigger, so a 1R position is too small to be worth taking.

**Computed from.** One comparison (`engine.py:200-201`):

```
risk_adr      = (trigger − stop) / adr_abs
entry_quality = "ok" if risk_adr <= 1.0 else "late_stop_wide"
```

`adr_abs = adr_pct / 100 × close` (`engine.py:50`); the threshold is
`params.max_stop_adr = 1.0` (`params.py:60`).

**History needed.** Nothing beyond what the verdict already needed (20 bars for ADR, plus the
cluster).

**Cost.** Free — a division and a comparison on values step 7 already produced.

> **Gap note.** This backend computes the same quantity under a different name and a
> different normalisation: `stopw_adr = stop / trigger / adr` (`detection.py:361`) — the stop
> width as a *fraction of price* divided by ADR *as a fraction*, versus q-scanner's price
> difference divided by ADR *in price units*. Algebraically these agree
> (`(t−s)/(adr·c) ≈ (t−s)/t/adr` when `close ≈ trigger`), and the same 1.0 threshold is
> already applied under the name `AFFORDABLE_ADR` (`backend/screener/candidates.py:48`,
> `Candidate.affordable`). The difference is presentational: q-scanner flags the *failures*
> (`late_stop_wide`), this backend flags the *passes* (`affordable`) — deliberately, because
> "~92% of the nightly list carries a cluster-low stop wider than §7's 1×ADR cap (median row
> 1.28×)" (`backend/screener/candidates.py:21-25`).

### 1.3 `trigger_price` / `stop_price` / `risk_adr`

**What they mean.** The breakout price to buy at, the cluster low to stop out at, and the
distance between them measured in average daily ranges (the position-sizing unit).

**Computed from** (`engine.py:192-200`):

```
trigger  = max( upper_line.value_at(as_of + 1), cluster.high )
stop     = cluster.low
risk_adr = (trigger − stop) / adr_abs
```

The `max` clamp is documented as load-bearing: the anchored upper line only descends, so in a
steep flag it projects *below* the cluster low, "which would put the trigger under the stop
(negative risk, nonsensical sizing)" (`engine.py:193-197`).

**History needed / cost.** Same as the verdict; free once the cluster and line exist.

> **Gap note.** This backend has both, and resolves the same clamp more strongly: `trigger =
> cluster_high` **by identity**, with the note "the clamp is dead"
> (`backend/screener/detection.py:359`). It also operates on the **unadjusted** OHLC series
> because "the trigger and stop are real prices" (`detection.py:40`), where q-scanner runs the
> pattern engine on the enriched frame whose SMAs are on raw `close`
> (`qscan/indicators.py:50-58`) while returns use `adjusted_close`. **This is not a gap.**

### 1.4 `move_pctile`

**What it means.** Where this name's prior move ranks against every other live name — the
cross-sectional form of "is this a momentum leader". It is the only cross-sectional input the
pure pattern engine accepts (`qscan/pattern/params.py:70-76`).

**Computed from** (`qscan/scan/panel.py:108-112`):

```
move_pctile[t] = max over c in {1m, 3m, 6m} of  percentile_rank( ret_c , over live names )
```

i.e. three separate cross-sectional percentile ranks (pandas `rank(pct=True) × 100`, average
method on ties), then the **best of the three** per name. Returns are simple
`adjusted_close` ratios over 21 / 63 / 126 bars (`panel.py:63-66`,
`qscan/indicators.py:17-25`).

Two thresholds consume it: `CANDIDATE_MOVE_PCTILE = 85` decides who gets a pattern evaluation
at all (`pipeline.py:18, 53`), and `move_pctile_min = 90` is the gate inside step 1
(`params.py:20`, `engine.py:72-73`). In the star rubric it scores as a linear ramp from 75
(zero) to 90 (full) (`qscan/pattern/verdict.py:59-62`).

**History needed.** 127 bars per symbol (for the 6m return), over the whole live universe.
Daily. No index needed.

**Cost.** One cross-sectional pass over the universe — cheap, but *not* per-symbol
computable. Three sorts of N floats.

> **Gap note.** This backend's `ranks` table already carries a per-lookback percentile for
> every universe member (`backend/screener/ranks.py:66-85`), so the raw material exists. Two
> differences of substance: (a) the percentile is an **empirical CDF** (`bisect_right / n`,
> `ranks.py:57-63`) not pandas' average-tie rank, so ties resolve upward rather than to the
> midpoint; (b) the gate is the **union of five top deciles, any-of** — explicitly *not* a
> composite, and measured to pass ~29% of the universe (`ranks.py:19-24`, `103-107`) — where
> q-scanner takes the *max of three* percentiles and gates at 85/90. These are different
> quantities and would not produce the same candidate set.

---

## 2. `/api/leaders` — tiers, cutoffs, `rs_pctile`

Governed by `docs/adr/0003-leaders-percentile-tiers.md` (ACCEPTED, option C).

### 2.1 `tier` (percentile band 1 / 2 / 3)

**What it means.** Glossary: "Which percentile band a name sits in: 1, 2, or 3. `ceil(n × f)`
names per band over the gated denominator" (`docs/glossary.md:47`). The method's own
definition of a momentum leader is "a stock in the **top 1–2% of gainers** over some
lookback" (`docs/glossary.md:45`); the table shows the top 3% so the 1% cohort is "visible
inside the wider list rather than hidden behind a single cut"
(`qscan/scan/leaders.py:4-6`).

**Computed from** (`qscan/scan/leaders.py:71-90`):

1. `valid = metrics.loc[gated, ret_col].dropna().sort_values(descending)`; `n = len(valid)`.
   Names with a null return for that lookback **leave the denominator** rather than counting
   as losers (ADR-0003 Q8, `docs/adr/0003:52-54`).
2. Band sizes `counts = [ceil(n × f) for f in (0.01, 0.02, 0.03)]`, implemented as
   `max(-(-n × round(f×100) // 100), 1)` — integer ceiling, floored at 1 so "a band is never
   empty while the universe is non-empty" (`leaders.py:54-60`).
3. `tier_of(rank)` returns the first band whose count the 1-indexed rank fits inside, else
   `None` (`leaders.py:63-68`).
4. Rows shown = `min(max(counts[-1], CONTEXT_ROWS=10), n)`. Rows past the 3% band are
   **context rows** carrying `tier = None`, rendered "–", "never badged as a leader"
   (`docs/glossary.md:48`, `leaders.py:78-82`).

The `tier` column is deliberately object dtype, not the int/None mix pandas coerces to
float+NaN, so SQLite and JSON can distinguish "outside the bands" from a band number
(`leaders.py:47-49`, ADR-0003 consequences).

**Lookbacks.** `1m, 3m, 6m, 12m, 18m, 24m` = 21 / 63 / 126 / 252 / 378 / 504 bars
(`leaders.py:24`, `qscan/indicators.py:17-25`).

**`5d_thrust` is not tiered.** It is a **threshold** scan — gated names with `ret_5d ≥ 30%`
— so "percentile tiers do not naturally apply" and every row carries `tier = None` with no
cutoffs (`docs/glossary.md:49`, `leaders.py:97-104`).

**History needed.** 505 bars per symbol to fill the 24m column; the universe's gated subset.
Daily. Own symbol only.

**Cost.** One sort per lookback over the gated universe (six sorts + one threshold filter).
Trivial. No prior session. Everything it reads is already in `panel.metrics`.

### 2.2 `cutoff`

**What it means.** Glossary: "The return at a band boundary — the 1% cutoff is the return of
the last name still inside the top 1%" (`docs/glossary.md:46`). ADR-0003 calls it "the most
valuable part of the request": *"Top 1% of 3m gainers starts at +40%" vs "+180% six months
ago" is a leadership-breadth read on the market* (`docs/adr/0003:29-31`).

**Computed from** (`leaders.py:84-89`) — one array lookup per band:

```
cutoff[f] = valid.iloc[ counts[f] − 1 ]     # the return of the last name inside band f
```

Persisted per run in a `leader_cutoffs` table keyed `(run_id, lookback, tier_pct)` carrying
`cutoff_ret_pct`, `n_names` and `universe` (`qscan/scan/db.py:44-51`, `142-158`) — so the
series accrues as a regime record even though "nothing consumes the history yet"
(ADR-0003 Q10). The API returns only the current run's cutoffs
(`qscan/api/app.py:51-62`).

The denominator is exported alongside deliberately: "of 164 gated names over 1m", so it is
never implicit (ADR-0003 Q8). ADR-0003 also records an accepted flaw: the gated universe moves
nightly, so "a name can leave the top 1% with no price change because 20 names were added to
gated" (`docs/adr/0003:23-25, 84-86`).

**History / cost.** Free — three index lookups into an array the tier computation already
sorted. The only requirement is that the cutoff use the **post-`dropna()`** count as its
denominator (ADR-0003 consequences, `docs/adr/0003:75-77`).

### 2.3 `rs_pctile`

**What it means.** The name's benchmark-relative strength, ranked cross-sectionally across
live names. Ported from an earlier project (`qscan/rs.py:1-7`).

**Computed from** (`qscan/rs.py:14-28`, then `qscan/scan/panel.py:68-70, 101`):

```
weighted_perf(s) = 0.4·(s/s[−63]) + 0.2·(s/s[−126]) + 0.2·(s/s[−189]) + 0.2·(s/s[−252])
rs_score         = weighted_perf(stock_adj_close) / weighted_perf(bench_adj_close) × 100
rs_pctile        = percentile_rank(rs_score) over LIVE names × 100
```

The benchmark series is reindexed onto the stock's index and forward-filled (`rs.py:26`);
`±inf` becomes NaN. Benchmark is `^JKSE` (IDX) or `^GSPC` (US)
(`qscan/markets.py:36-62`).

**History needed.** **252 bars of the symbol and 252 bars of the market index.** This is the
longest per-symbol history any leaders-table quantity requires.

**Cost.** Per-symbol O(bars) to build the series (only the last value is used —
`panel.py:70`), plus one cross-sectional rank. Cheap, but it introduces an **index-bar
dependency** the rest of the leaders table does not have.

> **Gap note.** This backend stores index bars (`MARKET_INDEX`, `backend/screener/app.py:290`,
> `backend/screener/pipeline.py:146`) and full `period="max"` daily history for members
> (`backend/screener/source.py:363`), so `rs_pctile` is computable from data already on disk.
> It is simply never computed: nothing in `backend/screener/` divides a name's performance by
> the index's. Its boards rank on **pure return, no volatility adjustment and no
> benchmark relativisation** — an explicit choice, since "normalising by ADR replaces up to 20
> of 30 US rows and answers a question the method does not ask"
> (`backend/screener/boards.py:4-7`).

> **Gap note (tiers).** This backend's boards are a **fixed top 30** per lookback
> (`BOARD_SIZE = 30`, `backend/screener/boards.py:38`) — a constant count, not a fraction of a
> denominator. The docstring notes this is over-determined against §1's "top 1–2%" (20–39 US
> names, IDX's natural decile 29). So there is no band structure and no cutoff: a row on the
> board carries no statement about what percentile it sits at, and the return that bought
> entry is not reported. Its `k/5` breadth badge (`boards.py:19-21`, `ranks.py:88-100`) is a
> different quantity entirely — a persistence count across lookbacks, not a percentile band.

---

## 3. `/api/sector-rrg` — the relative-rotation coordinates

**This is the single most expensive thing q-scanner computes.** Governed by
`docs/adr/0001-sector-rrg-parameterization.md` (ACCEPTED) and implemented in
`qscan/scan/sectors.py:297-388`.

### 3.1 The vocabulary

| Term | Definition (glossary's words) | Source |
|---|---|---|
| **pack** | "The equal-weight index built from a sector's *liquid* members: mean of member daily returns, compounded. Not cap-weighted; deliberately the tradeable pack, not the sector's market cap." | `sectors.py:135-154` |
| **composite** | "The equal-weight average of the sector packs — the *average sector*, and the benchmark both axes are measured against. Not IHSG: an EW pack against a cap-weighted index mostly measures the size factor." | `sectors.py:340-341` |
| **RS-Ratio** (x) | "`100 + z_cross(pack/composite return over rs_window)`. The x-axis: 3-month standing among sectors, in cross-sectional σ." | `sectors.py:343-347` |
| **RS-Momentum** (y) | "`100 + z_cross(change in that measure over mom_bars)`. The y-axis: how the standing moved over the last month. A difference, not a ratio — the measure crosses zero." | `sectors.py:345-348` |
| **z_cross** | "z-score taken *across sectors within one date* (population σ), never along one sector's history. What makes two sectors' positions comparable." | `sectors.py:157-166` |
| **tail** | "The last `tail` daily (RS-Ratio, RS-Momentum) points, oldest → newest. Trajectory, not just position." | `sectors.py:364-373` |
| **rank_score** | "Mean of (pack return − composite return) over `rank_windows` (21d, 63d). In return units, so it means the same thing for every sector — this is what sorts the sector list, not last-x." | `sectors.py:187-201` |
| **breadth** | "Per-sector counts: members in the universe's top momentum decile, and % of members within `near_high_frac` of their 252-bar high." | `sectors.py:223-265` |

**Coordinates are not percentiles.** `web/src/api.ts:119` warns: "Coordinates are
cross-sectional sigma around 100, not 0-100 percentiles." ADR-0001 records that the previous
percentile-scatter widget hardcoded a 0–100 domain, and swapping the data source without
rescaling "silently squashes every sector into one pixel" (`docs/adr/0001:44-46`).

### 3.2 The full computation, in order

Parameters, all from `SectorConfig` (`sectors.py:59-82`): `rs_window=63`, `mom_bars=21`,
`smooth=5`, `tail=15`, `min_members=3`, `min_sectors=2`, `liq_window=63`,
`rank_windows=(21,63)`, `breadth_pctile=90.0`, `near_high_frac=0.85`. `liq_floor` and
`use_adjusted` come from the `MarketProfile` (`sectors.py:76-82`, `qscan/markets.py:21-24`).

1. **Calendar.** `calendar = bench_close.index` — the benchmark supplies *only* the exchange
   trading calendar, "it is not the RS denominator" (`sectors.py:309-315`). With no benchmark
   cached, the whole result is empty (`sectors.py:312-313`).

2. **Liquid universe.** For each live frame, reindex `close` and `volume` onto the calendar,
   take `median(close × volume)` over the last 63 calendar bars with no-trade bars counted as
   0, and keep it if ≥ `liq_floor` (`sectors.py:169-184`).

3. **Grouping.** Liquid ∧ live ∧ classified names grouped by sector; `Unclassified` names
   "never form a pack" (`sectors.py:282-294`, ADR-0002 Q6).

4. **Member daily returns, corp-action aware** (`sectors.py:112-132`). When
   `use_adjusted=False` (both current markets, since `^JKSE` and `^GSPC` are price indices —
   `markets.py:47, 61`) the return is the **raw** `close` pct-change, so dividends read as the
   real price drops they are — *except* on bars where the adjustment factor `adj/close` jumps
   by more than `CORP_ACTION_JUMP = 0.15`, which flags a split/rights/bonus, where the
   adjusted return is substituted instead. Deliberately narrow so "genuine ARA/ARB days are
   never touched".

5. **Pack** (`sectors.py:135-154`). Reindex each member onto the calendar, forward-fill; a
   non-trading bar contributes return 0. `ew_ret = mean over members`;
   `pack = cumprod(1 + ew_ret)`, masked NaN before the pack's first member ever traded — "a
   young sector is skipped rather than read as a flat line losing to a moving composite"
   (ADR-0001 consequences, and `test_young_pack_is_masked_not_flatlined`).

6. **Coverage.** A sector is skipped with a named reason (`no_tradeable_pack`,
   `insufficient_history`, `too_few_sectors`, `nan_in_tail`) — and the skip list is itself
   returned as signal (`qscan/api/app.py:121-148`). The history bar is
   `_min_bars = rs_window + mom_bars + tail + smooth = 104` **return** bars
   (`sectors.py:268-279`).

7. **Composite** (`sectors.py:340-341`):
   `composite = cumprod(1 + mean across packs of pack.pct_change())` — equal-weighted across
   *packs*, "so a 120-name sector does not define the yardstick a 12-name sector is judged
   against".

8. **The two axes** (`sectors.py:343-348`):

   ```
   rs        = EWM(span=5, adjust=False) of  pack / composite
   standing  = rs / rs.shift(63) − 1              # 3-month relative standing
   change    = standing − standing.shift(21)      # a DIFFERENCE, not a ROC
   x         = 100 + z_cross(standing)
   y         = 100 + z_cross(change)
   ```

   `z_cross` (`sectors.py:157-166`) subtracts the per-date mean across sectors and divides by
   the per-date **population** σ (`ddof=0`), yielding NaN where the cross-section is
   degenerate. `change` is a difference because `standing` crosses zero, "so a ratio explodes"
   (`sectors.py:345-346`).

9. **`rank_score`** (`sectors.py:187-201`) — the actual sort key, in return units:

   ```
   mean over w in (21, 63) of [ pack[-1]/pack[-1-w] − composite[-1]/composite[-1-w] ]
   ```

   Rows are sorted by this, not by last-x, because "cross-sectional sigma is
   dispersion-dependent, so in a flat tape a trivial lead still scores +2 sigma"
   (`docs/adr/0001:90-92`, `sectors.py:385-386`).

10. **Breadth overlay** (`sectors.py:350-357`, `223-265`). Computed **once per run over the
    whole liquid universe**, not per sector:

    ```
    universe_mom  = adjusted-close returns over 21 / 63 / 126 bars, per liquid name
    pct           = cross-sectional percentile rank of each of the three columns × 100
    comp[t]       = mean of the three ranks              ∈ [0, 100]
    top_decile    = { t : comp[t] >= 90 }
    ```

    Then per sector: `n_top_decile`, `top_decile_names`, and `pct_near_52w_high` = share of
    members whose last adjusted close ≥ `0.85 × max(trailing 252 adjusted closes)`, requiring
    ≥ 60 non-NaN bars to be evaluated at all (`sectors.py:242-249`).

11. **Tail.** The last 15 daily `(x, y)` points, oldest → newest; **any NaN anywhere in the
    tail drops the sector entirely** with reason `nan_in_tail` (`sectors.py:364-374`).

### 3.3 Inputs, history, cost

**History needed.** Per liquid member: enough bars to cover the pack's `104` return bars
*plus* the 63-bar liquidity window and the 252-bar 52-week high — call it **≥ 253 daily bars**
per member in practice. Plus the **benchmark's** full index, used solely as the trading
calendar. Plus a **sector classification** for every member.

**Cost — this is the expensive one, and structurally so:**

- It needs **full aligned daily return series** for every liquid name, not last-bar snapshots.
  Every other q-scanner quantity works off `panel.metrics`, one row per ticker; the RRG builds
  a `dates × members` matrix per sector and a `dates × sectors` matrix on top.
- It needs a **cross-sectional pass per date**, not once at the end: `z_cross` is applied to
  the whole `standing` and `change` frames (`sectors.py:347-348`), i.e. ~`tail + rs_window +
  mom_bars` dates × 11 sectors of mean/σ.
- The breadth overlay is a **second** whole-universe cross-sectional pass (three percentile
  ranks over every liquid name, `sectors.py:353-356`).
- `pct_near_52w_high` is a 252-bar max per member — the only rolling-window-over-long-history
  quantity in the system.
- It does **not** need the prior session's output. Everything is trailing-only, so "any
  historical as_of replays deterministically" (`sectors.py:56`).

**The classification is a data dependency, not a computation.** ADR-0002 replaced yfinance
sector labels with the official **IDX-IC** taxonomy parsed from a quarterly IDX announcement
(`Lampiran 5`), verified to partition the 912 IHSG constituents exactly with zero duplicates
(`docs/adr/0002:13-18`). Against yfinance it agrees on only ~75% of shared names, and
yfinance `Industrials` (151 names) "shatters into INDUST 44 / TRANS 34 / INFRA 31 / ENERGY 27"
— "which is the whole reason the packs read as mush" (`docs/adr/0002:19-24`). The
classification is stored as a document with an `effective_from`/`effective_to` period, and
each run records the taxonomy it used in `runs.params_json`, because "sector strings are only
comparable within a taxonomy" (`qscan/scan/pipeline.py:70-71`).

> **Gap note.** This backend has **nothing** in this area. Its sector work
> (`backend/screener/sectors.py`) is a share-of-top-decile aggregation over the same rank
> table — *"it defines no new notion of 'strong'"* (`sectors.py:4-7`) — with two rotation
> columns (`share(1w) − share(6m)` and a 20-session temporal delta, `sectors.py:18-20`). That
> is a genuinely different construction: **counts of decile members**, not an equal-weight
> price index. It never builds a pack, never computes a return series for a sector, and has no
> benchmark-relative measure at all. Its taxonomy is the 11 Morningstar **GECS** buckets from
> yfinance labels (`backend/screener/sectors.py:41-55`, `store.py:113-120`) — i.e. exactly the
> taxonomy ADR-0002 rejected for IDX, with no effective period recorded. Everything else the
> RRG needs (daily OHLCV with adjusted closes, index bars, `period="max"` history) is already
> on disk.

---

## 4. `/api/sector-members` — the drill-down

**What it means.** "Every member of one sector's tradeable pack, with each lookback's return.
All the returns ride along so the page can re-rank by lookback without a refetch"
(`qscan/api/app.py:154-162`). The pack membership here is the **RRG pack** (liquid ∧ live ∧
classified), not the gated universe.

**Per-member fields and where each comes from** (`qscan/scan/db.py:83-94, 197-219`,
`qscan/api/app.py:185-207`):

| Field | Source |
|---|---|
| `returns` for 5d/1m/3m/6m/12m/18m/24m | `panel.metrics` last-bar snapshot (`panel.py:63-66`) — 5/21/63/126/252/378/504 bars |
| `adr_pct`, `dollar_vol`, `rs_pctile`, `passes_gates` | `panel.metrics` |
| `pct_of_52w_high` | `100 × last_adj_close / max(trailing 252 adj closes)`, needs ≥ 60 non-NaN bars (`sectors.py:242-248`) |
| `momentum_pctile` | the `comp` composite: mean of the cross-sectional percentile ranks of the 21/63/126-bar adjusted returns over the **liquid universe** (`sectors.py:350-356`) |
| `top_decile` | `momentum_pctile ≥ 90` (`sectors.py:237`) |
| `tiers` (per lookback) | joined from the `leaders` table, "the `leaders` table holds only the top 3%" (`api/app.py:176-182`) |
| `verdict`, `stars` | LEFT JOIN onto `setups` for the same run (`api/app.py:169-175`) |

**`pct_of_52w_high` is the one novel quantity.** Definition, from the payload contract: "last
close as % of the trailing 252-bar high" (`web/src/api.ts:59`, `db.py:90`). Note it is
computed on **adjusted** closes reindexed to the trading calendar and forward-filled, and the
252-bar window is a bar count over the calendar, not a calendar year.

**Cost.** Essentially free *given the RRG pass*. This is explicit in the code: `breadth_stats`
returns `members_detail` carrying the same two reads per ticker "so the member table and these
aggregates can never disagree — they are the same numbers, counted once"
(`sectors.py:233-236`). Standing alone it would cost one 252-bar max per member plus the
universe-wide momentum ranking.

> **Gap note.** This backend's `/api/sectors` is a flat 11-row table
> (`backend/screener/app.py:155-188`) with no member list. There *is* an industry board
> (`industry_strengths`, `backend/screener/sectors.py:195-229`) gated at `n ≥ 10` members, but
> it aggregates rather than drills down — no per-member rows anywhere. `pct_of_52w_high` has
> no analogue in `backend/screener/` at all: nothing computes a trailing 252-bar high.
> (`backend/screener/regime.py:160-173` computes a trailing **20**-bar new high for the index
> only.) The per-member returns and ADR all exist in the rank table and bars already.

---

## 5. `/api/new-ready` — the session diff

**What it means.** "READY tickers in the latest run that were not READY in the previous run"
(`qscan/api/app.py:79-81`). The thing that turns a nightly list into a *watchlist delta*.

**Computed from** (`qscan/api/app.py:82-98`) — a set difference over persisted rows:

```
current  = { ticker : setups WHERE run_id = latest    AND verdict = 'READY' }
previous = { ticker : setups WHERE run_id = latest−1  AND verdict = 'READY' }
new_ready = sorted(current − previous)
```

"Previous run" is `latest_run(con, market, offset=1)` — runs ordered by `as_of DESC`, one row
offset (`qscan/scan/db.py:230-234`). If there is no previous run, `previous` is empty and
every READY name is new. Re-running the same night **replaces** that run rather than appending
(`db.py:132-139`), so the diff never compares a night against itself.

**History needed.** No bars at all. It needs the **prior session's persisted verdicts** — the
one quantity on this list that is a function of the artifact store rather than of price data.
The module docstring names this as the reason the store accrues: "History accrues run over
run, which makes 'new READY today' a simple diff" (`qscan/scan/db.py:1-4`).

**Cost.** Two indexed SQLite reads and a set difference. The cheapest thing in this document.

> **Gap note.** This backend can already do this. It persists dated `detections` keyed
> `(market, session, symbol)` (`backend/screener/store.py:122-156`) and exposes
> `detections_before(market, session)` (`store.py:539-551`) — the exact read the diff needs.
> It also already computes a closely related delta: the boards' `NEW` marker is per-board
> absence from last session's rank rows (`backend/screener/boards.py:96-99`), and the digest
> tracks reported breaks per session (`digest_breaks`, `store.py:158-168`). What is missing is
> only that no endpoint surfaces "detected tonight, absent last session" for the candidate
> list. **This is a plumbing gap, not a data or computation gap.**

---

## 6. `/api/regime` — `mode`, breadth, and the two slope booleans

**What it means.** "Market regime: he doesn't predict, he sizes to the environment (§10)"
(`qscan/scan/regime.py:1`).

**`mode`** — three values, from the **benchmark index alone** (`qscan/scan/regime.py:32-37`):

| Mode | Condition |
|---|---|
| `long_friendly` | `close > sma10 > sma20` **and** `sma10_slope > 0` **and** `sma20_slope > 0` |
| `do_not_swing_long` | `sma10_slope < 0` **and** `sma20_slope < 0` **and** `sma10 < sma20` |
| `choppy_reduce_size` | everything else |
| `unknown` | benchmark absent, < 26 bars, or any non-finite input (`regime.py:14-16, 25`) |

**`sma10_rising` / `sma20_rising`** — sign of `slope_pct`, which is the 5-bar percent change
of the moving average itself: `(sma / sma.shift(5) − 1) × 100`
(`qscan/indicators.py:36-38`, `SLOPE_BARS = 5`), tested as `> 0` (`regime.py:29-30`). The
payload also carries `close`, `above_sma10`, `above_sma20`, `sma10_above_sma20`
(`regime.py:26-31`) — note `web/src/api.ts:113` declares `sma20_above_sma10`, which the
backend never writes; a live payload will not have that key.

Feeds sometimes append an empty session bar with `close=NaN`, so the last **finite** close is
used rather than the last row (`regime.py:20-22`).

**`breadth_pct_above_sma20`** (`regime.py:39-55`) — "% of live universe above its 20-day":

```
for each non-stale frame with ≥ 20 bars:
    total += 1;  above += (close[-1] > mean(close[-20:]))
breadth_pct_above_sma20 = round(above / total × 100, 1)
```

Note it is computed from the **raw** `close` (not `adjusted_close`), on a plain 20-bar mean,
and the SMA is recomputed inline rather than read off `indicators.enrich` — so it is
independent of the enriched frame.

**History needed.** > 25 bars of the benchmark for `mode` (`regime.py:16`); 20 bars per
universe member for breadth. Daily. Index **and** constituents.

**Cost.** `mode` is O(1) on one index series. Breadth is one linear pass over the whole live
universe with a 20-element mean each — cheap, but a whole-universe pass. No prior session.

> **Gap note — the shapes differ, and so does the breadth number.**
>
> | | q-scanner | this backend |
> |---|---|---|
> | states | `long_friendly` / `choppy_reduce_size` / `do_not_swing_long` / `unknown` | `FRIENDLY` / `CHOPPY` / `HOSTILE` / `None` (`backend/screener/regime.py:52`) |
> | HOSTILE rule | `s10<0 ∧ s20<0 ∧ sma10<sma20` | **identical** (`backend/screener/regime.py:107`) |
> | FRIENDLY rule | `close > sma10 > sma20 ∧ both rising` | `close > both SMAs ∧ both rising` — drops the `sma10 > sma20` ordering (`backend/screener/regime.py:109`) |
> | slope | sign of 5-bar % change of the SMA | sign of `SMA[t] > SMA[t−5]` — **the same test** (`backend/screener/regime.py:42-44`) |
> | index basis | raw `close` (`enrich` uses `close`) | `adj_close` (`backend/screener/indicators.py:68-74`) |
> | breadth | share of live names with `close > SMA20` | share of names **above both SMAs with both rising** (`backend/screener/regime.py:114-140`) |
> | posture | not in the payload | `full size` / `reduced` / `sit out` (`backend/screener/regime.py:56-60`) |
>
> The two `breadth` numbers are **different quantities with the same name**. q-scanner's is a
> one-condition count (`close > SMA20`); this backend's is the per-name form of its own
> FRIENDLY condition — four conditions — and will therefore read systematically lower. Any
> comparison across the two apps is invalid. `sma10_rising` / `sma20_rising` exist internally
> in this backend (inside `_snapshot`, `backend/screener/regime.py:76-92`) but are never
> exposed in `RegimeResponse`, which carries only `state`, `posture`, `breadth`
> (`backend/screener/app.py:297-303`).

---

## 7. Summary: cost and missing inputs

### Cheap — last-bar snapshot, or one cross-sectional sort

| Concept | Cost |
|---|---|
| `tier` (bands 1/2/3) | one sort per lookback over the gated set |
| `cutoff` | three array lookups per lookback, free once sorted |
| `move_pctile` | three cross-sectional percentile ranks over live names |
| `rs_pctile` | O(bars) per symbol for the last value + one rank; **needs 252 index bars** |
| `entry_quality`, `trigger`, `stop`, `risk_adr` | free once the cluster exists |
| `new_ready` | two indexed reads + a set difference; **no bars at all** |
| regime `mode`, `sma10_rising`, `sma20_rising` | O(1) on one index series |
| regime breadth | one linear pass over the live universe, 20-bar mean each |

### Moderate — per-symbol, bounded to a candidate set

| Concept | Cost |
|---|---|
| `verdict` | pure per-symbol pattern engine; 200-step slope grid over a ≤45-bar base; run only on gated names with `move_pctile ≥ 85` ∪ leaders |
| `pct_of_52w_high` | one 252-bar max per member |

### Expensive — a `dates × members` matrix and a per-date cross-section

| Concept | Cost |
|---|---|
| `/api/sector-rrg` coordinates | full aligned daily return series for every liquid name; equal-weight pack per sector; a composite on top; EWM + two shifts; `z_cross` applied **per date** across sectors; plus a second whole-universe pass for the momentum breadth overlay. The only computation here that does not fit in `panel.metrics`. |

### Inputs this backend does not currently have

Almost everything is computable from data already on disk. Only three genuine input gaps:

1. **A sector taxonomy with an effective period.** q-scanner's IDX packs run on **IDX-IC**,
   parsed from a quarterly IDX announcement and stored as a document with
   `effective_from`/`effective_to`, with each run recording which taxonomy it used
   (`docs/adr/0002`, `qscan/scan/pipeline.py:70-71`). This backend has yfinance **GECS**
   labels keyed `(market, symbol)` with a single `as_of` stamp and no effective period
   (`backend/screener/store.py:113-120`) — ~75% agreement on IDX names, with `Industrials`
   splitting four ways. Not a computation gap: a different, better source.
2. **A tradability-gated denominator.** Every q-scanner percentage is over `gated`
   (live ∧ liquidity ∧ ADR ≥ 4). This backend applies no such universe-level filter, so
   percentile bands computed over its universe would mean something different from
   q-scanner's.
3. **18m and 24m lookbacks.** This backend's `LOOKBACKS` stop at 12m
   (`backend/screener/indicators.py:42`); q-scanner's leaders tables and sector-member rows go
   to 504 bars. `period="max"` bars are on disk, so this is a computation gap, but the rank
   table's 2-year retention window (`backend/screener/store.py:174`) is the constraint to
   check if these are ever added.

Everything else the RRG, the leaders tiers, `rs_pctile`, `pct_of_52w_high` and `new_ready`
need — daily OHLCV with adjusted closes, index bars, sector labels, dated per-session derived
rows — this backend already ingests and persists. **Nothing in q-scanner requires intraday
data, and nothing requires a data feed this backend does not already call.**
