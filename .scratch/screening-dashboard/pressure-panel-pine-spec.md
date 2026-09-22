> **Superseded (2026-09-22).** The indicator that shipped is `~/Projects/pinescript-selling-buying-pressure` (intrabar buying/selling pressure). Nothing below was built. Kept for the ARA/ARB and pocket-pivot notes only. The trading plan (`docs/trading-plan.md`) references the shipped indicator.

# Pressure Panel — Pine Script spec

**Status:** draft, for review before any Pine is written.
**Scope:** a TradingView indicator for *reading charts by eye*. Nothing in the pipeline, rubric,
replay or backtest reads it.

## 1. The question it answers

Inside a base, two things:

1. **Has the selling stopped?** Down days getting smaller and quieter; closes holding the upper
   half of the day even on red days.
2. **Are buyers showing up?** Up days on volume that beats the heaviest recent selling.

It does not say *when to buy*. The trigger stays the break of the cluster high (CONTEXT.md
§The setup). This panel is context for that break, not a replacement for it.

## 2. The parity rule

Every quantity here will get a Python twin in `backend/screener/indicators.py` when (if) one is
pre-registered as a candidate dimension. **The definitions in §4 are the contract for both.** If
the Pine and the Python ever disagree, the Python is the authority and the Pine is the bug. A
definition change is made here first, then in both implementations.

## 3. Non-goals

- No entry/exit signals, no strategy, no backtest inside TradingView.
- No score. Nothing is summed or weighted.
- No A/D line, OBV or CMF. They are cumulative, so their level means nothing; what they add over
  §4.2 and §4.4 is not worth a second scale in the pane.
- No intrabar (lower-timeframe) volume split. Direction is decided per daily bar, the same way
  the Python can decide it from the store.
- No broker-summary or foreign-flow data. Not available in Pine and not in the store.

## 4. Definitions

All windows count **traded bars**, matching `indicators.py`'s rule for rolling statistics. All
comparisons use the chart's close series as TradingView provides it (see §7.2 on adjustment).

### 4.1 Bar direction

| Direction | Rule |
|---|---|
| up | `close > close[1]` |
| down | `close < close[1]` |
| flat | `close == close[1]` |

Close against the previous close, **not** against the open. A gap-up that fades is still an up
day for supply/demand purposes, and this is the rule the U/D ratio (4.4) needs anyway. Flat days
are common on low-priced IDX names where a tick is Rp 1, and they count as neither.

### 4.2 Max down volume, `maxDownVol10`

The largest `volume` among **down** bars in the **10 bars before today** (`[1]` through `[10]`),
excluding today.

- No down bar in that window → `na`.

### 4.3 Pocket pivot, `pocketPivot`

True when all hold:

1. today is an **up** bar (4.1)
2. `maxDownVol10` is not `na`
3. `volume > maxDownVol10` (strictly greater)
4. today is not a **locked** bar (4.6)

Deliberately the bare volume rule. The Morales–Kacher original adds MA-position conditions; those
are left out because the trend is already gated by the dashboard's prior-move and MA checks, and
each extra clause is another place for the two implementations to drift.

### 4.4 Up/Down volume ratio, `udRatio20`

`sum(volume of up bars) / sum(volume of down bars)` over the **last 20 bars including today**.
Flat bars are in neither sum.

- Down-volume sum is 0 → `na` (displayed as "—", never as infinity or a large number).
- Fewer than 20 bars of history → `na`.

Reading: above 1.0 buyers are heavier than sellers over the window; the panel colours the value
at the bands in §5.

### 4.5 Close Location Value, `clv`

`((close − low) − (high − close)) / (high − low)`, range −1 to +1.

- `high == low` → `na` (no range to locate a close in).
- **Upper half** means `clv >= 0`.

### 4.6 IDX price-limit flags

Applied only when `syminfo.prefix == "IDX"`. On any other exchange both flags are always false.

- **Locked bar:** `high == low`. The whole session printed one price, typically pinned at a limit.
  Excluded from pocket pivots (4.3). Its CLV is already `na`.
- **ARA close:** `close >= close[1] × (1 + araPct) − tol`, where `araPct` comes from the
  **previous close's** price tier and `tol` is 0.5 percentage points of `close[1]` (to absorb
  tick rounding).
- **ARB close:** `close <= close[1] × (1 − arbPct) + tol`, same tolerance.

ARA and ARB closes are **marked, not excluded**. Closing at the limit is real pressure. The mark
is there so you can tell "strong day" apart from "capped day".

Limit table (policy facts; **⚠ hand-verify against idx.co.id before shipping**, same standard as
`ARB_POLICY_ERAS` in `volatility.py`):

| Previous close | `araPct` | `arbPct` |
|---|---:|---:|
| Rp 50 – 200 | 35% | 15% |
| > Rp 200 – 5,000 | 25% | 15% |
| > Rp 5,000 | 20% | 15% |

The ARB column reflects the asymmetric 15% band of Kep-00003/BEI/04-2025 (effective 2025-04-08),
the era `volatility.py` already records. History before that date used different widths, so the
flags are only trusted on bars on or after 2025-04-08. Earlier bars get no ARA/ARB marks.

## 5. What the panel draws

One pane, below price, `overlay = false`. Volume stays in raw units, so the pane has one scale.

| Element | Drawn as | Colour |
|---|---|---|
| Volume | columns | up = green, down = red, flat = grey |
| `maxDownVol10` | step line over the columns | orange, thin |
| Pocket pivot | small triangle **below** the column | blue |
| CLV | small circle **above** the column | upper half: solid; lower half: 70% transparent. Same hue as the column |
| ARA close | "A" label above the column | green |
| ARB close | "B" label above the column | red |
| Locked bar | column drawn at 50% transparency | as its direction |
| `udRatio20` | status table, top-right of pane | < 1.0 red, 1.0–1.5 neutral, > 1.5 green |

The status table shows two cells: `U/D 20: 1.62` and the value 5 bars ago, so the direction of
the ratio is readable without a second scale.

**Why the ratio lives in a table and not as a line:** a ratio near 1.0 and a volume in the
millions cannot share one axis, and Pine gives an indicator pane one price scale. A second
indicator just for the line is the alternative (see §8, open question 2).

## 6. Inputs

Inputs exist so the defaults are visible and documented, not so they get tuned by eye. **The
defaults are the pre-registered values.** Changing one on a chart means you are no longer looking
at the definition the Python will test.

| Input | Default |
|---|---|
| Pocket-pivot lookback | 10 |
| U/D ratio window | 20 |
| U/D "strong" band | 1.5 |
| Show CLV dots | on |
| Show IDX limit marks | on |
| ARA/ARB tolerance (pp) | 0.5 |

## 7. Behaviour and edge cases

### 7.1 Timeframe

Daily only. On any other timeframe the pane draws nothing and shows one table cell:
`Pressure Panel is defined on daily bars only`. Weekly volume direction is a different question.

### 7.2 Data differences from the store

- **Volume units.** TradingView and the store may report IDX volume in different units (shares
  vs lots). Every quantity here is a comparison or a ratio of volumes, so units cancel out. No
  conversion is needed.
- **Adjustment.** TradingView's dividend adjustment setting can move `close[1]` enough to flip
  a near-flat day between up, flat and down. Parity checks (§9) are run with dividend
  adjustment **off** on the chart. Any leftover disagreement on a flat-vs-not bar is a data
  difference, not a definition bug.
- **Realtime bar.** On an unfinished daily bar every value can change. Pocket-pivot and limit
  marks on the realtime bar are drawn at 50% transparency until the bar closes. The alert (§7.3)
  fires on bar close only.

### 7.3 Alert

One `alertcondition`: pocket pivot, evaluated on bar close. Nothing else alerts.

## 8. Open questions

1. **ARA tier table.** The percentages in §4.6 come from memory of the current rules and must be
   checked against the exchange's decree before shipping. Wrong tiers give wrong "A" marks, not
   wrong pivots.
2. **Ratio as a line.** Is the status table enough, or do you want a second tiny indicator that
   plots `udRatio20` with a 1.0 reference line, so the trend of the ratio through the base is
   visible?
3. **Pocket pivot + MA.** Should a variant with "close above SMA50" be drawn as a second glyph, or
   left out entirely? Left out by default (§4.3). Adding it later means pre-registering it
   separately.

## 9. Acceptance

1. **Parity sample.** Pick 3 IDX names and 1 US name from the current watchlist. For 5 dated bars
   each (20 in total), compute §4.2–4.6 from `data/screener.duckdb` in a throwaway Python script and
   read the same bars from TradingView's Data Window. Booleans must match exactly, and ratios within
   1e-6 relative. Any mismatch is explained under §7.2 or it is a bug.
2. **Edge bars covered by the sample.** At least one each of a flat day, a locked day, an ARA
   close, a bar where `maxDownVol10` is `na`, and a bar where the U/D down-sum is 0 (or a note that
   none occurred in the sample).
3. **Timeframe guard.** On the weekly chart the pane shows only the notice from §7.1.
4. **Non-IDX guard.** On a US name, no ARA/ARB marks appear and locked-bar dimming never triggers
   from the IDX logic.
5. **Script size.** One file, Pine v6, no external libraries, under ~120 lines.
