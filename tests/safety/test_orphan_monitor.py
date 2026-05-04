import time
import pytest
import fakeredis
from unittest.mock import MagicMock
from safety.orphan_monitor import OrphanMonitor
from safety.state_store import StateStore
from safety.quarantine import QuarantineBook
from safety.alerts import AlertDispatcher, AlertConfig
from safety.types import OrderRecord


@pytest.fixture()
def store():
    return StateStore(redis_client=fakeredis.FakeRedis(decode_responses=True))


@pytest.fixture()
def quarantine(tmp_path):
    return QuarantineBook(log_path=str(tmp_path / "quarantine.jsonl"))


@pytest.fixture()
def alerts():
    return AlertDispatcher(config=AlertConfig(console=False, email=False))


@pytest.fixture()
def mock_http():
    client = MagicMock()
    client.list_recent_orders.return_value = []
    client.list_recent_fills.return_value = []
    return client


def test_tick_clean_when_no_orphans(store, quarantine, alerts, mock_http):
    monitor = OrphanMonitor(store=store, http=mock_http, quarantine=quarantine, alerts=alerts, interval_secs=60)
    result = monitor.tick()
    assert result["orphan_orders"] == 0
    assert result["orphan_fills"] == 0


def test_tick_detects_orphan_order(store, quarantine, alerts, mock_http):
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-ghost", "client_order_id": None, "status": "resting",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 5, "remaining_count": 5, "filled_count": 0}
    ]
    monitor = OrphanMonitor(store=store, http=mock_http, quarantine=quarantine, alerts=alerts, interval_secs=60)
    result = monitor.tick()
    assert result["orphan_orders"] == 1
    assert quarantine.is_quarantined("KXBTC15M-X")


def test_tick_detects_orphan_fill(store, quarantine, alerts, mock_http):
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
    mock_http.list_recent_fills.return_value = [
        {"trade_id": "fill-xyz", "order_id": "kalshi-UNKNOWN", "ticker": "KXBTC15M-X",
         "side": "yes", "yes_price": 55, "count": 5, "created_time": "2025-04-30T14:00:00Z"}
    ]
    monitor = OrphanMonitor(store=store, http=mock_http, quarantine=quarantine, alerts=alerts, interval_secs=60)
    result = monitor.tick()
    assert result["orphan_fills"] == 1


def test_monitor_starts_and_stops():
    store = MagicMock()
    store.get_open_orders.return_value = []
    http = MagicMock()
    http.list_recent_orders.return_value = []
    http.list_recent_fills.return_value = []
    quarantine = MagicMock()
    alerts = MagicMock()
    monitor = OrphanMonitor(store=store, http=http, quarantine=quarantine, alerts=alerts, interval_secs=0.05)
    monitor.start()
    time.sleep(0.15)
    monitor.stop()
    assert store.get_open_orders.call_count >= 1
