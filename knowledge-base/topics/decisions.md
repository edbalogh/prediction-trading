# Key Decisions

### Always prepend BookAction.CLEAR to snapshot deltas

**Date:** 2026-05-05
**Context:** Reconnect after a WS disconnect would re-subscribe and receive a fresh `orderbook_snapshot`.

Without a CLEAR, the snapshot's ADD deltas stack on top of whatever stale levels remain in the NautilusTrader order book from before the disconnect. The book ends up with ghost levels at prices that no longer exist. `orderbook_snapshot_to_deltas` now always prepends `OrderBookDelta.clear(...)` as the first delta, which wipes the book before the new levels are applied. This makes reconnect semantically equivalent to a cold start.

---

### Synchronous HTTP inside async via asyncio.to_thread

**Date:** 2026-05-05
**Context:** `KalshiHttpClient` uses `httpx.Client` (sync); the orderbook snapshot fetch happens inside an async method.

Calling a sync HTTP client directly inside an async coroutine blocks the entire event loop. The fix is `await asyncio.to_thread(self._http.get_orderbook, ticker)`, which runs the sync call in a thread pool. The alternative — switching `KalshiHttpClient` to `httpx.AsyncClient` — was considered but deferred: it would require reworking the catalog ingestion path which also uses the client synchronously.

---

### NautilusTrader subscription methods are synchronous

**Date:** 2026-05-05
**Context:** `LiveDataClient.subscribe_order_book_deltas` is a synchronous callback.

NautilusTrader calls subscription methods synchronously from its message bus. Any async work (REST fetch, WS subscribe) must be dispatched via `self.create_task(coro)` — NT's helper for scheduling coroutines from sync context. Calling `asyncio.create_task()` directly also works but bypasses NT's task lifecycle management.

---

### KalshiDataClient.__new__() pattern for testing

**Date:** 2026-05-05
**Context:** NautilusTrader's `LiveDataClient` has a DI-heavy constructor that requires a full actor context.

`KalshiDataClient.__new__(KalshiDataClient)` bypasses the constructor, then manually injects `_ws`, `_http`, `_subscribed_instruments`, `_handle_data`, and `create_task`. This is the idiomatic NT test pattern for client classes. The alternative — building a full NT test environment — is heavyweight and not required for unit testing the adapter logic.

---

### WebSocket auth headers are per-connection, not per-message

**Date:** 2026-05-05
**Context:** Kalshi WebSocket API v2 uses RSA-signed headers for authentication.

Auth headers include a timestamp and must be regenerated on each connection. `KalshiWsConnection` calls `http_client.websocket_headers()` fresh on every `connect()` call (including reconnects). This is why the reconnect sequence generates new headers rather than caching them from the initial connection.
