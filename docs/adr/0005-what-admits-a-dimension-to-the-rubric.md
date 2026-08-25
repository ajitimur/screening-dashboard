---
status: proposed
---

# What admits a dimension to the rubric, and what retires one

ADR 0001 settled what the rubric *encodes* — the method's revealed selection — ADR 0002 settled
what licenses *loosening* a gate, in two limbs, and ADR 0004 settled what licenses replacing a
threshold with a **graded input**. None of the three says what admits a **new**
dimension to the rubric, or what removes one. That gap is not theoretical: it is how
`Prior move` came to occupy a point of a nine-point rubric across two versions while measuring
**pooled spread 0.000** — 100.0% in the taken group and 100.0% in the not-taken group (§5b) —
a dimension that cannot move the sort under any field, by construction rather than by
misfortune. Nothing was violated when it was added, because nothing had been written down.

**Decided (#160/#161): a dimension is admitted on a selection contrast, and retired on the
absence of one.**

**Admission.** A dimension may enter the rubric only on a selection contrast (§5b's instrument:
taken detections against not-taken detections, no outcome variable) showing a **non-zero gap
with non-zero pooled spread**. Its weight is assigned from the **ordering** of the measured
gaps and never from their values, per ADR 0001's companion rule (#128 Q2): the signs survive
the field's 29% coverage hole and the magnitudes do not.

**Retirement.** A dimension measuring **pooled spread 0.000** is retired, not kept. It cannot
discriminate on any field, so no respecification and no reweighting can recover it, and the
`CONTEXT.md` defence of a **constant dimension** — "kept for what it documents, not for what it
discriminates" — is documentation bought at the price of a point.

**Two explicit exemptions from retirement**, because they are a different failure:

- A **wrong-way gap** (`Base length` −13.4pp, `Orderliness` −9.1pp) is evidence, not absence of
  it. A dimension he hits *less* often than the field he passed over may want inverting or
  respecifying; the measurement is live either way.
- A **×0 weight** is a live question held open at zero cost. `score.py` already records that
  `Base length` ×0 says "the dimension *as specified* earns nothing, not that base length is
  irrelevant," with `BASE_LEN_MAX = 14` named as the suspect. Deleting the row would delete the
  only place that question is visible.

The line the exemptions draw: **zero pooled spread means the dimension can never discriminate;
a wrong-way or zero-weighted dimension is one that discriminates against us, which is a
finding.** `Prior move` fails the first. `Base length` survives on the second.

## A dimension is admitted as a boolean; grading comes later

ADR 0004 permits a threshold to be replaced by a graded input, and its **first condition is
demonstrated signal** — "a null dimension should be weighted down or dropped, never
elaborated." A candidate dimension has no signal yet, by definition; that is what admission
measures. So grading is not available at admission, and a new dimension enters as a boolean
over a persisted quantity like the seven that preceded it. Once admitted and measured, ADR
0004's four conditions govern whether it may be graded, on its own evidence.

This composes rather than conflicts: 0004 asks what to do with a dimension that has signal,
this ADR asks whether a dimension has any.

## Pre-registration

The admission rule is only a guard if the ship criteria are fixed **before** the contrast runs.
Written after the numbers are visible, "the gap was positive" is unfalsifiable, and this rubric
has a track record of intuitions inverting — two of the seven dimensions §5b measured came back
wrong-way. So a candidate dimension is pre-registered as **one** variant, chosen on reasoning,
and the study returns pass or fail on that variant. Selecting among several candidate
booleans by whichever produces the largest gap is magnitude-fitting, which #128 Q2 forbids.

The first dimension registered under this ADR is **`RS line`** (#160, with the rubric change in
#161) — `RS = adj_close(name) /
adj_close(index)`, hit when `RS_today >= RS_at_base_start` over the detection's own base — with
these four criteria fixed in advance:

1. **Δ positive, pooled spread > 0** — ship, at the weight its gap's ordinal position implies.
2. **Δ positive, but disagreement with price-at-new-high-over-base under ~15%** — do not ship.
   The dimension is a restatement of the break test and would be a constant in disguise.
3. **Pooled spread 0.000** — do not ship. It is `Prior move` again.
4. **Δ negative** — do not ship, and record it. A negative gap says he selects names whose
   strength against the index *decayed* through the base, which is worth knowing.

Criterion 2's ~15% is a judgement, not a measurement, and is the one magnitude in this design
without evidence behind it. It is stated here so that a later argument about it is an argument
about a number on the record rather than a number nobody wrote down.

## The regime bound every candidate carries (#169)

Every contrast this ADR governs is measured on the same reference set: US breakout longs,
2019-10 to 2022-11. §3f of the replay findings put a number on what that costs. Over the twelve
months before his entries, **`QQQ` was negative on 1.7% of them** — roughly ten of 582 — and its
own median trailing-year return on those dates was **+39.7%**.

So the record holds almost no bear-market long-horizon observations. Two things follow, and a
pre-registration is expected to state both rather than rediscover them:

- **An index-relative dimension cannot be validated for a falling tape here.** It can be shown
  to select his entries against a rising one. That is a weaker claim, and the weight assigned
  from it inherits the weakness.
- **Netting out the index bounds the caveat; it does not remove it.** §3f's relative figures
  survive the subtraction — 74.2% of entries beating the index over `6m` against 37.8% of the
  same names on ordinary days — which is evidence of selection rather than of tape. It is not
  evidence that the selection works when the tape reverses, and a subtraction reads more
  reassuring than it is.

This bound sits alongside, and does not replace, the two the study already carries: §2's
coverage hole and §9's absence of a control group. `docs/out-of-sample-backtest-plan.md` is the
instrument that could retire it, since it is the only planned measurement outside this window.

## Considered options

- **Admit dimensions on judgement, as before.** Rejected: that is the process that produced a
  dimension with zero spread, and there is no reason to expect the next one to be luckier.
- **Retire on any weak or wrong-way gap.** Rejected: it would take `Base length`, `Orderliness`
  and `Volume`, discarding three live measurements. A dimension pointing the wrong way is the
  most informative kind — it says the rubric and the method disagree, and that disagreement is
  the whole subject of ADR 0001.
- **Require an outcome regression rather than a selection contrast.** Not available: §5a found
  no dimension predicts MFE (largest |r| = 0.158, pointing the wrong way), and ADR 0001 already
  rules outcome inadmissible against the rubric.
- **Keep `Prior move` at ×0 rather than retiring it**, mirroring `Base length`. Rejected: ×0
  preserves a row worth reading, and this row cannot be read. Its 100%/100% hit rates are not a
  finding about the method — they are an artefact of every detection having cleared the same
  decile gate to exist.

## Consequences

- **`Prior move` is retired and the rubric's floor goes with it.** The permanent 0.5★ that
  `score.py` describes — "``Prior move`` fires for every detection by construction (a permanent
  half-star floor)" — was that dimension. The real star range becomes **0.0–4.5**, and
  `test_score.py`'s floor assertion inverts from "always ≥ 0.5" to "0.0 is reachable."
- **The decile gate leaves the score and returns as metadata.** With `Prior move` gone, nothing
  in a breakdown records that a name cleared the gate ADR 0003 is about. The **binding lookback
  name** (`"3m"`) is emitted as a non-scored field instead. Its **percentile is deliberately not
  emitted**: §7 of the findings holds the no-percentile constraint to be permanent, on the
  ground that a percentile against a holed field "would look precise while quietly flattering
  the rubric." That constraint governs the replay rather than the live app, whose ranks have no
  such hole — but the margin is thin enough that the lookback's *name* is the honest thing to
  publish and the percentile is declined.
- **A new dimension forces a rubric version.** `RS line` ships as `RUBRIC_VERSION = 4`, joining
  the `RUBRIC_WEIGHTS` table so the paired re-run (#136) can score one field under v3 and v4 and
  separate a rubric change from a field change. Digests written under v3 are not recomputed.
- **The new dimension is measured on US only and ships to IDX unmeasured.** The replay field is
  US-only, so `RS line` is contrasted against `^IXIC` and never against `^JKSE`. §8 permits a
  weight *ordering* travelling to IDX as shape rather than magnitude, and `Tightness` and `ADR`
  already ride that precedent — but those were reweights of measured dimensions and this is a
  whole dimension, so the precedent is being stretched rather than applied. Recorded here
  rather than inherited silently.
- **The benchmark is `^IXIC`, with a known concentration bias.** Scoring NYSE industrials
  against a tech-heavy cap-weighted index measures something other than their own tape.
  `^GSPC` was considered and declined: a second reference instrument per market means the
  scorer and `regime.py` disagree about what the market is, for reasons nobody will recall.
  Revisit only if the dimension is found to fire on sector lines.
- **The contrast this rule reads must be re-run under `DETECTOR_VERSION = 2`.** §5b's published
  table — 69 taken against 14,354 not-taken — was measured under detector v1. #154's graded
  tightness grew the detector's population by **+111.3 detections per session (+123%)**, and
  while §3's detection row and §4's `in_field` anchor were re-pinned (104 → 159 of 656 — since
  amended to 242 → **349 of 656** on the whole field, and **397** under the live detector v3;
  #165, findings §4b), §5b was not. An ordinal position assigned against the v1 table would rank a v2-measured dimension
  among v1-measured ones, which is the field-change-versus-rubric-change confound in a new
  costume. The admission rule therefore requires the contrast to be **measured under the
  detector the dimension will ship against**.
- **The study's field carries a known, measured contamination.** `^IXIC` was synthesized as a
  rankable candidate in `replay.duckdb` (#162), inflating each session's ranked population by
  one name in ~1,000. It reaches neither the detections nor the not-taken group — 0 detection
  rows, and 0 of 505 sessions above the 0.90 gate, global max percentile 0.8246 — so the
  contrast is clean and only percentile denominators shift, by ~0.1%. Fixed separately rather
  than before the study, because rebuilding 4.7M rank rows would run this contrast against a
  different field than §5b did and break the comparability the ordinal rule depends on.
- **This is hard to reverse in the direction that matters.** Retiring a dimension changes the
  ceiling's composition and every digest frozen afterwards; re-admitting it later would need
  the evidence this ADR requires, which for `Prior move` can never exist.
