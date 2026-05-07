from __future__ import annotations
from unittest.mock import MagicMock, patch
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Price, Quantity

from strategies.threshold import ThresholdConfig, ThresholdStrategy


def make_tick(ticker: str, price: float) -> TradeTick:
    from nautilus_trader.model.enums import AggressorSide
    from nautilus_trader.model.identifiers import TradeId
    iid = InstrumentId(Symbol(ticker), Venue("KALSHI"))
    return TradeTick(
        instrument_id=iid,
        price=Price(price, 2),
        size=Quantity(1, 0),
        aggressor_side=AggressorSide.BUYER,
        trade_id=TradeId("t1"),
        ts_event=0,
        ts_init=0,
    )


def _make_order_factory(side: OrderSide) -> MagicMock:
    """Return a mock order_factory whose .market() returns an order with the given side."""
    mock_order = MagicMock()
    mock_order.side = side
    factory = MagicMock()
    factory.market.return_value = mock_order
    return factory


def test_config_defaults():
    cfg = ThresholdConfig(instrument_ids=["A.KALSHI"], strategy_id="test-001")
    assert cfg.buy_threshold == 0.25
    assert cfg.sell_threshold == 0.75
    assert cfg.trade_size == 5
    assert cfg.venue == "KALSHI"


def test_buy_signal_below_threshold():
    cfg = ThresholdConfig(instrument_ids=["A.KALSHI"], strategy_id="strat-1")
    strat = ThresholdStrategy(cfg)
    strat._positions = {"A": 0}
    strat._buy_threshold = 0.25
    strat._sell_threshold = 0.75
    strat._trade_size = 5

    submitted = []
    strat.submit_order = lambda order: submitted.append(order)

    tick = make_tick("A", 0.20)
    mock_factory = _make_order_factory(OrderSide.BUY)
    with patch.object(ThresholdStrategy, "order_factory",
                      new_callable=lambda: property(lambda self: mock_factory)):
        strat.on_trade_tick(tick)

    assert len(submitted) == 1
    assert submitted[0].side == OrderSide.BUY
    assert strat._positions["A"] == 5


def test_no_buy_when_already_long():
    cfg = ThresholdConfig(instrument_ids=["A.KALSHI"], strategy_id="strat-2")
    strat = ThresholdStrategy(cfg)
    strat._positions = {"A": 5}
    strat._buy_threshold = 0.25
    strat._sell_threshold = 0.75
    strat._trade_size = 5

    submitted = []
    strat.submit_order = lambda order: submitted.append(order)

    tick = make_tick("A", 0.20)
    strat.on_trade_tick(tick)

    assert len(submitted) == 0


def test_sell_signal_above_threshold():
    cfg = ThresholdConfig(instrument_ids=["A.KALSHI"], strategy_id="strat-3")
    strat = ThresholdStrategy(cfg)
    strat._positions = {"A": 5}
    strat._buy_threshold = 0.25
    strat._sell_threshold = 0.75
    strat._trade_size = 5

    submitted = []
    strat.submit_order = lambda order: submitted.append(order)

    tick = make_tick("A", 0.80)
    mock_factory = _make_order_factory(OrderSide.SELL)
    with patch.object(ThresholdStrategy, "order_factory",
                      new_callable=lambda: property(lambda self: mock_factory)):
        strat.on_trade_tick(tick)

    assert len(submitted) == 1
    assert submitted[0].side == OrderSide.SELL
    assert strat._positions["A"] == 0


def test_no_sell_when_flat():
    cfg = ThresholdConfig(instrument_ids=["A.KALSHI"], strategy_id="strat-4")
    strat = ThresholdStrategy(cfg)
    strat._positions = {"A": 0}
    strat._buy_threshold = 0.25
    strat._sell_threshold = 0.75

    submitted = []
    strat.submit_order = lambda order: submitted.append(order)

    tick = make_tick("A", 0.80)
    strat.on_trade_tick(tick)

    assert len(submitted) == 0
