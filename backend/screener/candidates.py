"""The candidate list: tonight's detections made readable (spec §5.1 / ticket 38).

Detection emits a base per name (spec §4.5); this module turns those dated rows
into the five-column list of the market workbench:

    ticker · star score · distance to trigger · stop width in ADR · industry · k/5

**The row decides whether to open the chart; the chart decides whether to trade**
(spec §5.1) — so the deliberately excluded columns (ADR, dollar volume, base
length, the five decile ranks, sector) live in the chart panel, not here.

Two properties are load-bearing and easy to get wrong:

- **The list sorts by star score descending, with a silent tiebreak.** At equal
  score a name that failed ``line_ok`` (the envelope fit's quality verdict) sorts
  **below** the accepted names — and nothing marks it: no glyph, no column, no
  chart annotation (spec §4.7). Two independent rulers put the demotion inside the
  eye's own noise floor, so it is a tiebreak and not a dimension. Sorting by
  distance to trigger was explicitly rejected — it puts a 2★ barcode above a 5★
  base (spec §5.1).
- **The stop column never filters.** The proposed stop is now the trader's own
  convention — a fixed 0.345 ADR below the trigger (issue #127), calibrated to his
  measured 649-entry distribution rather than the old ~1.28× cluster-low default —
  so every row sits at or under §7's 1×ADR cap and is ``affordable``. The flag
  stays the inverse form (highlight the sub-1×ADR minority), still never a filter;
  nothing is dropped (spec §4.6).

Composed from three streams, mirroring how the sector board composes ranks and
labels: the detection rows (the base + trigger + stop + the score's signal
vector), the rank table (the ``k/5`` breadth badge and the prior-move percentile)
and the label cache (the industry and the sector for the leave-one-out share). It
never re-runs detection or ranking — it reads what the pipeline published, and the
star score is **derived** from those persisted rows, never stored.

The score is stop-blind and regime-blind by construction: :func:`score.star_score`
takes neither, so no amount of wiring here can leak them in (spec §4.6 / §4.9).
"""

from __future__ import annotations

from .detection import Detection, detection_gate
from .models import Candidate, ScoreRow
from .ranks import Rank, breadth_counts
from .score import star_score
from .sectors import leave_one_out_sector_shares

# §7's 1×ADR affordability cap: a row at or below it is the highlighted minority.
# Never a filter — a wider stop is a real, readable row (spec §4.6).
AFFORDABLE_ADR = 1.0


def build_candidates(
    detections: list[Detection],
    ranks: list[Rank],
    industry_of: dict[str, str],
    sector_of: dict[str, str],
    dollar_volume_of: dict[str, float | None] | None = None,
    prev_detected: set[str] | frozenset[str] = frozenset(),
) -> list[Candidate]:
    """The candidate rows for a session, **sorted by star score** (spec §4.7/§5.1).

    ``industry_of`` maps symbol → industry from the label cache; a name with no
    cached label gets ``None`` rather than being dropped. ``sector_of`` maps
    symbol → GECS sector, for the score's leave-one-out sector share **and** the
    row's ``sector`` fact. ``ranks`` is the session's rank table, read for the
    ``k/5`` badge, the prior-move percentile and the row's ``decile_ranks``.

    The **chart-facts fold** (spec §4.3): a Setups card shows trigger, stop and
    distance without a per-symbol chart fetch, so those facts ride the row too,
    projected from the *same* detection the chart renders from. ``dollar_volume_of``
    maps symbol → the §4.1 median-20d liquidity off its bars (``None`` when the
    bars could not supply it, or the symbol is absent); it is the one fact not
    carried on the detection row itself, so the caller reads bars for it exactly as
    the chart does. ``prev_detected`` is last session's detected symbol set —
    ``new_tonight`` is absence from it, so on the first session every name is new.

    The score is derived here from the detection's own signal vector plus two
    cross-sectional inputs off the same session: the prior-move decile gate and
    the leave-one-out 1m sector share. The list then sorts by score descending
    with ``line_ok`` failures below equal-scored accepted names — a silent
    tiebreak, ticker breaking any remaining tie for a stable order.
    """
    dollar_volume_of = dollar_volume_of or {}
    breadth = breadth_counts(ranks)
    # The five decile ranks per name, grouped off the same rank table the chart
    # facts read (spec §4.3); a lookback the name is not ranked in is simply absent.
    decile_ranks: dict[str, dict[str, float]] = {}
    for r in ranks:
        decile_ranks.setdefault(r.symbol, {})[r.lookback] = r.percentile
    # Prior move (§4.7): the name clears the decile gate. Every detection does by
    # construction, but computed honestly off the same rank table rather than
    # assumed. Sector confirmation is the leave-one-out 1m share (§4.4).
    prior_move = detection_gate(ranks)
    sector_shares = leave_one_out_sector_shares(ranks, sector_of)

    rows = []
    for det in detections:
        stars, breakdown = star_score(
            det,
            prior_move=det.symbol in prior_move,
            sector_share=sector_shares.get(det.symbol, 0.0),
        )
        rows.append(
            (
                det,
                Candidate(
                    symbol=det.symbol,
                    score=stars,
                    breakdown=[ScoreRow(**vars(d)) for d in breakdown],
                    dist_adr=det.dist_adr,
                    stopw_adr=det.stopw_adr,
                    affordable=det.stopw_adr <= AFFORDABLE_ADR,
                    industry=industry_of.get(det.symbol),
                    breadth=breadth.get(det.symbol, 0),
                    # -- the chart-facts fold (spec §4.3), from the same detection.
                    # trigger_price is the overlay's borrowed name for the cluster
                    # high; stop_price is the proposed convention stop line
                    # (trigger − budget, issue #127), no longer the cluster low
                    # (never risk_adr; §2.3).
                    trigger_price=det.trigger,
                    stop_price=det.stop_price,
                    close=det.close,
                    sector=sector_of.get(det.symbol),
                    adr=det.adr,
                    dollar_volume=dollar_volume_of.get(det.symbol),
                    decile_ranks=decile_ranks.get(det.symbol, {}),
                    new_tonight=det.symbol not in prev_detected,
                ),
            )
        )
    # Star score descending; at equal score line_ok failures sink below accepted
    # names (the silent tiebreak); ticker breaks any final tie (spec §4.7).
    rows.sort(key=lambda r: (-r[1].score, not r[0].line_ok, r[0].symbol))
    return [candidate for _det, candidate in rows]
