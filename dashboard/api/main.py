# dashboard/api/main.py
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dashboard.api.config import STRATEGIES
from dashboard.api.db import database
from dashboard.api.routes.backtests import router as backtests_router
from dashboard.api.routes.strategies import router as strategies_router
from dashboard.api.routes.ws import router as ws_router, manager as ws_manager
from dashboard.api.services.backtest_runner import BacktestRunner
from dashboard.api.services.process_mgr import ProcessManager
from dashboard.api.services.state_poller import StatePoller

_logger = logging.getLogger(__name__)


def create_app(
    poller: StatePoller | None = None,
    process_mgr: ProcessManager | None = None,
    backtest_runner: BacktestRunner | None = None,
) -> FastAPI:
    _poller = poller or StatePoller()
    _process_mgr = process_mgr or ProcessManager()
    _backtest_runner = backtest_runner or BacktestRunner()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.poller = _poller
        app.state.process_mgr = _process_mgr
        app.state.backtest_runner = _backtest_runner
        database.init_db()

        push_task: asyncio.Task | None = None

        if poller is None:
            await _poller.start(STRATEGIES)

            async def _push_loop() -> None:
                _WS_HISTORY_LIMIT = 300
                while True:
                    snapshots = _poller.all_snapshots()
                    if snapshots:
                        trimmed = [
                            {**snap, "equity_history": snap["equity_history"][-_WS_HISTORY_LIMIT:]}
                            for snap in snapshots
                        ]
                        await ws_manager.broadcast({"snapshots": trimmed})
                    await asyncio.sleep(1.0)

            push_task = asyncio.create_task(_push_loop())

        yield

        if push_task:
            push_task.cancel()
            try:
                await push_task
            except asyncio.CancelledError:
                pass
        if poller is None:
            await _poller.stop()

    app = FastAPI(title="nautilus-plus dashboard", lifespan=lifespan)

    # Eager state init so TestClient works without lifespan context
    app.state.poller = _poller
    app.state.process_mgr = _process_mgr
    app.state.backtest_runner = _backtest_runner

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(strategies_router, prefix="/api")
    app.include_router(backtests_router, prefix="/api")
    app.include_router(ws_router)

    static_dir = Path(__file__).parent.parent / "ui" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
