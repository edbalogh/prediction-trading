from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from nautilus_trader.model.data import Bar, BarSpecification, BarType, TradeTick  # Bar/BarType used in Tasks 3-4
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
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        delta = dt - epoch
        return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000
    if unit == "ms":
        return int(value) * 1_000_000
    return int(value) * 1_000_000_000


def interval_minutes_to_bar_spec(interval_minutes: int) -> BarSpecification:
    spec = _INTERVAL_MAP.get(interval_minutes)
    if spec is None:
        raise ValueError(f"Unsupported interval_minutes={interval_minutes}. Supported: {sorted(_INTERVAL_MAP)}")
    return spec


def taker_side_to_aggressor(side: str) -> AggressorSide:
    if side == "yes":
        return AggressorSide.BUYER
    if side == "no":
        return AggressorSide.SELLER
    raise ValueError(f"Unknown taker_side value: {side!r}. Expected 'yes' or 'no'.")


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
            taker_raw = row.get("taker_side")
            if taker_raw is None or (isinstance(taker_raw, float) and pd.isna(taker_raw)):
                taker_raw = "yes"
            count_raw = row.get("count_fp")
            if count_raw is None or (isinstance(count_raw, float) and pd.isna(count_raw)):
                continue
            instrument_id = InstrumentId(Symbol(str(row["ticker"])), KALSHI_VENUE)
            ticks.append(TradeTick(
                instrument_id=instrument_id,
                price=Price(round(price_val, 2), 2),
                size=Quantity(int(float(str(count_raw))), 0),
                aggressor_side=taker_side_to_aggressor(str(taker_raw)),
                trade_id=TradeId(str(row["trade_id"])),
                ts_event=parse_ts_ns(str(row["created_time"])),
                ts_init=parse_ts_ns(str(row["created_time"])),
            ))
        if ticks:
            ticks.sort(key=lambda t: t.ts_event)
            self._catalog.write_data(ticks)
        _logger.info("sync_trades_file: wrote %d ticks from %s", len(ticks), parquet_path)
        self._mark_synced(parquet_path)
        return len(ticks)

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
        self._mark_synced(parquet_path)
        return len(bars)
