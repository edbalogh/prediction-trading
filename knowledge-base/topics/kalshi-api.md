# Kalshi API

## WebSocket API v2

**URL:** `wss://trading-api.kalshi.com/trade-api/ws/v2`

**Auth:** RSA-signed headers, sent at connection time. Headers must be regenerated on every new connection (they contain a timestamp). See `KalshiHttpClient.websocket_headers()`.

## Price Model

**Date:** 2026-05-05
**Context:** Kalshi prices are integers in cents (0–100); NautilusTrader expects decimals.

All prices are integers representing cents. Divide by 100 for the decimal value (e.g., 55 → 0.55). The `PRICE_PRECISION = 2` constant reflects this. YES prices are BUY; NO prices must be converted to YES-equivalent: `yes_price_cents = 100 - no_price_cents`. After conversion, NO-side orders become SELL orders on the YES price axis.

## WebSocket Message Types

### orderbook_snapshot
Sent immediately after subscribing to `orderbook_delta`. Full book state. Both `yes` and `no` arrays are `[price_cents, size]` pairs.

### orderbook_delta
Incremental update. Same structure as snapshot but sparse — only changed levels. `size = 0` means the level was removed (DELETE action). `size > 0` means the level's total quantity changed (UPDATE action).

### trade
Public trade. Key field: `ts` is Unix **milliseconds** (not seconds, not nanoseconds). Convert to nanoseconds: `ts_ns = ts_ms * 1_000_000`. The `taker_side` field is `"yes"` or `"no"` — maps directly to `AggressorSide.BUYER` / `AggressorSide.SELLER`.

## Subscription Commands

```json
{"id": 1, "cmd": "subscribe",   "params": {"channels": ["orderbook_delta"], "market_tickers": ["KXBTC15M-X"]}}
{"id": 2, "cmd": "unsubscribe", "params": {"channels": ["orderbook_delta"], "market_tickers": ["KXBTC15M-X"]}}
```

Valid channels: `orderbook_delta`, `trade`.

## REST Orderbook Endpoint

Returns `{"orderbook": {"yes": [[price_cents, size], ...], "no": [[no_price_cents, size], ...]}}`. The `get_orderbook(ticker)` method on `KalshiHttpClient` returns this structure directly.

## Trade ID

REST fills have `trade_id`. WebSocket trade messages may omit it. Fallback: `f"{market_ticker}-{ts}"` where `ts` is the millisecond timestamp. This is sufficient for deduplication; exact IDs are only available via REST.
