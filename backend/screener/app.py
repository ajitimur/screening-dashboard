"""The FastAPI app: resource endpoints, and it serves the built frontend.

One process on one local URL (spec §7.5). The skeleton exposes only the run
records; §7.5's other resource endpoints (regime, candidates, sectors, boards,
chart) land in later tickets against the same store.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from . import MARKETS
from .boards import board_symbols, build_boards
from .candidates import build_candidates
from .indicators import adr
from .models import (
    Board,
    BoardRow,
    BoardsResponse,
    CandidatesResponse,
    RegimeResponse,
    RunsResponse,
    SectorsResponse,
)
from .regime import breadth, posture, regime_state
from .sectors import (
    TEMPORAL_SESSIONS,
    industry_strengths,
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


def create_app(store: Store | None = None) -> FastAPI:
    """Build the app. Pass a ``store`` (e.g. a fixture) or let it open the file."""
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
        return RunsResponse(
            market=market,
            latest=latest,
            runs=store.runs(market),
            universe_size=len(store.universe(market, latest.session)) if latest else None,
        )

    @app.get("/api/boards/{market}", response_model=BoardsResponse)
    def get_boards(market: str) -> BoardsResponse:
        market = market.upper()
        if market not in MARKETS:
            raise HTTPException(status_code=404, detail=f"unknown market {market!r}")
        latest = store.latest_run(market)
        if latest is None:
            # No published run yet — an explicit empty state, not a fabricated date.
            return BoardsResponse(market=market, session=None, boards=[])
        session = latest.session
        rows = store.ranks(market, session)
        prev = store.ranks_before(market, session)
        # ADR is a column that rides each row for the toggle (§4.4); read bars only
        # for the names that land on some board, not the whole universe.
        adrs = {s: adr(store.bars(market, s)) for s in board_symbols(rows)}
        boards = [
            Board(
                lookback=b.lookback,
                rows=[BoardRow(**vars(r)) for r in b.rows],
            )
            for b in build_boards(rows, prev, adrs)
        ]
        return BoardsResponse(market=market, session=session, boards=boards)

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
        candidates = build_candidates(
            store.detections(market, session),
            store.ranks(market, session),
            industry_of,
            sector_of,
        )
        # Sorted by star score descending, line_ok failures a silent tiebreak
        # below equal-scored accepted names (spec §4.7); the UI reads ordered_by.
        return CandidatesResponse(
            market=market, session=session, ordered_by="score", candidates=candidates
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


app = create_app()
