import pytest
import respx
import httpx
from unittest.mock import MagicMock

from adapters.kalshi.http.client import KalshiHttpClient


def _make_client() -> KalshiHttpClient:
    return KalshiHttpClient(
        base_url="https://trading-api.kalshi.com/trade-api/v2",
        api_key="test-key",
        private_key_pem="",  # auth is mocked
    )


@respx.mock
def test_get_market_returns_market_dict():
    respx.get("https://trading-api.kalshi.com/trade-api/v2/markets/KXBTC15M-X").mock(
        return_value=httpx.Response(200, json={"market": {"ticker": "KXBTC15M-X", "status": "open"}})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})  # skip real signing
    result = client.get_market("KXBTC15M-X")
    assert result["ticker"] == "KXBTC15M-X"


@respx.mock
def test_list_markets_paged_returns_list():
    respx.get("https://trading-api.kalshi.com/trade-api/v2/markets").mock(
        return_value=httpx.Response(200, json={"markets": [{"ticker": "A"}, {"ticker": "B"}], "cursor": ""})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})
    result = client.list_markets_paged(status="open", pages=1)
    assert len(result) == 2
    assert result[0]["ticker"] == "A"


@respx.mock
def test_place_order_returns_order_id():
    respx.post("https://trading-api.kalshi.com/trade-api/v2/portfolio/orders").mock(
        return_value=httpx.Response(200, json={"order": {"order_id": "abc123", "status": "resting"}})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})
    result = client.place_order({"ticker": "KXBTC15M-X", "side": "yes", "count": 10, "type": "limit", "yes_price": 55})
    assert result["kalshi_order_id"] == "abc123"


@respx.mock
def test_cancel_order_succeeds():
    respx.delete("https://trading-api.kalshi.com/trade-api/v2/portfolio/orders/abc123").mock(
        return_value=httpx.Response(200, json={"order": {"order_id": "abc123", "status": "canceled"}})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})
    result = client.cancel_order("abc123")
    assert result["status"] == "canceled"


@respx.mock
def test_list_positions_returns_list():
    respx.get("https://trading-api.kalshi.com/trade-api/v2/portfolio/positions").mock(
        return_value=httpx.Response(200, json={"market_positions": [{"ticker": "KXBTC15M-X", "position": 5}], "cursor": ""})
    )
    client = _make_client()
    client._sign_headers = MagicMock(return_value={})
    result = client.list_positions()
    assert len(result) == 1
    assert result[0]["ticker"] == "KXBTC15M-X"
