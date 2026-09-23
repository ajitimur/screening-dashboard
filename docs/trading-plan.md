# Trading Plan and Rules of Engagement, v2

A manual playbook. It is read by a person at the chart, not by the pipeline. Nothing in
the screener, rubric, replay or backtest reads this file.

It supersedes the Notion page of the same name (2026-08-24 version). Where this plan and
the Notion page differ, this plan wins. Where this plan and
[`references/qullamaggie-method.md`](../references/qullamaggie-method.md) differ, the
method doc describes what Kris does; this plan describes what I do.

Vocabulary follows [`CONTEXT.md`](../CONTEXT.md). In particular: a **continuation setup**
is the pattern (a consolidation in an uptrend that breaks upward); a **continuation entry**
is an add to a position I already hold. They are not the same thing.

---

## 1. General rules

1. **No setup, no trade.** A name that did not come out of my own screening session is
   not tradeable. Not from a group chat, not from a briefing, not from memory.
2. **External ideas get laundered and delayed.** A name that reaches me from social media
   or a chat is ineligible until I have independently run it through section 4.
3. **Check the regime gate first.** If the gate is throttled, the best setup on the screen
   gets throttled size. Setup quality never overrides regime.
4. **Every trade is planned before it is placed.** Entry trigger, stop level, initial size,
   and the exit rule that governs it. Missing any of the four at the moment of entry means
   there is no entry.
5. **Always a hard stop.**
6. **Never average down.**
7. **Inactivity is a position.** A flat book in a hostile regime is the system working.
   Scarcity of setups is information, not a problem to trade out of.

---

## 2. Units and definitions

These are fixed for the whole document. A rule that names a number means that number in
these units.

| Term | Definition |
| --- | --- |
| **ADR** | Average Daily Range, `SMA20(high / low − 1)`, as in the glossary. The volatility unit for every threshold in this plan except exit rule 3. |
| **ATR** | Average True Range, 14 sessions. Used in exit rule 3 only. |
| **SMA n** | Simple moving average of closes over `n` sessions. This plan uses SMAs everywhere, including the index regime gate. The Notion page said EMA; the evidence this plan cites was measured on SMAs, so the plan uses SMAs. |
| **Sloping up** | The SMA's value today is above its value 5 sessions ago. |
| **Sloping down** | The value today is below its value 5 sessions ago. Same test, opposite sign. |
| **Distance from an SMA** | `(close − SMA) / (close × ADR)`, read as "n ADR above" or "n ADR below". |
| **NR7** | Today's range (`high − low`) is the narrowest of the last 7 sessions, today included. |
| **Inside day** | Today's high is below yesterday's high and today's low is above yesterday's low. |
| **RS line** | `adj_close(stock) / adj_close(index)`. Index is `$JKSE` for IDX and `$QQQ` for US. |
| **RS phase** | The RS line is above its own 21-day SMA. |
| **Break day** | The session whose close is above the high of the tight candles (section 5.1). |
| **Day 1** | The entry day. Day 5 is four sessions later. |

---

## 3. Regime gate

Checked at the start of every session, before any chart is opened. The regime state
decides the risk per trade; the trailing closed trades only matter when the state is
`CHOPPY`.

### 3.1 Regime state

The same three states the screener prints, computed the same way
(`backend/screener/regime.py`). One index per book: `^JKSE` for IDX, `^IXIC` (Nasdaq
Composite) for US. All slopes are the section 2 test: today against 5 sessions ago.

| State | Condition on the index | Risk per trade |
| --- | --- | --- |
| **FRIENDLY** | Close above both SMA10 and SMA20, and both sloping up | **1%, full risk.** The trailing table is not consulted. |
| **CHOPPY** | Anything that is neither FRIENDLY nor HOSTILE | **Read the trailing table** (section 3.2). |
| **HOSTILE** | SMA10 sloping down, SMA20 sloping down, and SMA10 below SMA20 | **0.25%, A-grade setups only.** The trailing table is not consulted. |

The two named states cannot both hold (one needs the SMA10 rising, the other falling), so
exactly one state applies every session. `CHOPPY` is the gap between them, not a third
definition.

### 3.2 Trailing closed trades (CHOPPY only)

Computed on the trailing 20 closed trades in that book, real and paper.

| Trailing expectancy | Level | Risk per trade |
| --- | --- | --- |
| ≥ 0R | Full risk | 1% |
| −0.3R to 0R | Slowing down | 0.5% |
| < −0.3R | Defensive | 0.25%, A-grade setups only (section 5.3) |
| Five consecutive stops | Defensive | 0.25% regardless of expectancy |

### 3.3 Release trigger (CHOPPY only)

Step up one row in the table when both hold:

- A follow-through day is logged on the book's index, and
- two of the last five closed trades in that book are profitable. Paper trades count.

### 3.4 What the backtest says about the states

The screener's own backtest priced each state's advice
([`references/backtest_regime_posture.txt`](../references/backtest_regime_posture.txt)).
On IDX, FRIENDLY is the one cell with a clear edge: +1.50R over 414 trades, interval
[+0.20, +3.05]. Every other cell, both markets, is **undecided**: the intervals straddle
zero, and US HOSTILE (−0.15R) is the only negative estimate over the full window. So the
full-risk-in-FRIENDLY rule has support on IDX; the reduced sizing in CHOPPY and HOSTILE is
a stance, not a measured result.

---

## 4. Universe and eligibility

A name must pass every row before it can be a setup.

| | US | IDX |
| --- | --- | --- |
| Liquidity | 30-day ADTV ≥ USD 10M | 30-day ADTV ≥ IDR 5B |
| Price | > USD 5 | > IDR 100 |
| Availability | | Never suspended in the last 12 months |
| Volatility | ADR ≥ 4% | ADR ≥ 3.5% |
| Relative strength | In RS phase | In RS phase |
| Trend | Above a rising SMA50 | Above a rising SMA50 |

Two notes on the IDX column, so the numbers are not mistaken for backtested ones. The
backtests in `references/` were run with an IDX liquidity floor of Rp 10B and an ADR floor
of 3.5% on both markets. Rp 5B admits a band of names no study has measured. The 3.5% ADR
floor on IDX is the looser of the two floors in practice: the IDX field's median ADR is
4.08% against 2.83% for the US
([`references/backtest_idx_adr_floor.md`](../references/backtest_idx_adr_floor.md)).

---

## 5. The continuation setup

This is the only setup in the plan. Episodic pivots and parabolic shorts are not traded.

### 5.1 What it looks like

A stock that has already moved, then rests. The rest is sideways, with higher lows and a
range that contracts into a few tight candles sitting on or near the rising SMA10 and
SMA20. The SMA50 is below, rising. Then one day the range expands upward through the high
of those tight candles. That day is the break day and the buy.

The three moving averages each answer one question, and only that question:

| SMA | Question | Rule |
| --- | --- | --- |
| **SMA10** | Am I late? | Entry must be less than 1.5 ADR above the SMA10. Beyond that line his expectancy is zero (−0.09R over 81 trades) and past 2.5 ADR there were no winners in 24 ([`references/breakout-entry-geometry.md`](../references/breakout-entry-geometry.md)). |
| **SMA20** | Has the base matured? | Price within ±2 ADR of the SMA20, and the SMA20 sloping up. This is what "the 20-day has caught up" means. |
| **SMA50** | Is this a real trend? | Above it, and it is sloping up. Distance above the 50 is not a reason to skip: the farther above it he bought, the better his trades did, as long as he was still close to the 10. |

The SMA10 and SMA50 point in opposite directions on purpose. Distance from the 10 measures
how late in the current thrust the entry is. Distance from the 50 measures how strong the
trend has been, and a strong trend is the setup, not a defect.

### 5.2 Hard rules

Every one of these must be true. One miss means no trade, at any grade.

1. Passes every row of section 4.
2. Above a rising SMA50.
3. Close within ±2 ADR of a rising SMA20.
4. Entry price less than 1.5 ADR above the SMA10.
5. **NR7** on the break day or the session before it.
6. In RS phase on the break day.
7. **Stop at the low of the entry day, and the stop is at most 1 ADR below the entry.**
   If the low of the day is more than 1 ADR away, there is no trade. Wait for it to set up
   again.
8. Regime gate checked (section 3) and the size it allows is the size placed.

The stop in rule 7 is set by the entry day's own range, not by the base. His stops sit at a
median 0.345 ADR, about a quarter of the base's width, well inside it. A stop under the base
would nearly quadruple risk per trade for the same entry.

### 5.3 Marks and grade

Marks are the things that make a setup textbook. They are not required.

- At least 3 sideways sessions before the break.
- The NR7 day is also an inside day.
- **Grey (Tightening) has painted inside the base** on the pressure indicator (section 5.4):
  both sides' pressure below their own normal while the range contracts. The one state the
  indicator paints clearly more often in real setups than on random days.
- Close at least 2 ADR above the SMA50. His best cell: ≥ 2 ADR above the 50 and ≤ 1.5 ADR
  above the 10, +1.57R at a 27% hit rate.
- A solid ▲ (buyer **surge**) on the break day: volume above 1.5 × the median of the prior
  10 sessions *and* buyers won the day. Volume alone is not enough; a gap-up that sells off
  all session clears the volume bar and prints a ▼. The ▲ fires only on the first surge day
  of a run, so a surge the day before leaves the break day without one. The day's volume is
  not known until the close: with a buy stop early in the session, count this mark missing.
- The sector or theme is moving as a pack.
- ADR ≥ 5%.
- Above the SMA200.

| Grade | Meaning |
| --- | --- |
| **A** | All hard rules pass and every mark is present. |
| **B** | All hard rules pass. One or more marks missing. |
| Below B | A hard rule failed. Not a trade. |

In `HOSTILE`, and at the Defensive level of the `CHOPPY` table, only A-grade setups are
taken.

### 5.4 The pressure indicator

Read from the **Buying / Selling Pressure** indicator
(`~/Projects/pinescript-selling-buying-pressure/buying-selling-pressure.pine`) on the daily
chart, with every input at its shipped default (short average 5, long average 20, surge
1.5 × the 10-day median, price-holding lookback 5) and **Mirror signals on**. The settings
are part of the reading. How to read it is in
`~/Projects/pinescript-selling-buying-pressure/docs/reading-the-indicator.md`.

**The indicator is a description of the base, not a gate.** Until 2026-09-22 this section
was hard rule 8: blue had to have painted inside the base, the last tint could not be
orange, and teal had to sit above red. That rule is withdrawn. It was a stance with no
study behind it, and the study that was then run (below) found that it would have refused
15 of 32 of Kris's own setups, and that none of its three conditions predicts anything.

What the indicator contributes now, both as marks in section 5.3:

- **Grey inside the base.** Tightening is the state that distinguishes a real setup from a
  random stretch of chart. It is what a continuation setup looks like from the inside.
- **A solid ▲ on the break day.** Volume above 1.5 × the prior 10-day median and buyers
  won it. Confirms participation, and is only known at the close.

And what it does not:

- **Orange inside the base is not a veto.** A flag after a big move paints orange because
  buying fades while the highs hold. That is the flag forming, not distribution. Kris's
  setups painted orange on 32% of their days, more than the 24% of ordinary days.
- **Blue is not required.** Seller Exhaustion belongs to the post-crash base, where sellers
  have to run out first. In a continuation setup it appears no more often than anywhere
  else, and its absence says nothing.
- **Teal above red is not required.** It held at the last close before the break in 56% of
  his setups, a coin flip.
- **A ▼ after a strong leg is not a top call.** Selling surges after a rally were followed
  by higher prices, not lower, in the study. ▼ means something only where nothing is
  exhausted and the columns have turned, at the end of a run.

**Read it on the completed bar of the session before the break day.** The break day's own
bar is built from a partial day's 5-minute bars until the close, so the lines, the tint and
the ▲ can still change. A ▲ counted before the close is a guess.

Two cautions carry over. Within a few weeks of a volume climax the long averages are
inflated, so every tint comes easily; weigh the lines over the tint. And no tint is not a
healthy tint: the indicator suppresses tint for the first 20 bars of intrabar history.

**What the study says.** Event study of every state and event on 40 US and 38 IDX names,
2020 to 2026, plus 32 hand-labelled bases from Kris's own setup charts, in
`~/Projects/pinescript-selling-buying-pressure/backtest/report.md` and
`.scratch/backtest/spec.md` there.

- Taken over all days, no event or state is followed by returns different from any other
  day, in either market. A crossing ▲ inside blue on US ran slightly *below* baseline.
- A close-location estimate of pressure from daily bars gives the same signals and the same
  results as the 5-minute estimate. The indicator's precision is not real.
- Inside Kris's bases, in the last five days before the break: grey in 47% against 21% for
  a random five-day window; blue 59% against 50%; a ▲ 72% against 64%. Grey is the only
  reading that separates his bases from noise, and it does so at about twice the base rate.
- Those bases broke out to +20% at 10 days with a 91% hit rate. That is selection, not the
  indicator: they are in the set because they worked.

### 5.5 Anti-patterns

Skip, and do not put on alert:

- Wide, loose, "barcode" consolidation. If a triangle cannot be drawn on it, there is no
  setup.
- Months of sideways with no momentum leg in front of it.
- Low ADR, slow stock, however clean the pattern.

Alert and revisit later:

- Fewer than 3 sideways sessions.
- SMA20 not yet inside the ±2 ADR band, or not yet sloping up.

---

## 6. Entry

Market order, or a buy stop, at the range expansion that breaks the high of the last tight
candles. Full size in one order. No starters, no scaling in.

Size: `shares = risk_amount / (entry − stop)`, where `risk_amount` is the regime gate's
percentage (section 3) of that market book's NLV at the time of the planned entry.

If the stock has already run past the 1.5 ADR line from the SMA10 by the time the order
can be placed, it is gone. Be faster next time.

### 6.1 Continuation entries (add-ons)

An add to an open position is a **continuation entry**. It is allowed only when the stock
has formed a fresh continuation setup that passes every hard rule in section 5.2 on its
own, with its own stop at its own entry-day low.

It is treated as a separate position: separate risk, separate stop, separate exit clock.
Sales are FIFO.

---

## 7. Exits

Day 1 is the entry day.

1. Sell one third when the gain is at least 2 × ADR, or on day 5 if the gain has not reached
   2 × ADR by then.
2. After the first sell, move the stop on the remainder to breakeven and trail it with an
   SMA: **SMA5 for IDX, SMA10 for US**. Exit the remainder on the first *close* below the
   trailing SMA. An intraday touch is not an exit.
3. Sell another third if the move is extended, meaning the close is at least 10 ATR above
   the SMA50.
4. If the stock hits ARA (IDX upper limit), sell half.
5. If the stock gaps down through the stop, cut at once. Do not wait for the stop level.
6. If the stock is suspended or enters FCA on IDX, sell all at once.

The IDX trail on the SMA5 is my choice, not his. The studies in `references/` measured the
10-day and the 20-day only; the SMA5 has no outcome evidence behind it yet.

---

## 8. Pre-trade checklist

Copy this into the journal entry before the order goes in. Every line filled, or no order.

```
Book:            IDX / US          Regime:  FRIENDLY / CHOPPY (Full / Slowing / Defensive) / HOSTILE
Ticker:                            Date (day 1):
ADR:             %                 RS phase:       yes / no
SMA50 rising, price above:  yes / no
SMA20 rising, price within ±2 ADR:  yes / no   (distance:     ADR)
Distance above SMA10:       ADR   (< 1.5)
NR7 on break day or day before:  yes / no      Inside day:  yes / no
Sideways sessions before break:
Pressure (read at prior close, defaults, mirror on):
  Grey in base:        yes / no   (mark)
Solid ▲ on break day:       yes / no / unknown at entry   (mark)
Entry:           Stop (LOD):          Stop width:      ADR   (≤ 1.0)
Risk %:          Risk amount:         Shares:
Marks present:   /8                  Grade:  A / B
Exit rule governing:  2×ADR or day 5 → 1/3; then trail SMA5 (IDX) / SMA10 (US)
```

---

## Provenance

- The 1.5 ADR line above the SMA10, the opposite sign of the SMA50, and the stop-inside-the-
  base finding: [`references/breakout-entry-geometry.md`](../references/breakout-entry-geometry.md)
  and [`references/qullamaggie-entry-ma-distance.md`](../references/qullamaggie-entry-ma-distance.md),
  579 matched trades, US, 2019-10 to 2022-11.
- The setup description, the MA catch-up preference, and the anti-patterns:
  [`references/qullamaggie-method.md`](../references/qullamaggie-method.md) §3.
- The IDX ADR floor field data: [`references/backtest_idx_adr_floor.md`](../references/backtest_idx_adr_floor.md).
- The pressure indicator's states and events:
  `~/Projects/pinescript-selling-buying-pressure/docs/reading-the-indicator.md`. The
  numbers in 5.4 and the withdrawal of the old confirmation rule:
  `~/Projects/pinescript-selling-buying-pressure/backtest/report.md` (event study, 78
  names, 2021–2026) and its section (c), 32 labelled bases from Kris's setup charts.
- The regime states: `backend/screener/regime.py`, the same rules the screener prints.
- The trailing-trades table, release trigger, and exit rules 1, 4, 5, 6: the Notion page this plan
  replaces, unchanged.
