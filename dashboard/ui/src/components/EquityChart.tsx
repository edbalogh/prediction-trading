// dashboard/ui/src/components/EquityChart.tsx
import {
  AreaChart, Area, XAxis, YAxis, ResponsiveContainer,
  Tooltip, CartesianGrid,
} from "recharts";
import type { EquityPoint } from "../types";

interface Props {
  history: EquityPoint[];
  startingCapital: number;
}

function formatTime(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDollar(val: number): string {
  return `$${val.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function EquityChart({ history, startingCapital }: Props) {
  if (history.length < 2) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted text-sm">
        Waiting for data...
      </div>
    );
  }

  // Downsample to max 300 points to keep rendering fast
  const step = Math.max(1, Math.floor(history.length / 300));
  const data = history.filter((_, i) => i % step === 0 || i === history.length - 1);

  const equities = data.map((d) => d.equity);
  const minEq = Math.min(...equities, startingCapital);
  const maxEq = Math.max(...equities, startingCapital);
  const padding = (maxEq - minEq) * 0.1 || 10;

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#7b5cff" stopOpacity={0.2} />
            <stop offset="95%" stopColor="#7b5cff" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f8" vertical={false} />
        <XAxis
          dataKey="ts"
          tickFormatter={formatTime}
          tick={{ fontSize: 9, fill: "#c0c0d8" }}
          tickLine={false}
          axisLine={false}
          minTickGap={60}
        />
        <YAxis
          domain={[minEq - padding, maxEq + padding]}
          tickFormatter={(v: number) => `$${(v / 1000).toFixed(1)}k`}
          tick={{ fontSize: 9, fill: "#c0c0d8" }}
          tickLine={false}
          axisLine={false}
          width={46}
        />
        <Tooltip
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter={(val: any) => [
            typeof val === "number" ? formatDollar(val as number) : String(val ?? ""),
            "Equity",
          ]}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          labelFormatter={(ts: any) =>
            typeof ts === "number" ? formatTime(ts as number) : String(ts ?? "")
          }
          contentStyle={{
            background: "#fff", border: "1px solid #e4e4f0",
            borderRadius: 8, fontSize: 11,
          }}
        />
        <Area
          type="monotone"
          dataKey="equity"
          stroke="#7b5cff"
          strokeWidth={2}
          fill="url(#equityGrad)"
          dot={false}
          activeDot={{ r: 4, fill: "#7b5cff", stroke: "#fff", strokeWidth: 2 }}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
