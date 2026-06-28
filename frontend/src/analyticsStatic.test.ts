import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const html = readFileSync(resolve(__dirname, '..', 'index.html'), 'utf8');
const tambonGeojsonPath = resolve(__dirname, '..', 'public', 'chiangmai-tambons.geojson');
const tambonMetaPath = resolve(__dirname, '..', 'public', 'chiangmai-tambons.meta.json');

describe('production analytics inline dashboard', () => {
  it('uses explicit satellite normalization instead of substring buckets', () => {
    expect(html).toContain('function normalizeSatelliteProduct');
    expect(html).toContain('function sourceProductRows');
    expect(html).toContain("N20");
    expect(html).toContain("NOAA-20 VIIRS");
    expect(html).not.toContain("const viirs=hotspots.filter(h=>(h.sat||'').includes('VIIRS')).length");
  });

  it('does not keep synthetic hourly hotspot bell curve in production analytics', () => {
    expect(html).not.toContain('let hourly=Array.from');
    expect(html).toContain('function hourlyBucketsFromHotspots');
  });

  it('routes analytics history windows through backend days query', () => {
    expect(html).toContain("/api/history?days=7");
    expect(html).toContain("/api/history?days=30");
    expect(html).not.toContain("fetchJson('/api/history', 60000)");
  });

  it('uses API provenance labels and avoids CAMS hardcode for PM2.5 panels', () => {
    expect(html).not.toContain('PM2.5 — 24h (CAMS)');
    expect(html).toContain('sourceLabel');
  });

  it('defines critical FRP once and reuses it across analytics and report surfaces', () => {
    expect(html).toContain('const CRITICAL_FRP_MW = 100');
    expect(html).not.toContain('h.frp>90');
  });

  it('builds district analytics from the 25-district list, not fire-phase six-card subset', () => {
    expect(html).toContain('function districtRowsFromHotspots');
    expect(html).not.toContain("livePhases.map(p=>({name:p.district,v:p.active_hotspots})");
  });

  it('wires real tambon polygons instead of leaving subdistrict analytics unavailable', () => {
    expect(existsSync(tambonGeojsonPath)).toBe(true);
    expect(existsSync(tambonMetaPath)).toBe(true);
    expect(html).toContain('/chiangmai-tambons.geojson');
    expect(html).toContain('function loadTambonBoundaries');
    expect(html).toContain('function tambonForPoint');
    expect(html).toContain('tambonSourceMeta');
  });
});
