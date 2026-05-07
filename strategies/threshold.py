from __future__ import annotations

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy


class ThresholdConfig(StrategyConfig, frozen=True):
    instrument_ids: list[str]
    venue: str = "KALSHI"
    buy_threshold: float = 0.25
    sell_threshold: float = 0.75
    trade_size: int = 5


class ThresholdStrategy(Strategy):
    def __init__(self, config: ThresholdConfig) -> None:
        super().__init__(config)
        self._venue = Venue(config.venue)
        self._buy_threshold = config.buy_threshold
        self._sell_threshold = config.sell_threshold
        self._trade_size = config.trade_size
        self._positions: dict[str, int] = {}

    def on_start(self) -> None:
        for iid_str in self.config.instrument_ids:
            iid = InstrumentId.from_str(iid_str)
            self.subscribe_trade_ticks(iid)
            self._positions[iid.symbol.value] = 0

    def on_trade_tick(self, tick: TradeTick) -> None:
        ticker = tick.instrument_id.symbol.value
        price = tick.price.as_double()
        pos = self._positions.get(ticker, 0)

        if price <= self._buy_threshold and pos <= 0:
            self._submit(tick.instrument_id, OrderSide.BUY, self._trade_size)
            self._positions[ticker] = self._trade_size
        elif price >= self._sell_threshold and pos > 0:
            self._submit(tick.instrument_id, OrderSide.SELL, pos)
            self._positions[ticker] = 0

    def _submit(self, instrument_id: InstrumentId, side: OrderSide, size: int) -> None:
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=side,
            quantity=Quantity(size, 0),
        )
        self.submit_order(order)
