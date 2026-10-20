import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const pub = (f: string) => readFileSync(resolve(__dirname, '../public', f), 'utf8');
function setup(body = '<div id="top"></div>') {
  const dom = new JSDOM(body, { runScripts: 'outside-only' });
  const w = dom.window as any;
  w.eval(pub('public-guidance.js')); w.eval(pub('ux-foundation.js')); w.eval(pub('analytics-summary.js')); w.eval(pub('forest-picker.js'));
  return { dom, w };
}
const history = {
  days: 7,
  analytics: {
    total: 32,
    hotspots: [
      { date: '2026-10-17', count: 6, source_requests_complete: true, partial_day: false },
      { date: '2026-10-18', count: 10, source_requests_complete: true, partial_day: false },
      { date: '2026-10-19', count: null, source_requests_complete: false, partial_day: false },
    ],
    pm25: [
      { date: '2026-10-17', value: 16.5, samples: 48, measurement_kind: 'measured' },
      { date: '2026-10-18', value: 40.2, samples: 48, measurement_kind: 'measured' },
      { date: '2026-10-18', value: 99, samples: 24, measurement_kind: 'model' },
    ],
    districts: [{ name: 'ฝาง', count: 12 }, { name: 'แม่แตง', count: 5 }, { name: 'ว่าง', count: 0 }],
  },
};

it('shows the summary and cards from the received numbers, gaps not filled with zero', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const h = { ...history, analytics: { ...history.analytics, forests: [{ forest_id: 'cmf-1', count: 3 }, { forest_id: 'cmf-2', count: 0 }] } };
  w.CmeAnalyticsSummary.render(el, h, { forecast: [{ date: '2026-10-20', temp_max_c: 32.3, rain_mm: 0, wind_kmh: 6 }],
    forestInfo: (id: string) => (id === 'cmf-1' ? { name: 'ป่าชุมชนบ้านทดสอบ', amphoe: 'ฝาง' } : null), mapDays: 4 });
  expect(el.querySelectorAll('.as-card').length).toBe(5); // 4 cards + weather
  // One-line summary built from the data, with the PCD level of the latest full day.
  const hero = el.querySelector('.as-hero').textContent;
  expect(hero).toContain('พบจุดความร้อน 32 จุด'); expect(hero).toContain('อ.ฝาง'); expect(hero).toContain('เริ่มมีผลต่อสุขภาพ');
  const hot = el.querySelector('.as-hot');
  expect(hot.textContent).toContain('วันที่พบมากที่สุด 18 ต.ค. · 10 จุด');
  expect(hot.textContent).toContain('ส่งข้อมูลไม่ครบ');
  // Missing day draws a flat marker, not a bar; replay names the map's real days.
  expect(hot.querySelectorAll('rect')[2].getAttribute('class')).toBe('as-gap');
  expect(hot.querySelector('[data-as-action="replay"]').textContent).toContain('4 วัน');
  // PM uses station values only.
  const pm = el.querySelector('.as-pm').textContent;
  expect(pm).toContain('40.2'); expect(pm).not.toContain('99');
  // Districts with zero points are not ranked.
  expect([...el.querySelectorAll('.as-rank [data-as-district]')].map((b: any) => b.dataset.asDistrict)).toEqual(['ฝาง', 'แม่แตง']);
  // Forests: only those with points, by name, and never called fire.
  const forest = el.querySelector('.as-forest');
  expect([...forest.querySelectorAll('[data-as-forest]')].map((b: any) => b.dataset.asForest)).toEqual(['cmf-1']);
  expect(forest.textContent).toContain('ป่าชุมชนบ้านทดสอบ'); expect(forest.textContent).toContain('ยังไม่ใช่เหตุไฟที่ยืนยันแล้ว');
  expect(el.querySelector('.as-forecast').textContent).toContain('ไม่ใช่การคาดการณ์ไฟ');
  dom.window.close();
});

it('says no points is not no fire', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  w.CmeAnalyticsSummary.render(el, { days: 7, analytics: { total: 0, hotspots: [], pm25: [], districts: [], forests: [] } }, {});
  expect(el.querySelector('.as-hot').textContent).toContain('ไม่ได้แปลว่าไม่มีไฟ');
  expect(el.querySelector('.as-forest').textContent).toContain('ไม่ได้แปลว่าไม่มีไฟ');
  expect(el.textContent).not.toContain('ปลอดภัย');
  dom.window.close();
});

it('shows a Thai message instead of empty cards when the archive cannot be read', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  w.CmeAnalyticsSummary.render(el, null, { error: 'อ่านข้อมูลย้อนหลังไม่ได้ตอนนี้' });
  expect(el.querySelector('[role="alert"]').textContent).toContain('อ่านข้อมูลย้อนหลังไม่ได้');
  dom.window.close();
});

it('filters a long forest list by name or district and keeps the select', () => {
  const opts = ['<option value="">เลือกป่าชุมชน</option>'];
  for (let i = 0; i < 40; i++) opts.push(`<option value="f${i}">ป่าชุมชนบ้าน${i} · อ.${i % 2 ? 'แม่ริม' : 'ฝาง'}</option>`);
  const { dom, w } = setup(`<select id="exportForest">${opts.join('')}</select>`);
  const sel = w.document.getElementById('exportForest');
  const input = sel.previousElementSibling.querySelector('input');
  input.value = 'อำเภอแม่ริม'; input.dispatchEvent(new w.Event('input'));
  expect([...sel.options].filter((o: any) => o.value).length).toBe(20);
  input.value = 'บ้าน7 '; input.dispatchEvent(new w.Event('input'));
  expect(sel.value).toBe('f7');
  input.value = ''; input.dispatchEvent(new w.Event('input'));
  expect(sel.options.length).toBe(41); expect(sel.value).toBe('f7');
  dom.window.close();
});
