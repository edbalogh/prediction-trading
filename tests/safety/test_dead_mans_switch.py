import time
import pytest
import fakeredis
from unittest.mock import MagicMock
from safety.dead_mans_switch import DeadMansSwitch
from safety.state_store import StateStore
from safety.types import OrderRecord


@pytest.fixture()
def store():
    return StateStore(redis_client=fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture()
def mock_http():
    client = MagicMock()
    return client


def test_heartbeat_prevents_cancellation(mock_http, store):
    dms = DeadMansSwitch(http=mock_http, store=store, timeout_secs=0.2, poll_interval_secs=0.05)
    dms.register_strategy("stat_arb")
    dms.start()
    dms.heartbeat("stat_arb")
    time.sleep(0.1)
    dms.heartbeat("stat_arb")
    time.sleep(0.1)
    dms.stop()
    mock_http.cancel_order.assert_not_called()


def test_expired_strategy_triggers_cancel(mock_http, store):
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
    dms = DeadMansSwitch(http=mock_http, store=store, timeout_secs=0.05, poll_interval_secs=0.02)
    dms.register_strategy("stat_arb")
    dms.start()
    time.sleep(0.15)
    dms.stop()
    mock_http.cancel_order.assert_called_with("kalshi-abc")


def test_unregistered_strategy_not_monitored(mock_http, store):
    dms = DeadMansSwitch(http=mock_http, store=store, timeout_secs=0.05, poll_interval_secs=0.02)
    dms.start()
    time.sleep(0.15)
    dms.stop()
    mock_http.cancel_order.assert_not_called()
