// dashboard/ui/src/hooks/useStrategyState.ts
import { useState, useCallback } from "react";
import type { StrategySnapshot, WsMessage } from "../types";
import { useWebSocket } from "./useWebSocket";

export type SnapshotMap = Record<string, StrategySnapshot>;

export function useStrategyState(): SnapshotMap {
  const [snapshots, setSnapshots] = useState<SnapshotMap>({});

  const handleMessage = useCallback((msg: WsMessage) => {
    setSnapshots((prev) => {
      const next = { ...prev };
      for (const snap of msg.snapshots) {
        next[snap.strategy] = snap;
      }
      return next;
    });
  }, []);

  useWebSocket(handleMessage);

  return snapshots;
}
