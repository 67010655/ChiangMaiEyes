import { useEffect, useRef, useState } from "react";
import L from "leaflet";

import type { Hotspot } from "../../lib/types";
import { getAgeColor } from "../../lib/hotspotAge";

export type Basemap = "light" | "satellite" | "terrain";

const BASEMAPS: Record<Basemap, { label: string; url: string; attribution: string; maxZoom: number }> = {
  light: {
    label: "สว่าง",
    url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    attribution: "&copy; OpenStreetMap &copy; CARTO",
    maxZoom: 20,
  },
  satellite: {
    label: "ดาวเทียม",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "&copy; Esri, Maxar, Earthstar Geographics",
    maxZoom: 19,
  },
  terrain: {
    label: "ภูมิประเทศ",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution: "&copy; OpenStreetMap &copy; OpenTopoMap",
    maxZoom: 17,
  },
};

type MapViewProps = {
  hotspots: Hotspot[];
  /** [lat, lng] — defaults to Chiang Mai but is fully overridable */
  center?: [number, number];
  zoom?: number;
  basemap?: Basemap;
};

// Clean Leaflet base map. No business logic baked in — just a configurable map
// with a hotspot layer. Centre/zoom/basemap are props, not hardcoded.
export function MapView({
  hotspots,
  center = [18.79, 98.98],
  zoom = 9,
  basemap: initialBasemap = "satellite",
}: MapViewProps) {
  const elRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const tileRef = useRef<L.TileLayer | null>(null);
  const markersRef = useRef<L.LayerGroup | null>(null);
  const [basemap, setBasemap] = useState<Basemap>(initialBasemap);

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

  // basemap tile layer
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (tileRef.current) tileRef.current.remove();
    const cfg = BASEMAPS[basemap];
    tileRef.current = L.tileLayer(cfg.url, { attribution: cfg.attribution, maxZoom: cfg.maxZoom }).addTo(map);
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
          `<b>จุดความร้อน</b><br/>อ.${h.district || "ไม่ระบุ"}<br/>${
            h.landuse_name || h.landuse_type || ""
          }<br/>แหล่ง: ${h.source}`,
        )
        .addTo(group);
    }
  }, [hotspots]);

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
      </div>
    </div>
  );
}
