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
  expect(el.querySelectorAll('.as-card').length).toBe(8); // 5 past cards + fire weather, outlook, weather
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

it('district view narrows the summary; LINE sign-up waits for live sensor coverage', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const shapes = [{ name: 'ฝาง', rings: [[[99, 19.8], [99.2, 19.8], [99.2, 20], [99, 19.8]]] }, { name: 'แม่อาย', rings: [[[99.2, 20], [99.3, 20], [99.3, 20.1], [99.2, 20]]] }];
  const h = { days: 7, analytics: { total: 5, hotspots: [], pm25: [], districts: [{ name: 'ฝาง', count: 5 }], forests: [], tambons: [{ name: 'เวียง', count: 3 }, { name: 'ม่อนปิ่น', count: 2 }] } };
  w.CmeAnalyticsSummary.render(el, h, { district: 'ฝาง', shapes });
  expect(el.querySelector('.as-hero').textContent).toContain('อ.ฝาง');
  expect(el.querySelector('.as-hero').textContent).toContain('ใน อ.ฝาง');
  expect([...el.querySelectorAll('.as-rank .as-name')].map((x: any) => x.textContent)).toEqual(['ต.เวียง', 'ต.ม่อนปิ่น']);
  expect(el.querySelector('.as-map path.dim')).not.toBeNull();
  // No coverage answer (no fetch here) means no sign-up card.
  expect(el.querySelector('.as-line')).toBeNull();
  expect(decodeURIComponent(w.CmeAnalyticsSummary.lineHref('ฝาง'))).toBe('https://line.me/R/oaMessage/@241mevgs/?แจ้งเตือนฝุ่น ฝาง');
  dom.window.close();
});

it('LINE sign-up lists only districts with enough live sensors', async () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const h = { days: 7, analytics: { total: 0, hotspots: [], pm25: [], districts: [], forests: [], tambons: [] } };
  const fetcher = async (url: string) => url === '/api/dust-alerts/coverage'
    ? { ok: true, json: async () => ({ enabled: true, min_sensors: 2, districts: { 'หางดง': 4, 'ฮอด': 2, 'ฝาง': 1 } }) }
    : { ok: false, json: async () => ({}) };
  w.CmeAnalyticsSummary.render(el, h, { district: 'ฝาง', shapes: [], fetcher });
  await new Promise(r => setTimeout(r, 20));
  const opts = [...el.querySelectorAll('[data-line-district] option')].map((x: any) => x.value).filter(Boolean);
  expect(opts.sort()).toEqual(['ฮอด', 'หางดง'].sort());
  expect(el.querySelector('.as-line').textContent).toContain('อ.ฝาง ยังมีเซนเซอร์ที่ส่งข้อมูลไม่ถึง 2 จุด');
  expect(el.querySelector('.as-line').textContent).toContain('World Air Quality Index Project');
  dom.window.close();
});

it('keeps fire and dust apart, and explains a clean long average next to many hotspots', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  // 40 days: 60 hotspots in April with dusty air, then clean rainy days.
  const dates = Array.from({ length: 40 }, (_, i) => new Date(Date.UTC(2026, 3, 1 + i)).toISOString().slice(0, 10));
  const h = { days: 40, analytics: { total: 60, districts: [{ name: 'แม่แจ่ม', count: 60 }],
    hotspots: dates.map((d, i) => ({ date: d, count: i < 15 ? 4 : 0, source_requests_complete: true, partial_day: false })),
    pm25: dates.map((d, i) => ({ date: d, value: i < 15 ? 50 : 8, samples: 48, measurement_kind: 'measured' })) } };
  w.CmeAnalyticsSummary.render(el, h, {});
  const fire = el.querySelector('.as-hl.fire').textContent, dust = el.querySelector('.as-hl.pm').textContent;
  expect(fire).toContain('พบจุดความร้อน 60 จุด'); expect(fire).not.toContain('ฝุ่น');
  expect(dust).toContain('ฝุ่นเฉลี่ยช่วงนี้ระดับ ดี'); // (15×50 + 25×8) / 40 = 23.75
  expect(dust).toContain('ระดับเริ่มมีผลต่อสุขภาพขึ้นไป 15 จาก 40 วัน');
  const why = el.querySelector('.as-why').textContent;
  expect(why).toContain('1 เม.ย.'); expect(why).toContain('50 µg/m³ (เริ่มมีผลต่อสุขภาพ)'); expect(why).toContain('สัปดาห์นั้นพบจุดความร้อน 16 จุด'); // 1–4 Apr × 4
  // A short range never gets the note.
  w.CmeAnalyticsSummary.render(el, history, {});
  expect(el.querySelector('.as-why')).toBeNull();
  dom.window.close();
});

it('24 h bars run oldest to newest and each readout names the date and hour range', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const hist = Array.from({ length: 24 }, (_, i) => (i === 14 ? 3 : 0));
  w.CmeAnalyticsSummary.render(el, { days: 1, analytics: { ...history.analytics, total: 3, hour_histogram: hist } }, {});
  const reads = [...el.querySelectorAll('.as-hot [data-read]')].map((r: any) => r.getAttribute('data-read'));
  expect(reads).toHaveLength(24);
  expect(reads.every((r: string) => /\d+ [ก-๙.]+ \d\d:00–\d\d:59 น\./.test(r))).toBe(true);
  expect(reads.find((r: string) => r.includes('14:00–14:59'))).toContain('3 จุด');
  expect(el.querySelector('.as-hot .as-axis').textContent).toContain('ตอนนี้');
  dom.window.close();
});

it('24 h card explains when the live home count is ahead of the archive', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const hist = Array.from({ length: 24 }, (_, i) => (i === 13 ? 2 : 0));
  const h = { days: 1, analytics: { ...history.analytics, total: 2, hour_histogram: hist } };
  w.CmeAnalyticsSummary.render(el, h, { liveCount: 9 });
  expect(el.querySelector('.as-hot .as-lag').textContent).toContain('9');
  expect(el.querySelector('.as-hot .as-lag').textContent).toContain('อีก 7 จุด');
  w.CmeAnalyticsSummary.render(el, h, { liveCount: 2 });
  expect(el.querySelector('.as-lag')).toBeNull();
  w.CmeAnalyticsSummary.render(el, { ...h, days: 7 }, { liveCount: 9 });
  expect(el.querySelector('.as-lag')).toBeNull();
  dom.window.close();
});

it('forest card says what it counts when no point fell inside a forest, and offers a longer range', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  w.CmeAnalyticsSummary.render(el, { days: 1, analytics: { total: 7, hotspots: [], pm25: [], districts: [], forests: [] } }, {});
  const card = el.querySelector('.as-forest');
  expect(card.textContent).toContain('677 แห่ง');
  expect(card.textContent).toContain('มี 7 จุดทั้งจังหวัด แต่อยู่นอกป่าทั้งหมด');
  expect(card.querySelector('[data-as-range]').getAttribute('data-as-range')).toBe('90d');
  dom.window.close();
});

it('a one-year view says when the archive starts, so empty early months are not read as no fire', () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const day = (d: string, count: number | null, done: boolean) => ({ date: d, count, source_requests_complete: done, partial_day: false });
  const hotspots = [day('2025-10-24', null, false), day('2026-01-01', null, false), day('2026-04-13', 40, true), day('2026-10-23', 3, true)];
  w.CmeAnalyticsSummary.render(el, { days: 365, analytics: { total: 43, hotspots, pm25: [], districts: [], forests: [] } }, {});
  const note = el.querySelector('.as-archive-start');
  expect(note.textContent).toContain('13 เม.ย. 2569');
  expect(note.textContent).toContain('ไม่ได้แปลว่าไม่มีไฟ');
  w.CmeAnalyticsSummary.render(el, { days: 7, analytics: { total: 3, hotspots: hotspots.slice(2), pm25: [], districts: [], forests: [] } }, {});
  expect(el.querySelector('.as-archive-start')).toBeNull();
  dom.window.close();
});

it('wind card adds the windiest time of day and how strong the wind was', async () => {
  const { dom, w } = setup(); const el = w.document.getElementById('top');
  const time: string[] = [], spd: number[] = [], dir: number[] = [];
  for (let d = 1; d <= 2; d++) for (let hr = 0; hr < 24; hr++) { time.push(`2026-10-0${d}T${String(hr).padStart(2, '0')}:00`); spd.push(hr >= 13 && hr <= 15 ? 22 : 4); dir.push(45); }
  const fetcher = async () => ({ ok: true, json: async () => ({ hourly: { time, wind_speed_10m: spd, wind_direction_10m: dir } }) });
  w.CmeAnalyticsSummary.render(el, { days: 2, analytics: { total: 0, hotspots: [], pm25: [], districts: [], forests: [] } }, { fetcher });
  for (let i = 0; i < 20 && !el.querySelector('.as-wind-extra'); i++) await new Promise(r => setTimeout(r, 10));
  const extra = el.querySelector('.as-wind-extra');
  expect(extra.querySelectorAll('.as-wind-hours rect')).toHaveLength(24);
  expect(extra.textContent).toContain('แรงสุดราว 13:00–16:00 น.');
  expect(extra.textContent).toMatch(/แรง 20 ขึ้นไป กม\.\/ชม\. 13%/);
  dom.window.close();
});
