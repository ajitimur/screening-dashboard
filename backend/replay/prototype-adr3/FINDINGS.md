# Recent 3 days vs the prior 3 days — is there anything in the ratio?

**Status: PROTOTYPE, throwaway.** Same standing as `prototype-tightness` (findings §3b)
and `prototype-base-length`: produced by the three scripts in this directory, **not** by
`python -m replay.study`, and **not** part of the reproducible study in findings §10.
No constant in `detection.py`, `score.py`, `universe.py` or `ranks.py` is touched.

**Question asked.** At the evaluation session (last session strictly before entry),
compare the **recent 3 bars** against the **prior 3 bars** — the three immediately behind
them. Is there something there?

**Answer in one line: yes, the contraction is real — and no, it is not usable, because it
is the absolute tightness of the last 3 days wearing a different hat.**

---

## What is new here: a control group

Every prior study in this repo carries the same limitation — no measurable
false-positive rate, because there is no set of setups he passed over (§7, §9). This
prototype gets a *partial* control for free: **the same tickers on random ordinary
days**. For each trade, 10 sessions of the same symbol are sampled within ±120 sessions
of the entry, never within 5 sessions of any real entry, seeded at 20260822 — **6,450
background sessions against 645 entries**.

That is *not* a false-positive rate. It answers a narrower question, exactly: **is this
feature a property of the entry, or just of the kind of stock he trades?** Every "lift"
below means entry pass-rate ÷ background pass-rate on that question and nothing more.

Coverage: **645 of 828** (170 tickers absent from the store, 11 short of history, 2 with
no prior session).

## 1. The contraction is real

| Feature | Entry p25 / **median** / p75 | Background p25 / **median** / p75 |
| --- | --- | --- |
| Recent 3-bar avg daily range % | 3.69 / **5.26** / 7.79 | 3.93 / **5.71** / 8.28 |
| Prior 3-bar avg daily range % | 4.21 / **5.82** / 8.80 | 3.89 / **5.66** / 8.29 |
| **adr3_ratio** (recent ÷ prior) | 0.69 / **0.89** / 1.10 | 0.77 / **0.99** / 1.29 |
| Recent 3-bar span, in ADR20 | 1.00 / **1.31** / 1.73 | 1.34 / **1.74** / 2.32 |
| **span3_ratio** (recent ÷ prior span) | 0.57 / **0.78** / 1.08 | 0.70 / **0.99** / 1.43 |
| **vol3_ratio** (recent ÷ prior volume) | 0.68 / **0.87** / 1.13 | 0.76 / **0.98** / 1.29 |
| Recent 3-bar volume ÷ 20-bar avg | 0.62 / **0.80** / 1.01 | 0.76 / **0.93** / 1.19 |

The background sits at **~1.0 on every ratio**, which is the sanity check working: a
random day has no reason to be quieter than the day before it. His entries sit
meaningfully below 1 on all three — daily range 0.89×, travel 0.78×, volume 0.87×. The
last 3 days *are* quieter, tighter and drier than the 3 before them.

(The recent-3-bar span median of **1.31 ADR** is §3b's committed k=3 median, to the
digit, from an independently written path. The machinery agrees where it overlaps.)

**Marginal lift by threshold:**

| Cut | Entry | Background | Lift |
| --- | --- | --- | --- |
| adr3_ratio ≤ 0.7 | 26.0% | 18.1% | 1.44× |
| adr3_ratio ≤ 0.9 | 51.8% | 39.3% | 1.32× |
| span3_ratio ≤ 0.5 | 17.1% | 9.1% | 1.87× |
| vol3_ratio ≤ 0.7 | 28.5% | 18.8% | 1.51× |
| **span3_recent ≤ 1.5 ADR** (level, not ratio) | 64.3% | 34.4% | **1.87×** |
| **span3_recent ≤ 1.0 ADR** (level, not ratio) | 25.0% | 7.7% | **3.25×** |

Note the last two rows already: the plain *level* of the 3-bar span out-lifts every
ratio in the table.

## 2. …and it adds nothing once the level is held fixed

If "recent quieter than prior" carried its own information, it would still lift inside a
band where the 3-bar span is roughly constant. Recomputed within span bands:

| span3_recent band | n (entry / bg) | adr3_ratio ≤ 0.7 | adr3_ratio ≤ 0.9 | vol3_ratio ≤ 0.7 | vol3_ratio ≤ 0.9 |
| --- | --- | --- | --- | --- | --- |
| < 1.0 ADR | 161 / 496 | **0.90×** | **0.95×** | 1.06× | 1.05× |
| 1.0–1.5 ADR | 254 / 1,723 | **0.94×** | **0.96×** | 1.04× | 1.02× |
| 1.5–2.5 ADR | 202 / 2,978 | **0.85×** | **0.91×** | 1.04× | 0.89× |

**Every lift collapses to ~1.0, several below it.** The marginal 1.32–1.44× on
`adr3_ratio` is entirely explained by the fact that entries with a quiet recent 3 days
are entries with a *tight* recent 3 days — which the level already measures, and
measures better (1.87×–3.25×). Conditioned on the level, the change carries no extra
information about whether he took the trade. The same is true of volume, to within
noise.

This is the useful result, and it is a negative one: **the comparison is redundant with a
feature the detector already has.** `TIGHT_MULT` on a 3-bar window is the level. Adding a
recent-vs-prior ADR ratio beside it would add a second knob measuring the first one.

## 3. And none of it predicts the outcome

MFE under the 10sma exit (the study's §A3 convention — exits are counterfactual, MFE is a
property of the entry). All 645 entries: median MFE 4.4%, mean R +1.26, R > 0 on 22.7%.

| Bucket | n | median MFE% | p75 MFE% | mean R |
| --- | --- | --- | --- | --- |
| adr3_ratio < 0.6 | 90 | 4.1 | 10.0 | 0.71 |
| adr3_ratio 0.6–0.85 | 207 | 4.7 | 14.9 | 1.93 |
| adr3_ratio 0.85–1.15 | 207 | 4.5 | 12.0 | 0.93 |
| adr3_ratio 1.15+ | 141 | 4.3 | 11.7 | 1.10 |
| vol3_ratio < 0.7 | 184 | 4.4 | 14.5 | 1.41 |
| vol3_ratio 1.5+ | 56 | 4.2 | 10.0 | 0.92 |

Seeded 20,000-resample bootstrap on the median MFE difference (a bootstrap because MFE is
heavily right-skewed):

| Contrast | median MFE | p |
| --- | --- | --- |
| adr3_ratio < 0.85 vs rest | 4.4 vs 4.5 | 0.518 |
| span3_ratio < 0.8 vs rest | 4.4 vs 4.5 | 0.514 |
| vol3_ratio < 0.7 vs rest | 4.4 vs 4.5 | 0.527 |
| span3_recent ≤ 1.5 ADR vs rest | 4.7 vs 4.2 | 0.188 |

Flat — indistinguishable from noise. These features describe **what he buys**, not
**which of his buys work**, which is the same split A3 found across the whole rubric.

## Verdict

**Do not add a recent-3 vs prior-3 feature.** It is real (the contraction exists and is a
property of the entry, not just of the name), it is redundant (conditioned on the 3-bar
span level, its lift is ~1.0), and it is outcome-blind (p ≈ 0.5). The existing 3-bar
`TIGHT_MULT` gate already captures the whole of it — and per §3b/§3a, the standing
recommendation not to move `TIGHT_MULT`, `K_MIN` or `K_MAX` is untouched by this.

**The one thing worth carrying forward** is the *method*, not the feature: the
same-name background sample is cheap, seeded, and gave a redundancy test the study could
not otherwise run. Any future candidate dimension can be put through the same conditional
lift check before it is scored.

## Caveats

- **The background is not a false-positive rate.** "This stock on an ordinary day" ≠ "a
  setup he passed over". §7/§9 stand unchanged.
- **Same-name matched by construction** — its strength and its bound. It says nothing
  about how these features behave across the wider universe.
- **The sampling window straddles the entry**, so post-breakout expansion sits in the
  control. That makes the control harder to beat, so the lifts are conservative.
- **US, 2019–2022**, one extraordinary momentum regime (§8).

---

**Reproduce:**

```
backend/.venv/bin/python backend/replay/prototype-adr3/measure_adr3.py   # writes adr3.json
backend/.venv/bin/python backend/replay/prototype-adr3/summarize.py      # prints every figure above
backend/.venv/bin/python backend/replay/prototype-adr3/build_html.py     # writes adr3.html
```

`adr3.html` is the driveable version — sliders for any threshold, a "hold the level
fixed" band selector, and three guided tabs walking the argument above. Double-click it,
or serve the directory (`python3 -m http.server`) if the browser blocks `file://`.

Run on 2026-08-22 against `data/replay.duckdb` (US, 2019-04-01..2022-12-31) and the
committed `references/trades_bo_gain10smaPct_desc.json`.
