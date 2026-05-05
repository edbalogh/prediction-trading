from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

import websockets

_logger = logging.getLogger(__name__)


class KalshiWsConnection:
    def __init__(
        self,
        *,
        http_client,
        reconnect_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
    ) -> None:
        self._http = http_client
        self._reconnect_delay = reconnect_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._subscriptions: dict[str, set[str]] = {}
        self._ws = None
        self._recv_task: asyncio.Task | None = None
        self._stop = False
        self._cmd_id = 0

        self.on_snapshot: Callable[[dict], None] | None = None
        self.on_delta: Callable[[dict], None] | None = None
        self.on_trade: Callable[[dict], None] | None = None

    async def connect(self) -> None:
        self._stop = False
        self._ws = await websockets.connect(
            self._http.websocket_url(),
            additional_headers=self._http.websocket_headers(),
        )
        await self._replay_subscriptions()
        self._recv_task = asyncio.create_task(self._recv_loop())

    async def disconnect(self) -> None:
        self._stop = True
        if self._recv_task is not None:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
            self._recv_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def subscribe(self, tickers: list[str], channels: list[str]) -> None:
        for channel in channels:
            self._subscriptions.setdefault(channel, set()).update(tickers)
        if self._ws is not None:
            await self._send_cmd("subscribe", tickers=tickers, channels=channels)

    async def unsubscribe(self, tickers: list[str], channels: list[str]) -> None:
        for channel in channels:
            if channel in self._subscriptions:
                self._subscriptions[channel].difference_update(tickers)
        if self._ws is not None:
            await self._send_cmd("unsubscribe", tickers=tickers, channels=channels)

    async def _send_cmd(self, cmd: str, *, tickers: list[str], channels: list[str]) -> None:
        self._cmd_id += 1
        await self._ws.send(json.dumps({
            "id": self._cmd_id,
            "cmd": cmd,
            "params": {"channels": channels, "market_tickers": tickers},
        }))

    async def _replay_subscriptions(self) -> None:
        for channel, tickers in self._subscriptions.items():
            if tickers:
                await self._send_cmd("subscribe", tickers=list(tickers), channels=[channel])

    async def _recv_loop(self) -> None:
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                msg_type = msg.get("type")
                payload = msg.get("msg", {})
                if msg_type == "orderbook_snapshot" and self.on_snapshot:
                    self.on_snapshot(payload)
                elif msg_type == "orderbook_delta" and self.on_delta:
                    self.on_delta(payload)
                elif msg_type == "trade" and self.on_trade:
                    self.on_trade(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("_recv_loop exited with exception", exc_info=True)
