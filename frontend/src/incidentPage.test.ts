import { JSDOM } from 'jsdom';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, it } from 'vitest';

const pub = (f: string) => readFileSync(resolve(__dirname, '../public', f), 'utf8');

// Run only the incident page from the source, with small stand-ins for the app's helpers.
function view() {
  const win = new JSDOM('', { runScripts: 'outside-only' }).window as any;
  win.eval(pub('decision-support.js'));
  win.eval(pub('incident-pins.js'));
  const src = pub('community-workspace.js');
  const body = src.slice(src.indexOf('  const OPEN_STATES='), src.indexOf('  function fieldChecksView'));
  return win.eval(`(function(){
    const root=window, E=()=>root.CmeEvidence, esc=v=>E().escapeHtml(v), date=v=>E().stamp(v);
    const statusNames={pending:'รอตรวจสอบ',closed:'ปิดเหตุ',cancelled:'ยกเลิกเหตุ'};
    const eventNames={created:'แจ้งเหตุ',status:'เปลี่ยนสถานะ',note:'บันทึกเพิ่มเติม',expired:'ปิดอัตโนมัติ'};
    const ago=()=>'3 ชม.ที่แล้ว';
    const button=(label,action,extra='',primary=false)=>'<button type="button" class="cw-btn'+(primary?' primary':'')+'" data-cw="'+action+'" '+extra+'>'+label+'</button>';
    const fieldChecksView=()=>'<i id="fc"></i>', photosView=()=>'<i id="ph"></i>';
    let state;
    ${body}
    return {render:s=>{state=s;return detailView();}};
  })()`);
}
const incident = (over: any = {}) => ({
  id: 'inc-1', forest_id: 'f1', status: 'pending', observation: 'fire', latitude: 18.83114, longitude: 98.92345, created_by: 'u9',
  observed_at: new Date(Date.now() - 4 * 36e5).toISOString(), created_at: new Date(Date.now() - 3 * 36e5).toISOString(),
  description: 'ไฟกำลังไหม้ใกล้ลำห้วย', contact_phone: null, nearby: null, ...over,
});
const st = (inc: any, { me = 'u1', admin = false, canNote = true, events }: any = {}) => ({
  session: { user: { id: me } }, me: { is_admin: admin, memberships: [] }, catalog: [{ forest_id: 'f1', name: 'ป่าชุมชนบ้านทดสอบ' }], forestId: 'f1',
  detail: { incident: inc, can_note: canNote, partners: [], photos: [], events: events ?? [{ kind: 'created', actor_name: 'สมชาย', note: 'x', created_at: inc.created_at }] },
});
const doc = (html: string) => new JSDOM(html).window.document;

it('the reporter sees what the pin means, the two ways to end it, and nothing about coordinating', () => {
  const d = doc(view().render(st(incident({ created_by: 'u1', contact_phone: '081-234-5678' }), { me: 'u1' })));
  expect(d.querySelector('.cw-todo h3')!.textContent).toBe('หมุดนี้ยังอยู่บนแผนที่ของตัวแทนป่าทุกคน');
  expect([...d.querySelectorAll('.cw-pick')].map(b => b.textContent!.trim())).toEqual(['✅จบงาน', '❌ไม่ใช่ไฟ']);
  expect(d.querySelector('.cw-sos a')!.getAttribute('href')).toBe('tel:1362');
  expect(d.querySelector('.cw-sos')!.textContent).toMatch(/หมุดจะหายเองในอีก/);
  expect(d.querySelector('.cw-info')!.textContent).toContain('คุณ');
  expect(d.querySelector('.cw-info a')!.getAttribute('href')).toBe('tel:0812345678');
  // The question and the buttons come before every detail.
  expect([...d.querySelectorAll('.cw-todo, .cw-info, .cw-timeline, .cw-more')].map(e => e.className.split(' ')[0])).toEqual(['cw-todo', 'cw-info', 'cw-timeline', 'cw-more']);
  for (const old of ['ผู้รับประสาน', 'รับเรื่อง', 'ขอให้ป่า', 'cw-steps', 'cwPartnerForm', 'cwMergeForm']) expect(d.body.innerHTML).not.toContain(old);
  // Ending needs no reason: the note box is optional and hidden until a button is pressed.
  const form = d.getElementById('cwStatusForm') as HTMLFormElement;
  expect(form.hidden).toBe(true);
  expect(form.querySelector('textarea')!.hasAttribute('required')).toBe(false);
});

it('another rep reads the pin but cannot end it; an admin can', () => {
  const rep = doc(view().render(st(incident(), { me: 'u1' })));
  expect(rep.querySelector('.cw-pick')).toBeNull();
  expect(rep.querySelector('.cw-todo h3')!.textContent).toContain('ผู้แจ้งเป็นคนกดจบงาน');
  expect(rep.querySelector('.cw-info')!.textContent).toContain('สมชาย');
  const admin = doc(view().render(st(incident(), { me: 'u1', admin: true })));
  expect(admin.querySelectorAll('.cw-pick')).toHaveLength(2);
});

it('an ended incident says so, offers nothing more, and keeps the history', () => {
  for (const [status, lead] of [['closed', 'จบงานแล้ว'], ['cancelled', 'ไม่ใช่ไฟ']]) {
    const d = doc(view().render(st(incident({ status, created_by: 'u1' }), { me: 'u1' })));
    expect(d.querySelector('.cw-todo h3')!.textContent).toContain(lead);
    expect(d.querySelector('.cw-pick')).toBeNull();
    expect(d.getElementById('cwNoteForm')).toBeNull();
    expect(d.querySelector('.cw-timeline li')).not.toBeNull();
  }
});

it('lists the forests near the point, marks the ones at risk, and names the system when it closes a pin', () => {
  const nearby = [{ forest_id: 'f1', name: 'ป่าของผู้แจ้ง', km: 0, risk: false, reporter: true }, { forest_id: 'f2', name: 'ป่าเสี่ยง', km: 2.3, risk: true, reporter: false }];
  const events = [{ kind: 'created', actor_name: 'สมชาย', note: '', created_at: new Date().toISOString() },
    { kind: 'expired', actor_name: 'ระบบอัตโนมัติ', note: 'ครบ 3 วัน', created_at: new Date().toISOString() }];
  const d = doc(view().render(st(incident({ nearby, status: 'closed' }), { events })));
  const rows = [...d.querySelectorAll('.pin-near li')].map(li => li.textContent!.replace(/\s+/g, ' ').trim());
  expect(rows).toEqual(['ป่าของผู้แจ้ง อยู่ในขอบเขตป่า ป่าของผู้แจ้ง', 'ป่าเสี่ยง 2.3 กม. เสี่ยง · ใกล้ไม่เกิน 5 กม.']);
  expect([...d.querySelectorAll('.cw-timeline strong')].map(e => e.textContent)).toEqual(['แจ้งเหตุ', 'ปิดอัตโนมัติ (ครบ 3 วัน)']);
});

it('escapes text from other people', () => {
  const d = doc(view().render(st(incident({ description: '<img src=x onerror=alert(1)>' }), { events: [{ kind: 'created', actor_name: '<b>x</b>', note: '', created_at: new Date().toISOString() }] })));
  expect(d.querySelector('.cw-info img')).toBeNull();
  expect(d.querySelector('.cw-info b')).toBeNull();
});
