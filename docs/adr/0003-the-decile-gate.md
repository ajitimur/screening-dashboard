---
status: proposed
---

# The decile gate is not loosened on this evidence

A1 measured the decile gate discarding **40% of Kullamägi's real entries** (recall 395/658,
60.0%) at the session before entry, against liquidity's 90.9%. It is the largest single loss
in the funnel and the finding most likely to be acted on wrongly, which is why #133 was raised
as a spike rather than a change.

This ADR records the option space and the reasoning. It is `proposed`, not `accepted`: the
decomposition ADR 0002 condition 2 requires is only 46% measured. It becomes `accepted` — or
is replaced — when #131 supplies the full run.

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

Decile verdicts read off the persisted chain for the 312 replayable trades entering after
2020-12-30:

| | count | share |
| --- | --- | --- |
| Coverage gap — in the store, not a universe member | 17 | 5.4% |
| Passes the 3-lookback detection gate | 184 | 59.0% |
| Present, recovered only by widening 3→5 lookbacks | 40 | 12.8% |
| Present, outside even the 5-lookback union | 71 | 22.8% |

**The loss is not a coverage artefact.** Only 5.4% is absent-from-field; the remaining ~35
points are genuine ranking verdicts. This satisfies the *shape* of ADR 0002 condition 2 but
not yet its coverage: these are 312 of 658 trades, skewed to 2021–22, with universe membership
read from the stored chain rather than recomputed. The 59.0% landing within a point of the
study's 60.0% headline is evidence the approximation is sound, not evidence it is sufficient.

**22.8% sit outside any decile construction.** That population is not reachable by widening
what the gate unions, and it is the honest ceiling on what loosening can recover.

## Considered options

- **Widen the gate from three lookbacks to five.** Recovers 40 trades — 12.8pp, about a third
  of the loss — taking decile recall from 59.0% to 71.8%, at a gate population of 27.2%
  instead of 19.4%. **The leading candidate.** It is the only option that widens the gate
  without changing what "top decile" means, and it is structural rather than a threshold move,
  so ADR 0002 condition 3 is satisfied and there is no magnitude to get wrong. Its population
  cost is 7.8 points of universe for 40 trades. Not decided here: condition 2 is 46% measured.
- **Move `TOP_DECILE` below 0.90.** The only option reaching into the 22.8% outside every
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

- **No constant changes.** Acting on this is separate work, gated on #131 and on this ADR
  reaching `accepted`.
- The evidence needed is named concretely: the full 658-trade decile decomposition into
  coverage gap / recovered-by-5 / outside-any-union, from a single forward chain. #131 is
  amended to emit it. The persisted store cannot supply it because `append_ranks` prunes
  beyond `RANK_RETENTION_YEARS` as the chain advances — `universe` survives for all 928
  sessions but `ranks` only for the last 505, and 450 of the 828 trades entered before that
  cutoff.
- Should 3→5 be adopted, the change is confined to `DETECTION_LOOKBACKS`. Nothing outside
  `detection.py` reads it, so the breadth badge, sector strength and the boards are untouched.
- The 22.8% is a standing statement about what this funnel cannot do. If those entries matter,
  the answer is a different selection stage, not a looser decile.
- Scoped to US 2019–2022. No figure here is an IDX expectation; the shape — that the decile
  stage is the expensive one and that its loss is a ranking verdict rather than a coverage
  hole — is what transfers.
