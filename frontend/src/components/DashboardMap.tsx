import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import L from 'leaflet';
import 'leaflet-velocity';
import { Crosshair, Minus, Plus, Wind } from 'lucide-react';
import type { DashboardResponse, Hotspot, Pm25Station } from '../lib/types';
import provinceGeoData from '../data/chiangmai-province.json';
import districtsGeoData from '../data/chiangmai-districts.json';
import { windDestinationName } from '../lib/wind';
import { fetchWindField } from '../lib/windGrid';

// ─────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────

type Props = {
  dashboard: DashboardResponse;
  layers: {
    hotspots: boolean;
    pm25: boolean;
    wind: boolean;
  };
  selection: MapSelection;
  onSelectionChange: (sel: MapSelection) => void;
};

export type MapSelection = {
  eyebrow: string;
  title: string;
  detail: string;
  imageKey?: string;
  imageLabel?: string;
  stats?: { label: string; value: string; tone?: 'good' | 'watch' | 'risk' }[];
};

// ─────────────────────────────────────────────
// GeoJSON preparation (module-level, computed once)
// ─────────────────────────────────────────────

// Province boundary: raw Polygon geometry { type, coordinates }
const provinceCoordsRaw = (provinceGeoData as { type: string; coordinates: number[][][] }).coordinates[0];

// World-minus-CM mask — dims everything outside the province
const maskFeature = {
  type: 'Feature',
  geometry: {
    type: 'Polygon',
    coordinates: [
      // outer ring: whole visible world in Web Mercator
      [[-180, -85.05], [180, -85.05], [180, 85.05], [-180, 85.05], [-180, -85.05]],
      // inner ring: CM province → creates the transparent "window"
      provinceCoordsRaw,
    ],
  },
  properties: {},
};

// Province fill + border
const provinceFeature = {
  type: 'Feature',
  geometry: provinceGeoData,
  properties: {},
};

// ─────────────────────────────────────────────
// Wind overlay streamlines (normalised -1…+1 space)
// The SVG has viewBox="-1.5 -1.5 3 3" with preserveAspectRatio="xMidYMid slice",
// so the group rotated by windRotation degrees makes the lines flow the right direction.
// ─────────────────────────────────────────────

// 6 streamlines with organic (non-uniform) x-positions and a full double-S curve.
// Paths span ±2 units so rotation up to ±45° still fills every viewport corner.
// Amplitude alternates sign so adjacent lines wave in opposite phase.
const WIND_OV_LINES = (
  [-1.15, -0.65, -0.15, 0.28, 0.72, 1.18] as const
).map((lx, i) => {
  const amp = 0.24 * (i % 2 === 0 ? 1 : -1);
  const d =
    `M ${lx} 2 ` +
    `C ${lx + amp} 1.25 ${lx - amp} 0.55 ${lx} 0 ` +
    `C ${lx + amp} -0.55 ${lx - amp} -1.25 ${lx} -2`;
  return { id: `wo-${i}`, d, delay: i * 0.45 };
});

// ─────────────────────────────────────────────
// Helper functions
// ─────────────────────────────────────────────

function clamp(v: number, mn: number, mx: number) {
  return Math.min(mx, Math.max(mn, v));
}

function formatPm25(v: number) {
  return `${v.toFixed(v % 1 ? 1 : 0)} µg/m³`;
}

function pm25ValueLabel(v: number) {
  return v.toFixed(v % 1 ? 1 : 0);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { timeStyle: 'short' }).format(new Date(value));
}

function pm25Color(pm25: number): string {
  if (pm25 <= 25) return '#16a34a';
  if (pm25 <= 37) return '#eab308';
  if (pm25 <= 50) return '#f97316';
  if (pm25 <= 90) return '#dc2626';
  return '#7c3aed';
}

function pm25Tone(pm25: number): 'good' | 'watch' | 'risk' {
  if (pm25 <= 25) return 'good';
  if (pm25 <= 50) return 'watch';
  return 'risk';
}

// Geographic plume radius in metres (scales naturally with Leaflet zoom)
function plumeRadiusMeters(pm25: number): number {
  return 4000 + (Math.min(pm25, 120) / 120) * 13000;
}

function stationImageKey(s: Pm25Station) {
  if (s.id === 'CM-O23') return 'bhubing';
  if (s.id === 'CM-O70') return 'chiangdao';
  if (s.id === 'CM-O71') return 'maechaem';
  if (s.id === 'CM-O69') return 'hot';
  if (s.id === 'CM-36T') return 'school';
  return 'city';
}

function hotspotImageKey(h: Hotspot) {
  return h.landuse_type && h.landuse_type !== 'OTHER' ? 'forest' : 'hotspot';
}

function hotspotPlaceTitle(h: Hotspot) {
  return h.landuse_name || h.district || h.id;
}

function hotspotLocation(h: Hotspot) {
  return [
    h.subdistrict ? `ต.${h.subdistrict}` : '',
    h.district ? `อ.${h.district}` : '',
  ]
    .filter(Boolean)
    .join(' ');
}

function hotspotStats(h: Hotspot): MapSelection['stats'] {
  return [
    { label: 'Confidence', value: `${h.confidence}%`, tone: h.confidence >= 80 ? 'risk' : 'watch' },
    { label: 'ประเภทพื้นที่', value: h.landuse_name || h.landuse_type || 'ไม่ระบุ' },
    { label: 'ดาวเทียม', value: h.satellite || 'VIIRS' },
    { label: 'เวลา', value: formatTime(h.detected_at) },
  ];
}

// ─────────────────────────────────────────────
// Initial / default selection
// ─────────────────────────────────────────────

export const initialSelection: MapSelection = {
  eyebrow: 'ขอบเขตจังหวัด',
  title: 'เชียงใหม่',
  detail:
    'จังหวัดขนาดใหญ่ทางภาคเหนือ พื้นที่ประมาณ 20,107 ตร.กม. ใช้ดู PM2.5 จุดความร้อน และทิศทางลมแบบโฟกัสเฉพาะเชียงใหม่',
  imageKey: 'province',
  imageLabel: 'Chiang Mai province',
  stats: [
    { label: 'พื้นที่', value: '20,107 ตร.กม.' },
    { label: 'อำเภอ', value: '24 อำเภอ' },
  ],
};

// ─────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────

export function DashboardMap({ dashboard, layers, selection: _selection, onSelectionChange }: Props) {
  const mapDivRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const hotspotsLayerRef = useRef<L.LayerGroup | null>(null);
  const pm25LayerRef = useRef<L.LayerGroup | null>(null);
  const velocityLayerRef = useRef<L.Layer | null>(null);

  // True once the Windy-style particle layer is live, so we can hide the
  // lightweight SVG streamline fallback.
  const [windParticlesOn, setWindParticlesOn] = useState(false);

  // Callback ref — avoids stale closures inside Leaflet event handlers
  const onSelChangeRef = useRef(onSelectionChange);
  useEffect(() => {
    onSelChangeRef.current = onSelectionChange;
  });

  // Zoom level as React state — triggers marker rebuild only on tier boundary crossings
  const [zoom, setZoom] = useState(9);

  // ── Initialise Leaflet map (once) ──────────────────────────────────────────
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return;

    const map = L.map(mapDivRef.current, {
      center: [18.78, 98.98],
      zoom: 9,
      minZoom: 7,
      maxZoom: 14,
      // Pan limit: CM + surrounding provinces (Mae Hong Son, Chiang Rai, Phayao, Lampang, Lamphun, Tak)
      maxBounds: L.latLngBounds([[16.8, 96.6], [21.2, 101.4]]),
      maxBoundsViscosity: 0.85,
      zoomControl: false, // we render our own buttons
      touchZoom: true,
      // tap: false handled below via CSS touch-action
      doubleClickZoom: true,
      scrollWheelZoom: true,
    });

    // OSM tiles
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
    }).addTo(map);

    // Leaflet built-in scale bar (replaces our static "20 km")
    L.control.scale({ imperial: false, position: 'bottomleft' }).addTo(map);

    // ── Static layers ─────────────────────────────────────────────────────────

    // 1. World-minus-CM mask (dim surrounding area)
    L.geoJSON(maskFeature as any, {
      style: {
        color: 'transparent',
        weight: 0,
        fillColor: '#0d1a15',
        fillOpacity: 0.24,
      },
      interactive: false,
    }).addTo(map);

    // 2. CM province fill (subtle green tint) + strong border
    L.geoJSON(provinceFeature as any, {
      style: {
        color: '#0f6b54',
        weight: 2.5,
        opacity: 0.9,
        fillColor: '#22c55e',
        fillOpacity: 0.05,
        lineJoin: 'round',
      },
      interactive: false,
    }).addTo(map);

    // 3. District boundaries (thin, hover highlight, clickable)
    L.geoJSON(districtsGeoData as any, {
      style: {
        color: '#6aab7a',
        weight: 0.8,
        opacity: 0.45,
        fillColor: 'transparent',
        fillOpacity: 0,
      },
      onEachFeature: (feature, layer) => {
        const nameTh: string = feature.properties?.nameTh || feature.properties?.name || '';
        layer.on({
          click: (e: L.LeafletMouseEvent) => {
            L.DomEvent.stopPropagation(e);
            onSelChangeRef.current({
              eyebrow: 'อำเภอ',
              title: nameTh,
              detail: 'คลิกจุดข้อมูลเพื่อดูสถานะ PM2.5 หรือจุดความร้อน',
              imageKey: 'district',
              imageLabel: nameTh,
              stats: [
                { label: 'จังหวัด', value: 'เชียงใหม่' },
                { label: 'ชั้นข้อมูล', value: 'ขอบเขตอำเภอ' },
              ],
            });
          },
          mouseover: () => (layer as L.Path).setStyle({ fillOpacity: 0.08, opacity: 0.8 }),
          mouseout: () => (layer as L.Path).setStyle({ fillOpacity: 0, opacity: 0.45 }),
        });
      },
    }).addTo(map);

    // 4. Province title label (DivIcon — fixed pixel size, doesn't scale)
    L.marker([18.6, 98.6], {
      icon: L.divIcon({
        html: '<span class="province-title-label">เชียงใหม่</span>',
        className: '',
        iconSize: [160, 40],
        iconAnchor: [80, 20],
      }),
      interactive: false,
    }).addTo(map);

    // ── Dynamic layer groups ───────────────────────────────────────────────────
    hotspotsLayerRef.current = L.layerGroup().addTo(map);
    pm25LayerRef.current = L.layerGroup().addTo(map);

    // Click on blank map → reset selection
    map.on('click', () => onSelChangeRef.current(initialSelection));

    // Track zoom for React re-renders (controls zoom readout + marker tier)
    map.on('zoomend', () => setZoom(map.getZoom()));

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Hotspot markers (rebuild on data/toggle/zoom) ──────────────────────────
  useEffect(() => {
    const group = hotspotsLayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!layers.hotspots) return;

    // Zoom tiers (matches Leaflet tile-zoom levels):
    //   sm  ≤ 9  → icon only, no label
    //   md 10–11 → icon + abbreviated district name
    //   lg ≥ 12  → icon + full district·subdistrict
    const tier = zoom <= 9 ? 'sm' : zoom <= 11 ? 'md' : 'lg';
    const size = tier === 'sm' ? 20 : tier === 'md' ? 26 : 34;

    dashboard.hotspots.items.forEach((h) => {
      const isForest = h.landuse_type && h.landuse_type !== 'OTHER';
      const labelHtml =
        tier !== 'sm' && h.district
          ? `<span class="lf-hotspot__label">${
              tier === 'lg' && h.subdistrict
                ? `อ.${h.district} · ต.${h.subdistrict}`
                : `อ.${h.district}`
            }</span>`
          : '';

      const icon = L.divIcon({
        html: `<div class="lf-hotspot${isForest ? ' lf-hotspot--forest' : ''}" style="width:${size}px;height:${size}px">
          <div class="lf-hotspot__halo"></div>
          <span class="lf-hotspot__fire" style="font-size:${Math.round(size * 0.72)}px">🔥</span>
          ${labelHtml}
        </div>`,
        className: 'lf-marker-wrap',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });

      L.marker([h.latitude, h.longitude], { icon, zIndexOffset: 100 })
        .on('click', (e: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(e);
          const loc = hotspotLocation(h);
          onSelChangeRef.current({
            eyebrow: 'จุดความร้อน',
            title: hotspotPlaceTitle(h),
            detail: `${loc ? `${loc} · ` : ''}ตรวจพบ ${formatTime(h.detected_at)} · ${h.source}`,
            imageKey: hotspotImageKey(h),
            imageLabel: hotspotPlaceTitle(h),
            stats: hotspotStats(h),
          });
        })
        .on('mouseover', () => {
          const loc = hotspotLocation(h);
          onSelChangeRef.current({
            eyebrow: 'จุดความร้อน',
            title: hotspotPlaceTitle(h),
            detail: `${loc ? `${loc} · ` : ''}ตรวจพบ ${formatTime(h.detected_at)} · ${h.source}`,
            imageKey: hotspotImageKey(h),
            imageLabel: hotspotPlaceTitle(h),
            stats: hotspotStats(h),
          });
        })
        .addTo(group);
    });
  }, [dashboard.hotspots.items, layers.hotspots, zoom]);

  // ── PM2.5 markers (rebuild on data/toggle/zoom) ────────────────────────────
  useEffect(() => {
    const group = pm25LayerRef.current;
    if (!group) return;
    group.clearLayers();
    if (!layers.pm25) return;

    const tier = zoom <= 9 ? 'sm' : zoom <= 11 ? 'md' : 'lg';
    const size = tier === 'sm' ? 28 : tier === 'md' ? 36 : 44;
    const currentPm25 = dashboard.pm25.current_pm25;

    // Plume circles use L.circle (radius in metres) → scale naturally with zoom
    L.circle([18.78, 98.6], {
      radius: plumeRadiusMeters(currentPm25) * 1.35,
      className: `lf-pm-plume lf-pm-plume--${pm25Tone(currentPm25)}`,
      interactive: false,
    }).addTo(group);

    dashboard.pm25.stations.forEach((s) => {
      L.circle([s.latitude, s.longitude], {
        radius: plumeRadiusMeters(s.pm25),
        className: `lf-pm-plume lf-pm-plume--${pm25Tone(s.pm25)}`,
        interactive: false,
      }).addTo(group);
    });

    // Province aggregate station (slightly larger marker)
    const aggSize = Math.round(size * 1.35);
    const aggLabelHtml =
      tier !== 'sm' ? `<span class="lf-station__label">เฉลี่ยจังหวัด</span>` : '';
    const aggSel: MapSelection = {
      eyebrow: 'ค่าเฉลี่ยจังหวัด',
      title: 'PM2.5 เชียงใหม่',
      detail: `${formatPm25(currentPm25)} · ${dashboard.pm25.category} · อัปเดต ${formatTime(dashboard.pm25.latest_update)}`,
      imageKey: 'province',
      imageLabel: 'Chiang Mai province',
      stats: [
        { label: 'PM2.5 เฉลี่ย', value: formatPm25(currentPm25), tone: pm25Tone(currentPm25) },
        { label: 'สถานี', value: `${dashboard.pm25.stations.length} จุด` },
      ],
    };

    const aggIcon = L.divIcon({
      html: `<div class="lf-station lf-station--agg" style="background:${pm25Color(currentPm25)};width:${aggSize}px;height:${aggSize}px">
        <span class="lf-station__value">${pm25ValueLabel(currentPm25)}</span>
        ${aggLabelHtml}
      </div>`,
      className: 'lf-marker-wrap',
      iconSize: [aggSize, aggSize],
      iconAnchor: [aggSize / 2, aggSize / 2],
    });
    L.marker([18.78, 98.6], { icon: aggIcon, zIndexOffset: 200 })
      .on('click', (e: L.LeafletMouseEvent) => {
        L.DomEvent.stopPropagation(e);
        onSelChangeRef.current(aggSel);
      })
      .on('mouseover', () => onSelChangeRef.current(aggSel))
      .addTo(group);

    // Individual station markers
    dashboard.pm25.stations.forEach((s) => {
      const stName =
        tier === 'lg' ? (s.name.trim() || s.id) : s.district || '';
      const stLabelHtml =
        tier !== 'sm' && stName
          ? `<span class="lf-station__label">${stName}</span>`
          : '';
      const next: MapSelection = {
        eyebrow: 'สถานีวัด PM2.5',
        title: s.name.trim() || s.id,
        detail: `${formatPm25(s.pm25)} · อัปเดต ${formatTime(s.updated_at)} · ${s.district}`,
        imageKey: stationImageKey(s),
        imageLabel: s.name.trim() || s.id,
        stats: [
          { label: 'PM2.5', value: formatPm25(s.pm25), tone: pm25Tone(s.pm25) },
          { label: 'อัปเดต', value: formatTime(s.updated_at) },
        ],
      };

      const stIcon = L.divIcon({
        html: `<div class="lf-station" style="background:${pm25Color(s.pm25)};width:${size}px;height:${size}px">
          <span class="lf-station__value">${pm25ValueLabel(s.pm25)}</span>
          ${stLabelHtml}
        </div>`,
        className: 'lf-marker-wrap',
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2],
      });
      L.marker([s.latitude, s.longitude], { icon: stIcon, zIndexOffset: 150 })
        .on('click', (e: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(e);
          onSelChangeRef.current(next);
        })
        .on('mouseover', () => onSelChangeRef.current(next))
        .addTo(group);
    });
  }, [dashboard.pm25, layers.pm25, zoom]);

  // ── Windy-style wind particles (leaflet-velocity + Open-Meteo grid) ────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    // Tear down when the layer is toggled off.
    if (!layers.wind) {
      if (velocityLayerRef.current) {
        map.removeLayer(velocityLayerRef.current);
        velocityLayerRef.current = null;
      }
      setWindParticlesOn(false);
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    fetchWindField(controller.signal)
      .then((data) => {
        if (cancelled || !mapRef.current) return;
        if (velocityLayerRef.current) {
          mapRef.current.removeLayer(velocityLayerRef.current);
          velocityLayerRef.current = null;
        }
        const layer = (L as any).velocityLayer({
          displayValues: false,
          data,
          minVelocity: 0,
          maxVelocity: 10,
          velocityScale: 0.014,
          particleAge: 80,
          particleMultiplier: 1 / 190,
          lineWidth: 1.6,
          frameRate: 20,
          opacity: 0.97,
          // Blue gradient (slow → fast) — high contrast over the light/green map.
          colorScale: ['#1e4fa3', '#2f7ad1', '#3aa0e6', '#57c4f0', '#8fe0ff'],
        });
        layer.addTo(mapRef.current);
        velocityLayerRef.current = layer;
        setWindParticlesOn(true);
      })
      .catch(() => {
        // Network/shape failure → keep the SVG streamline fallback visible.
        if (!cancelled) setWindParticlesOn(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [layers.wind]);

  // ── Zoom controls ─────────────────────────────────────────────────────────
  const handleZoomIn = useCallback(() => mapRef.current?.zoomIn(), []);
  const handleZoomOut = useCallback(() => mapRef.current?.zoomOut(), []);
  const handleReset = useCallback(() => {
    mapRef.current?.setView([18.78, 98.98], 9, { animate: true });
    onSelectionChange(initialSelection);
  }, [onSelectionChange]);

  // ── Wind ──────────────────────────────────────────────────────────────────
  const windRotation = dashboard.weather.wind_direction_deg + 180;
  const windSpeed = dashboard.weather.wind_speed_kmh;
  const windSourceText = dashboard.weather.wind_direction_text;
  const windDestinationText = windDestinationName(dashboard.weather.wind_direction_deg);
  const windDur = clamp(36 / (windSpeed + 5), 1.4, 6);

  const windSelection: MapSelection = {
    eyebrow: 'ทิศทางลม',
    title: `ไปทาง${windDestinationText}`,
    detail: `${windSpeed} km/h · ลมมาจากทิศ${windSourceText} แล้วพัดไปทาง${windDestinationText} · อัปเดต ${formatTime(dashboard.weather.latest_update)}`,
    imageKey: 'wind',
    imageLabel: 'Wind layer',
    stats: [
      { label: 'ความเร็ว', value: `${windSpeed} km/h` },
      { label: 'มาจาก', value: windSourceText },
      { label: 'ไปทาง', value: windDestinationText },
    ],
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="map-canvas">
      {/* Leaflet map mount point */}
      <div ref={mapDivRef} className="map-leaflet" />

      {/* Wind streamline overlay — fallback shown only until the leaflet-velocity
          particle layer is live (or if its grid fetch fails) */}
      {layers.wind && !windParticlesOn && (
        <svg
          className="wind-field-overlay"
          viewBox="-2 -2 4 4"
          preserveAspectRatio="xMidYMid slice"
          aria-hidden
          style={{ '--wind-dur': `${windDur}s` } as CSSProperties}
        >
          <g transform={`rotate(${windRotation})`}>
            {WIND_OV_LINES.map((line) => (
              <g key={line.id}>
                <path
                  id={line.id}
                  className="wind-flow-line"
                  d={line.d}
                  fill="none"
                  strokeWidth="0.022"
                  style={{ animationDelay: `${-line.delay}s` }}
                />
                <circle className="wind-particle" r="0.032">
                  <animateMotion
                    dur={`${windDur}s`}
                    begin={`${-line.delay}s`}
                    repeatCount="indefinite"
                    rotate="auto"
                    keyPoints="0;1"
                    keyTimes="0;1"
                    calcMode="linear"
                  >
                    <mpath href={`#${line.id}`} />
                  </animateMotion>
                </circle>
              </g>
            ))}
          </g>
        </svg>
      )}

      {/* Wind chip button */}
      {layers.wind && (
        <button
          type="button"
          className="wind-chip"
          onClick={() => onSelectionChange(windSelection)}
          aria-label={`ลมไปทาง${windDestinationText} ${windSpeed} km/h`}
        >
          <span className="wind-chip__compass" style={{ transform: `rotate(${windRotation}deg)` }}>
            <Wind size={15} />
          </span>
          <span className="wind-chip__text">
            <b>ไป{windDestinationText}</b>
            <small>{windSpeed} km/h</small>
          </span>
        </button>
      )}

      <div className="map-help">ลากเพื่อเลื่อน · เลื่อนเมาส์เพื่อซูม · คลิกจุดข้อมูล</div>

      <div className="map-legend">
        <span><i className="dot dot--pm" />สถานีวัด PM2.5</span>
        <span><i className="fire-ic">🔥</i>จุดความร้อน</span>
        <span><i className="arrow-ic">↑</i>ทิศทางลม</span>
      </div>

      <div className="map-controls">
        <span className="zoom-readout">ซูม {zoom}</span>
        <button type="button" aria-label="ขยาย" onClick={handleZoomIn}>
          <Plus size={18} />
        </button>
        <button type="button" aria-label="ย่อ" onClick={handleZoomOut}>
          <Minus size={18} />
        </button>
        <button type="button" aria-label="กลับสู่มุมมองเริ่มต้น" onClick={handleReset}>
          <Crosshair size={18} />
        </button>
      </div>
    </div>
  );
}
