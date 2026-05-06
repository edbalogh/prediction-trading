#!/usr/bin/env python3
"""
Minimal backtest demo — KXBTC15M binary option, threshold mean-reversion strategy.

Usage:
    python3.11 backtest_demo.py

Syncs one day of KXBTC15M trade data into a temporary catalog, then runs a
simple threshold strategy: buy YES when price < buy_threshold, sell when
price > sell_threshold.
"""
from __future__ import annotations

import sys

# ── 1. Build a small catalog from one day of KXBTC15M data ──────────────────

CATALOG_PATH = "/tmp/backtest-demo-catalog"
INGESTION_DIR = "/Users/edbalogh/Trading/Ingestion/data"
DEMO_DATE = "2026-02-20"
DEMO_TICKER = "KXBTC15M-26FEB201230-30"

from catalog.sync import CatalogBuilder

builder = CatalogBuilder(ingestion_data_dir=INGESTION_DIR, catalog_path=CATALOG_PATH)
parquet_path = f"{INGESTION_DIR}/trades/series=KXBTC15M/date={DEMO_DATE}/part.parquet"
if not builder.is_synced(parquet_path):
    count = builder.sync_trades_file(parquet_path)
    print(f"Synced {count} ticks from {DEMO_DATE}")

from nautilus_trader.persistence.catalog import ParquetDataCatalog

catalog = ParquetDataCatalog(CATALOG_PATH)
ticks = catalog.trade_ticks(instrument_ids=[f"{DEMO_TICKER}.KALSHI"])
print(f"Loaded {len(ticks)} trade ticks for {DEMO_TICKER}")
if not ticks:
    print("No ticks — check catalog path and ticker")
    sys.exit(1)

price_vals = [t.price.as_double() for t in ticks]
print(f"Price range: {min(price_vals):.2f} – {max(price_vals):.2f}")

# ── 2. Construct the BinaryOption instrument ─────────────────────────────────

from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.objects import Currency, Price, Quantity, Money

KALSHI_VENUE = Venue("KALSHI")
instrument_id = InstrumentId(Symbol(DEMO_TICKER), KALSHI_VENUE)

instrument = BinaryOption(
    instrument_id=instrument_id,
    raw_symbol=Symbol(DEMO_TICKER),
    asset_class=AssetClass.ALTERNATIVE,
    currency=Currency.from_str("USD"),
    price_precision=2,
    price_increment=Price(0.01, 2),
    size_precision=0,
    size_increment=Quantity(1, 0),
    activation_ns=ticks[0].ts_event,
    expiration_ns=ticks[-1].ts_event + 1,
    max_quantity=None,
    min_quantity=Quantity(1, 0),
    ts_event=0,
    ts_init=0,
    outcome=DEMO_TICKER,
    description="Will BTC reach target at 12:30pm?",
)

# ── 3. Set up the backtest engine ────────────────────────────────────────────

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.currencies import USD

engine = BacktestEngine(
    config=BacktestEngineConfig(
        logging=LoggingConfig(log_level="WARNING"),
    )
)

engine.add_venue(
    venue=KALSHI_VENUE,
    oms_type=OmsType.NETTING,
    account_type=AccountType.CASH,
    starting_balances=[Money(10_000, USD)],
)

engine.add_instrument(instrument)
engine.add_data(ticks)

# ── 4. Define the strategy ───────────────────────────────────────────────────

from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide


class ThresholdConfig(StrategyConfig, frozen=True):
    instrument_id: str
    buy_threshold: float = 0.25
    sell_threshold: float = 0.50
    trade_size: int = 10


class ThresholdStrategy(Strategy):
    """Buy YES when price drops below buy_threshold; sell when it rises above sell_threshold."""

    def __init__(self, config: ThresholdConfig) -> None:
        super().__init__(config)
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.buy_threshold = config.buy_threshold
        self.sell_threshold = config.sell_threshold
        self.trade_size = config.trade_size
        self._net_position = 0

    def on_start(self) -> None:
        self.subscribe_trade_ticks(self.instrument_id)
        self.log.info(f"Strategy started — buy<{self.buy_threshold}, sell>{self.sell_threshold}")

    def on_trade_tick(self, tick: TradeTick) -> None:
        price = tick.price.as_double()

        if price <= self.buy_threshold and self._net_position <= 0:
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity(self.trade_size, 0),
            )
            self.submit_order(order)
            self._net_position += self.trade_size

        elif price >= self.sell_threshold and self._net_position > 0:
            order = self.order_factory.market(
                instrument_id=self.instrument_id,
                order_side=OrderSide.SELL,
                quantity=Quantity(self._net_position, 0),
            )
            self.submit_order(order)
            self._net_position = 0


strategy = ThresholdStrategy(
    ThresholdConfig(
        instrument_id=f"{DEMO_TICKER}.KALSHI",
        buy_threshold=0.25,
        sell_threshold=0.50,
        trade_size=10,
    )
)

engine.add_strategy(strategy)

# ── 5. Run ───────────────────────────────────────────────────────────────────

print("\nRunning backtest...")
engine.run()
print("Done.\n")

# ── 6. Results ───────────────────────────────────────────────────────────────

from nautilus_trader.model.currencies import USD as USD_CURRENCY

print("=== Order Fills ===")
fills = engine.trader.generate_order_fills_report()
print(fills.to_string() if not fills.empty else "  (no fills)")

print("\n=== Positions ===")
positions = engine.trader.generate_positions_report()
print(positions.to_string() if not positions.empty else "  (no positions)")

print("\n=== Account ===")
account = engine.trader.generate_account_report(KALSHI_VENUE)
print(account.to_string() if not account.empty else "  (no account data)")

engine.dispose()
