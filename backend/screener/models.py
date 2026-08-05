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

# The three-state market regime is defined and computed in the domain layer; the
# API surface re-exports it so ``RegimeResponse.state`` shares one source of truth
# (v1-spec §4.9).
from .regime import RegimeState

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


class RegimeResponse(BaseModel):
    """The market regime banner's payload — **advisory only** (spec §4.9).

    Carries the three-state ``state``, its sizing posture in *words*, market
    ``breadth`` (share of the universe above its own rising SMA10/20, displayed
    and gating nothing), and the as-of ``session``. Two banners, one per market,
    never combined into a global verdict. The regime never filters, reorders or
    scores the candidate list — every field here is read and shown, none gates.

    ``state`` is ``None`` when the regime is **undefined** (fewer than 25 index
    bars) or no run has published; ``session`` is ``None`` only in the latter
    case, which is how the banner tells "warming up" from "nothing yet". ``posture``
    is ``None`` whenever ``state`` is.
    """

    market: str
    session: date | None
    state: RegimeState | None
    posture: str | None
    breadth: float | None
