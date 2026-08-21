---
status: accepted
---

# The decile gate is not loosened on this evidence

A1 measured the decile gate discarding **40% of Kullamägi's real entries** (recall 395/658,
60.0%) at the session before entry, against liquidity's 90.9%. It is the largest single loss
in the funnel and the finding most likely to be acted on wrongly, which is why #133 was raised
as a spike rather than a change.

This ADR records the option space and the reasoning.

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
  `DETECTION_LOOKBACKS`.
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
