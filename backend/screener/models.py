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


class ScoreRow(BaseModel):
    """One row of a candidate's star-score breakdown (spec §4.7).

    Eight of these reconstruct the score arithmetically next to the chart — the
    dimension's name, its weight (2 for tightness and orderliness, 1 for the rest)
    and whether it hit. ``n/10 → stars`` is ``sum(weight where hit) ÷ 2``.
    """

    dimension: str
    weight: int
    hit: bool


class Candidate(BaseModel):
    """One row of the candidate list — a detection made readable (spec §5.1).

    Five columns off the detection row. ``score`` is the star score (0–5) and the
    sort key of the list; ``breakdown`` carries its eight-row rubric so the chart
    panel can reconstruct the arithmetic (spec §4.7). ``dist_adr`` is the distance
    to the trigger in ADR (``(trigger − close) / adr_abs``); ``stopw_adr`` is the
    stop width in ADR (``(trigger − cluster_low) / adr_abs``, the watchlist stop
    of §4.6). The stop column **never filters** — instead the affordable sub-1×ADR
    minority is flagged (``affordable``), the inverse of marking the ~92%
    unaffordable majority. ``industry`` is the theme layer (``None`` if the label
    was never fetched); ``breadth`` is the ``k/5`` badge, a persistence count and
    **not** a quality score.

    Nothing here marks a ``line_ok`` failure: the fit's quality is a **silent
    tiebreak** that orders the list but is never surfaced in the row (spec §4.7).
    """

    symbol: str
    score: float
    breakdown: list[ScoreRow]
    dist_adr: float
    stopw_adr: float
    affordable: bool
    industry: str | None
    breadth: int


class CandidatesResponse(BaseModel):
    """Tonight's candidate list for one market (spec §5.1).

    ``session`` is the as-of published session, ``None`` when no run has
    published (an explicit empty state). ``ordered_by`` is ``"score"`` now that
    the star-score rubric lands (ticket 39): the list sorts by star score
    descending, with ``line_ok`` failures silently below equal-scored accepted
    names. The field remains for the UI to read the order honestly.
    """

    market: str
    session: date | None
    ordered_by: Literal["ticker", "score"]
    candidates: list[Candidate]


class Candle(BaseModel):
    """One OHLCV bar for the chart, **unadjusted** — real price levels the trigger
    and stop rules are placed at (spec §5.1 / §3.5). ``session`` is the trading
    date; the frontend renders these as candlesticks and the volume histogram."""

    session: date
    open: float
    high: float
    low: float
    close: float
    volume: int


class MaPoint(BaseModel):
    """One point of a moving-average line series — the value at a session. The
    line skips the leading bars where the window has not yet filled, so a series
    is shorter than the candle series and starts later (spec §4.2)."""

    session: date
    value: float


class ChartFacts(BaseModel):
    """The facts block beside the chart (spec §5.1): the numbers the row deliberately
    left off, read here where the trade decision is made.

    Populated from the name's detection row (``base_len``, ``trigger``,
    ``dist_adr``, ``stopw_adr``, ``adr``), its bars (``dollar_volume``, the §4.1
    median-20d liquidity), its rank rows (``decile_ranks``, percentile per
    lookback) and the label cache (``sector``). ``None`` for the whole block when
    the symbol has no detection tonight — the chart still draws, but there is no
    base to describe.
    """

    base_len: int
    trigger: float
    # Distance from today's close up to the trigger, in ADR — "how soon" (§5.1).
    dist_adr: float
    # Stop width normalised to ADR: (trigger − cluster_low)/adr_abs (§4.6).
    stopw_adr: float
    adr: float
    # Median unadjusted close × volume over 20 traded bars (§4.1). ``None`` if the
    # name's bars could not supply it.
    dollar_volume: float | None
    # lookback -> percentile in [0, 1]; the five decile ranks (§4.3). A lookback
    # the name is not ranked in (a recent listing) is simply absent from the map.
    decile_ranks: dict[str, float]
    # Yahoo/Morningstar GECS sector; ``None`` if the label was never fetched (§3.3).
    sector: str | None


class ChartResponse(BaseModel):
    """One symbol's evidence bundle — the chart panel in a single call (spec §5.1).

    Candles plus the daily MA set (SMA 10/20/50 and the 65 EMA, spec §2) as line
    series, and the facts block. ``session`` is the as-of published session, or
    ``None`` when no run has published (an explicit empty state). The MA lines are
    computed over the full stored history and then sliced to the drawn window, so
    the first drawn point already carries a full window behind it.
    """

    market: str
    symbol: str
    session: date | None
    candles: list[Candle]
    sma10: list[MaPoint]
    sma20: list[MaPoint]
    sma50: list[MaPoint]
    ema65: list[MaPoint]
    facts: ChartFacts | None


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
