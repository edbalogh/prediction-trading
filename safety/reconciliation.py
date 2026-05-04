from __future__ import annotations

import logging
from typing import Any

from safety.alerts import AlertDispatcher
from safety.quarantine import QuarantineBook
from safety.state_store import StateStore
from safety.types import AlertEvent, OrphanEvent, ReconciliationResult

_logger = logging.getLogger(__name__)


class ReconciliationGate:
    def __init__(
        self,
        *,
        store: StateStore,
        http: Any,
        quarantine: QuarantineBook,
        alerts: AlertDispatcher,
    ) -> None:
        self._store = store
        self._http = http
        self._quarantine = quarantine
        self._alerts = alerts

    def run(self) -> ReconciliationResult:
        _logger.info("reconciliation gate: starting")
        live_orders = self._http.list_recent_orders(status=None)
        cached_orders = self._store.get_open_orders()

        live_by_kalshi_id: dict[str, dict] = {}
        live_by_client_id: dict[str, dict] = {}
        for o in live_orders:
            oid = o.get("order_id")
            cid = o.get("client_order_id")
            if oid:
                live_by_kalshi_id[oid] = o
            if cid:
                live_by_client_id[cid] = o

        cached_by_client_id = {o.client_order_id: o for o in cached_orders}

        resolved_fills: list[str] = []
        resolved_cancels: list[str] = []
        orphan_orders: list[str] = []
        unresolvable: list[dict] = []

        for cached in cached_orders:
            live = live_by_client_id.get(cached.client_order_id)
            if live is None:
                _logger.warning("cached order missing from exchange: client_order_id=%s", cached.client_order_id)
                unresolvable.append({"client_order_id": cached.client_order_id, "reason": "missing from exchange"})
                self._alerts.dispatch(AlertEvent(
                    level="CRITICAL",
                    message=f"Cached order missing from exchange: {cached.client_order_id}",
                    context={"ticker": cached.ticker, "strategy_id": cached.strategy_id},
                ))
                continue
            status = live.get("status", "")
            if status in ("executed", "filled"):
                filled = live.get("filled_count", cached.quantity)
                self._store.mark_order_filled(cached.client_order_id, filled=filled)
                resolved_fills.append(cached.client_order_id)
                _logger.info("resolved missed fill: client_order_id=%s", cached.client_order_id)
            elif status in ("canceled", "cancelled"):
                self._store.mark_order_canceled(cached.client_order_id)
                resolved_cancels.append(cached.client_order_id)
                _logger.info("resolved missed cancel: client_order_id=%s", cached.client_order_id)

        for live in live_orders:
            cid = live.get("client_order_id")
            oid = live.get("order_id")
            status = live.get("status", "")
            if status in ("canceled", "cancelled", "executed", "filled"):
                continue
            if cid and cid in cached_by_client_id:
                continue
            _logger.warning("orphan order at exchange: kalshi_order_id=%s", oid)
            orphan_orders.append(oid)
            self._quarantine.append(OrphanEvent(
                event_type="ORDER",
                ticker=live.get("ticker", ""),
                strategy_id=None,
                detail={"kalshi_order_id": oid, "client_order_id": cid},
            ))
            self._alerts.dispatch(AlertEvent(
                level="CRITICAL",
                message=f"Orphan order detected at exchange: {oid}",
                context={"ticker": live.get("ticker"), "client_order_id": cid},
            ))

        result = ReconciliationResult(
            resolved_fills=resolved_fills,
            resolved_cancels=resolved_cancels,
            orphan_orders=orphan_orders,
            orphan_fills=[],
            orphan_positions=[],
            unresolvable=unresolvable,
        )
        if result.is_clean:
            _logger.info("reconciliation gate: clean — releasing strategies")
        else:
            _logger.error("reconciliation gate: %d unresolvable gaps, %d orphan orders",
                          len(unresolvable), len(orphan_orders))
        return result
