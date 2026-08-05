"""The candidate list: tonight's detections made readable (spec §5.1 / ticket 38).

Detection emits a base per name (spec §4.5); this module turns those dated rows
into the five-column list of the market workbench:

    ticker · star score · distance to trigger · stop width in ADR · industry · k/5

**The row decides whether to open the chart; the chart decides whether to trade**
(spec §5.1) — so the deliberately excluded columns (ADR, dollar volume, base
length, the five decile ranks, sector) live in the chart panel, not here.

Two properties are load-bearing and easy to get wrong:

- **The score is a placeholder.** The star-score rubric lands in a later ticket
  (39); until then ``score`` is ``None`` and the list is ordered **by ticker**,
  not by an invented temporary sort. Sorting by distance to trigger was explicitly
  rejected — it puts a 2★ barcode above a 5★ base (spec §5.1).
- **The stop column never filters.** ~92% of the nightly list carries a
  cluster-low stop wider than §7's 1×ADR cap (median row 1.28×), so a flag on the
  failures would fire on nearly every row and carry no information. The useful
  form is the inverse: the affordable sub-1×ADR **minority** is highlighted
  (``affordable``), and nothing is dropped (spec §4.6).

Composed from three streams, mirroring how the sector board composes ranks and
labels: the detection rows (the base + trigger + stop), the rank table (the
``k/5`` breadth badge, via :func:`ranks.breadth_counts`) and the label cache (the
industry). It never re-runs detection or ranking — it reads what the pipeline
published.
"""

from __future__ import annotations

from .detection import Detection
from .models import Candidate
from .ranks import Rank, breadth_counts

# §7's 1×ADR affordability cap: a row at or below it is the highlighted minority.
# Never a filter — a wider stop is a real, readable row (spec §4.6).
AFFORDABLE_ADR = 1.0


def build_candidates(
    detections: list[Detection],
    ranks: list[Rank],
    industry_of: dict[str, str],
) -> list[Candidate]:
    """The candidate rows for a session, **ordered by ticker** (spec §5.1).

    ``industry_of`` maps symbol → industry from the label cache; a name with no
    cached label gets ``None`` rather than being dropped. ``ranks`` is the
    session's rank table, read only for the ``k/5`` badge.
    """
    breadth = breadth_counts(ranks)
    return [
        Candidate(
            symbol=det.symbol,
            score=None,  # placeholder until the rubric lands (ticket 39)
            dist_adr=det.dist_adr,
            stopw_adr=det.stopw_adr,
            affordable=det.stopw_adr <= AFFORDABLE_ADR,
            industry=industry_of.get(det.symbol),
            breadth=breadth.get(det.symbol, 0),
        )
        for det in sorted(detections, key=lambda d: d.symbol)
    ]
