from __future__ import annotations

import time
import pytest

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.model.identifiers import ClientId, InstrumentId, Symbol, Venue
from nautilus_trader.model.enums import AccountType, OmsType
from nautilus_trader.model.objects import Currency, Price, Quantity

from adapters.kalshi.paper import PaperExecClientConfig, PaperExecutionClient, PaperExecClientFactory
from adapters.kalshi.constants import KALSHI_VENUE


def _make_client(starting_cash: float = 10_000.0) -> PaperExecutionClient:
    from nautilus_trader.common.component import MessageBus, TestClock
    from nautilus_trader.model.identifiers import TraderId
    clock = TestClock()
    msgbus = MessageBus(
        trader_id=TraderId("TRADER-001"),
        clock=clock,
    )
    cache = Cache()
    provider = InstrumentProvider()
    cfg = PaperExecClientConfig(starting_cash=starting_cash)
    return PaperExecutionClient(
        config=cfg,
        instrument_provider=provider,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )


def test_initial_state():
    client = _make_client(10_000.0)
    assert client.cash() == 10_000.0
    assert client.positions() == {}
    assert client.fills() == []


@pytest.mark.asyncio
async def test_connect_sets_cash():
    client = _make_client(5_000.0)
    await client._connect()
    assert client.cash() == 5_000.0


def test_config_default_cash():
    cfg = PaperExecClientConfig()
    assert cfg.starting_cash == 10_000.0


def test_factory_registers_instance():
    from nautilus_trader.common.component import MessageBus, TestClock
    from nautilus_trader.model.identifiers import TraderId
    from adapters.kalshi import paper as paper_mod
    paper_mod._paper_exec_client = None

    clock = TestClock()
    msgbus = MessageBus(trader_id=TraderId("TRADER-001"), clock=clock)
    cache = Cache()
    cfg = PaperExecClientConfig()

    client = PaperExecClientFactory.create(
        loop=None,
        name="PAPER",
        config=cfg,
        msgbus=msgbus,
        cache=cache,
        clock=clock,
    )
    assert paper_mod._paper_exec_client is client
