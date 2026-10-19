import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const evidence = readFileSync(resolve(__dirname, '../public/decision-support.js'), 'utf8');
const workspace = readFileSync(resolve(__dirname, '../public/community-workspace.js'), 'utf8');
const f = { forest_id: 'fixture-A', name: 'ป่าทดสอบ', amphoe: 'อำเภอทดสอบ', latitude: 18.85, longitude: 98.85,
  boundary: { type: 'Polygon', coordinates: [[[98.8,18.8],[98.9,18.8],[98.9,18.9],[98.8,18.9],[98.8,18.8]]] } };
const tick = () => new Promise(r => setTimeout(r, 5));
const code = { code: 'CME-ABCD2345', expires_at: '2026-10-19T03:10:00+00:00', add_friend_url: 'https://line.me/R/ti/p/%40241mevgs',
  chat_url: 'https://line.me/R/oaMessage/%40241mevgs/?%E0%B9%80%E0%B8%8A%E0%B8%B7%E0%B9%88%E0%B8%AD%E0%B8%A1%E0%B8%9A%E0%B8%B1%E0%B8%8D%E0%B8%8A%E0%B8%B5%20CME-ABCD2345' };

async function setup({ available = true, approved = false } = {}) {
  const dom = new JSDOM('<section id="communityview"><button id="communityClose"></button><div id="communityContent"></div></section>',
    { url: 'https://fixture.example/', runScripts: 'outside-only' });
  const w = dom.window as any;
  w.eval(evidence);
  const calls: any[] = [];
  let linked = false;
  const user = { id: 'fixture-user' };
  w.fetch = async (url: string, request: any) => {
    const path = url.replace('/api/community', '');
    calls.push({ path, method: request.method || 'GET' });
    if (path === '/line/link-code') linked = false;
    const data = path === '/status' ? { ready: true, email_mode: 'test' }
      : path === '/me' ? { is_admin: false, memberships: approved ? [{ ...f, status: 'approved' }] : [], preferences: { events_enabled: false, quiet_start: 21, quiet_end: 7 } }
      : path === '/line' ? { available, linked, linked_at: linked ? '2026-10-19T03:05:00+00:00' : null, basic_id: '@241mevgs', add_friend_url: code.add_friend_url }
      : path === '/line/link-code' ? code
      : [];
    return { ok: true, json: async () => data };
  };
  w.eval(workspace);
  w.CmeCommunity.init({ apiBase: '', user: () => user, session: async () => ({ user, access_token: 'fixture-only-token' }),
    forests: () => [f], catalog: async () => ({ forests: [f] }), dashboard: () => ({ data_quality: {}, hotspots: { items: [] }, pm25: { stations: [] } }),
    closeOthers() {}, activate() {}, home() {}, signin() {}, pick() {}, locate() {}, exportForest() {}, legacyPhase() {} });
  await w.CmeCommunity.open('preferences');
  await tick();
  return { dom, w, calls, link: () => { linked = true; } };
}
const click = async (w: any, action: string) => { w.document.querySelector(`[data-cw="${action}"]`).click(); await tick(); await tick(); };

it('a representative links LINE by sending a prefilled one-time code, then sees the linked state', async () => {
  const { dom, w, calls, link } = await setup({ approved: true });
  const doc = w.document;
  expect(doc.body.textContent).toContain('แจ้งเตือนทาง LINE');
  await click(w, 'line-link');
  expect(calls.some(c => c.path === '/line/link-code' && c.method === 'POST')).toBe(true);
  const anchors = [...doc.querySelectorAll('.cw-line a')] as any[];
  expect(anchors.map(a => a.href)).toEqual([code.add_friend_url, code.chat_url]);
  expect(anchors.every(a => a.target === '_blank' && a.rel === 'noopener')).toBe(true);
  expect(doc.body.textContent).toContain('CME-ABCD2345');
  link();
  await click(w, 'line-refresh');
  expect(doc.body.textContent).toContain('ผูก LINE แล้ว');
  expect(doc.body.textContent).not.toContain('CME-ABCD2345');
  expect(doc.querySelector('[data-cw="line-test"]')).toBeNull();
  dom.window.close();
});

it('says alerts start only after approval, and hides the button when LINE is not configured', async () => {
  let s = await setup({ approved: false });
  expect(s.w.document.body.textContent).toContain('หลังผู้ดูแลอนุมัติ');
  s.dom.window.close();
  s = await setup({ available: false });
  expect(s.w.document.querySelector('[data-cw="line-link"]')).toBeNull();
  expect(s.w.document.body.textContent).toContain('ยังไม่ได้เปิดใช้การแจ้งเตือนทาง LINE');
  s.dom.window.close();
});
