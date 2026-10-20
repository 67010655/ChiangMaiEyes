import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const src = readFileSync(resolve(__dirname, '../public/fire-weather.js'), 'utf8');
function load() { const dom = new JSDOM('', { runScripts: 'outside-only' }); (dom.window as any).eval(src); return { dom, F: (dom.window as any).CmeFireWeather }; }

it('matches the standard FWI test day (Van Wagner & Pickett 1985)', () => {
  const { dom, F } = load();
  const [d] = F.series([{ date: '2026-04-13', T: 17, H: 42, W: 25, r: 0 }], 46);
  expect(d.ffmc).toBeCloseTo(87.693, 2); expect(d.dmc).toBeCloseTo(8.545, 2); expect(d.dc).toBeCloseTo(19.014, 2);
  expect(d.isi).toBeCloseTo(10.854, 2); expect(d.bui).toBeCloseTo(8.490, 2); expect(d.fwi).toBeCloseTo(10.096, 2);
  dom.window.close();
});

it('uses tropical day lengths at Chiang Mai and lets rain lower the danger', () => {
  const { dom, F } = load();
  expect(F.dayLength(18.8, 3)).toBe(9.5); expect(F.dayLength(46, 3)).toBe(12.8);
  const days = (rainLast: number) => [...Array(10)].map((_, i) => ({ date: `2026-03-${String(i + 1).padStart(2, '0')}`, T: 36, H: 25, W: 12, r: i === 9 ? rainLast : 0 }));
  const dry = F.series(days(0), 18.8), wet = F.series(days(30), 18.8);
  expect(dry[9].fwi).toBeGreaterThan(wet[9].fwi);
  expect(F.CLASSES[F.classOf(dry[9].fwi)].label).not.toBe('ต่ำมาก');
  // missing weather never becomes a number
  expect(F.series([{ date: '2026-03-01', T: NaN, H: 30, W: 5, r: 0 }], 18.8)[0].fwi).toBeNull();
  dom.window.close();
});

it('reads noon values and the 24 h rain ending at noon', () => {
  const { dom, F } = load();
  const time: string[] = [], T: number[] = [], H: number[] = [], W: number[] = [], P: number[] = [];
  for (let d = 1; d <= 2; d++) for (let h = 0; h < 24; h++) {
    time.push(`2026-03-0${d}T${String(h).padStart(2, '0')}:00`); T.push(h); H.push(50); W.push(10); P.push(h === 6 ? 2 : 0.1);
  }
  const days = F.noonDays({ time, temperature_2m: T, relative_humidity_2m: H, wind_speed_10m: W, precipitation: P });
  expect(days[0].date).toBe('2026-03-01'); expect(Number.isNaN(days[0].r)).toBe(true); // not 24 h of rain yet
  expect(days[1].T).toBe(12); expect(days[1].r).toBeCloseTo(2 + 23 * 0.1, 5);
  dom.window.close();
});

it('labels the card as weather that favours fire, not a fire-location forecast, and cites its sources', () => {
  const { dom, F } = load();
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Bangkok' }).format(new Date());
  const day = (n: number) => { const x = new Date(today + 'T12:00:00Z'); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
  const data = [
    { name: 'ฝาง', days: [-1, 0, 1, 2].map(n => ({ date: day(n), fwi: 10 + n * 10 })) },
    { name: 'ฮอด', days: [-1, 0, 1, 2].map(n => ({ date: day(n), fwi: 5 })) },
  ];
  const html = F.fwiCard(data, {});
  expect(html).toContain('ไม่ใช่การพยากรณ์ว่าไฟจะเกิดที่ไหน');
  expect(html).toContain('Van Wagner'); expect(html).toContain('EFFIS');
  expect(F.fwiCard(data, { focus: 'ฝาง' })).toContain('สูง'); // 30 on day +2
  expect(F.outlookCard([{ week: day(3), rain: 2, rainAnom: -12, temp: 30, tempAnom: 1.5 }])).toContain('แห้งกว่าปกติ');
  dom.window.close();
});
