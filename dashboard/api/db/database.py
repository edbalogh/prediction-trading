# dashboard/api/db/database.py
from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

_DB_PATH: Path = Path(__file__).parent.parent.parent / "db" / "backtests.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS backtest_runs (
    id           TEXT    PRIMARY KEY,
    strategy     TEXT    NOT NULL,
    started_at   INTEGER NOT NULL,
    finished_at  INTEGER,
    status       TEXT    NOT NULL,
    progress_pct INTEGER DEFAULT 0,
    progress_msg TEXT,
    params       TEXT    NOT NULL,
    result       TEXT
);
"""


def init_db() -> None:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.executescript(_SCHEMA)


def _run_query(sql: str, params: tuple) -> list[dict[str, Any]]:
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def _run_write(sql: str, params: tuple) -> None:
    with sqlite3.connect(str(_DB_PATH)) as conn:
        conn.execute(sql, params)
        conn.commit()


async def db_query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_run_query, sql, params)


async def db_write(sql: str, params: tuple = ()) -> None:
    await asyncio.to_thread(_run_write, sql, params)
