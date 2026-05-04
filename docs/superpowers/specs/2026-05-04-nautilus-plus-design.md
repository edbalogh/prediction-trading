# nautilus-plus: Kalshi Trading System Design

**Date:** 2026-05-04  
**Status:** Approved  
**Scope:** Phase 1 — Kalshi adapter, safety layer, data catalog bridge, strategy framework

---

## 1. Goals

Build a personal prediction market trading system using NautilusTrader as the core engine. The system must support the full research-to-live loop: backtest → paper trade → live execution. Initial venue is Kalshi; Polymarket is a planned Phase 2 (adapter pattern is the same).

Primary strategy style: statistical arbitrage and event-driven piggybacking (e.g., correlating Kalshi markets against external data sources). The system must be rock-solid on order/fill/position integrity — no orphan positions, no lost fills.

**Deployment:** Mac Mini initially; cloud-portable by design.

---

## 2. Repository Structure

```
nautilus-plus/
├── adapters/
│   └── kalshi/
│       ├── __init__.py
│       ├── config.py           # KalshiDataClientConfig, KalshiExecClientConfig
│       ├── constants.py        # Venue, instrument type constants
│       ├── providers.py        # KalshiInstrumentProvider
│       ├── data.py             # KalshiDataClient
│       ├── execution.py        # KalshiExecutionClient
│       ├── factories.py        # Instrument/event converters
│       └── http/               # Ported Kalshi REST client (from kalshi-agent-trader)
│           ├── client.py
│           └── auth.py         # RSA key signing
├── safety/
│   ├── __init__.py
│   ├── reconciliation.py       # Startup reconciliation gate
│   ├── orphan_monitor.py       # Continuous orphan detection
│   ├── quarantine.py           # Orphan quarantine book
│   └── alerts.py               # Alert dispatch (email/push)
├── catalog/
│   ├── __init__.py
│   └── sync.py                 # Ingestion → NautilusTrader catalog bridge
├── strategies/
│   ├── __init__.py
│   └── stat_arb/
│       ├── __init__.py
│       ├── config.py
│       └── strategy.py         # StatArb Strategy subclass
├── backtest/
│   ├── __init__.py
│   └── runners/                # Backtest config scripts per strategy
├── live/
│   ├── __init__.py
│   └── configs/                # Live/paper launcher configs
├── notebooks/                  # Research and strategy development
├── run.py                      # Unified launcher (--mode backtest/paper/live)
├── pyproject.toml
└── README.md
```

---

## 3. Kalshi Adapter

**Language:** Python (following Betfair adapter pattern). NautilusTrader's Rust core handles event processing performance; the adapter does not need Rust.

### 3.1 KalshiInstrumentProvider

- Fetches active markets from Kalshi REST API
- Converts each market to a NautilusTrader `BinaryOption` instrument
- Maps Kalshi ticker (e.g., `KXBTC15M-25APR30-T65499.99`) to `InstrumentId`
- Supports lazy load (specific markets on demand) and bulk load (all markets in a series)
- Caches instrument definitions; refreshes on reconnect

### 3.2 KalshiDataClient

- Maintains WebSocket connection to Kalshi market data stream
- Subscribes to order book deltas and trade ticks per instrument
- Normalizes to NautilusTrader `OrderBookDelta` and `TradeTick`
- Implements exponential backoff reconnect
- Fills missed during reconnect window are recovered via reconciliation (not replayed from WebSocket)

### 3.3 KalshiExecutionClient

- REST API for order submission and management
- Translates NautilusTrader `SubmitOrder` / `CancelOrder` commands to Kalshi API calls
- Maps YES/NO sides to NautilusTrader BUY/SELL; maps $0.01–$1.00 contract price to NautilusTrader price
- All orders submitted with a deterministic `ClOrdId` generated before the API call (UUID4, generated client-side, idempotent retry safety)
- Polls for fill confirmations; emits `OrderFilled` events back to the engine
- Implements `generate_order_status_reports()` and `generate_fill_reports()` for startup reconciliation

### 3.4 Auth

RSA key signing ported directly from `kalshi-agent-trader/app/` — no rewrite needed.

---

## 4. Order Safety & Reconciliation Layer

Strategies are paused and cannot submit orders until the safety layer confirms state is clean. This applies on every startup and every reconnect.

### 4.1 Startup Reconciliation Gate

1. Load cached state from Redis (orders, positions, fills)
2. Fetch live state from Kalshi API (open orders, positions, recent fills)
3. Diff the two states
4. Emit synthetic `OrderFilled` / `OrderCancelled` / `OrderRejected` events for any gap
5. Release strategies to trade only when cached state matches Kalshi state exactly
6. If diff cannot be auto-resolved: **halt all strategies, fire alert, require manual intervention**

### 4.2 Kalshi-Specific Reconciliation Cases

- **Market Settlement:** On startup, check for markets that settled while offline. Emit synthetic settlement events; clear positions.
- **Market Suspension/Halt:** Poll for suspended markets; force-cancel any cached open orders against suspended markets.
- **Yes/No Netting:** A fill on the NO side of a YES position is a partial close, not a new position. Reconciliation understands yes/no netting.
- **Partial Fill Ambiguity:** If fill quantity doesn't match any known order exactly and the executing party is ambiguous, quarantine the position and alert rather than auto-assign.

### 4.3 Orphan Detection (Continuous)

Runs as a background actor during live trading. Triggers **immediate halt + alert** on:

- Any order open at Kalshi with no corresponding cached order
- Any position at Kalshi that no strategy claims
- Any fill arriving for a cancelled or unknown order

### 4.4 Orphan Quarantine Book

Unattributable positions are moved to a quarantine book:
- Tracked and reported, never silently ignored
- Not counted in any strategy's position
- Alert fires with full details (instrument, quantity, estimated P&L)
- Requires explicit manual resolution before the affected instrument can be traded again

### 4.5 Strategy-Level Position Limits

Each strategy config declares `max_position` per instrument. The safety layer enforces this as a hard pre-trade check — orders exceeding the limit are rejected before reaching the adapter.

### 4.6 Dead-Man's-Switch

Configurable per strategy (`heartbeat_timeout_seconds`). If no strategy heartbeat for the configured duration, all open orders for that strategy are automatically cancelled.

### 4.7 Alert Channels

Configurable per deployment: email (default), push notification, or both. Alerts include: event type, instrument, strategy name, expected vs. actual state, and whether the system auto-resolved or halted.

---

## 5. Data Catalog Bridge

**Source:** `/Users/edbalogh/Trading/Ingestion/data/` — Hive-partitioned Parquet (`series=X/date=Y/part.parquet`)  
**Target:** `~/.nautilus/catalog/` — NautilusTrader `ParquetDataCatalog` format

### 5.1 CatalogBuilder (`catalog/sync.py`)

- Reads from Ingestion Parquet files
- Normalizes schema to NautilusTrader Arrow types: `TradeTick`, `OrderBookDelta`, `Bar`
- Maps Kalshi series/ticker to NautilusTrader `InstrumentId`
- Writes to local NautilusTrader catalog
- Idempotent: skips dates already present in catalog

### 5.2 Nightly Sync

- Called from Ingestion project's `run_all.py` after existing collect steps
- No changes to existing collectors required
- Backtests read exclusively from the catalog — no direct dependency on Ingestion file layout

**Flag for Ingestion project:** Add `catalog_sync.py` as a post-collect step in `run_all.py`.

---

## 6. Strategy Framework

Strategies are NautilusTrader `Strategy` subclasses in `strategies/`. Each strategy:

- Declares instruments it trades and `max_position` per instrument
- Implements event callbacks: `on_order_book_delta`, `on_trade_tick`, `on_bar`
- Submits orders only via NautilusTrader's `submit_order` — never directly to the adapter
- Has a serializable config dataclass for reproducible backtests

### 6.1 Phase 1 Strategy: StatArb

Watches correlated markets (e.g., KXBTC15M vs. Coinbase BTC price from crypto bars data). Identifies divergence between Kalshi implied probability and external price signal. Fades back to fair value.

Config parameters: `series`, `external_instrument_id`, `entry_threshold`, `exit_threshold`, `max_position`.

---

## 7. Backtest → Paper → Live Progression

All three modes use identical strategy code. Only the execution client and data source change.

| Mode | Data Source | Execution |
|------|-------------|-----------|
| `backtest` | Catalog Parquet | `BacktestEngine` (simulated fills) |
| `paper` | Live Kalshi WebSocket | `KalshiExecutionClient` (dry-run, no real orders) |
| `live` | Live Kalshi WebSocket | `KalshiExecutionClient` (real orders) |

`run.py --mode [backtest|paper|live] --strategy [strategy_name] --config [config.json]`

Paper mode intercepts orders before the API call but runs full position tracking, reconciliation, and the safety layer — validating the entire system before real money is at risk.

---

## 8. Persistence

- **Redis** — NautilusTrader `CacheDatabaseConfig` for order/position/fill state
- **NautilusTrader Catalog** — Parquet for historical market data (backtesting)
- **Quarantine log** — append-only JSON file for orphan audit trail

---

## 9. Phase 2: Polymarket

NautilusTrader ships a Polymarket adapter. Phase 2 adds `adapters/polymarket/` as a thin config wrapper around the upstream adapter, with the same safety layer wired in. No strategy changes required — strategies see normalized NautilusTrader events regardless of venue.

---

## 10. Out of Scope (Phase 1)

- UI / dashboard (use NautilusTrader's built-in logging and Redis inspection)
- Cloud deployment (Mac Mini target; cloud-portable by design)
- Market-making strategies (infrastructure supports it, strategy implementation deferred)
- Polymarket adapter (Phase 2)
