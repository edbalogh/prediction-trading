# Data Catalog Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `CatalogBuilder` that reads Hive-partitioned Parquet files from the Ingestion project and writes them into NautilusTrader's `ParquetDataCatalog` format, enabling backtests to run off the same data collected nightly.

**Architecture:** A single `catalog/sync.py` module with a `CatalogBuilder` class that converts Ingestion Parquet files to NautilusTrader `TradeTick` and `Bar` objects, then calls `catalog.write_data()`. Idempotency is enforced by a JSON state file that records which source files have already been ingested — re-running never writes duplicates. The class is usable both programmatically (called from `run_all.py`) and via a CLI entry point.

**Tech Stack:** Python 3.11, pandas>=2, pyarrow, nautilus_trader 1.221 (`ParquetDataCatalog`, `TradeTick`, `Bar`, `BarType`, `BarSpecification`), pytest

---

## Ingestion Data Layout (read-only source)

```
/Users/edbalogh/Trading/Ingestion/data/
├── trades/
│   └── series=KXATPMATCH/
│       └── date=2026-03-25/
│           └── part.parquet   # columns: trade_id, ticker, count_fp(str), yes_price_dollars(str), taker_side("yes"/"no"), created_time(ISO8601Z), series_ticker
├── candlesticks/
│   └── interval=60m/
│       └── series=KXATPCHALLENGERMATCH/
│           └── date=2026-03-23/
│               └── part.parquet   # columns: end_period_ts(Unix seconds int64), ticker, interval_minutes(int64), price_open/high/low/close(str nullable), volume(str)
└── crypto_bars/
    └── symbol=BTC-USD/
        └── date=2026-02-16/
            └── part.parquet   # columns: open_time(ms int64), open/high/low/close/volume(float64), symbol(str)
```

## NautilusTrader Catalog Target

Default path: `~/.nautilus/catalog/` (expandable, configurable)

Key API:
- `ParquetDataCatalog(path)` — opens or creates catalog
- `catalog.write_data(list[TradeTick | Bar])` — appends data (must be sorted by `ts_event`)
- `catalog.trade_ticks(instrument_ids=["TICKER.KALSHI"])` — reads back
- `catalog.bars(instrument_ids=["TICKER.KALSHI"])` — reads back

## NautilusTrader Object Construction

**TradeTick:**
```python
TradeTick(
    instrument_id=InstrumentId(Symbol("KXBTC15M-X"), Venue("KALSHI")),
    price=Price(0.55, 2),
    size=Quantity(10, 0),
    aggressor_side=AggressorSide.BUYER,   # "yes" taker → BUYER, "no" taker → SELLER
    trade_id=TradeId("trade-uuid"),
    ts_event=1_000_000_000,   # nanoseconds
    ts_init=1_000_000_000,
)
```

**Bar (60-minute candlestick):**
```python
BarType(
    InstrumentId(Symbol("KXBTC15M-X"), Venue("KALSHI")),
    BarSpecification(1, BarAggregation.HOUR, PriceType.LAST),   # 60min → HOUR, NOT 60-MINUTE (raises ValueError)
)
Bar(bar_type, Price(open,2), Price(high,2), Price(low,2), Price(close,2), Quantity(volume,0), ts_event_ns, ts_init_ns)
```

**Bar (1-minute crypto):**
```python
BarType(
    InstrumentId(Symbol("BTC-USD"), Venue("CRYPTO")),
    BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
)
```

**Interval mapping (interval_minutes → BarSpecification):**
```
1 min  → BarSpecification(1,  MINUTE, LAST)
5 min  → BarSpecification(5,  MINUTE, LAST)
15 min → BarSpecification(15, MINUTE, LAST)
30 min → BarSpecification(30, MINUTE, LAST)
60 min → BarSpecification(1,  HOUR,   LAST)   ← NautilusTrader rejects 60-MINUTE
1440   → BarSpecification(1,  DAY,    LAST)
```

---

## File Map

| File | Responsibility |
|------|----------------|
| `catalog/__init__.py` | Empty package marker |
| `catalog/sync.py` | `CatalogBuilder` — all conversion + sync logic |
| `tests/catalog/__init__.py` | Empty |
| `tests/catalog/test_sync.py` | All tests for catalog sync |
| `pyproject.toml` | Add `pandas>=2,<3` dependency |

---

## Task 1: Package Scaffolding + Conversion Helpers

**Files:**
- Create: `catalog/__init__.py`
- Create: `catalog/sync.py` (skeleton with helpers)
- Create: `tests/catalog/__init__.py`
- Create: `tests/catalog/test_sync.py`
- Modify: `pyproject.toml` (add pandas)

- [ ] **Step 1: Create package directories**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && mkdir -p catalog tests/catalog && touch catalog/__init__.py tests/catalog/__init__.py
```

- [ ] **Step 2: Add pandas to pyproject.toml and install**

Edit `pyproject.toml` to add `"pandas>=2,<3"` to the `dependencies` list:

```toml
dependencies = [
    "nautilus_trader>=1.208,<2",
    "httpx>=0.27,<1",
    "cryptography>=42,<45",
    "websockets>=13,<15",
    "redis>=5,<6",
    "pydantic>=2.0,<3",
    "pandas>=2,<3",
]
```

Then install:
```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pip install pandas
```

- [ ] **Step 3: Write failing tests for conversion helpers**

`tests/catalog/test_sync.py`:
```python
import pytest
from catalog.sync import (
    parse_ts_ns,
    interval_minutes_to_bar_spec,
    taker_side_to_aggressor,
)
from nautilus_trader.model.data import BarSpecification
from nautilus_trader.model.enums import BarAggregation, PriceType, AggressorSide


def test_parse_ts_ns_iso8601():
    ts = parse_ts_ns("2026-03-25T23:47:43.556733Z")
    assert ts > 0
    # 2026-03-25 is after 2026-01-01 (unix ns > 1.77e18)
    assert ts > 1_770_000_000_000_000_000


def test_parse_ts_ns_unix_seconds():
    # end_period_ts in candlesticks is Unix seconds int
    ts = parse_ts_ns(1_774_274_400)
    assert ts == 1_774_274_400 * 1_000_000_000


def test_parse_ts_ns_unix_milliseconds():
    # open_time in crypto_bars is Unix milliseconds
    ts = parse_ts_ns(1_771_218_000_000, unit="ms")
    assert ts == 1_771_218_000_000 * 1_000_000


def test_interval_minutes_to_bar_spec_60():
    spec = interval_minutes_to_bar_spec(60)
    assert spec == BarSpecification(1, BarAggregation.HOUR, PriceType.LAST)


def test_interval_minutes_to_bar_spec_1():
    spec = interval_minutes_to_bar_spec(1)
    assert spec == BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)


def test_interval_minutes_to_bar_spec_30():
    spec = interval_minutes_to_bar_spec(30)
    assert spec == BarSpecification(30, BarAggregation.MINUTE, PriceType.LAST)


def test_taker_side_yes_is_buyer():
    assert taker_side_to_aggressor("yes") == AggressorSide.BUYER


def test_taker_side_no_is_seller():
    assert taker_side_to_aggressor("no") == AggressorSide.SELLER
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py -v
```
Expected: `ImportError — No module named 'catalog.sync'`

- [ ] **Step 5: Implement conversion helpers in `catalog/sync.py`**

```python
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from nautilus_trader.model.data import Bar, BarSpecification, BarType, TradeTick
from nautilus_trader.model.enums import AggressorSide, BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TradeId, Venue
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog import ParquetDataCatalog

_logger = logging.getLogger(__name__)

KALSHI_VENUE = Venue("KALSHI")
CRYPTO_VENUE = Venue("CRYPTO")

_INTERVAL_MAP: dict[int, BarSpecification] = {
    1:    BarSpecification(1,  BarAggregation.MINUTE, PriceType.LAST),
    5:    BarSpecification(5,  BarAggregation.MINUTE, PriceType.LAST),
    15:   BarSpecification(15, BarAggregation.MINUTE, PriceType.LAST),
    30:   BarSpecification(30, BarAggregation.MINUTE, PriceType.LAST),
    60:   BarSpecification(1,  BarAggregation.HOUR,   PriceType.LAST),
    1440: BarSpecification(1,  BarAggregation.DAY,    PriceType.LAST),
}


def parse_ts_ns(value: str | int, unit: str = "s") -> int:
    """Convert ISO8601 string or numeric timestamp to nanoseconds."""
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1_000_000_000)
    if unit == "ms":
        return int(value) * 1_000_000
    return int(value) * 1_000_000_000


def interval_minutes_to_bar_spec(interval_minutes: int) -> BarSpecification:
    spec = _INTERVAL_MAP.get(interval_minutes)
    if spec is None:
        raise ValueError(f"Unsupported interval_minutes={interval_minutes}. Supported: {sorted(_INTERVAL_MAP)}")
    return spec


def taker_side_to_aggressor(side: str) -> AggressorSide:
    return AggressorSide.BUYER if side == "yes" else AggressorSide.SELLER
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py -v
```
Expected: 8 passed.

- [ ] **Step 7: Commit**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && git add catalog/ tests/catalog/ pyproject.toml && git commit -m "feat: catalog package scaffolding and conversion helpers"
```

---

## Task 2: Trade File Sync (TradeTick)

**Files:**
- Modify: `catalog/sync.py` — add `CatalogBuilder` class + trade file sync
- Modify: `tests/catalog/test_sync.py` — add trade sync tests

- [ ] **Step 1: Write failing tests for trade sync**

Append to `tests/catalog/test_sync.py`:
```python
import tempfile
import os
import pandas as pd
from catalog.sync import CatalogBuilder


@pytest.fixture()
def tmp_catalog(tmp_path):
    catalog_path = str(tmp_path / "catalog")
    ingestion_dir = str(tmp_path / "ingestion")
    os.makedirs(catalog_path)
    os.makedirs(ingestion_dir)
    return CatalogBuilder(ingestion_data_dir=ingestion_dir, catalog_path=catalog_path)


def _write_trades_parquet(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_sync_trades_file_writes_trade_ticks(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "trades" / "series=KXBTC15M" / "date=2026-03-25" / "part.parquet")
    _write_trades_parquet(parquet_path, [
        {
            "trade_id": "trade-001",
            "ticker": "KXBTC15M-TEST",
            "count_fp": "10.00",
            "yes_price_dollars": "0.55",
            "no_price_dollars": "0.45",
            "taker_side": "yes",
            "created_time": "2026-03-25T10:00:00.000000Z",
            "series_ticker": "KXBTC15M",
        },
        {
            "trade_id": "trade-002",
            "ticker": "KXBTC15M-TEST",
            "count_fp": "5.00",
            "yes_price_dollars": "0.56",
            "no_price_dollars": "0.44",
            "taker_side": "no",
            "created_time": "2026-03-25T10:01:00.000000Z",
            "series_ticker": "KXBTC15M",
        },
    ])
    count = tmp_catalog.sync_trades_file(parquet_path)
    assert count == 2

    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    ticks = catalog.trade_ticks(instrument_ids=["KXBTC15M-TEST.KALSHI"])
    assert len(ticks) == 2
    assert str(ticks[0].price) == "0.55"
    assert str(ticks[1].price) == "0.56"


def test_sync_trades_file_skips_rows_with_missing_price(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "trades" / "series=KXBTC15M" / "date=2026-03-26" / "part.parquet")
    _write_trades_parquet(parquet_path, [
        {
            "trade_id": "trade-003",
            "ticker": "KXBTC15M-TEST",
            "count_fp": "10.00",
            "yes_price_dollars": None,
            "no_price_dollars": None,
            "taker_side": "yes",
            "created_time": "2026-03-26T10:00:00.000000Z",
            "series_ticker": "KXBTC15M",
        },
        {
            "trade_id": "trade-004",
            "ticker": "KXBTC15M-TEST",
            "count_fp": "3.00",
            "yes_price_dollars": "0.60",
            "no_price_dollars": "0.40",
            "taker_side": "yes",
            "created_time": "2026-03-26T10:01:00.000000Z",
            "series_ticker": "KXBTC15M",
        },
    ])
    count = tmp_catalog.sync_trades_file(parquet_path)
    assert count == 1


def test_sync_trades_no_is_seller(tmp_catalog, tmp_path):
    from nautilus_trader.model.enums import AggressorSide
    parquet_path = str(tmp_path / "ingestion" / "trades" / "series=KXBTC15M" / "date=2026-03-27" / "part.parquet")
    _write_trades_parquet(parquet_path, [{
        "trade_id": "trade-005",
        "ticker": "KXBTC15M-TEST",
        "count_fp": "2.00",
        "yes_price_dollars": "0.40",
        "no_price_dollars": "0.60",
        "taker_side": "no",
        "created_time": "2026-03-27T10:00:00.000000Z",
        "series_ticker": "KXBTC15M",
    }])
    tmp_catalog.sync_trades_file(parquet_path)
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    ticks = catalog.trade_ticks(instrument_ids=["KXBTC15M-TEST.KALSHI"])
    assert ticks[0].aggressor_side == AggressorSide.SELLER
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py::test_sync_trades_file_writes_trade_ticks -v
```
Expected: `AttributeError` — `CatalogBuilder` not defined.

- [ ] **Step 3: Implement `CatalogBuilder` class and `sync_trades_file`**

Append to `catalog/sync.py` (after the helper functions):
```python
class CatalogBuilder:
    def __init__(
        self,
        *,
        ingestion_data_dir: str,
        catalog_path: str = "~/.nautilus/catalog",
    ) -> None:
        self._ingestion_dir = Path(ingestion_data_dir)
        self._catalog_path = str(Path(catalog_path).expanduser())
        self._state_path = Path(self._catalog_path) / ".catalog_sync_state.json"
        self._catalog = ParquetDataCatalog(self._catalog_path)
        self._synced_files: set[str] = set()
        self._load_state()

    # ── State management ──────────────────────────────────────────────────────

    def _load_state(self) -> None:
        if self._state_path.exists():
            data = json.loads(self._state_path.read_text())
            self._synced_files = set(data.get("synced_files", []))

    def _save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps({"synced_files": sorted(self._synced_files)}, indent=2))

    def _relative(self, path: str) -> str:
        return str(Path(path).relative_to(self._ingestion_dir))

    def is_synced(self, path: str) -> bool:
        return self._relative(path) in self._synced_files

    def _mark_synced(self, path: str) -> None:
        self._synced_files.add(self._relative(path))
        self._save_state()

    # ── Trades → TradeTick ────────────────────────────────────────────────────

    def sync_trades_file(self, parquet_path: str) -> int:
        df = pd.read_parquet(parquet_path)
        ticks: list[TradeTick] = []
        for _, row in df.iterrows():
            yes_price_raw = row.get("yes_price_dollars")
            if yes_price_raw is None or (isinstance(yes_price_raw, float) and pd.isna(yes_price_raw)):
                continue
            try:
                price_val = float(yes_price_raw)
            except (ValueError, TypeError):
                continue
            instrument_id = InstrumentId(Symbol(str(row["ticker"])), KALSHI_VENUE)
            ticks.append(TradeTick(
                instrument_id=instrument_id,
                price=Price(round(price_val, 2), 2),
                size=Quantity(int(float(str(row["count_fp"]))), 0),
                aggressor_side=taker_side_to_aggressor(str(row.get("taker_side", "yes"))),
                trade_id=TradeId(str(row["trade_id"])),
                ts_event=parse_ts_ns(str(row["created_time"])),
                ts_init=parse_ts_ns(str(row["created_time"])),
            ))
        if ticks:
            ticks.sort(key=lambda t: t.ts_event)
            self._catalog.write_data(ticks)
        _logger.info("sync_trades_file: wrote %d ticks from %s", len(ticks), parquet_path)
        return len(ticks)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py -v
```
Expected: 11 passed (8 previous + 3 new).

- [ ] **Step 5: Commit**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && git add catalog/sync.py tests/catalog/test_sync.py && git commit -m "feat: trade file sync to NautilusTrader catalog (TradeTick)"
```

---

## Task 3: Candlestick File Sync (Bar)

**Files:**
- Modify: `catalog/sync.py` — add `sync_candlesticks_file`
- Modify: `tests/catalog/test_sync.py` — add candlestick sync tests

- [ ] **Step 1: Write failing tests**

Append to `tests/catalog/test_sync.py`:
```python
def _write_candlesticks_parquet(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_sync_candlesticks_file_writes_bars(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "candlesticks" / "interval=60m" / "series=KXBTC15M" / "date=2026-03-25" / "part.parquet")
    _write_candlesticks_parquet(parquet_path, [
        {
            "end_period_ts": 1_774_274_400,   # Unix seconds
            "ticker": "KXBTC15M-TEST",
            "interval_minutes": 60,
            "price_open": "0.50",
            "price_high": "0.60",
            "price_low": "0.48",
            "price_close": "0.55",
            "volume": "100.00",
        },
    ])
    count = tmp_catalog.sync_candlesticks_file(parquet_path)
    assert count == 1

    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    from nautilus_trader.model.data import BarType, BarSpecification
    from nautilus_trader.model.enums import BarAggregation, PriceType
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["KXBTC15M-TEST.KALSHI"])
    assert len(bars) == 1
    assert str(bars[0].open) == "0.50"
    assert str(bars[0].close) == "0.55"


def test_sync_candlesticks_file_skips_null_ohlc(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "candlesticks" / "interval=60m" / "series=KXBTC15M" / "date=2026-03-26" / "part.parquet")
    _write_candlesticks_parquet(parquet_path, [
        {   # Null OHLC — should be skipped
            "end_period_ts": 1_774_278_000,
            "ticker": "KXBTC15M-TEST",
            "interval_minutes": 60,
            "price_open": None,
            "price_high": None,
            "price_low": None,
            "price_close": None,
            "volume": "0.00",
        },
        {   # Valid — should be written
            "end_period_ts": 1_774_281_600,
            "ticker": "KXBTC15M-TEST",
            "interval_minutes": 60,
            "price_open": "0.53",
            "price_high": "0.58",
            "price_low": "0.51",
            "price_close": "0.56",
            "volume": "50.00",
        },
    ])
    count = tmp_catalog.sync_candlesticks_file(parquet_path)
    assert count == 1


def test_sync_candlesticks_bar_type_uses_hour_for_60min(tmp_catalog, tmp_path):
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    parquet_path = str(tmp_path / "ingestion" / "candlesticks" / "interval=60m" / "series=KXBTC15M" / "date=2026-03-27" / "part.parquet")
    _write_candlesticks_parquet(parquet_path, [{
        "end_period_ts": 1_774_285_200,
        "ticker": "KXBTC15M-HOURTEST",
        "interval_minutes": 60,
        "price_open": "0.40",
        "price_high": "0.45",
        "price_low": "0.38",
        "price_close": "0.42",
        "volume": "20.00",
    }])
    tmp_catalog.sync_candlesticks_file(parquet_path)
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["KXBTC15M-HOURTEST.KALSHI"])
    assert len(bars) == 1
    # Bar type string should contain "HOUR" not "MINUTE"
    assert "HOUR" in str(bars[0].bar_type)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py::test_sync_candlesticks_file_writes_bars -v
```
Expected: `AttributeError — CatalogBuilder has no attribute sync_candlesticks_file`

- [ ] **Step 3: Implement `sync_candlesticks_file`**

Add to the `CatalogBuilder` class in `catalog/sync.py`:
```python
    # ── Candlesticks → Bar ────────────────────────────────────────────────────

    def sync_candlesticks_file(self, parquet_path: str) -> int:
        df = pd.read_parquet(parquet_path)
        bars: list[Bar] = []
        for _, row in df.iterrows():
            open_raw = row.get("price_open")
            high_raw = row.get("price_high")
            low_raw  = row.get("price_low")
            close_raw = row.get("price_close")
            if any(v is None or (isinstance(v, float) and pd.isna(v)) for v in [open_raw, high_raw, low_raw, close_raw]):
                continue
            try:
                open_val  = float(str(open_raw))
                high_val  = float(str(high_raw))
                low_val   = float(str(low_raw))
                close_val = float(str(close_raw))
                vol_val   = float(str(row.get("volume") or "0"))
            except (ValueError, TypeError):
                continue
            interval_minutes = int(row["interval_minutes"])
            spec = interval_minutes_to_bar_spec(interval_minutes)
            instrument_id = InstrumentId(Symbol(str(row["ticker"])), KALSHI_VENUE)
            bar_type = BarType(instrument_id, spec)
            ts_event = parse_ts_ns(int(row["end_period_ts"]))
            bars.append(Bar(
                bar_type=bar_type,
                open=Price(round(open_val, 2), 2),
                high=Price(round(high_val, 2), 2),
                low=Price(round(low_val, 2), 2),
                close=Price(round(close_val, 2), 2),
                volume=Quantity(int(vol_val), 0),
                ts_event=ts_event,
                ts_init=ts_event,
            ))
        if bars:
            bars.sort(key=lambda b: b.ts_event)
            self._catalog.write_data(bars)
        _logger.info("sync_candlesticks_file: wrote %d bars from %s", len(bars), parquet_path)
        return len(bars)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py -v
```
Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && git add catalog/sync.py tests/catalog/test_sync.py && git commit -m "feat: candlestick file sync to NautilusTrader catalog (Bar)"
```

---

## Task 4: Crypto Bar File Sync (Bar)

**Files:**
- Modify: `catalog/sync.py` — add `sync_crypto_bars_file`
- Modify: `tests/catalog/test_sync.py` — add crypto bar tests

- [ ] **Step 1: Write failing tests**

Append to `tests/catalog/test_sync.py`:
```python
def _write_crypto_bars_parquet(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_sync_crypto_bars_file_writes_bars(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "crypto_bars" / "symbol=BTC-USD" / "date=2026-02-16" / "part.parquet")
    _write_crypto_bars_parquet(parquet_path, [
        {
            "open_time": 1_771_218_000_000,   # Unix milliseconds
            "open": 68830.14,
            "high": 68863.96,
            "low": 68802.66,
            "close": 68802.66,
            "volume": 6.364871,
            "close_time": 1_771_218_060_000,
            "quote_volume": 437920.060861,
            "symbol": "BTC-USD",
        },
        {
            "open_time": 1_771_218_060_000,
            "open": 68802.66,
            "high": 68834.97,
            "low": 68806.68,
            "close": 68830.14,
            "volume": 2.123524,
            "close_time": 1_771_218_120_000,
            "quote_volume": 146162.488628,
            "symbol": "BTC-USD",
        },
    ])
    count = tmp_catalog.sync_crypto_bars_file(parquet_path)
    assert count == 2

    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["BTC-USD.CRYPTO"])
    assert len(bars) == 2
    # Price precision is 2
    assert str(bars[0].open) == "68830.14"


def test_sync_crypto_bars_uses_crypto_venue(tmp_catalog, tmp_path):
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    parquet_path = str(tmp_path / "ingestion" / "crypto_bars" / "symbol=ETH-USD" / "date=2026-02-16" / "part.parquet")
    _write_crypto_bars_parquet(parquet_path, [{
        "open_time": 1_771_218_000_000,
        "open": 3000.50,
        "high": 3010.00,
        "low": 2990.00,
        "close": 3005.00,
        "volume": 100.5,
        "close_time": 1_771_218_060_000,
        "quote_volume": 301500.0,
        "symbol": "ETH-USD",
    }])
    tmp_catalog.sync_crypto_bars_file(parquet_path)
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["ETH-USD.CRYPTO"])
    assert len(bars) == 1
    assert "CRYPTO" in str(bars[0].bar_type)


def test_sync_crypto_bars_uses_1_minute_spec(tmp_catalog, tmp_path):
    parquet_path = str(tmp_path / "ingestion" / "crypto_bars" / "symbol=BTC-USD" / "date=2026-02-17" / "part.parquet")
    _write_crypto_bars_parquet(parquet_path, [{
        "open_time": 1_771_300_000_000,
        "open": 70000.0,
        "high": 70100.0,
        "low": 69900.0,
        "close": 70050.0,
        "volume": 5.0,
        "close_time": 1_771_300_060_000,
        "quote_volume": 350250.0,
        "symbol": "BTC-USD",
    }])
    tmp_catalog.sync_crypto_bars_file(parquet_path)
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    bars = catalog.bars(instrument_ids=["BTC-USD.CRYPTO"])
    assert "MINUTE" in str(bars[0].bar_type)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py::test_sync_crypto_bars_file_writes_bars -v
```
Expected: `AttributeError — sync_crypto_bars_file not defined`

- [ ] **Step 3: Implement `sync_crypto_bars_file`**

Add to the `CatalogBuilder` class in `catalog/sync.py`:
```python
    # ── Crypto Bars → Bar ─────────────────────────────────────────────────────

    def sync_crypto_bars_file(self, parquet_path: str) -> int:
        df = pd.read_parquet(parquet_path)
        bars: list[Bar] = []
        spec = BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST)
        for _, row in df.iterrows():
            try:
                open_val  = float(row["open"])
                high_val  = float(row["high"])
                low_val   = float(row["low"])
                close_val = float(row["close"])
                vol_val   = float(row["volume"])
            except (ValueError, TypeError, KeyError):
                continue
            instrument_id = InstrumentId(Symbol(str(row["symbol"])), CRYPTO_VENUE)
            bar_type = BarType(instrument_id, spec)
            ts_event = parse_ts_ns(int(row["open_time"]), unit="ms")
            bars.append(Bar(
                bar_type=bar_type,
                open=Price(round(open_val, 2), 2),
                high=Price(round(high_val, 2), 2),
                low=Price(round(low_val, 2), 2),
                close=Price(round(close_val, 2), 2),
                volume=Quantity(int(vol_val * 1000), 3),
                ts_event=ts_event,
                ts_init=ts_event,
            ))
        if bars:
            bars.sort(key=lambda b: b.ts_event)
            self._catalog.write_data(bars)
        _logger.info("sync_crypto_bars_file: wrote %d bars from %s", len(bars), parquet_path)
        return len(bars)
```

**Note on volume precision:** Crypto bar volumes (e.g. 6.364871 BTC) need sub-integer precision. Using `Quantity(int(vol * 1000), 3)` stores 3 decimal places (e.g. 6.364871 → 6364, SIZE_PRECISION=3, displayed as 6.364). Adjust if needed.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py -v
```
Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && git add catalog/sync.py tests/catalog/test_sync.py && git commit -m "feat: crypto bar file sync to NautilusTrader catalog (Bar)"
```

---

## Task 5: Orchestration, Idempotency, and CLI

**Files:**
- Modify: `catalog/sync.py` — add `sync_trades`, `sync_candlesticks`, `sync_crypto_bars`, `sync_all`, `__main__` block
- Modify: `tests/catalog/test_sync.py` — add orchestration + idempotency tests

- [ ] **Step 1: Write failing tests for orchestration**

Append to `tests/catalog/test_sync.py`:
```python
def test_sync_trades_discovers_and_syncs_all_files(tmp_catalog, tmp_path):
    ingestion_dir = str(tmp_path / "ingestion")
    # Write two trade files for different series/dates
    for series, date in [("KXBTC15M", "2026-03-25"), ("KXBTC15M", "2026-03-26")]:
        path = os.path.join(ingestion_dir, "trades", f"series={series}", f"date={date}", "part.parquet")
        _write_trades_parquet(path, [{
            "trade_id": f"t-{date}",
            "ticker": f"{series}-TEST",
            "count_fp": "1.00",
            "yes_price_dollars": "0.50",
            "no_price_dollars": "0.50",
            "taker_side": "yes",
            "created_time": f"{date}T10:00:00.000000Z",
            "series_ticker": series,
        }])
    total = tmp_catalog.sync_trades()
    assert total == 2


def test_idempotency_does_not_double_write(tmp_catalog, tmp_path):
    from nautilus_trader.persistence.catalog import ParquetDataCatalog
    ingestion_dir = str(tmp_path / "ingestion")
    path = os.path.join(ingestion_dir, "trades", "series=KXBTC15M", "date=2026-03-28", "part.parquet")
    _write_trades_parquet(path, [{
        "trade_id": "t-idempotent",
        "ticker": "KXBTC15M-IDEM",
        "count_fp": "1.00",
        "yes_price_dollars": "0.50",
        "no_price_dollars": "0.50",
        "taker_side": "yes",
        "created_time": "2026-03-28T10:00:00.000000Z",
        "series_ticker": "KXBTC15M",
    }])
    # First sync
    tmp_catalog.sync_trades()
    # Second sync — file already marked as synced, should skip
    count = tmp_catalog.sync_trades()
    assert count == 0

    catalog = ParquetDataCatalog(tmp_catalog._catalog_path)
    ticks = catalog.trade_ticks(instrument_ids=["KXBTC15M-IDEM.KALSHI"])
    assert len(ticks) == 1   # Not duplicated


def test_sync_all_returns_summary(tmp_catalog, tmp_path):
    ingestion_dir = str(tmp_path / "ingestion")
    path = os.path.join(ingestion_dir, "trades", "series=KXBTC15M", "date=2026-03-29", "part.parquet")
    _write_trades_parquet(path, [{
        "trade_id": "t-all",
        "ticker": "KXBTC15M-ALL",
        "count_fp": "1.00",
        "yes_price_dollars": "0.50",
        "no_price_dollars": "0.50",
        "taker_side": "yes",
        "created_time": "2026-03-29T10:00:00.000000Z",
        "series_ticker": "KXBTC15M",
    }])
    summary = tmp_catalog.sync_all()
    assert "trades" in summary
    assert summary["trades"] >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py::test_sync_trades_discovers_and_syncs_all_files -v
```
Expected: `AttributeError — sync_trades not defined`

- [ ] **Step 3: Implement orchestration methods**

Add to the `CatalogBuilder` class in `catalog/sync.py`:
```python
    # ── Orchestration ─────────────────────────────────────────────────────────

    def sync_trades(self, series: str | None = None) -> int:
        """Sync all unseen trade parquet files. Returns total records written."""
        pattern = "trades"
        if series:
            pattern = f"trades/series={series}"
        return self._sync_files(
            pattern=pattern,
            sync_fn=self.sync_trades_file,
        )

    def sync_candlesticks(self, series: str | None = None) -> int:
        pattern = "candlesticks"
        if series:
            pattern = f"candlesticks/*/series={series}"
        return self._sync_files(
            pattern=pattern,
            sync_fn=self.sync_candlesticks_file,
        )

    def sync_crypto_bars(self, symbol: str | None = None) -> int:
        pattern = "crypto_bars"
        if symbol:
            pattern = f"crypto_bars/symbol={symbol}"
        return self._sync_files(
            pattern=pattern,
            sync_fn=self.sync_crypto_bars_file,
        )

    def sync_all(self) -> dict[str, int]:
        return {
            "trades":       self.sync_trades(),
            "candlesticks": self.sync_candlesticks(),
            "crypto_bars":  self.sync_crypto_bars(),
        }

    def _sync_files(self, *, pattern: str, sync_fn) -> int:
        total = 0
        for parquet_file in sorted(self._ingestion_dir.glob(f"{pattern}/**/part.parquet")):
            path_str = str(parquet_file)
            if self.is_synced(path_str):
                _logger.debug("skipping already-synced: %s", path_str)
                continue
            try:
                count = sync_fn(path_str)
                self._mark_synced(path_str)
                total += count
            except Exception:
                _logger.exception("failed to sync %s", path_str)
        return total
```

- [ ] **Step 4: Add `__main__` block for CLI use**

Append to the bottom of `catalog/sync.py` (outside the class):
```python

def main() -> None:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Sync Ingestion data to NautilusTrader catalog")
    parser.add_argument("--ingestion-dir", default="/Users/edbalogh/Trading/Ingestion/data",
                        help="Path to Ingestion data directory")
    parser.add_argument("--catalog-path", default="~/.nautilus/catalog",
                        help="Path to NautilusTrader catalog")
    parser.add_argument("--type", choices=["trades", "candlesticks", "crypto_bars", "all"],
                        default="all", help="Which data type to sync")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    builder = CatalogBuilder(ingestion_data_dir=args.ingestion_dir, catalog_path=args.catalog_path)

    if args.type == "all":
        summary = builder.sync_all()
    elif args.type == "trades":
        summary = {"trades": builder.sync_trades()}
    elif args.type == "candlesticks":
        summary = {"candlesticks": builder.sync_candlesticks()}
    else:
        summary = {"crypto_bars": builder.sync_crypto_bars()}

    for key, count in summary.items():
        print(f"{key}: {count} records synced")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run all tests to verify they pass**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/catalog/test_sync.py -v
```
Expected: 20 passed.

- [ ] **Step 6: Run full suite to confirm no regressions**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && pytest tests/ -v --tb=short 2>&1 | tail -5
```
Expected: 83 total tests passed (63 existing + 20 new).

- [ ] **Step 7: Smoke test against real data**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && python -m catalog.sync --ingestion-dir /Users/edbalogh/Trading/Ingestion/data --catalog-path /tmp/nautilus-test-catalog --type trades 2>&1 | tail -5
```
Expected: prints `trades: N records synced` with N > 0. No errors.

- [ ] **Step 8: Commit**

```bash
cd /Users/edbalogh/LiveProjects/nautilus-plus && git add catalog/sync.py tests/catalog/test_sync.py && git commit -m "feat: catalog sync orchestration, idempotency, and CLI entry point"
```

---

## Notes for Plan 4 (StatArb Strategy + run.py Launcher)

- `CatalogBuilder` is callable from `run.py` for nightly post-collect sync
- For backtests: `ParquetDataCatalog("~/.nautilus/catalog")` + `catalog.trade_ticks(instrument_ids=["KXBTC15M-X.KALSHI"])` 
- `sync_all()` is intentionally idempotent — safe to call from cron or `run_all.py`
- Orderbook deltas (`OrderBookDelta` from `orderbooks/` data) deferred to Plan 4 or later — requires reconstructing incremental deltas from snapshots, which is complex
- The catalog default path (`~/.nautilus/catalog`) is the same path NautilusTrader's backtester reads from by default
