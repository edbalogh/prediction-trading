from __future__ import annotations

import redis

from safety.types import OrderRecord

_ORDER_KEY = "nautilus_plus:order:{client_order_id}"
_OPEN_ORDERS_KEY = "nautilus_plus:open_orders"
_STRATEGY_ORDERS_KEY = "nautilus_plus:strategy_orders:{strategy_id}"
_KALSHI_ID_INDEX = "nautilus_plus:kalshi_id:{kalshi_order_id}"


class StateStore:
    def __init__(self, redis_client: redis.Redis | None = None, redis_url: str = "redis://localhost:6379") -> None:
        self._r = redis_client or redis.Redis.from_url(redis_url, decode_responses=True)

    def save_order(self, record: OrderRecord) -> None:
        key = _ORDER_KEY.format(client_order_id=record.client_order_id)
        self._r.hset(key, mapping=self._record_to_dict(record))
        if record.kalshi_order_id:
            self._r.set(_KALSHI_ID_INDEX.format(kalshi_order_id=record.kalshi_order_id), record.client_order_id)
        if record.is_open:
            self._r.sadd(_OPEN_ORDERS_KEY, record.client_order_id)
            self._r.sadd(_STRATEGY_ORDERS_KEY.format(strategy_id=record.strategy_id), record.client_order_id)
        else:
            self._r.srem(_OPEN_ORDERS_KEY, record.client_order_id)

    def get_order(self, client_order_id: str) -> OrderRecord | None:
        key = _ORDER_KEY.format(client_order_id=client_order_id)
        data = self._r.hgetall(key)
        if not data:
            return None
        return self._dict_to_record(data)

    def get_open_orders(self) -> list[OrderRecord]:
        ids = self._r.smembers(_OPEN_ORDERS_KEY)
        records = []
        for cid in ids:
            record = self.get_order(cid)
            if record and record.is_open:
                records.append(record)
        return records

    def get_order_by_kalshi_id(self, kalshi_order_id: str) -> OrderRecord | None:
        client_order_id = self._r.get(_KALSHI_ID_INDEX.format(kalshi_order_id=kalshi_order_id))
        if not client_order_id:
            return None
        return self.get_order(client_order_id)

    def get_orders_by_strategy(self, strategy_id: str) -> list[OrderRecord]:
        ids = self._r.smembers(_STRATEGY_ORDERS_KEY.format(strategy_id=strategy_id))
        records = []
        for cid in ids:
            record = self.get_order(cid)
            if record and record.is_open:
                records.append(record)
        return records

    def mark_order_filled(self, client_order_id: str, filled: int) -> None:
        record = self.get_order(client_order_id)
        key = _ORDER_KEY.format(client_order_id=client_order_id)
        self._r.hset(key, mapping={"status": "filled", "filled": str(filled)})
        self._r.srem(_OPEN_ORDERS_KEY, client_order_id)
        if record:
            self._r.srem(_STRATEGY_ORDERS_KEY.format(strategy_id=record.strategy_id), client_order_id)

    def mark_order_canceled(self, client_order_id: str) -> None:
        record = self.get_order(client_order_id)
        key = _ORDER_KEY.format(client_order_id=client_order_id)
        self._r.hset(key, mapping={"status": "canceled"})
        self._r.srem(_OPEN_ORDERS_KEY, client_order_id)
        if record:
            self._r.srem(_STRATEGY_ORDERS_KEY.format(strategy_id=record.strategy_id), client_order_id)

    @staticmethod
    def _record_to_dict(record: OrderRecord) -> dict[str, str]:
        return {
            "client_order_id": record.client_order_id,
            "kalshi_order_id": record.kalshi_order_id or "",
            "ticker": record.ticker,
            "strategy_id": record.strategy_id,
            "side": record.side,
            "price_cents": str(record.price_cents),
            "quantity": str(record.quantity),
            "filled": str(record.filled),
            "status": record.status,
        }

    @staticmethod
    def _dict_to_record(data: dict[str, str]) -> OrderRecord:
        return OrderRecord(
            client_order_id=data["client_order_id"],
            kalshi_order_id=data.get("kalshi_order_id") or None,
            ticker=data["ticker"],
            strategy_id=data["strategy_id"],
            side=data["side"],
            price_cents=int(data["price_cents"]),
            quantity=int(data["quantity"]),
            filled=int(data["filled"]),
            status=data["status"],
        )
