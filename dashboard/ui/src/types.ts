// dashboard/ui/src/types.ts

export interface Position {
  ticker: string;
  qty: number;
  avg_px: number;
  last_px: number;
  unrealized_pnl: number;
}

export interface Fill {
  ticker: string;
  side: "BUY" | "SELL" | "SETTLE";
  qty: number;
  price: number;
  pnl: number | null;
  ts: number;
  type: "trade" | "settlement";
}

export interface EquityPoint {
  ts: number;
  equity: number;
}

export interface StrategySnapshot {
  strategy: string;
  mode: "live" | "paper";
  status: "running" | "stopped" | "error";
  ts: number;
  equity: number | null;
  starting_capital: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  total_trades: number | null;
  win_rate: number | null;
  positions: Position[];
  recent_fills: Fill[];
  equity_history: EquityPoint[];
}

export interface StrategySummary {
  name: string;
  display_name: string;
  icon: string;
  status: "running" | "stopped" | "error";
  mode: "live" | "paper";
  equity: number | null;
  realized_pnl: number | null;
  unrealized_pnl: number | null;
  total_trades: number | null;
  win_rate: number | null;
}

export interface WsMessage {
  snapshots: StrategySnapshot[];
}

export interface ConfigField {
  key: string;
  label: string;
  type: "int" | "float" | "bool" | "string";
  default: number | boolean | string;
  min?: number;
  max?: number;
}

export interface StrategyConfig {
  strategy: string;
  schema: ConfigField[];
  values: Record<string, number | boolean | string>;
}

export interface BacktestKpis {
  total_trades: number;
  win_rate: number;
  realized_pnl: number;
  max_drawdown: number;
  sharpe: number;
}

export interface BacktestTrade {
  ts: number;
  ticker: string;
  side: "YES" | "NO";
  qty: number;
  price: number;
  pnl: number;
}

export interface BacktestRun {
  run_id: string;
  strategy: string;
  started_at: number;
  finished_at: number | null;
  status: "pending" | "running" | "done" | "error";
  progress_pct: number;
  params: {
    start_date: string;
    end_date: string;
    overrides: Record<string, number | boolean | string>;
  };
}

export interface BacktestDetail extends BacktestRun {
  progress_msg: string | null;
  kpis: BacktestKpis | null;
  trades: BacktestTrade[] | null;
  equity_curve: EquityPoint[] | null;
}
