from __future__ import annotations

import copy
import time
import logging

from pydantic import ConfigDict
from nautilus_trader.config import LiveExecClientConfig
from nautilus_trader.live.execution_client import LiveExecutionClient
from nautilus_trader.live.factories import LiveExecClientFactory
from nautilus_trader.model.enums import (
    AccountType, LiquiditySide, OmsType, OrderSide, OrderType, PriceType,
)
from nautilus_trader.model.identifiers import (
    ClientId, TradeId, VenueOrderId,
)
from nautilus_trader.model.objects import Currency, Money, Price

from adapters.kalshi.constants import KALSHI_VENUE

_logger = logging.getLogger(__name__)

_paper_exec_client: PaperExecutionClient | None = None


class PaperExecClientConfig(LiveExecClientConfig):
    model_config = ConfigDict(frozen=True)

    starting_cash: float = 10_000.0


class PaperExecutionClient(LiveExecutionClient):
    def __init__(self, *, config: PaperExecClientConfig, **kwargs) -> None:
        super().__init__(
            client_id=ClientId("KALSHI"),
            venue=KALSHI_VENUE,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=Currency.from_str("USD"),
            config=config,
            **kwargs,
        )
        self._starting_cash = config.starting_cash
        self._cash: float = config.starting_cash
        self._positions: dict[str, dict] = {}
        self._fills: list[dict] = []
        self._fill_counter: int = 0

    async def _connect(self) -> None:
        self._cash = self._starting_cash
        _logger.info("PaperExecutionClient connected, cash=%.2f", self._cash)

    async def _disconnect(self) -> None:
        _logger.info("PaperExecutionClient disconnected")

    def generate_order_status_reports(self, instrument_id=None, start=None, end=None, open_only=False):
        return []

    def generate_fill_reports(self, instrument_id=None, venue_order_id=None, start=None, end=None):
        return []

    async def _submit_order(self, command) -> None:
        order = command.order
        instrument_id = order.instrument_id
        ticker = instrument_id.symbol.value
        ts_now = time.time_ns()

        fill_id = self._fill_counter
        self._fill_counter += 1
        venue_order_id = VenueOrderId(f"paper-{fill_id}")

        self.generate_order_accepted(
            strategy_id=command.strategy_id,
            instrument_id=instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=venue_order_id,
            ts_event=ts_now,
        )

        cached_price = self._cache.price(instrument_id, PriceType.LAST)
        fill_price_float = cached_price.as_double() if cached_price is not None else 0.50
        fill_price = Price(fill_price_float, 2)
        qty = int(order.quantity.as_double())

        self.generate_order_filled(
            strategy_id=command.strategy_id,
            instrument_id=instrument_id,
            client_order_id=order.client_order_id,
            venue_order_id=venue_order_id,
            venue_position_id=None,
            trade_id=TradeId(f"paper-trade-{fill_id}"),
            order_side=order.side,
            order_type=OrderType.MARKET,
            last_qty=order.quantity,
            last_px=fill_price,
            quote_currency=Currency.from_str("USD"),
            commission=Money(0, Currency.from_str("USD")),
            liquidity_side=LiquiditySide.TAKER,
            ts_event=ts_now,
        )

        if order.side == OrderSide.BUY:
            self._cash -= fill_price_float * qty
            if ticker in self._positions:
                existing = self._positions[ticker]
                total_qty = existing["qty"] + qty
                existing["avg_px"] = (
                    (existing["avg_px"] * existing["qty"] + fill_price_float * qty)
                    / total_qty
                )
                existing["qty"] = total_qty
            else:
                self._positions[ticker] = {"qty": qty, "avg_px": fill_price_float}
        else:
            if ticker not in self._positions:
                _logger.warning(
                    "SELL for %s with no open position — cash credited but no position to close",
                    ticker,
                )
            self._cash += fill_price_float * qty
            if ticker in self._positions:
                remaining = self._positions[ticker]["qty"] - qty
                if remaining <= 0:
                    del self._positions[ticker]
                else:
                    self._positions[ticker]["qty"] = remaining

        self._fills.append({
            "ticker": ticker,
            "side": "BUY" if order.side == OrderSide.BUY else "SELL",
            "qty": qty,
            "price": fill_price_float,
            "ts": ts_now // 1_000_000_000,
        })

    async def _cancel_order(self, command) -> None:
        pass

    def cash(self) -> float:
        return self._cash

    def positions(self) -> dict[str, dict]:
        return copy.deepcopy(self._positions)

    def fills(self) -> list[dict]:
        return list(self._fills)


class PaperExecClientFactory(LiveExecClientFactory):
    @staticmethod
    def create(loop, name, config, msgbus, cache, clock):
        global _paper_exec_client
        from nautilus_trader.common.providers import InstrumentProvider
        client = PaperExecutionClient(
            loop=loop,
            config=config,
            instrument_provider=InstrumentProvider(),
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
        _paper_exec_client = client
        return client
