from __future__ import annotations

import logging
import time
from nautilus_trader.core.uuid import UUID4
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, TYPE_CHECKING

from nautilus_trader.execution.reports import FillReport, OrderStatusReport
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.model.enums import AccountType, LiquiditySide, OmsType, OrderSide, OrderStatus, OrderType, TimeInForce
from nautilus_trader.model.identifiers import (
    AccountId,
    ClientId,
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


class KalshiExecutionClient(LiveExecutionClient):
    def __init__(
        self,
        *,
        http_client,
        config,
        **kwargs,
    ) -> None:
        super().__init__(
            client_id=ClientId("KALSHI"),
            venue=KALSHI_VENUE,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=Currency.from_str("USD"),
            **kwargs,
        )
        self._http = http_client
        self._config = config

    async def _connect(self) -> None:
        _logger.info("KalshiExecutionClient connecting")

    async def _disconnect(self) -> None:
        _logger.info("KalshiExecutionClient disconnecting")

    def generate_order_status_reports(self, instrument_id=None, start=None, end=None, open_only=False):
        ts_init = time.time_ns()
        raw_orders = self._http.list_recent_orders()
        reports = []
        for raw in raw_orders:
            try:
                reports.append(map_order_status_report(raw, account_id=self.account_id, ts_init=ts_init))
            except Exception:
                _logger.exception("failed to map order %s", raw.get("order_id"))
        return reports

    def generate_fill_reports(self, instrument_id=None, venue_order_id=None, start=None, end=None):
        ts_init = time.time_ns()
        raw_fills = self._http.list_recent_fills()
        reports = []
        for raw in raw_fills:
            try:
                ticker = raw["ticker"]
                instrument_id_fill = kalshi_ticker_to_instrument_id(ticker)
                yes_price_val = raw.get("yes_price")
                no_price_val = raw.get("no_price")
                if yes_price_val is not None:
                    yes_price = yes_price_val
                elif no_price_val is not None:
                    yes_price = 100 - no_price_val
                else:
                    raise ValueError(f"fill {raw.get('trade_id')} has neither yes_price nor no_price")
                side_str = raw.get("side", "yes")
                order_side = OrderSide.BUY if side_str == "yes" else OrderSide.SELL
                reports.append(FillReport(
                    account_id=self.account_id,
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
                    report_id=UUID4(),
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
