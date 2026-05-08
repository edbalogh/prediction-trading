// dashboard/ui/src/api/client.ts
import type { StrategySummary, StrategyConfig, BacktestRun, BacktestDetail } from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) throw new Error(`GET ${path} failed: ${resp.status}`);
  return resp.json() as Promise<T>;
}

async function post<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(`POST ${path} failed: ${resp.status} — ${JSON.stringify(detail)}`);
  }
  return resp.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(`POST ${path} failed: ${resp.status} — ${JSON.stringify(detail)}`);
  }
  return resp.json() as Promise<T>;
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(`PUT ${path} failed: ${resp.status} — ${JSON.stringify(detail)}`);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  strategies: (): Promise<StrategySummary[]> => get("/strategies"),
  startStrategy: (name: string, mode: "paper" | "live"): Promise<{ status: string }> =>
    post(`/strategies/${name}/start?mode=${mode}`),
  stopStrategy: (name: string): Promise<{ status: string }> =>
    post(`/strategies/${name}/stop`),
  getConfig: (name: string): Promise<StrategyConfig> => get(`/strategies/${name}/config`),
  putConfig: (
    name: string,
    values: Record<string, number | boolean | string>
  ): Promise<{ status: string }> => put(`/strategies/${name}/config`, values),
  startBacktest: (
    name: string,
    body: { start_date: string; end_date: string; overrides: Record<string, number | boolean | string> }
  ): Promise<{ run_id: string; status: string }> =>
    postJson(`/strategies/${name}/backtests`, body),
  listBacktests: (name: string): Promise<BacktestRun[]> =>
    get(`/strategies/${name}/backtests`),
  getBacktest: (runId: string): Promise<BacktestDetail> =>
    get(`/backtests/${runId}`),
  exportBacktestUrl: (runId: string): string => `${BASE}/backtests/${runId}/export`,
};
