# Is the detector throwing away setups you want?

Type: prototype
Status: open
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

Carries **6 repeat pairs**, which with ticket 22's 6 would take ticket 20's test–retest ceiling from
12 pairs to 24 and roughly halve its error.
