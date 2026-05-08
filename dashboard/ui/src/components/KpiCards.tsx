// dashboard/ui/src/components/KpiCards.tsx
import type { StrategySnapshot } from "../types";

function fmt(n: number | null, prefix = ""): string {
  if (n === null || n === undefined) return "—";
  const sign = n >= 0 ? "+" : "";
  return `${prefix}${sign}${n.toFixed(2)}`;
}

function fmtPct(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

interface KpiProps {
  label: string;
  value: string;
  valueClass?: string;
  sub?: string;
  subClass?: string;
}

function Kpi({ label, value, valueClass = "", sub, subClass = "text-text-muted" }: KpiProps) {
  return (
    <div className="bg-card border border-card-border rounded-xl px-3.5 py-3 shadow-sm">
      <p className="text-[10.5px] text-text-muted uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-xl font-bold tracking-tight ${valueClass}`}>{value}</p>
      {sub && <p className={`text-[10px] mt-0.5 ${subClass}`}>{sub}</p>}
    </div>
  );
}

interface Props {
  snapshot: StrategySnapshot | null;
}

export function KpiCards({ snapshot }: Props) {
  if (!snapshot || snapshot.status === "stopped") {
    return (
      <div className="grid grid-cols-5 gap-2.5">
        {["Realized P&L", "Unrealized P&L", "Total Trades", "Win Rate", "Equity"].map((label) => (
          <Kpi key={label} label={label} value="—" />
        ))}
      </div>
    );
  }

  const { realized_pnl, unrealized_pnl, total_trades, win_rate, equity, starting_capital, positions } = snapshot;
  const equityPct = equity && starting_capital ? ((equity - starting_capital) / starting_capital) * 100 : null;

  return (
    <div className="grid grid-cols-5 gap-2.5">
      <Kpi
        label="Realized P&L"
        value={`$${fmt(realized_pnl)}`}
        valueClass={realized_pnl !== null && realized_pnl >= 0 ? "text-profit" : "text-loss"}
        sub="all-time"
      />
      <Kpi
        label="Unrealized P&L"
        value={`$${fmt(unrealized_pnl)}`}
        valueClass={unrealized_pnl !== null && unrealized_pnl >= 0 ? "text-profit" : "text-loss"}
        sub={`${positions.length} open position${positions.length !== 1 ? "s" : ""}`}
      />
      <Kpi
        label="Total Trades"
        value={total_trades?.toString() ?? "—"}
        sub="fills (trades + settlements)"
      />
      <Kpi
        label="Win Rate"
        value={fmtPct(win_rate)}
        valueClass="text-accent"
        sub={win_rate !== null ? "settled positions" : "no settlements yet"}
      />
      <Kpi
        label="Equity"
        value={equity !== null ? `$${equity.toFixed(2)}` : "—"}
        sub={equityPct !== null ? `${equityPct >= 0 ? "+" : ""}${equityPct.toFixed(2)}% all-time` : undefined}
        subClass={equityPct !== null && equityPct >= 0 ? "text-profit" : "text-loss"}
      />
    </div>
  );
}
