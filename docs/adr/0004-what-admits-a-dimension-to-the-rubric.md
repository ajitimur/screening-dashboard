---
status: proposed
---

# What admits a dimension to the rubric, and what retires one

ADR 0001 settled what the rubric *encodes* — the method's revealed selection — and ADR 0002
settled what licenses *loosening* a gate, in two limbs. Neither says what admits a **new**
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
- **A new dimension forces a rubric version.** `RS line` ships as `RUBRIC_VERSION = 3`, joining
  the `RUBRIC_WEIGHTS` table so the paired re-run (#136) can score one field under v2 and v3 and
  separate a rubric change from a field change. Digests written under v2 are not recomputed.
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
