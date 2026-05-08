# dashboard/api/services/process_mgr.py
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)
_SIGTERM_TIMEOUT = 5.0  # seconds to wait after SIGTERM before SIGKILL


class ProcessManager:
    """Spawns and tracks strategy subprocess instances."""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}
        self._modes: dict[str, str] = {}

    def is_running(self, name: str) -> bool:
        proc = self._processes.get(name)
        return proc is not None and proc.returncode is None

    def get_mode(self, name: str) -> str | None:
        return self._modes.get(name) if self.is_running(name) else None

    async def start(self, name: str, mode: str, script: Path, cwd: Path) -> None:
        """Launch strategy subprocess. Raises RuntimeError if already running."""
        if self.is_running(name):
            raise RuntimeError(f"{name} already running")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(script),
            cwd=str(cwd),
        )
        self._processes[name] = proc
        self._modes[name] = mode
        _logger.info("Started %s (%s) pid=%d", name, mode, proc.pid)

    async def stop(self, name: str) -> None:
        """Send SIGTERM; escalate to SIGKILL after timeout. Raises if not running."""
        if not self.is_running(name):
            raise RuntimeError(f"{name} not running")
        proc = self._processes[name]
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=_SIGTERM_TIMEOUT)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
        self._processes.pop(name, None)
        self._modes.pop(name, None)
        _logger.info("Stopped %s", name)
