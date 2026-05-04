from __future__ import annotations

from pydantic import ConfigDict, Field
from nautilus_trader.config import LiveDataClientConfig, LiveExecClientConfig

from adapters.kalshi.constants import KALSHI_BASE_URL


class KalshiDataClientConfig(LiveDataClientConfig):
    model_config = ConfigDict(frozen=True)

    api_key: str = Field(...)
    private_key_pem: str = Field(...)
    base_url: str = KALSHI_BASE_URL
    ws_reconnect_delay_secs: float = 1.0
    ws_reconnect_max_delay_secs: float = 30.0


class KalshiExecClientConfig(LiveExecClientConfig):
    model_config = ConfigDict(frozen=True)

    api_key: str = Field(...)
    private_key_pem: str = Field(...)
    base_url: str = KALSHI_BASE_URL
    reconcile_on_connect: bool = True
