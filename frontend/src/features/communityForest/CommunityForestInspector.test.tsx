import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CommunityForestInspector } from "./CommunityForestInspector";
import type { CommunityForestRow } from "./communityForestData";

const row: CommunityForestRow = {
  id: "cf-1",
  rank: 1,
  forestName: "Mae Chaem Community Forest",
  village: "Mae Pan",
  tambon: "Chang Khoeng",
  amphoe: "Mae Chaem",
  score: 91,
  reportCount: 4,
  lastReportAt: "2026-06-07T07:30:00+07:00",
  reasons: ["patrol", "firebreak"],
  sourceMode: "PROTOTYPE",
  latitude: 18.503,
  longitude: 98.361,
  authorityOwner: "Mae Chaem committee",
  boundarySource: "Prototype point",
  boundaryConfidence: "prototype",
  verificationStatus: "prototype",
  hotspotActivityDeltaPercent: -12.5,
  satelliteContext: {
    sourceMode: "DERIVED",
    nearestZoneId: "mae-chaem-reserve",
    nearestZoneName: "Mae Chaem reserved forest",
    drynessClass: "critical",
    distanceKm: 1.2,
    ndvi: 0.25,
    ndmi: -0.11,
    nbr: 0.14,
    rainfall30dMm: null,
    slopeMeanDeg: 21.4,
    hotspotPressure7d: 7,
    firePressureIndex: 81.5,
  },
  scoreBreakdown: {
    management: 21,
    prevention: 30,
    utilization: 20,
    ecologicalOutcome: 20,
  },
};

describe("CommunityForestInspector", () => {
  it("renders boundary authority and verification context", () => {
    const html = renderToStaticMarkup(<CommunityForestInspector row={row} />);

    expect(html).toContain("Mae Chaem committee");
    expect(html).toContain("Prototype point");
    expect(html).toContain("prototype");
    expect(html).toContain("-12.5%");
    expect(html).toContain("Mae Chaem reserved forest");
    expect(html).toContain("81.5");
    expect(html).toContain("critical");
  });
});
