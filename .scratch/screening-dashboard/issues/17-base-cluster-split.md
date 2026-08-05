# Replace the window rule with a base/cluster split?

Type: prototype
Status: resolved
Blocked by: 16

## Question

Should ticket 08's D2/D3/D4 window search be replaced by a two-level **base + cluster** structure,
and what does that cost the decisions built on top of it?

Ticket 16 established that the window is the load-bearing choice, not the line fit, and that D4's
primary window is **3 bars on 52% of detections**. It also measured the alternative — q-scanner's
split, ported in [`prototypes/16-trendline-fit/split.py`](../prototypes/16-trendline-fit/split.py)
over 318,357 bar-dates — and the structural numbers are good:

| | ticket 08 (D2–D4) | base/cluster split |
| --- | --- | --- |
| base length, median | 3 bars | **14 bars** (IQR 8–22) |
| trigger-to-stop | gated at 1×ADR, 30–69% rejected | **bounded ≤1.5×ADR by construction** (max measured 1.499) |
| US names / night | ~64 | **~63** (with a ≥25% prior-move floor) |
| IDX names / night | ~12 | **~11** |

The base runs from the **prior move's peak** to today (capped at 45 bars); inside it a **3–7 bar
trailing cluster spanning ≤1.5×ADR** must sit on a rising 10/20/50 MA. The line anchors at the
cluster's max high and fits backwards over the base's highs.

Two things make this more than a swap, and they are what the ticket has to settle:

- **It supplies the looseness cut ticket 16's R3 owes.** With D6 no longer gating, something must
  express §3.4's "loose, wide-range consolidation" auto-reject as a property of the base. The
  cluster's ≤1.5×ADR span *is* that cut, and it bounds the stop as a side effect rather than as a
  gate — which is precisely the separation the trader asked for. If this ticket rejects the split,
  it owes an alternative looseness cut, and R3 stays unfinished until it does.
- **It removes D3's retained window set, which D7 depends on.** Contraction — one of §3.5's two ×2
  dimensions — is scored as the `range(L)` curve against a √L baseline, and that curve *is* the
  retained set. A base/cluster split produces one base, not a nested family, so contraction needs a
  new definition. **Ticket 15's rubric is built on the current one and is in flight**, so this is
  the expensive part, not the detection change.

Also open:

- **Does D7's "narrow" half come back here?** Ticket 16's R3 left D7 measuring only "narrowing"
  because D6 no longer gates narrowness. The cluster range in ADR is the obvious candidate for the
  missing half — it is already computed and already bounded.
- **Does the eye agree?** The measurement is **structural only** — base length, cluster existence,
  line drawability, list length, stop width. Nothing checks that the setups it surfaces are the ones
  the trader wants, and the two detectors have never been compared on the same dates. A deck showing
  both detectors' picks for the same night is the obvious instrument, and it is also the deck that
  can finally ask ticket 16's unasked eye question, because the bases are long enough to draw a line
  on.
- **What survives from ticket 08?** §3.2's "piercing is desirable" and the elimination of pivot
  detection hold under both — q-scanner judges the line on touch zones and bounded overshoot, not on
  pivots. D2's "the base always ends today" also survives. Say explicitly which decisions are
  amended and which stand, because ticket 13 assembles from them.
- **The parameter count.** Ticket 08 resolved with zero tunables and ticket 09 cost it two. The split
  adds many: move windows, cluster k range, tightness multiplier, MA proximity, catch-up multiples,
  slope grid, overshoot weights and tolerances. Ticket 16 declined to let that drift unremarked;
  price it here rather than absorbing it silently.

---

## Resolution

**The base/cluster split is adopted whole — detection and description.** Decided by the trader
against the session's recommendation, which was to adopt it for description only; the disagreement
is recorded in R2 because it is the ticket's main risk and ticket 15 inherits it.

Measured over 318,617 (symbol, night) pairs and graded on a 75-card blind deck. Full working in
[`prototypes/17-base-cluster/`](../prototypes/17-base-cluster/), headline numbers in its
[`FINDINGS.md`](../prototypes/17-base-cluster/FINDINGS.md), grades in `grades17.txt`.

### R1. Ticket 16's "the list lands where it already is" is true of the count and false of the contents

The two detectors overlap on **26%** of picks (Jaccard 0.156). Per night, per market: **US 21.3 vs
20.4 names with 5.5 shared; IDX 3.9 vs 3.4 with 1.1 shared** (1-in-3 sampling). List length — the
number ticket 16 reported as reassurance — is the one property that cannot distinguish the two.

Neither mechanism is the cluster. The split drops 08's picks mostly on **line drawability** (58.8%),
its touch-zone and bounded-overshoot test; 08 drops the split's picks mostly on **D6's stop gate**
(80.8%), which ticket 16's R3 had already removed. Under R3, **86.2% of the split's picks are names
08 also finds**, so the real comparison was never "two rival detectors" but *D6's cut versus the
split's cut over mostly the same pool* — and those two cuts agree on 62.9% of detections.

### R2. The eye endorses the split's drawing decisively and its name selection not at all

Deck 17, blind, 75 cards, both sections fully graded.

| section 1 — the names (bare charts, no overlay, 20 per arm) | mean | ≥4★ |
| --- | --- | --- |
| shared | 3.30 | 45% |
| split only | 3.25 | 50% |
| 08 only | 2.85 | 25% |

**split-only minus 08-only: +0.40 stars, permutation p = 0.298.** The direction favours the split;
the evidence does not clear significance. At this effect size the deck would need ~140 cards per arm,
not 20.

| section 2 — the drawing (same bars, both geometries, side randomised) | votes |
| --- | --- |
| the split's base + cluster | **10** |
| ticket 08's primary window | 1 |
| neither | 4 |

**10 of 11, binomial p = 0.011**, over a median 3-bar window against a median 18-bar base. This is
the eye question ticket 16 left unasked, and it answers *against the 3-bar window* rather than
between the two line fits — consistent with 16's R4, which called the window the load-bearing choice.

**The session recommended adopting the geometry only** — detection staying with 08's window search
plus a cluster looseness cut — on the grounds that section 1 is the half that justifies changing
which names appear, and it came back null. **The trader took the full split**, reading section 2 as
an endorsement of the whole object and section 1's +0.40 as directionally real. That is the call;
the accepted risk is that **the nightly list changes by three quarters of its contents on a
name-level result that did not clear significance**, and it cannot be revisited cheaply, because
ticket 15's rubric is refitted on the new structure in between.

One thing the full swap buys that the narrower option did not: **coverage**. The split defines its
own population, so there is no gap — where the description-only option was applied to 08's
detections, 7.1% had no computable base and would have needed a fallback rendering.

### R3. What is amended in ticket 08, and what stands

**Replaced:**

- **D3** (retain every valid window) — deleted. The retained set was D7's contraction domain.
- **D4** (primary = shortest valid window) — deleted. The base runs from the prior move's peak to
  today, capped at 45 bars, with a 3–7 bar trailing cluster spanning ≤1.5×ADR on a rising 10/20/50 MA.
- **D5** (trigger = `min(flat high, line)`) — replaced by `max(line_at(t+1), cluster_high)`. Opposite
  clamp direction; already-breached falls **16.0% → 0.2%**.
- **D2** (boundaries by OLS) — amended to the envelope anchored at the cluster's max high, fitted
  backwards over the base's highs.
- **The stop** moves from the base low to the **cluster low**, which bounds trigger-to-stop by the
  cluster's own definition — measured max **1.499 ADR** over 54,201 detections. D6 is therefore not
  merely un-gated (16's R3) but unnecessary.
- **D9/D14** (the search is self-capping) — gone. `MAX_BASE_LEN 45` is now an explicit cap, and it
  binds: moving it 30→60 swings the list 15.5%.

**Stands:**

- §3.2's **piercing is desirable** — q-scanner judges the line on touch zones and bounded overshoot,
  not on pivots, so both implementations agree here.
- The **elimination of pivot detection**, for the same reason.
- **The base always ends today** (D2's end-anchoring), which is why detection emits a state, not an
  event, and why ticket 08's D1 `WATCHING`→`TRIGGERED` transition survives.
- **D15's decile gate** off ticket 06's rank table. Note the redundancy this creates: the split
  carries its own ≥25% prior-move floor as a list-length control, so there are now *two* momentum
  filters. Both were applied in the deck sampling; which one survives is ticket 19's.
- **D11 dry-up**, **D8 churn** and **D10 MA distance** survive as quantities but change domain — they
  are now computed over the split's base, and D10 additionally overlaps the split's own MA catch-up
  test. Reconciling them is ticket 15's, not this ticket's.

### R4. D7's tightness dimension, and the one signal this comparison produced

With D3's retained set gone, contraction has no domain. Every candidate replacement was scored on
the ticket-09 trap — being a base-length proxy — over the 120 existing deck-A grades:

| candidate | r vs eye | partial r, controlling for base length |
| --- | --- | --- |
| cluster range ÷ base range | +0.242 | **−0.020** |
| base height in ADR | −0.269 | **−0.022** |
| √L shortfall over trailing sub-windows of the base | −0.138 | +0.034 |
| cluster range ÷ ADR | +0.127 | +0.175 |
| **cluster length k** | +0.236 | **+0.260** |

The two that look significant unadjusted **collapse to zero** under the length control: ticket 09's
failure mode in new clothing. The incumbent D7 as shipped correlates **−0.338** with the eye —
significantly *against* it.

- **The "narrow" half R3 owed is the cluster range in ADR.** It is nearly length-free but
  **compressed by construction** — median 1.33, IQR 1.20–1.42, hard ceiling 1.50, 16.9% pinned within
  0.05 of it — because the cluster is *selected* to fit under the multiplier. Fine as a gate, poor as
  a ranking key. **Whether the ×2 tightness dimension can be scored at all on this structure is
  ticket 15's to settle**, and it is now a real risk rather than a formality.
- **Cluster length k is the one new signal**: partial r **+0.260** in-sample and **+0.218** on deck
  17's fresh grades, both length-free. The trader prefers a longer tight cluster independent of how
  long the base is. The incumbent structure has no analogue for it and it is already computed.

**A correction to this ticket's own working.** The session first found the split *inherits* ticket
09's base-length problem (eye vs the split's base length, r = −0.375 on deck-A cards). It does not
reproduce out-of-sample: on deck 17's fresh cards the same correlation is **+0.029**, and against
08's window −0.041. The −0.375 was an artefact of deck A's population, where a long base means the
pathological "months of sideways" case rather than a long base as such. **Base length is not
evidence against the split.**

### R5. The parameter bill is 22, and one number is the whole cut

Ticket 08 resolved with zero tunables; ticket 09 cost it two; round 2 fitted six thresholds. The
split adds **22 free numbers** — 4 move windows, base min/max, cluster k range, the tightness
multiplier, two MA catch-up multiples, four line-fit numbers, six line-validity numbers, and the
prior-move floor. `MA_PROX_ADR` is defined and never read. **None is fitted to anything**; they are
q-scanner's defaults carried across whole.

Swept over 400 US names, swing in nightly list length across each parameter's plausible range:

| parameter | swing |
| --- | --- |
| `TIGHT_MULT` (1.25 / **1.5** / 1.75) | **63.2%** |
| `MAX_OVERSHOOT_FRAC` | 21.1% |
| `MAX_BASE_LEN` | 15.5% |
| `TOUCH_TOL_ADR` | 13.7% |
| `K_MAX` | 6.1% |

The tightness multiplier is simultaneously §3.4's looseness cut, the thing that bounds the stop, and
an unfitted borrowed constant that moves the list by two thirds across a range nobody could call
wrong on principle. **Priced here, not absorbed silently** — graduated to
[ticket 19](19-fit-the-split-parameters.md).

### R6. The option that was measured and not taken

For the record, because it is cheap to return to if ticket 15 cannot score tightness on the new
structure: ticket 08's detector plus **only** the cluster, as the looseness cut R3 asked for.
`08 + a cluster spanning ≤1.25×ADR` lands at **59 US / 11 IDX per night** — today's list length for
**one** parameter, with D2–D5, D7 and ticket 15's rubric untouched, and the stop shown at the cluster
low (within 1.5 ADR on 94.2% of detections against 64.1%). Working in `hybrid.py`.

### Knock-ons

- **Ticket 15 is unblocked but re-scoped, and its deck A fit is partly invalidated.** Its fitted
  contraction threshold (1.80) is defined over D3's retained set, which no longer exists; its churn
  and MA-distance numbers now measure a 14-bar base rather than a 3-bar window. Its carried-in D5
  probe (deck B) is moot — already-breached is 0.2% under the new trigger. Body updated.
- **Ticket 14 reopens.** Its A2 splits crossings three ways and reports only type 1, resting on D5's
  line descending nightly (98.3% of triggers) and on 16.4% of setups being born triggered. Under the
  `max()` clamp that population is **0.2%**, and the trigger no longer descends to meet a flat name.
  The rule was explicitly conditioned on this — *"if ticket 15 revisits D5, this reopens"* — so it
  does. Graduated to [ticket 18](18-digest-rule-under-the-clamped-trigger.md).
- **Ticket 11's I5 is amended.** The chart drew "the primary window only" because drawing D3's
  retained set would render the degeneracy. There is no retained set now: the chart draws the base
  with the cluster shaded inside it, the envelope, the clamped trigger and the cluster-low stop —
  which is the rendering the trader picked 10 of 11 times. `chart17.py` is the reference.
- **Ticket 12 is unaffected.** Detections, signal vectors and scores are dated append-only rows; a
  changed detector writes different rows, not a different schema.
