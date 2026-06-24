import { describe, expect, it } from "vitest";

import {
  buildCommunityForestRows,
  buildCommunityForestRowsFromRanking,
  sourceModeForCommunityForest,
} from "./communityForestData";
import type { DashboardResponse } from "../../lib/types";

describe("communityForestData", () => {
  it("combines weekly league ranking into UI rows", () => {
    const dashboard = {
      intelligence: {
        weekly_forest_league: {
          week_id: "2026-06-07",
          scoring_window: "2026-06-01 to 2026-06-07",
          scheduled_recompute: "Sunday 23:55",
          rate_limit_rule: "one report per forest/village/day",
          ranking: [
            {
              forest_id: "cf-1",
              forest_name: "ป่าชุมชนแม่แจ่ม",
              village: "บ้านแม่ปาน",
              tambon: "ช่างเคิ่ง",
              amphoe: "แม่แจ่ม",
              latitude: 18.503,
              longitude: 98.361,
              total_score: 87,
              rank: 1,
              report_count: 3,
              last_report_at: "2026-06-07T07:30:00+07:00",
              authority_owner: "Mae Chaem committee",
              boundary_source: "Prototype point",
              boundary_confidence: "prototype",
              verification_status: "prototype",
              hotspot_activity_delta_percent: -12.5,
              satellite_context: {
                source_mode: "DERIVED",
                nearest_zone_id: "mae-chaem-reserve",
                nearest_zone_name: "Mae Chaem reserved forest",
                dryness_class: "critical",
                distance_km: 1.2,
                ndvi: 0.25,
                ndmi: -0.11,
                nbr: 0.14,
                rainfall_30d_mm: null,
                slope_mean_deg: 21.4,
                hotspot_pressure_7d: 7,
                fire_pressure_index: 81.5,
              },
              score_breakdown: {
                management: 25,
                prevention: 30,
                utilization: 17,
                ecological_outcome: 15,
              },
              reasons: ["ลาดตระเวน", "แนวกันไฟ"],
            },
          ],
        },
      },
      data_quality: {
        community_forests: {
          label: "Community forest league",
          source: "Seed reports",
          source_mode: "PROTOTYPE",
          confidence: 0.4,
          is_stale: false,
          note: "prototype",
        },
      },
    } as unknown as DashboardResponse;

    const rows = buildCommunityForestRows(dashboard);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      id: "cf-1",
      forestName: "ป่าชุมชนแม่แจ่ม",
      amphoe: "แม่แจ่ม",
      score: 87,
      sourceMode: "PROTOTYPE",
      authorityOwner: "Mae Chaem committee",
      boundaryConfidence: "prototype",
      hotspotActivityDeltaPercent: -12.5,
    });
    expect(rows[0].satelliteContext).toMatchObject({
      nearestZoneName: "Mae Chaem reserved forest",
      drynessClass: "critical",
      firePressureIndex: 81.5,
    });
    expect(rows[0].reasons).toEqual(["ลาดตระเวน", "แนวกันไฟ"]);
  });

  it("defaults community forest source mode to PROTOTYPE when data_quality is missing", () => {
    expect(sourceModeForCommunityForest({} as DashboardResponse)).toBe(
      "PROTOTYPE",
    );
  });

  it("builds rows from a merged ranking list", () => {
    const rows = buildCommunityForestRowsFromRanking(
      [
        {
          forest_id: "cf-2",
          forest_name: "ป่าชุมชนสะเมิง",
          village: "บ้านแม่สาบ",
          tambon: "สะเมิงใต้",
          amphoe: "สะเมิง",
          latitude: 18.849,
          longitude: 98.73,
          total_score: 71,
          rank: 2,
          report_count: 2,
          last_report_at: "2026-06-06T10:00:00+07:00",
          score_breakdown: {
            management: 20,
            prevention: 22,
            utilization: 14,
            ecological_outcome: 15,
          },
          reasons: ["จัดการเชื้อเพลิง"],
        },
      ],
      "DERIVED",
    );

    expect(rows[0]).toMatchObject({
      id: "cf-2",
      forestName: "ป่าชุมชนสะเมิง",
      score: 71,
      sourceMode: "DERIVED",
    });
  });
});
