from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest
import websockets

from adapters.kalshi.ws import KalshiWsConnection


def make_http_client(port: int) -> MagicMock:
    http_client = MagicMock()
    http_client.websocket_url.return_value = f"ws://localhost:{port}"
    http_client.websocket_headers.return_value = {}
    return http_client


async def test_connect_sends_no_subscribe_on_empty():
    sent: list[dict] = []

    async def handler(ws):
        async for msg in ws:
            sent.append(json.loads(msg))

    async with websockets.serve(handler, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        conn = KalshiWsConnection(http_client=make_http_client(port))
        await conn.connect()
        await asyncio.sleep(0.05)
        await conn.disconnect()

    assert sent == []


async def test_subscribe_sends_correct_command():
    received: list[dict] = []

    async def handler(ws):
        async for msg in ws:
            received.append(json.loads(msg))

    async with websockets.serve(handler, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        conn = KalshiWsConnection(http_client=make_http_client(port))
        await conn.connect()
        await conn.subscribe(["KXBTC15M-X"], ["orderbook_delta"])
        await asyncio.sleep(0.05)
        await conn.disconnect()

    assert len(received) == 1
    cmd = received[0]
    assert cmd["cmd"] == "subscribe"
    assert "KXBTC15M-X" in cmd["params"]["market_tickers"]
    assert "orderbook_delta" in cmd["params"]["channels"]


async def test_on_snapshot_callback_fires():
    snapshot_payload = {"market_ticker": "KXBTC15M-X", "yes": [[55, 100]], "no": []}

    async def handler(ws):
        await ws.send(json.dumps({"type": "orderbook_snapshot", "msg": snapshot_payload}))
        await ws.wait_closed()

    received: list[dict] = []

    async with websockets.serve(handler, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        conn = KalshiWsConnection(http_client=make_http_client(port))
        conn.on_snapshot = received.append
        await conn.connect()
        await asyncio.sleep(0.1)
        await conn.disconnect()

    assert len(received) == 1
    assert received[0] == snapshot_payload


async def test_on_delta_callback_fires():
    delta_payload = {"market_ticker": "KXBTC15M-X", "yes": [[55, 150]], "no": []}

    async def handler(ws):
        await ws.send(json.dumps({"type": "orderbook_delta", "msg": delta_payload}))
        await ws.wait_closed()

    received: list[dict] = []

    async with websockets.serve(handler, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        conn = KalshiWsConnection(http_client=make_http_client(port))
        conn.on_delta = received.append
        await conn.connect()
        await asyncio.sleep(0.1)
        await conn.disconnect()

    assert len(received) == 1
    assert received[0] == delta_payload


async def test_on_trade_callback_fires():
    trade_payload = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 10,
        "taker_side": "yes",
        "ts": 1746400000000,
    }

    async def handler(ws):
        await ws.send(json.dumps({"type": "trade", "msg": trade_payload}))
        await ws.wait_closed()

    received: list[dict] = []

    async with websockets.serve(handler, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        conn = KalshiWsConnection(http_client=make_http_client(port))
        conn.on_trade = received.append
        await conn.connect()
        await asyncio.sleep(0.1)
        await conn.disconnect()

    assert len(received) == 1
    assert received[0] == trade_payload
