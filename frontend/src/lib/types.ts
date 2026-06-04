export type Hotspot = {
  id: string;
  latitude: number;
  longitude: number;
  district: string;
  subdistrict?: string | null;
  landuse_type?: string | null;
  landuse_name?: string | null;
  satellite?: string | null;
  confidence: number;
  source: string;
  detected_at: string;
  sources?: string[];
  source_count?: number;
};

export type HotspotResponse = {
  count: number;
  density_per_100_km2: number;
  latest_update: string;
  source: string;
  items: Hotspot[];
  source_breakdown?: Record<string, number>;
};

export type HotspotHistoryDay = {
  date: string;
  count: number;
};

export type HotspotHistoryResponse = {
  days: HotspotHistoryDay[];
  source: string;
  latest_update: string;
};

export type DailyMetric = {
  date: string;
  value: number;
};

export type WeatherHistoryDay = {
  date: string;
  temp_max: number;
  temp_min: number;
  wind_max: number;
  humidity: number;
};

export type HistoryResponse = {
  days: number;
  hotspots: HotspotHistoryDay[];
  pm25: DailyMetric[];
  weather: WeatherHistoryDay[];
  sources: Record<string, string>;
  latest_update: string;
};

export type Pm25Station = {
  id: string;
  name: string;
  district: string;
  latitude: number;
  longitude: number;
  pm25: number;
  trend: string;
  updated_at: string;
};

export type Pm25Response = {
  current_pm25: number;
  category: string;
  color: 'green' | 'yellow' | 'orange' | 'red' | 'purple';
  trend: string;
  latest_update: string;
  source: string;
  stations: Pm25Station[];
};

export type WeatherResponse = {
  wind_speed_kmh: number;
  wind_direction_deg: number;
  wind_direction_text: string;
  temperature_c: number;
  humidity_percent: number;
  latest_update: string;
  source: string;
  station_name?: string | null;
  station_latitude?: number | null;
  station_longitude?: number | null;
  pressure_hpa?: number | null;
  rain_15m_mm?: number | null;
  rain_1h_mm?: number | null;
  rain_today_mm?: number | null;
  temperature_min_today_c?: number | null;
  temperature_max_today_c?: number | null;
};

export type RiskResponse = {
  score: number;
  category: 'Low' | 'Medium' | 'High';
  formula: string;
  factors: Record<string, number | string>;
};

export type SummaryResponse = {
  language: string;
  text: string;
  source: string;
};

export type DashboardResponse = {
  hotspots: HotspotResponse;
  pm25: Pm25Response;
  weather: WeatherResponse;
  risk: RiskResponse;
  summary: SummaryResponse;
};

export type DataStatusResponse = {
  mode: 'local-refresh-snapshot' | 'live-backend';
  latest_update: string;
  snapshot_age_minutes: number;
  hotspot_count: number;
  source: string;
  source_breakdown?: Record<string, number>;
  local_refresh_required: boolean;
  vercel_fetches_rfd_directly: boolean;
  notes: string[];
};
