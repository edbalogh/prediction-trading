from __future__ import annotations

import asyncio
import logging
from collections import deque
from datetime import datetime, timezone

from nautilus_trader.config import StrategyConfig
from nautilus_trader.model.data import TradeTick
from nautilus_trader.model.enums import OrderSide, PriceType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.objects import Quantity
from nautilus_trader.trading.strategy import Strategy

from adapters.kalshi.constants import KALSHI_VENUE
from adapters.kalshi.factories import kalshi_ticker_to_instrument_id, market_to_binary_option
from strategies.mlb_burst_signals import SweepResult, confirm_w1, detect_sweep

_logger = logging.getLogger(__name__)


class MLBBurstConfig(StrategyConfig, frozen=True):
    sweep_min_spread_cents: int = 3
    sweep_min_fills: int = 2
    sweep_max_duration_s: float = 0.5
    w1_window_start_s: float = 0.3
    w1_window_end_s: float = 3.0
    w1_min_trades: int = 2
    w1_same_dir_pct: float = 0.60
    bail_seconds: int = 45
    max_notional_usd: float = 1.00


def _parse_home_name(title: str) -> str:
    """Extract home team name from Kalshi market title 'Away vs Home Winner?'."""
    parts = title.split(" vs ", 1)
    if len(parts) != 2:
        return ""
    tail = parts[1]
    if " Winner?" not in tail and not tail.endswith("Winner?"):
        return ""
    return tail.replace(" Winner?", "").strip()


def _match_game_pk(home_name: str, mlb_games: list[dict]) -> int | None:
    """Match a Kalshi home team name to an MLB Stats gamePk.

    Tries three strategies in order:
    1. Exact match against home_city or full home_name
    2. City-prefix match with optional team abbreviation suffix (e.g. "New York M" → Mets)
    3. Name-prefix match: Kalshi name is a prefix of the full MLB team name
       (e.g. "San Diego" prefix of "San Diego Padres")
    """
    normalized = home_name.lower()
    for game in mlb_games:
        city = (game.get("home_city") or "").lower()
        name = (game.get("home_name") or "").lower()
        if normalized == city or normalized == name:
            return game["gamePk"]
        if city and normalized.startswith(city):
            suffix = normalized[len(city):].strip()
            if not suffix:
                return game["gamePk"]
            name_words = name.split()
            if name_words and name_words[-1].startswith(suffix):
                return game["gamePk"]
        # MLB Stats API sometimes returns empty city; fall back to name-prefix matching
        if name and name.startswith(normalized):
            return game["gamePk"]
    return None


def _compute_qty(entry_price: float, *, max_notional: float) -> int:
    """Return floor(max_notional / entry_price), minimum 1."""
    if entry_price <= 0:
        return 1
    return max(1, int(max_notional / entry_price))


class MLBBurstStrategy(Strategy):
    def __init__(
        self,
        config: MLBBurstConfig,
        *,
        kalshi_http,
        mlb_stats,
    ) -> None:
        super().__init__(config)
        self._kalshi_http = kalshi_http
        self._mlb_stats = mlb_stats
        self._ready: bool = False
        self._buffers: dict[str, deque[TradeTick]] = {}
        self._ticker_to_game_pk: dict[str, int] = {}
        self._pending_sweeps: dict[str, SweepResult] = {}
        self._entered_games: set[int] = set()
        self._position_qty: dict[str, int] = {}
        self._pending_tasks: dict[str, asyncio.Task] = {}
        self._filter_tasks: set[asyncio.Task] = set()

    def on_start(self) -> None:
        self._ready = False
        self._buffers.clear()
        self._ticker_to_game_pk.clear()
        self._pending_sweeps.clear()
        self._entered_games.clear()
        self._position_qty.clear()
        # Note: do NOT clear _pending_tasks here — if tasks are running, they need on_stop() first
        asyncio.ensure_future(self._discover_markets())

    async def _discover_markets(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            markets = await asyncio.to_thread(
                self._kalshi_http.list_markets_paged,
                series_ticker="KXMLBGAME",
                status="open",
            )
            mlb_games = await self._mlb_stats.async_get_schedule(today)
        except Exception:
            _logger.exception("market discovery failed")
            return

        for market in markets:
            ticker = market.get("ticker", "")
            title = market.get("title", "")
            yes_sub = (market.get("yes_sub_title") or "").strip()
            home_name = _parse_home_name(title)
            if not home_name:
                continue
            if yes_sub.lower() != home_name.lower():
                continue  # away team ticker — skip
            game_pk = _match_game_pk(home_name, mlb_games)
            if game_pk is None:
                _logger.warning("no gamePk match for %s (home: %s)", ticker, home_name)
                continue
            instrument = market_to_binary_option(market)
            self.cache.add_instrument(instrument)
            self._ticker_to_game_pk[ticker] = game_pk
            self._buffers[ticker] = deque()
            self.subscribe_trade_ticks(instrument.id)
            _logger.info("subscribed to %s (gamePk=%d)", ticker, game_pk)

        self._ready = True
        _logger.info(
            "market discovery complete: %d home markets", len(self._ticker_to_game_pk)
        )

    def on_trade_tick(self, tick: TradeTick) -> None:
        if not self._ready:
            return
        ticker = tick.instrument_id.symbol.value
        if ticker not in self._buffers:
            return

        buf = self._buffers[ticker]
        buf.append(tick)
        cutoff = tick.ts_event - 60_000_000_000
        while buf and buf[0].ts_event < cutoff:
            buf.popleft()

        if ticker in self._pending_sweeps:
            self._check_w1(tick, ticker, buf)
        else:
            sweep = detect_sweep(
                buf,
                min_fills=self.config.sweep_min_fills,
                max_duration_s=self.config.sweep_max_duration_s,
                min_spread_cents=self.config.sweep_min_spread_cents,
            )
            if sweep is not None:
                self._pending_sweeps[ticker] = sweep

    def _check_w1(self, tick: TradeTick, ticker: str, buf: deque[TradeTick]) -> None:
        sweep = self._pending_sweeps[ticker]
        w1_start_ns = sweep.end_ts + int(self.config.w1_window_start_s * 1_000_000_000)
        w1_end_ns = sweep.end_ts + int(self.config.w1_window_end_s * 1_000_000_000)
        now = tick.ts_event

        if now > w1_end_ns:
            del self._pending_sweeps[ticker]
            return

        if now < w1_start_ns:
            return

        if confirm_w1(
            buf,
            sweep,
            window_start_s=self.config.w1_window_start_s,
            window_end_s=self.config.w1_window_end_s,
            min_trades=self.config.w1_min_trades,
            same_dir_pct=self.config.w1_same_dir_pct,
        ):
            del self._pending_sweeps[ticker]
            entry_price = sweep.end_price
            cached = self.cache.price(tick.instrument_id, PriceType.LAST)
            if cached is not None:
                entry_price = cached.as_double()
            task = asyncio.ensure_future(
                self._check_filters_and_enter(tick.instrument_id, sweep, entry_price)
            )
            self._filter_tasks.add(task)
            task.add_done_callback(self._filter_tasks.discard)

    async def _check_filters_and_enter(
        self,
        instrument_id: InstrumentId,
        sweep: SweepResult,
        entry_price: float,
    ) -> None:
        ticker = instrument_id.symbol.value
        game_pk = self._ticker_to_game_pk.get(ticker)
        if game_pk is None:
            return

        # Reserve synchronously before yielding to avoid double-entry race
        if game_pk in self._entered_games:
            _logger.info("skip %s: already entered game %d", ticker, game_pk)
            return
        self._entered_games.add(game_pk)

        try:
            game_state = await self._mlb_stats.async_get_game_state(game_pk)
        except Exception:
            _logger.warning("MLB Stats call failed for %s — skip entry", ticker)
            self._entered_games.discard(game_pk)
            return

        if game_state.get("half", "").lower() != "bottom":
            _logger.info(
                "skip %s: not bottom half (half=%s)", ticker, game_state.get("half")
            )
            self._entered_games.discard(game_pk)
            return

        qty = _compute_qty(entry_price, max_notional=self.config.max_notional_usd)
        order = self.order_factory.market(
            instrument_id=instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(qty, 0),
        )
        self.submit_order(order)

        entry_ts = self.clock.timestamp_ns()
        self._position_qty[ticker] = qty
        task = asyncio.ensure_future(
            self._hold_or_bail(ticker, game_pk, sweep.end_ts, entry_ts)
        )
        self._pending_tasks[ticker] = task
        _logger.info(
            "ENTRY: %s side=%s qty=%d px=%.2f gamePk=%d",
            ticker, sweep.side, qty, entry_price, game_pk,
        )

    async def _hold_or_bail(
        self,
        ticker: str,
        game_pk: int,
        sweep_ts: int,
        entry_ts: int,
    ) -> None:
        try:
            await asyncio.sleep(self.config.bail_seconds)
            since_ns = sweep_ts - 5_000_000_000
            until_ns = entry_ts + self.config.bail_seconds * 1_000_000_000
            try:
                scoring = await self._mlb_stats.async_get_scoring_plays(
                    game_pk, since_ns, until_ns
                )
            except Exception:
                _logger.warning(
                    "MLB Stats failed at hold/bail check for %s — defaulting to bail",
                    ticker,
                )
                scoring = []

            if scoring:
                _logger.info(
                    "HOLD: scoring play confirmed for %s (gamePk=%d)", ticker, game_pk
                )
            else:
                _logger.info(
                    "BAIL: no scoring play for %s (gamePk=%d) — exiting", ticker, game_pk
                )
                qty = self._position_qty.get(ticker, 0)
                if qty > 0:
                    # Reconstruct InstrumentId from ticker since this method doesn't receive it directly
                    instrument_id = kalshi_ticker_to_instrument_id(ticker)
                    order = self.order_factory.market(
                        instrument_id=instrument_id,
                        order_side=OrderSide.SELL,
                        quantity=Quantity(qty, 0),
                    )
                    self.submit_order(order)
        finally:
            self._pending_tasks.pop(ticker, None)

    def on_stop(self) -> None:
        for task in list(self._filter_tasks):
            task.cancel()
        self._filter_tasks.clear()
        for task in list(self._pending_tasks.values()):
            task.cancel()
        self._pending_tasks.clear()
