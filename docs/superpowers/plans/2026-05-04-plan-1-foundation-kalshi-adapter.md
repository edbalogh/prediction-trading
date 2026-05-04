# Foundation + Kalshi Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `nautilus-plus` project with a fully functional Kalshi adapter (instrument provider, data client, execution client) that integrates with NautilusTrader's live trading engine.

**Architecture:** Python package built on NautilusTrader. The Kalshi HTTP client is ported directly from `kalshi-agent-trader`. Three adapter classes (`KalshiInstrumentProvider`, `KalshiDataClient`, `KalshiExecutionClient`) wrap that client and translate between Kalshi's API and NautilusTrader's normalized event model. `BinaryOption` is NautilusTrader's built-in instrument type for yes/no contracts.

**Tech Stack:** Python 3.12, NautilusTrader 1.x, httpx, cryptography, websockets, pytest, pytest-asyncio

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project definition, dependencies |
| `adapters/kalshi/__init__.py` | Public exports |
| `adapters/kalshi/config.py` | `KalshiAdapterConfig`, `KalshiDataClientConfig`, `KalshiExecClientConfig` |
| `adapters/kalshi/constants.py` | `KALSHI_VENUE`, price/size precision constants |
| `adapters/kalshi/http/auth.py` | RSA-PSS request signing (ported) |
| `adapters/kalshi/http/client.py` | `KalshiHttpClient` — REST + WebSocket URL builder (ported) |
| `adapters/kalshi/factories.py` | `market_to_binary_option()`, `orderbook_snapshot_to_deltas()`, `fill_to_trade_tick()` |
| `adapters/kalshi/providers.py` | `KalshiInstrumentProvider` |
| `adapters/kalshi/data.py` | `KalshiDataClient` |
| `adapters/kalshi/execution.py` | `KalshiExecutionClient` |
| `tests/adapters/kalshi/http/test_auth.py` | Auth signing tests |
| `tests/adapters/kalshi/http/test_client.py` | HTTP client tests (mocked httpx) |
| `tests/adapters/kalshi/test_factories.py` | Conversion function tests |
| `tests/adapters/kalshi/test_providers.py` | InstrumentProvider tests |
| `tests/adapters/kalshi/test_execution.py` | ExecutionClient tests |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `adapters/__init__.py`
- Create: `adapters/kalshi/__init__.py`
- Create: `adapters/kalshi/http/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/adapters/__init__.py`
- Create: `tests/adapters/kalshi/__init__.py`
- Create: `tests/adapters/kalshi/http/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "nautilus-plus"
version = "0.1.0"
description = "Personal prediction market trading system built on NautilusTrader"
requires-python = ">=3.12"
dependencies = [
    "nautilus_trader>=1.208,<2",
    "httpx>=0.27,<1",
    "cryptography>=42,<45",
    "websockets>=13,<15",
    "redis>=5,<6",
    "pydantic>=2.0,<3",
]

[project.optional-dependencies]
dev = [
    "pytest>=8,<9",
    "pytest-asyncio>=0.24,<1",
    "respx>=0.21,<1",
]

[tool.hatch.build.targets.wheel]
packages = ["adapters", "safety", "catalog", "strategies", "backtest", "live"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty `__init__.py` files**

```bash
touch adapters/__init__.py
touch adapters/kalshi/__init__.py
touch adapters/kalshi/http/__init__.py
touch tests/__init__.py
touch tests/adapters/__init__.py
touch tests/adapters/kalshi/__init__.py
touch tests/adapters/kalshi/http/__init__.py
```

- [ ] **Step 3: Install dependencies**

```bash
pip install -e ".[dev]"
```

Expected: Installation completes. Run `python -c "import nautilus_trader; print(nautilus_trader.__version__)"` to verify.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml adapters/ tests/
git commit -m "feat: project scaffolding and dependencies"
```

---

## Task 2: Auth Module

**Files:**
- Create: `adapters/kalshi/http/auth.py`
- Create: `tests/adapters/kalshi/http/test_auth.py`

- [ ] **Step 1: Write failing test**

`tests/adapters/kalshi/http/test_auth.py`:
```python
import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

from adapters.kalshi.http.auth import sign_request, load_private_key


def _make_test_key() -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()
    return private_pem, public_key


def test_sign_request_returns_base64_string():
    private_pem, _ = _make_test_key()
    key = load_private_key(private_pem.decode())
    signature = sign_request(key, timestamp_ms="1234567890000", method="GET", path="/markets/KXBTC15M")
    decoded = base64.b64decode(signature)
    assert len(decoded) == 256  # RSA-2048 produces 256-byte signatures


def test_sign_request_is_verifiable():
    private_pem, public_key = _make_test_key()
    key = load_private_key(private_pem.decode())
    timestamp_ms = "1234567890000"
    method = "POST"
    path = "/portfolio/orders"
    signature = sign_request(key, timestamp_ms=timestamp_ms, method=method, path=path)
    msg = f"{timestamp_ms}{method}{path}".encode()
    public_key.verify(base64.b64decode(signature), msg, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.DIGEST_LENGTH,
    ), hashes.SHA256())  # raises if invalid


def test_load_private_key_from_pem_string():
    private_pem, _ = _make_test_key()
    key = load_private_key(private_pem.decode())
    assert key is not None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/adapters/kalshi/http/test_auth.py -v
```
Expected: `ImportError` — `adapters.kalshi.http.auth` doesn't exist yet.

- [ ] **Step 3: Implement auth module**

`adapters/kalshi/http/auth.py`:
```python
from __future__ import annotations

import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


def load_private_key(pem_string: str) -> RSAPrivateKey:
    return serialization.load_pem_private_key(pem_string.encode(), password=None)


def sign_request(key: RSAPrivateKey, *, timestamp_ms: str, method: str, path: str) -> str:
    msg = f"{timestamp_ms}{method}{path}".encode()
    signature = key.sign(msg, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.DIGEST_LENGTH,
    ), hashes.SHA256())
    return base64.b64encode(signature).decode()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/adapters/kalshi/http/test_auth.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add adapters/kalshi/http/auth.py tests/adapters/kalshi/http/test_auth.py
git commit -m "feat: kalshi RSA request signing"
```

---

## Task 3: HTTP Client

**Files:**
- Create: `adapters/kalshi/http/client.py`
- Create: `tests/adapters/kalshi/http/test_client.py`

- [ ] **Step 1: Write failing tests**

`tests/adapters/kalshi/http/test_client.py`:
```python
import pytest
import respx
import httpx
from unittest.mock import MagicMock

from adapters.kalshi.http.client import KalshiHttpClient


def _make_client() -> KalshiHttpClient:
    return KalshiHttpClient(
        base_url="https://trading-api.kalshi.com/trade-api/v2",
        api_key="test-key",
        private_key_pem="",  # auth is mocked
    )


@respx.mock
def test_get_market_returns_market_dict():
    respx.get("https://trading-api.kalshi.com/trade-api/v2/markets/KXBTC15M-X").mock(
        return_value=httpx.Response(200, json={"market": {"ticker": "KXBTC15M-X", "status": "open"}})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})  # skip real signing
    result = client.get_market("KXBTC15M-X")
    assert result["ticker"] == "KXBTC15M-X"


@respx.mock
def test_list_markets_paged_returns_list():
    respx.get("https://trading-api.kalshi.com/trade-api/v2/markets").mock(
        return_value=httpx.Response(200, json={"markets": [{"ticker": "A"}, {"ticker": "B"}], "cursor": ""})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})
    result = client.list_markets_paged(status="open", pages=1)
    assert len(result) == 2
    assert result[0]["ticker"] == "A"


@respx.mock
def test_place_order_returns_order_id():
    respx.post("https://trading-api.kalshi.com/trade-api/v2/portfolio/orders").mock(
        return_value=httpx.Response(200, json={"order": {"order_id": "abc123", "status": "resting"}})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})
    result = client.place_order({"ticker": "KXBTC15M-X", "side": "yes", "count": 10, "type": "limit", "yes_price": 55})
    assert result["kalshi_order_id"] == "abc123"


@respx.mock
def test_cancel_order_succeeds():
    respx.delete("https://trading-api.kalshi.com/trade-api/v2/portfolio/orders/abc123").mock(
        return_value=httpx.Response(200, json={"order": {"order_id": "abc123", "status": "canceled"}})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})
    result = client.cancel_order("abc123")
    assert result["status"] == "canceled"


@respx.mock
def test_list_positions_returns_list():
    respx.get("https://trading-api.kalshi.com/trade-api/v2/portfolio/positions").mock(
        return_value=httpx.Response(200, json={"market_positions": [{"ticker": "KXBTC15M-X", "position": 5}], "cursor": ""})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})
    result = client.list_positions()
    assert len(result) == 1
    assert result[0]["ticker"] == "KXBTC15M-X"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/adapters/kalshi/http/test_client.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement HTTP client**

`adapters/kalshi/http/client.py`:
```python
from __future__ import annotations

import time
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from adapters.kalshi.http.auth import load_private_key, sign_request

_RETRYABLE = {429, 500, 502, 503, 504}


class KalshiHttpClient:
    def __init__(self, *, base_url: str, api_key: str, private_key_pem: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._key: RSAPrivateKey | None = load_private_key(private_key_pem) if private_key_pem else None

    # ── Instruments ──────────────────────────────────────────────────────────

    def get_market(self, ticker: str) -> dict[str, Any]:
        data = self._request("GET", f"/markets/{ticker}")
        return data.get("market", data)

    def list_markets_paged(
        self,
        *,
        status: str | None = "open",
        series_ticker: str | None = None,
        limit: int = 1000,
        pages: int = 10,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(pages):
            params: dict[str, Any] = {"limit": limit}
            if status:
                params["status"] = status
            if series_ticker:
                params["series_ticker"] = series_ticker
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/markets", params=params)
            results.extend(data.get("markets", []))
            cursor = data.get("cursor", "")
            if not cursor:
                break
        return results

    def get_orderbook(self, ticker: str) -> dict[str, Any]:
        return self._request("GET", f"/markets/{ticker}/orderbook")

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/portfolio/orders", json=payload)
        order = data.get("order", data)
        return {
            "kalshi_order_id": order.get("order_id") or order.get("id"),
            "status": order.get("status", "accepted"),
            "raw": data,
        }

    def cancel_order(self, kalshi_order_id: str) -> dict[str, Any]:
        data = self._request("DELETE", f"/portfolio/orders/{kalshi_order_id}")
        return data.get("order", data)

    def list_recent_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        data = self._request("GET", "/portfolio/orders", params={"limit": limit, "status": "resting"})
        return data.get("orders", [])

    def list_recent_fills(self, limit: int = 100) -> list[dict[str, Any]]:
        data = self._request("GET", "/portfolio/fills", params={"limit": limit})
        return data.get("fills", [])

    # ── Positions ─────────────────────────────────────────────────────────────

    def list_positions(self, limit: int = 1000, pages: int = 10) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(pages):
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/portfolio/positions", params=params)
            results.extend(data.get("market_positions", []))
            cursor = data.get("cursor", "")
            if not cursor:
                break
        return results

    # ── WebSocket ─────────────────────────────────────────────────────────────

    def websocket_url(self) -> str:
        base = self._base_url.replace("/trade-api/v2", "")
        return base.replace("https://", "wss://") + "/trade-api/ws/v2"

    def websocket_headers(self) -> dict[str, str]:
        path = "/trade-api/ws/v2"
        ts_ms = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": sign_request(self._key, timestamp_ms=ts_ms, method="GET", path=path),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sign_headers(self, method: str, path: str) -> dict[str, str]:
        ts_ms = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": sign_request(self._key, timestamp_ms=ts_ms, method=method, path=path),
        }

    def _request(
        self,
        method: str,
        api_path: str,
        json: dict | None = None,
        params: dict | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        url = self._base_url + api_path
        headers = self._sign_headers(method, api_path) if self._key else {}
        for attempt in range(retries):
            with httpx.Client(timeout=10) as client:
                response = client.request(method, url, json=json, params=params, headers=headers)
            if response.status_code not in _RETRYABLE or attempt == retries - 1:
                response.raise_for_status()
                return response.json()
            time.sleep(2 ** attempt)
        raise RuntimeError("unreachable")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/adapters/kalshi/http/test_client.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add adapters/kalshi/http/client.py tests/adapters/kalshi/http/test_client.py
git commit -m "feat: kalshi HTTP client with retry and signing"
```

---

## Task 4: Constants and Config

**Files:**
- Create: `adapters/kalshi/constants.py`
- Create: `adapters/kalshi/config.py`

- [ ] **Step 1: Write constants**

`adapters/kalshi/constants.py`:
```python
from nautilus_trader.model.identifiers import Venue

KALSHI_VENUE = Venue("KALSHI")

KALSHI_BASE_URL = "https://trading-api.kalshi.com/trade-api/v2"
KALSHI_DEMO_URL = "https://demo-api.kalshi.co/trade-api/v2"

PRICE_PRECISION = 2      # Kalshi prices are cents: 0.01 to 1.00
SIZE_PRECISION = 0       # Contracts are whole numbers
PRICE_INCREMENT = 0.01
SIZE_INCREMENT = 1
```

- [ ] **Step 2: Write config**

`adapters/kalshi/config.py`:
```python
from __future__ import annotations

from nautilus_trader.config import LiveDataClientConfig, LiveExecClientConfig

from adapters.kalshi.constants import KALSHI_BASE_URL


class KalshiDataClientConfig(LiveDataClientConfig, frozen=True):
    api_key: str
    private_key_pem: str
    base_url: str = KALSHI_BASE_URL
    ws_reconnect_delay_secs: float = 1.0
    ws_reconnect_max_delay_secs: float = 30.0


class KalshiExecClientConfig(LiveExecClientConfig, frozen=True):
    api_key: str
    private_key_pem: str
    base_url: str = KALSHI_BASE_URL
    reconcile_on_connect: bool = True
```

- [ ] **Step 3: Verify imports work**

```bash
python -c "from adapters.kalshi.constants import KALSHI_VENUE; from adapters.kalshi.config import KalshiDataClientConfig; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add adapters/kalshi/constants.py adapters/kalshi/config.py
git commit -m "feat: kalshi adapter constants and config"
```

---

## Task 5: Factories (Market Data Conversion)

**Files:**
- Create: `adapters/kalshi/factories.py`
- Create: `tests/adapters/kalshi/test_factories.py`

- [ ] **Step 1: Write failing tests**

`tests/adapters/kalshi/test_factories.py`:
```python
import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.enums import AggressorSide

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.factories import (
    market_to_binary_option,
    kalshi_ticker_to_instrument_id,
    orderbook_snapshot_to_deltas,
    fill_to_trade_tick,
)


SAMPLE_MARKET = {
    "ticker": "KXBTC15M-25APR30-T65499.99",
    "series_ticker": "KXBTC15M",
    "status": "open",
    "yes_bid": 55,
    "yes_ask": 57,
    "close_time": "2025-04-30T15:00:00Z",
    "result": "",
    "title": "Will BTC be above $65,499.99 at 3pm?",
}

SAMPLE_ORDERBOOK = {
    "ticker": "KXBTC15M-25APR30-T65499.99",
    "orderbook": {
        "yes": [[55, 100], [54, 200]],
        "no": [[44, 150], [43, 75]],
    },
}

SAMPLE_FILL = {
    "trade_id": "fill-001",
    "ticker": "KXBTC15M-25APR30-T65499.99",
    "side": "yes",
    "yes_price": 55,
    "count": 10,
    "created_time": "2025-04-30T14:00:00Z",
    "is_taker": True,
}


def test_market_to_binary_option_returns_binary_option():
    instrument = market_to_binary_option(SAMPLE_MARKET)
    assert isinstance(instrument, BinaryOption)
    assert instrument.id.symbol.value == "KXBTC15M-25APR30-T65499.99"
    assert instrument.id.venue == KALSHI_VENUE


def test_kalshi_ticker_to_instrument_id():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-25APR30-T65499.99")
    assert instrument_id == InstrumentId(Symbol("KXBTC15M-25APR30-T65499.99"), KALSHI_VENUE)


def test_orderbook_snapshot_to_deltas_returns_list():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-25APR30-T65499.99")
    deltas = orderbook_snapshot_to_deltas(SAMPLE_ORDERBOOK, instrument_id=instrument_id, ts_event=1000, ts_init=1000)
    assert len(deltas) > 0


def test_fill_to_trade_tick_returns_trade_tick():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-25APR30-T65499.99")
    tick = fill_to_trade_tick(SAMPLE_FILL, instrument_id=instrument_id, ts_init=1000)
    assert tick.price.as_double() == pytest.approx(0.55)
    assert tick.size.as_double() == 10.0
    assert tick.aggressor_side == AggressorSide.BUYER
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/adapters/kalshi/test_factories.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement factories**

`adapters/kalshi/factories.py`:
```python
from __future__ import annotations

from datetime import datetime, timezone

from nautilus_trader.model.data import OrderBookDelta, TradeTick
from nautilus_trader.model.enums import AggressorSide, BookAction, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TradeId
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.objects import Price, Quantity, Money
from nautilus_trader.model.identifiers import Currency

from adapters.kalshi.constants import (
    KALSHI_VENUE,
    PRICE_PRECISION,
    SIZE_PRECISION,
    PRICE_INCREMENT,
    SIZE_INCREMENT,
)


def kalshi_ticker_to_instrument_id(ticker: str) -> InstrumentId:
    return InstrumentId(Symbol(ticker), KALSHI_VENUE)


def market_to_binary_option(market: dict) -> BinaryOption:
    ticker = market["ticker"]
    instrument_id = kalshi_ticker_to_instrument_id(ticker)

    close_time = market.get("close_time", "")
    if close_time:
        expiration_ns = int(datetime.fromisoformat(close_time.replace("Z", "+00:00")).timestamp() * 1e9)
    else:
        expiration_ns = 0

    return BinaryOption(
        instrument_id=instrument_id,
        raw_symbol=Symbol(ticker),
        asset_class=1,  # AssetClass.ALTERNATIVE
        currency=Currency.from_str("USD"),
        price_precision=PRICE_PRECISION,
        price_increment=Price(PRICE_INCREMENT, PRICE_PRECISION),
        size_precision=SIZE_PRECISION,
        size_increment=Quantity(SIZE_INCREMENT, SIZE_PRECISION),
        activation_ns=0,
        expiration_ns=expiration_ns,
        max_quantity=None,
        min_quantity=Quantity(1, SIZE_PRECISION),
        max_notional=None,
        min_notional=None,
        max_price=Price(1.00, PRICE_PRECISION),
        min_price=Price(0.01, PRICE_PRECISION),
        margin_init=None,
        margin_maint=None,
        maker_fee=None,
        taker_fee=None,
        ts_event=0,
        ts_init=0,
        outcome=market.get("title", ticker),
        description=market.get("title", ""),
    )


def orderbook_snapshot_to_deltas(
    snapshot: dict,
    *,
    instrument_id: InstrumentId,
    ts_event: int,
    ts_init: int,
) -> list[OrderBookDelta]:
    deltas: list[OrderBookDelta] = []
    orderbook = snapshot.get("orderbook", {})

    for price_cents, size in orderbook.get("yes", []):
        deltas.append(OrderBookDelta.from_dict({
            "instrument_id": str(instrument_id),
            "action": BookAction.ADD,
            "order": {
                "side": OrderSide.BUY,
                "price": round(price_cents / 100, PRICE_PRECISION),
                "size": size,
                "order_id": 0,
            },
            "flags": 0,
            "sequence": 0,
            "ts_event": ts_event,
            "ts_init": ts_init,
        }))

    for price_cents, size in orderbook.get("no", []):
        yes_price_cents = 100 - price_cents
        deltas.append(OrderBookDelta.from_dict({
            "instrument_id": str(instrument_id),
            "action": BookAction.ADD,
            "order": {
                "side": OrderSide.SELL,
                "price": round(yes_price_cents / 100, PRICE_PRECISION),
                "size": size,
                "order_id": 0,
            },
            "flags": 0,
            "sequence": 0,
            "ts_event": ts_event,
            "ts_init": ts_init,
        }))

    return deltas


def fill_to_trade_tick(
    fill: dict,
    *,
    instrument_id: InstrumentId,
    ts_init: int,
) -> TradeTick:
    price_cents = fill.get("yes_price") or (100 - fill.get("no_price", 0))
    price = round(price_cents / 100, PRICE_PRECISION)
    size = fill["count"]
    is_taker = fill.get("is_taker", True)
    side = fill.get("side", "yes")

    if side == "yes":
        aggressor = AggressorSide.BUYER if is_taker else AggressorSide.SELLER
    else:
        aggressor = AggressorSide.SELLER if is_taker else AggressorSide.BUYER

    created = fill.get("created_time", "")
    if created:
        ts_event = int(datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() * 1e9)
    else:
        ts_event = ts_init

    return TradeTick(
        instrument_id=instrument_id,
        price=Price(price, PRICE_PRECISION),
        size=Quantity(size, SIZE_PRECISION),
        aggressor_side=aggressor,
        trade_id=TradeId(fill.get("trade_id", "unknown")),
        ts_event=ts_event,
        ts_init=ts_init,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/adapters/kalshi/test_factories.py -v
```
Expected: 4 passed. If `BinaryOption` constructor signature differs from installed version, adjust to match — run `python -c "from nautilus_trader.model.instruments import BinaryOption; help(BinaryOption.__init__)"` to inspect.

- [ ] **Step 5: Commit**

```bash
git add adapters/kalshi/factories.py tests/adapters/kalshi/test_factories.py
git commit -m "feat: kalshi market data conversion factories"
```

---

## Task 6: Instrument Provider

**Files:**
- Create: `adapters/kalshi/providers.py`
- Create: `tests/adapters/kalshi/test_providers.py`

- [ ] **Step 1: Write failing tests**

`tests/adapters/kalshi/test_providers.py`:
```python
import pytest
from unittest.mock import MagicMock, patch
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.test_kit.mocks.cache import MockCache

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.providers import KalshiInstrumentProvider
from adapters.kalshi.config import KalshiDataClientConfig


SAMPLE_MARKETS = [
    {
        "ticker": "KXBTC15M-25APR30-T65499.99",
        "series_ticker": "KXBTC15M",
        "status": "open",
        "yes_bid": 55,
        "yes_ask": 57,
        "close_time": "2025-04-30T15:00:00Z",
        "title": "BTC above 65499.99 at 3pm?",
    },
    {
        "ticker": "KXBTC15M-25APR30-T65999.99",
        "series_ticker": "KXBTC15M",
        "status": "open",
        "yes_bid": 30,
        "yes_ask": 32,
        "close_time": "2025-04-30T15:00:00Z",
        "title": "BTC above 65999.99 at 3pm?",
    },
]


@pytest.fixture()
def mock_http_client():
    client = MagicMock()
    client.list_markets_paged.return_value = SAMPLE_MARKETS
    client.get_market.side_effect = lambda ticker: next(m for m in SAMPLE_MARKETS if m["ticker"] == ticker)
    return client


@pytest.fixture()
def provider(mock_http_client):
    config = KalshiDataClientConfig(api_key="key", private_key_pem="pem")
    return KalshiInstrumentProvider(http_client=mock_http_client, config=config)


def test_load_all_populates_instruments(provider, mock_http_client):
    provider.load_all()
    mock_http_client.list_markets_paged.assert_called_once()
    instruments = provider.get_all()
    assert len(instruments) == 2


def test_load_by_ticker_returns_instrument(provider, mock_http_client):
    instrument_id = InstrumentId(Symbol("KXBTC15M-25APR30-T65499.99"), KALSHI_VENUE)
    provider.load(instrument_id)
    instrument = provider.find(instrument_id)
    assert instrument is not None
    assert instrument.id == instrument_id


def test_load_series_loads_filtered_markets(provider, mock_http_client):
    provider.load_series("KXBTC15M")
    mock_http_client.list_markets_paged.assert_called_once_with(series_ticker="KXBTC15M", status="open")
    instruments = provider.get_all()
    assert len(instruments) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/adapters/kalshi/test_providers.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement instrument provider**

`adapters/kalshi/providers.py`:
```python
from __future__ import annotations

import logging

from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.model.identifiers import InstrumentId

from adapters.kalshi.config import KalshiDataClientConfig
from adapters.kalshi.factories import market_to_binary_option
from adapters.kalshi.http.client import KalshiHttpClient

_logger = logging.getLogger(__name__)


class KalshiInstrumentProvider(InstrumentProvider):
    def __init__(self, http_client: KalshiHttpClient, config: KalshiDataClientConfig) -> None:
        super().__init__()
        self._http = http_client
        self._config = config

    def load_all(self, filters: dict | None = None) -> None:
        markets = self._http.list_markets_paged(status="open")
        _logger.info("loaded %d markets from Kalshi", len(markets))
        for market in markets:
            try:
                instrument = market_to_binary_option(market)
                self.add(instrument)
            except Exception:
                _logger.exception("failed to convert market ticker=%s", market.get("ticker"))

    def load(self, instrument_id: InstrumentId, filters: dict | None = None) -> None:
        ticker = instrument_id.symbol.value
        market = self._http.get_market(ticker)
        try:
            instrument = market_to_binary_option(market)
            self.add(instrument)
        except Exception:
            _logger.exception("failed to convert market ticker=%s", ticker)

    def load_series(self, series_ticker: str) -> None:
        markets = self._http.list_markets_paged(series_ticker=series_ticker, status="open")
        _logger.info("loaded %d markets for series %s", len(markets), series_ticker)
        for market in markets:
            try:
                instrument = market_to_binary_option(market)
                self.add(instrument)
            except Exception:
                _logger.exception("failed to convert market ticker=%s", market.get("ticker"))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/adapters/kalshi/test_providers.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add adapters/kalshi/providers.py tests/adapters/kalshi/test_providers.py
git commit -m "feat: KalshiInstrumentProvider"
```

---

## Task 7: Execution Client

**Files:**
- Create: `adapters/kalshi/execution.py`
- Create: `tests/adapters/kalshi/test_execution.py`

- [ ] **Step 1: Write failing tests**

`tests/adapters/kalshi/test_execution.py`:
```python
import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId, Symbol, ClientOrderId, VenueOrderId, AccountId
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.test_kit.stubs.commands import TestCommandStubs
from nautilus_trader.test_kit.stubs.execution import TestExecStubs

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.execution import KalshiExecutionClient, kalshi_order_payload


def test_kalshi_order_payload_buy_yes():
    instrument_id = InstrumentId(Symbol("KXBTC15M-25APR30-T65499.99"), KALSHI_VENUE)
    payload = kalshi_order_payload(
        ticker="KXBTC15M-25APR30-T65499.99",
        side=OrderSide.BUY,
        price=Price(0.55, 2),
        quantity=Quantity(10, 0),
        client_order_id="clord-001",
    )
    assert payload["ticker"] == "KXBTC15M-25APR30-T65499.99"
    assert payload["side"] == "yes"
    assert payload["yes_price"] == 55
    assert payload["count"] == 10
    assert payload["client_order_id"] == "clord-001"
    assert payload["type"] == "limit"


def test_kalshi_order_payload_sell_is_no_side():
    payload = kalshi_order_payload(
        ticker="KXBTC15M-25APR30-T65499.99",
        side=OrderSide.SELL,
        price=Price(0.55, 2),
        quantity=Quantity(10, 0),
        client_order_id="clord-002",
    )
    assert payload["side"] == "no"
    assert payload["no_price"] == 45  # 100 - 55


def test_generate_order_status_reports_maps_open_orders():
    from adapters.kalshi.execution import map_order_status_report
    from nautilus_trader.execution.reports import OrderStatusReport
    from nautilus_trader.model.enums import OrderStatus

    raw_order = {
        "order_id": "kalshi-123",
        "client_order_id": "clord-001",
        "ticker": "KXBTC15M-25APR30-T65499.99",
        "side": "yes",
        "yes_price": 55,
        "original_count": 10,
        "remaining_count": 4,
        "filled_count": 6,
        "status": "resting",
        "created_time": "2025-04-30T14:00:00Z",
    }
    account_id = AccountId("KALSHI-001")
    report = map_order_status_report(raw_order, account_id=account_id, ts_init=0)
    assert isinstance(report, OrderStatusReport)
    assert report.venue_order_id == VenueOrderId("kalshi-123")
    assert report.client_order_id == ClientOrderId("clord-001")
    assert report.order_status == OrderStatus.PARTIALLY_FILLED
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/adapters/kalshi/test_execution.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement execution client**

`adapters/kalshi/execution.py`:
```python
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from nautilus_trader.execution.clients import LiveExecutionClient
from nautilus_trader.execution.reports import FillReport, OrderStatusReport, PositionStatusReport
from nautilus_trader.model.enums import LiquiditySide, OrderSide, OrderStatus, OrderType, TimeInForce
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    Symbol,
    TradeId,
    VenueOrderId,
)
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.currency import Currency

from adapters.kalshi.config import KalshiExecClientConfig
from adapters.kalshi.constants import KALSHI_VENUE, PRICE_PRECISION, SIZE_PRECISION
from adapters.kalshi.factories import kalshi_ticker_to_instrument_id
from adapters.kalshi.http.client import KalshiHttpClient

_logger = logging.getLogger(__name__)


def kalshi_order_payload(
    *,
    ticker: str,
    side: OrderSide,
    price: Price,
    quantity: Quantity,
    client_order_id: str,
) -> dict[str, Any]:
    price_cents = round(price.as_double() * 100)
    count = int(quantity.as_double())
    if side == OrderSide.BUY:
        return {
            "ticker": ticker,
            "side": "yes",
            "yes_price": price_cents,
            "count": count,
            "type": "limit",
            "client_order_id": client_order_id,
        }
    else:
        no_price_cents = 100 - price_cents
        return {
            "ticker": ticker,
            "side": "no",
            "no_price": no_price_cents,
            "count": count,
            "type": "limit",
            "client_order_id": client_order_id,
        }


def _parse_ts(value: str | None) -> int:
    if not value:
        return 0
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1e9)


def _map_status(status: str, filled: int, original: int) -> OrderStatus:
    if status in ("canceled", "cancelled"):
        return OrderStatus.CANCELED
    if status == "resting":
        return OrderStatus.PARTIALLY_FILLED if filled > 0 else OrderStatus.ACCEPTED
    if status in ("executed", "filled"):
        return OrderStatus.FILLED
    return OrderStatus.ACCEPTED


def map_order_status_report(raw: dict, *, account_id: AccountId, ts_init: int) -> OrderStatusReport:
    ticker = raw["ticker"]
    instrument_id = kalshi_ticker_to_instrument_id(ticker)
    filled = raw.get("filled_count", 0) or 0
    original = raw.get("original_count", 1) or 1
    remaining = raw.get("remaining_count", original - filled) or 0
    yes_price = raw.get("yes_price") or (100 - (raw.get("no_price") or 0))
    side_str = raw.get("side", "yes")
    order_side = OrderSide.BUY if side_str == "yes" else OrderSide.SELL

    return OrderStatusReport(
        account_id=account_id,
        instrument_id=instrument_id,
        venue_order_id=VenueOrderId(raw["order_id"]),
        client_order_id=ClientOrderId(raw["client_order_id"]) if raw.get("client_order_id") else None,
        order_side=order_side,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        order_status=_map_status(raw.get("status", ""), filled, original),
        price=Price(round(yes_price / 100, PRICE_PRECISION), PRICE_PRECISION),
        quantity=Quantity(original, SIZE_PRECISION),
        filled_qty=Quantity(filled, SIZE_PRECISION),
        avg_px=Price(round(yes_price / 100, PRICE_PRECISION), PRICE_PRECISION) if filled > 0 else None,
        ts_accepted=_parse_ts(raw.get("created_time")),
        ts_last=_parse_ts(raw.get("updated_time") or raw.get("created_time")),
        ts_init=ts_init,
        report_id=uuid.uuid4(),
    )


class KalshiExecutionClient(LiveExecutionClient):
    def __init__(
        self,
        *,
        http_client: KalshiHttpClient,
        config: KalshiExecClientConfig,
        **kwargs,
    ) -> None:
        super().__init__(venue=KALSHI_VENUE, **kwargs)
        self._http = http_client
        self._config = config

    async def _connect(self) -> None:
        _logger.info("KalshiExecutionClient connecting")

    async def _disconnect(self) -> None:
        _logger.info("KalshiExecutionClient disconnecting")

    def generate_order_status_reports(
        self,
        instrument_id: InstrumentId | None = None,
        start=None,
        end=None,
        open_only: bool = False,
    ) -> list[OrderStatusReport]:
        ts_init = time.time_ns()
        account_id = self.account_id
        raw_orders = self._http.list_recent_orders()
        reports = []
        for raw in raw_orders:
            try:
                reports.append(map_order_status_report(raw, account_id=account_id, ts_init=ts_init))
            except Exception:
                _logger.exception("failed to map order %s", raw.get("order_id"))
        return reports

    def generate_fill_reports(
        self,
        instrument_id: InstrumentId | None = None,
        venue_order_id: VenueOrderId | None = None,
        start=None,
        end=None,
    ) -> list[FillReport]:
        ts_init = time.time_ns()
        account_id = self.account_id
        raw_fills = self._http.list_recent_fills()
        reports = []
        for raw in raw_fills:
            try:
                ticker = raw["ticker"]
                instrument_id_fill = kalshi_ticker_to_instrument_id(ticker)
                yes_price = raw.get("yes_price") or (100 - (raw.get("no_price") or 0))
                side_str = raw.get("side", "yes")
                order_side = OrderSide.BUY if side_str == "yes" else OrderSide.SELL
                reports.append(FillReport(
                    account_id=account_id,
                    instrument_id=instrument_id_fill,
                    venue_order_id=VenueOrderId(raw["order_id"]),
                    trade_id=TradeId(raw["trade_id"]),
                    order_side=order_side,
                    last_qty=Quantity(raw["count"], SIZE_PRECISION),
                    last_px=Price(round(yes_price / 100, PRICE_PRECISION), PRICE_PRECISION),
                    liquidity_side=LiquiditySide.TAKER if raw.get("is_taker") else LiquiditySide.MAKER,
                    commission=Money(0, Currency.from_str("USD")),
                    ts_event=_parse_ts(raw.get("created_time")),
                    ts_init=ts_init,
                    report_id=uuid.uuid4(),
                ))
            except Exception:
                _logger.exception("failed to map fill %s", raw.get("trade_id"))
        return reports

    async def _submit_order(self, command) -> None:
        order = command.order
        ticker = order.instrument_id.symbol.value
        payload = kalshi_order_payload(
            ticker=ticker,
            side=order.side,
            price=order.price,
            quantity=order.quantity,
            client_order_id=str(order.client_order_id),
        )
        try:
            result = self._http.place_order(payload)
            self.generate_order_accepted(
                strategy_id=command.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                venue_order_id=VenueOrderId(result["kalshi_order_id"]),
                ts_event=time.time_ns(),
            )
        except Exception as e:
            self.generate_order_rejected(
                strategy_id=command.strategy_id,
                instrument_id=order.instrument_id,
                client_order_id=order.client_order_id,
                reason=str(e),
                ts_event=time.time_ns(),
            )

    async def _cancel_order(self, command) -> None:
        venue_order_id = command.venue_order_id
        if venue_order_id is None:
            _logger.warning("cancel_order called with no venue_order_id for %s", command.client_order_id)
            return
        try:
            self._http.cancel_order(str(venue_order_id))
            self.generate_order_canceled(
                strategy_id=command.strategy_id,
                instrument_id=command.instrument_id,
                client_order_id=command.client_order_id,
                venue_order_id=venue_order_id,
                ts_event=time.time_ns(),
            )
        except Exception as e:
            _logger.exception("cancel_order failed for %s: %s", venue_order_id, e)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/adapters/kalshi/test_execution.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add adapters/kalshi/execution.py tests/adapters/kalshi/test_execution.py
git commit -m "feat: KalshiExecutionClient with order status and fill report generation"
```

---

## Task 8: Public Exports and Full Suite

**Files:**
- Modify: `adapters/kalshi/__init__.py`

- [ ] **Step 1: Wire public exports**

`adapters/kalshi/__init__.py`:
```python
from adapters.kalshi.config import KalshiDataClientConfig, KalshiExecClientConfig
from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.execution import KalshiExecutionClient
from adapters.kalshi.providers import KalshiInstrumentProvider

__all__ = [
    "KALSHI_VENUE",
    "KalshiDataClientConfig",
    "KalshiExecClientConfig",
    "KalshiExecutionClient",
    "KalshiInstrumentProvider",
]
```

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -v
```
Expected: All tests pass (auth: 3, client: 5, factories: 4, providers: 3, execution: 3 = 18 total).

- [ ] **Step 3: Verify import from top level**

```bash
python -c "from adapters.kalshi import KalshiExecutionClient, KalshiInstrumentProvider, KALSHI_VENUE; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Final commit**

```bash
git add adapters/kalshi/__init__.py
git commit -m "feat: wire kalshi adapter public exports"
```

---

## Notes for Next Plans

- **Plan 2 (Safety & Reconciliation):** `KalshiExecutionClient.generate_order_status_reports()` and `generate_fill_reports()` are the entry points for the reconciliation gate. The safety layer wraps the execution client.
- **Plan 3 (Data Catalog Bridge):** The `factories.py` `market_to_binary_option()` function is reused to populate instrument catalog metadata.
- **Plan 4 (StatArb + Launcher):** `KalshiInstrumentProvider.load_series()` is the entry point for loading a series' worth of instruments before a backtest or live session.
- **`KalshiDataClient` (WebSocket streaming):** Not included in this plan — it requires an async WebSocket event loop and is best built after the execution client is proven. Add as Plan 1b or the first task in Plan 4.
