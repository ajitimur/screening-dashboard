# What does "tight" actually mean in Qullamägi's trades?

*Plain-language version. The same study written in the project's usual technical
register is in [FINDINGS.md](FINDINGS.md) — same numbers, same conclusions.*

**This is a throwaway experiment.** Nothing here runs inside the app. Once the
lesson is folded into the real code, this folder can be deleted.

---

## Two words you need first

**ADR — the stock's average daily swing.** How far a stock typically travels
between its low and its high in a single day, averaged over the last 20 days.
It's used as a measuring stick so a wild stock and a sleepy one can be compared
fairly. "1.3 ADR" means *about one and a third normal days of movement*.

**R — profit compared to what was risked.** If you plan to lose $100 if you're
wrong, then making $200 is "2R". Losing the planned amount is "−1R". It lets you
compare a big trade and a small one on equal terms.

---

## The question

Before the app suggests a stock, it checks whether the stock has gone *quiet* —
whether the last few days have been unusually calm, coiled up before a move.
Right now the rule is:

> Look at the last 3 to 7 days. If any of those stretches covers **1.5 ADR or
> less**, the stock counts as quiet. Otherwise, reject it.

That number, 1.5, was inherited from an older tool. Nobody had ever checked it
against what Qullamägi's own trades actually looked like. So that's what this
does.

## How it was measured

For each of his 828 recorded trades, go back to the day *before* he bought — the
last day the app could have spotted anything — and measure how much ground the
stock covered over the previous 3, 4, 5, 6 and 7 days.

Crucially, **nothing was filtered during measurement.** Every trade's raw numbers
were recorded, so any cutoff can be tested afterwards without redoing the work.

**How many trades this covers: 649 of 828 (78%).** The missing 179 are almost all
companies that have since been delisted, so there's no price history left for
them. A handful were too new to have enough history.

---

## What was found

### 1. "Tight" usually means about 1.3 ADR over three days

That's the typical trade. But he's far from strict about it:

| | quietest of his trades | typical | looser end | loosest quarter |
|---|---|---|---|---|
| ground covered in 3 days | 0.80 ADR | **1.31 ADR** | 1.73 ADR | above 2.16 ADR |

Read the middle column as: *in a typical buy, the previous three days together
covered only about one and a third days' worth of normal movement.* Genuinely
coiled up.

But a quarter of his buys were looser than 1.73, and some were much looser. So
"tight" describes his **habit**, not a line he refuses to cross.

### 2. The current 1.5 cutoff isn't wrong — but it isn't special either

It sits partway up his own range. About 64% of his trades are quieter than it;
the other **231 of his real trades would be rejected** by it.

And there's no natural break in the data at 1.5. If you look at the chart of all
his trades, the shape flows straight through that point — no cliff, no gap,
nothing to suggest the stock behaves differently on either side. The number is
reasonable, but it's a choice, not a discovery.

### 3. Quieter really is better — but it fades gradually

Group his trades by how quiet the stock was beforehand, and the results decline
steadily:

| how quiet beforehand | number of trades | average result |
|---|---|---|
| very quiet (under 1.0 ADR) | 164 | **+2.02R** |
| quiet (1.0–1.5) | 254 | **+1.35R** |
| middling (1.5–2.0) | 139 | **+0.84R** |
| loose (2.0–3.0) | 82 | **+0.35R** |
| very loose (over 3.0) | 10 | **−0.36R** |

Quietness clearly matters — the quietest group earned nearly six times the
looser ones. **But notice the decline is smooth.** There's no sudden collapse at
1.5. A trade at 1.6 performs almost identically to one at 1.4.

**This is the main finding: quietness deserves to be a *score*, not a door.**
Right now it's used as pass/fail, which throws away a third of his trade style to
capture something that could be measured on a sliding scale instead.

> **An important quirk of his trading:** most of his trades *lose*. The typical
> trade in every single group above hits its stop-loss and loses exactly what was
> risked. He makes money because the occasional winner is enormous. That's why
> this table uses averages — if you looked at the "typical" trade instead, every
> group would look like a loss, and you'd wrongly conclude nothing works.

### 4. The technical constants do two different jobs

Small but useful: the rule says "check stretches of 3 to 7 days." It turns out
the 3-day stretch is *always* the quietest one — it can't be otherwise, since a
longer stretch can only include more movement, never less. Confirmed on all 649
trades.

So the "7" never decides whether a stock passes or fails. It only affects the
*score* the stock gets afterwards. The two numbers look like a matched pair in
the code, but they're doing unrelated jobs — worth renaming so nobody assumes
otherwise.

### 5. His stop-loss is a totally separate — and much smaller — number

You'd reasonably assume he puts his stop-loss just below the quiet zone. **He
doesn't.**

| | typical |
|---|---|
| width of the quiet zone | 1.31 ADR |
| **his actual stop-loss distance** | **0.38 ADR** (about 2.3% below his buy price) |
| how far his stop sits *above* the zone's floor | 0.99 ADR |

His stop is roughly **a third** of the quiet zone's width, sitting comfortably
*inside* it rather than beneath it. He's risking that single day's move, not the
whole base.

So two very different things share the word "tight": how calm the stock has been,
and how little he's willing to lose. They differ by about 3.5×. Confusing them
would roughly **triple the risk on every trade** — worth keeping as separate,
separately-named ideas.

*One data caveat:* the trade records store original prices, while the price
history has been adjusted for stock splits. For any company that split after the
trade, those two are on different scales. So 173 trades were excluded **from the
stop-loss figures only**. All the quietness measurements come purely from price
history and aren't affected by this at all.

---

## The bottom line

**"Tight" means the last three days covering roughly 1.3 ADR or less** — about
one and a third normal days of movement compressed into three. That's his centre
of gravity, not a rule he obeys.

**And quietness should be scored, not gated.** It's a genuinely strong signal,
but a gradual one. The current hard cutoff at 1.5 discards 231 of his own trades
— roughly a third of his style — to capture something that varies smoothly.

This *supports* rather than contradicts the earlier recommendation in
`references/qullamaggie-replay-findings.md` to leave the window alone. That
advice rested on quietness being a real signal, which this confirms and
strengthens. What's new is that we can now measure what the hard cutoff costs.

### Suggested next steps (decisions for a human, not things I changed)

1. Let quietness score on a sliding scale instead of pass/fail, and loosen the
   rejection cutoff to something that only catches genuine outliers.
2. Rename the "quietest stretch" measurement to what it really is — the 3-day
   range — and note in the code that the "7" can't affect pass/fail.
3. Keep "how calm the stock is" and "how much he risks" as two clearly separate
   named concepts. They are not the same measurement.

## What this study can't tell you

Every number here comes from stocks he **bought**. It says nothing about the
quiet, promising setups he looked at and decided to skip — that comparison is a
separate piece of work already covered elsewhere in the project.

---

## Trying it yourself

Open **`tightness.html`** — one self-contained file, just double-click it. Drag
the slider to any cutoff and watch how many of his trades survive and how the
results shift. Five tabs walk through each finding above.

To rebuild the data from scratch:

```
backend/.venv/bin/python backend/replay/prototype-tightness/measure_tightness.py
backend/.venv/bin/python backend/replay/prototype-tightness/build_html.py
```
