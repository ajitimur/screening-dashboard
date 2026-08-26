# Why the rubric's edge reverses inside the stateless field

Issue #211, PRD #182. The companion to
[the anchor divergence](backtest_anchor_divergence.md), which ends by saying `in_field`
"is **not settled and cannot be settled here**". This page settles it.

Read that page first. In one line: #198 ran both markets end to end, checked the six
anchors against the run's own field, and five settled. `in_field` did not — it flipped
the sign of findings §4b's gap, from the committed **+1.95pp** to **−5.01pp**, and a
sign flip is the one outcome the anchor table refuses to let a written cause waive.

## The verdict

**It is a property of the method under the gates this run is contracted to use, not a
defect in how the field is built.**

The reversal is attributable to the **conjunction of two gates** — the ADR20 floor of
3.5% and the trend gate, `close > SMA50`. Neither one alone accounts for it: dropping
either leaves the gap negative. Dropping **both** restores the sign. The liquidity floor
is not the cause and is exonerated below.

Both of those gates are doing exactly what the contract says they should. Nothing is
miscomputed: the rebuilt membership reproduces the run's own universe rows exactly, and
every gate reproduces `backtest.universe`'s own predicate. There is no bug to fix, so
`in_field` is **not** re-measured over a repaired field — there is no repair to make.

What the run has actually measured is this: **the published rubric's edge over the app's
field is an edge over names the app's universe lets in and the contract's does not.**
Screen those names out first and the edge does not survive. That is a finding about the
method, it is #194's question arriving from a different direction, and it is reported
here as the result rather than adjusted away.

**No constant was moved to get this answer, and none is proposed.** Restoring the sign
requires removing two gates outright, not loosening either — and a gate removal goes
through ADR 0002 and its evidence rule, not through this ticket.

## The isolation

The trouble with #198's third measurement is that it moves *towards* the app: a
different store, a different universe. This one moves the other way and stays inside the
run's own field. One store (`data/backtest.duckdb`), one population (the same 503
replayable trades), one detector (v3), one window (US, 2019-04-01 .. 2022-12-30, 126
burn-in, 821 measured sessions). The only thing that moves between rows is **which gates
build the universe**.

| variant | members/sess | field detections | `in_field` | picks ≥3.5★ | field ≥3.5★ | gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **all three** — the run's own field | 362.6 | 35,971 | 165/503 (32.8%) | 14.55% | 19.55% | **−5.01pp** |
| no ADR floor | 906.2 | 84,329 | 247/503 (49.1%) | 14.98% | 16.44% | −1.46pp |
| no trend gate | 771.2 | 82,650 | 231/503 (45.9%) | 14.29% | 15.73% | −1.44pp |
| no liquidity floor | 985.1 | 103,411 | 193/503 (38.4%) | 16.58% | 18.44% | −1.86pp |
| **liquidity only** — both dropped | 1,687.8 | 176,643 | 322/503 (64.0%) | 13.35% | 12.64% | **+0.72pp** |

Reproduce with:

```
python -m backtest.field_gate_isolation --store data/backtest.duckdb
```

which writes [`backtest_gate_isolation.txt`](backtest_gate_isolation.txt) and
[`backtest_gate_isolation.json`](backtest_gate_isolation.json), both carrying the
per-dimension rows below as well as this table. About 40 minutes.

### Why this table can be trusted

The store's persisted `universe` rows are the *intersection* of every gate, so a row
that **drops** a gate needs names the run never stored. Membership is therefore rebuilt
from the candidate bars rather than read back — and that rebuild is the load-bearing
claim here, so it is checked rather than assumed, two ways:

- Under the full gate set it reproduces the store's own universe rows **exactly**:
  297,709 stored, 297,709 rebuilt, **0 extra and 0 missing** across all 821 sessions.
  `run_isolation` raises rather than reporting a single cell if this is not exact,
  because a gate measured off a pool that is not the run's field is measuring the pool.
- Each gate predicate is pinned against `backtest.universe`'s own `passes_*` function on
  the same bars, in `tests/test_field_gate_isolation.py`, along with the shared-evaluation
  path every variant reads from.

The 362.6 members per session in the baseline row is 297,709 ÷ 821 — the stored figure,
not a recomputed one — and that row reproduces the committed −5.01pp to the digit.

## Reading the table

**No single gate is the cause.** Every single-gate drop moves the gap by a similar
amount — +3.55, +3.57, +3.15 — and every one of them leaves it negative. A ticket that
demanded "attribute it to a specific gate, not the universe as a whole" gets a two-gate
answer, and the two are named: the ADR floor and the trend gate.

**Those two are exactly the gates the app's universe has no counterpart for.** The app's
universe is liquidity, instrument type, listing age and density; it has neither a
volatility gate nor a trend gate (`backtest.universe`'s own module docstring says so).
The divergence page lists three differences from the app — the ADR floor, the ADTV floor
and the dropped hysteresis — and **omits the trend gate**. That omission matters, because
the trend gate turns out to be half the answer.

**The liquidity floor is exonerated.** It is the one gate both universes have; they
differ only in level, and the contract's $10M is *looser* than the app's $20M, so it
admits names rather than excluding them. Dropping it moves the gap least in the direction
that matters, and the `liquidity only` row keeps it and still lands positive.

**The two-gate row is the app's shape, and it lands where the app lands.** `liquidity
only` gives `in_field` 322 of 503 — 64.0% — against the app's own 324 of 503, 64.4%. Two
trades apart, from a different store by a different route. So this row is the app-shaped
field reached from inside the run's own store.

**Hysteresis is not isolated here, and its exoneration is inferential.** The third
difference the divergence page names is that the contract drops the app's membership
hysteresis band, and no variant above restores it — the contract's classifier is
stateless by construction (`backtest.universe.classify` takes no `prior_members`), so
adding the band back is not a gate that can be switched off. What bounds it is the row
above: `liquidity only` reaches the app's own `in_field` to within two trades **without**
hysteresis, which leaves little room for the band to be carrying the sign. That is a
bound, not a measurement, and it is the one difference of the four this page has not
varied directly.

**The movement is entirely in the field, not in his picks.** Across every row his picks
sit between 13.35% and 16.58% — a narrow band with no trend. The field swings from
12.64% to 19.55%. The gates do not make his trades look worse; they make **the field look
better**, by removing the names that were dragging the field's average down.

## The mechanism

The two gates that cause the reversal each **duplicate a rubric dimension**. Applying
one raises the *field's* hit rate on the dimension it duplicates until there is no
spread left to discriminate on, and the dimension's contribution to the gap collapses.

Per-dimension hit rates, his picks against the field on the sessions he traded, under
the run's own field and under the app-shaped one:

| dimension | wt | run's field: picks / field / gap | app-shaped: picks / field / gap |
| --- | ---: | ---: | ---: |
| **ADR** | 2 | 89.7% / 90.7% / **−1.0pp** | 77.0% / 61.3% / **+15.7pp** |
| **MA support** | 1 | 86.1% / 85.8% / **+0.2pp** | 78.6% / 68.8% / **+9.8pp** |
| Tightness | 2 | 43.0% / 25.0% / +18.0pp | 40.4% / 20.7% / +19.7pp |
| Base length | 0 | 52.1% / 67.8% / −15.7pp | 46.6% / 57.8% / −11.2pp |
| Volume | 1 | 26.1% / 32.3% / −6.2pp | 35.7% / 39.7% / −4.0pp |
| Orderliness | 1 | 40.6% / 43.6% / −3.0pp | 34.5% / 37.5% / −3.0pp |
| Prior move | 1 | 100% / 100% / 0.0pp | 100% / 100% / 0.0pp |

The correspondence is one-to-one, and it is the whole explanation:

- **The ADR floor kills the ADR dimension.** The rubric's heaviest dimension — 2 points
  of 9 — scores `adr >= 5%` (`screener.score.ADR_MIN`). The universe gate is
  `ADR20 >= 3.5%` (`backtest.universe.ADR_FLOOR`). Same variable, two thresholds. Under
  the gate the field clears the 5% dimension **90.7%** of the time against his picks'
  89.7%: a dimension worth +15.7pp of edge on the app-shaped field is worth −1.0pp here.
- **The trend gate kills MA support.** `close > SMA50` is a trend qualification, and
  `MA support` scores `sma20_rising`. Requiring the whole field to sit above its 50-day
  average lifts the field's hit rate from 68.8% to 85.8%, and the dimension's +9.8pp
  goes to +0.2pp.
- **Every dimension with no corresponding gate barely moves.** Tightness (+18.0 vs
  +19.7), Orderliness (−3.0 vs −3.0), Volume (−6.2 vs −4.0), Prior move (0.0 vs 0.0).
  `Base length` carries weight 0 and cannot move any star total at all.

The single-gate rows confirm it by moving one dimension each. Drop the ADR floor and
the ADR dimension comes back to **+11.8pp** while MA support stays flattened at −0.6pp.
Drop the trend gate and MA support comes back to **+11.9pp** while ADR only partly
recovers, to +3.9pp. Each gate suppresses its own dimension and leaves the other's
suppressed, which is the prediction this explanation makes and the measurement it could
have failed.

That is why no *single* drop restores the sign. Dropping the ADR floor gives back one
dimension and leaves MA support flattened; dropping the trend gate does the reverse.
Only removing both returns two dimensions' worth of discrimination, and +0.72pp is what
that buys.

It also says where his edge lives: **Tightness**, at +18 to +20pp on either field and
weighted 2. That dimension survives both gates untouched. What the gates
remove is not his edge but the rubric's other two sources of separation.

**On the deliberate 3.5% / 5% gap.** `backtest/universe.py` sets the floor below the
rubric's threshold on purpose, and says why: findings §6 measured the 5% floor silently
withholding a score point from 31% of his real entries, so "a universe cut at 5% would
leave the ADR dimension with no spread left to test." The reasoning is sound and is not
disturbed here. What this measurement adds is that **1.5 percentage points was not enough
clearance to achieve it**: at a 3.5% floor the field already clears the 5% dimension
90.7% of the time, and the spread the gap was meant to preserve is gone anyway.

That is a finding about a constant, and per this ticket it is **reported, not acted on**.
Nothing here proposes moving `ADR_FLOOR`; a change to it would need to go through ADR
0002's evidence rule, would re-open the §6 trade-off the current value was chosen to
respect, and would invalidate this run's persisted denominator. It is recorded so that whoever
revisits the floor knows the 1.5pp clearance does not buy the spread the docstring claims
for it.

The seven-dimension replayed score is what these rows report: `Sector` is cross-sectional
and is not reconstructed on this path, so it is absent rather than shown as zero.

## What this does and does not license

- **The anchor stays failed.** `in_field` diverges, its cause is now understood, and a
  sign flip is still not waivable by a written cause — that rule exists precisely so a
  finding like this one cannot be argued past. `backtest.full_run` continues to emit no
  figure, plot or payload. What has changed is that the run is no longer blocked on an
  *unexplained* divergence; it is blocked on a *result*.
- **This is not the only thing blocking the run.** #196's survivorship bound is
  independently larger than the effect the run is looking for — its pessimistic twin goes
  negative for any headline below **+0.605R**. Settling `in_field` does not touch that.
- **The plan's ship criterion is not what this refutes** — see below.
- **#194 now has its input.** `backtest.ranking` has been ready since #206 and has never
  had a denominator. This finding is a *selection* contrast, not an outcome one; #194
  asks whether a higher star score predicts a better **result**, which is a different and
  stronger question. Nothing here answers it, and this page is not a substitute for it.

### On the ship criterion

The ticket says "the plan's ship criterion assumes the opposite", i.e. that the rubric
ranks. Read against the plan, that is not accurate, and the point is worth being exact about:
the ship criterion is what the whole run is for.

The ship criterion is: *arm B's after-cost expectancy > 0 in a market across both windows,
**and** the pessimistic bound from Phase 2 keeps it above 0.* It is an expectancy
criterion over the **detector's** trades and exits. It does not read the rubric, and
nothing in it requires his picks to out-score the field.

The plan is explicit that the rubric might not decide. Its three-outcome table
includes "They are flat, but his selection beat them → his edge is discretionary, and the
rubric's job is to *rank*, not to *decide*." A rubric that does not separate his picks
from a screened field is a result the plan already contemplates publishing.

So no ship-criterion revision follows from this page. What does follow is narrower and
should be said plainly: **findings §4b's gap should not be quoted as evidence that the
rubric ranks, without naming the field it was measured over.** Under the app's universe
it is +1.95pp; under the contract's stateless universe it is −5.01pp; the number is a
property of the pair, not of the rubric. The ranking claim's real test is #194's, on
outcomes.

## What was checked, and what it rules out

Both directions, as the ticket requires — the pin was re-measured, not assumed.

**The committed pin now has a second measurement agreeing with it, and both were re-run
here.** Against `data/replay.duckdb` under the app's universe:

| population | `in_field` | gap |
| --- | ---: | ---: |
| all 656 replayable trades | 397/656 (60.5%) | **+1.95pp** |
| the same 503 the backtest store can rank | 324/503 (64.4%) | **+1.86pp** |

Both come from `replay.discrimination_grid.run_grid` rather than from this page's own
module, so they are **not** in `backtest_gate_isolation.json` — the command that
reproduces them is under "Reproducing this page" below.

The first reproduces the committed figure exactly. The second holds the population fixed
at the backtest store's 503 names and returns the same sign within a hair — so the pin is
corroborated by a measurement over a different population, and the suspicion moves onto
the field rather than onto the pin. Both rows were re-run for this page rather than
quoted from #198.

Taken with what #198 already ruled out, the causes now excluded are:

- **not the bars** — of the 496 trades both stores can measure, all 496 carry
  bit-identical geometry;
- **not the detector** — recall reproduces at 421/503 = 83.70% against 83.69%;
- **not the population** — held fixed above, the sign holds;
- **not the candidate pool or the membership code** — the rebuild reproduces the store's
  universe rows exactly, 0 extra and 0 missing over 821 sessions;
- **not the liquidity floor** — measured, and it is not the gate that moves the sign;
- **not any single gate at all** — every one-gate drop leaves the gap negative.

What is left is the pair, and the pair is the contract working as written.

## Reproducing this page

- the variant table, from `python -m backtest.field_gate_isolation --store data/backtest.duckdb`;
- the two replay rows, from `replay.discrimination_grid.run_grid` against
  `data/replay.duckdb` over the same window, once with all 828 trades and once with the
  trade list restricted to the names `data/backtest.duckdb.coverage.US.json` lists as
  `stored`;
- the rubric weights and thresholds, from `screener.score.DIMENSIONS` and `ADR_MIN`;
- the gates, from `backtest.universe` and the contract cells it reads.
