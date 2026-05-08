from __future__ import annotations

STRATEGIES: dict[str, dict] = {
    "mlb_burst": {
        "display_name": "MLB Burst",
        "icon": "⚡",
        "state_port": 8766,
        "paper_script": "scripts/paper_trade_mlb.py",
        "live_script": None,
        "starting_capital": 10_000.0,
    },
    "threshold": {
        "display_name": "Threshold",
        "icon": "↕",
        "state_port": 8767,
        "paper_script": "scripts/paper_trade.py",
        "live_script": None,
        "starting_capital": 10_000.0,
    },
}
