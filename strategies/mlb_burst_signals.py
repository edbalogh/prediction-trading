from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from nautilus_trader.model.data import TradeTick


@dataclass(frozen=True)
class SweepResult:
    side: str        # "YES" or "NO"
    end_price: float
    end_ts: int      # nanoseconds


def detect_sweep(
    ticks: deque[TradeTick],
    *,
    min_fills: int,
    max_duration_s: float,
    min_spread_cents: int,
) -> SweepResult | None:
    """
    Scan ticks for a price burst satisfying:
    - >= min_fills within max_duration_s seconds
    - Price spread >= min_spread_cents / 100
    - Clear net direction (start != end price)

    Backtest note: test alternate thresholds (different min_spread_cents, min_fills,
    max_duration_s) against the reference dataset before live deployment.
    """
    tick_list = list(ticks)
    window_ns = int(max_duration_s * 1_000_000_000)
    min_spread = min_spread_cents / 100

    for i in range(len(tick_list)):
        burst = [tick_list[i]]
        for j in range(i + 1, len(tick_list)):
            if tick_list[j].ts_event - tick_list[i].ts_event > window_ns:
                break
            burst.append(tick_list[j])
        if len(burst) < min_fills:
            continue
        prices = [t.price.as_double() for t in burst]
        if max(prices) - min(prices) < min_spread:
            continue
        start_price = prices[0]
        end_price = prices[-1]
        if end_price > start_price:
            side = "YES"
        elif end_price < start_price:
            side = "NO"
        else:
            continue
        return SweepResult(side=side, end_price=end_price, end_ts=burst[-1].ts_event)
    return None


def confirm_w1(
    ticks: deque[TradeTick],
    sweep: SweepResult,
    *,
    window_start_s: float,
    window_end_s: float,
    min_trades: int,
    same_dir_pct: float,
) -> bool:
    """
    Confirm W1 using ticks in [sweep.end_ts + window_start_s, sweep.end_ts + window_end_s].

    All three conditions must pass:
    1. >= min_trades in window
    2. >= same_dir_pct have price at or beyond sweep end price (in sweep direction)
    3. At least one tick strictly past sweep end price (continuation)

    Backtest note: test removing condition 3, varying same_dir_pct (0.5–0.8), and
    replacing condition 2 with consecutive-direction counting against the reference dataset.
    """
    start_ns = sweep.end_ts + int(window_start_s * 1_000_000_000)
    end_ns = sweep.end_ts + int(window_end_s * 1_000_000_000)
    window_ticks = [t for t in ticks if start_ns <= t.ts_event <= end_ns]

    if len(window_ticks) < min_trades:
        return False

    prices = [t.price.as_double() for t in window_ticks]
    if sweep.side == "YES":
        same_dir_count = sum(1 for p in prices if p >= sweep.end_price)
        has_continuation = any(p > sweep.end_price for p in prices)
    else:
        same_dir_count = sum(1 for p in prices if p <= sweep.end_price)
        has_continuation = any(p < sweep.end_price for p in prices)

    if same_dir_count / len(prices) < same_dir_pct:
        return False
    return has_continuation
