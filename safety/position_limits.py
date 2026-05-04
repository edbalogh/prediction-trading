from __future__ import annotations

import logging

_logger = logging.getLogger(__name__)


class PositionLimitChecker:
    def __init__(self, limits: dict[str, int]) -> None:
        self._limits = limits
        self.last_violation_reason: str | None = None

    def check(self, *, ticker: str, strategy_id: str, current_position: int, order_quantity: int) -> bool:
        self.last_violation_reason = None
        series = ticker.split("-")[0]
        limit = self._limits.get(series)
        if limit is None:
            return True
        projected = current_position + order_quantity
        if projected > limit:
            self.last_violation_reason = (
                f"order would exceed position limit: series={series} "
                f"current={current_position} order={order_quantity} limit={limit}"
            )
            _logger.warning(self.last_violation_reason)
            return False
        return True
