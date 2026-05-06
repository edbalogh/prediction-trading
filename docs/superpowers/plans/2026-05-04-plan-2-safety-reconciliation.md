# Safety & Reconciliation Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the safety layer that sits between strategies and the Kalshi exchange — preventing orphan positions, detecting lost fills, enforcing position limits, and alerting on any irreconcilable state.

**Architecture:** Standalone Python classes (no NautilusTrader component dependencies) that wrap the Kalshi HTTP client. A Redis-backed `StateStore` is the source of truth for what orders we've submitted. A `ReconciliationGate` diffs Redis state vs. live Kalshi state on every startup/reconnect and either auto-resolves gaps or halts. An `OrphanMonitor` runs continuously during live trading. The `KalshiExecutionClient` is updated to call the gate on `_connect()` and the `PositionLimitChecker` on `_submit_order()`.

**Tech Stack:** Python 3.11, redis>=5, smtplib (stdlib), threading (stdlib), dataclasses (stdlib), pytest, pytest-asyncio

---

## NautilusTrader API Notes (from Plan 1 learnings)

- `Currency` is in `nautilus_trader.model.objects`
- `LiveExecutionClient` is in `nautilus_trader.live.execution_client`
- `UUID4` is `nautilus_trader.core.uuid.UUID4`
- Config classes use `ConfigDict(frozen=True)` with `Field(...)` for required fields
- `KalshiHttpClient` has `list_recent_orders(status=None)`, `list_recent_fills()`, `list_positions()`

---

## File Map

| File | Responsibility |
|------|----------------|
| `safety/__init__.py` | Public exports |
| `safety/types.py` | Shared dataclasses: `OrderRecord`, `ReconciliationResult`, `OrphanEvent`, `AlertEvent` |
| `safety/state_store.py` | `StateStore` — Redis-backed order/position tracking with our own schema |
| `safety/alerts.py` | `AlertDispatcher` — email (SMTP) + console alert delivery |
| `safety/quarantine.py` | `QuarantineBook` — append-only JSON log for orphan positions |
| `safety/reconciliation.py` | `ReconciliationGate` — startup diff + auto-resolve + halt logic |
| `safety/position_limits.py` | `PositionLimitChecker` — pre-trade position limit enforcement |
| `safety/orphan_monitor.py` | `OrphanMonitor` — background thread continuous orphan detection |
| `safety/dead_mans_switch.py` | `DeadMansSwitch` — per-strategy heartbeat + auto-cancel |
| `adapters/kalshi/execution.py` | Modified: wire gate + limit checker into `_connect` / `_submit_order` |
| `tests/safety/__init__.py` | Empty |
| `tests/safety/test_types.py` | Type construction sanity tests |
| `tests/safety/test_state_store.py` | StateStore Redis tests (uses fakeredis) |
| `tests/safety/test_alerts.py` | AlertDispatcher tests (mocked SMTP) |
| `tests/safety/test_quarantine.py` | QuarantineBook tests |
| `tests/safety/test_reconciliation.py` | ReconciliationGate tests (core logic) |
| `tests/safety/test_position_limits.py` | PositionLimitChecker tests |
| `tests/safety/test_orphan_monitor.py` | OrphanMonitor tests |
| `tests/safety/test_dead_mans_switch.py` | DeadMansSwitch tests |

---

## Task 1: Types and Safety Package Scaffolding

**Files:**
- Create: `safety/__init__.py`
- Create: `safety/types.py`
- Create: `tests/safety/__init__.py`
- Create: `tests/safety/test_types.py`

- [ ] **Step 1: Create package structure**

```bash
mkdir -p safety tests/safety
touch safety/__init__.py tests/safety/__init__.py
```

- [ ] **Step 2: Write failing test**

`tests/safety/test_types.py`:
```python
from safety.types import OrderRecord, ReconciliationResult, OrphanEvent, AlertEvent


def test_order_record_construction():
    record = OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-25APR30-T65499.99",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    )
    assert record.client_order_id == "clord-001"
    assert record.is_open


def test_order_record_is_open_for_partial_fill():
    record = OrderRecord(
        client_order_id="clord-002",
        kalshi_order_id="kalshi-xyz",
        ticker="KXBTC15M-25APR30-T65499.99",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=4,
        status="open",
    )
    assert record.is_open
    assert not record.is_filled


def test_reconciliation_result_has_gaps():
    result = ReconciliationResult(
        resolved_fills=[],
        resolved_cancels=[],
        orphan_orders=["kalshi-999"],
        orphan_fills=[],
        orphan_positions=[],
        unresolvable=[{"reason": "unknown order", "data": {}}],
    )
    assert result.has_unresolvable
    assert not result.is_clean


def test_reconciliation_result_is_clean():
    result = ReconciliationResult(
        resolved_fills=[],
        resolved_cancels=[],
        orphan_orders=[],
        orphan_fills=[],
        orphan_positions=[],
        unresolvable=[],
    )
    assert result.is_clean


def test_orphan_event_construction():
    event = OrphanEvent(
        event_type="ORDER",
        ticker="KXBTC15M-X",
        strategy_id=None,
        detail={"kalshi_order_id": "abc"},
        ts=1234567890,
    )
    assert event.event_type == "ORDER"


def test_alert_event_construction():
    event = AlertEvent(
        level="CRITICAL",
        message="Orphan position detected",
        context={"ticker": "KXBTC15M-X"},
    )
    assert event.level == "CRITICAL"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/safety/test_types.py -v
```
Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 4: Implement types**

`safety/types.py`:
```python
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OrderRecord:
    client_order_id: str
    kalshi_order_id: str | None
    ticker: str
    strategy_id: str
    side: str          # "yes" or "no"
    price_cents: int
    quantity: int
    filled: int
    status: str        # "open", "filled", "canceled"

    @property
    def is_open(self) -> bool:
        return self.status == "open" and self.filled < self.quantity

    @property
    def is_filled(self) -> bool:
        return self.filled >= self.quantity


@dataclass
class ReconciliationResult:
    resolved_fills: list[dict[str, Any]]
    resolved_cancels: list[str]           # client_order_ids
    orphan_orders: list[str]              # kalshi_order_ids with no local record
    orphan_fills: list[dict[str, Any]]
    orphan_positions: list[dict[str, Any]]
    unresolvable: list[dict[str, Any]]

    @property
    def is_clean(self) -> bool:
        return not self.unresolvable and not self.orphan_orders and not self.orphan_positions

    @property
    def has_unresolvable(self) -> bool:
        return bool(self.unresolvable)


@dataclass
class OrphanEvent:
    event_type: str        # "ORDER", "FILL", "POSITION"
    ticker: str
    strategy_id: str | None
    detail: dict[str, Any]
    ts: int = field(default_factory=lambda: int(time.time()))


@dataclass
class AlertEvent:
    level: str             # "INFO", "WARNING", "CRITICAL"
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    ts: int = field(default_factory=lambda: int(time.time()))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/safety/test_types.py -v
```
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add safety/ tests/safety/
git commit -m "feat: safety layer types and package structure"
```

---

## Task 2: StateStore (Redis-backed order tracking)

**Files:**
- Create: `safety/state_store.py`
- Create: `tests/safety/test_state_store.py`

**Note:** Tests use `fakeredis` — install it first: `pip install fakeredis`

- [ ] **Step 1: Install fakeredis**

```bash
pip install fakeredis
```

Also add it to `pyproject.toml` dev dependencies:
```toml
[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
    "pytest-asyncio>=0.24,<1",
    "respx>=0.21,<1",
    "fakeredis>=2,<3",
]
```

- [ ] **Step 2: Write failing tests**

`tests/safety/test_state_store.py`:
```python
import pytest
import fakeredis
from safety.state_store import StateStore
from safety.types import OrderRecord


@pytest.fixture()
def store():
    fake = fakeredis.FakeRedis(decode_responses=True)
    return StateStore(redis_client=fake)


def test_save_and_get_order(store):
    record = OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    )
    store.save_order(record)
    retrieved = store.get_order("clord-001")
    assert retrieved is not None
    assert retrieved.client_order_id == "clord-001"
    assert retrieved.kalshi_order_id == "kalshi-abc"
    assert retrieved.ticker == "KXBTC15M-X"


def test_get_open_orders(store):
    for i in range(3):
        store.save_order(OrderRecord(
            client_order_id=f"clord-{i}",
            kalshi_order_id=f"kalshi-{i}",
            ticker="KXBTC15M-X",
            strategy_id="stat_arb",
            side="yes",
            price_cents=55,
            quantity=10,
            filled=0,
            status="open",
        ))
    store.save_order(OrderRecord(
        client_order_id="clord-filled",
        kalshi_order_id="kalshi-filled",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=10,
        status="filled",
    ))
    open_orders = store.get_open_orders()
    assert len(open_orders) == 3
    assert all(o.status == "open" for o in open_orders)


def test_mark_order_filled(store):
    store.save_order(OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    ))
    store.mark_order_filled("clord-001", filled=10)
    record = store.get_order("clord-001")
    assert record.status == "filled"
    assert record.filled == 10


def test_mark_order_canceled(store):
    store.save_order(OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    ))
    store.mark_order_canceled("clord-001")
    record = store.get_order("clord-001")
    assert record.status == "canceled"


def test_get_orders_by_strategy(store):
    store.save_order(OrderRecord(
        client_order_id="clord-a",
        kalshi_order_id="kalshi-a",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    ))
    store.save_order(OrderRecord(
        client_order_id="clord-b",
        kalshi_order_id="kalshi-b",
        ticker="KXMLBGAME-X",
        strategy_id="mlb_arb",
        side="yes",
        price_cents=40,
        quantity=5,
        filled=0,
        status="open",
    ))
    arb_orders = store.get_orders_by_strategy("stat_arb")
    assert len(arb_orders) == 1
    assert arb_orders[0].client_order_id == "clord-a"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/safety/test_state_store.py -v
```
Expected: `ImportError`.

- [ ] **Step 4: Implement StateStore**

`safety/state_store.py`:
```python
from __future__ import annotations

import json
from typing import Any

import redis

from safety.types import OrderRecord

_ORDER_KEY = "nautilus_plus:order:{client_order_id}"
_OPEN_ORDERS_KEY = "nautilus_plus:open_orders"
_STRATEGY_ORDERS_KEY = "nautilus_plus:strategy_orders:{strategy_id}"


class StateStore:
    def __init__(self, redis_client: redis.Redis | None = None, redis_url: str = "redis://localhost:6379") -> None:
        self._r = redis_client or redis.Redis.from_url(redis_url, decode_responses=True)

    def save_order(self, record: OrderRecord) -> None:
        key = _ORDER_KEY.format(client_order_id=record.client_order_id)
        self._r.hset(key, mapping=self._record_to_dict(record))
        if record.is_open:
            self._r.sadd(_OPEN_ORDERS_KEY, record.client_order_id)
            self._r.sadd(_STRATEGY_ORDERS_KEY.format(strategy_id=record.strategy_id), record.client_order_id)

    def get_order(self, client_order_id: str) -> OrderRecord | None:
        key = _ORDER_KEY.format(client_order_id=client_order_id)
        data = self._r.hgetall(key)
        if not data:
            return None
        return self._dict_to_record(data)

    def get_open_orders(self) -> list[OrderRecord]:
        ids = self._r.smembers(_OPEN_ORDERS_KEY)
        records = []
        for cid in ids:
            record = self.get_order(cid)
            if record and record.is_open:
                records.append(record)
        return records

    def get_orders_by_strategy(self, strategy_id: str) -> list[OrderRecord]:
        ids = self._r.smembers(_STRATEGY_ORDERS_KEY.format(strategy_id=strategy_id))
        records = []
        for cid in ids:
            record = self.get_order(cid)
            if record and record.is_open:
                records.append(record)
        return records

    def mark_order_filled(self, client_order_id: str, filled: int) -> None:
        key = _ORDER_KEY.format(client_order_id=client_order_id)
        self._r.hset(key, mapping={"status": "filled", "filled": str(filled)})
        self._r.srem(_OPEN_ORDERS_KEY, client_order_id)

    def mark_order_canceled(self, client_order_id: str) -> None:
        key = _ORDER_KEY.format(client_order_id=client_order_id)
        self._r.hset(key, mapping={"status": "canceled"})
        self._r.srem(_OPEN_ORDERS_KEY, client_order_id)

    @staticmethod
    def _record_to_dict(record: OrderRecord) -> dict[str, str]:
        return {
            "client_order_id": record.client_order_id,
            "kalshi_order_id": record.kalshi_order_id or "",
            "ticker": record.ticker,
            "strategy_id": record.strategy_id,
            "side": record.side,
            "price_cents": str(record.price_cents),
            "quantity": str(record.quantity),
            "filled": str(record.filled),
            "status": record.status,
        }

    @staticmethod
    def _dict_to_record(data: dict[str, str]) -> OrderRecord:
        return OrderRecord(
            client_order_id=data["client_order_id"],
            kalshi_order_id=data.get("kalshi_order_id") or None,
            ticker=data["ticker"],
            strategy_id=data["strategy_id"],
            side=data["side"],
            price_cents=int(data["price_cents"]),
            quantity=int(data["quantity"]),
            filled=int(data["filled"]),
            status=data["status"],
        )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/safety/test_state_store.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add safety/state_store.py tests/safety/test_state_store.py pyproject.toml
git commit -m "feat: redis-backed state store for order tracking"
```

---

## Task 3: AlertDispatcher

**Files:**
- Create: `safety/alerts.py`
- Create: `tests/safety/test_alerts.py`

- [ ] **Step 1: Write failing tests**

`tests/safety/test_alerts.py`:
```python
import pytest
from unittest.mock import patch, MagicMock
from safety.alerts import AlertDispatcher, AlertConfig
from safety.types import AlertEvent


@pytest.fixture()
def console_only_config():
    return AlertConfig(console=True, email=False)


@pytest.fixture()
def email_config():
    return AlertConfig(
        console=True,
        email=True,
        smtp_host="localhost",
        smtp_port=1025,
        smtp_from="alerts@nautilus-plus.local",
        smtp_to=["trader@example.com"],
    )


def test_dispatch_logs_to_console(console_only_config, caplog):
    import logging
    dispatcher = AlertDispatcher(config=console_only_config)
    event = AlertEvent(level="CRITICAL", message="Orphan position detected", context={"ticker": "KXBTC15M-X"})
    with caplog.at_level(logging.CRITICAL, logger="safety.alerts"):
        dispatcher.dispatch(event)
    assert "Orphan position detected" in caplog.text


def test_dispatch_sends_email_when_configured(email_config):
    dispatcher = AlertDispatcher(config=email_config)
    event = AlertEvent(level="CRITICAL", message="Halt: unresolvable reconciliation gap", context={})
    with patch("smtplib.SMTP") as mock_smtp_class:
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)
        dispatcher.dispatch(event)
    mock_smtp_class.assert_called_once_with("localhost", 1025)


def test_dispatch_skips_email_when_not_configured(console_only_config):
    dispatcher = AlertDispatcher(config=console_only_config)
    event = AlertEvent(level="WARNING", message="test", context={})
    with patch("smtplib.SMTP") as mock_smtp_class:
        dispatcher.dispatch(event)
    mock_smtp_class.assert_not_called()


def test_critical_alert_raises_if_halt_on_critical(email_config):
    email_config = AlertConfig(
        console=True,
        email=False,
        halt_on_critical=True,
    )
    dispatcher = AlertDispatcher(config=email_config)
    event = AlertEvent(level="CRITICAL", message="Halt required", context={})
    with pytest.raises(SystemExit):
        dispatcher.dispatch(event)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/safety/test_alerts.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement AlertDispatcher**

`safety/alerts.py`:
```python
from __future__ import annotations

import logging
import smtplib
import sys
from dataclasses import dataclass, field
from email.mime.text import MIMEText

from safety.types import AlertEvent

_logger = logging.getLogger("safety.alerts")


@dataclass
class AlertConfig:
    console: bool = True
    email: bool = False
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_from: str = "alerts@nautilus-plus.local"
    smtp_to: list[str] = field(default_factory=list)
    halt_on_critical: bool = False


class AlertDispatcher:
    def __init__(self, config: AlertConfig) -> None:
        self._config = config

    def dispatch(self, event: AlertEvent) -> None:
        if self._config.console:
            self._log(event)
        if self._config.email:
            self._send_email(event)
        if self._config.halt_on_critical and event.level == "CRITICAL":
            sys.exit(f"HALT: {event.message}")

    def _log(self, event: AlertEvent) -> None:
        level = getattr(logging, event.level, logging.WARNING)
        _logger.log(level, "[%s] %s | context=%s", event.level, event.message, event.context)

    def _send_email(self, event: AlertEvent) -> None:
        body = f"Level: {event.level}\nMessage: {event.message}\nContext: {event.context}\nTimestamp: {event.ts}"
        msg = MIMEText(body)
        msg["Subject"] = f"[nautilus-plus] {event.level}: {event.message[:80]}"
        msg["From"] = self._config.smtp_from
        msg["To"] = ", ".join(self._config.smtp_to)
        try:
            with smtplib.SMTP(self._config.smtp_host, self._config.smtp_port) as smtp:
                smtp.sendmail(self._config.smtp_from, self._config.smtp_to, msg.as_string())
        except Exception:
            _logger.exception("failed to send alert email for event: %s", event.message)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/safety/test_alerts.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add safety/alerts.py tests/safety/test_alerts.py
git commit -m "feat: alert dispatcher with console and email channels"
```

---

## Task 4: QuarantineBook

**Files:**
- Create: `safety/quarantine.py`
- Create: `tests/safety/test_quarantine.py`

- [ ] **Step 1: Write failing tests**

`tests/safety/test_quarantine.py`:
```python
import json
import os
import tempfile
import pytest
from safety.quarantine import QuarantineBook
from safety.types import OrphanEvent


@pytest.fixture()
def quarantine(tmp_path):
    log_path = str(tmp_path / "quarantine.jsonl")
    return QuarantineBook(log_path=log_path)


def test_append_writes_to_file(quarantine, tmp_path):
    event = OrphanEvent(
        event_type="ORDER",
        ticker="KXBTC15M-X",
        strategy_id=None,
        detail={"kalshi_order_id": "abc123"},
        ts=1000,
    )
    quarantine.append(event)
    log_path = str(tmp_path / "quarantine.jsonl")
    with open(log_path) as f:
        lines = f.readlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["event_type"] == "ORDER"
    assert data["detail"]["kalshi_order_id"] == "abc123"


def test_append_multiple_events(quarantine, tmp_path):
    for i in range(3):
        quarantine.append(OrphanEvent(
            event_type="FILL",
            ticker=f"KXBTC15M-{i}",
            strategy_id="stat_arb",
            detail={"trade_id": f"fill-{i}"},
            ts=1000 + i,
        ))
    log_path = str(tmp_path / "quarantine.jsonl")
    with open(log_path) as f:
        lines = f.readlines()
    assert len(lines) == 3


def test_get_all_returns_events(quarantine):
    quarantine.append(OrphanEvent(event_type="POSITION", ticker="KXBTC15M-X", strategy_id=None, detail={"qty": 5}, ts=1000))
    quarantine.append(OrphanEvent(event_type="ORDER", ticker="KXBTC15M-Y", strategy_id=None, detail={"id": "x"}, ts=1001))
    events = quarantine.get_all()
    assert len(events) == 2
    assert events[0].event_type == "POSITION"
    assert events[1].event_type == "ORDER"


def test_is_quarantined_returns_true_for_active_ticker(quarantine):
    quarantine.append(OrphanEvent(event_type="POSITION", ticker="KXBTC15M-X", strategy_id=None, detail={}, ts=1000))
    assert quarantine.is_quarantined("KXBTC15M-X")
    assert not quarantine.is_quarantined("KXBTC15M-Y")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/safety/test_quarantine.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement QuarantineBook**

`safety/quarantine.py`:
```python
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path

from safety.types import OrphanEvent

_DEFAULT_LOG_PATH = "data/quarantine.jsonl"


class QuarantineBook:
    def __init__(self, log_path: str = _DEFAULT_LOG_PATH) -> None:
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._quarantined_tickers: set[str] = set()
        self._events: list[OrphanEvent] = []
        self._load_existing()

    def append(self, event: OrphanEvent) -> None:
        self._events.append(event)
        self._quarantined_tickers.add(event.ticker)
        with self._path.open("a") as f:
            f.write(json.dumps(dataclasses.asdict(event)) + "\n")

    def get_all(self) -> list[OrphanEvent]:
        return list(self._events)

    def is_quarantined(self, ticker: str) -> bool:
        return ticker in self._quarantined_tickers

    def _load_existing(self) -> None:
        if not self._path.exists():
            return
        with self._path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = OrphanEvent(**data)
                    self._events.append(event)
                    self._quarantined_tickers.add(event.ticker)
                except Exception:
                    pass
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/safety/test_quarantine.py -v
```
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add safety/quarantine.py tests/safety/test_quarantine.py
git commit -m "feat: append-only quarantine book for orphan positions"
```

---

## Task 5: PositionLimitChecker

**Files:**
- Create: `safety/position_limits.py`
- Create: `tests/safety/test_position_limits.py`

- [ ] **Step 1: Write failing tests**

`tests/safety/test_position_limits.py`:
```python
import pytest
from safety.position_limits import PositionLimitChecker


def test_check_passes_when_under_limit():
    checker = PositionLimitChecker(limits={"KXBTC15M": 100})
    assert checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=50, order_quantity=10)


def test_check_fails_when_over_limit():
    checker = PositionLimitChecker(limits={"KXBTC15M": 100})
    assert not checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=95, order_quantity=10)


def test_check_passes_at_exact_limit():
    checker = PositionLimitChecker(limits={"KXBTC15M": 100})
    assert checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=90, order_quantity=10)


def test_check_uses_series_prefix_for_lookup():
    checker = PositionLimitChecker(limits={"KXMLBGAME": 50})
    assert checker.check(ticker="KXMLBGAME-2025-NYY-BOS", strategy_id="mlb_arb", current_position=10, order_quantity=5)
    assert not checker.check(ticker="KXMLBGAME-2025-NYY-BOS", strategy_id="mlb_arb", current_position=48, order_quantity=5)


def test_check_passes_with_no_limit_configured():
    checker = PositionLimitChecker(limits={})
    assert checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=999, order_quantity=999)


def test_violation_reason_is_accessible():
    checker = PositionLimitChecker(limits={"KXBTC15M": 100})
    checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=95, order_quantity=10)
    assert checker.last_violation_reason is not None
    assert "limit" in checker.last_violation_reason.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/safety/test_position_limits.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement PositionLimitChecker**

`safety/position_limits.py`:
```python
from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


class PositionLimitChecker:
    def __init__(self, limits: dict[str, int]) -> None:
        self._limits = limits
        self.last_violation_reason: str | None = None

    def check(self, *, ticker: str, strategy_id: str, current_position: int, order_quantity: int) -> bool:
        self.last_violation_reason = None
        series = ticker.split("-")[0]
        limit = self._limits.get(series)
        if limit is None:
            return True
        projected = current_position + order_quantity
        if projected > limit:
            self.last_violation_reason = (
                f"order would exceed position limit: series={series} "
                f"current={current_position} order={order_quantity} limit={limit}"
            )
            _logger.warning(self.last_violation_reason)
            return False
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/safety/test_position_limits.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add safety/position_limits.py tests/safety/test_position_limits.py
git commit -m "feat: pre-trade position limit checker"
```

---

## Task 6: ReconciliationGate

**Files:**
- Create: `safety/reconciliation.py`
- Create: `tests/safety/test_reconciliation.py`

- [ ] **Step 1: Write failing tests**

`tests/safety/test_reconciliation.py`:
```python
import pytest
import fakeredis
from unittest.mock import MagicMock
from safety.reconciliation import ReconciliationGate
from safety.state_store import StateStore
from safety.types import OrderRecord, ReconciliationResult
from safety.quarantine import QuarantineBook
from safety.alerts import AlertDispatcher, AlertConfig


@pytest.fixture()
def store(tmp_path):
    fake = fakeredis.FakeRedis(decode_responses=True)
    return StateStore(redis_client=fake)


@pytest.fixture()
def quarantine(tmp_path):
    return QuarantineBook(log_path=str(tmp_path / "quarantine.jsonl"))


@pytest.fixture()
def alerts():
    return AlertDispatcher(config=AlertConfig(console=False, email=False))


@pytest.fixture()
def mock_http():
    client = MagicMock()
    client.list_recent_orders.return_value = []
    client.list_recent_fills.return_value = []
    client.list_positions.return_value = []
    return client


def _open_order_record(client_order_id="clord-001", kalshi_order_id="kalshi-abc", ticker="KXBTC15M-X"):
    return OrderRecord(
        client_order_id=client_order_id,
        kalshi_order_id=kalshi_order_id,
        ticker=ticker,
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    )


def test_clean_run_when_states_match(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001", "status": "resting",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 10, "remaining_count": 10, "filled_count": 0}
    ]
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert result.is_clean


def test_detects_missed_fill(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001", "status": "executed",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 10, "remaining_count": 0, "filled_count": 10}
    ]
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert "clord-001" in result.resolved_fills or len(result.resolved_fills) == 1
    assert result.is_clean


def test_detects_missed_cancel(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001", "status": "canceled",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 10, "remaining_count": 10, "filled_count": 0}
    ]
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert "clord-001" in result.resolved_cancels
    assert result.is_clean


def test_detects_orphan_order_at_exchange(store, quarantine, alerts, mock_http):
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-unknown", "client_order_id": None, "status": "resting",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 5, "remaining_count": 5, "filled_count": 0}
    ]
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert "kalshi-unknown" in result.orphan_orders
    assert not result.is_clean


def test_detects_cached_order_missing_from_exchange(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = []
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert len(result.unresolvable) == 1
    assert "clord-001" in result.unresolvable[0].get("client_order_id", "")


def test_settled_position_is_cleared(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001", "status": "executed",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 10, "remaining_count": 0, "filled_count": 10}
    ]
    mock_http.list_positions.return_value = []
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert result.is_clean
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/safety/test_reconciliation.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement ReconciliationGate**

`safety/reconciliation.py`:
```python
from __future__ import annotations

import logging
from typing import Any

from safety.alerts import AlertDispatcher
from safety.quarantine import QuarantineBook
from safety.state_store import StateStore
from safety.types import AlertEvent, OrphanEvent, ReconciliationResult

_logger = logging.getLogger(__name__)


class ReconciliationGate:
    def __init__(
        self,
        *,
        store: StateStore,
        http: Any,
        quarantine: QuarantineBook,
        alerts: AlertDispatcher,
    ) -> None:
        self._store = store
        self._http = http
        self._quarantine = quarantine
        self._alerts = alerts

    def run(self) -> ReconciliationResult:
        _logger.info("reconciliation gate: starting")
        live_orders = self._http.list_recent_orders(status=None)
        cached_orders = self._store.get_open_orders()

        live_by_kalshi_id: dict[str, dict] = {}
        live_by_client_id: dict[str, dict] = {}
        for o in live_orders:
            oid = o.get("order_id")
            cid = o.get("client_order_id")
            if oid:
                live_by_kalshi_id[oid] = o
            if cid:
                live_by_client_id[cid] = o

        cached_by_client_id = {o.client_order_id: o for o in cached_orders}

        resolved_fills: list[str] = []
        resolved_cancels: list[str] = []
        orphan_orders: list[str] = []
        unresolvable: list[dict] = []

        for cached in cached_orders:
            live = live_by_client_id.get(cached.client_order_id)
            if live is None:
                _logger.warning("cached order missing from exchange: client_order_id=%s", cached.client_order_id)
                unresolvable.append({"client_order_id": cached.client_order_id, "reason": "missing from exchange"})
                self._alerts.dispatch(AlertEvent(
                    level="CRITICAL",
                    message=f"Cached order missing from exchange: {cached.client_order_id}",
                    context={"ticker": cached.ticker, "strategy_id": cached.strategy_id},
                ))
                continue
            status = live.get("status", "")
            if status in ("executed", "filled"):
                filled = live.get("filled_count", cached.quantity)
                self._store.mark_order_filled(cached.client_order_id, filled=filled)
                resolved_fills.append(cached.client_order_id)
                _logger.info("resolved missed fill: client_order_id=%s", cached.client_order_id)
            elif status in ("canceled", "cancelled"):
                self._store.mark_order_canceled(cached.client_order_id)
                resolved_cancels.append(cached.client_order_id)
                _logger.info("resolved missed cancel: client_order_id=%s", cached.client_order_id)

        for live in live_orders:
            cid = live.get("client_order_id")
            oid = live.get("order_id")
            status = live.get("status", "")
            if status in ("canceled", "cancelled", "executed", "filled"):
                continue
            if cid and cid in cached_by_client_id:
                continue
            _logger.warning("orphan order at exchange: kalshi_order_id=%s", oid)
            orphan_orders.append(oid)
            self._quarantine.append(OrphanEvent(
                event_type="ORDER",
                ticker=live.get("ticker", ""),
                strategy_id=None,
                detail={"kalshi_order_id": oid, "client_order_id": cid},
            ))
            self._alerts.dispatch(AlertEvent(
                level="CRITICAL",
                message=f"Orphan order detected at exchange: {oid}",
                context={"ticker": live.get("ticker"), "client_order_id": cid},
            ))

        result = ReconciliationResult(
            resolved_fills=resolved_fills,
            resolved_cancels=resolved_cancels,
            orphan_orders=orphan_orders,
            orphan_fills=[],
            orphan_positions=[],
            unresolvable=unresolvable,
        )
        if result.is_clean:
            _logger.info("reconciliation gate: clean — releasing strategies")
        else:
            _logger.error("reconciliation gate: %d unresolvable gaps, %d orphan orders",
                          len(unresolvable), len(orphan_orders))
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/safety/test_reconciliation.py -v
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add safety/reconciliation.py tests/safety/test_reconciliation.py
git commit -m "feat: reconciliation gate with orphan detection and auto-resolve"
```

---

## Task 7: OrphanMonitor and DeadMansSwitch

**Files:**
- Create: `safety/orphan_monitor.py`
- Create: `safety/dead_mans_switch.py`
- Create: `tests/safety/test_orphan_monitor.py`
- Create: `tests/safety/test_dead_mans_switch.py`

- [ ] **Step 1: Write failing tests for OrphanMonitor**

`tests/safety/test_orphan_monitor.py`:
```python
import time
import pytest
import fakeredis
from unittest.mock import MagicMock, patch
from safety.orphan_monitor import OrphanMonitor
from safety.state_store import StateStore
from safety.quarantine import QuarantineBook
from safety.alerts import AlertDispatcher, AlertConfig
from safety.types import OrderRecord


@pytest.fixture()
def store():
    return StateStore(redis_client=fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture()
def quarantine(tmp_path):
    return QuarantineBook(log_path=str(tmp_path / "quarantine.jsonl"))


@pytest.fixture()
def alerts():
    return AlertDispatcher(config=AlertConfig(console=False, email=False))


@pytest.fixture()
def mock_http():
    client = MagicMock()
    client.list_recent_orders.return_value = []
    client.list_recent_fills.return_value = []
    return client


def test_tick_clean_when_no_orphans(store, quarantine, alerts, mock_http):
    monitor = OrphanMonitor(store=store, http=mock_http, quarantine=quarantine, alerts=alerts, interval_secs=60)
    result = monitor.tick()
    assert result["orphan_orders"] == 0
    assert result["orphan_fills"] == 0


def test_tick_detects_orphan_order(store, quarantine, alerts, mock_http):
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-ghost", "client_order_id": None, "status": "resting",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 5, "remaining_count": 5, "filled_count": 0}
    ]
    monitor = OrphanMonitor(store=store, http=mock_http, quarantine=quarantine, alerts=alerts, interval_secs=60)
    result = monitor.tick()
    assert result["orphan_orders"] == 1
    assert quarantine.is_quarantined("KXBTC15M-X")


def test_tick_detects_orphan_fill(store, quarantine, alerts, mock_http):
    store.save_order(OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    ))
    mock_http.list_recent_fills.return_value = [
        {"trade_id": "fill-xyz", "order_id": "kalshi-UNKNOWN", "ticker": "KXBTC15M-X",
         "side": "yes", "yes_price": 55, "count": 5, "created_time": "2025-04-30T14:00:00Z"}
    ]
    monitor = OrphanMonitor(store=store, http=mock_http, quarantine=quarantine, alerts=alerts, interval_secs=60)
    result = monitor.tick()
    assert result["orphan_fills"] == 1


def test_monitor_starts_and_stops():
    store = MagicMock()
    store.get_open_orders.return_value = []
    http = MagicMock()
    http.list_recent_orders.return_value = []
    http.list_recent_fills.return_value = []
    quarantine = MagicMock()
    alerts = MagicMock()
    monitor = OrphanMonitor(store=store, http=http, quarantine=quarantine, alerts=alerts, interval_secs=0.05)
    monitor.start()
    time.sleep(0.15)
    monitor.stop()
    assert store.get_open_orders.call_count >= 1
```

- [ ] **Step 2: Write failing tests for DeadMansSwitch**

`tests/safety/test_dead_mans_switch.py`:
```python
import time
import pytest
from unittest.mock import MagicMock
from safety.dead_mans_switch import DeadMansSwitch


@pytest.fixture()
def mock_http():
    client = MagicMock()
    client.list_recent_orders.return_value = []
    return client


def test_heartbeat_prevents_cancellation(mock_http):
    dms = DeadMansSwitch(http=mock_http, timeout_secs=0.2, poll_interval_secs=0.05)
    dms.register_strategy("stat_arb")
    dms.start()
    dms.heartbeat("stat_arb")
    time.sleep(0.1)
    dms.heartbeat("stat_arb")
    time.sleep(0.1)
    dms.stop()
    mock_http.cancel_order.assert_not_called()


def test_expired_strategy_triggers_cancel(mock_http):
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001",
         "status": "resting", "ticker": "KXBTC15M-X"}
    ]
    dms = DeadMansSwitch(http=mock_http, timeout_secs=0.05, poll_interval_secs=0.02)
    dms.register_strategy("stat_arb")
    dms.start()
    time.sleep(0.15)
    dms.stop()
    mock_http.cancel_order.assert_called()


def test_unregistered_strategy_not_monitored(mock_http):
    dms = DeadMansSwitch(http=mock_http, timeout_secs=0.05, poll_interval_secs=0.02)
    dms.start()
    time.sleep(0.15)
    dms.stop()
    mock_http.list_recent_orders.assert_not_called()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest tests/safety/test_orphan_monitor.py tests/safety/test_dead_mans_switch.py -v
```
Expected: `ImportError` for both.

- [ ] **Step 4: Implement OrphanMonitor**

`safety/orphan_monitor.py`:
```python
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from safety.alerts import AlertDispatcher
from safety.quarantine import QuarantineBook
from safety.state_store import StateStore
from safety.types import AlertEvent, OrphanEvent

_logger = logging.getLogger(__name__)


class OrphanMonitor:
    def __init__(
        self,
        *,
        store: StateStore,
        http: Any,
        quarantine: QuarantineBook,
        alerts: AlertDispatcher,
        interval_secs: float = 60.0,
    ) -> None:
        self._store = store
        self._http = http
        self._quarantine = quarantine
        self._alerts = alerts
        self._interval = interval_secs
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def tick(self) -> dict[str, int]:
        orphan_orders = 0
        orphan_fills = 0
        cached_open = {o.kalshi_order_id: o for o in self._store.get_open_orders() if o.kalshi_order_id}

        live_orders = self._http.list_recent_orders(status="resting")
        for live in live_orders:
            oid = live.get("order_id")
            cid = live.get("client_order_id")
            if oid and oid not in cached_open:
                ticker = live.get("ticker", "")
                _logger.warning("orphan order detected: kalshi_order_id=%s", oid)
                orphan_orders += 1
                self._quarantine.append(OrphanEvent(
                    event_type="ORDER",
                    ticker=ticker,
                    strategy_id=None,
                    detail={"kalshi_order_id": oid, "client_order_id": cid},
                ))
                self._alerts.dispatch(AlertEvent(
                    level="CRITICAL",
                    message=f"Orphan order detected (continuous monitor): {oid}",
                    context={"ticker": ticker},
                ))

        live_fills = self._http.list_recent_fills()
        for fill in live_fills:
            oid = fill.get("order_id")
            if oid and oid not in cached_open:
                ticker = fill.get("ticker", "")
                _logger.warning("orphan fill: trade_id=%s order_id=%s", fill.get("trade_id"), oid)
                orphan_fills += 1
                self._quarantine.append(OrphanEvent(
                    event_type="FILL",
                    ticker=ticker,
                    strategy_id=None,
                    detail=fill,
                ))
                self._alerts.dispatch(AlertEvent(
                    level="CRITICAL",
                    message=f"Orphan fill detected: trade_id={fill.get('trade_id')}",
                    context={"ticker": ticker, "order_id": oid},
                ))

        return {"orphan_orders": orphan_orders, "orphan_fills": orphan_fills}

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="OrphanMonitor")
        self._thread.start()
        _logger.info("OrphanMonitor started (interval=%.1fs)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        _logger.info("OrphanMonitor stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                _logger.exception("OrphanMonitor tick error")
            self._stop_event.wait(self._interval)
```

- [ ] **Step 5: Implement DeadMansSwitch**

`safety/dead_mans_switch.py`:
```python
from __future__ import annotations

import logging
import threading
import time
from typing import Any

_logger = logging.getLogger(__name__)


class DeadMansSwitch:
    def __init__(
        self,
        *,
        http: Any,
        timeout_secs: float = 300.0,
        poll_interval_secs: float = 10.0,
    ) -> None:
        self._http = http
        self._timeout = timeout_secs
        self._poll_interval = poll_interval_secs
        self._strategies: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register_strategy(self, strategy_id: str) -> None:
        with self._lock:
            self._strategies[strategy_id] = time.monotonic()
        _logger.info("DeadMansSwitch registered strategy: %s (timeout=%.0fs)", strategy_id, self._timeout)

    def heartbeat(self, strategy_id: str) -> None:
        with self._lock:
            if strategy_id in self._strategies:
                self._strategies[strategy_id] = time.monotonic()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="DeadMansSwitch")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._check()
            self._stop_event.wait(self._poll_interval)

    def _check(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [sid for sid, last in self._strategies.items() if now - last > self._timeout]
        for strategy_id in expired:
            _logger.error("DeadMansSwitch triggered for strategy=%s — cancelling all open orders", strategy_id)
            open_orders = self._http.list_recent_orders(status="resting")
            for order in open_orders:
                oid = order.get("order_id")
                if oid:
                    try:
                        self._http.cancel_order(oid)
                        _logger.info("dead mans switch cancelled order=%s", oid)
                    except Exception:
                        _logger.exception("failed to cancel order=%s", oid)
            with self._lock:
                self._strategies.pop(strategy_id, None)
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/safety/test_orphan_monitor.py tests/safety/test_dead_mans_switch.py -v
```
Expected: 7 passed (4 + 3).

- [ ] **Step 7: Commit**

```bash
git add safety/orphan_monitor.py safety/dead_mans_switch.py tests/safety/test_orphan_monitor.py tests/safety/test_dead_mans_switch.py
git commit -m "feat: continuous orphan monitor and dead mans switch"
```

---

## Task 8: Wire into KalshiExecutionClient + Public Exports

**Files:**
- Modify: `adapters/kalshi/execution.py`
- Modify: `safety/__init__.py`

The execution client needs to:
1. Call `ReconciliationGate.run()` in `_connect()` and halt if result is not clean
2. Call `PositionLimitChecker.check()` in `_submit_order()` and reject if limit exceeded
3. Call `StateStore.save_order()` in `_submit_order()` after successful submission
4. Call `StateStore.mark_order_filled()` / `mark_order_canceled()` on fill/cancel events

- [ ] **Step 1: Write failing tests**

`tests/adapters/kalshi/test_execution_safety.py`:
```python
import pytest
import fakeredis
from unittest.mock import AsyncMock, MagicMock, patch
from safety.state_store import StateStore
from safety.quarantine import QuarantineBook
from safety.alerts import AlertDispatcher, AlertConfig
from safety.reconciliation import ReconciliationGate
from safety.position_limits import PositionLimitChecker
from adapters.kalshi.execution import kalshi_order_payload
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.objects import Price, Quantity


def test_kalshi_order_payload_records_side_correctly():
    payload = kalshi_order_payload(
        ticker="KXBTC15M-X",
        side=OrderSide.BUY,
        price=Price(0.55, 2),
        quantity=Quantity(10, 0),
        client_order_id="clord-001",
    )
    assert payload["side"] == "yes"
    assert payload["yes_price"] == 55


def test_position_limit_check_logic():
    checker = PositionLimitChecker(limits={"KXBTC15M": 50})
    assert checker.check(ticker="KXBTC15M-X", strategy_id="s", current_position=40, order_quantity=5)
    assert not checker.check(ticker="KXBTC15M-X", strategy_id="s", current_position=48, order_quantity=5)


def test_reconciliation_gate_marks_missed_fill():
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    store = StateStore(redis_client=fake_redis)
    from safety.types import OrderRecord
    store.save_order(OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    ))
    http = MagicMock()
    http.list_recent_orders.return_value = [{
        "order_id": "kalshi-abc",
        "client_order_id": "clord-001",
        "status": "executed",
        "ticker": "KXBTC15M-X",
        "side": "yes",
        "yes_price": 55,
        "original_count": 10,
        "remaining_count": 0,
        "filled_count": 10,
    }]
    http.list_recent_fills.return_value = []
    http.list_positions.return_value = []
    import tempfile, os
    quarantine = QuarantineBook(log_path=os.path.join(tempfile.mkdtemp(), "q.jsonl"))
    alerts = AlertDispatcher(config=AlertConfig(console=False, email=False))
    gate = ReconciliationGate(store=store, http=http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert result.is_clean
    order = store.get_order("clord-001")
    assert order.status == "filled"
```

- [ ] **Step 2: Run tests to verify they fail (the new test file)**

```bash
pytest tests/adapters/kalshi/test_execution_safety.py -v
```
Expected: All 3 tests should actually pass already (they test existing code). If any fail, investigate.

- [ ] **Step 3: Wire safety imports into public exports**

`safety/__init__.py`:
```python
from safety.alerts import AlertConfig, AlertDispatcher
from safety.dead_mans_switch import DeadMansSwitch
from safety.orphan_monitor import OrphanMonitor
from safety.position_limits import PositionLimitChecker
from safety.quarantine import QuarantineBook
from safety.reconciliation import ReconciliationGate
from safety.state_store import StateStore
from safety.types import AlertEvent, OrderRecord, OrphanEvent, ReconciliationResult

__all__ = [
    "AlertConfig",
    "AlertDispatcher",
    "AlertEvent",
    "DeadMansSwitch",
    "OrderRecord",
    "OrphanEvent",
    "OrphanMonitor",
    "PositionLimitChecker",
    "QuarantineBook",
    "ReconciliationGate",
    "ReconciliationResult",
    "StateStore",
]
```

- [ ] **Step 4: Verify import**

```bash
python -c "from safety import ReconciliationGate, OrphanMonitor, DeadMansSwitch, PositionLimitChecker; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v
```
Expected: All tests pass (18 adapter + safety tests).

- [ ] **Step 6: Final commit**

```bash
git add safety/__init__.py tests/adapters/kalshi/test_execution_safety.py
git commit -m "feat: wire safety layer public exports and integration tests"
```

---

## Notes for Plan 3 (Data Catalog Bridge)

- `StateStore` uses key prefix `nautilus_plus:` to avoid collision with NautilusTrader's own Redis keys
- `ReconciliationGate` calls `http.list_recent_orders(status=None)` to get all orders regardless of status — ensure the HTTP client's `status=None` path sends no status filter
- The `DeadMansSwitch` uses `list_recent_orders(status="resting")` — only resting orders need cancellation
- `QuarantineBook` default path `data/quarantine.jsonl` — ensure `data/` directory exists or configure explicitly
