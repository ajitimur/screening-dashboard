# Universe definition and data hygiene

Type: grilling
Status: open
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

**From ticket 10 (market regime filter):** the regime evaluates the last **closed** session per market
and surfaces its date. Determining "closed" — the market-calendar rule that distinguishes a complete
daily bar from the partial one ticket 02 proved Yahoo will hand you mid-session — is settled *here*, and
applies to every consumer of the latest bar, not just the regime.
