import { describe, expect, test } from 'vitest';
import { buildDataStatusFromDashboard, getDataStatusCopy } from './dataStatus';
import type { DashboardResponse, DataStatusResponse } from './types';

const status: DataStatusResponse = {
  mode: 'local-refresh-snapshot',
  latest_update: '2026-06-03T00:43:25+07:00',
  snapshot_age_minutes: 36,
  hotspot_count: 18,
  source: 'Royal Forest Department Firemap + NASA FIRMS',
  source_breakdown: {
    'Royal Forest Department Firemap': 14,
    'NASA FIRMS': 8,
  },
  local_refresh_required: true,
  vercel_fetches_rfd_directly: false,
  notes: [],
};

describe('getDataStatusCopy', () => {
  test('explains the local snapshot refresh mode', () => {
    const copy = getDataStatusCopy(status);

    expect(copy.modeLabel).toBe('Snapshot จากเครื่องไทย');
    expect(copy.ageLabel).toBe('36 นาที');
    expect(copy.breakdownLabel).toBe('Royal Forest Department Firemap 14 · NASA FIRMS 8');
    expect(copy.detail).toContain('Vercel ไม่ได้ดึง RFD สดโดยตรง');
  });
});

describe('buildDataStatusFromDashboard', () => {
  test('derives a snapshot status when the status endpoint is unavailable', () => {
    const dashboard = {
      hotspots: {
        count: 18,
        density_per_100_km2: 0.09,
        latest_update: '2026-06-03T00:19:27+07:00',
        source: 'Royal Forest Department Firemap + NASA FIRMS',
        items: [],
        source_breakdown: { NASA: 8 },
      },
      pm25: {
        current_pm25: 18,
        category: 'good',
        color: 'green',
        trend: 'stable',
        latest_update: '2026-06-03T00:00:00+07:00',
        source: 'Air4Thai',
        stations: [],
      },
      weather: {
        wind_speed_kmh: 2,
        wind_direction_deg: 349,
        wind_direction_text: 'north',
        temperature_c: 25,
        humidity_percent: 90,
        latest_update: '2026-06-03T00:43:25+07:00',
        source: 'Open-Meteo',
      },
      risk: { score: 2, category: 'Low', formula: 'test', factors: {} },
      summary: { language: 'th', text: 'test', source: 'fallback' },
    } satisfies DashboardResponse;

    const derived = buildDataStatusFromDashboard(dashboard, new Date('2026-06-03T01:13:25+07:00'));

    expect(derived.latest_update).toBe('2026-06-03T00:43:25+07:00');
    expect(derived.snapshot_age_minutes).toBe(30);
    expect(derived.hotspot_count).toBe(18);
    expect(derived.vercel_fetches_rfd_directly).toBe(false);
  });
});
