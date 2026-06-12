import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  Award,
  BookOpen,
  CalendarDays,
  ClipboardList,
  CloudSun,
  Database,
  ExternalLink,
  Flame,
  Home,
  Info,
  MapPin,
  RefreshCcw,
  Send,
  ShieldCheck,
  Trophy,
  Wind,
  Sun,
  Cloud,
  CloudRain,
  AlertTriangle,
  Thermometer,
  Droplets,
  Eye,
  Compass,
  Phone,
  MessageSquare,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

import { fetchDashboard, fetchDataStatus, fetchHistory } from "./lib/api";

import {
  buildDataStatusFromDashboard,
  getDataStatusCopy,
} from "./lib/dataStatus";

import {
  getDistanceKm,
  initialSelection,
  type MapSelection,
} from "./lib/mapSelection";

import { riskPercent } from "./lib/risk";

import type {
  DashboardResponse,
  DataStatusResponse,
  HistoryResponse,
  OperationalIntelligenceResponse,
  WeeklyForestRankingEntry,
} from "./lib/types";

import dashboardSnapshot from "./data/dashboardSnapshot.json";

import districtsGeoData from "./data/chiangmai-districts.json";

import communityForestData from "./data/community-forests-prototype.json";

import fireZoneData from "./data/fire-management-zones-prototype.json";

import { windDestinationName, getBearing } from "./lib/wind";

import { getDistrictPhysics, calculateRateOfSpread } from "./lib/firePhysics";

const DashboardMap = lazy(() =>
  import("./components/DashboardMap").then((module) => ({
    default: module.DashboardMap,
  })),
);

const AiAdvisor = lazy(() =>
  import("./components/AiAdvisor").then((module) => ({
    default: module.AiAdvisor,
  })),
);

type LayerState = {
  hotspots: boolean;

  pm25: boolean;

  wind: boolean;

  landmarks: boolean;

  fuelRisk: boolean;

  communityForests: boolean;

  fireZones: boolean;

  predictions: boolean;
};

const fallback = dashboardSnapshot as DashboardResponse;

type CommunityForestSummary = {
  generatedAt?: string;

  officialInfographicCount: number;

  officialInfographicAreaRai: number;

  rfdCoordinatePoints: number;

  thaicfnetDetailedForests: number;

  thaicfnetGeocodedForests: number;

  detailedForestsWithFireManagement: number;
};

type PrototypeZone = {
  district: string;

  health: "Green" | "Yellow" | "Red";

  healthScore: number;

  rfdCoordinatePoints: number;

  detailedForests: number;

  fireManagementForests: number;

  estimatedAreaRai: number;
};

type CommunityForestPrototype = {
  id: string;

  name: string;

  village: string;

  tambon: string;

  amphoe: string;

  areaRai: number;

  fireManagement: boolean;

  fireActivities: string[];

  managementPlan: boolean;

  committeeTotal: number;

  lat: number;

  lng: number;
};

const communityForestSummary = (
  communityForestData as { summary: CommunityForestSummary }
).summary;

const communityForests = (
  communityForestData as { forests: CommunityForestPrototype[] }
).forests;

const prototypeZones = (fireZoneData as { zones: PrototypeZone[] }).zones;

const operatorIntelligenceFallback: OperationalIntelligenceResponse = {
  annual_hotspot_stats: {
    this_year_count: 43731,
    last_year_count: 51280,
    change_percent: -14.7,
    source: "ข้อมูลจำลองเทียบจุดความร้อนสะสมจากแนว GISTDA/TAMFIRE",
  },
  drought_zones: [
    {
      id: "dry-mae-chaem",
      location_name: "สันเขาฝั่งตะวันตก อ.แม่แจ่ม",
      latitude: 18.503,
      longitude: 98.361,
      soil_moisture_percent: 18,
      drought_index: 0.78,
      trend: "drying",
      risk_level: "high",
    },
    {
      id: "dry-samoeng",
      location_name: "แนวสะสมเชื้อเพลิง อ.สะเมิง",
      latitude: 18.849,
      longitude: 98.73,
      soil_moisture_percent: 16.2,
      drought_index: 0.83,
      trend: "drying",
      risk_level: "critical",
    },
  ],
  landuse_breakdown: [
    { landuse_type: "NRF", label: "ป่าสงวนแห่งชาติ", count: 5, percent: 62.5 },
    { landuse_type: "CONSERVATION", label: "ป่าอนุรักษ์", count: 1, percent: 12.5 },
    { landuse_type: "AGRI", label: "พื้นที่เกษตร", count: 1, percent: 12.5 },
    { landuse_type: "OTHER", label: "ชุมชนและอื่น ๆ", count: 1, percent: 12.5 },
  ],
  weekly_forest_league: {
    week_id: "2026-06-07",
    scoring_window: "2026-06-07 to 2026-06-13",
    scheduled_recompute: "คำนวณใหม่ทุกวันอาทิตย์ 23:55 น. เวลาไทย",
    rate_limit_rule: "รับรายงานกิจกรรมภาคสนามได้ 1 ครั้งต่อป่าชุมชน/หมู่บ้าน/วัน",
    ranking: [
      {
        forest_id: "cf-mae-chaem-001",
        forest_name: "ป่าชุมชนแม่แจ่ม",
        village: "บ้านแม่ปาน",
        tambon: "ช่างเคิ่ง",
        amphoe: "แม่แจ่ม",
        latitude: 18.503,
        longitude: 98.361,
        total_score: 94,
        rank: 1,
        report_count: 1,
        last_report_at: "2026-06-07T07:30:00+07:00",
        score_breakdown: {
          management: 25,
          prevention: 29,
          utilization: 20,
          ecological_outcome: 20,
        },
        reasons: ["ลาดตระเวน", "แนวกันไฟ", "จัดการเชื้อเพลิง", "ข้อตกลงงดเผา"],
      },
    ],
  },
  localizedPredictions: [
    {
      id: "pred-smoke-mae-chaem",
      locationName: "บ้านแม่ปาน อ.แม่แจ่ม",
      latitude: 18.503,
      longitude: 98.361,
      forecastType: "dust",
      severity: "high",
      lead_time_hours: 12,
      reason_for_prediction:
        "PM2.5 อาจเพิ่มขึ้นใน 12 ชั่วโมง เพราะลมพาควันเข้าสู่หมู่บ้านในหุบเขา จุดความร้อนใกล้เคียงและการระบายอากาศต่ำทำให้เสี่ยงรับควันมากขึ้น",
    },
    {
      id: "pred-fire-samoeng",
      locationName: "บ้านแม่สาบ อ.สะเมิง",
      latitude: 18.849,
      longitude: 98.73,
      forecastType: "fire",
      severity: "critical",
      lead_time_hours: 24,
      reason_for_prediction:
        "ความเสี่ยงไฟลามสูง เพราะความชื้นดินต่ำ เชื้อเพลิงแห้ง และรายงานภาคสนามสัปดาห์นี้ยังพบงานจัดการเชื้อเพลิงค้างอยู่",
    },
  ],
  source_notes: [
    "เป็นข้อมูลจำลองชั่วคราวระหว่างรอเชื่อมข้อมูลรอยไหม้ ความถี่การไหม้จาก GISTDA และค่าภัยแล้งจาก TAMFIRE",
  ],
};

function forecastTypeLabel(value: string) {
  return value === "fire" ? "ไฟป่า" : value === "dust" ? "ฝุ่น" : value;
}

function severityLabel(value: string) {
  if (value === "critical") return "วิกฤต";
  if (value === "high") return "สูง";
  if (value === "medium") return "ปานกลาง";
  if (value === "watch") return "เฝ้าระวัง";
  return value;
}

function sourceDisplayLabel(value: string) {
  return value
    .replace("Royal Forest Department Firemap", "แผนที่ไฟป่า กรมป่าไม้")
    .replace("GISTDA API Gateway VIIRS 1-day", "GISTDA VIIRS รายวัน")
    .replace("NASA FIRMS", "NASA FIRMS")
    .replace("Air4Thai Live API", "Air4Thai สด")
    .replace("Thai Meteorological Department AWS", "สถานีอุตุนิยมวิทยาไทย");
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatCurrentTime(value: Date) {
  const hours = String(value.getHours()).padStart(2, "0");

  const minutes = String(value.getMinutes()).padStart(2, "0");

  const seconds = String(value.getSeconds()).padStart(2, "0");

  return `${hours}:${minutes}:${seconds}`;
}

function formatCurrentDate(value: Date) {
  return new Intl.DateTimeFormat("th-TH", {
    weekday: "long",

    day: "numeric",

    month: "long",

    year: "numeric",
  }).format(value);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("th-TH").format(value);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat("th-TH", { timeStyle: "short" }).format(
    new Date(value),
  );
}

function weeklyForestScore(forest: CommunityForestPrototype) {
  const activityScore = Math.min(36, forest.fireActivities.length * 12);

  const planScore = forest.managementPlan ? 18 : 0;

  const fireScore = forest.fireManagement ? 16 : 0;

  const committeeScore = Math.min(
    12,
    Math.round((forest.committeeTotal || 0) / 2),
  );

  const areaScore =
    forest.areaRai > 0 ? Math.min(8, Math.round(forest.areaRai / 180)) : 0;

  return Math.min(
    100,
    28 + activityScore + planScore + fireScore + committeeScore + areaScore,
  );
}

function forestScoreReason(forest: CommunityForestPrototype) {
  const reasons = [
    forest.managementPlan ? "มีแผนจัดการ" : "",

    forest.fireActivities.includes("ลาดตระเวนในพื้นที่ป่าชุมชน")
      ? "ลาดตระเวน"
      : "",

    forest.fireActivities.includes("ทำแนวป้องกันไฟป่า") ? "แนวกันไฟ" : "",

    forest.fireActivities.some((item) => item.includes("เชื้อเพลิง"))
      ? "ลดเชื้อเพลิง"
      : "",
  ].filter(Boolean);

  return reasons.length ? reasons.join(" · ") : "รอข้อมูลกิจกรรมจากชุมชน";
}

function prototypeForestRanking(): WeeklyForestRankingEntry[] {
  return communityForests
    .map((forest) => ({
      forest,
      rawScore: weeklyForestScore(forest),
    }))
    .sort((a, b) => b.rawScore - a.rawScore)
    .map(({ forest, rawScore }, index) => {
      const score = Math.max(62, Math.min(90, rawScore - 10 - index * 3));
      return {
        forest_id: forest.id,
        forest_name: forest.name,
        village: forest.village || forest.name,
        tambon: forest.tambon || "ไม่ระบุ",
        amphoe: forest.amphoe || "ไม่ระบุ",
        latitude: forest.lat,
        longitude: forest.lng,
        total_score: score,
        rank: 0,
        report_count: Math.max(1, forest.fireActivities.length),
        last_report_at: `${communityForestSummary.generatedAt || "2026-06-07"}T00:00:00+07:00`,
        score_breakdown: {
          management: forest.managementPlan ? 25 : 12,
          prevention: Math.min(30, forest.fireActivities.length * 10),
          utilization: forest.committeeTotal > 0 ? 18 : 10,
          ecological_outcome: forest.fireManagement ? 20 : 12,
        },
        reasons: forestScoreReason(forest).split(" · "),
      };
    })
    .map((item, index) => ({ ...item, rank: index + 1 }));
}

const dataConnectorCandidates = [
  {
    title: "PM2.5 + โรคที่เกี่ยวข้อง จ.เชียงใหม่",

    source: "สำนักงานสาธารณสุขจังหวัดเชียงใหม่ / data.go.th",

    use: "เสริม proof ว่าพื้นที่ที่ลดไฟได้ ช่วยลดผลกระทบสุขภาพ/ฝุ่นในพื้นที่ได้อย่างไร",

    url: "https://www.data.go.th/dataset/pm2-5",
  },

  {
    title: "ข้อมูลการใช้ที่ดิน",

    source: "กรมพัฒนาที่ดิน / data.go.th",

    use: "ช่วยแยกพื้นที่เกษตร ข้าวโพด ป่า และพื้นที่รอยต่อ เพื่อปรับ Boundary Risk ให้แม่นขึ้น",

    url: "https://www.data.go.th/en/dataset/landuse1",
  },

  {
    title: "ที่ตั้งและสภาพทั่วไปของหมู่บ้าน 76 จังหวัด",

    source: "ฐานข้อมูล GIS หมู่บ้าน / data.go.th",

    use: "จับคู่ป่าชุมชนกับหมู่บ้านรับผิดชอบ และใช้คำนวณระยะจากชุมชนถึง boundary risk",

    url: "https://www.data.go.th/dataset/gis-01",
  },
] as const;

function getRiskTone(score: number) {
  if (score <= 3) return "low";

  if (score <= 6) return "medium";

  return "high";
}

const riskLabelTh: Record<string, string> = {
  low: "ความเสี่ยงต่ำ",

  medium: "ความเสี่ยงปานกลาง",

  high: "ความเสี่ยงสูง",
};

const adviceByColor: Record<string, { heading: string; text: string }> = {
  green: {
    heading: "คุณภาพอากาศดีมาก",

    text: "เหมาะสำหรับกิจกรรมกลางแจ้ง ทำต่อเนื่องได้ตามปกติ และติดตามสถานการณ์เป็นระยะ",
  },

  yellow: {
    heading: "คุณภาพอากาศปานกลาง",

    text: "ทำกิจกรรมกลางแจ้งได้ กลุ่มเสี่ยงควรสังเกตอาการและลดกิจกรรมหนักเป็นเวลานาน",
  },

  orange: {
    heading: "เริ่มมีผลต่อสุขภาพ",

    text: "กลุ่มเสี่ยงควรลดกิจกรรมกลางแจ้ง และสวมหน้ากากป้องกันฝุ่นเมื่อต้องอยู่นอกอาคาร",
  },

  red: {
    heading: "มีผลต่อสุขภาพ",

    text: "ทุกคนควรลดกิจกรรมกลางแจ้ง สวมหน้ากาก N95 และปิดประตูหน้าต่างเมื่ออยู่ในอาคาร",
  },

  purple: {
    heading: "อยู่ในระดับอันตราย",

    text: "งดกิจกรรมกลางแจ้งทั้งหมด อยู่ในอาคารที่ปิดมิดชิด และใช้เครื่องฟอกอากาศหากเป็นไปได้",
  },
};

const REC_ICONS = [Home, BookOpen, MapPin] as const;

type DistrictPreset = { name: string; coords: [number, number] };

type DistrictGeometry = {
  type: "Polygon" | "MultiPolygon";

  coordinates: number[][][] | number[][][][];
};

function districtCenter(geometry: DistrictGeometry): [number, number] {
  const rings =
    geometry.type === "Polygon"
      ? (geometry.coordinates as number[][][])
      : (geometry.coordinates as number[][][][]).flat(1);

  const points = rings.flat();

  const total = points.reduce(
    (acc, point) => ({ lng: acc.lng + point[0], lat: acc.lat + point[1] }),

    { lng: 0, lat: 0 },
  );

  return [total.lat / points.length, total.lng / points.length];
}

const DISTRICT_PRESETS: DistrictPreset[] = (
  (
    districtsGeoData as {
      features: Array<{
        properties?: { nameTh?: string; name?: string };
        geometry: DistrictGeometry;
      }>;
    }
  ).features ?? []
)

  .map((feature) => ({
    name:
      feature.properties?.nameTh ??
      feature.properties?.name ??
      "อำเภอไม่ระบุชื่อ",

    coords: districtCenter(feature.geometry),
  }))

  .sort((a, b) => a.name.localeCompare(b.name, "th"));

function getPm25Color(val: number) {
  if (val <= 25) return "green"; // ดีมาก (≤15) + ดี (≤25) → green

  if (val <= 37.5) return "yellow";

  if (val <= 75) return "orange";

  if (val <= 120) return "red";

  return "purple";
}

function getPm25Label(val: number) {
  if (val <= 15) return "ดีมาก";

  if (val <= 25) return "ดี";

  if (val <= 37.5) return "ปานกลาง";

  if (val <= 75) return "เริ่มมีผลกระทบต่อสุขภาพ";

  if (val <= 120) return "มีผลกระทบต่อสุขภาพ";

  return "อันตราย";
}

function estimateVisibilityKm(pm25: number): string {
  const km = Math.max(1.0, Math.min(10.0, 10.0 - (pm25 / 150.0) * 9.0));

  return km.toFixed(1);
}

function getFireRiskLabel(risk: "low" | "medium" | "high" | "critical") {
  if (risk === "low") return "เสี่ยงต่ำ";

  if (risk === "medium") return "เสี่ยงปานกลาง";

  if (risk === "high") return "เสี่ยงสูง";

  return "วิกฤตอันตราย";
}

function WeatherIcon({
  type,
  size = 20,
}: {
  type: "sun" | "cloud" | "rain";
  size?: number;
}) {
  if (type === "sun") return <Sun size={size} style={{ color: "#f59e0b" }} />;

  if (type === "rain")
    return <CloudRain size={size} style={{ color: "#3b82f6" }} />;

  return <Cloud size={size} style={{ color: "#94a3b8" }} />;
}

function getHourlyForecast(
  temp: number,

  pm25: number,

  windDeg: number,

  windSpeed: number,

  hotspots: number,
) {
  const hours = [];

  const baseTime = new Date();

  for (let i = 1; i <= 8; i++) {
    const forecastTime = new Date(baseTime.getTime() + i * 60 * 60 * 1000);

    const hourStr =
      forecastTime.toLocaleTimeString("th-TH", {
        hour: "2-digit",
        minute: "2-digit",
      }) + " น.";

    const tempOffset = Math.sin((i / 8) * Math.PI) * 3 - 1.5;

    const simulatedTemp = temp + tempOffset;

    const pmOffset = Math.sin((i / 4) * Math.PI) * 10 + i * 0.4;

    const simulatedPm = Math.max(5, Math.round(pm25 + pmOffset));

    const hotspotOffset = Math.round(Math.sin((i / 6) * Math.PI) * 5 + i * 0.2);

    const simulatedHotspots = Math.max(0, hotspots + hotspotOffset);

    const simulatedWindDeg =
      (windDeg + Math.round((Math.random() - 0.5) * 30) + 360) % 360;

    const destName = windDestinationName(simulatedWindDeg);

    let icon: "sun" | "cloud" | "rain" = "sun";

    if (i % 6 === 0) icon = "rain";
    else if (i % 3 === 0) icon = "cloud";

    hours.push({
      time: hourStr,

      temp: simulatedTemp,

      pm25: simulatedPm,

      hotspots: simulatedHotspots,

      windDeg: simulatedWindDeg,

      windSpeed: Math.max(2, Math.round(windSpeed + (Math.random() - 0.5) * 5)),

      smokeDrift: `พัดไป ${destName}`,

      icon,
    });
  }

  return hours;
}

function getDailyForecast(
  temp: number,

  pm25: number,

  windDeg: number,

  hotspots: number,
) {
  const daysTh = [
    "วันอาทิตย์",
    "วันจันทร์",
    "วันอังคาร",
    "วันพุธ",
    "วันพฤหัสบดี",
    "วันศุกร์",
    "วันเสาร์",
  ];

  const todayIdx = new Date().getDay();

  const list = [];

  for (let i = 1; i <= 7; i++) {
    const dayIdx = (todayIdx + i) % 7;

    const dayLabel =
      i === 1 ? "วันพรุ่งนี้" : i === 2 ? "วันมะรืน" : daysTh[dayIdx];

    const minTemp = Math.round(temp - 7 + Math.sin(i) * 2.5);

    const maxTemp = Math.round(temp + 3 + Math.cos(i) * 2.5);

    const pmVal = Math.max(
      10,
      Math.round(pm25 + Math.sin(i / 2) * 15 + i * 0.9),
    );

    let fireRisk: "low" | "medium" | "high" | "critical" = "low";

    if (pmVal > 90) fireRisk = "critical";
    else if (pmVal > 50) fireRisk = "high";
    else if (pmVal > 30) fireRisk = "medium";

    const estHotspotsMin = Math.max(
      0,
      Math.round(hotspots * 0.7 + Math.sin(i) * 6),
    );

    const estHotspotsMax = Math.max(
      estHotspotsMin + 1,
      Math.round(hotspots * 1.4 + Math.cos(i) * 10),
    );

    const simWindDeg = (windDeg + i * 15) % 360;

    const destName = windDestinationName(simWindDeg);

    const smokeDisp = `พัดเข้า ${destName}`;

    let icon: "sun" | "cloud" | "rain" = "sun";

    if (i % 5 === 0) icon = "rain";
    else if (i % 2 === 0) icon = "cloud";

    list.push({
      day: dayLabel,

      tempMin: minTemp,

      tempMax: maxTemp,

      pm25: pmVal,

      fireRisk,

      hotspots: `${estHotspotsMin} - ${estHotspotsMax} จุด`,

      smokeDisp,

      icon,
    });
  }

  return list;
}

function CitizenTravelGuide({ dailyForecast }: { dailyForecast: any[] }) {
  const next3Days = dailyForecast.slice(0, 3);

  return (
    <section className="card citizen-guide-card">
      <div className="card__head">
        <span className="card__title">
          🧭 คู่มือวางแผนการเดินทางและสุขภาพ (3 วันล่วงหน้า)
        </span>
      </div>

      <p className="personal-checker-desc" style={{ marginBottom: "12px" }}>
        คำแนะนำเพื่อการเดินทางและทำกิจกรรมอย่างปลอดภัยตามระดับความเสี่ยงฝุ่นควันและไฟไหม้ป่า
        <br />
        <em style={{ fontSize: "0.75rem", color: "var(--muted)" }}>
          ⚠️ ข้อมูลพยากรณ์อากาศเป็นการประมาณการ
          ไม่ใช่ข้อมูลพยากรณ์จากกรมอุตุนิยมวิทยา
        </em>
      </p>

      <div className="citizen-guide-list">
        {next3Days.map((day, idx) => {
          let healthText =
            "คุณภาพอากาศดีมาก: ท่องเที่ยวและออกกำลังกายกลางแจ้งได้ปกติ";

          let healthColor = "green";

          if (day.pm25 <= 15) {
            healthText = "อากาศดีเยี่ยม: เหมาะกับทุกกิจกรรมกลางแจ้ง";

            healthColor = "green";
          } else if (day.pm25 <= 25) {
            healthText = "อากาศดี: ทำกิจกรรมกลางแจ้งได้ตามปกติ";

            healthColor = "green";
          } else if (day.pm25 <= 37.5) {
            healthText = "อากาศปานกลาง: กลุ่มเสี่ยงควรสังเกตอาการ";

            healthColor = "yellow";
          } else if (day.pm25 <= 75) {
            healthText = "เริ่มมีผลต่อสุขภาพ: สวมหน้ากากอนามัยเมื่อออกกลางแจ้ง";

            healthColor = "orange";
          } else {
            healthText = "มีผลต่อสุขภาพ: งดกิจกรรมกลางแจ้งและสวมหน้ากาก N95";

            healthColor = "red";
          }

          let travelAdvice = "แนะนำท่องเที่ยวได้ตามปกติ";

          let travelIcon = "✅";

          if (day.fireRisk === "critical" || day.pm25 > 75) {
            travelAdvice = "หลีกเลี่ยงการท่องเที่ยวกลางแจ้ง/พื้นที่ใกล้เขตป่า";

            travelIcon = "❌";
          } else if (day.fireRisk === "high" || day.pm25 > 37.5) {
            travelAdvice = "ท่องเที่ยวได้ แต่อยู่ในร่มเป็นหลักและสวมหน้ากาก";

            travelIcon = "⚠️";
          }

          const badgeClass = `hourly-pm-badge badge--${healthColor}`;

          return (
            <div
              key={idx}
              className="citizen-guide-item"
              style={{
                background: "var(--surface-soft)",

                border: "1px solid var(--line)",

                borderRadius: "14px",

                padding: "14px",

                marginBottom: idx < 2 ? "12px" : "0",

                display: "flex",

                flexDirection: "column",

                gap: "8px",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <strong style={{ fontSize: "0.95rem", color: "var(--text)" }}>
                  {day.day}
                </strong>

                <div
                  style={{ display: "flex", alignItems: "center", gap: "6px" }}
                >
                  <WeatherIcon type={day.icon} size={18} />

                  <span style={{ fontSize: "0.8rem", color: "var(--muted)" }}>
                    {day.icon === "sun"
                      ? "แดดจัด/แล้ง"
                      : day.icon === "rain"
                        ? "มีฝน/ชื้น"
                        : "เมฆบางส่วน"}
                  </span>
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "8px",
                  alignItems: "center",
                }}
              >
                <span
                  className={badgeClass}
                  style={{
                    fontSize: "0.75rem",
                    padding: "2px 8px",
                    borderRadius: "99px",
                  }}
                >
                  ฝุ่น {day.pm25} µg/m³
                </span>

                <span style={{ fontSize: "0.82rem", color: "var(--text)" }}>
                  {healthText}
                </span>
              </div>

              <div
                style={{
                  fontSize: "0.8rem",
                  color: "var(--text)",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  borderTop: "1px dashed var(--line)",
                  paddingTop: "6px",
                }}
              >
                <span>{travelIcon}</span>

                <span>
                  <strong>คำแนะนำเดินทาง:</strong> {travelAdvice}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function PollutantsBreakdown({ pm25 }: { pm25: number }) {
  const items = [
    {
      name: "PM2.5",
      value: pm25,
      unit: "µg/m³",
      max: 150,
      color: getPm25Color(pm25),
      isLive: true,
    },

    {
      name: "PM10",
      value: Math.round(pm25 * 1.35),
      unit: "µg/m³",
      max: 200,
      color: getPm25Color(pm25 * 0.8),
      isLive: false,
    },

    {
      name: "CO",
      value: (pm25 * 0.012 + 0.18).toFixed(2),
      unit: "mg/m³",
      max: 10,
      color: "green",
      isLive: false,
    },

    {
      name: "NO2",
      value: Math.round(pm25 * 0.38 + 6),
      unit: "ppb",
      max: 100,
      color: "green",
      isLive: false,
    },

    {
      name: "SO2",
      value: (pm25 * 0.07 + 1.1).toFixed(1),
      unit: "ppb",
      max: 80,
      color: "green",
      isLive: false,
    },

    {
      name: "O3",
      value: Math.round(40 + Math.sin(new Date().getHours() / 12) * 12),
      unit: "ppb",
      max: 120,
      color: "green",
      isLive: false,
    },
  ];

  return (
    <section
      className="card pollutants-bento"
      aria-label="ดัชนีสารมลพิษทางอากาศ"
    >
      <div className="card__head">
        <span className="card__title">
          🔬 สารมลพิษทางอากาศ (Pollutants Index)
        </span>
      </div>

      <p
        style={{
          fontSize: "0.73rem",
          color: "var(--muted)",
          margin: "0 0 10px 0",
        }}
      >
        PM2.5 วัดจริงจาก Air4Thai · PM10 CO NO2 SO2 O3 ประมาณการจาก PM2.5
        (ไม่ใช่ค่าวัดโดยตรง)
      </p>

      <div className="pollutants-grid-layout">
        {items.map((item) => {
          const fillPct = Math.min(
            100,
            (parseFloat(item.value.toString()) / item.max) * 100,
          );

          const colorHex =
            item.color === "green"
              ? "#10b981"
              : item.color === "yellow"
                ? "#f59e0b"
                : item.color === "orange"
                  ? "#f97316"
                  : item.color === "red"
                    ? "#ef4444"
                    : "#8b5cf6";

          return (
            <div key={item.name} className="pollutant-card">
              <span className="pollutant-name">{item.name}</span>

              <strong className="pollutant-value">{item.value}</strong>

              <span className="pollutant-unit">{item.unit}</span>

              <div className="pollutant-bar-track">
                <div
                  className="pollutant-bar-fill"
                  style={{ width: `${fillPct}%`, backgroundColor: colorHex }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function EmergencyContacts() {
  const hotlines = [
    {
      number: "1362",

      title: "สายด่วนดับไฟป่า (24 ชม.)",

      dept: "กรมอุทยานแห่งชาติ สัตว์ป่า และพันธุ์พืช",

      desc: "แจ้งเหตุไฟไหม้ป่าในเขตป่าสงวน/อุทยานแห่งชาติ ฟรีตลอด 24 ชั่วโมง",

      primary: true,
    },

    {
      number: "1784",

      title: "สายด่วนสาธารณภัย ปภ.",

      dept: "กรมป้องกันและบรรเทาสาธารณภัย",

      desc: "แจ้งภัยพิบัติ หมอกควันวิกฤต หรือขอความช่วยเหลือฉุกเฉิน",

      primary: false,
    },

    {
      number: "053-112236",

      title: "ศูนย์ประสานงานไฟป่าเชียงใหม่",

      dept: "ศูนย์บัญชาการแก้ปัญหาไฟป่าและฝุ่น PM2.5",

      desc: "สายตรงประสานงานดับไฟป่าและการเผาในพื้นที่จังหวัดเชียงใหม่",

      primary: false,
    },
  ];

  return (
    <section className="card emergency-contacts-card">
      <div className="card__head" style={{ marginBottom: "12px" }}>
        <span
          className="card__title"
          style={{ display: "flex", alignItems: "center", gap: "8px" }}
        >
          <AlertTriangle size={18} style={{ color: "#f97316" }} />
          📞 สายด่วน & ช่องทางแจ้งเหตุไฟป่าเชียงใหม่
        </span>
      </div>

      <p
        className="personal-checker-desc"
        style={{ marginBottom: "14px", fontSize: "0.82rem" }}
      >
        หากท่านพบเห็นประกายไฟ จุด hotspot หรือแนวควันป่า
        สามารถโทรแจ้งเจ้าหน้าที่หรือส่งพิกัดทาง LINE เพื่อเข้าระงับเหตุได้ทันที
      </p>

      <div className="hotline-list">
        {hotlines.map((h) => (
          <a
            key={h.number}
            href={`tel:${h.number.replace(/-/g, "")}`}
            className={`hotline-item ${h.primary ? "hotline-item--primary" : ""}`}
          >
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "2px",
                minWidth: 0,
                paddingRight: "8px",
              }}
            >
              <span className="hotline-title">{h.title}</span>

              <span className="hotline-dept">{h.dept}</span>

              <span className="hotline-desc">{h.desc}</span>
            </div>

            <div className="hotline-icon-box">
              <Phone size={18} />
            </div>
          </a>
        ))}
      </div>

      <div
        className="line-report-panel"
        style={{
          marginTop: "14px",

          paddingTop: "12px",

          borderTop: "1px dashed var(--line)",

          display: "flex",

          flexDirection: "column",

          gap: "10px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "10px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <div
              style={{
                display: "grid",

                placeItems: "center",

                width: "34px",

                height: "34px",

                borderRadius: "8px",

                background: "#06c755",

                color: "#ffffff",
              }}
            >
              <MessageSquare size={16} />
            </div>

            <div style={{ display: "flex", flexDirection: "column" }}>
              <span style={{ fontSize: "0.8rem", fontWeight: 700 }}>
                LINE ผ่อดีดี (@podd-report)
              </span>

              <span style={{ fontSize: "0.72rem", color: "var(--muted)" }}>
                แจ้งเหตุไฟป่าและเผาในที่โล่ง เชียงใหม่
              </span>
            </div>
          </div>

          <a
            className="line-report-link"
            href="https://line.me/R/ti/p/%40podd-report"
            target="_blank"
            rel="noreferrer"
            style={{
              display: "inline-flex",

              alignItems: "center",

              minHeight: "44px",

              padding: "6px 12px",

              background: "#06c755",

              color: "#ffffff",

              borderRadius: "999px",

              fontSize: "0.78rem",

              fontWeight: 800,

              textDecoration: "none",

              transition: "background 0.15s ease",
            }}
            onMouseOver={(e) => (e.currentTarget.style.background = "#05b04b")}
            onMouseOut={(e) => (e.currentTarget.style.background = "#06c755")}
          >
            เพิ่มเพื่อน LINE
          </a>
        </div>

        <div
          style={{
            background: "var(--surface-soft)",

            padding: "8px 12px",

            borderRadius: "8px",

            border: "1px solid var(--line)",

            fontSize: "0.72rem",

            color: "var(--text)",
          }}
        >
          💡 <strong>ขั้นตอนการแจ้งเหตุสำหรับเชียงใหม่:</strong>
          <br />
          1. เพิ่มเพื่อน LINE และกดเลือก <strong>"ลงทะเบียน"</strong>
          <br />
          2. กรอกรหัสพื้นที่ อบจ.เชียงใหม่:{" "}
          <strong
            style={{
              color: "#f97316",
              fontSize: "0.8rem",
              fontFamily: "monospace",
            }}
          >
            3326113
          </strong>
        </div>
      </div>
    </section>
  );
}

function computeRecommendations(
  pm25: number,
  hotspots: number,
  riskScore: number,
): Array<{ label: string; detail: string }> {
  let r1: string;

  if (pm25 <= 25 && riskScore <= 3) {
    r1 = "ออกจากบ้านได้:อากาศดี เหมาะสำหรับกิจกรรมกลางแจ้งทุกประเภท";
  } else if (pm25 <= 37) {
    r1 = "ออกจากบ้านได้:แนะนำสวมหน้ากากหากออกกำลังกายกลางแจ้งนาน";
  } else if (pm25 <= 50 || riskScore <= 6) {
    r1 = "ออกนอกบ้านด้วยความระมัดระวัง:สวม N95 และลดเวลาอยู่กลางแจ้ง";
  } else {
    r1 = "แนะนำอยู่ในอาคาร:PM2.5 เกินเกณฑ์ปลอดภัย ลดการสัมผัสอากาศภายนอก";
  }

  let r2: string;

  if (pm25 <= 25) {
    r2 = "เด็กไปโรงเรียนได้:คุณภาพอากาศดี ปลอดภัยสำหรับเด็ก";
  } else if (pm25 <= 37) {
    r2 = "เด็กไปโรงเรียนได้:แนะนำสวมหน้ากากและงดกิจกรรมกลางแจ้ง";
  } else if (pm25 <= 50) {
    r2 = "ควรปรึกษาโรงเรียน:PM2.5 เริ่มส่งผลต่อระบบทางเดินหายใจของเด็ก";
  } else {
    r2 = "แนะนำให้เด็กอยู่บ้าน:PM2.5 สูงเกินเกณฑ์ปลอดภัยสำหรับเด็กเล็ก";
  }

  let r3: string;

  if (hotspots === 0) {
    r3 = "เจ้าหน้าที่:ยังไม่พบจุดความร้อน เฝ้าระวังตามปกติ";
  } else if (hotspots <= 10) {
    r3 = `เจ้าหน้าที่:พบ ${hotspots} จุดความร้อน ให้ติดตามพื้นที่ป่าและชายป่า`;
  } else if (hotspots <= 50) {
    r3 = `เจ้าหน้าที่:${hotspots} จุดความร้อน เพิ่มกำลังเฝ้าระวังพื้นที่ป่าและเกษตรชายขอบ`;
  } else {
    r3 = `เจ้าหน้าที่:${hotspots} จุดความร้อน สถานการณ์วิกฤต — ระดมพลทุกพื้นที่หนาแน่น`;
  }

  return [r1, r2, r3].map((s) => {
    const idx = s.indexOf(":");

    return { label: s.slice(0, idx), detail: s.slice(idx + 1) };
  });
}

const PM_SEGMENTS = ["#16a34a", "#eab308", "#f97316", "#dc2626", "#7c3aed"];

const PM_BOUNDS = [0, 25, 37, 50, 90, 150];

const PM_TICKS = [25, 37, 50, 90];

// Map a PM2.5 reading onto an equal-width 5-band category scale so the marker

// lines up with its colour band and the printed thresholds.

function pmScalePercent(value: number) {
  for (let i = 0; i < 5; i += 1) {
    const lo = PM_BOUNDS[i];

    const hi = PM_BOUNDS[i + 1];

    if (value <= hi || i === 4) {
      const t = Math.min(Math.max((value - lo) / (hi - lo), 0), 1);

      return Math.min((i + t) * 20, 100);
    }
  }

  return 100;
}

function Pm25Scale({ value }: { value: number }) {
  // Real category scale: the current reading against published thresholds, not

  // a fabricated time series. The number + badge carry the value for assistive

  // tech, so the bar itself is decorative to a screen reader.

  const pct = pmScalePercent(value);

  return (
    <div className="pm-scale" aria-hidden>
      <div className="pm-scale__bar">
        <div className="pm-scale__track">
          {PM_SEGMENTS.map((color) => (
            <span
              key={color}
              className="pm-scale__seg"
              style={{ background: color }}
            />
          ))}
        </div>

        <span className="pm-scale__marker" style={{ left: `${pct}%` }} />
      </div>

      <div className="pm-scale__ticks">
        {PM_TICKS.map((tick, i) => (
          <span key={tick} style={{ left: `${(i + 1) * 20}%` }}>
            {tick}
          </span>
        ))}
      </div>
    </div>
  );
}

function Sparkline() {
  // Decorative 24h trend placeholder because the backend does not expose a time series yet.

  const points = [10, 9, 11, 8, 12, 9, 8, 10, 9, 13, 10, 9, 11, 8, 9, 10];

  const w = 132;

  const h = 44;

  const max = Math.max(...points);

  const min = Math.min(...points);

  const step = w / (points.length - 1);

  const path = points

    .map((v, i) => {
      const x = i * step;

      const y = h - ((v - min) / (max - min || 1)) * (h - 6) - 3;

      return `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    })

    .join(" ");

  return (
    <div
      style={{ position: "relative" }}
      aria-label="กราฟแนวโน้ม PM2.5 ย้อนหลัง 24 ชั่วโมง (ข้อมูลตัวอย่าง)"
    >
      <svg
        className="sparkline"
        viewBox={`0 0 ${w} ${h}`}
        preserveAspectRatio="none"
        aria-hidden
      >
        <path d={`${path} L${w} ${h} L0 ${h} Z`} className="sparkline__fill" />

        <path d={path} className="sparkline__line" />
      </svg>

      <span
        style={{
          position: "absolute",
          top: 0,
          right: 0,
          fontSize: "0.6rem",
          color: "var(--muted)",
          opacity: 0.7,
        }}
      >
        ตัวอย่าง
      </span>
    </div>
  );
}

function RiskDonut({ score, tone }: { score: number; tone: string }) {
  const r = 52;

  const c = 2 * Math.PI * r;

  const pct = riskPercent(score) / 100;

  const stroke =
    tone === "low" ? "#16a34a" : tone === "medium" ? "#eab308" : "#dc2626";

  return (
    <svg className="risk-donut" viewBox="0 0 130 130">
      <circle
        cx="65"
        cy="65"
        r={r}
        fill="none"
        stroke="#e6efe9"
        strokeWidth="12"
      />

      <circle
        cx="65"
        cy="65"
        r={r}
        fill="none"
        stroke={stroke}
        strokeWidth="12"
        strokeLinecap="round"
        strokeDasharray={`${c * pct} ${c}`}
        transform="rotate(-90 65 65)"
      />

      <text x="65" y="60" textAnchor="middle" className="risk-donut__score">
        {score}
      </text>

      <text x="65" y="82" textAnchor="middle" className="risk-donut__max">
        /10
      </text>
    </svg>
  );
}

// One historical metric as a compact bar trend (≈14 points). Authority-only.

function TrendBars({
  emoji,

  title,

  points,

  color,

  unit,

  decimals = 0,
}: {
  emoji: string;

  title: string;

  points: { date: string; value: number }[];

  color: (v: number) => string;

  unit: string;

  decimals?: number;
}) {
  if (points.length === 0) return null;

  const max = Math.max(...points.map((p) => p.value), 1);

  const peak = Math.max(...points.map((p) => p.value));

  const latest = points[points.length - 1].value;

  const todayIso = new Date().toISOString().slice(0, 10);

  const fmt = (v: number) => v.toFixed(decimals);

  const lbl = (iso: string) => {
    const d = new Date(`${iso}T00:00:00`);

    return `${d.getDate()}/${d.getMonth() + 1}`;
  };

  return (
    <div className="trend-block">
      <div className="trend-block__head">
        <span className="trend-block__title">
          {emoji} {title}
        </span>

        <span className="trend-block__stat">
          ล่าสุด <b>{fmt(latest)}</b> · สูงสุด {fmt(peak)} {unit}
        </span>
      </div>

      <div className="trend-bars">
        {points.map((p) => {
          const h = Math.max(Math.round((p.value / max) * 100), 2);

          return (
            <div
              key={p.date}
              className={`trend-bar${p.date === todayIso ? " trend-bar--today" : ""}`}
              title={`${lbl(p.date)} · ${fmt(p.value)} ${unit}`}
            >
              <div
                className="trend-bar__fill"
                style={{ height: `${h}%`, background: color(p.value) }}
              />
            </div>
          );
        })}
      </div>

      <div className="trend-axis">
        <span>{lbl(points[0].date)}</span>

        <span>{lbl(points[Math.floor(points.length / 2)].date)}</span>

        <span className="trend-axis--today">วันนี้</span>
      </div>
    </div>
  );
}

const historySourceLinks = [
  {
    label: "GISTDA Disaster",
    detail: "ตรวจจุดความร้อนและพื้นที่เผาไหม้บนแผนที่ทางการ",
    href: "https://disaster.gistda.or.th/fire",
  },
  {
    label: "NASA FIRMS",
    detail: "เทียบข้อมูลดาวเทียม VIIRS รายวันและย้อนหลัง",
    href: "https://firms.modaps.eosdis.nasa.gov/map/",
  },
  {
    label: "Air4Thai",
    detail: "ตรวจค่า PM2.5 จากสถานีภาคพื้นดิน",
    href: "http://air4thai.pcd.go.th/webV3/",
  },
  {
    label: "TMD AWS",
    detail: "ดูสภาพอากาศ ลม ความชื้น และฝนจากกรมอุตุฯ",
    href: "https://www.tmd.go.th/",
  },
];

function peakPoint(points: { date: string; value: number }[]) {
  return points.reduce(
    (best, point) => (point.value > best.value ? point : best),
    points[0],
  );
}

function shortDateLabel(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

// Dual-scale overlay: hotspot bars + PM2.5 line on independent axes, so an

// analyst can read whether smoke tracks the fire count even at different scales.

function OverlayChart({
  hotspots,

  pm25,
}: {
  hotspots: { date: string; value: number }[];

  pm25: { date: string; value: number }[];
}) {
  if (hotspots.length === 0 || pm25.length === 0) return null;

  const n = Math.max(hotspots.length, pm25.length);

  const W = 600;

  const H = 150;

  const padT = 8;

  const padB = 20;

  const hpMax = Math.max(...hotspots.map((d) => d.value), 1);

  const pmMax = Math.max(...pm25.map((d) => d.value), 1);

  const bw = W / n;

  const plotH = H - padT - padB;

  const baseY = H - padB;

  const linePts = pm25

    .map(
      (d, i) =>
        `${(i * bw + bw / 2).toFixed(1)},${(padT + (1 - d.value / pmMax) * plotH).toFixed(1)}`,
    )

    .join(" ");

  const hpPeak = peakPoint(hotspots);
  const pmPeak = peakPoint(pm25);
  const latestHotspot = hotspots[hotspots.length - 1];
  const latestPm25 = pm25[pm25.length - 1];
  const samePeakDay = hpPeak.date === pmPeak.date;
  const watchDays = hotspots.filter((d) => d.value > 0).length;
  const insight = samePeakDay
    ? "PM2.5 และจุดความร้อนขึ้นสูงวันเดียวกัน ควรไล่ตรวจทิศลมและพื้นที่ต้นลมในวันนั้น"
    : "จุดสูงสุดคนละวัน ให้ใช้ประกอบกับลม/ความชื้นก่อนสรุปแหล่งควัน";

  return (
    <div className="trend-block">
      <div className="trend-block__head">
        <span className="trend-block__title">PM2.5 เทียบจุดความร้อน</span>

        <span className="overlay-legend">
          <i className="ov-dot ov-dot--fire" />
          จุดความร้อน <i className="ov-dot ov-dot--pm" />
          PM2.5
        </span>
      </div>

      <svg
        className="overlay-chart"
        viewBox={`0 0 ${W} ${H}`}
        role="img"
        aria-label="PM2.5 เทียบจุดความร้อน"
      >
        {hotspots.map((d, i) => {
          const top = padT + (1 - d.value / hpMax) * plotH;

          return (
            <rect
              key={d.date}
              x={i * bw + 1}
              y={top}
              width={Math.max(bw - 2, 1)}
              height={baseY - top}
              fill="#f97316"
              opacity="0.55"
              rx="1"
            >
              <title>{`${shortDateLabel(d.date)} · ${d.value} จุด`}</title>
            </rect>
          );
        })}

        <polyline
          points={linePts}
          fill="none"
          stroke="#0ea5e9"
          strokeWidth="2"
          strokeLinejoin="round"
        />
      </svg>

      <div className="trend-axis">
        <span>🔥 สูงสุด {hpMax} จุด</span>

        <span style={{ color: "#0ea5e9", fontWeight: 800 }}>
          PM2.5 สูงสุด {pmMax} µg/m³
        </span>
      </div>

      <div className="overlay-insight-grid" aria-label="สรุปข้อมูลที่ใช้ตัดสินใจ">
        <div className="overlay-insight-card overlay-insight-card--fire">
          <span>วันที่จุดความร้อนสูงสุด</span>
          <b>{shortDateLabel(hpPeak.date)}</b>
          <small>{hpPeak.value} จุด · มี hotspot {watchDays} วันในช่วงนี้</small>
        </div>

        <div className="overlay-insight-card overlay-insight-card--pm">
          <span>วันที่ PM2.5 สูงสุด</span>
          <b>{shortDateLabel(pmPeak.date)}</b>
          <small>{pmPeak.value} µg/m³ · ล่าสุด {latestPm25.value} µg/m³</small>
        </div>

        <div className="overlay-insight-card">
          <span>สถานะล่าสุด</span>
          <b>{latestHotspot.value} จุด</b>
          <small>{shortDateLabel(latestHotspot.date)} · ใช้ยืนยันร่วมกับทิศลมและความชื้น</small>
        </div>
      </div>

      <p className="overlay-analysis-note">{insight}</p>

      <div className="overlay-source-links" aria-label="แหล่งข้อมูลอ้างอิง">
        {historySourceLinks.map((source) => (
          <a key={source.href} href={source.href} target="_blank" rel="noreferrer">
            <span>{source.label}</span>
            <small>{source.detail}</small>
            <ExternalLink size={14} />
          </a>
        ))}
      </div>
    </div>
  );
}

// Authority-only: real backward trends pulled live from NASA VIIRS and

// Open-Meteo — the app's look back in time, for analysis.

function HistorySection({ history }: { history: HistoryResponse | null }) {
  // Genuinely null for ~8s while the multi-source history loads → skeleton,

  // not a blank gap. (The dashboard itself always has fallback data, so it

  // never needs one.)

  if (!history) {
    return (
      <section
        className="card history-section"
        aria-busy="true"
        aria-label="กำลังโหลดข้อมูลย้อนหลัง"
      >
        <div className="card__head">
          <span className="card__title">
            📊 ข้อมูลย้อนหลัง 30 วัน (เชิงวิเคราะห์)
          </span>
        </div>

        <div className="history-charts">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="trend-block">
              <span className="skeleton skeleton--title" />

              <span className="skeleton skeleton--chart" />
            </div>
          ))}
        </div>
      </section>
    );
  }

  const hp = history.hotspots.map((d) => ({ date: d.date, value: d.count }));

  const pm = history.pm25.map((d) => ({ date: d.date, value: d.value }));

  const temp = history.weather.map((d) => ({
    date: d.date,
    value: d.temp_max,
  }));

  const wind = history.weather.map((d) => ({
    date: d.date,
    value: d.wind_max,
  }));

  const humid = history.weather.map((d) => ({
    date: d.date,
    value: d.humidity,
  }));

  if (hp.length === 0 && pm.length === 0 && temp.length === 0) return null;

  const pmColor = (v: number) => pmHex(getPm25Color(v));

  const tempColor = (t: number) =>
    t >= 38 ? "#dc2626" : t >= 35 ? "#f97316" : t >= 30 ? "#f59e0b" : "#10b981";

  // Drier + windier = higher fire/smoke risk, so colour those toward red.

  const windColor = (w: number) =>
    w >= 18 ? "#dc2626" : w >= 12 ? "#f97316" : "#10b981";

  const humidColor = (h: number) =>
    h < 40 ? "#dc2626" : h < 60 ? "#f97316" : "#10b981";

  return (
    <section
      className="card history-section"
      aria-label={`ข้อมูลย้อนหลัง ${history.days} วัน`}
    >
      <div className="card__head">
        <span className="card__title">
          📊 ข้อมูลย้อนหลัง {history.days} วัน (เชิงวิเคราะห์)
        </span>
      </div>

      <p className="personal-checker-desc" style={{ marginBottom: "16px" }}>
        แนวโน้มจริงรายวันจากดาวเทียมและโมเดลอุตุฯ
        เพื่อวิเคราะห์ความสัมพันธ์ไฟ–ควัน–สภาพอากาศ
      </p>

      <div className="history-charts">
        <OverlayChart hotspots={hp} pm25={pm} />

        <TrendBars
          emoji="🌡️"
          title="อุณหภูมิสูงสุด/วัน"
          points={temp}
          color={tempColor}
          unit="°C"
          decimals={1}
        />

        <TrendBars
          emoji="💨"
          title="ความเร็วลมสูงสุด/วัน"
          points={wind}
          color={windColor}
          unit="km/h"
          decimals={1}
        />

        <TrendBars
          emoji="💧"
          title="ความชื้นเฉลี่ย/วัน"
          points={humid}
          color={humidColor}
          unit="%"
        />
      </div>
    </section>
  );
}

function OperationalIntelPanel({
  intelligence,
  onSelectPrediction,
}: {
  intelligence: OperationalIntelligenceResponse;
  onSelectPrediction: (
    prediction: OperationalIntelligenceResponse["localizedPredictions"][number],
  ) => void;
}) {
  const annual = intelligence.annual_hotspot_stats;
  const changeLabel = `${annual.change_percent > 0 ? "+" : ""}${annual.change_percent}%`;

  return (
    <section className="card operator-intel-card">
      <div className="card__head">
        <span className="card__title">ชั้นข้อมูลปฏิบัติการ</span>
      </div>

      <div className="operator-intel-grid">
        <div className="operator-intel-metric">
          <span>จุดความร้อนสะสม</span>
          <b>{formatNumber(annual.this_year_count)}</b>
          <small>
            เทียบปีก่อน {formatNumber(annual.last_year_count)} ({changeLabel})
          </small>
        </div>

        <div className="operator-intel-metric">
          <span>ภัยแล้ง / ความชื้นดิน</span>
          <b>{intelligence.drought_zones.length} พื้นที่</b>
          <small>
            {intelligence.drought_zones
              .slice(0, 2)
              .map(
                (zone) =>
                  `${zone.location_name}: ${zone.soil_moisture_percent}%`,
              )
              .join(" / ")}
          </small>
        </div>
      </div>

      <div className="operator-intel-breakdown">
        {intelligence.landuse_breakdown.map((item) => (
          <div key={item.landuse_type} className="operator-intel-breakdown__row">
            <span>{item.label}</span>
            <b>
              {item.count} ({item.percent}%)
            </b>
          </div>
        ))}
      </div>

      <div className="localized-prediction-list">
        {intelligence.localizedPredictions.map((prediction) => (
          <button
            key={prediction.id}
            type="button"
            className={`localized-prediction-card localized-prediction-card--${prediction.severity}`}
            onClick={() => onSelectPrediction(prediction)}
          >
            <span>
              {forecastTypeLabel(prediction.forecastType)} +
              {prediction.lead_time_hours} ชม.
            </span>
            <b>{prediction.locationName}</b>
            <small>{prediction.reason_for_prediction}</small>
          </button>
        ))}
      </div>
    </section>
  );
}

function pmHex(color: string) {
  return color === "green"
    ? "#10b981"
    : color === "yellow"
      ? "#f59e0b"
      : color === "orange"
        ? "#f97316"
        : color === "red"
          ? "#ef4444"
          : "#8b5cf6";
}

// Mobile-first "today at a glance" card: the three pillars (air · risk ·

// hotspots) as one compact block so a citizen sees the whole situation

// without scrolling. Hidden on desktop (where the detailed cards lead).

function CitizenSummary({
  pm25,

  pm25Color,

  temp,

  riskScore,

  riskTone,

  hotspots,
}: {
  pm25: number;

  pm25Color: string;

  temp: number;

  riskScore: number;

  riskTone: string;

  hotspots: number;
}) {
  const airHex = pmHex(pm25Color);

  const riskHex =
    riskTone === "low"
      ? "#16a34a"
      : riskTone === "medium"
        ? "#eab308"
        : "#dc2626";

  const fireHex =
    hotspots === 0 ? "#16a34a" : hotspots <= 20 ? "#f97316" : "#dc2626";

  const tiles = [
    {
      accent: airHex,
      label: "คุณภาพอากาศ",
      value: `${pm25}`,
      unit: "µg/m³",
      tag: getPm25Label(pm25),
    },

    {
      accent: riskHex,
      label: "ความเสี่ยงหมอกควัน",
      value: riskScore,
      suffix: "/10",
      unit: "คะแนน",
      tag: riskLabelTh[riskTone],
    },

    {
      accent: fireHex,
      label: "จุดความร้อน",
      value: `${hotspots}`,
      unit: "จุด",
      tag: "ดาวเทียมวันนี้",
    },
  ] as const;

  return (
    <section className="card today-summary" aria-label="สรุปสถานการณ์วันนี้">
      <div className="card__head">
        <span className="card__title">📊 สถานการณ์วันนี้ · เชียงใหม่</span>
      </div>

      <div className="today-summary__grid">
        {tiles.map((t) => (
          <div
            key={t.label}
            className="summary-tile"
            style={{ ["--accent" as string]: t.accent }}
          >
            <span className="summary-tile__label">{t.label}</span>

            <strong className="summary-tile__value">
              {t.value}

              {"suffix" in t && t.suffix ? <em>{t.suffix}</em> : null}
            </strong>

            <span className="summary-tile__unit">{t.unit}</span>

            <span className="summary-tile__tag">{t.tag}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function App() {
  const [dashboard, setDashboard] = useState<DashboardResponse>(fallback);

  const [dataStatus, setDataStatus] = useState<DataStatusResponse | null>(null);

  const [history, setHistory] = useState<HistoryResponse | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

  const [layers, setLayers] = useState<LayerState>({
    hotspots: true,

    pm25: true,

    wind: true,

    landmarks: false,

    fuelRisk: true,

    communityForests: true,

    fireZones: true,

    predictions: true,
  });

  const [note, setNote] = useState<"pm" | "risk" | null>(null);

  const [mapSelection, setMapSelection] =
    useState<MapSelection>(initialSelection);

  const [now, setNow] = useState(() => new Date());

  const [theme, setTheme] = useState<"light" | "dark">("light");

  const [userLocation, setUserLocation] = useState<[number, number] | null>(
    null,
  );

  const [isPinningMode, setIsPinningMode] = useState(false);

  const [mapFullscreen, setMapFullscreen] = useState(false);

  const [hoveredDistrict, setHoveredDistrict] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<
    "overview" | "aqi" | "fire_weather" | "community" | "checker"
  >("overview");

  const [sidebarOpen, setSidebarOpen] = useState(true);

  const selectHomeLocation = useCallback(
    (coords: [number, number]) => {
      const windDest = windDestinationName(
        dashboard.weather.wind_direction_deg,
      );

      const pm25Value = `${dashboard.pm25.current_pm25.toFixed(1)} µg/m³`;

      const pm25SelectionTone: "good" | "watch" | "risk" =
        dashboard.pm25.color === "green"
          ? "good"
          : dashboard.pm25.color === "yellow"
            ? "watch"
            : "risk";

      setUserLocation(coords);

      setIsPinningMode(false);

      setMapSelection({
        eyebrow: "พิกัดบ้านของฉัน",

        lat: coords[0],

        lng: coords[1],

        title: `บ้านของฉัน (${coords[0].toFixed(4)}, ${coords[1].toFixed(4)})`,

        detail: `ปักตำแหน่งนี้เป็นบ้านของคุณแล้ว ใช้ประเมินร่วมกับ PM2.5 ${pm25Value}, จุดความร้อน ${dashboard.hotspots.count} จุด และลมที่กำลังพัดไปทาง${windDest}`,

        mapUrl: `https://www.google.com/maps?q=${coords[0]},${coords[1]}`,

        imageKey: "district",

        imageLabel: "ตำแหน่งบ้านของฉัน",

        stats: [
          {
            label: "พิกัด",
            value: `${coords[0].toFixed(4)}, ${coords[1].toFixed(4)}`,
          },

          { label: "PM2.5 วันนี้", value: pm25Value, tone: pm25SelectionTone },

          {
            label: "จุดความร้อน",
            value: `${dashboard.hotspots.count} จุด`,
            tone: dashboard.hotspots.count > 0 ? "watch" : "good",
          },

          {
            label: "ลม",
            value: `${dashboard.weather.wind_speed_kmh.toFixed(1)} กม./ชม. ไป${windDest}`,
          },
        ],
      });

      window.requestAnimationFrame(() => {
        document
          .querySelector(".map-detail-bar")
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    },
    [
      dashboard.hotspots.count,
      dashboard.pm25.color,
      dashboard.pm25.current_pm25,
      dashboard.weather.wind_direction_deg,
      dashboard.weather.wind_speed_kmh,
    ],
  );

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const loadDashboard = useCallback(() => {
    setLoading(true);

    fetchDashboard()
      .then((data) => {
        setDashboard(data);

        setError(null);

        fetchDataStatus()
          .then(setDataStatus)

          .catch(() => setDataStatus(buildDataStatusFromDashboard(data)));
      })

      .catch((err: Error) => {
        setError(err.message);

        setDataStatus(buildDataStatusFromDashboard(fallback));
      })

      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadDashboard();

    const refreshId = window.setInterval(loadDashboard, 5 * 60 * 1000);

    return () => window.clearInterval(refreshId);
  }, [loadDashboard]);

  useEffect(() => {
    const clockId = window.setInterval(() => setNow(new Date()), 1000);

    return () => window.clearInterval(clockId);
  }, []);

  useEffect(() => {
    if (!history) {
      fetchHistory()
        .then(setHistory)

        .catch(() => undefined);
    }
  }, [history]);

  useEffect(() => {
    if (!userLocation) return;

    let nearest: any = null;

    let minD = Infinity;

    dashboard.hotspots.items.forEach((h) => {
      const d = getDistanceKm(
        userLocation[0],
        userLocation[1],
        h.latitude,
        h.longitude,
      );

      if (d < minD) {
        minD = d;

        nearest = h;
      }
    });

    if (nearest) {
      const bearing = getBearing(
        nearest.latitude,
        nearest.longitude,
        userLocation[0],
        userLocation[1],
      );

      const windTowards = (dashboard.weather.wind_direction_deg + 180) % 360;

      const angleDiff = Math.min(
        360 - Math.abs(bearing - windTowards),
        Math.abs(bearing - windTowards),
      );

      const windPushes = angleDiff <= 45;

      // Calculate physics factors

      const phys = getDistrictPhysics(nearest.district);

      const {
        rosMultiplier,
        description: rosDesc,
        slopeEffect,
      } = calculateRateOfSpread(
        phys.slope_deg,

        phys.fuel_flammability,

        phys.history_multiplier,

        dashboard.weather.wind_speed_kmh,

        windPushes,
      );

      let riskVal = "ปลอดภัย";

      let riskColor: "good" | "watch" | "risk" = "good";

      if (minD <= 5) {
        riskVal = "เสี่ยงสูงมาก (ใกล้จุดไฟป่า)";

        riskColor = "risk";
      } else if (minD <= 15) {
        riskVal = windPushes
          ? "เฝ้าระวังเข้ม (อยู่ใต้ลมควันพัดหาตัว)"
          : "เฝ้าระวัง (ใกล้พื้นที่เกิดไฟ)";

        riskColor = windPushes ? "risk" : "watch";
      } else if (windPushes && dashboard.pm25.current_pm25 > 37) {
        riskVal = "เฝ้าระวัง (อยู่ใต้ลมกลุ่มควัน)";

        riskColor = "watch";
      }

      // Elevate risk based on high rate of spread (ROS)

      if (minD <= 15 && rosMultiplier >= 3.0) {
        riskVal = "วิกฤตอันตราย (ไฟลามรวดเร็วพิเศษ)";

        riskColor = "risk";
      } else if (minD <= 15 && rosMultiplier >= 1.8 && riskColor !== "risk") {
        riskVal = "เสี่ยงสูง (ไฟลามรวดเร็ว)";

        riskColor = "risk";
      }

      const windDest = windDestinationName(
        dashboard.weather.wind_direction_deg,
      );

      setMapSelection({
        eyebrow: "การประเมินความเสี่ยงรายบุคคล",

        lat: userLocation[0],

        lng: userLocation[1],

        title: `พิกัดบ้านฉัน (${userLocation[0].toFixed(4)}, ${userLocation[1].toFixed(4)})`,

        detail: `ห่างจากจุดไฟไหม้ที่ใกล้ที่สุด ${minD.toFixed(1)} กม. ใน อ.${nearest.district || "ไม่ระบุ"} โดยลมกำลังพัด${windPushes ? `ตรงเข้าหาพิกัดของคุณ (ไปทาง${windDest})` : `เบี่ยงออกไปทิศทางอื่น`}`,

        stats: [
          {
            label: "ระยะห่างไฟป่า",
            value: `${minD.toFixed(1)} กม.`,
            tone: minD <= 10 ? "risk" : "watch",
          },

          {
            label: "การพัดของควัน",
            value: windPushes ? "พัดเข้าหาตัว" : "พัดหนีออกไป",
            tone: windPushes ? "risk" : "good",
          },

          { label: "สภาพเชื้อเพลิง", value: phys.forest_type },

          {
            label: "ความชันภูมิประเทศ",
            value: `${phys.slope_deg}° (ลามเร็ว ${slopeEffect.toFixed(1)}x)`,
            tone: phys.slope_deg >= 25 ? "risk" : "watch",
          },

          {
            label: "ความเร็วลามไฟ (ROS)",
            value: `${rosMultiplier.toFixed(1)} เท่า (${rosDesc})`,
            tone: rosMultiplier >= 1.8 ? "risk" : "watch",
          },

          {
            label: "ประวัติไฟป่า",
            value: phys.history_level,
            tone: phys.history_multiplier >= 1.3 ? "risk" : "watch",
          },

          { label: "ความเสี่ยงส่วนบุคคล", value: riskVal, tone: riskColor },
        ],
      });
    }
  }, [
    userLocation,
    dashboard.hotspots.items,
    dashboard.weather.wind_direction_deg,
    dashboard.pm25.current_pm25,
    dashboard.weather.wind_speed_kmh,
  ]);

  const updatedAt = useMemo(() => {
    const times = [
      dashboard.hotspots.latest_update,
      dashboard.pm25.latest_update,
      dashboard.weather.latest_update,
    ];

    const sorted = [...times].sort();

    return sorted[sorted.length - 1] ?? dashboard.pm25.latest_update;
  }, [dashboard]);

  const riskTone = getRiskTone(dashboard.risk.score);

  const intelligence = dashboard.intelligence ?? operatorIntelligenceFallback;

  const topCommunityZones = useMemo(
    () =>
      [...prototypeZones]

        .sort(
          (a, b) =>
            a.healthScore - b.healthScore ||
            b.rfdCoordinatePoints - a.rfdCoordinatePoints,
        )

        .slice(0, 4),

    [],
  );

  const weeklyForestRanking = [
    ...intelligence.weekly_forest_league.ranking,
    ...prototypeForestRanking().filter(
      (fallback) =>
        !intelligence.weekly_forest_league.ranking.some(
          (item) => item.forest_id === fallback.forest_id,
        ),
    ),
  ]
    .sort((a, b) => b.total_score - a.total_score)
    .slice(0, 5);

  const weeklyForestLeaderScore = Math.max(
    ...weeklyForestRanking.map((item) => item.total_score),
    1,
  );

  const allOn =
    layers.hotspots &&
    layers.pm25 &&
    layers.wind &&
    layers.communityForests &&
    layers.fireZones &&
    layers.predictions;

  const toggleLayer = (key: keyof LayerState) =>
    setLayers((current) => ({ ...current, [key]: !current[key] }));

  const toggleNote = (key: "pm" | "risk") =>
    setNote((current) => (current === key ? null : key));

  const setAll = () =>
    setLayers({
      hotspots: true,

      pm25: true,

      wind: true,

      landmarks: false,

      fuelRisk: true,

      communityForests: true,

      fireZones: true,

      predictions: true,
    });

  const pm25Time = formatTime(dashboard.pm25.latest_update);

  const weatherTime = formatTime(dashboard.weather.latest_update);

  const advice = adviceByColor[dashboard.pm25.color] ?? adviceByColor.green;

  const recommendations = computeRecommendations(
    dashboard.pm25.current_pm25,

    dashboard.hotspots.count,

    dashboard.risk.score,
  );

  const factors = dashboard.risk.factors;

  const pm25Points = Number(factors.pm25_points ?? 0);

  const hotspotPoints = Number(factors.hotspot_points ?? 0);

  const windFactor = Number(factors.wind_factor ?? 0);

  const windSourceText = dashboard.weather.wind_direction_text;

  const windDestinationText = windDestinationName(
    dashboard.weather.wind_direction_deg,
  );

  const dataStatusCopy = dataStatus ? getDataStatusCopy(dataStatus) : null;

  const spreadWatchLevel =
    dashboard.hotspots.count >= 30 || windFactor > 0
      ? "เฝ้าระวังเข้ม"
      : dashboard.hotspots.count > 0
        ? "เฝ้าระวัง"
        : "ต่ำ";

  const spreadWatchTone =
    dashboard.hotspots.count >= 30 || windFactor > 0
      ? "risk"
      : dashboard.hotspots.count > 0
        ? "watch"
        : "good";

  const hourlyForecast = useMemo(() => {
    return getHourlyForecast(
      dashboard.weather.temperature_c,

      dashboard.pm25.current_pm25,

      dashboard.weather.wind_direction_deg,

      dashboard.weather.wind_speed_kmh,

      dashboard.hotspots.count,
    );
  }, [dashboard]);

  const dailyForecast = useMemo(() => {
    return getDailyForecast(
      dashboard.weather.temperature_c,

      dashboard.pm25.current_pm25,

      dashboard.weather.wind_direction_deg,

      dashboard.hotspots.count,
    );
  }, [dashboard]);

  const selectLocalizedPrediction = useCallback(
    (
      prediction: OperationalIntelligenceResponse["localizedPredictions"][number],
    ) => {
      setMapSelection({
        eyebrow: "คาดการณ์รายพื้นที่",
        title: prediction.locationName,
        detail: prediction.reason_for_prediction,
        lat: prediction.latitude,
        lng: prediction.longitude,
        mapUrl: `https://www.google.com/maps?q=${prediction.latitude},${prediction.longitude}`,
        imageKey: prediction.forecastType === "fire" ? "hotspot" : "wind",
        imageLabel: prediction.locationName,
        stats: [
          {
            label: "ประเภทคาดการณ์",
            value: `${forecastTypeLabel(prediction.forecastType)} +${prediction.lead_time_hours} ชม.`,
            tone: prediction.severity === "watch" ? "watch" : "risk",
          },
          {
            label: "ระดับ",
            value: severityLabel(prediction.severity),
            tone: prediction.severity === "watch" ? "watch" : "risk",
          },
        ],
      });
      setSidebarOpen(true);
    },
    [],
  );

  const aqiGlowClass = `badge--glow badge--glow-${dashboard.pm25.color}`;
  const situationItems = [
    {
      key: "pm25",
      label: "PM2.5",
      value: `${Math.round(dashboard.pm25.current_pm25)} µg/m³`,
      detail: getPm25Label(dashboard.pm25.current_pm25),
      tone: dashboard.pm25.color,
      onClick: () => {
        setActiveTab("aqi");
        setSidebarOpen(true);
      },
    },
    {
      key: "hotspots",
      label: "จุดความร้อน",
      value: formatNumber(dashboard.hotspots.count),
      detail: `${dashboard.hotspots.density_per_100_km2.toFixed(1)}/100 กม²`,
      tone: dashboard.hotspots.count > 0 ? "hot" : "green",
      onClick: () => {
        setActiveTab("fire_weather");
        setSidebarOpen(true);
      },
    },
    {
      key: "wind",
      label: "ลม",
      value: `ไป${windDestinationText}`,
      detail: `${Math.round(dashboard.weather.wind_speed_kmh)} km/h`,
      tone: "blue",
      onClick: () => {
        setActiveTab("fire_weather");
        setSidebarOpen(true);
      },
    },
    {
      key: "risk",
      label: "ความเสี่ยง",
      value: `${dashboard.risk.score}/10`,
      detail: riskLabelTh[riskTone],
      tone: riskTone,
      onClick: () => {
        setActiveTab("overview");
        setSidebarOpen(true);
      },
    },
  ];

  return (
    <div className="app-shell" data-ui-mode="operator">
      <header className="topbar">
        <div className="brand-lockup">
          <span className="brand-mark" aria-hidden>
            <svg
              viewBox="0 0 24 24"
              width="22"
              height="22"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z" />

              <path d="M7 11l2.5-2.5M12 12l4-4" opacity="0.6" />

              <circle cx="12" cy="12" r="3" />
            </svg>
          </span>

          <div className="brand-text">
            <h1>ChiangMaiEyes</h1>

            <p>
              <span className="brand-bar" />
              รายงานจุดความร้อน ฝุ่นละออง และทิศทางลม
              <span className="brand-sep">|</span>จังหวัดเชียงใหม่
            </p>
          </div>
        </div>

        <div className="situation-strip" aria-label="สรุปสถานการณ์ปัจจุบัน">
          {situationItems.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`situation-chip situation-chip--${item.tone}`}
              onClick={item.onClick}
            >
              <span className="situation-chip__dot" aria-hidden />
              <span className="situation-chip__copy">
                <span className="situation-chip__label">{item.label}</span>
                <strong>{item.value}</strong>
              </span>
              <span className="situation-chip__detail">{item.detail}</span>
            </button>
          ))}
        </div>

        <div className="topbar__actions">
          <div className="operator-scope-badge">มุมมองเจ้าหน้าที่หน้างาน</div>

          {/* Theme Switcher */}

          <button
            type="button"
            className="theme-toggle-btn"
            onClick={() => setTheme((t) => (t === "light" ? "dark" : "light"))}
            aria-label="สลับโหมดสี"
          >
            {theme === "light" ? "🌙" : "☀️"}
          </button>

          <div className="date-pill" aria-label="วันที่และเวลาปัจจุบัน">
            <CalendarDays size={16} aria-hidden />

            <div
              style={{ display: "flex", flexDirection: "column", gap: "1px" }}
            >
              <strong
                style={{
                  fontSize: "1.05rem",
                  fontFamily: "monospace",
                  fontWeight: 800,
                }}
              >
                {formatCurrentTime(now)}
              </strong>

              <span className="date-pill__full">{formatCurrentDate(now)}</span>
            </div>
          </div>

          <div className="live-pill">
            <span className="live-dot" />

            <div>
              <strong>{loading ? "กำลังอัปเดต" : "อัปเดตล่าสุด"}</strong>

              <span className="live-pill__full">
                {formatDateTime(updatedAt)}
              </span>

              <span className="live-pill__short">
                {loading ? "กำลังอัปเดต" : `อัปเดต ${formatTime(updatedAt)}`}
              </span>
            </div>
          </div>

          <button
            className="icon-button"
            type="button"
            onClick={loadDashboard}
            aria-label="อัปเดตข้อมูล"
          >
            <RefreshCcw size={18} />
          </button>
        </div>
      </header>

      {error && <div className="notice">{error}</div>}

      <div className="main-content-layout">
        {/* LEFT COLLAPSIBLE SIDEBAR */}

        <aside
          className={`sidebar-container ${sidebarOpen ? "open" : "collapsed"}`}
        >
          {/* TAB SELECTION HEADER */}

          <div className="sidebar-tabs">
            <button
              type="button"
              className={`sidebar-tab-btn ${activeTab === "overview" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("overview");

                setSidebarOpen(true);
              }}
              title="ภาพรวม & ที่ปรึกษา AI"
            >
              <Home size={18} />

              <span>ภาพรวม</span>
            </button>

            <button
              type="button"
              className={`sidebar-tab-btn ${activeTab === "aqi" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("aqi");

                setSidebarOpen(true);
              }}
              title="คุณภาพอากาศ & สารมลพิษ"
            >
              <CloudSun size={18} />

              <span>ฝุ่น PM2.5</span>
            </button>

            <button
              type="button"
              className={`sidebar-tab-btn ${activeTab === "fire_weather" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("fire_weather");

                setSidebarOpen(true);
              }}
              title="พยากรณ์จุดไฟ & สภาพอากาศ"
            >
              <Flame size={18} />

              <span>ไฟ & ลม</span>
            </button>

            <button
              type="button"
              className={`sidebar-tab-btn ${activeTab === "community" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("community");

                setSidebarOpen(true);
              }}
              title="เครือข่ายป่าชุมชน"
            >
              <Trophy size={18} />

              <span>ป่าชุมชน</span>
            </button>

            <button
              type="button"
              className={`sidebar-tab-btn ${activeTab === "checker" ? "active" : ""}`}
              onClick={() => {
                setActiveTab("checker");

                setSidebarOpen(true);
              }}
              title="ตรวจสอบความเสี่ยงส่วนบุคคล & สายด่วน"
            >
              <MapPin size={18} />

              <span>แจ้งภัย</span>
            </button>
          </div>

          <div className="sidebar-panel-content">
            <div className="sidebar-body">
              {activeTab === "overview" && (
                <div className="tab-pane">
                  {/* Weekly Forest League */}

                  <div className="community-action-panel community-action-panel--league">
                    <div className="community-action-panel__head">
                      <span className="community-action-panel__icon">
                        <Trophy size={18} />
                      </span>

                      <div>
                        <span>ลีกป่าชุมชนรายสัปดาห์</span>

                        <strong>อันดับผลงานป้องกันไฟ</strong>
                      </div>
                    </div>

                    <div className="forest-ranking-list">
                      {weeklyForestRanking.map((item, index) => {
                        const previous = weeklyForestRanking[index - 1];
                        const gap = previous
                          ? Math.max(previous.total_score - item.total_score, 0)
                          : 0;
                        const percent = Math.max(
                          8,
                          Math.round((item.total_score / weeklyForestLeaderScore) * 100),
                        );
                        const rankLabel = index === 0 ? "แชมป์" : `อันดับ ${index + 1}`;

                        return (
                          <button
                            key={item.forest_id}
                            type="button"
                            className={`forest-ranking-row forest-ranking-row--rank-${index + 1}`}
                            onClick={() =>
                              setMapSelection({
                                eyebrow: "ลีกป่าชุมชนรายสัปดาห์",

                                title: `อันดับ ${index + 1}: ${item.forest_name}`,

                                detail: `${item.reasons.join(" / ") || "รอรายงานภาคสนาม"} - คะแนนรายสัปดาห์จากกิจกรรมป้องกันไฟในพื้นที่`,

                                lat: item.latitude,

                                lng: item.longitude,

                                stats: [
                                  {
                                    label: "คะแนนสัปดาห์นี้",
                                    value: `${item.total_score}/100`,
                                    tone: item.total_score >= 80 ? "good" : "watch",
                                  },

                                  {
                                    label: "ช่องว่างจากอันดับก่อนหน้า",
                                    value: index === 0 ? "นำอยู่" : `ตาม ${gap} คะแนน`,
                                    tone: index === 0 ? "good" : gap >= 8 ? "risk" : "watch",
                                  },

                                  {
                                    label: "อำเภอ / ตำบล",
                                    value: `${item.amphoe || "ไม่ระบุ"} / ${item.tambon || "ไม่ระบุ"}`,
                                  },

                                  {
                                    label: "ที่มาคะแนน",
                                    value: `จัดการ ${item.score_breakdown.management} / ป้องกัน ${item.score_breakdown.prevention} / ใช้ประโยชน์ ${item.score_breakdown.utilization} / นิเวศ ${item.score_breakdown.ecological_outcome}`,
                                  },
                                ],
                              })
                            }
                          >
                            <span className="forest-ranking-row__rank">
                              <small>{rankLabel}</small>
                              <b>{index + 1}</b>
                            </span>

                            <span className="forest-ranking-row__main">
                              <b>{item.forest_name}</b>

                              <small>
                                {item.amphoe || "ไม่ระบุ"} · {item.report_count} รายงาน ·{" "}
                                {index === 0 ? "เป้าหมายให้ทีมอื่นไล่ทัน" : `ตามอันดับบน ${gap} คะแนน`}
                              </small>

                              <span className="forest-ranking-row__meter" aria-hidden="true">
                                <i style={{ width: `${percent}%` }} />
                              </span>
                            </span>

                            <span className="forest-ranking-row__score">
                              <b>{item.total_score}</b>
                              <small>/100</small>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  <OperationalIntelPanel
                    intelligence={intelligence}
                    onSelectPrediction={selectLocalizedPrediction}
                  />



                  {/* Risk Card */}

                  <section className="card risk-card" data-risk={riskTone}>
                    <div className="card__head">
                      <span className="card__title">
                        คะแนนเสี่ยงการเกิดหมอกควันวันนี้
                      </span>

                      <button
                        type="button"
                        className="card__info-btn"
                        aria-label="อธิบายวิธีคำนวณคะแนนเสี่ยง"
                        aria-expanded={note === "risk"}
                        onClick={() => toggleNote("risk")}
                      >
                        <Info size={15} />
                      </button>
                    </div>

                    {note === "risk" && (
                      <p className="card__note">
                        ประมวลผลความเสี่ยง (0-10) จากปัจจัย PM2.5 (40%),
                        จุดความร้อนดาวเทียม (40%) และกำลังลมลามไฟ (20%)
                      </p>
                    )}

                    <div className="risk-card__body">
                      <div className="risk-card__gauge">
                        <RiskDonut
                          score={dashboard.risk.score}
                          tone={riskTone}
                        />

                        <span className="risk-card__label">
                          {riskLabelTh[riskTone]}
                        </span>
                      </div>

                      <ul className="risk-card__factors">
                        <li>
                          <span>
                            <i className="dot dot--pm" />
                            ฝุ่นละออง PM2.5
                          </span>

                          <strong>
                            {pm25Points.toFixed(1)} <em>/4</em>
                          </strong>
                        </li>

                        <li>
                          <span>
                            <i className="dot dot--hot" />
                            จุดความร้อนสะสม
                          </span>

                          <strong>
                            {hotspotPoints.toFixed(1)} <em>/4</em>
                          </strong>
                        </li>

                        <li>
                          <span>
                            <i className="dot dot--wind" />
                            ความเร็วกระแสลม
                          </span>

                          <strong>
                            {windFactor.toFixed(1)} <em>/2</em>
                          </strong>
                        </li>
                      </ul>
                    </div>

                    {true && (
                      <p
                        className="risk-card__formula"
                        style={{ fontSize: "0.72rem", marginTop: "10px" }}
                      >
                        สมการลามควัน: {dashboard.risk.formula}
                      </p>
                    )}
                  </section>

                  {/* Advice Card */}

                  <section className="card advice-card">
                    <div className="card__head">
                      <ShieldCheck
                        size={18}
                        style={{ color: "var(--green)" }}
                      />

                      <span className="card__title">
                        สรุป AI สำหรับหน้างาน
                      </span>
                    </div>

                    {false && (
                      <>
                        <h3
                          className={`advice-card__heading advice-card__heading--${dashboard.pm25.color}`}
                          style={{ fontSize: "1.05rem", margin: "8px 0 4px" }}
                        >
                          {advice.heading}
                        </h3>

                        <p
                          className="advice-card__text"
                          style={{ fontSize: "0.84rem", margin: "0 0 10px" }}
                        >
                          {advice.text}
                        </p>

                        <ul
                          className="advice-recs"
                          style={{
                            fontSize: "0.8rem",
                            paddingLeft: "14px",
                            margin: "0 0 12px",
                          }}
                        >
                          {recommendations.map(({ label, detail }, i) => (
                            <li key={i} style={{ marginBottom: "6px" }}>
                              <strong>{label}:</strong> {detail}
                            </li>
                          ))}
                        </ul>
                      </>
                    )}

                    <Suspense
                      fallback={
                        <div className="ai-briefing ai-briefing__text--fallback">
                          กำลังโหลดที่ปรึกษา...
                        </div>
                      }
                    >
                      <AiAdvisor dashboard={dashboard} />
                    </Suspense>
                  </section>
                </div>
              )}

              {activeTab === "aqi" && (
                <div className="tab-pane">
                  {/* Hero weather / AQI Card */}

                  <section className="card hero-weather-card">
                    <div className="hero-weather-main">
                      <div className="hero-temp-box">
                        <WeatherIcon
                          type={
                            dashboard.weather.temperature_c > 30
                              ? "sun"
                              : "cloud"
                          }
                          size={46}
                        />

                        <span className="hero-temp">
                          {dashboard.weather.temperature_c.toFixed(0)}

                          <span className="hero-temp-unit">°C</span>
                        </span>

                        <div className="hero-weather-condition">
                          <span className="hero-weather-text">
                            {dashboard.weather.temperature_c > 30
                              ? "แดดจัด/อากาศร้อน"
                              : "มีเมฆบางส่วน"}
                          </span>

                          <span className="hero-weather-desc">
                            รู้สึกเหมือน{" "}
                            {Math.round(dashboard.weather.temperature_c - 1)}°C
                          </span>
                        </div>
                      </div>

                      <div className="hero-aqi-badge-wrapper">
                        <span className={aqiGlowClass}>
                          PM2.5: {dashboard.pm25.current_pm25} µg/m³
                        </span>

                        <span
                          style={{
                            fontSize: "0.78rem",
                            fontWeight: 700,
                            color: "var(--muted)",
                            marginTop: "4px",
                          }}
                        >
                          {getPm25Label(dashboard.pm25.current_pm25)}
                        </span>

                        <div
                          className="pm25-quality-bar"
                          aria-label="ระดับ PM2.5"
                        >
                          {[
                            { max: 25, color: "#16a34a", label: "ดีมาก" },

                            { max: 37, color: "#eab308", label: "ดี" },

                            { max: 50, color: "#f97316", label: "ปานกลาง" },

                            { max: 90, color: "#dc2626", label: "มีผลกระทบ" },

                            { max: 200, color: "#7c3aed", label: "อันตราย" },
                          ].map((band, i) => (
                            <div
                              key={`${band.max}-${i}`}
                              className="pm25-band"
                              style={{ background: band.color }}
                            >
                              <span>{band.label}</span>
                            </div>
                          ))}

                          <div
                            className="pm25-indicator"
                            style={{
                              left: `${Math.min((dashboard.pm25.current_pm25 / 200) * 100, 100)}%`,
                            }}
                            aria-label={`ค่าปัจจุบัน ${dashboard.pm25.current_pm25}`}
                          />
                        </div>
                      </div>
                    </div>

                    <div style={{ marginTop: "16px" }}>
                      <Pm25Scale value={dashboard.pm25.current_pm25} />
                    </div>
                  </section>

                  {/* Pollutants breakdown */}

                  <PollutantsBreakdown pm25={dashboard.pm25.current_pm25} />

                  {/* Citizen Travel Guide */}

                  {false && (
                    <CitizenTravelGuide dailyForecast={dailyForecast} />
                  )}

                  {/* 24h PM2.5 trend sparkline */}

                  <section className="card trend-card">
                    <div
                      className="card__head"
                      style={{ marginBottom: "12px" }}
                    >
                      <span className="card__title">
                        📈 แนวโน้มฝุ่นละอองย้อนหลัง (ตัวอย่าง)
                      </span>
                    </div>

                    <div style={{ padding: "10px 0" }}>
                      <Sparkline />
                    </div>
                  </section>
                </div>
              )}

              {activeTab === "fire_weather" && (
                <div className="tab-pane">
                  {/* Hotspot count card */}

                  <section className="card mini-card mini-card--hotspots">
                    <span className="card__title">จุดความร้อนสะสมวันนี้</span>

                    <div className="mini-card__body">
                      <span className="mini-card__icon mini-card__icon--fire">
                        <Flame size={20} />
                      </span>

                      <div className="mini-card__value">
                        <strong>{dashboard.hotspots.count}</strong>

                        <span>จุดสะสม</span>
                      </div>
                    </div>

                    <small className="card__foot">
                      NASA FIRMS / GISTDA · {pm25Time} น.
                    </small>
                  </section>

                  {/* Meteorological bento */}

                  <section className="card weather-bento-card">
                    <div
                      className="card__head"
                      style={{ marginBottom: "12px" }}
                    >
                      <span className="card__title">💨 สภาพอุตุนิยมวิทยา</span>
                    </div>

                    <div className="metrics-bento-grid">
                      <div className="metric-bento-item">
                        <div className="metric-bento-icon">
                          <Droplets size={16} />
                        </div>

                        <div className="metric-bento-content">
                          <span className="metric-bento-label">
                            ความชื้นสัมพัทธ์
                          </span>

                          <span className="metric-bento-value">
                            {Math.round(dashboard.weather.humidity_percent)}%
                          </span>
                        </div>
                      </div>

                      <div className="metric-bento-item">
                        <div className="metric-bento-icon">
                          <Wind size={16} />
                        </div>

                        <div className="metric-bento-content">
                          <span className="metric-bento-label">
                            ความเร็วลม / ทิศลม
                          </span>

                          <span className="metric-bento-value">
                            ไป{windDestinationText}
                          </span>

                          <span className="metric-bento-sub">
                            {dashboard.weather.wind_speed_kmh} km/h (ทิศ{" "}
                            {windSourceText})
                          </span>
                        </div>
                      </div>

                      <div className="metric-bento-item">
                        <div className="metric-bento-icon">
                          <Eye size={16} />
                        </div>

                        <div className="metric-bento-content">
                          <span className="metric-bento-label">ทัศนวิสัย</span>

                          <span className="metric-bento-value">
                            ~{estimateVisibilityKm(dashboard.pm25.current_pm25)}{" "}
                            กม.
                          </span>
                        </div>
                      </div>

                      <div className="metric-bento-item">
                        <div className="metric-bento-icon">
                          <Compass size={16} />
                        </div>

                        <div className="metric-bento-content">
                          <span className="metric-bento-label">
                            ความกดอากาศ
                          </span>

                          <span className="metric-bento-value">
                            {dashboard.weather.pressure_hpa != null
                              ? `${dashboard.weather.pressure_hpa.toFixed(0)} hPa`
                              : "1010 hPa"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </section>

                  {/* 8h forecast strip */}

                  <section className="card hourly-forecast-card">
                    <div className="card__head">
                      <span className="card__title">
                        ⏰ พยากรณ์ทิศทางควันและจุดไฟรายชั่วโมง (8 ชม.)
                      </span>
                    </div>

                    <p
                      className="personal-checker-desc"
                      style={{ marginBottom: "12px" }}
                    >
                      การจำลองทิศทางการพัดพาของควันไฟป่า
                      <br />
                      <em
                        style={{ fontSize: "0.75rem", color: "var(--muted)" }}
                      >
                        ⚠️ ค่า PM2.5 และจุดไฟสะสมเป็นการจำลองแบบมีทิศทาง
                      </em>
                    </p>

                    <div className="forecast-hourly-list">
                      {hourlyForecast.map((hour, idx) => {
                        const pmColorClass = `hourly-pm-badge badge--${getPm25Color(hour.pm25)}`;

                        return (
                          <div key={idx} className="hourly-item-box">
                            <span className="hourly-time">{hour.time}</span>

                            <WeatherIcon type={hour.icon} size={22} />

                            <span className="hourly-temp">
                              {Math.round(hour.temp)}°
                            </span>

                            <span className={pmColorClass}>
                              ฝุ่น {hour.pm25}
                            </span>

                            <span className="hourly-hotspots">
                              <Flame size={12} /> {hour.hotspots} จุด
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </section>

                  {/* 7-day outlook table */}

                  <section className="card daily-forecast-card">
                    <div className="card__head">
                      <span className="card__title">
                        📅 พยากรณ์ความเสี่ยงไฟป่า 7 วันข้างหน้า
                      </span>
                    </div>

                    <div style={{ overflowX: "auto" }}>
                      <table className="daily-forecast-table">
                        <thead>
                          <tr
                            style={{
                              borderBottom: "2px solid var(--line)",
                              textAlign: "left",
                            }}
                          >
                            <th className="daily-cell">วันที่</th>

                            <th className="daily-cell">สภาพอากาศ</th>

                            <th className="daily-cell">อุณหภูมิ</th>

                            <th className="daily-cell">ระดับความเสี่ยง</th>

                            <th
                              className="daily-cell"
                              style={{ textAlign: "center" }}
                            >
                              จุดไฟคาดการณ์
                            </th>
                          </tr>
                        </thead>

                        <tbody>
                          {dailyForecast.map((day, idx) => {
                            const riskBadgeClass = `hourly-pm-badge badge--${day.fireRisk === "critical" ? "purple" : day.fireRisk === "high" ? "red" : day.fireRisk === "medium" ? "orange" : "green"}`;

                            return (
                              <tr key={idx} className="daily-row">
                                <td className="daily-cell daily-day-cell">
                                  {day.day}
                                </td>

                                <td className="daily-cell daily-weather-cell">
                                  <WeatherIcon type={day.icon} size={16} />

                                  <span
                                    style={{
                                      fontSize: "0.74rem",
                                      marginLeft: "4px",
                                    }}
                                  >
                                    {day.icon === "sun"
                                      ? "แล้ง"
                                      : day.icon === "rain"
                                        ? "ชื้น"
                                        : "เมฆ"}
                                  </span>
                                </td>

                                <td className="daily-cell daily-temp-cell">
                                  {day.tempMin}°/{day.tempMax}°C
                                </td>

                                <td className="daily-cell daily-risk-cell">
                                  <span className={riskBadgeClass}>
                                    {getFireRiskLabel(day.fireRisk)}
                                  </span>
                                </td>

                                <td
                                  className="daily-cell daily-hotspot-cell"
                                  style={{ textAlign: "center" }}
                                >
                                  {day.hotspots}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </section>

                  {/* History section (Authority only) */}

                  {true && (
                    <HistorySection history={history} />
                  )}
                </div>
              )}

              {activeTab === "community" && (
                <div className="tab-pane">
                  {/* Forest command strip stats */}

                  <section
                    className="community-command-strip"
                    aria-label="Community Forest Fire Management stats"
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "12px",
                    }}
                  >
                    <div className="community-command-strip__header">
                      <span className="community-command-strip__eyebrow">
                        Forest Command Center
                      </span>

                      <strong>ศูนย์จัดการเครือข่ายป่าชุมชน</strong>
                    </div>

                    <div
                      className="community-command-strip__metrics"
                      style={{
                        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                        gap: "8px",
                      }}
                    >
                      <div>
                        <span>ป่าชุมชน (Infographic)</span>

                        <b>
                          {formatNumber(
                            communityForestSummary.officialInfographicCount,
                          )}
                        </b>

                        <small>
                          {formatNumber(
                            communityForestSummary.officialInfographicAreaRai,
                          )}{" "}
                          ไร่
                        </small>
                      </div>

                      <div>
                        <span>พิกัดกรมป่าไม้</span>

                        <b>
                          {formatNumber(
                            communityForestSummary.rfdCoordinatePoints,
                          )}
                        </b>
                      </div>

                      <div>
                        <span>ข้อมูลพิกัด marker</span>

                        <b>
                          {formatNumber(
                            communityForestSummary.thaicfnetGeocodedForests,
                          )}
                        </b>
                      </div>

                      <div>
                        <span>มีข้อมูลจัดการไฟ</span>

                        <b>
                          {formatNumber(
                            communityForestSummary.detailedForestsWithFireManagement,
                          )}
                        </b>
                      </div>
                    </div>

                    <div
                      className="community-command-strip__zones"
                      style={{
                        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                        gap: "6px",
                      }}
                    >
                      {topCommunityZones.map((zone) => (
                        <div
                          key={zone.district}
                          className={`community-zone-pill community-zone-pill--${zone.health.toLowerCase()}`}
                          style={{ padding: "8px", cursor: "pointer" }}
                          onMouseEnter={() => setHoveredDistrict(zone.district)}
                          onMouseLeave={() => setHoveredDistrict(null)}
                          onClick={() => {
                            const preset = DISTRICT_PRESETS.find((p) =>
                              p.name.includes(zone.district),
                            );

                            if (preset) {
                              selectHomeLocation(preset.coords);
                            }
                          }}
                        >
                          <span>อ.{zone.district}</span>

                          <b>{zone.healthScore}/100</b>
                        </div>
                      ))}
                    </div>
                  </section>

                  {/* Village Report Intake */}

                  <div className="community-action-panel community-action-panel--form">
                    <div className="community-action-panel__head">
                      <span className="community-action-panel__icon">
                        <ClipboardList size={18} />
                      </span>

                      <div>
                        <span>Village Report Intake</span>

                        <strong>ขั้นตอนรายงานกิจกรรมป่า</strong>
                      </div>
                    </div>

                    <div
                      className="report-flow"
                      style={{
                        gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
                        gap: "8px",
                      }}
                    >
                      {[
                        ["1", "เลือกป่าชุมชน", "ฐานข้อมูลชาวบ้าน"],

                        ["2", "บันทึกกิจกรรม", "ลาดตระเวน/แนวกันไฟ"],

                        ["3", "แนบรูป + GPS", "ยืนยันหลักฐาน proof"],

                        ["4", "อัปเดตเว็บ", "คำนวณอันดับ ranking"],
                      ].map(([step, title, text]) => (
                        <div
                          key={step}
                          className="report-flow__step"
                          style={{ padding: "8px" }}
                        >
                          <span
                            style={{
                              width: "20px",
                              height: "20px",
                              fontSize: "0.74rem",
                            }}
                          >
                            {step}
                          </span>

                          <b style={{ fontSize: "0.78rem" }}>{title}</b>

                          <small style={{ fontSize: "0.62rem" }}>{text}</small>
                        </div>
                      ))}
                    </div>

                    <button
                      type="button"
                      className="report-flow__cta"
                      onClick={() =>
                        setMapSelection({
                          eyebrow: "Google Form Intake",

                          title: "ระบบรับข้อมูลกิจกรรมป้องกันไฟป่า",

                          detail:
                            "ระบบใช้ Google Form เพื่อให้ชาวบ้านถ่ายภาพและส่งพิกัดจากมือถือได้ทันที โดยจะแปลงเป็นคะแนน Forest League รายสัปดาห์",

                          stats: [
                            {
                              label: "ช่องทางส่ง",
                              value: "LINE Podd / Google Form",
                            },

                            {
                              label: "การตรวจสอบ",
                              value: "ภาพถ่ายระบุเวลา/พิกัด",
                              tone: "good",
                            },
                          ],
                        })
                      }
                    >
                      <Send size={14} />
                      ดูรายละเอียด Flow
                    </button>
                  </div>

                  {/* Open government data connectors */}

                  <div className="community-action-panel community-action-panel--data">
                    <div className="community-action-panel__head">
                      <span className="community-action-panel__icon">
                        <Database size={18} />
                      </span>

                      <div>
                        <span>ตัวเชื่อมข้อมูลเปิด</span>

                        <strong>ชุดข้อมูลประกอบการประเมิน</strong>
                      </div>
                    </div>

                    <div className="data-connector-list">
                      {dataConnectorCandidates.map((item) => (
                        <a
                          key={item.title}
                          href={item.url}
                          target="_blank"
                          rel="noreferrer"
                          className="data-connector-row"
                          style={{
                            gridTemplateColumns: "minmax(0, 1fr) auto",
                            minHeight: "44px",
                            padding: "6px 8px",
                          }}
                        >
                          <span>
                            <b style={{ fontSize: "0.78rem" }}>{item.title}</b>

                            <small style={{ fontSize: "0.62rem" }}>
                              {item.source}
                            </small>
                          </span>

                          <ExternalLink size={12} style={{ flexShrink: 0 }} />
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === "checker" && (
                <div className="tab-pane">
                  {/* GPS risk assessment */}

                  <section className="card personal-checker-card">
                    <div className="card__head">
                      <span className="card__title">
                        🏠 ตรวจสอบความเสี่ยงตำแหน่งพิกัดของฉัน
                      </span>
                    </div>

                    <p
                      className="personal-checker-desc"
                      style={{ fontSize: "0.8rem", margin: "6px 0 12px" }}
                    >
                      เลือกอำเภอหรือใช้ GPS
                      เพื่อระบุระยะห่างจุดไฟไหม้และทิศกระแสลมทันที
                    </p>

                    <div
                      className="personal-checker-actions"
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "8px",
                      }}
                    >
                      <button
                        type="button"
                        className="btn-gps"
                        onClick={() => {
                          if (navigator.geolocation) {
                            navigator.geolocation.getCurrentPosition(
                              (pos) => {
                                selectHomeLocation([
                                  pos.coords.latitude,
                                  pos.coords.longitude,
                                ]);
                              },

                              (err) => {
                                alert(`ไม่สามารถระบุพิกัดได้: ${err.message}`);
                              },
                            );
                          } else {
                            alert("เบราว์เซอร์ไม่รองรับ GPS");
                          }
                        }}
                      >
                        📍 ระบุตำแหน่งผ่าน GPS
                      </button>

                      <select
                        className="select-location"
                        value=""
                        onChange={(e) => {
                          if (e.target.value) {
                            const coords = e.target.value
                              .split(",")
                              .map(Number) as [number, number];

                            selectHomeLocation(coords);
                          }
                        }}
                      >
                        <option value="" disabled>
                          -- เลือกอำเภอในเชียงใหม่ --
                        </option>

                        {DISTRICT_PRESETS.map((p) => (
                          <option key={p.name} value={p.coords.join(",")}>
                            {p.name}
                          </option>
                        ))}
                      </select>

                      <button
                        type="button"
                        className={`btn-pin-map${isPinningMode ? " active" : ""}`}
                        onClick={() => setIsPinningMode(!isPinningMode)}
                      >
                        📌{" "}
                        {isPinningMode
                          ? "กำลังรอปักหมุด... คลิกบนแผนที่"
                          : "ปักหมุดตำแหน่งบนแผนที่"}
                      </button>
                    </div>

                    {userLocation ? (
                      <div
                        className="personal-checker-status active"
                        style={{
                          marginTop: "12px",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <span>
                          พิกัด:{" "}
                          <b>
                            {userLocation[0].toFixed(3)},{" "}
                            {userLocation[1].toFixed(3)}
                          </b>
                        </span>

                        <button
                          type="button"
                          className="btn-clear"
                          onClick={() => {
                            setUserLocation(null);

                            setIsPinningMode(false);

                            setMapSelection(initialSelection);
                          }}
                          style={{
                            padding: "3px 8px",
                            borderRadius: "4px",
                            border: "1px solid var(--line)",
                            background: "#fff",
                          }}
                        >
                          ยกเลิก
                        </button>
                      </div>
                    ) : (
                      <div
                        className="personal-checker-status"
                        style={{ marginTop: "10px" }}
                      >
                        <span style={{ fontSize: "0.74rem" }}>
                          💡 แนะนำ:
                          สามารถคลิกบนแผนที่เพื่อประเมินความเสี่ยงได้เช่นกัน
                        </span>
                      </div>
                    )}
                  </section>

                  {/* Emergency contacts card */}

                  <EmergencyContacts />
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* RIGHT MAP STAGE WRAPPER */}

        <div className="map-stage-wrapper">
          {/* Collapse/Expand Sidebar Toggle Button */}

          <button
            type="button"
            className={`sidebar-toggle-btn ${sidebarOpen ? "open" : "closed"}`}
            onClick={() => {
              setSidebarOpen(!sidebarOpen);

              setTimeout(() => {
                window.dispatchEvent(new Event("resize"));
              }, 150);
            }}
            aria-label={sidebarOpen ? "ปิดแถบข้าง" : "เปิดแถบข้าง"}
          >
            {sidebarOpen ? (
              <ChevronLeft size={16} />
            ) : (
              <ChevronRight size={16} />
            )}
          </button>

          <section
            className={`map-stage map-hero${mapFullscreen ? " map-hero--fullscreen" : ""}`}
            aria-label="แผนที่สถานการณ์เชียงใหม่"
            style={{
              width: "100%",
              height: "100%",
              border: "none",
              borderRadius: 0,
              boxShadow: "none",
            }}
          >
            <div
              className="map-layer-selector command-layer-strip"
              aria-label="ชั้นข้อมูลแผนที่"
            >
              <div className="layer-selector-title">ชั้นข้อมูลแผนที่</div>

              <button
                type="button"
                className={`layer-btn ${allOn ? "active" : ""}`}
                onClick={setAll}
                aria-pressed={allOn}
              >
                <span className="layer-dot layer-dot--all" />
                <span>ทั้งหมด</span>
              </button>

              <hr className="layer-divider" />

              <button
                type="button"
                className={`layer-btn ${layers.pm25 ? "active" : ""}`}
                onClick={() => toggleLayer("pm25")}
                aria-pressed={layers.pm25}
              >
                <span className="layer-dot layer-dot--pm" />
                <span>PM2.5</span>
              </button>

              <button
                type="button"
                className={`layer-btn ${layers.hotspots ? "active" : ""}`}
                onClick={() => toggleLayer("hotspots")}
                aria-pressed={layers.hotspots}
              >
                <span className="layer-dot layer-dot--hot" />
                <span>จุดความร้อน</span>
              </button>

              <button
                type="button"
                className={`layer-btn ${layers.wind ? "active" : ""}`}
                onClick={() => toggleLayer("wind")}
                aria-pressed={layers.wind}
              >
                <span className="layer-dot layer-dot--wind" />
                <span>ลม</span>
              </button>

              <button
                type="button"
                className={`layer-btn ${layers.fireZones ? "active" : ""}`}
                onClick={() => toggleLayer("fireZones")}
                aria-pressed={layers.fireZones}
              >
                <span className="layer-dot layer-dot--zone" />
                <span>เขตไฟ</span>
              </button>

              <button
                type="button"
                className={`layer-btn ${layers.communityForests ? "active" : ""}`}
                onClick={() => toggleLayer("communityForests")}
                aria-pressed={layers.communityForests}
              >
                <span className="layer-dot layer-dot--forest" />
                <span>ป่าชุมชน</span>
              </button>

              <button
                type="button"
                className={`layer-btn ${layers.landmarks ? "active" : ""}`}
                onClick={() => toggleLayer("landmarks")}
                aria-pressed={layers.landmarks}
              >
                <span className="layer-dot layer-dot--landmark" />
                <span>สถานที่</span>
              </button>

              <button
                type="button"
                className={`layer-btn ${layers.fuelRisk ? "active" : ""}`}
                onClick={() => toggleLayer("fuelRisk")}
                aria-pressed={layers.fuelRisk}
              >
                <span className="layer-dot layer-dot--fuel" />

                <span>NDVI</span>
              </button>

              <button
                type="button"
                className={`layer-btn ${layers.predictions ? "active" : ""}`}
                onClick={() => toggleLayer("predictions")}
                aria-pressed={layers.predictions}
              >
                <span className="layer-dot layer-dot--prediction" />
                <span>AI</span>
              </button>
            </div>

            <Suspense
              fallback={<div className="map-loading">กำลังโหลดแผนที่...</div>}
            >
              <DashboardMap
                dashboard={dashboard}
                layers={layers}
                selection={mapSelection}
                onSelectionChange={setMapSelection}
                theme={theme}
                userLocation={userLocation}
                onMapClick={selectHomeLocation}
                isPinningMode={isPinningMode}
                onPinningModeChange={setIsPinningMode}
                isFullscreen={mapFullscreen}
                onToggleFullscreen={() => setMapFullscreen((prev) => !prev)}
                hoveredDistrict={hoveredDistrict}
              />
            </Suspense>
          </section>

        </div>
      </div>

      <footer className="page-foot">
        <span>
          แหล่งข้อมูลดาวเทียมและอุตุฯ: {dashboard.hotspots.source} ·{" "}
          {dashboard.pm25.source} · {dashboard.weather.source}
        </span>

        <span>ChiangMaiEyes © 2026 · Pitching Prototype V2.0</span>
        <span className="page-foot__sources-th">
          แหล่งข้อมูลดาวเทียมและอุตุฯ: {sourceDisplayLabel(dashboard.hotspots.source)} ·{" "}
          {sourceDisplayLabel(dashboard.pm25.source)} · {sourceDisplayLabel(dashboard.weather.source)}
        </span>

        <span className="page-foot__product-th">
          ChiangMaiEyes © 2026 · ต้นแบบเวอร์ชัน 2.0
        </span>
      </footer>
    </div>
  );
}
