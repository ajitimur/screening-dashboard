# Qullamaggie Method — Core Reference

Distilled from ~360 Kristjan Kullamägi (Qullamaggie) stream/video transcripts (~2.2M words).
Everything below is what he actually says in the transcripts. Parameters that he never states numerically
have been **resolved by Aji** and are marked `[SET BY AJI]` — those are house rules, not his words.

> **Two things he calls "tight."** This document uses the word for both, and they are *not* the same
> quantity — the replay measured them **3.8× apart** on the same 649 entries (findings §3b, issue #147):
>
> - **Base tightness** — the setup's geometry, how quiet the stock was *before* the break. §3.1's range
>   contraction, §3.2's cluster, §3.5's ×2 dimension. Median **1.310 ADR**.
> - **Stop width** — his risk, how much of the entry he will lose. §7's stop, §6's trigger choice, §8's
>   sizing input. Median **0.345 ADR**.
>
> He does **not** stop under the consolidation low; his stop is the **low of the entry day** (§7).
> Reading "the stop sits below the tight zone" off this document would place it near 1.3 ADR and
> nearly quadruple risk per trade. Definitions live in [`CONTEXT.md`](../CONTEXT.md).

---

## 0. Operating philosophy

- Three setups only: **Breakout/Continuation**, **Episodic Pivot (EP)**, **Parabolic Short**. Nothing else.
- He is a **home-run trader**: most trades scratch or lose small; roughly 10–15% of trades produce
nearly all of the P&L. The method is engineered so the winners are allowed to run.
- Edge comes from **stock selection + narrow stop width**, not prediction. Price action dictates; no macro calls.
- He invented none of it — ADR, the EP, the breakout, the parabolic short are all borrowed (Minervini,
Dan Zanger, Stockbee lineage). Pattern recognition on the *strongest* stocks is the skill.
- Repeated hard filter: **do not trade slow or choppy stocks.** No momentum, no ADR, no trade.

---



## 1. Universe & scanning



### Liquidity floor `[SET BY AJI]`


| Market  | Minimum average daily dollar volume           |
| ------- | --------------------------------------------- |
| **US**  | **$20,000,000 / day** (his own stated cutoff) |
| **IDX** | **Rp 1,000,000,000 / day**                    |


> **Sizing caveat (not his rule — worth adding):** Rp 1B/day is thin in absolute terms. His US floor exists so
> that a 10–20% position can be entered and exited without slippage. On IDX, add a second constraint:
> **intended position value ≤ ~5–10% of the stock's average daily value traded**, or the exit at the stop
> won't be reachable at the stop. This binds *before* the Rp 1B floor does once your account grows.



### Volatility floor (ADR)

- Focus on stocks with **ADR ≥ 4–5%**. He rejects names on the spot for being slow:
1.9 ADR, 2.4 ADR, 2.8 ADR → "you shouldn't even be trading this thing."
- ADR is the *primary* stock-quality filter, above market cap. For a small account: high-ADR names, market cap irrelevant.
- Comparative logic he uses out loud: if two vehicles express the same theme, take the higher-ADR one
(e.g. a 7.6-ADR name over a 2.4-ADR ETF on the same sector; AGQ at 4.9 ADR over SLV at 2.6).



### ADR definition (settled — TradingView)

```pine
//@version=5
indicator("ADR %")
length = input.int(20)
adr    = 100 * (ta.sma(high / low, length) - 1)
plot(adr)
```

Equivalently `ADR% = SMA20( (High / Low − 1) × 100 )` — identical, since SMA is linear.

Caveat to be aware of, not to fix: on stream he sometimes describes ADR as gap-inclusive (today's high vs
*yesterday's* low, "like ATR but it includes gaps"). The formula above is **intraday-range only and excludes
gaps**, so a habitual gapper screens *lower* than it really moves. Immaterial for flags; **matters for EPs** —
the `3 × ADR` gap test in §4 is therefore slightly generous. All ADR thresholds in this document assume the
TradingView definition.

### The scans (nightly / weekly)

1. **Up ≥ 30% in the past 5 days**
2. **Biggest gainers over 1 / 3 / 6 / 12 / 18 / 24 months**
3. **Intraday gainers + pre-market gappers** (for EPs)
4. **His watchlist**, built from 1–3

A "momentum leader" = a stock in the **top 1–2% of gainers** over some lookback (1m / 3m / 6m).
His tradeable US universe at size: roughly **150 stocks**. Nightly review: ~10 minutes.

---



## 2. Chart setup


| Timeframe     | Moving averages                                                                                               |
| ------------- | ------------------------------------------------------------------------------------------------------------- |
| **Daily**     | 10, 20, 50 (and 100/150/200 for context) — **simple**. The *only* exponential on the daily is the **65 EMA**. |
| **60-minute** | 10, 20, 65 — **exponential only**.                                                                            |


Plus ADR(20) and dollar volume as displayed columns.

Why they matter: the strongest stocks **"surf" the rising 10 and 20** and rarely violate them. Price riding the
rising 10/20/65 EMA on the 60-min = *frontside*. Those same EMAs flipping to resistance = *backside*.

---



## 3. Setup 1 — Breakout / Continuation (the bread and butter)



### 3.1 Preconditions

1. **A big prior move.** `[SET BY AJI]` The stock must sit in the **top decile of 1–6 month returns** within its
  universe (IDX or US). This is the gate that separates a real flag from a random consolidation.
2. **Consolidation after the move**: sideways, **higher lows**, **range contraction** — it gets *tight*
  (**base tightness**; nothing here is about where the stop goes).
3. **Minimum consolidation length** `[SET BY AJI]`: **3–5 days sideways, minimum, for every variant**
  (flag, HTF, triangle, base). Shorter than that and there is no range to break.
4. **The 10-day and 20-day catch up** to price during the consolidation. He repeatedly refuses setups with
  "it needs a few more days sideways for the 20-day to catch up," and states a preference for
   **20-day-based setups over 10-day ones** ("I never trust the 10-day ones").
5. Ideally the pullback found support on a **rising 10 / 20 / 50-day**.
6. **Break of the range on volume.**



### 3.2 Geometry — how he actually draws the trendline

*Sources: the video transcripts, plus a community explainer (ZM / AR / APPS worked examples) that quotes Kris
directly. Quotes below marked **[K]** are his words; the rest is the explainer's reconstruction of his method.*

**The gate first:**

> **Draw the triangle. Connect the lower highs with a descending line; connect the higher lows with a rising line.
> If you cannot draw a triangle — if there is no range and no higher lows — there is no setup. Full stop.**

He says this almost verbatim, repeatedly: *"if you can't draw a triangle, there's no setup."*

**But drawing it correctly is the part everyone gets wrong.** Three rules:

**(1) The trendline visualizes the trend and sets the alert. That's all it is.**
Two functions only: see the tightening, and hang a price alert on the line. It is not a magic level.

**(2) Do not connect random points — connect the *overall trend*.**

- **[K]** *"Trendlines, connecting some random points, I don't believe in that."*
- **[K]** *"It's the overall trend — these undercuts and overshoots, they're normal. You want to see the overall trend."*
- **[K]** *"You'll see a lot of these trendlines and triangles I draw, the price moves both above and below them.
You **want** these undercuts and overshoots, you want those false breakdowns and false breakouts — that's where
you build setup strength. You need to look at the overall trend... you can clearly see it's getting tighter and
tighter. You want to visualise the tightness."*

So: candles poking through the line in both directions is **correct and desirable**. A line that every candle
respects perfectly is a line drawn on too few points. The false breaks *are* the base-building.

**(3) The drawing procedure — find the tight cluster first, then extrapolate backwards.**

> **Find a tight range  sitting on a rising moving average → anchor the line there →
> extrapolate it backwards over the prior highs.**

This is the inversion most people miss. The naive method — connect the recent swing highs and wait for a break
above them — produces a **late entry**, far from the moving average, with a wide stop. (The APPS example in the
explainer: connect-the-highs gives you an entry that "would not have been great.") Drawing from the tight cluster
gives you a line that price crosses **while it is still hugging the 10/20/50-day**.

**Why this matters more than it looks — it's the load-bearing link to your stop rule:**

> *"Kris always buys very close to his moving averages. That's another thing you can't do if you wait for the
> 'true' range break above recent highs."*

Buying at/near the rising MA is what makes a **≤ 1 × ADR stop (§7)** physically possible. Wait for the textbook
break of the recent high and the MA is now 8–10% below you, the stop is unaffordable, and the trade is dead on
arrival. **The geometry rule and the stop rule are the same rule.**

Corollary, from Kris on $AR: by the time price cleared the obvious highs he said **[K]** *"there is no setup —
the setup was a few days ago off the 50d."* The setup is at the MA, not at the high.

**(4) A breakout by itself is not an edge.**

- **[K]** *"A breakout is not an edge. You need to buy breakouts in the right stocks — just a breakout is not an edge."*
This is why §3.1's top-decile prior-move gate exists. The line is worthless on a stock that shouldn't be on the
watchlist in the first place.

**Other notes:**

- **Names don't matter.** Triangle, wedge, pennant, flag, channel — he shrugs at the vocabulary ("I call it a
triangle, the fancy word is wedge I guess"). What matters is **converging boundaries + higher lows + tightening**.
He mocks rigid HTF definitions: most are too strict and will make you miss the best setups. Whether the pullback
was 10% or 35% is not the test.
- **Channel** = same thing with parallel rather than converging boundaries. Same treatment.
- **Bear flag** = exact mirror (big move down, lower highs + higher lows tightening, break *below*). Useful as an
exit/avoid signal even if you never short.
- **He places and trails stops off the pivots themselves** — the 60-min and daily higher lows — manually. He won't
use an automatic trailing stop because it wouldn't sit on the pivot he wants.



### 3.3 Vocabulary → verdict

His live language maps almost 1:1 onto a grading scale. Learn it, because it *is* the rubric:


| He says                                                                                   | Means                      | Action           |
| ----------------------------------------------------------------------------------------- | -------------------------- | ---------------- |
| "linear and orderly", "clean", "tight", "smooth", "very explosive"                        | Textbook                   | Trade, full size |
| "obeying the 10 and 20", "surfing the rising 10-day"                                      | Institutional accumulation | Strong positive  |
| "needs to tighten up", "needs a few more days sideways", "let the 20-day catch up"        | Not yet                    | Alert, wait      |
| "wide and loose", "sloppy", "all over the place", "random", **"it looks like a barcode"** | No structure               | Skip permanently |
| "too choppy", "it's a slow stock", "low ADR"                                              | No edge                    | Skip permanently |




### 3.4 Anti-patterns (auto-reject)

- Loose, wide-range consolidation. Can't draw the triangle → skip.
- Consolidation < 3–5 days, or MAs haven't caught up → skip (alert, revisit).
- No prior big move / not top-decile → not a setup at any price.
- Low ADR / slow stock → skip regardless of how pretty the pattern is.
- Months of sideways with no momentum leg in front of it → skip.



### 3.5 Setup quality score (1–5 stars) `[SET BY AJI]`

He grades every setup 1–5 stars on stream but never publishes the rubric. From how he actually talks, the
score is driven overwhelmingly by **base tightness and orderliness of the range and pullback** — not by
pattern taxonomy. (Base tightness throughout this section: the range's own geometry. The stop never
enters the score — see the note at the top.) Formalized:


| Dimension                                                        | Weight | 1 point if…                                                      |
| ---------------------------------------------------------------- | ------ | ---------------------------------------------------------------- |
| **Tightness** of the range (contraction into the breakout)       | **×2** | Range is narrow and *narrowing*; recent candles are small-bodied |
| **Orderliness** of the pullback (linear, clean, no wild candles) | **×2** | Pullback is a smooth drift, not a barcode; obeys 10/20-day       |
| Prior move strength (top decile 1–6m)                            | ×1     | Yes                                                              |
| Higher lows intact into the breakout level                       | ×1     | Yes                                                              |
| MA support: 10/20 caught up and rising; 50 respected             | ×1     | Yes                                                              |
| Volume: dry-up in the base, expansion on the break               | ×1     | Yes                                                              |
| Sector / theme confirmation                                      | ×1     | Yes                                                              |
| ADR ≥ 5%                                                         | ×1     | Yes                                                              |


Max 10 → **stars = score ÷ 2**. Tightness and orderliness are double-weighted because they are the two
things he actually names when he calls something five-star, and the two things he names when he rejects.
**Trade 4–5 stars at full size; 3 stars at half size or not at all; below 3, don't.**

---



## 4. Setup 2 — Episodic Pivot (EP) — **DEFERRED, NOT IN v1**

A catalyst-driven gap that starts a whole new trend.

**Trigger** `[SET BY AJI]`**:**

```
gap%  ≥  max( 10% , 3 × ADR )
```

Plus, from his own words:

- **Catalyst**: earnings (his favourite — "earnings breakouts are the most powerful breakouts") or major news.
- **The gap must be big relative to the stock's own ADR** — this is the point of the formula above. He dismissed
a +17% gap as "barely 2× ADR" for a high-ADR name, and praised a +20% gap that was **~5× that stock's ADR**.
Sweet spot he quotes for larger caps: **+10% to +30%**.
- **Volume explosion out of the gate** `[SET BY AJI]`**: first-5-minute volume ≥ 50% of 20-day average daily volume.**
(His own benchmark example was extreme: a stock averaging ~1.6M shares/day traded **1.5M shares in the first
5 minutes**, ~90% of ADV. 50% is the permissive floor; ≥90% is a five-star EP.)
- Strongest version: the EP gaps up **out of a base / from strength** — i.e. it is *also* a breakout.
- "Deep EPs" (gap out of a long downtrend, reclaiming the 150/200-day) work, but he says they are **not his
comfort zone** and he underperforms on them. Treat as lower conviction.
- Extreme gaps (>100%) can work in small caps but are the exception, not the plan.

**Entry**: opening range high (§6). **Stops, sizing and sell rules are identical to the breakout.**

---



## 5. Setup 3 — Parabolic Short — **DEFERRED, NOT IN v1**

Cut from the decision skill for now: shorting is not practically available to you on IDX, and it is the part of
his method with the largest blow-up risk (he lost a quarter of his capital in a single day shorting frontside,
and six figures on other attempts).

**Retained only as a long-side defence signal:**

- *Frontside* = 10 / 20 / 65 EMA (60-min) act as **support**; higher lows; still going up. **You may hold longs.**
- *Backside* = those same EMAs flip to **resistance**; **lower highs**; intraday ranges breaking down.
**A name that has gone backside is a SELL / DO-NOT-BUY. Never buy a breakout in a backside stock.**

If you later trade this on IBKR, the missing rule is his definition of a "true parabolic" (he says "that's not
even close to a parabolic" constantly but never gives numbers) — plus: only short the backside, enter on
opening-range-low breaks / VWAP failures / 60-min bear flags, take a **starter first and add** (unlike longs),
and cover into weakness at the 10 / 20 / 50-day.

---



## 6. Entries — the breakout and/or opening range break

He buys as soon as the range break, or on ORB if the price gapped up over the range.

**Which day is "the day the range breaks"?** The day price crosses **the trendline drawn per §3.2** — anchored on the tight consolidation days cluster and extrapolated backwards — **not** the day it takes out the prior swing high. Those are
usually different days, and the difference is the entire trade: the trendline break happens while price is still
hugging the rising 10/20/50-day (affordable stop); the swing-high break happens after price has left the MA behind
(stop too wide → §7 kills the trade). If you find yourself entering far from a moving average, you drew the line wrong.


| Trigger        | Character                                                                                                  |
| -------------- | ---------------------------------------------------------------------------------------------------------- |
| **1-min ORH**  | Earliest, **narrowest stop width**, **highest failure rate**. His most-used on high-conviction names.                 |
| **5-min ORH**  | Middle ground. The "second chance" if the 1-min fails or you missed it.                                    |
| **60-min ORH** | Lowest failure rate, but often **way too wide** — the stock has already run and the stop becomes unusable. |


**Selection logic: use the shortest timeframe whose stop you can actually afford** (§7). If the 60-min opening
range puts your stop beyond 1× ADR, the trade is dead — pass, and wait for it to set up again.

Other mechanics:

- **Longs: buy full size immediately.** No starters, no scaling in, no waiting for confirmation.
- Missed both the 1-min and 5-min ORH and it's already ~14%+ past the trigger: **it's gone. Be faster next time.**
- Re-entry is legitimate: stopped out, then it reclaims the range → he re-buys, sometimes higher.
---



## 7. Stops

- **Default stop = low of the day (LOD)** on the entry day. Alternatives: low of the opening range, or low of the
breakout day. On a gap-*down* open below the prior day's low, he uses the **red-to-green / green-to-red** level.
- **Max stop width** `[SET BY AJI]`**: 1 × ADR.** If the required stop is wider than one ADR, **no trade** — pass and
wait for a re-set. (Consistent with him rejecting ~8% stops and approving one that was "less than half the ATR,
well within the criteria.")
- **Narrow stop width is the entire game.** They are also what makes the sizing in §8 arithmetic work.
- Stops only move **up**, never wider. After the first partial → **stop to breakeven**.
- Intraday defence: if the breakout **falls back into its range** or takes out the LOD, cut or halve.
*"The best breakouts go straight up and never make you second-guess."*

---



## 8. Risk & position sizing


| Parameter                   | Value                                                                                           |
| --------------------------- | ----------------------------------------------------------------------------------------------- |
| **Risk per trade**          | **0.3–0.5%** of account, typical. **Hard cap 1%.** He says 1% risk is *a lot* of risk.          |
| **Position size**           | **10–20%** of account typical; up to **~25%** on high conviction + liquidity.                   |
| **Sizing math**             | `shares = max_dollar_risk ÷ (entry − stop)`. He does it mentally in ~10 seconds; no calculator. |
| **Positions held**          | He runs 20–26; recommends **< 20**.                                                             |
| **Small accounts (< $50k)** | Be **concentrated**: 5–6 positions max, 20–25% each.                                            |
| **Exposure**                | Can exceed 100% (margin) in a strong tape; goes near-flat when there's no edge.                 |


**Position size (10–20% of equity) ≠ risk (0.3–0.5% of equity).** The stop distance reconciles them — which is
exactly why the 1× ADR cap in §7 is load-bearing: a wider stop forces a smaller position, and past 1× ADR the
position gets too small to be worth the slot.

---



## 9. Sell rules (longs) — the part most people get wrong

The canonical rule, repeated across years:

1. **Ignore the first 1–2 days.** Do nothing, no matter how much it runs.
2. **Sell 1/3 to 1/2 into strength on day 3–5.** (He sometimes splits: 1/3 on day 3, 1/3 on day 5.)
3. **Move the stop to breakeven** on the remainder.
4. **Trail the rest with a moving average. Exit on the first CLOSE below it.**

**Which MA to trail with** `[SET BY AJI]`**:**


| Stock's ADR | Trail with    |
| ----------- | ------------- |
| **< 5%**    | **10-day MA** |
| **≥ 5%**    | **20-day MA** |


(Rationale: the faster the stock, the more room it needs — a 7-ADR name will slice the 10-day on noise alone.
Exception: declared long-horizon position trades may trail the 50-day, sized ≤ 10%.)

Overnight rule of thumb: closes **near the lows of the day** and below your level → out. Closes strong → hold,
and today's low becomes the new stop.

---



## 10. Market regime filter

He does not predict, but he does **size to the environment**:

- **Long-friendly**: index and leaders above a **rising 10 and 20-day**; breakouts follow through
("they just go up, no headaches"); fresh leadership; sectors moving in packs.
- **Do not swing long**: **10-day sloping down, 20-day sloping down, 10 below 20** → "high fail rate,
you probably shouldn't swing trade on the long side."
- **Choppy markets** produce false signals both ways — fewer trades, smaller size, and he says openly
"I don't see an edge right now" and sits.
- **Pullbacks are information**: whatever holds up (finds support on the 20-day while the index tests the 50)
is showing **relative strength** → those lead the next leg. In a *deep* washout, the first bounce is led by
the most beaten-down junk; in a *mild* (5–10%) pullback, it's the RS names that lead.
- **Sector matters**: strength clusters. Check the theme of every candidate.

---

