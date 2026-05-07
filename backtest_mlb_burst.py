#!/usr/bin/env python3
"""
MLB Burst Strategy Backtest — full signal replay on historical KXMLBGAME data.

Replays all KXMLBGAME home-team tickers using the exact sweep + W1 signal detection
from strategies/mlb_burst_signals.py. For each confirmed signal simulates two scenarios:
  - Bail-always  : exit 45 seconds after entry at market price
  - Hold-always  : hold to settlement (YES=1.00, NO=0.00)

The MLB Stats bottom-half filter is NOT applied here — the MLB Stats API only
returns current/final game state, not historical time-snapshots. Signal counts
therefore include top-half sweeps and overstate what the live strategy would trade.

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
from datetime import datetime, timezone

import pandas as pd

# ── Config ─────────────────────────────────────────────────────────────────────

INGESTION_DIR = "/Users/edbalogh/Trading/Ingestion/data"
SERIES        = "KXMLBGAME"
OUTPUT_HTML   = "/tmp/backtest_mlb_burst.html"
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

# ── Helpers ────────────────────────────────────────────────────────────────────

def _date_range(start: str, end: str) -> list[str]:
    dates = pd.date_range(start, end, freq="D")
    return [d.strftime("%Y-%m-%d") for d in dates]


def is_home_ticker(ticker: str) -> bool:
    """
    Home ticker: the game body (second segment) ends with the team code (third segment).
    e.g. KXMLBGAME-26APR051920STLDET-DET → 26APR051920STLDET ends with DET → home
         KXMLBGAME-26APR051920STLDET-STL → does not end with STL → away
    """
    parts = ticker.split("-")
    return len(parts) >= 3 and parts[-2].endswith(parts[-1])


def compute_qty(price: float) -> int:
    if price <= 0:
        return 1
    return max(1, int(MAX_NOTIONAL_USD / price))


# Lightweight tick stand-in so we can reuse detect_sweep / confirm_w1 without
# constructing NautilusTrader Cython objects for millions of rows.
class _Price:
    __slots__ = ("_v",)
    def __init__(self, v: float): self._v = v
    def as_double(self) -> float: return self._v

class _Tick:
    __slots__ = ("ts_event", "price")
    def __init__(self, ts_ns: int, price: float):
        self.ts_event = ts_ns
        self.price = _Price(price)


# ── Load data ──────────────────────────────────────────────────────────────────

DATES = _date_range(START_DATE, END_DATE)
# Markets dates: include a few extra days for same-day or next-day settlements
MARKET_DATES = _date_range(START_DATE, "2026-05-09")

print(f"Loading KXMLBGAME trade data from {START_DATE} to {END_DATE}...")
t0 = time.time()

trade_frames = []
for date in DATES:
    path = f"{INGESTION_DIR}/trades/series={SERIES}/date={date}/part.parquet"
    if not os.path.exists(path):
        continue
    df = pd.read_parquet(
        path,
        columns=["ticker", "yes_price_dollars", "created_time"],
    )
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
    f"  Loaded {len(all_trades):,} home-ticker trades across "
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

# ── Signal replay ──────────────────────────────────────────────────────────────

from strategies.mlb_burst_signals import detect_sweep, confirm_w1, SweepResult

print("Replaying signals...")
t1 = time.time()

all_signals: list[dict] = []
tickers = all_trades["ticker"].unique()

for ticker in tickers:
    tdf = all_trades[all_trades["ticker"] == ticker]

    buf: deque[_Tick] = deque()
    pending_sweep: SweepResult | None = None

    rows = list(tdf.itertuples(index=False))

    for i, row in enumerate(rows):
        tick = _Tick(int(row.ts_ns), float(row.yes_price_dollars))

        # Append + prune 60-second window
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
                    entry_price = tick.price.as_double()
                    entry_ts_ns = tick.ts_event

                    # Find bail exit price: first tick at or after entry + 45s
                    bail_target_ns = entry_ts_ns + BAIL_SECONDS * 1_000_000_000
                    future_rows = rows[i + 1:]
                    bail_price = entry_price  # default: flat if no future ticks
                    for fr in future_rows:
                        if int(fr.ts_ns) >= bail_target_ns:
                            bail_price = float(fr.yes_price_dollars)
                            break
                    else:
                        # Use last available tick price if window never reached
                        if future_rows:
                            bail_price = float(future_rows[-1].yes_price_dollars)

                    qty = compute_qty(entry_price)
                    bail_pnl = (bail_price - entry_price) * qty

                    result = settlement_map.get(ticker)
                    settle_price = (1.00 if result == "yes" else 0.00) if result else None
                    settle_pnl = (settle_price - entry_price) * qty if settle_price is not None else None

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
                        "settle_pnl":   settle_pnl if settle_pnl is None else round(settle_pnl, 4),
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
    f"  {len(all_signals)} signals across {len(tickers)} tickers in {time.time()-t1:.1f}s"
)

if not all_signals:
    print("No signals found — something may be wrong with the config or data.")
    sys.exit(1)

# ── Compute summary stats ──────────────────────────────────────────────────────

df = pd.DataFrame(all_signals)
df["entry_dt"] = pd.to_datetime(df["entry_dt"], utc=True)
df["entry_date"] = df["entry_dt"].dt.date
df["entry_hour"] = df["entry_dt"].dt.hour

settled = df[df["settle_pnl"].notna()].copy()

bail_total_pnl  = df["bail_pnl"].sum()
hold_total_pnl  = settled["settle_pnl"].sum() if not settled.empty else 0.0
bail_win_rate   = (df["bail_pnl"] > 0).mean() * 100
hold_win_rate   = ((settled["settle_pnl"] > 0).mean() * 100) if not settled.empty else 0.0
n_trades        = len(df)
n_yes_sweeps    = (df["sweep_side"] == "YES").sum()
n_no_sweeps     = (df["sweep_side"] == "NO").sum()
n_settled       = len(settled)

# Cumulative equity curves
df_sorted = df.sort_values("entry_dt").reset_index(drop=True)
df_sorted["cum_bail_pnl"]   = df_sorted["bail_pnl"].cumsum()
df_sorted["cum_bail_equity"] = STARTING_CAPITAL + df_sorted["cum_bail_pnl"]

settled_sorted = settled.sort_values("entry_dt").reset_index(drop=True)
settled_sorted["cum_hold_pnl"] = settled_sorted["settle_pnl"].cumsum()
settled_sorted["cum_hold_equity"] = STARTING_CAPITAL + settled_sorted["cum_hold_pnl"]

# Daily signal counts
daily_counts = df.groupby("entry_date").size().reset_index(name="count")
daily_counts["entry_date"] = daily_counts["entry_date"].astype(str)

# Hourly distribution (UTC hours)
hourly_counts = df.groupby("entry_hour").size().reset_index(name="count")

# Best/worst trades (bail)
best_bail  = df.loc[df["bail_pnl"].idxmax()]
worst_bail = df.loc[df["bail_pnl"].idxmin()]

# ── Build HTML report ──────────────────────────────────────────────────────────

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

def _fig_to_div(fig) -> str:
    return pio.to_html(fig, full_html=False, include_plotlyjs=False)


# --- Chart 1: Equity curves ---
fig_equity = go.Figure()
fig_equity.add_trace(go.Scatter(
    x=df_sorted["entry_dt"].dt.strftime("%Y-%m-%d %H:%M"),
    y=df_sorted["cum_bail_equity"],
    mode="lines",
    name="Bail-always",
    line=dict(color="#2196F3", width=2),
))
if not settled_sorted.empty:
    fig_equity.add_trace(go.Scatter(
        x=settled_sorted["entry_dt"].dt.strftime("%Y-%m-%d %H:%M"),
        y=settled_sorted["cum_hold_equity"],
        mode="lines",
        name="Hold-to-settlement",
        line=dict(color="#4CAF50", width=2),
    ))
fig_equity.add_hline(
    y=STARTING_CAPITAL, line_dash="dash",
    line_color="#888", annotation_text="Starting capital",
)
fig_equity.update_layout(
    title="Cumulative Equity — Bail-always vs Hold-to-settlement",
    xaxis_title="Signal time (UTC)",
    yaxis_title="Account balance ($)",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    height=400, margin=dict(l=60, r=20, t=80, b=60),
    plot_bgcolor="#fafafa",
)
equity_div = _fig_to_div(fig_equity)


# --- Chart 2: Daily signal counts ---
fig_daily = go.Figure(go.Bar(
    x=daily_counts["entry_date"],
    y=daily_counts["count"],
    marker_color="#7E57C2",
))
fig_daily.update_layout(
    title="Signals per Day",
    xaxis_title="Date",
    yaxis_title="Signal count",
    height=300, margin=dict(l=60, r=20, t=60, b=80),
    plot_bgcolor="#fafafa",
)
daily_div = _fig_to_div(fig_daily)


# --- Chart 3: Hourly distribution ---
fig_hourly = go.Figure(go.Bar(
    x=hourly_counts["entry_hour"],
    y=hourly_counts["count"],
    marker_color="#FF7043",
))
fig_hourly.update_layout(
    title="Signal Count by Hour of Day (UTC)",
    xaxis_title="Hour (UTC)",
    yaxis_title="Signal count",
    height=300, margin=dict(l=60, r=20, t=60, b=60),
    plot_bgcolor="#fafafa",
    xaxis=dict(tickmode="linear", dtick=1),
)
hourly_div = _fig_to_div(fig_hourly)


# --- Chart 4: P&L distribution ---
fig_pnl = go.Figure()
fig_pnl.add_trace(go.Histogram(
    x=df["bail_pnl"],
    nbinsx=40,
    name="Bail P&L",
    marker_color="#2196F3",
    opacity=0.7,
))
if not settled.empty:
    fig_pnl.add_trace(go.Histogram(
        x=settled["settle_pnl"],
        nbinsx=40,
        name="Hold P&L",
        marker_color="#4CAF50",
        opacity=0.7,
    ))
fig_pnl.update_layout(
    title="P&L Distribution per Trade",
    barmode="overlay",
    xaxis_title="P&L ($)",
    yaxis_title="Count",
    height=300, margin=dict(l=60, r=20, t=60, b=60),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    plot_bgcolor="#fafafa",
)
pnl_dist_div = _fig_to_div(fig_pnl)


# --- Trade table ---
table_rows = []
for _, row in df_sorted.iterrows():
    bail_cls = "pos" if row["bail_pnl"] > 0 else ("neg" if row["bail_pnl"] < 0 else "")
    hold_cls = ""
    hold_str = "—"
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


# --- Summary stat cards ---
def stat_card(label: str, value: str, sub: str = "", color: str = "#333") -> str:
    return (
        f'<div class="card">'
        f'<div class="card-label">{label}</div>'
        f'<div class="card-value" style="color:{color}">{value}</div>'
        f'<div class="card-sub">{sub}</div>'
        f'</div>'
    )

bail_color  = "#2E7D32" if bail_total_pnl >= 0 else "#C62828"
hold_color  = "#2E7D32" if hold_total_pnl >= 0 else "#C62828"

cards_html = "".join([
    stat_card("Total Signals", f"{n_trades:,}", f"{START_DATE} → {END_DATE}"),
    stat_card("YES Sweeps", f"{n_yes_sweeps:,}", f"NO: {n_no_sweeps:,}"),
    stat_card("Bail P&L", f"${bail_total_pnl:+,.2f}",
              f"win rate {bail_win_rate:.0f}% ({n_trades} trades)", bail_color),
    stat_card("Hold P&L", f"${hold_total_pnl:+,.2f}",
              f"win rate {hold_win_rate:.0f}% ({n_settled} settled)", hold_color),
    stat_card("Avg Bail / trade", f"${bail_total_pnl/n_trades:+.3f}",
              f"best ${best_bail['bail_pnl']:+.2f} / worst ${worst_bail['bail_pnl']:+.2f}"),
])

import plotly
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>MLB Burst Backtest</title>
<script src="https://cdn.plot.ly/plotly-{plotly.__version__}.min.js"></script>
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
  .warn    {{ background: #FFF8E1; border-left: 4px solid #FFC107;
              padding: 10px 14px; border-radius: 4px; font-size: 13px;
              margin-bottom: 20px; }}
  .table-wrap {{ max-height: 500px; overflow-y: auto; }}
</style>
</head>
<body>
<h1>MLB Burst Strategy — Full Backtest</h1>
<div class="subtitle">
  KXMLBGAME home-team tickers &nbsp;·&nbsp; {START_DATE} through {END_DATE}
  &nbsp;·&nbsp; {len(tickers):,} unique tickers
  &nbsp;·&nbsp; Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
</div>

<div class="warn">
  ⚠️ <strong>Bottom-half filter not applied.</strong>
  The live strategy only enters in the bottom half (home team batting). This backtest
  includes top-half sweeps, which roughly doubles signal count and may overstate P&amp;L.
  Settlement data covers {n_settled}/{n_trades} signals; the rest had no settlement record.
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
print(f"  Signals   : {n_trades}")
print(f"  Bail P&L  : ${bail_total_pnl:+.2f}  (win rate {bail_win_rate:.0f}%)")
print(f"  Hold P&L  : ${hold_total_pnl:+.2f}  (win rate {hold_win_rate:.0f}%, {n_settled} settled)")
print(f"  Report    : {OUTPUT_HTML}")
