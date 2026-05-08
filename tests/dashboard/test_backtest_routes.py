# tests/dashboard/test_backtest_routes.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock

from dashboard.api.main import create_app
from dashboard.api.services.state_poller import StatePoller
from dashboard.api.services.process_mgr import ProcessManager
from dashboard.api.services.backtest_runner import BacktestRunner


def _make_client(runner: MagicMock | None = None) -> TestClient:
    mock_poller = MagicMock(spec=StatePoller)
    mock_poller.get_snapshot.return_value = None
    mock_mgr = MagicMock(spec=ProcessManager)
    mock_mgr.is_running.return_value = False
    mock_mgr.get_mode.return_value = None
    mock_runner = runner or MagicMock(spec=BacktestRunner)
    if runner is None:
        mock_runner.is_running.return_value = False
    app = create_app(poller=mock_poller, process_mgr=mock_mgr, backtest_runner=mock_runner)
    return TestClient(app)


def test_start_backtest_returns_200():
    runner = MagicMock(spec=BacktestRunner)
    runner.is_running.return_value = False
    runner.start = AsyncMock(return_value="run123")
    client = _make_client(runner=runner)
    resp = client.post(
        "/api/strategies/mlb_burst/backtests",
        json={"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
    )
    assert resp.status_code == 200
    assert resp.json()["run_id"] == "run123"


def test_start_backtest_unknown_strategy_returns_404():
    client = _make_client()
    resp = client.post(
        "/api/strategies/nonexistent/backtests",
        json={"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
    )
    assert resp.status_code == 404


def test_start_backtest_already_running_returns_409():
    runner = MagicMock(spec=BacktestRunner)
    runner.is_running.return_value = True
    client = _make_client(runner=runner)
    resp = client.post(
        "/api/strategies/mlb_burst/backtests",
        json={"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
    )
    assert resp.status_code == 409


def test_list_backtests_returns_runs():
    runner = MagicMock(spec=BacktestRunner)
    runner.is_running.return_value = False
    runner.list_runs = AsyncMock(return_value=[
        {
            "run_id": "abc", "strategy": "mlb_burst", "started_at": 1000,
            "finished_at": 2000, "status": "done", "progress_pct": 100,
            "params": {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
        }
    ])
    client = _make_client(runner=runner)
    resp = client.get("/api/strategies/mlb_burst/backtests")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["run_id"] == "abc"


def test_get_backtest_returns_detail():
    runner = MagicMock(spec=BacktestRunner)
    runner.is_running.return_value = False
    runner.get_run = AsyncMock(return_value={
        "run_id": "abc", "strategy": "mlb_burst", "status": "done",
        "progress_pct": 100, "progress_msg": "Complete",
        "params": {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
        "kpis": {"total_trades": 5, "win_rate": 0.6, "realized_pnl": 10.0,
                 "max_drawdown": -2.0, "sharpe": 1.0},
        "trades": [{"ts": 1000, "ticker": "K-stub", "side": "YES", "qty": 1, "price": 0.5, "pnl": 5.0}],
        "equity_curve": [{"ts": 1000, "equity": 10010.0}],
    })
    client = _make_client(runner=runner)
    resp = client.get("/api/backtests/abc")
    assert resp.status_code == 200
    assert resp.json()["kpis"]["total_trades"] == 5


def test_get_backtest_not_found_returns_404():
    runner = MagicMock(spec=BacktestRunner)
    runner.is_running.return_value = False
    runner.get_run = AsyncMock(return_value=None)
    client = _make_client(runner=runner)
    resp = client.get("/api/backtests/nonexistent")
    assert resp.status_code == 404


def test_export_returns_csv_with_correct_columns():
    runner = MagicMock(spec=BacktestRunner)
    runner.is_running.return_value = False
    runner.get_run = AsyncMock(return_value={
        "run_id": "abc", "status": "done", "kpis": None, "equity_curve": None,
        "trades": [{"ts": 1000, "ticker": "K-stub", "side": "YES", "qty": 1, "price": 0.5, "pnl": 5.0}],
    })
    client = _make_client(runner=runner)
    resp = client.get("/api/backtests/abc/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "ticker" in resp.text
    assert "K-stub" in resp.text


def test_export_not_done_returns_409():
    runner = MagicMock(spec=BacktestRunner)
    runner.is_running.return_value = False
    runner.get_run = AsyncMock(return_value={
        "run_id": "abc", "status": "running", "trades": None, "kpis": None, "equity_curve": None,
    })
    client = _make_client(runner=runner)
    resp = client.get("/api/backtests/abc/export")
    assert resp.status_code == 409


def test_start_backtest_no_script_returns_400(monkeypatch):
    import dashboard.api.routes.backtests as routes_module
    from dashboard.api.config import STRATEGIES
    patched = {**STRATEGIES}
    patched["mlb_burst"] = {k: v for k, v in STRATEGIES.get("mlb_burst", {}).items() if k != "backtest_script"}
    monkeypatch.setattr(routes_module, "STRATEGIES", patched)
    client = _make_client()
    resp = client.post(
        "/api/strategies/mlb_burst/backtests",
        json={"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
    )
    assert resp.status_code == 400
