import pytest
from safety.position_limits import PositionLimitChecker


def test_check_passes_when_under_limit():
    checker = PositionLimitChecker(limits={"KXBTC15M": 100})
    assert checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=50, order_quantity=10)


def test_check_fails_when_over_limit():
    checker = PositionLimitChecker(limits={"KXBTC15M": 100})
    assert not checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=95, order_quantity=10)


def test_check_passes_at_exact_limit():
    checker = PositionLimitChecker(limits={"KXBTC15M": 100})
    assert checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=90, order_quantity=10)


def test_check_uses_series_prefix_for_lookup():
    checker = PositionLimitChecker(limits={"KXMLBGAME": 50})
    assert checker.check(ticker="KXMLBGAME-2025-NYY-BOS", strategy_id="mlb_arb", current_position=10, order_quantity=5)
    assert not checker.check(ticker="KXMLBGAME-2025-NYY-BOS", strategy_id="mlb_arb", current_position=48, order_quantity=5)


def test_check_passes_with_no_limit_configured():
    checker = PositionLimitChecker(limits={})
    assert checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=999, order_quantity=999)


def test_violation_reason_is_accessible():
    checker = PositionLimitChecker(limits={"KXBTC15M": 100})
    checker.check(ticker="KXBTC15M-25APR30-T65499.99", strategy_id="stat_arb", current_position=95, order_quantity=10)
    assert checker.last_violation_reason is not None
    assert "limit" in checker.last_violation_reason.lower()
