import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const source = readFileSync(resolve(__dirname, '../public/three-d-extras.js'), 'utf8');
const html = readFileSync(resolve(__dirname, '../index.html'), 'utf8');
function load() { const dom = new JSDOM('', { runScripts: 'outside-only' }); (dom.window as any).eval(source); return dom; }

it('places a district label inside the largest part of the outline', () => {
  const dom = load(); const X = (dom.window as any).CmeThreeDExtras;
  const square = (x: number, y: number, s: number) => [[x, y], [x + s, y], [x + s, y + s], [x, y + s], [x, y]];
  const [lon, lat] = X.labelPoint({ type: 'MultiPolygon', coordinates: [[square(98, 18, 0.1)], [square(99, 19, 1)]] });
  expect(lon).toBeCloseTo(99.5, 5); expect(lat).toBeCloseTo(19.5, 5);
  dom.window.close();
});

it('reads wind from the same grid format as the 2D streamlines, and nothing outside it', () => {
  const dom = load(); const X = (dom.window as any).CmeThreeDExtras;
  const header = { nx: 2, ny: 2, lo1: 98, la1: 20, dx: 1, dy: 1 };
  // rows from north to south, west to east
  const field = [{ header, data: [1, 3, 1, 3] }, { header, data: [0, 0, -2, -2] }];
  const s = X.sampler(field);
  expect(s(98.5, 19.5)).toEqual([2, -1]);
  expect(s(97, 19.5)).toBeNull();
  expect(X.sampler(null)).toBeNull();
  dom.window.close();
});

it('public popups no longer show the experimental 0-100 score (D2) and cameras are gone (D1)', () => {
  const forest = html.slice(html.indexOf('function forestPopupHtml('), html.indexOf('function openForestDetails('));
  expect(forest).not.toContain('/100'); expect(forest).not.toContain('experimentalScore');
  expect(html).not.toContain('data-layer="burnScar"');
  expect(html).not.toContain('คะแนนความเสี่ยง (ประมาณ)');
  expect(html).not.toContain('id="cameraview"');
  expect(html).not.toContain('/api/public-cameras');
});
