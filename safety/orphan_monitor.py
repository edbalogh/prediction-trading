from __future__ import annotations

import logging
import threading
from typing import Any

from safety.alerts import AlertDispatcher
from safety.quarantine import QuarantineBook
from safety.state_store import StateStore
from safety.types import AlertEvent, OrphanEvent

_logger = logging.getLogger(__name__)


class OrphanMonitor:
    def __init__(
        self,
        *,
        store: StateStore,
        http: Any,
        quarantine: QuarantineBook,
        alerts: AlertDispatcher,
        interval_secs: float = 60.0,
    ) -> None:
        self._store = store
        self._http = http
        self._quarantine = quarantine
        self._alerts = alerts
        self._interval = interval_secs
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def tick(self) -> dict[str, int]:
        orphan_orders = 0
        orphan_fills = 0
        cached_open_ids = {o.kalshi_order_id for o in self._store.get_open_orders() if o.kalshi_order_id}

        live_orders = self._http.list_recent_orders(status="resting")
        for live in live_orders:
            oid = live.get("order_id")
            cid = live.get("client_order_id")
            if oid and oid not in cached_open_ids:
                ticker = live.get("ticker", "")
                _logger.warning("orphan order detected: kalshi_order_id=%s", oid)
                orphan_orders += 1
                self._quarantine.append(OrphanEvent(
                    event_type="ORDER",
                    ticker=ticker,
                    strategy_id=None,
                    detail={"kalshi_order_id": oid, "client_order_id": cid},
                ))
                self._alerts.dispatch(AlertEvent(
                    level="CRITICAL",
                    message=f"Orphan order detected (continuous monitor): {oid}",
                    context={"ticker": ticker},
                ))

        live_fills = self._http.list_recent_fills()
        for fill in live_fills:
            oid = fill.get("order_id")
            if oid and oid not in cached_open_ids and self._store.get_order_by_kalshi_id(oid) is None:
                ticker = fill.get("ticker", "")
                _logger.warning("orphan fill: trade_id=%s order_id=%s", fill.get("trade_id"), oid)
                orphan_fills += 1
                self._quarantine.append(OrphanEvent(
                    event_type="FILL",
                    ticker=ticker,
                    strategy_id=None,
                    detail=fill,
                ))
                self._alerts.dispatch(AlertEvent(
                    level="CRITICAL",
                    message=f"Orphan fill detected: trade_id={fill.get('trade_id')}",
                    context={"ticker": ticker, "order_id": oid},
                ))

        return {"orphan_orders": orphan_orders, "orphan_fills": orphan_fills}

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="OrphanMonitor")
        self._thread.start()
        _logger.info("OrphanMonitor started (interval=%.1fs)", self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        _logger.info("OrphanMonitor stopped")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.tick()
            except Exception:
                _logger.exception("OrphanMonitor tick error")
            self._stop_event.wait(self._interval)
