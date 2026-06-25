import { useCallback, useEffect, useState } from "react";

import { fetchDashboard, fetchHistory } from "../lib/api";
import { mockDashboard, mockHistory } from "../lib/devMock";
import type { DashboardResponse, HistoryResponse } from "../lib/types";

const DEV = import.meta.env.DEV;

export type DashboardState = {
  dashboard: DashboardResponse;
  history: HistoryResponse | null;
  loading: boolean;
  error: string | null;
  updatedAt: Date;
  refresh: () => void;
};

// Single source of dashboard data. In dev (no backend) it falls back to mock
// data so the UI renders fully; in prod it fetches the live API.
export function useDashboard(): DashboardState {
  const [dashboard, setDashboard] = useState<DashboardResponse>(
    DEV ? mockDashboard : mockDashboard,
  );
  const [history, setHistory] = useState<HistoryResponse | null>(
    DEV ? mockHistory : null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState(new Date());

  const refresh = useCallback(() => {
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
      .catch(() => {
        /* keep existing history (mock in dev) on failure */
      });
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { dashboard, history, loading, error, updatedAt, refresh };
}
