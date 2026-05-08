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
