from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class OrderRecord:
    client_order_id: str
    kalshi_order_id: str | None
    ticker: str
    strategy_id: str
    side: str          # "yes" or "no"
    price_cents: int
    quantity: int
    filled: int
    status: str        # "open", "filled", "canceled"

    @property
    def is_open(self) -> bool:
        return self.status == "open" and self.filled < self.quantity

    @property
    def is_filled(self) -> bool:
        return self.filled >= self.quantity


@dataclass
class ReconciliationResult:
    resolved_fills: list[str]              # client_order_ids
    resolved_cancels: list[str]           # client_order_ids
    orphan_orders: list[str]              # kalshi_order_ids with no local record
    orphan_fills: list[dict[str, Any]]
    orphan_positions: list[dict[str, Any]]
    unresolvable: list[dict[str, Any]]

    @property
    def is_clean(self) -> bool:
        return not self.unresolvable and not self.orphan_orders and not self.orphan_positions

    @property
    def has_unresolvable(self) -> bool:
        return bool(self.unresolvable)


@dataclass
class OrphanEvent:
    event_type: str        # "ORDER", "FILL", "POSITION"
    ticker: str
    strategy_id: str | None
    detail: dict[str, Any]
    ts: int = field(default_factory=time.time_ns)


@dataclass
class AlertEvent:
    level: str             # "INFO", "WARNING", "CRITICAL"
    message: str
    context: dict[str, Any] = field(default_factory=dict)
    ts: int = field(default_factory=time.time_ns)
