# Setup detection algorithm — making the breakout/continuation computable

Type: grilling
Status: open
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
