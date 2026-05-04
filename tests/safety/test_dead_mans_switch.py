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
