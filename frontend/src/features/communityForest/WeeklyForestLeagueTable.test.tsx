import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WeeklyForestLeagueTable } from "./WeeklyForestLeagueTable";
import type { CommunityForestRow } from "./communityForestData";

const rows: CommunityForestRow[] = [
  {
    id: "cf-1",
    rank: 1,
    forestName: "ป่าชุมชนแม่แจ่ม",
    village: "บ้านแม่ปาน",
    tambon: "ช่างเคิ่ง",
    amphoe: "แม่แจ่ม",
    score: 87,
    reportCount: 3,
    lastReportAt: "2026-06-07T07:30:00+07:00",
    reasons: ["ลาดตระเวน", "แนวกันไฟ"],
    sourceMode: "PROTOTYPE",
    latitude: 18.503,
    longitude: 98.361,
    authorityOwner: "Mae Chaem committee",
    boundarySource: "Prototype point",
    boundaryConfidence: "prototype",
    verificationStatus: "prototype",
    hotspotActivityDeltaPercent: -12.5,
    satelliteContext: null,
    scoreBreakdown: {
      management: 25,
      prevention: 30,
      utilization: 17,
      ecologicalOutcome: 15,
    },
  },
];

describe("WeeklyForestLeagueTable", () => {
  it("renders accountability columns, source status, and boundary confidence", () => {
    const html = renderToStaticMarkup(
      <WeeklyForestLeagueTable
        rows={rows}
        selectedId="cf-1"
        onSelect={() => undefined}
      />,
    );
    expect(html).toContain("prototype");
    expect(html).toContain("Prototype point");

    expect(html).toContain("อันดับ");
    expect(html).toContain("ป่าชุมชนแม่แจ่ม");
    expect(html).toContain("แนวกันไฟ");
    expect(html).toContain("ข้อมูลต้นแบบ");
  });
});
