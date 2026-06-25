// DEV-ONLY mock data. Used as the fallback/initial state when running
// `npm run dev` with no backend, so charts render with realistic numbers.
// Gated behind import.meta.env.DEV in App.tsx — never ships in production.
import type { DashboardResponse, HistoryResponse, Hotspot } from "./types";

const DAY = 86_400_000;
const now = Date.now();

const districtLanduse: Record<string, string> = {
  อมก๋อย: "forest",
  แม่แจ่ม: "forest",
  ฮอด: "crops",
  เชียงดาว: "shrub",
  แม่แตง: "grass",
  จอมทอง: "crops",
  ดอยเต่า: "bare",
  สันทราย: "built",
};
const perDistrict = [38, 31, 24, 19, 14, 11, 7, 4];

const items: Hotspot[] = [];
Object.keys(districtLanduse).forEach((district, di) => {
  const landuse = districtLanduse[district];
  for (let i = 0; i < perDistrict[di]; i += 1) {
    const ageDays = (i % 9) + Math.random();
    items.push({
      id: `${district}-${i}`,
      latitude: 18.2 + Math.random() * 0.9,
      longitude: 98.2 + Math.random() * 0.9,
      district,
      landuse_type: landuse,
      landuse_name: landuse,
      confidence: 60 + Math.round(Math.random() * 40),
      frp: 10 + Math.round(Math.random() * 150),
      brightness: 300 + Math.round(Math.random() * 80),
      source: "NASA FIRMS",
      detected_at: new Date(now - ageDays * DAY).toISOString(),
    });
  }
});

export const mockDashboard = {
  hotspots: {
    count: items.length,
    density_per_100_km2: 9.4,
    latest_update: new Date(now).toISOString(),
    source: "NASA FIRMS (mock)",
    items,
  },
  pm25: {
    current_pm25: 34,
    category: "ปานกลาง",
    color: "yellow",
    trend: "rising",
    latest_update: new Date(now).toISOString(),
    source: "Air4Thai (mock)",
    stations: [],
  },
  weather: {
    wind_speed_kmh: 6,
    wind_direction_deg: 45,
    wind_direction_text: "ตะวันออกเฉียงเหนือ",
    temperature_c: 33,
    humidity_percent: 48,
    latest_update: new Date(now).toISOString(),
    source: "TMD (mock)",
  },
  risk: { score: 6, category: "Medium", formula: "", factors: {} },
  summary: { language: "th", text: "", source: "" },
  intelligence: {
    hotspot_trend: {
      window_days: 7,
      recent_count: 148,
      previous_count: 120,
      change_percent: 23,
      source: "history",
    },
    drought_zones: [],
    landuse_breakdown: [
      { landuse_type: "forest", label: "ป่าไม้ · Forest", count: 93, percent: 63 },
      { landuse_type: "crops", label: "เกษตร · Crops", count: 31, percent: 21 },
      { landuse_type: "shrub", label: "พุ่มไม้ · Shrub", count: 12, percent: 8 },
      { landuse_type: "grass", label: "หญ้า · Grass", count: 7, percent: 5 },
      { landuse_type: "built", label: "สิ่งปลูกสร้าง · Built", count: 4, percent: 3 },
    ],
    weekly_forest_league: {
      week_id: "2026-W25",
      scoring_window: "2026-06-21 to 2026-06-27",
      scheduled_recompute: "คำนวณใหม่ทุกวันอาทิตย์ 23:55 น.",
      rate_limit_rule: "รับรายงานกิจกรรมภาคสนามได้ 1 ครั้งต่อป่าชุมชน/หมู่บ้าน/วัน",
      ranking: [
        {
          forest_id: "forest-1",
          forest_name: "ป่าชุมชนบ้านปง",
          village: "บ้านปง",
          tambon: "บ้านปง",
          amphoe: "หางดง",
          latitude: 18.723,
          longitude: 98.854,
          total_score: 95,
          rank: 1,
          report_count: 5,
          last_report_at: new Date(now - 12 * 3600 * 1000).toISOString(),
          score_breakdown: { management: 25, prevention: 25, utilization: 20, ecological_outcome: 25 },
          reasons: ["ทำแนวกันไฟ 5.2 กม.", "ลาดตระเวนร่วม 3 ครั้ง"],
        },
        {
          forest_id: "forest-2",
          forest_name: "ป่าชุมชนดอยสุเทพ",
          village: "ศรีวิชัย",
          tambon: "สุเทพ",
          amphoe: "เมืองเชียงใหม่",
          latitude: 18.804,
          longitude: 98.921,
          total_score: 88,
          rank: 2,
          report_count: 3,
          last_report_at: new Date(now - 24 * 3600 * 1000).toISOString(),
          score_breakdown: { management: 20, prevention: 25, utilization: 20, ecological_outcome: 23 },
          reasons: ["ดับไฟป่าเฉียบพลัน 2 จุด", "แนวกันไฟ 3.0 กม."],
        },
        {
          forest_id: "forest-3",
          forest_name: "ป่าชุมชนบ้านทา",
          village: "บ้านทา",
          tambon: "ทาทุ่งหลวง",
          amphoe: "แม่ทา",
          latitude: 18.521,
          longitude: 98.712,
          total_score: 82,
          rank: 3,
          report_count: 2,
          last_report_at: new Date(now - 48 * 3600 * 1000).toISOString(),
          score_breakdown: { management: 20, prevention: 20, utilization: 20, ecological_outcome: 22 },
          reasons: ["ลาดตระเวนร่วม 2 ครั้ง", "ประชาสัมพันธ์งดเผา"],
        },
      ],
    },
    localizedPredictions: [],
    source_notes: [],
  },
} as unknown as DashboardResponse;

export const mockHistory = {
  days: 14,
  hotspots: Array.from({ length: 14 }, (_, i) => ({
    date: new Date(now - (13 - i) * DAY).toISOString().slice(0, 10),
    count: [12, 9, 14, 22, 31, 18, 11, 8, 15, 27, 41, 33, 24, 19][i],
  })),
  pm25: Array.from({ length: 14 }, (_, i) => ({
    date: new Date(now - (13 - i) * DAY).toISOString().slice(0, 10),
    value: [28, 25, 31, 40, 52, 44, 33, 27, 35, 48, 61, 50, 41, 36][i],
  })),
  weather: [],
  sources: {},
  latest_update: new Date(now).toISOString(),
} as unknown as HistoryResponse;
