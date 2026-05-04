from __future__ import annotations

import logging
import time
from nautilus_trader.core.uuid import UUID4
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from nautilus_trader.execution.reports import FillReport, OrderStatusReport
from nautilus_trader.model.enums import LiquiditySide, OrderSide, OrderStatus, OrderType, TimeInForce
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientOrderId,
    InstrumentId,
    Symbol,
    TradeId,
    VenueOrderId,
)
from nautilus_trader.model.objects import Currency, Money, Price, Quantity

from adapters.kalshi.constants import KALSHI_VENUE, PRICE_PRECISION, SIZE_PRECISION
from adapters.kalshi.factories import kalshi_ticker_to_instrument_id

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
    yes_price = raw.get("yes_price") or (100 - (raw.get("no_price") or 0))
    side_str = raw.get("side", "yes")
    order_side = OrderSide.BUY if side_str == "yes" else OrderSide.SELL

    avg_px = Decimal(str(round(yes_price / 100, PRICE_PRECISION))) if filled > 0 else None

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
        avg_px=avg_px,
        ts_accepted=_parse_ts(raw.get("created_time")),
        ts_last=_parse_ts(raw.get("updated_time") or raw.get("created_time")),
        ts_init=ts_init,
        report_id=UUID4(),
    )


# Stub class — full LiveExecutionClient integration wired up in Task 8+
class KalshiExecutionClient:
    """
    Kalshi execution client stub.

    NOTE: Does not inherit from LiveExecutionClient yet; full wiring
    will be done during integration (Task 8+). The pure helper functions
    kalshi_order_payload and map_order_status_report are fully implemented.
    """

    def __init__(self, *, http_client, config, **kwargs) -> None:
        self._http = http_client
        self._config = config
