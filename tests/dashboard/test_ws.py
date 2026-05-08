import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from dashboard.api.main import create_app
from dashboard.api.services.state_poller import StatePoller
from dashboard.api.routes.ws import ConnectionManager


SAMPLE_SNAP = {
    "strategy": "mlb_burst", "mode": "paper", "status": "running",
    "ts": 1746720000, "equity": 10_284.50, "starting_capital": 10_000.0,
    "realized_pnl": 266.30, "unrealized_pnl": 18.20,
    "total_trades": 2, "win_rate": 1.0,
    "positions": [], "recent_fills": [], "equity_history": [],
}


def test_websocket_connection_accepted():
    """Verify the /ws endpoint accepts connections."""
    poller = MagicMock(spec=StatePoller)
    poller.all_snapshots.return_value = []
    app = create_app(poller=poller)
    client = TestClient(app)
    with client.websocket_connect("/ws") as ws:
        assert ws is not None  # connection opened without error


@pytest.mark.asyncio
async def test_broadcast_delivers_to_connected_client():
    """Verify ConnectionManager.broadcast() sends data to mock websockets."""
    received: list[dict] = []

    class MockWS:
        async def send_json(self, data: dict) -> None:
            received.append(data)

    manager = ConnectionManager()
    manager._connections.append(MockWS())  # type: ignore[arg-type]

    await manager.broadcast({"snapshots": [SAMPLE_SNAP]})

    assert len(received) == 1
    assert received[0]["snapshots"][0]["strategy"] == "mlb_burst"
    assert received[0]["snapshots"][0]["equity"] == 10_284.50


@pytest.mark.asyncio
async def test_broadcast_removes_dead_connections():
    """Dead WebSocket connections are removed from the manager."""

    class DeadWS:
        async def send_json(self, data: dict) -> None:
            raise RuntimeError("connection closed")

    manager = ConnectionManager()
    manager._connections.append(DeadWS())  # type: ignore[arg-type]

    await manager.broadcast({"snapshots": []})

    assert len(manager._connections) == 0
