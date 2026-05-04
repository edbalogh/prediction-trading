from safety.types import OrderRecord, ReconciliationResult, OrphanEvent, AlertEvent


def test_order_record_construction():
    record = OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-25APR30-T65499.99",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    )
    assert record.client_order_id == "clord-001"
    assert record.is_open


def test_order_record_is_open_for_partial_fill():
    record = OrderRecord(
        client_order_id="clord-002",
        kalshi_order_id="kalshi-xyz",
        ticker="KXBTC15M-25APR30-T65499.99",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=4,
        status="open",
    )
    assert record.is_open
    assert not record.is_filled


def test_reconciliation_result_has_gaps():
    result = ReconciliationResult(
        resolved_fills=[],
        resolved_cancels=[],
        orphan_orders=["kalshi-999"],
        orphan_fills=[],
        orphan_positions=[],
        unresolvable=[{"reason": "unknown order", "data": {}}],
    )
    assert result.has_unresolvable
    assert not result.is_clean


def test_reconciliation_result_is_clean():
    result = ReconciliationResult(
        resolved_fills=[],
        resolved_cancels=[],
        orphan_orders=[],
        orphan_fills=[],
        orphan_positions=[],
        unresolvable=[],
    )
    assert result.is_clean


def test_orphan_event_construction():
    event = OrphanEvent(
        event_type="ORDER",
        ticker="KXBTC15M-X",
        strategy_id=None,
        detail={"kalshi_order_id": "abc"},
        ts=1234567890,
    )
    assert event.event_type == "ORDER"


def test_alert_event_construction():
    event = AlertEvent(
        level="CRITICAL",
        message="Orphan position detected",
        context={"ticker": "KXBTC15M-X"},
    )
    assert event.level == "CRITICAL"
