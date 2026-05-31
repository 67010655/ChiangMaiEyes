import { useState } from 'react';
import { Crosshair, Minus, Plus } from 'lucide-react';
import type { DashboardResponse } from '../lib/types';

type Props = {
  dashboard: DashboardResponse;
  layers: {
    hotspots: boolean;
    pm25: boolean;
    wind: boolean;
  };
};

// Simplified province outline for the stylized map. Production can replace this
// with OSM relation 1908771 or an official Thai administrative GeoJSON source.
const chiangMaiProvinceBoundary: [number, number][] = [
  [20.15, 98.78],
  [20.08, 99.14],
  [19.88, 99.42],
  [19.52, 99.54],
  [19.22, 99.34],
  [18.98, 99.47],
  [18.63, 99.34],
  [18.3, 99.35],
  [17.92, 99.2],
  [17.55, 98.96],
  [17.43, 98.62],
  [17.56, 98.28],
  [17.84, 97.96],
  [18.07, 97.58],
  [18.42, 97.38],
  [18.72, 97.5],
  [18.98, 97.74],
  [19.34, 97.76],
  [19.62, 98.02],
  [19.94, 98.26],
  [20.15, 98.78],
];

const neighbours: { label: string; lat: number; lng: number }[] = [
  { label: 'เชียงราย', lat: 19.95, lng: 99.72 },
  { label: 'แม่ฮ่องสอน', lat: 18.52, lng: 97.18 },
  { label: 'ลำพูน', lat: 18.0, lng: 99.0 },
  { label: 'ลำปาง', lat: 18.28, lng: 99.66 },
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

const COS_LAT = Math.cos((18.85 * Math.PI) / 180);
const PROJ = 1000;

function project(lat: number, lng: number) {
  return { x: lng * COS_LAT * PROJ, y: -lat * PROJ };
}

const boundaryPts = chiangMaiProvinceBoundary.map(([lat, lng]) => project(lat, lng));
const xs = boundaryPts.map((p) => p.x);
const ys = boundaryPts.map((p) => p.y);
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
const viewBox = `${viewMinX} ${viewMinY} ${viewW} ${viewH}`;
const cx = viewMinX + viewW / 2;
const cy = viewMinY + viewH / 2;

const boundaryPath = boundaryPts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x} ${p.y}`).join(' ') + ' Z';

const STATION_R = viewW * 0.02;
const HOTSPOT_R = viewW * 0.012;
const VALUE_FONT = viewW * 0.022;
const NEIGHBOUR_FONT = viewW * 0.026;
const CENTER_FONT = viewW * 0.05;

function pm25Color(pm25: number) {
  if (pm25 <= 25) return '#16a34a';
  if (pm25 <= 37) return '#eab308';
  if (pm25 <= 50) return '#f97316';
  if (pm25 <= 90) return '#dc2626';
  return '#7c3aed';
}

export function DashboardMap({ dashboard, layers }: Props) {
  const [zoom, setZoom] = useState(1);

  const windRotation = dashboard.weather.wind_direction_deg + 180;
  const arrowSize = viewW * 0.024;

  const cityCenter = project(18.98, 98.6);

  return (
    <div className="map-canvas">
      <svg viewBox={viewBox} role="img" aria-label="แผนที่จังหวัดเชียงใหม่" preserveAspectRatio="xMidYMid meet">
        <defs>
          <radialGradient id="terrain" cx="42%" cy="38%" r="80%">
            <stop offset="0%" stopColor="#f4faf5" />
            <stop offset="100%" stopColor="#e7f0ea" />
          </radialGradient>
          <linearGradient id="province" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#d7eede" />
            <stop offset="100%" stopColor="#c2e6cf" />
          </linearGradient>
          <filter id="soft" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy={viewW * 0.004} stdDeviation={viewW * 0.004} floodColor="#1f4d3a" floodOpacity="0.18" />
          </filter>
        </defs>

        <rect x={viewMinX} y={viewMinY} width={viewW} height={viewH} fill="url(#terrain)" />

        <g
          transform={`translate(${cx} ${cy}) scale(${zoom}) translate(${-cx} ${-cy})`}
          style={{ transition: 'transform 0.25s ease' }}
        >
          {/* province halo + fill */}
          <path d={boundaryPath} fill="none" stroke="#0f6b54" strokeWidth={viewW * 0.012} strokeOpacity="0.12" />
          <path
            d={boundaryPath}
            fill="url(#province)"
            stroke="#0f6b54"
            strokeWidth={viewW * 0.0045}
            strokeDasharray={`${viewW * 0.012} ${viewW * 0.009}`}
            strokeLinejoin="round"
          />

          {neighbours.map((n) => {
            const p = project(n.lat, n.lng);
            return (
              <text
                key={n.label}
                x={p.x}
                y={p.y}
                fontSize={NEIGHBOUR_FONT}
                fill="#7c8d84"
                fontWeight={600}
                textAnchor="middle"
              >
                {n.label}
              </text>
            );
          })}

          {/* central province label */}
          <text
            x={cityCenter.x}
            y={cityCenter.y - viewW * 0.07}
            fontSize={CENTER_FONT}
            fill="#3f5a4e"
            fontWeight={700}
            textAnchor="middle"
            opacity="0.55"
          >
            เชียงใหม่
          </text>

          {layers.wind &&
            windPositions.map(([lat, lng]) => {
              const p = project(lat, lng);
              return (
                <g key={`${lat}-${lng}`} transform={`translate(${p.x} ${p.y}) rotate(${windRotation})`}>
                  <path
                    d={`M0 ${-arrowSize} L${arrowSize * 0.4} ${-arrowSize * 0.1} L${arrowSize * 0.16} ${-arrowSize * 0.1} L${arrowSize * 0.16} ${arrowSize} L${-arrowSize * 0.16} ${arrowSize} L${-arrowSize * 0.16} ${-arrowSize * 0.1} L${-arrowSize * 0.4} ${-arrowSize * 0.1} Z`}
                    fill="#3b82f6"
                    opacity="0.85"
                  />
                </g>
              );
            })}

          {layers.hotspots &&
            dashboard.hotspots.items.map((h) => {
              const p = project(h.latitude, h.longitude);
              return <circle key={h.id} cx={p.x} cy={p.y} r={HOTSPOT_R} fill="#ef4444" stroke="#fff" strokeWidth={viewW * 0.002} />;
            })}

          {layers.pm25 && (
            <g>
              {/* aggregate marker */}
              <g filter="url(#soft)">
                <circle cx={cityCenter.x} cy={cityCenter.y} r={STATION_R * 1.7} fill="#16a34a" stroke="#fff" strokeWidth={viewW * 0.004} />
                <text
                  x={cityCenter.x}
                  y={cityCenter.y + VALUE_FONT * 0.36}
                  fontSize={VALUE_FONT * 1.15}
                  fill="#fff"
                  fontWeight={700}
                  textAnchor="middle"
                >
                  {dashboard.pm25.current_pm25}
                </text>
              </g>

              {dashboard.pm25.stations.map((s) => {
                const p = project(s.latitude, s.longitude);
                return (
                  <g key={s.id} filter="url(#soft)">
                    <circle cx={p.x} cy={p.y} r={STATION_R} fill={pm25Color(s.pm25)} stroke="#fff" strokeWidth={viewW * 0.003} />
                    <text
                      x={p.x}
                      y={p.y - STATION_R - VALUE_FONT * 0.35}
                      fontSize={VALUE_FONT}
                      fill="#143b2d"
                      fontWeight={700}
                      textAnchor="middle"
                    >
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
        <button type="button" aria-label="ขยาย" onClick={() => setZoom((z) => Math.min(2.4, +(z + 0.25).toFixed(2)))}>
          <Plus size={18} />
        </button>
        <button type="button" aria-label="ย่อ" onClick={() => setZoom((z) => Math.max(0.8, +(z - 0.25).toFixed(2)))}>
          <Minus size={18} />
        </button>
        <button type="button" aria-label="กลับสู่มุมมองเริ่มต้น" onClick={() => setZoom(1)}>
          <Crosshair size={18} />
        </button>
      </div>
    </div>
  );
}
