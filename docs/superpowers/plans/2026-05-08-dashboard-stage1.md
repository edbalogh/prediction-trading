# Dashboard Stage 1: Shell + Live Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI orchestrator + React frontend that displays real-time live/paper strategy state — KPI cards, equity curve, open positions, and trade log — by polling the existing strategy state HTTP endpoints.

**Architecture:** FastAPI backend polls each running strategy's `/state` HTTP endpoint every second, accumulates equity history in memory, normalizes the data, and fans it out to browsers via WebSocket. React SPA connects via WebSocket and renders live-updating components. Vite dev server proxies `/api` and `/ws` to the FastAPI app during development; in production FastAPI serves the built React static files.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, pytest, pytest-asyncio — React 18, TypeScript, Vite 5, Tailwind CSS 3, Recharts, React Router v6

**Scope:** Stage 1 only (read-only monitoring, no start/stop, no auth, no SQLite). Stages 2–4 have separate plans.

---

## File Map

```
dashboard/
├── api/
│   ├── requirements.txt
│   ├── __init__.py
│   ├── main.py                   # FastAPI app, CORS, static mount, lifespan
│   ├── config.py                 # STRATEGIES registry dict
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── strategies.py         # GET /api/strategies
│   │   └── ws.py                 # /ws WebSocket + ConnectionManager
│   └── services/
│       ├── __init__.py
│       └── state_poller.py       # Async polling loop, state normalizer, equity history
└── ui/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── postcss.config.js
    ├── tsconfig.json
    ├── index.html
    └── src/
        ├── main.tsx
        ├── App.tsx                # Root: router + layout
        ├── types.ts               # Shared TypeScript interfaces
        ├── api/
        │   └── client.ts          # Typed fetch wrappers for REST
        ├── hooks/
        │   ├── useWebSocket.ts    # Manages WS connection, reconnect
        │   └── useStrategyState.ts # Subscribes to WS, returns per-strategy state
        ├── components/
        │   ├── Sidebar.tsx
        │   ├── TopBar.tsx
        │   ├── KpiCards.tsx
        │   ├── EquityChart.tsx    # Recharts AreaChart
        │   ├── PositionsTable.tsx
        │   └── TradeLog.tsx
        └── pages/
            └── StrategyPage.tsx   # Assembles all components for one strategy

tests/
└── dashboard/
    ├── __init__.py
    ├── test_state_poller.py
    ├── test_strategies_route.py
    └── test_ws.py
```

---

## Task 1: Backend — requirements and project skeleton

**Files:**
- Create: `dashboard/api/requirements.txt`
- Create: `dashboard/api/__init__.py`
- Create: `dashboard/api/config.py`
- Create: `dashboard/api/routes/__init__.py`
- Create: `dashboard/api/services/__init__.py`
- Create: `tests/dashboard/__init__.py`

- [ ] **1.1 Create the requirements file**

`httpx`, `pytest`, `pytest-asyncio`, and `respx` are already in `pyproject.toml` dev deps. Only FastAPI and uvicorn are new:

```
# dashboard/api/requirements.txt
fastapi==0.115.12
uvicorn[standard]==0.34.2
```

- [ ] **1.2 Install dependencies**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus
pip install -r dashboard/api/requirements.txt
pip install -e ".[dev]"   # ensures pytest/respx/httpx are present
```

Expected: all packages install without conflicts. Verify with `python -c "import fastapi, uvicorn; print('ok')`.

- [ ] **1.3 Create empty init files**

```python
# dashboard/api/__init__.py
# dashboard/api/routes/__init__.py
# dashboard/api/services/__init__.py
# tests/dashboard/__init__.py
```
(All four files are empty — just `touch` them or create with no content.)

- [ ] **1.4 Create strategy registry**

```python
# dashboard/api/config.py
"""
Registry of known strategies and their state-server configuration.
Add a new entry here whenever a new strategy script is created.
"""
from __future__ import annotations

STRATEGIES: dict[str, dict] = {
    "mlb_burst": {
        "display_name": "MLB Burst",
        "icon": "⚡",
        "state_port": 8766,
        "paper_script": "scripts/paper_trade_mlb.py",
        "live_script": None,          # not yet wired
        "starting_capital": 10_000.0,
    },
    "threshold": {
        "display_name": "Threshold",
        "icon": "↕",
        "state_port": 8767,
        "paper_script": "scripts/paper_trade.py",
        "live_script": None,
        "starting_capital": 10_000.0,
    },
}
```

- [ ] **1.5 Commit skeleton**

```bash
git add dashboard/ tests/dashboard/
git commit -m "feat(dashboard): add project skeleton and strategy registry"
```

---

## Task 2: State poller service

**Files:**
- Create: `dashboard/api/services/state_poller.py`
- Create: `tests/dashboard/test_state_poller.py`

The poller runs as a background asyncio task, polling each strategy's `/state` endpoint and normalizing the response into a consistent `StrategySnapshot` dict. It accumulates equity history in memory.

- [ ] **2.1 Write the failing tests**

```python
# tests/dashboard/test_state_poller.py
import pytest
import respx
import httpx
from dashboard.api.services.state_poller import StatePoller, normalize_state


MOCK_STATE = {
    "equity": 10_284.50,
    "starting_capital": 10_000.0,
    "pnl": 284.50,
    "realized_pnl": 266.30,
    "unrealized_pnl": 18.20,
    "positions": {
        "KXMLB-NYY": {"qty": 2, "avg_px": 0.62, "last_px": 0.66, "unrealized_pnl": 8.00},
    },
    "fills": [
        {"ticker": "KXMLB-ATL", "side": "SETTLE", "qty": 2,
         "price": 1.0, "result": "yes", "pnl": 62.0, "ts": 1746700000, "type": "settlement"},
        {"ticker": "KXMLB-BOS", "side": "BUY", "qty": 1,
         "price": 0.54, "ts": 1746699000, "type": "trade"},
    ],
    "entered_games": [],
    "pending_tasks_count": 0,
    "subscribed_markets": ["KXMLB-NYY"],
    "ts": 1746720000,
}


def test_normalize_state_basic_fields():
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=[])
    assert snap["strategy"] == "mlb_burst"
    assert snap["mode"] == "paper"
    assert snap["status"] == "running"
    assert snap["equity"] == 10_284.50
    assert snap["realized_pnl"] == 266.30
    assert snap["unrealized_pnl"] == 18.20
    assert snap["ts"] == 1746720000


def test_normalize_state_positions():
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=[])
    positions = snap["positions"]
    assert len(positions) == 1
    assert positions[0]["ticker"] == "KXMLB-NYY"
    assert positions[0]["qty"] == 2
    assert positions[0]["avg_px"] == 0.62
    assert positions[0]["unrealized_pnl"] == 8.00


def test_normalize_state_fills_returned_reversed():
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=[])
    fills = snap["recent_fills"]
    # Most recent first
    assert fills[0]["ticker"] == "KXMLB-BOS"
    assert fills[1]["ticker"] == "KXMLB-ATL"


def test_normalize_state_win_rate_from_settlements():
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=[])
    # 1 settlement with pnl=62.0 (win), 0 losses → 100%
    assert snap["win_rate"] == 1.0
    assert snap["total_trades"] == 2  # total fills count


def test_normalize_state_win_rate_none_when_no_settlements():
    state = {**MOCK_STATE, "fills": []}
    snap = normalize_state("mlb_burst", "paper", state, equity_history=[])
    assert snap["win_rate"] is None
    assert snap["total_trades"] == 0


def test_normalize_state_equity_history_appended():
    history = [{"ts": 1746700000, "equity": 10_100.0}]
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=history)
    assert snap["equity_history"][-1]["equity"] == 10_284.50
    assert snap["equity_history"][-1]["ts"] == 1746720000


@pytest.mark.asyncio
async def test_poller_fetches_state():
    with respx.mock:
        respx.get("http://localhost:8766/state").mock(
            return_value=httpx.Response(200, json=MOCK_STATE)
        )
        poller = StatePoller()
        await poller.poll_once("mlb_burst", port=8766)
        snap = poller.get_snapshot("mlb_burst")
        assert snap is not None
        assert snap["equity"] == 10_284.50


@pytest.mark.asyncio
async def test_poller_marks_stopped_on_connection_error():
    with respx.mock:
        respx.get("http://localhost:8767/state").mock(
            side_effect=httpx.ConnectError("refused")
        )
        poller = StatePoller()
        await poller.poll_once("threshold", port=8767)
        snap = poller.get_snapshot("threshold")
        assert snap["status"] == "stopped"
```

- [ ] **2.2 Run tests — expect failures**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus
python -m pytest tests/dashboard/test_state_poller.py -v 2>&1 | head -30
```

Expected: `ImportError` — `dashboard.api.services.state_poller` does not exist yet.

- [ ] **2.3 Implement state poller**

```python
# dashboard/api/services/state_poller.py
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

_logger = logging.getLogger(__name__)

# Max equity history points kept in memory per strategy (~24h at 1s poll = 86400 pts)
_MAX_HISTORY = 86_400


def normalize_state(
    strategy: str,
    mode: str,
    raw: dict[str, Any],
    equity_history: list[dict],
) -> dict[str, Any]:
    """Convert a raw /state response into a normalized StrategySnapshot."""
    fills: list[dict] = raw.get("fills", [])

    # Win rate from settlement fills only
    settlements = [f for f in fills if f.get("type") == "settlement" and "pnl" in f]
    if settlements:
        wins = sum(1 for f in settlements if f["pnl"] > 0)
        win_rate: float | None = wins / len(settlements)
    else:
        win_rate = None

    # Positions: dict → list, sorted by ticker
    raw_positions: dict = raw.get("positions", {})
    positions = [
        {
            "ticker": ticker,
            "qty": info["qty"],
            "avg_px": info["avg_px"],
            "last_px": info.get("last_px", info["avg_px"]),
            "unrealized_pnl": info.get("unrealized_pnl", 0.0),
        }
        for ticker, info in sorted(raw_positions.items())
    ]

    # Equity history: append current point, cap length
    ts = raw.get("ts", int(time.time()))
    equity = raw.get("equity", raw.get("starting_capital", 10_000.0))
    new_history = list(equity_history)
    # Avoid duplicate timestamps
    if not new_history or new_history[-1]["ts"] != ts:
        new_history.append({"ts": ts, "equity": equity})
    if len(new_history) > _MAX_HISTORY:
        new_history = new_history[-_MAX_HISTORY:]

    # Fills: most recent first
    recent_fills = list(reversed(fills))

    return {
        "strategy": strategy,
        "mode": mode,
        "status": "running",
        "ts": ts,
        "equity": equity,
        "starting_capital": raw.get("starting_capital", 10_000.0),
        "realized_pnl": raw.get("realized_pnl", 0.0),
        "unrealized_pnl": raw.get("unrealized_pnl", 0.0),
        "total_trades": len(fills),
        "win_rate": win_rate,
        "positions": positions,
        "recent_fills": recent_fills,
        "equity_history": new_history,
    }


def _stopped_snapshot(strategy: str, mode: str) -> dict[str, Any]:
    return {
        "strategy": strategy,
        "mode": mode,
        "status": "stopped",
        "ts": int(time.time()),
        "equity": None,
        "starting_capital": None,
        "realized_pnl": None,
        "unrealized_pnl": None,
        "total_trades": None,
        "win_rate": None,
        "positions": [],
        "recent_fills": [],
        "equity_history": [],
    }


class StatePoller:
    """
    Polls each registered strategy's /state HTTP endpoint.
    Maintains a normalized snapshot and equity history per strategy.
    """

    def __init__(self) -> None:
        self._snapshots: dict[str, dict] = {}
        self._equity_history: dict[str, list[dict]] = {}
        self._client = httpx.AsyncClient(timeout=2.0)
        self._task: asyncio.Task | None = None

    async def poll_once(self, strategy: str, port: int, mode: str = "paper") -> None:
        """Fetch /state for one strategy and update the snapshot cache."""
        url = f"http://localhost:{port}/state"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            raw = response.json()
            history = self._equity_history.get(strategy, [])
            snap = normalize_state(strategy, mode, raw, history)
            self._equity_history[strategy] = snap["equity_history"]
            self._snapshots[strategy] = snap
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            self._snapshots[strategy] = _stopped_snapshot(strategy, mode)

    def get_snapshot(self, strategy: str) -> dict | None:
        return self._snapshots.get(strategy)

    def all_snapshots(self) -> list[dict]:
        return list(self._snapshots.values())

    async def start(self, strategies: dict[str, dict], poll_interval: float = 1.0) -> None:
        """Start background polling loop for all registered strategies."""
        async def _loop() -> None:
            while True:
                for name, cfg in strategies.items():
                    await self.poll_once(
                        name,
                        port=cfg["state_port"],
                        mode="paper",  # Stage 2 will detect live vs paper
                    )
                await asyncio.sleep(poll_interval)

        self._task = asyncio.create_task(_loop())
        _logger.info("StatePoller started for %d strategies", len(strategies))

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
        _logger.info("StatePoller stopped")
```

- [ ] **2.4 Run tests — expect pass**

```bash
python -m pytest tests/dashboard/test_state_poller.py -v
```

Expected: all 8 tests pass.

- [ ] **2.5 Commit**

```bash
git add dashboard/api/services/state_poller.py tests/dashboard/test_state_poller.py
git commit -m "feat(dashboard): add state poller service with normalizer"
```

---

## Task 3: Strategies REST route

**Files:**
- Create: `dashboard/api/routes/strategies.py`
- Create: `tests/dashboard/test_strategies_route.py`

- [ ] **3.1 Write the failing tests**

```python
# tests/dashboard/test_strategies_route.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from dashboard.api.main import create_app
from dashboard.api.services.state_poller import StatePoller


@pytest.fixture
def client():
    poller = MagicMock(spec=StatePoller)
    poller.get_snapshot.side_effect = lambda name: (
        {
            "strategy": name, "mode": "paper", "status": "running",
            "equity": 10_284.50, "realized_pnl": 266.30,
            "unrealized_pnl": 18.20, "total_trades": 2, "win_rate": 1.0,
        }
        if name == "mlb_burst"
        else {"strategy": name, "mode": "paper", "status": "stopped",
              "equity": None, "realized_pnl": None, "unrealized_pnl": None,
              "total_trades": None, "win_rate": None}
    )
    app = create_app(poller=poller)
    return TestClient(app)


def test_get_strategies_returns_all(client):
    resp = client.get("/api/strategies")
    assert resp.status_code == 200
    data = resp.json()
    names = {s["name"] for s in data}
    assert "mlb_burst" in names
    assert "threshold" in names


def test_get_strategies_running_status(client):
    resp = client.get("/api/strategies")
    strategies = {s["name"]: s for s in resp.json()}
    assert strategies["mlb_burst"]["status"] == "running"
    assert strategies["mlb_burst"]["equity"] == 10_284.50


def test_get_strategies_stopped_status(client):
    resp = client.get("/api/strategies")
    strategies = {s["name"]: s for s in resp.json()}
    assert strategies["threshold"]["status"] == "stopped"
    assert strategies["threshold"]["equity"] is None
```

- [ ] **3.2 Run tests — expect failures**

```bash
python -m pytest tests/dashboard/test_strategies_route.py -v 2>&1 | head -20
```

Expected: `ImportError` — modules do not exist yet.

- [ ] **3.3 Implement the strategies route**

```python
# dashboard/api/routes/strategies.py
from __future__ import annotations

from fastapi import APIRouter, Request

from dashboard.api.config import STRATEGIES

router = APIRouter()


@router.get("/strategies")
async def list_strategies(request: Request) -> list[dict]:
    poller = request.app.state.poller
    result = []
    for name, cfg in STRATEGIES.items():
        snap = poller.get_snapshot(name) or {}
        result.append({
            "name": name,
            "display_name": cfg["display_name"],
            "icon": cfg["icon"],
            "status": snap.get("status", "stopped"),
            "mode": snap.get("mode", "paper"),
            "equity": snap.get("equity"),
            "realized_pnl": snap.get("realized_pnl"),
            "unrealized_pnl": snap.get("unrealized_pnl"),
            "total_trades": snap.get("total_trades"),
            "win_rate": snap.get("win_rate"),
        })
    return result
```

- [ ] **3.4 Implement the FastAPI app (needed for tests to import)**

```python
# dashboard/api/main.py
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from dashboard.api.config import STRATEGIES
from dashboard.api.routes.strategies import router as strategies_router
from dashboard.api.routes.ws import router as ws_router
from dashboard.api.services.state_poller import StatePoller

_logger = logging.getLogger(__name__)


def create_app(poller: StatePoller | None = None) -> FastAPI:
    """
    Factory used both by the production server and tests.
    Tests pass a mock poller; production creates a real one.
    """
    _poller = poller or StatePoller()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.poller = _poller
        if poller is None:
            # Only start polling when running for real (not in tests)
            await _poller.start(STRATEGIES)
        yield
        if poller is None:
            await _poller.stop()

    app = FastAPI(title="nautilus-plus dashboard", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # tightened in Stage 4 auth
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(strategies_router, prefix="/api")
    app.include_router(ws_router)

    # Serve built React app (built in Task 15; skip if not yet built)
    static_dir = Path(__file__).parent.parent / "ui" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
```

- [ ] **3.5 Create stub WebSocket router (needed for main.py import)**

```python
# dashboard/api/routes/ws.py
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)

    async def broadcast(self, data: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            # Keep the connection alive; server pushes data via broadcast()
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
```

- [ ] **3.6 Run strategies route tests — expect pass**

```bash
python -m pytest tests/dashboard/test_strategies_route.py -v
```

Expected: all 3 tests pass.

- [ ] **3.7 Commit**

```bash
git add dashboard/api/routes/ dashboard/api/main.py
git commit -m "feat(dashboard): add FastAPI app, strategies route, WS stub"
```

---

## Task 4: WebSocket broadcast loop

**Files:**
- Modify: `dashboard/api/routes/ws.py`
- Modify: `dashboard/api/main.py`
- Create: `tests/dashboard/test_ws.py`

The lifespan starts a background task that pushes all strategy snapshots to connected WS clients every second.

- [ ] **4.1 Write the failing tests**

```python
# tests/dashboard/test_ws.py
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from dashboard.api.main import create_app
from dashboard.api.services.state_poller import StatePoller
from dashboard.api.routes.ws import ConnectionManager


SAMPLE_SNAP = {
    "strategy": "mlb_burst", "mode": "paper", "status": "running",
    "ts": 1746720000, "equity": 10_284.50, "starting_capital": 10_000.0,
    "realized_pnl": 266.30, "unrealized_pnl": 18.20,
    "total_trades": 2, "win_rate": 1.0,
    "positions": [], "recent_fills": [], "equity_history": [],
}


def test_websocket_connection_accepted():
    """Verify the /ws endpoint accepts connections."""
    poller = MagicMock(spec=StatePoller)
    poller.all_snapshots.return_value = []
    app = create_app(poller=poller)
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        assert ws is not None  # connection opened without error


@pytest.mark.asyncio
async def test_broadcast_delivers_to_connected_client():
    """Verify ConnectionManager.broadcast() sends data to mock websockets."""
    received: list[dict] = []

    class MockWS:
        async def send_json(self, data: dict) -> None:
            received.append(data)

    manager = ConnectionManager()
    manager._connections.append(MockWS())  # type: ignore[arg-type]

    await manager.broadcast({"snapshots": [SAMPLE_SNAP]})

    assert len(received) == 1
    assert received[0]["snapshots"][0]["strategy"] == "mlb_burst"
    assert received[0]["snapshots"][0]["equity"] == 10_284.50


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections():
    """Dead WebSocket connections are removed from the manager."""

    class DeadWS:
        async def send_json(self, data: dict) -> None:
            raise RuntimeError("connection closed")

    manager = ConnectionManager()
    manager._connections.append(DeadWS())  # type: ignore[arg-type]

    await manager.broadcast({"snapshots": []})

    assert len(manager._connections) == 0
```

- [ ] **4.2 Run test — expect failure**

```bash
python -m pytest tests/dashboard/test_ws.py -v 2>&1 | head -20
```

Expected: test fails — broadcast not yet called from a push loop.

- [ ] **4.3 Add broadcast loop to main.py lifespan**

Replace the `create_app` function in `dashboard/api/main.py`:

```python
# dashboard/api/main.py
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from dashboard.api.config import STRATEGIES
from dashboard.api.routes.strategies import router as strategies_router
from dashboard.api.routes.ws import router as ws_router, manager as ws_manager
from dashboard.api.services.state_poller import StatePoller

_logger = logging.getLogger(__name__)


def create_app(poller: StatePoller | None = None) -> FastAPI:
    _poller = poller or StatePoller()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.poller = _poller

        push_task: asyncio.Task | None = None

        if poller is None:
            await _poller.start(STRATEGIES)

            async def _push_loop() -> None:
                while True:
                    snapshots = _poller.all_snapshots()
                    if snapshots:
                        await ws_manager.broadcast({"snapshots": snapshots})
                    await asyncio.sleep(1.0)

            push_task = asyncio.create_task(_push_loop())

        yield

        if push_task:
            push_task.cancel()
            try:
                await push_task
            except asyncio.CancelledError:
                pass
        if poller is None:
            await _poller.stop()

    app = FastAPI(title="nautilus-plus dashboard", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(strategies_router, prefix="/api")
    app.include_router(ws_router)

    static_dir = Path(__file__).parent.parent / "ui" / "dist"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
```

- [ ] **4.4 Run all backend tests**

```bash
python -m pytest tests/dashboard/ -v
```

Expected: all tests pass.

- [ ] **4.5 Smoke test: start the server and verify the endpoint responds**

In one terminal, start `paper_trade_mlb.py` (or leave it stopped — stopped status is fine):

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus
uvicorn dashboard.api.main:app --reload --port 8000
```

In another terminal:
```bash
curl http://localhost:8000/api/strategies | python3 -m json.tool
```

Expected: JSON array with `mlb_burst` and `threshold`, both showing `"status": "stopped"` since no strategy is running.

- [ ] **4.6 Commit**

```bash
git add dashboard/api/main.py dashboard/api/routes/ws.py tests/dashboard/test_ws.py
git commit -m "feat(dashboard): add WebSocket broadcast loop pushing strategy snapshots"
```

---

## Task 5: React frontend scaffold

**Files:**
- Create: `dashboard/ui/package.json`
- Create: `dashboard/ui/vite.config.ts`
- Create: `dashboard/ui/tailwind.config.js`
- Create: `dashboard/ui/postcss.config.js`
- Create: `dashboard/ui/tsconfig.json`
- Create: `dashboard/ui/index.html`
- Create: `dashboard/ui/src/main.tsx`

- [ ] **5.1 Scaffold with Vite**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus/dashboard
npm create vite@latest ui -- --template react-ts
cd ui
npm install
```

- [ ] **5.2 Install additional dependencies**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus/dashboard/ui
npm install react-router-dom recharts
npm install -D tailwindcss postcss autoprefixer @types/recharts
npx tailwindcss init -p
```

- [ ] **5.3 Configure Tailwind**

```javascript
// dashboard/ui/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sidebar: "#ededf5",
        "sidebar-border": "#dddde8",
        "sidebar-active": "rgba(120,90,255,0.10)",
        accent: "#7b5cff",
        "accent-hover": "#6a4de8",
        surface: "#f6f6fa",
        card: "#ffffff",
        "card-border": "#e4e4f0",
        "text-primary": "#1a1a2e",
        "text-secondary": "#6060a0",
        "text-muted": "#9090b0",
        profit: "#16a34a",
        loss: "#dc2626",
        paper: "#2563eb",
      },
    },
  },
  plugins: [],
}
```

- [ ] **5.4 Add Tailwind directives to CSS**

```css
/* dashboard/ui/src/index.css */
@tailwind base;
@tailwind components;
@tailwind utilities;

* { box-sizing: border-box; }
body { margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
```

- [ ] **5.5 Configure Vite proxy (dev) and build output**

```typescript
// dashboard/ui/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  build: {
    outDir: "dist",
  },
});
```

- [ ] **5.6 Replace boilerplate index.html**

```html
<!-- dashboard/ui/index.html -->
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>nautilus+</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **5.7 Verify dev server starts**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus/dashboard/ui
npm run dev
```

Expected: Vite dev server running at `http://localhost:5173` with the default React boilerplate.

- [ ] **5.8 Commit**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus
git add dashboard/ui/
git commit -m "feat(dashboard): scaffold React + Vite + Tailwind frontend"
```

---

## Task 6: TypeScript types and API client

**Files:**
- Create: `dashboard/ui/src/types.ts`
- Create: `dashboard/ui/src/api/client.ts`

- [ ] **6.1 Create shared TypeScript types**

```typescript
// dashboard/ui/src/types.ts

export interface Position {
  ticker: string;
  qty: number;
  avg_px: number;
  last_px: number;
  unrealized_pnl: number;
}

export interface Fill {
  ticker: string;
  side: "BUY" | "SELL" | "SETTLE";
  qty: number;
  price: number;
  pnl: number | null;
  ts: number;
  type: "trade" | "settlement";
}

export interface EquityPoint {
  ts: number;
  equity: number;
}

export interface StrategySnapshot {
  strategy: string;
  mode: "live" | "paper";
  status: "running" | "stopped" | "error";
  ts: number;
  equity: number | null;
  starting_capital: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  total_trades: number | null;
  win_rate: number | null;
  positions: Position[];
  recent_fills: Fill[];
  equity_history: EquityPoint[];
}

export interface StrategySummary {
  name: string;
  display_name: string;
  icon: string;
  status: "running" | "stopped" | "error";
  mode: "live" | "paper";
  equity: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  total_trades: number | null;
  win_rate: number | null;
}

export interface WsMessage {
  snapshots: StrategySnapshot[];
}
```

- [ ] **6.2 Create REST API client**

```typescript
// dashboard/ui/src/api/client.ts
import type { StrategySummary } from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) throw new Error(`GET ${path} failed: ${resp.status}`);
  return resp.json() as Promise<T>;
}

export const api = {
  strategies: (): Promise<StrategySummary[]> => get("/strategies"),
};
```

- [ ] **6.3 Commit**

```bash
git add dashboard/ui/src/types.ts dashboard/ui/src/api/
git commit -m "feat(dashboard): add TypeScript types and REST API client"
```

---

## Task 7: WebSocket hook and strategy state hook

**Files:**
- Create: `dashboard/ui/src/hooks/useWebSocket.ts`
- Create: `dashboard/ui/src/hooks/useStrategyState.ts`

- [ ] **7.1 Create WebSocket hook**

```typescript
// dashboard/ui/src/hooks/useWebSocket.ts
import { useEffect, useRef, useCallback } from "react";
import type { WsMessage } from "../types";

const WS_URL = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
const RECONNECT_MS = 2_000;

export function useWebSocket(onMessage: (msg: WsMessage) => void): void {
  const wsRef = useRef<WebSocket | null>(null);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const connect = useCallback(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data) as WsMessage;
        onMessageRef.current(msg);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setTimeout(connect, RECONNECT_MS);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);
}
```

- [ ] **7.2 Create strategy state hook**

```typescript
// dashboard/ui/src/hooks/useStrategyState.ts
import { useState, useCallback } from "react";
import type { StrategySnapshot, WsMessage } from "../types";
import { useWebSocket } from "./useWebSocket";

type SnapshotMap = Record<string, StrategySnapshot>;

export function useStrategyState(): SnapshotMap {
  const [snapshots, setSnapshots] = useState<SnapshotMap>({});

  const handleMessage = useCallback((msg: WsMessage) => {
    setSnapshots((prev) => {
      const next = { ...prev };
      for (const snap of msg.snapshots) {
        next[snap.strategy] = snap;
      }
      return next;
    });
  }, []);

  useWebSocket(handleMessage);

  return snapshots;
}
```

- [ ] **7.3 Commit**

```bash
git add dashboard/ui/src/hooks/
git commit -m "feat(dashboard): add WebSocket and strategy state hooks"
```

---

## Task 8: Sidebar component

**Files:**
- Create: `dashboard/ui/src/components/Sidebar.tsx`

- [ ] **8.1 Implement Sidebar**

```tsx
// dashboard/ui/src/components/Sidebar.tsx
import { NavLink } from "react-router-dom";
import type { StrategySummary } from "../types";

interface Props {
  strategies: StrategySummary[];
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-profit shadow-[0_0_5px_rgba(22,163,74,0.6)]",
    paper:   "bg-paper  shadow-[0_0_5px_rgba(37,99,235,0.4)]",
    stopped: "bg-[#c8c8d8]",
    error:   "bg-loss",
  };
  return (
    <span
      className={`ml-auto w-1.5 h-1.5 rounded-full flex-shrink-0 ${colors[status] ?? colors.stopped}`}
    />
  );
}

function SidebarLink({
  to,
  icon,
  label,
  indicator,
}: {
  to: string;
  icon: string;
  label: string;
  indicator?: React.ReactNode;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 px-4 py-1.5 text-xs cursor-pointer border-r-2 transition-colors ${
          isActive
            ? "bg-sidebar-active text-accent font-semibold border-accent"
            : "text-text-secondary border-transparent hover:bg-sidebar-active/50 hover:text-text-primary"
        }`
      }
    >
      <span className="w-4 text-center opacity-75">{icon}</span>
      <span>{label}</span>
      {indicator}
    </NavLink>
  );
}

export function Sidebar({ strategies }: Props) {
  const anyLive = strategies.some((s) => s.status === "running");

  return (
    <aside className="w-[200px] bg-sidebar border-r border-sidebar-border flex flex-col flex-shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-4 border-b border-sidebar-border">
        <span className="text-sm font-extrabold tracking-tight text-text-primary">
          nautilus<span className="text-accent">+</span>
        </span>
        {anyLive && (
          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#f0fdf4] text-profit border border-[#bbf7d0]">
            LIVE
          </span>
        )}
      </div>

      {/* Strategies */}
      <div className="pt-3">
        <p className="px-4 pb-1 text-[9.5px] font-bold text-text-muted uppercase tracking-widest">
          Strategies
        </p>
        {strategies.map((s) => (
          <SidebarLink
            key={s.name}
            to={`/strategy/${s.name}`}
            icon={s.icon}
            label={s.display_name}
            indicator={<StatusDot status={s.status} />}
          />
        ))}
      </div>

      <div className="my-2 mx-4 border-t border-sidebar-border" />

      {/* Research */}
      <div>
        <p className="px-4 pb-1 text-[9.5px] font-bold text-text-muted uppercase tracking-widest">
          Research
        </p>
        <SidebarLink to="/backtest" icon="▶" label="Run Backtest" />
        <SidebarLink to="/backtest/history" icon="⊡" label="Backtest History" />
      </div>

      {/* Footer */}
      <div className="mt-auto px-4 py-3 border-t border-sidebar-border flex items-center gap-2">
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-accent to-purple-400 flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0">
          E
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold text-text-secondary truncate">nautilus-plus</p>
          <p className="text-[9.5px] text-text-muted">Mac Mini · LAN</p>
        </div>
        <button className="ml-auto text-text-muted text-sm">⚙</button>
      </div>
    </aside>
  );
}
```

- [ ] **8.2 Commit**

```bash
git add dashboard/ui/src/components/Sidebar.tsx
git commit -m "feat(dashboard): add Sidebar component with strategy nav and status dots"
```

---

## Task 9: TopBar component

**Files:**
- Create: `dashboard/ui/src/components/TopBar.tsx`

- [ ] **9.1 Implement TopBar**

```tsx
// dashboard/ui/src/components/TopBar.tsx
import type { StrategySnapshot } from "../types";

interface Props {
  snapshot: StrategySnapshot | null;
  displayName: string;
}

function StatusPill({ status, mode }: { status: string; mode: string }) {
  const configs: Record<string, { bg: string; text: string; border: string; label: string }> = {
    running: { bg: "bg-[#f0fdf4]", text: "text-profit", border: "border-[#bbf7d0]", label: "● Running" },
    paper:   { bg: "bg-[#eff6ff]", text: "text-paper",  border: "border-[#bfdbfe]", label: "◎ Paper" },
    stopped: { bg: "bg-[#f5f5f8]", text: "text-text-muted", border: "border-card-border", label: "○ Stopped" },
  };
  const key = status === "running" && mode === "paper" ? "paper" : status;
  const c = configs[key] ?? configs.stopped;
  return (
    <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full border ${c.bg} ${c.text} ${c.border}`}>
      {c.label}
    </span>
  );
}

export function TopBar({ snapshot, displayName }: Props) {
  const mode = snapshot?.mode ?? "paper";
  const status = snapshot?.status ?? "stopped";
  const modeLabel = mode === "live" ? "Live" : "Paper";

  return (
    <header className="h-[52px] bg-card border-b border-card-border px-5 flex items-center justify-between flex-shrink-0">
      <div className="flex items-center gap-3">
        <h1 className="text-[15px] font-bold text-text-primary">
          {displayName} — {modeLabel}
        </h1>
        <StatusPill status={status} mode={mode} />
      </div>
      <div className="flex gap-2">
        <button
          disabled
          className="text-[11.5px] font-semibold px-3.5 py-1.5 rounded-lg border border-card-border text-text-secondary opacity-50 cursor-not-allowed"
          title="Strategy control coming in Stage 2"
        >
          Edit Config
        </button>
        <button
          disabled
          className="text-[11.5px] font-semibold px-3.5 py-1.5 rounded-lg bg-[#fef2f2] text-loss border border-[#fecaca] opacity-50 cursor-not-allowed"
          title="Strategy control coming in Stage 2"
        >
          Stop Strategy
        </button>
      </div>
    </header>
  );
}
```

- [ ] **9.2 Commit**

```bash
git add dashboard/ui/src/components/TopBar.tsx
git commit -m "feat(dashboard): add TopBar component with status pill"
```

---

## Task 10: KPI Cards component

**Files:**
- Create: `dashboard/ui/src/components/KpiCards.tsx`

- [ ] **10.1 Implement KpiCards**

```tsx
// dashboard/ui/src/components/KpiCards.tsx
import type { StrategySnapshot } from "../types";

function fmt(n: number | null, prefix = ""): string {
  if (n === null || n === undefined) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${prefix}${sign}${n.toFixed(2)}`;
}

function fmtPct(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

interface KpiProps {
  label: string;
  value: string;
  valueClass?: string;
  sub?: string;
  subClass?: string;
}

function Kpi({ label, value, valueClass = "", sub, subClass = "text-text-muted" }: KpiProps) {
  return (
    <div className="bg-card border border-card-border rounded-xl px-3.5 py-3 shadow-sm">
      <p className="text-[10.5px] text-text-muted uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-xl font-bold tracking-tight ${valueClass}`}>{value}</p>
      {sub && <p className={`text-[10px] mt-0.5 ${subClass}`}>{sub}</p>}
    </div>
  );
}

interface Props {
  snapshot: StrategySnapshot | null;
}

export function KpiCards({ snapshot }: Props) {
  if (!snapshot || snapshot.status === "stopped") {
    return (
      <div className="grid grid-cols-5 gap-2.5">
        {["Realized P&L", "Unrealized P&L", "Total Trades", "Win Rate", "Equity"].map((label) => (
          <Kpi key={label} label={label} value="—" />
        ))}
      </div>
    );
  }

  const { realized_pnl, unrealized_pnl, total_trades, win_rate, equity, starting_capital, positions } = snapshot;
  const equityPct = equity && starting_capital ? ((equity - starting_capital) / starting_capital) * 100 : null;

  return (
    <div className="grid grid-cols-5 gap-2.5">
      <Kpi
        label="Realized P&L"
        value={`$${fmt(realized_pnl)}`}
        valueClass={realized_pnl !== null && realized_pnl >= 0 ? "text-profit" : "text-loss"}
        sub="all-time"
      />
      <Kpi
        label="Unrealized P&L"
        value={`$${fmt(unrealized_pnl)}`}
        valueClass={unrealized_pnl !== null && unrealized_pnl >= 0 ? "text-profit" : "text-loss"}
        sub={`${positions.length} open position${positions.length !== 1 ? "s" : ""}`}
      />
      <Kpi
        label="Total Trades"
        value={total_trades?.toString() ?? "—"}
        sub="fills (trades + settlements)"
      />
      <Kpi
        label="Win Rate"
        value={fmtPct(win_rate)}
        valueClass="text-accent"
        sub={win_rate !== null ? "settled positions" : "no settlements yet"}
      />
      <Kpi
        label="Equity"
        value={equity !== null ? `$${equity.toFixed(2)}` : "—"}
        sub={equityPct !== null ? `${equityPct >= 0 ? "+" : ""}${equityPct.toFixed(2)}% all-time` : undefined}
        subClass={equityPct !== null && equityPct >= 0 ? "text-profit" : "text-loss"}
      />
    </div>
  );
}
```

- [ ] **10.2 Commit**

```bash
git add dashboard/ui/src/components/KpiCards.tsx
git commit -m "feat(dashboard): add KpiCards component"
```

---

## Task 11: Equity Chart component

**Files:**
- Create: `dashboard/ui/src/components/EquityChart.tsx`

- [ ] **11.1 Implement EquityChart with Recharts**

```tsx
// dashboard/ui/src/components/EquityChart.tsx
import {
  AreaChart, Area, XAxis, YAxis, ResponsiveContainer,
  Tooltip, CartesianGrid,
} from "recharts";
import type { EquityPoint } from "../types";

interface Props {
  history: EquityPoint[];
  startingCapital: number;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDollar(val: number): string {
  return `$${val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function EquityChart({ history, startingCapital }: Props) {
  if (history.length < 2) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-sm">
        Waiting for data...
      </div>
    );
  }

  // Downsample to max 300 points to keep rendering fast
  const step = Math.max(1, Math.floor(history.length / 300));
  const data = history.filter((_, i) => i % step === 0 || i === history.length - 1);

  const equities = data.map((d) => d.equity);
  const minEq = Math.min(...equities, startingCapital);
  const maxEq = Math.max(...equities, startingCapital);
  const padding = (maxEq - minEq) * 0.1 || 10;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#7b5cff" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#7b5cff" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f8" vertical={false} />
        <XAxis
          dataKey="ts"
          tickFormatter={formatTime}
          tick={{ fontSize: 9, fill: "#c0c0d8" }}
          tickLine={false}
          axisLine={false}
          minTickGap={60}
        />
        <YAxis
          domain={[minEq - padding, maxEq + padding]}
          tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
          tick={{ fontSize: 9, fill: "#c0c0d8" }}
          tickLine={false}
          axisLine={false}
          width={46}
        />
        <Tooltip
          formatter={(val: number) => [formatDollar(val), "Equity"]}
          labelFormatter={(ts: number) => formatTime(ts)}
          contentStyle={{
            background: "#fff", border: "1px solid #e4e4f0",
            borderRadius: 8, fontSize: 11,
          }}
        />
        <Area
          type="monotone"
          dataKey="equity"
          stroke="#7b5cff"
          strokeWidth={2}
          fill="url(#equityGrad)"
          dot={false}
          activeDot={{ r: 4, fill: "#7b5cff", stroke: "#fff", strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **11.2 Commit**

```bash
git add dashboard/ui/src/components/EquityChart.tsx
git commit -m "feat(dashboard): add Recharts equity curve component"
```

---

## Task 12: Positions table and Trade Log components

**Files:**
- Create: `dashboard/ui/src/components/PositionsTable.tsx`
- Create: `dashboard/ui/src/components/TradeLog.tsx`

- [ ] **12.1 Implement PositionsTable**

```tsx
// dashboard/ui/src/components/PositionsTable.tsx
import type { Position } from "../types";

interface Props {
  positions: Position[];
}

export function PositionsTable({ positions }: Props) {
  if (positions.length === 0) {
    return (
      <p className="text-text-muted text-xs py-4 text-center">No open positions</p>
    );
  }

  return (
    <table className="w-full text-xs border-collapse">
      <thead>
        <tr className="border-b border-[#f0f0f8]">
          {["Ticker", "Side", "Qty", "Entry", "Last", "Unr. P&L"].map((h) => (
            <th
              key={h}
              className={`pb-2 font-semibold text-text-muted uppercase tracking-wide text-[9.5px] ${
                h === "Ticker" ? "text-left" : "text-right"
              }`}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => {
          // YES/NO derived from: qty>0 is YES (long), need actual side field
          // For now all paper positions are BUY/YES
          const pnlColor = p.unrealized_pnl >= 0 ? "text-profit" : "text-loss";
          return (
            <tr key={p.ticker} className="border-b border-[#f8f8fc] last:border-0">
              <td className="py-1.5 font-mono font-semibold text-accent text-[11px]">{p.ticker}</td>
              <td className="py-1.5 text-right">
                <span className="bg-[#f0fdf4] text-profit text-[9px] font-bold px-1.5 py-0.5 rounded">
                  YES
                </span>
              </td>
              <td className="py-1.5 text-right text-text-primary">{p.qty}</td>
              <td className="py-1.5 text-right text-text-primary">${p.avg_px.toFixed(2)}</td>
              <td className="py-1.5 text-right text-text-primary">${p.last_px.toFixed(2)}</td>
              <td className={`py-1.5 text-right font-semibold ${pnlColor}`}>
                {p.unrealized_pnl >= 0 ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **12.2 Implement TradeLog**

```tsx
// dashboard/ui/src/components/TradeLog.tsx
import type { Fill } from "../types";

interface Props {
  fills: Fill[];
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

const SIDE_STYLE: Record<string, string> = {
  BUY:    "text-profit font-bold",
  SELL:   "text-loss font-bold",
  SETTLE: "text-accent font-bold",
};

export function TradeLog({ fills }: Props) {
  if (fills.length === 0) {
    return <p className="text-text-muted text-xs py-4 text-center">No trades yet</p>;
  }

  return (
    <div className="max-h-48 overflow-y-auto divide-y divide-[#f4f4f8]">
      {fills.slice(0, 50).map((fill, i) => (
        <div key={i} className="flex items-baseline gap-2 py-1.5 text-[11px]">
          <span className="font-mono text-text-muted text-[10px] flex-shrink-0 w-[52px]">
            {formatTime(fill.ts)}
          </span>
          <span className="font-mono font-semibold text-accent text-[10.5px] flex-shrink-0 w-[150px] truncate">
            {fill.ticker}
          </span>
          <span className={`text-[10px] flex-shrink-0 w-[36px] ${SIDE_STYLE[fill.side] ?? ""}`}>
            {fill.side}
          </span>
          <span className="text-text-secondary flex-1 text-[10.5px]">
            {fill.qty} × ${fill.price.toFixed(2)}
          </span>
          {fill.pnl !== null && fill.pnl !== undefined ? (
            <span className={`font-semibold flex-shrink-0 ${fill.pnl >= 0 ? "text-profit" : "text-loss"}`}>
              {fill.pnl >= 0 ? "+" : ""}${fill.pnl.toFixed(2)}
            </span>
          ) : (
            <span className="text-text-muted flex-shrink-0">open</span>
          )}
        </div>
      ))}
    </div>
  );
}
```

- [ ] **12.3 Commit**

```bash
git add dashboard/ui/src/components/PositionsTable.tsx dashboard/ui/src/components/TradeLog.tsx
git commit -m "feat(dashboard): add PositionsTable and TradeLog components"
```

---

## Task 13: Strategy page assembly

**Files:**
- Create: `dashboard/ui/src/pages/StrategyPage.tsx`

- [ ] **13.1 Implement StrategyPage**

```tsx
// dashboard/ui/src/pages/StrategyPage.tsx
import { useParams } from "react-router-dom";
import type { StrategySummary } from "../types";
import type { SnapshotMap } from "../hooks/useStrategyState";
import { TopBar } from "../components/TopBar";
import { KpiCards } from "../components/KpiCards";
import { EquityChart } from "../components/EquityChart";
import { PositionsTable } from "../components/PositionsTable";
import { TradeLog } from "../components/TradeLog";

interface Props {
  strategies: StrategySummary[];
  snapshots: SnapshotMap;
}

function Card({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-card-border rounded-xl shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#f0f0f8]">
        <span className="text-xs font-semibold text-text-primary">{title}</span>
        {sub && <span className="text-[10.5px] text-text-muted">{sub}</span>}
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  );
}

export function StrategyPage({ strategies, snapshots }: Props) {
  const { name } = useParams<{ name: string }>();
  const strategy = strategies.find((s) => s.name === name);
  const snapshot = name ? snapshots[name] ?? null : null;

  if (!strategy) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted">
        Strategy not found.
      </div>
    );
  }

  const history = snapshot?.equity_history ?? [];
  const startingCapital = snapshot?.starting_capital ?? 10_000;

  return (
    <div className="flex flex-col h-full">
      <TopBar snapshot={snapshot} displayName={strategy.display_name} />
      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3.5">
        <KpiCards snapshot={snapshot} />

        <div className="grid grid-cols-[2fr_1fr] gap-3">
          <Card title="Equity Curve" sub={`$${startingCapital.toLocaleString()} start`}>
            <div className="h-32">
              <EquityChart history={history} startingCapital={startingCapital} />
            </div>
          </Card>
          <Card title="Open Positions" sub={`${snapshot?.positions.length ?? 0} active`}>
            <PositionsTable positions={snapshot?.positions ?? []} />
          </Card>
        </div>

        <Card title="Trade Log" sub="Most recent first">
          <TradeLog fills={snapshot?.recent_fills ?? []} />
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **13.2 Update the SnapshotMap export in the hook**

Add an export to `dashboard/ui/src/hooks/useStrategyState.ts` so `StrategyPage` can import the type:

```typescript
// dashboard/ui/src/hooks/useStrategyState.ts
import { useState, useCallback } from "react";
import type { StrategySnapshot, WsMessage } from "../types";
import { useWebSocket } from "./useWebSocket";

export type SnapshotMap = Record<string, StrategySnapshot>;

export function useStrategyState(): SnapshotMap {
  const [snapshots, setSnapshots] = useState<SnapshotMap>({});

  const handleMessage = useCallback((msg: WsMessage) => {
    setSnapshots((prev) => {
      const next = { ...prev };
      for (const snap of msg.snapshots) {
        next[snap.strategy] = snap;
      }
      return next;
    });
  }, []);

  useWebSocket(handleMessage);

  return snapshots;
}
```

- [ ] **13.3 Commit**

```bash
git add dashboard/ui/src/pages/ dashboard/ui/src/hooks/useStrategyState.ts
git commit -m "feat(dashboard): add StrategyPage assembling all live monitoring components"
```

---

## Task 14: App root and routing

**Files:**
- Modify: `dashboard/ui/src/main.tsx`
- Create: `dashboard/ui/src/App.tsx`

- [ ] **14.1 Implement App.tsx**

```tsx
// dashboard/ui/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { StrategyPage } from "./pages/StrategyPage";
import { useStrategyState } from "./hooks/useStrategyState";
import { api } from "./api/client";
import type { StrategySummary } from "./types";

function BacktestPlaceholder({ title }: { title: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-text-muted gap-2">
      <p className="text-lg font-semibold">{title}</p>
      <p className="text-sm">Coming in Stage 3</p>
    </div>
  );
}

export function App() {
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const snapshots = useStrategyState();

  useEffect(() => {
    api.strategies().then(setStrategies).catch(console.error);
    const id = setInterval(() => {
      api.strategies().then(setStrategies).catch(console.error);
    }, 5_000);
    return () => clearInterval(id);
  }, []);

  const defaultStrategy = strategies[0]?.name;

  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden bg-surface">
        <Sidebar strategies={strategies} />
        <main className="flex-1 overflow-hidden flex flex-col">
          <Routes>
            <Route
              path="/"
              element={
                defaultStrategy ? (
                  <Navigate to={`/strategy/${defaultStrategy}`} replace />
                ) : (
                  <div className="flex items-center justify-center h-full text-text-muted">
                    Loading strategies...
                  </div>
                )
              }
            />
            <Route
              path="/strategy/:name"
              element={<StrategyPage strategies={strategies} snapshots={snapshots} />}
            />
            <Route path="/backtest" element={<BacktestPlaceholder title="Run Backtest" />} />
            <Route path="/backtest/history" element={<BacktestPlaceholder title="Backtest History" />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
```

- [ ] **14.2 Update main.tsx**

```tsx
// dashboard/ui/src/main.tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

- [ ] **14.3 Commit**

```bash
git add dashboard/ui/src/App.tsx dashboard/ui/src/main.tsx
git commit -m "feat(dashboard): add App root with routing and sidebar integration"
```

---

## Task 15: Integration, build, and start script

**Files:**
- Create: `scripts/start_dashboard.sh`

- [ ] **15.1 End-to-end dev test**

With the FastAPI server already running (`uvicorn dashboard.api.main:app --reload --port 8000`):

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus/dashboard/ui
npm run dev
```

Open `http://localhost:5173` in a browser.

Expected:
- Sidebar loads with MLB Burst (⚡) and Threshold (↕) — both showing stopped (gray dot)
- Navigating to `/strategy/mlb_burst` shows the strategy page with all `—` KPI values
- No console errors

Now start `paper_trade_mlb.py` in a third terminal:
```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus
python scripts/paper_trade_mlb.py
```

Within 2 seconds the sidebar MLB Burst dot should turn green, KPI cards should populate, and the equity curve should start drawing.

- [ ] **15.2 Build the React app for production**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus/dashboard/ui
npm run build
```

Expected: `dist/` directory created with `index.html` and hashed JS/CSS bundles.

- [ ] **15.3 Verify FastAPI serves the built app**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus
uvicorn dashboard.api.main:app --port 8000
```

Open `http://localhost:8000` — should serve the full React app.

- [ ] **15.4 Create start script**

```bash
#!/usr/bin/env bash
# scripts/start_dashboard.sh
# Starts the nautilus-plus dashboard.
# Usage: bash scripts/start_dashboard.sh [--dev]
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$SCRIPT_DIR/.."
UI_DIR="$ROOT/dashboard/ui"

if [[ "$1" == "--dev" ]]; then
  echo "Starting in development mode (hot reload)..."
  # Start FastAPI in background
  uvicorn dashboard.api.main:app --reload --port 8000 &
  API_PID=$!
  # Start Vite dev server
  cd "$UI_DIR" && npm run dev
  kill "$API_PID"
else
  echo "Building UI..."
  cd "$UI_DIR" && npm run build
  echo "Starting dashboard at http://0.0.0.0:8000"
  cd "$ROOT" && uvicorn dashboard.api.main:app --host 0.0.0.0 --port 8000
fi
```

```bash
chmod +x scripts/start_dashboard.sh
```

- [ ] **15.5 Add .superpowers/ to .gitignore**

```bash
echo ".superpowers/" >> /Users/edbalogh/LiveProjects/nautilus-plus/.gitignore
```

- [ ] **15.6 Run full backend test suite one final time**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus
python -m pytest tests/dashboard/ -v
```

Expected: all tests pass.

- [ ] **15.7 Final commit**

```bash
git add scripts/start_dashboard.sh .gitignore
git commit -m "feat(dashboard): add production start script and .gitignore update

Stage 1 complete — FastAPI orchestrator + React frontend with real-time
live/paper strategy monitoring via WebSocket.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Self-Test Checklist

Before marking Stage 1 complete, verify:

- [ ] `python -m pytest tests/dashboard/ -v` → all pass
- [ ] `npm run build` in `dashboard/ui/` → no TypeScript errors, build succeeds
- [ ] FastAPI starts with `uvicorn dashboard.api.main:app --port 8000`
- [ ] `GET http://localhost:8000/api/strategies` returns both strategies with correct status
- [ ] With `paper_trade_mlb.py` running, WS at `ws://localhost:8000/ws` pushes state every ~1s
- [ ] Browser at `http://localhost:8000` shows full dashboard with live-updating KPIs and equity curve

---

## What's Next (Stage 2)

Stage 2 adds:
- Start/stop strategy processes from the UI (process manager)
- Config editor modal (read/write `strategies/<name>/config.json`)
- Sidebar status indicators update in real time
- `?mode=live|paper` parameter on start

Plan will be written separately once Stage 1 is verified working.
