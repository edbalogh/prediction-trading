# dashboard/api/routes/backtests.py
from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse

from dashboard.api.config import STRATEGIES, ROOT_DIR

router = APIRouter()


@router.post("/strategies/{name}/backtests")
async def start_backtest(name: str, request: Request, body: dict = Body(...)) -> dict:
    if name not in STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {name}")

    cfg = STRATEGIES[name]
    script = cfg.get("backtest_script")
    if not script:
        raise HTTPException(status_code=400, detail=f"No backtest_script configured for {name}")

    runner = request.app.state.backtest_runner
    if runner.is_running(name):
        raise HTTPException(status_code=409, detail=f"{name} backtest already running")

    start_date = body.get("start_date")
    end_date = body.get("end_date")
    if not start_date or not end_date:
        raise HTTPException(status_code=422, detail="start_date and end_date are required")

    params = {
        "start_date": start_date,
        "end_date": end_date,
        "overrides": body.get("overrides", {}),
    }
    run_id = await runner.start(name, Path(script), ROOT_DIR, params)
    return {"run_id": run_id, "status": "pending"}


@router.get("/strategies/{name}/backtests")
async def list_backtests(name: str, request: Request) -> list[dict]:
    if name not in STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {name}")
    return await request.app.state.backtest_runner.list_runs(name)


@router.get("/backtests/{run_id}")
async def get_backtest(run_id: str, request: Request) -> dict:
    run = await request.app.state.backtest_runner.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


@router.get("/backtests/{run_id}/export")
async def export_backtest(run_id: str, request: Request) -> StreamingResponse:
    run = await request.app.state.backtest_runner.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    if run["status"] != "done":
        raise HTTPException(status_code=409, detail="Run is not complete")

    trades = run.get("trades") or []
    output = io.StringIO()
    writer = csv.DictWriter(
        output, fieldnames=["ts", "ticker", "side", "qty", "price", "pnl"]
    )
    writer.writeheader()
    for trade in trades:
        writer.writerow({k: trade.get(k, "") for k in ["ts", "ticker", "side", "qty", "price", "pnl"]})
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=backtest_{run_id}.csv"},
    )
