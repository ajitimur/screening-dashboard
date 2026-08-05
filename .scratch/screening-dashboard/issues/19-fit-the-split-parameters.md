# Fit the split's 22 parameters, or accept them as borrowed defaults

Type: prototype
Status: resolved
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

---

## Answer

**Nothing is fitted, and that is the resolution rather than a failure to reach one.** Of the 22
numbers, **five can move anything at all**; three are provably redundant and are deleted; the rest
stand as q-scanner's defaults with the evidence for standing recorded. The one number that moves
most — `TIGHT_MULT` — turned out not to be a detection parameter at all, which changed the ticket:
it is the **stop budget**, and once measured against §7 the live question stopped being "what value
fits" and became "does the screen enforce §7", which is a trader's call and was taken as one.

The prototype is [`19-fit-params/`](../prototypes/19-fit-params/); full working in
[`FINDINGS.md`](../prototypes/19-fit-params/FINDINGS.md). 400 US names (seed 19) on a 1-in-3 date
grid — 172,991 bar-dates, 19,527 accepted detections — plus IDX's full 288-name universe.

### R1. The bill is five live numbers, not twenty-two

| verdict | numbers | evidence |
| --- | --- | --- |
| **dead — deleted** | `MA_PROX_ADR` | zero references in any function body |
| **one number, not two** | `OVER_W`, `UNDER_W` | the fit loss is scale-invariant, so only their *ratio* binds: (3.0, 1.0) and (6.0, 2.0) give **byte-identical** lists, as do (6.0, 1.0) and (3.0, 0.5) |
| **discretisation — frozen** | `SLOPE_STEPS` | 25 → 800 steps moves the list ±0.1% |
| **redundant — dropped** | `MAX_OVERSHOOT_FRAC` | catches only 4.4% of candidates the ADR test misses (r = +0.32) |
| **redundant — dropped** | prior-move floor 25% | ticket 06's decile gate cuts **89.4%** of what the floor passes; the floor cuts **7.7%** of what the gate passes (Jaccard 10.5%) |
| **near-inert — frozen** | `K_MAX` | 7 → 9 moves the list −1.7% |
| **live** | `TIGHT_MULT`, `K_MIN`, `MAX_BASE_LEN`, `MAX_OVERSHOOT_ADR`, the touch group | R2–R4 |

**Ticket 18's trigger identity replicates** on a fresh sample: the fitted line set the trigger in
**0 of 19,527** detections. Its four inheriting parameters price as existence-and-drawing only, as
18 said; `MAX_SLOPE_ADR` is additionally near saturation (0.5 → 1.0 moves the list +1.1%), so the
slope cap almost never binds upward.

The redundancy finding carries a second lesson the map should not lose: **ticket 17's 63% swing was
measured on the ungated list.** The decile gate runs first and is by far the stronger filter. Every
list-length number in this ticket is quoted after it.

### R2. `TIGHT_MULT` is the stop budget. It stays at 1.5, and §7 moves to the display.

The cluster spans ≤ `TIGHT_MULT` × ADR and the stop runs trigger → cluster low, so `TIGHT_MULT`
**is** the worst-case stop in ADR units. §7 caps stop width at **1 × ADR** and calls anything wider
a no-trade. Ticket 08 gated exactly this (D6, rejecting 30–69%); ticket 17 deleted the gate on the
argument that the cluster bounds the stop "as a side effect rather than as a gate" — an argument
about *form*, which was never paired with the number about *substance*:

| `TIGHT_MULT` | gated /night | k mean | stop median | **within §7** |
| --- | --- | --- | --- | --- |
| 1.000 | 23.1 | 3.70 | 0.88 | **100%** |
| 1.250 | 30.7 | 4.02 | 1.08 | 28% |
| **1.500** | **39.7** | **4.41** | **1.28** | **8%** |
| 1.750 | 46.4 | 4.87 | 1.47 | 3% |

**At the inherited default, 92% of the nightly list carries a cluster-low stop that §7 calls a
no-trade.** Ticket 17 recorded the bound (≤1.5, max measured 1.499); nobody measured the
distribution against the cap.

**The decision: `TIGHT_MULT` stays at 1.5, no stop gate is restored, and the screen shows every
detection with its stop width — marking the ones outside 1 × ADR rather than hiding them.**

The reasoning, and the option that was put and declined. A restored 1×ADR gate was measured first
and initially preferred: it leaves the rubric's k dimension nearly intact (4.41 → 4.23, against
3.70 if `TIGHT_MULT` were re-tightened to 1.0 instead) and brings the nightly list to 16.9 names,
inside ticket 06's reviewability concern. It was declined once its **price** was measured:

- **8.5% of detections survive** it (39.7 → 16.9 US names/night).
- Survivors are **more volatile, bigger movers**: mean ADR 6% → 10%, mean prior move 104% → 177%.
  Mechanical, since the stop is measured in ADR units — a high-ADR name passes with a wider
  absolute cluster — but a real selection effect, not a neutral filter.
- **Only 25 of ticket 15's 164 graded cards survive (15%), and the removed cards graded *higher***
  (eye 2.91 removed vs 2.44 kept).

That last point is the load-bearing one, and it is consistent with an independent measurement: on
the 164 graded cards the eye grades **looser** clusters higher, monotonically — 2.54 → 2.75 → 2.94
across (0.75,1.0] → (1.0,1.25] → (1.25,1.5] ADR, r = +0.140 (p = 0.286, and every card was selected
under 1.5, so this can only speak about tightening — but the sign is the finding). **The eye and the
stop rule disagree, in the same direction, on every measurement taken.**

So the screen does not adjudicate between them. §7's real stop is the entry-day LOD or opening-range
low, which sits **above** the cluster low; the cluster-low stop is a conservative EOD proxy for a
number the screen cannot see. Filtering on the proxy would delete the trader's preferred setups on
evidence that is systematically pessimistic. §7 is enforced at entry, with intraday data, by the
human — and the screen's job is to make that check free rather than to pre-empt it.

**A caveat for whoever builds this**: at the default, ~92% of rows carry the mark, and a flag that
fires on 92% of a list is not a flag. The useful form is almost certainly the **stop width in ADR
as a sorted column**, with the ≤1×ADR minority highlighted — the inverse of "mark the failures".
Ticket 13 owns the final shape; the decision here is that the number is *shown and not filtered on*.

### R3. Line validity is one decision and a spare

`line_ok` passes 53.1% of the 53,922 candidates reaching it — this is what ticket 17's 58.8% drop
of 08's picks is made of. Instrumented per clause (the duplicated fit reproduces `split.py`'s own
`line_ok` at **100.0000%** agreement):

| clause | passes | `line_ok` if dropped |
| --- | --- | --- |
| `over_max ≤ 1.0 ADR` | 68.9% | 73.3% (**+20.2pp**) |
| `over_frac ≤ 20%` | 86.1% | 56.2% (+3.1pp) |
| `zones ≥ 2` | 44.7% | 64.5% |
| `zones ≥ 1 & reaches 60% back` | 84.3% | 64.5% |

The touch clauses are an **OR**, so neither binds alone — dropping *either* gives the same 64.5%,
and dropping both costs +11.4pp. `MIN_TOUCHES = 2` decides nothing by itself, and the four numbers
behind the touch test are **one decision expressed four ways**. `MAX_OVERSHOOT_ADR` is the number
doing the cutting; `MAX_OVERSHOOT_FRAC` is dropped per R1.

So the answer to "can the six be cut down" is yes: **two live decisions** (bounded overshoot in ADR;
is a line drawable from its touches) behind what is now five numbers rather than six.

### R4. One set of numbers serves both markets

IDX tracks US across the whole `TIGHT_MULT` grid — k mean 3.66/4.51/5.44 against US's
3.70/4.41/5.32 at 1.0/1.5/2.0, stop medians identical to two decimals, §7 shares identical. ADR
distributions are comparable (US median 4.49%, IDX 3.97%). **No per-market parameter set is
needed**, which is what the ADR normalisation promised and had not been checked.

**Ticket 09's D13 hole stays closed under the split**: 98.5% of accepted IDX clusters contain zero
collapsed (zero-range) bars, against the 98.1% ticket 15 measured on the old detector. Worth
re-checking because the cluster is *selected* for tightness — precisely where a limit-day bar would
hide — and it did not get worse.

### R5. `K_MIN` is live, `K_MAX` is not, and neither moves

| K_MIN–K_MAX | /night | vs 3–7 | k mean |
| --- | --- | --- | --- |
| 2–7 | 57.9 | +49.1% | 3.62 |
| **3–7** | **39.9** | — | **4.41** |
| 3–9 | 39.4 | −1.7% | 4.50 |
| 4–7 | 26.5 | −36.6% | 5.23 |

k serves three consumers — detection, the digest's breakout lookback (18 R3), and ticket 15's
tightness dimension — and three consumers is a strong argument for leaving a non-binding number
alone. **3–7 stands.**

### R6. There was no fitting instrument, and the eye is not one

The ticket asked what the instrument would be. The graded set cannot fit *detector* parameters: it
contains only names the detector emitted, so it cannot see what a parameter change would newly
admit, and R2's eye result shows the failure concretely — the only direction it can speak about is
the one the evidence declines to support. Deck D's rejected-candidates arm remains the shape that
could see them, and it is **already in ticket 20's scope**; this ticket does not duplicate it.

Which means the honest summary of the whole ticket: **every one of the 22 numbers still stands as a
borrowed default.** What changed is that they are now classified rather than uniformly unexamined —
five can move anything, two decisions sit behind the line test, one number was misunderstood as a
detection parameter when it is a risk parameter, and three are gone.

### Ticket 18's reopen condition — discharged

Ticket 18 left: *"If ticket 19 moves `TIGHT_MULT`, `K_MIN` or `K_MAX`, the digest moves with them."*
**None of the three moved.** The digest's numbers stand exactly as 18 measured them — effective
breakout lookback median 4, mean 4.37, k=3 on 37.3% of detections. The condition is discharged, not
carried forward.

### Hand-offs

- **To ticket 13 (spec):** the parameter table in R1 is what the build session gets — five numbers
  it may touch, the rest frozen with the measurement that froze them. Plus R2's display decision:
  stop width in ADR is a **shown, sorted, non-filtering** column.
- **To ticket 11 (IA):** R2 needs almost nothing built — **I4 already carries a "Stop width ÷ 1×ADR"
  column**, so the display half of this decision was specified before it was decided. What ticket 11
  did not have is the **base rate**, and it changes how the column reads: I4 justifies it with "a row
  at 0.97× is nearly dead", which implies most rows sit below 1.0. **Roughly 92% sit above it.** The
  column is therefore not a veto indicator but the list's *widest* axis of variation, and the ≤1×ADR
  minority is what wants highlighting. Amendment recorded there.
- **To ticket 20:** R2's finding that the eye prefers what §7 rejects sharpens what the rubric is
  being confirmed *on*. No blocking dependency — 20 confirms the band on cards already rendered.
- **To ticket 21 (new):** whether the score and the digest should know about the stop at all.
