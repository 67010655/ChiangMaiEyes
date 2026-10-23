import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const pub = (f: string) => readFileSync(resolve(__dirname, '../public', f), 'utf8');
const user = { id: 'u1' };
const incident = (over: any = {}) => ({
  id: 'inc-1', forest_id: 'f1', status: 'pending', observation: 'fire', latitude: 18.83114, longitude: 98.92345,
  observed_at: new Date(Date.now() - 14 * 864e5).toISOString(), created_at: new Date(Date.now() - 14 * 864e5 + 3 * 36e5).toISOString(),
  description: '', version: 1, coordinator_id: null, published: false, ...over,
});

// Run only the incident-page view from the source, with small stand-ins for the app's helpers.
function view() {
  const win = new JSDOM('', { runScripts: 'outside-only' }).window as any;
  win.eval(pub('decision-support.js'));
  const src = pub('community-workspace.js');
  const body = src.slice(src.indexOf('const NOW='), src.indexOf('  function fieldChecksView'));
  return win.eval(`(function(){
    const root=window, E=()=>root.CmeEvidence, esc=v=>E().escapeHtml(v), date=v=>E().stamp(v);
    const statusNames={pending:'รอตรวจสอบ',confirmed:'ยืนยันเหตุ',coordinating:'กำลังประสาน',controlled:'ควบคุมได้',closed:'ปิดเหตุ',cancelled:'ยกเลิกเหตุ',approved:'a',invited:'b',accepted:'c',declined:'d'};
    const eventNames={created:'แจ้งเหตุ'};
    const badge=s=>'<span class="cw-status '+s+'">'+statusNames[s]+'</span>';
    const ago=()=>'14 วันที่แล้ว';
    const stepper=()=>'<ol class="cw-steps"></ol>';
    const button=(label,action,extra='',primary=false)=>'<button type="button" class="cw-btn'+(primary?' primary':'')+'" data-cw="'+action+'" '+extra+'>'+label+'</button>';
    const options=()=>'', fieldChecksView=()=>'', photosView=()=>'', allowedForests=()=>[];
    let state;
    ${body}
    return {render:s=>{state=s;return detailView();}};
  })()`);
}
const st = (inc: any, over: any = {}) => ({
  session: { user }, me: { is_admin: true, memberships: [] }, catalog: [{ forest_id: 'f1', name: 'ป่าชุมชนบ้านทุ่งยาว' }], incidents: [], forestId: 'f1',
  detail: { incident: inc, events: [], partners: [], photos: [], can_manage: true, can_note: true, ...over },
});
const doc = (html: string) => new JSDOM(html).window.document;

it('leads with the question and the action buttons, in plain words', () => {
  const d = doc(view().render(st(incident())));
  expect(d.querySelector('.cw-todo h3')!.textContent).toBe('รอคนไปดู: ไฟนี้เป็นของจริงไหม?');
  expect([...d.querySelectorAll('.cw-pick')].map(b => b.textContent!.trim())).toEqual(['✅เป็นไฟจริง', '❌ไม่ใช่ไฟ']);
  expect(d.querySelector('.cw-sos a')!.getAttribute('href')).toBe('tel:1362');
  expect(d.querySelector('.cw-alert.warn')!.textContent).toContain('ค้างมา 14 วัน');
  // The question and buttons come before every detail.
  const order = [...d.querySelectorAll('.cw-todo, .cw-info, .cw-timeline, .cw-more')].map(e => e.className.split(' ')[0]);
  expect(order).toEqual(['cw-todo', 'cw-info', 'cw-timeline', 'cw-more']);
  expect(d.querySelector('.cw-claim')!.textContent).toContain('ยังไม่มีใครตามเรื่องนี้');
  expect(d.body.textContent).not.toContain('ผู้รับประสาน');
  // The status form exists for the buttons to fill in, hidden until one is picked.
  expect((d.getElementById('cwStatusForm') as HTMLFormElement).hidden).toBe(true);
});

it('each stage offers only the buttons that make sense, named by what happened', () => {
  const buttons = (inc: any) => [...doc(view().render(st(inc))).querySelectorAll('.cw-pick')].map(b => b.textContent!.trim());
  expect(buttons(incident({ status: 'confirmed' }))).toEqual(['🤝เริ่มขอความช่วยเหลือ', '🧯คุมไฟได้แล้ว', '❌ไม่ใช่ไฟ']);
  const c = doc(view().render(st(incident({ status: 'controlled', coordinator_id: 'u1' }))));
  expect([...c.querySelectorAll('.cw-pick')].map(b => b.textContent!.trim())).toEqual(['✔️จบเรื่อง', '🔥ไฟกลับมา']);
  expect((c.querySelectorAll('.cw-pick')[1] as HTMLElement).dataset.status).toBe('coordinating');
  expect(c.querySelector('.cw-claim')).toBeNull();
  expect(buttons(incident({ status: 'closed' }))).toEqual(['↩️เปิดเรื่องนี้ใหม่']);
});

it('a viewer without manage rights sees no status buttons and is told why', () => {
  const d = doc(view().render(st(incident(), { can_manage: false })));
  expect(d.querySelector('.cw-pick')).toBeNull();
  expect(d.body.textContent).toContain('ต้องเป็นผู้ที่ได้รับสิทธิ์จัดการเหตุ');
});

it('smoke reads as smoke, and the web-submit time shows only when it differs by more than 30 minutes', () => {
  const same = doc(view().render(st(incident({ observation: 'smoke', created_at: new Date(Date.now() - 14 * 864e5 + 60000).toISOString() }))));
  expect(same.querySelector('h2')!.textContent).toContain('💨 ควัน');
  expect(same.body.textContent).not.toContain('ส่งเข้าเว็บ');
  expect(doc(view().render(st(incident()))).body.textContent).toContain('ส่งเข้าเว็บ');
});
