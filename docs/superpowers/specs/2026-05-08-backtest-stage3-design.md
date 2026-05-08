# Dashboard Stage 3: Backtest Runner Design

**Goal:** Add a backtest subsystem to the nautilus-plus dashboard — users can trigger a strategy backtest with a custom date range and parameter overrides, track progress in real time, and explore results (KPIs, equity curve, trade table, CSV export) without leaving the UI.

---

## Architecture

Stage 3 adds four backend pieces and two frontend pieces on top of the existing Stage 2 dashboard:

**Backend additions:**
- `dashboard/api/db/` — SQLite connection management and schema initialisation
- `dashboard/api/services/backtest_runner.py` — spawns backtest subprocess, streams stdout, writes progress and result to SQLite
- `dashboard/api/routes/backtests.py` — four REST routes (start, list, detail, export)
- `dashboard/api/config.py` — each strategy gains `backtest_script` path and string-typed data source path fields in `config_schema`

**Frontend additions:**
- `dashboard/ui/src/pages/BacktestPage.tsx` — run form + history list + detail view
- `dashboard/ui/src/App.tsx` — new route `/strategies/:name/backtests`

`BacktestRunner` is wired into `app.state` via `create_app()` alongside the existing `StatePoller` and `ProcessManager`. The UI polls the detail endpoint every 2 seconds while a run is in-progress.

---

## Script Contract

Each strategy that supports backtesting provides a script at a registered path (`backtest_script` in config.py, e.g. `strategies/mlb_burst/backtest.py`).

**Invocation:**
```bash
python strategies/mlb_burst/backtest.py \
  --start 2025-01-01 \
  --end   2025-03-31 \
  --params '{"sweep_min_spread_cents": 5, "data_path": "/data/mlb/2025"}'
```

- `--start` / `--end`: ISO date strings (inclusive)
- `--params`: JSON string containing any config_schema key overrides, including data source paths

**stdout protocol (JSONL — one object per line):**

Progress event (emitted periodically during the run):
```json
{"type": "progress", "pct": 45, "msg": "Processing game 47/200"}
```

Result event (last line, emitted on completion):
```json
{
  "type": "result",
  "kpis": {
    "total_trades": 42,
    "win_rate": 0.62,
    "realized_pnl": 187.50,
    "max_drawdown": -45.00,
    "sharpe": 1.2
  },
  "trades": [
    {"ts": 1234567890, "ticker": "KXMLBGAME-...", "side": "YES", "qty": 5, "price": 0.35, "pnl": 8.75}
  ],
  "equity_curve": [
    {"ts": 1234567890, "equity": 10000.0}
  ]
}
```

Progress goes to stdout (so the runner can parse it line-by-line). Logs and debug output go to stderr (ignored by the runner, visible in the terminal).

If the script exits non-zero or emits no result line, the run is marked `error`.

---

## Database Schema

Single table, created with `CREATE TABLE IF NOT EXISTS` on app startup (no migrations framework).

```sql
CREATE TABLE IF NOT EXISTS backtest_runs (
    id           TEXT    PRIMARY KEY,   -- uuid4 hex
    strategy     TEXT    NOT NULL,
    started_at   INTEGER NOT NULL,      -- unix timestamp
    finished_at  INTEGER,               -- NULL until done or error
    status       TEXT    NOT NULL,      -- pending | running | done | error
    progress_pct INTEGER DEFAULT 0,
    progress_msg TEXT,
    params       TEXT    NOT NULL,      -- JSON: {start_date, end_date, overrides: {...}}
    result       TEXT                   -- JSON: {kpis, trades, equity_curve}, NULL until done
);
```

SQLite file path: `dashboard/db/backtests.db` (created on first run, excluded from git via `.gitignore`).

---

## API Routes

### `POST /api/strategies/{name}/backtests`

Start a backtest run.

Request body:
```json
{
  "start_date": "2025-01-01",
  "end_date":   "2025-03-31",
  "overrides":  {"sweep_min_spread_cents": 5, "data_path": "/data/mlb/2025"}
}
```

Response (202):
```json
{"run_id": "abc123", "status": "pending"}
```

Errors: 404 unknown strategy, 400 no `backtest_script` configured, 409 a run already in-progress for this strategy.

Behaviour: writes a `pending` row to SQLite, then fires the subprocess. The subprocess is managed by `BacktestRunner`; the route returns immediately.

---

### `GET /api/strategies/{name}/backtests`

List all runs for a strategy, most recent first.

Response:
```json
[
  {
    "run_id": "abc123",
    "started_at": 1234567890,
    "finished_at": 1234568000,
    "status": "done",
    "progress_pct": 100,
    "params": {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}}
  }
]
```

No KPIs or trades in the list response — detail is fetched separately.

---

### `GET /api/backtests/{run_id}`

Full run detail.

Response:
```json
{
  "run_id": "abc123",
  "strategy": "mlb_burst",
  "status": "done",
  "progress_pct": 100,
  "progress_msg": "Complete",
  "params": {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
  "kpis": {"total_trades": 42, "win_rate": 0.62, "realized_pnl": 187.50, "max_drawdown": -45.00, "sharpe": 1.2},
  "trades": [...],
  "equity_curve": [...]
}
```

`kpis`, `trades`, and `equity_curve` are `null` until `status === "done"`.

---

### `GET /api/backtests/{run_id}/export`

Download trades as CSV.

Response: `Content-Type: text/csv`, `Content-Disposition: attachment; filename="backtest_{run_id}.csv"`

Columns: `ts, ticker, side, qty, price, pnl`

Error: 404 if run not found, 409 if run not yet done.

---

## BacktestRunner Service

```python
class BacktestRunner:
    async def start(self, run_id, strategy, script, params) -> None
    async def get_run(self, run_id) -> dict | None      # reads from SQLite
    async def list_runs(self, strategy) -> list[dict]   # reads from SQLite
    def is_running(self, strategy) -> bool
```

`start()` inserts a `running` row, spawns `asyncio.create_subprocess_exec`, and launches a background task that reads stdout line-by-line. Each progress line updates the DB row. The final result line is parsed and stored as JSON in the `result` column with `status = "done"`. On non-zero exit or missing result line, sets `status = "error"`.

Only one run per strategy at a time (enforced by `is_running()` check in the route).

---

## Frontend: BacktestPage

Route: `/strategies/:name/backtests`

Layout: two-column on wide screens, stacked on narrow.

**Left column — Run form:**
- Start date / end date inputs (HTML `<input type="date">`)
- Param overrides: type-aware fields rendered from `config_schema`, pre-filled by calling `GET /api/strategies/{name}/config` on mount. Field types: `int`/`float` → number input, `string` → text input, `bool` → toggle. (This is the same logic as `ConfigEditor` extended to handle `string`.)
- "Run Backtest" button — disabled while `isRunning`
- Inline error display if start fails

**Right column — History + detail:**
- Run history list (most recent first):
  - Shows: date range, `started_at` formatted timestamp, status badge, progress bar if `status === "running"`
  - Clicking a row selects it and shows the detail panel below
- Detail panel (selected run):
  - KPI cards: Total Trades, Win Rate, Realized P&L, Max Drawdown, Sharpe
  - Equity curve (`EquityChart` component, reused from StrategyPage)
  - Trade table: ts (formatted), ticker, side badge, qty, price, P&L
  - "Export CSV" button
  - "Re-run" button — pre-fills the run form with that run's params

**Polling:** while any visible run has `status === "running"`, the page polls `GET /api/backtests/{run_id}` every 2 seconds. Polling stops when status becomes `done` or `error`.

---

## Config Changes

Each strategy in `config.py` gains:

```python
"backtest_script": "strategies/mlb_burst/backtest.py",
```

Data source path fields are added to `config_schema` with `"type": "string"`:

```python
{"key": "data_path", "label": "Data Path", "type": "string", "default": "data/mlb"},
```

The `validate_config` function in `config_mgr.py` is extended to accept `"string"` type (currently only handles `int` and `float`).

---

## File Map

```
dashboard/
├── api/
│   ├── config.py                      ← add backtest_script + string config fields
│   ├── main.py                        ← wire BacktestRunner into app.state
│   ├── db/
│   │   └── database.py                ← new: SQLite init, get_db(), schema creation
│   ├── routes/
│   │   └── backtests.py               ← new: 4 routes
│   └── services/
│       └── backtest_runner.py         ← new: BacktestRunner class
└── ui/src/
    ├── App.tsx                        ← add /strategies/:name/backtests route
    ├── types.ts                       ← add BacktestRun, BacktestDetail interfaces
    ├── api/client.ts                  ← add startBacktest, listBacktests, getBacktest, exportUrl
    ├── components/
    │   └── Sidebar.tsx                ← add Backtests nav link per strategy
    └── pages/
        └── BacktestPage.tsx           ← new: run form + history + detail

dashboard/db/                          ← new: gitignored, created on first run
    backtests.db

strategies/
├── mlb_burst/backtest.py              ← new: stub entry point implementing JSONL contract (real logic provided separately)
└── threshold/backtest.py              ← new: stub entry point implementing JSONL contract (real logic provided separately)

tests/dashboard/
├── test_backtest_runner.py            ← new
└── test_backtest_routes.py            ← new
```

---

## Testing

**`test_backtest_runner.py`:** mock subprocess, verify progress rows updated in SQLite, verify result stored on completion, verify error status on non-zero exit.

**`test_backtest_routes.py`:** mock `BacktestRunner`, verify start returns 202, verify 409 when already running, verify list returns sorted runs, verify detail returns parsed kpis/trades/equity_curve, verify export returns CSV with correct columns.

All tests use an in-memory SQLite database (`:memory:`) via a fixture that overrides `get_db()`.
