import pytest
import fakeredis
from safety.state_store import StateStore
from safety.types import OrderRecord


@pytest.fixture()
def store():
    fake = fakeredis.FakeRedis(decode_responses=True)
    return StateStore(redis_client=fake)


def test_save_and_get_order(store):
    record = OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    )
    store.save_order(record)
    retrieved = store.get_order("clord-001")
    assert retrieved is not None
    assert retrieved.client_order_id == "clord-001"
    assert retrieved.kalshi_order_id == "kalshi-abc"
    assert retrieved.ticker == "KXBTC15M-X"


def test_get_open_orders(store):
    for i in range(3):
        store.save_order(OrderRecord(
            client_order_id=f"clord-{i}",
            kalshi_order_id=f"kalshi-{i}",
            ticker="KXBTC15M-X",
            strategy_id="stat_arb",
            side="yes",
            price_cents=55,
            quantity=10,
            filled=0,
            status="open",
        ))
    store.save_order(OrderRecord(
        client_order_id="clord-filled",
        kalshi_order_id="kalshi-filled",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=10,
        status="filled",
    ))
    open_orders = store.get_open_orders()
    assert len(open_orders) == 3
    assert all(o.status == "open" for o in open_orders)


def test_mark_order_filled(store):
    store.save_order(OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    ))
    store.mark_order_filled("clord-001", filled=10)
    record = store.get_order("clord-001")
    assert record.status == "filled"
    assert record.filled == 10


def test_mark_order_canceled(store):
    store.save_order(OrderRecord(
        client_order_id="clord-001",
        kalshi_order_id="kalshi-abc",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    ))
    store.mark_order_canceled("clord-001")
    record = store.get_order("clord-001")
    assert record.status == "canceled"


def test_get_orders_by_strategy(store):
    store.save_order(OrderRecord(
        client_order_id="clord-a",
        kalshi_order_id="kalshi-a",
        ticker="KXBTC15M-X",
        strategy_id="stat_arb",
        side="yes",
        price_cents=55,
        quantity=10,
        filled=0,
        status="open",
    ))
    store.save_order(OrderRecord(
        client_order_id="clord-b",
        kalshi_order_id="kalshi-b",
        ticker="KXMLBGAME-X",
        strategy_id="mlb_arb",
        side="yes",
        price_cents=40,
        quantity=5,
        filled=0,
        status="open",
    ))
    arb_orders = store.get_orders_by_strategy("stat_arb")
    assert len(arb_orders) == 1
    assert arb_orders[0].client_order_id == "clord-a"
