import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { MapLibreTerrainView } from "./MapLibreTerrainView";
import type { DashboardResponse } from "../../lib/types";

const dashboard = {
  hotspots: {
    count: 1,
    density_per_100_km2: 0.2,
    latest_update: "2026-06-21T14:00:00+07:00",
    source: "test",
    items: [
      {
        id: "hot-1",
        latitude: 18.79,
        longitude: 98.98,
        district: "เมืองเชียงใหม่",
        confidence: 80,
        source: "test",
        detected_at: "2026-06-21T14:00:00+07:00",
      },
    ],
  },
  pm25: {
    current_pm25: 18,
    category: "ดีมาก",
    color: "green",
    trend: "stable",
    latest_update: "2026-06-21T14:00:00+07:00",
    source: "test",
    stations: [
      {
        id: "PM-1",
        name: "Chiang Mai",
        district: "เมืองเชียงใหม่",
        latitude: 18.78,
        longitude: 98.99,
        pm25: 18,
        trend: "stable",
        updated_at: "2026-06-21T14:00:00+07:00",
      },
    ],
  },
  weather: {
    wind_speed_kmh: 12,
    wind_direction_deg: 90,
    wind_direction_text: "ทิศตะวันออก",
    temperature_c: 32,
    humidity_percent: 60,
    latest_update: "2026-06-21T14:00:00+07:00",
    source: "test",
    station_latitude: 18.77,
    station_longitude: 98.97,
  },
  risk: { score: 4, category: "Medium", formula: "test", factors: {} },
  summary: { language: "th", text: "test", source: "test" },
} satisfies DashboardResponse;

describe("MapLibreTerrainView", () => {
  it("renders a terrain container even when MapTiler credentials are absent", () => {
    const html = renderToStaticMarkup(<MapLibreTerrainView mapTilerKey="" />);

    expect(html).toContain("maplibre-terrain-view");
    expect(html).toContain("3D terrain map");
  });

  it("renders 3D terrain controls for basemap, height, and building blocks", () => {
    const html = renderToStaticMarkup(<MapLibreTerrainView mapTilerKey="" />);

    expect(html).toContain("Base map");
    expect(html).toContain("Relief");
    expect(html).toContain("Satellite");
    expect(html).toContain("Terrain height");
    expect(html).toContain("4x");
    expect(html).toContain("Prototype buildings");
    expect(html).toContain("DEM terrain");
  });

  it("renders operational data legend and wind compass when dashboard data is provided", () => {
    const html = renderToStaticMarkup(
      <MapLibreTerrainView
        dashboard={dashboard}
        layers={{
          hotspots: true,
          pm25: true,
          wind: true,
          communityForests: true,
          fireZones: true,
        }}
        mapTilerKey=""
      />,
    );

    expect(html).toContain("3D map data overlays");
    expect(html).toContain("PM2.5 area");
    expect(html).toContain("Hotspot");
    expect(html).toContain("ป่าชุมชน");
    expect(html).toContain("เขตไฟ/ลม");
    expect(html).toContain("ลมไป");
    expect(html).toContain("12 km/h");
  });
});
