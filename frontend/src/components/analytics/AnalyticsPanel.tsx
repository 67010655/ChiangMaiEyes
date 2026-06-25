import "./analytics.css";

import type { DashboardResponse, HistoryResponse } from "../../lib/types";
import { StatTiles } from "./StatTiles";
import { DailyTrendChart } from "./DailyTrendChart";
import { BarChartH, type BarItem } from "./BarChartH";

type AnalyticsPanelProps = {
  dashboard: DashboardResponse;
  history: HistoryResponse | null;
};

// Colours for the landcover breakdown, keyed by substring of the type/label.
function landcoverColor(typeOrLabel: string): string {
  const k = typeOrLabel.toLowerCase();
  if (k.includes("forest") || k.includes("tree") || k.includes("ป่า")) return "#16a34a";
  if (k.includes("shrub") || k.includes("scrub") || k.includes("พุ่ม")) return "#a16207";
  if (k.includes("grass") || k.includes("หญ้า")) return "#65a30d";
  if (k.includes("crop") || k.includes("เกษตร") || k.includes("พืช")) return "#eab308";
  if (k.includes("bare") || k.includes("โล่ง") || k.includes("ดิน")) return "#d6b88a";
  if (k.includes("built") || k.includes("เมือง") || k.includes("สิ่งปลูก")) return "#8b5cf6";
  return "#16a34a";
}

function byDistrict(dashboard: DashboardResponse): BarItem[] {
  const counts = new Map<string, number>();
  for (const h of dashboard.hotspots.items) {
    const d = h.district || "ไม่ระบุ";
    counts.set(d, (counts.get(d) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([label, value]) => ({ label, value, color: "#ea580c" }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 8);
}

function byLandcover(dashboard: DashboardResponse): BarItem[] {
  const breakdown = dashboard.intelligence?.landuse_breakdown ?? [];
  return breakdown
    .slice()
    .sort((a, b) => b.count - a.count)
    .map((item) => ({
      label: item.label,
      value: item.count,
      color: landcoverColor(item.landuse_type || item.label),
    }));
}

// Left analytics column of the reference-style dashboard. Every widget is fed
// by real dashboard/history data — no simulated series.
export function AnalyticsPanel({ dashboard, history }: AnalyticsPanelProps) {
  const districtBars = byDistrict(dashboard);
  const landcoverBars = byLandcover(dashboard);

  return (
    <div className="analytics-panel">
      <StatTiles
        hotspotCount={dashboard.hotspots.count}
        densityPer100Km2={dashboard.hotspots.density_per_100_km2}
        pm25={dashboard.pm25}
        risk={dashboard.risk}
        weather={dashboard.weather}
      />

      <DailyTrendChart days={history?.hotspots ?? []} />

      <BarChartH
        title="จุดความร้อนตามประเภทพื้นที่ · By Landcover"
        icon="🌲"
        items={landcoverBars}
        unit=" จุด"
        emptyText="ยังไม่มีข้อมูลการใช้ที่ดิน"
      />

      <BarChartH
        title="จุดความร้อนรายอำเภอ · By District"
        icon="📍"
        items={districtBars}
        unit=" จุด"
        emptyText="ยังไม่มีจุดความร้อนในพื้นที่"
      />
    </div>
  );
}
