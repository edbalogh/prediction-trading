from __future__ import annotations

import pytest

from nautilus_trader.cache.cache import Cache
from nautilus_trader.common.providers import InstrumentProvider

from adapters.kalshi.paper import PaperExecClientConfig, PaperExecutionClient, PaperExecClientFactory


def _make_client(starting_cash: float = 10_000.0) -> PaperExecutionClient:
    import asyncio
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
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
    return PaperExecutionClient(
        loop=loop,
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
async def test_connect_resets_cash():
    client = _make_client(5_000.0)
    client._cash = 3_000.0  # simulate drift after trading
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
