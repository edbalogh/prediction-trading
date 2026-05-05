import pytest
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.enums import AggressorSide, BookAction, OrderSide

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.factories import (
    market_to_binary_option,
    kalshi_ticker_to_instrument_id,
    orderbook_snapshot_to_deltas,
    fill_to_trade_tick,
    ws_delta_to_order_book_deltas,
    ws_trade_to_trade_tick,
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


def test_orderbook_snapshot_to_deltas_starts_with_clear():
    from nautilus_trader.model.enums import BookAction
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-25APR30-T65499.99")
    deltas = orderbook_snapshot_to_deltas(SAMPLE_ORDERBOOK, instrument_id=instrument_id, ts_event=1000, ts_init=1000)
    assert deltas[0].action == BookAction.CLEAR


def test_fill_to_trade_tick_returns_trade_tick():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-25APR30-T65499.99")
    tick = fill_to_trade_tick(SAMPLE_FILL, instrument_id=instrument_id, ts_init=1000)
    assert tick.price.as_double() == pytest.approx(0.55)
    assert tick.size.as_double() == 10.0
    assert tick.aggressor_side == AggressorSide.BUYER


# ── WebSocket factory tests ───────────────────────────────────────────────────


def test_ws_delta_to_order_book_deltas_update():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 150]], "no": []}
    deltas = ws_delta_to_order_book_deltas(msg, instrument_id=instrument_id, ts_event=1000, ts_init=2000)
    assert len(deltas) == 1
    assert deltas[0].action == BookAction.UPDATE
    assert deltas[0].order.price.as_double() == pytest.approx(0.55)
    assert deltas[0].order.size.as_double() == 150.0
    assert deltas[0].order.side == OrderSide.BUY


def test_ws_delta_to_order_book_deltas_delete():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {"market_ticker": "KXBTC15M-X", "yes": [[55, 0]], "no": []}
    deltas = ws_delta_to_order_book_deltas(msg, instrument_id=instrument_id, ts_event=1000, ts_init=2000)
    assert len(deltas) == 1
    assert deltas[0].action == BookAction.DELETE


def test_ws_delta_no_side_price_conversion():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    # no_price=45 → yes_equivalent=55 → 0.55
    msg = {"market_ticker": "KXBTC15M-X", "yes": [], "no": [[45, 100]]}
    deltas = ws_delta_to_order_book_deltas(msg, instrument_id=instrument_id, ts_event=0, ts_init=0)
    assert len(deltas) == 1
    assert deltas[0].order.price.as_double() == pytest.approx(0.55)
    assert deltas[0].order.side == OrderSide.SELL


def test_ws_trade_yes_taker_is_buyer():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 10,
        "taker_side": "yes",
        "ts": 1746400000000,
    }
    tick = ws_trade_to_trade_tick(msg, instrument_id=instrument_id, ts_init=9999)
    assert tick.aggressor_side == AggressorSide.BUYER
    assert tick.price.as_double() == pytest.approx(0.55)
    assert tick.size.as_double() == 10.0


def test_ws_trade_no_taker_is_seller():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 5,
        "taker_side": "no",
        "ts": 1746400000000,
    }
    tick = ws_trade_to_trade_tick(msg, instrument_id=instrument_id, ts_init=9999)
    assert tick.aggressor_side == AggressorSide.SELLER


def test_ws_trade_ts_milliseconds_to_nanoseconds():
    instrument_id = kalshi_ticker_to_instrument_id("KXBTC15M-X")
    msg = {
        "market_ticker": "KXBTC15M-X",
        "yes_price": 55,
        "no_price": 45,
        "count": 1,
        "taker_side": "yes",
        "ts": 1746400000000,
    }
    tick = ws_trade_to_trade_tick(msg, instrument_id=instrument_id, ts_init=0)
    assert tick.ts_event == 1746400000000 * 1_000_000
