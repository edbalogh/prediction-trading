# tests/dashboard/test_database.py
import pytest
import dashboard.api.db.database as database
from dashboard.api.db.database import init_db, db_query, db_write


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "_DB_PATH", tmp_path / "test.db")
    init_db()


async def test_init_creates_backtest_runs_table():
    rows = await db_query(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='backtest_runs'", ()
    )
    assert len(rows) == 1


async def test_db_write_and_query_roundtrip():
    await db_write(
        "INSERT INTO backtest_runs (id, strategy, started_at, status, params) "
        "VALUES (?, ?, ?, ?, ?)",
        ("run1", "mlb_burst", 1000, "running", "{}"),
    )
    rows = await db_query("SELECT * FROM backtest_runs WHERE id=?", ("run1",))
    assert len(rows) == 1
    assert rows[0]["strategy"] == "mlb_burst"
    assert rows[0]["status"] == "running"


async def test_db_write_updates_existing_row():
    await db_write(
        "INSERT INTO backtest_runs (id, strategy, started_at, status, params) "
        "VALUES (?, ?, ?, ?, ?)",
        ("run2", "threshold", 2000, "running", "{}"),
    )
    await db_write("UPDATE backtest_runs SET status=? WHERE id=?", ("done", "run2"))
    rows = await db_query("SELECT status FROM backtest_runs WHERE id=?", ("run2",))
    assert rows[0]["status"] == "done"
