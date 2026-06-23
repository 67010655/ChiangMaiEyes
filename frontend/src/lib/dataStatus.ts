import type { DashboardResponse, DataStatusResponse } from './types';

const HOTSPOT_WATCH_MINUTES = 75;
const HOTSPOT_STALE_MINUTES = 180;

export type FreshnessLevel = 'fresh' | 'watch' | 'stale';

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

export function getHotspotAgeMinutes(status: DataStatusResponse) {
  return status.hotspot_age_minutes ?? status.snapshot_age_minutes;
}

function getFreshnessAgeMinutes(status: DataStatusResponse) {
  return Math.max(
    getHotspotAgeMinutes(status),
    status.refresh_age_minutes ?? 0,
  );
}

export function getHotspotLatestUpdate(status: DataStatusResponse) {
  return status.hotspot_latest_update ?? status.latest_update;
}

export function getDataFreshnessState(status: DataStatusResponse) {
  const hotspotAgeMinutes = getHotspotAgeMinutes(status);
  const freshnessAgeMinutes = getFreshnessAgeMinutes(status);
  const workerIsPartial = Boolean(status.refresh_status && status.refresh_status !== 'ok');
  const level: FreshnessLevel =
    workerIsPartial || freshnessAgeMinutes > HOTSPOT_STALE_MINUTES
      ? 'stale'
      : freshnessAgeMinutes > HOTSPOT_WATCH_MINUTES
        ? 'watch'
        : 'fresh';

  const label =
    level === 'fresh'
      ? 'ตรวจล่าสุด'
      : level === 'watch'
        ? 'ควรตรวจซ้ำ'
        : 'ข้อมูลค้าง';

  const title =
    level === 'fresh'
      ? 'Hotspot สดจากรอบ refresh ล่าสุด'
      : level === 'watch'
        ? 'Hotspot เริ่มเก่า ตรวจสอบก่อนใช้ตัดสินใจ'
        : 'Hotspot เก่าเกินเกณฑ์ ห้ามถือว่า realtime';

  return {
    level,
    label,
    title,
    hotspotAgeMinutes,
    hotspotAgeLabel: formatAge(hotspotAgeMinutes),
    hotspotLatestUpdate: getHotspotLatestUpdate(status),
    pm25AgeLabel:
      typeof status.pm25_age_minutes === 'number'
        ? formatAge(status.pm25_age_minutes)
        : formatAge(status.snapshot_age_minutes),
    weatherAgeLabel:
      typeof status.weather_age_minutes === 'number'
        ? formatAge(status.weather_age_minutes)
        : formatAge(status.snapshot_age_minutes),
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
    hotspot_latest_update: dashboard.hotspots.latest_update,
    hotspot_age_minutes: Math.round(Math.max(0, now.getTime() - new Date(dashboard.hotspots.latest_update).getTime()) / 60_000),
    pm25_latest_update: dashboard.pm25.latest_update,
    pm25_age_minutes: Math.round(Math.max(0, now.getTime() - new Date(dashboard.pm25.latest_update).getTime()) / 60_000),
    weather_latest_update: dashboard.weather.latest_update,
    weather_age_minutes: Math.round(Math.max(0, now.getTime() - new Date(dashboard.weather.latest_update).getTime()) / 60_000),
    hotspot_count: dashboard.hotspots.count,
    source: dashboard.hotspots.source,
    source_breakdown: dashboard.hotspots.source_breakdown,
    local_refresh_required: true,
    vercel_fetches_rfd_directly: false,
    data_quality: dashboard.data_quality,
    notes: [],
  };
}
