# tests/dashboard/test_control_routes.py
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch

from dashboard.api.main import create_app
from dashboard.api.services.state_poller import StatePoller
from dashboard.api.services.process_mgr import ProcessManager


def _make_test_client(process_mgr=None, poller=None):
    mock_poller = poller or MagicMock(spec=StatePoller)
    mock_poller.get_snapshot.return_value = None
    mock_mgr = process_mgr or MagicMock(spec=ProcessManager)
    mock_mgr.is_running.return_value = False
    app = create_app(poller=mock_poller, process_mgr=mock_mgr)
    return TestClient(app)


# --- start/stop ---

def test_start_strategy_returns_200():
    mgr = MagicMock(spec=ProcessManager)
    mgr.is_running.return_value = False
    mgr.start = AsyncMock()
    client = _make_test_client(process_mgr=mgr)
    resp = client.post("/api/strategies/mlb_burst/start?mode=paper")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


def test_start_unknown_strategy_returns_404():
    client = _make_test_client()
    resp = client.post("/api/strategies/nonexistent/start?mode=paper")
    assert resp.status_code == 404


def test_start_already_running_returns_409():
    mgr = MagicMock(spec=ProcessManager)
    mgr.is_running.return_value = True
    client = _make_test_client(process_mgr=mgr)
    resp = client.post("/api/strategies/mlb_burst/start?mode=paper")
    assert resp.status_code == 409


def test_stop_strategy_returns_200():
    mgr = MagicMock(spec=ProcessManager)
    mgr.is_running.return_value = True
    mgr.stop = AsyncMock()
    client = _make_test_client(process_mgr=mgr)
    resp = client.post("/api/strategies/mlb_burst/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


def test_stop_not_running_returns_409():
    mgr = MagicMock(spec=ProcessManager)
    mgr.is_running.return_value = False
    client = _make_test_client(process_mgr=mgr)
    resp = client.post("/api/strategies/mlb_burst/stop")
    assert resp.status_code == 409


# --- config ---

def test_get_config_returns_schema_and_values(tmp_path):
    with patch("dashboard.api.routes.strategies.config_mgr.read_config",
               return_value={"sweep_min_spread_cents": 7, "bail_seconds": 60,
                             "sweep_min_fills": 2, "sweep_max_duration_s": 0.5,
                             "w1_window_start_s": 0.3, "w1_window_end_s": 3.0,
                             "w1_min_trades": 2, "w1_same_dir_pct": 0.6,
                             "max_notional_usd": 1.0}):
        client = _make_test_client()
        resp = client.get("/api/strategies/mlb_burst/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "schema" in data
    assert "values" in data
    assert data["values"]["sweep_min_spread_cents"] == 7


def test_put_config_saves_valid_values():
    with patch("dashboard.api.routes.strategies.config_mgr.validate_config", return_value=[]), \
         patch("dashboard.api.routes.strategies.config_mgr.write_config") as mock_write:
        client = _make_test_client()
        payload = {"sweep_min_spread_cents": 5, "bail_seconds": 30,
                   "sweep_min_fills": 2, "sweep_max_duration_s": 0.5,
                   "w1_window_start_s": 0.3, "w1_window_end_s": 3.0,
                   "w1_min_trades": 2, "w1_same_dir_pct": 0.6, "max_notional_usd": 1.0}
        resp = client.put("/api/strategies/mlb_burst/config", json=payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "saved"
    mock_write.assert_called_once()


def test_put_config_rejects_invalid_values():
    with patch("dashboard.api.routes.strategies.config_mgr.validate_config",
               return_value=["sweep_min_spread_cents: expected int, got str"]):
        client = _make_test_client()
        resp = client.put("/api/strategies/mlb_burst/config",
                          json={"sweep_min_spread_cents": "five"})
    assert resp.status_code == 422
