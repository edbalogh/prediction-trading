# dashboard/api/routes/strategies.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request

from dashboard.api.config import STRATEGIES, ROOT_DIR
from dashboard.api.services import config_mgr

router = APIRouter()


@router.get("/strategies")
async def list_strategies(request: Request) -> list[dict]:
    poller = request.app.state.poller
    process_mgr = getattr(request.app.state, "process_mgr", None)
    result = []
    for name, cfg in STRATEGIES.items():
        snap = poller.get_snapshot(name) or {}
        mode = (process_mgr.get_mode(name) if process_mgr else None) or snap.get("mode", "paper")
        result.append({
            "name": name,
            "display_name": cfg["display_name"],
            "icon": cfg["icon"],
            "status": snap.get("status", "stopped"),
            "mode": mode,
            "equity": snap.get("equity"),
            "realized_pnl": snap.get("realized_pnl"),
            "unrealized_pnl": snap.get("unrealized_pnl"),
            "total_trades": snap.get("total_trades"),
            "win_rate": snap.get("win_rate"),
        })
    return result


@router.post("/strategies/{name}/start")
async def start_strategy(
    name: str,
    request: Request,
    mode: str = Query("paper", pattern="^(paper|live)$"),
) -> dict:
    if name not in STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {name}")

    cfg = STRATEGIES[name]
    process_mgr = request.app.state.process_mgr

    if process_mgr.is_running(name):
        raise HTTPException(status_code=409, detail=f"{name} is already running")

    script_key = "paper_script" if mode == "paper" else "live_script"
    script = cfg.get(script_key)
    if not script:
        raise HTTPException(status_code=400, detail=f"No {mode} script configured for {name}")

    await process_mgr.start(name, mode, Path(script), ROOT_DIR)
    request.app.state.poller.set_mode(name, mode)

    return {"status": "started", "strategy": name, "mode": mode}


@router.post("/strategies/{name}/stop")
async def stop_strategy(name: str, request: Request) -> dict:
    if name not in STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {name}")

    process_mgr = request.app.state.process_mgr

    if not process_mgr.is_running(name):
        raise HTTPException(status_code=409, detail=f"{name} is not running")

    await process_mgr.stop(name)
    request.app.state.poller.clear_mode(name)

    return {"status": "stopped", "strategy": name}


@router.get("/strategies/{name}/config")
async def get_config(name: str) -> dict:
    if name not in STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {name}")

    cfg = STRATEGIES[name]
    schema = cfg.get("config_schema", [])
    config_path = str(ROOT_DIR / cfg["config_path"])
    values = config_mgr.read_config(config_path, schema)

    return {"strategy": name, "schema": schema, "values": values}


@router.put("/strategies/{name}/config")
async def put_config(name: str, body: dict = Body(...)) -> dict:
    if name not in STRATEGIES:
        raise HTTPException(status_code=404, detail=f"Unknown strategy: {name}")

    cfg = STRATEGIES[name]
    schema = cfg.get("config_schema", [])
    errors = config_mgr.validate_config(body, schema)
    if errors:
        raise HTTPException(status_code=422, detail={"errors": errors})

    config_path = str(ROOT_DIR / cfg["config_path"])
    config_mgr.write_config(config_path, body)

    return {"status": "saved", "strategy": name}
