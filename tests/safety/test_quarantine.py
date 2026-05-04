import json
import pytest
from safety.quarantine import QuarantineBook
from safety.types import OrphanEvent


@pytest.fixture()
def quarantine(tmp_path):
    log_path = str(tmp_path / "quarantine.jsonl")
    return QuarantineBook(log_path=log_path)


def test_append_writes_to_file(quarantine, tmp_path):
    event = OrphanEvent(
        event_type="ORDER",
        ticker="KXBTC15M-X",
        strategy_id=None,
        detail={"kalshi_order_id": "abc123"},
        ts=1000,
    )
    quarantine.append(event)
    log_path = str(tmp_path / "quarantine.jsonl")
    with open(log_path) as f:
        lines = f.readlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["event_type"] == "ORDER"
    assert data["detail"]["kalshi_order_id"] == "abc123"


def test_append_multiple_events(quarantine, tmp_path):
    for i in range(3):
        quarantine.append(OrphanEvent(
            event_type="FILL",
            ticker=f"KXBTC15M-{i}",
            strategy_id="stat_arb",
            detail={"trade_id": f"fill-{i}"},
            ts=1000 + i,
        ))
    log_path = str(tmp_path / "quarantine.jsonl")
    with open(log_path) as f:
        lines = f.readlines()
    assert len(lines) == 3


def test_get_all_returns_events(quarantine):
    quarantine.append(OrphanEvent(event_type="POSITION", ticker="KXBTC15M-X", strategy_id=None, detail={"qty": 5}, ts=1000))
    quarantine.append(OrphanEvent(event_type="ORDER", ticker="KXBTC15M-Y", strategy_id=None, detail={"id": "x"}, ts=1001))
    events = quarantine.get_all()
    assert len(events) == 2
    assert events[0].event_type == "POSITION"
    assert events[1].event_type == "ORDER"


def test_is_quarantined_returns_true_for_active_ticker(quarantine):
    quarantine.append(OrphanEvent(event_type="POSITION", ticker="KXBTC15M-X", strategy_id=None, detail={}, ts=1000))
    assert quarantine.is_quarantined("KXBTC15M-X")
    assert not quarantine.is_quarantined("KXBTC15M-Y")


def test_load_existing_restores_state_on_restart(tmp_path):
    log_path = str(tmp_path / "quarantine.jsonl")
    # First instance: write events
    q1 = QuarantineBook(log_path=log_path)
    q1.append(OrphanEvent(event_type="ORDER", ticker="KXBTC15M-X", strategy_id=None, detail={"id": "abc"}, ts=1000))
    q1.append(OrphanEvent(event_type="FILL", ticker="KXBTC15M-Y", strategy_id="stat_arb", detail={"id": "def"}, ts=1001))

    # Second instance: reload from same file
    q2 = QuarantineBook(log_path=log_path)
    events = q2.get_all()
    assert len(events) == 2
    assert events[0].event_type == "ORDER"
    assert events[1].ticker == "KXBTC15M-Y"
    assert q2.is_quarantined("KXBTC15M-X")
    assert q2.is_quarantined("KXBTC15M-Y")
    assert not q2.is_quarantined("KXBTC15M-Z")
