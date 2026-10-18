import {JSDOM} from 'jsdom';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {expect,test} from 'vitest';

const source=readFileSync(new URL('../public/spread-workspace.js',import.meta.url),'utf8');
const tick=()=>new Promise(r=>setTimeout(r,0));
function setup(){
  const dom=new JSDOM('<details id="spreadWorkspace"></details>',{runScripts:'outside-only',url:'https://test.invalid/'}),w=dom.window as any;
  Object.defineProperty(w,'crypto',{value:webcrypto});
  w.CmeEvidence={escapeHtml:(v:any)=>String(v??'').replace(/[&<>"']/g,(c:string)=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]||c)),stamp:(s:any)=>s,distanceKm:()=>0};
  w.allForests=[{forest_id:'cmf-th-2522',name:'<img onerror=x>',amphoe:'ทดสอบ'}];
  w.fetchJson=async()=>({point:{latitude:19,longitude:99,slope_deg:20,upslope_to_deg:250}});
  w.structuredClone=structuredClone;w.matchMedia=()=>({matches:true});w.eval(source);return {dom,w,form:w.document.getElementById('spreadForm')};
}
async function seed(w:any,form:any){
  w.document.getElementById('spreadWorkspace').dispatchEvent(new w.Event('toggle'));
  // Populate through the actual disclosure/click path.
  w.document.getElementById('spreadWorkspace').open=true;
  await tick();await tick();
  form.elements.forest_id.value='cmf-th-2522';
  w.document.querySelector('[data-spread-example]').click();
}
function result(request:any,sourceText='example'){
  const frames=[{minutes:30,head_distance_m:0,scenario_area_ha:0,geometry:null},{minutes:60,head_distance_m:0,scenario_area_ha:0,geometry:null}];
  const req=structuredClone(request);req.fuel.evidence.source=sourceText;
  return {inputs:{request:req,terrain:{mode:'manual',slope_deg:0,upslope_to_deg:0},ignition:{latitude:19,longitude:99}},
    cases:[{rates:{head_m_min:0,heading_to_deg:null},frames}],baseline:{frames},input_sha256:'a'.repeat(64),
    model_version:'test-model',issued_at:'2020-01-01T00:00:00Z',limitations:[sourceText]};
}

test('blank fuel cannot silently become zero; example is explicitly a foreign reference',async()=>{
  const {dom,w,form}=setup();expect(()=>w.CmeSpread.payload()).toThrow('กรอกข้อมูล');
  await seed(w,form);const p=w.CmeSpread.payload();
  expect(p.fuel.evidence.basis).toBe('reference');expect(p.fuel.evidence.source).toContain('ไม่ใช่ผลสำรวจ');
  expect(p.wind.midflame_mps).toBe(.508);expect(p.wind.evidence.basis).toBe('assumed');
  expect(p.terrain).toEqual({mode:'copernicus_forest_point'});expect(p.latitude).toBeUndefined();
  expect(form.elements.slope.disabled).toBe(true);expect(w.document.querySelector('img')).toBeNull();dom.window.close();
});

test('manual terrain needs its own values and source; partial sensitivity bounds rejected',async()=>{
  const {dom,w,form}=setup();await seed(w,form);
  form.elements.terrain_mode.value='manual';form.elements.terrain_mode.dispatchEvent(new w.Event('change',{bubbles:true}));
  expect(form.elements.slope.disabled).toBe(false);expect(()=>w.CmeSpread.payload()).toThrow('กรอกข้อมูล');
  form.elements.moisture_lo.value='';expect(()=>w.CmeSpread.payload()).toThrow('ทั้งสองค่า');dom.window.close();
});

test('an edited form cannot render or save a delayed result for older inputs',async()=>{
  const {dom,w,form}=setup();await seed(w,form);let resolve:any;
  w.fetch=()=>new Promise(r=>resolve=r);
  const p=w.CmeSpread.payload();form.dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));
  form.elements.moisture.value='8';form.elements.moisture.dispatchEvent(new w.Event('input',{bubbles:true}));
  resolve({ok:true,json:async()=>result(p)});await tick();await tick();
  expect(w.document.getElementById('spreadResult').hidden).toBe(true);
  expect(w.document.getElementById('spreadStatus').textContent).toContain('ข้อมูลถูกเปลี่ยน');dom.window.close();
});

test('output escapes evidence and preserves true model zero; changes clear the result',async()=>{
  const {dom,w,form}=setup();await seed(w,form);const p=w.CmeSpread.payload();w.CmeSpread.render(result(p,'<img src=x onerror=evil()>'));
  expect(w.document.querySelector('img')).toBeNull();
  expect(w.document.getElementById('spreadReadout').textContent).toContain('0 เมตร');
  expect(w.document.getElementById('spreadInputs').textContent).toContain('<img');
  form.elements.wind.dispatchEvent(new w.Event('input',{bubbles:true}));expect(w.document.getElementById('spreadResult').hidden).toBe(true);dom.window.close();
});

test('saving uses account session and stable IDs when the second record needs retry',async()=>{
  const {dom,w,form}=setup();await seed(w,form);w.CmeSpread.render(result(w.CmeSpread.payload()));
  w.sb={auth:{getSession:async()=>({data:{session:{access_token:'test-token'}}})}};
  const calls:any[]=[];let failModel=true;
  w.fetch=async(path:string,options:any)=>{const body=JSON.parse(options.body);calls.push({path,options,body});
    const fail=body.kind==='model'&&failModel;if(fail)failModel=false;return {ok:!fail,json:async()=>fail?{detail:'temporary failure'}:{id:body.id}};};
  w.document.getElementById('spreadSave').click();await tick();await tick();
  expect(w.document.getElementById('spreadSaveStatus').textContent).toContain('ยังบันทึกไม่ครบ');
  w.document.getElementById('spreadSave').click();await tick();await tick();
  expect(calls).toHaveLength(4);expect(calls[0].body.id).toBe(calls[2].body.id);expect(calls[1].body.id).toBe(calls[3].body.id);
  expect(calls[0].options.headers.Authorization).toBe('Bearer test-token');
  expect(calls[1].body.data.fuel_record_id).toBe(calls[0].body.id);
  expect(w.document.getElementById('spreadSaveStatus').textContent).toContain('บันทึกเชื้อเพลิงและผลแล้ว');dom.window.close();
});

test('saved results remain scoped to the chosen forest and cannot be saved again as new output',async()=>{
  const {dom,w,form}=setup();await seed(w,form);const stored=result(w.CmeSpread.payload());
  w.HTMLElement.prototype.scrollIntoView=()=>{};
  w.sb={auth:{getSession:async()=>({data:{session:{access_token:'test-token'}}})}};
  let requestPath='';w.fetch=async(path:string)=>{requestPath=path;return {ok:true,json:async()=>[{id:'saved',created_at:'2020-01-01T00:00:00Z',data:{schema:'cme-spread-scenario-v1',result:{...stored,model_version:'cme-single-dead-albini1976-ellipse-v1'}}}]};};
  w.document.getElementById('spreadSavedLoad').click();await tick();await tick();
  expect(requestPath).toContain('/forests/cmf-th-2522/research?kind=model');
  const select=w.document.getElementById('spreadSaved');select.value='saved';select.dispatchEvent(new w.Event('change'));
  expect(w.document.getElementById('spreadResult').hidden).toBe(false);
  expect(w.document.getElementById('spreadSave').disabled).toBe(true);
  expect(w.document.getElementById('spreadStatus').textContent).toContain('ไม่ได้คำนวณใหม่');
  form.elements.forest_id.dispatchEvent(new w.Event('change',{bubbles:true}));
  expect(w.document.getElementById('spreadSavedLabel').hidden).toBe(true);await tick();dom.window.close();
});

function diagnostic(hash:string){return {input_sha256:hash,scenario_issued_at:'2020-01-01T00:00:00Z',unique_observation_count:1,duplicate_count:0,nominal_point_coverage_percent:100,baseline_point_coverage_percent:100,field_arrival_sample_count:0,field_arrival_no_model_arrival_count:0,mean_absolute_arrival_error_minutes:null,baseline_mean_absolute_arrival_error_minutes:null,limitations:['synthetic test only'],observations:[{kind:'firms_detection',source:'<img src=x onerror=evil()>',latitude:19,longitude:99,elapsed_minutes:30,model_arrival_minutes:0,baseline_arrival_minutes:0,arrival_error_minutes:null}]};}
function addPoint(w:any){const f=w.document.getElementById('spreadObservation');f.elements.latitude.value='19';f.elements.longitude.value='99';f.elements.observed_at.value='2020-01-01T07:30';f.elements.source.value='synthetic browser test only';f.dispatchEvent(new w.Event('submit',{cancelable:true}));}

test('comparison sends the displayed snapshot and discards stale results after point removal',async()=>{
  const {dom,w,form}=setup();await seed(w,form);const stored=result(w.CmeSpread.payload());w.CmeSpread.render(stored);addPoint(w);
  let resolve:any,body:any;w.fetch=(_p:any,o:any)=>{body=JSON.parse(o.body);return new Promise(r=>resolve=r);};
  w.document.getElementById('spreadCompare').click();expect(body.snapshot).toEqual(stored);expect(body.scenario).toBeUndefined();
  w.document.querySelector('[data-remove-observation]').click();resolve({ok:true,json:async()=>diagnostic(stored.input_sha256)});await tick();await tick();
  expect(w.document.getElementById('spreadComparison').textContent).toBe('');expect(w.document.getElementById('spreadCompareSave').disabled).toBe(true);dom.window.close();
});

test('comparison can be saved with original model link; retry retains id and escapes sources',async()=>{
  const {dom,w,form}=setup();await seed(w,form);const stored=result(w.CmeSpread.payload());w.CmeSpread.render(stored);
  w.sb={auth:{getSession:async()=>({data:{session:{access_token:'test-token'}}})}};let fail=true;const calls:any[]=[];
  w.fetch=async(path:any,o:any)=>{const b=JSON.parse(o.body);calls.push({path,b});const isComparison=b.data?.schema==='cme-spread-evaluation-v1';if(isComparison&&fail){fail=false;return {ok:false,json:async()=>({detail:'temporary'})};}return {ok:true,json:async()=>path.includes('/evaluate-snapshot')?diagnostic(stored.input_sha256):{id:b.id}};};
  w.document.getElementById('spreadSave').click();await tick();await tick();addPoint(w);w.document.getElementById('spreadCompare').click();await tick();await tick();
  expect(w.document.querySelector('img')).toBeNull();expect(w.document.getElementById('spreadCompareSave').disabled).toBe(false);
  w.document.getElementById('spreadCompareSave').click();await tick();await tick();expect(w.document.getElementById('spreadCompareSaveStatus').textContent).toContain('ยังบันทึกไม่ได้');
  w.document.getElementById('spreadCompareSave').click();await tick();await tick();
  const saves=calls.filter(c=>c.b.data?.schema==='cme-spread-evaluation-v1');expect(saves).toHaveLength(2);expect(saves[0].b.id).toBe(saves[1].b.id);
  expect(saves[0].b.data.scenario_record_id).toBe(calls[1].b.id);expect(saves[0].b.data.observations).toHaveLength(1);
  expect(w.document.getElementById('spreadCompareSave').disabled).toBe(true);dom.window.close();
});

test('reopens a saved comparison by loading its exact parent, without simulate or evaluate',async()=>{
  const {dom,w,form}=setup();await seed(w,form);w.HTMLElement.prototype.scrollIntoView=()=>{};
  const stored={...result(w.CmeSpread.payload()),model_version:'cme-single-dead-albini1976-ellipse-v1'};
  const saved={id:'comparison-id',created_at:'2020-01-01T03:00:00Z',data:{schema:'cme-spread-evaluation-v1',scenario_record_id:'parent-id',evaluation:diagnostic(stored.input_sha256),observations:[]}};
  w.sb={auth:{getSession:async()=>({data:{session:{access_token:'test-token'}}})}};const paths:string[]=[];
  w.fetch=async(path:string)=>{paths.push(path);return {ok:true,json:async()=>path.endsWith('/parent-id')?{id:'parent-id',created_at:'2020-01-01T00:00:00Z',data:{schema:'cme-spread-scenario-v1',result:stored}}:[saved]};};
  w.document.getElementById('spreadSavedLoad').click();await tick();await tick();
  const select=w.document.getElementById('spreadSaved');select.value='comparison-id';select.dispatchEvent(new w.Event('change'));await tick();await tick();
  expect(paths).toHaveLength(2);expect(paths[1]).toContain('/forests/cmf-th-2522/research/parent-id');
  expect(w.document.getElementById('spreadCompareSaveStatus').textContent).toContain('ไม่ได้คำนวณใหม่');expect(w.document.getElementById('spreadComparison').textContent).toContain('FIRMS');
  expect(w.document.querySelector('img')).toBeNull();dom.window.close();
});
