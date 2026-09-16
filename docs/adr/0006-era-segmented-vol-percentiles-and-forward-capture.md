---
status: accepted
---

# Era-segmented volatility percentiles, with readings captured forward

## Context

The volatility state ranks the market index's 21-day realized vol against its own
history and words the result (spec §4.10). On IDX, daily moves are hard-capped by the
auto-rejection bands, and the band widths have been changed by decree four times since
2020 — most recently to an asymmetric 15% downside on 2025-04-08 (Kep-00003/BEI/04-2025).
A percentile ranked across those changes compares observations censored by different
amounts: the tight-limit eras make the past look artificially calm, so today reads as
more extreme than it is. The bias direction is known; its size is not.

Two histories were on the table for IDX: rank within the current ARB policy era only
(~17 months at decision time, growing daily), or rank across a longer span with the
worst-censored years excluded (longer, but still mixing limit regimes). US has no such
problem — circuit breakers halt trading rather than capping the printed move — so its
percentile uses one continuous rolling 3-year window either way.

Separately: the app computes regime state and breadth on read and persists neither.
Whether the volatility reading follows that precedent or is also recorded was its own
question, because a future era change makes retro-computation genuinely ambiguous — the
right denominator for a past session depends on an era table that itself changes.

## Decision

IDX percentiles rank **within the current ARB policy era only**, with the sample size
displayed beside the percentile so thinness is visible rather than hidden. Era
boundaries are decree dates, kept as a module constant, hand-verified against
idx.co.id (which blocks automated fetch); they are policy facts, not calendar data,
and are never inferred from bars.

The nightly pipeline also **captures each session's readings forward** into a
write-once table beside `follow_through`: raw 21-day vol, percentile, sample size,
era start, and the second-leg value. The state word is not stored — it is derivable
from percentile plus edges, and storing it would freeze a display convention into
historical rows. Display stays compute-on-read, like the regime.

## Consequences

- The IDX percentile is honest but coarse at first, and a future era change resets it
  to undefined for roughly three months (the 60-reading warm-up). That reset is the
  design working: the new era genuinely has no history.
- US and IDX carry the same signal name with different denominator quality. The
  visible sample size is the disclosure.
- The forward record is the only unbiased input a future vol-managed-sizing backtest
  can have; like follow-through, it is irrecoverable if not started at launch, which
  is why the schema was fixed before the first nightly run rather than iterated.
- Widening an era or adding one is a config edit plus a warm-up, not a redesign.
