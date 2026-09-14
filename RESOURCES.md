# Stock Trading with VWAP — Resources

All entries verified free and loading as of 2026-09-14 unless flagged. $0 budget applies (see MISSION.md).

## Knowledge

### Primary sources
- [Paper: "VWAP Strategies" — Ananth Madhavan, *Journal of Trading*, 2002](https://www.smallake.kr/wp-content/uploads/2016/03/TP_Spring_2002_Madhavan.pdf)
  Why institutions benchmark execution to VWAP and how that shapes their trading. Use for: understanding *why* price gravitates around VWAP — the order flow anchored to it.
- [Paper: "Volume Weighted Average Price Optimal Execution" — Busseti & Boyd (Stanford), arXiv:1509.08503](https://arxiv.org/abs/1509.08503)
  How VWAP-benchmarked algos schedule orders against the volume curve. Math-heavy; skim intro/conclusion. Use for: knowing the mechanical behavior of the algos on the other side of your trades.
- Berkowitz, Logue & Noser 1988 (*Journal of Finance*) — the paper that originated the VWAP benchmark. [Abstract only is free](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1988.tb02591.x); read Madhavan's summary instead. Use for: provenance/citation.

### Expert practitioner
- [Alphatrends free VWAP archive — Brian Shannon, CMT](https://alphatrends.net/archives/category/vwap/about-vwap/)
  The core practitioner curriculum: anchored VWAP from earnings/gaps/highs-lows, reading who is in control. **Use this archive URL** — the site's headline /anchored-vwap/ page is a sales funnel for the book/membership.
- [YouTube: Brian Shannon @alphatrends](https://www.youtube.com/@alphatrends)
  Near-daily free videos applying AVWAP live. Use for: watching entries/exits framed in real time. (Channel verified via [Wikipedia](https://en.wikipedia.org/wiki/Brian_Shannon).)
- [Article: "Why You NEED VWAP For Your Intraday Trading" — SMB Training](https://www.smbtraining.com/blog/why-you-need-vwap-for-your-intraday-trading)
  Three concrete intraday uses: relative strength vs. VWAP, trend confirmation, capitulation spotting. Their own caveat: VWAP is for confirmation and thesis-building, never a standalone signal. More at the [SMB VWAP tag archive](https://www.smbtraining.com/blog/tag/vwap).
- [Video: "The EASY Stock Trade You Need to Learn (2-Day VWAP)" — SMB Capital](https://www.youtube.com/watch?v=xesrK4KAzfM)
  One repeatable second-day VWAP-support playbook from a real prop desk. Use for: moving from concept to a concrete setup.
- [Article: "Reader question: is VWAP useful?" — Adam Grimes, 2015](https://adamhgrimes.com/reader-question-is-vwap-useful/)
  The skeptic's case: his testing found no statistical edge in VWAP touches vs. any other average. Use for: the counterweight — forces you to define what edge you're actually claiming. Deliberately included.

### Glossary tier
- [StockCharts ChartSchool: Volume-Weighted Average Price (VWAP)](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/volume-weighted-average-price-vwap)
  Cleanest free formula/mechanics reference: worked calculation, uses, limitations. Reach for this first for definitions.
- [StockCharts ChartSchool: Anchored VWAP](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-overlays/anchored-vwap)
  Neutral AVWAP mechanics companion to Shannon; notes that converging AVWAPs mark strong S/R zones.
- [Investopedia: VWAP](https://www.investopedia.com/terms/v/vwap.asp) — **unverified** (blocks our crawler); canonical slug. Prefer StockCharts, which covers the same ground and is verified.

## Wisdom (Communities)

- [Brian Shannon on X — @alphatrends](https://x.com/alphatrends)
  Highest-signal free feed for this topic: free annotated AVWAP charts near-daily. Use for: calibrating your own daily reads against his.
- [r/Daytrading](https://www.reddit.com/r/Daytrading/)
  Large and beginner-heavy; moderation is volume-oriented, signal-to-noise low. Use for: seeing common mistakes, not learning technique.
- [futures.io](https://futures.io/) — better-moderated forum with a trade-journal culture; VWAP threads skew futures. Requires free registration; current state unverified (bot-blocked).
- Elite Trader — skip: weak moderation, high vendor-shill ratio. Archives only.

## Gaps

- **No free structured intraday-VWAP course exists.** Shannon's structured material is behind his book/membership; the free path stitches his YouTube + archive + SMB blog. Lessons in this workspace fill that role.
- **No free quantitative evidence FOR discretionary VWAP entries.** Academic work treats VWAP as an execution benchmark, not an entry signal; the only free quantitative treatment found is Grimes's negative result. Keep this in view when forming conviction.
- Berkowitz/Logue/Noser full text is paywalled everywhere legal.
