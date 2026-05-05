# Architecture

## Component Overview

```
KalshiHttpClient          — synchronous REST client (httpx.Client)
KalshiWsConnection        — raw WebSocket lifecycle, no NautilusTrader types
KalshiDataClient          — LiveDataClient subclass, owns WsConnection, bridges to NautilusTrader
factories.py              — stateless conversion functions (Kalshi dicts → NautilusTrader objects)
```

## Layer Boundaries

**Date:** 2026-05-05
**Context:** Deciding how to split WebSocket responsibilities.

`KalshiWsConnection` deliberately holds no NautilusTrader types. It only manages the socket connection, subscription state, reconnect logic, and message dispatch. `KalshiDataClient` owns the connection and wires the three callbacks (`on_snapshot`, `on_delta`, `on_trade`). This split makes the WebSocket layer independently testable without the NautilusTrader component hierarchy.

## Order Book Model

**Date:** 2026-05-05
**Context:** Kalshi has YES and NO sides; NautilusTrader expects a single BUY/SELL order book.

The Kalshi order book has two sides: YES (buy the contract) and NO (sell the contract). These are merged into a single price axis. YES prices map to BUY orders. NO prices are converted to YES-equivalent (`100 - no_price_cents`) and mapped to SELL orders. All prices are divided by 100 to produce decimal values in [0.0, 1.0].

## Backtest vs Live

**Date:** 2026-05-05
**Context:** Architecture decision for how each mode gets data.

Backtest mode reads from the Parquet catalog. Live/paper mode uses `KalshiDataClient` via WebSocket. The catalog is populated separately via `KalshiHttpClient`. The two paths share `factories.py` conversions but are otherwise independent.
