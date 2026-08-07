"""The FastAPI app: resource endpoints, and it serves the built frontend.

One process on one local URL (spec §7.5). The skeleton exposes only the run
records; §7.5's other resource endpoints (regime, candidates, sectors, boards,
chart) land in later tickets against the same store.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles

from . import MARKETS
from .boards import board_symbols, build_boards
from .candidates import build_candidates
from .chart import build_chart
from .detection import detection_gate
from .indicators import adr, median_dollar_volume
from .models import (
    CandidatesResponse,
    ChartResponse,
    Leader,
    LeaderRow,
    LeadersResponse,
    RegimeResponse,
    RunsResponse,
    RunTriggerResponse,
    SectorDetailResponse,
    SectorsResponse,
)
from .regime import breadth, posture, regime_state
from .runner import RunManager
from .schedule import run_is_due
from .sectors import (
    SECTORS,
    TEMPORAL_SESSIONS,
    industry_strengths,
    leave_one_out_sector_shares,
    sector_members,
    sector_strengths,
)
from .source import MARKET_INDEX
from .store import Store

# Repo root, resolved from …/backend/screener/app.py — so the file path and the
# served frontend are the same regardless of the process's working directory.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist"

# The store the app reads. Overridable via env so a fixture path can be injected
# without a rewrite (Seam 2 constructs the app against an in-memory store).
DEFAULT_DB_PATH = os.environ.get("SCREENER_DB", str(_REPO_ROOT / "data" / "screener.duckdb"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_app(
    store: Store | None = None,
    *,
    run_manager: RunManager | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> FastAPI:
    """Build the app. Pass a ``store`` (e.g. a fixture) or let it open the file.

    ``run_manager`` drives run-on-open (spec §7.3): when present, opening a tab
    whose last final session is missing kicks a background run via
    ``POST /api/runs/{market}``. ``clock`` supplies ``now`` for the ``run_due``
    finality decision — injectable so a test can pin the wall clock.
    """
    owns_store = store is None
    store = store or Store.open(DEFAULT_DB_PATH)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if owns_store:
            store.close()

    app = FastAPI(
        title="Qullamaggie Screening Dashboard", version="1.0.0", lifespan=lifespan
    )
    app.state.store = store

    @app.get("/api/runs/{market}", response_model=RunsResponse)
    def get_runs(market: str) -> RunsResponse:
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        latest = store.latest_run(market)
        # Run-on-open (spec §7.3): the tab reads whether its last final session is
        # missing (``run_due``) and whether a run is already in flight
        # (``running``), so opening it kicks a run and shows a progress state
        # without ever serving a half-written session — the served ``latest`` is
        # the last *published* run throughout.
        return RunsResponse(
            market=market,
            latest=latest,
            runs=store.runs(market),
            universe_size=len(store.universe(market, latest.session)) if latest else None,
            run_due=run_is_due(latest.session if latest else None, market, clock()),
            running=run_manager.is_running(market) if run_manager else False,
            # A run that crashed clears ``running`` and publishes nothing, which
            # is indistinguishable from never having run at all. Surface the
            # coordinator's error so the tab says the run failed rather than
            # kicking another one into the same wall in silence.
            run_error=run_manager.error(market) if run_manager else None,
        )

    @app.post("/api/runs/{market}", response_model=RunTriggerResponse)
    def trigger_run(market: str) -> RunTriggerResponse:
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        if run_manager is None:
            # No coordinator wired (e.g. a read-only deployment without a source);
            # the tab falls back to showing the last published session unchanged.
            raise HTTPException(status_code=503, detail="run trigger not configured")
        # Single-flight: a second open mid-run joins the running run rather than
        # starting a duplicate (spec §7.3). The tab polls /api/runs until running
        # clears, then reloads the now-complete session.
        triggered = run_manager.trigger(market)
        return RunTriggerResponse(
            market=market, triggered=triggered, running=run_manager.is_running(market)
        )

    def _leaders(market: str) -> LeadersResponse:
        """The five leaderboards for one market — the body of ``/api/leaders`` and
        its ``/api/boards`` alias (spec §4.4 / §10.2)."""
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        latest = store.latest_run(market)
        if latest is None:
            # No published run yet — an explicit empty state, not a fabricated date.
            return LeadersResponse(market=market, session=None, boards=[])
        session = latest.session
        rows = store.ranks(market, session)
        prev = store.ranks_before(market, session)
        # ADR and dollar volume are columns that ride each row for the toggle /
        # phase-1 control bar (§4.4); read bars only once, for the names that land
        # on some board, not the whole universe.
        members = board_symbols(rows)
        bars = {s: store.bars(market, s) for s in members}
        adrs = {s: adr(bars[s]) for s in members}
        dollar_volumes = {s: median_dollar_volume(bars[s]) for s in members}
        # Sector is a store lookup off the label cache (§3.3 / §4.4); absent when
        # the label was never fetched, carried as ``None`` rather than fabricated.
        labels = store.labels(market)
        sectors = {s: (labels[s].sector if s in labels else None) for s in members}
        boards = [
            Leader(
                lookback=b.lookback,
                # tier / rs_pctile / cutoffs are phase-2 and default to null.
                rows=[LeaderRow(**vars(r)) for r in b.rows],
            )
            for b in build_boards(rows, prev, adrs, sectors, dollar_volumes)
        ]
        return LeadersResponse(market=market, session=session, boards=boards)

    @app.get("/api/leaders/{market}", response_model=LeadersResponse)
    def get_leaders(market: str) -> LeadersResponse:
        return _leaders(market)

    # ``/api/boards`` is kept as an alias so the whole backend lands on ``main``
    # ahead of any frontend work without breaking v1; it dies later, in the
    # integration commit (spec §10.2 constraint 1).
    @app.get("/api/boards/{market}", response_model=LeadersResponse)
    def get_boards(market: str) -> LeadersResponse:
        return _leaders(market)

    @app.get("/api/sectors/{market}", response_model=SectorsResponse)
    def get_sectors(market: str) -> SectorsResponse:
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        latest = store.latest_run(market)
        if latest is None:
            # No run has published: the 11-sector axis still renders, all at 0%
            # (spec §4.4 S8), and there is no industry board yet.
            return SectorsResponse(
                market=market,
                session=None,
                sectors=sector_strengths([], {}),
                industries=[],
            )
        rows = store.ranks(market, latest.session)
        labels = store.labels(market)
        sector_of = {sym: label.sector for sym, label in labels.items()}
        industry_of = {sym: label.industry for sym, label in labels.items()}
        # The temporal delta differences against the rank table TEMPORAL_SESSIONS
        # sessions back; absent (fewer sessions of history), the delta is None.
        history = store.rank_sessions(market)
        past_rows = None
        if latest.session in history:
            idx = history.index(latest.session)
            if idx >= TEMPORAL_SESSIONS:
                past_rows = store.ranks(market, history[idx - TEMPORAL_SESSIONS])
        return SectorsResponse(
            market=market,
            session=latest.session,
            sectors=sector_strengths(rows, sector_of, past_rows=past_rows),
            industries=industry_strengths(rows, industry_of, sector_of),
        )

    @app.get("/api/sectors/{market}/{sector}", response_model=SectorDetailResponse)
    def get_sector_detail(market: str, sector: str) -> SectorDetailResponse:
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        # ``sector`` arrives URL-decoded, so a GECS label with a space (e.g.
        # "Consumer Cyclical") resolves as itself. A label outside the 11-sector
        # axis is a clean 404 rather than a 200 that looks like an empty pack —
        # the drill-down only ever links from a real sector row (spec §5.5).
        if sector not in SECTORS:
            raise HTTPException(status_code=404, detail=f"unknown sector {sector!r}")
        latest = store.latest_run(market)
        if latest is None:
            # No run has published: the sector resolves but has no members yet —
            # an explicit empty state, not a fabricated date (spec §4.7).
            return SectorDetailResponse(
                market=market, session=None, sector=sector, members=[]
            )
        rows = store.ranks(market, latest.session)
        labels = store.labels(market)
        sector_of = {sym: label.sector for sym, label in labels.items()}
        return SectorDetailResponse(
            market=market,
            session=latest.session,
            sector=sector,
            members=sector_members(rows, sector_of, sector),
        )

    @app.get("/api/candidates/{market}", response_model=CandidatesResponse)
    def get_candidates(market: str) -> CandidatesResponse:
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        latest = store.latest_run(market)
        if latest is None:
            # No published run yet — an explicit empty state, not a fabricated
            # date. The order is by score, there is simply nothing to order.
            return CandidatesResponse(
                market=market, session=None, ordered_by="score", candidates=[]
            )
        session = latest.session
        # Compose the list from what the pipeline published for this session: the
        # detection rows (base + trigger + stop + the score's signal vector), the
        # rank table (the k/5 badge, the prior-move percentile) and the label cache
        # (the industry, and the sector for the score's leave-one-out share). The
        # regime never enters — the list is identical in all three states (§4.9).
        labels = store.labels(market)
        industry_of = {sym: label.industry for sym, label in labels.items()}
        sector_of = {sym: label.sector for sym, label in labels.items()}
        detections = store.detections(market, session)
        # The chart-facts fold (spec §4.3): dollar_volume is the one row fact not
        # carried on the detection row, so read each detected name's bars and
        # compute the §4.1 median-20d liquidity exactly as the chart does — scoped
        # to the published session so a newer quarantined pull never leaks in.
        dollar_volume_of = {
            det.symbol: median_dollar_volume(
                [b for b in store.bars(market, det.symbol) if b.session <= session]
            )
            for det in detections
        }
        # new_tonight: absence from the previous session's detected rows — the
        # per-session analogue of the board's per-lookback NEW diff (spec §4.3).
        prev_detected = {
            d.symbol for d in store.detections_before(market, session)
        }
        candidates = build_candidates(
            detections,
            store.ranks(market, session),
            industry_of,
            sector_of,
            dollar_volume_of=dollar_volume_of,
            prev_detected=prev_detected,
        )
        # Sorted by star score descending, line_ok failures a silent tiebreak
        # below equal-scored accepted names (spec §4.7); the UI reads ordered_by.
        return CandidatesResponse(
            market=market, session=session, ordered_by="score", candidates=candidates
        )

    @app.get("/api/chart/{market}/{symbol}", response_model=ChartResponse)
    def get_chart(
        market: str,
        symbol: str,
        bars_window: int | None = Query(default=None, alias="bars", ge=1),
    ) -> ChartResponse:
        # ``?bars=N`` draws only the last N bars — so a 60-bar thumbnail costs 60
        # bars, not a full stored history (spec §4.6). Omitting it keeps the full
        # default window; the truncation runs *after* the session filter below, so
        # a quarantined pull's bars can never survive into a windowed response.
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        bars = store.bars(market, symbol)
        if not bars:
            # A symbol the store has never seen — genuinely absent, not an empty
            # state. Click-a-row can only reach names that have bars, so this is
            # the hand-typed-URL case.
            raise HTTPException(
                status_code=404, detail=f"no bars for {symbol!r} in {market}"
            )
        # Compose the bundle from what the pipeline published for the as-of
        # session: the detection row (the facts' base/trigger/stop), the rank
        # rows (the decile ranks) and the label cache (the sector). The chart
        # re-computes nothing about detection or ranking (spec §5.1).
        latest = store.latest_run(market)
        session = latest.session if latest else None
        detection = None
        ranks_for_symbol: list = []
        sector = None
        prior_move = False
        sector_share = 0.0
        if latest is not None:
            # Scope to bars on or before the published session so a newer,
            # quarantined pull's bars never leak onto the chart (§4.9).
            bars = [b for b in bars if b.session <= session]
            session_ranks = store.ranks(market, session)
            detection = next(
                (d for d in store.detections(market, session) if d.symbol == symbol),
                None,
            )
            ranks_for_symbol = [r for r in session_ranks if r.symbol == symbol]
            label = store.label(market, symbol)
            sector = label.sector if label else None
            if detection is not None:
                # The setup overlay's breakdown needs the same two cross-sectional
                # inputs the candidate list scores with (candidates.build_candidates):
                # the prior-move decile gate and the leave-one-out 1m sector share,
                # both off this session's rank table and labels (spec §4.7). Only a
                # name with a base tonight is scored, so this is skipped otherwise.
                labels = store.labels(market)
                sector_of = {sym: label.sector for sym, label in labels.items()}
                prior_move = symbol in detection_gate(session_ranks)
                sector_share = leave_one_out_sector_shares(
                    session_ranks, sector_of
                ).get(symbol, 0.0)
        return build_chart(
            market, symbol, session, bars, detection, ranks_for_symbol, sector,
            prior_move=prior_move, sector_share=sector_share, window=bars_window,
        )

    @app.get("/api/regime/{market}", response_model=RegimeResponse)
    def get_regime(market: str) -> RegimeResponse:
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        latest = store.latest_run(market)
        if latest is None:
            # No published run yet — nothing to advise, and the banner stays off.
            return RegimeResponse(
                market=market, session=None, state=None, posture=None, breadth=None
            )
        as_of = latest.session
        # Evaluate on the last closed (published) session: filter to bars on or
        # before it, so a newer quarantined pull's bars never leak in (§4.9).
        index_bars = [
            b for b in store.bars(market, MARKET_INDEX[market]) if b.session <= as_of
        ]
        members = store.universe(market, as_of)
        members_bars = {
            s: [b for b in store.bars(market, s) if b.session <= as_of] for s in members
        }
        state = regime_state(index_bars)
        return RegimeResponse(
            market=market,
            session=as_of,
            state=state,
            posture=posture(state),
            breadth=breadth(members_bars),
        )

    # FastAPI serves the built frontend so it is one process on one URL. Mounted
    # last so it never shadows /api. Absent before the first `vite build`, so the
    # mount is conditional rather than a hard startup dependency.
    if _FRONTEND_DIST.is_dir():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")

    return app


def _default_run_manager() -> RunManager:
    """The production run-on-open coordinator (spec §7.3).

    Drives :func:`screener.run.run_live` off the request thread — the same live
    run the scheduled CLI performs, so a run-on-open and a scheduled run are
    byte-for-byte the same work. Each run owns its store connection, so the tab
    stays responsive and the write path never shares the app's read connection.
    """
    from .run import run_live

    return RunManager(run_live)


app = create_app(run_manager=_default_run_manager())
