import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it, vi } from 'vitest';

const pub = (f: string) => readFileSync(resolve(__dirname, '../public', f), 'utf8');
const forest = (id: string, name: string, lat: number, lon: number) => ({ forest_id: id, name, latitude: lat, longitude: lon });
// A stand-in for CmeCoordination.nearest: distances are given, nearest first.
const rowsFor = (pairs: [any, number][]) => () => pairs.map(([f, km]) => ({ forest: f, km })).sort((a, b) => a.km - b.km);

function setup(url = 'https://chiangmaieyes.vercel.app/') {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url });
  const win = dom.window as any;
  win.fetch = vi.fn(() => { throw new Error('practice must never call the server'); });
  win.eval(pub('practice-report.js'));
  return { win, P: win.CmePracticeReport };
}

it('a practice report reaches the same forests a real one would: not the own forest, only within 5 km, at most 10', () => {
  const { P } = setup();
  const own = forest('own', 'ป่าบ้านต้นเรื่อง', 18.5, 98.4);
  const near = Array.from({ length: 12 }, (_, i) => [forest('n' + i, 'ป่าใกล้ ' + i, 18.51, 98.41), 0.5 + i * 0.3] as [any, number]);
  const far = forest('far', 'ป่าไกล', 18.7, 98.6);
  const rows = P.nearby(18.5, 98.4, rowsFor([[own, 0], ...near, [far, 9.2]]));
  expect(rows.find((r: any) => r.forest_id === 'own')).toMatchObject({ own: true, risk: false });
  expect(rows.find((r: any) => r.forest_id === 'far').risk).toBe(false);
  const sent = P.alerted(rows);
  expect(sent).toHaveLength(10);
  expect(sent.map((r: any) => r.forest_id)).not.toContain('own');
  expect(sent[0].km).toBeLessThanOrEqual(sent[9].km);
});

it('the sample LINE text uses the real wording, but says no link was sent', () => {
  const { P } = setup();
  const p = { observation: 'smoke', observed_at: '2026-11-10T09:20:00+07:00', latitude: 18.5, longitude: 98.4, own_forest: 'ป่าบ้านต้นเรื่อง', reporter: 'สมชาย', contact_phone: '081-234-5678' };
  const text = P.alertText(p, { name: 'ป่าบ้านข้างเคียง', km: 2.3, lat: 18.52, lon: 98.43 });
  expect(text).toContain('🚨 มีรายงานไฟใกล้ป่าชุมชนของคุณ');
  expect(text).toContain('👁️ ตัวแทนป่าบ้านต้นเรื่อง เห็นควัน');
  expect(text).toMatch(/📏 อยู่ห่างขอบเขตป่าบ้านข้างเคียง ประมาณ 2\.3 กม\. ทางทิศ\S+ของป่านั้น/);
  expect(text).toContain('☎️ ติดต่อผู้แจ้ง 081-234-5678');
  expect(text).toContain('โทร 1362');
  expect(text).not.toMatch(/https?:\/\//);
  expect(P.closedText(p, 'cancelled')).toContain('❌ หมุดไฟใกล้ป่าคุณ ถูกบันทึกว่าไม่ใช่ไฟ');
});

it('checks the form like the real one', () => {
  const { P } = setup();
  const ok = { latitude: '18.5', longitude: '98.4', observed_local: '2026-11-10T09:20', contact_phone: '' };
  expect(P.validate(ok)).toBe('');
  expect(P.validate({ ...ok, latitude: '' })).toContain('ใส่ตำแหน่งก่อน');
  expect(P.validate({ ...ok, latitude: '13.7', longitude: '100.5' })).toContain('นอกจังหวัดเชียงใหม่');
  expect(P.validate({ ...ok, contact_phone: 'abc' })).toContain('เบอร์โทร');
});

it('practice pins live in this browser for a day only', () => {
  const { P, win } = setup();
  const now = Date.parse('2026-11-10T12:00:00+07:00');
  P.save([{ id: 'a', created_at: '2026-11-10T08:00:00+07:00' }, { id: 'b', created_at: '2026-11-08T08:00:00+07:00' }]);
  expect(P.load(now).map((p: any) => p.id)).toEqual(['a']);
  win.localStorage.setItem(P.KEY, 'not json');
  expect(P.load(now)).toEqual([]);
});

it('a full practice run: the link turns practice on, the form sends nothing anywhere, the steps advance', async () => {
  vi.useFakeTimers();
  const { P, win } = setup('https://chiangmaieyes.vercel.app/#practice');
  const own = forest('own', 'ป่าบ้านต้นเรื่อง', 18.5, 98.4), next = forest('n1', 'ป่าบ้านข้างเคียง', 18.52, 98.43);
  P.init({ nearest: rowsFor([[own, 0], [next, 2.3]]), area: () => ({ status: 'matched', tambon: 'ช่างเคิ่ง', district: 'อำเภอแม่แจ่ม' }) });
  const doc = win.document;
  expect(P.active()).toBe(true);
  expect(win.location.hash).toBe('');
  expect(doc.getElementById('practiceBanner')!.textContent).toContain('ไม่ส่ง LINE');

  P.open({ lat: 18.5, lon: 98.4 });
  expect(doc.querySelector('.pr-area')!.textContent).toBe('จุดนี้อยู่ ต.ช่างเคิ่ง อ.แม่แจ่ม');
  const form = doc.getElementById('prForm') as HTMLFormElement;
  (form.elements.namedItem('description') as HTMLTextAreaElement).value = 'ควันขึ้นหลังดอย';
  form.dispatchEvent(new win.Event('submit', { bubbles: true, cancelable: true }));
  expect(doc.querySelector('.pr-sending')!.textContent).toContain('กำลังส่ง');
  vi.advanceTimersByTime(1300);
  expect(doc.querySelector('.pr-card h2')!.textContent).toBe('ส่งแล้ว (ฝึก)');
  expect(doc.querySelectorAll('.pr-near li')).toHaveLength(1);
  expect(doc.querySelector('.pr-near')!.textContent).toContain('ป่าบ้านข้างเคียง');
  expect(doc.querySelector('.pr-line pre')!.textContent).toContain('ตัวแทนป่าบ้านต้นเรื่อง เห็นควัน');
  expect(doc.querySelector('.pr-steps li.now')!.textContent).toContain('ติดตาม');

  const note = doc.getElementById('prNote') as HTMLFormElement;
  (note.elements.namedItem('note') as HTMLTextAreaElement).value = 'ไฟเริ่มสงบ';
  note.dispatchEvent(new win.Event('submit', { bubbles: true, cancelable: true }));
  expect(doc.querySelector('.pr-steps li.now')!.textContent).toContain('จบงาน');
  (doc.querySelector('[data-pr="done"]') as HTMLButtonElement).click();
  expect(doc.querySelector('.pr-card h2')!.textContent).toBe('จบงานแล้ว (ฝึก)');
  expect(doc.querySelectorAll('.pr-steps li.done')).toHaveLength(4);
  expect(P.load()[0]).toMatchObject({ closed: 'closed', notes: [{ text: 'ไฟเริ่มสงบ' }] });

  expect(win.fetch).not.toHaveBeenCalled();
  (doc.querySelector('#practiceBanner [data-pr="exit"]') as HTMLButtonElement).click();
  expect(P.active()).toBe(false);
  vi.useRealTimers();
});

it('a map pick goes to the practice form only when practice asked for it', () => {
  const { P, win } = setup();
  P.init({ pick: () => {} });
  expect(P.takePick(18.5, 98.4)).toBe(false);
  P.setActive(true); P.open();
  (win.document.querySelector('[data-pr="pick"]') as HTMLButtonElement).click();
  expect(P.takePick(18.5, 98.4)).toBe(true);
  expect((win.document.querySelector('#prForm [name="latitude"]') as HTMLInputElement).value).toBe('18.50000');
  expect(P.takePick(18.6, 98.5)).toBe(false);
});
