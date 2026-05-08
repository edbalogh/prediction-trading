from __future__ import annotations

from fastapi import APIRouter, Request

from dashboard.api.config import STRATEGIES

router = APIRouter()


@router.get("/strategies")
async def list_strategies(request: Request) -> list[dict]:
    poller = request.app.state.poller
    result = []
    for name, cfg in STRATEGIES.items():
        snap = poller.get_snapshot(name) or {}
        result.append({
            "name": name,
            "display_name": cfg["display_name"],
            "icon": cfg["icon"],
            "status": snap.get("status", "stopped"),
            "mode": snap.get("mode", "paper"),
            "equity": snap.get("equity"),
            "realized_pnl": snap.get("realized_pnl"),
            "unrealized_pnl": snap.get("unrealized_pnl"),
            "total_trades": snap.get("total_trades"),
            "win_rate": snap.get("win_rate"),
        })
    return result
