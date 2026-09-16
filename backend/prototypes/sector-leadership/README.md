# PROTOTYPE: the sector leadership study

**Throwaway.** Nothing imports this. Not part of the pipeline, the sector board, the
rubric or the backtest. Reads a copy of the store, never the live file.

## The question

Research note 06 (§7) proposed three measures for the sector board. Does any of them
predict **Sector leadership** next month better than the two rotation columns already
there, the **Shape differential** and the **Temporal delta**? Terms are CONTEXT.md
§Themes, fixed in PR #227.

## The design, as settled before the code was written

- **Target.** Sector leadership: the three sectors with the largest 20-session rise in
  `share(1m)`, counted only where the sector has two or more members in the decile at the
  end (`ROTATION_MIN_MEMBERS`). One horizon, 20 sessions.
- **Score.** Top-3 hit rate per market: the share of a forecaster's top three that were
  in the leadership set, averaged over every forecast session. Chance is the size of
  the leadership set over 11. Rank correlation across the 11 sectors is printed beside
  it and never decides.
- **Bar.** A candidate earns a column only if it beats the better of the two incumbents.
  The gap is scored per session and given a 20-session block bootstrap interval.
- **History.** Reconstructed from `bars` in `data/screener.duckdb`, 2019-01 onward, both
  markets. The universe per past session is the pipeline's own rules, imported from
  `screener.universe` (liquidity median with hysteresis, listing age, density). The rank
  table is the pipeline's own anchors, imported from `screener.indicators`. Today's
  sector labels apply to every past date. IDX is also split at the ARB decree date
  `screener.volatility.ARB_POLICY_ERAS` holds, the way ADR 0006 does.
- **Parameters.** The note's, and nothing else. Turnover share: sector dollar volume as a
  share of the universe's over 5 sessions less the same over 60. Participation: share of
  members above their own 20-bar SMA is the forecaster; the 50-bar share and net 20-bar
  new highs are computed beside it and do not decide. Rotation momentum: EWM span 10 of
  `share(1m)`, standardised across the sectors, then EWM span 10 of its 5-session change,
  standardised again; the rank by that momentum is the forecaster. No sweeps.
- **Ties** break in `SECTORS` order, the board's own rule.

## Run it

    cp data/screener.duckdb /somewhere/copy.duckdb
    backend/.venv/bin/python backend/prototypes/sector-leadership/study.py --store /somewhere/copy.duckdb [--market IDX]

About three seconds for IDX, two minutes for US. Writes `results.txt`, `results.json`
and one per-session CSV per market beside the script. The committed copies are the run of
2026-09-16 over bars through 2026-09-15 (US) and 2026-09-16 (IDX).

## What the study found

**1. No candidate beats the better incumbent, on either market, pooled or per era.**
Pooled hit rates, chance beside them:

| forecaster | IDX (1,831 sessions, chance 0.256) | US (1,916 sessions, chance 0.273) |
| --- | ---: | ---: |
| Shape differential (incumbent) | 0.263 | 0.281 |
| Temporal delta (incumbent) | 0.216 | 0.139 |
| Turnover share | 0.254 | 0.226 |
| Participation | 0.231 | 0.179 |
| Rotation momentum | 0.217 | 0.146 |

Gap to the Shape differential, with the block bootstrap 95% interval: Turnover share
IDX −0.009 [−0.034, +0.014], US −0.056 [−0.082, −0.030]; Participation IDX −0.032
[−0.056, −0.008], US −0.103 [−0.125, −0.082]; Rotation momentum IDX −0.046 [−0.070,
−0.024], US −0.135 [−0.157, −0.112]. Every US gap is negative with an interval that
excludes zero. On IDX only Turnover share's interval touches zero, from below.

**2. Nothing predicts. The best forecaster is at chance.** The Shape differential's hit
rate is chance to within a point on both markets (0.263 against 0.256, 0.281 against
0.273) and its rank correlation with the rise is zero (−0.03 IDX, +0.00 US). The
incumbents were never measured against this target before; this is the first reading
of them, and it says the board's default sort does not forecast next month's leaders
either. That was not the study's question and it settles nothing about the columns,
which were adopted for what they describe tonight, not for what they predict.

**3. The target mean-reverts, and any measure that reads the current level of
`share(1m)` is anti-correlated with it.** Rank correlations with the rise: Temporal
delta −0.39 IDX / −0.38 US, Rotation momentum −0.34 / −0.37, Participation −0.19 /
−0.30, and the `share(1m)` level itself −0.57 / −0.50. The mechanism is
arithmetic: the rise is `share(1m, t+20) − share(1m, t)`, so it carries `−share(1m, t)`,
and a bounded share built from a handful of decile members regresses. A sector that
leads tonight is, by this target, less likely to be in next month's top three. The
Shape differential escapes because `share(1w) − share(6m)` carries little of the 1m
level. This is a property of the target as defined and is recorded, not acted on: a
contrarian column is a new hypothesis, and this study registered one direction.

**4. One positive cell, and it does not clear.** In the current IDX ARB era (from
2025-04-08, 324 sessions) Participation edges the Shape differential, 0.265 against
0.246, gap +0.020 with an interval of [−0.030, +0.073]. In the era before it (1,507
sessions) the same gap is −0.043 [−0.069, −0.018]. A cell that flips sign across eras
on a third of the sample is not a pass.

**5. The reconstruction matches the store.** Over the 29 sessions the store holds a
universe for, the reconstructed membership agrees at a mean Jaccard of 0.92 (IDX) and
0.93 (US); on the latest session the counts are 354 against 353 and 2,051 against 2,047.
The per-sector `share(1m)` numerator and denominator on the latest session match the
stored ranks exactly on IDX and within one name in four US sectors. The residue is the
store's cold start (no hysteresis history on 2026-08-05) and sticky membership for
names whose fetch failed on a given night, neither of which the study can see.

**6. Turnover share on IDX is often one name.** The median concentration (the top
member's share of its sector's 5-session dollar volume) is 0.35 on IDX and 0.10 on US.
The note's warning holds; it never got the chance to matter.

## Verdict

**All three candidates fail the bar.** No sortable column ships. Per the outcome
contract, the three glossary entries (Turnover share, Participation, Rotation momentum)
are marked measured and refused, the way the RS line's refusal is recorded in
`references/backtest_findings.md`. The star score, the regime and the candidate list
were out of scope and are untouched.

## Caveats, carried with the result

- **Survivorship.** Sector labels exist only for the names the store labels today, so
  every past sector is assembled from survivors. Absolute hit rates are inflated and are
  not to be quoted; incumbents and candidates share the hole, so only the differences
  are read. `results.txt` prints this warning at the top and the bottom.
- **Today's labels on every past date.** Accepted in the design. A name that changed
  sector is counted where it sits now.
- **Instrument type.** The store has no instrument names for past dates, so the
  common-stock exclusion could not be re-applied; indices, the four US ETFs the ingest
  carries as references and the FX series are excluded by symbol. Whatever else the
  pipeline would have excluded by name sits in the percentile population, on both sides
  of the comparison.
- **Overlapping windows.** Forecast sessions are daily and the horizon is 20 sessions,
  so neighbouring sessions share most of their outcome. The block bootstrap uses
  20-session blocks for that reason; the session counts overstate the independent
  evidence by about that factor.
- **One era boundary.** `ARB_POLICY_ERAS` records one decree date. ADR 0006 mentions
  four changes since 2020; only the one the module holds is used, because the ADR says
  eras are never inferred.

## Vocabulary

Reuses CONTEXT.md: **Sector leadership**, **Shape differential**, **Temporal delta**,
**Turnover share**, **Participation**, **Rotation momentum**, **share**, **session**,
**market**. Nothing new is coined here.
