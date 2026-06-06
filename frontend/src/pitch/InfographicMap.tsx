import { useMemo, useState } from 'react';
import districtsGeo from '../data/chiangmai-districts.json';
import {
  DISTRICT_META,
  healthBand,
  BAND_FILL,
  BAND_FILL_SOFT,
  type DistrictMeta,
} from './pitchData';

type Ring = number[][];
type Geometry = {
  type: 'Polygon' | 'MultiPolygon';
  coordinates: number[][][] | number[][][][];
};
type Feature = {
  properties: { name?: string; nameTh?: string };
  geometry: Geometry;
};

const WIDTH = 920;
const HEIGHT = 760;
const PAD = 36;

const META_BY_NAME = new Map(DISTRICT_META.map((m) => [m.name, m]));

type LayerState = {
  hotspots: boolean;
  forests: boolean;
  risk: boolean;
  activity: boolean;
};

// Collect polygon rings from a geometry.
function ringsOf(geom: Geometry): Ring[] {
  if (geom.type === 'Polygon') return geom.coordinates as Ring[];
  return (geom.coordinates as number[][][][]).flatMap((poly) => poly as Ring[]);
}

function centroidOf(rings: Ring[]): [number, number] {
  let x = 0;
  let y = 0;
  let n = 0;
  // Use the largest ring (outer boundary) for a stable centroid.
  const outer = rings.reduce((a, b) => (b.length > a.length ? b : a), rings[0]);
  for (const [lng, lat] of outer) {
    x += lng;
    y += lat;
    n += 1;
  }
  return [x / n, y / n];
}

// Deterministic pseudo-random for stable hotspot placement.
function seeded(seed: number) {
  let s = seed % 2147483647;
  if (s <= 0) s += 2147483646;
  return () => {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

export function InfographicMap({
  layers,
  selected,
  onSelect,
}: {
  layers: LayerState;
  selected: string;
  onSelect: (name: string) => void;
}) {
  const [mode, setMode] = useState<'2d' | '3d'>('3d');
  const [hover, setHover] = useState<string | null>(null);

  const { project, districts, bounds } = useMemo(() => {
    const features = (districtsGeo as { features: Feature[] }).features;
    let minLng = Infinity;
    let maxLng = -Infinity;
    let minLat = Infinity;
    let maxLat = -Infinity;
    for (const f of features) {
      for (const ring of ringsOf(f.geometry)) {
        for (const [lng, lat] of ring) {
          if (lng < minLng) minLng = lng;
          if (lng > maxLng) maxLng = lng;
          if (lat < minLat) minLat = lat;
          if (lat > maxLat) maxLat = lat;
        }
      }
    }
    const spanLng = maxLng - minLng;
    const spanLat = maxLat - minLat;
    const scale = Math.min((WIDTH - PAD * 2) / spanLng, (HEIGHT - PAD * 2) / spanLat);
    const offsetX = (WIDTH - spanLng * scale) / 2;
    const offsetY = (HEIGHT - spanLat * scale) / 2;
    const project = (lng: number, lat: number): [number, number] => [
      offsetX + (lng - minLng) * scale,
      // invert lat so north is up
      offsetY + (maxLat - lat) * scale,
    ];

    const districts = features.map((f, idx) => {
      const meta = META_BY_NAME.get(f.properties.name ?? '');
      const rings = ringsOf(f.geometry);
      const d = rings
        .map((ring) => {
          const pts = ring.map(([lng, lat]) => project(lng, lat));
          return 'M' + pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join('L') + 'Z';
        })
        .join(' ');
      const [clng, clat] = centroidOf(rings);
      const [cx, cy] = project(clng, clat);
      return { feature: f, meta, d, cx, cy, idx };
    });

    return { project, districts, bounds: { minLng, maxLng, minLat, maxLat, scale, offsetX, offsetY, maxLat2: maxLat } };
  }, []);

  // Hotspot dots scattered within bounding box, biased toward high-risk districts.
  const hotspotDots = useMemo(() => {
    const dots: { x: number; y: number }[] = [];
    districts.forEach(({ meta, cx, cy }) => {
      if (!meta) return;
      const rnd = seeded(meta.num * 97 + 13);
      const count = Math.round(meta.hotspots / 2);
      for (let i = 0; i < count; i += 1) {
        dots.push({ x: cx + (rnd() - 0.5) * 64, y: cy + (rnd() - 0.5) * 64 });
      }
    });
    return dots;
  }, [districts]);

  const selectedMeta: DistrictMeta | undefined = META_BY_NAME.get(selected);

  // 3D isometric tilt applied to the whole map group.
  const groupTransform =
    mode === '3d'
      ? `translate(${WIDTH / 2} ${HEIGHT / 2 + 10}) scale(1 0.78) rotate(-1.2) translate(${-WIDTH / 2} ${-HEIGHT / 2})`
      : '';

  const depth = mode === '3d' ? 16 : 0;

  return (
    <div className="pm-map">
      <div className="pm-map__toggle" role="group" aria-label="มุมมองแผนที่">
        <button
          type="button"
          className={mode === '2d' ? 'is-active' : ''}
          onClick={() => setMode('2d')}
        >
          2D
        </button>
        <button
          type="button"
          className={mode === '3d' ? 'is-active' : ''}
          onClick={() => setMode('3d')}
        >
          3D
        </button>
      </div>

      <svg
        className="pm-map__svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="แผนที่อินโฟกราฟิกจังหวัดเชียงใหม่ แสดงคะแนนสุขภาพป่าและจุดความร้อนรายอำเภอ"
      >
        <defs>
          <filter id="pm-soft" x="-20%" y="-20%" width="140%" height="140%">
            <feDropShadow dx="0" dy="6" stdDeviation="10" floodColor="#1d3a2a" floodOpacity="0.18" />
          </filter>
          <radialGradient id="pm-terrain" cx="42%" cy="34%" r="80%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.5" />
            <stop offset="55%" stopColor="#ffffff" stopOpacity="0.06" />
            <stop offset="100%" stopColor="#1d3a2a" stopOpacity="0.1" />
          </radialGradient>
          <pattern id="pm-hill" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(35)">
            <line x1="0" y1="0" x2="0" y2="7" stroke="#1d3a2a" strokeWidth="0.6" strokeOpacity="0.06" />
          </pattern>
        </defs>

        <g transform={groupTransform}>
          {/* extrusion side walls for 3D depth */}
          {depth > 0 &&
            districts.map(({ d, idx }) => (
              <path
                key={`depth-${idx}`}
                d={d}
                transform={`translate(0 ${depth})`}
                fill="#2c4a37"
                opacity={0.55}
              />
            ))}

          {/* district top faces */}
          {districts.map(({ feature, meta, d, idx, cx, cy }) => {
            const name = feature.properties.name ?? `d-${idx}`;
            const band = meta ? healthBand(meta.health) : 'green';
            const isSel = name === selected;
            const isHover = name === hover;
            const baseFill = mode === '3d' ? BAND_FILL_SOFT[band] : BAND_FILL[band];
            return (
              <g key={`face-${idx}`}>
                <path
                  d={d}
                  fill={baseFill}
                  stroke={isSel ? '#10231d' : '#f3f6ef'}
                  strokeWidth={isSel ? 2.4 : 1.1}
                  opacity={isHover && !isSel ? 0.92 : 1}
                  style={{ cursor: 'pointer', transition: 'opacity 0.15s ease' }}
                  onClick={() => onSelect(name)}
                  onMouseEnter={() => setHover(name)}
                  onMouseLeave={() => setHover(null)}
                />
                {/* terrain sheen + hillshade only on faces */}
                <path d={d} fill="url(#pm-terrain)" pointerEvents="none" />
                <path d={d} fill="url(#pm-hill)" pointerEvents="none" />
                {isSel && (
                  <path d={d} fill="none" stroke="#10231d" strokeWidth={2.6} pointerEvents="none" />
                )}
              </g>
            );
          })}

          {/* risk zone rings */}
          {layers.risk &&
            districts.map(({ meta, cx, cy, idx }) => {
              if (!meta || healthBand(meta.health) === 'green' || healthBand(meta.health) === 'yellow')
                return null;
              return (
                <circle
                  key={`risk-${idx}`}
                  cx={cx}
                  cy={cy}
                  r={30}
                  fill="none"
                  stroke="#c2603f"
                  strokeWidth={1.4}
                  strokeDasharray="3 4"
                  opacity={0.7}
                  pointerEvents="none"
                />
              );
            })}

          {/* hotspot dots */}
          {layers.hotspots &&
            hotspotDots.map((dot, i) => (
              <g key={`hs-${i}`} pointerEvents="none">
                <circle cx={dot.x} cy={dot.y} r={6} fill="#c2603f" opacity={0.18} />
                <circle cx={dot.x} cy={dot.y} r={2.6} fill="#c2603f" stroke="#fff" strokeWidth={0.8} />
              </g>
            ))}

          {/* number badges */}
          {districts.map(({ meta, cx, cy, idx }) => {
            if (!meta) return null;
            return (
              <g key={`badge-${idx}`} pointerEvents="none">
                <circle cx={cx} cy={cy} r={12} fill="#10231d" opacity={0.92} />
                <text
                  x={cx}
                  y={cy + 4}
                  textAnchor="middle"
                  fontSize={12}
                  fontWeight={700}
                  fill="#ffffff"
                >
                  {meta.num}
                </text>
                <text
                  x={cx}
                  y={cy + 26}
                  textAnchor="middle"
                  fontSize={11}
                  fontWeight={600}
                  fill="#10231d"
                  stroke="#f3f6ef"
                  strokeWidth={2.6}
                  paintOrder="stroke"
                >
                  {meta.label}
                </text>
              </g>
            );
          })}

          {/* community forest markers */}
          {layers.forests &&
            districts
              .filter(({ meta }) => meta && meta.forests > 30)
              .map(({ cx, cy, idx }) => (
                <g key={`forest-${idx}`} transform={`translate(${cx + 22} ${cy - 18})`} pointerEvents="none">
                  <rect x={-9} y={-9} width={18} height={18} rx={5} fill="#0f6b54" />
                  <path
                    d="M0,-4 L4,3 L-4,3 Z M0,0 L5,6 L-5,6 Z"
                    fill="#ffffff"
                    transform="translate(0 -1) scale(0.62)"
                  />
                </g>
              ))}
        </g>

        {/* compass */}
        <g transform={`translate(${WIDTH - 56} ${HEIGHT - 64})`} opacity={0.8}>
          <circle r={22} fill="none" stroke="#10231d" strokeWidth={1.2} opacity={0.4} />
          <path d="M0,-18 L5,4 L0,-1 L-5,4 Z" fill="#c2603f" />
          <text x={0} y={-26} textAnchor="middle" fontSize={11} fontWeight={700} fill="#10231d">
            N
          </text>
        </g>
      </svg>

      <div className="pm-map__scale" aria-hidden="true">
        <span className="pm-map__scale-bar" />
        <span>0</span>
        <span>25</span>
        <span>50 km</span>
      </div>

      <ul className="pm-map__legend" aria-label="คำอธิบายคะแนนสุขภาพป่า">
        <li><span className="pm-dot" style={{ background: BAND_FILL.green }} />Green 76–100</li>
        <li><span className="pm-dot" style={{ background: BAND_FILL.yellow }} />Yellow 41–75</li>
        <li><span className="pm-dot" style={{ background: BAND_FILL.orange }} />Orange 21–40</li>
        <li><span className="pm-dot" style={{ background: BAND_FILL.red }} />Red 0–20</li>
        <li><span className="pm-dot pm-dot--hot" />Hotspot</li>
      </ul>
    </div>
  );
}
