# KalshiDataClient Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement WebSocket-based live market data streaming for Kalshi, enabling NautilusTrader paper and live trading modes with order book and trade tick feeds.

**Architecture:** `KalshiWsConnection` handles raw WebSocket lifecycle, reconnect, and subscription tracking with no NautilusTrader types. `KalshiDataClient(LiveDataClient)` owns the connection and translates messages to NautilusTrader `OrderBookDelta` and `TradeTick` objects using two new factory functions.

**Tech Stack:** Python asyncio, `websockets>=13` (already in dependencies), NautilusTrader `LiveDataClient`, `pytest-asyncio` (already configured with `asyncio_mode = "auto"`).

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `adapters/kalshi/factories.py` | Modify | Add `ws_delta_to_order_book_deltas`, `ws_trade_to_trade_tick` |
| `adapters/kalshi/ws.py` | Create | `KalshiWsConnection` — raw WebSocket lifecycle, reconnect, subscription management |
| `adapters/kalshi/data.py` | Create | `KalshiDataClient(LiveDataClient)` — owns connection, translates to NT types |
| `adapters/kalshi/__init__.py` | Modify | Export `KalshiDataClient` |
| `tests/adapters/kalshi/test_factories.py` | Modify | Append 6 unit tests for new factory functions |
| `tests/adapters/kalshi/test_ws.py` | Create | 6 in-process WebSocket server tests |
| `tests/adapters/kalshi/test_data.py` | Create | 6 unit tests using `FakeWsConnection` stub |

---

### Task 1: Factory functions for WebSocket messages

**Files:**
- Modify: `adapters/kalshi/factories.py`
- Modify: `tests/adapters/kalshi/test_factories.py`

- [ ] **Step 1: Append 6 failing tests to `tests/adapters/kalshi/test_factories.py`**

Append after the last existing test in the file:

```python
# ── WebSocket factory tests ───────────────────────────────────────────────────

from adapters.kalshi.factories import ws_delta_to_order_book_deltas, ws_trade_to_trade_tick
from nautilus_trader.model.enums import BookAction, OrderSide


def test_ws_delta_to_order_book_deltas_update():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 150]], "no": []}
    deltas = ws_delta_to_order_book_deltas(msg, instrument_id=instrument_id, ts_event=1000, ts_init=2000)
    assert len(deltas) == 1
    assert deltas[0].action == BookAction.UPDATE
    assert deltas[0].order.price.as_double() == pytest.approx(0.55)
    assert deltas[0].order.size.as_double() == 150.0
    assert deltas[0].order.side == OrderSide.BUY


def test_ws_delta_to_order_book_deltas_delete():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 0]], "no": []}
    deltas = ws_delta_to_order_book_deltas(msg, instrument_id=instrument_id, ts_event=1000, ts_init=2000)
    assert len(deltas) == 1
    assert deltas[0].action == BookAction.DELETE


def test_ws_delta_no_side_price_conversion():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    # no_price=45 → yes_equivalent=55 → 0.55
    msg = {"market_ticker": "KXBTC15M-X", "yes": [], "no": [[45, 100]]}
    deltas = ws_delta_to_order_book_deltas(msg, instrument_id=instrument_id, ts_event=0, ts_init=0)
    assert len(deltas) == 1
    assert deltas[0].order.price.as_double() == pytest.approx(0.55)
    assert deltas[0].order.side == OrderSide.SELL


def test_ws_trade_yes_taker_is_buyer():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 10,
        "taker_side": "yes",
        "ts": 1746400000000,
    }
    tick = ws_trade_to_trade_tick(msg, instrument_id=instrument_id, ts_init=9999)
    assert tick.aggressor_side == AggressorSide.BUYER
    assert tick.price.as_double() == pytest.approx(0.55)
    assert tick.size.as_double() == 10.0


def test_ws_trade_no_taker_is_seller():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 5,
        "taker_side": "no",
        "ts": 1746400000000,
    }
    tick = ws_trade_to_trade_tick(msg, instrument_id=instrument_id, ts_init=9999)
    assert tick.aggressor_side == AggressorSide.SELLER


def test_ws_trade_ts_milliseconds_to_nanoseconds():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 1,
        "taker_side": "yes",
        "ts": 1746400000000,
    }
    tick = ws_trade_to_trade_tick(msg, instrument_id=instrument_id, ts_init=0)
    assert tick.ts_event == 1746400000000 * 1_000_000
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/adapters/kalshi/test_factories.py -v -k "ws_delta or ws_trade"
```

Expected: 6 failures with `ImportError: cannot import name 'ws_delta_to_order_book_deltas'`

- [ ] **Step 3: Add the two factory functions to `adapters/kalshi/factories.py`**

Append after `fill_to_trade_tick`:

```python
def ws_delta_to_order_book_deltas(
    msg: dict,
    *,
    instrument_id: InstrumentId,
    ts_event: int,
    ts_init: int,
) -> list[OrderBookDelta]:
    deltas: list[OrderBookDelta] = []
    for price_cents, size in msg.get("yes", []):
        action = BookAction.UPDATE if size > 0 else BookAction.DELETE
        order = BookOrder(
            side=OrderSide.BUY,
            price=Price(round(price_cents / 100, PRICE_PRECISION), PRICE_PRECISION),
            size=Quantity(size, SIZE_PRECISION),
            order_id=0,
        )
        deltas.append(OrderBookDelta(
            instrument_id=instrument_id,
            action=action,
            order=order,
            flags=0,
            sequence=0,
            ts_event=ts_event,
            ts_init=ts_init,
        ))
    for price_cents, size in msg.get("no", []):
        yes_price_cents = 100 - price_cents
        action = BookAction.UPDATE if size > 0 else BookAction.DELETE
        order = BookOrder(
            side=OrderSide.SELL,
            price=Price(round(yes_price_cents / 100, PRICE_PRECISION), PRICE_PRECISION),
            size=Quantity(size, SIZE_PRECISION),
            order_id=0,
        )
        deltas.append(OrderBookDelta(
            instrument_id=instrument_id,
            action=action,
            order=order,
            flags=0,
            sequence=0,
            ts_event=ts_event,
            ts_init=ts_init,
        ))
    return deltas


def ws_trade_to_trade_tick(
    msg: dict,
    *,
    instrument_id: InstrumentId,
    ts_init: int,
) -> TradeTick:
    yes_price = msg.get("yes_price")
    price_cents = yes_price if yes_price is not None else (100 - msg["no_price"])
    aggressor = AggressorSide.BUYER if msg.get("taker_side", "yes") == "yes" else AggressorSide.SELLER
    trade_id = msg.get("trade_id") or f"{msg['market_ticker']}-{msg['ts']}"
    return TradeTick(
        instrument_id=instrument_id,
        price=Price(round(price_cents / 100, PRICE_PRECISION), PRICE_PRECISION),
        size=Quantity(msg["count"], SIZE_PRECISION),
        aggressor_side=aggressor,
        trade_id=TradeId(trade_id),
        ts_event=msg["ts"] * 1_000_000,
        ts_init=ts_init,
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/adapters/kalshi/test_factories.py -v
```

Expected: all tests pass (4 existing + 6 new = 10 total)

- [ ] **Step 5: Commit**

```bash
git add adapters/kalshi/factories.py tests/adapters/kalshi/test_factories.py
git commit -m "feat: add ws_delta_to_order_book_deltas and ws_trade_to_trade_tick factory functions"
```

---

### Task 2: KalshiWsConnection — core

**Files:**
- Create: `adapters/kalshi/ws.py`
- Create: `tests/adapters/kalshi/test_ws.py`

- [ ] **Step 1: Create `tests/adapters/kalshi/test_ws.py` with 5 failing tests**

```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/adapters/kalshi/test_ws.py -v
```

Expected: 5 failures with `ModuleNotFoundError: No module named 'adapters.kalshi.ws'`

- [ ] **Step 3: Create `adapters/kalshi/ws.py`**

```python
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
        if self._ws is not None:
            await self._ws.close()

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
            pass
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/adapters/kalshi/test_ws.py -v
```

Expected: 5 tests pass

- [ ] **Step 5: Commit**

```bash
git add adapters/kalshi/ws.py tests/adapters/kalshi/test_ws.py
git commit -m "feat: add KalshiWsConnection with basic connect/subscribe/recv dispatch"
```

---

### Task 3: KalshiWsConnection — reconnect

**Files:**
- Modify: `adapters/kalshi/ws.py`
- Modify: `tests/adapters/kalshi/test_ws.py`

- [ ] **Step 1: Append reconnect test to `tests/adapters/kalshi/test_ws.py`**

```python
async def test_reconnect_resubscribes():
    events: asyncio.Queue = asyncio.Queue()

    async def handler(ws):
        async for msg in ws:
            await events.put(json.loads(msg))
            # Exit after first subscribe command, causing server to close the connection
            break

    async with websockets.serve(handler, "localhost", 0) as server:
        port = server.sockets[0].getsockname()[1]
        conn = KalshiWsConnection(
            http_client=make_http_client(port),
            reconnect_delay=0.05,
        )
        conn.on_snapshot = lambda _: None  # silence callback
        await conn.connect()
        await conn.subscribe(["KXBTC15M-X"], ["orderbook_delta"])

        first = await asyncio.wait_for(events.get(), timeout=2.0)
        assert first["cmd"] == "subscribe"

        # Server closed connection after receiving the subscribe; wait for reconnect + re-subscribe
        second = await asyncio.wait_for(events.get(), timeout=3.0)
        assert second["cmd"] == "subscribe"
        assert "KXBTC15M-X" in second["params"]["market_tickers"]

        await conn.disconnect()
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/adapters/kalshi/test_ws.py::test_reconnect_resubscribes -v
```

Expected: FAIL — the reconnect never happens with the basic `_recv_loop`

- [ ] **Step 3: Replace `_recv_loop` in `adapters/kalshi/ws.py` with reconnect version**

Replace the existing `_recv_loop` method:

```python
    async def _recv_loop(self) -> None:
        delay = self._reconnect_delay
        while not self._stop:
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
                _logger.warning("WebSocket error, will reconnect", exc_info=True)

            if self._stop:
                break

            await asyncio.sleep(delay)
            delay = min(delay * 2, self._reconnect_max_delay)

            try:
                self._ws = await websockets.connect(
                    self._http.websocket_url(),
                    additional_headers=self._http.websocket_headers(),
                )
                await self._replay_subscriptions()
                delay = self._reconnect_delay
                _logger.info("WebSocket reconnected")
            except Exception:
                _logger.warning("Reconnect attempt failed, will retry in %.1fs", delay)
```

- [ ] **Step 4: Run all ws tests to confirm all 6 pass**

```bash
pytest tests/adapters/kalshi/test_ws.py -v
```

Expected: all 6 tests pass

- [ ] **Step 5: Commit**

```bash
git add adapters/kalshi/ws.py tests/adapters/kalshi/test_ws.py
git commit -m "feat: add exponential backoff reconnect with subscription replay to KalshiWsConnection"
```

---

### Task 4: KalshiDataClient

**Files:**
- Create: `adapters/kalshi/data.py`
- Create: `tests/adapters/kalshi/test_data.py`

- [ ] **Step 1: Create `tests/adapters/kalshi/test_data.py` with 6 failing tests**

The `FakeWsConnection` stub duck-types `KalshiWsConnection` — no real socket.

```python
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from nautilus_trader.model.data import OrderBookDelta, TradeTick
from nautilus_trader.model.enums import AggressorSide, BookAction
from nautilus_trader.model.identifiers import InstrumentId, Symbol

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.data import KalshiDataClient


class FakeWsConnection:
    def __init__(self) -> None:
        self.subscribe_calls: list[tuple] = []
        self.unsubscribe_calls: list[tuple] = []
        self.on_snapshot = None
        self.on_delta = None
        self.on_trade = None
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe(self, tickers: list[str], channels: list[str]) -> None:
        self.subscribe_calls.append((tickers, channels))

    async def unsubscribe(self, tickers: list[str], channels: list[str]) -> None:
        self.unsubscribe_calls.append((tickers, channels))


def make_client(fake_ws: FakeWsConnection, fake_http: MagicMock) -> tuple[KalshiDataClient, list]:
    client = object.__new__(KalshiDataClient)
    client._ws = fake_ws
    client._http = fake_http
    client._subscribed_instruments: set[InstrumentId] = set()
    handled: list = []
    client._handle_data = lambda d: handled.append(d)
    client._log = MagicMock()
    scheduled: list[asyncio.Task] = []
    client.create_task = lambda coro, **kw: scheduled.append(asyncio.ensure_future(coro)) or scheduled[-1]
    client._scheduled = scheduled
    return client, handled


def make_instrument_id(ticker: str = "KXBTC15M-X") -> InstrumentId:
    return InstrumentId(Symbol(ticker), KALSHI_VENUE)


async def test_subscribe_order_book_deltas_fetches_snapshot():
    fake_ws = FakeWsConnection()
    fake_http = MagicMock()
    fake_http.get_orderbook.return_value = {
        "orderbook": {"yes": [[55, 100]], "no": []}
    }
    client, handled = make_client(fake_ws, fake_http)

    instrument_id = make_instrument_id()
    client.subscribe_order_book_deltas(instrument_id=instrument_id, book_type=None, depth=0)

    await asyncio.gather(*client._scheduled)

    assert fake_http.get_orderbook.called_with("KXBTC15M-X")
    assert any(isinstance(d, OrderBookDelta) for d in handled)
    assert fake_ws.subscribe_calls == [(["KXBTC15M-X"], ["orderbook_delta"])]


async def test_subscribe_trade_ticks_subscribes_trade_channel():
    fake_ws = FakeWsConnection()
    fake_http = MagicMock()
    client, _ = make_client(fake_ws, fake_http)

    instrument_id = make_instrument_id()
    client.subscribe_trade_ticks(instrument_id=instrument_id)

    await asyncio.gather(*client._scheduled)

    assert fake_ws.subscribe_calls == [(["KXBTC15M-X"], ["trade"])]


async def test_on_ws_snapshot_emits_order_book_deltas():
    fake_ws = FakeWsConnection()
    client, handled = make_client(fake_ws, MagicMock())

    instrument_id = make_instrument_id()
    client._subscribed_instruments.add(instrument_id)

    snapshot_msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 100], [54, 200]], "no": [[45, 50]]}
    client._on_ws_snapshot(snapshot_msg)

    assert len(handled) == 3
    assert all(isinstance(d, OrderBookDelta) for d in handled)


async def test_on_ws_delta_emits_update():
    fake_ws = FakeWsConnection()
    client, handled = make_client(fake_ws, MagicMock())

    instrument_id = make_instrument_id()
    client._subscribed_instruments.add(instrument_id)

    delta_msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 150]], "no": []}
    client._on_ws_delta(delta_msg)

    assert len(handled) == 1
    assert handled[0].action == BookAction.UPDATE


async def test_on_ws_delta_emits_delete():
    fake_ws = FakeWsConnection()
    client, handled = make_client(fake_ws, MagicMock())

    instrument_id = make_instrument_id()
    client._subscribed_instruments.add(instrument_id)

    delta_msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 0]], "no": []}
    client._on_ws_delta(delta_msg)

    assert len(handled) == 1
    assert handled[0].action == BookAction.DELETE


async def test_on_ws_trade_emits_trade_tick():
    fake_ws = FakeWsConnection()
    client, handled = make_client(fake_ws, MagicMock())

    instrument_id = make_instrument_id()
    client._subscribed_instruments.add(instrument_id)

    trade_msg = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 10,
        "taker_side": "yes",
        "ts": 1746400000000,
    }
    client._on_ws_trade(trade_msg)

    assert len(handled) == 1
    tick = handled[0]
    assert isinstance(tick, TradeTick)
    assert tick.price.as_double() == pytest.approx(0.55)
    assert tick.size.as_double() == 10.0
    assert tick.aggressor_side == AggressorSide.BUYER
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/adapters/kalshi/test_data.py -v
```

Expected: 6 failures with `ModuleNotFoundError: No module named 'adapters.kalshi.data'`

- [ ] **Step 3: Create `adapters/kalshi/data.py`**

```python
from __future__ import annotations

import logging
import time

from nautilus_trader.live.data_client import LiveDataClient
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.identifiers import ClientId, InstrumentId

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.factories import (
    kalshi_ticker_to_instrument_id,
    orderbook_snapshot_to_deltas,
    ws_delta_to_order_book_deltas,
    ws_trade_to_trade_tick,
)
from adapters.kalshi.ws import KalshiWsConnection

_logger = logging.getLogger(__name__)


class KalshiDataClient(LiveDataClient):
    def __init__(
        self,
        *,
        http_client,
        config,
        **kwargs,
    ) -> None:
        super().__init__(
            client_id=ClientId("KALSHI"),
            venue=KALSHI_VENUE,
            **kwargs,
        )
        self._http = http_client
        self._ws = KalshiWsConnection(
            http_client=http_client,
            reconnect_delay=config.ws_reconnect_delay_secs,
            reconnect_max_delay=config.ws_reconnect_max_delay_secs,
        )
        self._subscribed_instruments: set[InstrumentId] = set()

    async def _connect(self) -> None:
        self._ws.on_snapshot = self._on_ws_snapshot
        self._ws.on_delta = self._on_ws_delta
        self._ws.on_trade = self._on_ws_trade
        await self._ws.connect()

    async def _disconnect(self) -> None:
        await self._ws.disconnect()

    def subscribe_order_book_deltas(self, instrument_id, book_type=None, depth=0, **kwargs) -> None:
        self._subscribed_instruments.add(instrument_id)
        ticker = instrument_id.symbol.value
        self.create_task(self._subscribe_orderbook_async(ticker, instrument_id))

    def unsubscribe_order_book_deltas(self, instrument_id, **kwargs) -> None:
        self._subscribed_instruments.discard(instrument_id)
        ticker = instrument_id.symbol.value
        self.create_task(self._ws.unsubscribe([ticker], ["orderbook_delta"]))

    def subscribe_trade_ticks(self, instrument_id, **kwargs) -> None:
        self._subscribed_instruments.add(instrument_id)
        ticker = instrument_id.symbol.value
        self.create_task(self._ws.subscribe([ticker], ["trade"]))

    def unsubscribe_trade_ticks(self, instrument_id, **kwargs) -> None:
        self._subscribed_instruments.discard(instrument_id)
        ticker = instrument_id.symbol.value
        self.create_task(self._ws.unsubscribe([ticker], ["trade"]))

    async def _subscribe_orderbook_async(self, ticker: str, instrument_id: InstrumentId) -> None:
        ts_now = time.time_ns()
        snapshot = self._http.get_orderbook(ticker)
        deltas = orderbook_snapshot_to_deltas(snapshot, instrument_id=instrument_id, ts_event=ts_now, ts_init=ts_now)
        for delta in deltas:
            self._handle_data(delta)
        await self._ws.subscribe([ticker], ["orderbook_delta"])

    def _on_ws_snapshot(self, msg: dict) -> None:
        instrument_id = kalshi_ticker_to_instrument_id(msg.get("market_ticker", ""))
        if instrument_id not in self._subscribed_instruments:
            _logger.warning("snapshot for unsubscribed ticker %s", msg.get("market_ticker"))
            return
        ts_now = time.time_ns()
        deltas = orderbook_snapshot_to_deltas(
            {"orderbook": msg},
            instrument_id=instrument_id,
            ts_event=ts_now,
            ts_init=ts_now,
        )
        for delta in deltas:
            self._handle_data(delta)

    def _on_ws_delta(self, msg: dict) -> None:
        instrument_id = kalshi_ticker_to_instrument_id(msg.get("market_ticker", ""))
        if instrument_id not in self._subscribed_instruments:
            _logger.warning("delta for unsubscribed ticker %s", msg.get("market_ticker"))
            return
        ts_now = time.time_ns()
        deltas = ws_delta_to_order_book_deltas(msg, instrument_id=instrument_id, ts_event=ts_now, ts_init=ts_now)
        for delta in deltas:
            self._handle_data(delta)

    def _on_ws_trade(self, msg: dict) -> None:
        instrument_id = kalshi_ticker_to_instrument_id(msg.get("market_ticker", ""))
        if instrument_id not in self._subscribed_instruments:
            _logger.warning("trade for unsubscribed ticker %s", msg.get("market_ticker"))
            return
        tick = ws_trade_to_trade_tick(msg, instrument_id=instrument_id, ts_init=time.time_ns())
        self._handle_data(tick)
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/adapters/kalshi/test_data.py -v
```

Expected: all 6 tests pass

- [ ] **Step 5: Run full test suite to confirm no regressions**

```bash
pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add adapters/kalshi/data.py tests/adapters/kalshi/test_data.py
git commit -m "feat: add KalshiDataClient with order book and trade tick subscriptions"
```

---

### Task 5: Exports and integration

**Files:**
- Modify: `adapters/kalshi/__init__.py`

- [ ] **Step 1: Add `KalshiDataClient` to `adapters/kalshi/__init__.py`**

Replace the file contents with:

```python
from adapters.kalshi.config import KalshiDataClientConfig, KalshiExecClientConfig
from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.data import KalshiDataClient
from adapters.kalshi.execution import KalshiExecutionClient
from adapters.kalshi.providers import KalshiInstrumentProvider

__all__ = [
    "KALSHI_VENUE",
    "KalshiDataClient",
    "KalshiDataClientConfig",
    "KalshiExecClientConfig",
    "KalshiExecutionClient",
    "KalshiInstrumentProvider",
]
```

- [ ] **Step 2: Verify the import works**

```bash
python -c "from adapters.kalshi import KalshiDataClient; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full test suite one final time**

```bash
pytest tests/ -v
```

Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add adapters/kalshi/__init__.py
git commit -m "feat: export KalshiDataClient from adapters.kalshi"
```

---

## Self-Review Checklist

**Spec coverage:**

| Spec Requirement | Task |
|-----------------|------|
| `ws_delta_to_order_book_deltas` factory | Task 1 |
| `ws_trade_to_trade_tick` factory | Task 1 |
| `KalshiWsConnection` with callbacks, subscribe/unsubscribe, `_subscriptions` tracking | Task 2 |
| Reconnect with exponential backoff, subscription replay | Task 3 |
| `KalshiDataClient._connect` / `_disconnect` | Task 4 |
| `subscribe_order_book_deltas` → REST snapshot + WS subscribe | Task 4 |
| `subscribe_trade_ticks` → WS subscribe | Task 4 |
| `unsubscribe_*` methods | Task 4 |
| `_on_ws_snapshot` / `_on_ws_delta` / `_on_ws_trade` handlers | Task 4 |
| Unknown-ticker guard with warning log | Task 4 |
| `KalshiDataClient` exported from `__init__` | Task 5 |
| `test_ws.py` in-process server tests (6) | Tasks 2–3 |
| `test_data.py` FakeWsConnection tests (6) | Task 4 |
| `test_factories.py` additions (6) | Task 1 |

All spec sections covered. No placeholders.
