# Near-miss population: a measurement

Measured 2026-08-06 for GitHub issue #53. **This is a measurement, not a design.**
It sizes the population of names that today vanish silently out of
`backend/screener/detection.py` — nothing here proposes a verdict scheme, a
threshold, or a surface.

Reference framing (q-scanner-v2): a middle tier `NEEDS_MORE_TIME` (the structure
is real but immature) versus `NO_SETUP` (a hard gate failed). The question this
note answers is only: **how many names per market per night would land in that
middle tier?**

---

## 1. Every rejection point in `detect()`, classified

`detect()` is a straight-line sequence of early returns
(`backend/screener/detection.py:305-393`). Listed in the order it applies them.
"Hard" = the name is structurally unsuitable and no amount of waiting changes it
tonight; "immature" = the same name could qualify on a later session with no
change to the name itself, only to its price action.

| # | Rejection point | file:line | Condition | Class |
|---|---|---|---|---|
| 0 | **decile gate** | `backend/screener/pipeline.py:172-176`, rule at `backend/screener/detection.py:396-406` | not top-decile in any of 1m/3m/6m — the name never reaches `detect()` | **hard** (the reference's "no prior move / too slow") |
| 1 | no bar on/before `as_of` | `detection.py:314-316` (`idx is None`) | the name has no bar at this session | **hard** (not evaluable) |
| 2 | short history | `detection.py:314-316` (`idx < MIN_HISTORY`, 80) | fewer than 80 stored bars | **hard** — see caveat C4 |
| 3 | ADR non-positive | `detection.py:322-324` | `_adr(...)` is `None` or ≤ 0 | **hard** (a dead / flat series) |
| 4 | no prior move | `detection.py:327-329`; helper `detection.py:161-182` | no `MOVE_WINDOWS` window has ≥ 5 bars, or every window's origin low is ≤ 0 | **hard** |
| 5 | **base too short** | `detection.py:336-337` (`base_len < MIN_BASE_LEN`, 3) | the prior move's peak is within the last 2 bars — the base has not started forming | **immature** — see caveat C3 |
| 6 | **not caught up** | `detection.py:339-347` | `close − SMA10 > 1.0×ADR` or `close − SMA20 > 2.0×ADR` — price is extended above the 10/20 | **immature** (the reference's "price not caught up to the 10/20-day") |
| 7 | **no cluster** | `detection.py:349-351`; helper `detection.py:185-202` | no trailing 3–7 bar window spans ≤ `1.5×ADR` | **immature** (the reference's "cluster not tight yet") |

Notes on what is *not* here:

- **`line_ok` is not a rejection point.** The envelope fit's quality verdict is
  computed at `detection.py:355-357` and carried on the row; a name that fails it
  is still emitted and only sinks in the sort (`backend/screener/candidates.py:100-102`).
  So the reference's "no drawable line" hard gate **has no counterpart in this
  codebase** and contributes zero rejects.
- **"barcode" is not a rejection point.** `churn_l` (`detection.py:258-271`) is a
  scored dimension (`backend/screener/score.py:103`), never a gate. Same for
  "backside" — there is no such test.
- `_find_cluster` has a second `return None` at `detection.py:192` (`adr_abs <= 0`),
  which is unreachable from `detect()` because point 3 already rejected on it.
- The universe gate (`backend/screener/universe.py:146`, liquidity + instrument
  type + listing age) sits upstream of everything above; it is the denominator,
  not a rejection point counted here.

**Every hard gate precedes every immature gate in the control flow.** So a name
rejected at points 5–7 has, by construction, already cleared every hard gate —
the near-miss bucket needs no further filtering.

---

## 2. Method (reproducible)

1. The live DB was locked by an in-flight `python -m screener.run US`. A byte copy
   of `data/screener.duckdb` (+ `.wal`) was taken at 23:30 local into
   `.scratch/nearmiss/screener.duckdb`. All measurement runs against that copy.
2. `.scratch/nearmiss/measure.py` re-implements `detect()`'s control flow while
   calling the production module's own private helpers (`_adr`, `_prior_move`,
   `_find_cluster`, `_sma_close`, `_fit_envelope`, `_churn_l`, `_dryup`) and its
   published constants. **`backend/screener/detection.py` was not modified.** The
   mirror labels which early return fired instead of returning `None`, and
   additionally evaluates all three immature tests *independently* for every name
   that clears the hard gates (production short-circuits at the first failure).
3. Universe and ranks are read from the store for sessions that have them; where
   absent (IDX 2026-08-04, all US) they are recomputed with the production
   `rank_table` / `rebuild_universe` — see caveats.
4. Star scores are derived exactly as the API does: `star_score(det,
   prior_move=det.symbol in detection_gate(ranks), sector_share=
   leave_one_out_sector_shares(ranks, sector_of).get(sym, 0.0))` — the same three
   inputs `backend/screener/candidates.py:71-84` uses.
5. **Validation.** For the two IDX sessions with stored detection rows the mirror
   reproduces the stored count and the stored symbols exactly (2026-08-05: 6,
   2026-08-06: 5). This is the check that the mirror is faithful.

Scripts (throwaway, `.scratch/nearmiss/`): `measure.py` (the counts),
`build_us.py` (reconstructs the US universe/ranks on the copy), `missing.py` /
`missing2.py` (characterise the US bar-coverage hole). The 1 GB DB copy is not
committed.

---

## 3. IDX — three sessions

| Session | Universe | Not top-decile | Entering `detect()` | Detections | **Near-miss** |
|---|---|---|---|---|---|
| 2026-08-04 | 80 | 65 | 15 | 6 | **9** |
| 2026-08-05 | 78 | 63 | 15 | 6 | **9** |
| 2026-08-06 | 80 | 66 | 14 | 5 | **9** |

Rejection histogram over the names that entered `detect()`:

| Reason | class | 08-04 | 08-05 | 08-06 |
|---|---|---|---|---|
| no bar on/before `as_of` | hard | 0 | 0 | 0 |
| short history | hard | 0 | 0 | 0 |
| ADR non-positive | hard | 0 | 0 | 0 |
| no prior move | hard | 0 | 0 | 0 |
| base too short | immature | 7 | 7 | 7 |
| not caught up | immature | 2 | 2 | 1 |
| no cluster | immature | 0 | 0 | 1 |
| **emitted** | — | 6 | 6 | 5 |

Because every hard gate fires zero times on IDX, **100% of IDX rejects inside
`detect()` are immature**. The near-miss population is 9 names a night against a
candidate list of 5–6 — i.e. naming the middle tier would roughly **2.5× the
number of rows the app has anything to say about** on IDX.

Independent failure counts (each immature test evaluated for all names past the
hard gates, so these overlap):

| Session | base too short | not caught up | no cluster |
|---|---|---|---|
| 2026-08-04 | 7 | 8 | 5 |
| 2026-08-05 | 7 | 9 | 8 |
| 2026-08-06 | 7 | 5 | 7 |

How many of the three immature tests each name fails (0 = emitted):

| Session | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 2026-08-04 | 6 | 1 | 5 | 3 |
| 2026-08-05 | 6 | 0 | 3 | 6 |
| 2026-08-06 | 5 | 3 | 2 | 4 |

The "fails exactly one" column is the tightest possible near-miss reading: **0–3
names a night on IDX**.

---

## 4. US — three sessions

**Read section 6 caveat C1 before using these numbers.** The US universe here is
reconstructed and materially incomplete.

| Session | Universe | Not top-decile | Entering `detect()` | Detections | **Near-miss** |
|---|---|---|---|---|---|
| 2026-08-03 | 1,156 | 904 | 252 | 44 | **206** |
| 2026-08-04 | 1,160 | 905 | 255 | 28 | **225** |
| 2026-08-05 | 1,167 | 921 | 246 | 27 | **216** |

Rejection histogram over the names that entered `detect()`:

| Reason | class | 08-03 | 08-04 | 08-05 |
|---|---|---|---|---|
| no bar on/before `as_of` | hard | 0 | 0 | 0 |
| short history | hard | 2 | 2 | 3 |
| ADR non-positive | hard | 0 | 0 | 0 |
| no prior move | hard | 0 | 0 | 0 |
| base too short | immature | 74 | 83 | 91 |
| not caught up | immature | 50 | 85 | 60 |
| no cluster | immature | 82 | 57 | 65 |
| **emitted** | — | 44 | 28 | 27 |

**99% of US rejects inside `detect()` are immature** (2–3 hard rejects a night out
of ~220). Near-miss ÷ detections is **4.7× / 8.0× / 8.0×**.

Independent failure counts (overlapping):

| Session | base too short | not caught up | no cluster |
|---|---|---|---|
| 2026-08-03 | 74 | 109 | 184 |
| 2026-08-04 | 83 | 158 | 201 |
| 2026-08-05 | 91 | 135 | 173 |

How many of the three immature tests each name fails (0 = emitted):

| Session | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| 2026-08-03 | 44 | 97 | 57 | 52 |
| 2026-08-04 | 28 | 76 | 81 | 68 |
| 2026-08-05 | 27 | 97 | 55 | 64 |

"Fails exactly one" is **76–97 names a night** on US — still 3× the emitted list.

---

## 5. Star score distribution of today's emitted detections

Computed exactly as `candidates.build_candidates` does. IDX has a warm label
cache, so its scores are final. US has **no label cache in the snapshot**, so the
Sector dimension (1 point, 0.5 stars) cannot fire for any US name; the US table
therefore shows a **lower bound** and a **`+1 point` upper bracket** (what the
score would be if every name's leave-one-out sector share cleared 0.10). The
truth is between them.

### IDX

| Stars | 08-04 | 08-05 | **08-06 (today)** |
|---|---|---|---|
| 2.0 | 1 | 2 | 1 |
| 2.5 | 0 | 1 | 0 |
| 3.0 | 1 | 1 | 1 |
| 3.5 | 2 | 1 | 2 |
| 4.0 | 1 | 0 | 1 |
| 4.5 | 1 | 1 | 0 |
| **total** | 6 | 6 | **5** |
| **> 3★** | 4 (66.7%) | 2 (33.3%) | **3 (60.0%)** |
| **> 4★** | 1 (16.7%) | 1 (16.7%) | **0 (0.0%)** |

Today's IDX list: TAMA.JK 4.0, PKPK.JK 3.5, RLCO.JK 3.5, RBMS.JK 3.0, SGER.JK 2.0.

### US (lower bound — Sector dimension unavailable)

| Stars | 08-03 | 08-04 | **08-05 (latest)** |
|---|---|---|---|
| 0.5 | 1 | 0 | 0 |
| 1.0 | 11 | 6 | 1 |
| 1.5 | 8 | 4 | 5 |
| 2.0 | 3 | 2 | 3 |
| 2.5 | 7 | 5 | 5 |
| 3.0 | 10 | 3 | 5 |
| 3.5 | 1 | 3 | 5 |
| 4.0 | 2 | 3 | 2 |
| 4.5 | 1 | 2 | 1 |
| **total** | 44 | 28 | **27** |
| **> 3★** | 4 (9.1%) | 8 (28.6%) | **8 (29.6%)** |
| **> 4★** | 1 (2.3%) | 2 (7.1%) | **1 (3.7%)** |

US upper bracket (every name credited the Sector point, i.e. all scores +0.5):

| Session | > 3★ | > 4★ |
|---|---|---|
| 2026-08-03 | 14 (31.8%) | 3 (6.8%) |
| 2026-08-04 | 11 (39.3%) | 5 (17.9%) |
| 2026-08-05 | 13 (48.1%) | 3 (11.1%) |

---

## 6. Caveats

**C1 — the US universe is incomplete, and this is the caveat that most changes
how the US numbers read.** The snapshot's US bars come from a run that was
interrupted, and the live `screener.run US` had not finished at measurement time,
so no US run/universe/ranks rows existed. `.scratch/nearmiss/build_us.py`
reconstructed them by calling the production `rebuild_universe` / `rebuild_ranks`
on the copy, with the two Nasdaq Trader listing files as the enumeration and
"no stored bars" standing in for "unresolved". Coverage is lopsided:

- `nasdaqlisted.txt` candidates: 4,314, of which **301 (7%) have no bars**;
- `otherlisted.txt` (NYSE/AMEX/ARCA) candidates: 3,179, of which **2,475 (78%)
  have no bars** — the ingest was cut off partway through the second file.

Missing names include plainly liquid ones (SHW, NI, GPK, HXL, EQNR). So the US
universe of ~1,167 is a **lower bound skewed toward NASDAQ listings**, and every
absolute US count — universe, entering, detections, near-miss — would grow, very
plausibly by ~1.5–2×, on a complete pull. The **ratios** (near-miss ÷ detections
≈ 5–8×, immature share ≈ 99%) are the numbers to lean on, not the levels. A
re-run of `measure.py` after a clean US night gives the true levels.

**C2 — the histogram is by *first* rejection.** Production short-circuits, so the
per-reason rows in the §3/§4 histograms attribute a name to the earliest gate it
fails. The "independent failure counts" and the "how many of three" tables are the
un-short-circuited view, and they show heavy overlap: on US, only ~35–40% of
near-misses fail exactly one immature test. Any middle tier's size depends on
whether it means "failed at least one immature test" (the big number) or "failed
exactly one" (the small one).

**C3 — `base_too_short` cannot be cleanly classified as "immature".** It fires
when the prior move's peak is 1–2 bars back (`detection.py:332-337`), i.e. the
name is **making new highs right now**. Calling that "base too short" is literal
but arguably misleading — the reference's `NEEDS_MORE_TIME` means "a base is
forming and isn't ready", whereas these names have not begun basing at all and are
extended. It is counted as immature here (the name genuinely can qualify in a few
sessions), but a design that shows the middle tier may want to separate it. It is
the single largest immature bucket on IDX (7 of 9 every night) and 33–37% of the
US one. Supporting evidence: the base-length histograms in
`.scratch/nearmiss/output.txt` show a heavy spike at `base_len ∈ {1,2}` — e.g. US
2026-08-05, 91 of the 243 names past the hard gates.

**C4 — `short_history` is temporally, not structurally, hard.** A name with < 80
bars becomes eligible purely by the passage of time. It is classed hard because it
is not a *setup* judgement at all, and it is numerically irrelevant (0 on IDX, 2–3
a night on US).

**C5 — IDX 2026-08-04 uses carried membership.** Only 2026-08-05/06 have stored
universe and rank rows for IDX; 2026-08-04's row reuses the 2026-08-06 membership
(80 names) and a recomputed rank table. Membership drifts slowly (78 → 80 over the
two stored nights), so the effect on the counts is small but nonzero.

**C6 — the IDX universe is capped upstream.** `YFinanceSourceClient._screen_idx`
requests `size=250` (`backend/screener/source.py:399`), so IDX enumerates 250
names before the liquidity/type/age gate leaves ~80. IDX counts are counts over
that capped enumeration, not over all of IDX.

**C7 — three sessions is not stability evidence, only a smell test.** IDX
near-miss is 9/9/9 and US is 206/225/216 across consecutive sessions, which looks
stable, but three adjacent nights share most of their names. Nothing here speaks
to weekly or regime-level variation.

**C8 — no US label cache.** See §5. The US star distribution is bracketed rather
than exact.
