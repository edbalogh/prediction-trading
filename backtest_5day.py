#!/usr/bin/env python3
"""
5-day backtest — KXATPMATCH binary options, threshold mean-reversion strategy.

Runs across the top N most-liquid contracts over the last 5 days of collected data.
Open positions at expiry are settled at $1.00 (YES) or $0.00 (NO) using markets data.
Generates a text report and saves an equity curve chart to /tmp/backtest_equity.png.

Usage:
    python3.11 backtest_5day.py
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import pandas as pd

# ── Config ───────────────────────────────────────────────────────────────────

CATALOG_PATH = "/tmp/nautilus-test-catalog"
INGESTION_DIR = "/Users/edbalogh/Trading/Ingestion/data"
DATES = ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05"]
SERIES = "KXATPMATCH"
TOP_N = 15
STARTING_CAPITAL = 10_000.0
BUY_THRESHOLD = 0.25
SELL_THRESHOLD = 0.75
TRADE_SIZE = 5

# ── 1. Sync data ─────────────────────────────────────────────────────────────

print(f"Loading data for {SERIES} over {DATES[0]} – {DATES[-1]}...")

from catalog.sync import CatalogBuilder
builder = CatalogBuilder(ingestion_data_dir=INGESTION_DIR, catalog_path=CATALOG_PATH)
for date in DATES:
    path = f"{INGESTION_DIR}/trades/series={SERIES}/date={date}/part.parquet"
    if os.path.exists(path) and not builder.is_synced(path):
        count = builder.sync_trades_file(path)
        print(f"  Synced {count:,} ticks for {date}")

# ── 2. Select top tickers ────────────────────────────────────────────────────

ticker_counts: dict[str, int] = defaultdict(int)
for date in DATES:
    path = f"{INGESTION_DIR}/trades/series={SERIES}/date={date}/part.parquet"
    if not os.path.exists(path):
        continue
    df = pd.read_parquet(path, columns=["ticker"])
    for t, n in df["ticker"].value_counts().items():
        ticker_counts[t] += n

top_tickers = [t for t, _ in sorted(ticker_counts.items(), key=lambda x: -x[1])[:TOP_N]]
print(f"\nTop {TOP_N} tickers by volume:")
for t in top_tickers:
    print(f"  {t}: {ticker_counts[t]:,} trades")

# ── 3. Load settlements from markets data ────────────────────────────────────

# markets/series=KXATPMATCH/date=*/part.parquet has result='yes'|'no' once finalized
settlement_map: dict[str, str] = {}  # ticker -> 'yes' | 'no'
settlement_dates = DATES + ["2026-05-06"]  # include next day for same-day settlements
for date in settlement_dates:
    path = f"{INGESTION_DIR}/markets/series={SERIES}/date={date}/part.parquet"
    if not os.path.exists(path):
        continue
    df = pd.read_parquet(path, columns=["ticker", "result"])
    finalized = df[df["result"].isin(["yes", "no"])].drop_duplicates("ticker")
    for _, row in finalized.iterrows():
        ticker = row["ticker"]
        if ticker in top_tickers and ticker not in settlement_map:
            settlement_map[ticker] = row["result"]

print(f"\nSettlement results loaded: {len(settlement_map)}/{len(top_tickers)} tickers")
for t in top_tickers:
    result = settlement_map.get(t, "unknown")
    print(f"  {t}: {result}")

# ── 4. Load ticks ────────────────────────────────────────────────────────────

from nautilus_trader.persistence.catalog import ParquetDataCatalog
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.instruments import BinaryOption
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.objects import Currency, Price, Quantity, Money

KALSHI_VENUE = Venue("KALSHI")
catalog = ParquetDataCatalog(CATALOG_PATH)

instrument_ids_str = [f"{t}.KALSHI" for t in top_tickers]
all_ticks = catalog.trade_ticks(instrument_ids=instrument_ids_str)
print(f"\nLoaded {len(all_ticks):,} total trade ticks across {TOP_N} instruments")

if not all_ticks:
    print("No ticks found — check catalog path")
    sys.exit(1)

ticks_by_instrument: dict[str, list] = defaultdict(list)
for tick in all_ticks:
    ticks_by_instrument[tick.instrument_id.symbol.value].append(tick)

# ── 5. Build instruments ─────────────────────────────────────────────────────

instruments = []
for ticker in top_tickers:
    ticks = ticks_by_instrument.get(ticker, [])
    if not ticks:
        continue
    iid = InstrumentId(Symbol(ticker), KALSHI_VENUE)
    ts_first = min(t.ts_event for t in ticks)
    ts_last = max(t.ts_event for t in ticks)
    instruments.append(BinaryOption(
        instrument_id=iid,
        raw_symbol=Symbol(ticker),
        asset_class=AssetClass.ALTERNATIVE,
        currency=Currency.from_str("USD"),
        price_precision=2,
        price_increment=Price(0.01, 2),
        size_precision=0,
        size_increment=Quantity(1, 0),
        activation_ns=ts_first,
        expiration_ns=ts_last + 1,
        max_quantity=None,
        min_quantity=Quantity(1, 0),
        ts_event=0,
        ts_init=0,
        outcome=ticker,
        description=ticker,
    ))

# ── 6. Backtest engine ───────────────────────────────────────────────────────

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.currencies import USD

engine = BacktestEngine(
    config=BacktestEngineConfig(logging=LoggingConfig(log_level="ERROR"))
)
engine.add_venue(
    venue=KALSHI_VENUE,
    oms_type=OmsType.NETTING,
    account_type=AccountType.CASH,
    starting_balances=[Money(STARTING_CAPITAL, USD)],
)
for instrument in instruments:
    engine.add_instrument(instrument)
engine.add_data(all_ticks)

# ── 7. Strategy ──────────────────────────────────────────────────────────────

from nautilus_trader.trading.strategy import Strategy
from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide


class ThresholdConfig(StrategyConfig, frozen=True):
    tickers: tuple[str, ...]
    venue: str = "KALSHI"
    buy_threshold: float = 0.25
    sell_threshold: float = 0.75
    trade_size: int = 5


class ThresholdStrategy(Strategy):
    """
    Buy YES when price < buy_threshold; take profit when price > sell_threshold.
    Open positions at expiry are settled in post-processing (not here).
    """

    def __init__(self, config: ThresholdConfig) -> None:
        super().__init__(config)
        self._venue = Venue(config.venue)
        self._buy_threshold = config.buy_threshold
        self._sell_threshold = config.sell_threshold
        self._trade_size = config.trade_size
        self._positions: dict[str, int] = {}

    def on_start(self) -> None:
        for ticker in self.config.tickers:
            iid = InstrumentId(Symbol(ticker), self._venue)
            self.subscribe_trade_ticks(iid)
            self._positions[ticker] = 0

    def on_trade_tick(self, tick: TradeTick) -> None:
        ticker = tick.instrument_id.symbol.value
        price = tick.price.as_double()
        pos = self._positions.get(ticker, 0)

        if price <= self._buy_threshold and pos <= 0:
            self._submit(tick.instrument_id, OrderSide.BUY, self._trade_size)
            self._positions[ticker] = self._trade_size
        elif price >= self._sell_threshold and pos > 0:
            self._submit(tick.instrument_id, OrderSide.SELL, pos)
            self._positions[ticker] = 0

    def _submit(self, instrument_id: InstrumentId, side: OrderSide, size: int) -> None:
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=side,
            quantity=Quantity(size, 0),
        )
        self.submit_order(order)


strategy = ThresholdStrategy(
    ThresholdConfig(
        tickers=tuple(t for t in top_tickers if t in ticks_by_instrument),
        buy_threshold=BUY_THRESHOLD,
        sell_threshold=SELL_THRESHOLD,
        trade_size=TRADE_SIZE,
    )
)
engine.add_strategy(strategy)

# ── 8. Run ───────────────────────────────────────────────────────────────────

print("\nRunning backtest...")
engine.run()
print("Done.\n")

# ── 9. Results + settlement post-processing ──────────────────────────────────

fills = engine.trader.generate_order_fills_report()
positions = engine.trader.generate_positions_report()
account = engine.trader.generate_account_report(KALSHI_VENUE)

total_fills = len(fills) if not fills.empty else 0
final_balance = float(account["total"].iloc[-1]) if not account.empty else STARTING_CAPITAL

# Split positions into closed and open
open_positions = pd.DataFrame()
closed_positions = pd.DataFrame()
if not positions.empty:
    if "ts_closed" in positions.columns:
        open_positions = positions[positions["ts_closed"].isna()].copy()
        closed_positions = positions[positions["ts_closed"].notna()].copy()
    else:
        open_positions = positions.copy()

# Compute settlement P&L for open positions
settlement_results = []
settlement_pnl = 0.0

for _, pos in open_positions.iterrows():
    ticker = str(pos["instrument_id"]).replace(".KALSHI", "")
    result = settlement_map.get(ticker)
    side = str(pos.get("side", "LONG"))

    # quantity: current open size
    raw_qty = pos.get("quantity", 0)
    try:
        qty = float(str(raw_qty).split()[0]) if raw_qty else 0
    except Exception:
        qty = 0

    avg_open = float(pos.get("avg_px_open", 0))

    if result is None or qty == 0:
        settlement_results.append({
            "ticker": ticker, "result": "unknown", "qty": qty,
            "avg_open": avg_open, "settlement_price": None, "pnl": 0.0,
        })
        continue

    settlement_price = 1.00 if result == "yes" else 0.00
    pnl = (settlement_price - avg_open) * qty
    settlement_pnl += pnl

    settlement_results.append({
        "ticker": ticker, "result": result, "qty": qty,
        "avg_open": avg_open, "settlement_price": settlement_price, "pnl": pnl,
    })

# Realized P&L from closed positions
realized_pnl = 0.0
if not closed_positions.empty and "realized_pnl" in closed_positions.columns:
    pnl_col = closed_positions["realized_pnl"].astype(str).str.replace(r"\s*USD", "", regex=True).astype(float)
    realized_pnl = pnl_col.sum()
    winners = (pnl_col > 0).sum()
    losers = (pnl_col < 0).sum()
else:
    winners = losers = 0

total_pnl = realized_pnl + settlement_pnl
total_pnl_pct = (total_pnl / STARTING_CAPITAL) * 100

# ── 10. Print report ─────────────────────────────────────────────────────────

print(f"{'='*56}")
print(f"  BACKTEST RESULTS — {SERIES} — {DATES[0]} to {DATES[-1]}")
print(f"{'='*56}")
print(f"  Starting capital      : ${STARTING_CAPITAL:>10,.2f}")
print(f"  Total fills           : {total_fills:>10}")
print(f"  Closed positions      : {len(closed_positions):>10}")
print(f"    Winners             : {winners:>10}")
print(f"    Losers              : {losers:>10}")
if winners + losers > 0:
    print(f"    Win rate (closed)   : {winners / (winners + losers) * 100:>9.1f}%")
print(f"  Realized P&L          : ${realized_pnl:>+10,.2f}")
print(f"  Open at expiry        : {len(open_positions):>10}")
print(f"  Settlement P&L        : ${settlement_pnl:>+10,.2f}")
print(f"  ──────────────────────────────────────")
print(f"  Total P&L             : ${total_pnl:>+10,.2f}  ({total_pnl_pct:+.2f}%)")
print(f"{'='*56}\n")

if settlement_results:
    print("=== Settlement of Open Positions ===")
    print(f"  {'Ticker':<42} {'Res':>3}  {'Qty':>3}  {'Avg Open':>8}  {'Settle':>6}  {'P&L':>8}")
    print(f"  {'-'*42} {'-'*3}  {'-'*3}  {'-'*8}  {'-'*6}  {'-'*8}")
    for s in sorted(settlement_results, key=lambda x: x["pnl"]):
        settle_str = f"{s['settlement_price']:.2f}" if s["settlement_price"] is not None else "  n/a"
        pnl_str = f"${s['pnl']:+.2f}" if s["settlement_price"] is not None else "  n/a"
        print(f"  {s['ticker']:<42} {s['result']:>3}  {s['qty']:>3.0f}  {s['avg_open']:>8.3f}  {settle_str:>6}  {pnl_str:>8}")

if not closed_positions.empty:
    print("\n=== Closed Positions ===")
    display_cols = [c for c in ["instrument_id", "side", "avg_px_open", "avg_px_close", "realized_pnl"] if c in closed_positions.columns]
    print(closed_positions[display_cols].to_string(index=False))

# ── 11. Equity curve ──────────────────────────────────────────────────────────

if not account.empty and len(account) > 2:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates

        account_copy = account.copy()
        account_copy.index = pd.to_datetime(account_copy.index)
        account_copy["total"] = account_copy["total"].astype(float)

        # Append settlement as a final point
        if settlement_results:
            last_ts = account_copy.index[-1] + pd.Timedelta(minutes=5)
            account_copy.loc[last_ts] = account_copy.iloc[-1].copy()
            account_copy.loc[last_ts, "total"] = float(account_copy["total"].iloc[-1]) + settlement_pnl

        fig, axes = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]})

        times = account_copy.index
        balances = account_copy["total"].astype(float)

        axes[0].plot(times, balances, color="#2196F3", linewidth=1.5)
        axes[0].axhline(y=STARTING_CAPITAL, color="#888", linestyle="--", linewidth=0.8, label="Starting capital")
        axes[0].fill_between(times, STARTING_CAPITAL, balances,
                             where=(balances >= STARTING_CAPITAL), alpha=0.15, color="green")
        axes[0].fill_between(times, STARTING_CAPITAL, balances,
                             where=(balances < STARTING_CAPITAL), alpha=0.15, color="red")

        # Mark settlement point
        if settlement_results:
            axes[0].axvline(x=last_ts, color="orange", linestyle=":", linewidth=1.2, label="Settlement")
            axes[0].scatter([last_ts], [balances.iloc[-1]], color="orange", zorder=5, s=40)

        final_total = float(balances.iloc[-1])
        total_return = final_total - STARTING_CAPITAL
        axes[0].set_title(
            f"{SERIES} Threshold Strategy — {DATES[0]} to {DATES[-1]}\n"
            f"Buy < {BUY_THRESHOLD} / Sell > {SELL_THRESHOLD} | {TOP_N} instruments | "
            f"Total P&L: ${total_return:+.2f}  ({total_return/STARTING_CAPITAL*100:+.2f}%)",
            fontsize=11,
        )
        axes[0].set_ylabel("Account Balance ($)")
        axes[0].legend(loc="upper left")
        axes[0].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        axes[0].grid(True, alpha=0.3)

        # Daily P&L
        daily = account_copy["total"].resample("D").last().dropna()
        daily_pnl = daily.diff().dropna()
        colors = ["green" if v >= 0 else "red" for v in daily_pnl]
        axes[1].bar(daily_pnl.index, daily_pnl.values, color=colors, alpha=0.7, width=0.6)
        axes[1].axhline(y=0, color="#888", linewidth=0.8)
        axes[1].set_ylabel("Daily P&L ($)")
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()
        chart_path = "/tmp/backtest_equity.png"
        plt.savefig(chart_path, dpi=150)
        plt.close()
        print(f"\nEquity curve chart saved to: {chart_path}")
    except Exception as e:
        print(f"\n(Chart generation skipped: {e})")

engine.dispose()
