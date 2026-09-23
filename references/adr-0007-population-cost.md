# What ADR 0007's gates cost the population

ADR 0007 added a **Trend** gate (`adj_close >= SMA50`) and made **catch-up** two-sided on
the SMA20 (`abs(adj_close − SMA20) <= 2.0 × ADR`), both reading the adjusted series. Its
Consequences section left one thing open and said so:

> **The population cost is not yet measured**, which is a departure from ADR 0002 condition 4
> and is called out rather than hidden. […] The count and a sample of what drops are to be
> measured over the existing store before this ships; a full replay ledger is reserved for if
> the drop looks wrong.

This is that measurement. **The drop does not look wrong**, so the reserved full ledger was
not drawn on, and the change ships on the count below.

## Method

Every detection the live store holds at `DETECTOR_VERSION` 3 — 8,499 rows over 25 sessions,
2026-08-20 to 2026-09-22, both markets — was replayed through the v4 detector on the same
bars at the same session. A row that no longer detects is attributed to its first failing
gate by `replay.funnel.diagnose_detection`, which walks `detect`'s gates in `detect`'s order
using `detect`'s own constants.

This is the **narrowing measured against the field it narrows**, not a recall figure: it
answers "what would last month's Setups grid have lost", which is the question the ADR's
consequence asks. Detection recall against his executed trades is the separate figure below.

## The count

| | detections | share |
| --- | ---: | ---: |
| stored at v3 | 8,499 | |
| survive at v4 | 5,805 | **68.3%** |
| dropped | 2,694 | **31.7%** |

By the gate that rejected them:

| gate | dropped | share of the v3 population |
| --- | ---: | ---: |
| `trend` | 2,610 | **30.7%** |
| `catch_up` (the new lower side) | 84 | **1.0%** |

**The Trend gate does essentially all of the work.** Widening catch-up into a band removes
1% of the field on its own, which is worth knowing before anyone attributes a future
population change to it: whatever this pair of gates does, the SMA50 floor is doing it.

By market, and the spread across sessions:

| market | kept | dropped | drop share | per-session drop share (min / median / max) |
| --- | ---: | ---: | ---: | --- |
| US | 4,814 | 2,472 | 33.9% | 25.6% / 34.0% / 66.7% |
| IDX | 991 | 222 | 18.3% | 10.2% / 18.6% / 26.7% |

**The drop is roughly half what the ADR budgeted for.** It wrote that "the backtest's
isolation table puts the trend gate at roughly halving members per session in a
differently-shaped field, and a two-sided SMA20 band narrows further". Measured on the app's
own field it is 31.7%, not ~50%, and the band's further narrowing is a single point. The
differently-shaped field is the reason: the backtest's stateless universe has an ADR floor
and an ADTV floor the app has neither of, and the isolation table's halving was measured
against members, not against detections that had already cleared a base.

The US/IDX split is the largest structured difference in the measurement and is not explained
here. It is consistent with IDX names sitting closer to their averages over this window, but
one month of two markets is not evidence for that and this file does not claim it.

## A sample of what drops

Twenty-five rows drawn at random (seed 7) from the 2,694:

```
US   2026-09-03  VIAV     trend      US   2026-08-20  ASTH     trend
US   2026-08-25  SIMO     trend      US   2026-09-16  COGT     trend
US   2026-09-10  ANAB     trend      US   2026-08-31  CNC      trend
US   2026-09-21  URGN     trend      IDX  2026-09-16  JGLE.JK  trend
IDX  2026-09-20  VKTR.JK  trend      US   2026-08-21  CIFR     trend
US   2026-08-20  PENG     trend      US   2026-09-11  IMNM     trend
US   2026-09-17  BLZE     trend      US   2026-09-10  TOST     trend
US   2026-08-21  NBIS     trend      US   2026-08-20  MTSI     trend
US   2026-09-08  RLAY     trend      US   2026-09-01  ASH      catch_up
US   2026-09-21  AGM      trend      US   2026-08-21  HUM      trend
US   2026-08-20  BB       trend      US   2026-09-17  SYRE     trend
US   2026-09-18  ICLR     trend      US   2026-08-24  SEZL     trend
US   2026-09-11  ARWR     trend
```

These are the names the ADR was written about: a name under its own 50-day average, sitting
in what the geometry reads as a base because the geometry never asked where the base was.

## Detection recall, the other direction

The same change measured against his 656 replayable executed trades, over `replay.duckdb`'s
bars at each trade's evaluation session — the `detection_recall` anchor's own quantity:

| detector | recall | ex-continuation |
| --- | ---: | ---: |
| v3 | 549 / 656 (83.7%) | 487 / 577 (84.4%) |
| **v4** | **421 / 656 (64.2%)** | **372 / 577 (64.5%)** |

**128 of his trades stop being detected.** By first failing gate at v4: `trend` 132,
`catch_up` 43, `base_length` 37, `history` 21, `cluster` 2. The four that the arithmetic does
not account for are trades that failed `catch_up` at v3 and now fail `trend`, which is checked
earlier.

The instrument was validated before the v4 figure was believed: run against `origin/main`'s
detector over the same store it reproduces the committed anchor exactly — **549 of 656**, with
the same miss breakdown (`catch_up` 47, `base_length` 37, `history` 21, `cluster` 2) that
`references/replay_study_report.txt` prints. So the v4 number is the gate moving, not the
harness.

**This is the price ADR 0007 knowingly accepted, and it is larger than the reference's 12.0%.**
`references/qullamaggie-entry-ma-distance.md` measured him entering below his own SMA50 on
12.0% of trades; 132 of 656 is 20.1%. The two are not the same quantity — the reference
measures the entry bar, this measures the evaluation session the night before, and a name
that crossed its average on the entry day is below it here — but the gap is large enough that
it should not be read as agreement. Nothing here revises the ADR's decision: it argued the
gate as fidelity to the plan and said in terms that "if a future study shows the gate costs
expectancy, that is not a surprise this ADR failed to anticipate; it is a price this ADR
knowingly accepted." This file is the size of that price, not a re-argument of it.

## What is still not measured

`in_field_stateless` — field membership counted over the backtest contract's stateless
universe (165 of 503 at v3, from #198's full run) — is **not** re-measured here. It needs a
reproduction of the full backtest run over `data/backtest.duckdb` and its denominator, which
is a separate exercise from the one the ADR made a precondition. Until it is run, no figure
from a v4 backtest run over that universe is anchored on field membership, which is the
anchor table refusing rather than failing.
