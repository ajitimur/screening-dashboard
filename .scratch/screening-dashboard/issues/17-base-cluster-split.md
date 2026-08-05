# Replace the window rule with a base/cluster split?

Type: prototype
Status: claimed
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
