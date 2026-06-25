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
  frp?: number | null;
  brightness?: number | null;
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

export type SourceMode = 'LIVE' | 'SNAPSHOT' | 'DERIVED' | 'PROTOTYPE' | 'UNAVAILABLE';

export type DataQualityMetadata = {
  label: string;
  source: string;
  source_mode: SourceMode;
  latest_update?: string | null;
  checked_at?: string | null;
  age_minutes?: number | null;
  update_cadence_minutes?: number | null;
  expected_observation_lag_minutes?: number | null;
  confidence: number;
  is_stale: boolean;
  note: string;
  decision_use?: string | null;
};

export type HotspotTrendStats = {
  window_days: number;
  recent_count: number;
  previous_count: number;
  change_percent: number;
  source: string;
};

export type DroughtZone = {
  id: string;
  location_name: string;
  latitude: number;
  longitude: number;
  soil_moisture_percent: number;
  drought_index: number;
  trend: 'improving' | 'stable' | 'drying';
  risk_level: 'low' | 'medium' | 'high' | 'critical';
};

export type SatelliteDrynessZone = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  radius_m: number;
  ndvi: number;
  ndmi: number;
  nbr: number;
  dryness_class: 'moderate' | 'high' | 'critical';
  dnbr?: number | null;
  burn_severity?: 'unburned' | 'low' | 'moderate' | 'high' | null;
  updated_at: string;
  source: string;
};

export type SatelliteLayerResponse = {
  source_mode: SourceMode;
  source: string;
  generated_at: string;
  dataset_ids: string[];
  cadence: string;
  dryness_zones: SatelliteDrynessZone[];
  notes: string[];
};

export type LanduseBreakdownItem = {
  landuse_type: string;
  label: string;
  count: number;
  percent: number;
};

export type WeeklyForestScoreBreakdown = {
  management: number;
  prevention: number;
  utilization: number;
  ecological_outcome: number;
};

export type CommunityForestSatelliteContext = {
  source_mode: SourceMode;
  nearest_zone_id: string;
  nearest_zone_name: string;
  dryness_class: "moderate" | "high" | "critical";
  distance_km: number;
  ndvi: number;
  ndmi: number;
  nbr: number;
  rainfall_30d_mm?: number | null;
  slope_mean_deg?: number | null;
  hotspot_pressure_7d: number;
  fire_pressure_index: number;
};

export type WeeklyForestRankingEntry = {
  forest_id: string;
  forest_name: string;
  village: string;
  tambon: string;
  amphoe: string;
  latitude: number;
  longitude: number;
  total_score: number;
  rank: number;
  report_count: number;
  last_report_at: string;
  score_breakdown: WeeklyForestScoreBreakdown;
  reasons: string[];
  authority_owner?: string | null;
  boundary_source?: string | null;
  boundary_confidence?: "official" | "estimated" | "prototype" | null;
  verification_status?: "verified" | "review_needed" | "prototype" | null;
  hotspot_activity_delta_percent?: number | null;
  satellite_context?: CommunityForestSatelliteContext | null;
};

export type WeeklyForestLeagueResponse = {
  week_id: string;
  scoring_window: string;
  scheduled_recompute: string;
  rate_limit_rule: string;
  ranking: WeeklyForestRankingEntry[];
  source_mode?: SourceMode;
};

export type LocalizedPrediction = {
  id: string;
  locationName: string;
  latitude: number;
  longitude: number;
  forecastType: 'dust' | 'fire';
  severity: 'watch' | 'high' | 'critical';
  reason_for_prediction: string;
  lead_time_hours: number;
};

export type OperationalIntelligenceResponse = {
  hotspot_trend: HotspotTrendStats;
  drought_zones: DroughtZone[];
  satellite_layers?: SatelliteLayerResponse | null;
  landuse_breakdown: LanduseBreakdownItem[];
  weekly_forest_league: WeeklyForestLeagueResponse;
  localizedPredictions: LocalizedPrediction[];
  source_notes: string[];
};

export type DistrictFirePhase = {
  district: string;
  phase: 'normal' | 'before' | 'during' | 'after';
  color: 'green' | 'yellow' | 'red' | 'grey';
  danger_score: number;
  active_hotspots: number;
  reasons: string[];
};

export type FirePhaseResponse = {
  generated_at: string;
  source_mode: SourceMode;
  phases: DistrictFirePhase[];
  notes: string[];
};

export type DashboardResponse = {
  hotspots: HotspotResponse;
  pm25: Pm25Response;
  weather: WeatherResponse;
  risk: RiskResponse;
  summary: SummaryResponse;
  intelligence?: OperationalIntelligenceResponse | null;
  data_quality?: Record<string, DataQualityMetadata>;
};

export type DataStatusResponse = {
  mode: 'local-refresh-snapshot' | 'live-backend';
  latest_update: string;
  snapshot_age_minutes: number;
  refresh_checked_at?: string | null;
  refresh_age_minutes?: number | null;
  refresh_status?: string | null;
  hotspot_latest_update?: string;
  hotspot_age_minutes?: number;
  pm25_latest_update?: string;
  pm25_age_minutes?: number;
  weather_latest_update?: string;
  weather_age_minutes?: number;
  hotspot_count: number;
  source: string;
  source_breakdown?: Record<string, number>;
  local_refresh_required: boolean;
  vercel_fetches_rfd_directly: boolean;
  data_quality?: Record<string, DataQualityMetadata>;
  notes: string[];
};
