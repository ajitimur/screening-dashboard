# Fit the split's 22 parameters, or accept them as borrowed defaults

Type: prototype
Status: claimed
Blocked by: 15

## Question

Ticket 17 adopted a detector carrying **22 free numbers, none of them fitted to anything**. Which of
them get calibrated, which stand as q-scanner's defaults, and on what evidence?

The bill, from [`params.py`](../prototypes/17-base-cluster/params.py):

| group | numbers |
| --- | --- |
| where the base starts | `MOVE_WINDOWS` (21/42/63/126), `MAX_BASE_LEN` 45, `MIN_BASE_LEN` 3 |
| the cluster | `K_MIN` 3, `K_MAX` 7, `TIGHT_MULT` 1.5 |
| catch-up to the MAs | `CATCHUP_10` 1.0, `CATCHUP_20` 2.0 |
| the fitted line | `OVER_W` 3.0, `UNDER_W` 1.0, `SLOPE_STEPS` 200, `MAX_SLOPE_ADR` 0.5 |
| line validity | `TOUCH_TOL_ADR` 0.35, `MIN_TOUCHES` 2, `MIN_TOUCH_GAP` 3, `MAX_OVERSHOOT_ADR` 1.0, `MAX_OVERSHOOT_FRAC` 0.20, `reaches_back` 0.6×base |
| list length | prior-move floor 25% |

Sensitivity is very uneven, which is what makes this tractable rather than hopeless — swing in
nightly list length across each parameter's plausible range:

| parameter | swing |
| --- | --- |
| `TIGHT_MULT` (1.25 / 1.5 / 1.75) | **63.2%** |
| `MAX_OVERSHOOT_FRAC` | 21.1% |
| `MAX_BASE_LEN` | 15.5% |
| `TOUCH_TOL_ADR` | 13.7% |
| `K_MAX` | 6.1% |

Specifically:

- **`TIGHT_MULT` is the whole cut and it is unfitted.** It is simultaneously §3.4's looseness
  auto-reject, the thing that bounds the stop to 1.5×ADR, and the single largest lever on list
  length. It should be *chosen*, against the trader's eye or against list length as an explicit
  budget, not inherited.
- **Which of the 22 are dead or redundant?** `MA_PROX_ADR` is defined and never read. The prior-move
  floor duplicates D15's decile gate as a second momentum filter — ticket 17 kept both and left the
  redundancy open. `SLOPE_STEPS` is a discretisation, not a preference.
- **Can the six line-validity numbers be cut down?** They decide whether a line is drawable, which is
  what drops 58.8% of ticket 08's picks — the largest single behaviour change ticket 17 introduced,
  and the least examined.
- **What is the fitting instrument?** Ticket 15's round-2 machinery is the obvious one, but it fits a
  *rubric* against grades, and these are *detector* parameters — a name the detector never emits
  cannot be graded. Deck D's rejected-candidates arm is the shape that can see them, and it is
  currently unowned.
- **Per-market.** Every number here is in ADR units and therefore scale-free, but IDX's limit days
  and quantization break that assumption in the same places they broke it for ticket 09's D13.

Blocked by ticket 15 because the rubric has to settle on the new structure first: fitting detector
parameters against a score that is itself being refitted would chase a moving target.

**Do not re-litigate** the adoption of the split itself — that is [ticket 17](17-base-cluster-split.md),
decided against a measured null on the name-level comparison and a decisive eye result on the
geometry. This ticket prices and tunes what was adopted.

## Added scope — ticket 18

[Ticket 18](18-digest-rule-under-the-clamped-trigger.md) found the trigger is `cluster_high` by
identity — the fitted line is anchored at the cluster's max high and searched over non-positive
slopes, so it can never set the level (100.0% of 29,242 detections). Two consequences for this
ticket's sweep:

- **Four of the 22 parameters cannot move the trigger.** `OVER_W`, `UNDER_W`, `SLOPE_STEPS` and
  `MAX_SLOPE_ADR` affect only whether a detection *exists* (via `line_ok`) and what the chart draws,
  never where the level sits. Price them on that basis rather than as trigger parameters. Worth
  asking directly whether the anchor-plus-non-positive-slope construction is intended, since it makes
  the line's contribution to the trigger unreachable by design rather than by tuning.
- **`K_MIN`/`K_MAX` do double duty.** The cluster high is the trigger, so the k range is also the
  digest's breakout lookback — ticket 18 R3 measured the effective lookback at median 4, mean 4.37
  (k=3 on 37.3% of detections). Fitting k on detection quality alone under-counts what it moves:
  it also sets how far price must travel to be reported at all.

`TIGHT_MULT` was already this ticket's headline at a 63% swing in list length; note that it swings
the digest by the same mechanism, since it is what selects the cluster whose high is the level.
