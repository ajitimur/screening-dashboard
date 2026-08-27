# The anchors, and what it took to settle them

Phase 6 of [the out-of-sample backtest plan](../docs/out-of-sample-backtest-plan.md)
(PRD #182, issue #198). The plan's third rule is anchor before believing, and its escape
hatch is "reproduce the figure, **or** explain the divergence in writing". This is that
writing.

Issue #197 built the table and found the geometry divergence; it left it unresolved and left
the anchors pinned at their committed values rather than widened to accommodate it. This page
resolves that one, and then records a second divergence — found by running the table against
the completed run — that **cannot** be resolved in writing and stops the run.

## Where this leaves the run

**The run is anchored.** Five anchors diverge with a cause set out below, and the sixth —
`in_field` over the contract's stateless universe — matches: 165 of 503 against a committed
165 of 503, gap −5.00655 against −5.01. `backtest.full_run` emits its figures.

It did not get there by waiving anything, so it is worth being precise about what moved.

For most of this page's life the sixth anchor **failed**, by flipping the sign of §4b's gap
— the one outcome the table refuses to let a written cause waive. That refusal was the table
working. What it had caught, though, was not a bug in the pipeline.

[#211](backtest_gate_isolation.md) established why the sign reverses: the contract's **ADR20
floor and trend gate acting together**, neither on its own, each duplicating a rubric
dimension and lifting the field's hit rate on it until no spread is left. It is a property of
the method under the gates this run is contracted to use, not a defect in how the field is
built. And it recorded the consequence as a rule: **§4b's gap must not be cited without
naming the field it was measured over** — +1.95pp under the app's universe, −5.01pp under the
contract's. The number is a property of the pair.

That rule is what the anchor was breaking. Holding this run to §4b's figure meant comparing a
count over the app's universe against a count over the contract's, which is not a failing
anchor — it is a subtraction between two numbers that were never the same number. So
`in_field` is now **two pins**, each naming its universe, and a run is checked against the one
measured over the field it actually screened:

| Universe | `in_field` | §4b gap | Anchors |
| --- | ---: | ---: | --- |
| The app's (`app`) | 397 of 656 | **+1.95pp** | the replay store, findings §4b |
| The contract's stateless (`stateless`) | 165 of 503 | **−5.01pp** | this run |

**No constant moved, no tolerance widened, and the sign check was not waived.** The stateless
pin carries its own `sign_checked` on the gap, so a run that comes back positive over the
contract's universe still fails for it. What changed is which pair the question is asked over.

**Read the stateless pin for what it is.** It is a first measurement, made by the run it now
anchors, so it detects drift from here on rather than confirming this run. The corroboration
lives on the other universe, where #211 made two measurements that agree with each other:
§4b's own 397/656 (+1.95pp) reproduced exactly, and the same 503 names held fixed giving
324/503 (+1.86pp). The pin is sound; the sign belongs to the pair.

## The divergence

The three geometry anchors are medians measured from his bars at his entries. They hold
whatever the detector does, so they anchor the **store and the indicators** — which is why
they are checked first and why a failure stops everything downstream.

| | 3-bar range | 5-bar range | ADR20 at entry eve | n |
| --- | --- | --- | --- | --- |
| Committed (findings §3b) | 1.31 ADR | 1.86 ADR | 6.08% | 649 |
| `data/replay.duckdb` | 1.3105 | 1.8633 | 6.0812% | 649 |
| `data/backtest.duckdb` | **1.2752** | **1.7674** | **6.4277%** | **496** |

The replay store reproduces all three to the digit. The backtest store — the store this
run is built on — does not, and it is not close: the 5-bar median is off by 0.10 ADR and
the ADR median by 0.35 percentage points, both far outside the anchors' tolerances.

## The cause: the sample, not the bars

The bars are identical. Of the 496 trades both stores can measure, **all 496 carry
bit-identical geometry** — every 3-bar range, every 5-bar range and every ADR agrees to
within 1e-9. There is no adjustment bug, no ingest bug and no indicator drift. The stores
disagree about *which trades are in the sample*, and about nothing else.

Measured off `replay.duckdb` alone, changing only which trades are kept:

| Sample | n | 3-bar | 5-bar | ADR20 |
| --- | --- | --- | --- | --- |
| A — every trade with bars (the committed sample) | 649 | 1.3105 | 1.8633 | 6.0812% |
| B — A minus references excluded by design (#162) | 499 | 1.2768 | 1.7685 | 6.4076% |
| C — B minus names never enumerated | 496 | 1.2752 | 1.7674 | 6.4277% |
| `backtest.duckdb`, measured directly | 496 | 1.2752 | 1.7674 | 6.4277% |

Row C and the backtest store agree to every digit printed. The backtest store's geometry
*is* the replay store's geometry over the same names.

The 153 trades between them split two ways, and the split matters because one half is the
design working and the other is a known defect:

**150 trades, 43 tickers — the reference exclusion, working as intended.** They are ETFs:
`SOXL`, `TQQQ`, `TNA`, `NUGT`, `JNUG`, `GBTC`, `ETHE`, `UVXY`, `LABU`, `ARKK` and thirty-three
more. Every one carries the enumeration reason `unread_reference`. The backtest's universe
ranks candidates, and reference instruments are computed like anything else and never
ranked (#162, and CONTEXT.md's *Instrument*). He traded them; the denominator this run
builds cannot, so a store scoped to what the run can rank will never carry them.

This half of the divergence is **not a bug and must not be tolerance-widened away.** The
committed anchors were measured over a sample that includes his ETF trades, and the
backtest store is scoped to exclude them. The two are measuring different populations on
purpose, and an anchor quietly widened to span both would stop being able to detect the
thing it exists to detect.

**3 trades, 1 ticker — survivorship.** `BBBY` is common stock, not a reference. It appears
in neither the listed nor the excluded set of `data/backtest.duckdb.enumeration.US.json`:
it was never enumerated at all, because the crawl enumerates from a current listing snapshot
and Bed Bath & Beyond was delisted in 2023. This is survivorship bias, it is a real defect,
and it is **not** fixed here. #196 owns bounding it, and has:
[the survivorship hole](backtest_survivorship.md).

Its effect on this anchor is small (row B → row C: 0.0016 ADR, 0.0011 ADR, 0.02pp) but its
effect on the wider run is not, and the small number here should not be read as reassurance.
Across the whole 828-trade reference set the same enumeration gap swallows **82 tickers and
144 trades** — the geometry anchor happens to sit on the part of it that is nearly empty,
because most never-enumerated names also lack the bar history the anchor needs.

## The gate-dependent anchors

Measured over **the run's own field** — the denominator this run persisted, built from the
contract's stateless universe — across the reference study's own window (US, 947 sessions,
2019-04-01 .. 2022-12-30, its first 126 burn-in). Not recomputed from the reference study's
outputs, which would anchor the new pipeline against the old one's answers and report a pass
for it.

Only 503 of his 828 trades are replayable against this store, against 656 on `replay.duckdb`
— the same scope difference the geometry anchors show, arriving in the denominators.

| Anchor | Committed | This run | Settles? |
| --- | --- | --- | --- |
| Blind-spot tickers / trades / R share | 92 / 172 / 18.0% | **136 / 325 / 25.9%** | yes, with cause |
| Detection recall (A1) | 549 of 656 | **421 of 503** | yes, with cause |
| `in_field` (A2, v3, whole), stateless universe | 165 of 503, gap **−5.01pp** | **165 of 503, gap −5.00655** | yes — matches |

The `in_field` row is quoted against the pin for **this run's universe**, which is what
changed since the sign flip; §4b's 397 of 656 is the app universe's pin and is not what a
stateless-universe run is held to. The two pins, and why they are two, are above.

**Blind spots — the survivorship hole, measured.** 136 tickers and 325 trades, carrying 25.9%
of his realised R, against findings §2's 92 / 172 / 18.0% over the four-year window. #196
predicted exactly this: "a 2012 start reaches further back, so expect worse — a better number
is a reason for suspicion, not celebration." It is worse, in the direction and roughly the
proportion expected. This is the bound #196 owns; it is measured here, not fixed here.

#196 has since landed, and its number is worse than this row suggests: 51.8% of the US
names listed inside the window are gone from today's enumeration, 37.7% weighted by how
long each was listed, and its pessimistic twin goes negative for any headline below
**+0.605R**. That bound is larger than the effect this run is looking for. It rides on every
result out of this run as one line, and it is **a separate question from the anchors** —
settling `in_field` says nothing about it either way. Whether it should hold a figure back
is a plan-level call for the issue author, not one this page makes.

**Detection recall — reproduced.** 421 of 503 is **83.70%**; the committed 549 of 656 is
**83.69%**. A different population returning the same rate to four decimal places is about as
strong a statement as this table can make that the store and the detector are sound. The
anchor fails only because its tolerance on both components is zero and the population moved.

**`in_field` — the sign flip, what caused it, and how the anchor was resolved.**

The measurement changed two things against the committed figure at once: the store, and the
universe the field is built from. So it was measured a third way, holding the population fixed:

| Store | Universe | Population | `in_field` | gap |
| --- | --- | --- | --- | --- |
| `replay.duckdb` | app's | all 656 | 397 (60.5%) | **+1.95** |
| `replay.duckdb` | app's | the same 503 | 324 (64.4%) | **+1.86** |
| `backtest.duckdb` | contract's stateless | 503 | 165 (32.8%) | **−5.01** |

**The population is not the cause.** Hold it fixed and run the same grid over the store the
committed figure came from, and the gap stays positive at +1.86 — within a hair of +1.95, and
the same sign. The flip appears only when the field is rebuilt from the contract's stateless
universe, which also more than halves `in_field`, 64.4% → 32.8%.

That narrowing is not itself surprising: the stateless universe adds an ADR20 floor of 3.5%,
adds a trend gate (`close > SMA50`), sets its ADTV floor at $10M rather than the app's $20M,
and drops the app's membership hysteresis, so it is a much tighter field and fewer of his
names reach it. What the sign says is different and is not explained by tightness: **inside
that narrower field, the published rubric ranks his trades below the field average rather
than above it.** The rubric's edge does not survive the gate the backtest runs under.

*(The trend gate was omitted when this paragraph was first written — the app's universe has
no counterpart for it at all. It turns out to be half the cause; see below.)*

Whether that is a defect in the field construction or a real result about the rubric out of
sample was the open question, and this issue could not settle it. **#211 has**:
[the gate isolation](backtest_gate_isolation.md) attributes it to the **ADR20 floor and the
trend gate acting together** — every single-gate drop leaves the gap negative, dropping both
turns it positive — and returns the verdict **property, not defect**. What was already
settled is where it is *not*: not the bars (bit-identical), not the detector (recall
reproduces to four decimals), and not the population (isolated above); #211 adds that it is
not the liquidity floor and not the membership reconstruction either, and #213 that it is
not the dropped hysteresis band — worth 0.05pp of the gap and two trades of `in_field`
against a gate's 3.5pp. All four differences this paragraph names have now been varied
directly.

**This anchor is a first measurement**, flagged as such in the table precisely so a mismatch is
investigated in both directions rather than charged straight to the new pipeline. The committed
+1.95 has no second measurement agreeing with it. The +1.86 above is now that second
measurement, and it agrees — which moves the suspicion onto the stateless field rather than
onto the pin.

**And that is what resolved the anchor.** Once the pin is corroborated and the reversal is a
measured property of the gates, the mismatch is no longer a claim about the pipeline; it is
the anchor asking its question over the wrong pair. §4b's figure is the app universe's, this
run's field is the contract's, and the table now carries a pin for each
(`in_field` / `in_field_stateless`). The run is checked against its own, matches it exactly,
and the app universe's pin stays where §4b left it — unmoved, and no longer quoted at a run
it does not describe. The sign check rides on the new pin too, so a stateless-universe run
that came back positive would still fail.

A row's universe is now part of what the row *is*, the same way its detector version and its
field already were. `backtest.anchors` refuses a measurement counted over one universe when
the run names the other, rather than reporting it as a sign flip, and
`references/backtest_field_anchors.json` must name the universe it counted — the file being
the one path the documented reproduction command uses.

## What follows from this

- The geometry divergence is **explained**, and the cause is sample composition, proven by
  the fact that the shared 496 trades agree bit-for-bit and that row C reproduces the
  backtest store exactly.
- The anchors stay **pinned at their committed values**, as #197 left them. They are correct
  for the population they were measured over.
- The store and the indicators are **anchored**: whatever else is wrong with this run, the
  bars are the bars the reference study measured.
- The survivorship residual rides on every result out of this run as one line, and is
  bounded by [#196](backtest_survivorship.md) rather than by this page. This run measures it
  larger than findings §2 did, 136 / 325 / 25.9% against 92 / 172 / 18.0%, over a window
  reaching seven years further back — and #196's own bound is larger still.
- The detector is **anchored**: recall reproduces its rate to four decimal places over a
  population 23% smaller.
- `in_field` is **settled, by splitting the pin rather than by waiving the flip.** The
  rubric's edge reverses inside the contract's stateless field, and
  [#211](backtest_gate_isolation.md) attributed that to the **ADR20 floor and the trend gate
  together**, neither alone — a property of the method under the contracted gates rather than
  a defect in the field. It is not the bars, not the detector and not the population. Since
  the figure is a property of the pair (rubric, universe), the anchor now carries one pin per
  universe and this run is checked against its own, which it matches exactly. No constant
  moved and the sign check still rides on both pins.
- **The rubric's edge over the app's field is an edge over names the app's universe lets in
  and the contract's does not.** That is #211's finding, and settling the anchor does not
  soften it. §4b's gap may not be cited without naming the field it was measured over.

Every divergence is recorded through the mechanism rather than only here, so a reader who
never opens this file still cannot mistake one for a match:

```
python -m backtest.anchors --store data/backtest.duckdb \
    --field-measurements references/backtest_field_anchors.json \
    --explain median_range_3bar_adr="..." \
    --explain median_range_5bar_adr="..." \
    --explain median_adr_at_entry_eve="..." \
    --explain coverage_blind_spot="..." \
    --explain detection_recall="..." \
    --out-json references/backtest_anchors.json
```

Run with a cause supplied for the five that need one, all six settle, the command exits zero
and writes `references/backtest_anchors.json`. The table as it printed is committed at
[`backtest_anchors.txt`](backtest_anchors.txt).

The universe is not an argument. It is read off `backtest_field_anchors.json`, because which
of `in_field`'s two pins applies is a fact the run recorded about the gates that screened its
field, not a choice made at the command line. A field-measurements file that does not name
its universe is refused.

A sign flip in §4b's gap is still not explainable, and none was explained away here: the pin
this run is held to is negative by measurement, and a positive result over the contract's
universe would fail exactly as before.

## Reproducing this page

Every number above comes from the two committed stores and the committed reference set:

- the medians, from `backtest.anchors.measure_geometry` against each store;
- the split, from `data/backtest.duckdb.enumeration.US.json`'s exclusion reasons and
  `data/backtest.duckdb.coverage.US.json`'s `stored` list;
- rows A, B and C, by applying those two lists as filters to the replay store's sample;
- the gate-dependent anchors, from `replay.funnel.run_funnel` and
  `replay.discrimination_grid.run_grid` against `data/backtest.duckdb` over
  2019-04-01 .. 2022-12-30 with 126 burn-in sessions, committed as
  `references/backtest_field_anchors.json`;
- the isolation row, from the same `run_grid` against `data/replay.duckdb` with the trade
  list restricted to the names `coverage.US.json` lists as `stored`.

The run those anchors are measured over is itself reproduced by:

```
python -m backtest.full_run --store data/backtest.duckdb
```

Both markets, the whole window, no dates on the command line — they come from
`references/backtest_run_contract.json`. It takes about three hours from a cold store and is
resumable: a second pass reads back every session the first computed.
