from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest
from nautilus_trader.model.data import OrderBookDelta, TradeTick
from nautilus_trader.model.enums import AggressorSide, BookAction
from nautilus_trader.model.identifiers import InstrumentId, Symbol

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.data import KalshiDataClient


class FakeWsConnection:
    def __init__(self) -> None:
        self.subscribe_calls: list[tuple] = []
        self.unsubscribe_calls: list[tuple] = []
        self.on_snapshot = None
        self.on_delta = None
        self.on_trade = None
        self._connected = False

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def subscribe(self, tickers: list[str], channels: list[str]) -> None:
        self.subscribe_calls.append((tickers, channels))

    async def unsubscribe(self, tickers: list[str], channels: list[str]) -> None:
        self.unsubscribe_calls.append((tickers, channels))


def make_client(fake_ws: FakeWsConnection, fake_http: MagicMock) -> tuple[KalshiDataClient, list]:
    client = KalshiDataClient.__new__(KalshiDataClient)
    client._ws = fake_ws
    client._http = fake_http
    client._subscribed_instruments: set[InstrumentId] = set()
    handled: list = []
    client._handle_data = lambda d: handled.append(d)
    scheduled: list[asyncio.Task] = []
    client.create_task = lambda coro, **kw: scheduled.append(asyncio.ensure_future(coro)) or scheduled[-1]
    client._scheduled = scheduled
    return client, handled


def make_instrument_id(ticker: str = "KXBTC15M-X") -> InstrumentId:
    return InstrumentId(Symbol(ticker), KALSHI_VENUE)


async def test_subscribe_order_book_deltas_fetches_snapshot():
    fake_ws = FakeWsConnection()
    fake_http = MagicMock()
    fake_http.get_orderbook.return_value = {
        "orderbook": {"yes": [[55, 100]], "no": []}
    }
    client, handled = make_client(fake_ws, fake_http)

    instrument_id = make_instrument_id()
    client.subscribe_order_book_deltas(instrument_id=instrument_id, book_type=None, depth=0)

    await asyncio.gather(*client._scheduled)

    assert fake_http.get_orderbook.called
    assert any(isinstance(d, OrderBookDelta) for d in handled)
    assert fake_ws.subscribe_calls == [(["KXBTC15M-X"], ["orderbook_delta"])]


async def test_subscribe_trade_ticks_subscribes_trade_channel():
    fake_ws = FakeWsConnection()
    fake_http = MagicMock()
    client, _ = make_client(fake_ws, fake_http)

    instrument_id = make_instrument_id()
    client.subscribe_trade_ticks(instrument_id=instrument_id)

    await asyncio.gather(*client._scheduled)

    assert fake_ws.subscribe_calls == [(["KXBTC15M-X"], ["trade"])]


async def test_on_ws_snapshot_emits_order_book_deltas():
    fake_ws = FakeWsConnection()
    client, handled = make_client(fake_ws, MagicMock())

    instrument_id = make_instrument_id()
    client._subscribed_instruments.add(instrument_id)

    snapshot_msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 100], [54, 200]], "no": [[45, 50]]}
    client._on_ws_snapshot(snapshot_msg)

    assert len(handled) == 3
    assert all(isinstance(d, OrderBookDelta) for d in handled)


async def test_on_ws_delta_emits_update():
    fake_ws = FakeWsConnection()
    client, handled = make_client(fake_ws, MagicMock())

    instrument_id = make_instrument_id()
    client._subscribed_instruments.add(instrument_id)

    delta_msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 150]], "no": []}
    client._on_ws_delta(delta_msg)

    assert len(handled) == 1
    assert handled[0].action == BookAction.UPDATE


async def test_on_ws_delta_emits_delete():
    fake_ws = FakeWsConnection()
    client, handled = make_client(fake_ws, MagicMock())

    instrument_id = make_instrument_id()
    client._subscribed_instruments.add(instrument_id)

    delta_msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 0]], "no": []}
    client._on_ws_delta(delta_msg)

    assert len(handled) == 1
    assert handled[0].action == BookAction.DELETE


async def test_on_ws_trade_emits_trade_tick():
    fake_ws = FakeWsConnection()
    client, handled = make_client(fake_ws, MagicMock())

    instrument_id = make_instrument_id()
    client._subscribed_instruments.add(instrument_id)

    trade_msg = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 10,
        "taker_side": "yes",
        "ts": 1746400000000,
    }
    client._on_ws_trade(trade_msg)

    assert len(handled) == 1
    tick = handled[0]
    assert isinstance(tick, TradeTick)
    assert tick.price.as_double() == pytest.approx(0.55)
    assert tick.size.as_double() == 10.0
    assert tick.aggressor_side == AggressorSide.BUYER
