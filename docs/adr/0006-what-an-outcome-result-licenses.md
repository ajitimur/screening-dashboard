---
status: accepted
---

# What a candidate outcome test licenses

ADR 0005 admits a dimension to the rubric on a **selection contrast** — taken detections
against not-taken detections, no outcome variable — and its considered options record why:
"Require an outcome regression rather than a selection contrast. **Not available**." When that
was written it was true. §5a found no dimension predicts MFE, and ADR 0001 rules outcome
inadmissible against the rubric, which is a claim about what the rubric *encodes* and not a
claim that outcomes are unmeasurable.

The out-of-sample backtest (PRD #182) changed the availability. `backtest.candidates` (#195)
measured both registered candidates against an outcome variable — R after costs, on trades
taken mechanically over a window the trade record does not cover, with no rubric weight fitted
to it and no detection able to see it. That instrument did not exist for ADR 0005 and this ADR
says what it licenses.

**Decided (#221): a candidate outcome test changes what a dimension owes, never what it gets.**

It admits nothing on its own and retires nothing on its own. The selection contrast remains the
only instrument that decides. What this ADR adds is a rule for when a *further* measurement is
required before ADR 0005's criteria can be read, and what a wrong-way outcome result obliges.

## The measurement this ADR governs

The **candidate outcome test** as `backtest.candidates` defines it and
`references/backtest_candidate_outcomes.json` commits it: for a registered candidate
dimension, the hit group's mean R against the miss group's mean R, with a symbol-clustered 95%
interval on the gap. Absence is a group and never a value on the cut — a name that had not
listed six months back, or that was missing a price at an anchor, enters no gap.

## What it licenses, coming in: the crowding rule

ADR 0005's criterion 2 refuses a dimension whose not-taken hit rate is above ~85% — restated
there as disagreement with `Prior move` under ~15%, which is the same number read from the other
side. **That criterion is narrowed here, and the threshold does not move.**

A dimension whose not-taken hit rate is **at or above 85%, or within one standard error of it**,
is a **crowded dimension**. It is no longer refused. It owes a candidate outcome test, and ADR
0005's criteria cannot be read on it until that test has been run.

`scripts/relative_move_contrast.py` already computes exactly this region: `HIT_RATE_CEILING =
0.85` with a one-standard-error band, returning `on_the_bound`. Nothing in that script changes.
What changes is what `on_the_bound` obliges — a further measurement rather than a stall.

### Why the old criterion was wrong, and what it was right about

Criterion 2 was guarding against a real thing, stated in its own words: a `6m`-relative grade
"may have little left to say *within* that population even though it has plenty within his trade
record." That is a claim about the dimension being **uninformative inside an already-gated
field**. It is not a claim about the dimension being mechanically unable to move the sort —
criterion 1's pooled-spread limb owns that, and criterion 3 owns its mirror.

The firing rate was a **stand-in** for informativeness, chosen because nothing measured
informativeness directly. The stand-in is now measurable, and it was wrong. On the backtest
field `Relative move` fires on **90.0%** of US detections (11,014 hit against 1,217 miss) and
**92.2%** of IDX detections (1,087 against 92) — both *further past* the ceiling than the 84.94%
that stalled it on the replay field. On IDX the 7.8% it does not fire on returned **−1.075R**
against the hit group's **+0.852R**. A dimension true of nearly every name separated outcomes
decisively.

The "constant in disguise" language criterion 2 carries was borrowed from `Prior move`, which is
true of **100%** of detections in both groups and genuinely cannot move anything. 85% is not
100%, and 92 IDX trades is not nothing. **`Constant dimension` and `Crowded dimension` are
different objects**, and ADR 0005 treated them as one.

### Why the threshold does not move

Choosing a new number now — with `Relative move`'s 84.94% already visible — is the
magnitude-fitting ADR 0005's pre-registration section exists to prevent, and it is the specific
failure that section warned about: "Choosing a rounding here is choosing a verdict after seeing
the number." So 85% stays exactly where it was written.

What changes is the **job** it does, and the change repairs the complaint ADR 0005 filed against
it. That ADR called the ~15% "a judgement, not a measurement… the one magnitude in this design
with nothing behind it," and it was right to, because a number deciding *ship or do not ship*
must be defensible to the hundredth of a point. A number deciding **which candidates owe a
further measurement** can be approximately right and still do its job correctly. The threshold
was never fit for the first task. It is fit for the second.

## What passing the test means

A candidate outcome test is **passed** when:

1. **At least one market's gap clears zero** — its symbol-clustered 95% interval sits entirely
   above zero, which is the verdict rule `backtest.candidates` fixed in advance (#195); and
2. **No market points the wrong way** — no market's gap interval sits entirely below zero.

**The gap is read with the absent group excluded.** `backtest.candidates` reports a second
figure that reads absence as a miss, which is what a shipped boolean would do; that figure is a
diagnostic and the payload says so — "what a shipped boolean would do with it is reported
separately and sets no verdict." The two disagree on the US for `Relative move` (+0.396R
crossing zero at −0.03; +0.454R clearing it at +0.05), and choosing the passing row after seeing
which one passes is verdict-shopping. **The pre-registered row is read, always, including when it
is the one that fails.**

### Why one market suffices, and why §8 permits it

`score.py` holds **one rubric for both markets** and argues its own case for that: "one set
serves both markets… a weight *ordering* is shape not magnitude, so §8 permits it travelling to
IDX." Findings §8 is the governing prior — **shapes travel between US and IDX, magnitudes do
not** — and it constrains what a single-market outcome result may carry.

**A gap's size is a magnitude and does not travel.** `+1.927R` is a fact about Jakarta.

**Sign agreement across markets is a shape and does travel.** Across the four measured cells,
`Relative move` is positive in **both** markets and `RS line` is negative in one. §8's own
examples of travelling shape are rules of this kind — "that a dimension's null must be read
against its spread" — and this is one: *a dimension that points the same way in both tapes, and
decisively in the one with power, is showing a property of the method rather than of a regime.*

Condition 2 is what makes this a shape claim rather than a magnitude claim, and it has teeth:
`RS line` fails it on the US (−0.191R), so this rule would have refused it on outcome grounds
the way ADR 0005's criterion 4 refused it on selection grounds.

**This does not license a per-market rubric.** `references/backtest_idx_adr_floor.md` reached
the same conclusion for `ADR_FLOOR` — "keep 3.5%, and do not make the constant per-market on
this evidence" — and the same reasoning holds here. Splitting the rubric would need to overturn
`score.py`'s §8 argument, which nothing measured here does.

## What it licenses, going out

**A wrong-way candidate outcome test retires nothing.** Money evidence does not decide in either
direction; ADR 0005's instrument still does.

A dimension whose gap interval sits **entirely below zero** in any market is **re-argued**: a
ticket is opened, at the time the outcome result is recorded and not deferred, requiring that
dimension's **selection contrast to be re-run under the current detector**. The dimension
**keeps its weight** while that is pending, because weights come from the selection ordering and
nothing else (below).

Dropping the dimension to **×0** is an outcome the re-argument may reach, not something that
happens automatically. ADR 0005 already holds ×0 to be "a live question held open at zero cost,"
and that is the right shape for a dimension under re-argument — but ×0 is a rubric change and
forces a version stamp, so it is a conclusion the re-argument draws rather than a consequence
this ADR imposes.

**The asymmetry is deliberate.** Neither direction decides. Coming in, the outcome test unblocks
ADR 0005's criteria; going out, it obliges ADR 0005's criteria to be re-read. In both directions
the selection contrast is what speaks.

## Weight is untouched

**A candidate outcome test never sets, raises, or lowers a weight.** ADR 0001's companion rule
(#128 Q2) stands unqualified: the replay licenses a change's *direction*, from the **ordering**
of the measured selection gaps, and never a gap's value. An outcome gap is a value, from a
different instrument on a different field, and ranking dimensions by it would mix two orderings
into one — the field-change-versus-rubric-change confound ADR 0005 spent a consequence guarding
against.

There is also nothing to rank in. Two of eight dimensions have ever had a candidate outcome
test run on them. A dimension admitted with an outcome test in the loop takes its ordinal
position in the **selection** gap ordering, exactly as one admitted without.

## ADR 0002 does not govern admission

`references/backtest_findings.md` records that an outcome result "goes through the calibration
rule — ADR 0002, as findings §7 restates it — like any other change." That phrasing is loose and
is corrected here.

ADR 0002 governs **loosening a gate**. Its score-dimension limb reads "a score dimension may be
loosened only when A3 shows that dimension has no signal *and* that dimension shows real
spread"; its four-condition limb governs a cross-sectional cut. Admitting a new dimension is
neither. Replay findings §7 already draws this distinction for two other changes — the stop
convention is "outside the rule entirely" and the tightness restructure is one "ADR 0002 does not
govern… and ADR 0004 records what does" — and admission is a third case of the same kind.

**Admission is governed by ADR 0005, as narrowed here.** Making this ADR pretend to satisfy a
rule built for a different kind of change would be worse than naming the rule that applies.

## Provisional admission

**Any dimension admitted with a candidate outcome test in the loop is admitted provisionally**,
and is re-read when the next out-of-sample measurement runs. `docs/out-of-sample-backtest-plan.md`
is the instrument.

**No minimum sample size is set**, and the omission is deliberate. A floor chosen now would be a
magnitude picked with the answer already visible — the same failure as moving the 85%. The
symbol-clustered interval already prices small samples, which is what a clustered bootstrap is
for. What the thinness obliges is that it be **stated wherever the figure is quoted**, not that
an arbitrary threshold be invented to gate it.

## The bounds this rule carries

Every one of these attaches to any admission made under this ADR.

- **The deciding sample is thin.** IDX holds 1,196 closed trades over 247 symbols across
  fourteen years, and the miss group behind `Relative move`'s gap is **92 trades**. The interval
  clears zero; the sample is small.
- **IDX's survivorship bound is the weaker one.** Jakarta's hole is counted on the enumeration
  side, is neither exposure-weighted nor separated from recycled tickers, and is therefore
  optimistic in a known direction. The true bound can only be lower.
- **The regime bound is inherited whole from ADR 0005.** No index-relative dimension has been
  validated against a falling tape. `QQQ` was negative before 1.7% of his entries, and the
  backtest does not retire this bound so much as widen the window it was measured in.
- **Multiple testing.** `backtest.candidates` reports 20 intervals at a nominal 95%, of which the
  four gap rows are the measurement and the rest are diagnostics. IDX `Relative move`'s gap is
  p=0.002, which clears a correction over the four gap rows comfortably. Recorded so a later
  reader does not have to reconstruct it.
- **The US graded correlation points the wrong way.** ρ = −0.021 on the US against +0.068 on
  IDX. This ADR admits booleans and the correlation sets no verdict here, but any ADR 0004
  grading proposal for this dimension starts from it rather than discovering it.

## Consequences

- **ADR 0005's criterion 2 is narrowed, not deleted.** Its threshold is unchanged and its
  purpose is unchanged. What changes is that tripping it obliges a measurement instead of
  returning a refusal. ADR 0005 carries a pointer to this ADR at that criterion.
- **ADR 0005's block on a third candidate is lifted.** That ADR held that "no third candidate
  should be registered until the ~15% has been argued on its own." This is that argument, and
  the register is open.
- **`on_the_bound` changes meaning without changing behaviour.** The harness returns the same
  verdict on the same computation; a `on_the_bound` result now means the dimension is crowded
  and owes a candidate outcome test.
- **`Relative move` is admitted**, at ×1, as `RUBRIC_VERSION = 4`. The reading is recorded in
  full below. The code change is a separate ticket, so that no constant moves before this rule
  lands.
- **A candidate outcome test is now part of a crowded dimension's registration.** A candidate
  registered from here that is expected to be crowded should say so when it registers, rather
  than discovering the obligation after the contrast runs.

## The reading: `Relative move` (#170, #171, #195) — **admitted**

Applied after this rule was written, not before.

| step | ADR 0005 criterion | reads | outcome |
| --- | --- | --- | --- |
| gap and spread | 1, first limb | Δ **+3.6pp**, pooled spread **0.357** (detector v3) | passes |
| crowding | 2, as narrowed here | not-taken hit rate **84.94%**, 0.29 s.e. inside the ceiling | **crowded — owes a candidate outcome test** |
| the outcome test | this ADR | IDX **+1.927R** [+0.57, +3.14] clears; US **+0.396R** [−0.03, +0.77] does not clear and does not point the wrong way | **passes** — one market clears, none against |
| too few names | 3 | 84.94%, far above the ~15% floor | does not fire |
| wrong-way gap | 4 | Δ positive on both fields | does not fire |

**Admitted, at ×1.** Δ +3.6pp ranks below `Tightness` (+13.5) and `MA support` (+6.3) in §5d's
republished ordering, so the ordinal rule puts it with the ×1s — the weight ADR 0005 had already
computed for this dimension had it been admitted. `RUBRIC_VERSION = 4`. **Provisional**, and
re-read at the next out-of-sample measurement.

The consequences ADR 0005 wrote for an admission now fire: `Prior move` retires, the rubric's
permanent 0.5★ floor goes with it, the star range becomes 0.0–4.5, and the decile gate returns
as the **binding lookback name** on the candidates payload with its percentile deliberately not
emitted.

## Considered options

- **Delete criterion 2 outright.** Rejected: a high firing rate is genuine grounds for
  suspicion, and criterion 3 does not catch the crowded case — it catches the sparse one. The
  guard was aimed at something real and only its instrument was wrong.
- **Move the threshold instead.** Rejected: this is the exact move ADR 0005's pre-registration
  section forbids, and doing it with `Relative move`'s 84.94% already on the page would be
  indefensible however defensible the new number.
- **Read the as-shipped gap** (absence counted as a miss). Rejected: it is the row that passes on
  the US, and it was pre-registered as a diagnostic. Switching to it now is verdict-shopping.
- **Require every market to pass.** Rejected: the thinner market will rarely have the power, so
  the rule would refuse everything and never fire.
- **Let any single market's pass suffice, with no wrong-way condition.** Rejected: it would carry
  a magnitude across markets in violation of §8, and it would admit a dimension that loses money
  in the market it mostly ships to.
- **Make the rubric per-market.** Rejected: `score.py` argues the shared rubric is what §8
  requires, `backtest_idx_adr_floor.md` refused the same split for `ADR_FLOOR` on the same
  reasoning, and nothing measured here overturns either.
- **Retire on a wrong-way outcome result.** Rejected (#221): it would let outcome evidence decide
  on its own in one direction while merely unblocking in the other. Obliging a re-argument keeps
  the instrument to one job in both directions.
- **Set a minimum sample size for a passing outcome test.** Rejected: a magnitude chosen with the
  answer visible. The clustered interval already does this work honestly.
- **Amend ADR 0005 in place.** Rejected: 0005's considered options record that an outcome
  instrument was *not available*, and that sentence is why the document is shaped as it is.
  Overwriting it would delete the reasoning and leave the conclusion.
