from __future__ import annotations

from datetime import datetime, timezone

from nautilus_trader.model.data import BookOrder, OrderBookDelta, TradeTick
from nautilus_trader.model.enums import AggressorSide, AssetClass, BookAction, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TradeId
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.objects import Currency, Price, Quantity

from adapters.kalshi.constants import (
    KALSHI_VENUE,
    PRICE_PRECISION,
    SIZE_PRECISION,
    PRICE_INCREMENT,
    SIZE_INCREMENT,
)


def kalshi_ticker_to_instrument_id(ticker: str) -> InstrumentId:
    return InstrumentId(Symbol(ticker), KALSHI_VENUE)


def market_to_binary_option(market: dict) -> BinaryOption:
    ticker = market["ticker"]
    instrument_id = kalshi_ticker_to_instrument_id(ticker)

    close_time = market.get("close_time", "")
    if close_time:
        expiration_ns = int(datetime.fromisoformat(close_time.replace("Z", "+00:00")).timestamp() * 1e9)
    else:
        expiration_ns = 0

    return BinaryOption(
        instrument_id=instrument_id,
        raw_symbol=Symbol(ticker),
        asset_class=AssetClass.ALTERNATIVE,
        currency=Currency.from_str("USD"),
        price_precision=PRICE_PRECISION,
        price_increment=Price(PRICE_INCREMENT, PRICE_PRECISION),
        size_precision=SIZE_PRECISION,
        size_increment=Quantity(SIZE_INCREMENT, SIZE_PRECISION),
        activation_ns=0,
        expiration_ns=expiration_ns,
        max_quantity=None,
        min_quantity=Quantity(1, SIZE_PRECISION),
        ts_event=0,
        ts_init=0,
        outcome=market.get("title", ticker),
        description=market.get("title", ""),
    )


def orderbook_snapshot_to_deltas(
    snapshot: dict,
    *,
    instrument_id: InstrumentId,
    ts_event: int,
    ts_init: int,
) -> list[OrderBookDelta]:
    deltas: list[OrderBookDelta] = []
    orderbook = snapshot.get("orderbook", {})

    for price_cents, size in orderbook.get("yes", []):
        order = BookOrder(
            side=OrderSide.BUY,
            price=Price(round(price_cents / 100, PRICE_PRECISION), PRICE_PRECISION),
            size=Quantity(size, SIZE_PRECISION),
            order_id=0,
        )
        deltas.append(OrderBookDelta(
            instrument_id=instrument_id,
            action=BookAction.ADD,
            order=order,
            flags=0,
            sequence=0,
            ts_event=ts_event,
            ts_init=ts_init,
        ))

    for price_cents, size in orderbook.get("no", []):
        yes_price_cents = 100 - price_cents
        order = BookOrder(
            side=OrderSide.SELL,
            price=Price(round(yes_price_cents / 100, PRICE_PRECISION), PRICE_PRECISION),
            size=Quantity(size, SIZE_PRECISION),
            order_id=0,
        )
        deltas.append(OrderBookDelta(
            instrument_id=instrument_id,
            action=BookAction.ADD,
            order=order,
            flags=0,
            sequence=0,
            ts_event=ts_event,
            ts_init=ts_init,
        ))

    return deltas


def fill_to_trade_tick(
    fill: dict,
    *,
    instrument_id: InstrumentId,
    ts_init: int,
) -> TradeTick:
    yes_price_val = fill.get("yes_price")
    no_price_val = fill.get("no_price")
    if yes_price_val is not None:
        price_cents = yes_price_val
    elif no_price_val is not None:
        price_cents = 100 - no_price_val
    else:
        raise ValueError(f"fill {fill.get('trade_id')} has neither yes_price nor no_price")
    price = round(price_cents / 100, PRICE_PRECISION)
    size = fill["count"]
    is_taker = fill.get("is_taker", True)
    side = fill.get("side", "yes")

    if side == "yes":
        aggressor = AggressorSide.BUYER if is_taker else AggressorSide.SELLER
    else:
        aggressor = AggressorSide.SELLER if is_taker else AggressorSide.BUYER

    created = fill.get("created_time", "")
    if created:
        ts_event = int(datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp() * 1e9)
    else:
        ts_event = ts_init

    return TradeTick(
        instrument_id=instrument_id,
        price=Price(price, PRICE_PRECISION),
        size=Quantity(size, SIZE_PRECISION),
        aggressor_side=aggressor,
        trade_id=TradeId(fill.get("trade_id", "unknown")),
        ts_event=ts_event,
        ts_init=ts_init,
    )


def ws_delta_to_order_book_deltas(
    msg: dict,
    *,
    instrument_id: InstrumentId,
    ts_event: int,
    ts_init: int,
) -> list[OrderBookDelta]:
    deltas: list[OrderBookDelta] = []
    for price_cents, size in msg.get("yes", []):
        action = BookAction.UPDATE if size > 0 else BookAction.DELETE
        order = BookOrder(
            side=OrderSide.BUY,
            price=Price(round(price_cents / 100, PRICE_PRECISION), PRICE_PRECISION),
            size=Quantity(size, SIZE_PRECISION),
            order_id=0,
        )
        deltas.append(OrderBookDelta(
            instrument_id=instrument_id,
            action=action,
            order=order,
            flags=0,
            sequence=0,
            ts_event=ts_event,
            ts_init=ts_init,
        ))
    for price_cents, size in msg.get("no", []):
        yes_price_cents = 100 - price_cents
        action = BookAction.UPDATE if size > 0 else BookAction.DELETE
        order = BookOrder(
            side=OrderSide.SELL,
            price=Price(round(yes_price_cents / 100, PRICE_PRECISION), PRICE_PRECISION),
            size=Quantity(size, SIZE_PRECISION),
            order_id=0,
        )
        deltas.append(OrderBookDelta(
            instrument_id=instrument_id,
            action=action,
            order=order,
            flags=0,
            sequence=0,
            ts_event=ts_event,
            ts_init=ts_init,
        ))
    return deltas


def ws_trade_to_trade_tick(
    msg: dict,
    *,
    instrument_id: InstrumentId,
    ts_init: int,
) -> TradeTick:
    yes_price = msg.get("yes_price")
    no_price = msg.get("no_price")
    if yes_price is not None:
        price_cents = yes_price
    elif no_price is not None:
        price_cents = 100 - no_price
    else:
        raise ValueError(f"ws trade msg has neither yes_price nor no_price: {msg}")
    aggressor = AggressorSide.BUYER if msg.get("taker_side", "yes") == "yes" else AggressorSide.SELLER
    trade_id = msg.get("trade_id") or f"{msg['market_ticker']}-{msg['ts']}"
    return TradeTick(
        instrument_id=instrument_id,
        price=Price(round(price_cents / 100, PRICE_PRECISION), PRICE_PRECISION),
        size=Quantity(msg["count"], SIZE_PRECISION),
        aggressor_side=aggressor,
        trade_id=TradeId(trade_id),
        ts_event=msg["ts"] * 1_000_000,
        ts_init=ts_init,
    )
