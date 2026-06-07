import type { DashboardResponse, DataStatusResponse } from './types';

function formatAge(minutes: number) {
  if (minutes < 60) return `${minutes} นาที`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest === 0 ? `${hours} ชม.` : `${hours} ชม. ${rest} นาที`;
}

function formatBreakdown(sourceBreakdown?: Record<string, number>) {
  const entries = Object.entries(sourceBreakdown ?? {});
  if (entries.length === 0) return 'ไม่มี source breakdown';
  return entries.map(([source, count]) => `${source} ${count}`).join(' · ');
}

export function getDataStatusCopy(status: DataStatusResponse) {
  const modeLabel = status.mode === 'local-refresh-snapshot' ? 'ข้อมูลสำรองจากเครื่องไทย' : 'ข้อมูลสดจากเซิร์ฟเวอร์';
  const detail = status.vercel_fetches_rfd_directly
    ? 'Vercel backend ดึงข้อมูลจาก upstream ได้โดยตรง'
    : 'Vercel ไม่ได้ดึง RFD สดโดยตรง ข้อมูลมาจาก refresh worker บนเครื่องไทยแล้ว push snapshot ขึ้น production';

  return {
    modeLabel,
    ageLabel: formatAge(status.snapshot_age_minutes),
    breakdownLabel: formatBreakdown(status.source_breakdown),
    detail,
  };
}

export function buildDataStatusFromDashboard(dashboard: DashboardResponse, now = new Date()): DataStatusResponse {
  const sortedUpdates = [
    dashboard.hotspots.latest_update,
    dashboard.pm25.latest_update,
    dashboard.weather.latest_update,
  ].sort((a, b) => new Date(a).getTime() - new Date(b).getTime());
  const latestUpdate = sortedUpdates[sortedUpdates.length - 1] ?? dashboard.hotspots.latest_update;
  const ageMs = Math.max(0, now.getTime() - new Date(latestUpdate).getTime());

  return {
    mode: 'local-refresh-snapshot',
    latest_update: latestUpdate,
    snapshot_age_minutes: Math.round(ageMs / 60_000),
    hotspot_count: dashboard.hotspots.count,
    source: dashboard.hotspots.source,
    source_breakdown: dashboard.hotspots.source_breakdown,
    local_refresh_required: true,
    vercel_fetches_rfd_directly: false,
    notes: [],
  };
}
