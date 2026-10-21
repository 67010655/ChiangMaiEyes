import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const src = readFileSync(resolve(__dirname, '../public/map-search.js'), 'utf8');
const sheetSrc = readFileSync(resolve(__dirname, '../public/hotspot-sheet.js'), 'utf8');
const evidence = readFileSync(resolve(__dirname, '../public/decision-support.js'), 'utf8');
const items = [
  { kind: 'forest', name: 'ป่าชุมชนบ้านแม่คงคา', sub: 'อ.แม่แจ่ม' },
  { kind: 'tambon', name: 'แม่สาว', sub: 'อ.แม่อาย' },
  { kind: 'district', name: 'แม่ริม' },
  { kind: 'district', name: 'สันป่าตอง' },
  { kind: 'tambon', name: 'ริมใต้', sub: 'อ.แม่ริม' },
];

it('finds every place containing the text, grouped district > tambon > forest', () => {
  const dom = new JSDOM('', { runScripts: 'outside-only' }); const w = dom.window as any; w.eval(src);
  const r = w.CmeMapSearch.rank(items, 'แม่');
  expect(r.map((x: any) => x.name)).toEqual(['แม่ริม', 'แม่สาว', 'ริมใต้', 'ป่าชุมชนบ้านแม่คงคา']); // grouped: district, tambon, forest
  expect(w.CmeMapSearch.rank(items, 'ป่าตอง').map((x: any) => x.name)).toEqual(['สันป่าตอง']);
  expect(w.CmeMapSearch.rank(items, '')).toEqual([]);
  const html = w.CmeMapSearch.listHtml(r, 'แม่');
  expect(html).toContain('<mark>แม่</mark>');
  expect(w.CmeMapSearch.listHtml([], 'zzz')).toContain('ไม่พบ');
  dom.window.close();
});

it('typing shows a list, Enter picks the first, Escape hides', async () => {
  const dom = new JSDOM('<div class="map-search"><input id="q" placeholder="ค้นหา"></div>', { runScripts: 'outside-only' }); const w = dom.window as any; w.eval(src);
  const picked: any[] = [];
  const input = w.document.getElementById('q');
  w.CmeMapSearch.init({ input, items: () => items, suggest: () => [{ kind: 'district', name: 'ฝาง', extra: '3 จุด' }], onPick: (r: any) => picked.push(r.name) });
  input.dispatchEvent(new w.Event('focus'));
  expect(w.document.querySelector('.ms-title')?.textContent).toContain('จุดความร้อน');
  input.value = 'ริม'; input.dispatchEvent(new w.Event('input'));
  expect(w.document.querySelectorAll('.ms-opt').length).toBe(2);
  input.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter' }));
  expect(picked).toEqual(['แม่ริม']); // districts come first
  input.value = 'แม'; input.dispatchEvent(new w.Event('input'));
  input.dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Escape' }));
  expect(w.document.getElementById('mapSearchList').hidden).toBe(true);
  dom.window.close();
});

it('the sheet opens at half height and dragging down stops at the title row', () => {
  const dom = new JSDOM('', { runScripts: 'outside-only' }); const w = dom.window as any;
  w.requestAnimationFrame = (f: any) => f(); w.eval(evidence); w.eval(sheetSrc);
  w.CmeHotspotSheet.openPanel({ kicker: 'k', title: 't', html: '<p>x</p>' });
  const sheet = w.document.getElementById('hotspotSheet');
  expect(sheet.dataset.stop).toBe('half');
  w.CmeHotspotSheet.setStop('peek');
  expect(sheet.dataset.stop).toBe('peek'); expect(sheet.hidden).toBe(false);
  expect(sheet.querySelector('.hs-sheet-close')).not.toBeNull();
  dom.window.close();
});
