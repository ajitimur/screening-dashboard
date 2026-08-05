# Ticket 16 — what the measurement found before any grading

Measured over the whole round-2 pool: **31,553 detections** (24,604 US + 6,949 IDX), not deck A's
120 cards. Reproduce with `compare.py` → `analyse.py` → `longest.py`.

## T1. The ticket's premise was half right: F3 *is* a fitting artefact

Ticket 09's F3 — 16.4% of `WATCHING` setups emitted with the trigger already below the close — is
confirmed as an artefact of where the line sits, not of D5's `min()` rule being wrong in principle.

| trigger rule | already-breached |
| --- | --- |
| OLS + `min()` — ticket 08 D5, today | **16.0%** |
| envelope + `min()` | **2.1%** |
| either fit + `max()` (q-scanner's clamp) | **0.2%** |

The residual breaches under the envelope are trivially shallow: median 0.003 ADR below the close,
against 0.097 ADR today.

## T2. But the reference implementation differs on the *clamp*, not the fit — and that was conflated

The ticket was charted as "envelope or least squares". Reading `q-scanner-v2/qscan/pattern/engine.py`
(step 7) shows it **does not derive the trigger from the line at all**:

```python
trigger = max(uf.line.value_at(as_of + 1), cl.high)   # cl = the tight cluster
stop    = cl.low
```

with its own comment explaining why: the line only descends from the cluster's max high, so
projecting it forward "always lands at or below the cluster high — and in steep flags it falls
below the cluster **low**, which would put the trigger under the stop".

So q-scanner clamps **up** to the recent high; ticket 08's D5 clamps **down** to it via `min()`.
**Opposite directions.** Two further mismatches: q-scanner anchors the envelope at the max high of
the *trailing cluster* (3–7 bars), not of the whole base, and it stops at the **cluster low**, not
the base low. The fit and the clamp are separable, so both were varied:

| fit | clamp | Δ trigger | breached | D6 gate rejects |
| --- | --- | --- | --- | --- |
| OLS | `min()` — today | — | 16.0% | 0.0% (by construction) |
| envelope | `min()` | +0.171 ADR | 2.1% | **30.9%** |
| OLS | `max()` | +0.513 ADR | 0.2% | **69.4%** |
| envelope | `max()` | +0.513 ADR | 0.2% | **69.4%** |

The bottom two rows are *identical* because the `max()` clamp binds on 82% of detections — where it
binds, the line is irrelevant and the trigger is simply the recent high. **The clamp is a far bigger
lever than the fit**, and the ticket's headline figure (+0.09 ADR, from deck A's 120) understated
the move because it measured a mis-specified anchor.

## T3. The gate cost is real, not a threshold artefact

Adopting the envelope under `min()` costs 30.9% of today's accepted pool to D6's 1×ADR affordability
gate (US 31.5%, IDX 29.0%; 26.4% among 4–5 star setups). That loss is **not** a pile of setups
sitting just over the line: the newly-rejected had a median stop width of **0.914 ADR under OLS
already**, and 56.1% were already above 0.9. They were never comfortably affordable — the OLS
trigger sitting too low is what made them look affordable. Relaxing the gate to 1.10 ADR recovers
42.8% of them; to 1.25 ADR, 74.8%.

The loss is mildly *benign* in shape: it falls hardest on 2★ setups (33.8%) and lightest on 5★
(20.1%), and concentrates in 5–10 bar bases (49.4%).

## T4. The load-bearing decision is the window, and it is upstream of this ticket

Ticket 08's **D4** takes the shortest valid end-anchored window as the primary one (D3 is the
neighbouring decision to *retain* every valid window; the two are easy to conflate). Measured:

- The primary window is **3 bars on 52%** of detections, **≤5 bars on 83.6%**.
- The longest valid window has a median of **13 bars**; median gap is **9 bars**.
- Only 18.3% of detections have primary == longest.

**This is not an oversight in ticket 08 — it is an accepted degeneracy, and that is what makes it
arguable.** D4 records that every distance quantity over an end-anchored window is monotone in L
(the window low is a running minimum, the high a running maximum), so ranking windows by tightness
or by MA proximity *collapses* to L=3. A √L normalisation was considered and dropped; the degeneracy
was accepted instead, defended on the grounds that the shortest window gives the earliest,
nearest-the-MA trigger — the entry §3.2 argues hardest for, and what keeps the §7 stop affordable.

That argument holds for tightness and MA proximity. **It does not obviously carry to a line fit**,
which D5 then performs over the same window: "the shortest window gives the most affordable entry"
says nothing about whether a descending boundary through three points describes anything. The
degeneracy was accepted for one purpose and inherited by another. Ticket 08 flagged D5 itself twice
as the weakest link — *"the decision most likely to look wrong against real charts"*.

**Neither fit means anything over 3 points.** "Envelope or least squares" is close to moot at the
place the trigger is actually computed — and over the primary window the base is only 1.22 ADR tall
(median), so `min()` vs `max()` is very nearly the choice between triggering at the base low end or
the base high, which is why the two clamps differ by 0.513 ADR.

Fitting over the longest window instead — the shape a triangle actually describes, and the shape
ticket 09's `chart.py` drew — does not rescue it, because the base is then 3.26 ADR tall and D6's
gate against the **base low** rejects 72.8–95.0%. Paired with q-scanner's **cluster low** stop it is
survivable but still expensive:

| longest window, stop = cluster low | breached | D6 rejects |
| --- | --- | --- |
| OLS + `min()` | 21.2% | 38.9% |
| envelope + `min()` | 4.4% | 61.3% |
| envelope + `max()` | 0.2% | 84.3% |

## T5. The conformance bug is confirmed and fixed here

Ticket 09's `chart.py` drew both the retained-set band and the primary band, fitted the triangle over
the **longest** window, and drew a trigger from the **shortest** — so deck A showed a triangle over
one base and a trigger from another, against ticket 11's I5. Given T4's numbers (3 bars vs 13),
**this is almost certainly the bulk of what the trader's eye objected to**: the line looked wrong
relative to the drawn triangle because they belong to different windows. `chart16.py` draws the
primary window only, per I5.

## T6. D6 stops being a gate — and that alone is unaffordable

**The trader's call:** the 1×ADR affordability test is an entry-time judgement, not a screening
criterion. This is a scanner; its job is to surface setups, and the stop is decided when the trade
is taken. D6 becomes a displayed quantity, never a hard cut.

Correct in principle, but it cannot stand alone, because D6 was the only thing holding the list
down. With nothing rejected on trigger-to-stop (`nogate.py`):

| | US/night | IDX/night |
| --- | --- | --- |
| today, D6 gating | ~64 | ~12 |
| D6 shown, not enforced | **~314** | **~47** |

190,044 ungated detections against 31,553. Ticket 11 designed the nightly review around ~10
minutes; a 314-name list is not that.

Ticket 08's own words explain why: *"This gate is what §3.4's first auto-reject ('loose, wide-range
consolidation') looks like in numbers."* **D6 was doing two jobs under one number** — §7
affordability (entry-time, the trader's) and §3.4 looseness (screening, the app's). They were
conflated because the same ratio measures both.

**Resolution: separate them.** Stop width becomes a column and sort key, never a cut. A looseness
cut stays, but expressed as a property of the *base* rather than of the trader's affordability.

Knock-on: **D7 leans on D6 being a gate.** It scores tightness as only "narrowing", not "narrow",
reasoning that narrowness *"is already pass/fail"* via D6. Remove the gate and "narrow" is captured
nowhere, leaving the ×2 tightness dimension measuring half of what §3.5 asks. Whatever looseness cut
replaces D6 has to restore it.

## T7. q-scanner's base/cluster split supplies exactly that cut — measured

Ported in `split.py` over 318,357 bar-dates. It is not a variant of D2–D4 but a different structure:
the base runs from the **prior move's peak** to today (capped at 45 bars), and inside it a **3–7 bar
trailing cluster spanning ≤ 1.5×ADR** must exist, sitting on a rising 10/20/50 MA.

| funnel | share of bar-dates |
| --- | --- |
| base ≥ 3 bars | 75.1% |
| tight 3–7 bar cluster | 34.8% |
| caught up to the 10/20 | 32.3% |
| drawable line (touch zones + bounded overshoot) | 18.2% |
| all three | **17.0%** |

Three properties fall out, and together they answer T4 and T6 at once:

**1. The base becomes a shape you can fit a line to.** Median **14 bars** (IQR 8–22) against ticket
08's 3. The envelope-vs-OLS question becomes meaningful for the first time.

**2. The stop is bounded by construction — no affordability gate needed.** Trigger is
`max(line, cluster_high)` and the stop is the cluster low, so trigger-to-stop cannot exceed the
cluster's own range, which is *defined* as ≤ 1.5×ADR. Measured maximum across all 54,201 surviving
detections: **1.499 ADR**. The tightness cut and the affordability question are the same object,
expressed the way the trader asked for it — as a property of the base, not of their stop.

**3. The list lands where it already is.** With q-scanner's own prior-move fallback (≥25% run-up):

| prior-move floor | US/night | IDX/night |
| --- | --- | --- |
| none | 89.9 | 15.3 |
| ≥ 25% | **62.6** | **11.0** |
| ≥ 40% | 44.0 | 8.1 |
| ≥ 60% | 29.3 | 6.2 |

~63 US/night against today's ~64 — the same nightly volume, but with 14-bar bases, a structurally
bounded stop, and no affordability gate doing hidden screening work.

**Caveat:** this measures *structure* only — base length, cluster existence, line drawability, list
length, stop width. It does not check that the setups it finds are the ones the eye wants, and no
star rubric was re-derived. That comparison is unowned.

## What this leaves for the eye

`deck16.html` (50 cards, blind A/B, seed 16) asks which line sits where you would draw it. It is
built and it works, but its cards have a **median base of 3 bars**, because that is what the primary
window is — so it asks the eye to choose between two lines through three points. That is a weak
question, and it is weak for the same reason T4 is the real finding. It should probably be rebuilt
over whatever window the ticket settles on.
