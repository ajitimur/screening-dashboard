# PROTOTYPE — momentum candle, then a coil above the MAs

**Throwaway.** Nothing imports this. Not part of the pipeline, the rubric, or the backtest.

## The question

A momentum candle on big volume, then a tight consolidation that holds above the
rising moving averages while volume goes quiet — does that rule set fire on the
boxes marked by eye (the golden set below), without drowning the watchlist in junk?

Blank slate by decision: independent of the `volume-dryup` prototype's labels
and findings (grilling 2026-09-13, Q9 = b).

## The rules (all constants at the top of `coil.py`)

- **Momentum candle** — close-to-close gain ≥ 1×ADR, close in the upper *half*
  of the day's range (see finding 1), volume ≥ 1.8× the mean of the 20 bars
  before it.
- **Thrust** — the maximal run of consecutive up-closes containing at least one
  momentum candle, capped at its last 5 days, total gain ≤ 20% (see finding 5).
- **Box** — 3–15 days, starting up to 6 bars after the thrust ends (a pullback
  in between stays outside it — see finding 6); height ≤ 1.5×ADR (in price, as
  of the thrust end); closes above MA50 with `floor(0.10 × days)` violations
  forgiven (MA20 was demoted from gate to score — finding 6); MA50 above its
  value 10 bars earlier; mean box volume below the rolling 20-day average.
- **Score** — MA5/10/20 spread in ADR units on the firing day; tighter sorts
  higher. A ranking, not a gate.

The detector fires *while the box is forming* (point-in-time: `detect(rows, i)`
reads nothing past `i`). One Python implementation feeds both the viewer and
the scan, so they cannot disagree.

## Run it

    backend/.venv/bin/python backend/prototypes/momentum-coil/extract.py   # golden symbols → bars.js + recall report
    open backend/prototypes/momentum-coil/momentum-coil.html              # or: python3 -m http.server 8777 --directory backend/prototypes/momentum-coil

    backend/.venv/bin/python backend/prototypes/momentum-coil/scan.py [YYYY-MM-DD]   # ranked IDX watchlist for one session

Both read `data/screener.duckdb` (IDX bars through 2026-08-31) read-only.
Universe floor in the scan: 30-day mean traded value ≥ Rp 5B.

## Labelled set (marked by eye, all 2026)

After the full August labelling pass (every name the month's sweep surfaced
was judged), the label lists live in `extract.py`:

- **34 must-catch windows — 34 CAUGHT.** The original seven (SGER, TINS,
  SOCI×2, KOKA, GTSI, PTRO) plus 22 plain-yes August names, 4 "ok, but the
  box span differs" names (GGRM, HRUM, IATA, NCKL), and CMRY's long base.
- **5 eye-marked boxes accepted as out-of-pattern** (`OUT_OF_PATTERN`), i.e.
  known, deliberate misses: TKIM and HRTA (MA50 flat/declining — the
  MA50-rising gate stays by decision), LSIP and SMIL (no momentum candle
  exists; quiet drift-up bases are a different pattern), SLIS (coil after a
  +36% parabolic thrust; tentative label).
- **18 must-stay-quiet windows — 3 fully quiet, 15 still fire** on 33 junk
  sessions total. The biggest offender is OILS (13 sessions); most junk names
  fire only 1–5 sessions.

## What the prototype found

**1. The upper-third close rule is the binding gate, and it rejects golden
TINS.** As grilled (close position ≥ 2/3), TINS end-Aug never fires: its two
thrust days — 07-31 (+6.7% on 3.82× volume) and 08-14 (+4.6% on 2.54×) — closed
at 0.60 and 0.53 of their range. Every other clause passed. Relaxed to the
upper half (0.5), all four golden boxes are caught; `CLOSE_POS` is seeded at
0.5 for that reason. Whether 0.5 lets in junk elsewhere is the open trade-off.

**2. Precision looks strong at the seeded thresholds.** Sweeping every IDX
session of Aug 2026 (19 sessions, ~195–219 liquid names each): 1–6 coils per
session, mean ≈ 2.7, and 19 unique symbols across the whole month. All four
golden boxes surface. Setups persist across sessions the way a watchlist
wants: GTSI held 2026-08-12→20, PTRO 08-11→24, SOCI twice (08-10→14 and
08-21→27, matching both golden windows). The non-golden names to label by eye:
KOKA, AADI, AYAM, SIMP, PTRO, MDIA, TKIM, GTSI, HATM, EMAS, YELO, BEEF, AMMN,
ISAT, FPNI, JARR.

**3. SGER fires once (08-10) and then goes quiet, yet the box runs to 08-19.**
Later sessions fail because the box grown from the original thrust exceeds
either the height cap or the MA-violation allowance, and the freshest-thrust
rule finds no newer thrust. One firing is enough to put it on the watchlist,
but "keeps firing while the coil holds" was the Q1(a) framing — worth deciding
whether single-day detection is acceptable or the box should be allowed to
re-anchor.

**4. `floor(0.10 × days)` forgives nothing below a 10-day box.** For the
golden boxes (3–8 days) the MA gate is effectively strict. It didn't cost a
golden catch, but it is stricter than "10% of days" sounds.

**5. The eye rejects coils after parabolic thrusts, and percent beats ADR for
saying so.** The KOKA July box — junk by eye — sat after a +42.7% thrust; the
GTSI mislabel scare sat after +27.5%. Every eye-approved coil's thrust was
≤ 18.5%. In ADR units the split is 2.8 vs 2.9 — too thin to trust — so
`MAX_THRUST = 0.20` is a percent, a deliberate exception to the
everything-in-ADR house style. Caveat: a parabolic run can still sneak in by
re-anchoring to its last ≤20% sub-thrust (GTSI did exactly this before being
relabelled fine), so the cap is a junk *reducer*, not a guarantee.

**6. The grilled MA gate was doing negative work.** Golden KOKA (08-26 →
09-08) closes below MA20 on all 10 box days while coiling on a rising MA50
with MA5/10/20 wrapped tight around price; meanwhile boxes that passed the
MA20 gate were being called junk. Gate demoted to closes-above-MA50-only; the
short MAs live in the convergence score instead. Same session: the box start
was allowed to float up to 6 bars past the thrust end (`BOX_GAP`), because
KOKA's coil starts after a 4-day pullback ending in a −8.2% flush, and
anchored at the thrust the box spans 1.58×ADR — over the cap.

**7. Eight features fail to explain the one residual false positive.** PTRO
fires one stale session (08-24, box 1.25×ADR vs 1.18 the day before — "too
wide" by eye) and no measurable feature separates it: golden boxes reach
1.46×ADR, and MA-convergence score, height, volume ratio, box length, gap,
thrust size, trailing run-up (3 variants) and giveback all overlap. One
borderline session on a "probably" label is not worth a ninth gate — fitting
it would be fitting noise.

**8. Precision after the loosening round: ~9 candidates/session.** August 2026
sweep (19 sessions, ~195–219 liquid names each): 176 firings, 49 unique
symbols, vs 51 firings / 19 uniques under the original strict rules. The
loosening that bought KOKA-recall tripled the watchlist. Whether 9/day is
"drowning in junk" or "a fine shortlist to eyeball" is the user's call, and
several of the 49 may simply be good setups nobody has labelled yet — GTSI
started as "junk" and flipped on second look.

**9. The full labelling pass: ~72% of watchlist names are keepers.** All 49
August names judged by eye: 33 good (22 plain yes, 11 with box-span notes),
13 junk, 3 wanted a different box than the detector drew. Firing-weighted:
~33 of 176 August firings (~19%) land in junk windows. No measurable feature
separates the junk — across 135 positive and 41 negative firings, AUC for
MA-convergence score, height, volume ratio, box length, gap, thrust size,
distance above MA50, liquidity and 3-month return all sit between 0.39 and
0.64, and the apparent ADR signal (junk lives on wilder names) dissolves at
name level: positives span 2.1%–12.4% ADR with negatives interleaved
throughout. The residual junk is the eye seeing something these ten numbers
don't measure.

**10. The MA50-rising gate blocks two eye-approved boxes — and stays anyway.**
TKIM (08-04→10) and HRTA (08-11→19) pass every other gate; disabling the rise
check catches both while barely moving the labelled junk (no new junk names,
+4 junk sessions). The user kept the gate regardless — a deliberate
precision-over-recall call, recorded in `OUT_OF_PATTERN` rather than by
loosening the rule a third time.

**11. Two eye-boxes have no momentum candle at all.** LSIP and SMIL coil
without any day gaining ≥1×ADR on ≥1.8× volume (best candidates: 0.5–5%
gains, ≤1.6× volume). Accepted as out-of-pattern: the momentum candle is the
defining premise of this screener, and a quiet drift-up base is a different
pattern (a possible second screener, not a looser gate here).

**12. Out-of-sample month (July 2026): precision holds.** July swept far
quieter — 49 firings, 13 unique names (August: 176/49). Of the 8 cold names,
5 were keepers by eye (MAPI, RGAS, PKPK, SMRA, and MARK whose box the
detector had correctly caught in June), 3 junk (MORA, NTBK, KETR): ~63%
name-level vs August's 72%, on a small sample. Two August junk names (BFIN,
HATM) fired again in July — junk repeats. And the box-*ending* weakness
showed again: MARK kept firing 3 sessions after the eye called its box over
(exactly the PTRO 08-24 failure), and SMRA stopped firing 08-06 where the eye
extends the box to 08-14. The already-labelled names behaved too: SGER's July
firings (07-17, 07-27→30) were judged "perfect" — the detector's span matches
the eye's exactly — while GGRM's lone 07-01 firing was junk (a stale leftover,
now a negative window). Every recall label is caught: 40/40.

## Open

- Does `CLOSE_POS = 0.5` hold up across more sessions, or does it need the
  2/3 rule plus a volume-scaled exception (huge volume forgives a mid-range
  close)?
- What ends a box? PTRO's box was over by eye on 08-23 ("too wide") but no
  measured feature says so. Candidate ideas: range expansion of the newest
  bars vs the box's own quietest stretch, or a hard staleness cut shorter
  than 15 days.
- What is the eye measuring in the 13 junk names that ten features don't
  capture (finding 9)? Candidates untested: churn/orderliness of the box
  candles (the codebase's `_churn_l`), gap risk, position within the longer
  base structure, sector/theme context.
- Box-span disagreements: the eye wants CMRY's ~35-trading-day base (over
  `BOX_MAX = 15`), wants GGRM/IATA/NCKL to keep firing to late August, and
  starts HRUM's box earlier. Duration and staleness rules are the least
  settled part of the model — note the existing screener's **base** caps at
  45 bars.
- All labels come from one month on one exchange. Out-of-sample month next.

## Vocabulary

Reuses CONTEXT.md rather than reinventing it: **ADR** (`SMA20(high/low − 1)`,
never "ATR"), **session**, **market**.
New here, and absent from the codebase: **momentum candle** (a single-day
event — sharper than the glossary's multi-week **prior move**), **thrust**,
**box** (an explicit MA-anchored consolidation — a near neighbour of **base**
/ **cluster**, but bounded by a thrust rather than a prior-move peak), and
**MA convergence** as a ranking score. None promoted to CONTEXT.md until they
earn it.
