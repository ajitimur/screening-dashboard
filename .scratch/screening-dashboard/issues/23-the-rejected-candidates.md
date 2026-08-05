# Is the detector throwing away setups you want?

Type: prototype
Status: resolved
Blocked by: —

## Question

If the names the detector **rejects** grade as well as the ones it surfaces, the screen is
discarding setups the trader wants — and the whole star-score effort is calibrated on the wrong
population.

**This obligation has now been passed along three tickets without being discharged.** Ticket 11
ruled there is no rejected-candidates view in v1 and handed the inspection to ticket 09, which did
not do it. Round 2's deck D was never graded. Ticket 15 rendered deck D3 and stopped, then
[ticket 20](20-confirm-the-band-and-measure-the-ceiling.md) carried it again and settled the band
and the ceiling instead. It gets its own ticket here so it stops hiding inside someone else's.

Nothing needs building. **`deck3_D.html` is rendered and waiting**: 46 cards — 20 split rejects,
20 accepted detections, 6 repeats — all bare, so nothing on a card says which is which. The
question on the deck is deliberately the different one: **is there a setup here you would want to
see tonight?** Then:

    analyse3.py A=<grades3_A.txt> E=<grades3_E.txt> D=<string>

Section 6 is written and verified. The 20 rejects split evenly between the split's **own** two
rejection paths — 10 `no_cluster`, 10 `line_not_drawable`. The third path, `not_caught_up`, is 1.6%
of bar-dates and is deliberately not sampled.

**The question is live rather than inherited**, which is why it survived three hand-offs without
going stale: [ticket 17](17-base-cluster-split.md) replaced the window rule with the base/cluster
split, so *which* names get rejected changed. This measures the current detector, not ticket 08's.

Sizing, from `PREREGISTRATION_R3.md` §2: 20 per arm resolves a **1.00★** difference at 80% power;
a 0.75★ difference needs 33 per arm. So a clear result is readable and a marginal one is not — say
which arrived rather than reading a null as a pass.

Carries **6 repeat pairs**. Ticket 22's 6 landed independently and in parallel; the two repeat sets
are **disjoint**, so together they take ticket 20's test–retest ceiling to **24 pairs**.

## Answer

**No — the detector is not throwing away setups you want.** 46 bare cards graded; full write-up in
[`DECK_D_RESULTS.md`](../prototypes/15-grading-round-2/DECK_D_RESULTS.md).

**Pooled rejects grade −0.90★ below accepted detections** (n=20 vs 20, se 0.40, 95% CI −1.67 to
−0.13). The interval excludes zero, so the direction is established. The deck was sized to resolve
1.00★ and −0.90★ falls just inside that, so **the sign is the finding and the size is provisional**
— a 0.75★ gap would have needed 33/arm. The obligation ticket 11 opened and tickets 09, 15 and 20
each carried without discharging is **discharged here, in the detector's favour**: the star score is
calibrated on the right population.

**But the result is carried almost entirely by one of the two rejection paths.**

| arm | n | mean eye | Δ vs detections | 95% CI |
| --- | --- | --- | --- | --- |
| accepted detections | 20 | 3.20 | — | — |
| reject `no_cluster` | 10 | 1.80 | −1.40★ | −2.44 to −0.36 |
| reject `line_not_drawable` | 10 | 2.80 | −0.40★ | −1.22 to **+0.42** |

`no_cluster` earns its place — 7 of 10 cards graded 1★. `line_not_drawable` does not separate: its
interval spans zero, −0.40★ is below the eye's own 0.56★ noise floor, and 3 of its 10 cards graded
4★ against a detection arm that only reaches 3.20. **That path is unresolved, and n=10 could never
have resolved it** — carried to [ticket 25](25-the-line-not-drawable-path.md). The third path,
`not_caught_up`, was deliberately not sampled and remains unmeasured.

**The ceiling moved 12 pairs → 18 and held**: test–retest **r = +0.831**, mean absolute difference
0.56★ (ticket 20 measured +0.808 on 12). **Ticket 22 did the same thing at the same time**, on a
*disjoint* set of 6 repeats, reading **+0.854** (0.44★) on its own 18. Both are honest 18-pair
measurements of the same quantity and they agree to within 0.02; neither is the pooled figure. The
combined **24-pair ceiling is unmeasured**, and it is the number every correlation on this map should
eventually be read against.

Nothing else moved — deck D carries no A or E cards, so the tightness gate, the boolean/continuous
choice, the 4★ cut and the orderliness band's failure all read exactly as ticket 20 left them.

**Method note:** section 6 of `analyse3.py` printed per-arm means and stopped, with no contrast and
no interval — a null would have read as a pass, the exact failure this ticket warned about. It now
computes the pooled contrast against R3 §2's sizing and names which resolution arrived.
