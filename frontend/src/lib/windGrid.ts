// Builds a Windy-style wind grid for leaflet-velocity from the TMD AWS station
// reading. TMD exposes a single current wind observation for Chiang Mai, so the
// visual layer uses a uniform field instead of mixing in another weather source.

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
// This ensures wind particles fill the entire visible map, not just a small
// rectangle focused on Chiang Mai city.
const WEST = 96.0;
const EAST = 102.0;
const SOUTH = 16.0;
const NORTH = 22.0;
const STEP = 0.25;

const NX = Math.round((EAST - WEST) / STEP) + 1;
const NY = Math.round((NORTH - SOUTH) / STEP) + 1;

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

export function buildWindFieldFromStation(windSpeedKmh: number, windDirectionDeg: number, refTime: string): VelocityField[] {
  const speedMs = Math.max(0, Number(windSpeedKmh) || 0) / 3.6;
  const radians = ((Number(windDirectionDeg) || 0) * Math.PI) / 180;
  // Meteorological convention: direction is where wind comes from.
  const uValue = -speedMs * Math.sin(radians);
  const vValue = -speedMs * Math.cos(radians);
  const size = NX * NY;

  return [
    { header: makeHeader(2, refTime), data: new Array(size).fill(uValue) },
    { header: makeHeader(3, refTime), data: new Array(size).fill(vValue) },
  ];
}
