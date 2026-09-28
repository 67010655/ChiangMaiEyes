import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const rootVercel = readFileSync(resolve(__dirname, '..', '..', 'vercel.json'), 'utf8');
const html = readFileSync(resolve(__dirname, '..', 'index.html'), 'utf8');
const productionDoc = readFileSync(resolve(__dirname, '..', '..', 'docs', 'PRODUCTION_FRONTEND.md'), 'utf8');
const boundaries = JSON.parse(readFileSync(resolve(__dirname, '..', '..', 'backend', 'app', 'data', 'community-forests-chiangmai.geojson'), 'utf8'));
const reactForests = JSON.parse(readFileSync(resolve(__dirname, 'data', 'community-forests-official.json'), 'utf8'));

describe('production deployment contract', () => {
  it('uses the boundary shapefile as the only community forest count', () => {
    const sourceIds = boundaries.features.map((feature: { properties: { id: string } }) => feature.properties.id);
    const reactIds = reactForests.forests.map((forest: { id: string }) => forest.id);
    expect(sourceIds.length).toBe(677);
    expect(reactForests.summary.recordCount).toBe(sourceIds.length);
    expect(reactIds).toEqual(sourceIds);
    expect(reactForests.forests.every((forest: { boundary: { type: string } }) =>
      ['Polygon', 'MultiPolygon'].includes(forest.boundary.type))).toBe(true);
    expect(html).toContain("fetchJson('/api/community-forests'");
  });
  it('keeps GitHub push deployments enabled for the frontend project', () => {
    expect(rootVercel).not.toContain('"deploymentEnabled": false');
  });

  it('documents that production currently boots the inline dashboard entry', () => {
    expect(html).toContain('PRODUCTION_ENTRY: inline-dashboard');
    expect(productionDoc).toContain('Production currently boots from `frontend/index.html`');
    expect(html).not.toContain('<script type="module" src="/src/main.tsx"></script>');
  });

  it('uses current provider names in visible data-source labels', () => {
    expect(html).toContain('Open-Meteo');
    expect(html).not.toContain('OpenWeather');
  });

  it('keeps critical Thai metadata readable instead of mojibake', () => {
    expect(html).toContain('ศูนย์เฝ้าระวังไฟป่า');
    expect(html).toContain('จังหวัดเชียงใหม่');
    expect(html.slice(0, 2500)).not.toContain('เธ');
  });

  it('preserves production report history, forest proximity, and tablet controls', () => {
    expect(html).toContain('myReportsModalBackdrop');
    expect(html).toContain('showForestProximity(');
    expect(html).toContain('show3DForestProximity(');
    expect(html).toContain('tabletInsightsBtn');
    expect(html).not.toContain('basemaps.cartocdn.com');
  });
});
