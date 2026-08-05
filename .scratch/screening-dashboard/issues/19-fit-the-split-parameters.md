# Fit the split's 22 parameters, or accept them as borrowed defaults

Type: prototype
Status: open
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
