import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import "../../styles/terrain.css";

import communityForestData from "../../data/community-forests-prototype.json";
import fireZoneData from "../../data/fire-management-zones-prototype.json";
import { windDestinationName } from "../../lib/wind";
import type { DashboardResponse } from "../../lib/types";

type Props = {
  dashboard?: DashboardResponse;
  layers?: TerrainLayerState;
  mapTilerKey?: string;
};

type BasemapId = "relief" | "streets" | "satellite";

type TerrainLayerState = {
  hotspots: boolean;
  pm25: boolean;
  wind: boolean;
  communityForests: boolean;
  fireZones: boolean;
};

type BuildingFeature = {
  type: "Feature";
  properties: {
    height: number;
    color: string;
  };
  geometry: {
    type: "Polygon";
    coordinates: number[][][];
  };
};

type BuildingCollection = {
  type: "FeatureCollection";
  features: BuildingFeature[];
};

type GeoFeature = {
  type: "Feature";
  properties: Record<string, string | number | boolean | null>;
  geometry: {
    type: "Point" | "LineString" | "Polygon" | "MultiPolygon";
    coordinates: unknown;
  };
};

type GeoCollection = {
  type: "FeatureCollection";
  features: GeoFeature[];
};

type CommunityForest = {
  id: string;
  name: string;
  amphoe: string;
  lat: number;
  lng: number;
  estimatedBoundaryRadiusM: number;
  fireManagement: boolean;
};

type FireManagementZone = {
  id: string;
  name: string;
  health: "Green" | "Yellow" | "Red";
  geometry: GeoFeature["geometry"];
};

type TerrainInspector = {
  eyebrow: string;
  title: string;
  detail: string;
  lng: number;
  lat: number;
  stats: Array<{ label: string; value: string }>;
};

const BASEMAPS: Array<{ id: BasemapId; label: string }> = [
  { id: "relief", label: "Relief" },
  { id: "streets", label: "Street" },
  { id: "satellite", label: "Satellite" },
];

const EXAGGERATION_LEVELS = [1.6, 2.6, 4] as const;
const DEFAULT_EXAGGERATION = 2.6;
const CAMERA_CENTER: [number, number] = [98.975, 18.79];
const CAMERA_ZOOM = 10.95;
const CAMERA_PITCH = 54;
const CAMERA_BEARING = -24;
const DEFAULT_LAYERS: TerrainLayerState = {
  hotspots: true,
  pm25: true,
  wind: true,
  communityForests: true,
  fireZones: true,
};

const INSPECTABLE_LAYER_IDS = [
  "pm25-point-circle",
  "pm25-area-fill",
  "hotspot-point-circle",
  "hotspot-plume-fill",
  "fire-zone-fill",
  "community-boundary-fill",
  "community-point-circle",
  "wind-vector-line",
  "real-buildings-fill",
] as const;

const COMMUNITY_FORESTS = (
  communityForestData as { forests: CommunityForest[] }
).forests;

const FIRE_MANAGEMENT_ZONES = (fireZoneData as { zones: FireManagementZone[] })
  .zones;

function emptyCollection(): GeoCollection {
  return { type: "FeatureCollection", features: [] };
}

function circlePolygon(
  lng: number,
  lat: number,
  radiusMeters: number,
  steps = 48,
): number[][][] {
  const earthRadius = 6371008.8;
  const latRad = (lat * Math.PI) / 180;
  const lngRad = (lng * Math.PI) / 180;
  const angularDistance = radiusMeters / earthRadius;
  const ring: number[][] = [];

  for (let i = 0; i <= steps; i += 1) {
    const bearing = (i / steps) * Math.PI * 2;
    const pointLat = Math.asin(
      Math.sin(latRad) * Math.cos(angularDistance) +
        Math.cos(latRad) * Math.sin(angularDistance) * Math.cos(bearing),
    );
    const pointLng =
      lngRad +
      Math.atan2(
        Math.sin(bearing) * Math.sin(angularDistance) * Math.cos(latRad),
        Math.cos(angularDistance) - Math.sin(latRad) * Math.sin(pointLat),
      );
    ring.push([(pointLng * 180) / Math.PI, (pointLat * 180) / Math.PI]);
  }

  return [ring];
}

function pm25Color(pm25: number) {
  if (pm25 <= 25) return "#16a34a";
  if (pm25 <= 37) return "#eab308";
  if (pm25 <= 50) return "#f97316";
  if (pm25 <= 90) return "#dc2626";
  return "#7c3aed";
}

function pm25RadiusMeters(pm25: number) {
  return 4000 + (Math.min(pm25, 120) / 120) * 13000;
}

function zoneHealthColor(health: FireManagementZone["health"]) {
  if (health === "Green") return "#16a34a";
  if (health === "Yellow") return "#eab308";
  return "#dc2626";
}

function windLineFromWeather(dashboard: DashboardResponse): GeoFeature {
  const origin: [number, number] = [
    dashboard.weather.station_longitude ?? 98.9692,
    dashboard.weather.station_latitude ?? 18.7711,
  ];
  const towardsRad = ((dashboard.weather.wind_direction_deg + 180) * Math.PI) / 180;
  const distance = 0.09 + Math.min(0.08, dashboard.weather.wind_speed_kmh / 260);
  const latScale = Math.cos((origin[1] * Math.PI) / 180);
  const end: [number, number] = [
    origin[0] + (distance * Math.sin(towardsRad)) / latScale,
    origin[1] + distance * Math.cos(towardsRad),
  ];

  return {
    type: "Feature",
    properties: {
      kind: "Wind vector",
      speed: dashboard.weather.wind_speed_kmh,
      direction: dashboard.weather.wind_direction_deg,
    },
    geometry: {
      type: "LineString",
      coordinates: [origin, end],
    },
  };
}

function buildTerrainData(
  dashboard?: DashboardResponse,
  layers: TerrainLayerState = DEFAULT_LAYERS,
) {
  const pm25Areas = emptyCollection();
  const pm25Points = emptyCollection();
  const hotspotPoints = emptyCollection();
  const hotspotPlumes = emptyCollection();
  const fireZones = emptyCollection();
  const communityBoundaries = emptyCollection();
  const communityPoints = emptyCollection();
  const windVector = emptyCollection();

  if (dashboard && layers.pm25) {
    const aggregatePm = dashboard.pm25.current_pm25;
    pm25Areas.features.push({
      type: "Feature",
      properties: {
        kind: "PM2.5 area",
        label: "PM2.5 province average",
        value: aggregatePm,
        color: pm25Color(aggregatePm),
      },
      geometry: {
        type: "Polygon",
        coordinates: circlePolygon(98.6, 18.78, pm25RadiusMeters(aggregatePm) * 1.35),
      },
    });

    dashboard.pm25.stations.forEach((station) => {
      pm25Areas.features.push({
        type: "Feature",
        properties: {
          kind: "PM2.5 area",
          label: station.name || station.id,
          value: station.pm25,
          color: pm25Color(station.pm25),
        },
        geometry: {
          type: "Polygon",
          coordinates: circlePolygon(
            station.longitude,
            station.latitude,
            pm25RadiusMeters(station.pm25),
          ),
        },
      });
      pm25Points.features.push({
        type: "Feature",
        properties: {
          kind: "PM2.5 station",
          label: station.name || station.id,
          value: station.pm25,
          color: pm25Color(station.pm25),
        },
        geometry: {
          type: "Point",
          coordinates: [station.longitude, station.latitude],
        },
      });
    });
  }

  if (dashboard && layers.hotspots) {
    dashboard.hotspots.items.forEach((hotspot) => {
      hotspotPoints.features.push({
        type: "Feature",
        properties: {
          kind: "Hotspot",
          label: hotspot.landuse_name || hotspot.district || hotspot.id,
          confidence: hotspot.confidence,
          source: hotspot.source,
        },
        geometry: {
          type: "Point",
          coordinates: [hotspot.longitude, hotspot.latitude],
        },
      });

      if (layers.wind) {
        const windDir = dashboard.weather.wind_direction_deg;
        const windSpeed = dashboard.weather.wind_speed_kmh;
        const towardsRad = ((windDir + 180) * Math.PI) / 180;
        const length = 0.025 + Math.min(0.09, (windSpeed / 32) * 0.09);
        const spreadHalfRad = 0.3;
        const latScale = Math.cos((hotspot.latitude * Math.PI) / 180);
        const pointA = [
          hotspot.longitude + (length * Math.sin(towardsRad - spreadHalfRad)) / latScale,
          hotspot.latitude + length * Math.cos(towardsRad - spreadHalfRad),
        ];
        const pointB = [
          hotspot.longitude + (length * Math.sin(towardsRad + spreadHalfRad)) / latScale,
          hotspot.latitude + length * Math.cos(towardsRad + spreadHalfRad),
        ];
        hotspotPlumes.features.push({
          type: "Feature",
          properties: { kind: "Smoke plume", label: "Smoke plume", speed: windSpeed },
          geometry: {
            type: "Polygon",
            coordinates: [[[hotspot.longitude, hotspot.latitude], pointA, pointB, [hotspot.longitude, hotspot.latitude]]],
          },
        });
      }
    });
  }

  if (layers.fireZones) {
    FIRE_MANAGEMENT_ZONES.forEach((zone) => {
      fireZones.features.push({
        type: "Feature",
        properties: {
          id: zone.id,
          kind: "Fire zone",
          label: zone.name,
          health: zone.health,
          color: zoneHealthColor(zone.health),
        },
        geometry: zone.geometry,
      });
    });
  }

  if (layers.communityForests) {
    COMMUNITY_FORESTS.forEach((forest) => {
      const color = forest.fireManagement ? "#10b981" : "#f59e0b";
      communityBoundaries.features.push({
        type: "Feature",
        properties: {
          id: forest.id,
          kind: "Community forest boundary",
          label: forest.name,
          amphoe: forest.amphoe,
          boundary: "Estimated radius from prototype community forest point",
          color,
        },
        geometry: {
          type: "Polygon",
          coordinates: circlePolygon(
            forest.lng,
            forest.lat,
            forest.estimatedBoundaryRadiusM,
          ),
        },
      });
      communityPoints.features.push({
        type: "Feature",
        properties: {
          id: forest.id,
          kind: "Community forest",
          label: forest.name,
          amphoe: forest.amphoe,
          active: forest.fireManagement,
          color,
        },
        geometry: {
          type: "Point",
          coordinates: [forest.lng, forest.lat],
        },
      });
    });
  }

  if (dashboard && layers.wind) {
    windVector.features.push(windLineFromWeather(dashboard));
  }

  return {
    pm25Areas,
    pm25Points,
    hotspotPoints,
    hotspotPlumes,
    fireZones,
    communityBoundaries,
    communityPoints,
    windVector,
  };
}

function setSourceData(map: maplibregl.Map, id: string, data: GeoCollection) {
  const source = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
  source?.setData(data as never);
}

function updateTerrainSources(
  map: maplibregl.Map,
  dashboard?: DashboardResponse,
  layers?: TerrainLayerState,
) {
  const data = buildTerrainData(dashboard, layers);
  setSourceData(map, "pm25-areas", data.pm25Areas);
  setSourceData(map, "pm25-points", data.pm25Points);
  setSourceData(map, "hotspot-points", data.hotspotPoints);
  setSourceData(map, "hotspot-plumes", data.hotspotPlumes);
  setSourceData(map, "fire-zones", data.fireZones);
  setSourceData(map, "community-boundaries", data.communityBoundaries);
  setSourceData(map, "community-points", data.communityPoints);
  setSourceData(map, "wind-vector", data.windVector);
}

function propText(
  properties: Record<string, unknown> | null | undefined,
  key: string,
  fallback = "",
) {
  const value = properties?.[key];
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function propNumber(
  properties: Record<string, unknown> | null | undefined,
  key: string,
) {
  const value = properties?.[key];
  if (typeof value === "number") return value;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function buildInspector(
  feature: maplibregl.MapGeoJSONFeature,
  lngLat: maplibregl.LngLat,
): TerrainInspector {
  const properties = feature.properties as Record<string, unknown> | undefined;
  const kind = propText(properties, "kind", "Map layer");
  const label = propText(properties, "label", kind);
  const lng = Number(lngLat.lng.toFixed(5));
  const lat = Number(lngLat.lat.toFixed(5));
  const value = propNumber(properties, "value");
  const confidence = propNumber(properties, "confidence");
  const speed = propNumber(properties, "speed");
  const direction = propNumber(properties, "direction");
  const health = propText(properties, "health");
  const amphoe = propText(properties, "amphoe");
  const source = propText(properties, "source");
  const boundary = propText(properties, "boundary");

  const stats = [
    value !== null ? { label: "Value", value: String(value) } : null,
    confidence !== null ? { label: "Confidence", value: `${confidence}%` } : null,
    speed !== null ? { label: "Wind speed", value: `${speed} km/h` } : null,
    direction !== null ? { label: "Wind direction", value: `${direction} deg` } : null,
    health ? { label: "Zone health", value: health } : null,
    amphoe ? { label: "District", value: amphoe } : null,
    source ? { label: "Source", value: source } : null,
    boundary ? { label: "Boundary", value: boundary } : null,
    { label: "Coordinates", value: `${lat.toFixed(5)}, ${lng.toFixed(5)}` },
  ].filter(Boolean) as TerrainInspector["stats"];

  return {
    eyebrow: kind,
    title: label,
    detail: `${kind} at ${lat.toFixed(5)}, ${lng.toFixed(5)}`,
    lng,
    lat,
    stats,
  };
}

function pointInspector(
  eyebrow: string,
  title: string,
  detail: string,
  lng: number,
  lat: number,
  stats: TerrainInspector["stats"] = [],
): TerrainInspector {
  const roundedLng = Number(lng.toFixed(5));
  const roundedLat = Number(lat.toFixed(5));
  return {
    eyebrow,
    title,
    detail,
    lng: roundedLng,
    lat: roundedLat,
    stats: [
      ...stats,
      { label: "Coordinates", value: `${roundedLat.toFixed(5)}, ${roundedLng.toFixed(5)}` },
    ],
  };
}

function geometryCenter(geometry: GeoFeature["geometry"]): [number, number] | null {
  const points: number[][] = [];
  const collect = (value: unknown) => {
    if (!Array.isArray(value)) return;
    if (
      value.length >= 2 &&
      typeof value[0] === "number" &&
      typeof value[1] === "number"
    ) {
      points.push(value as number[]);
      return;
    }
    value.forEach(collect);
  };

  collect(geometry.coordinates);
  if (!points.length) return null;
  const sums = points.reduce(
    (acc, point) => [acc[0] + point[0], acc[1] + point[1]],
    [0, 0],
  );
  return [sums[0] / points.length, sums[1] / points.length];
}

function createTerrainMarker(
  map: maplibregl.Map,
  lng: number,
  lat: number,
  className: string,
  label: string,
  onClick: () => void,
) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = `terrain-map-marker ${className}`;
  element.setAttribute("aria-label", label);
  element.title = label;
  element.addEventListener("click", (event) => {
    event.stopPropagation();
    onClick();
  });

  return new maplibregl.Marker({
    element,
    anchor: "center",
    pitchAlignment: "map",
    rotationAlignment: "viewport",
  })
    .setLngLat([lng, lat])
    .addTo(map);
}

function rectangle(
  lng: number,
  lat: number,
  width: number,
  height: number,
  extrusion: number,
): BuildingFeature {
  return {
    type: "Feature",
    properties: {
      height: extrusion,
      color: extrusion > 90 ? "#445c53" : "#6f8679",
    },
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [lng - width, lat - height],
          [lng + width, lat - height],
          [lng + width, lat + height],
          [lng - width, lat + height],
          [lng - width, lat - height],
        ],
      ],
    },
  };
}

const buildingBlocks: BuildingCollection = {
  type: "FeatureCollection",
  features: [
    rectangle(98.985, 18.789, 0.0036, 0.0024, 96),
    rectangle(98.995, 18.789, 0.003, 0.0028, 130),
    rectangle(99.006, 18.785, 0.0044, 0.0022, 82),
    rectangle(98.977, 18.783, 0.0031, 0.0032, 112),
    rectangle(98.988, 18.778, 0.0035, 0.0022, 74),
    rectangle(99.0, 18.776, 0.0032, 0.0028, 118),
    rectangle(98.971, 18.794, 0.0028, 0.0034, 66),
    rectangle(98.966, 18.786, 0.0038, 0.0021, 78),
    rectangle(99.012, 18.794, 0.0032, 0.003, 104),
    rectangle(98.982, 18.799, 0.0042, 0.002, 88),
    rectangle(99.018, 18.78, 0.0036, 0.0032, 92),
    rectangle(98.973, 18.774, 0.0032, 0.0022, 58),
  ],
};

function setBasemapVisibility(map: maplibregl.Map, basemap: BasemapId) {
  map.setLayoutProperty(
    "basemap-relief",
    "visibility",
    basemap === "relief" ? "visible" : "none",
  );
  map.setLayoutProperty(
    "basemap-streets",
    "visibility",
    basemap === "streets" ? "visible" : "none",
  );
  map.setLayoutProperty(
    "basemap-satellite",
    "visibility",
    basemap === "satellite" ? "visible" : "none",
  );
}

export function MapLibreTerrainView({ dashboard, layers, mapTilerKey }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markerRef = useRef<maplibregl.Marker[]>([]);
  const [basemap, setBasemap] = useState<BasemapId>("relief");
  const [terrainExaggeration, setTerrainExaggeration] = useState(DEFAULT_EXAGGERATION);
  const [showBuildings, setShowBuildings] = useState(true);
  const [inspector, setInspector] = useState<TerrainInspector | null>(null);
  const activeLayers = layers ?? DEFAULT_LAYERS;
  const windDestinationText = dashboard
    ? windDestinationName(dashboard.weather.wind_direction_deg)
    : "";
  const windRotation = dashboard ? dashboard.weather.wind_direction_deg + 180 : 0;
  const terrainSource = useMemo(
    () =>
      mapTilerKey
        ? {
            type: "raster-dem" as const,
            url: `https://api.maptiler.com/tiles/terrain-rgb-v2/tiles.json?key=${mapTilerKey}`,
            tileSize: 256,
          }
        : {
            type: "raster-dem" as const,
            tiles: [
              "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
            ],
            encoding: "terrarium" as const,
            tileSize: 256,
            maxzoom: 15,
            attribution: "Elevation tiles by Mapzen and AWS Open Data",
          },
    [mapTilerKey],
  );

  useEffect(() => {
    if (!ref.current) return undefined;

    const map = new maplibregl.Map({
      container: ref.current,
      style: {
        version: 8,
        sources: {
          opentopo: {
            type: "raster",
            tiles: ["https://tile.opentopomap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "Map data: OpenStreetMap, SRTM | Map style: OpenTopoMap",
          },
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "OpenStreetMap contributors",
          },
          satellite: {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            attribution: "Esri World Imagery",
          },
          "building-blocks": {
            type: "geojson",
            data: buildingBlocks,
          },
          ...(mapTilerKey
            ? {
                "real-buildings": {
                  type: "vector" as const,
                  url: `https://api.maptiler.com/tiles/v4/tiles.json?key=${mapTilerKey}`,
                },
              }
            : {}),
          "pm25-areas": {
            type: "geojson",
            data: emptyCollection() as never,
          },
          "pm25-points": {
            type: "geojson",
            data: emptyCollection() as never,
          },
          "hotspot-points": {
            type: "geojson",
            data: emptyCollection() as never,
          },
          "hotspot-plumes": {
            type: "geojson",
            data: emptyCollection() as never,
          },
          "fire-zones": {
            type: "geojson",
            data: emptyCollection() as never,
          },
          "community-boundaries": {
            type: "geojson",
            data: emptyCollection() as never,
          },
          "community-points": {
            type: "geojson",
            data: emptyCollection() as never,
          },
          "wind-vector": {
            type: "geojson",
            data: emptyCollection() as never,
          },
        },
        layers: [
          {
            id: "basemap-relief",
            type: "raster",
            source: "opentopo",
            layout: { visibility: "visible" },
            paint: {
              "raster-saturation": -0.22,
              "raster-contrast": 0.18,
            },
          },
          {
            id: "basemap-streets",
            type: "raster",
            source: "osm",
            layout: { visibility: "none" },
            paint: { "raster-saturation": -0.12 },
          },
          {
            id: "basemap-satellite",
            type: "raster",
            source: "satellite",
            layout: { visibility: "none" },
            paint: {
              "raster-saturation": -0.08,
              "raster-contrast": 0.08,
            },
          },
          {
            id: "pm25-area-fill",
            type: "fill",
            source: "pm25-areas",
            paint: {
              "fill-color": ["get", "color"],
              "fill-opacity": 0.18,
            },
          },
          {
            id: "pm25-area-line",
            type: "line",
            source: "pm25-areas",
            paint: {
              "line-color": ["get", "color"],
              "line-opacity": 0.52,
              "line-width": 1.5,
            },
          },
          {
            id: "hotspot-plume-fill",
            type: "fill",
            source: "hotspot-plumes",
            paint: {
              "fill-color": "#f97316",
              "fill-opacity": 0.22,
            },
          },
          {
            id: "fire-zone-fill",
            type: "fill",
            source: "fire-zones",
            paint: {
              "fill-color": ["get", "color"],
              "fill-opacity": 0.11,
            },
          },
          {
            id: "fire-zone-line",
            type: "line",
            source: "fire-zones",
            paint: {
              "line-color": ["get", "color"],
              "line-opacity": 0.82,
              "line-width": 2,
              "line-dasharray": [2, 2],
            },
          },
          {
            id: "community-boundary-fill",
            type: "fill",
            source: "community-boundaries",
            paint: {
              "fill-color": ["get", "color"],
              "fill-opacity": 0.13,
            },
          },
          {
            id: "community-boundary-line",
            type: "line",
            source: "community-boundaries",
            paint: {
              "line-color": ["get", "color"],
              "line-opacity": 0.92,
              "line-width": 2,
              "line-dasharray": [1.4, 1.8],
            },
          },
          {
            id: "wind-vector-line",
            type: "line",
            source: "wind-vector",
            paint: {
              "line-color": "#2563eb",
              "line-opacity": 0.88,
              "line-width": 5,
              "line-blur": 0.4,
            },
          },
          {
            id: "pm25-point-circle",
            type: "circle",
            source: "pm25-points",
            paint: {
              "circle-color": ["get", "color"],
              "circle-radius": 7,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
              "circle-opacity": 0.95,
            },
          },
          {
            id: "hotspot-point-circle",
            type: "circle",
            source: "hotspot-points",
            paint: {
              "circle-color": "#dc2626",
              "circle-radius": 7,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
              "circle-opacity": 0.98,
            },
          },
          {
            id: "community-point-circle",
            type: "circle",
            source: "community-points",
            paint: {
              "circle-color": ["get", "color"],
              "circle-radius": 6,
              "circle-stroke-color": "#ffffff",
              "circle-stroke-width": 2,
              "circle-opacity": 0.95,
            },
          },
          {
            id: "building-blocks-fill",
            type: "fill-extrusion",
            source: "building-blocks",
            minzoom: 9,
            layout: { visibility: mapTilerKey ? "none" : "visible" },
            paint: {
              "fill-extrusion-color": ["get", "color"],
              "fill-extrusion-height": ["get", "height"],
              "fill-extrusion-base": 0,
              "fill-extrusion-opacity": 0.9,
            },
          },
          ...(mapTilerKey
            ? [
                {
                  id: "real-buildings-fill",
                  type: "fill-extrusion" as const,
                  source: "real-buildings",
                  "source-layer": "building",
                  minzoom: 13,
                  paint: {
                    "fill-extrusion-color": "#5f756b",
                    "fill-extrusion-height": [
                      "case",
                      ["has", "render_height"],
                      ["to-number", ["get", "render_height"]],
                      ["has", "height"],
                      ["to-number", ["get", "height"]],
                      12,
                    ] as never,
                    "fill-extrusion-base": [
                      "case",
                      ["has", "render_min_height"],
                      ["to-number", ["get", "render_min_height"]],
                      ["has", "min_height"],
                      ["to-number", ["get", "min_height"]],
                      0,
                    ] as never,
                    "fill-extrusion-opacity": 0.82,
                  },
                },
              ]
            : []),
        ],
      },
      center: CAMERA_CENTER,
      zoom: CAMERA_ZOOM,
      pitch: CAMERA_PITCH,
      bearing: CAMERA_BEARING,
      maxPitch: 85,
      attributionControl: { compact: true },
    });

    mapRef.current = map;
    requestAnimationFrame(() => map.resize());
    map.addControl(
      new maplibregl.NavigationControl({ visualizePitch: true }),
      "top-right",
    );

    map.on("load", () => {
      map.addSource("terrain", terrainSource);
      map.addSource("terrain-hillshade-dem", terrainSource);
      map.addLayer(
        {
          id: "terrain-hillshade",
          type: "hillshade",
          source: "terrain-hillshade-dem",
          paint: {
            "hillshade-accent-color": "#567268",
            "hillshade-exaggeration": 0.86,
            "hillshade-highlight-color": "#f8fbf9",
            "hillshade-shadow-color": "#344c43",
          },
        },
        "pm25-area-fill",
      );
      map.setTerrain({ source: "terrain", exaggeration: DEFAULT_EXAGGERATION });
      updateTerrainSources(map, dashboard, activeLayers);
      map.easeTo({
        center: CAMERA_CENTER,
        zoom: CAMERA_ZOOM,
        pitch: CAMERA_PITCH,
        bearing: CAMERA_BEARING,
        duration: 900,
      });
    });

    return () => {
      mapRef.current = null;
      map.remove();
    };
  }, [terrainSource]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) return;
    setBasemapVisibility(map, basemap);
  }, [basemap]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getSource("terrain")) return;
    map.setTerrain({ source: "terrain", exaggeration: terrainExaggeration });
  }, [terrainExaggeration]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.getLayer("building-blocks-fill")) return;
    map.setLayoutProperty(
      "building-blocks-fill",
      "visibility",
      showBuildings && !mapTilerKey ? "visible" : "none",
    );
    if (map.getLayer("real-buildings-fill")) {
      map.setLayoutProperty(
        "real-buildings-fill",
        "visibility",
        showBuildings ? "visible" : "none",
      );
    }
  }, [showBuildings]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!map.isStyleLoaded()) {
      map.once("idle", () => updateTerrainSources(map, dashboard, activeLayers));
      return;
    }
    updateTerrainSources(map, dashboard, activeLayers);
  }, [dashboard, activeLayers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return undefined;

    const updateMarkers = () => {
      markerRef.current.forEach((marker) => marker.remove());
      markerRef.current = [];

      if (dashboard && activeLayers.pm25) {
        dashboard.pm25.stations.forEach((station) => {
          markerRef.current.push(
            createTerrainMarker(
              map,
              station.longitude,
              station.latitude,
              "terrain-map-marker--pm",
              `PM2.5 ${station.pm25} at ${station.name || station.id}`,
              () =>
                setInspector(
                  pointInspector(
                    "PM2.5 station",
                    station.name || station.id,
                    `PM2.5 station at ${station.latitude.toFixed(5)}, ${station.longitude.toFixed(5)}`,
                    station.longitude,
                    station.latitude,
                    [
                      { label: "PM2.5", value: `${station.pm25} µg/m³` },
                      { label: "Trend", value: station.trend },
                    ],
                  ),
                ),
            ),
          );
        });
      }

      if (dashboard && activeLayers.hotspots) {
        dashboard.hotspots.items.forEach((hotspot) => {
          markerRef.current.push(
            createTerrainMarker(
              map,
              hotspot.longitude,
              hotspot.latitude,
              "terrain-map-marker--hot",
              `Hotspot ${hotspot.id}`,
              () =>
                setInspector(
                  pointInspector(
                    "Hotspot",
                    hotspot.landuse_name || hotspot.district || hotspot.id,
                    `Hotspot at ${hotspot.latitude.toFixed(5)}, ${hotspot.longitude.toFixed(5)}`,
                    hotspot.longitude,
                    hotspot.latitude,
                    [
                      { label: "Confidence", value: `${hotspot.confidence}%` },
                      { label: "Source", value: hotspot.source },
                    ],
                  ),
                ),
            ),
          );
        });
      }

      if (activeLayers.communityForests) {
        COMMUNITY_FORESTS.forEach((forest) => {
          markerRef.current.push(
            createTerrainMarker(
              map,
              forest.lng,
              forest.lat,
              "terrain-map-marker--forest",
              forest.name,
              () =>
                setInspector(
                  pointInspector(
                    "Community forest",
                    forest.name,
                    `Community forest point at ${forest.lat.toFixed(5)}, ${forest.lng.toFixed(5)}`,
                    forest.lng,
                    forest.lat,
                    [
                      { label: "District", value: forest.amphoe },
                      {
                        label: "Boundary",
                        value: "Estimated prototype radius",
                      },
                    ],
                  ),
                ),
            ),
          );
        });
      }

      if (activeLayers.fireZones) {
        FIRE_MANAGEMENT_ZONES.forEach((zone) => {
          const center = geometryCenter(zone.geometry);
          if (!center) return;
          markerRef.current.push(
            createTerrainMarker(
              map,
              center[0],
              center[1],
              "terrain-map-marker--fire-zone",
              zone.name,
              () =>
                setInspector(
                  pointInspector(
                    "Fire zone",
                    zone.name,
                    `Fire zone marker at ${center[1].toFixed(5)}, ${center[0].toFixed(5)}`,
                    center[0],
                    center[1],
                    [{ label: "Zone health", value: zone.health }],
                  ),
                ),
            ),
          );
        });
      }
    };

    if (map.isStyleLoaded()) {
      updateMarkers();
    } else {
      map.once("idle", updateMarkers);
    }

    return () => {
      markerRef.current.forEach((marker) => marker.remove());
      markerRef.current = [];
    };
  }, [dashboard, activeLayers]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return undefined;

    const disposers: Array<() => void> = [];

    const installHandlers = () => {
      INSPECTABLE_LAYER_IDS.forEach((layerId) => {
        if (!map.getLayer(layerId)) return;

        const handleClick = (event: maplibregl.MapLayerMouseEvent) => {
          const feature = event.features?.[0];
          if (!feature) return;
          setInspector(buildInspector(feature, event.lngLat));
        };
        const handleEnter = () => {
          map.getCanvas().style.cursor = "pointer";
        };
        const handleLeave = () => {
          map.getCanvas().style.cursor = "";
        };

        map.on("click", layerId, handleClick);
        map.on("mouseenter", layerId, handleEnter);
        map.on("mouseleave", layerId, handleLeave);

        disposers.push(() => {
          map.off("click", layerId, handleClick);
          map.off("mouseenter", layerId, handleEnter);
          map.off("mouseleave", layerId, handleLeave);
        });
      });
    };

    if (map.isStyleLoaded()) {
      installHandlers();
    } else {
      map.once("idle", installHandlers);
    }

    return () => {
      disposers.forEach((dispose) => dispose());
    };
  }, []);

  return (
    <div className="maplibre-terrain-shell">
      <div ref={ref} className="maplibre-terrain-view" aria-label="3D terrain map" />
      <div className="terrain-control-panel" aria-label="3D map controls">
        <div className="terrain-control-panel__group">
          <span>Base map</span>
          <div className="terrain-segmented">
            {BASEMAPS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={basemap === item.id ? "active" : ""}
                onClick={() => setBasemap(item.id)}
                aria-pressed={basemap === item.id}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="terrain-control-panel__group">
          <span>Terrain height</span>
          <div className="terrain-segmented">
            {EXAGGERATION_LEVELS.map((level) => (
              <button
                key={level}
                type="button"
                className={terrainExaggeration === level ? "active" : ""}
                onClick={() => setTerrainExaggeration(level)}
                aria-pressed={terrainExaggeration === level}
              >
                {level}x
              </button>
            ))}
          </div>
        </div>

        <button
          type="button"
          className={`terrain-building-toggle${showBuildings ? " active" : ""}`}
          onClick={() => setShowBuildings((value) => !value)}
          aria-pressed={showBuildings}
        >
          {mapTilerKey ? "Real buildings" : "Prototype buildings"}
        </button>
      </div>
      <div className="terrain-context-chip">
        <strong>DEM terrain</strong>
        <span>
          Hillshade + {terrainExaggeration}x height, {mapTilerKey ? "MapTiler buildings" : "prototype buildings"}
        </span>
      </div>
      {dashboard && activeLayers.wind && (
        <div className="terrain-wind-compass" aria-label={`Wind toward ${windDestinationText}`}>
          <span
            className="terrain-wind-compass__dial"
            style={{ transform: `rotate(${windRotation}deg)` }}
          >
            ↑
          </span>
          <span>
            <b>ลมไป{windDestinationText}</b>
            <small>{dashboard.weather.wind_speed_kmh} km/h</small>
          </span>
        </div>
      )}
      <div className="terrain-data-legend" aria-label="3D map data overlays">
        <span><i className="terrain-data-legend__dot terrain-data-legend__dot--pm" />PM2.5 area</span>
        <span><i className="terrain-data-legend__dot terrain-data-legend__dot--hot" />Hotspot</span>
        <span><i className="terrain-data-legend__dot terrain-data-legend__dot--forest" />ป่าชุมชน</span>
        <span><i className="terrain-data-legend__line" />เขตไฟ/ลม</span>
      </div>
      {inspector && (
        <section className="terrain-inspector" aria-label="3D selected map data">
          <div className="terrain-inspector__head">
            <span>{inspector.eyebrow}</span>
            <button
              type="button"
              onClick={() => setInspector(null)}
              aria-label="Close 3D map inspector"
            >
              ×
            </button>
          </div>
          <strong>{inspector.title}</strong>
          <p>{inspector.detail}</p>
          <div className="terrain-inspector__stats">
            {inspector.stats.map((item) => (
              <span key={`${item.label}-${item.value}`}>
                <b>{item.label}</b>
                {item.value}
              </span>
            ))}
          </div>
          <a
            href={`https://www.google.com/maps?q=${inspector.lat},${inspector.lng}`}
            target="_blank"
            rel="noreferrer"
          >
            Open coordinates
          </a>
        </section>
      )}
    </div>
  );
}
