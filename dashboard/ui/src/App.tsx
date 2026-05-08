// dashboard/ui/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { Sidebar } from "./components/Sidebar";
import { StrategyPage } from "./pages/StrategyPage";
import { BacktestPage } from "./pages/BacktestPage";
import { useStrategyState } from "./hooks/useStrategyState";
import { api } from "./api/client";
import type { StrategySummary } from "./types";

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
            <Route
              path="/strategy/:name/backtests"
              element={<BacktestPage strategies={strategies} />}
            />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
