---
status: accepted
---

# The study's survivorship hole is accepted, not closed

The replay store is built from today's listing snapshot, so it cannot see the names that
died. Measured against the reference set the hole is **91 of 312 tickers, 170 trades, 18.1%
of total realised R** (`references/blind_spot_tickers.json`), and it is not a random 18.1%:
the missing names are disproportionately the ones a momentum screener surfaces and that
later failed. Every field-derived result in `references/qullamaggie-replay-findings.md` is
bounded by it, the A2 ranking null most of all.

#129 proposed to close it by sourcing bar history that includes delisted and renamed
listings. **Decided (#129, closed as won't-do): the hole stands as documented.** No source
of delisted US daily bars for 2019–2022 is available at zero cost, and there is no budget
for one. The hole is therefore a permanent property of the study rather than a temporary
gap awaiting a ticket.

## Considered options

- **Buy delisted history.** Every provider that carries 2019–2022 delisted US bars is paid:
  EODHD, FirstRateData (~7,000 delisted tickers), HistoricalData.net, Nasdaq ZHDM. Retail
  tiers start around $100/month and rise to institutional pricing. Rejected on cost, and
  only on cost — this is the option that would actually work, and it remains the one thing
  that would reopen the question.
- **Free sources.** Free tiers give listing *identity* but not prices: FMP's delisted-companies
  API is explicitly reference data, and Tiingo's `supported_tickers` file carries per-ticker
  date ranges. Enough to explain *why* a ticker is blind, never enough to replay it.
- **Restrict the study to survivors.** Drop the 91 from the reference set and report on the
  221 that remain. Rejected: this converts a *disclosed* hole into a hidden one. The
  denominator would silently become "trades in companies that survived", which biases the
  reference set harder than the missing bars do, and the caveat would stop being visible in
  the figures.

## Consequences

- The blind-spot figures are a **standing caveat, not a TODO**. Coverage stays attached to
  every field-derived result as `blind_spot_count`, and no future reading of the findings
  should treat the hole as pending resolution.
- Results are bounded **directionally, not just in magnitude**. Because the missing names
  skew toward high-return names that later died, a finding's exposure to the hole depends on
  how those names would have *ranked*, which is unmeasurable without their bars. A2's null
  is the sharpest case: it is evidence against discrimination on the field we can see, and
  cannot become proof of its absence.
- The drift guard keeps the hole honest. `replay.reference.assert_matches_reference` raises
  `DriftError` if the recomputed counts move, so the figures cannot quietly shift under the
  study — a correction has to be a deliberate re-pin.
- Reversal is cheap in code and gated by money. Nothing here is baked into the schema; the
  replay store is rebuilt from a bar source by `replay.store.build_replay_store`. Buying
  history would require re-pinning the reference figures and re-deriving every field-derived
  figure in the findings document, but no redesign.
