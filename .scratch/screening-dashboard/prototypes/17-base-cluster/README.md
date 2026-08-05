# Ticket 17 — replace the window rule with a base/cluster split?

Throwaway prototype for [`17-base-cluster-split.md`](../../issues/17-base-cluster-split.md).
Builds on the ticket-09 prototype (bars, detector, rank table) and the ticket-16 one (the split
port, the envelope fits); `cache/` symlinks to ticket 09's.

**Read [`FINDINGS.md`](FINDINGS.md) first.** Short version: ticket 16 measured the split's structure
and it looked like a free upgrade. Measured against the *names*, it is a different screen of the
same size — 26% overlap with today's list — and its accept/reject is uncorrelated with the trader's
120 existing grades. The cluster is worth having; the base is what costs ticket 15's rubric.

## Code

| file | what it does |
| --- | --- |
| `overlap.py` | joins both scans on (market, symbol, date); the agreement and funnel tables |
| `at_dates.py` | runs the split at arbitrary bars — the two scans sweep different date grids |
| `grades.py` | the split's accept/reject against deck A's 120 existing human grades |
| `contraction.py` | candidate replacements for D7, scored on eye correlation and the length trap |
| `params.py` | the parameter bill, and a sensitivity sweep of the five load-bearing ones |
| `hybrid.py` | ticket 08's base + the split's cluster — the option the ticket did not name |
| `chart17.py` | candles in three modes: bare, 08's geometry, the split's geometry |
| `build_deck17.py` | renders `deck17.html` — 75 cards, two sections, seed 17 |

Run order: `overlap.py` → `grades.py` → `contraction.py` → `params.py` → `hybrid.py` →
`build_deck17.py`. Needs `pandas numpy` and ticket 09's cache.

## The deck

`deck17.html` is self-contained; open it in a browser.

- **Section 1, cards 1–60**: bare charts, graded `1`–`5`. Blind — 20 cards from each of the three
  arms (shared / 08 only / split only), shuffled, with no overlay that could identify the arm.
- **Section 2, cards 61–75**: the same bars drawn by both detectors, side by side. `a` / `b` / `n`.
  Which side is which is randomised per card; the key is in `deck17_key.json`.

`j`/`k` move, grades persist in the browser, **export** emits a 75-character string to paste back
into the session.
