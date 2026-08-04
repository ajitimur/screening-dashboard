# Universe definition and data hygiene

Type: grilling
Status: resolved
Blocked by: 01, 02

## Question

What exactly is "the tradeable universe" for each market, and what gets thrown out before anything is
ranked?

The method reference fixes the two floors (§1): US ≥ $20M/day average dollar volume, IDX ≥ Rp 1B/day,
and ADR ≥ 4–5%. This ticket settles everything around them:

- **Floor mechanics** — average dollar volume over what window? Median instead of mean, given IDX spikes?
  Is the ADR floor a hard universe gate or a per-setup gate (it appears in both §1 and §3.5)?
- **Which floor binds** — the reference warns that on IDX, position value ≤ 5–10% of average daily value
  traded binds before the Rp 1B floor once the account grows. Does the universe encode that, and does
  the app need to know the account size to do it?
- **US numbers are concrete (ticket 02):** Nasdaq Trader listing files enumerate **5,711 symbols** after
  filtering, and carry an `ETF` flag that separates funds cleanly — so the instrument-filtering question
  below has a ready mechanism on the US side. The equivalent IDX filter is the screener's
  `quoteType: EQUITY` (ticket 01).
- **Instrument filtering** — common stock only? Exclude ETFs, funds, REITs, warrants, rights, preferred?
  Sector-proxy ETFs are wanted for the rotation view but not as candidates — one universe or two?
- **Minimum listing age** — how much history before a name is rankable at all, and what happens to a
  90-day-old IPO that's up 300% (exactly the kind of name he'd want).
- **IDX-specific exclusions** — suspended names, ARA/ARB limit days, "papan pemantauan khusus" (special
  monitoring board), full-call-auction names, no-trade days. Which of these disqualify and which are
  just gaps to handle.
- **Adjusted vs raw prices** — returns want adjusted; ADR and gap math arguably want raw. Which series
  feeds which computation, and what happens on a rights-issue day.
- **Rebuild cadence** — is the universe recomputed nightly, or pinned weekly so rankings stay stable?
- **Expected size** — roughly how many names survive per market. His tradeable US universe at size is
  ~150 stocks; is that the shortlist or the universe?
- **The IDX enumeration gap — answered by ticket 01.** Yahoo's 840 vs IDX's 963 listed is explained:
  the missing ~120 are suspended or delisted. Not a coverage gap for tonight's scan; it *is*
  survivorship bias for any backtest (see the validation fog patch). Nothing to decide here beyond
  acknowledging it.
- **IDX numbers are now concrete (ticket 01):** 840 enumerable, **292 clear the Rp 1B/day floor** using
  `Close × Volume` (volume is shares, not lots — verified). Decide whether 292 is the universe you want
  or whether the floor needs moving.
- **Adjusted vs raw on IDX is not a free choice (ticket 01).** Yahoo applies rights adjustments
  invisibly and unauditably, so raw traded prices are **unrecoverable**. Momentum/MA/consolidation math
  is unaffected; any rule referencing an absolute real-world price level (tick bands, ARA/ARB
  reconstruction) cannot be implemented on IDX history. Decide what depends on that.
- **Phantom bars (ticket 01)** — 4.0% of IDX bars have `Volume == 0`, and suspended names emit *more*
  bars than active ones. Define the drop rule here, since every downstream computation inherits it.
- **Throttling vs. missing data (from ticket 03)** — Yahoo rate-limits after ~200 rapid calls and
  **fails as silence**, returning empty rather than erroring loudly. Any universe-construction step
  must treat "no data" as suspect until proven, or a throttled run will silently shrink the universe.

Resolve against `references/qullamaggie-method.md` §1, and against whatever the data-source research
says is actually obtainable.

**Raised by ticket 10 (market regime filter):** the regime needs the last **closed** session per market
and must surface its date. D8 below settles it for every consumer of the latest bar — non-final bars are
dropped at ingest on an exchange-clock rule, so nothing downstream ever sees a partial session.

## Answer

Resolved 2026-08-04 in a grilling session. Thirteen decisions below. Every number in the "Measured"
section was produced during this session against live Yahoo data (`yfinance 1.5.2`, throwaway venv,
nothing installed into the project) by applying the rules exactly as decided — so the universe sizes
are observations of *this* rule stack, not estimates.

A principle emerged across the answers and is worth stating once, because three separate rules are
instances of it: **removal requires stronger evidence than admission.** Sticky membership (D7),
the asymmetric hysteresis band (D11) and the post-rank ADR filter (D3) all encode it. Admitting a
marginal name shows you something you can dismiss with your eyes; removing one hides it forever.

### D1 — One instruments table with a `role` column, not two universes

`role` is `candidate` or `reference`. Sector-proxy ETFs are ingested as `reference` — computed like
anything else, never rankable. Floors filter `role = candidate`.

Rationale: ingestion, bar storage and ADR/return math are identical for `XLE` and `AAPL`; two
universes duplicate all of it for nothing. Membership stops being the thing that encodes tradeability
— the floors do that. Role is free at enumeration on both sides: the Nasdaq Trader `ETF` flag on US,
`quoteType: EQUITY` on IDX.

**Hand-off to ticket 07:** IDX has essentially no sector-ETF `reference` set, so the rotation view
will likely need a *computed* sector index there rather than a proxy instrument.

### D2 — Liquidity floor is the **median** of `close × volume` over the trailing **20 traded bars**

Median, not mean. 20 bars to match ADR's `SMA20`, so one window constant across the app.

Rationale: on IDX a Rp 200M/day name that prints one Rp 40B block trade clears a 20-day *mean* of
Rp 1B on that single bar without having become tradeable. The median asks "on a typical day, is there
Rp 1B here?", which is the question the floor exists to answer.

**Correction to an in-session claim:** the median was predicted to bind "meaningfully tighter" than
ticket 01's single-day rule. Measured, it binds ~14% tighter (288 vs 336 on the same day) — real, but
much less than predicted.

### D3 — ADR is **not** a universe gate; it is a post-rank filter, default on at ≥ 4%

Universe = liquidity + instrument type + listing age. ADR filters the ranked list and is toggleable.

Rationale, strongest first:
- **Decile denominators must be stable.** Ranking is against the whole tradeable universe per market.
  If ADR gates membership, the denominator breathes with the volatility regime — in a dead tape the
  universe shrinks and a name's decile rank improves without the name doing anything, so rankings stop
  being comparable across time. Liquidity is stable enough to gate on; volatility is not.
- **An ADR gate is structurally late.** A 3.5-ADR name that starts moving is a name whose ADR is
  *becoming* 8. Gating evicts it on the eve of the move and readmits it ~20 bars later, after the
  setup. The method exists to catch stocks that just woke up.
- **§3.5 already prices ADR** as a scored dimension. Gating too means low-ADR names never reach the
  rubric designed to penalise them, making that dimension near-constant across everything you see.

### D4 — The IDX sizing caveat is **not** encoded in the app at all

No gate, no `account_size` config, no warning badge. The app surfaces median-20d dollar volume on the
candidate row; the ≤ 5–10%-of-ADV participation rule is applied by the trader at entry.

Rationale: encoded as a gate, decile ranks would shift when the account is *funded* — names vanishing
from the leaderboard because the account grew. Rejected as a badge too: it is a rule the trader already
applies, and §8 (position sizing) is out of scope on this map.

### D5 — Minimum listing age: one low universe gate, then per-lookback eligibility

Universe gate: **≥ 20 non-phantom bars** (the minimum for ADR and median dollar volume to exist).
Ranking: each lookback ranks only names with that much history. A 90-day-old IPO appears in the 1m and
3m leaderboards and is **absent** — not zero-filled, not backfilled — from 6m/12m/18m/24m.

Rationale: a single global gate forces a false choice — 24 months never shows a recent IPO (which the
method wants), 20 days fills the 12-month board with 4-month names carrying garbage returns. Partial-
window returns are *systematically* extreme, so they'd colonise the top decile on noise and train the
user to ignore the top rows. Per-lookback denominators differ, which is correct: they're different
questions.

Also: a **"recent listing" marker** for names under ~12 months of bars — a flag, never a disqualifier.

**Fact, not assumption:** neither source gives a true listing date (Nasdaq Trader files don't carry
one; Yahoo doesn't expose it reliably), so **listing age = date of first available bar**. On IDX that
proxy floors at 2000 (ticket 01 measured Yahoo's IDX history as effectively beginning then) — harmless,
26 years past any threshold.

### D6 — Phantom bars are dropped; a density gate doubles as suspension detection

1. A bar is phantom if `volume == 0`. It is **removed from the series** — never zero-filled, never
   carried forward — before ADR, tightness, returns or dollar volume.
2. Windows count **traded bars**, not calendar days.
3. **Density gate:** a name stays in the universe only if ≥ 16 of the market's last 20 sessions were
   non-phantom for it *and* its most recent final bar is within 3 sessions of the market's latest.

Rationale:
- A no-trade bar prints `high == low == close`, contributing exactly 0 to `SMA20(high/low − 1)` and
  dragging ADR toward zero. A thin name would screen as "slow" because it didn't trade.
- Dropping alone opens a hole, which is what part 3 closes: in pure traded-bar space, a name suspended
  for eight months with 20 scattered trades has a well-formed 20-bar ADR and would sail in on stale data.
- **The density gate removes the need for a suspension list, which is unobtainable anyway** (ticket 01
  measured idx.co.id as Cloudflare-403 to every server-side request). "Hasn't traded in 3 sessions" is
  the *behaviour* we care about, and it catches suspensions, monitoring-board illiquidity and quiet
  delistings identically, with nothing to maintain and nothing to go stale. An official list would tell
  us less.

**No trading-calendar dependency:** "the market's last 20 sessions" is the union of bar dates across
that market's universe on the night's pull. That *is* the exchange calendar, observed — it costs nothing
and cannot drift, which a hardcoded two-exchange holiday table certainly would.

Thresholds 80% / 3 sessions are defaults, not sacred.

### D7 — Throttle-silence: absence of data means nothing; incomplete runs don't publish

1. Zero rows is **`unresolved`**, a third state — never `absent`. Retried with backoff.
2. **Sticky membership.** A name leaves the universe only on positive evidence — real bars failing the
   density gate. Never because a fetch failed. `unresolved` names carry yesterday's classification
   forward, visibly stale-marked.
3. **Run-level completeness gate.** If < ~99% of enumerated symbols resolve after retries, the run is
   **quarantined**: it does not replace the universe or the leaderboard. Last good run stands, bannered.
   (Ticket 02 measured 99.93% at 12 req/s, so this is a low bar in practice.)
4. **Enumeration is checked too.** A materially smaller symbol list than the last good run is a failed
   run, not a shrinking exchange.

Rationale: missing data and a dead stock produce byte-identical responses, so no per-symbol care can
separate them — the only robust move is to make the ambiguous signal non-actionable. Rule 2 is
load-bearing; 1/3/4 are plumbing. Silent shrinkage is worse than a failed run *because it looks like
success*: a smaller universe makes every decile easier to reach, pushing junk onto the leaderboard with
nothing anywhere saying "this is wrong". Rule 4 exists because per-symbol failures are countable against
a known denominator, but a truncated enumeration moves the denominator itself and passes rule 3 at 100%.

### D8 — Provisional bars are dropped; finality is keyed to the exchange clock

A bar dated `D` is final iff, in that exchange's local timezone, `now > D's normal session close + 30
min`. Non-final bars are **discarded at ingest** — not stored as provisional, not shown flagged.

Rationale: ticket 02 *proved* this (14 minutes of trading served as a full day), and a partial bar
corrupts ADR, dollar volume and tightness simultaneously — on today's bar, the one weighted most. It
cannot depend on the schedule because the app runs **locally**, invoked at any hour; keying to the
exchange clock makes results identical regardless of when it's run. Store-and-flag was rejected: it
obliges every downstream computation to remember to exclude, forever, and the one that forgets fails
silently — precisely the bug class this ticket fights. One filter at ingest is one place to be right.

Interacts with D6: "latest traded bar within 3 sessions" counts **final** bars.

Two facts checked so no table is needed:
- **US half-days need no handling.** Early closes are at 13:00 ET, so a rule keyed to the normal 16:00
  close + 30 min errs in the safe direction — it waits longer than necessary, never shorter.
- **IDX is clear:** ticket 01 measured the 2026-08-04 bar present at 19:49 WIB against a 16:00 close.

### D9 — Adjusted everywhere, except dollar volume; and **no absolute-price rules in v1**

- **Adjusted series** for returns, MAs, gaps, contraction, ADR, tightness.
- **Unadjusted `close × volume`** for dollar volume.
- **Store both** series (raw OHLC + `Adj Close` + dividends + splits arrive in one Yahoo call).
- **No minimum price filter, no absolute-price rule anywhere.**

Rationale — this reframes ticket 01's scariest finding as mostly harmless:
- **Nearly every quantity in the method is a ratio, and ratios are invariant to multiplicative
  adjustment.** ADR is `SMA20(high/low − 1)`; scale by 10/11 and `high/low` is unchanged. Percentage
  range, distance-to-MA, tightness, percentage returns: all invariant. **The BBRI 10/11 rights rescale
  changes no number we compute.**
- Adjustment bites in only two places. First, at a corporate action *inside* a window — raw prints an
  ex-dividend gap that never traded and a split cliff; adjusted removes both correctly, so **adjusted
  wins for anything spanning history**.
- Second, absolute price levels — and **v1 has none**. Tick bands and ARA/ARB reconstruction are
  already unimplementable (D10). A minimum price filter is also rejected: the dollar-volume floor
  excludes penny junk far more precisely, and on IDX low nominal prices are normal (a Rp 50 stock is
  not a US-sense penny stock). With no absolute-price rule in the system, "raw IDX prices are
  unrecoverable" costs exactly nothing.
- **Dollar volume is the real exception:** Yahoo rescales prices for corporate actions but leaves
  volume alone, so `adjusted close × raw volume` is wrong by the adjustment ratio for all pre-event
  history. Identical within a clean 20-day window; only the unadjusted product is meaningful across one.

### D10 — No IDX-specific exclusion mechanics. Built deliberately, not omitted

Three of the ticket's five IDX hazards are already dead: **suspended** → D6 density gate, **no-trade
days** → D6 phantom drop, **delisted** → D7 sticky membership + enumeration check. The other two:

**Special monitoring board / full call auction — no exclusion.** The authoritative list is on
idx.co.id (Cloudflare-403), and neither ticket 01 nor 03 surfaced a board/segment field from Yahoo, so
any rule would be a guess dressed as a filter. Not needed: call-auction names fail the Rp 1B median or
the 80% density gate. And the converse is the real defence — a monitoring-board name that *does* clear
a 20-day median of Rp 1B across 16 of 20 sessions is genuinely liquid, and excluding it would be
excluding a real name on a label rather than its behaviour.

**ARA/ARB limit days — not handled here; stays in fog for ticket 08.** Detection needs the auto-reject
band (tiered by price and board; table on the blocked idx.co.id), and per D9 raw IDX prices are
unrecoverable so bands can't be inferred from history. A genuine dead end on free data, not an unmade
decision. The distortion runs in the safe direction: a limit-locked bar has a collapsed high/low range,
so it **understates** ADR — risking a missed candidate, not a bad one promoted.

**Accepted residual risk: a limit-locked IDX name may screen as low-ADR and we will not know.**

### D11 — Nightly rebuild, with an asymmetric hysteresis band and nightly membership snapshots

Rebuild nightly. A name **enters** at ≥ 1.0× the floor and **leaves** only below **0.8×**. Snapshot
universe membership nightly, one row per name per night.

Rationale: pinning weekly is stale in exactly the wrong direction — a name that just became liquid is a
name that just started attracting money, which is the signal; and since data is pulled nightly anyway,
pinning buys no compute saving. But a hard threshold plus nightly rebuild produces boundary churn:
names entering and exiting night after night with no change in price action, each transition moving the
decile denominator and re-ranking everything. Measured: **25 IDX names and 141 US names** sit in the
0.8–1.0× band — small enough to confirm the band is a targeted fix, not a blunt one.

The band is asymmetric by design (easy in, sticky out), consistent with D7 and D3.

Snapshots are the only way any future validation can ask "what was rankable that night" — the one thing
we can start accumulating today for free against the survivorship-bias problem. Complements the nightly
listing-file snapshots already assigned to ticket 12.

### D12 — Floors kept at their reference values: **Rp 1B/day** (IDX) and **$20M/day** (US)

And **§1's "~150 stocks" is his shortlist, not his universe** — the floors are not tuned to hit it.

Rationale: §1's 150 is what survives liquidity *and* ADR ≥ 4–5% *and* his account size. Ours is the
liquidity-only population, since D3 moved ADR downstream and D4 dropped account size entirely — a
different stage of the funnel, so matching the numbers would mean over-filtering by two criteria
deliberately moved elsewhere.

288 IDX names gives a ~29-name top decile — reviewable nightly. At Rp 5B it'd be 165 names, so a decile
is 16 and the ranking gets coarse and jumpy at the boundary. At Rp 500M it'd be 364, but the extra 76
are names the trader's own participation rule makes untradeable anyway — extra rows, diluted deciles.

The floor is one config number over a nightly-rebuilt universe. Ticket 08's detection work will say far
more about whether 288 is the right pool than more reasoning here.

### D13 — Instrument filtering: **common stock only**

Excluded by security-name pattern: **warrants, rights, units, notes/bonds, preferred, trusts/funds.**
**ADRs are kept** — they are common equity and are not in any excluded class.

This was a stricter cut than initially recommended, chosen deliberately by the trader: "exclude them
all, i want stocks only."

**A defect found by measuring rather than reasoning, recorded because it nearly shipped:** the first
preferred pattern included `Depositary Sh`, but "American Depositary Shares" is the **ADR** structure.
That regex would have deleted **BABA, ARM, SE, PDD, NOK, SHEL, JD, VALE, UL, INFY, ARGX, SIMO** from the
universe — the most liquid, highest-ADR names the method exists to trade. Corrected to
`\bPreferred\b|\bPfd\b`, which rescued **278 names**.

**Accepted costs, named rather than hidden:**
- Excluding trusts/funds on a name match deletes **NTRS (Northern Trust)** — an operating bank caught by
  its legal name — plus ~22 liquid REITs/BDCs (DLR, ESS, CPT, FRT, ARCC).
- Excluding units deletes **MLP common units** (ET at ~$179M/day, MPLX at ~$88M).
- Excluding preferred deletes **ITUB and BNS**, whose US lines are preferred-share ADRs and are the
  primary way to trade those issuers.

**⚠ This is the only non-behavioural rule in the entire ticket** — every other rule tests what a name
*does*; this one matches its name. It misfires in both directions and **needs a spot-check against the
surviving list on the first real pipeline run.**

**Low stakes, worth knowing:** the whole instrument-type question moves ~38 names out of 2,004 (1.9%)
on US. The liquidity floor and density gate do nearly all the work.

---

## Measured — universe sizes under this exact rule stack

Live Yahoo data, 2026-08-04, `yfinance 1.5.2`. Stage order: enumerate → drop phantom bars → density
gate → median-20d floor → instrument-type exclusion.

| stage | IDX | US |
|---|---|---|
| enumerated | 840 (`quoteType: EQUITY`) | 6,944 (non-ETF, non-test) |
| ≥ 1 non-phantom bar | 840 | 6,789 (97.77%) |
| passing density gate | 831 | 5,937 |
| median-20d ≥ floor | 288 (Rp 1B) | 2,004 ($20M) |
| **after D13 instrument exclusion** | **288** | **1,966** |
| in 0.8–1.0× hysteresis band | 25 | 141 |

Floor sensitivity (median-20d, post-density):

| IDX floor | survivors | | US floor | survivors |
|---|---|---|---|---|
| Rp 0.5B | 364 | | $10M | 2,437 |
| **Rp 1B** | **288** | | **$20M** | **2,004** |
| Rp 2B | 228 | | $50M | 1,390 |
| Rp 5B | 165 | | $100M | 928 |
| Rp 10B | 109 | | | |

Two observations from the measurement:

- **The density gate's value is market-asymmetric.** It removed 9 names on IDX but **852** on US. Yahoo's
  IDX screener already returns only actively-traded names, whereas the Nasdaq Trader files carry a long
  tail of barely-traded instruments. On IDX the gate is a *guard* against future suspensions; on US it is
  a bulk filter doing real work tonight.
- **Instrument-type filtering is nearly cosmetic** next to the liquidity floor (1.9% of US names).

## Findings handed to other tickets

- **→ Ticket 06 (ranking and decile model): "top decile" is probably the wrong cut on US.** A decile of
  1,966 is ~197 names — unreviewable in a 10-minute nightly pass, and lopsided against IDX's ~29. §1
  gives a tighter native definition: a momentum leader is the **top 1–2% of gainers**, which on ~2,000
  names is ~30 — matching IDX's decile almost exactly. Ticket 06 should decide between a percentile that
  is constant *in rank* vs constant *in count* across two markets of very different size.
- **→ Ticket 06: per-lookback denominators differ** by construction (D5). Ranking must handle a universe
  whose size varies by lookback.
- **→ Ticket 08: ARA/ARB limit days** remain undecided and unimplementable on free data (D10). Whether
  contraction/tightness need to handle them is ticket 08's call.
- **→ Ticket 07: IDX has no meaningful sector-ETF `reference` set** (D1) — rotation there likely needs a
  computed sector index.
- **→ Ticket 12: history depth** is now specifiable and lands there (see map fog graduation).

## Probe scripts

Disposable, in the job scratch dir — `idx_universe.py`, `us_universe.py`, `us_instrument_types.py`,
`us_noncommon_liquid.py`. Nothing was installed into the project.
