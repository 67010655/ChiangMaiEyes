import { useMemo, useState } from 'react';
import { Crosshair, Minus, Plus } from 'lucide-react';
import type { DashboardResponse } from '../lib/types';
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

const COS_LAT = Math.cos((18.85 * Math.PI) / 180);
const PROJ = 1000;

// GeoJSON coords = [lng, lat]
function project(lat: number, lng: number) {
  return { x: lng * COS_LAT * PROJ, y: -lat * PROJ };
}

function geoRingToPath(ring: number[][]): string {
  return ring
    .map((c, i) => {
      const p = project(c[1], c[0]);
      return `${i === 0 ? 'M' : 'L'}${p.x.toFixed(2)} ${p.y.toFixed(2)}`;
    })
    .join(' ') + ' Z';
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

// Province boundary coords [lng, lat]
const provinceCoordsRaw = (provinceGeo as { type: string; coordinates: number[][][] }).coordinates[0];
const provincePath = geoRingToPath(provinceCoordsRaw);

// Compute viewBox from province extent
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

// District centroids for label positioning (computed from GADM)
const districtLabels: { name: string; lat: number; lng: number }[] = [
  { name: 'แม่ริม', lat: 18.92, lng: 98.96 },
  { name: 'เมือง', lat: 18.79, lng: 98.98 },
  { name: 'สันทราย', lat: 18.98, lng: 99.13 },
  { name: 'ดอยสะเก็ด', lat: 18.93, lng: 99.22 },
  { name: 'แม่ตาง', lat: 19.2, lng: 98.93 },
  { name: 'เชียงดาว', lat: 19.37, lng: 98.96 },
  { name: 'ฝาง', lat: 19.92, lng: 99.22 },
  { name: 'จอมทอง', lat: 18.44, lng: 98.69 },
  { name: 'ฮอด', lat: 18.18, lng: 98.59 },
  { name: 'แม่แจ่ม', lat: 18.49, lng: 98.33 },
  { name: 'กัลยาณิ', lat: 19.04, lng: 98.43 },
  { name: 'แม่วาง', lat: 18.65, lng: 98.75 },
  { name: 'สะเมิง', lat: 18.84, lng: 98.73 },
  { name: 'แม่อาย', lat: 20.04, lng: 99.17 },
  { name: 'สันกำแพง', lat: 18.74, lng: 99.12 },
];

export function DashboardMap({ dashboard, layers }: Props) {
  const [zoom, setZoom] = useState(1);

  const windRotation = dashboard.weather.wind_direction_deg + 180;
  const arrowSize = viewW * 0.024;

  const aggCenter = project(18.98, 98.6);

  const districtPaths = useMemo(
    () =>
      (districtsGeo as unknown as GeoCollection).features.map((f) => ({
        path: geoGeomToPath(f.geometry as { type: string; coordinates: number[][][] | number[][][][] }),
        name: f.properties.name,
        nameTh: f.properties.nameTh,
      })),
    [],
  );

  return (
    <div className="map-canvas">
      <svg
        viewBox={`${viewMinX} ${viewMinY} ${viewW} ${viewH}`}
        role="img"
        aria-label="แผนที่จังหวัดเชียงใหม่"
        preserveAspectRatio="xMidYMid meet"
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
          <filter id="soft" x="-30%" y="-30%" width="160%" height="160%">
            <feDropShadow dx="0" dy={viewW * 0.003} stdDeviation={viewW * 0.004} floodColor="#1f4d3a" floodOpacity="0.18" />
          </filter>
          <clipPath id="province-clip">
            <path d={provincePath} />
          </clipPath>
        </defs>

        {/* Background */}
        <rect x={viewMinX} y={viewMinY} width={viewW} height={viewH} fill="url(#terrain)" />

        <g transform={`translate(${cx} ${cy}) scale(${zoom}) translate(${-cx} ${-cy})`} style={{ transition: 'transform 0.25s ease' }}>

          {/* Province fill */}
          <path d={provincePath} fill="url(#province)" />

          {/* District boundaries (clipped inside province) */}
          <g clipPath="url(#province-clip)">
            {districtPaths.map((d) => (
              <path
                key={d.name}
                d={d.path}
                fill="none"
                stroke="#6aab7a"
                strokeWidth={viewW * 0.0012}
                strokeOpacity="0.45"
              />
            ))}
          </g>

          {/* Province border */}
          <path d={provincePath} fill="none" stroke="#0f6b54" strokeWidth={viewW * 0.01} strokeOpacity="0.15" />
          <path
            d={provincePath}
            fill="none"
            stroke="#0f6b54"
            strokeWidth={viewW * 0.0042}
            strokeDasharray={`${viewW * 0.011} ${viewW * 0.008}`}
            strokeLinejoin="round"
          />

          {/* Neighbour labels */}
          {neighbours.map((n) => {
            const p = project(n.lat, n.lng);
            return (
              <text key={n.label} x={p.x} y={p.y} fontSize={NEIGHBOUR_FONT} fill="#7c8d84" fontWeight={600} textAnchor="middle">
                {n.label}
              </text>
            );
          })}

          {/* District name labels */}
          {districtLabels.map((d) => {
            const p = project(d.lat, d.lng);
            return (
              <text key={d.name} x={p.x} y={p.y} fontSize={DISTRICT_FONT} fill="#3d6a50" fontWeight={500} textAnchor="middle" opacity="0.7">
                {d.name}
              </text>
            );
          })}

          {/* Province centre label */}
          <text x={aggCenter.x} y={aggCenter.y - viewW * 0.08} fontSize={CENTER_FONT} fill="#3f5a4e" fontWeight={700} textAnchor="middle" opacity="0.45">
            เชียงใหม่
          </text>

          {/* Wind arrows */}
          {layers.wind &&
            windPositions.map(([lat, lng]) => {
              const p = project(lat, lng);
              return (
                <g key={`${lat}-${lng}`} transform={`translate(${p.x} ${p.y}) rotate(${windRotation})`}>
                  <path
                    d={`M0 ${-arrowSize} L${arrowSize * 0.4} ${-arrowSize * 0.1} L${arrowSize * 0.16} ${-arrowSize * 0.1} L${arrowSize * 0.16} ${arrowSize} L${-arrowSize * 0.16} ${arrowSize} L${-arrowSize * 0.16} ${-arrowSize * 0.1} L${-arrowSize * 0.4} ${-arrowSize * 0.1} Z`}
                    fill="#3b82f6"
                    opacity="0.82"
                  />
                </g>
              );
            })}

          {/* Hotspot dots */}
          {layers.hotspots &&
            dashboard.hotspots.items.map((h) => {
              const p = project(h.latitude, h.longitude);
              return <circle key={h.id} cx={p.x} cy={p.y} r={HOTSPOT_R} fill="#ef4444" stroke="#fff" strokeWidth={viewW * 0.002} />;
            })}

          {/* PM2.5 station markers */}
          {layers.pm25 && (
            <g>
              <g filter="url(#soft)">
                <circle cx={aggCenter.x} cy={aggCenter.y} r={STATION_R * 1.7} fill="#16a34a" stroke="#fff" strokeWidth={viewW * 0.004} />
                <text x={aggCenter.x} y={aggCenter.y + VALUE_FONT * 0.36} fontSize={VALUE_FONT * 1.15} fill="#fff" fontWeight={700} textAnchor="middle">
                  {dashboard.pm25.current_pm25}
                </text>
              </g>

              {dashboard.pm25.stations.map((s) => {
                const p = project(s.latitude, s.longitude);
                return (
                  <g key={s.id} filter="url(#soft)">
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
        <button type="button" aria-label="ขยาย" onClick={() => setZoom((z) => Math.min(3, +(z + 0.3).toFixed(1)))}>
          <Plus size={18} />
        </button>
        <button type="button" aria-label="ย่อ" onClick={() => setZoom((z) => Math.max(0.8, +(z - 0.3).toFixed(1)))}>
          <Minus size={18} />
        </button>
        <button type="button" aria-label="กลับสู่มุมมองเริ่มต้น" onClick={() => setZoom(1)}>
          <Crosshair size={18} />
        </button>
      </div>
    </div>
  );
}
