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

### First registration: `RS line` (#160) — **measured, and refused**

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

**The verdict was do not ship**, on criterion 4 (findings §5d): Δ **−5.8pp** under detector v1
and **−2.1pp** under the live v3, with criterion 2 at 11.2% disagreement standing ready to
refuse it had the sign come back the other way. The mechanism was the **anchor** — `base_start`
is a local high under both of the detector's branches, so the rule asks a name to hold its
ratio to the index measured *from a local maximum*, which almost nothing does. The dimension
fires on one detection in ten in **both** groups. So the process worked: a criterion nobody
could argue with afterwards fired on a number nobody had seen when it was written. `Prior move`
stayed at ×1, `RUBRIC_VERSION` stayed 3, and the slot stayed open.

### Second registration: `Relative move` (#170) — measured, and undecided

§3f (#169) measured the quantity `Prior move` gates on, directly, for the first time, and found
it has real spread once expressed as a degree: `6m` median **+55.8%**, p25 +15.1 to p95 +370.7,
and **74.2%** of his entries beating `QQQ` over six months against **37.8%** of the same names
on an ordinary day — `^IXIC`, which is `MARKET_INDEX` and so the benchmark this dimension would
actually use, reads **75.1%** on the same column. That is the limb this ADR requires and the
binary dimension cannot reach — so the slot `RS line` failed to fill has a second candidate.

**The dimension, as registered.** The name's `6m` calendar return **relative to
`MARKET_INDEX`**, compounded, in **ADR units**:

```
value = ((1 + r6m(name)) / (1 + r6m(index)) − 1) / ADR(name)
hit   = value > 0
```

- **Compounded, not subtracted.** Over six months a percentage-point difference and a multiple
  are different quantities, and only the second means "outran the market" (§3f's own wording,
  and its own arithmetic).
- **Both legs are `indicators.calendar_return`** — the rank table's own definition,
  calendar-anchored through `anchor_date`, resolving to the **last bar on or before** the
  anchor. This is the one place the dimension departs from `RS line`, which requires a bar
  *exactly* on its anchor, and the departure is forced: an anchor six calendar months back
  lands on a weekend or a holiday about three days in ten, so an exact rule would score a
  calendar artefact rather than a name. `RS line`'s anchors are traded sessions by
  construction, which is why exactness was free there.
- **A missing bar on either leg scores `False`**, with the value **absent rather than zero**,
  and is never carried forward. Same rule and same reason as `RS line`: scoring `False` costs
  at most one point on a rare edge, where *excluding* the name would let a data gap remove a
  candidate from the list. A name that had not listed six months ago is already absent from the
  `6m` lookback in the rank table, so this is the substrate's convention and not a new one.
- **`ADR` is the name's own `SMA20(high/low − 1)`, taken at the session being scored** and
  never past it, absent under 20 bars — and absent means `False` by the rule above. The
  denominator is where a lookahead would hide: the replay hands whole bar series in and never
  slices them to the session, which is safe for `RS line` because it reads two named sessions
  exactly, and is not safe for a trailing average. `relative_move_adr` does its own slicing.
- **The benchmark is `MARKET_INDEX`** — `^IXIC` (US), `^JKSE` (IDX) — declined `^GSPC` for the
  reason in the consequences below. §3f's headline columns are `QQQ` and its `^IXIC` check
  reproduces every row within two points, so the switch of benchmark is not load-bearing for
  the result — but every figure quoted here is `QQQ`'s unless it says otherwise, and the
  contrast will be run against `^IXIC`.
- **It is named `Relative move`, not `Prior move`.** `score.RUBRICS` re-scores a stored
  breakdown by dimension *name*, so reusing the label would make a v4 row mean one quantity and
  a v3 row another under the same key, and the paired A2 re-run (#136) would compare two
  quantities while believing it compares two rubrics. The executable definition is
  `screener.relative_strength.relative_move_adr`.

**Why `6m`, fixed before the contrast exists.** Two figures §3f published: the beat-rate against
the index is *higher* at `6m` (74.2%) than at `12m` (67.5%; both `QQQ`), and 26.0% of entries
underperformed the index over the year; and while the entry-vs-ordinary gap in ADR units is
larger at `12m` (+22.83 against **+12.41**), §3f records that column as the noisier one — an
ordinary day's `12m` median is +0.4%, so it is set by a handful of ten-baggers, where `6m` sits
against an ordinary day's −11.2%. One window. Trying three and keeping the widest gap is the
magnitude-fitting this section exists to prevent.

**Why the cut sits at zero, and what the ADR units are for.** ADR is positive, so the
denominator cannot flip a sign: **the boolean is ADR-invariant**, and "outran the index" is the
whole rule, with no free parameter — the property that made `RS line`'s definition honest, kept.
Any non-zero ADR cut-point would be a magnitude read off the replay, which #128 Q2 forbids, and
no published boundary supports one: §3f denominates the *raw* returns in ADR and the *relative*
ones in percent, so even ADR 0004's "use the study's own bucket edges" route is unavailable
here. The units therefore buy nothing at admission — they buy the **stored value**. This ADR
admits a dimension as a boolean because grading needs demonstrated signal and a candidate has
none; but a breakdown row carries the value while the rubric owns the mapping (#154), and a row
cannot be re-denominated retroactively. Persisting ADR units now is what would let ADR 0004's
grading question be asked later, on measured evidence, without re-scoring history. A tie scores
`False`; that is measure-zero and is fixed only so the definition has no ambiguity.

**The weight is not a number yet, and that is the rule rather than an omission.** Weights come
from the *ordering* of the measured gaps. §5d republished that ordering under the live detector
— ADR +26.4, Tightness +13.5, MA support +6.3, `Prior move` 0.0, Volume −0.3, Orderliness −5.9,
Base length −7.8 — with ×2 held by the top two and ×1 by everything positive below. So: **×2 if
the measured Δ outranks `Tightness`, ×1 otherwise.** That is an ordinal position, not a reading
of a gap's value.

The four criteria, fixed in advance:

1. **Δ positive, and the not-taken hit rate between ~15% and ~85%** — ship, at the weight above,
   as `RUBRIC_VERSION = 4`, and `Prior move` retires with the binding-lookback metadata
   replacing it (see the consequences). A hit rate strictly inside those bounds makes pooled
   spread non-zero by construction, so the original criterion 1's second clause is carried
   rather than dropped.
2. **Δ positive, but disagreement with `Prior move` under ~15% on the not-taken group** — do not
   ship. `Prior move` is `True` on every detection, so disagreement with it is exactly
   `1 − hit rate`, read on the same group criteria 1 and 3 read. A dimension
   firing on more than five names in six of the field he passed over is the constant in a new
   costume: the decile gate
   already guarantees top-decile in one of four lookbacks, and a `6m`-relative grade may have
   little left to say *within* that population even though it has plenty within his trade
   record. §3f cannot see this — it never looks at the field — which is why #171 exists and why
   this is the criterion most likely to fire.
3. **The not-taken hit rate under ~15%** — do not ship. This **widens** criterion 3 as it was
   written for `RS line` ("pooled spread 0.000"), and the widening is §5d's tuition: that
   dimension had pooled spread **0.326** and still could not speak, because a rule firing on one
   detection in ten measures its −2.1pp gap across a sliver of the field. Spread 0.000 is the
   degenerate case of the two bounds — 0% here, 100% under criterion 2 — so nothing is lost by
   stating it this way, and the rule gets harder to pass rather than easier.
4. **Δ negative** — do not ship, and record it. **This is what kills it**, and it is the
   pre-registered answer to the objection that `RS line` had this shape already.

**What a negative gap would mean, said before the numbers.** `RS line`'s Δ is negative because
he selects names whose strength against the index *decayed through the base* — and §5d's own
post-mortem names the anchor as the mechanism. This dimension is anchored somewhere else: a
fixed calendar date six months back, which on the modal detection (median base length 12) sits
roughly five months before the base begins. It measures the advance, where `RS line` measures
the consolidation of it. That is the argument, in advance, for why the two are different
statistics. **If Δ comes back negative anyway, the anchor was not the mechanism** — and what is
measured is that within an already-gated field he selects names with *less* index-relative
strength than the ones he passed over. That folds the index-relative family, not just this
variant, and **no third anchor may be proposed off the back of it**: choosing one after seeing
two negatives is exactly the fitting this section forbids. The `Prior move` slot would then be
closed by evidence rather than left open by default, which is a result worth having.

**Two things this registration deliberately does not settle.** It says nothing about
`detection_gate`, which stays a percentile union of four lookbacks — this is about the rubric
only. And the boolean cannot duplicate the `ADR ×2` dimension, being ADR-invariant, but a later
*graded* form would divide by the same quantity a ×2 dimension already scores; that is a
question for the grading proposal ADR 0004 would govern, and it is recorded here so that
proposal starts from it rather than discovering it.

**If it ships, the decile gate leaves the score, and #161's answer is what brings it back.**
`Prior move` is the only breakdown row recording that a name cleared the gate ADR 0003 is about
— the one discarding ~40% of his real entries — so retiring it without a replacement loses that
outright. The replacement is the **binding lookback name** (`"3m"`) as a non-scored field on the
candidates payload, and **not** its percentile, for the reason the consequences give. This is
not a separate ticket because it only becomes real if this dimension is admitted; if it is
refused the way `RS line` was, `Prior move` stays at ×1 and the gate keeps its record in the
score.

**It was inert until #171 ran.** §3f is executed trades against a same-name background, which is
not a control group of rejected setups — the footing `RS line` was rightly refused on. Until the
selection contrast existed there was no Δ, no pooled spread and no hit rate, and none of the four
criteria could fire. #171's constraints attached: the contrast is measured under the detector the
dimension would ship against (live v3, not the store's persisted v1), and it reproduces §5b's
seven gaps as its control before anything new is trusted. Three bounds ride the result whatever
it says: §2's coverage hole (§3f joined **70.2%** of his logged breakout longs to bars, skewed
against the blown-up 2020–21 small-cap cohort), §9's absent control group on the *trade* side,
and the regime bound below — which this candidate carries with full force, being index-relative
by construction.

#### The result (#171, findings §5e): **the criteria do not separate, and nothing ships**

| Field | Taken | Not-taken | Δ | Pooled spread | Disagreement with `Prior move` |
| --- | --- | --- | --- | --- | --- |
| detector v1 | 91.3% (n=69) | 87.3% (n=14,354) | **+4.0** | 0.332 | 12.7% |
| detector v3 (live) | 88.6% (n=140) | 84.9% (n=34,543) | **+3.6** | 0.357 | **15.1%** |

Δ is **positive on both fields**, which is the one thing `RS line` never managed and the
pre-registered evidence that the anchor was the mechanism behind its null. Criterion 4 does not
fire. Criterion 3 does not fire.

**Criteria 1 and 2 are the same number, and it landed on its own bound.** Disagreement with
`Prior move` is exactly `1 − hit rate`, so the ~85% ceiling and the ~15% floor are one threshold
read from two sides. Under v1 the not-taken hit rate is 87.3% and criterion 2 refuses the
dimension. Under the live v3 — the field the ADR requires the verdict to be read on — it is
**84.94%**, which is **0.06pp** inside the ceiling and **0.29 standard errors** from it (s.e.
0.19pp at n=34,543). On the literal threshold criterion 1 admits it; on any reading that honours
the tilde it does not.

**This ADR declines to resolve that, and records why.** The ~15% was written down as "a
judgement, not a measurement… the one magnitude in this design with nothing behind it," to be
argued about *before* it decided anything. It has now decided something by six hundredths of a
point, and the argument has not happened. Choosing a rounding here is choosing a verdict after
seeing the number, which is the move the pre-registration clause exists to prevent — and the
choice is not small: admission retires `Prior move`, forces `RUBRIC_VERSION = 4`, and changes the
composition of every star ceiling frozen afterwards, which the consequences below call hard to
reverse in the direction that matters.

**Nothing shipped.** `RUBRIC_VERSION` stays 3, `DIMENSIONS` is untouched, `Prior move` keeps its
×1 and the decile gate keeps its record in the score. Had the dimension been admitted its weight
would have been **×1**: Δ +3.6 ranks below `Tightness` (+13.5) and below `MA support` (+6.3), so
the ordinal rule puts it with the ×1s.

**The gap is not firm either, and that is the more useful half of the result.** Δ +3.6pp carries
a standard error of **2.70pp** on a taken group of 140 — 1.35 s.e. from zero, before §2's
coverage hole is allowed for at all. The mechanism is the one criterion 2 was written for: within
a field the decile gate has already filtered, **89.2% of the not-taken detections are up over six
months** and 88.5% over twelve, so a `6m`-relative grade has little left to say there however
much it has to say inside his trade record. `Prior move`'s 100.0%/100.0% is the limiting case of
the same fact. §3f could not see this, because it never looks at the field.

**What is settled, and what a third candidate must answer first.** The index-relative family is
not folded — a positive Δ on both fields is the opposite of the result that would have folded it,
and the anchor distinction the registration argued for in advance held up. What is not settled is
this threshold. **No third candidate should be registered until the ~15% has been argued on its
own**, because the next one will meet the same bound and a threshold chosen after two dimensions
have bounced off it is not a pre-registration.

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

**None of the first four have happened.** They are what follows *if* a registered dimension is
admitted, and nothing has been: `RS line` was refused on criterion 4, and `Relative move` was
measured by #171 and landed on the threshold that decides it. They are written in the indicative
because they were written before the first verdict, and are left that way — a consequence
restated as a hope reads as a weaker commitment than it is.

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
- **A new dimension forces a rubric version.** An admitted dimension ships as
  `RUBRIC_VERSION = 4`, joining the `RUBRIC_WEIGHTS` table so the paired re-run (#136)
  can score one field under v3 and v4 and separate a rubric change from a field change.
  Digests written under v3 are not recomputed.
- **The new dimension is measured on US only and ships to IDX unmeasured.** The replay field is
  US-only, so a candidate is contrasted against `^IXIC` and never against `^JKSE`. §8 permits a
  weight *ordering* travelling to IDX as shape rather than magnitude, and `Tightness` and `ADR`
  already ride that precedent — but those were reweights of measured dimensions and this is a
  whole dimension, so the precedent is being stretched rather than applied. Recorded here
  rather than inherited silently.
- **The benchmark is `^IXIC`, with a known concentration bias.** Scoring NYSE industrials
  against a tech-heavy cap-weighted index measures something other than their own tape.
  `^GSPC` was considered and declined: a second reference instrument per market means the
  scorer and `regime.py` disagree about what the market is, for reasons nobody will recall.
  Revisit only if the dimension is found to fire on sector lines.
- **The contrast this rule reads must be re-run under the detector the dimension ships
  against** — written as `DETECTOR_VERSION = 2` when this ADR was drafted, and already one
  version stale by the time §5d ran it: #149 admitted `12m` to the detection gate
  afterwards, so the live detector is **v3**. The requirement is the version the dimension
  would ship against, not the number written here. §5b's published
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
