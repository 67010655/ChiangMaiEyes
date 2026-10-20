import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const src = readFileSync(resolve(__dirname, '../public/dust-sensors.js'), 'utf8');
function setup() {
  const dom = new JSDOM('<div id="top"></div>', { runScripts: 'outside-only' });
  const w = dom.window as any; w.eval(src); return { dom, w };
}
const NOW = Date.parse('2026-10-21T03:00:00Z');
const sensor = { uid: 1, name: 'farm <b>', lat: 18.4, lon: 98.65, district: 'จอมทอง', aqi_pm25: 120, time: '2026-10-21T02:30:00+00:00', fresh: true };

it('uses the US EPA AQI categories and colours, not the PCD µg/m³ scale', () => {
  const { dom, w } = setup(); const S = w.CmeDustSensors;
  expect([50, 51, 100, 101, 150, 151, 201, 301].map((v: number) => S.level(v).label)).toEqual(
    ['ดี', 'ปานกลาง', 'ปานกลาง', 'เริ่มมีผลต่อกลุ่มเสี่ยง', 'เริ่มมีผลต่อกลุ่มเสี่ยง', 'มีผลต่อสุขภาพ', 'มีผลต่อสุขภาพมาก', 'อันตราย']);
  expect(S.level(120).color).toBe('#ff7e00');
  dom.window.close();
});

it('sensor popup says AQI not µg/m³, credits WAQI and escapes names', () => {
  const { dom, w } = setup();
  const html = w.CmeDustSensors.popupHtml(sensor, { now: NOW });
  expect(html).toContain('<b>120</b> AQI');
  expect(html).toContain('ไม่ใช่ค่า µg/m³');
  expect(html).toContain('World Air Quality Index Project');
  expect(html).toContain('30 นาทีที่แล้ว');
  expect(html).toContain('farm &lt;b&gt;');
  expect(w.CmeDustSensors.popupHtml({ ...sensor, fresh: false }, { now: NOW })).toContain('ไม่นับในค่าอำเภอ');
  dom.window.close();
});

it('district line shows a median only with 2+ live sensors', () => {
  const { dom, w } = setup(); const S = w.CmeDustSensors;
  const data = { min_sensors: 2, districts: { 'หางดง': { n: 4, median: 88, level: 2 }, 'ฝาง': { n: 1, median: null, level: null } } };
  expect(S.districtHtml(data, 'หางดง')).toContain('ค่ากลางจาก 4 จุด');
  expect(S.districtHtml(data, 'หางดง')).toContain('<b>88</b> AQI');
  expect(S.districtHtml(data, 'ฝาง')).toContain('มี 1 จุด ต้องมีอย่างน้อย 2 จุด');
  expect(S.districtHtml(data, 'แม่วาง')).toContain('ไม่มี ต้องมีอย่างน้อย 2 จุด');
  dom.window.close();
});

it('loads once per 10 minutes and retries after a failure', async () => {
  const { dom, w } = setup(); const S = w.CmeDustSensors; let calls = 0;
  const ok = async () => { calls++; return { ok: true, json: async () => ({ status: 'ok', sensors: [], districts: {} }) }; };
  await S.load(ok); await S.load(ok); expect(calls).toBe(1);
  S._reset();
  await expect(S.load(async () => ({ ok: false, json: async () => ({}) }))).rejects.toThrow();
  await S.load(ok); expect(calls).toBe(2);
  dom.window.close();
});
