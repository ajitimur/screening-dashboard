# PROTOTYPE — What does "tight" mean in Qullamägi's own trades?

**Throwaway.** Nothing here is imported by the app. Delete the directory once the
verdict is folded in.

*A plain-language version of this study — same numbers, same conclusions, no
jargon — is in [FINDINGS-plain.md](FINDINGS-plain.md).*

## The question

`detection.py` gates on a trailing 3–7 bar window spanning `<= TIGHT_MULT x ADR`
with `TIGHT_MULT = 1.5`, and `score.py` scores tightness as `cluster_k >= 5`
(`TIGHT_K`). Both are borrowed defaults from q-scanner-v2 — no one had checked
them against the geometry his actual entries had. This measures it.

## Method

For each of the 828 trades in `references/trades_bo_gain10smaPct_desc.json`, walk
to the **evaluation session** — the last session strictly before entry, the same
convention `replay/funnel.py` uses — and record the raw trailing k-bar range in
ADR for every k in 3..7, plus his own stop and entry in the same units. ADR is
`SMA20(high/low - 1) x close`, as in `screener/indicators.py`. Nothing is gated
at measurement time; the HTML re-derives pass rates for any threshold.

**Coverage: 649 / 828 (78.4%).** Skipped: 170 tickers absent from the bar store
(mostly delisted), 7 with under 20 bars of history, 2 with no prior session.
Bars span 2019-04-01 → 2022-12-30.

## Findings

### 1. "Tight" is a median of 1.31 ADR, not a threshold

The tightest trailing window his entries offered:

| | p10 | p25 | median | p75 | p90 | max |
|---|---|---|---|---|---|---|
| tightest 3–7 bar range (ADR) | 0.80 | 1.00 | **1.31** | 1.73 | 2.16 | 5.09 |

`TIGHT_MULT = 1.5` sits at roughly his **64th percentile** — it keeps 418 of 649
and turns away 231 of his own trades. The histogram has no gap, shoulder or
inflection at 1.5. Nothing in his record marks that spot.

### 2. `cluster_min_range_adr` is just the 3-bar range

Range is monotone in `k` — a longer window can only contain more high and more
low — so the minimum over `k in 3..7` is **always** `k = 3`. Confirmed on all
649 trades, identical to the last decimal. The diagnostic added for the A1 study
(issue #132) reports the 3-bar range under a more general name.

Consequence: **only `K_MIN` decides pass/fail.** `K_MAX` never affects whether a
name is tight enough — it only sets the *reported* `cluster_k`, which is what the
rubric's ×2 tightness dimension then scores. The two constants are doing
completely different jobs, which the current naming hides.

| window | p25 | median | p75 | p90 | share ≤ 1.5 ADR |
|---|---|---|---|---|---|
| k = 3 | 1.00 | 1.31 | 1.73 | 2.16 | 64.4% |
| k = 4 | 1.20 | 1.55 | 2.05 | 2.48 | 47.3% |
| k = 5 | 1.36 | 1.86 | 2.31 | 2.84 | 33.1% |
| k = 6 | 1.61 | 2.06 | 2.55 | 3.24 | 20.3% |
| k = 7 | 1.77 | 2.25 | 2.81 | 3.55 | 13.9% |

Note the last column against `TIGHT_K = 5`: only a third of his entries had a
5-bar window inside 1.5 ADR, so the rubric's ×2 dimension is a genuinely
selective test, not a formality.

### 3. Tightness pays — continuously, with no step at 1.5

Median R is `-1.00` in every bucket: most of his trades stop out and the record
lives in its tail, so **mean R is the statistic, not median**.

| 3-bar range (ADR) | trades | mean R | median R | win rate |
|---|---|---|---|---|
| 0.0–1.0 | 164 | **2.02** | -1.00 | 23.2% |
| 1.0–1.5 | 254 | **1.35** | -1.00 | 25.3% |
| 1.5–2.0 | 139 | **0.84** | -1.00 | 18.0% |
| 2.0–3.0 | 82 | **0.35** | -1.00 | 22.0% |
| 3.0+ | 10 | **-0.36** | -1.00 | 20.0% |

Monotone across the whole range, and smooth — the decline through 1.5 looks
exactly like the decline through 1.0 or 2.0. Tightness is a real, strong signal
and a *continuous* one.

At the shipped 1.5 the gate keeps 64.4% of his trades and 82.6% of his total R,
splitting mean R 1.61 (kept) vs 0.61 (rejected). Loosen it to ~3.0 and it keeps
98.5% of trades and 100.4% of his R — the rejected tail is net negative, which is
why the share can exceed 100%.

### 4. His stop is not the consolidation low

If "tight" meant "stop under the cluster," his risk would be about as wide as the
cluster (~1.3 ADR). It is not:

| | p25 | median | p75 | p90 |
|---|---|---|---|---|
| his stop width (ADR) | 0.26 | **0.38** | 0.52 | 0.72 |
| his stop width (% of price) | 1.46% | **2.28%** | 3.42% | 5.50% |
| stop distance *above* the 3-bar low (ADR) | 0.67 | **0.99** | 1.40 | 1.99 |

His stop is about **a third of the tightest window**, and sits a median 0.99 ADR
*above* the 3-bar low. He risks the entry bar, not the base. Two different
quantities wear the word "tight"; conflating them would roughly triple risk per
trade.

*Caveat:* the trade record's prices are raw while the stored bars are
split-adjusted, so a ticker that split after the trade compares two scales. Rows
whose entry price sits within 0.7–1.45× the prior close are treated as comparable
(476 of 649); the rest are excluded from **stop figures only**. Every
range-in-ADR number is computed from bars alone and is unaffected.

## Verdict

**Tight = the last 3 bars spanning about 1.3 ADR or less** — his median, a centre
of mass rather than a rule he respects. Half his entries are looser than 1.31, a
quarter looser than 1.73.

The load-bearing finding is **§3: tightness is a score, not a gate.** The shipped
`TIGHT_MULT = 1.5` is defensible as a percentile of his behaviour but arbitrary
as a cliff — it discards 231 of his own trades (35.6%) carrying 17.4% of his R,
to buy a mean-R separation the rubric could capture by scoring the 3-bar range
continuously.

This does **not** contradict the A1/A3 recommendation in
`references/qullamaggie-replay-findings.md` ("leave the window unchanged").
That verdict rests on tightness having real selection signal, which §3 confirms
and strengthens (+20.8pp in A3's contrast). What is new is that the signal is
*graded*, so the cost of expressing it as a hard rejection is now measured.

### Suggested follow-ups (not implemented — decisions, not prototypes)

1. Move tightness from a funnel rejection to a rubric input: loosen `TIGHT_MULT`
   toward ~2.5–3.0 as an outlier guard, and let the ×2 dimension score the 3-bar
   range on a graded scale instead of the `cluster_k >= 5` boolean.
2. Rename `cluster_min_range_adr` to what it is (`range_3bar_adr`), and document
   that `K_MAX` cannot affect pass/fail.
3. Keep base tightness and stop width as separate named concepts in the domain
   model — they differ by ~3.5×.

## What this does not settle

Every number is conditioned on trades he **took**. There is no counterfactual
here for the tight bases he passed over — that is A3's selection contrast. R
figures use the record's own 10-SMA exit, not the app's.

## Running it

```
backend/.venv/bin/python backend/replay/prototype-tightness/measure_tightness.py  # -> tightness.json
backend/.venv/bin/python backend/replay/prototype-tightness/build_html.py         # -> tightness.html
backend/.venv/bin/python backend/replay/prototype-tightness/summarize.py          # console tables
```

Then open `tightness.html` — a single self-contained file. Free-play sliders for
`TIGHT_MULT` / `K_MIN` / `K_MAX`, plus five guided tabs walking the findings
above. Needs `data/replay.duckdb`, which is untracked; the script falls back to
the main checkout's copy when run from a worktree.
