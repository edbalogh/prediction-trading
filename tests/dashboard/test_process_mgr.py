# tests/dashboard/test_process_mgr.py
import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from dashboard.api.services.process_mgr import ProcessManager


def _make_mock_proc(returncode=None):
    """Return a mock asyncio.subprocess.Process."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    return proc


@pytest.mark.asyncio
async def test_start_launches_subprocess():
    mgr = ProcessManager()
    mock_proc = _make_mock_proc(returncode=None)
    with patch(
        "dashboard.api.services.process_mgr.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        await mgr.start("mlb_burst", "paper", Path("scripts/paper_trade_mlb.py"), Path("/root"))
    assert mgr.is_running("mlb_burst")
    assert mgr.get_mode("mlb_burst") == "paper"


@pytest.mark.asyncio
async def test_start_raises_if_already_running():
    mgr = ProcessManager()
    mock_proc = _make_mock_proc(returncode=None)
    with patch(
        "dashboard.api.services.process_mgr.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        await mgr.start("mlb_burst", "paper", Path("scripts/paper_trade_mlb.py"), Path("/root"))
        with pytest.raises(RuntimeError, match="already running"):
            await mgr.start("mlb_burst", "paper", Path("scripts/paper_trade_mlb.py"), Path("/root"))


@pytest.mark.asyncio
async def test_stop_sends_sigterm():
    mgr = ProcessManager()
    mock_proc = _make_mock_proc(returncode=None)
    with patch(
        "dashboard.api.services.process_mgr.asyncio.create_subprocess_exec",
        new=AsyncMock(return_value=mock_proc),
    ):
        await mgr.start("mlb_burst", "paper", Path("scripts/paper_trade_mlb.py"), Path("/root"))
        await mgr.stop("mlb_burst")
    mock_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_stop_raises_if_not_running():
    mgr = ProcessManager()
    with pytest.raises(RuntimeError, match="not running"):
        await mgr.stop("mlb_burst")


def test_is_running_false_when_process_exited():
    mgr = ProcessManager()
    mock_proc = _make_mock_proc(returncode=0)  # process has exited
    mgr._processes["mlb_burst"] = mock_proc
    assert mgr.is_running("mlb_burst") is False


def test_is_running_true_when_process_alive():
    mgr = ProcessManager()
    mock_proc = _make_mock_proc(returncode=None)  # still running
    mgr._processes["mlb_burst"] = mock_proc
    mgr._modes["mlb_burst"] = "paper"
    assert mgr.is_running("mlb_burst") is True


def test_get_mode_returns_none_when_stopped():
    mgr = ProcessManager()
    assert mgr.get_mode("mlb_burst") is None


def test_get_mode_returns_mode_when_running():
    mgr = ProcessManager()
    mock_proc = _make_mock_proc(returncode=None)
    mgr._processes["mlb_burst"] = mock_proc
    mgr._modes["mlb_burst"] = "live"
    assert mgr.get_mode("mlb_burst") == "live"
