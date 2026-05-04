from __future__ import annotations

import logging
import threading
import time
from typing import Any

from safety.state_store import StateStore

_logger = logging.getLogger(__name__)


class DeadMansSwitch:
    def __init__(
        self,
        *,
        http: Any,
        store: StateStore,
        timeout_secs: float = 300.0,
        poll_interval_secs: float = 10.0,
    ) -> None:
        self._http = http
        self._store = store
        self._timeout = timeout_secs
        self._poll_interval = poll_interval_secs
        self._strategies: dict[str, float] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register_strategy(self, strategy_id: str) -> None:
        with self._lock:
            self._strategies[strategy_id] = time.monotonic()
        _logger.info("DeadMansSwitch registered strategy: %s (timeout=%.0fs)", strategy_id, self._timeout)

    def heartbeat(self, strategy_id: str) -> None:
        with self._lock:
            if strategy_id in self._strategies:
                self._strategies[strategy_id] = time.monotonic()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="DeadMansSwitch")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._check()
            self._stop_event.wait(self._poll_interval)

    def _check(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [sid for sid, last in self._strategies.items() if now - last > self._timeout]
        for strategy_id in expired:
            _logger.error("DeadMansSwitch triggered for strategy=%s — cancelling open orders", strategy_id)
            strategy_orders = self._store.get_orders_by_strategy(strategy_id)
            for order in strategy_orders:
                if order.kalshi_order_id:
                    try:
                        self._http.cancel_order(order.kalshi_order_id)
                        _logger.info("dead mans switch cancelled order=%s", order.kalshi_order_id)
                    except Exception:
                        _logger.exception("failed to cancel order=%s", order.kalshi_order_id)
            with self._lock:
                self._strategies.pop(strategy_id, None)
