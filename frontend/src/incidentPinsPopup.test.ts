import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const pub = (f: string) => readFileSync(resolve(__dirname, '../public', f), 'utf8');
const win = new JSDOM('', { runScripts: 'outside-only' }).window as any;
win.eval(pub('decision-support.js'));
win.eval(pub('incident-pins.js'));
const P = win.CmeIncidentPins;
const NOW = Date.parse('2026-10-23T12:00:00+07:00');
const pin = (over: any = {}) => ({
  id: '30000000-0000-4000-8000-000000000001', forest_id: 'f1', forest_name: 'ป่าชุมชนบ้านแม่คงคา', amphoe: 'อำเภอแม่แจ่ม', observation: 'fire',
  latitude: 18.4, longitude: 98.45, observed_at: '2026-10-23T10:30:00+07:00', created_at: '2026-10-23T11:00:00+07:00', expires_at: '2026-10-26T11:00:00+07:00',
  description: 'ไฟกำลังไหม้ใกล้ลำห้วย', contact_phone: '081-234-5678', status: 'pending', reporter_name: 'สมชาย', mine: false, can_close: false, can_open: false,
  nearby: [{ forest_id: 'f1', name: 'ป่าชุมชนบ้านแม่คงคา', km: 0, risk: false, reporter: true }, { forest_id: 'f2', name: 'ป่าบ้านข้างเคียง', km: 3.4, risk: true, reporter: false }, { forest_id: 'f3', name: 'ป่าบ้านไกล', km: 8.1, risk: false, reporter: false }],
  ...over,
});
const html = (p: any, extra = {}) => new JSDOM(P.popupHtml(p, { now: NOW, ...extra })).window.document;

it('the pin popup says who reported, what, where, when and how to reach them', () => {
  const d = html(pin());
  expect(d.querySelector('h3')!.textContent).toContain('เห็นเปลวไฟที่ ป่าชุมชนบ้านแม่คงคา');
  expect(d.querySelector('h3 small')!.textContent).toBe('อ.แม่แจ่ม');
  expect(d.querySelector('.pin-who')!.textContent).toMatch(/แจ้งโดย สมชาย .* แจ้ง1 ชม.ที่แล้ว/);
  expect(d.querySelector('blockquote')!.textContent).toBe('ไฟกำลังไหม้ใกล้ลำห้วย');
  expect(d.querySelector('.pin-phone a')!.getAttribute('href')).toBe('tel:0812345678');
  expect(d.querySelector('.pin-kicker')!.textContent).toContain('ยังไม่ใช่การยืนยันจากหน่วยงาน');
  expect(d.querySelector('.pin-note')!.textContent).toMatch(/อีก 2 วัน 23 ชม\./);
  expect(d.querySelector('.pin-note a')!.getAttribute('href')).toBe('tel:1362');
});

it('lists the nearby forests with the reporter\'s own first and the ones within 5 km marked', () => {
  const rows = [...html(pin()).querySelectorAll('.pin-near li')].map(li => li.textContent!.replace(/\s+/g, ' ').trim());
  expect(rows).toEqual(['ป่าชุมชนบ้านแม่คงคา อยู่ในขอบเขตป่า ป่าของผู้แจ้ง', 'ป่าบ้านข้างเคียง 3.4 กม. เสี่ยง · ใกล้ไม่เกิน 5 กม.', 'ป่าบ้านไกล 8.1 กม.']);
});

it('falls back to the map\'s own nearest-forest list when the server has not stored one yet', () => {
  const fallback = [{ forest: { forest_id: 'f1', name: 'ป่าของผู้แจ้ง' }, km: 0.04 }, { forest: { forest_id: 'f9', name: 'ป่าใกล้' }, km: 4.2 }, { forest: { forest_id: 'f8', name: 'ป่าไกล' }, km: 9 }];
  const rows = [...html(pin({ nearby: null }), { fallback }).querySelectorAll('.pin-near li')].map(li => li.textContent!.replace(/\s+/g, ' ').trim());
  expect(rows[0]).toContain('ป่าของผู้แจ้ง') && expect(rows[0]).toContain('ป่าของผู้แจ้ง');
  expect(rows[1]).toContain('เสี่ยง') && expect(rows[2]).not.toContain('เสี่ยง');
});

it('only the reporter or an admin gets the end buttons; only people with access get "open the incident"', () => {
  expect(html(pin()).querySelector('.pin-actions')).toBeNull();
  const owner = html(pin({ mine: true, can_close: true, can_open: true }));
  expect([...owner.querySelectorAll('.pin-btn')].map(b => b.textContent)).toEqual(['เปิดใบเหตุ', '✅ จบงาน', '❌ ไม่ใช่ไฟ']);
  expect(owner.querySelector('.pin-who')!.textContent).toContain('(คุณ)');
  expect([...owner.querySelectorAll('[data-pin-close]')].map(b => (b as HTMLElement).dataset.outcome)).toEqual(['closed', 'cancelled']);
  // Buttons carry inline handlers: a Leaflet popup does not pass clicks on to the page.
  expect(owner.querySelector('[data-pin-open]')!.getAttribute('onclick')).toContain('pinOpenIncident');
});

it('escapes everything a person typed, including the phone and the forest names', () => {
  const evil = '<img src=x onerror=alert(1)>';
  const d = html(pin({ description: evil, reporter_name: evil, forest_name: evil, contact_phone: '"><script>1</script>', nearby: [{ forest_id: 'x', name: evil, km: 1, risk: true, reporter: false }] }));
  expect(d.querySelector('img')).toBeNull();
  expect(d.querySelector('script')).toBeNull();
  expect(d.body.innerHTML).toContain('&lt;img');
});

it('pins fade as they age so a forgotten one is easy to tell from a new report', () => {
  expect(P.tone(pin(), NOW)).toBe('fresh');
  expect(P.tone(pin({ created_at: '2026-10-22T09:00:00+07:00' }), NOW)).toBe('mid');
  expect(P.tone(pin({ created_at: '2026-10-20T09:00:00+07:00' }), NOW)).toBe('old');
  expect(P.iconHtml(pin(), NOW)).toContain('class="ring"');
  expect(P.iconHtml(pin({ created_at: '2026-10-20T09:00:00+07:00' }), NOW)).not.toContain('class="ring"');
  expect(P.leftText(pin({ expires_at: '2026-10-23T12:30:00+07:00' }), NOW)).toBe('1 ชม.');
  expect(P.leftText(pin({ expires_at: '2026-10-23T11:00:00+07:00' }), NOW)).toBe('ใกล้ปิดอัตโนมัติ');
});
