from __future__ import annotations

import logging
import time

from nautilus_trader.live.data_client import LiveDataClient
from nautilus_trader.model.identifiers import ClientId, InstrumentId

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.factories import (
    kalshi_ticker_to_instrument_id,
    orderbook_snapshot_to_deltas,
    ws_delta_to_order_book_deltas,
    ws_trade_to_trade_tick,
)
from adapters.kalshi.ws import KalshiWsConnection

_logger = logging.getLogger(__name__)


class KalshiDataClient(LiveDataClient):
    def __init__(
        self,
        *,
        http_client,
        config,
        **kwargs,
    ) -> None:
        super().__init__(
            client_id=ClientId("KALSHI"),
            venue=KALSHI_VENUE,
            **kwargs,
        )
        self._http = http_client
        self._ws = KalshiWsConnection(
            http_client=http_client,
            reconnect_delay=config.ws_reconnect_delay_secs,
            reconnect_max_delay=config.ws_reconnect_max_delay_secs,
        )
        self._subscribed_instruments: set[InstrumentId] = set()

    async def _connect(self) -> None:
        self._ws.on_snapshot = self._on_ws_snapshot
        self._ws.on_delta = self._on_ws_delta
        self._ws.on_trade = self._on_ws_trade
        await self._ws.connect()

    async def _disconnect(self) -> None:
        await self._ws.disconnect()

    def subscribe_order_book_deltas(self, instrument_id, book_type=None, depth=0, **kwargs) -> None:
        self._subscribed_instruments.add(instrument_id)
        ticker = instrument_id.symbol.value
        self.create_task(self._subscribe_orderbook_async(ticker, instrument_id))

    def unsubscribe_order_book_deltas(self, instrument_id, **kwargs) -> None:
        self._subscribed_instruments.discard(instrument_id)
        ticker = instrument_id.symbol.value
        self.create_task(self._ws.unsubscribe([ticker], ["orderbook_delta"]))

    def subscribe_trade_ticks(self, instrument_id, **kwargs) -> None:
        self._subscribed_instruments.add(instrument_id)
        ticker = instrument_id.symbol.value
        self.create_task(self._ws.subscribe([ticker], ["trade"]))

    def unsubscribe_trade_ticks(self, instrument_id, **kwargs) -> None:
        self._subscribed_instruments.discard(instrument_id)
        ticker = instrument_id.symbol.value
        self.create_task(self._ws.unsubscribe([ticker], ["trade"]))

    async def _subscribe_orderbook_async(self, ticker: str, instrument_id: InstrumentId) -> None:
        ts_now = time.time_ns()
        snapshot = self._http.get_orderbook(ticker)
        deltas = orderbook_snapshot_to_deltas(snapshot, instrument_id=instrument_id, ts_event=ts_now, ts_init=ts_now)
        for delta in deltas:
            self._handle_data(delta)
        await self._ws.subscribe([ticker], ["orderbook_delta"])

    def _on_ws_snapshot(self, msg: dict) -> None:
        instrument_id = kalshi_ticker_to_instrument_id(msg.get("market_ticker", ""))
        if instrument_id not in self._subscribed_instruments:
            _logger.warning("snapshot for unsubscribed ticker %s", msg.get("market_ticker"))
            return
        ts_now = time.time_ns()
        deltas = orderbook_snapshot_to_deltas(
            {"orderbook": msg},
            instrument_id=instrument_id,
            ts_event=ts_now,
            ts_init=ts_now,
        )
        for delta in deltas:
            self._handle_data(delta)

    def _on_ws_delta(self, msg: dict) -> None:
        instrument_id = kalshi_ticker_to_instrument_id(msg.get("market_ticker", ""))
        if instrument_id not in self._subscribed_instruments:
            _logger.warning("delta for unsubscribed ticker %s", msg.get("market_ticker"))
            return
        ts_now = time.time_ns()
        deltas = ws_delta_to_order_book_deltas(msg, instrument_id=instrument_id, ts_event=ts_now, ts_init=ts_now)
        for delta in deltas:
            self._handle_data(delta)

    def _on_ws_trade(self, msg: dict) -> None:
        instrument_id = kalshi_ticker_to_instrument_id(msg.get("market_ticker", ""))
        if instrument_id not in self._subscribed_instruments:
            _logger.warning("trade for unsubscribed ticker %s", msg.get("market_ticker"))
            return
        tick = ws_trade_to_trade_tick(msg, instrument_id=instrument_id, ts_init=time.time_ns())
        self._handle_data(tick)
