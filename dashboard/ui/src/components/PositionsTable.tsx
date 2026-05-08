// dashboard/ui/src/components/PositionsTable.tsx
import type { Position } from "../types";

interface Props {
  positions: Position[];
}

export function PositionsTable({ positions }: Props) {
  if (positions.length === 0) {
    return (
      <p className="text-text-muted text-xs py-4 text-center">No open positions</p>
    );
  }

  return (
    <table className="w-full text-xs border-collapse">
      <thead>
        <tr className="border-b border-[#f0f0f8]">
          {["Ticker", "Side", "Qty", "Entry", "Last", "Unr. P&L"].map((h) => (
            <th
              key={h}
              className={`pb-2 font-semibold text-text-muted uppercase tracking-wide text-[9.5px] ${
                h === "Ticker" ? "text-left" : "text-right"
              }`}
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => {
          const pnlColor = p.unrealized_pnl >= 0 ? "text-profit" : "text-loss";
          return (
            <tr key={p.ticker} className="border-b border-[#f8f8fc] last:border-0">
              <td className="py-1.5 font-mono font-semibold text-accent text-[11px]">{p.ticker}</td>
              <td className="py-1.5 text-right">
                <span className="bg-[#f0fdf4] text-profit text-[9px] font-bold px-1.5 py-0.5 rounded">
                  YES
                </span>
              </td>
              <td className="py-1.5 text-right text-text-primary">{p.qty}</td>
              <td className="py-1.5 text-right text-text-primary">${p.avg_px.toFixed(2)}</td>
              <td className="py-1.5 text-right text-text-primary">${p.last_px.toFixed(2)}</td>
              <td className={`py-1.5 text-right font-semibold ${pnlColor}`}>
                {p.unrealized_pnl >= 0 ? "+" : ""}${p.unrealized_pnl.toFixed(2)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
