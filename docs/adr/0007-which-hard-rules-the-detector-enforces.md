---
status: accepted
---

# Which of the trading plan's hard rules the detector enforces

> **Implemented, and the open measurement is closed.** The Consequences below say the
> population cost "is not yet measured" and make measuring it a condition of shipping. It has
> since been measured: **31.7%** of the live store's v3 detections drop, the Trend gate
> accounting for 30.7 points of that and the two-sided band for 1.0 — roughly half what this
> ADR budgeted for. Detection recall against his 656 replayable entries falls **549 → 421**.
> Neither number revises the decision; both are recorded in
> `references/adr-0007-population-cost.md`, which also names the one anchor still unmeasured.

`docs/trading-plan.md` §5.2 lists eight hard rules, every one of which must hold before a
name can be traded. Three of them are moving-average preconditions (rule 2, above a rising
SMA50; rule 3, within ±2 ADR of a rising SMA20; rule 4, entry under 1.5 ADR above the
SMA10). **The detector enforces none of them.** Its only MA test is `catch_up`, a one-sided
ceiling on how far the close sits *above* the 10 and 20 — so a name that has fallen through
every average passes it trivially, and the Setups grid shows broken-down names beside real
bases.

That gap was found by reading cards, not by a study. This ADR records which hard rules close
it, which deliberately do not, and the rule that decides.

## The governance gap this walks into

ADR 0002 says what evidence licenses **loosening** a gate. ADR 0004 says what licenses
changing a gate's *shape*. **Nothing says what licenses adding one**, because until now
nobody had proposed a narrowing — every pressure on this detector since #145 has run the
other way.

The absence of a rule is not permission. But it is also not the obstacle it first looks
like, because the change below is not argued from the replay at all. It is argued from a
specification this project already wrote and then failed to implement. The evidence rules in
0001, 0002 and 0004 all govern *what the trade record licenses*; they are silent here for the
same reason they are silent about the liquidity floor.

## Decided (2026-09-23)

**A hard rule from the trading plan enters the detector when all three hold.**

1. **It is a property of the name, knowable on the detection session.** Not a property of
   the break day or the fill. Rule 2 and rule 3 are statements about where price sits
   tonight. Rules 5 (NR7 on the break day), 6 (RS phase on the break day) and 7 (stop at the
   entry day's low) are facts about a session that has not happened.
2. **Its screener form can be stated without the part the eye judges better.** The detector
   is a funnel to a chart, not the trade decision, and every Setups card carries a mini
   chart. A clause the eye reads off that chart in under a second is not worth encoding.
3. **Rejecting on it is cheaper than reading the chart.** A rule that removes names you
   would have dismissed at a glance saves attention. A rule that removes names you would
   have wanted to look at costs more than it saves, whatever its hit rate.

Applied to the eight:

| rule | detector | why |
| --- | --- | --- |
| 1. Passes §4 | no | liquidity and price are the universe's job already |
| **2. Above a rising SMA50** | **yes, without `rising`** | a property of tonight; the floor is the condition the broken-down cards failed |
| **3. Within ±2 ADR of a rising SMA20** | **yes, without `rising`** | a property of tonight |
| 4. Entry under 1.5 ADR above the SMA10 | **no** — moves to the card | a property of the *entry*, which the plan says in so many words |
| 5. NR7 on the break day | no | break-day fact |
| 6. In RS phase on the break day | no | break-day fact; the decile gate already approximates it |
| 7. Stop at the entry day's low | no | entry-day fact |
| 8. Regime gate checked | no | a sizing decision, and §4.9 keeps the regime out of the list by construction |

**The slope clauses are dropped on purpose.** The plan says "a *rising* SMA50" and "a
*rising* SMA20"; the detector will test neither. This is condition 2: slope is the single
most legible thing on a chart, every card has one, and a screener that pre-judges it removes
names its user could have triaged instantly. The screener runs looser than the plan and the
eye closes the gap. That division is the whole reason the Setups grid is a card grid and
never a table (§5.2).

**This is fidelity, not performance, and the distinction is load-bearing.** The evidence in
`references/` mildly argues the *other* way: Kullamägi entered below his own SMA50 on
**12.0%** of trades, and that bucket is **n = 69, mean R +0.88** — better than three of the
buckets above the line — with a Spearman of **+0.048** against R, which is noise
(`references/qullamaggie-entry-ma-distance.md:113-114`, `:202-217`). The plan already knew this
and chose the hard rule anyway; its SMA50 row says "Distance above the 50 is not a reason to
skip" while §5.2 rule 2 still demands the floor.

That is a coherent position and it is the one adopted: **those 12% are a master's discretion,
and a rule-following trader does not get to replicate discretion.** The backtest reached the
same place from the same direction — `backend/backtest/contract.py:236-241` justifies its own
trend gate as "the method's own precondition (story 10)" and cites no measurement either.

No outcome claim is made here, and none may be read into it later. If a future study shows
the gate costs expectancy, that is not a surprise this ADR failed to anticipate; it is a
price this ADR knowingly accepted.

## What changes, concretely

- A fourth detector gate, **Trend**: `adj_close >= sma(bars, 50)`, named to match
  `backend/backtest/universe.py:107`'s existing `passes_trend_gate` so both paths share a
  word for one idea. The two remain different classifiers; this ADR does not merge them, and
  the app still has no ADR floor and no ADTV floor where the backtest has both.
- **Catch-up becomes two-sided on the 20**, `abs(adj_close − sma20) <= 2.0 × adr_abs`. The
  condition keeps the name `catch_up`: it is persisted as a `failed_condition` value in the
  funnel, and renaming it would orphan stored rows. Its `CONTEXT.md` entry is rewritten,
  because the word now describes a band and used to describe a ceiling.
- **Both read the adjusted series.** `bars.py` already states the house rule — the
  unadjusted OHLC for order levels, "the adjusted close for everything geometric" — and a
  trend floor and a maturity band are geometry, not order levels. The trigger and the stop
  stay unadjusted, which is why they exist. The current `catch_up` reads unadjusted via
  `_sma_close` and moves; on an IDX bonus issue the two conventions would otherwise disagree
  about the same name for fifty bars.
- `DETECTOR_VERSION` 3 → 4. The population changes, so the stamp exists to stop a silent
  comparison against v3 rows (the same reason ADR 0004 gives).

## Considered options

- **Put the SMA50 test in the universe.** Rejected, and it is the option that would have
  done real damage. The universe is the denominator the decile ranks are computed against,
  so a trend condition there re-ranks the entire market as a side effect, and every name's
  percentile moves for reasons unrelated to it. It also breaks the universe's stated shape
  ("liquidity, instrument type and listing age, and nothing else") and fights sticky
  membership, which exists precisely so the denominator does not churn — and a name crosses
  its 50 constantly. `backend/backtest/universe.py:15-31` reached the same conclusion from
  the other side and built a second classifier rather than touch the app's.
- **Mark the names instead of rejecting them**, the shape #154 moved base tightness to.
  Rejected on the same discipline argument that licenses the gate at all: a sous chef who
  must exercise judgement on every marked card is not following a cookbook. Noted as the
  reversible option if the population cost turns out to be wrong.
- **Keep the plan's `rising` clauses.** Rejected under condition 2. It would also make the
  detector stricter than its own user wants, which is the opposite failure from the one being
  fixed.
- **Take the backtest's gate verbatim** (`adj_close > sma50`, strict). Cosmetic difference;
  `>=` is adopted because the plan says "above it" and a close exactly on the average is not
  the complaint that prompted this. Worth noting the two now differ by a boundary case.
- **Enforce all eight hard rules.** Rejected by condition 1 — four of them are facts about a
  session that has not happened when the detector runs.

## Consequences

- **`MA support` stops sorting, and this is accepted.** `close > SMA50` and `sma20_rising`
  are close to the same condition in different clothes: requiring the first lifts the
  second's hit rate from **68.8% to 85.8%** and collapses the dimension's separating power
  from **+9.8pp to +0.2pp** (`references/backtest_gate_isolation.md:237-241`, measured on a
  no-slope gate, which is exactly this one). The rubric is **not** touched in the same
  change — ADR 0004 condition 3 forbids a shape change and a weight change riding together,
  or neither is attributable. Whether the dimension has become dead weight is a later
  question with its own measurement.
- **The population cost is not yet measured**, which is a departure from ADR 0002 condition
  4 and is called out rather than hidden. The backtest's isolation table puts the trend gate
  at roughly halving members per session in a differently-shaped field, and a two-sided SMA20
  band narrows further. The count and a sample of what drops are to be measured over the
  existing store before this ships; a full replay ledger is reserved for if the drop looks
  wrong.
- **Rule 4 is now homeless, and that is the next decision, not this one.** `CATCHUP_10 = 1.0`
  is a borrowed `q-scanner-v2` default that ticket 19 skipped when it fitted the detector's
  parameters — the spec says the quiet part out loud, "a borrowed default from `q-scanner-v2`,
  fitted to nothing" (`.scratch/screening-dashboard/v1-spec.md:509`). The measured line is
  **1.5**, not 1.0, and it lives in the plan and nowhere in the code. Removing the ceiling in
  favour of a trigger-to-SMA10 distance on the card is a **loosening** and goes through ADR
  0002 on its own evidence, in its own change, so its effect stays attributable against this
  one. It is not licensed by this ADR.
- **This is the first narrowing, and it sets a precedent whether or not it means to.** The
  three conditions above are written to be reached for again. A future proposal that fails
  condition 1 or 2 should be refused by them.
- **Hard to reverse in the direction that matters**, for ADR 0002's reason: every digest
  written after it freezes a list drawn from a narrower field, and loosening back does not
  recover the record.
- **`docs/adr/` already contains two files numbered 0006**, from parallel worktrees. This is
  0007 and collides with neither, but the numbering is no longer a reliable ordering and a
  future ADR should scan the directory rather than increment the last title it saw.
