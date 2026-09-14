# Mission: Swing Trading with VWAP

## Why
Swing trade — holds of days to weeks — with anchored VWAP as a live decision tool: not just a line on the chart, but the thing that times entries and exits and says whether buyers or sellers control the move since a meaningful event (earnings, breakout, swing low). The end state is discretionary swing trades where AVWAP is doing real work in the decision.

## Success looks like
- Look at a daily chart with an anchored VWAP and state, in one sentence, who has controlled the move since the anchor and why
- Choose defensible anchor points (earnings gaps, breakout days, major swing highs/lows) rather than arbitrary ones
- Plan a swing entry using AVWAP (e.g., a pullback to a rising earnings-anchored VWAP) with a defined invalidation on daily closes before entering
- Explain why institutions benchmark to VWAP, and use that to reason about where large-participant interest sits across a multi-day move
- Review past trades and articulate whether the AVWAP read was right or wrong, separately from whether the trade made money

## Constraints
- $0 budget for data vendors and courses — free resources only
- Already builds trading software (screening dashboard, backtests over intraday sessions), so is comfortable with quantitative framing; don't dumb down the math, but the goal is trading skill, not implementation
- Learning happens in short sessions alongside project work

## Out of scope
- Intraday/day trading with session VWAP — understand it exists, but the craft being built is multi-day
- Implementing VWAP in the screening-dashboard codebase (may become a later mission; keep teaching platform-agnostic for now)
- VWAP execution algos from the sell-side/broker perspective (understand *why* they exist, but not how to build one)
- Options, futures, crypto — stocks only for now
