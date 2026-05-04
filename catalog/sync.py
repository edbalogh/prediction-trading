from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

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
