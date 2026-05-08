# dashboard/api/services/backtest_runner.py
from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from dashboard.api.db import database

_logger = logging.getLogger(__name__)


class BacktestRunner:
    """Spawns strategy backtest subprocesses and tracks results in SQLite."""

    def __init__(self) -> None:
        self._running: dict[str, str] = {}  # strategy -> run_id

    def is_running(self, strategy: str) -> bool:
        return strategy in self._running

    async def start(
        self,
        strategy: str,
        script: Path,
        cwd: Path,
        params: dict[str, Any],
    ) -> str:
        """Insert a running row, fire background task, return run_id."""
        if self.is_running(strategy):
            raise RuntimeError(f"{strategy} already running")
        run_id = uuid.uuid4().hex
        now = int(time.time())
        await database.db_write(
            "INSERT INTO backtest_runs (id, strategy, started_at, status, params) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, strategy, now, "running", json.dumps(params)),
        )
        self._running[strategy] = run_id
        task = asyncio.create_task(self._run(run_id, strategy, script, cwd, params))
        task.add_done_callback(
            lambda t: _logger.error("Backtest task raised", exc_info=t.exception())
            if not t.cancelled() and t.exception()
            else None
        )
        return run_id

    async def _run(
        self,
        run_id: str,
        strategy: str,
        script: Path,
        cwd: Path,
        params: dict[str, Any],
    ) -> None:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(script),
            "--start", params["start_date"],
            "--end", params["end_date"],
            "--params", json.dumps(params.get("overrides", {})),
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        result_data: dict | None = None
        try:
            async for raw_line in proc.stdout:
                line = raw_line.decode().strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "progress":
                    await database.db_write(
                        "UPDATE backtest_runs SET progress_pct=?, progress_msg=? WHERE id=?",
                        (event.get("pct", 0), event.get("msg", ""), run_id),
                    )
                elif event.get("type") == "result":
                    result_data = event
        finally:
            await proc.wait()
            self._running.pop(strategy, None)

        now = int(time.time())
        if result_data and proc.returncode == 0:
            await database.db_write(
                "UPDATE backtest_runs "
                "SET status=?, finished_at=?, progress_pct=100, result=? WHERE id=?",
                ("done", now, json.dumps(result_data), run_id),
            )
        else:
            await database.db_write(
                "UPDATE backtest_runs SET status=?, finished_at=? WHERE id=?",
                ("error", now, run_id),
            )
        _logger.info("Backtest %s finished: %s", run_id, "done" if result_data else "error")

    async def list_runs(self, strategy: str) -> list[dict[str, Any]]:
        rows = await database.db_query(
            "SELECT id, strategy, started_at, finished_at, status, progress_pct, params "
            "FROM backtest_runs WHERE strategy=? ORDER BY started_at DESC",
            (strategy,),
        )
        result = []
        for row in rows:
            r = dict(row)
            r["run_id"] = r.pop("id")
            r["params"] = json.loads(r["params"])
            result.append(r)
        return result

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        rows = await database.db_query(
            "SELECT * FROM backtest_runs WHERE id=?",
            (run_id,),
        )
        if not rows:
            return None
        row = dict(rows[0])
        row["run_id"] = row.pop("id")
        row["params"] = json.loads(row["params"])
        raw_result = row.pop("result", None)
        if raw_result:
            parsed = json.loads(raw_result)
            row["kpis"] = parsed.get("kpis")
            row["trades"] = parsed.get("trades")
            row["equity_curve"] = parsed.get("equity_curve")
        else:
            row["kpis"] = None
            row["trades"] = None
            row["equity_curve"] = None
        return row
