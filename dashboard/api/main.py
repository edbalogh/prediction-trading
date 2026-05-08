from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from dashboard.api.config import STRATEGIES
from dashboard.api.routes.strategies import router as strategies_router
from dashboard.api.routes.ws import router as ws_router
from dashboard.api.services.state_poller import StatePoller

_logger = logging.getLogger(__name__)


def create_app(poller: StatePoller | None = None) -> FastAPI:
    """
    Factory used both by the production server and tests.
    Tests pass a mock poller; production creates a real one.
    """
    _poller = poller or StatePoller()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.poller = _poller
        if poller is None:
            # Only start polling when running for real (not in tests)
            await _poller.start(STRATEGIES)
        yield
        if poller is None:
            await _poller.stop()

    app = FastAPI(title="nautilus-plus dashboard", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # tightened in Stage 4 auth
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(strategies_router, prefix="/api")
    app.include_router(ws_router)

    # Serve built React app (built in Task 15; skip if not yet built)
    static_dir = Path(__file__).parent.parent / "ui" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
