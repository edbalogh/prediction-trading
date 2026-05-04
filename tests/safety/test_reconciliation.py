import pytest
import fakeredis
from unittest.mock import MagicMock
from safety.reconciliation import ReconciliationGate
from safety.state_store import StateStore
from safety.types import OrderRecord, ReconciliationResult
from safety.quarantine import QuarantineBook
from safety.alerts import AlertDispatcher, AlertConfig


@pytest.fixture()
def store():
    fake = fakeredis.FakeRedis(decode_responses=True)
    return StateStore(redis_client=fake)


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
    client.list_positions.return_value = []
    return client


def _open_order_record(client_order_id="clord-001", kalshi_order_id="kalshi-abc", ticker="KXBTC15M-X"):
    return OrderRecord(
        client_order_id=client_order_id,
        kalshi_order_id=kalshi_order_id,
        ticker=ticker,
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    )


def test_clean_run_when_states_match(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001", "status": "resting",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 10, "remaining_count": 10, "filled_count": 0}
    ]
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert result.is_clean


def test_detects_missed_fill(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001", "status": "executed",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 10, "remaining_count": 0, "filled_count": 10}
    ]
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert "clord-001" in result.resolved_fills or len(result.resolved_fills) == 1
    assert result.is_clean


def test_detects_missed_cancel(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001", "status": "canceled",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 10, "remaining_count": 10, "filled_count": 0}
    ]
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert "clord-001" in result.resolved_cancels
    assert result.is_clean


def test_detects_orphan_order_at_exchange(store, quarantine, alerts, mock_http):
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-unknown", "client_order_id": None, "status": "resting",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 5, "remaining_count": 5, "filled_count": 0}
    ]
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert "kalshi-unknown" in result.orphan_orders
    assert not result.is_clean


def test_detects_cached_order_missing_from_exchange(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = []
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert len(result.unresolvable) == 1
    assert "clord-001" in result.unresolvable[0].get("client_order_id", "")


def test_settled_position_is_cleared(store, quarantine, alerts, mock_http):
    record = _open_order_record()
    store.save_order(record)
    mock_http.list_recent_orders.return_value = [
        {"order_id": "kalshi-abc", "client_order_id": "clord-001", "status": "executed",
         "ticker": "KXBTC15M-X", "side": "yes", "yes_price": 55,
         "original_count": 10, "remaining_count": 0, "filled_count": 10}
    ]
    mock_http.list_positions.return_value = []
    gate = ReconciliationGate(store=store, http=mock_http, quarantine=quarantine, alerts=alerts)
    result = gate.run()
    assert result.is_clean
