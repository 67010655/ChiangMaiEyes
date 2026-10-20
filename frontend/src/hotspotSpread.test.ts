import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const source = readFileSync(resolve(__dirname, '../public/hotspot-spread.js'), 'utf8');
function setup() {
  const dom = new JSDOM('', { runScripts: 'outside-only' });
  const w = dom.window as any; w.eval(source);
  return { dom, S: w.CmeHotspotSpread };
}
const ring = [[99.0, 18.7], [99.01, 18.7], [99.01, 18.71], [99.0, 18.7]];
const data = {
  as_of: '2026-10-20T03:49:20Z',
  inputs: [
    { point: { latitude: 18.5, longitude: 98.5 } },
    { point: { latitude: 18.70001, longitude: 99.00001 } },
  ],
  frames: [
    { hours: 6, geometry: { features: [{ properties: { origin_index: 1 }, geometry: { type: 'Polygon', coordinates: [ring] } }] } },
    { hours: 3, geometry: { features: [{ properties: { origin_index: 1 }, geometry: { type: 'Polygon', coordinates: [ring] } }] } },
  ],
};

it('finds the model frames for the tapped point only, smallest first', () => {
  const { dom, S } = setup();
  const r = S.framesFor(data, 18.7, 99.0);
  expect(r.frames.map((f: any) => f.hours)).toEqual([3, 6]);
  expect(S.framesFor(data, 18.5, 98.5)).toBeNull(); // input exists but has no outline
  expect(S.framesFor(data, 19, 99)).toBeNull();
  dom.window.close();
});

it('grows outlines from the point and always labels them as an experiment', () => {
  const { dom, S } = setup();
  const g = S.scaleGeometry({ type: 'Polygon', coordinates: [ring] }, 99.0, 18.7, 0);
  expect(g.coordinates[0].every(([x, y]: number[]) => x === 99.0 && y === 18.7)).toBe(true);
  const text = S.caption(S.framesFor(data, 18.7, 99.0));
  expect(text).toContain('ทดลอง');
  expect(text).toContain('ถ้าจุดนี้ยังไหม้และไม่มีการดับ');
  expect(text).toContain('ยังไม่สอบเทียบ');
  dom.window.close();
});

it('offers the button only for points the model covers (last 24 hours)', () => {
  const { dom, S } = setup();
  expect(S.buttonHtml({ lat: 18.7, lon: 99, detected_at: new Date(Date.now() - 3 * 3600e3).toISOString() })).toContain('hs-spread-btn');
  expect(S.buttonHtml({ lat: 18.7, lon: 99, detected_at: new Date(Date.now() - 30 * 3600e3).toISOString() })).toBe('');
  dom.window.close();
});
