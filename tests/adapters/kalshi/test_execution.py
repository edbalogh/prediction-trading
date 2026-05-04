import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId, Symbol, ClientOrderId, VenueOrderId, AccountId
from nautilus_trader.model.objects import Price, Quantity

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
