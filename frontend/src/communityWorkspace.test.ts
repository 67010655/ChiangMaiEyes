import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';

const evidence = readFileSync(resolve(__dirname, '../public/decision-support.js'), 'utf8');
const workspace = readFileSync(resolve(__dirname, '../public/community-workspace.js'), 'utf8');
const f = { forest_id: 'fixture-A', name: 'ป่าทดสอบ <script>bad()</script>', amphoe: 'อำเภอทดสอบ', latitude: 18.85, longitude: 98.85,
  boundary: { type: 'Polygon', coordinates: [[[98.8,18.8],[98.9,18.8],[98.9,18.9],[98.8,18.9],[98.8,18.8]]] } };
const forestPublic = readFileSync(resolve(__dirname, '../public/forest-public.js'), 'utf8');
const tick = () => new Promise(resolve => setTimeout(resolve, 5));
async function setup({ signedIn = false, approved = false, failCreate = false, offline = false, nullStation = false, publicView = false, hash = '', admin = false, draft = null as any } = {}) {
  const dom = new JSDOM('<section id="communityview"><button id="communityClose"></button><div id="communityContent"></div></section>',
    { url: 'https://fixture.example/' + hash, runScripts: 'outside-only' });
  const w = dom.window as any;
  w.eval(evidence);
  if (publicView) w.eval(forestPublic);
  const calls: any[] = [];
  let user: any = signedIn ? { id: 'fixture-user' } : null;
  w.fetch = async (url: string, request: any) => {
    if (offline) throw new Error('Fixture connection lost');
    const path = url.replace('/api/community', '');
    calls.push({ path, ...request });
    const data = path === '/status' ? { ready: true, email_mode: 'test' }
      : path === '/me' ? { is_admin: admin, memberships: approved ? [{ ...f, status: 'approved' }] : [], preferences: { events_enabled: false, quiet_start: 21, quiet_end: 7 } }
      : path === '/incidents' && request.method === 'POST' ? { detail: 'Fixture network failure' }
      : path === '/review-queue' ? [{ id: 'm1', name: 'ป่าคำขอ', amphoe: 'อ', status: 'pending', request_note: 'x', email: 'fixture@example.test' }]
      : [];
    return { ok: !(path === '/incidents' && request.method === 'POST' && failCreate), json: async () => data };
  };
  if (draft) w.localStorage.setItem('cme-incident-draft-v1/fixture-user', JSON.stringify(draft));
  w.eval(workspace);
  w.CmeCommunity.init({ apiBase: '', user: () => user, session: async () => user ? { user, access_token: 'fixture-only-token' } : null,
    forests: () => [f], catalog: async () => ({ forests: [f] }), dashboard: () => ({
      data_quality: { hotspots: { source_mode: 'LIVE', is_stale: false, latest_update: new Date().toISOString() }, pm25: { source_mode: 'LIVE', is_stale: false } },
      hotspots: { items: [] }, pm25: { current_pm25: 99, stations: nullStation ? [{latitude:18.85,longitude:98.85,pm25:null}] : [{ latitude: 19.2, longitude: 99, pm25: 99 }] }
    }), closeOthers() {}, activate() {}, home() {}, signin() {}, pick() {}, locate() {}, exportForest() {}, legacyPhase() {} });
  await w.CmeCommunity.open('forest');
  return { dom, w, calls, logout: async () => { user = null; w.CmeCommunity.authChanged(); await tick(); await tick(); } };
}

describe('representative workspace interaction and evidence boundaries', () => {
  it('approved rep: my-forest view leads with status, a record button and what to do, in 3 tabs', async () => {
    const { dom } = await setup({ signedIn: true, approved: true, publicView: true });
    const doc = dom.window.document;
    expect([...doc.querySelectorAll('.cw-tabs button')].map((b: any) => b.textContent)).toEqual(['ป่าของฉัน', 'เหตุทั้งหมด', 'การแจ้งเตือน']);
    expect(doc.querySelector('.rp-head')?.textContent).toContain('ป่าที่คุณดูแล');
    expect(doc.querySelector('.fp-status.calm')).not.toBeNull();
    expect(doc.querySelector('.rp-cta [data-cw="create"]')?.textContent).toContain('บันทึกเหตุ');
    expect(doc.querySelector('.rp-todo')?.textContent).toContain('ต้องทำอะไรตอนนี้');
    expect(doc.body.textContent).not.toContain('99 µg/m³');
    expect(doc.querySelector('script')).toBeNull();
    dom.window.close();
  });
  it('an admin who represents no forest gets an overview, not a 677-forest "my forest"', async () => {
    const { dom } = await setup({ signedIn: true, admin: true, publicView: true });
    const doc = dom.window.document;
    expect([...doc.querySelectorAll('.cw-tabs button')].map((b: any) => b.textContent)).toEqual(['ภาพรวม', 'เหตุทั้งหมด', 'ตรวจคำขอ (1)', 'การแจ้งเตือน']);
    expect(doc.querySelector('.adm-stats')?.textContent).toContain('คำขอรอตรวจ');
    expect(doc.getElementById('cwActiveForest')).toBeNull();
    expect(doc.getElementById('fpSearch')).not.toBeNull();
    dom.window.close();
  });
  it('one forest: the record form names it instead of asking again; no experimental button anywhere', async () => {
    const { dom, w } = await setup({ signedIn: true, approved: true, publicView: true });
    const doc = dom.window.document;
    doc.querySelector('.rp-cta [data-cw="create"]')!.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await tick();
    expect(doc.querySelector('#cwIncidentForm select[name="forest_id"]')).toBeNull();
    expect((doc.querySelector('#cwIncidentForm input[name="forest_id"]') as any).value).toBe('fixture-A');
    expect(doc.querySelector('.cw-for')?.textContent).toContain('บันทึกให้');
    await w.CmeCommunity.open('incidents');
    expect(doc.querySelector('[data-cw="legacy-phase"]')).toBeNull();
    expect(doc.querySelectorAll('[data-cw="scope"]').length).toBe(2);
    dom.window.close();
  });
  it('a draft older than 3 hours is offered, not silently reused', async () => {
    const draft = { id: 'old', forest_id: 'fixture-A', observation: 'fire', observed_local: '2026-10-16T23:32', latitude: '18.85', longitude: '98.85', description: 'old note', saved_at: '2026-10-16T16:32:00Z' };
    const { dom, w } = await setup({ signedIn: true, approved: true, publicView: true, draft });
    const doc = dom.window.document;
    doc.querySelector('.rp-cta [data-cw="create"]')!.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await tick();
    expect((doc.querySelector('[name="observed_local"]') as any).value).not.toBe('2026-10-16T23:32');
    expect(doc.querySelector('.cw-alert')?.textContent).toContain('มีร่างที่ยังไม่ได้ส่ง');
    doc.querySelector('[data-cw="old-draft-use"]')!.dispatchEvent(new w.MouseEvent('click', { bubbles: true }));
    await tick();
    expect((doc.querySelector('[name="description"]') as any).value).toBe('old note');
    dom.window.close();
  });
  it('a shared forest link opens that forest card for everyone', async () => {
    const { dom } = await setup({ publicView: true, hash: '#community/forest/fixture-A' });
    await tick(); await tick();
    const doc = dom.window.document;
    expect(doc.getElementById('communityview')?.classList.contains('open')).toBe(true);
    expect(doc.querySelector('.fp-card')).not.toBeNull();
    expect(doc.querySelector('.fp-current')?.textContent).toContain('ป่าทดสอบ');
    dom.window.close();
  });
  it('signed out: everyone sees the forest lookup, no rep tabs, and still no private requests', async () => {
    const { dom, calls } = await setup({ publicView: true });
    const doc = dom.window.document;
    expect(doc.querySelector('.cw-tabs')).toBeNull();
    expect(doc.getElementById('fpSearch')).not.toBeNull();
    expect(doc.body.textContent).toContain('เป็นตัวแทนป่าชุมชน?');
    expect(doc.querySelector('[data-cw="signin"]')).not.toBeNull();
    expect(doc.querySelector('script')).toBeNull();
    expect(calls.some(call => call.path === '/me' || call.path === '/incidents')).toBe(false);
    dom.window.close();
  });
  it('shows a retryable failure instead of an endless loading state when the first request fails', async () => {
    const { dom } = await setup({ offline: true });
    expect(dom.window.document.body.textContent).toContain('Fixture connection lost');
    expect(dom.window.document.body.textContent).toContain('ระบบข้อมูลชุมชนยังไม่พร้อม');
    expect(dom.window.document.body.textContent).not.toContain('กำลังโหลดข้อมูลพื้นที่');
    dom.window.close();
  });
  it('does not request private records while signed out', async () => {
    const { dom, calls } = await setup();
    expect(dom.window.document.body.textContent).toContain('พื้นที่สำหรับตัวแทนป่าชุมชน');
    expect(calls.every(call => !call.headers.Authorization)).toBe(true);
    expect(calls.some(call => call.path === '/me' || call.path === '/incidents')).toBe(false);
    dom.window.close();
  });
  it('shows an approval request rather than a report form for an unapproved account', async () => {
    const { dom, calls } = await setup({ signedIn: true });
    expect(dom.window.document.getElementById('cwMembershipForm')).not.toBeNull();
    expect(dom.window.document.getElementById('cwIncidentForm')).toBeNull();
    expect(calls.find(call => call.path === '/me').headers.Authorization).toBe('Bearer fixture-only-token');
    expect(dom.window.document.querySelector('script')).toBeNull();
    dom.window.close();
  });
  it('does not substitute provincial PM for an unmeasured forest and escapes forest names', async () => {
    const { dom } = await setup({ signedIn: true, approved: true });
    expect(dom.window.document.body.textContent).toContain('ไม่มีสถานีที่ใช้ได้');
    expect(dom.window.document.body.textContent).not.toContain('99 µg/m³');
    expect(dom.window.document.querySelector('script')).toBeNull();
    dom.window.close();
  });
  it('retains the same draft request ID on failure, allowing an idempotent retry', async () => {
    const { dom, w, calls } = await setup({ signedIn: true, approved: true, failCreate: true });
    await w.CmeCommunity.newIncident({ lat: 18.85, lon: 98.85 });
    const form = dom.window.document.getElementById('cwIncidentForm')!;
    form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }));
    await tick();await tick();
    const first = JSON.parse(calls.find(call => call.method === 'POST' && call.path === '/incidents').body);
    expect(dom.window.document.body.textContent).toContain('Fixture network failure');
    const next = dom.window.document.getElementById('cwIncidentForm')!;
    next.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }));
    await tick();await tick();
    const attempts = calls.filter(call => call.method === 'POST' && call.path === '/incidents');
    expect(JSON.parse(attempts[1].body).id).toBe(first.id);
    expect(first.observed_at.endsWith('+07:00')).toBe(true);
    expect(w.localStorage.length).toBe(1);
    dom.window.close();
  });
  it('does not convert a missing station reading inside the forest into zero PM',async()=>{
    const {dom}=await setup({signedIn:true,approved:true,nullStation:true});
    expect(dom.window.document.body.textContent).toContain('ไม่มีสถานีที่ใช้ได้');
    expect(dom.window.document.body.textContent).not.toContain('0 µg/m³');dom.window.close();
  });
  it('retains an unsent membership explanation when a refresh rerenders the form',async()=>{
    const {dom,w}=await setup({signedIn:true});
    const note=dom.window.document.querySelector<HTMLTextAreaElement>('#cwMembershipForm textarea')!;
    note.value='Fixture explanation to keep';note.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
    await w.CmeCommunity.open('forest');
    expect(dom.window.document.querySelector<HTMLTextAreaElement>('#cwMembershipForm textarea')!.value).toBe('Fixture explanation to keep');
    dom.window.close();
  });
  it('removes private content immediately on sign out', async () => {
    const { dom, logout } = await setup({ signedIn: true, approved: true });
    expect(dom.window.document.getElementById('cwActiveForest')).not.toBeNull();
    await logout();
    expect(dom.window.document.getElementById('cwActiveForest')).toBeNull();
    expect(dom.window.document.body.textContent).toContain('พื้นที่สำหรับตัวแทนป่าชุมชน');
    dom.window.close();
  });
  it('clears the hidden workspace before switching to an export or another view', async () => {
    const { dom,w,logout } = await setup({ signedIn:true,approved:true });
    w.CmeCommunity.hide();
    expect(dom.window.document.getElementById('communityview')?.classList.contains('open')).toBe(false);
    expect(dom.window.document.getElementById('communityContent')?.textContent).toBe('');
    await logout();
    expect(dom.window.document.getElementById('communityContent')?.textContent).toBe('');
    dom.window.close();
  });
});
