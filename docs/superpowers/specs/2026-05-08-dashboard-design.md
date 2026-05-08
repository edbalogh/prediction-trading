# nautilus-plus Dashboard Design

**Date:** 2026-05-08
**Status:** Approved
**Scope:** Full-stack trading dashboard — live/paper monitoring, backtest management, strategy config

---

## 1. Goals

Build a sleek, modern web dashboard for the nautilus-plus trading system that supports:

- **Monitoring** live and paper trading strategies in real time
- **Controlling** strategies (start, stop, edit config parameters)
- **Running backtests** with configurable parameters per strategy
- **Tracking** backtest history with full run details, charts, and trade reports

Accessible over LAN from any machine (laptop, etc.) running on a Mac Mini. Cloud-portable by design.

---

## 2. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Orchestrator API | FastAPI (Python) | Same language as trading system; async-native; easy WebSocket support |
| Frontend | React + Vite + Tailwind CSS + shadcn/ui | Mainstream, fast dev loop, excellent component ecosystem |
| Real-time | WebSocket (FastAPI native) | Push live P&L / position / trade updates to browser |
| Backtest history | SQLite (via SQLAlchemy) | Zero ops, local file, survives restarts, fully queryable |
| Config storage | JSON files per strategy (existing pattern) | UI reads, edits, and writes these; live/paper launchers read them |
| Auth | API token in HTTP header + cookie | Simple, sufficient for LAN; ready to upgrade to OAuth for cloud |
| Serving | FastAPI serves React SPA static build | One process to deploy; no separate web server |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Browser (React SPA)                  │
│  Sidebar + Live View + Paper View + Backtest Dashboard       │
└────────────────┬──────────────────────────────┬─────────────┘
                 │ REST (config, backtest CRUD)  │ WebSocket (live state)
                 ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     Orchestrator (FastAPI)                    │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Strategy    │  │ Backtest     │  │ Config            │  │
│  │ Process Mgr │  │ Job Runner   │  │ Manager           │  │
│  └──────┬──────┘  └──────┬───────┘  └───────────────────┘  │
│         │                │                                   │
│         │          ┌─────▼──────┐                           │
│         │          │  SQLite DB  │                          │
│         │          │ (run history│                          │
│         │          │  + trades)  │                          │
│         │          └────────────┘                           │
└─────────┼───────────────────────────────────────────────────┘
          │ subprocess / HTTP poll
          ▼
┌─────────────────────────────────────────────────────────────┐
│              Strategy Processes (NautilusTrader)              │
│                                                              │
│  paper_trade_mlb.py   ← state HTTP server on port 876x      │
│  live_trade_mlb.py    ← state HTTP server on port 876x      │
│  (future strategies follow same pattern)                     │
└─────────────────────────────────────────────────────────────┘
```

### 3.1 Orchestrator Responsibilities

- **Process management:** spawn and kill strategy subprocesses on demand
- **State polling:** poll each running strategy's state HTTP endpoint (~1s interval), push updates to browser via WebSocket
- **Backtest execution:** run backtest scripts as async subprocesses; stream stdout to browser; store results in SQLite
- **Config management:** read/write strategy JSON config files; validate before write
- **Auth:** validate API token on all routes

### 3.2 Strategy Process Contract

Each strategy script (live or paper) must:
- Expose a `GET /state` endpoint on an assigned port that returns current P&L, positions, trade log, and heartbeat timestamp
- Read its config from a well-known JSON path at startup
- Exit cleanly on `SIGTERM`

The existing `paper_trade_mlb.py` already satisfies this contract (port 8766). New strategies follow the same pattern.

### 3.3 Real-time Data Flow

1. Orchestrator polls each running strategy's `/state` every 1 second
2. Aggregates state into a per-strategy snapshot
3. Pushes snapshot over WebSocket to all connected browser clients
4. Browser React state updates; charts and tables re-render

No browser-to-strategy direct connection — all data flows through the orchestrator.

---

## 4. Visual Design

### 4.1 Aesthetic

- **Theme:** Light with dark sidebar hybrid (Supabase/Retool style)
- **Sidebar:** Soft light-slate (`#ededf5`), subtle borders, dark text, purple accent on active item
- **Main content:** Off-white (`#f6f6fa`) background, white cards with light borders
- **Accent color:** Purple/indigo (`#7b5cff`) for active states, charts, primary buttons
- **Status colors:** Green (`#16a34a`) for live/profit, Blue (`#2563eb`) for paper, Red (`#dc2626`) for stopped/loss
- **Typography:** System font stack (-apple-system, Segoe UI); monospace (SF Mono) for tickers and numbers

### 4.2 Sidebar Navigation

```
nautilus+  [LIVE]
─────────────────
STRATEGIES
  ⚡ MLB Burst      ● (green = running)
  ↕  Threshold      ○ (gray = stopped)
─────────────────
MODES
  ● Live Trading
  ◎ Paper Trade    ● (blue = running)
─────────────────
RESEARCH
  ▶ Run Backtest
  ⊡ Backtest History
─────────────────
[avatar] nautilus-plus  ⚙
         Mac Mini · LAN
```

Clicking a strategy in the sidebar navigates to that strategy's Live or Paper view (whichever is active, or defaults to Live). Modes section navigates to the all-strategies aggregate view for that mode.

---

## 5. Views

### 5.1 Strategy Detail View (Live & Paper)

Shared layout — identical structure, different status badge color (green=Live, blue=Paper).

**Top bar:**
- Strategy name + mode (e.g. "MLB Burst — Live")
- Status pill: `● Running` / `◎ Paper` / `○ Stopped`
- Buttons: `Edit Config` · `Stop Strategy` (when running) or `Start Strategy` (when stopped)

**Safety alert bar** (shown when safety events are active):
- Dead-man's switch warnings, orphan detections, reconciliation failures
- Yellow/amber bar with event description

**KPI cards (5):**
- Realized P&L (with today delta)
- Unrealized P&L (with open position count)
- Total Trades (with today count)
- Win Rate (W/L breakdown)
- Equity (all-time % change)

**Charts row (2-column):**
- Equity curve (area + line, Recharts, live-updating)
- Open positions table (ticker, YES/NO side, qty, avg entry, unrealized P&L)

**Trade log:**
- Scrollable, most recent first
- Columns: time, ticker, side (BUY/SELL), signal type, qty × price, realized P&L

### 5.2 Config Editor (Modal or Slide-over)

Triggered by `Edit Config` button. Works identically for Live, Paper, and Backtest run configuration.

- Renders all strategy parameters as editable form fields (type-aware: number inputs, toggles, date pickers)
- Reads from `strategies/<name>/config.json`
- Validates on save (type checking, range constraints declared by the strategy)
- Writes back to `strategies/<name>/config.json` on save
- Live/paper launchers read this file at startup — changes take effect on next start
- Backtest runner reads it as defaults but allows per-run overrides without saving

### 5.3 Backtest Dashboard

**Layout:** Two-pane horizontal split.

**Left pane (260px fixed):**
- *Configure & Run* section at top:
  - Strategy selector dropdown
  - Start date / End date pickers
  - Parameter grid (reads from strategy config as defaults, editable per-run without saving)
  - `▶ Run Backtest` button — triggers async job, shows spinner in history list
- *History list* below (scrollable):
  - Each item: strategy name, date run, date range, P&L summary, parameter tags
  - In-progress runs show animated spinner + "Running" pill
  - Click to load detail in right pane

**Right pane (flexible):**
- *Run header:* strategy name, run date, date range, duration
- *Parameters used:* compact chip row showing all non-default params
- *KPI cards (4):* Total P&L, Win Rate, Max Drawdown, Total Trades
- *Charts (side by side):* Equity curve + Drawdown %
- *Trade report table:* date/time, ticker, signal type, entry, exit, P&L — paginated, exportable to CSV
- *Action buttons:* `Export CSV` · `Re-run with Changes` (pre-fills left pane form with this run's params)

### 5.4 Aggregate Mode Views (future)

"Live Trading" and "Paper Trade" sidebar items show an all-strategies summary — a grid of strategy cards each showing current P&L and status. Not in scope for Stage 1.

---

## 6. Backtest Storage Schema (SQLite)

```sql
-- One row per backtest run
CREATE TABLE backtest_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy    TEXT NOT NULL,           -- "mlb_burst", "threshold"
    started_at  DATETIME NOT NULL,
    finished_at DATETIME,
    status      TEXT NOT NULL,           -- "running", "complete", "failed"
    date_from   DATE NOT NULL,
    date_to     DATE NOT NULL,
    params      TEXT NOT NULL,           -- JSON blob of parameters used
    -- Summary stats (populated on completion)
    total_pnl       REAL,
    win_rate        REAL,
    max_drawdown    REAL,
    total_trades    INTEGER,
    equity_curve    TEXT                -- JSON array of {date, equity} points
);

-- One row per trade within a backtest run
CREATE TABLE backtest_trades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES backtest_runs(id),
    trade_dt    DATETIME NOT NULL,
    ticker      TEXT NOT NULL,
    side        TEXT NOT NULL,          -- "BUY" / "SELL"
    signal_type TEXT,                   -- "W1+sweep", "sweep", etc.
    qty         INTEGER NOT NULL,
    entry_price REAL NOT NULL,
    exit_price  REAL,
    pnl         REAL
);
```

---

## 7. API Routes

### Orchestrator REST API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/strategies` | List all strategies with current status |
| `GET` | `/api/strategies/{name}/config` | Read strategy config |
| `PUT` | `/api/strategies/{name}/config` | Write strategy config |
| `POST` | `/api/strategies/{name}/start` | Start live or paper trade (`?mode=live\|paper`) |
| `POST` | `/api/strategies/{name}/stop` | Stop running strategy |
| `GET` | `/api/backtests` | List all backtest runs (paginated) |
| `GET` | `/api/backtests/{id}` | Get single run with trades |
| `POST` | `/api/backtests` | Start a new backtest run |
| `GET` | `/api/backtests/{id}/trades` | Get trades for a run (paginated) |
| `GET` | `/api/backtests/{id}/trades/csv` | Export trades as CSV |
| `WS` | `/ws` | WebSocket: push strategy state snapshots |

### WebSocket Message Format

```json
{
  "strategy": "mlb_burst",
  "mode": "live",
  "ts": 1746720000,
  "equity": 10302.50,
  "realized_pnl": 284.50,
  "unrealized_pnl": 18.20,
  "total_trades": 47,
  "win_rate": 0.617,
  "positions": [...],
  "recent_trades": [...],
  "safety_events": [...]
}
```

---

## 8. Auth

- Single API token stored in `.env` (`DASHBOARD_TOKEN=...`)
- Frontend stores token in `localStorage` after login
- All API requests send `Authorization: Bearer <token>` header
- WebSocket handshake sends token as query param (`?token=...`)
- Login page served at `/login` — single password field that exchanges for the token
- No token expiry for LAN use; add rotation when cloud-deploying

---

## 9. Project Structure

```
nautilus-plus/
├── dashboard/
│   ├── api/
│   │   ├── main.py              # FastAPI app, mounts static, registers routes
│   │   ├── routes/
│   │   │   ├── strategies.py    # /api/strategies/* routes
│   │   │   ├── backtests.py     # /api/backtests/* routes
│   │   │   └── ws.py            # /ws WebSocket handler
│   │   ├── services/
│   │   │   ├── process_mgr.py   # subprocess spawn/kill/poll
│   │   │   ├── backtest_runner.py
│   │   │   └── config_mgr.py
│   │   ├── db.py                # SQLAlchemy setup + models
│   │   └── auth.py              # token validation middleware
│   └── ui/                      # React + Vite frontend
│       ├── src/
│       │   ├── App.tsx
│       │   ├── components/
│       │   │   ├── Sidebar.tsx
│       │   │   ├── TopBar.tsx
│       │   │   ├── KpiCards.tsx
│       │   │   ├── EquityChart.tsx
│       │   │   ├── PositionsTable.tsx
│       │   │   ├── TradeLog.tsx
│       │   │   ├── SafetyAlerts.tsx
│       │   │   ├── ConfigEditor.tsx
│       │   │   ├── BacktestForm.tsx
│       │   │   ├── BacktestHistory.tsx
│       │   │   └── BacktestDetail.tsx
│       │   ├── pages/
│       │   │   ├── StrategyPage.tsx
│       │   │   └── BacktestPage.tsx
│       │   ├── hooks/
│       │   │   ├── useWebSocket.ts
│       │   │   └── useStrategyState.ts
│       │   └── api/
│       │       └── client.ts    # typed fetch wrappers
│       ├── package.json
│       └── vite.config.ts
├── scripts/
│   └── start_dashboard.sh       # starts orchestrator; builds UI if needed
```

---

## 10. Implementation Stages

### Stage 1 — Shell + Live Monitoring (read-only)
- FastAPI orchestrator skeleton with auth
- React app shell: sidebar, routing, top bar
- WebSocket connection + live state display for existing `paper_trade_mlb.py`
- KPI cards, equity curve, positions table, trade log (read-only, no start/stop yet)

### Stage 2 — Strategy Control + Config Editor
- Start/stop buttons wired to process manager
- Config editor modal (read config, edit form, save)
- Strategy status indicators update in real time in sidebar

### Stage 3 — Backtest Dashboard
- SQLite schema + migrations
- Backtest runner (async subprocess, stdout capture)
- History list + in-progress polling
- Full detail view: KPIs, charts, trade table, CSV export, re-run

### Stage 4 — Polish & Hardening
- Login page + token auth end-to-end
- Error states and empty states throughout
- Mobile-responsive sidebar (collapse to icon rail)
- Aggregate mode view (all strategies at a glance)

---

## 11. Out of Scope

- Cloud deployment / HTTPS / reverse proxy (infrastructure, not app code)
- Multi-user access / per-user permissions
- Push notifications (covered by existing `safety/alerts.py`)
- Historical replay or tick-level chart zoom beyond what's in the trade log
