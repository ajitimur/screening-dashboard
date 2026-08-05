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


class SectorStrength(BaseModel):
    """One sector's leadership and rotation numbers (spec §4.4 / ticket 07 S2–S8).

    ``shares`` carries the five per-lookback strengths — the share of this
    sector's members in that lookback's top decile, ``k/n``. ``members`` is
    ``n`` (the sector's universe count) and ``decile_counts`` is ``k`` per
    lookback, so the UI can render the ``k/n`` fragility badge (S4).
    """

    sector: str
    # n: the sector's universe members carrying this label. Always rendered even
    # at 0 — a dead sector is information (S8).
    members: int
    # lookback -> k/n share in [0, 1]; all five lookbacks always present.
    shares: dict[str, float]
    # lookback -> k, the count of members in that lookback's top decile.
    decile_counts: dict[str, int]
    # share(1w) − share(6m), the default rotation sort (S3). Positive = rotating in.
    shape_differential: float
    # share(1m, tonight) − share(1m, 20 sessions ago). ``None`` until 20 sessions
    # of rank history exist (S3) — the noisiest column, caveated in the UI.
    temporal_delta: float | None
    # k(1w) ≥ 2: this sector may top the rotation board. A thin single-name
    # sector cannot, and sorts into a separate visible group below (S4).
    rotation_eligible: bool
    # k(1m) < 2: the temporal delta rests on fewer than two names, so the Δ20d
    # cell is greyed and marked (S4).
    delta_low_confidence: bool


class IndustryStrength(BaseModel):
    """One ranked industry's shares (spec §4.4 / ticket 07 S5).

    An industry is ranked only at ``members ≥ 10`` — one rule, both markets,
    yielding many more rows on US than IDX. Industry *is* the theme layer (S1).
    """

    industry: str
    sector: str
    members: int
    shares: dict[str, float]
    decile_counts: dict[str, int]
    shape_differential: float


class SectorsResponse(BaseModel):
    """The sector board and the ranked-industry board for one market (§4.4).

    ``sectors`` is always the full 11-sector axis, default-sorted by shape
    differential with the rotation-ineligible sectors grouped below (S4/S8).
    ``industries`` carries only the ``members ≥ 10`` rows. ``session`` is the
    as-of published session, ``None`` when no run has published.
    """

    market: str
    session: date | None
    sectors: list[SectorStrength]
    industries: list[IndustryStrength]
