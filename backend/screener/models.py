"""Pydantic response models.

These are the OpenAPI schema source of truth: FastAPI derives the OpenAPI
document from them, and ``openapi-typescript`` turns that into the committed
frontend ``.d.ts`` (v1-spec §7.5). Renaming a field here is meant to break the
frontend typecheck rather than surface as a runtime ``undefined``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

# A run either published its session or was quarantined behind a banner because
# it resolved < ~99% of enumerated symbols (v1-spec §3.4 rule 7 / A2).
RunStatus = Literal["published", "quarantined"]


class RunRecord(BaseModel):
    """One row of the append-only ``runs`` table, keyed ``(market, session)``."""

    market: str
    session: date
    status: RunStatus
    symbols_enumerated: int
    symbols_resolved: int
    created_at: datetime


class RunsResponse(BaseModel):
    """Run records for one market, newest first.

    ``latest`` is the last *published* run — the as-of session the tab renders.
    It is ``None`` when no run has published yet, which the tab shows as an
    explicit empty state rather than a blank or a fabricated date.
    """

    market: str
    latest: RunRecord | None
    runs: list[RunRecord]
    # Tonight's tradeable universe size — the count of membership rows for the
    # latest published session (spec §4.1). ``None`` when no run has published.
    universe_size: int | None


class BoardRow(BaseModel):
    """One leaderboard row: a name ranked on **pure return**, plus its furniture
    (spec §4.3 / ticket 06). ``breadth`` is the ``k/5`` badge (lookbacks currently
    led — a persistence count, *not* a quality score); ``is_new`` marks absence
    from this board last session; ``surge`` flags a 1w name up ≥30% over the week;
    ``adr`` is a column for the toggle, never the sort key, ``None`` when it cannot
    be computed."""

    symbol: str
    raw_return: float
    breadth: int
    is_new: bool
    surge: bool
    adr: float | None


class Board(BaseModel):
    """One market's leaderboard for a single lookback (spec §5.2)."""

    lookback: str
    rows: list[BoardRow]


class BoardsResponse(BaseModel):
    """The five leaderboards for one market, off the nightly path (spec §5.2).

    ``session`` is the as-of session the boards were ranked on — the latest
    published run — or ``None`` when no run has published yet, which the tab shows
    as an explicit empty state.
    """

    market: str
    session: date | None
    boards: list[Board]
