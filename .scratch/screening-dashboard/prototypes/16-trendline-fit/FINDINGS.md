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

## What this leaves for the eye

`deck16.html` (50 cards, blind A/B, seed 16) asks which line sits where you would draw it. It is
built and it works, but its cards have a **median base of 3 bars**, because that is what the primary
window is — so it asks the eye to choose between two lines through three points. That is a weak
question, and it is weak for the same reason T4 is the real finding. It should probably be rebuilt
over whatever window the ticket settles on.
