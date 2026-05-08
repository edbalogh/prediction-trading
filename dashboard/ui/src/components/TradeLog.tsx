// dashboard/ui/src/components/TradeLog.tsx
import type { Fill } from "../types";

interface Props {
  fills: Fill[];
}

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

const SIDE_STYLE: Record<string, string> = {
  BUY:    "text-profit font-bold",
  SELL:   "text-loss font-bold",
  SETTLE: "text-accent font-bold",
};

export function TradeLog({ fills }: Props) {
  if (fills.length === 0) {
    return <p className="text-text-muted text-xs py-4 text-center">No trades yet</p>;
  }

  return (
    <div className="max-h-48 overflow-y-auto divide-y divide-[#f4f4f8]">
      {fills.slice(0, 50).map((fill, i) => (
        <div key={i} className="flex items-baseline gap-2 py-1.5 text-[11px]">
          <span className="font-mono text-text-muted text-[10px] flex-shrink-0 w-[52px]">
            {formatTime(fill.ts)}
          </span>
          <span className="font-mono font-semibold text-accent text-[10.5px] flex-shrink-0 w-[150px] truncate">
            {fill.ticker}
          </span>
          <span className={`text-[10px] flex-shrink-0 w-[36px] ${SIDE_STYLE[fill.side] ?? ""}`}>
            {fill.side}
          </span>
          <span className="text-text-secondary flex-1 text-[10.5px]">
            {fill.qty} × ${fill.price.toFixed(2)}
          </span>
          {fill.pnl !== null && fill.pnl !== undefined ? (
            <span className={`font-semibold flex-shrink-0 ${fill.pnl >= 0 ? "text-profit" : "text-loss"}`}>
              {fill.pnl >= 0 ? "+" : ""}${fill.pnl.toFixed(2)}
            </span>
          ) : (
            <span className="text-text-muted flex-shrink-0">open</span>
          )}
        </div>
      ))}
    </div>
  );
}
