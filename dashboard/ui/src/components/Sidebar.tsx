// dashboard/ui/src/components/Sidebar.tsx
import { NavLink } from "react-router-dom";
import type { StrategySummary } from "../types";

interface Props {
  strategies: StrategySummary[];
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    running: "bg-profit shadow-[0_0_5px_rgba(22,163,74,0.6)]",
    paper:   "bg-paper  shadow-[0_0_5px_rgba(37,99,235,0.4)]",
    stopped: "bg-[#c8c8d8]",
    error:   "bg-loss",
  };
  return (
    <span
      className={`ml-auto w-1.5 h-1.5 rounded-full flex-shrink-0 ${colors[status] ?? colors.stopped}`}
    />
  );
}

function SidebarLink({
  to,
  icon,
  label,
  indicator,
}: {
  to: string;
  icon: string;
  label: string;
  indicator?: React.ReactNode;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 px-4 py-1.5 text-xs cursor-pointer border-r-2 transition-colors ${
          isActive
            ? "bg-sidebar-active text-accent font-semibold border-accent"
            : "text-text-secondary border-transparent hover:bg-sidebar-active/50 hover:text-text-primary"
        }`
      }
    >
      <span className="w-4 text-center opacity-75">{icon}</span>
      <span>{label}</span>
      {indicator}
    </NavLink>
  );
}

export function Sidebar({ strategies }: Props) {
  const anyLive = strategies.some((s) => s.status === "running");

  return (
    <aside className="w-[200px] bg-sidebar border-r border-sidebar-border flex flex-col flex-shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-4 border-b border-sidebar-border">
        <span className="text-sm font-extrabold tracking-tight text-text-primary">
          nautilus<span className="text-accent">+</span>
        </span>
        {anyLive && (
          <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-[#f0fdf4] text-profit border border-[#bbf7d0]">
            LIVE
          </span>
        )}
      </div>

      {/* Strategies */}
      <div className="pt-3">
        <p className="px-4 pb-1 text-[9.5px] font-bold text-text-muted uppercase tracking-widest">
          Strategies
        </p>
        {strategies.map((s) => (
          <SidebarLink
            key={s.name}
            to={`/strategy/${s.name}`}
            icon={s.icon}
            label={s.display_name}
            indicator={<StatusDot status={s.status} />}
          />
        ))}
      </div>

      <div className="my-2 mx-4 border-t border-sidebar-border" />

      {/* Research */}
      <div>
        <p className="px-4 pb-1 text-[9.5px] font-bold text-text-muted uppercase tracking-widest">
          Research
        </p>
        <SidebarLink to="/backtest" icon="▶" label="Run Backtest" />
        <SidebarLink to="/backtest/history" icon="⊡" label="Backtest History" />
      </div>

      {/* Footer */}
      <div className="mt-auto px-4 py-3 border-t border-sidebar-border flex items-center gap-2">
        <div className="w-6 h-6 rounded-full bg-gradient-to-br from-accent to-purple-400 flex items-center justify-center text-white text-[11px] font-bold flex-shrink-0">
          E
        </div>
        <div className="min-w-0">
          <p className="text-[11px] font-semibold text-text-secondary truncate">nautilus-plus</p>
          <p className="text-[9.5px] text-text-muted">Mac Mini · LAN</p>
        </div>
        <button className="ml-auto text-text-muted text-sm">⚙</button>
      </div>
    </aside>
  );
}
