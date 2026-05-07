from __future__ import annotations

from nautilus_trader.live.factories import LiveDataClientFactory, LiveExecClientFactory

from adapters.kalshi.config import KalshiDataClientConfig, KalshiExecClientConfig
from adapters.kalshi.data import KalshiDataClient
from adapters.kalshi.execution import KalshiExecutionClient
from adapters.kalshi.http.client import KalshiHttpClient
from adapters.kalshi.providers import KalshiInstrumentProvider


class KalshiDataClientFactory(LiveDataClientFactory):
    @staticmethod
    def create(loop, name, config: KalshiDataClientConfig, msgbus, cache, clock):
        http_client = KalshiHttpClient(
            base_url=config.base_url,
            api_key=config.api_key,
            private_key_pem=config.private_key_pem,
        )
        return KalshiDataClient(
            loop=loop,
            http_client=http_client,
            config=config,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )


class KalshiExecClientFactory(LiveExecClientFactory):
    @staticmethod
    def create(loop, name, config: KalshiExecClientConfig, msgbus, cache, clock):
        http_client = KalshiHttpClient(
            base_url=config.base_url,
            api_key=config.api_key,
            private_key_pem=config.private_key_pem,
        )
        provider = KalshiInstrumentProvider(
            http_client=http_client,
            config=KalshiDataClientConfig(
                api_key=config.api_key,
                private_key_pem=config.private_key_pem,
                base_url=config.base_url,
            ),
        )
        return KalshiExecutionClient(
            loop=loop,
            http_client=http_client,
            config=config,
            instrument_provider=provider,
            msgbus=msgbus,
            cache=cache,
            clock=clock,
        )
