// dashboard/ui/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { StrategyPage } from "./pages/StrategyPage";
import { useStrategyState } from "./hooks/useStrategyState";
import { api } from "./api/client";
import type { StrategySummary } from "./types";

function BacktestPlaceholder({ title }: { title: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full text-text-muted gap-2">
      <p className="text-lg font-semibold">{title}</p>
      <p className="text-sm">Coming in Stage 3</p>
    </div>
  );
}

export function App() {
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const snapshots = useStrategyState();

  useEffect(() => {
    api.strategies().then(setStrategies).catch(console.error);
    const id = setInterval(() => {
      api.strategies().then(setStrategies).catch(console.error);
    }, 5_000);
    return () => clearInterval(id);
  }, []);

  const defaultStrategy = strategies[0]?.name;

  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden bg-surface">
        <Sidebar strategies={strategies} />
        <main className="flex-1 overflow-hidden flex flex-col">
          <Routes>
            <Route
              path="/"
              element={
                defaultStrategy ? (
                  <Navigate to={`/strategy/${defaultStrategy}`} replace />
                ) : (
                  <div className="flex items-center justify-center h-full text-text-muted">
                    Loading strategies...
                  </div>
                )
              }
            />
            <Route
              path="/strategy/:name"
              element={<StrategyPage strategies={strategies} snapshots={snapshots} />}
            />
            <Route path="/backtest" element={<BacktestPlaceholder title="Run Backtest" />} />
            <Route path="/backtest/history" element={<BacktestPlaceholder title="Backtest History" />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
