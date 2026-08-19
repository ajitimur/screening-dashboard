# Setting the screener up in TradingView

How to reproduce this app's funnel inside TradingView, with every constant carrying the
provenance the replay study gave it. Companion file: `tradingview/qullamaggie_base.pine`.

**Read this first.** TradingView cannot do the one thing the app's funnel is built on:
a **cross-sectional percentile**. There is no "top decile of 3-month return within the
universe" filter, because the screener filters rows independently and never ranks them
against each other. Everything below is arranged around that single limitation — the
decile gate becomes a *sorted top-N cut saved into a watchlist*, and the watchlist is then
the population every later stage runs against.

Provenance for every number: `qullamaggie-method.md`, `qullamaggie-replay-findings.md`, and
`backend/screener/{universe,detection,score}.py`. Where this recipe departs from the app,
the departure is marked **DEVIATION** and carries its reason.

---

## The shape of it

Four layers, matching the app's three funnel stages plus the rubric:

| Layer | App stage | TradingView |
| --- | --- | --- |
| 1. Universe | liquidity | Stock Screener, saved as a filter preset |
| 2. Strength | decile | five sorted screens → union into one watchlist |
| 3. Setup | detection | Pine Screener over that watchlist |
| 4. Rank | star score | a Pine column, sorted descending |
| 5. Order | — | trigger + stop alert on the chart |

Layers 1–2 rebuild weekly. Layer 3 runs nightly, ~10 minutes.

---

## Layer 1 — Universe (native Stock Screener)

| Filter | Value | Provenance |
| --- | --- | --- |
| Market / Exchange | US (NYSE, Nasdaq, AMEX) | scope |
| Security type | Common stock, primary listing | `universe._EXCLUDED_INSTRUMENT` — preferreds, funds, trusts, warrants out; **ADRs stay in** |
| Volume × Price | ≥ 20M | `LIQUIDITY_FLOOR` US = $20M/day, his own stated cutoff |
| Average Volume (30 day) | ≥ 300K shares | guard: stops a one-day volume spike carrying a thin name past the dollar filter |
| **Volatility Month** | **≥ 3.5%** | the ADR floor — see below, this is the important one |

### Volatility Month *is* ADR

TradingView computes `Volatility Month = mean((high − low) / low × 100)` over the bars in
the last 30 days. The method's ADR is `SMA20(high / low − 1) × 100`. Same formula, ~21 bars
instead of 20. **Use the native field — you do not need Pine for the ADR floor.**

### But do not set that floor at 5%

The obvious move is `Volatility Month ≥ 5`, matching `ADR_MIN = 0.05`. Don't. Findings §6,
finding 2, over 649 of his real entries:

- **30.7% of his executed entries had ADR at or under 5%**
- p25 = 4.7%, median 6.1%
- the withheld tail runs all the way down to **1.4%**, not bunched just under the floor
- and critically: **the ADR hard gate rejected 0 of his entries** (§3). In the app, 5% is a
  *score point*, never a cut.

A hard 5% screen throws away nearly a third of the trades this whole system exists to find.
Set the hard cut at **3.5%** — low enough to keep the tail, high enough to drop the "1.9 ADR,
you shouldn't even be trading this thing" names — and let 5% do its real job in the rubric,
where a miss costs points, not existence.

### One thing you cannot reproduce: hysteresis

`universe.py` uses the **median** of `close × volume` over 20 bars and lets a member stay
until it drops below `0.8 ×` the floor (`HYSTERESIS_EXIT`), so membership does not flicker.
TradingView has neither the median nor the band. Consequence: names will pop in and out at
the boundary week to week. **Apply the hysteresis by hand — do not delete a watchlist name
for one soft week.** Membership is sticky; removal requires positive evidence.

Save this as a screener preset: **"US universe"**.

---

## Layer 2 — Strength: the decile gate, rebuilt as five sorted cuts

This is the expensive stage and the one worth getting right. §3: **the decile gate discards
40% of his real entries on its own**, before the detector is ever consulted — the largest
single loss in the funnel, nearly five times the liquidity stage's.

You cannot filter on percentile, so you sort and cut:

1. Start from the **US universe** preset.
2. Add the **Performance %** column for one lookback.
3. Sort descending. Select the top **N ≈ 10% of the row count** the preset returns.
4. Add the selection to a watchlist named **`Q — leaders`**.
5. Repeat for each of the five lookbacks, adding into the *same* watchlist.

### Use five lookbacks, not three

| Lookback | TradingView field |
| --- | --- |
| 1 week | Performance % 1W |
| 1 month | Performance % 1M |
| 3 months | Performance % 3M |
| 6 months | Performance % 6M |
| 12 months | Performance % 1Y |

The app's *detector* gate reads only 1m/3m/6m (`DETECTION_LOOKBACKS`). The replay measured
what that costs. Of the 263 decile misses (§3, #133):

| Bucket | Count | Share |
| --- | --- | --- |
| Coverage gap — not a universe member that session | 64 | 24.3% |
| **Recovered by widening the gate 3 → 5** | **75** | **28.5%** |
| Outside even the five-lookback union | 124 | 47.1% |

**75 of his real entries — 11.4% of all 658 replayable trades — sat inside the five-lookback
union and outside the three.** That is a width decision, not a judgement about his names, and
it is the one decile change A1 measures directly. The app holds at three because widening
there has an unmeasurable precision cost (§7: there is no control group, so no false-positive
rate). **In TradingView that argument is weaker, because you are the precision filter** — you
eyeball ~150 charts a night, and a bad name costs you ten seconds, not a bad fill. Take the
five.

The union lands at roughly **29% of the universe**, not 10% — five overlapping deciles, not
one. Expect a few hundred names; his own tradeable US universe at size was ~150.

### His own absolute scans, as a cross-check

Not percentile, so they work as plain filters — run them alongside, not instead:

- **Performance % 1W ≥ 30%** (his "up ≥30% in 5 days" scan)
- biggest gainers over 1 / 3 / 6 / 12 months — the same sorted-top-N cut
- a momentum leader is the **top 1–2% of gainers** over some lookback

---

## Layer 3 — Setup detection (Pine Screener)

Source: `tradingview/qullamaggie_base.pine`. Add it to favourites, open **Pine Screener**,
point it at the `Q — leaders` watchlist, pick that indicator.

What it computes per name, ported from `detection.py`:

| Column | Rule | Constant |
| --- | --- | --- |
| `ADR %` | `100 × (SMA20(high/low) − 1)` | — |
| `Cluster k` | largest trailing k in 3–7 bars whose range ≤ `tightMult × ADR` | `K_MIN,K_MAX = 3,7` |
| `Cluster ADR` | that window's width in ADR | `TIGHT_MULT = 1.5` |
| `Min range ADR` | tightest 3–7 window **regardless** of threshold — the §3a diagnostic | — |
| `Catch-up` | `close − SMA10 ≤ 1.0·ADR` **and** `close − SMA20 ≤ 2.0·ADR` | `CATCHUP_10, CATCHUP_20` |
| `Trigger` | the cluster's max high, **by identity** | — |
| `Dist ADR` | `(trigger − close) / ADR` — "how soon" | — |
| `Stop` | `trigger − 0.345 × ADR × trigger` | `STOP_CONVENTION_ADR` |
| `Points` / `Stars` | the v2 rubric, below | `RUBRIC_VERSION = 2` |
| `Detection` | 1 when cluster **and** catch-up **and** base ≥ 3 bars **and** ADR > 0 | — |
| `Break` | `close > trigger[1]` — today's close above yesterday's trigger | — |

Filter the screener to `Detection = 1`, sort by `Stars` descending.

### DEVIATION: cluster width 1.5 → 2.0 ADR

The app holds `TIGHT_MULT = 1.5` and §3a argues that decision at length. Read it before
overriding — the recommendation there is explicit: *leave the window unchanged.*

The measurement it rests on: `cluster` is the single largest detection miss, **171 of 278
(61.5%)**, more than `catch_up`, `base_length` and `history` combined. When the misses were
split (contradicting what the section originally predicted):

| Partition | Count | Share |
| --- | --- | --- |
| Fresh entries — *not* re-entries | 148 | 86.5% |
| **Marginal — tightest window ≤ 2.0 ADR** | **113** | **66.1%** |
| Far — genuinely in motion, no base | 58 | 33.9% |

Median tightest window: **1.85 ADR** against a 1.5 gate (p25 1.68, p75 2.13). That is the
shape of *a boundary set slightly tight*, not of names wildly in motion.

The app refuses to widen because the **calibration rule** (§7) forbids it — Tightness has
clear signal (§5b, +20.8pp, second-strongest selector), so widening it on a recall miss is
exactly the "chase recall with no measurable precision" trap.

**The rule governs the app. It does not govern your eye.** A widen that recovers 113 of his
entries at an unmeasured cost in noise is a trade the *study* cannot price — but in a manual
screen you price it visually, in seconds, per chart. So: run at **2.0**, and read
`Cluster ADR` as a quality column, not a pass/fail. Anything over 1.5 is a name you look at
twice and mostly decline. **If you find yourself declining nearly all of them, put it back
to 1.5** — that is the honest test, and it is cheap to run.

This is a deliberate departure from a documented decision, not an oversight. Do not port it
back into `detection.py`; the constant there stands on the calibration rule.

### What the Pine port cannot do

Marked in the source. Four gaps:

- **Prior move** — cross-sectional, so it is granted `true` by construction, exactly as in
  the app. The `Q — leaders` watchlist *is* that gate. §5a and §5b both find it 100% in
  every group the study can build; it is documentation, never discrimination.
- **Sector** — no sector-share data in Pine. The point is left unscored, so the automatic
  ceiling is 8 of 9 points. Add it by eye when the theme confirms.
- **Base length / prior-move peak** — the app searches windows of 21/42/63/126 bars for the
  best low→high run-up and starts the base at its peak. The Pine proxy is *bars since the
  45-bar high*, capped at `MAX_BASE_LEN = 45`. Close enough for a screen; it feeds a
  dimension weighted **×0** anyway (below), so the approximation costs nothing in the score.
- **Envelope / `line_ok`** — omitted entirely. It is not a gate in the app either (a silent
  tiebreak), and you are about to draw the line by hand.

---

## Layer 4 — Ranking: the v2 rubric

`RUBRIC_VERSION = 2`, recalibrated by PRD #138 against the measured selection contrast. Nine
points, halved to stars, range **0.5–4.5** (never 0–5 — one dimension always fires, one is
worth zero).

| Dimension | Weight | Rule | Why that weight (§5b Δ, taken vs field) |
| --- | --- | --- | --- |
| **ADR** | **×2** | `ADR ≥ 5%` | **+29.4pp — the sharpest selector in the rubric** |
| **Tightness** | **×2** | `cluster_k ≥ 5` | **+20.8pp — second sharpest** |
| MA support | ×1 | SMA20 rising, sign-only (`X[t] > X[t−5]`) | +4.3pp, inside the noise |
| Prior move | ×1 | top decile (constant) | 100% in both groups |
| Volume | ×1 | dry-up ≤ 0.95 | −3.9pp |
| Orderliness | ×1 | `0.30 ≤ churn/L ≤ 0.60` | **−9.1pp — he hits it *less* than the field** |
| Sector | ×1 | 1m sector share ≥ 0.10 | unmeasurable |
| **Base length** | **×0** | `base_len ≤ 14` | **−13.4pp — the largest wrong-way gap** |

Trade 4–5 stars full size, 3 at half or not at all, below 3 don't.

### The three filters the findings tell you NOT to add

This is the most actionable thing in the study, and it is all negative space. **Three
dimensions run the wrong way** — he takes setups that hit them *less* often than the field he
passed over:

- **Do not filter on consolidation length.** Base length is −13.4pp, the largest wrong-way
  gap in the rubric, and is now weighted **×0**. A "consolidated ≥ N days" filter is actively
  anti-correlated with his selection. (`BASE_LEN_MAX = 14` is the named suspect behind the
  sign and is left open — the ×0 says the dimension *as specified* earns nothing, not that
  base length is irrelevant.)
- **Do not filter on how clean the base looks.** Orderliness is −9.1pp, and was demoted ×2→×1
  for it. This is counter-intuitive against his own vocabulary — "linear and orderly", "not a
  barcode" — but the measurement is what it is. His stated rubric and his revealed selection
  disagree here.
- **Do not filter on volume dry-up or breakout volume.** −3.9pp, inside the noise. Keep it as
  a column, never a cut.

**Filter hard on ADR and tightness. Everything else is a column you read, not a gate.**

---

## Layer 5 — Trigger, stop, alert

- **Trigger** = the cluster's max high, by identity. Equivalently: today's close above the
  last `k` sessions' high. The fitted trendline **never** sets the trigger — it visualises
  tightness and hangs the alert, and that is all it is.
- **Break** = an event, not a state: today's close above *yesterday's* trigger.
- **Stop** = `0.345 × ADR` below the trigger. This is the single strongest preliminary
  finding (§6, finding 1), measured over 649 executed entries:

| | Median stop width | At or under 1.0 ADR |
| --- | --- | --- |
| Cluster-low convention (what the detector used to propose) | 1.28 ADR | 14.2% |
| **Kullamägi's executed trades** | **0.345 ADR** | **98.15%** |

p25 0.238, p75 0.490. **The stop you were going to draw at the base low is roughly four
times too wide.** Draw it at 0.345 ADR under the trigger instead. This is why the geometry
rule matters — anchor the line at the tight cluster and extrapolate *backwards*, so you enter
while price still hugs the rising 10/20, where a ≤1 ADR stop is physically affordable. Wait
for the textbook break of the obvious highs and the MA is 8–10% below you, the stop is
unaffordable, and the trade is dead on arrival. **The geometry rule and the stop rule are the
same rule.**

Alert: price crossing the trendline you drew off the cluster. Chart setup — daily SMA 10/20/50
(+100/150/200 for context), 65 EMA the only exponential on the daily; 60-minute 10/20/65 EMA.

---

## What this screener will not do for you

Carry these with the same weight as the recipe.

- **It does not predict returns.** §5a regressed all seven testable dimensions against MFE
  across his own trades: every correlation is negligible, the largest is **MA support at
  −0.158** pointing the *wrong* way, and four of six are negative. Nothing in the rubric
  predicts how far a trade runs. The star score ranks by **resemblance to his selection**,
  full stop. The reweight that produced v2 carries **no return claim**.
- **The ranking is not validated.** A2 measured a flat null under v1; the v2 re-run opens a
  gap in the discriminating direction (14.4% of his picks at ≥3.5★ against the field's 8.8%)
  but the v2 weights were fitted to that very separation, so the gap is **in-sample** and
  marginal at **p = 0.055**. Weakened, not reversed.
- **Precision is unmeasurable.** The reference set records only trades he *entered*, never a
  setup he declined. There is no false-positive rate and never will be from this data.
  Recall must never be optimised on its own — that is the trap every "just widen it" instinct
  in this document walks toward.
- **The magnitudes are regime-bound.** US, 2019–2022, with **86.6% of entries from 2020–21** —
  a once-in-a-decade US momentum window. §8: *the shape of the findings travels, the
  magnitudes do not.*
- **For IDX, carry the structure and none of the numbers.** The reference set contains no IDX
  trade. Floor is Rp 1B/day, and the binding constraint once your account grows is not the
  floor at all but **intended position ≤ 5–10% of the name's daily value traded** — otherwise
  the exit at the stop is not reachable at the stop.
- **The field the study read is missing 29% of its tickers**, skewed toward names that later
  died. Every field-derived figure above sits on that hole — including the +29.4pp ADR gap,
  which should be read as a **ceiling, not a point estimate**, because the reconstruction
  preferentially kept his high-ADR trades.

---

## TradingView's own limits, for planning

- **Pine Screener needs a paid plan.** Watchlists cap around 1,000 symbols; indices up to
  4,000 (25,000 on Premium).
- **One indicator per screen** — hence a single script emitting every column.
- **Last 500 bars only.** Fine here: the deepest lookback is 126 bars.
- **Daily timeframe** is supported; custom timeframes are not.
- **Five `request.*()` calls max** per script. The port uses none — everything is computed on
  the chart's own series.
- Only one scan runs at a time across all browser tabs.

Sources: [Pine Screener requirements](https://www.tradingview.com/support/solutions/43000742436-tradingview-pine-screener-key-features-and-requirements/),
[Screener volatility formula](https://www.tradingview.com/support/solutions/43000635876-how-is-volatility-calculated-in-the-screener/),
[Screeners walkthrough](https://www.tradingview.com/support/solutions/43000718885-tradingview-screeners-walkthrough/).
