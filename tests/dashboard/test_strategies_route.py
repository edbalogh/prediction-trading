import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from dashboard.api.main import create_app
from dashboard.api.services.state_poller import StatePoller


@pytest.fixture
def client():
    poller = MagicMock(spec=StatePoller)
    poller.get_snapshot.side_effect = lambda name: (
        {
            "strategy": name, "mode": "paper", "status": "running",
            "equity": 10_284.50, "realized_pnl": 266.30,
            "unrealized_pnl": 18.20, "total_trades": 2, "win_rate": 1.0,
        }
        if name == "mlb_burst"
        else {"strategy": name, "mode": "paper", "status": "stopped",
              "equity": None, "realized_pnl": None, "unrealized_pnl": None,
              "total_trades": None, "win_rate": None}
    )
    app = create_app(poller=poller)
    with TestClient(app) as c:
        yield c


def test_get_strategies_returns_all(client):
    resp = client.get("/api/strategies")
    assert resp.status_code == 200
    data = resp.json()
    names = {s["name"] for s in data}
    assert "mlb_burst" in names
    assert "threshold" in names


def test_get_strategies_running_status(client):
    resp = client.get("/api/strategies")
    strategies = {s["name"]: s for s in resp.json()}
    assert strategies["mlb_burst"]["status"] == "running"
    assert strategies["mlb_burst"]["equity"] == 10_284.50


def test_get_strategies_stopped_status(client):
    resp = client.get("/api/strategies")
    strategies = {s["name"]: s for s in resp.json()}
    assert strategies["threshold"]["status"] == "stopped"
    assert strategies["threshold"]["equity"] is None
