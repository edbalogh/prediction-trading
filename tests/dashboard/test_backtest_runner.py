# tests/dashboard/test_backtest_runner.py
import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import dashboard.api.db.database as database
from dashboard.api.db.database import init_db, db_write, db_query
from dashboard.api.services.backtest_runner import BacktestRunner


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "_DB_PATH", tmp_path / "test.db")
    init_db()


class _FakeStream:
    """Async-iterable fake stdout for subprocess mocks."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = [(line + "\n").encode() for line in lines]
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> bytes:
        if self._idx >= len(self._lines):
            raise StopAsyncIteration
        data = self._lines[self._idx]
        self._idx += 1
        return data


def _make_mock_proc(lines: list[str], returncode: int = 0) -> MagicMock:
    proc = MagicMock()
    proc.returncode = returncode
    proc.wait = AsyncMock(return_value=returncode)
    proc.stdout = _FakeStream(lines)
    return proc


_RESULT_LINE = json.dumps({
    "type": "result",
    "kpis": {
        "total_trades": 5,
        "win_rate": 0.6,
        "realized_pnl": 10.0,
        "max_drawdown": -2.0,
        "sharpe": 1.0,
    },
    "trades": [{"ts": 1000, "ticker": "K-stub", "side": "YES", "qty": 1, "price": 0.5, "pnl": 5.0}],
    "equity_curve": [{"ts": 1000, "equity": 10010.0}],
})


async def test_start_creates_row_and_stores_result():
    runner = BacktestRunner()
    lines = ['{"type":"progress","pct":50,"msg":"halfway"}', _RESULT_LINE]
    mock_proc = _make_mock_proc(lines)
    with patch(
        "dashboard.api.services.backtest_runner.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        run_id = await runner.start(
            "mlb_burst", Path("backtest.py"), Path("/root"),
            {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
        )
        await asyncio.sleep(0.05)

    run = await runner.get_run(run_id)
    assert run["status"] == "done"
    assert run["kpis"]["total_trades"] == 5
    assert run["equity_curve"][0]["equity"] == 10010.0


async def test_start_marks_error_on_missing_result_line():
    runner = BacktestRunner()
    mock_proc = _make_mock_proc([])  # no result line, exits cleanly
    with patch(
        "dashboard.api.services.backtest_runner.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        run_id = await runner.start(
            "mlb_burst", Path("backtest.py"), Path("/root"),
            {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
        )
        await asyncio.sleep(0.05)

    run = await runner.get_run(run_id)
    assert run["status"] == "error"


async def test_is_running_true_immediately_after_start():
    runner = BacktestRunner()
    mock_proc = _make_mock_proc([_RESULT_LINE])
    with patch(
        "dashboard.api.services.backtest_runner.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        await runner.start(
            "mlb_burst", Path("backtest.py"), Path("/root"),
            {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
        )
    assert runner.is_running("mlb_burst")


async def test_start_raises_if_already_running():
    runner = BacktestRunner()
    mock_proc = _make_mock_proc([_RESULT_LINE])
    with patch(
        "dashboard.api.services.backtest_runner.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        await runner.start(
            "mlb_burst", Path("backtest.py"), Path("/root"),
            {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
        )
        with pytest.raises(RuntimeError, match="already running"):
            await runner.start(
                "mlb_burst", Path("backtest.py"), Path("/root"),
                {"start_date": "2025-01-01", "end_date": "2025-03-31", "overrides": {}},
            )


async def test_list_runs_returns_most_recent_first():
    runner = BacktestRunner()
    await db_write(
        "INSERT INTO backtest_runs (id, strategy, started_at, status, params) VALUES (?, ?, ?, ?, ?)",
        ("r1", "mlb_burst", 1000, "done", "{}"),
    )
    await db_write(
        "INSERT INTO backtest_runs (id, strategy, started_at, status, params) VALUES (?, ?, ?, ?, ?)",
        ("r2", "mlb_burst", 2000, "done", "{}"),
    )
    runs = await runner.list_runs("mlb_burst")
    assert runs[0]["run_id"] == "r2"
    assert runs[1]["run_id"] == "r1"


async def test_get_run_returns_none_for_unknown():
    runner = BacktestRunner()
    result = await runner.get_run("nonexistent")
    assert result is None
