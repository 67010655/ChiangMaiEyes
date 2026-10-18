import {readFileSync} from 'node:fs';
import {JSDOM} from 'jsdom';
import {expect,test} from 'vitest';

const source=readFileSync(new URL('../public/hindcast-workspace.js',import.meta.url),'utf8');
const report=JSON.parse(readFileSync(new URL('../../backend/app/data/season-hindcast-2026.json',import.meta.url),'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,0));
function setup(){
  const dom=new JSDOM('<details id="hindcastWorkspace"><div id="hindcastContent"></div></details>',{runScripts:'outside-only'});
  const w=dom.window as any;
  w.CmeEvidence={escapeHtml:(s:any)=>String(s??'').replace(/[&<>"']/g,(c:string)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]||c)),stamp:(s:any)=>s};
  w.AbortSignal=AbortSignal;w.eval(source);
  return {dom,w,host:w.document.getElementById('hindcastWorkspace')};
}

test('historical data loads only on opening, and a visible case is rerun through both real API contracts',async()=>{
  const {dom,w,host}=setup();const calls:any[]=[];
  w.fetch=async(path:string,options:any)=>{calls.push({path,body:options.body?JSON.parse(options.body):undefined});
    const data=path==='/api/hindcast/2026'?report:path.endsWith('/simulate')?{issued_at:'2026-10-17T00:00:00Z',marker:'snapshot'}:
      {nominal_point_coverage_percent:report.cases[0].scenarios[4].coverage_percent,unique_observation_count:report.cases[0].observation_count};
    return {ok:true,json:async()=>data};};
  expect(calls).toHaveLength(0);host.open=true;await tick();await tick();
  expect(w.document.getElementById('hindcastContent').textContent).toContain('32,376');
  w.document.getElementById('hindcastRun').click();await tick();await tick();
  expect(calls.map(c=>c.path)).toEqual(['/api/hindcast/2026','/api/spread/simulate','/api/spread/evaluate-snapshot']);
  expect(calls[1].body).toEqual(report.cases[0].scenarios[4].request);
  expect(calls[2].body.observations).toEqual(report.cases[0].observations);
  expect(w.document.getElementById('hindcastRunStatus').textContent).toContain('ตรงกับผลที่บันทึก');
  expect(w.document.getElementById('hindcastRunStatus').textContent).toContain('ยังไม่ใช่ accuracy');dom.window.close();
});

test('a delayed comparison cannot overwrite the selected historical case',async()=>{
  const {dom,w,host}=setup();let resolve:any;
  w.fetch=async(path:string)=>path==='/api/hindcast/2026'?{ok:true,json:async()=>report}:
    path.endsWith('/simulate')?{ok:true,json:async()=>({issued_at:'2026-10-17T00:00:00Z'})}:new Promise(r=>resolve=r);
  host.open=true;await tick();await tick();w.document.getElementById('hindcastRun').click();await tick();
  const select=w.document.getElementById('hindcastCase');select.value=report.cases[1].id;select.dispatchEvent(new w.Event('change'));
  resolve({ok:true,json:async()=>({nominal_point_coverage_percent:100,unique_observation_count:999})});await tick();await tick();
  expect(w.document.getElementById('hindcastRunStatus').textContent).not.toContain('999');
  expect(w.document.getElementById('hindcastCaseResult').textContent).toContain(String(report.cases[1].observation_count));dom.window.close();
});

test('missing retrospective artifact has an escaped failure and retry instead of invented zero results',async()=>{
  const {dom,w,host}=setup();w.fetch=async()=>({ok:false,json:async()=>({detail:'<img onerror=evil()> not ready'})});
  host.open=true;await tick();await tick();
  expect(w.document.querySelector('img')).toBeNull();
  expect(w.document.getElementById('hindcastContent').textContent).toContain('อ่านข้อมูลไม่ได้');
  expect(w.document.getElementById('hindcastRetry')).not.toBeNull();dom.window.close();
});
