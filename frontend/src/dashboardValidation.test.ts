import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
import {expect,test} from 'vitest';

const source=readFileSync(new URL('../public/validation-ui.js',import.meta.url),'utf8');
const report=JSON.parse(readFileSync(new URL('../../backend/app/data/dashboard-validation-2026.json',import.meta.url),'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,0));
function setup(){
  const dom=new JSDOM('<details id="validationWorkspace"><div id="validationContent"></div></details>',{runScripts:'outside-only'});
  const w=dom.window as any;w.AbortSignal=AbortSignal;
  w.CmeEvidence={escapeHtml:(s:any)=>String(s??'').replace(/[&<>"']/g,(c:string)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]||c)),stamp:(s:any)=>s};
  w.eval(source);return {dom,w,host:w.document.getElementById('validationWorkspace')};
}

test('measured scores render lazily with units and satellite coverage kept distinct',async()=>{
  const {dom,w,host}=setup();const calls:string[]=[];
  w.fetch=async(path:string)=>{calls.push(path);return {ok:true,json:async()=>report};};
  expect(calls).toHaveLength(0);host.open=true;await tick();await tick();
  const text=w.document.getElementById('validationContent').textContent;
  expect(text).toContain('13.03 µg/m³');expect(text).toContain('239/240');
  expect(text).toContain('57.05%');expect(text).toContain('ไม่ใช่ accuracy ของพื้นที่ไหม้');
  expect(text).toContain('MAE ยิ่งต่ำ');expect(calls).toEqual(['/api/hindcast/2026/validation']);
  expect(w.document.querySelectorAll('#validationPmChart polyline').length).toBeGreaterThan(1);dom.window.close();
});

test('changing case and variant updates scores and never relabels envelope as burned area',async()=>{
  const {dom,w,host}=setup();w.fetch=async()=>({ok:true,json:async()=>report});host.open=true;await tick();await tick();
  const select=w.document.getElementById('validationFireCase');select.value='2026-03-28';select.dispatchEvent(new w.Event('change'));
  const variant=w.document.getElementById('validationFireVariant');variant.value='all_initial_flat';variant.dispatchEvent(new w.Event('change'));
  const text=w.document.getElementById('validationFireReadout').textContent;
  expect(text).toContain('รู้จุดเริ่ม 2 จุด');expect(text).toContain('ตรวจพบภายหลัง 10 จุด');expect(text).toContain('375 m');
  const station=w.document.getElementById('validationPmStation');station.value='36T';station.dispatchEvent(new w.Event('change'));
  expect(w.document.querySelector('#validationPmChart svg').getAttribute('aria-label')).toContain('36T');dom.window.close();
});

test('upstream errors remain escaped and permit retry without showing fake scores',async()=>{
  const {dom,w,host}=setup();let fail=true;
  w.fetch=async()=>fail?{ok:false,json:async()=>({detail:'<img src=x onerror=evil()> unavailable'})}:{ok:true,json:async()=>report};
  host.open=true;await tick();await tick();expect(w.document.querySelector('img')).toBeNull();
  expect(w.document.getElementById('validationContent').textContent).not.toContain('13.03');
  fail=false;w.document.getElementById('validationRetry').click();await tick();await tick();
  expect(w.document.getElementById('validationContent').textContent).toContain('13.03');dom.window.close();
});
