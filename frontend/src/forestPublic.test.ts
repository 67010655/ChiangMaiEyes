import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const pub = (f: string) => readFileSync(resolve(__dirname, '../public', f), 'utf8');
function setup() {
  const dom = new JSDOM('<div id="top"></div>', { url: 'https://fixture.example/', runScripts: 'outside-only' });
  const w = dom.window as any;
  w.eval(pub('decision-support.js')); w.eval(pub('dust-sensors.js')); w.eval(pub('forest-public.js'));
  return { dom, w };
}
const NOW = Date.parse('2026-10-21T03:00:00Z');
const square = (x: number, y: number, d = 0.02) => ({ type: 'Polygon', coordinates: [[[x, y], [x + d, y], [x + d, y + d], [x, y + d], [x, y]]] });
const A = { forest_id: 'A', name: 'ป่า <b>A</b>', amphoe: 'ฝาง', latitude: 19.91, longitude: 99.21, area_rai: 1200, boundary: square(99.2, 19.9) };
const B = { forest_id: 'B', name: 'ป่า B', amphoe: 'ฮอด', latitude: 18.21, longitude: 98.61, boundary: square(98.6, 18.2) };
const ago = (m: number) => new Date(NOW - m * 6e4).toISOString();
const live = { source_mode: 'LIVE', is_stale: false, latest_update: ago(5) };
const dash = (items: any[], wind: any = { wind_direction_deg: 270, wind_speed_kmh: 8, source: 'fixture' }) =>
  ({ data_quality: { hotspots: live, weather: live }, hotspots: { items }, weather: wind });
const hs = (lat: number, lon: number, m: number) => ({ latitude: lat, longitude: lon, detected_at: ago(m) });

it('status: in the forest, around it within 5 km, or neither', () => {
  const { dom, w } = setup(); const P = w.CmeForestPublic;
  expect(P.situation(A, dash([hs(19.91, 99.21, 30)]), NOW)).toMatchObject({ status: 'alert', inside: 1, near: 0 });
  expect(P.situation(A, dash([hs(19.91, 99.25, 30)]), NOW)).toMatchObject({ status: 'watch', inside: 0, near: 1 });
  expect(P.situation(A, dash([hs(19.91, 99.40, 30)]), NOW)).toMatchObject({ status: 'calm' });
  expect(P.situation(A, dash([hs(19.91, 99.21, 60 * 30)]), NOW)).toMatchObject({ status: 'calm' });
  const stale = { ...dash([]), data_quality: { hotspots: { ...live, is_stale: true } } };
  expect(P.situation(A, stale, NOW).status).toBe('unknown');
  dom.window.close();
});

it('says whether the wind blows from the nearest outside hotspot toward the forest', () => {
  const { dom, w } = setup(); const P = w.CmeForestPublic;
  // Hotspot west of the forest; wind FROM the west (270°) blows east, toward the forest.
  expect(P.situation(A, dash([hs(19.91, 99.17, 30)]), NOW).wind).toMatchObject({ toward: true, dir: 'ตะวันออก', kmh: 8 });
  expect(P.situation(A, dash([hs(19.91, 99.17, 30)], { wind_direction_deg: 90, wind_speed_kmh: 5 }), NOW).wind.toward).toBe(false);
  expect(P.situation(A, dash([]), NOW).wind.toward).toBe(null);
  dom.window.close();
});

it('lists forests near hotspots by latest detection, never as a ranking', () => {
  const { dom, w } = setup(); const P = w.CmeForestPublic;
  const rows = P.forestsNearHotspots([A, B], dash([hs(19.91, 99.21, 300), hs(18.21, 98.61, 20)]), NOW);
  expect(rows.map((r: any) => r.forest.forest_id)).toEqual(['B', 'A']);
  const html = P.listHtml(rows, 'A');
  expect(html).toContain('ไม่ใช่การจัดอันดับ');
  expect(html).toContain('ป่า &lt;b&gt;A&lt;/b&gt;');
  expect(P.listHtml([], '')).toContain('การไม่พบจุดไม่ได้ยืนยันว่าไม่มีไฟ');
  dom.window.close();
});

it('forest card escapes names, labels sources and draws the map', () => {
  const { dom, w } = setup(); const P = w.CmeForestPublic;
  const html = P.forestCard(A, dash([hs(19.91, 99.25, 30)]), NOW);
  expect(html).not.toContain('<b>A</b>');
  expect(html).toContain('ลมอ้างอิงระดับจังหวัด ไม่ใช่ลมที่วัดในป่านี้');
  expect(html).toContain('RECOFTC');
  expect(html).toContain('tel:1362');
  expect(html).toMatch(/<circle[^>]*class="near"/);
  dom.window.close();
});

it('dust: nearest live sensor within 15 km in AQI, not µg/m³', () => {
  const { dom, w } = setup(); const P = w.CmeForestPublic;
  const data = { sensors: [{ uid: 1, name: 's', lat: 19.95, lon: 99.21, aqi_pm25: 120, time: ago(30), fresh: true },
    { uid: 2, name: 'old', lat: 19.91, lon: 99.21, aqi_pm25: 300, time: ago(400), fresh: false }] };
  expect(P.nearestSensor(A, data).s.uid).toBe(1);
  expect(P.dustHtml(A, data)).toContain('120 AQI');
  expect(P.dustHtml(A, data)).toContain('ไม่ใช่ µg/m³');
  expect(P.dustHtml(B, data)).toContain('ไม่มีเซนเซอร์ในระยะ 15 กม.');
  dom.window.close();
});

it('fire weather line is today at the forest point, with the not-a-fire-forecast note', () => {
  const { dom, w } = setup();
  w.CmeFireWeather = { CLASSES: [{ label: 'ต่ำมาก', color: '#38bdf8' }, { label: 'ต่ำ' }, { label: 'ปานกลาง' }, { label: 'สูง' }], classOf: (v: number) => v < 5 ? 0 : v < 11 ? 1 : v < 21 ? 2 : 3 };
  const days = [{ date: '2026-10-21', fwi: 4.8 }, { date: '2026-10-22', fwi: 25 }, { date: '2026-10-23', fwi: 30 }];
  const html = w.CmeForestPublic.fwiHtml(days, '2026-10-21');
  expect(html).toContain('ต่ำมาก');
  expect(html).toContain('7 วันข้างหน้ามี 2 วันระดับสูงขึ้นไป');
  expect(html).toContain('ไม่ใช่การพยากรณ์ว่าไฟจะเกิดที่ไหน');
  dom.window.close();
});
