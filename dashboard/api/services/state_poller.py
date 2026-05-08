from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

_logger = logging.getLogger(__name__)

# Max equity history points kept in memory per strategy (~24h at 1s poll = 86400 pts)
_MAX_HISTORY = 86_400


def normalize_state(
    strategy: str,
    mode: str,
    raw: dict[str, Any],
    equity_history: list[dict],
) -> dict[str, Any]:
    """Convert a raw /state response into a normalized StrategySnapshot."""
    fills: list[dict] = raw.get("fills", [])

    # Win rate from settlement fills only
    settlements = [f for f in fills if f.get("type") == "settlement" and "pnl" in f]
    if settlements:
        wins = sum(1 for f in settlements if f["pnl"] > 0)
        win_rate: float | None = wins / len(settlements)
    else:
        win_rate = None

    # Positions: dict → list, sorted by ticker
    raw_positions: dict = raw.get("positions", {})
    positions = [
        {
            "ticker": ticker,
            "qty": info["qty"],
            "avg_px": info["avg_px"],
            "last_px": info.get("last_px", info["avg_px"]),
            "unrealized_pnl": info.get("unrealized_pnl", 0.0),
        }
        for ticker, info in sorted(raw_positions.items())
    ]

    # Equity history: append current point, cap length
    ts = raw.get("ts", int(time.time()))
    equity = raw.get("equity", raw.get("starting_capital", 10_000.0))
    new_history = list(equity_history)
    # Avoid duplicate timestamps
    if not new_history or new_history[-1]["ts"] != ts:
        new_history.append({"ts": ts, "equity": equity})
    if len(new_history) > _MAX_HISTORY:
        new_history = new_history[-_MAX_HISTORY:]

    # Fills: most recent first
    recent_fills = list(reversed(fills))

    return {
        "strategy": strategy,
        "mode": mode,
        "status": "running",
        "ts": ts,
        "equity": equity,
        "starting_capital": raw.get("starting_capital", 10_000.0),
        "realized_pnl": raw.get("realized_pnl", 0.0),
        "unrealized_pnl": raw.get("unrealized_pnl", 0.0),
        "total_trades": len(fills),
        "win_rate": win_rate,
        "positions": positions,
        "recent_fills": recent_fills,
        "equity_history": new_history,
    }


def _stopped_snapshot(strategy: str, mode: str) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "mode": mode,
        "status": "stopped",
        "ts": int(time.time()),
        "equity": None,
        "starting_capital": None,
        "realized_pnl": None,
        "unrealized_pnl": None,
        "total_trades": None,
        "win_rate": None,
        "positions": [],
        "recent_fills": [],
        "equity_history": [],
    }


def _error_snapshot(strategy: str, mode: str) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "mode": mode,
        "status": "error",
        "ts": int(time.time()),
        "equity": None,
        "starting_capital": None,
        "realized_pnl": None,
        "unrealized_pnl": None,
        "total_trades": None,
        "win_rate": None,
        "positions": [],
        "recent_fills": [],
        "equity_history": [],
    }


class StatePoller:
    """
    Polls each registered strategy's /state HTTP endpoint.
    Maintains a normalized snapshot and equity history per strategy.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, dict] = {}
        self._equity_history: dict[str, list[dict]] = {}
        self._client = httpx.AsyncClient(timeout=2.0)
        self._task: asyncio.Task | None = None

    async def poll_once(self, strategy: str, port: int, mode: str = "paper") -> None:
        """Fetch /state for one strategy and update the snapshot cache."""
        url = f"http://localhost:{port}/state"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            raw = response.json()
            history = self._equity_history.get(strategy, [])
            snap = normalize_state(strategy, mode, raw, history)
            self._equity_history[strategy] = snap["equity_history"]
            self._snapshots[strategy] = snap
        except (httpx.ConnectError, httpx.TimeoutException):
            self._snapshots[strategy] = _stopped_snapshot(strategy, mode)
        except httpx.HTTPStatusError:
            self._snapshots[strategy] = _error_snapshot(strategy, mode)

    def get_snapshot(self, strategy: str) -> dict | None:
        return self._snapshots.get(strategy)

    def all_snapshots(self) -> list[dict]:
        return list(self._snapshots.values())

    async def start(self, strategies: dict[str, dict], poll_interval: float = 1.0) -> None:
        """Start background polling loop for all registered strategies."""
        async def _loop() -> None:
            while True:
                for name, cfg in strategies.items():
                    await self.poll_once(
                        name,
                        port=cfg["state_port"],
                        mode="paper",  # Stage 2 will detect live vs paper
                    )
                await asyncio.sleep(poll_interval)

        self._task = asyncio.create_task(_loop())
        _logger.info("StatePoller started for %d strategies", len(strategies))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
        _logger.info("StatePoller stopped")
