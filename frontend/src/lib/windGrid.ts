// Wind field builder for leaflet-velocity.
// Two sources:
//   buildWindFieldFromStation — uniform field from single AWS reading (instant fallback)
//   fetchWindGrid             — spatial grid from Open-Meteo forecast (9 sample points,
//                               bilinear-interpolated to full NX×NY) — better coverage

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

// Bounding box covering the full map viewport (CM + surrounding provinces).
const WEST = 96.0;
const EAST = 102.0;
const SOUTH = 16.0;
const NORTH = 22.0;
const STEP = 0.25;

const NX = Math.round((EAST - WEST) / STEP) + 1;   // 25
const NY = Math.round((NORTH - SOUTH) / STEP) + 1; // 25

function makeHeader(parameterNumber: number, refTime: string): VelocityField['header'] {
  return {
    parameterCategory: 2,
    parameterNumber,
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

// --- uniform field from single AWS station -----------------------------------

export function buildWindFieldFromStation(
  windSpeedKmh: number,
  windDirectionDeg: number,
  refTime: string,
): VelocityField[] {
  const speedMs = Math.max(0, Number(windSpeedKmh) || 0) / 3.6;
  const radians = ((Number(windDirectionDeg) || 0) * Math.PI) / 180;
  // Meteorological convention: direction is where wind comes FROM.
  const uValue = -speedMs * Math.sin(radians);
  const vValue = -speedMs * Math.cos(radians);
  const size = NX * NY;
  return [
    { header: makeHeader(2, refTime), data: new Array(size).fill(uValue) },
    { header: makeHeader(3, refTime), data: new Array(size).fill(vValue) },
  ];
}

// --- spatial grid from Open-Meteo (3×3 sample, bilinear interpolated) -------

// Sample points: 3 lats × 3 lons = 9 requests in one Open-Meteo batch call.
const SAMPLE_LATS = [17.5, 19.0, 20.5];  // south → north
const SAMPLE_LONS = [97.5, 99.0, 100.5]; // west  → east

function speedDirToUV(speedMs: number, dirDeg: number): [number, number] {
  const r = (dirDeg * Math.PI) / 180;
  return [-speedMs * Math.sin(r), -speedMs * Math.cos(r)];
}

function bilinear(
  grid: number[][],   // [latIdx][lonIdx], latIdx 0 = SOUTH sample
  sLats: number[],
  sLons: number[],
  lat: number,
  lon: number,
): number {
  const nLat = sLats.length;
  const nLon = sLons.length;

  // Clamp lat index
  let li = 0;
  for (let i = 0; i < nLat - 1; i++) {
    if (lat >= sLats[i]) li = i;
  }
  li = Math.min(li, nLat - 2);

  // Clamp lon index
  let lj = 0;
  for (let j = 0; j < nLon - 1; j++) {
    if (lon >= sLons[j]) lj = j;
  }
  lj = Math.min(lj, nLon - 2);

  const tx = (lon - sLons[lj]) / (sLons[lj + 1] - sLons[lj]);
  const ty = (lat - sLats[li]) / (sLats[li + 1] - sLats[li]);
  const cx = Math.max(0, Math.min(1, tx));
  const cy = Math.max(0, Math.min(1, ty));

  return (
    grid[li][lj]         * (1 - cx) * (1 - cy) +
    grid[li][lj + 1]     * cx       * (1 - cy) +
    grid[li + 1][lj]     * (1 - cx) * cy +
    grid[li + 1][lj + 1] * cx       * cy
  );
}

export async function fetchWindGrid(): Promise<VelocityField[]> {
  // Build comma-separated lat/lon pairs for 3×3 grid (row-major: lat0lon0, lat0lon1 ...)
  const latList = SAMPLE_LATS.flatMap(lat => SAMPLE_LONS.map(() => lat)).join(',');
  const lonList = SAMPLE_LATS.flatMap(() => SAMPLE_LONS).join(',');

  const url =
    `https://api.open-meteo.com/v1/forecast` +
    `?latitude=${latList}&longitude=${lonList}` +
    `&hourly=windspeed_10m,winddirection_10m` +
    `&forecast_days=1&timezone=Asia%2FBangkok`;

  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Open-Meteo wind grid: ${res.status}`);

  // Response is array of 9 objects (one per sample point), same order as input.
  const results: Array<{
    hourly: { time: string[]; windspeed_10m: number[]; winddirection_10m: number[] };
  }> = await res.json();

  if (!Array.isArray(results) || results.length !== 9) {
    throw new Error('Unexpected Open-Meteo multi-location response shape');
  }

  // Find closest hour to now (Bangkok time = UTC+7)
  const nowMs = Date.now();
  const times = results[0].hourly.time;
  let hourIdx = 0;
  let minDiff = Infinity;
  for (let i = 0; i < times.length; i++) {
    const diff = Math.abs(new Date(times[i] + '+07:00').getTime() - nowMs);
    if (diff < minDiff) { minDiff = diff; hourIdx = i; }
  }

  // Build 3×3 UV grids [latIdx][lonIdx]
  const uGrid: number[][] = SAMPLE_LATS.map(() => new Array(SAMPLE_LONS.length).fill(0));
  const vGrid: number[][] = SAMPLE_LATS.map(() => new Array(SAMPLE_LONS.length).fill(0));

  for (let li = 0; li < SAMPLE_LATS.length; li++) {
    for (let lj = 0; lj < SAMPLE_LONS.length; lj++) {
      const pIdx = li * SAMPLE_LONS.length + lj;
      const speed = (results[pIdx].hourly.windspeed_10m[hourIdx] ?? 0) / 3.6; // km/h → m/s
      const dir = results[pIdx].hourly.winddirection_10m[hourIdx] ?? 0;
      const [u, v] = speedDirToUV(speed, dir);
      uGrid[li][lj] = u;
      vGrid[li][lj] = v;
    }
  }

  const refTime = new Date().toISOString();
  const uData = new Array(NX * NY).fill(0);
  const vData = new Array(NX * NY).fill(0);

  // data[row * NX + col]: row 0 = NORTH (la1), col 0 = WEST (lo1)
  for (let row = 0; row < NY; row++) {
    const lat = NORTH - row * STEP;
    for (let col = 0; col < NX; col++) {
      const lon = WEST + col * STEP;
      uData[row * NX + col] = bilinear(uGrid, SAMPLE_LATS, SAMPLE_LONS, lat, lon);
      vData[row * NX + col] = bilinear(vGrid, SAMPLE_LATS, SAMPLE_LONS, lat, lon);
    }
  }

  return [
    { header: makeHeader(2, refTime), data: uData },
    { header: makeHeader(3, refTime), data: vData },
  ];
}
