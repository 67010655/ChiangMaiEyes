// Shared "colour by age" scale for hotspots. Mirrors the marker colouring in
// DashboardMap (hotspotAgeColor) exactly so the legend and the map markers
// never disagree. Newest = hot red, oldest = pale yellow.
//
// NOTE: keep these bands in sync with `hotspotAgeColor` in
// components/DashboardMap.tsx (thresholds at 1/3/5/7 days). Long-term these two
// should be unified to import from here.

export type HotspotAgeBand = {
  id: string;
  label: string;
  sublabel: string;
  color: string;
  /** inclusive lower bound in days since detection */
  minDays: number;
  /** inclusive upper bound in days (Infinity for the oldest band) */
  maxDays: number;
};

export const HOTSPOT_AGE_BANDS: HotspotAgeBand[] = [
  { id: "0-1", label: "0–1 วัน", sublabel: "ใหม่ล่าสุด", color: "#dc2626", minDays: 0, maxDays: 1 },
  { id: "2-3", label: "2–3 วัน", sublabel: "", color: "#f97316", minDays: 1, maxDays: 3 },
  { id: "4-5", label: "4–5 วัน", sublabel: "", color: "#f59e0b", minDays: 3, maxDays: 5 },
  { id: "6-7", label: "6–7 วัน", sublabel: "", color: "#fbbf24", minDays: 5, maxDays: 7 },
  { id: "8+", label: "8+ วัน", sublabel: "เก่าสุด", color: "#fde047", minDays: 7, maxDays: Infinity },
];

export function ageInDays(detectedAt: string, now: Date = new Date()): number {
  const t = new Date(detectedAt).getTime();
  if (Number.isNaN(t)) return 0;
  return Math.max(0, (now.getTime() - t) / 86_400_000);
}

// Matches DashboardMap's hotspotAgeColor thresholds (d <= 1 / 3 / 5 / 7).
export function getAgeColor(detectedAt: string, now?: Date): string {
  const d = ageInDays(detectedAt, now);
  if (d <= 1) return "#dc2626";
  if (d <= 3) return "#f97316";
  if (d <= 5) return "#f59e0b";
  if (d <= 7) return "#fbbf24";
  return "#fde047";
}
