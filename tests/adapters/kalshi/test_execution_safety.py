import pytest
import fakeredis
import os
import tempfile
from unittest.mock import MagicMock
from safety.state_store import StateStore
from safety.quarantine import QuarantineBook
from safety.alerts import AlertDispatcher, AlertConfig
from safety.reconciliation import ReconciliationGate
from safety.position_limits import PositionLimitChecker
from safety.types import OrderRecord
from adapters.kalshi.execution import kalshi_order_payload
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.objects import Price, Quantity


def test_kalshi_order_payload_records_side_correctly():
    """Test that BUY orders map to 'yes' side with correct price cents."""
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
    """Test position limit checker allows orders within limits and rejects those exceeding limits."""
    checker = PositionLimitChecker(limits={"KXBTC15M": 50})

    # Order that fits within limit
    assert checker.check(
        ticker="KXBTC15M-X",
        strategy_id="s",
        current_position=40,
        order_quantity=5
    )

    # Order that would exceed limit
    assert not checker.check(
        ticker="KXBTC15M-X",
        strategy_id="s",
        current_position=48,
        order_quantity=5
    )


def test_reconciliation_gate_marks_missed_fill():
    """Test that reconciliation gate detects and marks missed fills from exchange."""
    fake_redis = fakeredis.FakeRedis(decode_responses=True)
    store = StateStore(redis_client=fake_redis)

    # Save an open order locally
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

    # Mock HTTP client with exchange data showing the order was filled
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

    # Set up quarantine and alerts
    quarantine = QuarantineBook(log_path=os.path.join(tempfile.mkdtemp(), "q.jsonl"))
    alerts = AlertDispatcher(config=AlertConfig(console=False, email=False))

    # Run reconciliation
    gate = ReconciliationGate(store=store, http=http, quarantine=quarantine, alerts=alerts)
    result = gate.run()

    # Verify the reconciliation was clean
    assert result.is_clean

    # Verify the order was marked as filled in local store
    order = store.get_order("clord-001")
    assert order.status == "filled"
    assert order.filled == 10
