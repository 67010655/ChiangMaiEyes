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
};

export type HotspotResponse = {
  count: number;
  density_per_100_km2: number;
  latest_update: string;
  source: string;
  items: Hotspot[];
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
