# MLB Sweep Strategy — Design Spec

**Date:** 2026-05-08  
**Status:** Draft

---

## Overview

A market-making strategy that maintains resting limit BUY YES orders on every active `KXMLBGAME` ticker at three price levels below mid. When a large taker sweeps the YES price down through a resting order, it fills. The strategy then sells aggressively 120 seconds later. Orders are repriced every minute and cancelled when a game reaches the 9th inning or later.

---

## Trading Rules

- **Entry:** Resting limit BUY YES orders at `mid - 15¢`, `mid - 25¢`, `mid - 40¢` with quantities `1`, `2`, `4` contracts respectively.
- **Both tickers:** Subscribe both YES tickers per game (covers sweeps in both price directions).
- **Reprice:** Every 60 seconds — cancel existing orders, poll bid/ask via REST, submit fresh orders at updated levels.
- **Mid guard:** Only place orders when `0.20 ≤ mid ≤ 0.80`.
- **Late game guard:** Cancel all orders and stop repricing when `inning > 8`.
- **Fill:** Independent per level. A trade tick at or below a resting order price triggers a fill.
- **Exit:** 120 seconds after each fill, poll current best bid and submit a market SELL for that quantity.

---

## Architecture

### New files

| File | Purpose |
|------|---------|
| `strategies/mlb_sweep/mlb_sweep.py` | Strategy class |
| `scripts/paper_trade_mlb_sweep.py` | Runner script |

### Modified files

| File | Change |
|------|--------|
| `adapters/kalshi/paper.py` | Limit order support in `PaperExecutionClient` |

---

## Component Design

### `MLBSweepConfig`

```python
class MLBSweepConfig(StrategyConfig):
    reprice_interval_s: int = 60
    offsets_cents: list[int] = [15, 25, 40]
    sizes: list[int] = [1, 2, 4]
    mid_min: float = 0.20
    mid_max: float = 0.80
    exit_delay_s: int = 120
```

### `MLBSweepStrategy`

Inherits from `nautilus_trader.trading.strategy.Strategy`.

**Dependencies (constructor injection):**
- `kalshi_http: KalshiHttpClient` — REST polls for bid/ask and orderbook
- `mlb_stats: MLBStatsClient` — inning checks
- `paper_exec: PaperExecutionClient | None` — for fill simulation; `None` in live mode

**State:**
- `_ticker_to_game_pk: dict[str, int]` — populated at startup
- `_active_tickers: set[str]` — tickers still in reprice loop
- `_level_orders: dict[str, list[ClientOrderId]]` — 3 order IDs per ticker (or empty if not yet placed)
- `_exit_tasks: dict[str, asyncio.Task]` — 120s exit tasks keyed by `client_order_id`
- `_reprice_task: asyncio.Task | None` — the single 60s reprice loop

**Lifecycle:**

`on_start()`:
1. `_discover_markets()` async — fetch all open `KXMLBGAME` tickers from Kalshi, build `_ticker_to_game_pk` (both home and away tickers per game via `_match_game_pk`), subscribe trade ticks for all.
2. Start `_reprice_loop()` task.

`on_trade_tick(tick)`:
1. If `paper_exec` is set: call `paper_exec.simulate_fills(ticker, price_float, ts_ns)`.

`on_order_filled(event)`:
1. Remove the filled order ID from `_level_orders[ticker]`.
2. Launch `_exit_task(ticker, qty)` — sleep `exit_delay_s`, poll best bid, submit market SELL.

`on_stop()`:
1. Cancel `_reprice_task`.
2. Cancel all `_exit_tasks`.
3. Cancel all pending limit orders via `cancel_order()` for each ID in `_level_orders`.

### `_reprice_loop()` (async, runs every 60s)

For each ticker in `_active_tickers`:

1. Look up `game_pk` in `_ticker_to_game_pk`.
2. Call `mlb_stats.get_game_state(game_pk)` — if `inning > 8`, cancel all orders for this ticker, remove from `_active_tickers`, continue to next.
3. Call `kalshi_http.get_orderbook(ticker)` — extract best bid + best ask as floats.
4. Compute `mid = (bid + ask) / 2`. If `mid < mid_min` or `mid > mid_max`: cancel existing orders for this ticker (if any), clear `_level_orders[ticker]`, skip placement — we hold no orders until mid returns to range.
5. Cancel existing orders in `_level_orders[ticker]` (submit `cancel_order()` for each stored ID).
6. Submit 3 new limit BUY orders at `mid - offset` for each `(offset, qty)` pair from config.
7. Store the 3 new `ClientOrderId`s in `_level_orders[ticker]`.

### `PaperExecutionClient` enhancements

**New state:**
```python
_pending_limits: dict[ClientOrderId, _PendingLimit]
```

where `_PendingLimit` is a small dataclass:
```python
@dataclass
class _PendingLimit:
    ticker: str
    order_side: OrderSide
    limit_price: float
    quantity: int
    strategy_id: StrategyId
    instrument_id: InstrumentId
    client_order_id: ClientOrderId
    venue_order_id: VenueOrderId
```

**`_submit_order` changes:**
- If `order.order_type == OrderType.LIMIT`: store in `_pending_limits`, generate `OrderAccepted` only, return.
- Market orders: unchanged (fill immediately as before).

**`_cancel_order` changes:**
- If `command.client_order_id` in `_pending_limits`: remove it, generate `OrderCanceled` event, return.
- Otherwise: no-op (unchanged).

**New method `simulate_fills(ticker, trade_price, ts_ns)`:**
```python
def simulate_fills(self, ticker: str, trade_price: float, ts_ns: int) -> None:
    to_fill = [
        pl for pl in self._pending_limits.values()
        if pl.ticker == ticker
        and pl.order_side == OrderSide.BUY
        and trade_price <= pl.limit_price
    ]
    for pl in to_fill:
        del self._pending_limits[pl.client_order_id]
        self._fill_limit_order(pl, fill_price=pl.limit_price, ts_ns=ts_ns)
```

`_fill_limit_order(pl, fill_price, ts_ns)` generates `OrderFilled` using the same `generate_order_filled` call as the existing market order path, then updates `_positions`, `_cash`, and `_fills` identically. Fills at the limit price (not LAST), so paper P&L correctly reflects the resting order price.

---

## Data Flow

```
Kalshi WebSocket ──► on_trade_tick()
                          │
                          ▼
                  paper_exec.simulate_fills()
                          │
                    limit crossed?
                          │ yes
                          ▼
                  on_order_filled()
                          │
                          ▼
                  _exit_task (120s sleep)
                          │
                          ▼
                  get_orderbook() → bid
                          │
                          ▼
                  market SELL submitted

60s timer ──► _reprice_loop()
                  │
                  ├── inning > 8? → deactivate ticker
                  ├── mid out of range? → skip
                  ├── cancel old orders
                  └── submit 3 new limit BUYs
```

---

## Market Discovery

`_discover_markets()` async:
1. `kalshi_http.get_markets(series="KXMLBGAME", status="open")` — get all active tickers.
2. `mlb_stats.get_schedule(date=today)` — get today's MLB games.
3. For each Kalshi market: parse title to extract both team names (home and away), match each to a `gamePk` using extended `_match_game_pk` logic.
4. Populate `_ticker_to_game_pk` for both tickers per game.
5. Subscribe trade ticks for all discovered tickers.

Reuses `_parse_home_name` and `_match_game_pk` from mlb_burst; adds `_parse_away_name` to match the away team ticker to the same `gamePk`.

---

## Testing

| Test file | Coverage |
|-----------|---------|
| `tests/strategies/test_mlb_sweep.py` | Reprice loop, fill detection, exit task, inning cutoff, mid guard |
| `tests/adapters/kalshi/test_paper_limit_orders.py` | `simulate_fills`, `_cancel_order`, limit vs market order paths |

Key test cases:
- Trade tick at exactly limit price → fill generated
- Trade tick above limit price → no fill
- Cancel during reprice → `OrderCanceled` event, removed from pending
- `inning > 8` → orders cancelled, ticker deactivated
- `mid < 0.20` or `mid > 0.80` → no orders placed
- Exit task fires 120s after fill, submits SELL at current bid
