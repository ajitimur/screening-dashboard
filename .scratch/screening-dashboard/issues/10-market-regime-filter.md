# Market regime filter

Type: grilling
Status: open
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
