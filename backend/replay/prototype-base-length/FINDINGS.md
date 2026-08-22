# How the base forms — length, depth, and when the tightening starts

**Status: PROTOTYPE, side-car to a side-car.** Same standing as
`prototype-tightness` (findings §3b): produced by `measure_base.py` +
`summarize.py` in this directory, **not** by `python -m replay.study`, and **not**
part of the reproducible study in findings §10. No constant in `detection.py`,
`score.py`, `universe.py` or `ranks.py` is touched by it. Every figure below is
checkable by re-running the two scripts against `data/replay.duckdb`.

**Question.** §3b measured how *narrow* the final cluster was on the trades he took —
the k-bar range in ADR at the evaluation session. It never asked how the cluster got
there: how long the base had been forming, how deep it was, what it was resting on,
or when the contraction began. This measures that.

**Method and coverage.** Same reference set, same conventions, same n as §3b:
the evaluation session is the last session strictly before entry, ADR is
`screener.indicators.adr_abs` (SMA20 of `high/low - 1`, times close), and coverage is
**649 of 828 (78.4%)** — 170 tickers absent from the bar store, 7 short of 20 bars,
2 with no prior session. 79 of the 649 are continuation entries (within 5 sessions of a
prior entry in the same ticker); they are tagged and kept in every denominator, never
dropped. Nothing is gated at measurement time, so any threshold below is re-derivable
from `base.json` without a rebuild.

**One machinery check before anything else.** The 5-bar range-ratio at d=0 comes back
at a median of **1.86 ADR** — which is §3b's committed k=5 median, to the digit,
computed here by an independently written path. The two prototypes agree where they
overlap.

---

## 1. How long is the base?

There is no single number, because "base length" is not one measurement. Two
independent readings, reported side by side rather than one being picked:

**D1 — overhead-supply age.** Sessions from the highest high in the trailing 120
sessions to the evaluation session. This is the classic base count: how long since
price last traded where it is about to break out to.

| | p10 | p25 | **median** | p75 | p90 |
| --- | --- | --- | --- | --- | --- |
| All 649 | 5 | 11 | **24** | 63 | 100 |
| Fresh only (570) | 5 | 11 | **24** | 65 | 101 |

Continuation entries do not move it. The distribution is **broad and not unimodal**:

| Bucket | Count | Share |
| --- | --- | --- |
| ≤ 5 sessions | 78 | 12.0% |
| 6–30 sessions | 275 | **42.4%** |
| 31–60 sessions | 125 | 19.3% |
| > 60 sessions | 171 | 26.3% |

2.8% are censored at the 120-session lookback, so the right tail is a floor, not a
figure.

**D2 — containment length.** The largest n whose trailing n-bar range still fits inside
T × ADR. This asks the tightness question in reverse: not "how tight is the last window"
but "how far back does the tightness extend".

| Threshold | p10 | p25 | **median** | p75 | p90 | max |
| --- | --- | --- | --- | --- | --- | --- |
| within 1.5 ADR (`TIGHT_MULT`) | 1 | 2 | **3** | 5 | 7 | 13 |
| within 2.0 ADR | 2 | 3 | **5** | 8 | 10 | 16 |
| within 3.0 ADR | 5 | 7 | **11** | 14 | 17 | 41 |
| within 4.0 ADR | 9 | 12 | **17** | 22 | 29 | 121 |

Essentially uncensored (0.0–0.8%), so these are real distributions, not lookback
artefacts.

**Read the two together.** The *tight* part of the base is short — a median of 3
sessions inside 1.5 ADR and 11 inside 3 ADR — while the *structure* it sits in is
much longer, a median 24 sessions of overhead supply with a quarter of entries
breaking out of something older than three months. A base is a multi-week structure
whose final contraction is a handful of days. Those are two different things and the
detector only sees the second one.

**Implication for the detector, stated but not acted on.** `K_MIN, K_MAX = 3, 7`
brackets the 1.5-ADR containment distribution almost exactly (median 3, p90 7) — the
existing window is well placed against *his* geometry, which is a stronger defence of
those constants than §3a could offer. It is also the reason the window cannot answer
"is there a base": containment at 1.5 ADR runs out after a median of 3 sessions
whether the base behind it is 8 sessions or 80.

## 2. When does the tightening start?

**Not where the question expects — ADR itself barely moves.** The median 20-day ADR
across the 90 sessions before entry:

| Sessions before entry | 90 | 60 | 40 | 30 | 20 | 10 | 5 | 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Median ADR % | 5.77 | 5.90 | 5.90 | 6.01 | 5.98 | 6.13 | 6.19 | **6.08** |
| Median ratio to entry eve | 0.94 | 0.98 | 1.00 | 0.97 | 1.01 | 1.03 | 1.03 | 1.00 |

**Flat.** ADR at entry eve is 6.1%, and it was 5.8% three months earlier. There is no
volatility decay into his entries.

A per-trade "ADR now / ADR at its 90-day peak" reads a median of **0.71**, which looks
like contraction — but that statistic is the ratio to a *maximum* of a noisy series and
is biased downward by construction. The flat median curve is the honest reading, and
the two are not in conflict.

**What does tighten is travel, not daily range.** The trailing 5-bar high-low range
divided by ADR — the quantity the detector actually gates on — re-read at each
historical session:

| Sessions before entry | 90 | 60 | 40 | 30 | 20 | 15 | 10 | 7 | 5 | 3 | 2 | 1 | 0 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Median 5-bar range / ADR | 2.38 | 2.39 | 2.37 | 2.29 | 2.44 | 2.43 | 2.38 | 2.24 | 2.26 | 2.18 | 2.07 | 1.99 | **1.86** |

The series sits on a **flat baseline of ~2.4 ADR** from three months out to about ten
sessions before entry, then falls monotonically to 1.86 at the evaluation session. So:

> **The contraction is a late, ~7-to-10-session event, and it is a collapse in how far
> price travels — not a decline in how much it moves per day.** The stock keeps its
> 6% daily range throughout; the days simply stop stacking in one direction and start
> overlapping.

That distinction matters directly: a screen that waits for *ADR* to fall will wait
forever on his names, and a screen that ranks *by* falling ADR would rank his entries
below quieter, worse ones.

**How long the quiet has lasted at entry.** Sessions the 5-bar range has been
continuously inside 2 ADR: median **1**, p75 4, p90 8, max 25. 41.6% of entries have a
run of zero — the 5-bar range is already wider than 2 ADR on the evaluation session —
and only 6.6% have been quiet for 10 sessions or more. Days since the 5-bar range was
last wider than 2.5 ADR: median **4**.

He is not buying the end of a long quiet stretch. He is buying a few days after the
last expansion, with the contraction barely a week old.

## 3. What the base is resting on, and how deep it is

**The prior advance** — from the lowest low in the W sessions before the pivot, up to
the pivot high. Sensitive to W, so both are given:

| | p10 | p25 | **median** | p75 | p90 | censored |
| --- | --- | --- | --- | --- | --- | --- |
| Advance % (60-session cap) | 36 | 60 | **95** | 185 | 579 | 18.3% |
| Advance length (60-cap) | 19 | 36 | **53** | 58 | 60 | — |
| Advance % (120-session cap) | 48 | 83 | **166** | 369 | 898 | 11.1% |
| Advance length (120-cap) | 28 | 54 | **93** | 114 | 119 | — |

Both caps bind hard on the length, so read the advance as **"at least two to five
months, at least a doubling"** rather than as a point estimate. The magnitude is the
solid part: a median +95% within 60 sessions before the base even begins.

**Base depth** from the pivot high to the lowest low of the base: median **30.6%**
(p25 18.1%, p75 48.6%, p90 76.4%). In ADR units, median 5.8 ADR. These are not shallow
bases — a quarter of them give back half the pivot or more, which follows from the size
of the advance they are digesting.

## 4. Does any of it predict the outcome?

MFE under the 10sma exit is the outcome variable, following the study's §A3 convention:
the exits are counterfactual, MFE is a property of the entry. Realised R is shown
beside it and should be read as the weaker figure. Across all 649: median MFE 4.5%,
mean R +1.26, R > 0 on 22.7%.

| Cut | n | median MFE% | p75 MFE% | mean R | R>0 |
| --- | --- | --- | --- | --- | --- |
| **Quiet run ≥ 10 sessions** | 43 | **8.1** | 19.7 | 2.92 | 34.9% |
| Quiet run 0–1 | 351 | 4.0 | 10.9 | 0.40 | 19.7% |
| **Prior advance ≥ 200%** | 154 | **7.6** | 27.7 | 2.65 | 27.3% |
| Prior advance < 50% | 119 | 3.7 | 9.6 | −0.08 | 17.6% |
| **Base depth ≥ 50%** | 160 | **6.3** | 18.4 | 1.71 | 19.4% |
| Base depth < 20% | 191 | 3.4 | 8.9 | 0.87 | 23.7% |
| Base length 16–30 | 110 | 5.4 | 15.1 | 2.24 | 28.2% |

Bootstrap on the median MFE difference (20,000 resamples, seeded; a bootstrap because
MFE is heavily right-skewed and a t-test on these tails would be meaningless):

| Contrast | p |
| --- | --- |
| Quiet run ≥ 10 vs rest | **0.006** |
| Prior advance ≥ 200% vs rest | **<0.001** |
| Base depth ≥ 50% vs rest | **0.001** |
| Base length 16–30 vs rest | 0.111 |

**Base *length* does not predict anything** — the 16–30 bucket's edge does not survive
(p=0.11), and the buckets are otherwise flat. What does carry signal is the *size of
the move being digested* and the *duration of the quiet*, not how old the structure is.

**Four caveats, weighted the same as the results.** (a) These are cuts on his executed
trades only — there is no control group of setups he passed over, so none of this is a
precision measurement, and the study's standing limitation (§7, §9: no measurable
false-positive rate) applies unchanged. (b) The advance and depth cuts are close to
tautological with his selection: he buys big movers, so "big prior advance" partly
re-states "he took it". (c) n=43 for the strongest cut. (d) US, 2019–2022 — one
extraordinary momentum regime (§8).

**So this licenses no constant change.** It is characterisation, and the two candidate
ideas it suggests — a "quiet-run length" feature and a "prior advance" feature — would
each need the control group the study does not have before they could be scored.

## 5. What this adds to §3b, in one paragraph

§3b established that `TIGHT_MULT = 1.5` cuts his k=5 distribution at roughly the 64th
percentile with no gap or shoulder at the threshold. This adds the time axis behind
that snapshot: the tightness is **3 sessions deep** at 1.5 ADR (11 at 3 ADR), it is
**about a week old** when he buys, it sits inside a **~24-session** overhead structure
resting on a **≥95% advance**, and it arrives with **no fall in ADR at all** — the
contraction is in price travel, and the daily range is unchanged from three months
prior. The detector's 3–7 bar window is well matched to the first of those and blind to
the rest.

---

**Reproduce:**

```
backend/.venv/bin/python backend/replay/prototype-base-length/measure_base.py   # writes base.json
backend/.venv/bin/python backend/replay/prototype-base-length/summarize.py      # prints every figure above
```

Run on 2026-08-22 against `data/replay.duckdb` (US, 2019-04-01..2022-12-31) and the
committed `references/trades_bo_gain10smaPct_desc.json`.
