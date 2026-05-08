import pytest
import respx
import httpx
from dashboard.api.services.state_poller import StatePoller, normalize_state


MOCK_STATE = {
    "equity": 10_284.50,
    "starting_capital": 10_000.0,
    "pnl": 284.50,
    "realized_pnl": 266.30,
    "unrealized_pnl": 18.20,
    "positions": {
        "KXMLB-NYY": {"qty": 2, "avg_px": 0.62, "last_px": 0.66, "unrealized_pnl": 8.00},
    },
    "fills": [
        {"ticker": "KXMLB-ATL", "side": "SETTLE", "qty": 2,
         "price": 1.0, "result": "yes", "pnl": 62.0, "ts": 1746700000, "type": "settlement"},
        {"ticker": "KXMLB-BOS", "side": "BUY", "qty": 1,
         "price": 0.54, "ts": 1746699000, "type": "trade"},
    ],
    "entered_games": [],
    "pending_tasks_count": 0,
    "subscribed_markets": ["KXMLB-NYY"],
    "ts": 1746720000,
}


def test_normalize_state_basic_fields():
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=[])
    assert snap["strategy"] == "mlb_burst"
    assert snap["mode"] == "paper"
    assert snap["status"] == "running"
    assert snap["equity"] == 10_284.50
    assert snap["realized_pnl"] == 266.30
    assert snap["unrealized_pnl"] == 18.20
    assert snap["ts"] == 1746720000


def test_normalize_state_positions():
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=[])
    positions = snap["positions"]
    assert len(positions) == 1
    assert positions[0]["ticker"] == "KXMLB-NYY"
    assert positions[0]["qty"] == 2
    assert positions[0]["avg_px"] == 0.62
    assert positions[0]["unrealized_pnl"] == 8.00


def test_normalize_state_fills_returned_reversed():
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=[])
    fills = snap["recent_fills"]
    # Most recent first
    assert fills[0]["ticker"] == "KXMLB-BOS"
    assert fills[1]["ticker"] == "KXMLB-ATL"


def test_normalize_state_win_rate_from_settlements():
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=[])
    # 1 settlement with pnl=62.0 (win), 0 losses → 100%
    assert snap["win_rate"] == 1.0
    assert snap["total_trades"] == 2  # total fills count


def test_normalize_state_win_rate_none_when_no_settlements():
    state = {**MOCK_STATE, "fills": []}
    snap = normalize_state("mlb_burst", "paper", state, equity_history=[])
    assert snap["win_rate"] is None
    assert snap["total_trades"] == 0


def test_normalize_state_equity_history_appended():
    history = [{"ts": 1746700000, "equity": 10_100.0}]
    snap = normalize_state("mlb_burst", "paper", MOCK_STATE, equity_history=history)
    assert snap["equity_history"][-1]["equity"] == 10_284.50
    assert snap["equity_history"][-1]["ts"] == 1746720000


@pytest.mark.asyncio
async def test_poller_fetches_state():
    with respx.mock:
        respx.get("http://localhost:8766/state").mock(
            return_value=httpx.Response(200, json=MOCK_STATE)
        )
        poller = StatePoller()
        await poller.poll_once("mlb_burst", port=8766)
        snap = poller.get_snapshot("mlb_burst")
        assert snap is not None
        assert snap["equity"] == 10_284.50


@pytest.mark.asyncio
async def test_poller_marks_stopped_on_connection_error():
    with respx.mock:
        respx.get("http://localhost:8767/state").mock(
            side_effect=httpx.ConnectError("refused")
        )
        poller = StatePoller()
        await poller.poll_once("threshold", port=8767)
        snap = poller.get_snapshot("threshold")
        assert snap["status"] == "stopped"
