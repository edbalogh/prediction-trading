// dashboard/ui/src/pages/BacktestPage.tsx
import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "react-router-dom";
import type {
  StrategySummary,
  StrategyConfig,
  BacktestRun,
  BacktestDetail,
} from "../types";
import { api } from "../api/client";
import { EquityChart } from "../components/EquityChart";

interface Props {
  strategies: StrategySummary[];
}

function ParamInput({
  field,
  value,
  onChange,
}: {
  field: { key: string; label: string; type: string; min?: number; max?: number };
  value: number | boolean | string;
  onChange: (val: number | boolean | string) => void;
}) {
  if (field.type === "string") {
    return (
      <input
        type="text"
        value={value as string}
        onChange={(e) => onChange(e.target.value)}
        className="w-44 text-[12px] px-2 py-1 border border-card-border rounded-lg bg-surface text-text-primary focus:outline-none focus:border-accent"
      />
    );
  }
  const step = field.type === "float" ? "0.01" : "1";
  return (
    <input
      type="number"
      step={step}
      min={field.min}
      max={field.max}
      value={value as number}
      onChange={(e) => {
        const raw = e.target.value;
        const num = field.type === "int" ? parseInt(raw, 10) : parseFloat(raw);
        if (!isNaN(num)) onChange(num);
      }}
      className="w-28 text-right text-[12px] font-mono px-2 py-1 border border-card-border rounded-lg bg-surface text-text-primary focus:outline-none focus:border-accent"
    />
  );
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    running: { bg: "bg-[#eff6ff]", text: "text-paper",      label: "Running" },
    done:    { bg: "bg-[#f0fdf4]", text: "text-profit",     label: "Done" },
    error:   { bg: "bg-[#fef2f2]", text: "text-loss",       label: "Error" },
    pending: { bg: "bg-[#f5f5f8]", text: "text-text-muted", label: "Pending" },
  };
  const c = map[status] ?? map.pending;
  return (
    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

export function BacktestPage({ strategies }: Props) {
  const { name } = useParams<{ name: string }>();
  const strategy = strategies.find((s) => s.name === name);

  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [overrides, setOverrides] = useState<Record<string, number | boolean | string>>({});

  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<BacktestDetail | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!name) return;
    api.getConfig(name).then((cfg) => {
      setConfig(cfg);
      setOverrides({ ...cfg.values });
    }).catch(() => {});
    api.listBacktests(name).then(setRuns).catch(() => {});
  }, [name]);

  // Poll selected run when in-progress
  useEffect(() => {
    if (pollingRef.current) clearInterval(pollingRef.current);
    if (!selectedRunId) return;
    if (detail && detail.status !== "running" && detail.status !== "pending") return;

    const poll = async () => {
      const d = await api.getBacktest(selectedRunId).catch(() => null);
      if (!d) return;
      setDetail(d);
      if (d.status !== "running" && d.status !== "pending") {
        if (pollingRef.current) clearInterval(pollingRef.current);
        if (name) api.listBacktests(name).then(setRuns).catch(() => {});
      }
    };

    pollingRef.current = setInterval(poll, 2000);
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [selectedRunId, detail?.status, name]);

  const handleSelectRun = useCallback(async (runId: string) => {
    setSelectedRunId(runId);
    const d = await api.getBacktest(runId).catch(() => null);
    setDetail(d);
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!name) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const result = await api.startBacktest(name, {
        start_date: startDate,
        end_date: endDate,
        overrides,
      });
      const updatedRuns = await api.listBacktests(name);
      setRuns(updatedRuns);
      await handleSelectRun(result.run_id);
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : "Failed to start backtest.");
    } finally {
      setIsSubmitting(false);
    }
  }, [name, startDate, endDate, overrides, handleSelectRun]);

  const handleRerun = useCallback(
    (run: BacktestRun) => {
      setStartDate(run.params.start_date);
      setEndDate(run.params.end_date);
      if (config) {
        setOverrides({ ...config.values, ...run.params.overrides });
      }
    },
    [config]
  );

  const isAnyRunning = runs.some(
    (r) => r.status === "running" || r.status === "pending"
  );

  if (!strategy) {
    return (
      <div className="flex items-center justify-center h-full text-text-muted">
        Strategy not found.
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left column: run form */}
      <div className="w-[300px] flex-shrink-0 border-r border-card-border overflow-y-auto p-5 flex flex-col gap-4">
        <h2 className="text-[13px] font-bold text-text-primary">Run Backtest</h2>

        {/* Date range */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <label className="text-[11.5px] font-medium text-text-primary whitespace-nowrap">
              Start Date
            </label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="text-[12px] px-2 py-1 border border-card-border rounded-lg bg-surface text-text-primary focus:outline-none focus:border-accent"
            />
          </div>
          <div className="flex items-center justify-between gap-2">
            <label className="text-[11.5px] font-medium text-text-primary whitespace-nowrap">
              End Date
            </label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="text-[12px] px-2 py-1 border border-card-border rounded-lg bg-surface text-text-primary focus:outline-none focus:border-accent"
            />
          </div>
        </div>

        {/* Parameter overrides */}
        {config && config.schema.length > 0 && (
          <div className="space-y-2">
            <p className="text-[10px] font-bold text-text-muted uppercase tracking-widest">
              Parameters
            </p>
            {config.schema.map((field) => (
              <div key={field.key} className="flex items-center justify-between gap-2">
                <p className="text-[11.5px] font-medium text-text-primary truncate flex-1">
                  {field.label}
                </p>
                <ParamInput
                  field={field}
                  value={overrides[field.key] ?? field.default}
                  onChange={(val) =>
                    setOverrides((prev) => ({ ...prev, [field.key]: val }))
                  }
                />
              </div>
            ))}
          </div>
        )}

        {submitError && (
          <p className="text-[11px] text-loss bg-[#fef2f2] border border-[#fecaca] rounded-lg px-3 py-2">
            {submitError}
          </p>
        )}

        <button
          onClick={handleSubmit}
          disabled={isSubmitting || isAnyRunning || !startDate || !endDate}
          className="w-full text-[12px] font-semibold py-2 rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {isSubmitting ? "Starting…" : isAnyRunning ? "Running…" : "Run Backtest"}
        </button>
      </div>

      {/* Right column: history + detail */}
      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
        <h2 className="text-[13px] font-bold text-text-primary">History</h2>

        {runs.length === 0 ? (
          <p className="text-text-muted text-sm">No runs yet.</p>
        ) : (
          <div className="space-y-2">
            {runs.map((run) => (
              <button
                key={run.run_id}
                onClick={() => handleSelectRun(run.run_id)}
                className={`w-full text-left px-4 py-3 rounded-xl border transition-colors ${
                  selectedRunId === run.run_id
                    ? "border-accent bg-[#eff6ff]"
                    : "border-card-border bg-card hover:bg-surface"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[11.5px] font-medium text-text-primary">
                    {run.params.start_date} → {run.params.end_date}
                  </span>
                  <StatusBadge status={run.status} />
                </div>
                {(run.status === "running" || run.status === "pending") && (
                  <div className="mt-1.5 h-1 bg-[#e0e0f0] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent rounded-full transition-all"
                      style={{ width: `${run.progress_pct}%` }}
                    />
                  </div>
                )}
                <p className="text-[10px] text-text-muted mt-1">
                  {new Date(run.started_at * 1000).toLocaleString()}
                </p>
              </button>
            ))}
          </div>
        )}

        {/* In-progress detail */}
        {detail && (detail.status === "running" || detail.status === "pending") && (
          <div className="bg-card border border-card-border rounded-xl px-4 py-6 text-center">
            <p className="text-text-muted text-sm mb-3">
              {detail.progress_msg || "Running backtest…"}
            </p>
            <div className="h-2 bg-[#e0e0f0] rounded-full overflow-hidden max-w-xs mx-auto">
              <div
                className="h-full bg-accent rounded-full transition-all"
                style={{ width: `${detail.progress_pct}%` }}
              />
            </div>
            <p className="text-[11px] text-text-muted mt-2">{detail.progress_pct}%</p>
          </div>
        )}

        {/* Error detail */}
        {detail && detail.status === "error" && (
          <div className="bg-[#fef2f2] border border-[#fecaca] rounded-xl px-4 py-4">
            <p className="text-[12px] text-loss font-semibold">Backtest failed</p>
            <p className="text-[11px] text-loss/70 mt-1">
              The backtest script exited with an error. Check the terminal for details.
            </p>
          </div>
        )}

        {/* Done detail */}
        {detail && detail.status === "done" && (
          <div className="space-y-4">
            {/* KPI cards */}
            {detail.kpis && (
              <div className="grid grid-cols-5 gap-2">
                {[
                  { label: "Trades",      value: String(detail.kpis.total_trades) },
                  { label: "Win Rate",    value: `${(detail.kpis.win_rate * 100).toFixed(1)}%` },
                  { label: "Realized P&L", value: `$${detail.kpis.realized_pnl.toFixed(2)}` },
                  { label: "Max DD",      value: `$${detail.kpis.max_drawdown.toFixed(2)}` },
                  { label: "Sharpe",      value: detail.kpis.sharpe.toFixed(2) },
                ].map(({ label, value }) => (
                  <div
                    key={label}
                    className="bg-card border border-card-border rounded-xl px-3 py-2"
                  >
                    <p className="text-[9.5px] font-bold text-text-muted uppercase tracking-widest">
                      {label}
                    </p>
                    <p className="text-[14px] font-bold text-text-primary mt-0.5">{value}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Equity curve */}
            {detail.equity_curve && detail.equity_curve.length > 0 && (
              <div className="bg-card border border-card-border rounded-xl overflow-hidden">
                <div className="px-4 py-3 border-b border-card-border">
                  <span className="text-xs font-semibold text-text-primary">Equity Curve</span>
                </div>
                <div className="px-4 py-3 h-40">
                  <EquityChart history={detail.equity_curve} startingCapital={10_000} />
                </div>
              </div>
            )}

            {/* Trade table */}
            {detail.trades && (
              <div className="bg-card border border-card-border rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-4 py-3 border-b border-card-border">
                  <span className="text-xs font-semibold text-text-primary">
                    Trades ({detail.trades.length})
                  </span>
                  <div className="flex gap-2">
                    <a
                      href={api.exportBacktestUrl(detail.run_id)}
                      download
                      className="text-[11px] font-semibold px-3 py-1 rounded-lg border border-card-border text-text-secondary hover:bg-surface transition-colors"
                    >
                      Export CSV
                    </a>
                    <button
                      onClick={() => handleRerun(detail)}
                      className="text-[11px] font-semibold px-3 py-1 rounded-lg bg-accent text-white hover:bg-accent-hover transition-colors"
                    >
                      Re-run
                    </button>
                  </div>
                </div>
                {detail.trades.length === 0 ? (
                  <p className="px-4 py-4 text-[11px] text-text-muted">No trades.</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-[11.5px]">
                      <thead>
                        <tr className="border-b border-card-border">
                          {["Time", "Ticker", "Side", "Qty", "Price", "P&L"].map((h) => (
                            <th
                              key={h}
                              className="px-4 py-2 text-left text-[10px] font-bold text-text-muted uppercase tracking-widest"
                            >
                              {h}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {detail.trades.map((trade, i) => (
                          <tr
                            key={i}
                            className="border-b border-card-border last:border-0 hover:bg-surface"
                          >
                            <td className="px-4 py-2 text-text-muted">
                              {new Date(trade.ts * 1000).toLocaleString()}
                            </td>
                            <td className="px-4 py-2 font-mono text-text-primary text-[10.5px]">
                              {trade.ticker}
                            </td>
                            <td className="px-4 py-2">
                              <span
                                className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                  trade.side === "YES"
                                    ? "bg-[#f0fdf4] text-profit"
                                    : "bg-[#fef2f2] text-loss"
                                }`}
                              >
                                {trade.side}
                              </span>
                            </td>
                            <td className="px-4 py-2 text-text-primary">{trade.qty}</td>
                            <td className="px-4 py-2 font-mono text-text-primary">
                              {trade.price.toFixed(2)}
                            </td>
                            <td
                              className={`px-4 py-2 font-mono font-semibold ${
                                trade.pnl >= 0 ? "text-profit" : "text-loss"
                              }`}
                            >
                              {trade.pnl >= 0 ? "+" : ""}
                              {trade.pnl.toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
