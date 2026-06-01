import { useEffect, useMemo, useRef, useState, type CSSProperties, type KeyboardEvent, type PointerEvent } from 'react';
import { Crosshair, Minus, Plus, Wind } from 'lucide-react';
import type { DashboardResponse, Hotspot, Pm25Station } from '../lib/types';
import provinceGeo from '../data/chiangmai-province.json';
import districtsGeo from '../data/chiangmai-districts.json';
import neighbourGeo from '../data/neighbour-provinces.json';
import { windDestinationName } from '../lib/wind';

type Props = {
  dashboard: DashboardResponse;
  layers: {
    hotspots: boolean;
    pm25: boolean;
    wind: boolean;
  };
};

type GeoFeature = {
  type: string;
  properties: { name: string; nameTh: string };
  geometry: {
    type: string;
    coordinates: number[][][] | number[][][][];
  };
};

type GeoCollection = {
  type: string;
  features: GeoFeature[];
};

type ViewState = {
  zoom: number;
  panX: number;
  panY: number;
};

type DragState = {
  pointerId: number;
  startX: number;
  startY: number;
  panX: number;
  panY: number;
  moved: boolean;
};

type MapSelection = {
  eyebrow: string;
  title: string;
  detail: string;
  imageKey?: string;
  imageLabel?: string;
  stats?: { label: string; value: string; tone?: 'good' | 'watch' | 'risk' }[];
};

const COS_LAT = Math.cos((18.85 * Math.PI) / 180);
const PROJ = 1000;
const MIN_ZOOM = 1;
const MAX_ZOOM = 6.5;
const BUTTON_FACTOR = 1.45;
const DEFAULT_VIEW: ViewState = { zoom: 1, panX: 0, panY: 0 };

// GeoJSON coords = [lng, lat]
function project(lat: number, lng: number) {
  return { x: lng * COS_LAT * PROJ, y: -lat * PROJ };
}

function geoRingToPath(ring: number[][]): string {
  return (
    ring
      .map((c, i) => {
        const p = project(c[1], c[0]);
        return `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
      })
      .join(' ') + ' Z'
  );
}

function geoGeomToPath(geom: { type: string; coordinates: number[][][] | number[][][][] }): string {
  if (geom.type === 'Polygon') {
    const rings = geom.coordinates as number[][][];
    return rings.map(geoRingToPath).join(' ');
  }
  if (geom.type === 'MultiPolygon') {
    const polys = geom.coordinates as number[][][][];
    return polys.flatMap((poly) => poly.map(geoRingToPath)).join(' ');
  }
  return '';
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function clampView(next: ViewState): ViewState {
  const zoom = clamp(next.zoom, MIN_ZOOM, MAX_ZOOM);
  if (zoom <= 1) return { zoom: 1, panX: 0, panY: 0 };
  const maxPanX = (viewW * (zoom - 1)) / (2 * zoom);
  const maxPanY = (viewH * (zoom - 1)) / (2 * zoom);
  return {
    zoom,
    panX: clamp(next.panX, -maxPanX, maxPanX),
    panY: clamp(next.panY, -maxPanY, maxPanY),
  };
}

function formatPm25(value: number) {
  return `${value.toFixed(value % 1 ? 1 : 0)} µg/m³`;
}

function pm25ValueLabel(value: number) {
  return value.toFixed(value % 1 ? 1 : 0);
}

function formatTime(value: string) {
  return new Intl.DateTimeFormat('th-TH', { timeStyle: 'short' }).format(new Date(value));
}

// Province boundary coords [lng, lat]
const provinceCoordsRaw = (provinceGeo as { type: string; coordinates: number[][][] }).coordinates[0];
const provincePath = geoRingToPath(provinceCoordsRaw);

// Compute viewBox from province extent.
const projectedProvince = provinceCoordsRaw.map((c) => project(c[1], c[0]));
const xs = projectedProvince.map((p) => p.x);
const ys = projectedProvince.map((p) => p.y);
const rawMinX = Math.min(...xs);
const rawMaxX = Math.max(...xs);
const rawMinY = Math.min(...ys);
const rawMaxY = Math.max(...ys);
const spanX = rawMaxX - rawMinX;
const spanY = rawMaxY - rawMinY;
// Extra breathing room so the neighbouring provinces read as a ring around
// Chiang Mai. Horizontal padding is larger because the province is tall and
// narrow — this lets the east/west neighbours fill the frame edges.
const padX = spanX * 0.62;
const padY = spanY * 0.16;
const viewMinX = rawMinX - padX;
const viewMinY = rawMinY - padY;
const viewW = spanX + padX * 2;
const viewH = spanY + padY * 2;
const cx = viewMinX + viewW / 2;
const cy = viewMinY + viewH / 2;

const STATION_R = viewW * 0.016;
const HOTSPOT_R = viewW * 0.0095;
const VALUE_FONT = viewW * 0.0175;
const NEIGHBOUR_FONT = viewW * 0.02;
const CENTER_FONT = viewW * 0.036;
const DISTRICT_FONT = viewW * 0.0128;

// Neighbour provinces (decorative backdrop).
const neighbourPaths = (neighbourGeo as unknown as GeoCollection).features.map((f) => ({
  name: f.properties.name,
  nameTh: f.properties.nameTh,
  path: geoGeomToPath(f.geometry as { type: string; coordinates: number[][][] | number[][][][] }),
}));

// Curated label anchors so neighbour names sit nicely inside the frame.
const neighbourLabels: { name: string; lat: number; lng: number }[] = [
  { name: 'เชียงราย', lat: 19.92, lng: 99.74 },
  { name: 'แม่ฮ่องสอน', lat: 18.62, lng: 97.62 },
  { name: 'ลำพูน', lat: 18.0, lng: 99.05 },
  { name: 'ลำปาง', lat: 18.22, lng: 99.72 },
  { name: 'ตาก', lat: 17.4, lng: 98.62 },
  { name: 'พะเยา', lat: 19.32, lng: 99.92 },
];

// Wind streamlines — drawn around the origin, then translated to the province
// centre and rotated to the live wind bearing. Generous coverage so the field
// still fills the province at any rotation.
const WIND_COV = 1.2 * Math.max(spanX, spanY);
const WIND_HALF = WIND_COV / 2;
const WIND_LINES = Array.from({ length: 11 }, (_, i) => {
  const step = WIND_COV / 10;
  const lx = -WIND_HALF + i * step;
  const amp = step * 0.42 * (i % 2 === 0 ? 1 : -1);
  const d = `M ${lx.toFixed(1)} ${WIND_HALF.toFixed(1)} C ${(lx + amp).toFixed(1)} ${(WIND_COV / 6).toFixed(1)}, ${(lx - amp).toFixed(1)} ${(-WIND_COV / 6).toFixed(1)}, ${lx.toFixed(1)} ${(-WIND_HALF).toFixed(1)}`;
  return { id: `wind-line-${i}`, d, delay: (i % 5) * 0.6 };
});

function pm25Color(pm25: number) {
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

function plumeRadius(pm25: number) {
  return viewW * (0.045 + (Math.min(pm25, 120) / 120) * 0.1);
}

function stationImageKey(station: Pm25Station) {
  if (station.id === 'CM-O23') return 'bhubing';
  if (station.id === 'CM-O70') return 'chiangdao';
  if (station.id === 'CM-O71') return 'maechaem';
  if (station.id === 'CM-O69') return 'hot';
  if (station.id === 'CM-36T') return 'school';
  return 'city';
}

function hotspotImageKey(hotspot: Hotspot) {
  if (hotspot.landuse_type && hotspot.landuse_type !== 'OTHER') return 'forest';
  return 'hotspot';
}

function hotspotPlaceTitle(hotspot: Hotspot) {
  return hotspot.landuse_name || hotspot.district || hotspot.id;
}

function hotspotLocation(hotspot: Hotspot) {
  const parts = [
    hotspot.subdistrict ? `ต.${hotspot.subdistrict}` : '',
    hotspot.district ? `อ.${hotspot.district}` : '',
  ].filter(Boolean);
  return parts.join(' ');
}

function hotspotStats(hotspot: Hotspot): MapSelection['stats'] {
  return [
    { label: 'Confidence', value: `${hotspot.confidence}%`, tone: hotspot.confidence >= 80 ? 'risk' : 'watch' },
    { label: 'ประเภทพื้นที่', value: hotspot.landuse_name || hotspot.landuse_type || 'ไม่ระบุ' },
    { label: 'ดาวเทียม', value: hotspot.satellite || 'VIIRS' },
    { label: 'เวลา', value: formatTime(hotspot.detected_at) },
  ];
}

// District centroids for label positioning.
const districtLabels: { name: string; lat: number; lng: number }[] = [
  { name: 'แม่ริม', lat: 18.92, lng: 98.96 },
  { name: 'เมือง', lat: 18.79, lng: 98.98 },
  { name: 'สันทราย', lat: 18.98, lng: 99.13 },
  { name: 'ดอยสะเก็ด', lat: 18.93, lng: 99.22 },
  { name: 'แม่แตง', lat: 19.2, lng: 98.93 },
  { name: 'เชียงดาว', lat: 19.37, lng: 98.96 },
  { name: 'ฝาง', lat: 19.92, lng: 99.22 },
  { name: 'จอมทอง', lat: 18.44, lng: 98.69 },
  { name: 'ฮอด', lat: 18.18, lng: 98.59 },
  { name: 'แม่แจ่ม', lat: 18.49, lng: 98.33 },
  { name: 'กัลยาณิวัฒนา', lat: 19.04, lng: 98.43 },
  { name: 'แม่วาง', lat: 18.65, lng: 98.75 },
  { name: 'สะเมิง', lat: 18.84, lng: 98.73 },
  { name: 'แม่อาย', lat: 20.04, lng: 99.17 },
  { name: 'สันกำแพง', lat: 18.74, lng: 99.12 },
];

const initialSelection: MapSelection = {
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

export function DashboardMap({ dashboard, layers }: Props) {
  const [view, setView] = useState<ViewState>(DEFAULT_VIEW);
  const [smooth, setSmooth] = useState(false);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [selection, setSelection] = useState<MapSelection>(initialSelection);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  // Survives the pointerup→click sequence so a drag doesn't trigger a selection.
  const movedRef = useRef(false);

  const windRotation = dashboard.weather.wind_direction_deg + 180;
  const windSpeed = dashboard.weather.wind_speed_kmh;
  const windSourceText = dashboard.weather.wind_direction_text;
  const windDestinationText = windDestinationName(dashboard.weather.wind_direction_deg);
  // Faster wind ⇒ shorter cycle, so the streamlines visibly speed up.
  const windDur = clamp(36 / (windSpeed + 5), 1.4, 6);
  const aggCenter = project(18.98, 98.6);

  const districtPaths = useMemo(
    () =>
      (districtsGeo as unknown as GeoCollection).features.map((f) => ({
        path: geoGeomToPath(f.geometry as { type: string; coordinates: number[][][] | number[][][][] }),
        name: f.properties.name,
        nameTh: f.properties.nameTh || f.properties.name,
      })),
    [],
  );

  const mapTransform = `translate(${view.panX} ${view.panY}) translate(${cx} ${cy}) scale(${view.zoom}) translate(${-cx} ${-cy})`;

  // Convert a screen point into viewBox-space, accounting for the letterboxing
  // introduced by preserveAspectRatio="xMidYMid meet".
  const screenToViewBox = (clientX: number, clientY: number) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const scale = Math.min(rect.width / viewW, rect.height / viewH);
    const offsetX = (rect.width - viewW * scale) / 2;
    const offsetY = (rect.height - viewH * scale) / 2;
    return {
      x: viewMinX + (clientX - rect.left - offsetX) / scale,
      y: viewMinY + (clientY - rect.top - offsetY) / scale,
    };
  };

  // Zoom toward a viewBox-space anchor, keeping that point under the cursor.
  const zoomToward = (nextZoom: number, anchor: { x: number; y: number }) => {
    setView((current) => {
      const zoom = clamp(nextZoom, MIN_ZOOM, MAX_ZOOM);
      const content = {
        x: cx + (anchor.x - current.panX - cx) / current.zoom,
        y: cy + (anchor.y - current.panY - cy) / current.zoom,
      };
      return clampView({
        zoom,
        panX: anchor.x - cx - zoom * (content.x - cx),
        panY: anchor.y - cy - zoom * (content.y - cy),
      });
    });
  };

  const zoomByButton = (factor: number) => {
    setSmooth(true);
    zoomToward(viewRef.current.zoom * factor, { x: cx, y: cy });
  };

  const resetView = () => {
    setSmooth(true);
    setView(DEFAULT_VIEW);
    setSelection(initialSelection);
  };

  // Native, non-passive wheel listener so preventDefault actually stops the
  // page from scrolling and zooming feels continuous rather than stepped.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const onWheel = (event: globalThis.WheelEvent) => {
      event.preventDefault();
      setSmooth(false);
      const factor = Math.exp(-event.deltaY * 0.0016);
      zoomToward(viewRef.current.zoom * factor, screenToViewBox(event.clientX, event.clientY));
    };
    svg.addEventListener('wheel', onWheel, { passive: false });
    return () => svg.removeEventListener('wheel', onWheel);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handlePointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    setSmooth(false);
    movedRef.current = false;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      panX: view.panX,
      panY: view.panY,
      moved: false,
    });
  };

  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    if (!drag || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scale = Math.min(rect.width / viewW, rect.height / viewH) || 1;
    const dx = event.clientX - drag.startX;
    const dy = event.clientY - drag.startY;
    if (!drag.moved && Math.hypot(dx, dy) > 3) {
      movedRef.current = true;
      setDrag({ ...drag, moved: true });
    }
    setView((current) =>
      clampView({
        ...current,
        panX: drag.panX + dx / scale / current.zoom,
        panY: drag.panY + dy / scale / current.zoom,
      }),
    );
  };

  const stopDragging = (event: PointerEvent<SVGSVGElement>) => {
    if (drag?.pointerId === event.pointerId) {
      setDrag(null);
    }
  };

  const keySelect = (event: KeyboardEvent<SVGGElement>, next: MapSelection) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      setSelection(next);
    }
  };

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

  const selectStation = (station: Pm25Station) => {
    const tone = pm25Tone(station.pm25);
    setSelection({
      eyebrow: 'สถานีวัด PM2.5',
      title: station.name.trim() || station.id,
      detail: `${formatPm25(station.pm25)} · อัปเดต ${formatTime(station.updated_at)} · ${station.district} · ขอบเขตฝุ่นเป็นการประมาณด้วยรัศมีตามค่าฝุ่นของสถานี`,
      imageKey: stationImageKey(station),
      imageLabel: station.name.trim() || station.id,
      stats: [
        { label: 'PM2.5', value: formatPm25(station.pm25), tone },
        { label: 'รัศมีฝุ่น', value: tone === 'good' ? 'ต่ำ' : tone === 'watch' ? 'เฝ้าระวัง' : 'สูง', tone },
      ],
    });
  };

  const selectHotspot = (hotspot: Hotspot) => {
    const location = hotspotLocation(hotspot);
    setSelection({
      eyebrow: 'จุดความร้อน',
      title: hotspotPlaceTitle(hotspot),
      detail: `${location ? `${location} · ` : ''}ตรวจพบ ${formatTime(hotspot.detected_at)} · ${hotspot.source}`,
      imageKey: hotspotImageKey(hotspot),
      imageLabel: hotspotPlaceTitle(hotspot),
      stats: hotspotStats(hotspot),
    });
  };

  return (
    <div className="map-canvas">
      <svg
        ref={svgRef}
        className={`${drag?.moved ? 'is-dragging' : ''} ${smooth ? 'is-smooth' : ''}`.trim() || undefined}
        viewBox={`${viewMinX} ${viewMinY} ${viewW} ${viewH}`}
        role="img"
        aria-label="แผนที่จังหวัดเชียงใหม่"
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
        onPointerLeave={stopDragging}
      >
        <defs>
          <radialGradient id="terrain" cx="46%" cy="34%" r="90%">
            <stop offset="0%" stopColor="#f6fbf7" />
            <stop offset="62%" stopColor="#e8f0ea" />
            <stop offset="100%" stopColor="#d6e2da" />
          </radialGradient>
          <linearGradient id="province" x1="0" y1="0" x2="0.35" y2="1">
            <stop offset="0%" stopColor="#dcf0e2" />
            <stop offset="100%" stopColor="#bfe2c9" />
          </linearGradient>
          <linearGradient id="neighbour-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#e4ebe6" />
            <stop offset="100%" stopColor="#d4ded8" />
          </linearGradient>
          <pattern id="map-grid" width={viewW * 0.05} height={viewW * 0.05} patternUnits="userSpaceOnUse">
            <path
              d={`M ${viewW * 0.05} 0 L 0 0 0 ${viewW * 0.05}`}
              fill="none"
              stroke="#6aab7a"
              strokeWidth={viewW * 0.0006}
              strokeOpacity="0.16"
            />
          </pattern>
          <filter id="soft" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy={viewW * 0.0025} stdDeviation={viewW * 0.0035} floodColor="#1f4d3a" floodOpacity="0.2" />
          </filter>
          <filter id="province-lift" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy={viewW * 0.006} stdDeviation={viewW * 0.012} floodColor="#16432f" floodOpacity="0.22" />
          </filter>
          <clipPath id="province-clip">
            <path d={provincePath} />
          </clipPath>
          {/* Vignette that fades the decorative neighbours toward the frame edge. */}
          <radialGradient id="edge-fade" cx="50%" cy="48%" r="62%">
            <stop offset="0%" stopColor="#fff" />
            <stop offset="55%" stopColor="#fff" />
            <stop offset="100%" stopColor="#000" />
          </radialGradient>
          <mask id="neighbour-mask">
            <rect x={viewMinX} y={viewMinY} width={viewW} height={viewH} fill="url(#edge-fade)" />
          </mask>
        </defs>

        <rect x={viewMinX} y={viewMinY} width={viewW} height={viewH} fill="url(#terrain)" />

        <g transform={mapTransform} className="map-layer">
          {/* --- Decorative neighbouring provinces (muted backdrop) --- */}
          <g className="neighbour-layer" mask="url(#neighbour-mask)">
            {neighbourPaths.map((n) => (
              <path key={n.name} d={n.path} className="neighbour-path" />
            ))}
            {neighbourLabels.map((n) => {
              const p = project(n.lat, n.lng);
              return (
                <text key={n.name} x={p.x} y={p.y} className="neighbour-label" fontSize={NEIGHBOUR_FONT} textAnchor="middle">
                  {n.name}
                </text>
              );
            })}
          </g>

          {/* --- Chiang Mai (focus) --- */}
          <path d={provincePath} className="province-fill" fill="url(#province)" filter="url(#province-lift)" />
          <path d={provincePath} fill="url(#map-grid)" opacity="0.4" />

          <g clipPath="url(#province-clip)">
            {districtPaths.map((d) => {
              const next: MapSelection = {
                eyebrow: 'อำเภอ',
                title: d.nameTh,
                detail: 'อยู่ภายในขอบเขตจังหวัดเชียงใหม่ คลิกจุดข้อมูลเพื่อดูสถานะ PM2.5 หรือจุดความร้อน',
                imageKey: 'district',
                imageLabel: d.nameTh,
                stats: [
                  { label: 'จังหวัด', value: 'เชียงใหม่' },
                  { label: 'ชั้นข้อมูล', value: 'ขอบเขตอำเภอ' },
                ],
              };
              return (
                <path
                  key={d.name}
                  d={d.path}
                  className="district-path"
                  fill="rgba(255,255,255,0.02)"
                  stroke="#6aab7a"
                  strokeWidth={viewW * 0.0012}
                  strokeOpacity="0.5"
                  tabIndex={0}
                  role="button"
                  aria-label={`ดูรายละเอียดอำเภอ${d.nameTh}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (!movedRef.current) setSelection(next);
                  }}
                  onKeyDown={(event) => keySelect(event, next)}
                >
                  <title>{d.nameTh}</title>
                </path>
              );
            })}
          </g>

          <path d={provincePath} fill="none" stroke="#0f6b54" strokeWidth={viewW * 0.0085} strokeOpacity="0.12" />
          <path
            d={provincePath}
            fill="none"
            stroke="#0f6b54"
            strokeWidth={viewW * 0.004}
            strokeLinejoin="round"
          />

          {districtLabels.map((d) => {
            const p = project(d.lat, d.lng);
            return (
              <text
                key={d.name}
                x={p.x}
                y={p.y}
                fontSize={DISTRICT_FONT}
                fill="#3d6a50"
                fontWeight={500}
                textAnchor="middle"
                opacity="0.72"
              >
                {d.name}
              </text>
            );
          })}

          <text
            x={aggCenter.x}
            y={aggCenter.y - viewW * 0.08}
            className="province-title-label"
            fontSize={CENTER_FONT}
            textAnchor="middle"
          >
            เชียงใหม่
          </text>

          {/* --- Wind streamlines: flow over the province along the live bearing --- */}
          {layers.wind && (
            <g clipPath="url(#province-clip)" className="wind-field" aria-hidden style={{ '--wind-dur': `${windDur}s` } as CSSProperties}>
              <g transform={`translate(${cx} ${cy}) rotate(${windRotation})`}>
                {WIND_LINES.map((line) => (
                  <g key={line.id}>
                    <path
                      id={line.id}
                      className="wind-flow-line"
                      d={line.d}
                      fill="none"
                      strokeWidth={viewW * 0.0016}
                      style={{ animationDelay: `${-line.delay}s` }}
                    />
                    <circle className="wind-particle" r={viewW * 0.0026}>
                      <animateMotion dur={`${windDur}s`} begin={`${-line.delay}s`} repeatCount="indefinite" rotate="auto" keyPoints="0;1" keyTimes="0;1" calcMode="linear">
                        <mpath href={`#${line.id}`} />
                      </animateMotion>
                    </circle>
                  </g>
                ))}
              </g>
            </g>
          )}

          {layers.hotspots &&
            dashboard.hotspots.items.map((h) => {
              const p = project(h.latitude, h.longitude);
              const location = hotspotLocation(h);
              const next: MapSelection = {
                eyebrow: 'จุดความร้อน',
                title: hotspotPlaceTitle(h),
                detail: `${location ? `${location} · ` : ''}ตรวจพบ ${formatTime(h.detected_at)} · ${h.source}`,
                imageKey: hotspotImageKey(h),
                imageLabel: hotspotPlaceTitle(h),
                stats: hotspotStats(h),
              };
              return (
                <g
                  key={h.id}
                  className={`map-marker hotspot-marker ${h.landuse_type && h.landuse_type !== 'OTHER' ? 'hotspot-marker--forest' : 'hotspot-marker--other'}`}
                  tabIndex={0}
                  role="button"
                  aria-label={`ดูรายละเอียดจุดความร้อน ${hotspotPlaceTitle(h)}`}
                  onMouseEnter={() => selectHotspot(h)}
                  onFocus={() => selectHotspot(h)}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (!movedRef.current) selectHotspot(h);
                  }}
                  onKeyDown={(event) => keySelect(event, next)}
                >
                  <title>{`${hotspotPlaceTitle(h)} · ${h.confidence}% · ${h.satellite || 'VIIRS'}`}</title>
                  <circle className="hotspot-marker__halo" cx={p.x} cy={p.y} r={HOTSPOT_R * 2.45} />
                  <circle className="hotspot-marker__ring" cx={p.x} cy={p.y} r={HOTSPOT_R * 1.55} />
                  <text className="hotspot-marker__emoji" x={p.x} y={p.y + HOTSPOT_R * 0.58} fontSize={HOTSPOT_R * 2.05} textAnchor="middle">
                    🔥
                  </text>
                </g>
              );
            })}

          {layers.pm25 && (
            <g>
              <g clipPath="url(#province-clip)" className="pm-plume-layer">
                <circle
                  cx={aggCenter.x}
                  cy={aggCenter.y}
                  r={plumeRadius(dashboard.pm25.current_pm25) * 1.35}
                  className={`pm-plume pm-plume--${pm25Tone(dashboard.pm25.current_pm25)}`}
                />
                {dashboard.pm25.stations.map((s) => {
                  const p = project(s.latitude, s.longitude);
                  return <circle key={`plume-${s.id}`} cx={p.x} cy={p.y} r={plumeRadius(s.pm25)} className={`pm-plume pm-plume--${pm25Tone(s.pm25)}`} />;
                })}
              </g>

              <g
                filter="url(#soft)"
                className="map-marker pm-station"
                tabIndex={0}
                role="button"
                aria-label="ดูรายละเอียด PM2.5 เฉลี่ยจังหวัด"
                onMouseEnter={() =>
                  setSelection({
                    eyebrow: 'ค่าเฉลี่ยจังหวัด',
                    title: 'PM2.5 เชียงใหม่',
                    detail: `${formatPm25(dashboard.pm25.current_pm25)} · ${dashboard.pm25.category} · อัปเดต ${formatTime(dashboard.pm25.latest_update)}`,
                    imageKey: 'province',
                    imageLabel: 'Chiang Mai province',
                    stats: [
                      { label: 'PM2.5 เฉลี่ย', value: formatPm25(dashboard.pm25.current_pm25), tone: pm25Tone(dashboard.pm25.current_pm25) },
                      { label: 'สถานี', value: `${dashboard.pm25.stations.length} จุด` },
                    ],
                  })
                }
                onClick={(event) => {
                  event.stopPropagation();
                  if (movedRef.current) return;
                  setSelection({
                    eyebrow: 'ค่าเฉลี่ยจังหวัด',
                    title: 'PM2.5 เชียงใหม่',
                    detail: `${formatPm25(dashboard.pm25.current_pm25)} · ${dashboard.pm25.category} · อัปเดต ${formatTime(dashboard.pm25.latest_update)}`,
                    imageKey: 'province',
                    imageLabel: 'Chiang Mai province',
                    stats: [
                      { label: 'PM2.5 เฉลี่ย', value: formatPm25(dashboard.pm25.current_pm25), tone: pm25Tone(dashboard.pm25.current_pm25) },
                      { label: 'สถานี', value: `${dashboard.pm25.stations.length} จุด` },
                    ],
                  });
                }}
                onKeyDown={(event) =>
                  keySelect(event, {
                    eyebrow: 'ค่าเฉลี่ยจังหวัด',
                    title: 'PM2.5 เชียงใหม่',
                    detail: `${formatPm25(dashboard.pm25.current_pm25)} · ${dashboard.pm25.category}`,
                    imageKey: 'province',
                    imageLabel: 'Chiang Mai province',
                  })
                }
              >
                <circle cx={aggCenter.x} cy={aggCenter.y} r={STATION_R * 2.05} className="pm-station__ring" />
                <circle cx={aggCenter.x} cy={aggCenter.y} r={STATION_R * 1.42} fill={pm25Color(dashboard.pm25.current_pm25)} stroke="#fff" strokeWidth={viewW * 0.0035} />
                <text x={aggCenter.x} y={aggCenter.y + VALUE_FONT * 0.36} fontSize={VALUE_FONT * 1.15} fill="#fff" fontWeight={700} textAnchor="middle">
                  {pm25ValueLabel(dashboard.pm25.current_pm25)}
                </text>
              </g>

              {dashboard.pm25.stations.map((s) => {
                const p = project(s.latitude, s.longitude);
                const next: MapSelection = {
                  eyebrow: 'สถานีวัด PM2.5',
                  title: s.name.trim() || s.id,
                  detail: `${formatPm25(s.pm25)} · ${s.district}`,
                  imageKey: stationImageKey(s),
                  imageLabel: s.name.trim() || s.id,
                  stats: [
                    { label: 'PM2.5', value: formatPm25(s.pm25), tone: pm25Tone(s.pm25) },
                    { label: 'อัปเดต', value: formatTime(s.updated_at) },
                  ],
                };
                return (
                  <g
                    key={s.id}
                    filter="url(#soft)"
                    className="map-marker pm-station"
                    tabIndex={0}
                    role="button"
                    aria-label={`ดูรายละเอียดสถานี ${s.name.trim() || s.id}`}
                    onMouseEnter={() => selectStation(s)}
                    onFocus={() => selectStation(s)}
                    onClick={(event) => {
                      event.stopPropagation();
                      if (!movedRef.current) selectStation(s);
                    }}
                    onKeyDown={(event) => keySelect(event, next)}
                  >
                    <title>{`${s.name.trim() || s.id} · ${formatPm25(s.pm25)}`}</title>
                    <circle cx={p.x} cy={p.y} r={STATION_R * 1.45} className="pm-station__ring" />
                    <circle cx={p.x} cy={p.y} r={STATION_R * 1.04} fill={pm25Color(s.pm25)} stroke="#fff" strokeWidth={viewW * 0.0026} />
                    <text x={p.x} y={p.y + VALUE_FONT * 0.32} fontSize={VALUE_FONT * 0.86} fill="#fff" fontWeight={800} textAnchor="middle">
                      {pm25ValueLabel(s.pm25)}
                    </text>
                  </g>
                );
              })}
            </g>
          )}
        </g>
      </svg>

      {layers.wind && (
        <button
          type="button"
          className="wind-chip"
          onClick={() => setSelection(windSelection)}
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

      <div className="map-inspector" aria-live="polite">
        <div className={`map-inspector__photo map-inspector__photo--${selection.imageKey ?? 'province'}`}>
          <span>{selection.imageLabel ?? selection.title}</span>
        </div>
        <span>{selection.eyebrow}</span>
        <strong>{selection.title}</strong>
        <small>{selection.detail}</small>
        {selection.stats && (
          <div className="map-inspector__stats">
            {selection.stats.map((stat) => (
              <div key={`${stat.label}-${stat.value}`} className={`map-inspector__stat ${stat.tone ? `map-inspector__stat--${stat.tone}` : ''}`}>
                <span>{stat.label}</span>
                <b>{stat.value}</b>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="map-help">ลากเพื่อเลื่อน · เลื่อนเมาส์เพื่อซูมตรงจุด · คลิกจุดข้อมูล</div>

      <div className="map-legend">
        <span><i className="dot dot--pm" />สถานีวัด PM2.5</span>
        <span><i className="fire-ic">🔥</i>จุดความร้อน</span>
        <span><i className="arrow-ic">↑</i>ทิศทางลม</span>
      </div>

      <div className="map-scale" aria-hidden>
        <span className="map-scale__bar" />
        20 km
      </div>

      <div className="map-controls">
        <span className="zoom-readout">ซูม {view.zoom.toFixed(1)}x</span>
        <button type="button" aria-label="ขยาย" onClick={() => zoomByButton(BUTTON_FACTOR)}>
          <Plus size={18} />
        </button>
        <button type="button" aria-label="ย่อ" onClick={() => zoomByButton(1 / BUTTON_FACTOR)}>
          <Minus size={18} />
        </button>
        <button type="button" aria-label="กลับสู่มุมมองเริ่มต้น" onClick={resetView}>
          <Crosshair size={18} />
        </button>
      </div>
    </div>
  );
}
