# Market regime filter

Type: grilling
Status: resolved
Blocked by: 02

## Question

How does the app compute and present "is this a tape you should be swinging long in?"

§10 gives the rules qualitatively. Make them numeric:

- **Which index per market** — US: S&P 500, Nasdaq Composite, Russell 2000, or an equal-weighted
  breadth measure of your own universe? His names are small/mid momentum, so the S&P may be the wrong
  proxy. IDX: IHSG, LQ45, or a universe-derived breadth measure?
- **The gates** — §10's "do not swing long" is 10-day sloping down **and** 20-day sloping down **and**
  10 below 20. Define "sloping down" (slope over how many days, what threshold). Define the
  long-friendly condition symmetrically.
- **Three states or two** — long-friendly / choppy / don't-swing. "Choppy" is where he sits out, and
  it's the hardest to define. What makes a tape choppy numerically — whipsaw count, failed-breakout
  rate, index ADR, MA crossover frequency?
- **Breadth and follow-through** — "breakouts follow through" and "sectors moving in packs" are the
  signals he actually cites. The app can measure its own hit rate: what fraction of last week's
  detected breakouts are still above their breakout level? That's a strong regime signal and it's free
  once detection exists. Decide whether it's in v1.
- **What the app does with it** — a banner? A size multiplier on every candidate? Does a hostile regime
  suppress the candidate list entirely, or just annotate it? He does not stop looking; he stops sizing.
- **Per market independently** — IDX and US regimes diverge. Two separate verdicts, presumably; confirm.

Resolve against `references/qullamaggie-method.md` §10 and §2.

## Answer

Both markets get their own verdict, computed nightly from a single index each, using only sign-based
slope tests. No parameter on this ticket needs calibration, which is deliberate: nothing here can be
backtested, because delisted names return zero rows on Yahoo (ticket 02) and any historical series
rebuilt from today's universe is biased upward.

### Index per market

| Market | Index | Ticker |
| --- | --- | --- |
| US | Nasdaq Composite | `^IXIC` |
| IDX | IHSG (Jakarta Composite) | `^JKSE` |

Availability verified against the Yahoo chart endpoint already in use — `^JKSE`, `^GSPC`, `^IXIC`,
`^RUT` and `R-LQ45X.JK` all return full daily history, so this was a free choice, not a constrained one.

- **Nasdaq Composite over S&P 500**: `^GSPC` is cap-weighted into mega-caps and its 10/20-day slope can
  read healthy while small/mid momentum — the tape these candidates actually trade in — is in a
  downtrend.
- **Nasdaq Composite over Russell 2000**: `^RUT` fails the other way, dominated by unprofitable
  micro-caps and biotech that can sit in a downtrend for a year while momentum growth works, which would
  suppress sizing through a tradeable market.
- **IHSG over LQ45**: LQ45 is 45 large caps; the Rp 1B/day liquidity floor puts most IDX candidates
  outside it, so LQ45 would be measuring a different market from the one being screened.

### Moving averages and slope

§2 fixes the daily MAs as **simple** (the 65 EMA is the only exponential on the daily), so:

- `SMA10`, `SMA20` over index **daily closes**.
- **Rising** iff `SMA[t] > SMA[t-5]`; **falling** iff `SMA[t] < SMA[t-5]`. **Sign only — no magnitude
  threshold.** Five trading days is the natural resolution for a swing timeframe, and sign-only means
  there is no parameter to fit against an unbacktestable series.
- Hysteresis comes from the compound gate rather than from a deadband: the 20-day turns slowly, so the
  HOSTILE condition cannot flicker on a single bar.

### The three states

Evaluated independently per market, on the last **closed** session:

- **`HOSTILE`** — `SMA10` falling **AND** `SMA20` falling **AND** `SMA10 < SMA20`. (§10 verbatim.)
- **`FRIENDLY`** — `close > SMA10` **AND** `close > SMA20` **AND** `SMA10` rising **AND** `SMA20` rising.
- **`CHOPPY`** — everything else.

Chop is the **residual**, not a measured quantity. This is the load-bearing choice on the ticket: §10's
two named conditions are not complements, and the gap between them *is* chop — "false signals both ways,
I don't see an edge right now". Defining it as the residual adds **zero parameters**, maps §10
clause-for-clause, and fails safe, since a tape that cannot make up its mind lands in the cautious middle
by construction.

**No precedence rule is needed.** HOSTILE requires `SMA10` falling and FRIENDLY requires it rising, so
the two are mutually exclusive by construction; the three states partition the space exactly.

**Warm-up**: 25 index bars (`SMA20` plus the 5-day slope lookback). Below that, the state is undefined
rather than defaulted.

### What the app does with it

- A **persistent banner per market** — two banners, never combined into a global verdict. IHSG and the
  Nasdaq run on different cycles; a combined roll-up would require a combination rule with nothing to
  justify it, and would have a strong IHSG sat out because the Nasdaq rolled over.
- Each banner carries a **sizing posture**: `FRIENDLY` → full size, `CHOPPY` → reduced, `HOSTILE` → sit
  out. **Advisory words only, not a computed position size** — the §8 sizing calculator is out of scope,
  and this must not smuggle it back in.
- **The candidate list is identical in all three states.** Never filtered, never reordered by regime.
  This is the literal reading of §10 — *he does not stop looking, he stops sizing* — and it keeps the
  regime out of the detection path, so a bad regime call can never hide a setup.
- **The regime never touches the star score.** §3.5 grades the setup; a 5-star base is still a 5-star
  base in a bad tape, and folding regime in would destroy that distinction.
- The banner displays the **as-of session date** (see Dependencies).

### Breadth — shown, does not gate

Share of that market's tradeable universe above its own rising `SMA10`/`SMA20`, displayed beside the
banner. It is **not an input to the verdict** in v1.

The reason is specific, not caution for its own sake: **breadth is the measure survivorship bias corrupts
most directly.** Yahoo's screener enumerates only live names, so every historical breadth reading is
computed without the names that would have dragged it down — biased upward by a known but unmeasurable
amount. Any threshold picked today would be fitted to a series that is wrong in a known direction. It
costs nothing to compute (the universe is already pulled), so it goes on screen to be watched live and
promoted to a gate later, with evidence.

### Breakout follow-through — captured from day one, displayed later

Every detected setup and its **trigger level** is written to the store nightly, starting with the first
run.

- It is the **only regime signal here that is not survivorship-biased**, because it is recorded forward
  in real time rather than reconstructed from a surviving universe.
- It is **irrecoverable if skipped** — it cannot be rebuilt from Yahoo after the fact, so the clock has
  to start at launch.
- It needs months of history before the number means anything, so **no live reading and no gate in v1**.

This mirrors the nightly listing-file snapshot already assigned to ticket 12, and it is a genuine
contribution to the validation problem sitting in the map's fog.

### Dependencies handed to other tickets

- **Ticket 08 (setup detection)** owes this ticket a defined **trigger level** per detected setup — the
  quantity the follow-through capture records and later measures against.
- **Ticket 12 (architecture)** owes this ticket a **nightly setup-snapshot table** (symbol, date, trigger
  level) alongside the listing-file snapshot it already carries.
- **Ticket 05 (universe and data hygiene)** owns the **partial-last-bar** hazard from ticket 02 — a daily
  bar can be dated as complete while a session is still open. The regime must evaluate the last *closed*
  session and surface its date; how "closed" is determined per market calendar is settled there, not here.

### Explicitly rejected

- **Breadth replacing the index** — bets the whole filter on the measure the bias hits hardest.
- **Follow-through as a gate** — downstream of ticket 08, the highest-risk ticket on the map; a detection
  bug would silently corrupt the regime call too.
- **Hostile regime suppressing the candidate list** — contradicts "he does not stop looking", and the
  best setups often form during the hostile stretch that precedes the turn.
- **A continuous 0–100 regime score** — nothing in §10 to calibrate a continuous scale against.
- **Explicitly measured chop** (index ADR, crossover counts) — thresholds picked blind that can then
  contradict the slope gates.
