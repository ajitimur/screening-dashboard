# Star score calibration prototype

Throwaway prototype for ticket `../../issues/09-star-score-calibration.md`. Not production code.

- **`FINDINGS.md`** — what was measured before the grading session. Start here.
- **`deck.html`** — the blind-grading deck: 27 charts, score hidden until you click reveal.
  Open it directly in a browser; it is self-contained.

## Code

| file | what it does |
| --- | --- |
| `detector.py` | ticket 08's detector, readable reference implementation |
| `fastscan.py` | vectorised equivalent (slopes from cumsums); verified identical to the reference |
| `score.py` | first-cut §3.5 scorer, boolean and continuous variants |
| `synth.py` | controlled synthetic bases — the test that established F1 and F2 |
| `chart.py` | SVG candles with the detector's evidence drawn on |
| `fetch.py` / `universe.py` / `sectors.py` / `idx.py` | cached yfinance pulls |
| `ranks.py` | ticket 06's rank table at prototype scale |
| `sweep.py` / `outcomes.py` / `analyse.py` | the sweep, forward outcomes in R, and the analysis |
| `build_deck.py` | assembles `deck.html` |

Run order: `universe.py` → `sectors.py` → `ranks` (auto) → `sweep.py` → `outcomes.py` → `analyse.py`
→ `build_deck.py`. Needs `yfinance pandas numpy requests`.
