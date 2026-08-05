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
