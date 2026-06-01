import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent, type WheelEvent } from 'react';
import { Crosshair, Minus, Plus } from 'lucide-react';
import type { DashboardResponse, Hotspot, Pm25Station } from '../lib/types';
import provinceGeo from '../data/chiangmai-province.json';
import districtsGeo from '../data/chiangmai-districts.json';

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
};

type MapSelection = {
  eyebrow: string;
  title: string;
  detail: string;
};

const COS_LAT = Math.cos((18.85 * Math.PI) / 180);
const PROJ = 1000;
const MIN_ZOOM = 0.9;
const MAX_ZOOM = 3.4;
const ZOOM_STEP = 0.35;
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

function formatPm25(value: number) {
  return `${value.toFixed(value % 1 ? 1 : 0)} µg/m³`;
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
const padX = spanX * 0.2;
const padY = spanY * 0.08;
const viewMinX = rawMinX - padX;
const viewMinY = rawMinY - padY;
const viewW = spanX + padX * 2;
const viewH = spanY + padY * 2;
const cx = viewMinX + viewW / 2;
const cy = viewMinY + viewH / 2;

const STATION_R = viewW * 0.02;
const HOTSPOT_R = viewW * 0.012;
const VALUE_FONT = viewW * 0.022;
const NEIGHBOUR_FONT = viewW * 0.026;
const CENTER_FONT = viewW * 0.045;
const DISTRICT_FONT = viewW * 0.016;

function pm25Color(pm25: number) {
  if (pm25 <= 25) return '#16a34a';
  if (pm25 <= 37) return '#eab308';
  if (pm25 <= 50) return '#f97316';
  if (pm25 <= 90) return '#dc2626';
  return '#7c3aed';
}

const neighbours = [
  { label: 'เชียงราย', lat: 19.95, lng: 99.72 },
  { label: 'แม่ฮ่องสอน', lat: 18.52, lng: 97.18 },
  { label: 'ลำพูน', lat: 18.05, lng: 99.08 },
  { label: 'ลำปาง', lat: 18.28, lng: 99.68 },
  { label: 'ตาก', lat: 17.42, lng: 98.6 },
];

const windPositions: [number, number][] = [
  [19.55, 98.62],
  [19.3, 99.18],
  [19.02, 98.78],
  [18.66, 99.22],
  [18.58, 98.5],
  [18.22, 98.92],
  [18.4, 98.18],
  [19.72, 98.95],
];

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
  detail: 'ลากแผนที่เพื่อเลื่อน ซูมเข้าออกเพื่อดูเส้นอำเภอและจุดข้อมูลให้ชัดขึ้น',
};

export function DashboardMap({ dashboard, layers }: Props) {
  const [view, setView] = useState<ViewState>(DEFAULT_VIEW);
  const [drag, setDrag] = useState<DragState | null>(null);
  const [selection, setSelection] = useState<MapSelection>(initialSelection);
  const svgRef = useRef<SVGSVGElement | null>(null);

  const windRotation = dashboard.weather.wind_direction_deg + 180;
  const arrowSize = viewW * 0.024;
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

  const changeZoom = (delta: number) => {
    setView((current) => ({
      ...current,
      zoom: Number(clamp(current.zoom + delta, MIN_ZOOM, MAX_ZOOM).toFixed(2)),
    }));
  };

  const resetView = () => {
    setView(DEFAULT_VIEW);
    setSelection(initialSelection);
  };

  const handleWheel = (event: WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    changeZoom(event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
  };

  const handlePointerDown = (event: PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      panX: view.panX,
      panY: view.panY,
    });
  };

  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    if (!drag || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const scaleX = viewW / rect.width;
    const scaleY = viewH / rect.height;
    setView((current) => ({
      ...current,
      panX: drag.panX + ((event.clientX - drag.startX) * scaleX) / current.zoom,
      panY: drag.panY + ((event.clientY - drag.startY) * scaleY) / current.zoom,
    }));
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

  const selectStation = (station: Pm25Station) => {
    setSelection({
      eyebrow: 'สถานีวัด PM2.5',
      title: station.name.trim() || station.id,
      detail: `${formatPm25(station.pm25)} · อัปเดต ${formatTime(station.updated_at)} · ${station.district}`,
    });
  };

  const selectHotspot = (hotspot: Hotspot) => {
    setSelection({
      eyebrow: 'จุดความร้อน',
      title: hotspot.district || hotspot.id,
      detail: `ความเชื่อมั่น ${hotspot.confidence}% · ตรวจพบ ${formatTime(hotspot.detected_at)} · ${hotspot.source}`,
    });
  };

  return (
    <div className="map-canvas">
      <svg
        ref={svgRef}
        className={drag ? 'is-dragging' : undefined}
        viewBox={`${viewMinX} ${viewMinY} ${viewW} ${viewH}`}
        role="img"
        aria-label="แผนที่จังหวัดเชียงใหม่"
        preserveAspectRatio="xMidYMid meet"
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
        onPointerLeave={stopDragging}
      >
        <defs>
          <radialGradient id="terrain" cx="42%" cy="38%" r="80%">
            <stop offset="0%" stopColor="#f4faf5" />
            <stop offset="100%" stopColor="#e3ece6" />
          </radialGradient>
          <linearGradient id="province" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#d9eedf" />
            <stop offset="100%" stopColor="#c4e4cd" />
          </linearGradient>
          <pattern id="map-grid" width={viewW * 0.06} height={viewW * 0.06} patternUnits="userSpaceOnUse">
            <path d={`M ${viewW * 0.06} 0 L 0 0 0 ${viewW * 0.06}`} fill="none" stroke="#6aab7a" strokeWidth={viewW * 0.0007} strokeOpacity="0.18" />
          </pattern>
          <filter id="soft" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy={viewW * 0.003} stdDeviation={viewW * 0.004} floodColor="#1f4d3a" floodOpacity="0.18" />
          </filter>
          <clipPath id="province-clip">
            <path d={provincePath} />
          </clipPath>
        </defs>

        <rect x={viewMinX} y={viewMinY} width={viewW} height={viewH} fill="url(#terrain)" />

        <g transform={mapTransform} className="map-layer">
          <path d={provincePath} fill="url(#province)" />
          <path d={provincePath} fill="url(#map-grid)" opacity="0.42" />

          <g clipPath="url(#province-clip)">
            {districtPaths.map((d) => {
              const next = {
                eyebrow: 'อำเภอ',
                title: d.nameTh,
                detail: 'อยู่ภายในขอบเขตจังหวัดเชียงใหม่ คลิกจุดข้อมูลเพื่อดูสถานะ PM2.5 หรือจุดความร้อน',
              };
              return (
                <path
                  key={d.name}
                  d={d.path}
                  className="district-path"
                  fill="rgba(255,255,255,0.02)"
                  stroke="#6aab7a"
                  strokeWidth={viewW * 0.0014}
                  strokeOpacity="0.5"
                  tabIndex={0}
                  role="button"
                  aria-label={`ดูรายละเอียดอำเภอ${d.nameTh}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    setSelection(next);
                  }}
                  onKeyDown={(event) => keySelect(event, next)}
                >
                  <title>{d.nameTh}</title>
                </path>
              );
            })}
          </g>

          <path d={provincePath} fill="none" stroke="#0f6b54" strokeWidth={viewW * 0.01} strokeOpacity="0.15" />
          <path
            d={provincePath}
            fill="none"
            stroke="#0f6b54"
            strokeWidth={viewW * 0.0042}
            strokeDasharray={`${viewW * 0.011} ${viewW * 0.008}`}
            strokeLinejoin="round"
          />

          {neighbours.map((n) => {
            const p = project(n.lat, n.lng);
            return (
              <text key={n.label} x={p.x} y={p.y} fontSize={NEIGHBOUR_FONT} fill="#7c8d84" fontWeight={600} textAnchor="middle">
                {n.label}
              </text>
            );
          })}

          {districtLabels.map((d) => {
            const p = project(d.lat, d.lng);
            return (
              <text key={d.name} x={p.x} y={p.y} fontSize={DISTRICT_FONT} fill="#3d6a50" fontWeight={500} textAnchor="middle" opacity="0.74">
                {d.name}
              </text>
            );
          })}

          <text x={aggCenter.x} y={aggCenter.y - viewW * 0.08} fontSize={CENTER_FONT} fill="#3f5a4e" fontWeight={700} textAnchor="middle" opacity="0.42">
            เชียงใหม่
          </text>

          {layers.wind &&
            windPositions.map(([lat, lng]) => {
              const p = project(lat, lng);
              const next = {
                eyebrow: 'ทิศทางลม',
                title: dashboard.weather.wind_direction_text,
                detail: `${dashboard.weather.wind_speed_kmh} km/h · อัปเดต ${formatTime(dashboard.weather.latest_update)}`,
              };
              return (
                <g
                  key={`${lat}-${lng}`}
                  transform={`translate(${p.x} ${p.y}) rotate(${windRotation})`}
                  className="wind-arrow"
                  tabIndex={0}
                  role="button"
                  aria-label="ดูรายละเอียดทิศทางลม"
                  onClick={(event) => {
                    event.stopPropagation();
                    setSelection(next);
                  }}
                  onKeyDown={(event) => keySelect(event, next)}
                >
                  <title>{`${dashboard.weather.wind_direction_text} ${dashboard.weather.wind_speed_kmh} km/h`}</title>
                  <path
                    d={`M0 ${-arrowSize} L${arrowSize * 0.4} ${-arrowSize * 0.1} L${arrowSize * 0.16} ${-arrowSize * 0.1} L${arrowSize * 0.16} ${arrowSize} L${-arrowSize * 0.16} ${arrowSize} L${-arrowSize * 0.16} ${-arrowSize * 0.1} L${-arrowSize * 0.4} ${-arrowSize * 0.1} Z`}
                    fill="#2563eb"
                    opacity="0.82"
                  />
                </g>
              );
            })}

          {layers.hotspots &&
            dashboard.hotspots.items.map((h) => {
              const p = project(h.latitude, h.longitude);
              const next = {
                eyebrow: 'จุดความร้อน',
                title: h.district || h.id,
                detail: `ความเชื่อมั่น ${h.confidence}% · ตรวจพบ ${formatTime(h.detected_at)}`,
              };
              return (
                <g
                  key={h.id}
                  className="map-marker"
                  tabIndex={0}
                  role="button"
                  aria-label={`ดูรายละเอียดจุดความร้อน ${h.district || h.id}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    selectHotspot(h);
                  }}
                  onKeyDown={(event) => keySelect(event, next)}
                >
                  <title>{`${h.district || h.id} · ${h.confidence}%`}</title>
                  <circle cx={p.x} cy={p.y} r={HOTSPOT_R} fill="#ef4444" stroke="#fff" strokeWidth={viewW * 0.002} />
                </g>
              );
            })}

          {layers.pm25 && (
            <g>
              <g
                filter="url(#soft)"
                className="map-marker"
                tabIndex={0}
                role="button"
                aria-label="ดูรายละเอียด PM2.5 เฉลี่ยจังหวัด"
                onClick={(event) => {
                  event.stopPropagation();
                  setSelection({
                    eyebrow: 'ค่าเฉลี่ยจังหวัด',
                    title: 'PM2.5 เชียงใหม่',
                    detail: `${formatPm25(dashboard.pm25.current_pm25)} · ${dashboard.pm25.category} · อัปเดต ${formatTime(dashboard.pm25.latest_update)}`,
                  });
                }}
                onKeyDown={(event) =>
                  keySelect(event, {
                    eyebrow: 'ค่าเฉลี่ยจังหวัด',
                    title: 'PM2.5 เชียงใหม่',
                    detail: `${formatPm25(dashboard.pm25.current_pm25)} · ${dashboard.pm25.category}`,
                  })
                }
              >
                <circle cx={aggCenter.x} cy={aggCenter.y} r={STATION_R * 1.7} fill="#16a34a" stroke="#fff" strokeWidth={viewW * 0.004} />
                <text x={aggCenter.x} y={aggCenter.y + VALUE_FONT * 0.36} fontSize={VALUE_FONT * 1.15} fill="#fff" fontWeight={700} textAnchor="middle">
                  {dashboard.pm25.current_pm25}
                </text>
              </g>

              {dashboard.pm25.stations.map((s) => {
                const p = project(s.latitude, s.longitude);
                const next = {
                  eyebrow: 'สถานีวัด PM2.5',
                  title: s.name.trim() || s.id,
                  detail: `${formatPm25(s.pm25)} · ${s.district}`,
                };
                return (
                  <g
                    key={s.id}
                    filter="url(#soft)"
                    className="map-marker"
                    tabIndex={0}
                    role="button"
                    aria-label={`ดูรายละเอียดสถานี ${s.name.trim() || s.id}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectStation(s);
                    }}
                    onKeyDown={(event) => keySelect(event, next)}
                  >
                    <title>{`${s.name.trim() || s.id} · ${formatPm25(s.pm25)}`}</title>
                    <circle cx={p.x} cy={p.y} r={STATION_R} fill={pm25Color(s.pm25)} stroke="#fff" strokeWidth={viewW * 0.003} />
                    <text x={p.x} y={p.y - STATION_R - VALUE_FONT * 0.35} fontSize={VALUE_FONT} fill="#143b2d" fontWeight={700} textAnchor="middle">
                      {s.pm25}
                    </text>
                  </g>
                );
              })}
            </g>
          )}
        </g>
      </svg>

      <div className="map-inspector" aria-live="polite">
        <span>{selection.eyebrow}</span>
        <strong>{selection.title}</strong>
        <small>{selection.detail}</small>
      </div>

      <div className="map-help">ลากเพื่อเลื่อน · ซูมเพื่อดูรายละเอียด · คลิกจุดข้อมูล</div>

      <div className="map-legend">
        <span><i className="dot dot--pm" />สถานีวัด PM2.5</span>
        <span><i className="dot dot--hot" />จุดความร้อน</span>
        <span><i className="arrow-ic">↑</i>ทิศทางลม</span>
      </div>

      <div className="map-scale" aria-hidden>
        <span className="map-scale__bar" />
        20 km
      </div>

      <div className="map-controls">
        <span className="zoom-readout">ซูม {view.zoom.toFixed(1)}x</span>
        <button type="button" aria-label="ขยาย" onClick={() => changeZoom(ZOOM_STEP)}>
          <Plus size={18} />
        </button>
        <button type="button" aria-label="ย่อ" onClick={() => changeZoom(-ZOOM_STEP)}>
          <Minus size={18} />
        </button>
        <button type="button" aria-label="กลับสู่มุมมองเริ่มต้น" onClick={resetView}>
          <Crosshair size={18} />
        </button>
      </div>
    </div>
  );
}
