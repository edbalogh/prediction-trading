from __future__ import annotations

import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import AggressorSide, OrderSide
from nautilus_trader.model.identifiers import InstrumentId, Symbol, TradeId, Venue
from nautilus_trader.model.objects import Price, Quantity

from strategies.mlb_burst import MLBBurstConfig, _parse_home_name, _match_game_pk

KALSHI = Venue("KALSHI")
import uuid


def _tick(ticker: str, price: float, ts_event: int) -> TradeTick:
    iid = InstrumentId(Symbol(ticker), KALSHI)
    return TradeTick(
        instrument_id=iid,
        price=Price(price, 2),
        size=Quantity(1, 0),
        aggressor_side=AggressorSide.BUYER,
        trade_id=TradeId(uuid.uuid4().hex[:8]),
        ts_event=ts_event,
        ts_init=ts_event,
    )


def ms(n: float) -> int:
    return int(n * 1_000_000)


# ── Configuration ──────────────────────────────────────────────────────────────

def test_config_defaults():
    cfg = MLBBurstConfig(strategy_id="test-001")
    assert cfg.sweep_min_spread_cents == 3
    assert cfg.sweep_min_fills == 2
    assert cfg.sweep_max_duration_s == 0.5
    assert cfg.w1_window_start_s == 0.3
    assert cfg.w1_window_end_s == 3.0
    assert cfg.w1_min_trades == 2
    assert cfg.w1_same_dir_pct == 0.60
    assert cfg.bail_seconds == 45
    assert cfg.max_notional_usd == 1.00


# ── Home name parsing ──────────────────────────────────────────────────────────

def test_parse_home_name_extracts_home():
    assert _parse_home_name("New York M vs Arizona Winner?") == "Arizona"


def test_parse_home_name_handles_missing_vs():
    assert _parse_home_name("No vs separator") == ""


def test_parse_home_name_with_short_title():
    assert _parse_home_name("NYM vs AZ Winner?") == "AZ"


# ── GamePk matching ────────────────────────────────────────────────────────────

MLB_GAMES = [
    {"gamePk": 111, "home_city": "Arizona", "home_name": "Arizona Diamondbacks"},
    {"gamePk": 222, "home_city": "New York", "home_name": "New York Mets"},
    {"gamePk": 333, "home_city": "San Francisco", "home_name": "San Francisco Giants"},
    {"gamePk": 444, "home_city": "Kansas City", "home_name": "Kansas City Royals"},
]


def test_match_game_pk_exact_city():
    assert _match_game_pk("Arizona", MLB_GAMES) == 111


def test_match_game_pk_city_prefix_with_suffix():
    # "New York M" → city="New York" prefix, suffix="m", last word "mets" starts with "m"
    assert _match_game_pk("New York M", MLB_GAMES) == 222


def test_match_game_pk_city_prefix_no_suffix():
    assert _match_game_pk("San Francisco", MLB_GAMES) == 333


def test_match_game_pk_returns_none_for_unknown():
    assert _match_game_pk("Boston", MLB_GAMES) is None


def test_match_game_pk_case_insensitive():
    assert _match_game_pk("arizona", MLB_GAMES) == 111


def test_match_game_pk_kansas_city():
    assert _match_game_pk("Kansas City", MLB_GAMES) == 444


# ── Sizing ─────────────────────────────────────────────────────────────────────

def test_sizing_at_high_price():
    # floor(1.00 / 0.80) = 1
    from strategies.mlb_burst import _compute_qty
    assert _compute_qty(0.80, max_notional=1.00) == 1


def test_sizing_at_low_price():
    # floor(1.00 / 0.20) = 5
    from strategies.mlb_burst import _compute_qty
    assert _compute_qty(0.20, max_notional=1.00) == 5


def test_sizing_minimum_one():
    # floor(1.00 / 0.99) = 1
    from strategies.mlb_burst import _compute_qty
    assert _compute_qty(0.99, max_notional=1.00) == 1


def test_sizing_rounds_down():
    # floor(1.00 / 0.33) = 3
    from strategies.mlb_burst import _compute_qty
    assert _compute_qty(0.33, max_notional=1.00) == 3


# ── Strategy tick buffer and signal dispatch ───────────────────────────────────

def _make_strategy():
    """Return an MLBBurstStrategy with mocked dependencies, ready for unit testing."""
    from strategies.mlb_burst import MLBBurstConfig, MLBBurstStrategy

    cfg = MLBBurstConfig(strategy_id="test-001")
    kalshi_http = MagicMock()
    mlb_stats = MagicMock()
    mlb_stats.async_get_game_state = AsyncMock(
        return_value={"half": "bottom", "inning": 3, "status": "Live"}
    )
    mlb_stats.async_get_scoring_plays = AsyncMock(return_value=[])

    strat = MLBBurstStrategy(cfg, kalshi_http=kalshi_http, mlb_stats=mlb_stats)

    # Prime internal state as if discovery completed
    ticker = "KXMLBGAME-26MAY01-AZ"
    strat._buffers[ticker] = deque()
    strat._ticker_to_game_pk[ticker] = 12345
    strat._ready = True

    strat.submit_order = MagicMock()

    # Mock cache so _check_w1 doesn't blow up.
    # NautilusTrader Cython getset_descriptor properties shadow __dict__ entries,
    # so we patch at the class level temporarily via a Python property.
    mock_cache = MagicMock()
    mock_cache.price.return_value = None
    strat.__dict__["_mock_cache"] = mock_cache
    MLBBurstStrategy.cache = property(lambda self: self.__dict__["_mock_cache"])  # type: ignore[assignment]

    # Mock clock so _check_filters_and_enter doesn't blow up
    mock_clock = MagicMock()
    mock_clock.timestamp_ns.return_value = 999_000_000_000
    strat.__dict__["_mock_clock"] = mock_clock
    MLBBurstStrategy.clock = property(lambda self: self.__dict__["_mock_clock"])  # type: ignore[assignment]

    # Mock order_factory so _hold_or_bail can create orders
    mock_order = MagicMock()
    mock_order.order_side = OrderSide.SELL
    mock_order_factory = MagicMock()
    mock_order_factory.market.return_value = mock_order
    strat.__dict__["_mock_order_factory"] = mock_order_factory
    MLBBurstStrategy.order_factory = property(lambda self: self.__dict__["_mock_order_factory"])  # type: ignore[assignment]

    return strat, ticker


def test_tick_buffer_prunes_old_entries():
    strat, ticker = _make_strategy()
    buf = strat._buffers[ticker]
    # Add old tick (70s ago in ns)
    old_ts = ms(0)
    recent_ts = old_ts + 70_000_000_000  # 70 seconds later
    buf.append(_tick(ticker, 0.40, old_ts))
    buf.append(_tick(ticker, 0.40, recent_ts))

    # Feed a new tick — should prune the old one
    new_tick = _tick(ticker, 0.40, recent_ts + 1_000_000)
    strat.on_trade_tick(new_tick)

    # Old tick (old_ts=0) should be pruned; buffer should contain recent_ts tick + new_tick
    assert len(buf) >= 2
    assert buf[0].ts_event == recent_ts


def test_sweep_detected_stores_pending_sweep():
    strat, ticker = _make_strategy()
    buf = strat._buffers[ticker]

    # Seed buffer with a sweep: 2 fills, 200ms, 4-cent spread, YES direction
    buf.append(_tick(ticker, 0.30, ms(0)))
    buf.append(_tick(ticker, 0.34, ms(200)))

    # Next tick triggers sweep detection (no pending sweep yet)
    strat.on_trade_tick(_tick(ticker, 0.34, ms(300)))

    assert ticker in strat._pending_sweeps
    sweep = strat._pending_sweeps[ticker]
    assert sweep.side == "YES"


def test_w1_window_expiry_clears_pending_sweep():
    strat, ticker = _make_strategy()
    buf = strat._buffers[ticker]

    sweep_end_ts = ms(1000)
    from strategies.mlb_burst.mlb_burst_signals import SweepResult
    strat._pending_sweeps[ticker] = SweepResult(
        side="YES", end_price=0.40, end_ts=sweep_end_ts
    )
    buf.append(_tick(ticker, 0.40, sweep_end_ts))

    # Tick arrives after window end (3.1 seconds after sweep)
    late_tick = _tick(ticker, 0.40, sweep_end_ts + ms(3100))
    strat.on_trade_tick(late_tick)

    assert ticker not in strat._pending_sweeps


@pytest.mark.asyncio
async def test_w1_confirms_and_clears_pending_sweep():
    strat, ticker = _make_strategy()
    buf = strat._buffers[ticker]

    sweep_end_ts = ms(0)
    sweep_end_price = 0.40
    from strategies.mlb_burst.mlb_burst_signals import SweepResult
    strat._pending_sweeps[ticker] = SweepResult(
        side="YES", end_price=sweep_end_price, end_ts=sweep_end_ts
    )

    # Add W1 ticks: 2 ticks in window [300ms, 3000ms], both above sweep end price
    buf.append(_tick(ticker, 0.41, ms(400)))
    buf.append(_tick(ticker, 0.42, ms(600)))

    # Trigger on_trade_tick in W1 window
    w1_tick = _tick(ticker, 0.42, ms(700))
    strat.on_trade_tick(w1_tick)

    # Give create_task a chance to execute
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert ticker not in strat._pending_sweeps


@pytest.mark.asyncio
async def test_skips_entry_when_already_entered_game():
    strat, ticker = _make_strategy()
    buf = strat._buffers[ticker]

    strat._entered_games.add(12345)  # game already entered

    sweep_end_ts = ms(0)
    from strategies.mlb_burst.mlb_burst_signals import SweepResult
    strat._pending_sweeps[ticker] = SweepResult(
        side="YES", end_price=0.40, end_ts=sweep_end_ts
    )
    buf.append(_tick(ticker, 0.41, ms(400)))
    buf.append(_tick(ticker, 0.42, ms(600)))

    strat.on_trade_tick(_tick(ticker, 0.42, ms(700)))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    strat.submit_order.assert_not_called()


@pytest.mark.asyncio
async def test_skips_entry_when_mlb_stats_game_state_fails():
    strat, ticker = _make_strategy()
    buf = strat._buffers[ticker]
    strat._mlb_stats.async_get_game_state = AsyncMock(
        side_effect=RuntimeError("connection timeout")
    )

    from strategies.mlb_burst.mlb_burst_signals import SweepResult
    strat._pending_sweeps[ticker] = SweepResult(
        side="YES", end_price=0.40, end_ts=ms(0)
    )
    buf.append(_tick(ticker, 0.41, ms(400)))
    buf.append(_tick(ticker, 0.42, ms(600)))

    strat.on_trade_tick(_tick(ticker, 0.42, ms(700)))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    strat.submit_order.assert_not_called()
    # game_pk should NOT be in entered_games (entry slot released on failure)
    assert 12345 not in strat._entered_games


@pytest.mark.asyncio
async def test_skips_entry_when_top_half():
    strat, ticker = _make_strategy()
    buf = strat._buffers[ticker]
    strat._mlb_stats.async_get_game_state = AsyncMock(
        return_value={"half": "top", "inning": 3, "status": "Live"}
    )

    from strategies.mlb_burst.mlb_burst_signals import SweepResult
    strat._pending_sweeps[ticker] = SweepResult(
        side="YES", end_price=0.40, end_ts=ms(0)
    )
    buf.append(_tick(ticker, 0.41, ms(400)))
    buf.append(_tick(ticker, 0.42, ms(600)))

    strat.on_trade_tick(_tick(ticker, 0.42, ms(700)))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    strat.submit_order.assert_not_called()
    assert 12345 not in strat._entered_games


# ── Hold/bail coroutine ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hold_or_bail_sells_when_no_scoring_play():
    strat, ticker = _make_strategy()
    strat._mlb_stats.async_get_scoring_plays = AsyncMock(return_value=[])
    strat._position_qty[ticker] = 2

    submitted = []
    strat.submit_order = lambda o: submitted.append(o)

    # Patch asyncio.sleep to avoid 45s wait
    import strategies.mlb_burst.mlb_burst as burst_mod
    original_sleep = asyncio.sleep

    async def fast_sleep(n):
        await original_sleep(0)

    burst_mod.asyncio.sleep = fast_sleep
    try:
        await strat._hold_or_bail(ticker, 12345, sweep_ts=0, entry_ts=1_000_000_000)
    finally:
        burst_mod.asyncio.sleep = original_sleep

    assert len(submitted) == 1
    assert submitted[0].order_side == OrderSide.SELL


@pytest.mark.asyncio
async def test_hold_or_bail_holds_when_scoring_play_found():
    strat, ticker = _make_strategy()
    strat._mlb_stats.async_get_scoring_plays = AsyncMock(
        return_value=[{"result": {"event": "Home Run"}}]
    )
    strat._position_qty[ticker] = 2

    submitted = []
    strat.submit_order = lambda o: submitted.append(o)

    import strategies.mlb_burst.mlb_burst as burst_mod
    original_sleep = asyncio.sleep

    async def fast_sleep(n):
        await original_sleep(0)

    burst_mod.asyncio.sleep = fast_sleep
    try:
        await strat._hold_or_bail(ticker, 12345, sweep_ts=0, entry_ts=1_000_000_000)
    finally:
        burst_mod.asyncio.sleep = original_sleep

    assert len(submitted) == 0  # held, no sell submitted


@pytest.mark.asyncio
async def test_hold_or_bail_bails_on_mlb_stats_exception():
    strat, ticker = _make_strategy()
    strat._mlb_stats.async_get_scoring_plays = AsyncMock(
        side_effect=RuntimeError("timeout")
    )
    strat._position_qty[ticker] = 1

    submitted = []
    strat.submit_order = lambda o: submitted.append(o)

    import strategies.mlb_burst.mlb_burst as burst_mod
    original_sleep = asyncio.sleep

    async def fast_sleep(n):
        await original_sleep(0)

    burst_mod.asyncio.sleep = fast_sleep
    try:
        await strat._hold_or_bail(ticker, 12345, sweep_ts=0, entry_ts=0)
    finally:
        burst_mod.asyncio.sleep = original_sleep

    assert len(submitted) == 1
    assert submitted[0].order_side == OrderSide.SELL
