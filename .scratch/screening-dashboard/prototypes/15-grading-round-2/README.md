# Round 2 — the larger grading round

> **Round 3 supersedes the decks below.** Ticket 17 replaced the detector's window rule, so decks
> A, B and C measure a structure that no longer runs. Read
> **[`REFIT_FINDINGS.md`](REFIT_FINDINGS.md)** for what round 2's grades still say on the new
> geometry, then **[`PREREGISTRATION_R3.md`](PREREGISTRATION_R3.md)** for the round that replaces
> them. To grade: open `deck3_A.html` (the one that must be finished), then `deck3_C.html` and
> `deck3_D.html`, and run `analyse3.py A=<string> C=<string> D=<string>`.
>
> Round 3 code: `split_signals.py` · `split_tightness.py` · `split_diag.py` · `split_refit.py` ·
> `rubric3.py` · `build_deck3.py` · `analyse3.py`. Everything needs pandas 3.x — the cached
> pickles are written with its string dtype.


Prototype for ticket [`15-star-score-second-grading-round.md`](../../issues/15-star-score-second-grading-round.md).
Builds on ticket 09's prototype next door (`../09-star-score/`), which owns the detector, the bar
cache and the chart renderer. Nothing here re-implements those.

**Read [`PREREGISTRATION.md`](PREREGISTRATION.md) first.** It fixes the deck sizes, the sampling,
the fitting objective and every decision rule *before* any card was graded. That is the whole point:
round 1 ended at "weakly positive, thresholds unset", and a second round that picked its rules after
seeing the grades would not be able to tell a calibrated rubric from a fitted story.

## How to grade

Open the decks in a browser. They are self-contained files.

| deck | cards | question |
| --- | --- | --- |
| `decks/deck_A.html` | 120 | the core round — grade the setup 1–5★ |
| `decks/deck_B.html` | 52 | same question, split on the trigger |
| `decks/deck_C.html` | 52 | same question, IDX only |
| `decks/deck_D.html` | 40 | **different question** — is there a setup here at all? No overlays. |

`1`–`5` grades and advances, `0` clears, `j`/`k` move. Progress is kept in the browser, so you can
stop and come back. Hit **export** and paste the line back into the session.

**Deck A is the one that matters.** It alone answers the ticket's primary question and fits the
thresholds; B, C and D each answer one question carried in from ticket 09 and can wait for a second
sitting. Nothing is revealed until you submit — deliberately, so a card graded late is not shaped by
a score seen early.

## Code

| file | what it does |
| --- | --- |
| `rubric2.py` | the rubric: ticket 09's settled structure, thresholds left free, plus the fitter |
| `build_pool.py` | scores every detection under round-2 measurement, and collects the **rejects** |
| `sample.py` | draws the four decks exactly as the pre-registration specifies (seed 15) |
| `build_deck2.py` | renders the decks |
| `analyse2.py` | runs the pre-registered analysis over the exported grades |

Run order: `build_pool.py` → `sample.py` → `build_deck2.py` → (grade) → `analyse2.py grades.txt`.
Needs ticket 09's cache to exist; rebuild it with that prototype's `universe.py` → `sectors.py` →
`sweep.py` if it is missing.
