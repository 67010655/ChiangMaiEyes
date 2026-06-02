// Builds a Windy-style wind grid for leaflet-velocity from Open-Meteo.
//
// leaflet-velocity wants two GRIB-style objects ([U, V]) whose `data` arrays
// are row-major starting at the NW corner (la1/lo1), going east then south.
// Open-Meteo's multi-point endpoint returns results in the same order we send
// the coordinates, so we generate the grid in exactly that order.

export type VelocityField = {
  header: {
    parameterCategory: number;
    parameterNumber: number;
    parameterUnit: string;
    nx: number;
    ny: number;
    lo1: number;
    la1: number;
    lo2: number;
    la2: number;
    dx: number;
    dy: number;
    refTime: string;
    scanMode: number;
  };
  data: number[];
};

// Bounding box over Chiang Mai + immediate surroundings.
const WEST = 97.5;
const EAST = 100.0;
const SOUTH = 17.0;
const NORTH = 20.5;
const STEP = 0.25; // ~27 km cells — coarse is fine, the layer interpolates

const NX = Math.round((EAST - WEST) / STEP) + 1; // west → east
const NY = Math.round((NORTH - SOUTH) / STEP) + 1; // north → south

function makeHeader(parameterNumber: number, refTime: string): VelocityField['header'] {
  return {
    parameterCategory: 2, // Momentum
    parameterNumber, // 2 = U-component, 3 = V-component
    parameterUnit: 'm.s-1',
    nx: NX,
    ny: NY,
    lo1: WEST,
    la1: NORTH,
    lo2: EAST,
    la2: SOUTH,
    dx: STEP,
    dy: STEP,
    refTime,
    scanMode: 0,
  };
}

/**
 * Fetch current 10 m wind across the grid and return [U, V] velocity fields.
 * Throws on network/shape errors so the caller can fall back.
 */
export async function fetchWindField(signal?: AbortSignal): Promise<VelocityField[]> {
  const lats: number[] = [];
  const lons: number[] = [];
  // Row-major from the NW corner: north → south, west → east.
  for (let iy = 0; iy < NY; iy++) {
    const lat = NORTH - iy * STEP;
    for (let ix = 0; ix < NX; ix++) {
      lats.push(Number((lat).toFixed(4)));
      lons.push(Number((WEST + ix * STEP).toFixed(4)));
    }
  }

  const url =
    `https://api.open-meteo.com/v1/forecast` +
    `?latitude=${lats.join(',')}` +
    `&longitude=${lons.join(',')}` +
    `&current=wind_speed_10m,wind_direction_10m` +
    `&wind_speed_unit=ms`;

  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`Open-Meteo wind grid failed: ${res.status}`);
  const json = await res.json();
  const points: any[] = Array.isArray(json) ? json : [json];
  if (points.length !== NX * NY) {
    throw new Error(`wind grid size mismatch: got ${points.length}, expected ${NX * NY}`);
  }

  const u: number[] = new Array(points.length);
  const v: number[] = new Array(points.length);
  for (let i = 0; i < points.length; i++) {
    const cur = points[i]?.current ?? {};
    const spd = Number(cur.wind_speed_10m) || 0; // m/s
    const dirDeg = Number(cur.wind_direction_10m) || 0; // meteorological: FROM
    const rad = (dirDeg * Math.PI) / 180;
    // Met convention → vector the wind blows TOWARD.
    u[i] = -spd * Math.sin(rad);
    v[i] = -spd * Math.cos(rad);
  }

  const refTime = new Date().toISOString();
  return [
    { header: makeHeader(2, refTime), data: u },
    { header: makeHeader(3, refTime), data: v },
  ];
}
