import type {
  DashboardResponse,
  SourceMode,
  WeeklyForestRankingEntry,
} from "../../lib/types";

export type CommunityForestRow = {
  id: string;
  rank: number;
  forestName: string;
  village: string;
  tambon: string;
  amphoe: string;
  score: number;
  reportCount: number;
  lastReportAt: string;
  reasons: string[];
  sourceMode: SourceMode;
  latitude: number;
  longitude: number;
  authorityOwner: string | null;
  boundarySource: string | null;
  boundaryConfidence: "official" | "estimated" | "prototype" | null;
  verificationStatus: "verified" | "review_needed" | "prototype" | null;
  hotspotActivityDeltaPercent: number | null;
  satelliteContext: {
    sourceMode: SourceMode;
    nearestZoneId: string;
    nearestZoneName: string;
    drynessClass: "moderate" | "high" | "critical";
    distanceKm: number;
    ndvi: number;
    ndmi: number;
    nbr: number;
    rainfall30dMm: number | null;
    slopeMeanDeg: number | null;
    hotspotPressure7d: number;
    firePressureIndex: number;
  } | null;
  scoreBreakdown: {
    management: number;
    prevention: number;
    utilization: number;
    ecologicalOutcome: number;
  };
};

export function sourceModeForCommunityForest(
  dashboard: DashboardResponse,
): SourceMode {
  return dashboard.data_quality?.community_forests?.source_mode ?? "PROTOTYPE";
}

export function buildCommunityForestRows(
  dashboard: DashboardResponse,
): CommunityForestRow[] {
  return buildCommunityForestRowsFromRanking(
    dashboard.intelligence?.weekly_forest_league.ranking ?? [],
    sourceModeForCommunityForest(dashboard),
  );
}

export function buildCommunityForestRowsFromRanking(
  ranking: WeeklyForestRankingEntry[],
  sourceMode: SourceMode,
): CommunityForestRow[] {
  return ranking.map((entry) => ({
    id: entry.forest_id,
    rank: entry.rank,
    forestName: entry.forest_name,
    village: entry.village,
    tambon: entry.tambon,
    amphoe: entry.amphoe,
    score: entry.total_score,
    reportCount: entry.report_count,
    lastReportAt: entry.last_report_at,
    reasons: entry.reasons,
    sourceMode,
    latitude: entry.latitude,
    longitude: entry.longitude,
    authorityOwner: entry.authority_owner ?? null,
    boundarySource: entry.boundary_source ?? null,
    boundaryConfidence: entry.boundary_confidence ?? null,
    verificationStatus: entry.verification_status ?? null,
    hotspotActivityDeltaPercent: entry.hotspot_activity_delta_percent ?? null,
    satelliteContext: entry.satellite_context
      ? {
          sourceMode: entry.satellite_context.source_mode,
          nearestZoneId: entry.satellite_context.nearest_zone_id,
          nearestZoneName: entry.satellite_context.nearest_zone_name,
          drynessClass: entry.satellite_context.dryness_class,
          distanceKm: entry.satellite_context.distance_km,
          ndvi: entry.satellite_context.ndvi,
          ndmi: entry.satellite_context.ndmi,
          nbr: entry.satellite_context.nbr,
          rainfall30dMm: entry.satellite_context.rainfall_30d_mm ?? null,
          slopeMeanDeg: entry.satellite_context.slope_mean_deg ?? null,
          hotspotPressure7d: entry.satellite_context.hotspot_pressure_7d,
          firePressureIndex: entry.satellite_context.fire_pressure_index,
        }
      : null,
    scoreBreakdown: {
      management: entry.score_breakdown.management,
      prevention: entry.score_breakdown.prevention,
      utilization: entry.score_breakdown.utilization,
      ecologicalOutcome: entry.score_breakdown.ecological_outcome,
    },
  }));
}
