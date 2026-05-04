from __future__ import annotations

import logging

from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.model.identifiers import InstrumentId

from adapters.kalshi.config import KalshiDataClientConfig
from adapters.kalshi.factories import market_to_binary_option
from adapters.kalshi.http.client import KalshiHttpClient

_logger = logging.getLogger(__name__)


class KalshiInstrumentProvider(InstrumentProvider):
    def __init__(self, http_client: KalshiHttpClient, config: KalshiDataClientConfig) -> None:
        super().__init__()
        self._http = http_client
        self._config = config

    def load_all(self, filters: dict | None = None) -> None:
        markets = self._http.list_markets_paged(status="open")
        _logger.info("loaded %d markets from Kalshi", len(markets))
        for market in markets:
            try:
                instrument = market_to_binary_option(market)
                self.add(instrument)
            except Exception:
                _logger.exception("failed to convert market ticker=%s", market.get("ticker"))

    def load(self, instrument_id: InstrumentId, filters: dict | None = None) -> None:
        ticker = instrument_id.symbol.value
        market = self._http.get_market(ticker)
        try:
            instrument = market_to_binary_option(market)
            self.add(instrument)
        except Exception:
            _logger.exception("failed to convert market ticker=%s", ticker)

    def load_series(self, series_ticker: str) -> None:
        markets = self._http.list_markets_paged(series_ticker=series_ticker, status="open")
        _logger.info("loaded %d markets for series %s", len(markets), series_ticker)
        for market in markets:
            try:
                instrument = market_to_binary_option(market)
                self.add(instrument)
            except Exception:
                _logger.exception("failed to convert market ticker=%s", market.get("ticker"))
