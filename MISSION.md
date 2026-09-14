# Mission: Stock Trading with VWAP

## Why
Trade intraday with VWAP as a live decision tool — not just display it on a chart, but use it to time entries and exits and to read whether buyers or sellers are in control of a session. The end state is discretionary trades where VWAP is doing real work in the decision.

## Success looks like
- Look at any intraday chart with VWAP and state, in one sentence, who is in control and why
- Plan an entry using VWAP (e.g., a pullback-to-VWAP long in an uptrending session) with a defined invalidation point before entering
- Explain why institutions benchmark to VWAP, and use that to reason about where large-participant interest sits
- Use anchored VWAP from a meaningful event (earnings, breakout day, swing low) to find support/resistance that ordinary indicators miss
- Review past trades and articulate whether the VWAP read was right or wrong, separately from whether the trade made money

## Constraints
- $0 budget for data vendors and courses — free resources only
- Already builds trading software (screening dashboard, backtests over intraday sessions), so is comfortable with quantitative framing; don't dumb down the math, but the goal is trading skill, not implementation
- Learning happens in short sessions alongside project work

## Out of scope
- Implementing VWAP in the screening-dashboard codebase (may become a later mission; keep teaching platform-agnostic for now)
- VWAP execution algos from the sell-side/broker perspective (understand *why* they exist, but not how to build one)
- Options, futures, crypto — stocks only for now
