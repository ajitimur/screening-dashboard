# Setup detection algorithm — making the breakout/continuation computable

Type: grilling
Status: resolved
Blocked by: 05

## Question

How does a machine decide, from daily bars alone, that a stock is in a valid breakout/continuation
setup? This is the highest-risk ticket on the map.

§3 is written for a human eye. Each clause needs a computable definition — or an explicit admission
that it can't be computed and must be shown to the human instead:

- **Consolidation detection** — where does the base start and end? Anchor on the prior move's high, on a
  swing detection, on a volatility-contraction measure? §3.1 requires ≥ 3–5 days sideways.
- **Range contraction / tightness** — the load-bearing quantity (§3.5 weights it ×2). Candidates:
  ratio of recent N-day range to earlier N-day range; ATR or ADR compression; declining true range
  slope; narrowing high/low envelope. Pick one and define the threshold.
- **Higher lows** — over what pivot detection, and does a single undercut break it? §3.2 says undercuts
  and overshoots are *desirable*, so a naive monotonic test will reject the best setups. This is the
  trap to design around.
- **Orderliness** — the other ×2 dimension, and the fuzziest. "Smooth drift, not a barcode." Candidates:
  distribution of candle body sizes; count of wide-range days in the base; R² of a linear fit to the
  pullback; ratio of net drift to path length. Decide whether this is scorable at all or is the point
  where the human takes over.
- **The trendline** — §3.2 is explicit that the correct procedure is *find the tight cluster sitting on a
  rising MA, anchor there, extrapolate backwards over the prior highs* — not connect-the-swing-highs.
  Can that be automated? Its output sets the alert level and therefore the entry, and the entry sets
  whether the ≤ 1×ADR stop is affordable — so getting this wrong invalidates the trade, not just the
  chart. If it can't be automated reliably, what does the app draw instead?
- **MAs caught up** — §3.1 wants the 10 and 20 to have converged on price, with a stated preference for
  20-day-based setups. Define "caught up" as a distance threshold, and how the 10-vs-20 preference
  shows up in the score.
- **Volume** — dry-up in the base and expansion on the break, both as numeric tests.
- **Backside veto** — §5 says never buy a breakout in a backside stock. That test needs 60-minute bars
  (10/20/65 EMA flipping to resistance), which an EOD-only app doesn't have. Decide the daily-bar
  substitute, or accept the gap and surface it as a warning.
- **Stop affordability** — §7 caps the stop at 1×ADR and §6 says pick the shortest timeframe whose stop
  you can afford. With EOD data only, what stop can the app estimate, and does it reject candidates
  whose implied stop exceeds 1×ADR?
- **Output shape** — one boolean plus a score, or a set of graded signals the star rubric consumes?

**Data hazards this ticket must design around (from ticket 01):**

- **Phantom zero-volume bars** — 4.0% of IDX bars, concentrated in suspended names, which emit *more*
  bars than active ones. A flat bar is maximal "contraction" to any naive tightness measure, so these
  will manufacture five-star setups out of dead stocks unless dropped first.
- **ARA/ARB limit days** on IDX cap the daily range artificially, which biases both ADR and any
  range-contraction measure downward. Decide whether they need detecting.
- **Invisible rights adjustments** mean absolute historical price levels are not trustworthy on IDX.
  Relative geometry (ranges, ratios, MA distance) is fine; anything anchored to a real price is not.
- **The last bar may be partial (ticket 02)** — while a session is open, the current day's bar contains
  only the hours traded so far. Breakout detection keys on the *most recent* bar, which is precisely
  the one at risk. Decide explicitly whether detection ever runs against an open session, or only ever
  against closed bars.

- **ARA/ARB limit days on IDX — inherited from ticket 05, undecided by design.** Ticket 05 (D10)
  established that limit-day detection is a dead end on free data: the auto-reject band is tiered by
  price and board with the table behind Cloudflare, and raw IDX prices are unrecoverable so the bands
  cannot be inferred from history either. The distortion is that a limit-locked bar has a **collapsed
  high/low range**, which understates ADR and flatters tightness. Whether contraction/tightness must
  handle this at all is **this ticket's call** — it is the only place the question can be answered,
  because it depends on how contraction is defined.
- **The partial-bar question below is already settled** by ticket 05 (D8): non-final bars are dropped at
  ingest on an exchange-clock rule, so detection *never* sees an open session. What remains for this
  ticket is only whether detection wants anything else from the current session.
- **Inputs this ticket can assume**, all fixed by ticket 05: phantom (`volume == 0`) bars are already
  removed and windows count **traded bars**, not calendar days; series are **adjusted** (so all ratio
  measures are adjustment-safe); there is **no absolute-price rule** anywhere, so detection must not
  introduce one on IDX.

Resolve against `references/qullamaggie-method.md` §3, §6, §7. Expect this to spawn follow-on tickets.

**Owed to ticket 10 (market regime filter):** detection must emit a defined **trigger level** per
detected setup — the price the breakout keys on. Ticket 10 records it nightly from launch so a
follow-through series accumulates forward; without a stable definition here there is nothing to record
against, and the capture cannot be backfilled later.

---

## Answer

The breakout/continuation setup is computable from daily bars, and the resulting detector has **zero
tunable parameters**. That was not the expected outcome — the ticket was flagged as the highest-risk on
the map precisely because §3.5 double-weights the two dimensions least amenable to automation. Both turned
out to be measurable, but only after the base-finding problem was solved in a way that made them
measurable *fairly*.

### D1. Detection emits a state, not an event

Nightly, the detector emits every name **currently sitting in a valid base**, each with a star score and a
trigger level, regardless of whether anything happened today. The breakout is then a **state transition**
(`WATCHING` → `TRIGGERED`) on a name already known to the system, not a separate detector.

This is forced by ticket 10, which records a trigger level nightly from launch so a follow-through series
accumulates forward: you cannot record a trigger for a breakout that has already happened. It also matches
§3.1, whose preconditions describe a base forming rather than a break, and §3.2's stated purpose for the
line ("hang a price alert on the line").

Consequence: detection runs against **every universe member every night**, not just recent movers.

### D2. The base is found by an end-anchored backward search — no pivot detection anywhere

The base **always ends on the most recent bar**. There is no such thing as a base that ended last week,
because the detector reports state as of tonight. Only the start is unknown, so it is searched: evaluate
every candidate length L from 3 upward, ending today.

This eliminates swing/pivot detection entirely, which matters more than it sounds. §3.2 is explicit that
undercuts and overshoots are **desirable** — *"you want those false breakdowns and false breakouts, that's
where you build setup strength"* — so a pivot detector fights the method at exactly the bars that
distinguish the best setups. The search restates §3.2's inversion as an algorithm: anchor on the recent
tight cluster, extrapolate backwards over the prior highs.

### D3. Every valid window is retained

The search does not collapse to one window. The **set** of passing windows is itself evidence: a base valid
at L=3,4,5…14 is a nested, coherent contraction, while one valid only at L=7 is an artifact. This set later
turns out to be what makes contraction measurable (D7).

### D4. The primary window is the shortest valid one

Two designation rules were tried and rejected in session before this one was settled. The reasoning is
recorded because the failures are reusable:

**Every distance quantity over an end-anchored window is monotone in L.** Window low is a running minimum,
so it only falls as L grows; window high is a running maximum, so it only rises. Therefore:

- ranking windows by **raw tightness** collapses to L=3 — a 3-bar window is mechanically tighter than a
  14-bar one, having had fewer chances to move;
- ranking by **MA proximity** collapses to L=3 for the identical reason, since both the low and the trigger
  drift away from the MA as L grows.

Any argmax over a monotone quantity degenerates. Rather than correcting the monotonicity (a √L
normalisation and a mean-of-lows statistic were both considered), the degeneracy is **accepted**: primary
is the shortest valid window. This is defensible on the method's own terms — the shortest window yields the
**earliest, nearest-the-MA trigger**, which is the entry §3.2 spends its longest passage arguing for, and
which is what makes the §7 stop affordable. The base-length signal is not lost; it comes from the retained
set (D3) instead.

### D5. The trigger is the lower of a flat and a sloped level

`trigger = min(max high of the primary window, fitted descending line at today)`.

The sloped component is the high-side fit already computed for validity (D9). Taking the lower of the two
biases the trigger toward the earlier, more affordable entry in every case, and gives a base that goes
quiet a trigger that **descends each night it sits** — which is the behaviour §3.2 describes and the reason
the trendline break and the swing-high break are different days.

Accepted cost: the trigger's binding rule varies name to name, and it front-runs — more signals, more false
breaks. The false breaks are partly a feature per §3.2, but this is the decision most likely to need
revisiting after ticket 09 looks at real charts.

### D6. Stop is estimated at the base low, and unaffordable candidates are rejected

Detection fires before any entry exists, so §7's "low of the day on the entry day" is unavailable. The EOD
proxy is the **low of the primary window**:

```
implied stop width = (trigger − base low) ÷ trigger
reject when width > 1 × ADR
```

This is honest rather than convenient — §7 says to cut if price falls back into the range, so the base low
is where the stop actually goes. It is a **hard rejection, not a flag**, because §7 is unambiguous: wider
than 1×ADR means no trade. It is also the only mechanism that enforces §6's "shortest timeframe whose stop
you can afford" without intraday data, and it composes with D4 — the shortest valid window has the tightest
base low, so the gate systematically favours the near-MA setups the method wants.

This gate is what §3.4's first auto-reject ("loose, wide-range consolidation") looks like in numbers.

### D7. Contraction — the ×2 tightness dimension — is the range(L) curve against a √L baseline

The affordability gate (D6) already measures `(trigger − base low) ÷ ADR`, which **is** the primary window's
range in ADR units. So "narrow" is already pass/fail, and scoring narrowness again would put the ×2 weight
on a quantity that is already gated. §3.5 asks for two things — range is *narrow* **and** *narrowing* — and
the gate has the first. Tightness therefore scores only the second.

The retained window set (D3) gives `range(L)` for every candidate length: a curve, already computed. Under
a random walk that curve grows as √L. A contracting base grows **flatter** than √L, because the older bars
are wide and the recent ones are tight. Contraction is scored as how far below the √L baseline the observed
curve sits.

Length-fair by construction, needs no new data or new window, and degrades gracefully — a name with a
single valid window scores neutral rather than erroring.

### D8. Orderliness — the other ×2 dimension — is the churn ratio

`churn = Σ(daily ranges over the base) ÷ (base high − base low)`. A smooth drift traverses its range once
or twice; a barcode crosses it every session. This is §3.3's own image ("it looks like a barcode") made
numeric, and it is parameter-free and scale-free.

**The ticket's own candidate list was wrong here and the correction is the substance of this decision.**
"Ratio of net drift to path length" — the efficiency ratio — does not work: a base is *sideways by
definition*, so net drift is near zero for every good setup and the measure would score the tightest bases
as maximally disorderly. Dividing path length by the **envelope** rather than by net drift fixes this
completely while keeping the same intuition. R² of a linear fit to closes fails for the same reason.

Measured on the **longest** valid window, not the primary: on the primary it reduces to roughly L ÷ the
affordability width, which would double-count the §7 gate for a third time.

So orderliness **is** scorable — the ticket's open question of whether this is where the human takes over
resolves to no.

### D9. Validity is the triangle test

A window is valid when:

- a line fitted to its **highs** has slope ≤ 0, and
- a line fitted to its **lows** has slope ≥ 0, and
- L ≥ 3 (§3.1's minimum).

This is §3.2's gate sentence executed literally: *"connect the lower highs with a descending line; connect
the higher lows with a rising line. If you cannot draw a triangle, there is no setup. Full stop."*

Crucially it defuses the higher-lows trap **by construction**. A fit is not a monotonic test, so individual
bars may sit above or below either line without invalidating the window — which is not a tolerated
exception but the stated ideal. Every alternative considered (monotone lows with a tolerance band, a
containment cap on how far bars may pierce) reintroduces the trap with padding: the bar that breaks the
tolerance is usually the false breakdown that built the setup.

§3.5's "higher lows intact" dimension is therefore the **low-side fit slope**, already computed here — a
gate for validity, with its magnitude available as a score input.

Rising channels and parallel-boundary ranges are **excluded** by requiring the highs fit to be non-rising,
notwithstanding §3.2's "same treatment" aside, because the gate sentence he repeats verbatim is
specifically about the triangle.

### D10. MA catch-up is one number, and the 20-over-10 preference falls out of it

`ma_dist_adr = (base low − SMA20) ÷ (ADR × price)`, with SMA20 required to be rising.

"Rising" is tested **sign-only** — `SMA20[t]` vs `SMA20[t−5]` — reusing the exact convention ticket 10
settled for the regime filter. This keeps the map internally consistent and adds no tunable parameter,
which ticket 10 argued for on the grounds that survivorship bias makes any threshold uncalibratable.

§3.1's stated preference for 20-day-based setups over 10-day ones needs **no second rule**: a name still
riding well above its 20-day scores a large distance, while a genuine 20-day-based setup scores near zero.
SMA10 and SMA50 distances are chart context and score nothing.

### D11. Volume scores dry-up only in v1

`dryup = median base volume ÷ median volume over the 50 bars preceding the base`.

D1's state framing creates an asymmetry: dry-up is measurable every night, but **expansion only exists at
the break** — so half of §3.5's volume dimension is unmeasurable for exactly the names on the watchlist.
Scoring both would make a name's star score change at the moment it triggers with no change to its base,
forcing ticket 09 to calibrate two variants (`WATCHING` and `TRIGGERED`).

Resolved by scoring dry-up alone. Break-day expansion **is computed and persisted nightly** — ticket 10's
follow-through stream needs it — but never touches the score. The star score stays one number meaning the
same thing in every state.

Accepted cost: §3.5's volume dimension is permanently half-measured, and confirmation on the break is the
half he actually watches.

Both quantities are ratios, so ticket 01's shares-not-lots quirk on IDX cancels, and ticket 05 has already
dropped the phantom zero-volume bars that would otherwise crater every dry-up ratio.

### D12. §5's backside veto is knowingly left unenforced

The frontside/backside test needs 60-minute bars (10/20/65 EMA flipping to resistance), which an EOD app
does not have. A daily-65-EMA substitute was available and considered — §2 already places exactly one
exponential on the daily chart, the 65 EMA, and defines frontside/backside in those terms — but **no
substitute gates anything**.

The 65 EMA is still drawn on the chart per §2, and the missing check is surfaced as a standing caveat.
§5's auto-reject is therefore absent from v1. The known weakness of a caveat shown on every candidate is
that it is a caveat shown on none; this is accepted rather than solved.

This interacts with D15: excluding the 12m window from the prior-move gate removes the most likely route
for a rolled-over name to reach the candidate list, which is the same population the veto would have
caught. That is partial cover, not a substitute.

### D13. IDX limit days are knowingly unhandled

Ticket 05 (D10) established that limit-day detection is a dead end on free data — the auto-reject band is
tiered by price and board with the table behind Cloudflare, and raw IDX prices are unrecoverable so the
bands cannot be inferred from history. This ticket was handed the remaining question: whether
contraction/tightness must handle it at all.

**It does not, in v1.** The exposure is real and is stated plainly: a limit-locked bar has a collapsed
high/low range, which **flatters both ×2 dimensions simultaneously** — extreme contraction (D7), minimal
churn (D8). A dead stock can therefore score as a textbook base.

A generic liveness floor was available (invalidate a window whose median daily range falls below a fraction
of the name's longer-run ADR — market-agnostic, catches truncated as well as fully-locked bars, and
subsumes a zero-range test). It was declined in favour of relying on ticket 05's 80%/3-session density
gate, accepting that density catches *missing* bars rather than *present-but-flat* ones.

**Carried to ticket 09** as an explicit calibration item: it is the ticket that sits with real charts and
is the place this would surface empirically.

### D14. There is no Lmax — the triangle test self-caps

The search was originally specified with one free parameter: a cap stopping the base from swallowing the
momentum leg. **That parameter does not need to exist.**

Validity requires the highs fit to slope ≤ 0. Extending the window backwards into the momentum leg adds
**older bars with lower highs**, which tips that fit from descending to rising — so the window goes invalid
the moment the leg bleeds in. §3.1's "consolidation *after* the move" is already enforced by the geometry,
with no prior-move-high computation and nothing to tune.

What remains is a pure compute bound (search L up to ~60 bars and stop). It is not a modelling parameter:
it never binds, because validity fails long before it.

### D15. The prior-move gate is top-decile in any of 1m / 3m / 6m

Read from ticket 06's rank table — 06 established ranking as a **shared service** and §3.1's gate must not
define strength a second time. But only three of 06's five windows are read, and the two exclusions are for
stated reasons:

- **1w** is a momentum *burst*, not §3.1's "big prior move" — and it is the board 06 measured turning over
  16 of 30 rows nightly.
- **12m** is stale enough that a stock which topped out months ago still carries it, which is the backside
  case D12 no longer catches.

This narrows 06's ~29% union without touching its definitions. Detection remains a consumer.

### D16. Output is a score plus a chart evidence bundle

The emitted interface is the star score and the artifacts needed to draw the chart — the fitted lines, the
retained window set, the MAs, the trigger, the state. The raw signal vector is **internal**.

*Internal is not discarded.* The raw measurements are **persisted to the nightly stream**, because ticket 09
must be able to recalibrate over history rather than only forward, and because tickets 06 and 10 both
established that the nightly streams store raw numbers precisely so a later change can be replayed
backwards. This was reconciled in session rather than put as a separate question.

Accepted cost: the bundle is being designed against a consumer that does not exist yet — ticket 11 has not
decided what the chart shows. The bundle's *contents* should be treated as provisional and settled by 11.

### Owed to ticket 10, discharged

Detection emits a **stable trigger level** per detected setup: `min(max high of primary window, fitted
descending line at today)`, defined for every name in the `WATCHING` state. Ticket 10 can record it nightly
from launch.

### Two properties of the result

**Zero tunable parameters.** Every threshold that was reached for got removed: Lmax dissolved into the
triangle test (D14), "rising" is sign-only per ticket 10 (D10), the √L baseline is a random-walk null rather
than a fitted constant (D7), and churn is a bare ratio (D8). The only numeric constants are the method's
own — L ≥ 3 (§3.1) and 1×ADR (§7). This matches ticket 10's argument that on survivorship-biased data an
uncalibratable threshold is worse than none.

**Every scored quantity is a ratio.** Contraction, churn, MA distance, dry-up and stop width are all
dimensionless. Ticket 05 predicted this would make ticket 01's unrecoverable raw IDX prices cost nothing,
and it holds: nothing in detection is anchored to an absolute price level, on either market.

### What this leaves for ticket 09

Beyond its own scope, three items land on it from here:

1. **D5's trigger rule** — the min-of-two is the decision most likely to look wrong against real charts.
2. **D13's limit-day flattery** — whether locked IDX bars manufacture false five-star setups in practice.
3. **D11's half-measured volume dimension** — whether dry-up alone carries §3.5's volume point.

## Amendment — ticket 18

**D1 is amended: detection emits a base, not a state.** Ticket 17 recorded the
`WATCHING`→`TRIGGERED` transition as surviving the split. The *transition* does; the **state** does
not. Under ticket 17's trigger the level is the trailing cluster's max high, a window that includes
today, so `trigger_t ≥ high_t ≥ close_t` for every detection — a detected name is never above its own
trigger. Measured over 1,051 breaks: 55.0% are still detected the next night and **100% of those are
back below their new level**, because the cluster rolls forward to swallow the breakout bar.

So a **break** is an event against `(market, symbol, session)`, defined by ticket 14's A3
(`close_today > trigger_yesterday`), and `WATCHING` is the only state a detection can be in. Ticket
12 is unaffected — detections are already dated rows carrying their trigger, so the event is derivable
from rows that exist. See [ticket 18](18-digest-rule-under-the-clamped-trigger.md) R4.

**D5's successor is `cluster_high`, not `max(line, cluster_high)`** — the fitted line is anchored at
the cluster's max high with slopes constrained ≤ 0, so it can never exceed it. The open question
listed above ("D5's trigger rule is the decision most likely to look wrong") is therefore now a
question about the cluster parameters, which is ticket 19's. See 18 R1.
