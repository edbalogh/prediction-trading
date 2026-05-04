from __future__ import annotations

import time
from typing import Any

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from adapters.kalshi.http.auth import load_private_key, sign_request

_RETRYABLE = {429, 500, 502, 503, 504}


class KalshiHttpClient:
    def __init__(self, *, base_url: str, api_key: str, private_key_pem: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._key: RSAPrivateKey | None = load_private_key(private_key_pem) if private_key_pem else None

    # ── Instruments ──────────────────────────────────────────────────────────

    def get_market(self, ticker: str) -> dict[str, Any]:
        data = self._request("GET", f"/markets/{ticker}")
        return data.get("market", data)

    def list_markets_paged(
        self,
        *,
        status: str | None = "open",
        series_ticker: str | None = None,
        limit: int = 1000,
        pages: int = 10,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(pages):
            params: dict[str, Any] = {"limit": limit}
            if status:
                params["status"] = status
            if series_ticker:
                params["series_ticker"] = series_ticker
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/markets", params=params)
            results.extend(data.get("markets", []))
            cursor = data.get("cursor", "")
            if not cursor:
                break
        return results

    def get_orderbook(self, ticker: str) -> dict[str, Any]:
        return self._request("GET", f"/markets/{ticker}/orderbook")

    # ── Orders ────────────────────────────────────────────────────────────────

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = self._request("POST", "/portfolio/orders", json=payload)
        order = data.get("order", data)
        return {
            "kalshi_order_id": order.get("order_id") or order.get("id"),
            "status": order.get("status", "accepted"),
            "raw": data,
        }

    def cancel_order(self, kalshi_order_id: str) -> dict[str, Any]:
        data = self._request("DELETE", f"/portfolio/orders/{kalshi_order_id}")
        return data.get("order", data)

    def list_recent_orders(self, limit: int = 100) -> list[dict[str, Any]]:
        data = self._request("GET", "/portfolio/orders", params={"limit": limit, "status": "resting"})
        return data.get("orders", [])

    def list_recent_fills(self, limit: int = 100) -> list[dict[str, Any]]:
        data = self._request("GET", "/portfolio/fills", params={"limit": limit})
        return data.get("fills", [])

    # ── Positions ─────────────────────────────────────────────────────────────

    def list_positions(self, limit: int = 1000, pages: int = 10) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor = ""
        for _ in range(pages):
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor
            data = self._request("GET", "/portfolio/positions", params=params)
            results.extend(data.get("market_positions", []))
            cursor = data.get("cursor", "")
            if not cursor:
                break
        return results

    # ── WebSocket ─────────────────────────────────────────────────────────────

    def websocket_url(self) -> str:
        base = self._base_url.replace("/trade-api/v2", "")
        return base.replace("https://", "wss://") + "/trade-api/ws/v2"

    def websocket_headers(self) -> dict[str, str]:
        path = "/trade-api/ws/v2"
        ts_ms = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": sign_request(self._key, timestamp_ms=ts_ms, method="GET", path=path),
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sign_headers(self, method: str, path: str) -> dict[str, str]:
        ts_ms = str(int(time.time() * 1000))
        return {
            "KALSHI-ACCESS-KEY": self._api_key,
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
            "KALSHI-ACCESS-SIGNATURE": sign_request(self._key, timestamp_ms=ts_ms, method=method, path=path),
        }

    def _request(
        self,
        method: str,
        api_path: str,
        json: dict | None = None,
        params: dict | None = None,
        retries: int = 3,
    ) -> dict[str, Any]:
        url = self._base_url + api_path
        headers = self._sign_headers(method, api_path) if self._key else {}
        for attempt in range(retries):
            with httpx.Client(timeout=10) as client:
                response = client.request(method, url, json=json, params=params, headers=headers)
            if response.status_code not in _RETRYABLE or attempt == retries - 1:
                response.raise_for_status()
                return response.json()
            time.sleep(2 ** attempt)
        raise RuntimeError("unreachable")
