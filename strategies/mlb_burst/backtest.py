"""Stub backtest entry point — implements JSONL contract. Replace with real logic."""
from __future__ import annotations

import argparse
import json
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--params", default="{}")
    args = parser.parse_args()

    for i in range(1, 6):
        time.sleep(0.05)
        print(json.dumps({"type": "progress", "pct": i * 20, "msg": f"Processing batch {i}/5"}), flush=True)

    print(json.dumps({
        "type": "result",
        "kpis": {
            "total_trades": 0,
            "win_rate": 0.0,
            "realized_pnl": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
        },
        "trades": [],
        "equity_curve": [{"ts": int(time.time()), "equity": 10000.0}],
    }), flush=True)


if __name__ == "__main__":
    main()
