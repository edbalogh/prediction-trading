// dashboard/ui/src/api/client.ts
import type { StrategySummary } from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`);
  if (!resp.ok) throw new Error(`GET ${path} failed: ${resp.status}`);
  return resp.json() as Promise<T>;
}

export const api = {
  strategies: (): Promise<StrategySummary[]> => get("/strategies"),
};
