#!/usr/bin/env python3
"""
Paper trade the MLBBurstStrategy against live Kalshi KXMLBGAME markets.

Usage:
    python3 paper_trade_mlb.py

Credentials are loaded from .env in the project root.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from dotenv import load_dotenv
load_dotenv()

from aiohttp import web
from nautilus_trader.config import (
    LiveDataEngineConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    TradingNodeConfig,
)
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue

from adapters.kalshi.config import KalshiDataClientConfig
from adapters.kalshi.constants import KALSHI_BASE_URL
from adapters.kalshi.http.client import KalshiHttpClient
from adapters.kalshi.live_factories import KalshiDataClientFactory
from adapters.kalshi.paper import PaperExecClientConfig, PaperExecClientFactory
import adapters.kalshi.paper as paper_mod
from adapters.mlb_stats.client import MLBStatsClient
from strategies.mlb_burst import MLBBurstConfig, MLBBurstStrategy

STARTING_CAPITAL = 10_000.0
STATE_PORT = 8766

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
_logger = logging.getLogger(__name__)


def _build_state_response(node: TradingNode, strategy: MLBBurstStrategy) -> dict:
    exec_client = paper_mod._paper_exec_client
    if exec_client is None:
        return {"error": "exec client not ready"}

    cache = node.cache
    cash = exec_client.cash()
    raw_positions = exec_client.positions()

    unrealized_pnl = 0.0
    positions_out = {}
    kalshi_venue = Venue("KALSHI")
    for ticker, pos_info in raw_positions.items():
        iid = InstrumentId(Symbol(ticker), kalshi_venue)
        last_price_obj = cache.price(iid, PriceType.LAST)
        last_px = last_price_obj.as_double() if last_price_obj is not None else pos_info["avg_px"]
        qty = pos_info["qty"]
        position_unrealized = (last_px - pos_info["avg_px"]) * qty
        unrealized_pnl += position_unrealized
        positions_out[ticker] = {
            "qty": qty,
            "avg_px": round(pos_info["avg_px"], 4),
            "last_px": round(last_px, 4),
            "unrealized_pnl": round(position_unrealized, 4),
        }

    realized_pnl = exec_client.realized_pnl()
    total_pnl = realized_pnl + unrealized_pnl

    return {
        "equity": round(STARTING_CAPITAL + total_pnl, 4),
        "starting_capital": STARTING_CAPITAL,
        "pnl": round(total_pnl, 4),
        "realized_pnl": round(realized_pnl, 4),
        "unrealized_pnl": round(unrealized_pnl, 4),
        "positions": positions_out,
        "fills": exec_client.fills()[-20:],
        "entered_games": list(strategy._entered_games),
        "pending_tasks_count": len(strategy._pending_tasks),
        "subscribed_markets": list(strategy._ticker_to_game_pk.keys()),
        "ts": int(time.time()),
    }


async def run_state_server(node: TradingNode, strategy: MLBBurstStrategy) -> web.AppRunner:
    async def handle_state(request):
        data = _build_state_response(node, strategy)
        return web.Response(
            text=json.dumps(data),
            content_type="application/json",
            headers={"Access-Control-Allow-Origin": "*"},
        )

    app = web.Application()
    app.router.add_get("/state", handle_state)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "localhost", STATE_PORT, reuse_address=True)
    await site.start()
    _logger.info("StateServer listening on http://localhost:%d/state", STATE_PORT)
    return runner


def main() -> None:
    api_key = os.environ["KALSHI_API_KEY"]
    private_key_pem = os.environ["KALSHI_PRIVATE_KEY_PEM"]

    data_config = KalshiDataClientConfig(
        api_key=api_key,
        private_key_pem=private_key_pem,
    )

    node_config = TradingNodeConfig(
        trader_id="MLB-PAPER-001",
        logging=LoggingConfig(log_level="INFO"),
        data_clients={"KALSHI": data_config},
        exec_clients={"KALSHI": PaperExecClientConfig(
            starting_cash=STARTING_CAPITAL,
            api_key=api_key,
            private_key_pem=private_key_pem,
        )},
        data_engine=LiveDataEngineConfig(),
        exec_engine=LiveExecEngineConfig(),
    )

    async def _run():
        http_client = KalshiHttpClient(
            base_url=KALSHI_BASE_URL,
            api_key=api_key,
            private_key_pem=private_key_pem,
        )
        mlb_stats = MLBStatsClient()

        node = TradingNode(config=node_config)
        node.add_data_client_factory("KALSHI", KalshiDataClientFactory)
        node.add_exec_client_factory("KALSHI", PaperExecClientFactory)

        strategy = MLBBurstStrategy(
            MLBBurstConfig(strategy_id="mlb-burst-paper-001"),
            kalshi_http=http_client,
            mlb_stats=mlb_stats,
        )
        node.trader.add_strategy(strategy)
        node.build()

        runner = await run_state_server(node, strategy)
        try:
            await node.run_async()
        finally:
            await runner.cleanup()
            http_client.close()
            mlb_stats.close()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass
    finally:
        exec_client = paper_mod._paper_exec_client
        if exec_client:
            fills = exec_client.fills()
            open_positions = exec_client.positions()
            realized = exec_client.realized_pnl()
            open_cost_basis = sum(p["avg_px"] * p["qty"] for p in open_positions.values())
            equity = STARTING_CAPITAL + realized + open_cost_basis
            print(f"\n{'='*50}")
            print(f"  Realized P&L:    ${realized:+.2f}")
            print(f"  Open positions:  {len(open_positions)} (${open_cost_basis:.2f} at cost)")
            print(f"  Equity (at cost):${equity:.2f}")
            print(f"  Fills:           {len(fills)}")
            print(f"{'='*50}")


if __name__ == "__main__":
    main()
