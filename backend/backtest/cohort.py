"""Joining a simulated trade back to the persisted row that produced it.

Every measurement downstream of Phase 4 needs the same two things: an index of the
denominator's detection rows for a market, and a **total** join from the trades
the simulator took to the rows they came from. :mod:`backtest.ranking` needs the
score off that row; :mod:`backtest.candidates` needs the two candidate values off
the same row. The join itself is identical, and its refusal has to be, because the
argument for refusing is the same one in both places.

Why the join is total, and never a filter
-----------------------------------------
Every simulated trade came from a persisted detection: the simulator walks the
denominator's own rows. So a trade with no row is a broken denominator, not a
trade to drop. Dropping it quietly would shrink the cohort a measurement is
computed over with nothing in the output to say which trades left — and the trades
most likely to go missing are not a random sample of them, since whatever broke
the row is likely to correlate with the market, the year or the name.

Burn-in
-------
:func:`detection_index` excludes burn-in sessions by default, matching
:func:`~backtest.simulate.walk_detections`, so an index and the trades built
against it cover the same sessions rather than nearly the same ones. A warm-up
session is computed and persisted like any other and simply never measured (PRD
#182 story 76).
"""

from __future__ import annotations

from datetime import date
from typing import Mapping, Sequence

from replay.field import ScoredDetection

from .denominator import DenominatorStore
from .simulate import SimulatedTrade

# The key the denominator's own primary key uses: a symbol is detected at most
# once on a session, so the join below is exact rather than nearest.
DetectionIndex = Mapping[tuple[date, str], ScoredDetection]


def detection_index(
    denominator: DenominatorStore, market: str, *, include_burn_in: bool = False
) -> dict[tuple[date, str], ScoredDetection]:
    """Every persisted detection row for one market, keyed by session and symbol.

    The whole row rather than a projection of it, because its two callers want
    different parts — the star score, and the two candidate values — and an index
    per caller would walk the store twice to produce two views of one table.
    """
    index: dict[tuple[date, str], ScoredDetection] = {}
    for header in denominator.sessions(
        market, burn_in=None if include_burn_in else False
    ):
        for scored in denominator.detections(market, header.session):
            index[(header.session, scored.symbol)] = scored
    return index


def join_detections(
    trades: Sequence[SimulatedTrade], index: DetectionIndex
) -> list[tuple[SimulatedTrade, ScoredDetection]]:
    """Pair each trade with its persisted row, refusing a trade that has none.

    See the module docstring for why this raises rather than filters. The pairs
    come back in the order the trades arrived, so a caller building its own row
    type from them preserves whatever order the simulator produced.
    """
    out: list[tuple[SimulatedTrade, ScoredDetection]] = []
    for trade in trades:
        key = (trade.detection_session, trade.symbol)
        if key not in index:
            raise ValueError(
                f"no persisted detection row for {trade.symbol} detected "
                f"{trade.detection_session}: the join from trade to row is total, "
                "and a missing row is a broken denominator rather than a trade to "
                "drop"
            )
        out.append((trade, index[key]))
    return out
