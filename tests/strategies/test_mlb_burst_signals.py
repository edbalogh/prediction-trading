from __future__ import annotations

import uuid
from collections import deque

from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TradeId, Venue
from nautilus_trader.model.objects import Price, Quantity

from strategies.mlb_burst.mlb_burst_signals import SweepResult, detect_sweep, confirm_w1

KALSHI = Venue("KALSHI")
IID = InstrumentId(Symbol("KXMLBGAME-26MAY01-AZ"), KALSHI)


def _tick(price: float, ts_event: int) -> TradeTick:
    return TradeTick(
        instrument_id=IID,
        price=Price(price, 2),
        size=Quantity(1, 0),
        aggressor_side=AggressorSide.BUYER,
        trade_id=TradeId(uuid.uuid4().hex[:8]),
        ts_event=ts_event,
        ts_init=ts_event,
    )


def ms(n: float) -> int:
    """Convert milliseconds to nanoseconds."""
    return int(n * 1_000_000)


# ── detect_sweep ──────────────────────────────────────────────────────────────

def test_detect_sweep_yes_direction():
    buf = deque([
        _tick(0.30, ms(0)),
        _tick(0.34, ms(200)),   # 200ms window, spread=0.04, YES direction
    ])
    result = detect_sweep(buf, min_fills=2, max_duration_s=0.5, min_spread_cents=3)
    assert result is not None
    assert result.side == "YES"
    assert abs(result.end_price - 0.34) < 1e-6
    assert result.end_ts == ms(200)


def test_detect_sweep_no_direction():
    buf = deque([
        _tick(0.70, ms(0)),
        _tick(0.65, ms(300)),   # NO direction
    ])
    result = detect_sweep(buf, min_fills=2, max_duration_s=0.5, min_spread_cents=3)
    assert result is not None
    assert result.side == "NO"


def test_detect_sweep_returns_none_if_spread_too_small():
    buf = deque([
        _tick(0.50, ms(0)),
        _tick(0.51, ms(200)),   # spread=0.01 < 0.03
    ])
    result = detect_sweep(buf, min_fills=2, max_duration_s=0.5, min_spread_cents=3)
    assert result is None


def test_detect_sweep_returns_none_if_too_few_fills():
    buf = deque([
        _tick(0.30, ms(0)),     # only 1 fill
    ])
    result = detect_sweep(buf, min_fills=2, max_duration_s=0.5, min_spread_cents=3)
    assert result is None


def test_detect_sweep_returns_none_if_window_exceeded():
    buf = deque([
        _tick(0.30, ms(0)),
        _tick(0.40, ms(600)),   # 600ms > 500ms window
    ])
    result = detect_sweep(buf, min_fills=2, max_duration_s=0.5, min_spread_cents=3)
    assert result is None


def test_detect_sweep_returns_none_if_no_direction():
    # Spread passes but start==end price → no net direction
    buf = deque([
        _tick(0.30, ms(0)),
        _tick(0.40, ms(100)),
        _tick(0.30, ms(200)),   # net: start 0.30 == end 0.30, no direction despite spread
    ])
    result = detect_sweep(buf, min_fills=3, max_duration_s=0.5, min_spread_cents=3)
    assert result is None


def test_detect_sweep_with_three_fills():
    buf = deque([
        _tick(0.30, ms(0)),
        _tick(0.35, ms(100)),
        _tick(0.40, ms(200)),   # 3 fills, 200ms, spread=0.10
    ])
    result = detect_sweep(buf, min_fills=2, max_duration_s=0.5, min_spread_cents=3)
    assert result is not None
    assert result.side == "YES"
    assert abs(result.end_price - 0.40) < 1e-6


def test_detect_sweep_ignores_burst_outside_window():
    # First 2 ticks are 600ms apart (no valid sweep)
    # But ticks [1]+[2] are within 500ms with enough spread
    buf = deque([
        _tick(0.50, ms(0)),
        _tick(0.50, ms(600)),
        _tick(0.54, ms(900)),   # ticks[1]+ticks[2]: 300ms, spread=0.04, YES
    ])
    result = detect_sweep(buf, min_fills=2, max_duration_s=0.5, min_spread_cents=3)
    assert result is not None
    assert result.side == "YES"


# ── confirm_w1 ────────────────────────────────────────────────────────────────

def _sweep(side: str, end_price: float, end_ts: int) -> SweepResult:
    return SweepResult(side=side, end_price=end_price, end_ts=end_ts)


def test_confirm_w1_yes_sweep_confirmed():
    sweep = _sweep("YES", 0.40, ms(1000))
    # W1 window: 300ms–3000ms after sweep end
    buf = deque([
        _tick(0.40, ms(800)),   # before window - ignored
        _tick(0.41, ms(1500)),  # in window, above sweep end ✓
        _tick(0.42, ms(1800)),  # in window, above sweep end ✓
    ])
    result = confirm_w1(
        buf, sweep,
        window_start_s=0.3, window_end_s=3.0,
        min_trades=2, same_dir_pct=0.60,
    )
    assert result is True


def test_confirm_w1_no_sweep_confirmed():
    sweep = _sweep("NO", 0.60, ms(0))
    buf = deque([
        _tick(0.59, ms(500)),   # below sweep end ✓
        _tick(0.58, ms(800)),   # below sweep end ✓
    ])
    result = confirm_w1(
        buf, sweep,
        window_start_s=0.3, window_end_s=3.0,
        min_trades=2, same_dir_pct=0.60,
    )
    assert result is True


def test_confirm_w1_too_few_trades():
    sweep = _sweep("YES", 0.40, ms(0))
    buf = deque([
        _tick(0.42, ms(500)),   # only 1 trade in window
    ])
    result = confirm_w1(
        buf, sweep,
        window_start_s=0.3, window_end_s=3.0,
        min_trades=2, same_dir_pct=0.60,
    )
    assert result is False


def test_confirm_w1_majority_retreats():
    sweep = _sweep("YES", 0.40, ms(0))
    # 3 trades: 2 below sweep end price, 1 above → 1/3 = 33% < 60%
    buf = deque([
        _tick(0.38, ms(400)),   # below sweep end — retreating
        _tick(0.37, ms(600)),   # below sweep end — retreating
        _tick(0.41, ms(800)),   # above sweep end ✓
    ])
    result = confirm_w1(
        buf, sweep,
        window_start_s=0.3, window_end_s=3.0,
        min_trades=2, same_dir_pct=0.60,
    )
    assert result is False


def test_confirm_w1_no_price_continuation():
    sweep = _sweep("YES", 0.40, ms(0))
    # Trades at exactly sweep end price — not strictly above
    buf = deque([
        _tick(0.40, ms(400)),
        _tick(0.40, ms(600)),
    ])
    result = confirm_w1(
        buf, sweep,
        window_start_s=0.3, window_end_s=3.0,
        min_trades=2, same_dir_pct=0.60,
    )
    assert result is False


def test_confirm_w1_ignores_ticks_outside_window():
    sweep = _sweep("YES", 0.40, ms(0))
    buf = deque([
        _tick(0.45, ms(100)),   # before window start (0.3s)
        _tick(0.45, ms(3100)),  # after window end (3.0s)
    ])
    # No ticks in window → fewer than min_trades
    result = confirm_w1(
        buf, sweep,
        window_start_s=0.3, window_end_s=3.0,
        min_trades=2, same_dir_pct=0.60,
    )
    assert result is False


def test_confirm_w1_no_sweep_no_continuation():
    sweep = _sweep("NO", 0.60, ms(0))
    # All at sweep end price, none strictly below
    buf = deque([
        _tick(0.60, ms(400)),
        _tick(0.60, ms(600)),
    ])
    result = confirm_w1(
        buf, sweep,
        window_start_s=0.3, window_end_s=3.0,
        min_trades=2, same_dir_pct=0.60,
    )
    assert result is False
