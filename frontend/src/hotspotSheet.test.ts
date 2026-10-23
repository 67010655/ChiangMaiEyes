import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const evidence = readFileSync(resolve(__dirname, '../public/decision-support.js'), 'utf8');
const source = readFileSync(resolve(__dirname, '../public/hotspot-sheet.js'), 'utf8');
function setup() {
  const dom = new JSDOM('<button id="opener">x</button>', { runScripts: 'outside-only' });
  const w = dom.window as any; w.requestAnimationFrame = (f: any) => f(); w.eval(evidence); w.eval(source);
  return { dom, w, S: w.CmeHotspotSheet };
}

it('converts WGS84 to UTM 47N within a metre of a published reading', () => {
  const { dom, S } = setup();
  const u = S.utm(17.54624, 99.74458);
  expect(u.zone).toBe(47); expect(u.hemisphere).toBe('N');
  expect(Math.abs(u.easting - 579024)).toBeLessThanOrEqual(1);
  expect(Math.abs(u.northing - 1940140)).toBeLessThanOrEqual(1);
  expect(S.utm(NaN, 99)).toBeNull(); dom.window.close();
});

it('opens with the place as title, copyable coordinates, and closes back to the opener', () => {
  const { dom, w, S } = setup(); let closed = 0;
  const opener = w.document.getElementById('opener'); opener.focus();
  S.open({ lat: 18.8, lon: 98.9, district: 'แม่ริม', subdistrict: 'ริมใต้', sat: 'VIIRS', detected_at: '2026-10-19T07:14:00Z' }, '<div class="hs-pop">x</div>', { onClose: () => closed++ });
  const sheet = w.document.getElementById('hotspotSheet');
  expect(sheet.hidden).toBe(false);
  expect(w.document.getElementById('hotspotSheetTitle').textContent).toBe('ต.ริมใต้ อ.แม่ริม');
  expect([...sheet.querySelectorAll('[data-copy]')].map((b: any) => b.dataset.copy)).toEqual(['18.80000, 98.90000', expect.stringMatching(/^47N E \d{3},\d{3} N \d,\d{3},\d{3}$/)]);
  sheet.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  expect(sheet.hidden).toBe(true); expect(closed).toBe(1); expect(w.document.activeElement).toBe(opener);
  dom.window.close();
});

it('names the satellite whether FIRMS sends a code or the full name', () => {
  const { dom, w, S } = setup();
  const sat = (code: string) => {
    S.open({ lat: 18.8, lon: 98.9, sat: code, detected_at: '2026-10-19T07:14:00Z' }, '<div class="hs-pop">x</div>', {});
    return w.document.getElementById('hotspotSheet').textContent;
  };
  expect(sat('Aqua')).toContain('Aqua (MODIS)');
  expect(sat('T')).toContain('Terra (MODIS)');
  expect(sat('N')).toContain('Suomi NPP (VIIRS)');
  dom.window.close();
});
