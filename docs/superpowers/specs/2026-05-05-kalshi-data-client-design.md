# KalshiDataClient Implementation Design

**Date:** 2026-05-05
**Status:** Approved
**Scope:** WebSocket market data streaming for NautilusTrader live/paper trading modes

---

## 1. Goals

Implement `KalshiDataClient` — the NautilusTrader `LiveDataClient` subclass that streams live order book and trade data from Kalshi's WebSocket API. This unblocks paper and live trading modes; backtest mode is unaffected (it reads from the Parquet catalog).

---

## 2. Repository Changes

| File | Action | Responsibility |
|------|--------|----------------|
| `adapters/kalshi/ws.py` | Create | `KalshiWsConnection` — raw WebSocket lifecycle, reconnect, subscription management |
| `adapters/kalshi/data.py` | Create | `KalshiDataClient(LiveDataClient)` — NautilusTrader interface, owns the connection |
| `adapters/kalshi/factories.py` | Modify | Add `ws_delta_to_order_book_deltas`, `ws_trade_to_trade_tick` |
| `adapters/kalshi/__init__.py` | Modify | Export `KalshiDataClient` |
| `tests/adapters/kalshi/test_ws.py` | Create | Connection tests using in-process WebSocket server |
| `tests/adapters/kalshi/test_data.py` | Create | Data client tests with stubbed connection |
| `tests/adapters/kalshi/test_factories.py` | Create | Unit tests for new factory functions |

---

## 3. Kalshi WebSocket API (v2)

**URL:** derived from HTTP base URL via `http_client.websocket_url()` → `wss://trading-api.kalshi.com/trade-api/ws/v2`

**Auth:** RSA-signed headers via `http_client.websocket_headers()` — sent at connection time, not per-message.

### 3.1 Subscribe / Unsubscribe Commands

```json
{"id": 1, "cmd": "subscribe",   "params": {"channels": ["orderbook_delta"], "market_tickers": ["KXBTC15M-X"]}}
{"id": 2, "cmd": "unsubscribe", "params": {"channels": ["orderbook_delta"], "market_tickers": ["KXBTC15M-X"]}}
```

### 3.2 Inbound Message Types

**`orderbook_snapshot`** — sent immediately after subscribing to `orderbook_delta`. Full book state.
```json
{
  "type": "orderbook_snapshot",
  "msg": {
    "market_ticker": "KXBTC15M-X",
    "yes": [[55, 100], [54, 200]],
    "no":  [[45, 50]]
  }
}
```
`yes` entries are `[price_cents, size]` for BUY side. `no` entries are `[no_price_cents, size]`; YES-equivalent price = `100 - no_price_cents`.

**`orderbook_delta`** — incremental update. Same structure as snapshot but sparse: only changed levels included. `size = 0` means remove the level.
```json
{
  "type": "orderbook_delta",
  "msg": {
    "market_ticker": "KXBTC15M-X",
    "yes": [[55, 150]],
    "no":  [[45, 0]]
  }
}
```

**`trade`** — public trade. Uses `ts` (Unix milliseconds) not `created_time`.
```json
{
  "type": "trade",
  "msg": {
    "market_ticker": "KXBTC15M-X",
    "yes_price": 55,
    "no_price":  45,
    "count": 10,
    "taker_side": "yes",
    "ts": 1746400000000
  }
}
```

---

## 4. `KalshiWsConnection` (`adapters/kalshi/ws.py`)

Handles raw WebSocket only. No NautilusTrader types anywhere in this class.

### 4.1 Interface

```python
class KalshiWsConnection:
    def __init__(
        self,
        *,
        http_client: KalshiHttpClient,
        reconnect_delay: float = 1.0,
        reconnect_max_delay: float = 30.0,
    ) -> None: ...

    # Lifecycle
    async def connect(self) -> None
    async def disconnect(self) -> None

    # Subscriptions
    async def subscribe(self, tickers: list[str], channels: list[str]) -> None
    async def unsubscribe(self, tickers: list[str], channels: list[str]) -> None

    # Callbacks — set by KalshiDataClient before calling connect()
    on_snapshot: Callable[[dict], None] | None
    on_delta: Callable[[dict], None] | None
    on_trade: Callable[[dict], None] | None
```

### 4.2 Subscription Tracking

Active subscriptions stored as `_subscriptions: dict[str, set[str]]` mapping channel → set of tickers. Updated on every `subscribe`/`unsubscribe` call. Used to re-issue all subscriptions on reconnect.

### 4.3 Receive Loop

`connect()` starts `_recv_loop()` as an asyncio task. The loop:

1. Receives raw JSON from the socket
2. Parses `msg["type"]`
3. Dispatches to `on_snapshot`, `on_delta`, or `on_trade` callback (ignores unknown types)
4. On `ConnectionClosed` or any WebSocket exception: enters reconnect sequence

### 4.4 Reconnect Sequence

On connection loss:

1. Wait `current_delay` seconds (starts at `reconnect_delay`, doubles each attempt, capped at `reconnect_max_delay`)
2. Re-open socket with fresh auth headers (headers must be regenerated — they contain a timestamp)
3. Re-issue all entries in `_subscriptions`
4. Reset `current_delay` to `reconnect_delay` on successful reconnect

`disconnect()` sets a stop flag before cancelling the task so the reconnect loop does not fire on intentional shutdown.

---

## 5. `KalshiDataClient` (`adapters/kalshi/data.py`)

Inherits `LiveDataClient`. Owns one `KalshiWsConnection`.

### 5.1 Constructor

```python
class KalshiDataClient(LiveDataClient):
    def __init__(
        self,
        *,
        http_client: KalshiHttpClient,
        config: KalshiDataClientConfig,
        **kwargs,
    ) -> None: ...
```

Creates `KalshiWsConnection` from `http_client` and config reconnect parameters. Wires `on_snapshot`, `on_delta`, `on_trade` to internal handlers before `connect()` is called.

### 5.2 Lifecycle

```python
async def _connect(self) -> None:
    # Wire callbacks, then start WebSocket
    self._ws.on_snapshot = self._on_ws_snapshot
    self._ws.on_delta    = self._on_ws_delta
    self._ws.on_trade    = self._on_ws_trade
    await self._ws.connect()

async def _disconnect(self) -> None:
    await self._ws.disconnect()
```

### 5.3 Subscription Methods

NautilusTrader's subscription methods are synchronous. Async work (REST fetch, WS subscribe) is scheduled via `self.create_task(coro)` — NautilusTrader's helper for dispatching coroutines from sync callbacks.

**`subscribe_order_book_deltas(instrument_id, book_type, depth, kwargs)`:**
1. Extract `ticker = instrument_id.symbol.value`
2. Schedule async task that:
   a. Fetches REST snapshot: `http_client.get_orderbook(ticker)`
   b. Converts via `orderbook_snapshot_to_deltas(...)` and emits each delta via `self._handle_data(delta)`
   c. Subscribes WebSocket: `await self._ws.subscribe([ticker], ["orderbook_delta"])`

**`subscribe_trade_ticks(instrument_id, kwargs)`:**
1. Extract ticker
2. Schedule async task: `await self._ws.subscribe([ticker], ["trade"])`

**`unsubscribe_order_book_deltas(instrument_id, kwargs)`** and **`unsubscribe_trade_ticks(instrument_id, kwargs)`:**
- Schedule async task: `await self._ws.unsubscribe([ticker], [channel])`

### 5.4 Callback Handlers

**`_on_ws_snapshot(msg)`:** convert via `orderbook_snapshot_to_deltas`, emit each `OrderBookDelta` via `self._handle_data`.

**`_on_ws_delta(msg)`:** convert via `ws_delta_to_order_book_deltas`, emit each `OrderBookDelta`.

**`_on_ws_trade(msg)`:** convert via `ws_trade_to_trade_tick`, emit `TradeTick` via `self._handle_data`.

All handlers guard against unknown tickers (instrument not subscribed) by checking against a tracked set and logging a warning if the ticker is unexpected.

### 5.5 Missed Data on Reconnect

The connection layer re-subscribes automatically on reconnect, which triggers a fresh `orderbook_snapshot` from Kalshi. `_on_ws_snapshot` handles this identically to the initial snapshot — the book is re-seeded from the new snapshot. Missed fills during the gap are handled by the reconciliation gate (existing), not replayed here.

---

## 6. New Factory Functions (`adapters/kalshi/factories.py`)

### 6.1 `ws_delta_to_order_book_deltas`

```python
def ws_delta_to_order_book_deltas(
    msg: dict,
    *,
    instrument_id: InstrumentId,
    ts_event: int,
    ts_init: int,
) -> list[OrderBookDelta]: ...
```

Processes `msg["yes"]` and `msg["no"]` arrays. Each entry is `[price_cents, new_total_size]`:
- `size > 0` → `BookAction.UPDATE`
- `size == 0` → `BookAction.DELETE`

NO side: `yes_price_cents = 100 - no_price_cents`, `OrderSide.SELL`.

### 6.2 `ws_trade_to_trade_tick`

```python
def ws_trade_to_trade_tick(
    msg: dict,
    *,
    instrument_id: InstrumentId,
    ts_init: int,
) -> TradeTick: ...
```

- Price: `msg["yes_price"] / 100` (or `(100 - msg["no_price"]) / 100` as fallback)
- Size: `msg["count"]` (integer — WebSocket trade counts are whole contracts)
- `ts_event`: `msg["ts"] * 1_000_000` (milliseconds → nanoseconds)
- Aggressor: `taker_side="yes"` → `AggressorSide.BUYER`, `"no"` → `AggressorSide.SELLER`
- `trade_id`: `msg.get("trade_id", f"{msg['market_ticker']}-{msg['ts']}")` — fallback if no ID provided

---

## 7. Testing

### 7.1 `tests/adapters/kalshi/test_ws.py`

Uses an in-process WebSocket server (`websockets.serve`) to avoid mocking the socket itself. Tests:

- `test_connect_sends_no_subscribe_on_empty` — connect with no subscriptions, verify no subscribe command sent
- `test_subscribe_sends_correct_command` — subscribe, capture JSON sent by client, assert shape
- `test_on_snapshot_callback_fires` — server sends snapshot message, assert `on_snapshot` called with correct payload
- `test_on_delta_callback_fires` — server sends delta message, assert `on_delta` called
- `test_on_trade_callback_fires` — server sends trade message, assert `on_trade` called
- `test_reconnect_resubscribes` — server closes connection, verify client reconnects and re-issues prior subscriptions

### 7.2 `tests/adapters/kalshi/test_data.py`

Uses a duck-typed `FakeWsConnection` stub — no real socket. Tests:

- `test_subscribe_order_book_deltas_fetches_snapshot` — verify REST `get_orderbook` called and deltas emitted before WS subscribe
- `test_subscribe_trade_ticks_subscribes_trade_channel` — verify WS `subscribe` called with `["trade"]`
- `test_on_ws_snapshot_emits_order_book_deltas` — fire `on_snapshot` callback, assert `_handle_data` called with `OrderBookDelta` list
- `test_on_ws_delta_emits_update` — fire delta with size > 0, assert `BookAction.UPDATE`
- `test_on_ws_delta_emits_delete` — fire delta with size = 0, assert `BookAction.DELETE`
- `test_on_ws_trade_emits_trade_tick` — fire trade callback, assert `TradeTick` with correct price/size/aggressor

### 7.3 `tests/adapters/kalshi/test_factories.py` (additions)

Pure unit tests, no I/O:

- `test_ws_delta_to_order_book_deltas_update` — non-zero size → UPDATE action
- `test_ws_delta_to_order_book_deltas_delete` — zero size → DELETE action
- `test_ws_delta_no_side_price_conversion` — NO price correctly converted to YES-equivalent
- `test_ws_trade_yes_taker_is_buyer` — `taker_side="yes"` → `AggressorSide.BUYER`
- `test_ws_trade_no_taker_is_seller` — `taker_side="no"` → `AggressorSide.SELLER`
- `test_ws_trade_ts_milliseconds_to_nanoseconds` — `ts=1746400000000` → correct ns value

---

## 8. Out of Scope

- `subscribe_bars` / `subscribe_ticker` — not needed for Phase 1 strategies
- Quote-level data (bid/ask from ticker channel) — order book covers this
- WebSocket authentication refresh — Kalshi auth headers are per-connection; reconnect generates fresh headers automatically
