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

# Sector/industry labels are yfinance GECS, one taxonomy on both markets. Every
# sector-bearing response records it, because the labels carry a single ``as_of``
# and no effective period — a relabel silently rewrites history, so naming the
# taxonomy on the wire is the one thing that makes the gap legible (spec §2.6).
Taxonomy = Literal["GECS"]


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
    # Run-on-open (spec §7.3): ``run_due`` is true when the store's last final
    # session is missing — the tab kicks a run on open. ``running`` is true while
    # a run for this market is in flight, so the tab shows a progress state rather
    # than a half-written session (the served ``latest`` stays the last published
    # session throughout).
    run_due: bool = False
    running: bool = False
    # The message from the last run that *failed* for this market, or ``None``.
    # A failed run publishes nothing, so without this the tab cannot tell "no run
    # has ever happened" from "every run is crashing" — it kicks a run on open,
    # the run dies, and the same empty state comes back with nothing said.
    run_error: str | None = None


class RunTriggerResponse(BaseModel):
    """The reply to a run-on-open ``POST /api/runs/{market}`` (spec §7.3).

    ``triggered`` is true when this call started a run, false when one was
    already in flight (run-on-open is single-flight — a second open joins the
    running run rather than duplicating it). ``running`` is the market's state
    after the call: true whenever a run is in flight, so the tab polls until it
    clears and then reloads the now-complete session.
    """

    market: str
    triggered: bool
    running: bool


class LeaderRow(BaseModel):
    """One leaderboard row: a name ranked on **pure return**, plus its furniture
    (spec §4.3 / §4.4 / ticket 06). ``breadth`` is the ``k/5`` badge (lookbacks
    currently led — a persistence count, *not* a quality score); ``is_new`` marks
    absence from this board last session; ``surge`` flags a 1w name up ≥30% over
    the week; ``adr`` is a column for the toggle, never the sort key, ``None`` when
    it cannot be computed.

    ``sector`` and ``dollar_volume`` are the two **phase-1** additions (spec §4.4):
    both cheap, since the read already loads exactly these names' bars for the ADR
    column and sector is a store lookup. Without them the phase-1 control bar would
    ship with two live controls and two dead ones. ``sector`` is ``None`` when the
    label was never fetched; ``dollar_volume`` is ``None`` when the name's bars
    could not supply it, the same guard the ADR column carries.

    ``tier`` and ``rs_pctile`` are **phase-2**, typed nullable and returning
    ``None`` until the cross-sectional tier banding lands in the run (spec §4.4).
    """

    symbol: str
    raw_return: float
    breadth: int
    is_new: bool
    surge: bool
    adr: float | None
    # Phase-1 (spec §4.4): the sector label and §4.1 median-20d liquidity.
    sector: str | None
    dollar_volume: float | None
    # Phase-2 (spec §4.4): the tier band (1%/2%/3%) and relative-strength
    # percentile, both nullable until the run computes the banding.
    tier: str | None = None
    rs_pctile: float | None = None


class Leader(BaseModel):
    """One market's leaderboard for a single lookback (spec §5.2 / §5.3).

    ``cutoffs`` is a per-lookback block that sits **beside** the rows — the
    cutoff-return summary at the tier-band boundaries — never repeated on every
    row (spec §4.4). Phase-2, so ``None`` until the banding lands.
    """

    lookback: str
    rows: list[LeaderRow]
    cutoffs: dict[str, float] | None = None


class LeadersResponse(BaseModel):
    """The five leaderboards for one market, off the nightly path (spec §5.2 /
    §5.3). Formerly ``/api/boards``; renamed because *Board* now names the
    composite home screen (spec §10.2).

    ``session`` is the as-of session the boards were ranked on — the latest
    published run — or ``None`` when no run has published yet, which the tab shows
    as an explicit empty state.
    """

    market: str
    session: date | None
    boards: list[Leader]


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
    # The taxonomy the sector/industry labels came from — always ``"GECS"``
    # (spec §2.6 / §4.5). Recorded even here, where the axis renders unchanged.
    taxonomy: Taxonomy = "GECS"
    sectors: list[SectorStrength]
    industries: list[IndustryStrength]


class SectorMember(BaseModel):
    """One name inside a sector's drill-down (spec §5.5).

    The member list behind a sector row: what the Sectors screen drills into. A
    member is a universe name carrying this sector's label that appears in the
    session's rank table, so every field is read off that table (§4.3) — nothing
    is recomputed here.

    Phase-1 fields, all per-lookback so the client's lookback switch re-renders
    without a refetch: ``returns`` (the raw per-lookback return), ``pctile_universe``
    (the percentile, **named for its population** — this repo ranks over the whole
    universe, applying no tradability filter, so the field must not borrow a name
    that means ``gated`` elsewhere), and ``top_decile`` (whether the name is in
    that lookback's top decile, ``percentile ≥ TOP_DECILE`` — the per-name decile
    badge, P1). A lookback the name is not ranked in (a recent listing) is simply
    absent from all three maps.

    Phase-2 fields, typed nullable and always ``None`` today:
    - ``pct_of_52w_high`` — no 52-week high is computed anywhere yet (§1.3).
    - ``verdict`` — the detector's grade, where **``None`` means *not evaluated***,
      a different fact from ``extended`` (spec §2.1): a pack contains names the
      detector never ran on.
    """

    symbol: str
    # lookback -> raw return; only the lookbacks the name is ranked in.
    returns: dict[str, float]
    # lookback -> percentile in [0, 1] over the *universe* population.
    pctile_universe: dict[str, float]
    # lookback -> whether the name is in that lookback's top decile.
    top_decile: dict[str, bool]
    # P2: distance below the 52-week high; ``None`` — not computed anywhere today.
    pct_of_52w_high: float | None
    # P2: detector verdict; ``None`` means *not evaluated*, not ``extended`` (§2.1).
    verdict: str | None


class SectorDetailResponse(BaseModel):
    """The member list behind one sector — the drill-down (spec §5.5 / §4.5).

    ``sector`` echoes the resolved label (the path segment is URL-encoded, GECS
    labels carrying spaces such as ``Consumer Cyclical``). ``members`` is sorted
    by symbol; it is empty when no run has published (``session`` is ``None``, the
    explicit empty state) or when a valid sector simply has no members tonight.
    ``taxonomy`` is always ``"GECS"`` (§2.6).
    """

    market: str
    session: date | None
    sector: str
    taxonomy: Taxonomy = "GECS"
    members: list[SectorMember]


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
    """One row of the candidate list — a detection made readable (spec §5.1 / §4.3).

    ``score`` is the star score (0–5) and the sort key of the list; ``breakdown``
    carries its eight-row rubric so the row (or the chart panel) can reconstruct
    the arithmetic (spec §4.7). ``dist_adr`` is the distance to the trigger in ADR
    (``(trigger − close) / adr_abs``); ``stopw_adr`` is the stop width in ADR
    (``(trigger − cluster_low) / adr_abs``, the watchlist stop of §4.6). The stop
    column **never filters** — instead the affordable sub-1×ADR minority is flagged
    (``affordable``), the inverse of marking the ~92% unaffordable majority.
    ``industry`` is the theme layer (``None`` if the label was never fetched);
    ``breadth`` is the ``k/5`` badge, a persistence count and **not** a quality
    score.

    The **chart-facts fold** (spec §4.3): so a Setups card can show trigger, stop
    and distance without a per-symbol chart fetch, the fields that lived only in
    the chart bundle now ride the row too — projected from the *same* detection,
    which is the single source both endpoints render from. ``trigger_price`` /
    ``stop_price`` are the **borrowed** names for the overlay's trigger (cluster
    high) and stop (cluster low) — v1 had no word for them; ``risk_adr`` is
    **refused** (that quantity is ``stopw_adr`` and keeps its name). ``sector`` is
    new on this row, which carried ``industry`` only; both are wanted.
    ``dollar_volume`` and ``sector`` are ``None`` when the bars/label could not
    supply them, and ``decile_ranks`` omits a lookback the name is not ranked in —
    mirroring the chart facts block exactly.

    ``new_tonight`` (P1) is true exactly for names absent from the previous
    session's detected rows — the row-level fact that replaces the reference's
    standalone new-ready panel. ``verdict`` (P2) is typed now and returned ``None``.
    ``breakdown`` is typed nullable because at P2 the list will carry non-``detected``
    rows whose star score is undefined; on a P1 detected row it is always the
    eight-row rubric.

    Nothing here marks a ``line_ok`` failure: the fit's quality is a **silent
    tiebreak** that orders the list but is never surfaced in the row (spec §4.7).
    """

    symbol: str
    score: float
    breakdown: list[ScoreRow] | None
    dist_adr: float
    stopw_adr: float
    affordable: bool
    industry: str | None
    breadth: int
    # -- the chart-facts fold (spec §4.3): the numbers a Setups card needs without
    # a per-symbol chart fetch, projected from the same detection row.
    trigger_price: float          # overlay.trigger — the breakout level (borrowed)
    stop_price: float             # overlay.stop — the cluster-low watchlist stop (borrowed)
    close: float
    sector: str | None            # GECS sector; ``None`` if never fetched (new on the row)
    adr: float
    # Median unadjusted close × volume over 20 traded bars (§4.1). ``None`` if the
    # name's bars could not supply it.
    dollar_volume: float | None
    # lookback -> percentile in [0, 1]; a lookback the name is not ranked in is absent.
    decile_ranks: dict[str, float]
    # Newly detected — absent from last session's ``detected`` rows (P1, §2.4).
    new_tonight: bool
    # Phase-2 detector verdict; typed now, returned ``None`` (§4.3).
    verdict: str | None = None


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


class SetupOverlay(BaseModel):
    """The setup drawn on top of the candles (spec §5.1 / §3.5 / ticket 41) — the
    chart as *evidence for the score*, not merely a price chart.

    - ``base_start`` / ``cluster_start`` are the first sessions of the base and of
      the tight trailing cluster inside it; the frontend shades each region from
      its start to the last candle (the base always ends today, §4.5).
    - ``trigger`` (cluster high) and ``stop`` (cluster low) are the two horizontal
      rules §7's affordability test is read off geometrically.
    - ``envelope`` is the fitted upper line drawn **as a line series** so candles
      pierce it in both directions — per §3.2 that is the correct picture and must
      not be "fixed" in rendering. Anchored at the cluster's max-high bar with the
      detection's non-positive slope, so it can never exceed the trigger.
    - ``score`` (0–5 stars) and ``breakdown`` (the eight §4.7 dimensions, each with
      its weight and hit) reconstruct the sort key arithmetically beside the chart.

    ``None`` for the whole overlay when the name has no detection tonight — there
    is no base to shade, no envelope to fit and no score to break down.
    """

    base_start: date
    cluster_start: date
    trigger: float
    stop: float
    envelope: list[MaPoint]
    score: float
    breakdown: list[ScoreRow]


class ChartResponse(BaseModel):
    """One symbol's evidence bundle — the chart panel in a single call (spec §5.1).

    Candles plus the daily MA set (SMA 10/20/50 and the 65 EMA, spec §2) as line
    series, the ``setup`` overlay (base/cluster shading, envelope, trigger/stop and
    the §4.7 breakdown) and the facts block. ``session`` is the as-of published
    session, or ``None`` when no run has published (an explicit empty state). The
    MA lines are computed over the full stored history and then sliced to the drawn
    window, so the first drawn point already carries a full window behind it.
    """

    market: str
    symbol: str
    session: date | None
    candles: list[Candle]
    sma10: list[MaPoint]
    sma20: list[MaPoint]
    sma50: list[MaPoint]
    ema65: list[MaPoint]
    setup: SetupOverlay | None
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
