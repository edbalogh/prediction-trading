# dashboard/api/config.py
from __future__ import annotations
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent.parent  # dashboard/api/ → dashboard/ → project root

STRATEGIES: dict[str, dict] = {
    "mlb_burst": {
        "display_name": "MLB Burst",
        "icon": "⚡",
        "state_port": 8766,
        "paper_script": "scripts/paper_trade_mlb.py",
        "live_script": None,
        "backtest_script": "strategies/mlb_burst/backtest.py",
        "starting_capital": 10_000.0,
        "config_path": "strategies/mlb_burst/config.json",
        "config_schema": [
            {"key": "sweep_min_spread_cents", "label": "Min Sweep Spread (¢)",  "type": "int",    "default": 3,     "min": 1,    "max": 50},
            {"key": "sweep_min_fills",         "label": "Min Sweep Fills",       "type": "int",    "default": 2,     "min": 1},
            {"key": "sweep_max_duration_s",    "label": "Max Sweep Duration (s)", "type": "float", "default": 0.5,   "min": 0.1,  "max": 10.0},
            {"key": "w1_window_start_s",       "label": "W1 Window Start (s)",   "type": "float",  "default": 0.3,   "min": 0.05},
            {"key": "w1_window_end_s",         "label": "W1 Window End (s)",     "type": "float",  "default": 3.0,   "min": 0.5},
            {"key": "w1_min_trades",           "label": "W1 Min Trades",         "type": "int",    "default": 2,     "min": 1},
            {"key": "w1_same_dir_pct",         "label": "W1 Same Direction %",   "type": "float",  "default": 0.60,  "min": 0.0,  "max": 1.0},
            {"key": "bail_seconds",            "label": "Bail Seconds",          "type": "int",    "default": 45,    "min": 1},
            {"key": "max_notional_usd",        "label": "Max Notional (USD)",    "type": "float",  "default": 1.00,  "min": 0.01},
            {"key": "data_path",               "label": "Data Path",             "type": "string", "default": "data/mlb"},
        ],
    },
    "threshold": {
        "display_name": "Threshold",
        "icon": "↕",
        "state_port": 8767,
        "paper_script": "scripts/paper_trade.py",
        "live_script": None,
        "backtest_script": "strategies/threshold/backtest.py",
        "starting_capital": 10_000.0,
        "config_path": "strategies/threshold/config.json",
        "config_schema": [
            {"key": "buy_threshold",  "label": "Buy Threshold",           "type": "float",  "default": 0.25, "min": 0.01, "max": 0.99},
            {"key": "sell_threshold", "label": "Sell Threshold",          "type": "float",  "default": 0.75, "min": 0.01, "max": 0.99},
            {"key": "trade_size",     "label": "Trade Size (contracts)",  "type": "int",    "default": 5,    "min": 1},
            {"key": "data_path",      "label": "Data Path",               "type": "string", "default": "data/threshold"},
        ],
    },
}
