import pytest
from unittest.mock import MagicMock, patch
from nautilus_trader.model.identifiers import InstrumentId, Symbol

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.providers import KalshiInstrumentProvider
from adapters.kalshi.config import KalshiDataClientConfig


SAMPLE_MARKETS = [
    {
        "ticker": "KXBTC15M-25APR30-T65499.99",
        "series_ticker": "KXBTC15M",
        "status": "open",
        "yes_bid": 55,
        "yes_ask": 57,
        "close_time": "2025-04-30T15:00:00Z",
        "title": "BTC above 65499.99 at 3pm?",
    },
    {
        "ticker": "KXBTC15M-25APR30-T65999.99",
        "series_ticker": "KXBTC15M",
        "status": "open",
        "yes_bid": 30,
        "yes_ask": 32,
        "close_time": "2025-04-30T15:00:00Z",
        "title": "BTC above 65999.99 at 3pm?",
    },
]


@pytest.fixture()
def mock_http_client():
    client = MagicMock()
    client.list_markets_paged.return_value = SAMPLE_MARKETS
    client.get_market.side_effect = lambda ticker: next(m for m in SAMPLE_MARKETS if m["ticker"] == ticker)
    return client


@pytest.fixture()
def provider(mock_http_client):
    config = KalshiDataClientConfig(api_key="key", private_key_pem="pem")
    return KalshiInstrumentProvider(http_client=mock_http_client, config=config)


def test_load_all_populates_instruments(provider, mock_http_client):
    provider.load_all()
    mock_http_client.list_markets_paged.assert_called_once()
    instruments = provider.get_all()
    assert len(instruments) == 2


def test_load_by_ticker_returns_instrument(provider, mock_http_client):
    instrument_id = InstrumentId(Symbol("KXBTC15M-25APR30-T65499.99"), KALSHI_VENUE)
    provider.load(instrument_id)
    instrument = provider.find(instrument_id)
    assert instrument is not None
    assert instrument.id == instrument_id


def test_load_series_loads_filtered_markets(provider, mock_http_client):
    provider.load_series("KXBTC15M")
    mock_http_client.list_markets_paged.assert_called_once_with(series_ticker="KXBTC15M", status="open")
    instruments = provider.get_all()
    assert len(instruments) == 2
