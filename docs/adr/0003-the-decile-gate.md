---
status: accepted
---

# The decile gate: what its width should union

> Titled **"The decile gate is not loosened on this evidence"** until #149. It has since been
> loosened — by one lookback, not the two this ADR proposed. See the amendment below.

A1 measured the decile gate discarding **40% of Kullamägi's real entries** (recall 395/658,
60.0%) at the session before entry, against liquidity's 90.9%. It is the largest single loss
in the funnel and the finding most likely to be acted on wrongly, which is why #133 was raised
as a spike rather than a change.

This ADR records the option space and the reasoning.

---

## Amendment (#149): 3→5 is rejected. `12m` is adopted on its own; `1w` is refused on evidence

**The leading candidate below did not survive being measured.** #149 built the sweep this ADR
declined to authorise (`replay.gate_sweep`, `references/detection_gate_sweep.txt`) and
decomposed the 75 recovered trades by the lookback that admits each one. Every figure below
is from that sweep — 821 measured sessions, 656 replayable trades, coverage 92 blind-spot
tickers, detector v2 (#154's graded base tightness).

**`DETECTION_LOOKBACKS` is now `("1m", "3m", "6m", "12m")`.** That is not the widening this
ADR proposed.

### The 75 arrive entirely through the two lookbacks the spec excludes

| Admitted by | Count | Share |
| --- | --- | --- |
| `12m` only | **49** | 65.3% |
| `1w` only | **22** | 29.3% |
| both `1w` and `12m` | 4 | 5.3% |
| also by a lookback already gated | **0** | — (impossible by construction) |

So 3→5 buys its whole recall gain with names `detection.py:449` excluded *on purpose*. This
ADR argued the widening was safe because it is structural rather than a threshold move and
does not change what "top decile" means. Both remain true, and neither answers this.

### But "admitted by `12m`" is not "stale", and the difference decides it

The exclusion's stated worry is a name that *topped out months ago and has done nothing
since*. That is a claim about a name's recent ranks, not about which window let it in — so
#149 measured the recent ranks:

| Group | n | dead on 1m/3m/6m | within reach of the cut | median 6m pct |
| --- | --- | --- | --- | --- |
| `12m` only | 49 | **1** | 29 | **0.798** |
| `1w` only | 22 | **8** | 3 | 0.356 |

*(dead = below the field median on **every** gated window; within reach = ≥80th percentile on
at least one.)*

**One of the 49 trades `12m` recovers is stale in the sense the exclusion describes.** The
group's median 6m percentile is 0.798 — names sitting just under the cut, quiet on 1m because
they are *in a base*, which is the setup the detector exists to find. The same holds field-wide,
not only for his trades: **14.1%** of the detections `12m` adds are dead on the gated windows,
against **35.0%** for `1w`. The window named for staleness admits the *less* stale field of
the two.

### What each width costs, against the funnel's own going rate

The gate as measured spends **424.7 detections per entry it surfaces** (148,223 detections over
821 sessions, 349 entries surfaced). That is the denominator a marginal cost has to be read
against; a widening at 1.0× is buying entries at the price the funnel already pays.

| Width | Universe | Decile recall | Surfaced recall | Added detections | Per surfaced entry | vs going rate | Stale share of added |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `1m/3m/6m` (as measured) | 19.3% | 395/656 (60.2%) | 349/656 (53.2%) | — | — | — | — |
| `+1w` | 24.2% | 421/656 (64.2%) | 361/656 (55.0%) | 17,842 | 1,486.8 | **3.50×** | 29.9% |
| `+12m` | **21.9%** | **448/656 (68.3%)** | **397/656 (60.5%)** | 27,323 | 569.2 | **1.34×** | 13.4% |
| five (3→5) | 26.5% | 470/656 (71.6%) | 409/656 (62.3%) | 43,430 | 723.8 | 1.70× | 20.1% |

*The universe shares here — 19.3% and 26.5% — are the same two gates this ADR measured above
at 19.4% and 27.2%, over a different window: the sweep recomputes the rank table in memory and
so covers all **821** measured sessions, where the earlier figure covered the **505** the store
still held rank rows for. The gates are identical; the windows are not. The field volumes are
detector **v2** (#154) and are not comparable with any figure measured under v1, which is why
this table quotes its own baseline rather than #141's 14,239 anchor. On A2's basis that baseline
is 54,399 detections, 349/656 in the field and 109/656 on the board — the same three figures §4a
reports, reached by an independent path.*

Field inflation is a **volume** measure and never a false-positive rate: the added names carry
no verdict (findings §7, §9). It is reported on the basis #141 sets for the cluster gate, so
the funnel's two most expensive gates are priced comparably.

### And the trades each half recovers are opposite in quality

R here is fat-tailed — every group's median R is −1.00 — so the mean is a statement about one
name. Read the trimmed mean and the tail rate:

| Group | n | mean R | trim-5% R | win rate | R≥3 rate | best trade's share of R |
| --- | --- | --- | --- | --- | --- | --- |
| passing `1m/3m/6m` | 395 | 1.37 | 0.03 | 25.1% | 16.8% | 19.2% |
| recovered by `12m` | 49 | 1.87 | 0.12 | **24.5%** | **20.4%** | 70.7% |
| recovered by `1w` | 22 | −0.88 | −0.99 | **4.5%** | **0.0%** | — (no net R) |

**The `12m` half recovers trades indistinguishable from the ones the gate already passes.**
The `1w` half recovers 22 trades that won 4.5% of the time and not one of which reached 3R.
Bundling them into a single "75 recovered" is exactly what this ADR's headline number could
not see.

### Verdict

- **3→5 is rejected.** It is not one move: it is a defensible widening and an indefensible one
  quoted at a blended price.
- **`1w` stays excluded, now on evidence rather than on assertion.** It costs 3.50× the going
  rate, adds the stalest field of any width, and the entries it recovers lose.
- **`("1m", "3m", "6m", "12m")` is adopted.** ADR 0002's four conditions are met — the loss is
  measured directly (A1), shown not to be a coverage artefact (§3's decomposition), the change
  is structural with no threshold to justify, and the population cost is stated: **2.6 points
  of universe and 27,323 detections for 53 recovered entries, 48 of which the app would have
  surfaced.** Decile recall 60.2% → 68.3%; surfaced recall 53.2% → 60.5%. The board barely
  moves: 1,832 top-30 places change hands over 821 sessions, and his own entries' board count
  goes 109 → 111.
- **The §4.5 exclusion is amended, not ignored.** `12m` was excluded on a prediction about what
  it would admit; the prediction was measurable and it was wrong. `detection.py`'s docstring
  now records the measurement rather than the prediction.

### What this verdict does not claim

- **Precision is still unmeasurable.** 27,323 added detections are 27,323 names carrying no
  verdict, not 27,323 false positives. The out-of-sample backtest (`docs/out-of-sample-backtest-plan.md`)
  is what prices them properly; this decision lands before its Phase 3 so the denominator is
  frozen, which is what that plan asks for.
- **n = 49 is a small sample from one regime**, and 70.7% of its R is one trade. The claim
  rests on *absence of harm* (win rate 24.5% against 25.1%, R≥3 20.4% against 16.8%), which is
  what adoption needs, and not on the recovered group being better — which the sample cannot
  support.
- **Scope is US 2019–2022.** No figure here is an IDX expectation.
- The measurement is reproducible: `replay.gate_sweep` pins its baseline to the three-lookback
  width rather than reading the live constant, so the report that decided this can still be
  re-run after the decision moved that constant.

### Confirmed twice more, from outside the sweep's argument (#169/#172)

The `1w` refusal above rests on one instrument: the gate sweep, which prices what the lookback
recovers. §3f of the replay findings measured his entries themselves, and the week comes back
empty on two further readings that share none of the sweep's machinery:

| Reading | His entries | Same names, ordinary days |
| --- | --- | --- |
| `1w` return at entry (median) | **+0.3%** | +0.1% |
| Entries *down* on the week | **46.4%** | — |
| Beat `QQQ` over the trailing week | **48.1%** | 49.1% |

n = 582 of 828 logged breakout longs, measured through the session before entry. The `6m`
readings on the same panel are +55.8% and 74.2% against the background's 37.8%, so the panel
plainly can separate a lookback that matters; `1w` is the window where it cannot.

#### Both readings were re-measured per trade, and the claim narrowed (#172)

The pooled figures above hold two facts side by side without joining them, and each turned out to
need a correction. Neither reverses the refusal; one sharpens it and one removes a confound.

**The +0.3% is a mixture over bases, not over weeks.** A pooled median that flat is equally
consistent with weeks up 10% and down 10% cancelling, so base age was measured on the same rows
(§3c's D1, sessions from the highest high of the trailing 120) and the week re-read inside each
band:

| Base age | share of entries | median `1w` % | 95% CI | down on the week |
| --- | --- | --- | --- | --- |
| ≤5 sessions | 11.9% | +1.61 | [−0.27, +3.73] | 43.5% |
| 6–30 | 42.3% | **−0.04** | [−0.71, +0.40] | 50.4% |
| 31–60 | 20.3% | **−0.28** | [−0.59, +0.88] | 51.7% |
| >60 | 25.6% | +1.73 | [+0.87, +2.45] | 36.9% |

In the two bands holding the modal entry — **62.5% of entries** — the week is *flatter* than
pooled, both bootstrap CIs straddle zero, and more than half of entries are down on it. The
correction runs the sharpening way.

**The beat-rate had a confound, and survives it.** His entries break out of far younger structures
than an ordinary day sits in — base age median 24.5 against **75** — so 48.1% against 49.1%
compared two different base-age mixes. Matched band by band, the gaps are +3.3, +6.7 and +5.5 pp
in the three older bands, every one inside two standard errors.

**What the ≤5 and >60 bands are.** The `>60` band is the only one significantly up on the week,
and its `3m` median is **−3.3%** against +44.5% in the 6–30 band: a stale 120-session high means
there is no recent advance to base out of, and there the entry week *is* the move. That is a
different setup under the same label, and it is a population question this study has not
otherwise asked — not evidence for `1w`.

So the sentence this ADR relies on is the narrower one: **for entries breaking out of a
6-to-60-session structure, nothing about the prior week distinguishes it from any other week.**
That is the modal breakout in his record, and it is the population the exclusion has to hold on.

**What this adds and does not add.** It does not re-price the gate — recall, field inflation and
the quality of recovered trades are the sweep's to measure, and the verdict above stands on
those. What it adds is that the week carries no signal *at the entries themselves*, which is the
premise §4.5's exclusion asserted and #149 could only test indirectly. Three independent lines
now point the same way, and a future proposal to re-admit `1w` has to answer all three rather
than the sweep alone.

The bound: executed trades only, one regime, and a same-name background rather than a control
group of rejected setups (findings §9). None of these figures is a precision measurement, and the
band figures are per-trade readings of the same 582 rows rather than a second sample.

### A fourth line, and the first with a comparison group (#171)

The three above are all drawn from his trades alone. §5e of the replay findings ran the `1w`
return through §5b's selection contrast — his picks against the **not-taken detections**, field
members present the same nights in names he did not enter — over 505 sessions under the live
detector:

| `1w` reading, live detector v3 | His picks | The field he passed over | Δ |
| --- | --- | --- | --- |
| Raw, in ADR units, above zero | 37.9% | 42.4% | **−4.5pp** |
| Netted against `MARKET_INDEX` | 35.0% | 38.9% | **−3.9pp** |

Median week: **−0.19 ×ADR** in his picks and **−0.19** in the field he passed over, identical to
two decimals. n = 140 taken against 34,543 not-taken. Against setups he did not take on the same
nights, the week before his entry is not distinguishable from the week before theirs.

**One methodological warning rides with it**, because the same table measured the other way says
the opposite. Read at the detection's own session the gap is **+31.6pp** — the widest prior-move
gap anywhere in that study, wider than `ADR`'s — and all of it is the entry day: a taken
detection's session *is* the session he bought it on, one bar in a five-bar window. The rows above
are measured through the session strictly before, which is §3f's convention and adopted there for
the same reason. Any future `1w` proposal that quotes a gap has to say which session its window
ends on, because that choice is worth 36 points.

The comparison group is not a control group of rejected setups — he may never have seen those
names — and §5e's own coverage and regime bounds attach. What it removes is the objection that
the three readings above only ever looked at trades he took.

---

**Everything below this line is the reasoning as it stood before the sweep**, kept as the
record of what was argued and on what. Where it calls 3→5 "the leading candidate", read this
amendment.

---

**Accepted on the full run.** It was raised `proposed` because the decomposition ADR 0002
condition 2 requires was only 46% measured — 312 of 658 replayable trades, skewed to 2021–22.
#131 has since supplied the full forward chain, and `decompose_decile_misses` now covers all
658 (findings §3). The figures below are the full-run ones; the partial-run table this ADR
was drafted against is kept in **Appendix: what the partial run said**, because the two
disagree on one number in a way that matters.

## The gate is tighter than the parent spec says

PRD #114 (user story 8) and §3 of `references/qullamaggie-replay-findings.md` both describe
the gate as cutting "to roughly 29% of the universe". That figure belongs to a **different
gate**. There are two decile unions in the codebase:

- `ranks.py:107` unions **five** lookbacks (`1w`, `1m`, `3m`, `6m`, `12m`) at
  `percentile >= TOP_DECILE`. This is the breadth substrate, and it admits **27.2%** of the
  universe — the source of the ~29% figure.
- `detection.py:396`, `detection_gate`, unions only **three**: `DETECTION_LOOKBACKS =
  ("1m", "3m", "6m")`. This is the gate A1 measured, and it admits **19.4%**.

Measured over the 505 sessions the replay store still holds ranks for (2020-12-30 to
2022-12-30, mean universe 1876 names). The gate costing 40% of his entries is a third tighter
than every document describing it has said. `CONTEXT.md` carried the same conflation and is
corrected; #114 is left as the historical record of what was specified, with the discrepancy
noted here.

## What the loss is made of

Decile verdicts across all **658** replayable trades, from the single forward chain #131
supplies (`decompose_decile_misses`, findings §3):

| | count | share of 658 |
| --- | --- | --- |
| Passes the 3-lookback detection gate | 395 | **60.0%** |
| Coverage gap — in the store, not a universe member | 64 | **9.7%** |
| Present, recovered only by widening 3→5 lookbacks | 75 | **11.4%** |
| Present, outside even the 5-lookback union | 124 | **18.8%** |

**The loss is still not mostly a coverage artefact — but it is more of one than this ADR
first claimed.** The partial run put absent-from-field at 5.4% of trades (13.3% of the
misses). The full run puts it at **9.7% of trades — 24.3% of the misses**, close to double.
Three quarters of the loss remains a genuine ranking verdict, so ADR 0002 condition 2 is
satisfied and the conclusion holds; but "only 5.4% is absent-from-field" was an artefact of
the 2021–22-skewed subset and is corrected here rather than left standing.

**18.8% sit outside any decile construction** (was 22.8% on the partial run). That population
is not reachable by widening what the gate unions, and it is the honest ceiling on what
loosening can recover.

## Considered options

- **Widen the gate from three lookbacks to five.** Recovers **75 trades — 11.4pp, about a
  third of the loss** — taking decile recall from **60.0% to 71.4%**, at a gate population of
  27.2% instead of 19.4%. **The leading candidate, and it remains so on the full run.** It is
  the only option that widens the gate without changing what "top decile" means, and it is
  structural rather than a threshold move, so ADR 0002 condition 3 is satisfied and there is
  no magnitude to get wrong. Its population cost is **7.8 points of universe for 75 trades**.

  *Restated against the full run.* The recovered share slipped from 12.8pp to 11.4pp and the
  coverage gap it competes with nearly doubled, so the case is modestly weaker than drafted —
  the same 7.8 points of universe now buys a slightly smaller fraction of the loss. It is
  nonetheless still the leading candidate, because nothing about *why* it leads depends on the
  magnitude: it is the only structural option, the only one confined to a constant nothing
  else reads, and the only one with no threshold to justify. The alternatives were rejected on
  blast radius and on constant-count, and the full run moves neither of those arguments.
- **Move `TOP_DECILE` below 0.90.** The only option reaching into the 18.8% outside every
  union. Rejected on blast radius: `TOP_DECILE` is read by `ranks.py`, `sectors.py` and
  `boards.py` as well as `detection.py`, so moving it silently rewrites sector strength, the
  breadth badge `k/5` and every board — surfaces this study measured nothing about. It is also
  a threshold move, so ADR 0002 routes it to the score-dimension limb, which `Prior move` can
  never satisfy.
- **Per-lookback thresholds** — keep 0.90 on `1m`, relax `3m`/`6m`. Rejected: it introduces
  three constants needing independent justification to buy an effect the structural widening
  buys with none, and each new constant is a threshold move under ADR 0002.
- **Leave the gate.** The status quo, and the outcome if #131 contradicts the decomposition
  above. Not a null option: it costs 40% of his entries knowingly, which is defensible only
  because the gate is what makes the sample tractable at all.

## Consequences

- **No constant changes.** This ADR settles the *reasoning*, not the edit. Adopting 3→5 is
  separate work and needs its own ticket; nothing here authorises touching
  `DETECTION_LOOKBACKS`. *(Superseded by the amendment: #149 was that ticket, and it moved the
  constant to `("1m", "3m", "6m", "12m")` — not to the five-lookback set.)*
- **The evidence this ADR was waiting for has arrived.** The full 658-trade decomposition into
  coverage gap / recovered-by-5 / outside-any-union now rides the single forward chain (#131)
  and is committed in findings §3. The earlier obstacle — `append_ranks` pruning beyond
  `RANK_RETENTION_YEARS` as the chain advanced, leaving `ranks` for only the last 505 of 928
  sessions while 450 of 828 trades entered before that cutoff — no longer bounds the result.
- **One figure in this ADR moved materially on the full run** (the coverage gap, 5.4% → 9.7%
  of trades). Anyone citing the partial-run numbers from before this revision should re-read
  the appendix below.
- Should 3→5 be adopted, the change is confined to `DETECTION_LOOKBACKS`. Nothing outside
  `detection.py` reads it, so the breadth badge, sector strength and the boards are untouched.
  *(Confirmed by #149's narrower adoption: the whole edit was one tuple, and the backend suite
  passed unchanged.)*
- The **18.8%** is a standing statement about what this funnel cannot do. If those entries
  matter, the answer is a different selection stage, not a looser decile.
- Scoped to US 2019–2022. No figure here is an IDX expectation; the shape — that the decile
  stage is the expensive one and that its loss is mostly a ranking verdict rather than a
  coverage hole — is what transfers.

## Appendix: what the partial run said

Kept so a reader can see which figures moved, and by how much, rather than finding a silently
different table. These are the 312 replayable trades entering after 2020-12-30, with universe
membership read off the persisted chain rather than recomputed:

| | partial (312 trades) | full (658 trades) |
| --- | --- | --- |
| Passes the 3-lookback detection gate | 59.0% | **60.0%** |
| Coverage gap | 5.4% | **9.7%** |
| Recovered by widening 3→5 | 12.8% (40) | **11.4% (75)** |
| Outside even the 5-lookback union | 22.8% | **18.8%** |

The pass rate landing within a point of the study's headline was cited at the time as evidence
the approximation was sound. That held — but soundness on the headline did not imply soundness
on the decomposition: the coverage gap, the one figure the subset's 2021–22 skew would most
distort, is the one that nearly doubled. Worth remembering the next time a partial run is
offered as a stand-in for a full one.
