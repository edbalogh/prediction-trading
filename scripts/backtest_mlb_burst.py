#!/usr/bin/env python3
"""
MLB Burst Strategy Backtest — full signal replay on historical KXMLBGAME data.

Replays all KXMLBGAME home-team tickers using the exact sweep + W1 signal detection
from strategies/mlb_burst_signals.py. Applies the bottom-half filter by fetching
historical play-by-play from the MLB Stats API to determine the game state at each
signal timestamp.

For each confirmed, filtered signal simulates two scenarios:
  - Bail-always  : exit 45 seconds after entry at market price
  - Hold-always  : hold to settlement (YES=1.00, NO=0.00)

Usage:
    python3 backtest_mlb_burst.py

Output:
    /tmp/backtest_mlb_burst.html
"""
from __future__ import annotations

import os
import sys
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────

INGESTION_DIR    = "/Users/edbalogh/Trading/Ingestion/data"
SERIES           = "KXMLBGAME"
OUTPUT_HTML      = "/tmp/backtest_mlb_burst.html"
STARTING_CAPITAL = 10_000.0

# Strategy parameters (defaults from MLBBurstConfig)
SWEEP_MIN_FILLS        = 2
SWEEP_MAX_DURATION_S   = 0.5
SWEEP_MIN_SPREAD_CENTS = 3
W1_WINDOW_START_S      = 0.3
W1_WINDOW_END_S        = 3.0
W1_MIN_TRADES          = 2
W1_SAME_DIR_PCT        = 0.60
BAIL_SECONDS           = 45
MAX_NOTIONAL_USD       = 1.00

# Date range — everything up to yesterday (skip today which is live-trading)
START_DATE = "2026-03-25"
END_DATE   = "2026-05-06"

# MLB Stats fetch concurrency
MLB_FETCH_WORKERS = 20

# Map Kalshi team codes → prefix that matches MLB Stats home_name via _match_game_pk
TEAM_CODE_TO_NAME: dict[str, str] = {
    "ATH": "Athletics",
    "ATL": "Atlanta",
    "AZ":  "Arizona",
    "BAL": "Baltimore",
    "BOS": "Boston",
    "CHC": "Chicago C",   # Chicago Cubs (vs White Sox)
    "CIN": "Cincinnati",
    "CLE": "Cleveland",
    "COL": "Colorado",
    "CWS": "Chicago W",   # Chicago White Sox
    "DET": "Detroit",
    "HOU": "Houston",
    "KC":  "Kansas City",
    "LAA": "Los Angeles A",
    "LAD": "Los Angeles D",
    "MIA": "Miami",
    "MIL": "Milwaukee",
    "MIN": "Minnesota",
    "NYM": "New York M",
    "NYY": "New York Y",
    "PHI": "Philadelphia",
    "PIT": "Pittsburgh",
    "SD":  "San Diego",
    "SEA": "Seattle",
    "SF":  "San Francisco",
    "STL": "St. Louis",
    "TB":  "Tampa Bay",
    "TEX": "Texas",
    "TOR": "Toronto",
    "WSH": "Washington",
}

_MONTH = {"JAN":"01","FEB":"02","MAR":"03","APR":"04","MAY":"05","JUN":"06",
          "JUL":"07","AUG":"08","SEP":"09","OCT":"10","NOV":"11","DEC":"12"}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _date_range(start: str, end: str) -> list[str]:
    return [d.strftime("%Y-%m-%d") for d in pd.date_range(start, end, freq="D")]


def is_home_ticker(ticker: str) -> bool:
    parts = ticker.split("-")
    return len(parts) >= 3 and parts[-2].endswith(parts[-1])


def parse_ticker_date(ticker: str) -> str | None:
    """'KXMLBGAME-26APR051920STLDET-DET' → '2026-04-05'"""
    parts = ticker.split("-")
    if len(parts) < 3:
        return None
    body = parts[1]          # '26APR051920STLDET'
    year = "20" + body[:2]   # '2026'
    mon  = _MONTH.get(body[2:5])
    if not mon:
        return None
    day  = body[5:7]
    return f"{year}-{mon}-{day}"


def parse_home_team_code(ticker: str) -> str | None:
    parts = ticker.split("-")
    return parts[-1] if len(parts) >= 3 else None


def compute_qty(price: float) -> int:
    return max(1, int(MAX_NOTIONAL_USD / price)) if price > 0 else 1


# Lightweight tick stand-in — avoids constructing NautilusTrader Cython objects
# for millions of rows while still satisfying detect_sweep / confirm_w1 duck-typing.
class _Price:
    __slots__ = ("_v",)
    def __init__(self, v: float): self._v = v
    def as_double(self) -> float: return self._v

class _Tick:
    __slots__ = ("ts_event", "price")
    def __init__(self, ts_ns: int, price: float):
        self.ts_event = ts_ns
        self.price    = _Price(price)


# ── Load trade data ────────────────────────────────────────────────────────────

DATES        = _date_range(START_DATE, END_DATE)
MARKET_DATES = _date_range(START_DATE, "2026-05-09")

print(f"Loading KXMLBGAME trade data from {START_DATE} to {END_DATE}...")
t0 = time.time()

trade_frames = []
for date in DATES:
    path = f"{INGESTION_DIR}/trades/series={SERIES}/date={date}/part.parquet"
    if os.path.exists(path):
        df = pd.read_parquet(path, columns=["ticker", "yes_price_dollars", "created_time"])
        trade_frames.append(df)

if not trade_frames:
    print("No trade data found — check INGESTION_DIR")
    sys.exit(1)

all_trades = pd.concat(trade_frames, ignore_index=True)
all_trades["ts_ns"] = (
    pd.to_datetime(all_trades["created_time"], utc=True, format="ISO8601").astype("int64")
)
all_trades = all_trades.drop(columns=["created_time"])
all_trades = all_trades[all_trades["ticker"].apply(is_home_ticker)].copy()
all_trades = all_trades.sort_values(["ticker", "ts_ns"]).reset_index(drop=True)

print(
    f"  {len(all_trades):,} home-ticker trades, "
    f"{all_trades['ticker'].nunique()} tickers in {time.time()-t0:.1f}s"
)

# ── Load settlements ───────────────────────────────────────────────────────────

print("Loading settlement data...")
settlement_map: dict[str, str] = {}
for date in MARKET_DATES:
    path = f"{INGESTION_DIR}/markets/series={SERIES}/date={date}/part.parquet"
    if not os.path.exists(path):
        continue
    df = pd.read_parquet(path, columns=["ticker", "result"])
    for _, row in df[df["result"].isin(["yes", "no"])].iterrows():
        if row["ticker"] not in settlement_map:
            settlement_map[row["ticker"]] = row["result"]

print(f"  {len(settlement_map)} settlement results loaded")

# ── Build ticker → gamePk mapping via MLB Stats ────────────────────────────────

print("Fetching MLB Stats schedules to map tickers → gamePks...")
from adapters.mlb_stats.client import MLBStatsClient
from strategies.mlb_burst import _match_game_pk

mlb = MLBStatsClient()
_schedule_cache: dict[str, list[dict]] = {}

def _get_schedule(date: str) -> list[dict]:
    if date not in _schedule_cache:
        try:
            _schedule_cache[date] = mlb.get_schedule(date)
        except Exception:
            _schedule_cache[date] = []
    return _schedule_cache[date]

unique_tickers = all_trades["ticker"].unique()
ticker_to_game_pk: dict[str, int] = {}

for ticker in unique_tickers:
    date      = parse_ticker_date(ticker)
    team_code = parse_home_team_code(ticker)
    if not date or not team_code:
        continue
    search_name = TEAM_CODE_TO_NAME.get(team_code)
    if not search_name:
        continue
    schedule = _get_schedule(date)
    game_pk  = _match_game_pk(search_name, schedule)
    if game_pk is not None:
        ticker_to_game_pk[ticker] = game_pk

matched = len(ticker_to_game_pk)
print(f"  Matched {matched}/{len(unique_tickers)} tickers to gamePks")

# ── Parallel-fetch play-by-play timelines ──────────────────────────────────────

print(f"Fetching play-by-play for {len(set(ticker_to_game_pk.values()))} games "
      f"(up to {MLB_FETCH_WORKERS} concurrent)...")
t1 = time.time()

# game_pk → sorted list of (ts_ns, half_inning)
game_timelines: dict[int, list[tuple[int, str]]] = {}

def _fetch_timeline(game_pk: int) -> tuple[int, list[tuple[int, str]]]:
    """Fetch feed/live and extract (ts_ns, halfInning) for each play."""
    try:
        resp = mlb._session.get(f"/api/v1.1/game/{game_pk}/feed/live")
        resp.raise_for_status()
        data  = resp.json()
        plays = data.get("liveData", {}).get("plays", {}).get("allPlays", [])
        timeline: list[tuple[int, str]] = []
        for play in plays:
            about    = play.get("about", {})
            end_time = about.get("endTime", "")
            half     = about.get("halfInning", "")
            if not end_time or not half:
                continue
            dt     = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            ts_ns  = int(dt.timestamp()) * 1_000_000_000 + dt.microsecond * 1_000
            timeline.append((ts_ns, half))
        return game_pk, sorted(timeline)
    except Exception:
        return game_pk, []

unique_game_pks = list(set(ticker_to_game_pk.values()))
with ThreadPoolExecutor(max_workers=MLB_FETCH_WORKERS) as pool:
    futures = {pool.submit(_fetch_timeline, pk): pk for pk in unique_game_pks}
    for fut in as_completed(futures):
        pk, tl = fut.result()
        game_timelines[pk] = tl

non_empty = sum(1 for tl in game_timelines.values() if tl)
print(f"  {non_empty}/{len(unique_game_pks)} games have play data in {time.time()-t1:.1f}s")


def _half_inning_at(game_pk: int, ts_ns: int) -> str | None:
    """
    Return halfInning ('top'/'bottom') of the last completed play before ts_ns,
    or None if no plays precede the signal (pre-game) or game has no data.
    """
    timeline = game_timelines.get(game_pk, [])
    result = None
    for play_ts, half in timeline:
        if play_ts <= ts_ns:
            result = half
        else:
            break
    return result

# ── Signal replay with bottom-half filter ──────────────────────────────────────

from strategies.mlb_burst.mlb_burst_signals import detect_sweep, confirm_w1, SweepResult

print("Replaying signals (bottom-half filter applied)...")
t2 = time.time()

all_signals:    list[dict] = []
skipped_top:    int = 0
skipped_nogame: int = 0

for ticker in unique_tickers:
    tdf = all_trades[all_trades["ticker"] == ticker]
    if tdf.empty:
        continue

    game_pk = ticker_to_game_pk.get(ticker)

    buf: deque[_Tick]       = deque()
    pending_sweep: SweepResult | None = None

    rows = list(tdf.itertuples(index=False))

    for i, row in enumerate(rows):
        tick = _Tick(int(row.ts_ns), float(row.yes_price_dollars))

        buf.append(tick)
        cutoff = tick.ts_event - 60_000_000_000
        while buf and buf[0].ts_event < cutoff:
            buf.popleft()

        if pending_sweep is not None:
            w1_start_ns = pending_sweep.end_ts + int(W1_WINDOW_START_S * 1_000_000_000)
            w1_end_ns   = pending_sweep.end_ts + int(W1_WINDOW_END_S   * 1_000_000_000)
            now = tick.ts_event

            if now > w1_end_ns:
                pending_sweep = None
            elif now >= w1_start_ns:
                if confirm_w1(
                    buf, pending_sweep,
                    window_start_s=W1_WINDOW_START_S,
                    window_end_s=W1_WINDOW_END_S,
                    min_trades=W1_MIN_TRADES,
                    same_dir_pct=W1_SAME_DIR_PCT,
                ):
                    # ── Bottom-half filter ──────────────────────────────────
                    if game_pk is None:
                        skipped_nogame += 1
                        pending_sweep = None
                        continue
                    half = _half_inning_at(game_pk, tick.ts_event)
                    if half != "bottom":
                        skipped_top += 1
                        pending_sweep = None
                        continue
                    # ───────────────────────────────────────────────────────

                    entry_price = tick.price.as_double()
                    entry_ts_ns = tick.ts_event

                    bail_target_ns = entry_ts_ns + BAIL_SECONDS * 1_000_000_000
                    bail_price = entry_price
                    for fr in rows[i + 1:]:
                        if int(fr.ts_ns) >= bail_target_ns:
                            bail_price = float(fr.yes_price_dollars)
                            break
                    else:
                        if rows[i + 1:]:
                            bail_price = float(rows[-1].yes_price_dollars)

                    qty      = compute_qty(entry_price)
                    bail_pnl = (bail_price - entry_price) * qty

                    result       = settlement_map.get(ticker)
                    settle_price = (1.00 if result == "yes" else 0.00) if result else None
                    settle_pnl   = (
                        round((settle_price - entry_price) * qty, 4)
                        if settle_price is not None else None
                    )

                    all_signals.append({
                        "ticker":       ticker,
                        "entry_dt":     datetime.fromtimestamp(entry_ts_ns / 1e9, tz=timezone.utc),
                        "entry_price":  round(entry_price, 2),
                        "sweep_side":   pending_sweep.side,
                        "qty":          qty,
                        "bail_price":   round(bail_price, 2),
                        "bail_pnl":     round(bail_pnl, 4),
                        "settlement":   result,
                        "settle_price": settle_price,
                        "settle_pnl":   settle_pnl,
                    })
                    pending_sweep = None
        else:
            sweep = detect_sweep(
                buf,
                min_fills=SWEEP_MIN_FILLS,
                max_duration_s=SWEEP_MAX_DURATION_S,
                min_spread_cents=SWEEP_MIN_SPREAD_CENTS,
            )
            if sweep is not None:
                pending_sweep = sweep

print(
    f"  {len(all_signals)} bottom-half signals "
    f"({skipped_top} top-half skipped, {skipped_nogame} no-game skipped) "
    f"in {time.time()-t2:.1f}s"
)
mlb.close()

if not all_signals:
    print("No signals passed the bottom-half filter — check data or config.")
    sys.exit(1)

# ── Compute summary stats ──────────────────────────────────────────────────────

df = pd.DataFrame(all_signals)
df["entry_dt"]   = pd.to_datetime(df["entry_dt"], utc=True)
df["entry_date"] = df["entry_dt"].dt.date
df["entry_hour"] = df["entry_dt"].dt.hour

settled = df[df["settle_pnl"].notna()].copy()

bail_total_pnl = df["bail_pnl"].sum()
hold_total_pnl = settled["settle_pnl"].sum() if not settled.empty else 0.0
bail_win_rate  = (df["bail_pnl"] > 0).mean() * 100
hold_win_rate  = ((settled["settle_pnl"] > 0).mean() * 100) if not settled.empty else 0.0
n_trades       = len(df)
n_yes_sweeps   = (df["sweep_side"] == "YES").sum()
n_no_sweeps    = (df["sweep_side"] == "NO").sum()
n_settled      = len(settled)

df_sorted = df.sort_values("entry_dt").reset_index(drop=True)
df_sorted["cum_bail_pnl"]   = df_sorted["bail_pnl"].cumsum()
df_sorted["cum_bail_equity"] = STARTING_CAPITAL + df_sorted["cum_bail_pnl"]

settled_sorted = settled.sort_values("entry_dt").reset_index(drop=True)
settled_sorted["cum_hold_pnl"]   = settled_sorted["settle_pnl"].cumsum()
settled_sorted["cum_hold_equity"] = STARTING_CAPITAL + settled_sorted["cum_hold_pnl"]

daily_counts  = df.groupby("entry_date").size().reset_index(name="count")
daily_counts["entry_date"] = daily_counts["entry_date"].astype(str)
hourly_counts = df.groupby("entry_hour").size().reset_index(name="count")

best_bail  = df.loc[df["bail_pnl"].idxmax()]
worst_bail = df.loc[df["bail_pnl"].idxmin()]

# ── Build HTML report ──────────────────────────────────────────────────────────

import plotly.graph_objects as go
import plotly.io as pio

_plotlyjs_included = False

def _fig_to_div(fig) -> str:
    global _plotlyjs_included
    if not _plotlyjs_included:
        _plotlyjs_included = True
        return pio.to_html(fig, full_html=False, include_plotlyjs=True)
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


# Equity curves
fig_equity = go.Figure()
fig_equity.add_trace(go.Scatter(
    x=df_sorted["entry_dt"].dt.strftime("%Y-%m-%d %H:%M"),
    y=df_sorted["cum_bail_equity"],
    mode="lines", name="Bail-always (exit t+45s)",
    line=dict(color="#2196F3", width=2),
))
if not settled_sorted.empty:
    fig_equity.add_trace(go.Scatter(
        x=settled_sorted["entry_dt"].dt.strftime("%Y-%m-%d %H:%M"),
        y=settled_sorted["cum_hold_equity"],
        mode="lines", name="Hold-to-settlement",
        line=dict(color="#4CAF50", width=2),
    ))
fig_equity.add_hline(y=STARTING_CAPITAL, line_dash="dash",
                     line_color="#888", annotation_text="Starting capital")
fig_equity.update_layout(
    title="Cumulative Equity — Bail-always vs Hold-to-settlement",
    xaxis_title="Signal time (UTC)", yaxis_title="Account balance ($)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=400, margin=dict(l=60, r=20, t=80, b=60), plot_bgcolor="#fafafa",
)
equity_div = _fig_to_div(fig_equity)

# Daily signal count
fig_daily = go.Figure(go.Bar(
    x=daily_counts["entry_date"], y=daily_counts["count"],
    marker_color="#7E57C2",
))
fig_daily.update_layout(
    title="Signals per Day (bottom half only)",
    xaxis_title="Date", yaxis_title="Signal count",
    height=300, margin=dict(l=60, r=20, t=60, b=80), plot_bgcolor="#fafafa",
)
daily_div = _fig_to_div(fig_daily)

# Hourly distribution
fig_hourly = go.Figure(go.Bar(
    x=hourly_counts["entry_hour"], y=hourly_counts["count"],
    marker_color="#FF7043",
))
fig_hourly.update_layout(
    title="Signal Count by Hour of Day (UTC)",
    xaxis_title="Hour (UTC)", yaxis_title="Signal count",
    height=300, margin=dict(l=60, r=20, t=60, b=60), plot_bgcolor="#fafafa",
    xaxis=dict(tickmode="linear", dtick=1),
)
hourly_div = _fig_to_div(fig_hourly)

# P&L distribution
fig_pnl = go.Figure()
fig_pnl.add_trace(go.Histogram(
    x=df["bail_pnl"], nbinsx=40, name="Bail P&L",
    marker_color="#2196F3", opacity=0.7,
))
if not settled.empty:
    fig_pnl.add_trace(go.Histogram(
        x=settled["settle_pnl"], nbinsx=40, name="Hold P&L",
        marker_color="#4CAF50", opacity=0.7,
    ))
fig_pnl.update_layout(
    title="P&L Distribution per Trade",
    barmode="overlay", xaxis_title="P&L ($)", yaxis_title="Count",
    height=300, margin=dict(l=60, r=20, t=60, b=60),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    plot_bgcolor="#fafafa",
)
pnl_dist_div = _fig_to_div(fig_pnl)

# Trade table
table_rows = []
for _, row in df_sorted.iterrows():
    bail_cls = "pos" if row["bail_pnl"] > 0 else ("neg" if row["bail_pnl"] < 0 else "")
    hold_cls, hold_str = "", "—"
    if row["settle_pnl"] is not None:
        hold_cls = "pos" if row["settle_pnl"] > 0 else ("neg" if row["settle_pnl"] < 0 else "")
        hold_str = f"${row['settle_pnl']:+.2f}"
    table_rows.append(
        f"<tr>"
        f"<td>{row['entry_dt'].strftime('%m/%d %H:%M')}</td>"
        f"<td class='ticker'>{row['ticker']}</td>"
        f"<td class='side-{'yes' if row['sweep_side'] == 'YES' else 'no'}'>{row['sweep_side']}</td>"
        f"<td>{row['entry_price']:.2f}</td>"
        f"<td>{row['qty']}</td>"
        f"<td>{row['bail_price']:.2f}</td>"
        f"<td class='{bail_cls}'>${row['bail_pnl']:+.2f}</td>"
        f"<td>{row['settlement'] or '—'}</td>"
        f"<td class='{hold_cls}'>{hold_str}</td>"
        f"</tr>"
    )
table_html = "\n".join(table_rows)


def stat_card(label: str, value: str, sub: str = "", color: str = "#333") -> str:
    return (
        f'<div class="card">'
        f'<div class="card-label">{label}</div>'
        f'<div class="card-value" style="color:{color}">{value}</div>'
        f'<div class="card-sub">{sub}</div>'
        f'</div>'
    )

bail_color = "#2E7D32" if bail_total_pnl >= 0 else "#C62828"
hold_color = "#2E7D32" if hold_total_pnl >= 0 else "#C62828"

cards_html = "".join([
    stat_card("Total Signals", f"{n_trades:,}",
              f"bottom-half only · {START_DATE} → {END_DATE}"),
    stat_card("YES Sweeps", f"{n_yes_sweeps:,}", f"NO: {n_no_sweeps:,}"),
    stat_card("Bail P&L", f"${bail_total_pnl:+,.2f}",
              f"win rate {bail_win_rate:.0f}% ({n_trades} trades)", bail_color),
    stat_card("Hold P&L", f"${hold_total_pnl:+,.2f}",
              f"win rate {hold_win_rate:.0f}% ({n_settled} settled)", hold_color),
    stat_card("Avg Bail / trade", f"${bail_total_pnl/n_trades:+.3f}",
              f"best ${best_bail['bail_pnl']:+.2f} / worst ${worst_bail['bail_pnl']:+.2f}"),
    stat_card("Filtered out", f"{skipped_top + skipped_nogame:,}",
              f"top-half: {skipped_top} · no-game: {skipped_nogame}"),
])

import plotly
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MLB Burst Backtest</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          background: #f0f2f5; margin: 0; padding: 20px; color: #222; }}
  h1   {{ font-size: 22px; margin: 0 0 4px; }}
  .subtitle {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }}
  .card {{ background: #fff; border-radius: 8px; padding: 14px 20px; min-width: 160px;
            box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
  .card-label {{ font-size: 11px; text-transform: uppercase; color: #888; letter-spacing: .5px; }}
  .card-value {{ font-size: 26px; font-weight: 700; margin: 4px 0; }}
  .card-sub   {{ font-size: 11px; color: #aaa; }}
  .section    {{ background: #fff; border-radius: 8px; padding: 16px;
                 box-shadow: 0 1px 4px rgba(0,0,0,.1); margin-bottom: 20px; }}
  .charts-row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  .charts-row .section {{ flex: 1; min-width: 300px; }}
  table    {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
  th, td   {{ padding: 5px 8px; text-align: left; border-bottom: 1px solid #eee; }}
  th       {{ background: #f5f5f5; font-weight: 600; position: sticky; top: 0; }}
  .ticker  {{ font-family: monospace; font-size: 11px; }}
  .pos     {{ color: #2E7D32; font-weight: 600; }}
  .neg     {{ color: #C62828; font-weight: 600; }}
  .side-yes {{ color: #1565C0; font-weight: 600; }}
  .side-no  {{ color: #E65100; font-weight: 600; }}
  .table-wrap {{ max-height: 500px; overflow-y: auto; }}
</style>
</head>
<body>
<h1>MLB Burst Strategy — Full Backtest</h1>
<div class="subtitle">
  KXMLBGAME home-team tickers &nbsp;·&nbsp; bottom-half filter applied via MLB Stats API
  &nbsp;·&nbsp; {START_DATE} through {END_DATE}
  &nbsp;·&nbsp; Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
</div>

<div class="cards">
{cards_html}
</div>

<div class="section">
{equity_div}
</div>

<div class="charts-row">
  <div class="section">{daily_div}</div>
  <div class="section">{hourly_div}</div>
</div>

<div class="section">
{pnl_dist_div}
</div>

<div class="section">
  <h3 style="margin:0 0 10px;font-size:14px">All Signals ({n_trades})</h3>
  <div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>Time (UTC)</th><th>Ticker</th><th>Side</th>
        <th>Entry $</th><th>Qty</th><th>Bail exit $</th>
        <th>Bail P&amp;L</th><th>Settlement</th><th>Hold P&amp;L</th>
      </tr>
    </thead>
    <tbody>
{table_html}
    </tbody>
  </table>
  </div>
</div>

</body>
</html>"""

with open(OUTPUT_HTML, "w") as f:
    f.write(html)

print(f"\nBacktest complete.")
print(f"  Signals   : {n_trades} (bottom-half only)")
print(f"  Bail P&L  : ${bail_total_pnl:+.2f}  (win rate {bail_win_rate:.0f}%)")
print(f"  Hold P&L  : ${hold_total_pnl:+.2f}  (win rate {hold_win_rate:.0f}%, {n_settled} settled)")
print(f"  Report    : {OUTPUT_HTML}")
