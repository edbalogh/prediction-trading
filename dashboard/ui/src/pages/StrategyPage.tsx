// dashboard/ui/src/pages/StrategyPage.tsx
import { useState, useCallback } from "react";
import { useParams } from "react-router-dom";
import type { StrategySummary } from "../types";
import type { SnapshotMap } from "../hooks/useStrategyState";
import { TopBar } from "../components/TopBar";
import { KpiCards } from "../components/KpiCards";
import { EquityChart } from "../components/EquityChart";
import { PositionsTable } from "../components/PositionsTable";
import { TradeLog } from "../components/TradeLog";
import { ConfigEditor } from "../components/ConfigEditor";
import { api } from "../api/client";

interface Props {
  strategies: StrategySummary[];
  snapshots: SnapshotMap;
}

function Card({ title, sub, children }: { title: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="bg-card border border-card-border rounded-xl shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#f0f0f8]">
        <span className="text-xs font-semibold text-text-primary">{title}</span>
        {sub && <span className="text-[10.5px] text-text-muted">{sub}</span>}
      </div>
      <div className="px-4 py-3">{children}</div>
    </div>
  );
}

export function StrategyPage({ strategies, snapshots }: Props) {
  const { name } = useParams<{ name: string }>();
  const strategy = strategies.find((s) => s.name === name);
  const snapshot = name ? snapshots[name] ?? null : null;

  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [isActionLoading, setIsActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleStart = useCallback(async (mode: "paper" | "live") => {
    if (!name) return;
    setIsActionLoading(true);
    setActionError(null);
    try {
      await api.startStrategy(name, mode);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to start strategy.");
    } finally {
      setIsActionLoading(false);
    }
  }, [name]);

  const handleStop = useCallback(async () => {
    if (!name) return;
    setIsActionLoading(true);
    setActionError(null);
    try {
      await api.stopStrategy(name);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to stop strategy.");
    } finally {
      setIsActionLoading(false);
    }
  }, [name]);

  if (!strategy) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted">
        Strategy not found.
      </div>
    );
  }

  const history = snapshot?.equity_history ?? [];
  const startingCapital = snapshot?.starting_capital ?? 10_000;

  return (
    <div className="flex flex-col h-full">
      <TopBar
        snapshot={snapshot}
        displayName={strategy.display_name}
        onEditConfig={() => setIsConfigOpen(true)}
        onStart={handleStart}
        onStop={handleStop}
        isActionLoading={isActionLoading}
      />
      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-3.5">
        {actionError && (
          <div className="text-[11px] text-loss bg-[#fef2f2] border border-[#fecaca] rounded-lg px-3 py-2">
            {actionError}
          </div>
        )}
        <KpiCards snapshot={snapshot} />

        <div className="grid grid-cols-[2fr_1fr] gap-3">
          <Card title="Equity Curve" sub={`$${startingCapital.toLocaleString()} start`}>
            <div className="h-32">
              <EquityChart history={history} startingCapital={startingCapital} />
            </div>
          </Card>
          <Card title="Open Positions" sub={`${snapshot?.positions.length ?? 0} active`}>
            <PositionsTable positions={snapshot?.positions ?? []} />
          </Card>
        </div>

        <Card title="Trade Log" sub="Most recent first">
          <TradeLog fills={snapshot?.recent_fills ?? []} />
        </Card>
      </div>

      <ConfigEditor
        strategyName={strategy.name}
        displayName={strategy.display_name}
        isOpen={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
      />
    </div>
  );
}
