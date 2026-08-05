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
from .models import RegimeResponse, RunsResponse
from .regime import breadth, posture, regime_state
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
