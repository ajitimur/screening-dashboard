# Ticket 16 — trendline fitting: envelope or least squares?

Throwaway prototype for [`16-trendline-fitting-envelope-vs-least-squares.md`](../../issues/16-trendline-fitting-envelope-vs-least-squares.md).
Builds on ticket 09's prototype next door, which owns the detector, the bar cache and the original
chart renderer; `cache/` here is a symlink to it.

**Read [`FINDINGS.md`](FINDINGS.md) first.** Short version: the ticket asked which line to fit, and
the measurement says the fit is the smallest of three levers — the *clamp* direction matters more,
and the *window* matters most of all, because ticket 08's primary window is 3 bars on 52% of
detections and no line means much over three points.

## Code

| file | what it does |
| --- | --- |
| `envelope.py` | both upper fits, and the 2×2 of fit × clamp they imply |
| `compare.py` | re-fits all 31,553 detections over the **primary** window; writes `fit_compare.pkl` |
| `analyse.py` | decomposes the D6 gate loss — is it real or a threshold artefact? |
| `longest.py` | the same 2×2 over the **longest** valid window |
| `chart16.py` | candles over the primary window only (per ticket 11's I5), both lines drawn |
| `build_deck16.py` | renders `deck16.html` — 50 cards, blind A/B, seed 16 |

Run order: `compare.py` → `analyse.py` → `longest.py` → `build_deck16.py`.
Needs `pandas numpy` and ticket 09's cache.

## The deck

`deck16.html` is self-contained; open it in a browser. `a`/`b`/`n` answer and advance, `j`/`k` move,
**export** emits a 50-character string to paste back into the session. The A/B assignment is
randomised per card (key in `deck16_key.json`), so you cannot follow a colour.

Note its limitation, recorded in FINDINGS T4: the cards have a median base of **3 bars**, so the
deck asks the eye to choose between two lines through three points. It is worth grading only if the
window question resolves in favour of the primary window.
