import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.enums import AggressorSide

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.factories import (
    market_to_binary_option,
    kalshi_ticker_to_instrument_id,
    orderbook_snapshot_to_deltas,
    fill_to_trade_tick,
)


SAMPLE_MARKET = {
    "ticker": "KXBTC15M-25APR30-T65499.99",
    "series_ticker": "KXBTC15M",
    "status": "open",
    "yes_bid": 55,
    "yes_ask": 57,
    "close_time": "2025-04-30T15:00:00Z",
    "result": "",
    "title": "Will BTC be above $65,499.99 at 3pm?",
}

SAMPLE_ORDERBOOK = {
    "ticker": "KXBTC15M-25APR30-T65499.99",
    "orderbook": {
        "yes": [[55, 100], [54, 200]],
        "no": [[44, 150], [43, 75]],
    },
}

SAMPLE_FILL = {
    "trade_id": "fill-001",
    "ticker": "KXBTC15M-25APR30-T65499.99",
    "side": "yes",
    "yes_price": 55,
    "count": 10,
    "created_time": "2025-04-30T14:00:00Z",
    "is_taker": True,
}


def test_market_to_binary_option_returns_binary_option():
    instrument = market_to_binary_option(SAMPLE_MARKET)
    assert isinstance(instrument, BinaryOption)
    assert instrument.id.symbol.value == "KXBTC15M-25APR30-T65499.99"
    assert instrument.id.venue == KALSHI_VENUE


def test_kalshi_ticker_to_instrument_id():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-25APR30-T65499.99")
    assert instrument_id == InstrumentId(Symbol("KXBTC15M-25APR30-T65499.99"), KALSHI_VENUE)


def test_orderbook_snapshot_to_deltas_returns_list():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-25APR30-T65499.99")
    deltas = orderbook_snapshot_to_deltas(SAMPLE_ORDERBOOK, instrument_id=instrument_id, ts_event=1000, ts_init=1000)
    assert len(deltas) > 0


def test_fill_to_trade_tick_returns_trade_tick():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-25APR30-T65499.99")
    tick = fill_to_trade_tick(SAMPLE_FILL, instrument_id=instrument_id, ts_init=1000)
    assert tick.price.as_double() == pytest.approx(0.55)
    assert tick.size.as_double() == 10.0
    assert tick.aggressor_side == AggressorSide.BUYER
