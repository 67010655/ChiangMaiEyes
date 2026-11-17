import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it, vi } from 'vitest';

const src = readFileSync(resolve(__dirname, '../public/forest-proposal.js'), 'utf8');
function setup() {
  const dom = new JSDOM('<!doctype html><body></body>', { runScripts: 'outside-only', url: 'https://chiangmaieyes.vercel.app/' });
  const win = dom.window as any;
  win.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ id: 'abcdef12-0000', status: 'pending' }) }));
  win.eval(src);
  return { win, P: win.CmeForestProposal };
}

it('checks the proposal like the server does', () => {
  const { P } = setup();
  const ok = { name: 'ป่าชุมชนบ้านทดสอบ', latitude: '18.31', longitude: '98.33', contact_phone: '' };
  expect(P.validate(ok)).toBe('');
  expect(P.validate({ ...ok, name: 'x' })).toContain('ชื่อป่า');
  expect(P.validate({ ...ok, latitude: '' })).toContain('ตำแหน่ง');
  expect(P.validate({ ...ok, latitude: '13.7', longitude: '100.5' })).toContain('นอกจังหวัด');
  expect(P.validate({ ...ok, contact_phone: 'abc' })).toContain('เบอร์โทร');
});

it('a map pick fills the form, and sending posts to the team with the tambon filled in', async () => {
  const { P, win } = setup();
  P.init({ apiBase: '', pick: () => {}, area: () => ({ status: 'matched', tambon: 'กองแขก', district: 'อำเภอแม่แจ่ม' }) });
  expect(P.takePick(18.3, 98.3)).toBe(false);
  P.open();
  (win.document.querySelector('[data-fp="pick"]') as HTMLButtonElement).click();
  expect(P.takePick(18.31067, 98.33598)).toBe(true);
  const doc = win.document;
  expect(doc.querySelector('.pr-area').textContent).toBe('จุดนี้อยู่ ต.กองแขก อ.แม่แจ่ม');
  const form = doc.getElementById('fpForm') as HTMLFormElement;
  (form.elements.namedItem('name') as HTMLInputElement).value = 'ป่าชุมชนบ้านหัวดอยใหม่';
  form.dispatchEvent(new win.Event('submit', { bubbles: true, cancelable: true }));
  await new Promise(r => setTimeout(r, 0));
  const [url, opts] = win.fetch.mock.calls[0];
  expect(url).toBe('/api/community/forest-proposals');
  expect(JSON.parse(opts.body)).toMatchObject({ name: 'ป่าชุมชนบ้านหัวดอยใหม่', tambon: 'กองแขก', district: 'แม่แจ่ม', latitude: 18.31067, contact_phone: null });
  expect(doc.querySelector('.pr-card h2').textContent).toBe('ส่งแล้ว ขอบคุณครับ');
});

it('the map search offers a proposal when no forest matches, prefilled with what was typed', () => {
  const dom = new JSDOM('<!doctype html><body><div class="map-search"><input id="q"></div></body>', { runScripts: 'outside-only', url: 'https://chiangmaieyes.vercel.app/' });
  const win = dom.window as any;
  win.eval(readFileSync(resolve(__dirname, '../public/map-search.js'), 'utf8'));
  const proposed: string[] = [];
  const input = win.document.getElementById('q');
  win.CmeMapSearch.init({ input, items: () => [{ kind: 'district', name: 'แม่แจ่ม' }], onPick: () => {}, onPropose: (q: string) => proposed.push(q) });
  input.value = 'ป่าบ้านไม่มีในระบบ';
  input.dispatchEvent(new win.Event('input'));
  const opt = win.document.querySelector('.ms-propose');
  expect(opt).not.toBeNull();
  opt.dispatchEvent(new win.Event('pointerdown', { bubbles: true, cancelable: true }));
  expect(proposed).toEqual(['ป่าบ้านไม่มีในระบบ']);
  input.value = 'แม่แจ่ม';
  input.dispatchEvent(new win.Event('input'));
  expect(win.document.querySelector('.ms-propose')).not.toBeNull(); // a district match still offers it: no forest matched
});
