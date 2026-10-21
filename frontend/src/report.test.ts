import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const pub = (f: string) => readFileSync(resolve(__dirname, '../public', f), 'utf8');
function setup() {
  const dom = new JSDOM('<div id="paper"></div>', { runScripts: 'outside-only' });
  const w = dom.window as any; w.eval(pub('public-guidance.js')); w.eval(pub('report.js'));
  return { dom, w };
}
const now = Date.parse('2026-10-21T12:00:00+07:00');
const rows = [
  { id: 'a', lat: 19.9, lon: 99.2, detected_at: '2026-10-21T10:00:00+07:00', district: 'ฝาง', tambon: 'เวียง' },
  { id: 'b', lat: 19.91, lon: 99.21, detected_at: '2026-10-20T14:00:00+07:00', district: 'ฝาง', tambon: 'เวียง' },
  { id: 'c', lat: 18.5, lon: 98.6, detected_at: '2026-10-19T14:00:00+07:00', district: 'ฮอด', tambon: 'หางดง' },
];
const shapes = [{ name: 'ฝาง', rings: [[[99.1, 19.8], [99.3, 19.8], [99.3, 20], [99.1, 20], [99.1, 19.8]]] },
  { name: 'ฮอด', rings: [[[98.5, 18.4], [98.7, 18.4], [98.7, 18.6], [98.5, 18.6], [98.5, 18.4]]] }];

it('reads as a report: summary with fire and dust on separate lines, numbered sections, map, areas, contacts, sources', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('paper');
  const level = w.CmePublicGuidance.pmLevel(42);
  el.innerHTML = w.CmeReport.html({ scope: 'province', name: 'จังหวัดเชียงใหม่', hours: 72, rows, now, air: true, shapes,
    pm: { value: 42, stations: 2, level }, wind: { dir: 'ใต้', kmh: 6 },
    sources: [{ what: 'จุดความร้อน', label: 'NASA FIRMS', time: '21 ต.ค. 11:00 น.' }],
    contact: { name: 'สำนักจัดการทรัพยากรป่าไม้ที่ 1', phone: '052-081758', checked: '2026-10-09' }, showMap: true, showTable: false });
  const lines = [...el.querySelectorAll('.rp-summary p')].map((p: any) => p.textContent);
  expect(lines[0]).toContain('ตรวจพบจุดความร้อน 3 จุด'); expect(lines[0]).toContain('อ.ฝาง 2 จุด'); expect(lines[0]).not.toContain('ฝุ่น');
  expect(lines[1]).toContain('42 ไมโครกรัมต่อลูกบาศก์เมตร'); expect(lines[1]).toContain(level.label);
  expect(lines.at(-1)).toContain('1362');
  expect([...el.querySelectorAll('h2 span')].map((s: any) => s.textContent)).toEqual(['1', '2', '3', '4', '5', '6']);
  expect(el.querySelectorAll('.rp-map .rm-h').length).toBe(3);
  expect(el.querySelector('.rp-map').textContent).toContain('กม.'); // scale bar
  expect(el.textContent).toContain('2569'); // Buddhist-era date
  expect(el.textContent).toContain('052-081758');
  expect(el.textContent).not.toMatch(/AQI|WAQI/); // AQI may not be redistributed in an exported file
  dom.window.close();
});

it('without air data or hotspots it says so instead of showing zero dust or "no fire"', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('paper');
  el.innerHTML = w.CmeReport.html({ scope: 'forest', name: 'ป่าชุมชนบ้านทดสอบ', hours: 24, rows: [], now, air: false, shapes,
    forest: { name: 'ป่าชุมชนบ้านทดสอบ', amphoe: 'ฝาง' }, sources: [], showMap: false, showTable: true });
  expect(el.querySelector('.rp-summary').textContent).toContain('ไม่ได้ยืนยันว่าไม่มีไฟ');
  expect(el.textContent).not.toContain('ฝุ่น PM2.5 รอบล่าสุด');
  expect(el.textContent).toContain('ยังไม่มีช่องทางผู้ประสานงานป่าที่ยืนยันแล้ว');
  expect(el.querySelector('.rp-map')).toBeNull();
  dom.window.close();
});
