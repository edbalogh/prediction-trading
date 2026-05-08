// dashboard/ui/src/components/TopBar.tsx
import type { StrategySnapshot } from "../types";

interface Props {
  snapshot: StrategySnapshot | null;
  displayName: string;
}

function StatusPill({ status, mode }: { status: string; mode: string }) {
  const configs: Record<string, { bg: string; text: string; border: string; label: string }> = {
    running: { bg: "bg-[#f0fdf4]", text: "text-profit", border: "border-[#bbf7d0]", label: "● Running" },
    paper:   { bg: "bg-[#eff6ff]", text: "text-paper",  border: "border-[#bfdbfe]", label: "◎ Paper" },
    stopped: { bg: "bg-[#f5f5f8]", text: "text-text-muted", border: "border-card-border", label: "○ Stopped" },
  };
  const key = status === "running" && mode === "paper" ? "paper" : status;
  const c = configs[key] ?? configs.stopped;
  return (
    <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full border ${c.bg} ${c.text} ${c.border}`}>
      {c.label}
    </span>
  );
}

export function TopBar({ snapshot, displayName }: Props) {
  const mode = snapshot?.mode ?? "paper";
  const status = snapshot?.status ?? "stopped";
  const modeLabel = mode === "live" ? "Live" : "Paper";

  return (
    <header className="h-[52px] bg-card border-b border-card-border px-5 flex items-center justify-between flex-shrink-0">
      <div className="flex items-center gap-3">
        <h1 className="text-[15px] font-bold text-text-primary">
          {displayName} — {modeLabel}
        </h1>
        <StatusPill status={status} mode={mode} />
      </div>
      <div className="flex gap-2">
        <button
          disabled
          className="text-[11.5px] font-semibold px-3.5 py-1.5 rounded-lg border border-card-border text-text-secondary opacity-50 cursor-not-allowed"
          title="Strategy control coming in Stage 2"
        >
          Edit Config
        </button>
        <button
          disabled
          className="text-[11.5px] font-semibold px-3.5 py-1.5 rounded-lg bg-[#fef2f2] text-loss border border-[#fecaca] opacity-50 cursor-not-allowed"
          title="Strategy control coming in Stage 2"
        >
          Stop Strategy
        </button>
      </div>
    </header>
  );
}
