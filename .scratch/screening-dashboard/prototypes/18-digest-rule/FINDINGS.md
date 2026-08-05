# Ticket 18 — findings

Measurements behind [`18-digest-rule-under-the-clamped-trigger.md`](../../issues/18-digest-rule-under-the-clamped-trigger.md).

**Sample.** 260 US + 72 IDX names, ~3 years of daily bars each (760 bars), 251,321 bar-nights
evaluated, 29,242 detections (11.6%). Ticket 08's D15 decile gate is **not** applied, so every volume
figure is an upper bound. Seed 18.

**The one methodological thing worth carrying forward:** this is the first scan on this map to run on
**consecutive daily bars**. Tickets 09, 16 and 17 all swept a 1-in-3 date grid, which is fine for
measuring the *shape* of a detection and useless for measuring a *transition* — `trigger[t-1]` simply
does not exist on that grid. Nothing about the crossing population could have been measured earlier
even in principle.

## 1. The fitted line never sets the trigger (`crossings.py`, `clamp.py`)

Not a frequency — an identity. `fit_line` sets `y_a = high[anchor]` where `anchor` is the argmax of
the highs *inside the cluster*, so `y_a = cluster_high`; and slopes are searched over
`linspace(-MAX_SLOPE_ADR·adr, 0)`, so `m ≤ 0`. Then for `t+1 > anchor`:

```
line_at(t+1) = cluster_high + m·(t+1 − anchor) ≤ cluster_high
```

Measured: **clamp binds on 100.0%** of detections; the line sets the trigger on 0. Ticket 16's 82%
measured the clamp formula against ticket 08's window geometry, where the anchor is a different bar.

## 2. Two of ticket 14's three buckets are unreachable (`crossings.py`)

`cluster_high` is a max over a window that includes today, so `trigger_t ≥ high_t ≥ close_t`.

| type | event | ticket 14 | measured |
|---|---|---|---|
| 1 | price rose through yesterday's level | reported | 1,051 |
| 2 | level came down to meet a flat name | not reported | **0** |
| 3 | born triggered | not reported, 16.4% | **2** (0.007%) |
| 4 | level rose back over a cleared name | no bucket | 2 |

The type-3 and type-4 events, and the 3 rows where `close > trigger`, are cache artefacts where
`close > high`.

The level itself still moves — **rose 20.5%, fell 13.3%, flat 66.2%** of contiguous detected pairs —
it just can never fall below today's close, which is what kills type 2.

## 3. The break is an event, not a state (`repeats.py`)

Of the 1,051 breaks, **55.0%** are still detected the next night, and **100.0% of those are back below
their new level** (median level jump +0.021 ADR). The cluster rolls forward to include the breakout
bar, so `TRIGGERED` is never observable as a state.

## 4. Repeats (`repeats.py`, `episodes.py`)

| | |
|---|---|
| names reported more than once in ~3y | 80.3% |
| breaks within 20 sessions of the same name's last | 20.6% |
| breaks on consecutive sessions | 7.4% |
| median gap between a name's breaks | 70 sessions |

Detection episodes are short (median 2 sessions, max 22) and **85.5% of break-carrying episodes
contain exactly one break**. Repeats inside one episode land at a **higher** price — median **+1.10%**,
only **0.7%** lower — so they are continuation rather than a name flapping across a level.

| rule | US/night | IDX/night | rows kept |
|---|---|---|---|
| every break (no rule) | 7.0 | 0.9 | 100% |
| first break per detection episode | 5.9 | 0.8 | 86.1% |
| suppress a repeat within 5 sessions | 5.9 | 0.8 | 86.4% |
| suppress a repeat within 20 sessions | 5.5 | 0.7 | 79.4% |

## 5. What A3 actually says, and what it cannot see (`a3.py`)

`trigger_yesterday` is the highest high of the k bars ending yesterday, so A3 is a **k-bar closing
breakout** with k set by the tightness test:

| k | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|
| share | 37.3% | 24.8% | 15.3% | 9.0% | 13.6% |

Median 4, mean 4.37.

`trigger_yesterday` exists only if the name was detected yesterday, so lapsed resumers are invisible:

| lapse | n | median % above the stale level | US rows/night |
|---|---|---|---|
| 2 sessions | 213 | +0.78% | 1.4 |
| 3 | 241 | +1.18% | 1.5 |
| 4–5 | 401 | +1.56% | 2.4 |
| 6–10 | 704 | +3.57% | 4.6 |
| 11+ | 2,180 | +9.12% | 14.2 |

Closing the hole entirely: **US 7.0 → 31.0 rows/night**, median level age 13 sessions, +4.92% above it.

**A hypothesis this prototype tested and had to withdraw.** The session first argued a lapsed resumer
is merely *deferred* — re-armed on its new cluster, reported when it clears that. Measured over the
3,739 missed resumers: **8.6% are reported within 5 sessions, 12.5% within 10, 17.3% within 20.** The
short-lapse subset behaves no differently (8.6% / 11.9% / 15.2%). They are withheld, not delayed, and
the ticket states this as an accepted cost rather than a non-cost.
