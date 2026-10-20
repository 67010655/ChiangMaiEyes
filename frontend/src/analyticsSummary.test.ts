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
  expect(el.querySelectorAll('.as-card').length).toBe(6); // 5 past cards (incl. wind) + weather
  // One-line summary built from the data, with the PCD level of the latest full day.
  const hero = el.querySelector('.as-hero').textContent;
  expect(hero).toContain('พบจุดความร้อน 32 จุด'); expect(hero).toContain('อ.ฝาง'); expect(hero).toContain('ฝุ่นเฉลี่ยช่วงนี้ระดับ ปานกลาง'); // (16.5 + 40.2) / 2 full days
  const hot = el.querySelector('.as-hot');
  expect(hot.textContent).toContain('วันที่พบมากที่สุด 18 ต.ค. · 10 จุด');
  expect(hot.textContent).toContain('ส่งข้อมูลไม่ครบ');
  // Missing day draws a flat marker, not a bar; replay names the map's real days.
  expect(hot.querySelectorAll('rect')[2].getAttribute('class')).toBe('as-gap');
  expect(hot.querySelector('[data-as-action="replay"]').textContent).toContain('4 วัน');
  // PM uses station values only.
  const pm = el.querySelector('.as-pm').textContent;
  expect(pm).toContain('28.4'); expect(pm).toContain('ล่าสุด 40.2'); expect(pm).not.toContain('99');
  // Past and future are labelled apart.
  expect(el.querySelector('.as-section.past').textContent).toContain('ย้อนหลัง');
  expect(el.querySelector('.as-section.future').textContent).toContain('พยากรณ์');
  // Districts with zero points are not ranked.
  expect([...el.querySelectorAll('.as-rank [data-as-district]')].map((b: any) => b.dataset.asDistrict)).toEqual(['ฝาง', 'แม่แตง']);
  // Forests: only those with points, by name, and never called fire.
  const forest = el.querySelector('.as-forest');
  expect([...forest.querySelectorAll('[data-as-forest]')].map((b: any) => b.dataset.asForest)).toEqual(['cmf-1']);
  expect(forest.textContent).toContain('ป่าชุมชนบ้านทดสอบ'); expect(forest.textContent).toContain('ยังไม่ใช่เหตุไฟที่ยืนยันแล้ว');
  expect(el.querySelector('.as-forecast').textContent).toContain('ไม่ใช่การคาดการณ์ไฟ');
  dom.window.close();
});

it('fills a day with no station value from the model, kept apart and counted', () => {
  const { dom, w } = setup();
  const S = w.CmeAnalyticsSummary;
  const a = { pm25: [
    { date: '2026-09-01', value: 30, samples: 1, measurement_kind: 'model' },
    { date: '2026-09-02', value: 12, samples: 24, measurement_kind: 'measured' },
    { date: '2026-09-02', value: 50, samples: 24, measurement_kind: 'model' },
  ] };
  const pm = S.pmSeries(a, ['2026-09-01', '2026-09-02', '2026-09-03']);
  expect(pm.series.map((x: any) => [x.v, x.kind])).toEqual([[30, 'model'], [12, 'measured'], [null, null]]);
  expect(pm.stationDays).toBe(1); expect(pm.modelDays).toBe(1); expect(pm.avg).toBe(21);
  expect(pm.levels.find((l: any) => l.label === 'ดีมาก').n).toBe(1);
  expect(pm.levels.find((l: any) => l.label === 'ปานกลาง').n).toBe(1);
  dom.window.close();
});

it('summarises wind as where it blows to, with calm hours apart', () => {
  const { dom, w } = setup();
  // wind FROM the north-east (45 deg) blows TOWARD the south-west
  const hours = [...Array(6)].map(() => ({ spd: 10, dir: 45 })).concat([{ spd: 2, dir: 270 }, { spd: 3, dir: 90 }]);
  const st = w.CmeAnalyticsSummary.windStats({ hours });
  expect(st.top).toBe(5); // index 5 = ตะวันตกเฉียงใต้
  expect(Math.round(st.calmPct)).toBe(25);
  expect(st.avg).toBeCloseTo((60 + 5) / 8, 5);
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

it('compares with the previous period only when that period was actually received', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const day = (date: string, count: number | null, ok = true) => ({ date, count, source_requests_complete: ok, partial_day: false });
  const cur = { days: 2, start: '2026-10-18T00:00:00+07:00', analytics: { total: 12, hotspots: [day('2026-10-18', 6), day('2026-10-19', 6)], pm25: [], districts: [], forests: [] } };
  w.CmeAnalyticsSummary.render(el, cur, {});
  // Before the archive began the API says 0 with incomplete requests: never "0" or a percentage.
  const before = { analytics: { total: 0, hotspots: [day('2026-10-16', null, false), day('2026-10-17', null, false)], pm25: [] } };
  w.CmeAnalyticsSummary.renderCompare(el, cur, before);
  const hot = el.querySelector('[data-compare="hot"]').textContent;
  expect(hot).toContain('ยังเทียบไม่ได้'); expect(hot).not.toMatch(/\d+%/);
  const got = { analytics: { total: 8, hotspots: [day('2026-10-16', 4), day('2026-10-17', 4)], pm25: [] } };
  w.CmeAnalyticsSummary.renderCompare(el, cur, got);
  expect(el.querySelector('[data-compare="hot"]').textContent).toContain('มากกว่า 2 วันก่อนหน้า 4 จุด (+50%)');
  dom.window.close();
});

it('shades only the official burn-control days and cites the announcement', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const S = w.CmeAnalyticsSummary;
  expect(S.inBan('2026-05-31')).not.toBeNull(); expect(S.inBan('2026-06-01')).toBeNull(); expect(S.inBan('2026-12-31')).toBeNull();
  const h = { days: 3, analytics: { total: 1, pm25: [], districts: [], forests: [], hotspots: [
    { date: '2026-05-30', count: 1, source_requests_complete: true, partial_day: false },
    { date: '2026-05-31', count: 0, source_requests_complete: true, partial_day: false },
    { date: '2026-06-01', count: 0, source_requests_complete: true, partial_day: false }] } };
  S.render(el, h, {});
  expect(el.querySelectorAll('.as-hot .as-band').length).toBe(2);
  const note = el.querySelector('.as-ban-note');
  expect(note.textContent).toContain('ไม่ได้แปลว่าฝ่าฝืนทุกจุด');
  expect(note.querySelector('a[href*="pamiang.go.th"]')).not.toBeNull();
  dom.window.close();
});

it('a chosen forest narrows hotspots and labels dust and wind as province-wide', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const h = { days: 7, analytics: { total: 0, hotspots: [], pm25: [], districts: [{ name: 'ฝาง', count: 9 }], forests: [] } };
  w.CmeAnalyticsSummary.render(el, h, { forest: { forest_id: 'cmf-1', name: 'ป่าชุมชนบ้านทดสอบ', amphoe: 'ฝาง' } });
  expect(el.querySelector('.as-hero').textContent).toContain('ป่าชุมชนบ้านทดสอบ');
  expect(el.querySelector('.as-hero').textContent).toContain('ในขอบเขตป่านี้');
  expect(el.querySelector('.as-hero').textContent).not.toContain('อ.ฝาง'); // no province ranking inside one forest
  expect(el.querySelector('.as-dist')).toBeNull();
  expect([...el.querySelectorAll('.as-scope')].map((x: any) => x.textContent)).toEqual(['ภาพรวมจังหวัด', 'ภาพรวมจังหวัด']);
  dom.window.close();
});
