import { useCallback, useEffect, useRef, useState } from "react";

import { fetchDashboard, fetchHistory } from "../lib/api";
import { mockDashboard, mockHistory } from "../lib/devMock";
import type { DashboardResponse, HistoryResponse } from "../lib/types";

export type DashboardState = {
  dashboard: DashboardResponse;
  history: HistoryResponse | null;
  loading: boolean;
  error: string | null;
  updatedAt: Date;
  refresh: () => void;
  demoMode: boolean;
  setDemoMode: (v: boolean) => void;
};

export function useDashboard(): DashboardState {
  const [dashboard, setDashboard] = useState<DashboardResponse>(mockDashboard);
  const [history, setHistory] = useState<HistoryResponse | null>(mockHistory);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState(new Date());
  const [demoMode, setDemoModeState] = useState(false);
  const demoRef = useRef(false);

  const refresh = useCallback(() => {
    if (demoRef.current) return;
    setLoading(true);
    setError(null);
    fetchDashboard()
      .then((data) => {
        setDashboard(data);
        setUpdatedAt(new Date());
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "โหลดข้อมูลไม่สำเร็จ");
      })
      .finally(() => setLoading(false));
    fetchHistory()
      .then(setHistory)
      .catch(() => {});
  }, []);

  const setDemoMode = useCallback((v: boolean) => {
    demoRef.current = v;
    setDemoModeState(v);
    if (v) {
      setDashboard(mockDashboard);
      setHistory(mockHistory);
      setError(null);
    } else {
      refresh();
    }
  }, [refresh]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { dashboard, history, loading, error, updatedAt, refresh, demoMode, setDemoMode };
}
