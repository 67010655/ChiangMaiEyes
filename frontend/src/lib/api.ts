import type { DashboardResponse, DataStatusResponse, HistoryResponse, HotspotHistoryResponse } from './types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export async function fetchDashboard(): Promise<DashboardResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15_000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/dashboard`, {
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Dashboard API failed with ${response.status}`);
    }

    return response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchHotspotHistory(): Promise<HotspotHistoryResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 20_000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/hotspots/history`, {
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Hotspot history API failed with ${response.status}`);
    }

    return response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchHistory(): Promise<HistoryResponse> {
  const controller = new AbortController();
  // First (uncached) call chains several upstream requests, so allow ~35s.
  const timeoutId = setTimeout(() => controller.abort(), 35_000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/history`, {
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`History API failed with ${response.status}`);
    }

    return response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchDataStatus(): Promise<DataStatusResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 15_000);

  try {
    const response = await fetch(`${API_BASE_URL}/api/data-status`, {
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Data status API failed with ${response.status}`);
    }

    return response.json();
  } finally {
    clearTimeout(timeoutId);
  }
}
