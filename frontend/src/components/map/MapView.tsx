import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet-velocity";

import type { Hotspot, WeatherResponse } from "../../lib/types";
import { getAgeColor } from "../../lib/hotspotAge";
import {
  buildWindFieldFromStation,
  fetchWindGrid,
} from "../../lib/windGrid";

export type Basemap = "light" | "satellite" | "terrain";

const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY as string | undefined;

function mtUrl(style: string, ext: "jpg" | "png") {
  return `https://api.maptiler.com/maps/${style}/{z}/{x}/{y}.${ext}?key=${MAPTILER_KEY}`;
}

const MAPTILER_ATTR = '&copy; <a href="https://www.maptiler.com/copyright/" target="_blank" rel="noopener">MapTiler</a> &copy; OpenStreetMap';

type BasemapCfg = { label: string; url: string; attribution: string; maxZoom: number; labelUrl?: string };

const BASEMAPS: Record<Basemap, BasemapCfg> = {
  light: {
    label: "สว่าง",
    url: MAPTILER_KEY
      ? mtUrl("dataviz", "png")
      : "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    attribution: MAPTILER_KEY ? MAPTILER_ATTR : "Tiles &copy; Esri",
    maxZoom: MAPTILER_KEY ? 20 : 16,
  },
  satellite: {
    label: "ดาวเทียม",
    // MapTiler hybrid = imagery + labels in one tile; Esri imagery needs a separate label layer
    url: MAPTILER_KEY
      ? mtUrl("hybrid", "jpg")
      : "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: MAPTILER_KEY ? MAPTILER_ATTR : "&copy; Esri, Maxar, Earthstar Geographics",
    maxZoom: MAPTILER_KEY ? 20 : 19,
    labelUrl: MAPTILER_KEY
      ? undefined
      : "https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}",
  },
  terrain: {
    label: "ภูมิประเทศ",
    url: MAPTILER_KEY
      ? mtUrl("outdoor-v2", "png")
      : "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: MAPTILER_KEY ? MAPTILER_ATTR : "&copy; OpenStreetMap &copy; OpenTopoMap",
    maxZoom: MAPTILER_KEY ? 20 : 17,
  },
};

type MapViewProps = {
  hotspots: Hotspot[];
  weather?: WeatherResponse | null;
  /** [lat, lng] — defaults to Chiang Mai but is fully overridable */
  center?: [number, number];
  zoom?: number;
  basemap?: Basemap;
};

export function MapView({
  hotspots,
  weather,
  center = [18.79, 98.98],
  zoom = 9,
  basemap: initialBasemap = "satellite",
}: MapViewProps) {
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const tileRef = useRef<L.TileLayer | null>(null);
  const labelRef = useRef<L.TileLayer | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);
  const velRef = useRef<any>(null);
  const [basemap, setBasemap] = useState<Basemap>(initialBasemap);
  const [showWind, setShowWind] = useState(true);

  // init map once
  useEffect(() => {
    if (!elRef.current || mapRef.current) return;
    const map = L.map(elRef.current, { center, zoom, zoomControl: true, attributionControl: true });
    mapRef.current = map;
    markersRef.current = L.layerGroup().addTo(map);
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // basemap tile layer + optional hybrid label overlay
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (tileRef.current) tileRef.current.remove();
    if (labelRef.current) { labelRef.current.remove(); labelRef.current = null; }
    const cfg = BASEMAPS[basemap];
    tileRef.current = L.tileLayer(cfg.url, { attribution: cfg.attribution, maxZoom: cfg.maxZoom }).addTo(map);
    if (cfg.labelUrl) {
      labelRef.current = L.tileLayer(cfg.labelUrl, { maxZoom: cfg.maxZoom, opacity: 1 }).addTo(map);
    }
  }, [basemap]);

  // hotspot markers, coloured by age
  useEffect(() => {
    const group = markersRef.current;
    if (!group) return;
    group.clearLayers();
    for (const h of hotspots) {
      const color = getAgeColor(h.detected_at);
      L.circleMarker([h.latitude, h.longitude], {
        radius: 6,
        color: "#ffffff",
        weight: 1.5,
        fillColor: color,
        fillOpacity: 0.9,
      })
        .bindPopup(
          `<b>จุดความร้อน</b><br/>อ.${h.district || "ไม่ระบุ"}<br/>` +
          `${h.landuse_name || h.landuse_type || ""}<br/>` +
          (h.frp != null ? `FRP: ${h.frp.toFixed(1)} MW<br/>` : "") +
          `แหล่ง: ${h.source}`,
        )
        .addTo(group);
    }
  }, [hotspots]);

  // wind velocity layer — try real spatial grid first, fall back to station uniform field
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (velRef.current) {
      velRef.current.remove();
      velRef.current = null;
    }
    if (!showWind) return;

    const addVelocityLayer = (field: ReturnType<typeof buildWindFieldFromStation>) => {
      if (!mapRef.current) return;
      velRef.current = (L as any).velocityLayer({
        displayValues: true,
        displayOptions: {
          velocityType: "Wind",
          position: "bottomleft",
          emptyString: "ไม่มีข้อมูลลม",
          angleConvention: "bearingCW",
          speedUnit: "m/s",
        },
        data: field,
        maxVelocity: 20,
        colorScale: ["#93c5fd", "#60a5fa", "#3b82f6", "#1d4ed8", "#1e3a8a"],
        velocityScale: 0.006,
        opacity: 0.85,
        particleAge: 64,
        lineWidth: 1.5,
      }).addTo(mapRef.current);
    };

    // Try Open-Meteo spatial grid; fall back to station uniform field
    fetchWindGrid()
      .then(addVelocityLayer)
      .catch(() => {
        if (weather) {
          addVelocityLayer(
            buildWindFieldFromStation(
              weather.wind_speed_kmh,
              weather.wind_direction_deg,
              weather.latest_update,
            ),
          );
        }
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showWind, weather?.wind_direction_deg, weather?.wind_speed_kmh]);

  return (
    <div className="mapview">
      <div ref={elRef} className="mapview__canvas" />

      <div className="mapview__basemaps" role="group" aria-label="เลือกแผนที่ฐาน">
        {(Object.keys(BASEMAPS) as Basemap[]).map((key) => (
          <button
            key={key}
            type="button"
            className={`mapview__basemap-btn${basemap === key ? " is-active" : ""}`}
            onClick={() => setBasemap(key)}
          >
            {BASEMAPS[key].label}
          </button>
        ))}
        <button
          type="button"
          className={`mapview__basemap-btn${showWind ? " is-active" : ""}`}
          onClick={() => setShowWind((v) => !v)}
          title="แสดง/ซ่อน Animation ทิศทางลม"
        >
          {showWind ? "ลม ✓" : "ลม"}
        </button>
      </div>
    </div>
  );
}
